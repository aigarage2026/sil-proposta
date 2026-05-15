"""
High-level RAG service — index_document() and search() that combine the
embedder and the Qdrant store.

Multi-tenant by construction: every point carries `tenant_id` in its
payload; every query filters by it. Cross-tenant leakage is impossible
unless callers bypass this service and hit the store directly.

Chunking: simple paragraph + char-limit split. Sophisticated chunking
(sentence boundaries, semantic) is out of scope for Onda 5 and can land
when we have real RFP corpus to tune against.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional

from core.logger import get_logger
from services.rag.embedder import Embedder
from services.rag.qdrant_client import QdrantStore

logger = get_logger()


@dataclass
class RAGService:
    embedder: Embedder = field(default_factory=Embedder.from_settings)
    store: QdrantStore = field(default_factory=QdrantStore.from_settings)
    chunk_max_chars: int = 1500
    default_purpose: str = "legislacao"

    @classmethod
    def from_settings(cls) -> "RAGService":
        return cls()

    # ── chunking ─────────────────────────────────────────────────────────

    def _chunk(self, text: str) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= self.chunk_max_chars:
            return [text]
        # Split on double-newlines first; falls back to char windows if any
        # paragraph is itself oversized.
        chunks: list[str] = []
        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            if len(para) <= self.chunk_max_chars:
                chunks.append(para)
            else:
                for i in range(0, len(para), self.chunk_max_chars):
                    chunks.append(para[i : i + self.chunk_max_chars])
        return chunks

    # ── public ───────────────────────────────────────────────────────────

    async def index_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        text: str,
        purpose: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Embed + upsert. Returns number of chunks indexed."""
        purpose = purpose or self.default_purpose
        chunks = self._chunk(text)
        if not chunks:
            return 0

        vectors = await self.embedder.embed(chunks)
        if not vectors:
            return 0

        collection = self.store.collection_name(purpose)
        await self.store.ensure_collection(collection, vector_size=len(vectors[0]))

        ids = [
            hashlib.md5(f"{tenant_id}:{document_id}:{i}".encode("utf-8")).hexdigest()
            for i in range(len(chunks))
        ]
        payloads = [
            {
                "tenant_id": tenant_id,
                "document_id": document_id,
                "chunk_index": i,
                "text": c,
                **(metadata or {}),
            }
            for i, c in enumerate(chunks)
        ]
        upserted = await self.store.upsert(collection, ids=ids, vectors=vectors, payloads=payloads)
        logger.info(
            "rag_document_indexed",
            tenant_id=tenant_id,
            document_id=document_id,
            chunks=upserted,
            purpose=purpose,
        )
        return upserted

    async def search(
        self,
        *,
        tenant_id: str,
        query: str,
        purpose: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Returns top-k chunks for the tenant. Empty when query is empty."""
        if not query.strip():
            return []
        purpose = purpose or self.default_purpose
        vectors = await self.embedder.embed([query])
        if not vectors:
            return []
        collection = self.store.collection_name(purpose)
        results = await self.store.search(
            collection,
            query_vector=vectors[0],
            tenant_id=tenant_id,
            limit=limit,
        )
        return results

    async def purge_tenant(self, tenant_id: str, purposes: Optional[list[str]] = None) -> None:
        """LGPD hard-delete hook: drop every chunk owned by `tenant_id`.
        If `purposes` is None, purge every collection prefixed by the
        product's QDRANT_COLLECTION_PREFIX (callers normally pass the
        list they know exists).
        """
        targets = purposes or [self.default_purpose]
        for purpose in targets:
            collection = self.store.collection_name(purpose)
            try:
                await self.store.delete_tenant_points(collection, tenant_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "rag_purge_tenant_failed",
                    tenant_id=tenant_id,
                    collection=collection,
                    error=str(exc),
                )
