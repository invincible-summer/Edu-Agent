"""STT provider factory (settings-driven, fail-open like the embedding lane).

``VOICE_STT_PROVIDER``: off (default) | stub | whisper. ``whisper`` needs
``VOICE_WHISPER_BIN`` + ``VOICE_WHISPER_MODEL`` to point at real files;
anything wrong logs a warning and resolves to None so the voice endpoint
answers stt_unavailable instead of crashing the app.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..base import STTProvider
from .stub import StubSTT

log = logging.getLogger(__name__)

_INSTANCE: STTProvider | None = None
_INSTANCE_KEY: tuple | None = None


def _provider_key() -> tuple:
    from app.core.config import settings
    return (settings.voice_stt_provider, settings.voice_whisper_bin,
            settings.voice_whisper_model, settings.voice_whisper_lang,
            settings.voice_whisper_threads)


def reset_stt_provider() -> None:
    """Drop the cached provider (tests / config reload)."""
    global _INSTANCE, _INSTANCE_KEY
    _INSTANCE = None
    _INSTANCE_KEY = None


def get_stt_provider() -> STTProvider | None:
    global _INSTANCE, _INSTANCE_KEY
    from app.core.config import settings
    provider = (settings.voice_stt_provider or "off").strip().lower()
    if provider == "off":
        return None
    key = _provider_key()
    if _INSTANCE is not None and _INSTANCE_KEY == key:
        return _INSTANCE
    try:
        if provider == "stub":
            client: STTProvider = StubSTT()
        elif provider == "whisper":
            bin_path = settings.voice_whisper_bin
            model_path = settings.voice_whisper_model
            if not bin_path or not Path(bin_path).is_file():
                raise FileNotFoundError(f"VOICE_WHISPER_BIN 不存在: {bin_path!r}")
            if not model_path or not Path(model_path).is_file():
                raise FileNotFoundError(f"VOICE_WHISPER_MODEL 不存在: {model_path!r}")
            from .whisper_cpp import WhisperCppSTT
            client = WhisperCppSTT(bin_path, model_path,
                                   language=settings.voice_whisper_lang or "zh",
                                   threads=settings.voice_whisper_threads)
        else:
            log.warning("未知 VOICE_STT_PROVIDER=%r，语音 STT 关闭", provider)
            return None
    except Exception as exc:
        log.warning("语音 STT provider 初始化失败，STT 关闭: %s", exc)
        _INSTANCE = None
        _INSTANCE_KEY = key
        return None
    _INSTANCE = client
    _INSTANCE_KEY = key
    return client
