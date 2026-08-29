"""Independent learning-result ledger.

Question/answer/score/concept/time records are learning outcomes, not chat
content. They survive conversation archive and permanent chat purge. A source
session id is retained only as a navigational reference and is blanked from the
user-facing view when that conversation is permanently gone.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .atomic import atomic_write_text, file_lock

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_STUDENTS_DIR = _PROJECT_ROOT / "students"


def _safe(value: str) -> str:
    return Path(str(value or "")).name


def _path(student_id: str) -> Path:
    return _STUDENTS_DIR / f"{_safe(student_id)}.learning_records.json"


def _load(student_id: str) -> dict[str, Any]:
    path = _path(student_id)
    if not path.exists():
        return {"version": 1, "records": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return data
    except Exception:
        pass
    return {"version": 1, "records": []}


def _save(student_id: str, data: dict[str, Any]) -> None:
    _STUDENTS_DIR.mkdir(parents=True, exist_ok=True)
    data["version"] = 1
    data["updated_at"] = time.time()
    # This is the independent learning archive. Unlike the bounded UI cache
    # in quiz_recent, it must not silently discard older questions or scores.
    data["records"] = list(data.get("records") or [])
    atomic_write_text(_path(student_id), json.dumps(data, ensure_ascii=False, indent=2))


def _unique_ids(records: list[dict[str, Any]]) -> bool:
    """Re-key duplicate/empty record_ids in place; True when anything changed.

    Question ids are per-quiz in-set numbers (each quiz restarts at 1, every
    CAT question is "1"), so legacy ledgers can hold the same id several
    times. Nothing joins on record_id — verdicts match by session+stem,
    trash handlers by session — so re-keying is safe.
    """
    seen: set[str] = set()
    changed = False
    for item in records:
        rid = str(item.get("record_id") or "")
        if rid and rid not in seen:
            seen.add(rid)
            continue
        item["record_id"] = "lr_" + uuid.uuid4().hex[:16]
        changed = True
    return changed


def record_question(student_id: str, session_id: str, question: dict[str, Any], *,
                    topic: str = "", subject: str = "", grade: str = "",
                    source_kind: str = "chat") -> str:
    """Create or reuse a durable question record before grading."""
    if not student_id or not isinstance(question, dict):
        return ""
    question_id = str(question.get("id") or "") or "lr_" + uuid.uuid4().hex[:16]
    stem = str(question.get("stem") or "").strip()
    if not stem:
        return ""
    path = _path(student_id)
    with file_lock(path):
        data = _load(student_id)
        healed = _unique_ids(data["records"])
        stem_key = stem[:100]
        for item in data["records"]:
            if (item.get("record_id") == question_id
                    and item.get("session_id") == _safe(session_id)
                    and str(item.get("stem") or "").strip()[:100] == stem_key):
                if healed:
                    _save(student_id, data)
                return question_id
        # Any other occurrence of this id — in another session, or earlier in
        # this one filing a different question — is an in-set numbering
        # collision, not a replay: give this record a fresh unique id.
        taken = {str(item.get("record_id") or "") for item in data["records"]}
        while question_id in taken:
            question_id = "lr_" + uuid.uuid4().hex[:16]
        data["records"].append({
            "record_id": question_id,
            "session_id": _safe(session_id),
            "source_kind": source_kind if source_kind in {"chat", "assessment"} else "chat",
            "source_status": "active" if source_kind == "chat" else "independent",
            "created_at": time.time(),
            "updated_at": time.time(),
            "topic": str(topic or question.get("topic") or "")[:100],
            "subject": str(subject or "")[:80],
            "grade": str(grade or "")[:40],
            "knowledge_point": str(question.get("knowledge_point") or question.get("concept") or "")[:120],
            "knowledge_points": list(question.get("knowledge_points") or [])[:20],
            # 布鲁姆认知层级标签（题目生成时由出题器标注；旧记录无此键安全缺省）
            "bloom_level": str(question.get("bloom_level") or "")[:24],
            "stem": stem[:1000],
            "type": str(question.get("type") or question.get("q_type") or "multiple_choice"),
            "difficulty": question.get("difficulty", ""),
            "correct_answer": str(question.get("answer") or "")[:1000],
            "explanation": str(question.get("explanation") or "")[:1500],
            "student_answer": "",
            "verdict": "",
            "score": None,
        })
        _save(student_id, data)
    return question_id


def record_verdict(student_id: str, session_id: str, *, stem: str,
                   verdict: str, student_answer: str = "", score: float | None = None,
                   concept: str = "", subject: str = "",
                   source_kind: str = "chat") -> bool:
    if not student_id or not session_id or not stem:
        return False
    key = str(stem).strip()[:100]
    path = _path(student_id)
    with file_lock(path):
        data = _load(student_id)
        candidates = [x for x in reversed(data["records"])
                      if x.get("session_id") == _safe(session_id)
                      and str(x.get("stem") or "").strip()[:100] == key]
        if not candidates:
            record_question(student_id, session_id, {
                "stem": stem, "answer": "", "explanation": "",
                "knowledge_point": concept, "type": "short_answer"},
                subject=subject, source_kind=source_kind)
            data = _load(student_id)
            candidates = [x for x in reversed(data["records"])
                          if x.get("session_id") == _safe(session_id)
                          and str(x.get("stem") or "").strip()[:100] == key]
        if not candidates:
            return False
        item = candidates[0]
        item["verdict"] = str(verdict or "")
        item["student_answer"] = str(student_answer or "")[:1000]
        if score is not None:
            item["score"] = float(score)
        if concept:
            item["knowledge_point"] = str(concept)[:120]
        if subject:
            item["subject"] = str(subject)[:80]
        item["updated_at"] = time.time()
        _save(student_id, data)
        return True


def mark_source_deleted(student_id: str, session_id: str) -> int:
    path = _path(student_id)
    with file_lock(path):
        data = _load(student_id)
        changed = 0
        for item in data["records"]:
            if item.get("session_id") == _safe(session_id) and item.get("source_status") != "deleted":
                item["source_status"] = "deleted"
                item["source_message"] = "来源对话已删除，无法查看"
                item["updated_at"] = time.time()
                changed += 1
        if changed:
            _save(student_id, data)
        return changed


def detach_source_session(student_id: str, session_id: str) -> int:
    """Irreversibly remove a permanently deleted chat's source identifier.

    Learning outcomes remain intact, but the ledger can no longer be joined
    back to the erased conversation. This is intentionally separate from
    ``mark_source_deleted`` so an archived (still restorable) chat retains its
    internal association until permanent purge.
    """
    sid = _safe(session_id)
    path = _path(student_id)
    with file_lock(path):
        data = _load(student_id)
        changed = 0
        for item in data["records"]:
            if item.get("session_id") == sid:
                item["session_id"] = ""
                item["source_status"] = "deleted"
                item["source_message"] = "来源对话已永久删除，无法查看"
                item["updated_at"] = time.time()
                changed += 1
        if changed:
            _save(student_id, data)
        return changed


def mark_source_active(student_id: str, session_id: str) -> int:
    path = _path(student_id)
    with file_lock(path):
        data = _load(student_id)
        changed = 0
        for item in data["records"]:
            if item.get("session_id") == _safe(session_id) and item.get("source_status") == "deleted":
                item["source_status"] = "active"
                item.pop("source_message", None)
                item["updated_at"] = time.time()
                changed += 1
        if changed:
            _save(student_id, data)
        return changed


def list_records(student_id: str) -> list[dict[str, Any]]:
    try:
        records = list(reversed(_load(student_id).get("records") or []))
        # Display-side guard for legacy duplicate ids (persisted heal happens
        # on the next write via record_question); ids are not persisted here.
        _unique_ids(records)
        return records
    except Exception:
        return []
