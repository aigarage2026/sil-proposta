"""
Tests for services/lgpd/anonymizer.py.

Covers each pattern individually, no-op on safe inputs, idempotency (a
second pass leaves [TOKEN]s alone), payload-level helper, and the tenant
flag toggle (default True — fail-closed).
"""
from types import SimpleNamespace

import pytest

from services.lgpd.anonymizer import (
    anonymize,
    anonymize_payload,
    should_anonymize_for_tenant,
)

pytestmark = pytest.mark.unit


# ── single-pattern coverage ─────────────────────────────────────────────────


def test_masks_cpf():
    assert anonymize("CPF: 123.456.789-00 fim") == "CPF: [CPF] fim"


def test_masks_cnpj():
    assert anonymize("CNPJ 12.345.678/0001-90") == "CNPJ [CNPJ]"


def test_masks_email():
    assert anonymize("Contato: joao.silva@cast.com.br ok") == "Contato: [EMAIL] ok"


@pytest.mark.parametrize(
    "raw",
    [
        "(11) 98765-4321",
        "(11) 3456-7890",
        "+55 11 98765-4321",
        "11 98765-4321",
    ],
)
def test_masks_telefone_in_common_formats(raw):
    assert anonymize(f"tel: {raw} ok").startswith("tel: [TELEFONE]")


def test_bare_digit_sequences_are_not_masked():
    # Order numbers / PMS codes etc. must NOT be flagged as phones.
    text = "OP 12345678901 PMS 9988776655"
    assert anonymize(text) == text


# ── combined / boundary ─────────────────────────────────────────────────────


def test_masks_multiple_patterns_in_one_pass():
    src = (
        "Cliente João da Silva, CPF 123.456.789-00, e-mail joao@cast.com.br, "
        "CNPJ 12.345.678/0001-90, tel (11) 98765-4321."
    )
    out = anonymize(src)
    assert "[CPF]" in out
    assert "[CNPJ]" in out
    assert "[EMAIL]" in out
    assert "[TELEFONE]" in out
    # Original values must be gone.
    assert "123.456.789-00" not in out
    assert "12.345.678/0001-90" not in out
    assert "joao@cast.com.br" not in out
    assert "98765-4321" not in out


def test_idempotent():
    src = "CPF 111.222.333-44 e-mail a@b.com"
    once = anonymize(src)
    twice = anonymize(once)
    assert once == twice


def test_safe_input_unchanged():
    assert anonymize("Texto sem nenhum dado pessoal aqui.") == (
        "Texto sem nenhum dado pessoal aqui."
    )


def test_empty_inputs():
    assert anonymize(None) is None
    assert anonymize("") == ""


# ── payload helper ─────────────────────────────────────────────────────────


def test_anonymize_payload_only_targets_listed_fields():
    payload = {
        "rfp_text": "CPF 111.222.333-44",
        "title": "Proposta",
        "notes": "Contato joao@cast.com",
        "untouched": "CPF 999.999.999-99",
    }
    out = anonymize_payload(payload, fields=["rfp_text", "notes"])
    assert out["rfp_text"] == "CPF [CPF]"
    assert out["notes"] == "Contato [EMAIL]"
    # Field not in the list keeps its original — even if it contains PII.
    assert out["untouched"] == "CPF 999.999.999-99"
    # Untargeted fields preserved.
    assert out["title"] == "Proposta"


def test_anonymize_payload_does_not_mutate_input():
    payload = {"rfp_text": "CPF 111.222.333-44"}
    anonymize_payload(payload, fields=["rfp_text"])
    assert payload["rfp_text"] == "CPF 111.222.333-44"


def test_anonymize_payload_skips_non_string_values():
    payload = {"value": 12345, "rfp_text": "email@x.com"}
    out = anonymize_payload(payload, fields=["value", "rfp_text"])
    assert out["value"] == 12345
    assert out["rfp_text"] == "[EMAIL]"


# ── tenant flag ────────────────────────────────────────────────────────────


def test_should_anonymize_defaults_true_for_none_tenant():
    assert should_anonymize_for_tenant(None) is True


def test_should_anonymize_defaults_true_when_features_unset():
    tenant = SimpleNamespace(features=None)
    assert should_anonymize_for_tenant(tenant) is True


def test_should_anonymize_defaults_true_when_key_absent():
    tenant = SimpleNamespace(features={"some_other_flag": True})
    assert should_anonymize_for_tenant(tenant) is True


def test_should_anonymize_respects_false_opt_out():
    tenant = SimpleNamespace(features={"lgpd_anonymize_llm": False})
    assert should_anonymize_for_tenant(tenant) is False


def test_should_anonymize_respects_true_explicit_opt_in():
    tenant = SimpleNamespace(features={"lgpd_anonymize_llm": True})
    assert should_anonymize_for_tenant(tenant) is True
