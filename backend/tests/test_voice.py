"""Voice layer regressions: sentence splitting, speakable text, provider
factories, and the push-to-talk WebSocket protocol end to end (stub STT/TTS
+ a canned run_turn, so no model or LLM is touched)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.storage_sandbox import StorageSandboxTestCase

from app.voice.sentences import split_sentences, take_complete
from app.voice.speak_text import to_speakable
from app.voice.wav import pcm16_to_wav, wav_to_pcm16


class TestSentenceSplitting(unittest.TestCase):
    def test_chinese_terminators(self):
        self.assertEqual(split_sentences("你好。这是两句！还有；分号？"),
                         ["你好。", "这是两句！", "还有；", "分号？"])

    def test_ascii_dot_rules(self):
        parts = split_sentences("英文 fine. Next one. 小数 3.14 不切")
        self.assertEqual(parts, ["英文 fine.", "Next one.", "小数 3.14 不切"])

    def test_streaming_take_complete_keeps_remainder(self):
        complete, rest = take_complete("第一句完整。第二句还没说")
        self.assertEqual(complete, ["第一句完整。"])
        self.assertEqual(rest, "第二句还没说")
        complete, rest = take_complete(rest + "完了吗？")
        self.assertEqual(complete, ["第二句还没说完了吗？"])
        self.assertEqual(rest, "")

    def test_force_split_long_runon(self):
        parts = split_sentences("字" * 300)
        self.assertTrue(all(len(p) <= 121 for p in parts))
        self.assertGreaterEqual(sum(len(p) for p in parts), 300)

    def test_math_span_blocks_split(self):
        text = "定义为\n$$\\int_{-1}^{1} x. y$$\n所以收敛。下一段"
        complete, rest = take_complete(text)
        self.assertEqual(complete, ["定义为\n$$\\int_{-1}^{1} x. y$$\n所以收敛。"])
        self.assertEqual(rest, "下一段")

    def test_inline_math_decimal_intact(self):
        complete, rest = take_complete("圆周率是 $3.14$ 与 $2.71$。好了")
        self.assertEqual(complete, ["圆周率是 $3.14$ 与 $2.71$。"])
        self.assertEqual(rest, "好了")

    def test_unclosed_math_holds_buffer(self):
        complete, rest = take_complete("例如 $x^2 还没")
        self.assertEqual(complete, [])
        self.assertIn("$x^2", rest)


class TestSpeakText(unittest.TestCase):
    def test_markdown_stripped(self):
        out = to_speakable("## 标题\n\n**重点**与*强调*，[链接](http://x)，`x = 1`")
        self.assertNotIn("#", out)
        self.assertNotIn("**", out)
        self.assertNotIn("[", out)
        self.assertIn("重点", out)
        self.assertIn("链接", out)
        self.assertIn("x 等于 1", out)

    def test_code_fence_placeholder(self):
        out = to_speakable("看代码：\n```python\nprint(1)\n```\n结束。")
        self.assertNotIn("print", out)
        self.assertIn("代码", out)

    def test_math_readings(self):
        out = to_speakable("$\\frac{1}{2}$ 加 $\\sqrt{2}$ 等于多少？")
        self.assertIn("2分之1", out)
        self.assertIn("根号2", out)

    def test_math_equation_speakable(self):
        out = to_speakable("$a^2 + b^2 = c^2$")
        self.assertIn("的2次方", out)
        self.assertIn("等于", out)
        self.assertNotIn("$", out)
        self.assertNotIn("\\", out)

    def test_prose_dash_survives(self):
        out = to_speakable("well-known method，但是 x-1 会读成减，3-x 也是")
        self.assertIn("well-known", out)
        self.assertIn("x减1", out)
        self.assertIn("3减x", out)

    def test_display_math_multiline(self):
        out = to_speakable("定义为\n$$\\int_{-1}^{1}\\frac{1}{x^2} dx$$\n的情形。")
        self.assertNotIn("$", out)
        self.assertNotIn("\\int", out)
        self.assertIn("积分", out)
        self.assertIn("分之", out)

    def test_stray_dollars_stripped(self):
        out = to_speakable("费用是 $5 与 $$ 残留")
        self.assertNotIn("$", out)

    def test_bare_subscript_reading(self):
        out = to_speakable("当 $x_1$ 增大时")
        self.assertIn("x下标1", out)


class TestWavHelpers(unittest.TestCase):
    def test_roundtrip(self):
        pcm = b"\x01\x02" * 1600
        wav = pcm16_to_wav(pcm, 16000)
        out, rate = wav_to_pcm16(wav)
        self.assertEqual(out, pcm)
        self.assertEqual(rate, 16000)


class TestProviderFactories(unittest.TestCase):
    def tearDown(self) -> None:
        from app.voice.stt import reset_stt_provider
        from app.voice.tts import reset_tts_provider
        reset_stt_provider()
        reset_tts_provider()

    def test_off_by_default(self):
        from app.core.config import settings
        from app.voice.stt import get_stt_provider
        from app.voice.tts import get_tts_provider
        with patch.object(settings, "voice_stt_provider", "off"), \
                patch.object(settings, "voice_tts_provider", "off"):
            self.assertIsNone(get_stt_provider())
            self.assertIsNone(get_tts_provider())

    def test_stub_providers(self):
        from app.core.config import settings
        from app.voice.stt import get_stt_provider
        from app.voice.tts import get_tts_provider
        with patch.object(settings, "voice_stt_provider", "stub"), \
                patch.object(settings, "voice_tts_provider", "stub"):
            self.assertEqual(get_stt_provider().name, "stub")
            self.assertEqual(get_tts_provider().name, "stub")

    def test_whisper_missing_files_fail_open(self):
        from app.core.config import settings
        from app.voice.stt import get_stt_provider
        with patch.object(settings, "voice_stt_provider", "whisper"), \
                patch.object(settings, "voice_whisper_bin", "/nonexistent/whisper-cli"), \
                patch.object(settings, "voice_whisper_model", "/nonexistent/model.bin"):
            self.assertIsNone(get_stt_provider())


class TestVoiceWebSocket(StorageSandboxTestCase):
    """Full protocol walk with stub providers and a canned run_turn."""

    def setUp(self) -> None:
        super().setUp()
        from app.core.config import settings
        from app.voice.stt import reset_stt_provider
        from app.voice.tts import reset_tts_provider
        self._reset = (reset_stt_provider, reset_tts_provider)
        patches = [
            patch.object(settings, "voice_stt_provider", "stub"),
            patch.object(settings, "voice_tts_provider", "stub"),
        ]
        for p in patches:
            p.start()
        self._patches += patches

        from app.main import create_app
        from fastapi.testclient import TestClient
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self._reset[0]()
        self._reset[1]()
        super().tearDown()

    async def _canned_turn(self, user_message, session, tools, llm=None,
                           progress_cb=None, lang="zh", output_language=None,
                           attachments=None, student_id=""):
        yield {"type": "step", "step": "thinking"}
        yield {"type": "answer", "content": "勾股定理是对的。", "is_delta": True}
        yield {"type": "answer", "content": "两直角边的平方和等于斜边平方！", "is_delta": True}
        from app.core.session import save_session
        save_session(session)
        yield {"type": "done", "thinking": "", "answer": "…",
               "tool_calls": [], "trace_id": "trace_voice_test"}

    # -- helpers -----------------------------------------------------------

    def _ticket(self) -> str:
        resp = self.client.post("/api/v1/voice/ticket")
        self.assertEqual(resp.status_code, 200)
        return resp.json()["ticket"]

    def _speak_half_second(self) -> bytes:
        return b"\x00\x01" * 1600  # 0.1 s of PCM16 at 16 kHz

    # -- tests -------------------------------------------------------------

    def test_status_reflects_providers(self):
        data = self.client.get("/api/v1/voice/status").json()
        self.assertTrue(data["enabled"])
        self.assertEqual(data["stt"], "stub")

    def test_full_turn_over_ws(self):
        with patch("app.agents.chat_agent.run_turn", self._canned_turn):
            with self.client.websocket_connect(
                    f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
                ws.send_json({"type": "start", "session_id": None})
                bound = ws.receive_json()
                self.assertEqual(bound["type"], "session_bound")
                sid = bound["session_id"]

                ws.send_bytes(self._speak_half_second())
                ws.send_json({"type": "utterance_end"})

                self.assertEqual(ws.receive_json()["type"], "stt_start")
                stt = ws.receive_json()
                self.assertEqual(stt["type"], "stt_result")
                self.assertTrue(stt["text"])

                events = []
                first_error = None
                while True:
                    msg = ws.receive()
                    if "bytes" in msg and msg["bytes"] is not None:
                        events.append(("audio", len(msg["bytes"])))
                        continue
                    text = msg.get("text")
                    if text is None:
                        continue
                    import json as _json
                    ev = _json.loads(text)
                    events.append(ev["type"])
                    if ev["type"] == "error":
                        first_error = ev
                        break
                    if ev["type"] == "turn_end":
                        self.assertEqual(ev["session_id"], sid)
                        self.assertTrue(ev["tts_ok"])
                        break
                self.assertIsNone(first_error, f"unexpected error event: {first_error}")

        self.assertIn("step", events)
        self.assertEqual(events.count("answer_delta"), 2)
        # Both sentences were spoken: two tts_start/bytes/tts_end triples.
        self.assertEqual(events.count("tts_start"), 2)
        audio_frames = [e for e in events if isinstance(e, tuple)]
        self.assertEqual(len(audio_frames), 2)
        self.assertTrue(all(size > 0 for _tag, size in audio_frames))
        self.assertEqual(events.count("tts_end"), 2)

        # The turn persisted into the sandboxed session store.
        from app.agents.student_model.store import DEFAULT_STUDENT_ID
        from app.core.session import load_session
        session = load_session(sid)
        self.assertIsNotNone(session)
        self.assertEqual(session.student_id, DEFAULT_STUDENT_ID)

    def test_ticket_is_single_use(self):
        ticket = self._ticket()
        with self.client.websocket_connect(f"/api/v1/voice/ws?ticket={ticket}"):
            pass
        # A replayed ticket must be rejected before the protocol starts.
        with self.assertRaises(Exception):
            with self.client.websocket_connect(f"/api/v1/voice/ws?ticket={ticket}"):
                pass

    def test_bad_ticket_rejected(self):
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/api/v1/voice/ws?ticket=nope"):
                pass

    def test_header_auth_skips_ticket(self):
        from app.identity import store as id_store
        from app.identity.security import create_token, hash_password
        user = id_store.create_user("voice@test.local", "voice",
                                    hash_password("pw123456"))
        tok = create_token(user.id)
        with self.client.websocket_connect(
                "/api/v1/voice/ws",
                headers={"Authorization": f"Bearer {tok}"}) as ws:
            ws.send_json({"type": "ping"})
            self.assertEqual(ws.receive_json()["type"], "pong")

    def test_too_short_audio(self):
        with self.client.websocket_connect(
                f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
            ws.send_json({"type": "start", "session_id": None})
            ws.receive_json()
            ws.send_json({"type": "utterance_end"})
            ev = ws.receive_json()
            self.assertEqual(ev["type"], "error")
            self.assertEqual(ev["code"], "too_short")

    def test_truncated_audio_warns(self):
        from app.core.config import settings
        with patch.object(settings, "voice_max_audio_seconds", 5):
            with self.client.websocket_connect(
                    f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
                ws.send_json({"type": "start", "session_id": None})
                ws.receive_json()
                ws.send_bytes(b"\x00\x00" * (16000 * 6))  # 6 s > 5 s cap
                ws.send_json({"type": "utterance_end"})
                ev = ws.receive_json()
                self.assertEqual(ev, {"type": "warning",
                                      "code": "audio_truncated",
                                      "max_seconds": 5})

    def test_foreign_session_invisible(self):
        from app.core.session import TutorSession, save_session
        other = TutorSession(grade="")
        other.student_id = "usr_somebodyelse"
        other.session_id = "sess_foreign_voice"
        save_session(other)
        with self.client.websocket_connect(
                f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
            ws.send_json({"type": "start", "session_id": "sess_foreign_voice"})
            ev = ws.receive_json()
            self.assertEqual(ev["type"], "error")
            self.assertEqual(ev["code"], "session_not_found")

    def test_end_control_closes(self):
        with self.client.websocket_connect(
                f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
            ws.send_json({"type": "start", "session_id": None})
            ws.receive_json()
            ws.send_json({"type": "end"})
            self.assertEqual(ws.receive_json()["type"], "bye")


if __name__ == "__main__":
    unittest.main()
