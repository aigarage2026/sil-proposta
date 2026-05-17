"""
NER-based anonymizer for organization / person / location names.

Layer 2 of the pipeline (Layer 1 = regex anonymizer in services/lgpd/).
spaCy's pt_core_news_md tags PER / ORG / LOC entities; we replace each
unique surface form with a stable token of the form `[EMPRESA_3]`,
`[PESSOA_1]`, `[LOCAL_2]` — the integer is per-document so the same
client name reads consistently across chunks of the same DAM.

Cross-document consistency is NOT a goal: we are not building a key,
and seeing "EMPRESA_3" in two different chunks of two different
documents means two unrelated entities. This is safer than risking
real-name collisions.

Why pt_core_news_md (not _lg): _lg adds ~500 MB for marginal recall
gains in this domain (SAP proposals lean on common Brazilian names that
md already handles). The LLM second-pass (llm_review.py) catches what
md misses.

Acknowledged failure modes:
  - spaCy frequently mis-tags SAP module codes (SD/FI/MM) as ORG. We
    keep a stop-list to skip these.
  - Person names that double as common words (e.g., "Marcos" the name
    vs. "marcos legais") may slip; LLM review catches these.
"""
from __future__ import annotations

import functools
import re
from typing import Optional

# Module codes / acronyms spaCy tends to flag as ORG but are domain jargon.
_DOMAIN_STOPWORDS = frozenset({
    "sap", "abap", "sd", "fi", "mm", "co", "pp", "hr", "qm", "wm",
    "basis", "ams", "drc", "cpi", "ecc", "s4", "s/4", "s4hana", "s/4hana",
    "ehp", "spro", "nfe", "nf-e", "ctprime", "ctd", "tef", "sefaz",
    "fpi", "fatu", "imposto", "tributário", "fiscal",
    "icms", "ipi", "pis", "cofins", "iss", "irrf", "csll",
    "rfp", "ps", "wp", "kt", "qas", "prd", "dev",
    "go", "go-live", "kick-off", "kickoff",
    "direto ao ponto", "diretoaoponto",  # nossa marca (não anonimizar)
    "ai garage", "ai-garage",            # nossa marca
})

# Entity types we want to mask. spaCy pt-br emits: PER, ORG, LOC, MISC.
# We intentionally skip MISC (too noisy) and rely on regex for PII.
_TYPE_TO_TOKEN = {
    "PER": "PESSOA",
    "ORG": "EMPRESA",
    "LOC": "LOCAL",
}


@functools.lru_cache(maxsize=1)
def _nlp():
    """Load spaCy lazily — model is ~50 MB, no need to pay the cost in
    test runs that don't use NER.
    """
    import spacy

    return spacy.load("pt_core_news_md", disable=["lemmatizer", "tagger"])


def _is_stopword(surface: str) -> bool:
    s = surface.strip().lower()
    if len(s) <= 2:  # one/two-letter "entities" are almost always noise
        return True
    return s in _DOMAIN_STOPWORDS


# Existing anonymization tokens like [CNPJ], [PESSOA_3], [OP] etc. would
# otherwise be re-tagged by spaCy (a bare "CNPJ" looks like an org). We
# mask them with neutral placeholders before NER and restore after.
_EXISTING_TOKEN_RE = re.compile(r"\[[A-ZÁÉÍÓÚÂÊÔÃÕÇ_]+(?:_\d+)?\]")


def anonymize_entities(text: Optional[str]) -> str:
    """Replace person/org/location names with stable per-document tokens.

    Returns the text unchanged when input is empty. Idempotent on input
    that already contains tokens (the regex won't re-match them).
    """
    if not text:
        return text or ""

    # 1. Stash existing anonymization tokens so spaCy doesn't re-tag them.
    # Placeholder spans are kept so we can also skip NER entities that
    # accidentally overlap them (spaCy sometimes tags substrings of the
    # placeholder as PER/ORG, so a simple text replace isn't enough).
    stash: dict[str, str] = {}
    placeholder_ranges: list[tuple[int, int]] = []
    text_for_ner_parts: list[str] = []
    cursor = 0
    for m in _EXISTING_TOKEN_RE.finditer(text):
        ph = f"__ANON_{len(stash):04d}__"
        stash[ph] = m.group(0)
        text_for_ner_parts.append(text[cursor:m.start()])
        ph_start = sum(len(p) for p in text_for_ner_parts)
        text_for_ner_parts.append(ph)
        placeholder_ranges.append((ph_start, ph_start + len(ph)))
        cursor = m.end()
    text_for_ner_parts.append(text[cursor:])
    text_for_ner = "".join(text_for_ner_parts)

    def _overlaps_placeholder(start: int, end: int) -> bool:
        return any(not (end <= ps or start >= pe) for ps, pe in placeholder_ranges)

    doc = _nlp()(text_for_ner)

    # Map: surface form (case-insensitive) → token. Per-doc only.
    counters = {"PER": 0, "ORG": 0, "LOC": 0}
    seen: dict[tuple[str, str], str] = {}
    replacements: list[tuple[int, int, str]] = []

    for ent in doc.ents:
        if ent.label_ not in _TYPE_TO_TOKEN:
            continue
        if _overlaps_placeholder(ent.start_char, ent.end_char):
            continue
        surface = ent.text.strip()
        if _is_stopword(surface):
            continue
        key = (ent.label_, surface.lower())
        if key not in seen:
            counters[ent.label_] += 1
            seen[key] = f"[{_TYPE_TO_TOKEN[ent.label_]}_{counters[ent.label_]}]"
        replacements.append((ent.start_char, ent.end_char, seen[key]))

    if not replacements:
        # Restore stashed tokens and return.
        return _restore_stash(text_for_ner, stash)

    # Apply right-to-left so earlier offsets stay valid.
    replacements.sort(key=lambda r: r[0], reverse=True)
    out = text_for_ner
    for start, end, token in replacements:
        out = out[:start] + token + out[end:]
    return _restore_stash(out, stash)


def _restore_stash(text: str, stash: dict[str, str]) -> str:
    if not stash:
        return text
    out = text
    for ph, original in stash.items():
        out = out.replace(ph, original)
    return out


# Heuristic to flag chunks that probably still contain a name the NER
# missed — used by llm_review.py to decide what to send to the LLM
# second-pass. Cheap: counts capitalized words not in stopword list.
_TITLECASE_RE = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+\b")


def looks_like_residual_name(chunk: str) -> bool:
    """Returns True if chunk has 2+ unrelated TitleCase tokens — a hint
    that the NER may have missed a proper noun. False is conservative:
    we'd rather pay for an LLM call than leak a name.
    """
    if not chunk:
        return False
    tokens = _TITLECASE_RE.findall(chunk)
    suspicious = [t for t in tokens if t.lower() not in _DOMAIN_STOPWORDS]
    return len(suspicious) >= 2
