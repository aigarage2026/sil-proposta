"""
Sil-Proposta — Demo Engine
Gera propostas reais e determinísticas baseadas no intake
Sem dependência de LLM — funciona sempre
"""
import re
from typing import Any

KW = {
    "MM": ["compra","compras","procurement","pedido de compra","ordem de compra",
           "cotacao","cotação","fornecedor","material","estoque","inventario",
           "inventário","recebimento de mercadoria","nf entrada","migo","me21",
           "me51","requisicao","requisição","mrp","planejamento de materiais","wm"],
    "SD": ["venda","vendas","faturamento","nota fiscal saida","nf saida",
           "pedido de venda","cliente","order to cash","va01","vf01","billing",
           "entrega","expedicao","expedição","credito","crédito"],
    "FI": ["contas a pagar","contas a receber","conciliacao bancaria","pagamento automatico",
           "baixa de titulo","razao geral","f110","ap ","ar "],
    "PP": ["producao","produção","ordem de producao","bom","roteiro","planejamento de producao"],
    "HR": ["recursos humanos","folha de pagamento","payroll","hcm","funcionario","ferias","férias"],
    "PM": ["manutencao","manutenção","ordem de manutencao","equipamento","preventiva","corretiva"],
    "FISCAL": ["econf","tef","maquininha","pinpad","cbenef","beneficio fiscal",
               "icms","sped","adequacao fiscal","110750","in 1.608","portaria sre"],
    "MIGR":   ["migracao","migração","migrar","s/4hana","s4hana","upgrade","rise with sap"],
}


def detectar_processo(rfp_text: str) -> str:
    txt = rfp_text.lower()
    scores = {}
    for proc, kws in KW.items():
        s = sum(1 for kw in kws if kw in txt)
        if s > 0:
            scores[proc] = s
    if not scores:
        return "FISCAL"
    return max(scores, key=scores.get)


def gerar_proposta_demo(payload) -> dict:
    """Gera proposta completa e determinística baseada no intake."""
    rfp   = (payload.rfp_text or "").strip()
    ufs   = payload.states or ["SP"]
    tipo  = payload.project_type or "ams"
    ver   = payload.sap_version or "ecc605"
    lei   = payload.new_law or False
    txt   = rfp.lower()

    hasGO  = "GO" in ufs
    hasSP  = "SP" in [u.upper() for u in ufs]
    isMigr = tipo == "migration" or "migracao" in txt or "s/4hana" in txt
    isSupp = tipo == "support"

    needsCPI = lei or hasGO or "econf" in txt or "110750" in txt or "tef" in txt
    hasTerm  = "tef" in txt or "maquininha" in txt or "pinpad" in txt
    hasCBen  = "cbenef" in txt or (hasSP and ("nf-e" in txt or "fiscal" in txt))

    main_proc = detectar_processo(rfp) if rfp else ("FISCAL" if (lei or hasGO) else "SD")

    # ── Dimensionamento por processo ──
    mods = []
    entr = []
    prem = []

    if main_proc == "MM":
        dMM = 3 if isSupp else 20 if isMigr else 10
        dFI = 2 if isSupp else 8 if isMigr else 5
        mods = [{"frente":"MM","nivel":"Senior","dias":dMM},
                {"frente":"FI","nivel":"Senior","dias":dFI}]
        if dMM + dFI > 14:
            mods.append({"frente":"GP","nivel":"Senior","dias":max(2,int((dMM+dFI)*0.15))})
        entr = [
            {"mod":"MM","item":"Especificação funcional — ciclo de compras AS-IS / TO-BE"},
            {"mod":"MM","item":"Configuração: requisição → cotação → pedido → recebimento (MIGO)"},
            {"mod":"MM","item":"Tipos de documento de compra (NB, FO, RFQ) e grupos de compradores"},
            {"mod":"FI","item":"Integração MM/FI — contas a pagar (AP) e verificação de faturas (MIRO)"},
            {"mod":"FI","item":"Pagamento automático (F110) e conciliação bancária"},
        ]
        if "cotacao" in txt or "cotação" in txt:
            entr.append({"mod":"MM","item":"Processo de cotação ME41/ME47/ME49 e análise comparativa"})
        if "estoque" in txt or "inventario" in txt:
            entr.append({"mod":"MM","item":"Movimentos de estoque MIGO e inventário físico"})
        prem = [
            "A parametrização será baseada na organização de compras do cliente.",
            "O cadastro de fornecedores e materiais deve estar disponível para testes.",
            "O organograma de aprovação de compras deve ser fornecido pelo cliente.",
        ]

    elif main_proc in ("FISCAL",) or (main_proc == "SD" and (hasGO or hasSP or lei)):
        dSD = 3 if isSupp else 9 if hasGO else 8 if hasCBen else 6
        dFI = 2 if isSupp else 11 if hasGO else 8
        mods = [{"frente":"SD","nivel":"Senior","dias":dSD},
                {"frente":"FI","nivel":"Senior","dias":dFI}]
        if dSD + dFI > 14:
            mods.append({"frente":"GP","nivel":"Senior","dias":4})
        entr = [{"mod":"SD","item":"Especificação funcional — análise da legislação e cenários fiscais"}]
        if hasGO or lei:
            entr.append({"mod":"SD","item":"Configuração Grupo YA na NF-e (tpIntegra=1 — IN 1.608/2025-GO)"})
        if hasCBen:
            entr += [
                {"mod":"SD","item":"BAdI J_1BNF_ADD_DATA — preenchimento cBenef"},
                {"mod":"SD","item":"Tabela Z cBenef manutenível via SM30"},
            ]
        entr.append({"mod":"FI","item":"Especificação conciliação bancária e baixa de título"})
        if needsCPI:
            entr.append({"mod":"FI","item":"Trigger ECONF (110750) a partir da baixa FI"})

        abaps = []
        if hasTerm: abaps.append("BAPI Z — receber dados terminal PINPAD/TEF")
        if hasGO or lei: abaps.append("BAdI J_1BNF_ADD_DATA — Grupo YA / tpIntegra=1")
        if hasCBen and not hasGO: abaps.append("BAdI J_1BNF_ADD_DATA — cBenef")
        abaps.append("RFC Z — carregar dados para XML NF-e")
        if needsCPI:
            abaps += ["iFlow CPI — ECONF 110750 → SVRS SEFAZ","iFlow CPI — cancelamento 110751"]
        else:
            abaps.append("Configuração DRC → SEFAZ")
        abaps.append("Monitor Z — consulta/reenvio/cancelamento/status SEFAZ")
        nAb = 1 if len(abaps) <= 2 else 2 if len(abaps) <= 4 else 3
        dAb = max(5, int(len(abaps) * 14 / 8))
        for i in range(1, nAb+1):
            mods.append({"frente":f"ABAP {i}" if nAb > 1 else "ABAP","nivel":"Senior","dias":dAb})
        for a in abaps:
            entr.append({"mod":"ABAP","item":a})
        if hasTerm: prem.append("Esta proposta não contempla extração dos dados da maquininha/terminal.")
        if needsCPI: prem.append("O cliente deverá ter SAP CPI/BTP contratado e configurado.")

    elif main_proc == "SD":
        dSD = 4 if isSupp else 18 if isMigr else 10
        mods = [{"frente":"SD","nivel":"Senior","dias":dSD},
                {"frente":"FI","nivel":"Senior","dias":2 if isSupp else 6}]
        if dSD > 10: mods.append({"frente":"GP","nivel":"Senior","dias":3})
        entr = [
            {"mod":"SD","item":"Especificação funcional — ciclo de vendas OTC"},
            {"mod":"SD","item":"Configuração organização de vendas, canal e setor"},
            {"mod":"SD","item":"Tipos de documento de venda e determinação de preços (V/08)"},
            {"mod":"FI","item":"Contas a receber (AR) — integração SD/FI"},
        ]
        if "nota fiscal" in txt or "nf-e" in txt:
            entr.append({"mod":"SD","item":"Saída fiscal NF-e e DANFE"})

    elif main_proc == "MIGR":
        mods = [{"frente":"SD","nivel":"Senior","dias":20},
                {"frente":"FI","nivel":"Senior","dias":20},
                {"frente":"MM","nivel":"Senior","dias":15},
                {"frente":"GP","nivel":"Senior","dias":10},
                {"frente":"ABAP 1","nivel":"Senior","dias":20},
                {"frente":"ABAP 2","nivel":"Senior","dias":20}]
        entr = [
            {"mod":"SD","item":"Assessment gaps SD — ECC vs S/4HANA"},
            {"mod":"FI","item":"Assessment gaps FI/CO — ECC vs S/4HANA"},
            {"mod":"MM","item":"Assessment gaps MM — ECC vs S/4HANA"},
            {"mod":"ABAP","item":"Análise e adaptação de objetos Z customizados"},
            {"mod":"ABAP","item":"Testes de regressão dos processos críticos"},
        ]
        prem.append("O ambiente S/4HANA deve estar provisionado antes do início.")

    elif main_proc == "PP":
        mods = [{"frente":"PP","nivel":"Senior","dias":10},{"frente":"MM","nivel":"Senior","dias":6},
                {"frente":"GP","nivel":"Senior","dias":3}]
        entr = [
            {"mod":"PP","item":"Especificação — planejamento de produção"},
            {"mod":"PP","item":"Tipos de ordem, roteiros e BOM"},
            {"mod":"MM","item":"Integração PP/MM"},
        ]
    elif main_proc == "HR":
        mods = [{"frente":"HR/HCM","nivel":"Senior","dias":12},
                {"frente":"FI","nivel":"Senior","dias":4},
                {"frente":"GP","nivel":"Senior","dias":3}]
        entr = [
            {"mod":"HR","item":"Estrutura organizacional HCM"},
            {"mod":"HR","item":"Folha de pagamento"},
            {"mod":"FI","item":"Integração HR/FI"},
        ]
    elif main_proc == "PM":
        mods = [{"frente":"PM","nivel":"Senior","dias":10},{"frente":"MM","nivel":"Senior","dias":5}]
        entr = [
            {"mod":"PM","item":"Tipos de ordem de manutenção"},
            {"mod":"PM","item":"Estrutura de equipamentos"},
            {"mod":"MM","item":"Integração PM/MM"},
        ]
    else:
        mods = [{"frente":"SD","nivel":"Senior","dias":8},{"frente":"FI","nivel":"Senior","dias":4}]
        entr = [{"mod":"SD","item":"Especificação funcional"},{"mod":"FI","item":"Parametrização e testes"}]

    if isSupp:
        mods = [{"frente":r["frente"],"nivel":r["nivel"],"dias":max(1,int(r["dias"]/2))} for r in mods]
        entr  = entr[:3]

    prem += [
        "Os acessos necessários deverão estar liberados até o início do projeto.",
        "Todos os desenvolvimentos em ABAP.",
        "Gerenciamento remoto durante toda a execução.",
        "Dia de consultoria: 8h (08h30–12h/13h30–18h), segunda a sexta.",
    ]

    totalH = sum(r["dias"] * 8 for r in mods)
    tarifa = 245 if needsCPI else 235 if main_proc == "MM" else 260 if isMigr else 220
    valor  = round(totalH * tarifa)
    ufs_str = ", ".join(ufs)

    legis = []
    if hasGO:  legis.append("IN 1.608/2025-GSE (Goiás) — tpIntegra=1")
    if needsCPI: legis.append("NT 2024.002 — ECONF 110750/110751")
    if hasSP and hasCBen: legis.append("Portaria SRE 70/2025 (SP) — cBenef")

    rfp_curto = rfp[:55] if rfp else "Proposta SAP"
    titulo = f"DAM — {rfp_curto} ({ufs_str})"

    ver_label = {"ecc604":"ECC ≤ 6.04","ecc605":"ECC 6.05+","s4op":"S/4HANA On-premise","s4cloud":"S/4HANA Cloud"}.get(ver, ver)

    rfp_len = len(rfp)
    conf_escopo = 0.90 if rfp_len > 100 else 0.80 if rfp_len > 30 else 0.65

    return {
        "main_proc":   main_proc,
        "total_hours": totalH,
        "wp_resources": mods,
        "confidence": {
            "escopo":    conf_escopo,
            "horas":     0.82,
            "legislacao": 0.91 if legis else 0.72,
            "comercial": 0.95,
        },
        "agents_fired": ["Orquestrador","SD","FI","ABAP","DRC","Fiscal","Equipe","Comercial"],
        "dam": {
            "titulo":      titulo,
            "tipo_projeto": tipo,
            "versao_sap":  ver_label,
            "ufs":         ufs,
            "necessidade": rfp or "Adequação conforme legislação vigente.",
            "entregaveis": entr,
            "premissas":   prem,
            "equipe":      mods,
            "total_horas": totalH,
            "plano": {
                "needs_cpi": needsCPI,
                "main_proc": main_proc,
                "modules":   list({e["mod"] for e in entr}),
            },
            "reforma": {"decisao": "monitorar"},
            "fiscal":  {"legislacao": legis},
            "comercial": {"valor_referencia": valor, "tarifa_hora": tarifa},
        },
    }
