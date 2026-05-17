"""
Content-hash dedupe for the historical PS corpus.

Same DAM exists as both .docx and .pdf in 30–50% of the dataset; we
hash the EXTRACTED TEXT (not the raw file) so different export formats
of the same content collapse into one corpus entry.

Why text-of-extraction and not bytes:
  - Bytes differ between .docx and .pdf of the same content.
  - Even between two .docx versions, embedded metadata changes the bytes
    on every save.
  - Hashing the normalized extracted text (lowercase, whitespace-collapsed)
    catches the real duplicates.

Hash is sha256 truncated to 16 hex chars — small enough for a Qdrant
payload field, large enough to keep collisions astronomically unlikely
for a corpus of this size.
"""
from __future__ import annotations

import hashlib
import re

_WS_RE = re.compile(r"\s+")


def content_fingerprint(text: str) -> str:
    """Return a stable, normalized fingerprint of the document content."""
    if not text:
        return "empty"
    normalized = _WS_RE.sub(" ", text.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
