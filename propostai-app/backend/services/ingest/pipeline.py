"""
End-to-end ingest pipeline for one document.

Stages (each fail-open and short-circuit on empty input):

  1. load_document   → plain text (no images, no embedded media)
  2. anonymize       → regex pass (CPF/CNPJ/email/phone/OP/PMS/PC/contrato + DAM→PS)
  3. anonymize_entities → spaCy NER pass (PER/ORG/LOC → [PESSOA_N]/[EMPRESA_N]/[LOCAL_N])
  4. (optional) llm_review_chunk on chunks `looks_like_residual_name` flags
  5. content_fingerprint for dedupe
  6. extract_metadata
  7. RAGService.index_document  → Qdrant (purpose="propostas_historicas")

The caller (CLI script) walks files, calls IngestPipeline.process(path),
and aggregates IngestResult into a manifest. The pipeline itself is
agnostic of paths and concurrency — it processes one doc at a time.

Tenant scoping: the corpus is intentionally GLOBAL (sentinel
tenant_id="_global"). Cross-tenant safety relies on anonymization, not
on Qdrant filters — see Sócrates agent for the rationale.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.logger import get_logger
from services.ingest.dedupe import content_fingerprint
from services.ingest.entity_anonymizer import (
    anonymize_entities,
    looks_like_residual_name,
)
from services.ingest.loaders import load_document
from services.ingest.metadata import extract_metadata
from services.lgpd.anonymizer import anonymize
from services.propostai.agents.llm_client import LLMClient
from services.rag.service import RAGService

logger = get_logger()

# Sentinel tenant_id for the global Sócrates corpus. Anything else in
# Qdrant is per-tenant; this is the one collection where multiple
# tenants read the same chunks.
GLOBAL_TENANT_ID = "_global"
RAG_PURPOSE = "propostas_historicas"


@dataclass
class IngestResult:
    source_path: Path
    success: bool
    skipped_reason: Optional[str] = None
    fingerprint: Optional[str] = None
    chunks_indexed: int = 0
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class IngestPipeline:
    rag: RAGService
    llm_reviewer: Optional[LLMClient] = None  # None disables LLM second-pass
    # Track fingerprints seen in this batch so duplicates short-circuit
    # before any expensive work.
    _seen_fingerprints: set[str] = field(default_factory=set)

    async def process(self, path: Path) -> IngestResult:
        try:
            return await self._process_unsafe(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingest_doc_failed", path=str(path), error=str(exc))
            return IngestResult(
                source_path=path, success=False, error=str(exc),
            )

    async def _process_unsafe(self, path: Path) -> IngestResult:
        # 1. load
        text = load_document(path)
        if text is None:
            return IngestResult(
                source_path=path, success=False,
                skipped_reason="unsupported_format",
            )
        if not text.strip():
            return IngestResult(
                source_path=path, success=False, skipped_reason="empty_text",
            )

        # 2. regex anonymize (incl. DAM→PS rewrite)
        text = anonymize(text) or ""

        # 3. NER anonymize
        text = anonymize_entities(text)

        # 4. (optional) LLM review on suspicious chunks
        if self.llm_reviewer is not None:
            text = await self._llm_review_chunks(text)

        # 5. dedupe — content fingerprint after anonymization so cosmetic
        # differences (Cliente A vs Cliente B versions of the same boilerplate)
        # don't both consume embedding budget.
        fp = content_fingerprint(text)
        if fp in self._seen_fingerprints:
            return IngestResult(
                source_path=path, success=False,
                skipped_reason="duplicate", fingerprint=fp,
            )
        self._seen_fingerprints.add(fp)

        # 6. metadata
        meta = extract_metadata(text, path)

        # 7. index
        chunks = await self.rag.index_document(
            tenant_id=GLOBAL_TENANT_ID,
            document_id=fp,
            text=text,
            purpose=RAG_PURPOSE,
            metadata=meta.as_payload(),
        )

        return IngestResult(
            source_path=path,
            success=True,
            fingerprint=fp,
            chunks_indexed=chunks,
            metadata=meta.as_payload(),
        )

    async def _llm_review_chunks(self, text: str) -> str:
        """Chunk on paragraph boundaries, review only suspicious ones,
        recombine. Order preserved.
        """
        from services.ingest.llm_review import llm_review_chunk

        paragraphs = text.split("\n\n")
        tasks: list = []
        idx_map: list[int] = []  # which paragraph each task reviews
        for i, para in enumerate(paragraphs):
            if looks_like_residual_name(para):
                tasks.append(llm_review_chunk(para, self.llm_reviewer))
                idx_map.append(i)
        if not tasks:
            return text
        reviewed = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in zip(idx_map, reviewed):
            if isinstance(result, str):
                paragraphs[i] = result
        return "\n\n".join(paragraphs)
