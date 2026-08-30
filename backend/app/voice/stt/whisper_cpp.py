"""whisper.cpp STT provider (MIT; docs/VOICE_LICENSES.md).

Runs the prebuilt ``whisper-cli`` binary as a subprocess on a temporary
WAV file, so no ML dependency enters the main backend venv. Transcription
is CPU-bound and serialized process-wide: a 2-vCPU server must never run
two whisper processes at once.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from ..base import STTProvider, STTResult, STTUnavailable

log = logging.getLogger(__name__)

_SLOT: asyncio.Semaphore | None = None


def _slot() -> asyncio.Semaphore:
    global _SLOT
    if _SLOT is None:
        _SLOT = asyncio.Semaphore(1)
    return _SLOT


class WhisperCppSTT(STTProvider):
    name = "whisper"

    def __init__(self, bin_path: str, model_path: str, *, language: str = "zh",
                 threads: int = 2, timeout: float = 120.0):
        self.bin_path = bin_path
        self.model_path = model_path
        self.language = language
        self.threads = max(1, int(threads))
        self.timeout = timeout

    async def transcribe(self, wav: bytes) -> STTResult:
        with tempfile.TemporaryDirectory(prefix="edu-voice-stt-") as tmp:
            audio = Path(tmp) / "utterance.wav"
            audio.write_bytes(wav)
            cmd = [self.bin_path, "-m", self.model_path, "-f", str(audio),
                   "-l", self.language, "-t", str(self.threads), "-np", "-nt"]
            async with _slot():
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
                try:
                    out, err = await asyncio.wait_for(
                        proc.communicate(), self.timeout)
                except asyncio.TimeoutError:
                    proc.kill()
                    raise STTUnavailable("whisper 转写超时") from None
        if proc.returncode != 0:
            detail = err.decode(errors="replace")[-300:] if err else ""
            raise STTUnavailable(f"whisper-cli 退出码 {proc.returncode}: {detail}")
        text = _clean_output(out.decode(errors="replace"))
        return STTResult(text=text)


def _clean_output(stdout: str) -> str:
    """Keep transcript lines only: whisper.cpp prints its init logs to
    stderr, but belt-and-braces drop obvious log/blank noise."""
    lines = [ln.strip() for ln in stdout.splitlines()]
    keep = [ln for ln in lines
            if ln and not ln.startswith(("whisper_", "system_info", "###", "main:"))]
    return " ".join(keep)
