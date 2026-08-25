"""Embedding client for the RAG vector track (OpenAI-compatible Embeddings API).

Uses direct AsyncOpenAI transport (no shell proxy inheritance), plus semaphore
and exponential backoff, for the Embeddings endpoint. The vector
track is OPTIONAL: when EMBEDDING_API_KEY is unset, get_embedding_client()
returns None and every caller falls back to pure BM25 — the system never
depends on this client being available.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from openai import AsyncOpenAI
from openai import RateLimitError, APITimeoutError, APIConnectionError, APIStatusError

from .config import settings

log = logging.getLogger(__name__)

_BATCH_SIZE = 64     # embeddings per API call
_RETRY_MAX = 3
_RETRY_BASE_DELAY = 1.0


class EmbeddingClient:
    """Batched, retried wrapper around an OpenAI-compatible Embeddings API."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: float = 60.0):
        self.model = model or settings.embedding_model
        effective_url = base_url or settings.embedding_base_url
        # Direct network policy: do not inherit HTTP(S)_PROXY/ALL_PROXY.
        trust_env = False
        self.client = AsyncOpenAI(
            api_key=api_key or settings.embedding_api_key,
            base_url=effective_url,
            timeout=timeout,
            max_retries=0,  # retries handled below (same policy as llm_async)
            http_client=httpx.AsyncClient(trust_env=trust_env, timeout=timeout),
        )
        self._semaphore = asyncio.Semaphore(2)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches; returns one vector per input text.

        Raises after retries are exhausted — callers (vector_store/hybrid)
        treat any exception as "vector track unavailable" and fall back.
        """
        if not texts:
            return []
        vectors: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i:i + _BATCH_SIZE]
            vectors.extend(await self._embed_batch(batch))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._semaphore:
                    resp = await self.client.embeddings.create(
                        model=self.model, input=batch)
                # The API returns items in input order, but sort by index to
                # be safe — a misordered batch would silently corrupt the index.
                items = sorted(resp.data, key=lambda d: d.index)
                return [list(d.embedding) for d in items]
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                if attempt >= _RETRY_MAX:
                    raise
                await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            except APIStatusError as e:
                if e.status_code == 429 and attempt < _RETRY_MAX:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                    continue
                raise


_INSTANCE: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient | None:
    """Process-level cached client, or None when the vector track is off.

    The track is off when EMBEDDING_API_KEY (or an explicit base url/model)
    is not configured — mirroring the MULTIMODAL_* dual-track pattern.
    """
    global _INSTANCE
    if not settings.embedding_api_key:
        return None
    if _INSTANCE is None:
        try:
            _INSTANCE = EmbeddingClient()
        except Exception as e:
            log.warning("embedding client init failed; vector track disabled: %s", e)
            return None
    return _INSTANCE
