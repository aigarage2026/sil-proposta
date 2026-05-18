"""
Heuristic metadata extractor for the historical PS corpus.

Outputs the small payload Sócrates filters on at search time. We never
extract anything that would re-identify a client:
  - year       (from filename if "2023" / "2024" / "2025" appears,
                else from filesystem mtime)
  - modules    (set of SAP modules detected: SD/FI/MM/CO/PP/HR/ABAP/...)
  - doc_type   (PS / PT / PC — inferred from filename prefix or "DAM")
  - size_band  (small/medium/large/xl, inferred from text length as a
                rough proxy for project size — see SIZE_BANDS)
  - has_abap   (boolean shortcut for "this involved ABAP development")
  - has_fiscal (boolean shortcut for fiscal/legislation work)

These fields go into the Qdrant payload and are usable as filters.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

_MODULES = ("SD", "FI", "MM", "CO", "PP", "HR", "QM", "WM", "BASIS", "ABAP")
_FISCAL_HINTS = ("cBenef", "NF-e", "EFD", "REINF", "ICMS", "SEFAZ", "DRC",
                 "ECONF", "Reforma Tributária", "LC 214", "IBS", "CBS")

_YEAR_RE = re.compile(r"\b(20[1-3]\d)\b")
_DOCTYPE_PREFIX_RE = re.compile(r"^\s*(PS|PT|PC|DAM)\b", re.IGNORECASE)

# Char-length bands → project size proxy. Tuned on a sample of historical
# DAMs (small adjustments are not catastrophic; Sócrates uses this as a
# weak filter, not a hard cut).
SIZE_BANDS: tuple[tuple[int, str], ...] = (
    (3_000, "small"),
    (10_000, "medium"),
    (30_000, "large"),
)
SIZE_DEFAULT = "xl"


@dataclass(frozen=True)
class DocMetadata:
    year: Optional[int]
    modules: tuple[str, ...]
    doc_type: str
    size_band: str
    has_abap: bool
    has_fiscal: bool

    def as_payload(self) -> dict:
        return {
            "year": self.year,
            "modules": list(self.modules),
            "doc_type": self.doc_type,
            "size_band": self.size_band,
            "has_abap": self.has_abap,
            "has_fiscal": self.has_fiscal,
        }


def extract_metadata(text: str, source_path: Path) -> DocMetadata:
    name = source_path.name

    year = _extract_year(name) or _mtime_year(source_path)
    modules = _detect_modules(text)
    doc_type = _infer_doc_type(name)
    size_band = _size_band(text)
    has_abap = "ABAP" in modules
    has_fiscal = any(h.lower() in text.lower() for h in _FISCAL_HINTS)

    return DocMetadata(
        year=year,
        modules=modules,
        doc_type=doc_type,
        size_band=size_band,
        has_abap=has_abap,
        has_fiscal=has_fiscal,
    )


def _extract_year(name: str) -> Optional[int]:
    m = _YEAR_RE.search(name)
    return int(m.group(1)) if m else None


def _mtime_year(path: Path) -> Optional[int]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).year
    except OSError:
        return None


def _detect_modules(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    # Require a word boundary so we don't pick up "SDH" matching "SD".
    found = []
    upper = text.upper()
    for mod in _MODULES:
        if re.search(rf"\b{mod}\b", upper):
            found.append(mod)
    return tuple(found)


def _infer_doc_type(name: str) -> str:
    m = _DOCTYPE_PREFIX_RE.match(name)
    if not m:
        return "PS"  # default: treat as PS
    raw = m.group(1).upper()
    # DAM is the legacy name — collapse to PS in the metadata.
    return "PS" if raw == "DAM" else raw


def _size_band(text: str) -> str:
    n = len(text or "")
    for limit, band in SIZE_BANDS:
        if n < limit:
            return band
    return SIZE_DEFAULT
