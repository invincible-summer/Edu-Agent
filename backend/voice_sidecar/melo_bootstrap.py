"""Mount MeloTTS while keeping unused language paths out of the sidecar.

The pinned MeloTTS release imports every language cleaner from
``melo.text.cleaner`` even though this service selects only ``ZH`` (the
Chinese/English mixed frontend).  Japanese and Korean modules therefore have
import-time references to optional language packages that are never executed
by this sidecar.  Install small, fail-loud stubs for those references before
MeloTTS is imported instead of installing their language dictionaries or
copyleft packages.

If a future change selects a non-Chinese language, the relevant package must
be added deliberately and its license/data terms must be audited again.
"""
from __future__ import annotations

import importlib
import os
import sys
import types

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
MELO_ROOT = os.environ.get("MELO_ROOT") or os.path.abspath(
    os.path.join(_THIS_DIR, "..", "vendor", "MeloTTS"))


class _UnavailableLanguagePath(RuntimeError):
    """Raised if an excluded non-Chinese language path is accidentally used."""


class _KakasiConverterStub:
    def do(self, text: str) -> str:
        raise _UnavailableLanguagePath("Japanese text conversion is not installed")


class _KakasiStub:
    def setMode(self, *args, **kwargs) -> None:
        pass

    def getConverter(self) -> _KakasiConverterStub:
        return _KakasiConverterStub()


class _MeCabTaggerStub:
    def __init__(self, *args, **kwargs):
        pass

    def parse(self, *args, **kwargs):
        raise _UnavailableLanguagePath("Japanese MeCab parsing is not installed")


def _unavailable_num2words(*args, **kwargs):
    raise _UnavailableLanguagePath("Non-Chinese number normalization is not installed")


def _unavailable_anyascii(*args, **kwargs):
    raise _UnavailableLanguagePath("Korean transliteration is not installed")


def _unavailable_hangul_to_jamo(*args, **kwargs):
    raise _UnavailableLanguagePath("Korean jamo conversion is not installed")


def _unavailable_gruut(*args, **kwargs):
    raise _UnavailableLanguagePath("Non-Chinese phonemization is not installed")


class _UnavailableIPA:
    @staticmethod
    def without_stress(*args, **kwargs):
        raise _UnavailableLanguagePath("Non-Chinese IPA processing is not installed")


def _make_language_module(name: str) -> types.ModuleType:
    module = types.ModuleType(f"melo.text.{name}")
    message = f"MeloTTS language path {name!r} is not installed"

    def unavailable(*args, **kwargs):
        raise _UnavailableLanguagePath(message)

    module.text_normalize = unavailable
    module.g2p = unavailable
    module.get_bert_feature = unavailable
    module.distribute_phone = unavailable
    return module


def _install_stubs() -> None:
    # These modules are only imported at module load by Japanese/Korean
    # cleaners.  Do not import installed copies from a reused virtualenv.
    pykakasi = types.ModuleType("pykakasi")
    pykakasi.kakasi = _KakasiStub
    sys.modules["pykakasi"] = pykakasi

    num2words = types.ModuleType("num2words")
    num2words.num2words = _unavailable_num2words
    sys.modules["num2words"] = num2words

    mecab = types.ModuleType("MeCab")
    mecab.Tagger = _MeCabTaggerStub
    sys.modules["MeCab"] = mecab

    anyascii = types.ModuleType("anyascii")
    anyascii.anyascii = _unavailable_anyascii
    sys.modules["anyascii"] = anyascii

    jamo = types.ModuleType("jamo")
    jamo.hangul_to_jamo = _unavailable_hangul_to_jamo
    sys.modules["jamo"] = jamo

    gruut = types.ModuleType("gruut")
    gruut.__version__ = "excluded"
    gruut.sentences = _unavailable_gruut
    gruut.is_language_supported = _unavailable_gruut
    gruut.get_supported_languages = _unavailable_gruut
    sys.modules["gruut"] = gruut

    gruut_ipa = types.ModuleType("gruut_ipa")
    gruut_ipa.IPA = _UnavailableIPA
    sys.modules["gruut_ipa"] = gruut_ipa

    # get_bert() imports every language backend, and the upstream French,
    # Spanish and Korean modules construct tokenizers at import time.  Only
    # Chinese mixed English is supported here; pre-installing these modules
    # avoids downloading unrelated language models while retaining a loud
    # failure if a caller selects one accidentally.
    importlib.import_module("melo.text")
    for name in ("korean", "french", "spanish", "english_bert",
                 "japanese_bert", "french_bert", "spanish_bert"):
        sys.modules[f"melo.text.{name}"] = _make_language_module(name)


def bootstrap() -> str:
    """Put the pinned MeloTTS source on ``sys.path`` and install stubs."""
    if os.path.isdir(MELO_ROOT) and MELO_ROOT not in sys.path:
        sys.path.insert(0, MELO_ROOT)
    _install_stubs()
    return MELO_ROOT
