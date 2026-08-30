"""Answer text -> speakable plain text for TTS.

Chat answers are markdown with inline LaTeX; reading raw markup aloud is
unintelligible. Normalization: fenced code collapses to a short spoken
placeholder (inline code keeps its inner text), math fragments get common
LaTeX commands/symbols mapped to Chinese readings, markdown emphasis,
links and table pipes are stripped. Deliberately conservative — anything
unmapped survives as plain characters rather than being deleted.
"""
from __future__ import annotations

import re

_CODE_FENCE = re.compile(r"```.*?```", re.S)
_CODE_INLINE = re.compile(r"`([^`\n]+)`")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MATH_DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.S)
_MATH_INLINE = re.compile(r"\$([^$\n]+)\$")
_HEADING = re.compile(r"^#{1,6}\s*", re.M)
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.、)])\s+", re.M)
_QUOTE = re.compile(r"^>\s?", re.M)
_EMPH = re.compile(r"\*\*|__|\*|~~")
_TABLE_PIPE = re.compile(r"\|")
_HR = re.compile(r"^ {0,3}(?:-{3,}|\*{3,})$", re.M)

_MATH_READINGS: tuple[tuple[re.Pattern, str], ...] = (
    # \frac{a}{b} reads "b 分之 a" in Chinese.
    (re.compile(r"\\[dt]?frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}"), r"\2分之\1"),
    (re.compile(r"\\sqrt\s*\{([^{}]+)\}"), r"根号\1"),
    # \lim_{x \to \infty} f(x) -> "当x 趋于 无穷 时..." (before the generic
    # subscript rule mangles it into "下标").
    (re.compile(r"\\lim\s*_?\s*\{([^{}]+)\}"), r"当\1"),
    (re.compile(r"\\(?:le|leq)"), "小于等于"),
    (re.compile(r"\\(?:ge|geq)"), "大于等于"),
    (re.compile(r"\\neq?"), "不等于"),
    (re.compile(r"\\approx"), "约等于"),
    (re.compile(r"\\pm"), "正负"),
    (re.compile(r"\\times|\\cdot"), "乘"),
    (re.compile(r"\\div"), "除以"),
    (re.compile(r"\\to|\\rightarrow|\\longrightarrow"), "趋于"),
    (re.compile(r"\\lim"), "极限"),
    (re.compile(r"\\int"), "积分"),
    (re.compile(r"\\sum"), "求和"),
    (re.compile(r"\\infty"), "无穷"),
    (re.compile(r"\\pi\b"), "圆周率"),
    (re.compile(r"\\alpha"), "α"),
    (re.compile(r"\\beta"), "β"),
    (re.compile(r"\\theta"), "θ"),
    (re.compile(r"\\Delta|\\delta"), "Δ"),
    (re.compile(r"\^\s*\{([^{}]+)\}"), r"的\1次方"),
    (re.compile(r"\^\s*(\w)"), r"的\1次方"),
    (re.compile(r"_\s*\{([^{}]+)\}"), r"下标\1"),
    (re.compile(r"_\s*(\w)"), r"下标\1"),
    (re.compile(r"\\(?:left|right|quad|qquad|[,!;:~]|\\)"), ""),
    (re.compile(r"\\[a-zA-Z]+\s*"), ""),
    (re.compile(r"[{}]"), ""),
)

_SYMBOL_READINGS: tuple[tuple[re.Pattern, str], ...] = (
    # Glue spaced "+" to its operands FIRST so the alnum rule below then
    # turns "a + b" into "a加b" (math fragments keep operator spacing).
    (re.compile(r"\s*\+\s*"), "+"),
    # A hyphen reads as 减 only when a digit/CJK is on either side, so
    # "x-1" -> "x减1" while the compound-word hyphen in "well-known"
    # survives; "+" between alnum/CJK always reads 加.
    (re.compile(r"(?<=[0-9\u4e00-\u9fff])-(?=[0-9A-Za-z\u4e00-\u9fff])"), "减"),
    (re.compile(r"(?<=[0-9A-Za-z\u4e00-\u9fff])-(?=[0-9\u4e00-\u9fff])"), "减"),
    (re.compile(r"(?<=[0-9A-Za-z\u4e00-\u9fff])\+(?=[0-9A-Za-z\u4e00-\u9fff])"), "加"),
    (re.compile(r"="), "等于"),
    (re.compile(r"×|·"), "乘"),
    (re.compile(r"÷"), "除以"),
    (re.compile(r"≤"), "小于等于"),
    (re.compile(r"≥"), "大于等于"),
    (re.compile(r"≠"), "不等于"),
    (re.compile(r"≈"), "约等于"),
    (re.compile(r"→|->"), "趋于"),
    (re.compile(r"π"), "圆周率"),
)

def to_speakable(text: str) -> str:
    s = text
    s = _CODE_FENCE.sub("（这段是代码，具体请看屏幕）", s)
    s = _CODE_INLINE.sub(r"\1", s)
    s = _IMAGE.sub("", s)
    s = _LINK.sub(r"\1", s)
    s = _MATH_DISPLAY.sub(lambda m: _read_math(m.group(1)), s)
    s = _MATH_INLINE.sub(lambda m: _read_math(m.group(1)), s)
    # Unclosed spans (streaming cuts, oversized formulas forced apart,
    # unpaired $ from the model) can leave lone $ / $$ behind — reading
    # "美元" would be worse than silence.
    s = s.replace("$", "")
    s = _HEADING.sub("", s)
    s = _LIST_MARKER.sub("", s)
    s = _QUOTE.sub("", s)
    s = _HR.sub("", s)
    s = _EMPH.sub("", s)
    s = _TABLE_PIPE.sub("", s)
    for pattern, reading in _SYMBOL_READINGS:
        s = pattern.sub(reading, s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*\n\s*", "，", s)
    s = re.sub(r"，{2,}", "，", s)
    return s.strip("， ")


def _read_math(expr: str) -> str:
    out = expr
    for pattern, reading in _MATH_READINGS:
        out = pattern.sub(reading, out)
    return out
