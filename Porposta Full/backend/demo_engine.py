"""
Sil-Proposta — Demo Engine v2
Engine deterministica com casos reais SAP
"""
import re

KW = {
    "MM": ["compra","compras","procurement","pedido de compra","ordem de compra",
           "cotacao","cotação","fornecedor","material","estoque","inventario",
           "inventário","recebimento de mercadoria","nf entrada","migo","me21",
           "me51","requisicao","requisição","mrp","planejamento de materiais","wm"],
    "SD": ["venda","vendas","faturamento","nota fiscal saida","nf saida","nf-e",
           "pedido de venda","cliente","order to cash","va01","vf01","billing",
           "entrega","expedicao","expedição","credito","crédito","fatura","invoice",
           "filial","prefeitura","municipio","município","barueri","vargem",
           "nfs-e","nota fiscal servico","nota fiscal de servico","servico","serviço"],
    "FI": ["contas a pagar","contas a receber","conciliacao bancaria","pagamento automatico",
           "baixa de titulo","razao geral","f110","ap ","ar ","contabilidade"],
    "PP": ["producao","produção","ordem de producao","bom","roteiro","planejamento de producao"],
    "HR": ["recursos humanos","folha de pagamento","payroll","hcm","funcionario","ferias","férias"],
    "PM": ["manutencao","manutenção","ordem de manutencao","equipamento","preventiva","corretiva"],
    "FISCAL": ["econf","tef","maquininha","pinpad","cbenef","beneficio fiscal",
               "icms","sped","adequacao fiscal","110750","in 1.608","portaria sre"],
    "MIGR":   ["migracao","migração","migrar","s/4hana","s4hana","upgrade","rise with sap"],
    "ABAP":   ["abap","programa z","relatorio z","desenvolvimento","interface","badi","bapi","user exit"],
}

# Subtipos especiais que sempre incluem ABAP
SUBTIPO_ABAP_OBRIGATORIO = [
    "filial","prefeitura","municipio","município","nfs-e","nota fiscal de servico",
    "nota fiscal servico","invoicecom","invoice","range de numeracao","range de numeração",
    "envio de nota","econf","cpi","tef","maquininha",
]

def detectar_processo(rfp_text: str):
    txt = rfp_text.lower()
    scores = {}
    for proc, kws in KW.items():
        s = sum(1 for kw in kws if kw in txt)
        if s > 0:
            scores[proc] = s
    if not scores:
        return "SD", False
    main = max(scores, key=scores.get)
    # Detectar se precisa de ABAP obrigatório
    needs_abap = any(kw in txt for kw in SUBTIPO_ABAP_OBRIGATORIO) or "ABAP" in scores
    return main, needs_abap


def gerar_proposta_demo(payload) -> dict:
    rfp   = (payload.rfp_text or "").strip()
    obs   = getattr(payload, 'notes', '') or ''
    ufs   = payload.states or ["SP"]
    tipo  = payload.project_type or "ams"
    ver   = payload.sap_version or "ecc605"
    lei   = payload.new_law or False
    txt   = (rfp + " " + obs).lower()

    hasGO  = "GO" in ufs
    hasSP  = "SP" in [u.upper() for u in ufs]
    isMigr = tipo == "migration" or "migracao" in txt or "s/4hana" in txt
    isSupp = tipo == "support"

    needsCPI = lei or hasGO or "econf" in txt or "110750" in txt or "tef" in txt
    hasTerm  = "tef" in txt or "maquininha" in txt or "pinpad" in txt
    hasCBen  = "cbenef" in txt or (hasSP and ("nf-e" in txt or "fiscal" in txt))

    # Detectar processo e se precisa de ABAP obrigatório
    main_proc, needs_abap_forced = detectar_processo(rfp)
    if lei or hasGO:
        main_proc = "FISCAL"

    # Detectar subtipo de demanda
    is_filial_change  = any(k in txt for k in ["filial","prefeitura","municipio","município","barueri","vargem"])
    is_fiscal_change  = any(k in txt for k in ["fiscal","nf-e","nfs-e","nota fiscal","icms","iss"])
    has_testes_obs    = any(k in txt for k in ["teste","testes","homologacao","homologação","validacao","validação"])
    has_golive_obs    = any(k in txt for k in ["go-live","golive","go live","producao","produção","entrada em"])
    has_abap_explicit = any(k in txt for k in ["abap","programa","desenvolvimento","interface","badi"])

    # Forçar inclusão de ABAP se necessário
    needs_abap = needs_abap_forced or is_filial_change or has_abap_explicit or needsCPI

    # ── Extrair nome do cliente das observações ──
    cliente = ""
    m = re.search(r'cliente[:\s]+([A-Z][A-Za-z\s]{2,30})', rfp + " " + obs)
    if m:
        cliente = m.group(1).strip()

    mods = []
    entr = []
    prem = []

    # ════════════════════════════════════════════
    # CASO: MUDANÇA DE FILIAL / PREFEITURA (SD+ABAP)
    # ════════════════════════════════════════════
    if is_filial_change and main_proc in ("SD", "FISCAL"):
        # Horas baseadas no documento real ARMAC como referência
        h_entendimento = 6
        h_config       = 40
        h_abap         = 40
        h_testes       = 80 if has_testes_obs else 40
        h_aux_testes   = 16  # SD 8h + ABAP 8h
        h_golive       = 16  # SD 8h + ABAP 8h

        entr = [
            {"mod":"SD",   "item":"Entendimento do cenário — análise do chamado e contato com key user",      "horas": h_entendimento},
            {"mod":"SD",   "item":"Configuração de filial — endereço, organização de vendas e centro",        "horas": int(h_config*0.5)},
            {"mod":"SD",   "item":"Configuração de envio de NFS-e para nova prefeitura",                      "horas": int(h_config*0.3)},
            {"mod":"SD",   "item":"Configuração Invoicecom + range de numeração + cutover",                   "horas": int(h_config*0.2)},
            {"mod":"ABAP", "item":"Ajuste nos programas Z de envio de nota fiscal de serviço",                "horas": h_abap},
            {"mod":"SD",   "item":"Testes de validação — criação de contrato, cenários NFS-e e devoluções",   "horas": h_testes},
            {"mod":"SD",   "item":"Auxílio testes integrados (1 dia útil)",                                   "horas": 8},
            {"mod":"ABAP", "item":"Auxílio testes integrados (1 dia útil)",                                   "horas": 8},
            {"mod":"SD",   "item":"Acompanhamento Go-Live (1 dia útil)",                                      "horas": 8},
            {"mod":"ABAP", "item":"Acompanhamento Go-Live (1 dia útil)",                                      "horas": 8},
        ]

        total_sd   = h_entendimento + h_config + h_testes + 8 + 8
        total_abap = h_abap + 8 + 8
        mods = [
            {"frente":"SD",   "nivel":"Senior", "dias": max(1, round(total_sd/8))},
            {"frente":"ABAP", "nivel":"Senior", "dias": max(1, round(total_abap/8))},
        ]

        prem = [
            "Endereço correto de Vargem Grande Paulista deve ser fornecido pelo cliente antes do início.",
            "Acesso ao ambiente de Qualidade (QAS) deve estar liberado para configuração e testes.",
            "Cenários de teste devem ser validados pelo key user antes do Go-Live.",
            "O Invoicecom deve estar acessível e configurável pela equipe Cast Group.",
            "Range de numeração da nova prefeitura deve ser definido pelo cliente.",
        ]

    # ════════════════════════════════════════════
    # CASO: MM — Compras
    # ════════════════════════════════════════════
    elif main_proc == "MM":
        dMM = 3 if isSupp else 20 if isMigr else 10
        dFI = 2 if isSupp else 8 if isMigr else 5
        mods = [
            {"frente":"MM", "nivel":"Senior", "dias":dMM},
            {"frente":"FI", "nivel":"Senior", "dias":dFI},
        ]
        if dMM + dFI > 14:
            mods.append({"frente":"GP","nivel":"Senior","dias":max(2,int((dMM+dFI)*0.15))})
        if needs_abap:
            mods.append({"frente":"ABAP","nivel":"Senior","dias":5})
        entr = [
            {"mod":"MM", "item":"Entendimento do cenário — análise do chamado e levantamento AS-IS",        "horas":8},
            {"mod":"MM", "item":"Especificação funcional — ciclo de compras AS-IS / TO-BE",                 "horas":16},
            {"mod":"MM", "item":"Configuração: requisição → cotação → pedido → recebimento (MIGO)",         "horas":dMM*8//3},
            {"mod":"MM", "item":"Tipos de documento de compra (NB, FO, RFQ) e grupos de compradores",      "horas":8},
            {"mod":"FI", "item":"Integração MM/FI — contas a pagar (AP) e verificação de faturas (MIRO)",  "horas":dFI*8//2},
            {"mod":"FI", "item":"Pagamento automático (F110) e conciliação bancária",                      "horas":dFI*8//2},
            {"mod":"MM", "item":"Testes de validação end-to-end: RFQ → pedido → MIGO → MIRO → F110",       "horas":16},
            {"mod":"MM", "item":"Auxílio testes integrados (1 dia útil)",                                  "horas":8},
            {"mod":"MM", "item":"Acompanhamento Go-Live",                                                  "horas":8},
        ]
        if "cotação" in txt or "cotacao" in txt:
            entr.append({"mod":"MM","item":"Processo de cotação ME41/ME47/ME49 e análise comparativa","horas":8})
        if needs_abap:
            entr.append({"mod":"ABAP","item":"Desenvolvimento Z conforme especificação técnica","horas":40})
        prem = [
            "A parametrização será baseada na organização de compras do cliente.",
            "O cadastro de fornecedores e materiais deve estar disponível para testes.",
            "O organograma de aprovação de compras deve ser fornecido pelo cliente.",
        ]

    # ════════════════════════════════════════════
    # CASO: FISCAL / ECONF
    # ════════════════════════════════════════════
    elif main_proc in ("FISCAL",) or (main_proc == "SD" and (hasGO or hasSP or lei)):
        dSD = 3 if isSupp else 9 if hasGO else 8 if hasCBen else 6
        dFI = 2 if isSupp else 11 if hasGO else 8
        mods = [
            {"frente":"SD","nivel":"Senior","dias":dSD},
            {"frente":"FI","nivel":"Senior","dias":dFI},
        ]
        if dSD + dFI > 14:
            mods.append({"frente":"GP","nivel":"Senior","dias":4})

        abaps = []
        if hasTerm:   abaps.append("BAPI Z — receber dados terminal PINPAD/TEF")
        if hasGO or lei: abaps.append("BAdI J_1BNF_ADD_DATA — Grupo YA / tpIntegra=1")
        if hasCBen and not hasGO: abaps.append("BAdI J_1BNF_ADD_DATA — cBenef")
        abaps.append("RFC Z — carregar dados para XML NF-e")
        if needsCPI:
            abaps += ["iFlow CPI — ECONF 110750 → SVRS SEFAZ","iFlow CPI — cancelamento 110751"]
        else:
            abaps.append("Configuração DRC → SEFAZ")
        abaps.append("Monitor Z — consulta/reenvio/cancelamento/status SEFAZ")
        nAb  = 1 if len(abaps) <= 2 else 2 if len(abaps) <= 4 else 3
        dAb  = max(5, int(len(abaps) * 14 / 8))
        for i in range(1, nAb+1):
            mods.append({"frente":f"ABAP {i}" if nAb > 1 else "ABAP","nivel":"Senior","dias":dAb})

        entr = [
            {"mod":"SD",   "item":"Entendimento do cenário — análise da legislação e cenários fiscais", "horas":8},
            {"mod":"SD",   "item":"Especificação funcional SD","horas":16},
            {"mod":"FI",   "item":"Especificação conciliação bancária e baixa de título","horas":16},
        ]
        if hasGO or lei:
            entr.append({"mod":"SD","item":"Configuração Grupo YA na NF-e (tpIntegra=1 — IN 1.608/2025-GO)","horas":8})
        if hasCBen:
            entr += [
                {"mod":"SD","item":"BAdI J_1BNF_ADD_DATA — preenchimento cBenef","horas":16},
                {"mod":"SD","item":"Tabela Z cBenef manutenível via SM30","horas":8},
            ]
        if needsCPI:
            entr.append({"mod":"FI","item":"Trigger ECONF (110750) a partir da baixa FI","horas":8})
        for a in abaps:
            entr.append({"mod":"ABAP","item":a,"horas":dAb*8//len(abaps)})
        entr += [
            {"mod":"SD",   "item":"Testes de validação — cenários fiscais","horas":16},
            {"mod":"SD",   "item":"Auxílio testes integrados (1 dia útil)","horas":8},
            {"mod":"SD",   "item":"Acompanhamento Go-Live","horas":8},
        ]
        if hasTerm: prem.append("Esta proposta não contempla extração dos dados da maquininha/terminal.")
        if needsCPI: prem.append("O cliente deverá ter SAP CPI/BTP contratado e configurado.")

    # ════════════════════════════════════════════
    # CASO: SD genérico
    # ════════════════════════════════════════════
    elif main_proc == "SD":
        dSD = 4 if isSupp else 18 if isMigr else 10
        dAB = 5 if needs_abap else 0
        mods = [{"frente":"SD","nivel":"Senior","dias":dSD},
                {"frente":"FI","nivel":"Senior","dias":2 if isSupp else 6}]
        if needs_abap: mods.append({"frente":"ABAP","nivel":"Senior","dias":dAB})
        if dSD > 10: mods.append({"frente":"GP","nivel":"Senior","dias":3})
        entr = [
            {"mod":"SD","item":"Entendimento do cenário — análise do chamado","horas":8},
            {"mod":"SD","item":"Especificação funcional — ciclo de vendas OTC","horas":16},
            {"mod":"SD","item":"Configuração organização de vendas, canal e setor","horas":16},
            {"mod":"SD","item":"Tipos de documento de venda e determinação de preços (V/08)","horas":8},
            {"mod":"FI","item":"Contas a receber (AR) — integração SD/FI","horas":16},
        ]
        if needs_abap:
            entr.append({"mod":"ABAP","item":"Desenvolvimento Z conforme especificação técnica","horas":dAB*8})
        if "nota fiscal" in txt or "nf-e" in txt:
            entr.append({"mod":"SD","item":"Saída fiscal NF-e e DANFE","horas":8})
        entr += [
            {"mod":"SD","item":"Testes de validação","horas":16},
            {"mod":"SD","item":"Auxílio testes integrados (1 dia útil)","horas":8},
            {"mod":"SD","item":"Acompanhamento Go-Live","horas":8},
        ]

    # ════════════════════════════════════════════
    # CASO: MIGRAÇÃO
    # ════════════════════════════════════════════
    elif main_proc == "MIGR":
        mods = [
            {"frente":"SD",     "nivel":"Senior","dias":20},
            {"frente":"FI",     "nivel":"Senior","dias":20},
            {"frente":"MM",     "nivel":"Senior","dias":15},
            {"frente":"GP",     "nivel":"Senior","dias":10},
            {"frente":"ABAP 1", "nivel":"Senior","dias":20},
            {"frente":"ABAP 2", "nivel":"Senior","dias":20},
        ]
        entr = [
            {"mod":"SD",   "item":"Assessment gaps SD — ECC vs S/4HANA","horas":40},
            {"mod":"FI",   "item":"Assessment gaps FI/CO — ECC vs S/4HANA","horas":40},
            {"mod":"MM",   "item":"Assessment gaps MM — ECC vs S/4HANA","horas":40},
            {"mod":"ABAP", "item":"Análise e adaptação de objetos Z customizados","horas":80},
            {"mod":"ABAP", "item":"Testes de regressão dos processos críticos","horas":80},
        ]
        prem.append("O ambiente S/4HANA deve estar provisionado antes do início.")

    elif main_proc == "PP":
        mods = [{"frente":"PP","nivel":"Senior","dias":10},
                {"frente":"MM","nivel":"Senior","dias":6},
                {"frente":"GP","nivel":"Senior","dias":3}]
        entr = [
            {"mod":"PP","item":"Entendimento do cenário","horas":8},
            {"mod":"PP","item":"Especificação — planejamento de produção","horas":16},
            {"mod":"PP","item":"Tipos de ordem, roteiros e BOM","horas":24},
            {"mod":"MM","item":"Integração PP/MM","horas":16},
            {"mod":"PP","item":"Testes de validação","horas":16},
            {"mod":"PP","item":"Acompanhamento Go-Live","horas":8},
        ]
    elif main_proc == "HR":
        mods = [{"frente":"HR/HCM","nivel":"Senior","dias":12},
                {"frente":"FI","nivel":"Senior","dias":4},
                {"frente":"GP","nivel":"Senior","dias":3}]
        entr = [
            {"mod":"HR","item":"Entendimento do cenário","horas":8},
            {"mod":"HR","item":"Estrutura organizacional HCM","horas":24},
            {"mod":"HR","item":"Folha de pagamento","horas":40},
            {"mod":"FI","item":"Integração HR/FI","horas":16},
            {"mod":"HR","item":"Testes de validação","horas":16},
        ]
    elif main_proc == "PM":
        mods = [{"frente":"PM","nivel":"Senior","dias":10},
                {"frente":"MM","nivel":"Senior","dias":5}]
        entr = [
            {"mod":"PM","item":"Entendimento do cenário","horas":8},
            {"mod":"PM","item":"Tipos de ordem de manutenção","horas":16},
            {"mod":"PM","item":"Estrutura de equipamentos","horas":24},
            {"mod":"MM","item":"Integração PM/MM","horas":16},
            {"mod":"PM","item":"Testes de validação","horas":16},
        ]
    else:
        mods = [{"frente":"SD","nivel":"Senior","dias":8},
                {"frente":"FI","nivel":"Senior","dias":4}]
        entr = [
            {"mod":"SD","item":"Entendimento do cenário","horas":8},
            {"mod":"SD","item":"Especificação funcional","horas":16},
            {"mod":"FI","item":"Parametrização e testes","horas":16},
        ]

    if isSupp:
        mods = [{"frente":r["frente"],"nivel":r["nivel"],"dias":max(1,int(r["dias"]/2))} for r in mods]
        entr = entr[:4]

    # Premissas padrão sempre incluídas
    prem += [
        "Os acessos necessários deverão estar liberados até o início do projeto.",
        "Os usuários disponibilizados deverão ter acesso para depuração no ambiente de Qualidade.",
        "Todos os desenvolvimentos serão realizados em ABAP.",
        "Gerenciamento remoto durante toda a execução do projeto.",
        "Dia de consultoria: 8h (08h30–12h/13h30–18h), segunda a sexta.",
        "Dúvidas ou falhas devem ser reportadas durante o período de testes acordado em cronograma.",
        "Qualquer atraso por motivo do cliente comprometerá o prazo sem ônus à Cast Group.",
        "A documentação será entregue em língua portuguesa.",
    ]

    # Calcular totais
    totalH = sum(r["dias"] * 8 for r in mods)
    tarifa = 245 if needsCPI else 235 if main_proc == "MM" else 260 if main_proc == "MIGR" else 220
    valor  = round(totalH * tarifa)
    ufs_str = ", ".join(ufs)

    # Legislação
    legis = []
    if hasGO:            legis.append("IN 1.608/2025-GSE (Goiás) — tpIntegra=1")
    if needsCPI:         legis.append("NT 2024.002 — ECONF 110750/110751")
    if hasSP and hasCBen: legis.append("Portaria SRE 70/2025 (SP) — cBenef")
    if is_filial_change:  legis.append("Legislação municipal de Vargem Grande Paulista — NFS-e")

    rfp_curto = rfp[:55] if rfp else "Proposta SAP"
    titulo    = f"DAM — {rfp_curto} ({ufs_str})"
    ver_label = {"ecc604":"ECC ≤ 6.04","ecc605":"ECC 6.05+","s4op":"S/4HANA On-premise","s4cloud":"S/4HANA Cloud"}.get(ver, ver)
    rfp_len   = len(rfp)
    conf_esc  = 0.90 if rfp_len > 100 else 0.80 if rfp_len > 30 else 0.65

    # Matriz de impactos padrão
    impactos = [
        {"id":"01","descricao":"Erros durante o Go-Live","probabilidade":"Baixa","impacto":"Gravíssimo","classificacao":"Extremo","solucao":"Recuperação do backup antes da solução"},
        {"id":"02","descricao":"Engajamento dos Key Users","probabilidade":"Baixa","impacto":"Leve","classificacao":"Baixo","solucao":"Destacar necessidade do comprometimento no Kick-off"},
        {"id":"03","descricao":"Atraso por falta de acesso","probabilidade":"Média","impacto":"Médio","classificacao":"Moderado","solucao":"Liberação de acessos antes do início do projeto"},
    ]

    return {
        "main_proc":    main_proc,
        "total_hours":  totalH,
        "wp_resources": mods,
        "confidence": {
            "escopo":    conf_esc,
            "horas":     0.82,
            "legislacao": 0.91 if legis else 0.72,
            "comercial": 0.95,
        },
        "agents_fired": ["Orquestrador","SD","FI","ABAP","DRC","Fiscal","Equipe","Comercial"],
        "dam": {
            "titulo":       titulo,
            "cliente":      cliente,
            "tipo_projeto": tipo,
            "versao_sap":   ver_label,
            "ufs":          ufs,
            "necessidade":  rfp or "Adequação conforme legislação vigente.",
            "entregaveis":  entr,
            "premissas":    prem,
            "equipe":       mods,
            "total_horas":  totalH,
            "impactos":     impactos,
            "plano": {
                "needs_cpi":  needsCPI,
                "main_proc":  main_proc,
                "needs_abap": needs_abap,
                "modules":    list({e["mod"] for e in entr}),
            },
            "reforma":   {"decisao":"monitorar"},
            "fiscal":    {"legislacao": legis},
            "comercial": {"valor_referencia": valor, "tarifa_hora": tarifa},
        },
    }
