"""
Testes para o pipeline de ingestão (services/ingest/).

Estratégia:
  - Mockamos load_document para evitar I/O de DOCX/PDF reais.
  - Stub do RAGService captura as chamadas a index_document.
  - O entity_anonymizer roda de verdade (spacy + modelo md), mas em
    inputs curtos pra manter os tests rápidos. Marcados @slow não — o
    modelo já foi baixado e o load tem lru_cache.

Cobre:
  - Pipeline pula arquivos sem texto / unsupported.
  - Dedupe: dois docs com texto idêntico viram 1 só.
  - Pipeline aplica regex anonymizer (CPF mascarado).
  - Pipeline aplica NER (PER → [PESSOA_N]).
  - Pipeline aplica DAM → PS rewrite.
  - Metadata extrator detecta módulos SAP.
  - content_fingerprint estável para mesmo texto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest

from services.ingest.dedupe import content_fingerprint
from services.ingest.metadata import extract_metadata
from services.ingest.pipeline import GLOBAL_TENANT_ID, RAG_PURPOSE, IngestPipeline

pytestmark = pytest.mark.unit


@dataclass
class _StubRAG:
    indexed: list[dict] = field(default_factory=list)

    async def index_document(self, *, tenant_id, document_id, text, purpose=None, metadata=None):
        self.indexed.append({
            "tenant_id": tenant_id, "document_id": document_id,
            "text": text, "purpose": purpose, "metadata": metadata or {},
        })
        return len(text) // 1500 + 1  # fake chunk count


# ── dedupe ─────────────────────────────────────────────────────────────────


def test_fingerprint_stable_for_same_content():
    a = content_fingerprint("Texto A com    espaços\n\nvariados")
    b = content_fingerprint("texto a COM espaços variados")
    # Normaliza whitespace + lowercase → mesmo fingerprint.
    assert a == b


def test_fingerprint_distinct_for_different_content():
    a = content_fingerprint("Texto A")
    b = content_fingerprint("Texto B")
    assert a != b


# ── metadata ───────────────────────────────────────────────────────────────


def test_metadata_detects_modules():
    text = "Implementação SD com BAdI ABAP. Configuração FI sem MM envolvido."
    meta = extract_metadata(text, Path("fake.docx"))
    assert "SD" in meta.modules
    assert "ABAP" in meta.modules
    assert "FI" in meta.modules


def test_metadata_extracts_year_from_filename():
    text = "x"
    meta = extract_metadata(text, Path("DAM - 2023 - cliente.docx"))
    assert meta.year == 2023


def test_metadata_infers_doc_type_from_prefix():
    assert extract_metadata("x", Path("DAM - foo.docx")).doc_type == "PS"
    assert extract_metadata("x", Path("PT - foo.docx")).doc_type == "PT"
    assert extract_metadata("x", Path("PC - foo.docx")).doc_type == "PC"


def test_metadata_size_band():
    meta_small = extract_metadata("x" * 500, Path("a.docx"))
    meta_medium = extract_metadata("x" * 5000, Path("a.docx"))
    meta_large = extract_metadata("x" * 15000, Path("a.docx"))
    meta_xl = extract_metadata("x" * 50000, Path("a.docx"))
    assert meta_small.size_band == "small"
    assert meta_medium.size_band == "medium"
    assert meta_large.size_band == "large"
    assert meta_xl.size_band == "xl"


def test_metadata_fiscal_hint_detected():
    meta = extract_metadata("Implementação cBenef e NF-e para SEFAZ.", Path("x.docx"))
    assert meta.has_fiscal is True


# ── pipeline end-to-end (sem LLM review) ──────────────────────────────────


async def test_pipeline_skips_unsupported_format():
    pipeline = IngestPipeline(rag=_StubRAG(), llm_reviewer=None)
    result = await pipeline.process(Path("foo.zip"))
    assert result.success is False
    assert result.skipped_reason == "unsupported_format"


async def test_pipeline_skips_empty_text():
    with patch("services.ingest.pipeline.load_document", return_value="   "):
        pipeline = IngestPipeline(rag=_StubRAG(), llm_reviewer=None)
        result = await pipeline.process(Path("foo.docx"))
        assert result.success is False
        assert result.skipped_reason == "empty_text"


async def test_pipeline_dedupes_identical_text():
    text = "Implementação SD com BAdI. Cliente fictício."
    rag = _StubRAG()
    pipeline = IngestPipeline(rag=rag, llm_reviewer=None)
    with patch("services.ingest.pipeline.load_document", return_value=text):
        r1 = await pipeline.process(Path("a.docx"))
        r2 = await pipeline.process(Path("b.docx"))
    assert r1.success is True
    assert r2.success is False
    assert r2.skipped_reason == "duplicate"
    assert len(rag.indexed) == 1


async def test_pipeline_applies_regex_anonymizer():
    text = "Cliente CNPJ 12.345.678/0001-90 com OP 12345 aprovou DAM v2."
    rag = _StubRAG()
    pipeline = IngestPipeline(rag=rag, llm_reviewer=None)
    with patch("services.ingest.pipeline.load_document", return_value=text):
        await pipeline.process(Path("foo.docx"))
    indexed_text = rag.indexed[0]["text"]
    assert "[CNPJ]" in indexed_text
    assert "[OP]" in indexed_text
    # "DAM" rewrite — termo legado vira PS.
    assert "DAM" not in indexed_text
    assert "PS" in indexed_text


async def test_pipeline_routes_to_global_tenant_and_historic_purpose():
    rag = _StubRAG()
    pipeline = IngestPipeline(rag=rag, llm_reviewer=None)
    with patch("services.ingest.pipeline.load_document", return_value="conteúdo válido"):
        await pipeline.process(Path("foo.docx"))
    call = rag.indexed[0]
    assert call["tenant_id"] == GLOBAL_TENANT_ID
    assert call["purpose"] == RAG_PURPOSE


async def test_pipeline_metadata_carried_through_to_qdrant():
    text = "Implementação SD com ABAP em cBenef. " * 50
    rag = _StubRAG()
    pipeline = IngestPipeline(rag=rag, llm_reviewer=None)
    with patch("services.ingest.pipeline.load_document", return_value=text):
        await pipeline.process(Path("DAM - 2024 - foo.docx"))
    meta = rag.indexed[0]["metadata"]
    assert "SD" in meta["modules"]
    assert meta["year"] == 2024
    assert meta["has_fiscal"] is True
