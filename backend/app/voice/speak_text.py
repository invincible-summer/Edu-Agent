"""Answer text -> speakable plain text for TTS.

Chat answers are markdown with inline LaTeX; reading raw markup aloud is
unintelligible. Normalization: fenced code collapses to a short spoken
placeholder (inline code keeps its inner text), math fragments get common
LaTeX commands/symbols mapped to Chinese readings, markdown emphasis,
links and table pipes are stripped. Deliberately conservative — anything
unmapped survives as plain characters rather than being deleted (unknown
``\\command`` names keep their letters; they read as English words, which
beats silence or a raw backslash).

Math readings run in ordered stages (see ``_read_math``): semantic groups
with arguments first — nested ``\\frac``/``\\sqrt`` collapse inside-out in
a fixpoint loop — then ``^\\circ``/``\\%`` (they must beat the generic
superscript rule), combined ``\\sum``/``\\int`` bounds, named functions and
relations, and finally the keep-the-letters fallback.
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

# One brace group's content: any run of single characters and/or nested
# brace groups (two levels deep), so \frac{\frac{1}{2}}{3} and \sqrt{x^{2}+1}
# match as a whole; deeper spans still collapse because the fixpoint loop
# re-runs the substitution inside-out.
_GROUP = r"(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})+"

# Semantic argument groups, applied in a fixpoint loop (nested constructs
# like \frac{\sqrt{2}}{2} resolve over successive passes).
_MATH_READINGS_PASS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\\[dt]?frac\s*\{(" + _GROUP + r")\}\s*\{(" + _GROUP + r")}"),
     r"\2分之\1"),
    (re.compile(r"\\sqrt\s*\[([^\]]+)\]\s*\{(" + _GROUP + r")}"), r"\1次根号\2"),
    (re.compile(r"\\sqrt\s*\{(" + _GROUP + r")}"), r"根号\1"),
    (re.compile(r"\\binom\s*\{(" + _GROUP + r")\}\s*\{(" + _GROUP + r")}"),
     r"从\1中选\2"),
    (re.compile(r"\\overline\s*\{(" + _GROUP + r")}"), r"\1拔"),
    (re.compile(r"\\bar\s*\{(" + _GROUP + r")}"), r"\1拔"),
    (re.compile(r"\\hat\s*\{(" + _GROUP + r")}"), r"\1帽"),
    (re.compile(r"\\widehat\s*\{(" + _GROUP + r")}"), r"\1帽"),
    (re.compile(r"\\tilde\s*\{(" + _GROUP + r")}"), r"\1波浪"),
    (re.compile(r"\\overrightarrow\s*\{(" + _GROUP + r")}"), r"向量\1"),
    (re.compile(r"\\vec\s*\{(" + _GROUP + r")}"), r"向量\1"),
)

# Number sets: \mathbb{R} etc. Must run before the \text-family keeper
# (which would otherwise flatten \mathbb{R} to a bare letter).
_MATHBB_SETS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\\mathbb\s*\{\s*[Rr]\s*\}"), "实数集"),
    (re.compile(r"\\mathbb\s*\{\s*[Zz]\s*\}"), "整数集"),
    (re.compile(r"\\mathbb\s*\{\s*[Nn]\s*\}"), "自然数集"),
    (re.compile(r"\\mathbb\s*\{\s*[Qq]\s*\}"), "有理数集"),
    (re.compile(r"\\mathbb\s*\{\s*[Cc]\s*\}"), "复数集"),
)

# \text{...} and friends keep only their inner content.
_TEXT_KEEPER = re.compile(
    r"\\(?:operatorname\*?|text(?:rm|bf|it|sf|tt)?|math(?:rm|bf|it|sf|tt)|boldsymbol)\s*\{(" + _GROUP + r")\}")

_MATH_READINGS: tuple[tuple[re.Pattern, str], ...] = (
    # ---- positioned markers, before the generic ^/_ rules ----------------
    # 30^\circ / 30^{\circ} reads 度, NOT 的圈次方.
    (re.compile(r"\^\s*\{?\s*\\circ\s*\}?"), "度"),
    (re.compile(r"\\(?:degree|deg)\b"), "度"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*\\%"), r"百分之\1"),
    (re.compile(r"\\%"), "百分号"),
    (re.compile(r"\\pmod\s*\{(" + _GROUP + r")}"), r"模\1"),
    # \lim_{x \to \infty} f(x) -> "当x 趋于 无穷 时..." (before the generic
    # subscript rule mangles it into "下标").
    (re.compile(r"\\lim\s*_?\s*\{(" + _GROUP + r")}"), r"当\1"),
    # Combined bounds: \sum_{i=1}^{n} -> 求和，从i等于1到n（先于通用上下标）.
    (re.compile(r"\\sum\s*_\s*\{?([-+\d\w.=]+)\}?\s*\^\s*\{?([-+\d\w.=]+)\}?"),
     r"求和，从\1到\2，"),
    (re.compile(r"\\prod\s*_\s*\{?([-+\d\w.=]+)\}?\s*\^\s*\{?([-+\d\w.=]+)\}?"),
     r"连乘，从\1到\2，"),
    (re.compile(r"\\int\s*_\s*\{?([-+\d\w.=]+)\}?\s*\^\s*\{?([-+\d\w.=]+)\}?"),
     r"积分，从\1到\2，"),
    (re.compile(r"\\log\s*_\s*\{?(\w+)\}?"), r"以\1为底的对数"),
    # Prime: f'(x) -> f撇(x).
    (re.compile(r"\\prime\b"), "撇"),
    (re.compile(r"([\w\}])'"), r"\1撇"),
    # ---- relations / set operators (\\b-guarded: \\le must not eat \\left) -
    (re.compile(r"\\(?:le|leq|leqslant)\b"), "小于等于"),
    (re.compile(r"\\(?:ge|geq|geqslant)\b"), "大于等于"),
    (re.compile(r"\\(?:neq?)\b"), "不等于"),
    (re.compile(r"\\equiv"), "恒等于"),
    (re.compile(r"\\cong"), "全等于"),
    (re.compile(r"\\(?:simeq|approx)"), "约等于"),
    (re.compile(r"\\sim\b"), "相似于"),
    (re.compile(r"\\propto"), "成正比"),
    (re.compile(r"\\(?:perp)"), "垂直于"),
    (re.compile(r"\\(?:parallel|shortparallel)"), "平行于"),
    (re.compile(r"\\notin\b"), "不属于"),
    (re.compile(r"\\(?:in|isin)\b"), "属于"),
    (re.compile(r"\\(?:subseteqq?|subsetneq(?:q)?|subset)"), "包含于"),
    (re.compile(r"\\(?:supseteqq?|supset)"), "包含"),
    (re.compile(r"\\(?:cup|uplus)"), "并"),
    (re.compile(r"\\(?:cap|capwedge)"), "交"),
    (re.compile(r"\\setminus"), "差"),
    (re.compile(r"\\(?:emptyset|varnothing)"), "空集"),
    (re.compile(r"\\forall"), "任意"),
    (re.compile(r"\\(?:exists|exist)"), "存在"),
    (re.compile(r"\\(?:neg|lnot)"), "非"),
    (re.compile(r"\\(?:land|wedge|sqcap)"), "且"),
    (re.compile(r"\\(?:lor|vee|sqcup)"), "或"),
    (re.compile(r"\\(?:Rightarrow|Longrightarrow|implies|impl)"), "推出"),
    (re.compile(r"\\(?:Leftrightarrow|Longleftrightarrow|iff)"), "等价于"),
    (re.compile(r"\\mapsto"), "映射到"),
    (re.compile(r"\\mid\b"), "满足"),
    (re.compile(r"\\(?:nmid|nmid)"), "不整除"),
    # ---- geometry ---------------------------------------------------------
    (re.compile(r"\\(?:angle|measuredangle)"), "角"),
    (re.compile(r"\\(?:triangle|vartriangle)"), "三角形"),
    # ---- operators --------------------------------------------------------
    (re.compile(r"\\(?:pm)"), "正负"),
    (re.compile(r"\\(?:mp)"), "负正"),
    (re.compile(r"\\(?:times|cdot)"), "乘"),
    (re.compile(r"\\div\b"), "除以"),
    (re.compile(r"\\(?:ast|star)"), "乘"),
    (re.compile(r"\\(?:cdots|dots|ldots|vdots|ddots|adots)"), "等等"),
    (re.compile(r"\\(?:to\b|rightarrow|longrightarrow)"), "趋于"),
    (re.compile(r"\\infty"), "无穷"),
    (re.compile(r"\\(?:lim|limits)"), "极限"),
    (re.compile(r"\\int"), "积分"),
    (re.compile(r"\\sum"), "求和"),
    (re.compile(r"\\prod"), "连乘"),
    # ---- named functions --------------------------------------------------
    (re.compile(r"\\(?:arcsin|asin)"), "反正弦"),
    (re.compile(r"\\(?:arccos|acos)"), "反余弦"),
    (re.compile(r"\\(?:arctan|atan)"), "反正切"),
    (re.compile(r"\\sinh\b"), "双曲正弦"),
    (re.compile(r"\\cosh\b"), "双曲余弦"),
    (re.compile(r"\\tanh\b"), "双曲正切"),
    (re.compile(r"\\sin\b"), "正弦"),
    (re.compile(r"\\cos\b"), "余弦"),
    (re.compile(r"\\tan\b"), "正切"),
    (re.compile(r"\\cot\b"), "余切"),
    (re.compile(r"\\sec\b"), "正割"),
    (re.compile(r"\\csc\b"), "余割"),
    (re.compile(r"\\ln\b"), "自然对数"),
    (re.compile(r"\\lg\b"), "常用对数"),
    (re.compile(r"\\log\b"), "对数"),
    (re.compile(r"\\exp\b"), "指数函数"),
    (re.compile(r"\\max\b"), "最大值"),
    (re.compile(r"\\min\b"), "最小值"),
    (re.compile(r"\\sup\b"), "上确界"),
    (re.compile(r"\\inf\b"), "下确界"),
    (re.compile(r"\\gcd\b"), "最大公约数"),
    (re.compile(r"\\lcm\b"), "最小公倍数"),
    (re.compile(r"\\det\b"), "行列式"),
    (re.compile(r"\\dim\b"), "维数"),
    (re.compile(r"\\(?:bmod|mod)"), "模"),
    # ---- Greek letters: spoken Chinese names (math-class oral form) -------
    (re.compile(r"\\(?:alpha|upalpha)"), "阿尔法"),
    (re.compile(r"\\(?:beta|upbeta)"), "贝塔"),
    (re.compile(r"\\(?:gamma|Gamma|upgamma|upGamma)"), "伽马"),
    (re.compile(r"\\(?:delta|Delta|updelta|upDelta)"), "德尔塔"),
    (re.compile(r"\\(?:varepsilon|epsilon|upepsilon)"), "艾普西隆"),
    (re.compile(r"\\(?:zeta|upzeta)"), "泽塔"),
    (re.compile(r"\\(?:eta|upeta)"), "伊塔"),
    (re.compile(r"\\(?:theta|Theta|uptheta|upTheta)"), "西塔"),
    (re.compile(r"\\(?:iota|upiota)"), "伊奥塔"),
    (re.compile(r"\\(?:kappa|upkappa)"), "卡帕"),
    (re.compile(r"\\(?:lambda|Lambda|uplambda|upLambda)"), "拉姆达"),
    (re.compile(r"\\(?:mu|upmu)\b"), "缪"),
    (re.compile(r"\\(?:nu|upnu)"), "纽"),
    (re.compile(r"\\(?:xi|Xi|upxi|upXi)"), "克西"),
    (re.compile(r"\\pi\b|\\uppi\b"), "圆周率"),
    (re.compile(r"\\(?:rho|uprho)"), "柔"),
    (re.compile(r"\\(?:sigma|Sigma|upsigma|upSigma)"), "西格玛"),
    (re.compile(r"\\(?:tau|uptau)"), "陶"),
    (re.compile(r"\\(?:phi|varphi|Phi|upphi|upvarphi|upPhi)"), "斐"),
    (re.compile(r"\\(?:chi|upchi)"), "凯"),
    (re.compile(r"\\(?:psi|Psi|uppsi|upPsi)"), "普西"),
    (re.compile(r"\\(?:omega|Omega|upomega|upOmega)"), "欧米伽"),
    (re.compile(r"\\hbar"), "h拔"),
    # ---- matrix / delimiter scaffolding ----------------------------------
    (re.compile(r"\\(?:begin|end)\s*\{[a-zA-Z*]+\}"), ""),
    (re.compile(r"\\\{"), "集合"),
    (re.compile(r"\\\}"), ""),
    (re.compile(r"&"), "，"),
    (re.compile(r"\\\\(?:\s*\[\w+])?"), "，"),
    (re.compile(r"\\(?:bigl|bigr|Bigl|Bigr|biggl|biggr|Biggl|Biggr|left|right)\b"), ""),
    (re.compile(r"\\(?:quad|qquad|[,!;:>|<~]|\\|;|\s)"), " "),
    # ---- generic superscript / subscript ----------------------------------
    (re.compile(r"\^\s*\{([^{}]+)\}"), r"的\1次方"),
    (re.compile(r"\^\s*(\w)"), r"的\1次方"),
    (re.compile(r"_\s*\{([^{}]+)\}"), r"下标\1"),
    (re.compile(r"_\s*(\w)"), r"下标\1"),
    # Unknown commands keep their letters (English words beat deletion).
    (re.compile(r"\\([a-zA-Z]+)\s*"), r"\1 "),
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
    (re.compile(r"≤|≦"), "小于等于"),
    (re.compile(r"≥|≧"), "大于等于"),
    (re.compile(r"≠"), "不等于"),
    (re.compile(r"≈|≒"), "约等于"),
    (re.compile(r"≡"), "恒等于"),
    (re.compile(r"→|->|⟶"), "趋于"),
    (re.compile(r"π"), "圆周率"),
    (re.compile(r"∑"), "求和"),
    (re.compile(r"∫"), "积分"),
    (re.compile(r"√"), "根号"),
    (re.compile(r"∞"), "无穷"),
    (re.compile(r"∈"), "属于"),
    (re.compile(r"∪"), "并"),
    (re.compile(r"∩"), "交"),
    (re.compile(r"⊂|⊆"), "包含于"),
    (re.compile(r"⊥"), "垂直于"),
    (re.compile(r"∥"), "平行于"),
    (re.compile(r"∠"), "角"),
    (re.compile(r"△"), "三角形"),
    (re.compile(r"∵"), "因为"),
    (re.compile(r"∴"), "所以"),
    (re.compile(r"°"), "度"),
    (re.compile(r"′"), "撇"),
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
    # Number sets before the generic \text keeper flattens them.
    out = expr
    for pattern, reading in _MATHBB_SETS:
        out = pattern.sub(reading, out)
    out = _TEXT_KEEPER.sub(r"\1", out)
    # Argument groups collapse inside-out: \frac{\frac{1}{2}}{3} needs a
    # second pass over the substituted text. Bounded so a pathological
    # input can never loop forever.
    for _ in range(8):
        changed = False
        for pattern, reading in _MATH_READINGS_PASS:
            replaced = pattern.sub(reading, out)
            if replaced != out:
                changed = True
                out = replaced
        if not changed:
            break
    for pattern, reading in _MATH_READINGS:
        out = pattern.sub(reading, out)
    return out
