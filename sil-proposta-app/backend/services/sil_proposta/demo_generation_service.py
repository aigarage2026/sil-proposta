"""
Demo generation service — fallback deterministico sem LLM.
Migrado de demo_engine.py do legado.
"""
from core.config import get_settings
from schemas.intake import IntakePayload

settings = get_settings()

TARIFF = settings.SAP_DEFAULT_TARIFF_PER_HOUR


def _detect_process(rfp: str) -> str:
    """Detecta processo principal a partir do texto da RFP."""
    rfp_low = (rfp or "").lower()
    kw = {
        "MM": ["compra", "requisicao", "cotacao", "pedido compra", "migo", "miro", "fornecedor", "estoque"],
        "SD": ["venda", "fatura", "nf-e", "nota fiscal", "entrega", "remessa", "faturamento", "cbenef"],
        "FI": ["financeiro", "contabil", "pagamento", "conciliacao", "bancari", "econf", "titulo"],
        "PP": ["producao", "mrp", "ordem producao", "bom", "roteiro"],
        "HR": ["folha", "rh", "ferias", "rescisao", "ponto"],
        "PM": ["manutencao", "ordem manutencao", "preventiva"],
        "FISCAL": ["fiscal", "icms", "legislacao", "sefaz", "drc", "tpintegra", "cbenef", "portaria"],
        "MIGR": ["migracao", "migrar", "ecc", "s/4", "hana", "greenfield", "brownfield"],
    }
    scores = {k: sum(1 for w in words if w in rfp_low) for k, words in kw.items()}
    if max(scores.values(), default=0) == 0:
        return "SD"
    return max(scores, key=scores.get)


def gerar_proposta_demo(payload: IntakePayload) -> dict:
    """Gera proposta sem LLM — regras deterministicas."""
    rfp = payload.rfp_text or ""
    ufs = payload.states or ["SP"]
    proc = _detect_process(rfp)
    is_go = "GO" in ufs
    is_sp = "SP" in ufs

    # Resources base
    resources = [
        {"frente": "SD", "nivel": "Senior", "dias": 8},
        {"frente": "FI", "nivel": "Senior", "dias": 8},
        {"frente": "GP", "nivel": "Senior", "dias": 4},
    ]

    # ABAP
    needs_cpi = "econf" in rfp.lower() or "maquininha" in rfp.lower()
    abap_items = 3 if needs_cpi else 2
    n_abapers = 3 if abap_items >= 4 else min(abap_items, 2)
    abap_dias = 7 * (2 if needs_cpi else 1)

    for i in range(1, n_abapers + 1):
        resources.append({"frente": f"ABAP {i}", "nivel": "Senior", "dias": abap_dias})

    total_h = sum(r["dias"] * 8 for r in resources)
    valor = total_h * TARIFF

    # Entregaveis
    entregaveis = [
        {"mod": "SD", "item": "Entendimento do cenario — analise legislacao e cenarios fiscais"},
        {"mod": "SD", "item": "Especificacao funcional SD"},
    ]
    if is_go or is_sp:
        entregaveis.append({"mod": "SD", "item": "BAdI J_1BNF_ADD_DATA — preenchimento cBenef"})
        entregaveis.append({"mod": "SD", "item": "Tabela Z cBenef manutenivel via SM30"})
    entregaveis.extend([
        {"mod": "SD", "item": "Testes de validacao — cenarios fiscais"},
        {"mod": "SD", "item": "Auxilio testes integrados (1 dia util)"},
        {"mod": "SD", "item": "Acompanhamento Go-Live"},
        {"mod": "FI", "item": "Especificacao conciliacao bancaria e baixa de titulo"},
    ])

    if needs_cpi:
        entregaveis.extend([
            {"mod": "ABAP", "item": "BAdI J_1BNF_ADD_DATA — cBenef"},
            {"mod": "ABAP", "item": "RFC Z — carregar dados para XML NF-e"},
            {"mod": "ABAP", "item": "iFlow CPI — ECONF 110750/110751"},
            {"mod": "ABAP", "item": "Monitor Z — consulta/reenvio/cancelamento/status SEFAZ"},
        ])
    else:
        entregaveis.extend([
            {"mod": "ABAP", "item": "BAdI J_1BNF_ADD_DATA — cBenef"},
            {"mod": "ABAP", "item": "RFC Z — carregar dados para XML NF-e"},
            {"mod": "ABAP", "item": "Configuracao DRC -> SEFAZ"},
            {"mod": "ABAP", "item": "Monitor Z — consulta/reenvio/cancelamento/status SEFAZ"},
        ])

    # Legislacao
    legislacao = []
    if is_go:
        legislacao.append("IN 1.608/2025-GSE (tpIntegra=1)")
    if is_sp:
        legislacao.append("Portaria SRE 70/2025 (SP) — cBenef")
    legislacao.append("NT 2024.002 — ECONF (110750/110751)")

    # Premissas
    premissas = [
        "Os acessos necessarios deverao estar liberados ate o inicio do projeto.",
        "Os usuarios disponibilizados deverao ter acesso para depuracao em QAS.",
        "Todos os desenvolvimentos serao realizados em ABAP.",
        "Gerenciamento remoto durante toda a execucao do projeto.",
        "Dia de consultoria: 8h (08h30-12h/13h30-18h), segunda a sexta.",
        "Duvidas ou falhas devem ser reportadas durante testes.",
        "Qualquer atraso por motivo do cliente comprometera o prazo sem onus a Cast Group.",
        "A documentacao sera entregue em lingua portuguesa.",
    ]

    confidence = {
        "escopo": 0.90 if len(rfp) > 100 else 0.65,
        "horas": 0.82,
        "legislacao": 0.91 if ufs else 0.70,
        "comercial": 0.95,
    }

    dam = {
        "titulo": f"DAM — {rfp[:60] if rfp else 'Proposta SAP'} ({','.join(ufs)})",
        "tipo_projeto": payload.project_type,
        "versao_sap": payload.sap_version,
        "ufs": ufs,
        "necessidade": rfp[:200] if rfp else "Adequacao fiscal e operacional.",
        "entregaveis": entregaveis,
        "premissas": premissas,
        "equipe": resources,
        "total_horas": total_h,
        "plano": {"needs_cpi": needs_cpi, "modules": [proc]},
        "reforma": {"decisao": "monitorar"},
        "fiscal": {"legislacao": legislacao},
        "comercial": {"valor_referencia": valor, "faturamento": "50%/50%", "garantia": "30 dias", "validade": "30 dias"},
    }

    return {
        "dam": dam,
        "wp_resources": resources,
        "total_hours": total_h,
        "confidence": confidence,
        "agents_fired": ["Orquestrador", "SD", "FI", "ABAP", "DRC", "Fiscal Estadual", "Fiscal Federal", "Equipe/GP", "Comercial"],
        "main_proc": proc,
    }
