"""
PS (Proposta de Solução) historical-corpus ingest.

Loads, anonymizes, and indexes legacy DAM documents (Word/PDF/Excel) into
the Qdrant `propostai_propostas_historicas` collection so the Sócrates
agent can match new RFPs against past patterns.

The pipeline is one-way: originals stay on disk, only anonymized chunks
reach Qdrant. There is no path from a chunk back to a source filename or
client name — that's by design (see Sócrates contract).
"""
from services.ingest.loaders import load_document
from services.ingest.pipeline import IngestPipeline, IngestResult

__all__ = ["load_document", "IngestPipeline", "IngestResult"]
