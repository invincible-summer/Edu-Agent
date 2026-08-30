"""Traditional -> Simplified Chinese conversion for STT transcripts.

whisper.cpp's ``-l zh`` decoding still drifts into Traditional characters
(the multilingual models saw plenty of 繁体 in training), while this
product teaches in Simplified Chinese: a transcript like 「圓周率是圓的周長
與直徑的比值」 must not land in the chat history as-is. Two layers fix it:

1. decoding bias — ``--prompt`` carries a Simplified initial prompt
   (``VOICE_WHISPER_PROMPT``, see stt/whisper_cpp.py);
2. post-conversion — this module rewrites residual Traditional characters
   with the vendored OpenCC T2S tables (Apache-2.0, renamed from
   TSCharacters.txt/TSPhrases.txt to zh_t2s_chars.txt/zh_t2s_phrases.txt,
   see docs/VOICE_LICENSES.md).

Phrases are matched first (longest match): they resolve the handful of
char-level ambiguities — 乾淨→干净 but 乾隆→乾隆, 一目瞭然→一目了然 but
瞭望→瞭望 — before the single-character table collapses the rest.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _tables() -> tuple[dict[str, str], dict[str, str], int]:
    chars: dict[str, str] = {}
    phrases: dict[str, str] = {}
    longest = 0
    for filename, table in (("zh_t2s_phrases.txt", phrases),
                            ("zh_t2s_chars.txt", chars)):
        path = _DATA_DIR / filename
        if not path.is_file():
            continue  # fail-open: an incomplete checkout keeps transcripts
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, values = line.partition("\t")
            simplified = values.split()
            if not (sep and key and simplified):
                continue
            table[key] = simplified[0]
            longest = max(longest, len(key))
    return chars, phrases, longest


def to_simplified(text: str) -> str:
    """Rewrite Traditional characters/phrases to Simplified (zh only)."""
    if not text:
        return text
    chars, phrases, longest = _tables()
    if not chars:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        matched: str | None = None
        for end in range(min(n, i + longest), i, -1):
            hit = phrases.get(text[i:end])
            if hit is not None:
                matched = hit
                i = end
                break
        if matched is not None:
            out.append(matched)
            continue
        ch = text[i]
        out.append(chars.get(ch, ch))
        i += 1
    return "".join(out)
