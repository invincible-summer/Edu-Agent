"""Voice layer regressions for browser text input and MeloTTS output."""
from __future__ import annotations

import io
import math
import json
import struct
import wave
import unittest
from array import array
from unittest.mock import patch

from tests.storage_sandbox import StorageSandboxTestCase

from app.voice.sentences import split_sentences, take_complete
from app.voice.speak_text import to_speakable
from app.voice.wav import wav_to_pcm16


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

    def test_math_degree_not_power(self):
        out = to_speakable("角 $30^\\circ$ 是锐角")
        self.assertIn("30度", out)
        self.assertNotIn("次方", out)

    def test_math_function_names(self):
        out = to_speakable("$\\sin x + \\cos x$")
        self.assertIn("正弦", out)
        self.assertIn("余弦", out)
        self.assertNotIn("sin", out)
        self.assertNotIn("\\", out)

    def test_nested_frac_reads_inside_out(self):
        out = to_speakable("$\\frac{\\sqrt{2}}{2}$")
        self.assertIn("2分之根号2", out)

    def test_mathbb_set_names(self):
        out = to_speakable("$x \\in \\mathbb{R}$")
        self.assertIn("属于", out)
        self.assertIn("实数集", out)

    def test_percent_reading(self):
        out = to_speakable("增长 $50\\%$")
        self.assertIn("百分之50", out)

    def test_nth_root_reading(self):
        out = to_speakable("$\\sqrt[3]{8}$")
        self.assertIn("3次根号8", out)

    def test_text_group_keeps_content(self):
        out = to_speakable("$\\text{当 } x > 0 \\text{ 时递增}$")
        self.assertIn("当", out)
        self.assertIn("时递增", out)
        self.assertNotIn("text", out)

    def test_infty_and_tendency(self):
        out = to_speakable("$x \\to \\infty$")
        self.assertIn("趋于", out)
        self.assertIn("无穷", out)

    def test_combined_sum_bounds(self):
        out = to_speakable("$\\sum_{i=1}^{n} i$")
        self.assertIn("求和，从i等于1到n", out)

    def test_vec_and_bar_readings(self):
        out = to_speakable("$\\vec{a}$、$\\bar{x}$")
        self.assertIn("向量a", out)
        self.assertIn("x拔", out)




class TestWavHelpers(unittest.TestCase):
    def test_decode_sidecar_wav(self):
        pcm = b"\x01\x02" * 1600
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(44100)
            wav_file.writeframes(pcm)
        out, rate = wav_to_pcm16(buf.getvalue())
        self.assertEqual(out, pcm)
        self.assertEqual(rate, 44100)


class TestVoiceWebSocket(StorageSandboxTestCase):
    """Browser text protocol with a canned run_turn and stub TTS."""

    def setUp(self) -> None:
        super().setUp()
        from app.core.config import settings
        from app.voice.tts import reset_tts_provider
        self._reset_tts = reset_tts_provider
        patcher = patch.object(settings, "voice_tts_provider", "stub")
        patcher.start()
        self._patches.append(patcher)

        from app.main import create_app
        from fastapi.testclient import TestClient
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self._reset_tts()
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

    def _ticket(self) -> str:
        resp = self.client.post("/api/v1/voice/ticket")
        self.assertEqual(resp.status_code, 200)
        return resp.json()["ticket"]

    def _receive_turn(self, ws, session_id):
        events = []
        while True:
            msg = ws.receive()
            if msg.get("bytes") is not None:
                events.append(("audio", len(msg["bytes"])))
                continue
            if msg.get("text") is None:
                continue
            event = json.loads(msg["text"])
            events.append(event["type"])
            if event["type"] == "error":
                self.fail(f"unexpected error event: {event}")
            if event["type"] == "turn_end":
                self.assertEqual(event["session_id"], session_id)
                self.assertTrue(event["tts_ok"])
                return events

    def test_status_reports_browser_stt_and_tts(self):
        data = self.client.get("/api/v1/voice/status").json()
        self.assertEqual(data, {"enabled": True, "stt": "browser", "tts": "stub"})

    def test_status_disabled_tts_still_reports_browser_stt(self):
        from app.core.config import settings
        from app.voice.tts import reset_tts_provider

        with patch.object(settings, "voice_tts_provider", "off"):
            reset_tts_provider()
            data = self.client.get("/api/v1/voice/status").json()
        reset_tts_provider()
        self.assertEqual(data, {"enabled": False, "stt": "browser", "tts": None})

    def test_text_turn_without_pcm(self):
        with patch("app.agents.chat_agent.run_turn", self._canned_turn):
            with self.client.websocket_connect(
                    f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
                ws.send_json({"type": "start", "session_id": None})
                bound = ws.receive_json()
                self.assertEqual(bound["type"], "session_bound")
                sid = bound["session_id"]
                ws.send_json({"type": "utterance_end", "text": "我是谁"})
                self.assertEqual(ws.receive_json(), {"type": "stt_start"})
                self.assertEqual(ws.receive_json(),
                                 {"type": "stt_result", "text": "我是谁"})
                events = self._receive_turn(ws, sid)

        self.assertIn("answer_delta", events)
        self.assertEqual(events.count("answer_delta"), 2)
        self.assertEqual(events.count("tts_start"), 2)
        self.assertEqual(events.count("tts_end"), 2)
        audio_frames = [event for event in events if isinstance(event, tuple)]
        self.assertEqual(len(audio_frames), 2)
        self.assertTrue(all(size > 0 for _tag, size in audio_frames))

        from app.agents.student_model.store import DEFAULT_STUDENT_ID
        from app.core.session import load_session
        persisted = load_session(sid)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.student_id, DEFAULT_STUDENT_ID)

    def test_tts_failure_keeps_text_turn_alive(self):
        from app.voice.base import VoiceProviderError

        async def failing_synthesize(_provider, text, *, speed=None):
            raise VoiceProviderError("sidecar down", code="tts_unavailable")

        with patch("app.agents.chat_agent.run_turn", self._canned_turn), \
                patch("app.voice.tts.stub.StubTTS.synthesize", failing_synthesize):
            with self.client.websocket_connect(
                    f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
                ws.send_json({"type": "start", "session_id": None})
                sid = ws.receive_json()["session_id"]
                ws.send_json({"type": "utterance_end", "text": "我是谁"})
                events = []
                tts_ok = None
                while True:
                    msg = ws.receive()
                    if msg.get("bytes") is not None:
                        self.fail("a failed TTS provider must not emit audio")
                    event = json.loads(msg["text"])
                    events.append(event)
                    if event["type"] == "turn_end":
                        tts_ok = event["tts_ok"]
                        self.assertEqual(event["session_id"], sid)
                        break

        self.assertTrue(any(e["type"] == "answer_delta" for e in events))
        self.assertEqual(sum(e["type"] == "tts_error" for e in events), 1)
        self.assertFalse(tts_ok)
        self.assertFalse(any(e["type"] == "error" for e in events))

    def test_binary_audio_is_rejected_without_stt_fallback(self):
        with self.client.websocket_connect(
                f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
            ws.send_json({"type": "start", "session_id": None})
            self.assertEqual(ws.receive_json()["type"], "session_bound")
            ws.send_bytes(b"not an accepted input frame")
            self.assertEqual(ws.receive_json(), {
                "type": "error", "code": "binary_audio_unsupported"})

    def test_empty_text_returns_empty_transcript(self):
        with self.client.websocket_connect(
                f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
            ws.send_json({"type": "start", "session_id": None})
            self.assertEqual(ws.receive_json()["type"], "session_bound")
            ws.send_json({"type": "utterance_end", "text": "  "})
            self.assertEqual(ws.receive_json(), {"type": "stt_start"})
            self.assertEqual(ws.receive_json(),
                             {"type": "error", "code": "empty_transcript"})

    def test_ticket_is_single_use(self):
        ticket = self._ticket()
        with self.client.websocket_connect(f"/api/v1/voice/ws?ticket={ticket}"):
            pass
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
        token = create_token(user.id)
        with self.client.websocket_connect(
                "/api/v1/voice/ws",
                headers={"Authorization": f"Bearer {token}"}) as ws:
            ws.send_json({"type": "ping"})
            self.assertEqual(ws.receive_json()["type"], "pong")

    def test_busy_rejects_overlapping_text_turn(self):
        async def pending_turn(*args, **kwargs):
            yield {"type": "answer", "content": "未完成"}
            await asyncio.sleep(0.2)

        import asyncio
        with patch("app.agents.chat_agent.run_turn", pending_turn):
            with self.client.websocket_connect(
                    f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
                ws.send_json({"type": "start", "session_id": None})
                self.assertEqual(ws.receive_json()["type"], "session_bound")
                ws.send_json({"type": "utterance_end", "text": "第一句"})
                self.assertEqual(ws.receive_json()["type"], "stt_start")
                self.assertEqual(ws.receive_json()["type"], "stt_result")
                self.assertEqual(ws.receive_json()["type"], "answer_delta")
                ws.send_json({"type": "utterance_end", "text": "第二句"})
                self.assertEqual(ws.receive_json(), {"type": "error", "code": "busy"})

    def test_foreign_session_invisible(self):
        from app.core.session import TutorSession, save_session
        other = TutorSession(grade="")
        other.student_id = "usr_somebodyelse"
        other.session_id = "sess_foreign_voice"
        save_session(other)
        with self.client.websocket_connect(
                f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
            ws.send_json({"type": "start", "session_id": "sess_foreign_voice"})
            event = ws.receive_json()
            self.assertEqual(event["type"], "error")
            self.assertEqual(event["code"], "session_not_found")

    def test_end_control_closes(self):
        with self.client.websocket_connect(
                f"/api/v1/voice/ws?ticket={self._ticket()}") as ws:
            ws.send_json({"type": "start", "session_id": None})
            ws.receive_json()
            ws.send_json({"type": "end"})
            self.assertEqual(ws.receive_json()["type"], "bye")


if __name__ == "__main__":
    unittest.main()
