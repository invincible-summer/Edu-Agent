"""Task Understanding: turn the student's natural-language message into a
structured learning task (intent / subject / concept / goal).

Three paths, tried in order (Hybrid Understanding):
  1. Rule short-circuit -- greetings/acks -> CHITCHAT (no LLM call, saves
     tokens + latency, preserves V1's "don't loop on '你好'" behavior).
  2. LLM structured output -- for substantive questions, a low-budget
     non-streaming call returns a JSON task object.
  3. Rule-based fallback -- if the LLM fails/returns junk, coarse-classify by
     keyword triggers into a best-guess task type.

Every path returns a TaskUnderstanding; `source` records which path won so the
trace can explain the resulting plan.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..core.llm_async import AsyncLLMClient
from ..core.session import TutorSession
from .state import TaskType, TaskUnderstanding

# --- rule layer (mirrors + extends V1 chat_agent._classify_intent) ------------

# Exact greetings / acks -> direct chat, no tools, no LLM understanding call.
_GREETINGS = {
    "你好", "您好", "hi", "hello", "hey", "在吗", "在", "谢谢", "感谢",
    "好的", "ok", "嗯", "嗯嗯", "收到", "了解", "明白", "知道了",
    "行", "好", "666", "好的好的", "thx", "thanks", "bye", "再见",
}

# Keyword -> TaskType. First match wins (order matters: specific before general).
# These cover the V1 _TOOL_TRIGGERS plus a few diagnostic/review signals.
_KW_RULES: list[tuple[tuple[str, ...], TaskType]] = [
    (("出题", "练习", "测验", "测一测", "巩固", "考考", "做题", "刷题",
      "几道题", "道题", "出几道"), TaskType.PRACTICE),
    (("错题", "分析错", "为什么总错", "为什么老错", "薄弱", "哪里不懂",
      "诊断", "为什么做错"), TaskType.DIAGNOSE),
    (("复习", "总结", "回顾", "梳理", "归纳"), TaskType.REVIEW),
    (("计划", "怎么学", "学习路线", "学习计划", "复习计划", "规划"), TaskType.PLAN),
    (("解一下", "这道题", "算一下", "求解", "怎么算", "解题", "算出"), TaskType.SOLVE),
    (("生成", "帮我写", "编一道", "设计一道", "教案"), TaskType.GENERATE),
]

# "explain" signals -- broadest. Used both as a fast-path and as the fallback.
_EXPLAIN_KW = ("讲一下", "讲讲", "讲解", "解释", "是什么", "什么是", "为什么",
               "怎么理解", "我不懂", "我不会", "没懂", "没理解", "没学会",
              "原理", "概念", "帮我讲")

_ONE_SENTENCE_RE = re.compile(r"一句话|一两句话|one\s+sentence", re.I)
_CONCISE_RE = re.compile(r"简短|简洁|简单说|只要结论|不要展开|不要详细", re.I)
_TABLE_RE = re.compile(r"表格|对比表", re.I)
_STEPS_RE = re.compile(r"分步骤|按步骤|逐步", re.I)
_NO_ASSESS_RE = re.compile(r"不要(?:出题|测验|练习)|不需要(?:出题|测验|练习)|只(?:要|需)讲解|只回答", re.I)
_ASSESS_RE = re.compile(r"出.{0,5}题|练习|测验|测一测|考考|检测题|诊断题|做题", re.I)


def detect_response_constraints(msg: str) -> tuple[str, bool]:
    """Extract hard presentation constraints before adaptive teaching logic.

    A request such as “一句话解释 X” is not merely a style preference: it
    is a user-visible contract.  It suppresses the default closing assessment
    unless the same message explicitly asks for a quiz.
    """
    text = msg.strip()
    if _ONE_SENTENCE_RE.search(text):
        fmt = "one_sentence"
    elif _CONCISE_RE.search(text):
        fmt = "concise"
    elif _TABLE_RE.search(text):
        fmt = "table"
    elif _STEPS_RE.search(text):
        fmt = "steps"
    else:
        fmt = ""
    explicit_assessment = bool(_ASSESS_RE.search(text))
    allow_assessment = not bool(_NO_ASSESS_RE.search(text))
    if fmt in {"one_sentence", "concise"} and not explicit_assessment:
        allow_assessment = False
    return fmt, allow_assessment

# Regex patterns for spoken variants the substring keywords miss. Ordered
# most-specific first; first match wins. (re is imported at module top.)
_RULE_PATTERNS: list[tuple["re.Pattern[str]", TaskType]] = [
    (re.compile(r"出.{0,8}题"), TaskType.PRACTICE),       # 出5道...题 / 出两道题
    (re.compile(r"[做刷].{0,4}题"), TaskType.PRACTICE),   # 做题 / 刷几道题
    (re.compile(r"[总老].{0,4}错"), TaskType.DIAGNOSE),   # 总做错 / 老错
]

# Subject hints by keyword (best-effort, not authoritative).
_SUBJECT_KW: list[tuple[tuple[str, ...], str]] = [
   (("物理", "力", "运动", "电", "磁", "光", "热", "波", "能量", "功"), "物理"),
    (("牛顿", "定律", "惯性", "重力", "摩擦", "压强", "浮力", "密度"), "物理"),
    (("数学", "函数", "方程", "几何", "代数", "微积分", "导数", "积分",
      "三角", "向量", "概率", "统计", "数列"), "数学"),
    (("化学", "反应", "元素", "分子", "原子", "离子", "化学键", "有机"), "化学"),
    (("生物", "细胞", "基因", "遗传", "光合", "生态", "进化", "DNA"), "生物"),
    (("英语", "语法", "单词", "时态", "从句", "translation"), "英语"),
    (("语文", "文言文", "古诗", "阅读理解", "作文", "修辞"), "语文"),
    (("历史", "地理", "政治"), "文科综合"),
]


def _is_greeting(msg: str) -> bool:
    msg = msg.strip().lower()
    if msg in _GREETINGS:
        return True
    # very short (<5 chars) no punctuation -> treat as greeting/ack ONLY if it
    # carries no substantive signal (subject keyword or a teach/solve verb).
    # e.g. "讲惯性" is short but clearly an explain request, not a greeting.
    if len(msg) < 5 and not any(c in msg for c in "？！，。、,.?"):
        has_subject = any(any(kw in msg for kw in kws) for kws, _ in _SUBJECT_KW)
        starts_verb = any(msg.startswith(v) for v in
                          ("讲", "解", "算", "出", "为什么", "怎么", "帮"))
        if not has_subject and not starts_verb and not any(kw in msg for kw in _EXPLAIN_KW):
            return True
    return False


def _rule_classify(msg: str) -> TaskType:
    """Best-guess TaskType from keywords (no LLM). Falls back to EXPLAIN."""
    for kws, ttype in _KW_RULES:
        if any(kw in msg for kw in kws):
            return ttype
    # Looser path: regex patterns catch split-up spoken variants that exact
    # substrings miss (e.g. "出5道...题" -> PRACTICE, "总...做错" -> DIAGNOSE).
    for pat, ttype in _RULE_PATTERNS:
        if pat.search(msg):
            return ttype
    if any(kw in msg for kw in _EXPLAIN_KW):
        return TaskType.EXPLAIN
    return TaskType.EXPLAIN  # default teaching intent


def _guess_subject(msg: str) -> str:
    for kws, subj in _SUBJECT_KW:
        if any(kw in msg for kw in kws):
            return subj
    return ""


def _guess_concept(msg: str) -> str:
    """Best-effort concept extraction: strip leading politeness/verbs and
    punctuation, keep the short noun-ish remainder."""
    m = msg.strip()
    for lead in ("请用一句话", "用一句话", "请简短地", "简短地", "简短",
                 "我不会", "我不懂", "没懂", "没理解", "没学会",
                 "讲一下", "讲讲", "讲解一下", "讲解", "解释一下", "解释",
                 "什么是", "什么叫做", "请问", "帮我", "麻烦"):
        if m.startswith(lead):
            m = m[len(lead):]
    m = m.strip("，。、,.?？！！ \t\n")
    return m[:30]  # cap length; the planner/LLM will refine


def rule_understand(msg: str) -> TaskUnderstanding:
    """Pure rule path. CHITCHAT for greetings, else coarse-classify."""
    if _is_greeting(msg):
        return TaskUnderstanding(intent=TaskType.CHITCHAT, source="rule",
                                 requires_tools=False, confidence=1.0)
    ttype = _rule_classify(msg)
    response_format, allow_assessment = detect_response_constraints(msg)
    return TaskUnderstanding(
        intent=ttype,
        subject=_guess_subject(msg),
        concept=_guess_concept(msg),
        goal="practice" if ttype == TaskType.PRACTICE else "understand",
        requires_tools=ttype in (TaskType.PRACTICE, TaskType.DIAGNOSE),
        confidence=0.5,
        source="rule",
        response_format=response_format,
        allow_followup_assessment=allow_assessment,
    )


# --- LLM layer ---------------------------------------------------------------

from ..prompts.registry import get as _prompt

# 阶段D：prompt 文本统一由注册表管理（含版本号），此处薄 re-export 兼容。
_UNDERSTAND_SYSTEM = _prompt("understand_system").text


def _extract_json(text: str) -> dict[str, Any] | None:
    """Robustly pull a JSON object out of an LLM response."""
    if not text:
        return None
    text = text.strip()
    # strip ```json ... ``` fences if present
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        # last resort: find the first {...} block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
    return None


async def llm_understand(msg: str, llm: AsyncLLMClient) -> TaskUnderstanding | None:
    """LLM structured-output path. Returns None on any failure so the caller
    can fall back to rules (never raises into the turn)."""
    try:
        content, usage = await llm.complete(
            [{"role": "system", "content": _UNDERSTAND_SYSTEM},
             {"role": "user", "content": msg}],
            temperature=0.1,
            max_tokens=300,
            disable_thinking=True,  # JSON extraction: reasoning would starve the budget
        )
    except Exception:
        return None
    if not content:
        return None
    obj = _extract_json(content)
    if not obj:
        return None
    intent = TaskType.from_value(obj.get("intent"))
    if intent is None:
        return None  # junk intent -> let rules decide
    requires = obj.get("requires_tools")
    if not isinstance(requires, bool):
        # infer from intent if the model omitted/typed it wrong
        requires = intent in (TaskType.PRACTICE, TaskType.DIAGNOSE)
    return TaskUnderstanding(
        intent=intent,
        subject=str(obj.get("subject", "") or ""),
        concept=str(obj.get("concept", "") or ""),
        goal=str(obj.get("goal", "") or ""),
        difficulty=obj.get("difficulty") if isinstance(obj.get("difficulty"), str) else None,
        requires_tools=requires,
        response_format=str(obj.get("response_format", "") or ""),
        allow_followup_assessment=bool(obj.get("allow_followup_assessment", True)),
        confidence=0.8,
        source="llm",
    )


# --- public entry point ------------------------------------------------------

def _use_llm(understanding: "TaskUnderstanding | None") -> bool:
    """Whether to spend an LLM call. We only call the LLM when rules are
    uncertain: a high-confidence greeting/ack already settled it."""
    return understanding is None or (
        understanding.source == "rule" and understanding.intent != TaskType.CHITCHAT
    )


async def understand(msg: str, session: TutorSession, llm: AsyncLLMClient | None = None,
                     *, use_llm: bool | None = None) -> TaskUnderstanding:
    """Top-level task understanding.

    Order: rule short-circuit -> (optional) LLM -> rule fallback.
    A CHITCHAT rule result is final (no LLM). For substantive questions we try
    the LLM; if it fails we keep the rule result with source='fallback'.

    `use_llm` overrides the env-driven default (None = read env var)."""
    import os
    if use_llm is None:
        use_llm = os.getenv("SUPERVISOR_LLM_UNDERSTAND", "1") not in ("0", "false", "False")

    ruled = rule_understand(msg)
    if ruled.intent == TaskType.CHITCHAT:
        return ruled  # greeting/ack: never spend an LLM call

    if not use_llm or llm is None:
        return ruled

    llm_result = await llm_understand(msg, llm)
    if llm_result is not None:
        # Deterministic lexical constraints override an LLM style guess. The
        # student should not lose “一句话/不要出题” because the classifier
        # chose a remediation mode.
        response_format, allow_assessment = detect_response_constraints(msg)
        if response_format:
            llm_result.response_format = response_format
        if not allow_assessment:
            llm_result.allow_followup_assessment = False
        return llm_result

    # LLM failed -> degrade to the rule result, tagged as fallback
    return TaskUnderstanding(
        intent=ruled.intent, subject=ruled.subject, concept=ruled.concept,
        goal=ruled.goal, requires_tools=ruled.requires_tools,
        response_format=ruled.response_format,
        allow_followup_assessment=ruled.allow_followup_assessment,
        confidence=0.4, source="fallback",
    )
