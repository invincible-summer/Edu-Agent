"""Long-task advisor (M9): LLM execution suggestions for long-term tasks.

Each LongTermTask ("每天背 20 个单词") carries 1-3 concrete, personal
suggestions — how to execute it well given the goal, the student's current
mastery gap and schedule. One LLM call fills a whole batch (only entries
that lack suggestions), so goal-time enrichment costs a single round-trip.

Deterministic guardrails: the gate (parse_suggest_response) only accepts
suggestions keyed by the exact task ids we sent, 1-3 per task, length
capped; any failure degrades to template suggestions (never empty, never
raises). IMPORT-CLEAN: pure functions over plain data.
"""
from __future__ import annotations

import json
import re
from typing import Any

_TEMPLATES = [
    "拆成最小可执行单元，固定在每天同一时段做，降低启动成本。",
    "完成后在今日任务里打卡，连续记录会形成习惯连击。",
    "与本周周计划的任务绑定：先完成它再开始新内容。",
]


def build_suggest_prompt(goal_title: str, goal_level: str,
                         daily_minutes: int,
                         tasks: list[dict[str, str]],
                         context: str = "") -> list[dict[str, str]]:
    """Build the chat messages for the batch-suggestion LLM call.

    context: optional grounded context (goal-chain concepts / recently
    taught concepts / weak concepts) so suggestions reference what the
    student is actually working on instead of generic boilerplate.
    """
    lines = "\n".join(f"- id={t['id']}：{t['title']}" for t in tasks)
    context_block = f"\n{context.strip()}\n" if context and context.strip() else ""
    system = ("你是一名学习教练，擅长把flag式长期任务落成可执行的具体做法。"
              "只输出 JSON，不要输出任何其他内容。")
    user = f"""学生的长期目标：{goal_title or "（未设定）"}（当前水平：{goal_level or "未知"}，每天可学 {daily_minutes} 分钟）。{context_block}学生给自己定的长期任务：
{lines}

请为每个任务给 1-2 条具体、可执行的建议（怎么坚持、怎么与当前学习结合、什么时段做），每条 30 字以内，说人话，不要鸡汤。建议要结合上面的学习上下文（如有），不要泛泛而谈。

输出 JSON 格式（不要输出其他内容）：
```json
{{"suggestions": [{{"id": "任务id", "tips": ["建议一", "建议二"]}}]}}
```"""
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(text[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def parse_suggest_response(text: str, ids: list[str]) -> dict[str, list[str]] | None:
    """Parse + validate the batch suggestions. None on any gate failure.

    Gate: every returned id must be one we asked about; 1-3 non-empty tips
    per entry (capped to 3, each trimmed to 120 chars). Never raises.
    """
    try:
        obj = _extract_json(text)
        if not obj or not isinstance(obj.get("suggestions"), list):
            return None
        allowed = set(ids)
        out: dict[str, list[str]] = {}
        for entry in obj["suggestions"]:
            if not isinstance(entry, dict):
                return None
            tid = str(entry.get("id", ""))
            if tid not in allowed:
                return None
            tips = [str(t).strip()[:120]
                    for t in (entry.get("tips") or [])
                    if str(t).strip()][:3]
            if not tips:
                return None
            out[tid] = tips
        return out or None
    except Exception:
        return None


def fallback_suggestions(title: str) -> list[str]:
    """Deterministic suggestions when the LLM is unavailable (never empty)."""
    return list(_TEMPLATES[:2])
