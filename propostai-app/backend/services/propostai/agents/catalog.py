"""
PropostAI — Catálogo Determinístico de Demandas SAP
Mapeia tipo de demanda → agentes a executar + objetos ABAP + horas estimadas.
ESTE ARQUIVO É A FONTE ÚNICA DE VERDADE — sem LLM, sem incerteza.
"""

# ══════════════════════════════════════════════════════════════
# CATÁLOGO DE TIPOS DE DEMANDA
# Cada tipo define quais agentes executar, quais objetos ABAP, horas e fluxo
# ══════════════════════════════════════════════════════════════

DEMAND_TYPES = {

    # ── Mudança de filial / prefeitura (NFS-e) ──
    "filial_change": {
        "label": "Mudança de Filial / Prefeitura",
        "keywords": ["mudança de filial", "filial", "nova prefeitura", "vargem grande", "barueri", "mudar prefeitura", "alteração de prefeitura", "novo município", "transferência de filial"],
        "modules": ["SD", "ABAP"],
        "fiscal_scope": {"municipal": True},
        "needs_cpi": False,
        "needs_basis": False,
        "complexity": "media",
        "estimated_weeks": 3,
        "main_proc": "SD",
        "sistema_sap": "SAP standard + Invoicecom (NFS-e municipal)",
        "fluxo_solucao": "VA01 → VL01N → VF01 → NFS-e municipal → Invoicecom → Prefeitura",
        "abap_objects": [
            {"item": "Ajuste no programa Z de envio de NFS-e para nova prefeitura", "horas": 24, "fase": "Realize", "tipo": "Programa Z"},
            {"item": "Configuração Invoicecom + range de numeração para nova prefeitura", "horas": 16, "fase": "Realize", "tipo": "Configuração"},
            {"item": "Ajuste na BAdI de saída fiscal para novo município", "horas": 16, "fase": "Realize", "tipo": "BAdI"},
        ],
        "sd_objects": [
            {"item": "Configuração de filial — endereço, organização de vendas e centro", "horas": 16, "fase": "Realize"},
            {"item": "Configuração de envio de NFS-e para nova prefeitura", "horas": 16, "fase": "Realize"},
            {"item": "Cadastro de range de numeração e tipo de operação no novo município", "horas": 8, "fase": "Realize"},
        ],
    },

    # ── cBenef (NT 2019.001) ──
    "cbenef": {
        "label": "Implementação cBenef (NT 2019.001)",
        "keywords": ["cbenef", "código de benefício fiscal", "nt 2019.001", "benefício fiscal icms", "portaria sre"],
        "modules": ["SD", "ABAP"],
        "fiscal_scope": {"estadual": True},
        "needs_cpi": False,
        "needs_basis": False,
        "complexity": "media",
        "estimated_weeks": 4,
        "main_proc": "SD",
        "sistema_sap": "SAP DRC + BAdI customizada",
        "fluxo_solucao": "VA01 → VF01 → BAdI CL_NFE_PRINT → tabela ZCBENEF_UF → XML NF-e → SEFAZ",
        "abap_objects": [
            {"item": "Tabela Z ZCBENEF_UF para mapear UF + CST + Direito Fiscal → cBenef", "horas": 16, "fase": "Realize", "tipo": "Tabela Z", "transacao": "SE11/SM30"},
            {"item": "Campo CBENEF na tabela de item da NF", "horas": 8, "fase": "Realize", "tipo": "Append Estrutura", "transacao": "SE11"},
            {"item": "Ajuste das telas J1B1N, J1B2N, J1B3N para exibir CBENEF", "horas": 12, "fase": "Realize", "tipo": "Tela", "transacao": "SE80"},
            {"item": "Implementação BAdI CL_NFE_PRINT para preencher cBenef no XML", "horas": 16, "fase": "Realize", "tipo": "BAdI", "transacao": "SE19"},
            {"item": "Ajuste do DANFE para exibir o campo cBenef", "horas": 10, "fase": "Realize", "tipo": "SmartForm", "transacao": "SE38"},
            {"item": "Validação de consistência cBenef × CST × UF (Rejeição 931)", "horas": 12, "fase": "Realize", "tipo": "Enhancement", "transacao": "SE38"},
        ],
        "sd_objects": [
            {"item": "Especificação funcional dos 6 entregáveis ABAP", "horas": 16, "fase": "Explore"},
            {"item": "Cadastro dos códigos de cBenef para SP", "horas": 16, "fase": "Realize"},
        ],
    },

    # ── ECONF Goiás (IN 1.608) ──
    "econf_goias": {
        "label": "Atendimento IN 1.608/2025-GO (ECONF)",
        "keywords": ["econf", "110750", "in 1.608", "in 1608", "tpintegra", "evento ecconf", "conciliação financeira nf-e"],
        "modules": ["SD", "FI", "ABAP"],
        "fiscal_scope": {"estadual": True, "federal": True},
        "needs_cpi": True,
        "needs_basis": True,
        "complexity": "alta",
        "estimated_weeks": 8,
        "main_proc": "FISCAL",
        "sistema_sap": "SAP CPI (ECONF sem suporte DRC nativo)",
        "fluxo_solucao": "FI Baixa → trigger ECONF → ABAP Z → iFlow CPI → SVRS SEFAZ → Protocolo → SAP",
        "abap_objects": [
            {"item": "Programa Z de geração do evento ECONF (110750/110751)", "horas": 40, "fase": "Realize", "tipo": "Programa Z", "transacao": "SE38"},
            {"item": "Tabela Z de parametrização de cenários de pagamento (à vista vs posterior)", "horas": 16, "fase": "Realize", "tipo": "Tabela Z", "transacao": "SE11/SM30"},
            {"item": "BAdI para Grupo YA na NF-e (tpIntegra=1)", "horas": 24, "fase": "Realize", "tipo": "BAdI", "transacao": "SE19"},
            {"item": "Job batch diário para identificar pagamentos compensados", "horas": 16, "fase": "Realize", "tipo": "Job", "transacao": "SM36/SM37"},
            {"item": "Monitor Z para consulta/reenvio/cancelamento de eventos ECONF", "horas": 24, "fase": "Realize", "tipo": "Report Z", "transacao": "SE38"},
            {"item": "iFlow CPI para integração com SVRS SEFAZ-GO", "horas": 24, "fase": "Realize", "tipo": "iFlow CPI"},
        ],
        "sd_objects": [
            {"item": "Especificação funcional do Grupo YA e cenários ECONF", "horas": 16, "fase": "Explore"},
            {"item": "Configuração parâmetros de evento novo (tpIntegra)", "horas": 16, "fase": "Realize"},
        ],
        "fi_objects": [
            {"item": "Especificação trigger ECONF a partir da baixa FI", "horas": 16, "fase": "Explore"},
            {"item": "Configuração conciliação bancária (FF_5/FEBAN) e integração FI/ECONF", "horas": 16, "fase": "Realize"},
        ],
    },

    # ── Automação bancária (CNAB) ──
    "automacao_cnab": {
        "label": "Automação F110/CNAB (cobrança bancária)",
        "keywords": ["cnab", "automação f110", "remessa bancária", "automação bancária", "cobrança bancária", "boleto", "itaú", "bradesco"],
        "modules": ["FI", "ABAP"],
        "fiscal_scope": {},
        "needs_cpi": False,
        "needs_basis": True,
        "complexity": "media",
        "estimated_weeks": 5,
        "main_proc": "FI",
        "sistema_sap": "SAP FI + DMEE (geração CNAB)",
        "fluxo_solucao": "F110 (proposta + pagamento) → DMEE → arquivo CNAB → AL11 → banco",
        "abap_objects": [
            {"item": "Programa Z principal de automação F110 + geração CNAB + gravação AL11", "horas": 40, "fase": "Realize", "tipo": "Programa Z", "transacao": "SE38"},
            {"item": "Tabela Z de parametrização (Company Code + Divisão + Banco)", "horas": 16, "fase": "Realize", "tipo": "Tabela Z", "transacao": "SE11/SM30"},
            {"item": "Transação Z de auditoria/monitoramento das remessas", "horas": 24, "fase": "Realize", "tipo": "Transação Z", "transacao": "SE93/SE38"},
            {"item": "Validação de elegibilidade (BSID, AUGBL, ZLSPR, BUDAT, Net Due Date)", "horas": 16, "fase": "Realize", "tipo": "Programa Z"},
        ],
        "fi_objects": [
            {"item": "Configuração FBZP dos bancos + DMEE para layout CNAB", "horas": 16, "fase": "Realize"},
            {"item": "Especificação das regras de elegibilidade dos títulos", "horas": 16, "fase": "Explore"},
        ],
        "basis_objects": [
            {"item": "Criação de jobs nos ambientes DEV/QAS/PRD (SM36/SM37)", "horas": 8, "fase": "Deploy"},
        ],
    },

    # ── Integração Serasa ──
    "integracao_serasa": {
        "label": "Automação Baixa de Negativação Serasa",
        "keywords": ["serasa", "negativação", "baixa de negativação", "integração serasa"],
        "modules": ["FI", "ABAP"],
        "fiscal_scope": {},
        "needs_cpi": False,
        "needs_basis": True,
        "complexity": "baixa",
        "estimated_weeks": 3,
        "main_proc": "FI",
        "sistema_sap": "SAP FI + Integração Serasa existente",
        "fluxo_solucao": "Baixa pagamento (FI) → Job Z → Verifica títulos compensados → Aciona Integração Serasa existente",
        "abap_objects": [
            {"item": "Programa Z para identificar liquidações de títulos previamente negativados", "horas": 24, "fase": "Realize", "tipo": "Programa Z", "transacao": "SE38"},
            {"item": "Logs de envio/erro com detalhes da chamada à API Serasa", "horas": 8, "fase": "Realize", "tipo": "Tabela Z + log", "transacao": "SE11"},
        ],
        "fi_objects": [
            {"item": "Especificação técnica do programa Z de extração de títulos", "horas": 8, "fase": "Explore"},
        ],
        "basis_objects": [
            {"item": "Configuração de Jobs SM37 em QAS e PRD", "horas": 8, "fase": "Deploy"},
        ],
    },

    # ── CIAP / SOFICOM ──
    "ciap_soficom": {
        "label": "Ajuste CIAP / SOFICOM",
        "keywords": ["ciap", "resmesn", "/pgtpa/ciap", "soficom", "apuração icms"],
        "modules": ["FI", "ABAP", "ADDON"],
        "fiscal_scope": {"estadual": True},
        "needs_cpi": False,
        "needs_basis": False,
        "complexity": "baixa",
        "estimated_weeks": 3,
        "main_proc": "FI",
        "sistema_sap": "SAP FI + Add-on SOFICOM",
        "fluxo_solucao": "Apuração CIAP (RESMESN) → trigger antes da contabilização → preenchimento automático campo referência → documento contábil",
        "abap_objects": [
            {"item": "Enhancement na chamada antes da criação do documento contábil (CIAP)", "horas": 24, "fase": "Realize", "tipo": "Enhancement", "transacao": "SE19"},
        ],
        "fi_objects": [
            {"item": "Mapeamento + Especificação funcional do preenchimento do campo referência", "horas": 16, "fase": "Explore"},
        ],
        "addon_objects": [
            {"item": "Validação no módulo SOFICOM da execução do CIAP RESMESN", "horas": 8, "fase": "Realize"},
        ],
    },

    # ── Upgrade EHP ──
    "upgrade_ehp": {
        "label": "Upgrade SAP ECC (EHP)",
        "keywords": ["upgrade ehp", "ehp6 para ehp8", "upgrade enhancement package", "spau", "spdd", "atualização ehp"],
        "modules": ["SD", "FI", "MM", "PP", "HR", "CO", "ABAP", "BASIS"],
        "fiscal_scope": {},
        "needs_cpi": False,
        "needs_basis": True,
        "is_migration": True,
        "complexity": "alta",
        "estimated_weeks": 16,
        "main_proc": "MIGR",
        "sistema_sap": "SAP ECC EHP (atualização in-place via SUM)",
        "fluxo_solucao": "Ambiente bolha → SUM (upgrade EHP) → SPAU/SPDD → testes regressão por módulo → cutover → Go-Live",
        "abap_objects": [
            {"item": "SPAU — adaptação de programas customizados após upgrade", "horas": 80, "fase": "Realize", "tipo": "SPAU", "transacao": "SPAU"},
            {"item": "SPDD — adaptação de objetos do dicionário de dados", "horas": 40, "fase": "Realize", "tipo": "SPDD", "transacao": "SPDD"},
            {"item": "Análise de impacto em programas Z e BAdIs existentes", "horas": 80, "fase": "Explore", "tipo": "Análise"},
            {"item": "Correção de programas Z impactados pelo upgrade", "horas": 120, "fase": "Realize", "tipo": "Programa Z"},
        ],
        "basis_objects": [
            {"item": "Atualização do ambiente bolha para EHP destino", "horas": 80, "fase": "Realize", "tipo": "SUM"},
            {"item": "Execução do upgrade EHP via SUM em DEV/QAS/PRD", "horas": 120, "fase": "Realize", "tipo": "SUM"},
            {"item": "Planejamento de cutover e janela de manutenção", "horas": 40, "fase": "Deploy"},
        ],
    },

    # ── Reforma Tributária ──
    "reforma_tributaria": {
        "label": "Reforma Tributária (IBS/CBS)",
        "keywords": ["reforma tributária", "ibs", "cbs", "imposto seletivo", "lc 214", "ec 132"],
        "modules": ["SD", "FI", "ABAP", "BASIS"],
        "fiscal_scope": {"federal": True, "estadual": True, "municipal": True},
        "needs_cpi": False,
        "needs_basis": True,
        "needs_reform": True,
        "complexity": "alta",
        "estimated_weeks": 12,
        "main_proc": "FISCAL",
        "sistema_sap": "SAP S/4HANA (preparação Reforma Tributária)",
        "fluxo_solucao": "Análise impacto IBS/CBS → adequação tax determination → split payment → SPED → testes",
        "abap_objects": [
            {"item": "Adequação programas Z para novos campos IBS/CBS", "horas": 80, "fase": "Realize", "tipo": "Programa Z"},
            {"item": "Tabela Z de mapeamento de novas alíquotas e tributos", "horas": 40, "fase": "Realize", "tipo": "Tabela Z"},
        ],
    },

    # ── Demanda genérica (fallback) ──
    "generic": {
        "label": "Demanda Customizada",
        "keywords": [],
        "modules": [],  # determinado dinamicamente pela LLM
        "fiscal_scope": {},
        "needs_cpi": False,
        "needs_basis": False,
        "complexity": "media",
        "estimated_weeks": 4,
        "main_proc": "SD",
        "sistema_sap": "",
        "fluxo_solucao": "",
        "abap_objects": [],
    },
}


def classify_demand(rfp_text: str) -> str:
    """Classifica a RFP em um dos tipos do catálogo (determinístico, sem LLM)."""
    if not rfp_text:
        return "generic"
    text = rfp_text.lower()

    # Score por tipo baseado em keywords
    scores = {}
    for tipo, config in DEMAND_TYPES.items():
        if tipo == "generic":
            continue
        score = 0
        for kw in config["keywords"]:
            if kw.lower() in text:
                score += 1
        if score > 0:
            scores[tipo] = score

    if not scores:
        return "generic"

    # Retorna o tipo com maior score
    return max(scores, key=scores.get)


def get_demand_config(tipo: str) -> dict:
    """Retorna config completa do tipo de demanda."""
    return DEMAND_TYPES.get(tipo, DEMAND_TYPES["generic"])


# ══════════════════════════════════════════════════════════════
# CALCULADORA DETERMINÍSTICA DE EQUIPE
# ══════════════════════════════════════════════════════════════
def calculate_team(tipo: str, total_horas_entregaveis: int) -> list:
    """
    Calcula recursos da equipe de forma determinística.
    Distribui as horas entre as frentes baseado nos entregáveis reais.
    """
    config = get_demand_config(tipo)
    semanas = config.get("estimated_weeks", 4)

    recursos = []
    modules = config.get("modules", [])

    # Calcular dias por módulo proporcionalmente
    if "ABAP" in modules:
        # ABAP normalmente é 60-70% do esforço técnico
        abap_horas = sum(o.get("horas", 0) for o in config.get("abap_objects", []))
        if abap_horas == 0:
            abap_horas = total_horas_entregaveis * 0.5
        recursos.append({"frente": "ABAP", "nivel": "Senior", "dias": max(5, round(abap_horas / 8))})

    if "SD" in modules:
        sd_horas = sum(o.get("horas", 0) for o in config.get("sd_objects", []))
        if sd_horas == 0:
            sd_horas = 40  # padrão: 5 dias
        # Adicionar testes + apoio + go-live = +24h
        sd_horas += 24
        recursos.append({"frente": "SD", "nivel": "Senior", "dias": max(3, round(sd_horas / 8))})

    if "FI" in modules:
        fi_horas = sum(o.get("horas", 0) for o in config.get("fi_objects", []))
        if fi_horas == 0:
            fi_horas = 40
        fi_horas += 24
        recursos.append({"frente": "FI", "nivel": "Senior", "dias": max(3, round(fi_horas / 8))})

    if "MM" in modules:
        recursos.append({"frente": "MM", "nivel": "Senior", "dias": max(3, semanas * 2)})

    if "PP" in modules:
        recursos.append({"frente": "PP", "nivel": "Senior", "dias": max(3, semanas * 2)})

    if "HR" in modules:
        recursos.append({"frente": "HR", "nivel": "Senior", "dias": max(3, semanas * 2)})

    if "CO" in modules:
        recursos.append({"frente": "CO", "nivel": "Senior", "dias": max(3, semanas * 2)})

    if "BASIS" in modules or config.get("needs_basis"):
        basis_horas = sum(o.get("horas", 0) for o in config.get("basis_objects", []))
        if basis_horas == 0:
            basis_horas = 16  # 2 dias mínimo
        recursos.append({"frente": "BASIS", "nivel": "Senior", "dias": max(2, round(basis_horas / 8))})

    if "ADDON" in modules:
        addon_horas = sum(o.get("horas", 0) for o in config.get("addon_objects", []))
        if addon_horas == 0:
            addon_horas = 16
        recursos.append({"frente": "SOFICOM", "nivel": "Senior", "dias": max(2, round(addon_horas / 8))})

    # GP proporcional ao tamanho do projeto
    if semanas <= 3:
        gp_dias = 2
    elif semanas <= 6:
        gp_dias = 4
    elif semanas <= 12:
        gp_dias = 8
    else:
        gp_dias = 15
    recursos.append({"frente": "GP", "nivel": "Senior", "dias": gp_dias})

    return recursos


# ══════════════════════════════════════════════════════════════
# BUILDER DE ENTREGÁVEIS A PARTIR DO CATÁLOGO
# ══════════════════════════════════════════════════════════════
def build_entregaveis(tipo: str) -> list:
    """Constrói a lista completa de entregáveis a partir do catálogo."""
    config = get_demand_config(tipo)
    entregaveis = []

    # SD
    for o in config.get("sd_objects", []):
        entregaveis.append({**o, "mod": "SD"})

    # FI
    for o in config.get("fi_objects", []):
        entregaveis.append({**o, "mod": "FI"})

    # ABAP
    for o in config.get("abap_objects", []):
        entregaveis.append({**o, "mod": "ABAP"})

    # ADDON
    for o in config.get("addon_objects", []):
        entregaveis.append({**o, "mod": "SOFICOM"})

    # BASIS
    for o in config.get("basis_objects", []):
        entregaveis.append({**o, "mod": "BASIS"})

    # Adicionar testes/apoio padrão para cada módulo funcional
    funcionais = set()
    for e in entregaveis:
        if e["mod"] in ("SD", "FI", "MM", "PP", "HR", "CO", "QM", "WM"):
            funcionais.add(e["mod"])
    for mod in funcionais:
        entregaveis.append({"mod": mod, "item": f"Testes da consultoria — {mod}", "horas": 8, "fase": "Realize"})
        entregaveis.append({"mod": mod, "item": f"Apoio aos testes integrados (1 dia útil) — {mod}", "horas": 8, "fase": "Deploy"})
        entregaveis.append({"mod": mod, "item": f"Acompanhamento Go-Live (1 dia útil) — {mod}", "horas": 8, "fase": "Go-Live"})

    # ABAP: testes + apoio + go-live
    if any(e["mod"] == "ABAP" for e in entregaveis):
        entregaveis.append({"mod": "ABAP", "item": "Testes unitários ABAP", "horas": 8, "fase": "Realize"})
        entregaveis.append({"mod": "ABAP", "item": "Apoio aos testes integrados (1 dia útil) — ABAP", "horas": 8, "fase": "Deploy"})
        entregaveis.append({"mod": "ABAP", "item": "Acompanhamento Go-Live (1 dia útil) — ABAP", "horas": 8, "fase": "Go-Live"})
        entregaveis.append({"mod": "ABAP", "item": "Documentação técnica + suporte aos testes", "horas": 12, "fase": "Realize"})

    return entregaveis


# ══════════════════════════════════════════════════════════════
# 21 PREMISSAS PADRÃO DIRETO AO PONTO (sem placeholders)
# ══════════════════════════════════════════════════════════════
PREMISSAS_PADRAO = [
    "Caso necessário, tempo de suporte pós go-live, o mesmo pode ser solicitado via baseline AMS.",
    "Os acessos necessários para a realização das atividades deverão estar liberados até a data de início do projeto. O tempo de ociosidade da equipe do projeto, causado pela falta de acesso ou autorizações necessárias dentro do ambiente do cliente, impactarão o custo do projeto e serão tratados através de solicitação de mudança.",
    "Os usuários disponibilizados deverão ter acesso para depuração no ambiente de Qualidade.",
    "Criações/Manutenções/Correções em programas Z (programas Z, relatórios, formulários etc.) não fazem parte desta proposta, exceto os detalhados explicitamente no escopo.",
    "Todos os desenvolvimentos serão realizados utilizando linguagem ABAP.",
    "Desenvolvimento/Correção de interfaces com outros sistemas não faz parte do escopo desta proposta.",
    "O início das atividades previstas nesta proposta, bem como alocação efetiva dos consultores, acontecerá somente após aprovação formal do cronograma elaborado pela Direto ao Ponto, tendo como tempo estimado de disponibilização da equipe até 30 dias.",
    "O termo de aceite / encerramento do projeto se dará automaticamente 7 dias após: GO-LIVE ou período de suporte previsto, o que ocorrer primeiro.",
    "O gerenciamento desta proposta e acompanhamento das atividades realizadas pelos consultores, será feito de forma remota durante toda a execução do projeto.",
    "Dúvidas ou falhas devem ser reportadas durante o período de testes, acordado em cronograma. Somente serão considerados falhas/erros aqueles reportados durante a vigência do período de acompanhamento dos testes integrados.",
    "As atividades previstas serão realizadas de forma remota pelos consultores da Direto ao Ponto.",
    "Manuais de usuários serão de responsabilidade do Cliente.",
    "Treinamento de multiplicadores e usuários finais serão de responsabilidade do Cliente, bem como a preparação do material de treinamento.",
    "É de responsabilidade do cliente a revisão de manuais de usuário já existentes para os processos/desenvolvimentos previstos no escopo desta proposta.",
    "Os colaboradores do Cliente designados para atuar no projeto deverão possuir conhecimento detalhado das áreas que representam, bem como poder de tomada de decisões para implementação no projeto.",
    "Qualquer atraso por motivo do cliente comprometerá o prazo de entrega da solução sem qualquer ônus à Direto ao Ponto.",
    "Em caso de paralisação do projeto, o tempo de replanejamento na retomada do projeto será tratado através de solicitação de mudança de escopo e cobrado em proposta à parte.",
    "A documentação do projeto será entregue em língua portuguesa.",
    "Será utilizado o idioma português nas configurações e desenvolvimentos, não estando previstas traduções para outro idioma.",
    "Disponibilização de cenários de teste em QAS antes do início do projeto.",
    "O dia de consultoria tem uma duração de 8 horas, sendo o sugerido o horário 08h30-12h00 e 13h30-18h00. De segunda a sexta-feira.",
]


# ══════════════════════════════════════════════════════════════
# EXCLUSÕES PADRÃO
# ══════════════════════════════════════════════════════════════
EXCLUSOES_PADRAO = [
    "Não contempla aplicação de notas SAP",
    "Não contempla treinamento de usuários finais",
    "Não contempla migração de dados históricos",
    "Não contempla desenvolvimento/correção de interfaces com outros sistemas",
]


# ══════════════════════════════════════════════════════════════
# VALIDADOR — rejeita placeholders
# ══════════════════════════════════════════════════════════════
PLACEHOLDER_PATTERNS = [
    "premissa", "descrição", "descrição fiscal", "descricao",
    "lei específica", "lei especifica", "premissa específica",
    "item", "entregavel", "entregável", "...",
    "[descrição]", "(descrição)", "<descrição>",
]


def is_placeholder(text: str) -> bool:
    """Verifica se o texto é um placeholder genérico."""
    if not text:
        return True
    text_lower = text.lower().strip()
    if len(text_lower) < 5:
        return True
    # Match exato com placeholder
    if text_lower in PLACEHOLDER_PATTERNS:
        return True
    return False


def filter_entregaveis(entregaveis: list) -> list:
    """Remove entregáveis com placeholders ou itens vazios."""
    filtered = []
    seen = set()
    for e in entregaveis:
        if not isinstance(e, dict):
            continue
        item = e.get("item", "")
        if is_placeholder(item):
            continue
        # Deduplicar por item
        key = item.strip().lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        # Garantir campos obrigatórios
        if not e.get("horas"):
            e["horas"] = 8
        if not e.get("fase"):
            e["fase"] = "Realize"
        filtered.append(e)
    return filtered


def filter_premissas(premissas: list, rfp_text: str) -> list:
    """Filtra premissas removendo placeholders e premissas com termos fora da RFP."""
    rfp_lower = (rfp_text or "").lower()
    # Termos condicionais — só aparecem se estiverem na RFP
    conditional = ["maquininha", "tef", "pinpad", "econf", "serasa", "cnab", "boleto", "ciap"]
    filtered = []
    seen = set()
    for p in premissas:
        if not p or is_placeholder(p):
            continue
        if p in seen:
            continue
        p_lower = p.lower()
        skip = False
        for term in conditional:
            if term in p_lower and term not in rfp_lower:
                skip = True
                break
        if skip:
            continue
        seen.add(p)
        filtered.append(p)
    return filtered
