"""
Qdrant REST client wrapper — collection management + upsert + search.

v3 §16.7: one collection per (product, purpose), namespaced
`{QDRANT_COLLECTION_PREFIX}_{purpose}`. Multi-tenancy is enforced via
the `tenant_id` payload filter on every query, NOT via separate
collections (that would explode the operational cost in shared Qdrant).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx

from core.config import get_settings
from core.logger import get_logger

logger = get_logger()


@dataclass
class QdrantStore:
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: float = 10.0
    collection_prefix: Optional[str] = None
    http_factory: Optional[object] = None

    @classmethod
    def from_settings(cls) -> "QdrantStore":
        s = get_settings()
        return cls(
            base_url=s.QDRANT_URL.rstrip("/"),
            api_key=s.QDRANT_API_KEY or None,
            timeout=s.QDRANT_TIMEOUT_SECONDS,
            collection_prefix=s.QDRANT_COLLECTION_PREFIX,
        )

    def collection_name(self, purpose: str) -> str:
        prefix = self.collection_prefix or "rag"
        return f"{prefix}_{purpose}"

    def _http(self):
        if self.http_factory is not None:
            return self.http_factory()
        return httpx.AsyncClient(timeout=self.timeout, base_url=self.base_url or "")

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["api-key"] = self.api_key
        return h

    # ── collection management ────────────────────────────────────────────

    async def ensure_collection(self, name: str, vector_size: int) -> None:
        """Idempotent: create the collection if it doesn't exist.

        Uses PUT /collections/{name} which Qdrant treats as "create or
        replace config". We first GET to skip creation when the collection
        already exists with the right shape — avoids accidentally
        wiping a populated collection.
        """
        async with self._http() as client:
            r = await client.get(f"/collections/{name}", headers=self._headers())
            if r.status_code == 200:
                return
            if r.status_code not in (404, 400):
                r.raise_for_status()

            r = await client.put(
                f"/collections/{name}",
                headers=self._headers(),
                json={
                    "vectors": {"size": vector_size, "distance": "Cosine"},
                },
            )
            r.raise_for_status()
            logger.info("qdrant_collection_created", name=name, dim=vector_size)

    # ── upsert ───────────────────────────────────────────────────────────

    async def upsert(
        self,
        collection: str,
        *,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> int:
        if not (len(ids) == len(vectors) == len(payloads)):
            raise ValueError("ids, vectors, payloads must have the same length")
        if not ids:
            return 0
        points = [
            {"id": _id, "vector": v, "payload": p}
            for _id, v, p in zip(ids, vectors, payloads)
        ]
        async with self._http() as client:
            r = await client.put(
                f"/collections/{collection}/points",
                headers=self._headers(),
                json={"points": points},
                params={"wait": "true"},
            )
            r.raise_for_status()
        return len(points)

    # ── search ───────────────────────────────────────────────────────────

    async def search(
        self,
        collection: str,
        *,
        query_vector: list[float],
        tenant_id: str,
        limit: int = 5,
        extra_filter: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Returns [{id, score, payload}, ...] for the top `limit` matches
        inside the tenant's namespace. Cross-tenant results never returned.
        """
        must = [{"key": "tenant_id", "match": {"value": tenant_id}}]
        if extra_filter:
            must.append(extra_filter)
        body = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
            "filter": {"must": must},
        }
        async with self._http() as client:
            r = await client.post(
                f"/collections/{collection}/points/search",
                headers=self._headers(),
                json=body,
            )
            r.raise_for_status()
            data = r.json()
        return [
            {"id": p["id"], "score": p["score"], "payload": p.get("payload") or {}}
            for p in data.get("result") or []
        ]

    # ── tenant cleanup (for LGPD delete-tenant integration) ─────────────

    async def delete_tenant_points(self, collection: str, tenant_id: str) -> None:
        """Delete every point with `payload.tenant_id == tenant_id`.
        Called from the LGPD delete-tenant path when RAG is in use.
        """
        async with self._http() as client:
            r = await client.post(
                f"/collections/{collection}/points/delete",
                headers=self._headers(),
                json={
                    "filter": {
                        "must": [
                            {"key": "tenant_id", "match": {"value": tenant_id}}
                        ]
                    }
                },
                params={"wait": "true"},
            )
            r.raise_for_status()
