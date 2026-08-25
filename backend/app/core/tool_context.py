"""Tool-specific context projections; full results remain in business stores/SSE."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .config import settings
from .context import estimate_tokens
from .tool_protocol import ToolResult
from .trace import trace_dir_path


class ToolResultRetention(str, Enum):
    CURRENT_FULL = "current_full"
    RECENT_SUMMARY = "recent_summary"
    ARCHIVE_POINTER = "archive_pointer"


@dataclass(frozen=True)
class ToolContextProjection:
    tool: str
    retention: str
    text: str
    result_ref: str = ""
    projected_tokens: int = 0
    original_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _spill(tool: str, text: str) -> str:
    path = trace_dir_path() / f"tool_spill_{tool}_{int(time.time())}.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _quiz_projection(result: ToolResult) -> str:
    questions = result.data.get("questions", []) if isinstance(result.data, dict) else []
    lines: list[str] = []
    for i, q in enumerate(questions[:5], 1):
        if not isinstance(q, dict):
            continue
        # 题干/解析给足全文量级：模型要据此逐题讲解、点评和回答追问。
        stem = str(q.get("stem") or "").strip()[:300]
        answer = str(q.get("answer") or "").strip()[:60]
        explanation = str(q.get("explanation") or "").strip()[:260]
        kp = str(q.get("knowledge_point") or "").strip()[:30]
        seg = f"{i}. [{q.get('type', 'multiple_choice')}] {stem}｜答案:{answer}"
        if kp:
            seg += f"｜考点:{kp}"
        if explanation:
            seg += f"｜解析:{explanation}"
        lines.append(seg)
    digest = "\n".join(lines)
    return (f"[工具 {result.tool} 完成]\n"
            f"已生成 {len(questions)} 道结构化题目，题目卡已由前端渲染。"
            "题目内容如下（供你后续逐题讲解、点评和学生提问时引用）：\n"
            f"{digest}\n"
            "现在不要在正文重复题干、选项或解析；只引导学生先作答。"
            "学生作答或追问题目时，按上面的内容逐题讲解。")


def project_knowledge_evidence(result: ToolResult, limit: int) -> str:
    """Budget whole selected evidence blocks; never cut a material delimiter."""
    rows = result.data.get("results", []) if isinstance(result.data, dict) else []
    if not isinstance(rows, list) or not rows:
        return result.text[:limit]
    head = (f"从课程资料中筛选出 {len(rows)} 条可靠证据"
            f"（过滤 {int(result.data.get('omitted_count', 0) or 0)} 条）：")
    parts = [head]
    used = len(head)
    for row in rows:
        if not isinstance(row, dict):
            continue
        excerpt = str(row.get("evidence_excerpt") or row.get("text") or "").strip()
        source = str(row.get("filename") or row.get("source") or "资料")
        location = f" · 第{row.get('page')}页" if row.get("page") else ""
        confidence = row.get("confidence")
        block = (f"[来源：{source}{location} · chunk {row.get('index', 0)}]"
                 f" (置信度 {confidence})\n"
                 f"<material_excerpt>{excerpt}</material_excerpt>")
        if used + len(block) + 2 > limit:
            break
        parts.append(block)
        used += len(block) + 2
    if len(parts) == 1 and rows:
        # Keep one complete excerpt even when an unusually small custom limit is set.
        row = rows[0]
        excerpt = str(row.get("evidence_excerpt") or row.get("text") or "")
        source = str(row.get("filename") or row.get("source") or "资料")
        parts.append(f"[来源：{source}]\n<material_excerpt>{excerpt}</material_excerpt>")
    return "\n\n".join(parts)


def project_tool_result(result: ToolResult,
                        retention: ToolResultRetention = ToolResultRetention.CURRENT_FULL
                        ) -> ToolContextProjection:
    original = ((result.text or "") + "\n" +
                json.dumps(result.data, ensure_ascii=False, default=str))
    ref = ""
    if result.tool in {"generate_quiz", "fit_quiz"} and not result.is_error:
        text = _quiz_projection(result)
    elif result.tool in {"knowledge_search", "recall_history"} and result.text:
        limit = settings.tool_context_current_max_chars
        if retention == ToolResultRetention.RECENT_SUMMARY:
            limit = min(limit, 900)
        elif retention == ToolResultRetention.ARCHIVE_POINTER:
            limit = settings.tool_context_old_preview_chars
        if result.tool == "knowledge_search" and settings.rag_context_compress:
            body = project_knowledge_evidence(result, limit)
        else:
            body = result.text
            if len(body) > limit:
                ref = _spill(result.tool, body)
                body = body[:limit] + f"\n...[完整结果已保存: {ref}]"
        text = f"[工具 {result.tool} 完成]\n{body}"
    else:
        payload = json.dumps(result.data, ensure_ascii=False, default=str)[:1200]
        text = f"[工具 {result.tool} 完成]\n数据摘要：{payload}"
    return ToolContextProjection(
        tool=result.tool, retention=retention.value, text=text,
        result_ref=ref, projected_tokens=estimate_tokens(text),
        original_tokens=estimate_tokens(original))
