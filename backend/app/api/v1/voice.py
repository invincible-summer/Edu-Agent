"""Voice call API: push-to-talk WebSocket + one-time tickets (P10).

Browser WebSockets cannot carry the Authorization header and the repo
rule is "JWT never travels in a query string", so the handshake exchanges
the header-authed identity for a single-use 60 s ticket (POST /voice/ticket)
which the WS connect then spends; non-browser clients may simply send the
Authorization header directly.

Wire protocol (client PCM16 mono 16 kHz binary frames):
  C->S {"type":"start","session_id":sid|null,"workspace_id":ws|null}
  C->S <binary audio frames> ... {"type":"utterance_end"}   (one push-to-talk)
  S->C {"type":"session_bound","session_id"} / {"type":"stt_start"}
       {"type":"stt_result","text"} / step/tool_* status events /
       {"type":"answer_delta","content"} per LLM delta /
       {"type":"tts_start","seq","text","sample_rate"} + <binary PCM16> +
       {"type":"tts_end","seq"} per spoken sentence /
       {"type":"turn_end","session_id","tts_ok"}
  C->S {"type":"end"} closes the call.

The transcript runs through the normal chat pipeline (run_turn + the
session persistence inside it), so voice turns land in the same session
history, memory and RAG as typed turns. STT/TTS are plugins (app/voice)
selected by VOICE_* settings and default to off.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time

from fastapi import APIRouter, Depends, WebSocket

from app.core.config import settings
from app.core.ratelimit import rate_limit
from app.identity.deps import resolve_student_id, _try_user_from_header
from app.voice.base import VoiceProviderError
from app.voice.stt import get_stt_provider
from app.voice.tts import get_tts_provider
from app.voice.sentences import take_complete
from app.voice.speak_text import to_speakable
from app.voice.loudness import normalize_pcm16
from app.voice.wav import pcm16_to_wav

log = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

# 16 kHz mono 16-bit frames from the browser.
_SAMPLE_RATE = 16000
_FRAME_BYTES = _SAMPLE_RATE * 2  # bytes per second of audio
_MIN_AUDIO_BYTES = _FRAME_BYTES // 10  # 0.1 s
_TICKET_TTL = 60.0
# One failed TTS synthesis per turn is reported and the rest of the turn
# continues text-only; retrying every sentence against a dead sidecar
# would stall the call for minutes.
_TTS_FAILURE_LIMIT = 1


class _CallEnded(Exception):
    """Client said end: drain the loop and close gracefully."""


# --------------------------------------------------------------------------
# One-time WS tickets: {token: (student_id, expires_at)}
# --------------------------------------------------------------------------
_TICKETS: dict[str, tuple[str, float]] = {}


def _issue_ticket(student_id: str) -> str:
    now = time.time()
    expired = [t for t, (_sid, exp) in _TICKETS.items() if exp < now]
    for t in expired:
        _TICKETS.pop(t, None)
    token = secrets.token_urlsafe(24)
    _TICKETS[token] = (student_id, now + _TICKET_TTL)
    return token


def _consume_ticket(token: str) -> str | None:
    entry = _TICKETS.pop(token, None)
    if entry is None:
        return None
    student_id, exp = entry
    return student_id if exp >= time.time() else None


@router.get("/status")
def voice_status(student_id: str = Depends(resolve_student_id)):
    """Provider availability for the frontend's call-button visibility."""
    stt = get_stt_provider()
    tts = get_tts_provider()
    return {
        "enabled": stt is not None and tts is not None,
        "stt": stt.name if stt else None,
        "tts": tts.name if tts else None,
    }


@router.post("/ticket", dependencies=[Depends(rate_limit("voice_ticket", 30))])
def voice_ticket(student_id: str = Depends(resolve_student_id)):
    """Exchange the header-authed identity for a one-use WS ticket."""
    return {"ticket": _issue_ticket(student_id), "expires_in": int(_TICKET_TTL)}


@router.websocket("/ws")
async def voice_ws(websocket: WebSocket):
    """One push-to-talk voice call; one connection = one session binding."""
    # Header auth first (non-browser clients); ticket otherwise.
    user = _try_user_from_header(websocket.headers.get("Authorization"))
    if user is not None:
        student_id = user.id
    else:
        student_id = _consume_ticket(websocket.query_params.get("ticket", ""))
        if student_id is None:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    call = _VoiceCall(websocket, student_id)
    try:
        await call.run()
    finally:
        await call.shutdown()


class _VoiceCall:
    """State machine for a single voice call connection.

    ``_turn_task`` guards the one-turn-at-a-time rule: audio arriving
    while a turn is running is discarded (with a busy notice) so the
    CPU-constrained target never queues transcriptions behind each other.
    """

    def __init__(self, websocket: WebSocket, student_id: str):
        self.ws = websocket
        self.student_id = student_id
        self.stt = get_stt_provider()
        self.tts = get_tts_provider()
        self.session = None  # TutorSession, bound by start/first turn
        self.lang = "zh"
        self.audio = bytearray()
        self.audio_cap = _FRAME_BYTES * settings.voice_max_audio_seconds
        self.truncated = False
        self.turn_task: asyncio.Task | None = None
        # progress_cb fires inside run_turn's own control flow; events are
        # collected here and drained around each yielded event (single loop).
        self._outstanding: list[dict] = []

    # -- lifecycle ---------------------------------------------------------

    async def run(self) -> None:
        try:
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                data = msg.get("bytes")
                if data is not None:
                    self._feed_audio(data)
                    continue
                text = msg.get("text")
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                await self._on_control(event)
        except _CallEnded:
            try:
                await self.ws.close(code=1000)
            except Exception:
                pass
            return

    async def shutdown(self) -> None:
        if self.turn_task and not self.turn_task.done():
            self.turn_task.cancel()
            try:
                await self.turn_task
            except (asyncio.CancelledError, Exception):
                pass

    async def _on_control(self, event: dict) -> None:
        kind = str(event.get("type", ""))
        if kind == "start":
            await self._on_start(event)
        elif kind == "utterance_end":
            await self._on_utterance_end()
        elif kind == "ping":
            await self._send({"type": "pong"})
        elif kind == "end":
            await self._send({"type": "bye"})
            raise _CallEnded()
        # Audio-flush shorthand: an empty text frame is ignored above.

    # -- session binding (mirrors chat_stream semantics) --------------------

    async def _on_start(self, event: dict) -> None:
        from app.core.session import TutorSession, load_session, new_session_id
        from app.api.v1.chat import _validate_workspace_binding
        self.lang = str(event.get("lang") or "zh")
        session = None
        sid = str(event.get("session_id") or "").strip()
        if sid:
            session = load_session(sid)
            # Ownership: foreign sessions are invisible (no existence leak).
            if session is not None and session.student_id \
                    and session.student_id != self.student_id:
                await self._send({"type": "error", "code": "session_not_found"})
                return
        if session is None:
            session = TutorSession(grade="")
        session.student_id = self.student_id
        session.output_language = None
        if not session.session_id:
            session.session_id = new_session_id(
                str(event.get("title") or "")[:20] or "语音通话")
        workspace_id = str(event.get("workspace_id") or "").strip()
        if workspace_id and not session.workspace_id:
            try:
                _validate_workspace_binding(workspace_id, self.student_id)
            except Exception:
                await self._send({"type": "error", "code": "workspace_not_found"})
                return
            session.workspace_id = workspace_id
            from app.core.workspace import add_session_to_workspace
            add_session_to_workspace(workspace_id, session.session_id)
        self.session = session
        await self._send({"type": "session_bound", "session_id": session.session_id})

    def _ensure_session(self):
        """Auto-bind a fresh session when the client skipped start."""
        if self.session is not None:
            return self.session
        from app.core.session import TutorSession, new_session_id
        session = TutorSession(grade="")
        session.student_id = self.student_id
        session.output_language = None
        session.session_id = new_session_id("语音通话")
        self.session = session
        return session

    # -- audio ---------------------------------------------------------------

    def _feed_audio(self, data: bytes) -> None:
        room = self.audio_cap - len(self.audio)
        if room <= 0:
            self.truncated = True
            return
        if len(data) > room:
            self.audio.extend(data[:room])
            self.truncated = True
        else:
            self.audio.extend(data)

    async def _on_utterance_end(self) -> None:
        audio = bytes(self.audio)
        truncated = self.truncated
        self.audio.clear()
        self.truncated = False
        if self.turn_task is not None and not self.turn_task.done():
            await self._send({"type": "error", "code": "busy"})
            return
        if len(audio) < _MIN_AUDIO_BYTES:
            await self._send({"type": "error", "code": "too_short"})
            return
        if self.stt is None or self.tts is None:
            await self._send({"type": "error", "code": "voice_disabled"})
            return
        session = self._ensure_session()
        if truncated:
            await self._send({"type": "warning", "code": "audio_truncated",
                              "max_seconds": settings.voice_max_audio_seconds})
        self.turn_task = asyncio.create_task(
            self._run_turn(audio, session))
        # Report turn completion/failure to the loop (never crash it).
        self.turn_task.add_done_callback(self._turn_done)

    def _turn_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.warning("voice turn failed: %s", exc)

    # -- one push-to-talk turn ------------------------------------------------

    async def _run_turn(self, audio: bytes, session) -> None:
        await self._send({"type": "stt_start"})
        try:
            result = await self.stt.transcribe(pcm16_to_wav(audio, _SAMPLE_RATE))
        except VoiceProviderError as exc:
            await self._send({"type": "error", "code": exc.code,
                              "message": str(exc)})
            return
        except Exception as exc:  # engine crash must not kill the call
            log.warning("voice stt crashed: %s", exc)
            await self._send({"type": "error", "code": "stt_unavailable"})
            return
        text = (result.text or "").strip()
        if not text:
            await self._send({"type": "error", "code": "empty_transcript"})
            return
        await self._send({"type": "stt_result", "text": text})
        if not session.title:
            session.title = text[:20]

        from app.agents.chat_agent import run_turn
        from app.api.v1.chat import _build_tools
        tools = _build_tools(session)
        pending = ""
        tts_ok = True
        tts_failures = 0
        seq = 0

        def progress_cb(msg: str):
            self._outstanding.append({"type": "tool_progress", "message": msg})

        async def speak(sentence: str) -> None:
            nonlocal tts_ok, tts_failures, seq
            if not tts_ok or tts_failures >= _TTS_FAILURE_LIMIT:
                return
            speakable = to_speakable(sentence)
            if not speakable:
                return
            try:
                result_tts = await self.tts.synthesize(speakable)
            except VoiceProviderError as exc:
                tts_failures += 1
                tts_ok = tts_failures < _TTS_FAILURE_LIMIT
                await self._send({"type": "tts_error", "code": exc.code})
                return
            except Exception as exc:
                tts_failures += 1
                tts_ok = False
                log.warning("voice tts crashed: %s", exc)
                await self._send({"type": "tts_error", "code": "tts_unavailable"})
                return
            # Sentences synthesize independently and vary several dB in
            # loudness; level each clip so playback stays 忽大忽小-free.
            pcm = normalize_pcm16(result_tts.pcm16, result_tts.sample_rate)
            await self._send({"type": "tts_start", "seq": seq,
                              "text": sentence,
                              "sample_rate": result_tts.sample_rate})
            await self.ws.send_bytes(pcm)
            await self._send({"type": "tts_end", "seq": seq})
            seq += 1

        try:
            async for ev in run_turn(text, session, tools,
                                     progress_cb=progress_cb, lang=self.lang,
                                     output_language=None, student_id=self.student_id):
                while self._outstanding:
                    await self._send(self._outstanding.pop(0))
                etype = ev.get("type")
                if etype == "answer":
                    pending += ev.get("content") or ""
                    complete, pending = take_complete(pending)
                    await self._send({"type": "answer_delta",
                                      "content": ev.get("content") or ""})
                    for sentence in complete:
                        await speak(sentence)
                elif etype == "step":
                    await self._send({"type": "step", "step": ev.get("step")})
                elif etype == "tool_start":
                    await self._send({"type": "tool_start", "name": ev.get("name")})
                elif etype == "tool_warning":
                    await self._send({"type": "tool_warning",
                                      "warning": ev.get("warning")})
                elif etype == "retry":
                    await self._send({"type": "status", "stage": "retry",
                                      "attempt": ev.get("attempt")})
                elif etype == "done":
                    if ev.get("trace_id"):
                        from app.core.session import add_trace_id
                        if ev["trace_id"] not in session.trace_ids:
                            session.trace_ids.append(ev["trace_id"])
                            add_trace_id(session.session_id, ev["trace_id"])
                    if pending.strip():
                        await speak(pending.strip())
                        pending = ""
                elif etype == "error":
                    await self._send({"type": "error", "code": "agent_error",
                                      "message": ev.get("message")})
                    return
                # thinking/tool_result payloads stay server-side: a phone
                # call has no place to show them and CoT never leaves the box.
            while self._outstanding:
                await self._send(self._outstanding.pop(0))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("voice agent turn failed: %s", exc)
            await self._send({"type": "error", "code": "agent_error",
                              "message": str(exc)})
            return
        await self._send({"type": "turn_end", "session_id": session.session_id,
                          "tts_ok": tts_ok})

    async def _send(self, event: dict) -> None:
        await self.ws.send_text(json.dumps(event, ensure_ascii=False, default=str))
