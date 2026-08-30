"""Pluggable voice layer (P10 电话式语音对话).

The agent core only sees the STTProvider/TTSProvider contracts in
``base.py``. Concrete engines live behind provider factories and are
selected by VOICE_* settings — mirroring the embedding lane's
"explicit provider + fail-open" pattern: anything off or misconfigured
resolves to None and the voice endpoint degrades gracefully. Chat is
never affected. Licenses: docs/VOICE_LICENSES.md.
"""
