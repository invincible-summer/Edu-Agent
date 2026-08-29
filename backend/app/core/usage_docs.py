"""Usage docs: the admin-editable, all-user-readable /docs page content.

One global markdown document, stored at chat_history/settings/usage_docs.json
(alongside the OCR runtime policy — the established admin-settings root, no
per-owner attribution so the orphan scanner never touches it). Storage
contract mirrors ocr_policy: defensive read (missing/corrupt -> bootstrap
default), file_lock + atomic write. The document is version content, not user
runtime data, so it is safe to rewrite wholesale on save.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .atomic import atomic_write_text, file_lock

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DOCS_FILE = _PROJECT_ROOT / "chat_history" / "settings" / "usage_docs.json"

# size cap: a usage doc well beyond this is almost certainly a paste error
_MAX_MARKDOWN_CHARS = 200_000

_DEFAULT_MARKDOWN = """# 使用文档

欢迎来到 Next Tutor Agent —— 教材驱动的 AI 一对一辅导系统。

## 快速上手
1. 在「知识图谱」浏览教材概念，或在对话里直接提问；
2. 「学习编排」设定长期目标，系统生成周计划与每日任务；
3. 「测评中心」做自适应测评，弱项会自动进入学习账本；
4. 「我的画像」查看系统对你的理解（风格/目标/认知层级）。

> 本文档由管理员维护：管理员登录后可在本页直接编辑（支持 Markdown）。
"""


def _bootstrap() -> dict[str, Any]:
    return {"markdown": _DEFAULT_MARKDOWN, "updated_at": 0.0, "updated_by": ""}


def read_docs() -> dict[str, Any]:
    """Read the usage doc; missing/corrupt file -> bootstrap default.

    Never raises (the page must render for everyone even with a bad file).
    """
    try:
        data = json.loads(_DOCS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _bootstrap()
        md = str(data.get("markdown") or "")
        return {
            "markdown": md if md else _bootstrap()["markdown"],
            "updated_at": float(data.get("updated_at") or 0.0),
            "updated_by": str(data.get("updated_by") or ""),
        }
    except Exception:
        return _bootstrap()


def write_docs(markdown: str, *, updated_by: str = "") -> dict[str, Any]:
    """Persist a new doc version (atomic + lock). Returns the stored payload.

    Raises ValueError when the markdown exceeds the size cap; other failures
    raise OSError so the API can surface a 500 rather than silently dropping
    an admin edit.
    """
    md = str(markdown or "")
    if len(md) > _MAX_MARKDOWN_CHARS:
        raise ValueError("document too large")
    payload = {"markdown": md, "updated_at": time.time(),
               "updated_by": str(updated_by or "")}
    _DOCS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(_DOCS_FILE):
        atomic_write_text(_DOCS_FILE, json.dumps(payload, ensure_ascii=False))
    return payload
