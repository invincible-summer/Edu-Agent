#!/usr/bin/env python3
"""P9 验收回放：对公共教材库只读重放 3252512295 账号的取证问句。

不写任何存储、不调用任何 LLM/OCR API。加载公共库 chunks → 逐问句走
knowledge_search 的同款链路（多变体 BM25 召回 + 证据门 + 上下文重建），
打印 top-3/分级/摘录首行，用于人工核对修复效果。

用法（在 backend/ 下）：
    python scripts/replay_knowledge_queries.py            # 全部取证问句
    python scripts/replay_knowledge_queries.py 荷塘月色    # 按关键词过滤
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.library import load_library  # noqa: E402
from app.core.textbook import PUBLIC_STUDENT_ID  # noqa: E402

# 2026-08-25/26 取证问句（chat_history/trace 复盘原句）。
FORENSIC_QUERIES = [
    "拿来主义讲了什么",
    "《荷塘月色讲了什么》",
    "《荷塘月色讲》",
    "洛伦兹变化是什么",
    "伽利略变化是什么",
    "《我与地坛》是什么主题",
    "《沁园春长沙》是什么",
    "对数运算律是什么",
]


def _excerpt_head(item: dict, chars: int = 60) -> str:
    text = " ".join(str(item.get("evidence_excerpt") or "").split())
    return text[:chars] + ("…" if len(text) > chars else "")


async def replay(filter_text: str = "") -> None:
    from app.core.knowledge_store import KnowledgeStore
    from app.core.evidence_gate import apply_evidence_gate, effective_query
    from app.core.evidence_context import reconstruct_evidence

    lib = load_library(PUBLIC_STUDENT_ID)
    store = KnowledgeStore()
    store.chunks = []
    for meta in lib.files:
        fid = str(meta.get("id") or "")
        for c in lib.chunks_for(fid):
            c.file_id = fid
            store.chunks.append(c)
    if not store.chunks:
        print("公共库没有可回放的 chunks")
        return
    print(f"公共库载入 {len(store.chunks)} chunks / {len(lib.files)} 文件\n")

    chunk_index = {c.chunk_id: c for c in store.chunks}

    def chunk_lookup(chunk_id: str):
        c = chunk_index.get(str(chunk_id or ""))
        if c is None:
            return None
        return {"text": c.text, "metadata": dict(c.metadata or {})}

    queries = [q for q in FORENSIC_QUERIES if filter_text in q]
    for query in queries:
        # 与 KnowledgeSearchTool._multi_search 同源：多变体 + RRF 简化版
        # （回放只取首变体 top48，足以观察门控与重建行为）。
        core = effective_query(query)
        from app.core.retriever import BM25Index
        hits = BM25Index(store.chunks).search(core or query, top_k=48)
        candidates = []
        for rank, (c, score) in enumerate(hits):
            metadata = c.metadata or {}
            candidates.append({
                "source": c.source, "filename": c.source, "file_id": c.file_id,
                "chunk_id": c.chunk_id, "index": c.index, "text": c.text,
                "score": round(score, 3), "bm25_score": score, "page": c.page,
                "printed_page": metadata.get("printed_page"),
                "block_types": list(metadata.get("block_types", [])),
                "section_path": list(metadata.get("section_path", [])),
                "lesson": metadata.get("lesson"),
                "is_lesson": bool(metadata.get("is_lesson")),
            })
        gate = apply_evidence_gate(query, candidates, top_k=6)
        results = reconstruct_evidence(gate.selected, chunk_lookup) if gate.selected else []
        print(f"Q: {query}")
        print(f"   核心词: {core!r}   tier={gate.tier}   候选={len(candidates)} "
              f"选中={len(results)}   drops={gate.drop_reasons}")
        for r in results[:3]:
            label = r.get("lesson_label") or r.get("section") or r.get("chapter") or ""
            loc = (f"教材第{r['printed_page']}页" if r.get("printed_page")
                   else f"PDF第{r.get('page')}页")
            print(f"   [{r.get('confidence')}·{'低' if r.get('partial') else 'ok'}] "
                  f"{loc} {label} :: {_excerpt_head(r)}")
        if not results:
            print("   （NOT_FOUND）")
        print()


if __name__ == "__main__":
    asyncio.run(replay(sys.argv[1] if len(sys.argv) > 1 else ""))
