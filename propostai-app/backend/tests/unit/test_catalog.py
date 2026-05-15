"""
Unit tests for the deterministic demand catalog (services/propostai/agents/catalog.py).

Covers:
  - classify_demand: keyword hits, generic fallback, tie resolution
  - get_demand_config: known + unknown
  - calculate_team: per-module dias logic + GP scaling
  - build_entregaveis: cascades sd/fi/abap/addon/basis objects + adds
    standard testes/apoio/go-live padding per functional module
  - filter_entregaveis: placeholder/duplicate/missing-field handling
  - filter_premissas: conditional term gating against the RFP
  - is_placeholder: short / generic / valid inputs
"""
import pytest

from services.propostai.agents.catalog import (
    DEMAND_TYPES,
    EXCLUSOES_PADRAO,
    PREMISSAS_PADRAO,
    build_entregaveis,
    calculate_team,
    classify_demand,
    filter_entregaveis,
    filter_premissas,
    get_demand_config,
    is_placeholder,
)

pytestmark = pytest.mark.unit


# ── classify_demand ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rfp, expected",
    [
        ("Precisamos implementar cBenef NT 2019.001 em SP", "cbenef"),
        ("Atender IN 1.608/2025-GO com evento ECONF", "econf_goias"),
        ("Automação F110 + CNAB remessa bancária Itaú", "automacao_cnab"),
        ("Integração Serasa para baixa de negativação", "integracao_serasa"),
        ("CIAP RESMESN e SOFICOM precisam ajuste", "ciap_soficom"),
        ("Upgrade EHP6 para EHP8 com SPAU/SPDD", "upgrade_ehp"),
        ("Reforma Tributária IBS/CBS LC 214", "reforma_tributaria"),
        ("Mudança de filial para nova prefeitura de Vargem Grande", "filial_change"),
    ],
)
def test_classify_demand_matches_keywords(rfp, expected):
    assert classify_demand(rfp) == expected


def test_classify_demand_generic_when_empty():
    assert classify_demand("") == "generic"
    assert classify_demand(None) == "generic"


def test_classify_demand_generic_when_no_keyword_matches():
    assert classify_demand("Cliente quer alguma coisa não relacionada") == "generic"


def test_classify_demand_returns_highest_score():
    # Multiple keywords for econf_goias should beat a single cbenef hit.
    rfp = "Tem cbenef mas o foco é econf 110750 in 1.608 tpintegra"
    assert classify_demand(rfp) == "econf_goias"


# ── get_demand_config ─────────────────────────────────────────────────────


def test_get_demand_config_returns_existing_type():
    cfg = get_demand_config("cbenef")
    assert cfg["label"].startswith("Implementação cBenef")
    assert "SD" in cfg["modules"]


def test_get_demand_config_falls_back_to_generic():
    cfg = get_demand_config("does_not_exist")
    assert cfg["label"] == "Demanda Customizada"
    assert cfg["modules"] == []


def test_all_demand_types_have_required_fields():
    """Schema guard — every DEMAND_TYPES entry must have these keys so
    downstream consumers don't need to .get() everything.
    """
    required = {
        "label", "keywords", "modules", "fiscal_scope",
        "needs_cpi", "needs_basis", "complexity",
        "estimated_weeks", "main_proc",
    }
    for tipo, cfg in DEMAND_TYPES.items():
        missing = required - set(cfg.keys())
        assert not missing, f"{tipo} missing keys: {missing}"


# ── calculate_team ─────────────────────────────────────────────────────────


def test_calculate_team_sd_only_keeps_minimum():
    # Type with only SD objects → SD + GP resources only.
    rec = calculate_team("filial_change", 100)
    frentes = {r["frente"] for r in rec}
    assert "SD" in frentes
    assert "ABAP" in frentes  # filial_change has ABAP objects
    assert "GP" in frentes
    assert "FI" not in frentes


def test_calculate_team_gp_scales_with_estimated_weeks():
    # cbenef: 4 weeks → gp 2 (semanas<=3 is 2 dias, but 4 weeks → 4 dias).
    rec = calculate_team("cbenef", 80)
    gp = next(r for r in rec if r["frente"] == "GP")
    assert gp["dias"] == 4  # 4 semanas → gp_dias 4

    # upgrade_ehp: 16 weeks → gp 15
    rec = calculate_team("upgrade_ehp", 600)
    gp = next(r for r in rec if r["frente"] == "GP")
    assert gp["dias"] == 15


def test_calculate_team_generic_has_only_gp():
    rec = calculate_team("generic", 0)
    # Generic has no modules → only GP from the proportional rule.
    assert len(rec) == 1
    assert rec[0]["frente"] == "GP"


def test_calculate_team_abap_uses_objects_hours():
    # cbenef abap_objects sum to 74h → dias = round(74/8) = 9
    rec = calculate_team("cbenef", 200)
    abap = next(r for r in rec if r["frente"] == "ABAP")
    assert abap["dias"] == 9


# ── build_entregaveis ──────────────────────────────────────────────────────


def test_build_entregaveis_includes_all_module_objects():
    entregaveis = build_entregaveis("cbenef")
    mods = {e["mod"] for e in entregaveis}
    assert "SD" in mods
    assert "ABAP" in mods


def test_build_entregaveis_adds_standard_padding_per_functional_module():
    entregaveis = build_entregaveis("cbenef")
    # For each functional module the catalog touches, we get 3 padding rows:
    # testes, apoio testes integrados, acompanhamento Go-Live.
    sd_items = [e["item"] for e in entregaveis if e["mod"] == "SD"]
    assert any("Testes da consultoria — SD" == it for it in sd_items)
    assert any("Acompanhamento Go-Live (1 dia útil) — SD" == it for it in sd_items)


def test_build_entregaveis_adds_abap_specific_padding():
    entregaveis = build_entregaveis("cbenef")
    abap_items = [e["item"] for e in entregaveis if e["mod"] == "ABAP"]
    assert any("Testes unitários ABAP" == it for it in abap_items)
    assert any("Documentação técnica + suporte aos testes" == it for it in abap_items)


def test_build_entregaveis_generic_returns_no_module_objects():
    # generic has no objects defined; build_entregaveis returns just the
    # ABAP-padding section if it had any, but generic has no functional
    # mod either → empty list.
    entregaveis = build_entregaveis("generic")
    assert entregaveis == []


# ── filter_entregaveis ─────────────────────────────────────────────────────


def test_filter_entregaveis_drops_placeholders():
    src = [
        {"item": "Configuração real", "horas": 16, "fase": "Realize"},
        {"item": "premissa", "horas": 8, "fase": "Realize"},
        {"item": "descrição", "horas": 8, "fase": "Realize"},
        {"item": "", "horas": 8, "fase": "Realize"},
    ]
    out = filter_entregaveis(src)
    assert len(out) == 1
    assert out[0]["item"] == "Configuração real"


def test_filter_entregaveis_dedups_by_item():
    src = [
        {"item": "Configuração X", "horas": 16},
        {"item": "Configuração X", "horas": 8},  # duplicate, kept the first
    ]
    out = filter_entregaveis(src)
    assert len(out) == 1
    assert out[0]["horas"] == 16


def test_filter_entregaveis_fills_missing_fields():
    src = [{"item": "Algo importante"}]
    out = filter_entregaveis(src)
    assert out[0]["horas"] == 8
    assert out[0]["fase"] == "Realize"


def test_filter_entregaveis_drops_non_dict():
    # Items must be longer than 4 chars to pass is_placeholder.
    src = [{"item": "Entregável real e descritivo"}, "not a dict", None]
    out = filter_entregaveis(src)
    assert len(out) == 1


# ── is_placeholder ────────────────────────────────────────────────────────


@pytest.mark.parametrize("text", ["premissa", "Premissa", "...", "<descrição>", "item", "", None, "x"])
def test_is_placeholder_true(text):
    assert is_placeholder(text) is True


@pytest.mark.parametrize("text", [
    "Configuração de filial em SP",
    "Implementação BAdI CL_NFE_PRINT",
    "Programa Z de geração ECONF",
])
def test_is_placeholder_false(text):
    assert is_placeholder(text) is False


# ── filter_premissas ──────────────────────────────────────────────────────


def test_filter_premissas_keeps_unconditional():
    out = filter_premissas(PREMISSAS_PADRAO, rfp_text="qualquer texto")
    # The first padrão items have no conditional term and must pass through.
    assert "Os usuários disponibilizados deverão ter acesso para depuração no ambiente de Qualidade." in out


def test_filter_premissas_dedups():
    src = [
        "Premissa um repetida no input.",
        "Premissa um repetida no input.",
        "Premissa dois distinta.",
    ]
    out = filter_premissas(src, rfp_text="")
    assert out == [
        "Premissa um repetida no input.",
        "Premissa dois distinta.",
    ]


def test_filter_premissas_drops_placeholders():
    out = filter_premissas(["premissa", "", "Premissa real válida"], rfp_text="")
    assert out == ["Premissa real válida"]


def test_filter_premissas_drops_conditional_when_term_absent():
    src = [
        "Premissa sobre maquininha não pode aparecer",
        "Premissa sobre boleto não pode aparecer",
        "Premissa neutra",
    ]
    out = filter_premissas(src, rfp_text="texto sem termos condicionais")
    assert out == ["Premissa neutra"]


def test_filter_premissas_keeps_conditional_when_term_in_rfp():
    src = ["Premissa sobre maquininha aparece se RFP cita maquininha"]
    out = filter_premissas(src, rfp_text="A RFP fala de maquininha POS")
    assert len(out) == 1


# ── exclusões padrão ──────────────────────────────────────────────────────


def test_exclusoes_padrao_contains_standard_items():
    assert any("notas SAP" in e for e in EXCLUSOES_PADRAO)
    assert any("interfaces com outros sistemas" in e for e in EXCLUSOES_PADRAO)
