"""Voice call API: push-to-talk WebSocket + one-time tickets (P10).

Browser WebSockets cannot carry the Authorization header and the repo
rule is "JWT never travels in a query string", so the handshake exchanges
the header-authed identity for a single-use 60 s ticket (POST /voice/ticket)
which the WS connect then spends; non-browser clients may simply send the
Authorization header directly.

Wire protocol (browser Speech Recognition text only):
  C->S {"type":"start","session_id":sid|null,"workspace_id":ws|null}
  C->S {"type":"utterance_end","text":"..."} (one push-to-talk turn)
  S->C {"type":"session_bound","session_id"} / {"type":"stt_start"}
       {"type":"stt_result","text"} / step/tool_* status events /
       {"type":"answer_delta","content"} per LLM delta /
       {"type":"tts_start","seq","text","sample_rate"} + <binary PCM16> +
       {"type":"tts_end","seq"} per spoken clause (speech cut) /
       {"type":"turn_end","session_id","tts_ok"}
  C->S {"type":"end"} closes the call.

The transcript runs through the normal chat pipeline (run_turn + the
session persistence inside it), so voice turns land in the same session
history, memory and RAG as typed turns. Speech-to-text is performed only by
SpeechRecognition/webkitSpeechRecognition in the browser; the backend receives
final text and uses the configured TTS provider for spoken replies.

TTS runs as a pipeline, not inline awaits: the turn loop only enqueues
clause-level speech cuts (bounded queue) and keeps consuming the LLM
generator, while one worker task synthesizes and sends audio clips. The
client's FIFO playback queue absorbs clips that arrive early, so playback
of clip N overlaps synthesis of clip N+1 instead of pausing between
sentences. turn_end still follows the last audio frame (the producer joins
the worker before sending it), and a single worker keeps at most one
in-flight sidecar request per turn — the sidecar model is not
concurrency-guarded.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time

from fastapi import APIRouter, Depends, WebSocket

from app.core.ratelimit import rate_limit
from app.identity.deps import resolve_student_id, _try_user_from_header
from app.voice.base import VoiceProviderError
from app.voice.tts import get_tts_provider
from app.voice.sentences import take_speech_cuts
from app.voice.speak_text import to_speakable
from app.voice.loudness import normalize_pcm16

log = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

_TICKET_TTL = 60.0
# One failed TTS synthesis per turn is reported and the rest of the turn
# continues text-only; retrying every sentence against a dead sidecar
# would stall the call for minutes.
_TTS_FAILURE_LIMIT = 1
# Speech cuts waiting for synthesis. When full, the turn loop briefly parks
# (the client is still playing several clips of buffered audio, so playback
# never starves) which caps how far synthesis can run ahead of the socket.
_TTS_QUEUE_MAX = 8

# The MeloTTS sidecar rejects requests beyond 400 chars; speakable text is
# chunked well under that at punctuation boundaries so long derivations
# never kill the audio.
_SPEAK_CHUNK_MAX = 240
_SPEAK_CUTS = "，。；、！？, "


def _speakable_chunks(text: str) -> list[str]:
    if len(text) <= _SPEAK_CHUNK_MAX:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while n - start > _SPEAK_CHUNK_MAX:
        window = text[start:start + _SPEAK_CHUNK_MAX + 1]
        idx = max(window.rfind(p) for p in _SPEAK_CUTS)
        if idx < _SPEAK_CHUNK_MAX // 2:
            idx = _SPEAK_CHUNK_MAX - 1
        chunks.append(text[start:start + idx + 1])
        start += idx + 1
    if start < n:
        chunks.append(text[start:])
    return [chunk for chunk in chunks if chunk]


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
    tts = get_tts_provider()
    return {
        "enabled": tts is not None,
        "stt": "browser",
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

    ``turn_task`` guards the one-turn-at-a-time rule so repeated browser
    transcripts cannot queue multiple LLM/TTS turns on the same connection.
    """

    def __init__(self, websocket: WebSocket, student_id: str):
        self.ws = websocket
        self.student_id = student_id
        self.tts = get_tts_provider()
        self.session = None  # TutorSession, bound by start/first turn
        self.lang = "zh"
        self.turn_task: asyncio.Task | None = None
        # progress_cb fires inside run_turn's own control flow; events are
        # collected here and drained around each yielded event (single loop).
        self._outstanding: list[dict] = []
        # The turn loop and the TTS worker both send frames; the lock keeps
        # each tts_start + binary + tts_end trio atomic (no answer_delta or
        # turn_end may slip between a tts_start and its audio) and
        # serializes concurrent socket writes.
        self._send_lock = asyncio.Lock()

    # -- lifecycle ---------------------------------------------------------

    async def run(self) -> None:
        try:
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                if msg.get("bytes") is not None:
                    await self._send({"type": "error",
                                      "code": "binary_audio_unsupported"})
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
            text = event.get("text")
            await self._on_utterance_end(text if isinstance(text, str) else None)
        elif kind == "ping":
            await self._send({"type": "pong"})
        elif kind == "end":
            await self._send({"type": "bye"})
            raise _CallEnded()

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

    # -- one push-to-talk turn ---------------------------------------------

    async def _on_utterance_end(self, browser_text: str | None = None) -> None:
        if self.turn_task is not None and not self.turn_task.done():
            await self._send({"type": "error", "code": "busy"})
            return
        if self.tts is None:
            await self._send({"type": "error", "code": "voice_disabled"})
            return
        session = self._ensure_session()
        self.turn_task = asyncio.create_task(
            self._run_turn(browser_text, session))
        self.turn_task.add_done_callback(self._turn_done)

    def _turn_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.warning("voice turn failed: %s", exc)

    async def _run_turn(self, browser_text: str | None, session) -> None:
        await self._send({"type": "stt_start"})
        # Browser recognition is the sole STT path. Empty/invalid text never
        # triggers a server-side audio provider or fallback.
        text = (browser_text or "").strip()
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
        tts_q: asyncio.Queue = asyncio.Queue(maxsize=_TTS_QUEUE_MAX)

        def progress_cb(msg: str):
            self._outstanding.append({"type": "tool_progress", "message": msg})

        async def speak_worker() -> None:
            """Synthesize and send queued cuts; one clip in flight at a time.

            Keeps draining after a failure (sentences are consumed and
            dropped) so the bounded queue can never wedge the producer.
            """
            nonlocal tts_ok, tts_failures, seq
            while True:
                sentence = await tts_q.get()
                if sentence is None:
                    return
                if not tts_ok or tts_failures >= _TTS_FAILURE_LIMIT:
                    continue
                try:
                    speakable = to_speakable(sentence)
                    if not speakable:
                        continue
                    for i, chunk in enumerate(_speakable_chunks(speakable)):
                        try:
                            result_tts = await self.tts.synthesize(chunk)
                        except VoiceProviderError as exc:
                            tts_failures += 1
                            tts_ok = tts_failures < _TTS_FAILURE_LIMIT
                            await self._send({"type": "tts_error", "code": exc.code})
                            break
                        except Exception as exc:
                            tts_failures += 1
                            tts_ok = False
                            log.warning("voice tts crashed: %s", exc)
                            await self._send({"type": "tts_error",
                                              "code": "tts_unavailable"})
                            break
                        # Sentences synthesize independently and vary several
                        # dB in loudness; level each clip so playback stays
                        # 忽大忽小-free.
                        try:
                            pcm = normalize_pcm16(result_tts.pcm16,
                                                  result_tts.sample_rate)
                        except Exception as exc:
                            tts_failures += 1
                            tts_ok = False
                            log.warning("voice tts post-processing failed: %s", exc)
                            await self._send({"type": "tts_error",
                                              "code": "tts_unavailable"})
                            break
                        # Only the first chunk carries the raw sentence: the
                        # frontend blackboard renders formulas from
                        # tts_start.text and skips empty text, so
                        # continuations never duplicate the board.
                        async with self._send_lock:
                            await self._send_text(
                                {"type": "tts_start", "seq": seq,
                                 "text": sentence if i == 0 else "",
                                 "sample_rate": result_tts.sample_rate})
                            await self.ws.send_bytes(pcm)
                            await self._send_text({"type": "tts_end", "seq": seq})
                        seq += 1
                except Exception as exc:
                    # Dead socket and friends: stop speaking, keep draining.
                    tts_ok = False
                    log.warning("voice tts worker send failed: %s", exc)

        worker = asyncio.create_task(speak_worker())
        try:
            async for ev in run_turn(text, session, tools,
                                     progress_cb=progress_cb, lang=self.lang,
                                     output_language=None, student_id=self.student_id):
                while self._outstanding:
                    await self._send(self._outstanding.pop(0))
                etype = ev.get("type")
                if etype == "answer":
                    pending += ev.get("content") or ""
                    complete, pending = take_speech_cuts(pending)
                    await self._send({"type": "answer_delta",
                                      "content": ev.get("content") or ""})
                    for sentence in complete:
                        await tts_q.put(sentence)
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
                        await tts_q.put(pending.strip())
                        pending = ""
                elif etype == "error":
                    await self._send({"type": "error", "code": "agent_error",
                                      "message": ev.get("message")})
                    return
                # thinking/tool_result payloads stay server-side: a phone
                # call has no place to show them and CoT never leaves the box.
            while self._outstanding:
                await self._send(self._outstanding.pop(0))
            # Flush sentinel, then wait for the worker to finish sending the
            # queued audio so turn_end still follows the last audio frame.
            await tts_q.put(None)
            await worker
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("voice agent turn failed: %s", exc)
            await self._send({"type": "error", "code": "agent_error",
                              "message": str(exc)})
            return
        finally:
            # Early returns and cancellation must not leak a live worker.
            if not worker.done():
                worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        await self._send({"type": "turn_end", "session_id": session.session_id,
                          "tts_ok": tts_ok})

    async def _send_text(self, event: dict) -> None:
        await self.ws.send_text(json.dumps(event, ensure_ascii=False, default=str))

    async def _send(self, event: dict) -> None:
        async with self._send_lock:
            await self._send_text(event)
