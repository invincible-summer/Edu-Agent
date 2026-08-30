"""Deterministic STT stub (tests / offline demo).

Echoes a fixed line so the full voice turn pipeline (WebSocket protocol,
session persistence, event fan-out) runs end to end without any model.
"""
from __future__ import annotations

from ..base import STTProvider, STTResult

STUB_TEXT = "请给我讲一讲勾股定理。"


class StubSTT(STTProvider):
    name = "stub"

    def __init__(self, text: str = STUB_TEXT):
        self.text = text

    async def transcribe(self, wav: bytes) -> STTResult:
        return STTResult(text=self.text)
