"""
Tests for services/rag — embedder, qdrant client, and high-level service.

We never hit OpenAI or Qdrant for real. Instead each component takes a
`http_factory` callable; tests inject a fake httpx-shaped client that
records request URLs/bodies and returns scripted JSON.

Coverage:
  - Embedder.embed() batches inputs and unwraps the OpenAI response
  - Embedder.embed() raises without a key
  - QdrantStore.ensure_collection() short-circuits when 200, creates on 404
  - QdrantStore.search() always pushes a tenant_id filter
  - QdrantStore.upsert() validates aligned lengths and POSTs the points
  - QdrantStore.delete_tenant_points() builds the filter correctly
  - RAGService._chunk() respects the char limit + paragraph hint
  - RAGService.index_document() pipelines embed → ensure → upsert
  - RAGService.search() turns the query into vector + filtered search
  - RAGService.purge_tenant() iterates purposes and tolerates store errors
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pytest

from services.rag.embedder import Embedder
from services.rag.qdrant_client import QdrantStore
from services.rag.service import RAGService

pytestmark = pytest.mark.unit


# ── fake httpx ──────────────────────────────────────────────────────────────


@dataclass
class _RecordedRequest:
    method: str
    url: str
    json: Optional[dict] = None
    params: Optional[dict] = None
    headers: Optional[dict] = None


@dataclass
class _FakeResponse:
    status_code: int = 200
    _json: Any = None

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


@dataclass
class _FakeHttp:
    """Implements __aenter__/__aexit__ + get/post/put. Calls feed `recorded`."""
    recorded: list[_RecordedRequest] = field(default_factory=list)
    next_response: Callable[[_RecordedRequest], _FakeResponse] = field(default=lambda req: _FakeResponse())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def _capture(self, method, url, **kw):
        req = _RecordedRequest(
            method=method,
            url=url,
            json=kw.get("json"),
            params=kw.get("params"),
            headers=kw.get("headers"),
        )
        self.recorded.append(req)
        return self.next_response(req)

    async def get(self, url, **kw):
        return await self._capture("GET", url, **kw)

    async def post(self, url, **kw):
        return await self._capture("POST", url, **kw)

    async def put(self, url, **kw):
        return await self._capture("PUT", url, **kw)


def _factory_yielding(http: _FakeHttp):
    return lambda: http


# ════════════════════════════════════════════════════════════════════════════
# Embedder
# ════════════════════════════════════════════════════════════════════════════


async def test_embedder_requires_api_key():
    e = Embedder(api_key=None, model="text-embedding-3-large")
    with pytest.raises(ValueError):
        await e.embed(["x"])


async def test_embedder_returns_empty_on_empty_input():
    e = Embedder(api_key="sk-test", model="text-embedding-3-large")
    assert await e.embed([]) == []


async def test_embedder_single_batch_unwraps_vectors():
    http = _FakeHttp()
    http.next_response = lambda req: _FakeResponse(
        200,
        {"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]},
    )
    e = Embedder(
        api_key="sk-test",
        model="text-embedding-3-large",
        http_factory=_factory_yielding(http),
    )
    out = await e.embed(["a", "b"])
    assert out == [[0.1, 0.2], [0.3, 0.4]]
    # Authorization header on the request.
    assert len(http.recorded) == 1
    assert http.recorded[0].headers["Authorization"] == "Bearer sk-test"
    assert http.recorded[0].json == {
        "model": "text-embedding-3-large", "input": ["a", "b"]
    }


async def test_embedder_chunks_long_input_into_multiple_calls():
    http = _FakeHttp()
    # Always return one vector per chunk of size 1; total length will match.
    def respond(req):
        n = len(req.json["input"])
        return _FakeResponse(200, {"data": [{"embedding": [float(i)]} for i in range(n)]})
    http.next_response = respond

    e = Embedder(
        api_key="sk-test",
        model="text-embedding-3-large",
        http_factory=_factory_yielding(http),
    )
    # 250 inputs → 3 batches at the 100-max-batch cap.
    out = await e.embed([f"t{i}" for i in range(250)])
    assert len(out) == 250
    assert len(http.recorded) == 3


# ════════════════════════════════════════════════════════════════════════════
# QdrantStore
# ════════════════════════════════════════════════════════════════════════════


async def test_qdrant_ensure_collection_skips_when_already_exists():
    http = _FakeHttp()
    http.next_response = lambda req: _FakeResponse(200, {})
    q = QdrantStore(
        base_url="http://qdrant",
        collection_prefix="sil_proposta",
        http_factory=_factory_yielding(http),
    )
    await q.ensure_collection("sil_proposta_legislacao", vector_size=3072)
    # GET only — no PUT to create.
    assert [r.method for r in http.recorded] == ["GET"]


async def test_qdrant_ensure_collection_creates_on_404():
    http = _FakeHttp()
    responses = iter([
        _FakeResponse(404, {}),  # GET → not found
        _FakeResponse(200, {}),  # PUT create
    ])
    http.next_response = lambda req: next(responses)

    q = QdrantStore(
        base_url="http://qdrant",
        collection_prefix="sil_proposta",
        http_factory=_factory_yielding(http),
    )
    await q.ensure_collection("sil_proposta_legislacao", vector_size=128)
    assert [r.method for r in http.recorded] == ["GET", "PUT"]
    put_body = http.recorded[1].json
    assert put_body["vectors"]["size"] == 128
    assert put_body["vectors"]["distance"] == "Cosine"


async def test_qdrant_upsert_validates_aligned_lengths():
    q = QdrantStore(base_url="http://qdrant")
    with pytest.raises(ValueError):
        await q.upsert("c", ids=["a"], vectors=[], payloads=[{}])


async def test_qdrant_upsert_empty_is_noop():
    q = QdrantStore(base_url="http://qdrant")
    assert await q.upsert("c", ids=[], vectors=[], payloads=[]) == 0


async def test_qdrant_upsert_posts_points_with_wait():
    http = _FakeHttp()
    http.next_response = lambda req: _FakeResponse(200, {"status": "ok"})
    q = QdrantStore(
        base_url="http://qdrant",
        api_key="qd-key",
        http_factory=_factory_yielding(http),
    )
    n = await q.upsert(
        "sil_proposta_legislacao",
        ids=["id1", "id2"],
        vectors=[[0.1], [0.2]],
        payloads=[{"tenant_id": "t1"}, {"tenant_id": "t1"}],
    )
    assert n == 2
    req = http.recorded[0]
    assert req.method == "PUT"
    assert "/collections/sil_proposta_legislacao/points" in req.url
    assert req.params == {"wait": "true"}
    assert req.headers["api-key"] == "qd-key"
    body = req.json
    assert len(body["points"]) == 2
    assert body["points"][0] == {"id": "id1", "vector": [0.1], "payload": {"tenant_id": "t1"}}


async def test_qdrant_search_forces_tenant_filter():
    http = _FakeHttp()
    http.next_response = lambda req: _FakeResponse(
        200,
        {"result": [{"id": "x", "score": 0.99, "payload": {"text": "found"}}]},
    )
    q = QdrantStore(base_url="http://qdrant", http_factory=_factory_yielding(http))
    out = await q.search(
        "sil_proposta_legislacao",
        query_vector=[0.1, 0.2],
        tenant_id="t-alpha",
        limit=3,
    )
    assert out == [{"id": "x", "score": 0.99, "payload": {"text": "found"}}]
    req = http.recorded[0]
    must = req.json["filter"]["must"]
    assert must[0] == {"key": "tenant_id", "match": {"value": "t-alpha"}}


async def test_qdrant_delete_tenant_points_filters_by_tenant():
    http = _FakeHttp()
    http.next_response = lambda req: _FakeResponse(200, {})
    q = QdrantStore(base_url="http://qdrant", http_factory=_factory_yielding(http))
    await q.delete_tenant_points("sil_proposta_legislacao", "t-bye")
    req = http.recorded[0]
    assert req.method == "POST"
    assert "/points/delete" in req.url
    assert req.json["filter"]["must"][0]["match"]["value"] == "t-bye"


# ════════════════════════════════════════════════════════════════════════════
# RAGService
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class _StubEmbedder(Embedder):
    """Returns a fixed-size vector per input — no HTTP."""
    fixed_dim: int = 4
    calls: list[list[str]] = field(default_factory=list)

    async def embed(self, texts):  # type: ignore[override]
        self.calls.append(list(texts))
        return [[float(i)] * self.fixed_dim for i, _ in enumerate(texts, 1)]


@dataclass
class _StubStore:
    upserts: list[dict[str, Any]] = field(default_factory=list)
    ensured: list[tuple[str, int]] = field(default_factory=list)
    search_results: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[tuple[str, str]] = field(default_factory=list)
    raise_on_delete: bool = False
    collection_prefix: str = "sil_proposta"

    def collection_name(self, purpose: str) -> str:
        return f"{self.collection_prefix}_{purpose}"

    async def ensure_collection(self, name, vector_size):
        self.ensured.append((name, vector_size))

    async def upsert(self, collection, *, ids, vectors, payloads):
        self.upserts.append(
            {"collection": collection, "ids": ids, "vectors": vectors, "payloads": payloads}
        )
        return len(ids)

    async def search(self, collection, *, query_vector, tenant_id, limit, extra_filter=None):
        return self.search_results

    async def delete_tenant_points(self, collection, tenant_id):
        if self.raise_on_delete:
            raise RuntimeError("simulated")
        self.deleted.append((collection, tenant_id))


def test_chunk_returns_empty_for_blank_text():
    rag = RAGService(embedder=_StubEmbedder(api_key="k"), store=_StubStore())
    assert rag._chunk("") == []
    assert rag._chunk("   ") == []


def test_chunk_respects_max_chars():
    rag = RAGService(
        embedder=_StubEmbedder(api_key="k"),
        store=_StubStore(),
        chunk_max_chars=50,
    )
    text = "A" * 130
    out = rag._chunk(text)
    # 130 chars / 50 max → 3 chunks (50/50/30)
    assert len(out) == 3
    assert all(len(c) <= 50 for c in out)


def test_chunk_splits_on_double_newline_when_text_is_oversized():
    # Small texts stay as one chunk (early return). Splitting on \n\n only
    # kicks in when the whole document exceeds chunk_max_chars. Each
    # paragraph must itself fit in the limit, otherwise it gets sliced.
    rag = RAGService(
        embedder=_StubEmbedder(api_key="k"),
        store=_StubStore(),
        chunk_max_chars=15,
    )
    # Total length > 15 → \n\n splitter kicks in; each paragraph ≤ 15 chars.
    text = "Primeiro.\n\nSegundo.\n\nTerceiro."
    out = rag._chunk(text)
    assert out == ["Primeiro.", "Segundo.", "Terceiro."]


async def test_index_document_pipelines_embed_and_upsert():
    emb = _StubEmbedder(api_key="k", fixed_dim=4)
    store = _StubStore()
    rag = RAGService(embedder=emb, store=store, chunk_max_chars=20, default_purpose="legislacao")
    n = await rag.index_document(
        tenant_id="t1",
        document_id="doc-1",
        text="A" * 50,  # → 3 chunks at 20-char limit
        metadata={"source": "ConfazXX"},
    )
    assert n == 3
    assert len(emb.calls) == 1 and len(emb.calls[0]) == 3
    assert store.ensured == [("sil_proposta_legislacao", 4)]
    upserted = store.upserts[0]
    assert upserted["collection"] == "sil_proposta_legislacao"
    # Every payload carries tenant_id + document_id + chunk_index + source.
    for i, p in enumerate(upserted["payloads"]):
        assert p["tenant_id"] == "t1"
        assert p["document_id"] == "doc-1"
        assert p["chunk_index"] == i
        assert p["source"] == "ConfazXX"
        assert p["text"]


async def test_index_document_skips_empty_text():
    emb = _StubEmbedder(api_key="k")
    store = _StubStore()
    rag = RAGService(embedder=emb, store=store)
    assert await rag.index_document(tenant_id="t1", document_id="d1", text="") == 0
    assert emb.calls == []
    assert store.upserts == []


async def test_search_empty_query_short_circuits():
    rag = RAGService(embedder=_StubEmbedder(api_key="k"), store=_StubStore())
    assert await rag.search(tenant_id="t1", query="") == []
    assert await rag.search(tenant_id="t1", query="   ") == []


async def test_search_embeds_query_and_calls_store():
    emb = _StubEmbedder(api_key="k", fixed_dim=4)
    store = _StubStore(search_results=[{"id": "x", "score": 0.9, "payload": {"text": "hit"}}])
    rag = RAGService(embedder=emb, store=store)
    out = await rag.search(tenant_id="t1", query="diferimento ICMS", limit=2)
    assert out == [{"id": "x", "score": 0.9, "payload": {"text": "hit"}}]
    # Query embedded as a single string.
    assert emb.calls[-1] == ["diferimento ICMS"]


async def test_purge_tenant_iterates_purposes():
    store = _StubStore()
    rag = RAGService(embedder=_StubEmbedder(api_key="k"), store=store)
    await rag.purge_tenant("t1", purposes=["legislacao", "templates"])
    assert store.deleted == [
        ("sil_proposta_legislacao", "t1"),
        ("sil_proposta_templates", "t1"),
    ]


async def test_purge_tenant_swallows_store_error():
    store = _StubStore(raise_on_delete=True)
    rag = RAGService(embedder=_StubEmbedder(api_key="k"), store=store)
    # Should not raise — purge is best-effort.
    await rag.purge_tenant("t1", purposes=["legislacao"])
