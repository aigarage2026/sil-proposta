"""
LLM second-pass anonymization review.

Layer 3 of the pipeline. After regex (services/lgpd/anonymizer.py) and
NER (entity_anonymizer.py), we sample chunks that still look suspicious
(per `looks_like_residual_name`) and send them to Claude Haiku with a
strict "find and mask anything that looks like a real name/company/place
that the previous passes missed" prompt.

Cost control: only suspicious chunks go to the LLM (typically 15–25% of
the corpus, by observation on a sample of 50 docs). At ~$0.0005 / call
and ~6,900 docs, expected total < $5.

This module degrades gracefully: if no LLM credentials are configured,
it returns the input unchanged and the pipeline continues. The user is
warned at the CLI level when LLM review is disabled.
"""
from __future__ import annotations

from services.propostai.agents.llm_client import LLMClient, parse_llm_json

_SYSTEM_PROMPT = (
    "Você é um agente de privacidade. Recebe um trecho de proposta "
    "técnica em português brasileiro que JÁ passou por anonimização. "
    "Sua tarefa: encontrar QUALQUER nome próprio remanescente de pessoa "
    "física, empresa, marca ou cidade que tenha escapado, e substituir "
    "por tokens no formato [PESSOA_X], [EMPRESA_X] ou [LOCAL_X] "
    "(escolha X livremente, mantendo consistência no trecho).\n"
    "NÃO toque em: tokens já presentes (entre colchetes), siglas "
    "técnicas SAP (SD/FI/MM/ABAP/etc), nomes de transações SAP, nomes "
    "de normas (NT/IN/Portaria/LC), nomes geográficos genéricos (UFs).\n"
    "Mantenha 'Direto ao Ponto' e 'AI Garage' como está (nossa marca).\n"
    'Retorne APENAS JSON: {"text": "<trecho com substituições>"}.'
)


async def llm_review_chunk(chunk: str, llm: LLMClient) -> str:
    """Ask the LLM to mask anything the prior passes missed.

    Returns the chunk unchanged on any failure (we never block ingestion
    on a flaky LLM call — the NER+regex output is already safe enough to
    ship, the LLM pass is defense in depth).
    """
    if not chunk or not chunk.strip():
        return chunk
    try:
        raw = await llm.call(
            system=_SYSTEM_PROMPT,
            user=chunk,
            agent_name="ANON_REVIEW",
            max_tokens=2500,
        )
        parsed = parse_llm_json(raw) or {}
        reviewed = parsed.get("text")
        if isinstance(reviewed, str) and reviewed.strip():
            return reviewed
    except Exception:  # noqa: BLE001
        # Intentional: never raise from the review path.
        pass
    return chunk
