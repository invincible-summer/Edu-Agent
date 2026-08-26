"""Chroma vector index for the RAG vector track (optional, never fatal).

One embedded PersistentClient (no server process) with a single `materials`
collection (cosine space). Chunks are keyed by their deterministic chunk_id
("{file_id}#{idx}") so re-indexing is idempotent and old files backfill
naturally; each vector carries scope/file_id/source/index/page metadata.

Scope convention (mirrors the knowledge overlay): every chunk belongs to
exactly one scope, "session:{session_id}" or "workspace:{ws_id}", and
queries filter with `where={"scope": {"$in": scopes}}` — the same visibility
boundary the BM25 overlay enforces in memory.

Robustness contract: chromadb is lazily imported and EVERY entry point is
wrapped — any failure (missing package, corrupt db, embedding endpoint down)
disables the vector track with a one-time warning and the caller falls back
to pure BM25. Nothing here ever raises.
"""
from __future__ import annotations

import logging
from typing import Any

from .config import settings
from .retriever import Chunk

log = logging.getLogger(__name__)

_COLLECTION_NAME = "materials"
_GET_BATCH = 256      # ids per existence check
_UPSERT_BATCH = 128   # vectors per upsert

_client: Any | None = None
_collection: Any | None = None
_disabled = False
_warned = False


def _warn_once(msg: str, *args: Any) -> None:
    global _warned
    if not _warned:
        log.warning("RAG vector track disabled: " + msg, *args)
        _warned = True


def _disable(msg: str, *args: Any) -> None:
    global _disabled
    _disabled = True
    _warn_once(msg, *args)


def _get_collection():
    """Lazily create the client + collection; None when unavailable."""
    global _client, _collection
    if _disabled:
        return None
    if _collection is not None:
        return _collection
    try:
        import chromadb
        _client = chromadb.PersistentClient(path=settings.chroma_dir)
        _collection = _client.get_or_create_collection(
            name=_COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
        return _collection
    except Exception as e:
        _disable("chroma init failed (%s)", e)
        return None


def _reset() -> None:
    """Drop cached state (tests redirect chroma_dir between cases)."""
    global _client, _collection, _disabled, _warned
    _client = None
    _collection = None
    _disabled = False
    _warned = False


def _metadata(scope: str, c: Chunk) -> dict[str, Any]:
    # Chroma metadata values must be str/int/float/bool — page uses -1 for
    # "unknown" instead of None.
    return {"scope": scope, "file_id": c.file_id, "source": c.source,
            "index": c.index, "page": c.page if c.page is not None else -1}


async def ensure_indexed(scope: str, chunks: list[Chunk], embed_client: Any) -> bool:
    """Embed + upsert chunks missing from the index, then prune stale vectors
    that no longer correspond to any live chunk in this scope (idempotent).

    Rebuilds change chunk ids (text hash-stable but content may shift), so a
    naive upsert would leave orphans from the previous version — the RAG
    refresh must clean exactly the chunks it replaces, nothing else.
    """
    try:
        col = _get_collection()
        if col is None or embed_client is None or not chunks:
            return False
        ids = [c.chunk_id for c in chunks]
        live = set(ids)
        existing: set[str] = set()
        for i in range(0, len(ids), _GET_BATCH):
            got = col.get(ids=ids[i:i + _GET_BATCH])
            existing.update(got.get("ids") or [])
        missing = [c for c in chunks
                   if c.chunk_id not in existing
                   and not (c.metadata or {}).get("garble_excluded")]
        for i in range(0, len(missing), _UPSERT_BATCH):
            batch = missing[i:i + _UPSERT_BATCH]
            from .retriever import retrievable_text
            vectors = await embed_client.embed([retrievable_text(c) for c in batch])
            col.upsert(
                ids=[c.chunk_id for c in batch],
                embeddings=vectors,
                metadatas=[_metadata(scope, c) for c in batch],
            )
        # 旧版本孤儿向量：同 scope 但不在当前 chunk 集合里 → 删除（只删本
        # scope，不动其他教材/资料的向量）。失败只跳过，主路径不受影响。
        try:
            stale: list[str] = []
            offset = 0
            while True:
                got = col.get(where={"scope": scope}, include=[],
                              limit=_GET_BATCH, offset=offset)
                page = got.get("ids") or []
                if not page:
                    break
                stale.extend(i for i in page if i not in live)
                if len(page) < _GET_BATCH:
                    break
                offset += len(page)
            if stale:
                for i in range(0, len(stale), _GET_BATCH):
                    col.delete(ids=stale[i:i + _GET_BATCH])
        except Exception:
            pass  # 剪枝失败不影响主路径（下一轮刷新会再试）
        return True
    except Exception as e:
        _disable("ensure_indexed failed (%s)", e)
        return False


def query(query_vec: list[float], scopes: list[str], top_k: int) -> dict[str, float]:
    """Vector search restricted to the given scopes. Returns {chunk_id: distance},
    already ordered nearest-first (chroma's native ordering). Empty on failure."""
    try:
        col = _get_collection()
        if col is None or not scopes:
            return {}
        res = col.query(
            query_embeddings=[query_vec],
            n_results=max(1, top_k),
            where={"scope": {"$in": scopes}},
        )
        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        return dict(zip(ids, dists))
    except Exception as e:
        _disable("vector query failed (%s)", e)
        return {}


def delete_file(file_id: str) -> bool:
    """Remove every vector belonging to one file (any scope). Never raises."""
    try:
        col = _get_collection()
        if col is None:
            return False
        col.delete(where={"file_id": file_id})
        return True
    except Exception as e:
        _disable("vector delete_file failed (%s)", e)
        return False


def delete_scope(scope: str) -> bool:
    """Remove every vector in one scope (session/workspace teardown)."""
    try:
        col = _get_collection()
        if col is None:
            return False
        col.delete(where={"scope": scope})
        return True
    except Exception as e:
        _disable("vector delete_scope failed (%s)", e)
        return False
