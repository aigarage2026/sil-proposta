"""
LGPD anonymizer — strips Brazilian PII before sending text to an external LLM.

Decision recorded in v3 §4.5.5 E2 ("Anonimização LGPD antes de mandar pra
LLM") and reinforced by the [DAM Quality Gap] memory: anonymize ONLY on
the path to an external LLM. The DB and the internal context keep the
real values. Reversing anonymization on the LLM's response is a separate
problem we do not solve here — token stability would require a per-call
mapping, which the call sites can build on top of `_iter_replacements()`.

Patterns covered (forward-only):
  - CPF        →  [CPF]
  - CNPJ       →  [CNPJ]
  - e-mail     →  [EMAIL]
  - telefone   →  [TELEFONE]   (BR formats: (XX) 9XXXX-XXXX, (XX) XXXX-XXXX,
                                 +55 XX XXXX-XXXX, and the bare 10/11-digit
                                 form when separated by spaces)

CPF/CNPJ matching is shape-based, not check-digit-validated — false
positives on long ID strings are acceptable when the cost of leaking real
ones is much higher. The patterns require the standard punctuation so we
do not over-trigger on random 11-digit sequences (order numbers, IDs).

Config: `should_anonymize_for_tenant(tenant)` reads the boolean feature
`lgpd_anonymize_llm` from `tenant.features` (default True — fail-closed).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

CPF_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
CNPJ_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Brazilian phone formats — punctuated only. Bare digit sequences are not
# matched: too easy to false-positive on order/PMS numbers.
TELEFONE_RE = re.compile(
    r"(?:\+?55[\s-]?)?(?:\(\d{2}\)|\d{2})[\s-]?\d{4,5}[\s-]\d{4}\b"
)

# Order matters: e-mail before telefone, so a number-bearing local-part
# (e.g. user2024@example.com) doesn't get phone-masked first.
PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (CPF_RE, "[CPF]"),
    (CNPJ_RE, "[CNPJ]"),
    (EMAIL_RE, "[EMAIL]"),
    (TELEFONE_RE, "[TELEFONE]"),
)


def anonymize(text: Optional[str]) -> Optional[str]:
    """Return `text` with PII replaced by tokens. None / empty → unchanged."""
    if not text:
        return text
    out = text
    for pattern, token in PATTERNS:
        out = pattern.sub(token, out)
    return out


def anonymize_payload(payload: dict, fields: Iterable[str]) -> dict:
    """Apply anonymize() to selected string fields of a dict (shallow).
    Returns a new dict; original is not mutated. Non-string field values
    pass through untouched.
    """
    out = dict(payload)
    for f in fields:
        v = out.get(f)
        if isinstance(v, str):
            out[f] = anonymize(v)
    return out


def should_anonymize_for_tenant(tenant) -> bool:
    """Tenant-level toggle. Defaults to True (fail-closed: anonymize unless
    explicitly opted out). Accepts None gracefully — treated as default.
    """
    if tenant is None:
        return True
    features = getattr(tenant, "features", None) or {}
    value = features.get("lgpd_anonymize_llm")
    if value is None:
        return True
    return bool(value)
