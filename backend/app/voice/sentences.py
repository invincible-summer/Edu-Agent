"""Sentence segmentation for streaming TTS.

Voice turns speak answers while the LLM is still streaming: answer deltas
are buffered and every complete sentence is dispatched to TTS immediately,
so playback of the first sentence starts seconds before the turn ends.
Chinese terminators end a sentence unconditionally; an ASCII dot only ends
one when it is NOT glued to an alphanumeric neighbour (so "3.14" and
"e.g" stay intact while "fine. Next" splits). Terminators inside
$...$ / $$...$$ math spans never split: display formulas wrap lines and
would be cut open mid-span, leaving unbalanced delimiters that downstream
to_speakable can no longer recognize (raw LaTeX read aloud).
"""
from __future__ import annotations

_SENTENCE_END = "。！？!?…；;"
_MAX_CHARS = 120
_MIN_CUT_RATIO = 0.5
_CUT_PUNCTS = ("，", "、", "：", ",", ":", " ")


def split_sentences(text: str) -> list[str]:
    """Split finalized text into speakable sentences (whitespace dropped)."""
    complete, rest = take_complete(text)
    if rest.strip():
        complete.append(rest.strip())
    return _force_split_all(complete)


def take_complete(text: str) -> tuple[list[str], str]:
    """Streaming variant: return (complete sentences, trailing remainder).

    The remainder carries no terminator yet and stays buffered until more
    deltas arrive (the endpoint flushes it on done). An unclosed $ holds
    the buffer — the math span is still streaming in.
    """
    sentences: list[str] = []
    buf = ""
    n = len(text)
    in_math = False
    i = 0
    while i < n:
        ch = text[i]
        buf += ch
        if ch == "$":
            # "$$" opens/closes display math, a lone "$" inline math; the
            # same token that opened a span also closes it.
            if text.startswith("$$", i):
                buf += "$"
                i += 2
            else:
                i += 1
            in_math = not in_math
            continue
        if not in_math:
            if ch in _SENTENCE_END:
                sentences.append(buf)
                buf = ""
            elif ch == ".":
                nxt = text[i + 1] if i + 1 < n else ""
                if not (nxt and nxt.isalnum()):
                    sentences.append(buf)
                    buf = ""
        i += 1
    out = [s.strip() for s in sentences if s.strip()]
    return out, buf


def _force_split_all(sentences: list[str]) -> list[str]:
    out: list[str] = []
    for s in sentences:
        out.extend(_force_split(s))
    return out


def _force_split(sentence: str) -> list[str]:
    if len(sentence) <= _MAX_CHARS:
        return [sentence]
    parts: list[str] = []
    rest = sentence
    while len(rest) > _MAX_CHARS:
        window = rest[:_MAX_CHARS + 1]
        idx = max(window.rfind(p) for p in _CUT_PUNCTS)
        if idx < _MAX_CHARS * _MIN_CUT_RATIO:
            idx = _MAX_CHARS - 1
        parts.append(rest[:idx + 1].strip())
        rest = rest[idx + 1:]
    if rest.strip():
        parts.append(rest.strip())
    return [p for p in parts if p]
