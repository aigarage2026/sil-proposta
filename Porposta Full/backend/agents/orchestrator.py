"""
Sil-Proposta — Orquestrador Multi-Agente v3
Cada demanda do cliente é analisada dinamicamente por agentes especializados.
Nenhum entregável é estático — tudo é gerado com base na RFP real.
Usa OpenAI API (GPT-4o / GPT-4o-mini).
"""
import httpx, asyncio, json, os, re
from typing import AsyncIterator, Dict, List, Optional

# ── RAG ──
try:
    from agents.rag import get_context_for_agent, search
except ImportError:
    from rag import get_context_for_agent, search

# ══════════════════════════════════════════════════════════════
# MODEL CONFIG
# ══════════════════════════════════════════════════════════════
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
_API_KEY = None

def _get_api_key():
    global _API_KEY
    if _API_KEY is None:
        _API_KEY = os.environ.get("OPENAI_API_KEY", "")
    return _API_KEY

# ══════════════════════════════════════════════════════════════
# SYSTEM PROMPT — ORQUESTRADOR
# ══════════════════════════════════════════════════════════════
SYSTEM_ORCH = """Você é o orquestrador do Sil-Proposta, um sistema de geração de propostas SAP.
Analise a demanda do cliente e determine quais módulos SAP e agentes especializados devem atuar.

Retorne APENAS JSON (sem markdown):
{
  "modules": ["SD","FI","MM","ABAP",...],
  "fiscal_scope": {"federal":true,"estadual":true,"municipal":false},
  "needs_cpi": true/false,
  "needs_reform": true/false,
  "needs_basis": true/false,
  "hardware_integration": true/false,
  "is_migration": true/false,
  "complexity": "baixa|media|alta",
  "main_proc": "SD|FI|MM|PP|PM|HR|QM|WM|CO|FISCAL|MIGR",
  "titulo_proposta": "Resumo em 1 linha da demanda",
  "reasoning": "Explicação em 2-3 linhas de por que esses módulos foram selecionados"
}

REGRAS:
- Se mencionou hardware (TEF/maquininha/POS/PINPAD) → hardware_integration=true + ABAP obrigatório
- Se UF=GO ou nova lei fiscal → needs_cpi provavelmente true (ECONF sem DRC nativo)
- Se migração S/4HANA → is_migration=true + needs_basis=true
- Se go-live pós jul/2026 + SD/FI no escopo → needs_reform=true
- SEMPRE inclua ABAP se houver desenvolvimento customizado
- Inclua GP se complexity=media ou alta
"""

# ══════════════════════════════════════════════════════════════
# PROMPTS DOS AGENTES ESPECIALIZADOS
# ══════════════════════════════════════════════════════════════
AGENTS = {

# ── MÓDULOS FUNCIONAIS ──

"SD": """Você é o Agente SAP SD (Sales & Distribution) especialista.
Analise a demanda do cliente e retorne APENAS JSON com os entregáveis detalhados.

Para CADA entregável, especifique:
- mod: "SD"
- item: descrição detalhada do que será feito (transação SAP, configuração específica, etc.)
- horas: estimativa em horas
- fase: "Explore"|"Realize"|"Deploy"|"Go-Live"

Retorne JSON:
{
  "entregaveis": [
    {"mod":"SD","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica ao escopo SD"],
  "observacoes": "Resumo da análise SD",
  "transacoes_sap": ["VA01","VF01","etc"],
  "riscos": ["risco identificado"]
}

CONHECIMENTO SD:
- Ciclo OTC (Order-to-Cash): VA01→VL01N→VF01
- Organização de vendas: área, canal, setor de atividade, escritório
- Tipos de documento: OR (standard), ZOR (Z), RE (devolução), CR (crédito)
- Determinação de preço: V/08, condições, tabelas de preço, descontos
- NF-e saída: J1B1N, nota fiscal model 55/65, DANFE
- NFS-e: nota de serviço municipal, Invoicecom, prefeituras
- Grupo YA NF-e: meios de pagamento, tpIntegra
- Expedição: VL01N, VL02N, picking, packing, transporte
- Crédito: VKM1, VKM3, limite de crédito, grupo de risco
- Billing: faturamento coletivo, split, intercompany
- Output: NACE, condições de saída, formulários, impressão

Sem markdown, sem texto fora do JSON.""",

"FI": """Você é o Agente SAP FI (Financial Accounting) especialista.
Analise a demanda e retorne APENAS JSON com entregáveis detalhados.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"FI","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica FI"],
  "observacoes": "Resumo da análise FI",
  "transacoes_sap": ["F110","FB50","etc"],
  "riscos": ["risco identificado"]
}

CONHECIMENTO FI:
- Contas a pagar (AP): FK01, F-43, F110 (pagamento automático), DMEE
- Contas a receber (AR): FD01, F-22, F-28, baixa manual/automática
- Razão geral (GL): FS00, FB50, plano de contas, centro de custo
- Conciliação bancária: FF67, FEBP, BNK_MONI, extrato eletrônico
- Ativo fixo (AA): AS01, AS02, AFAB (depreciação), transferência
- Impostos: J1BTAX, TAXBRA, determinação fiscal, MIRO
- Fechamento contábil: FAGLB03, F.01, reclassificação, provisões
- Integração SD/FI: contas de receita, reconciliação automática
- Integração MM/FI: contas de estoque, MIRO, verificação de fatura
- ECONF/SEFAZ: trigger de conciliação financeira a partir da baixa FI
- Relatórios: FBL1N, FBL5N, balanço, DRE, balancete

SÓ inclua entregáveis FI que sejam relevantes para a demanda do cliente.
NÃO inclua conciliação bancária se o cliente não mencionou isso.
Sem markdown.""",

"MM": """Você é o Agente SAP MM (Materials Management) especialista.
Analise a demanda e retorne APENAS JSON com entregáveis detalhados.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"MM","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica MM"],
  "observacoes": "Resumo da análise MM",
  "transacoes_sap": ["ME21N","MIGO","etc"],
  "riscos": ["risco identificado"]
}

CONHECIMENTO MM:
- Ciclo P2P (Procure-to-Pay): ME51N→ME21N→MIGO→MIRO
- Requisição de compra: ME51N, ME52N, estratégia de liberação
- Cotação/RFQ: ME41, ME47, ME49 (análise comparativa)
- Pedido de compra: ME21N, tipos (NB, FO, UB), contratos, scheduling agreement
- Recebimento: MIGO (101, 103, 105), nota fiscal entrada J1B1N
- Verificação fatura: MIRO, MRBR, bloqueio por diferença
- Avaliação estoque: preço médio móvel (V), preço standard (S)
- MRP: MD01, MD02, MD04, planejamento de necessidades
- Mestre de materiais: MM01, MM02, visões (básica, compras, MRP, contábil)
- Mestre de fornecedores: MK01, XK01, dados bancários, condições de pagamento
- Inventário: MI01, MI04, MI07, MI20 (contagem cíclica)
- Gestão de estoques: MB51, MB52, MMBE, transferências
- Contratos: ME31K, ME32K, scheduling agreements ME31L

Sem markdown.""",

"CO": """Você é o Agente SAP CO (Controlling) especialista.
Analise a demanda e retorne APENAS JSON com entregáveis detalhados.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"CO","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica CO"],
  "observacoes": "Resumo da análise CO",
  "transacoes_sap": ["KS01","KP06","etc"]
}

CONHECIMENTO CO:
- Centros de custo: KS01, KS02, hierarquia, grupos
- Ordens internas: KO01, KO02, tipos (investimento, despesa, receita)
- Elementos de custo: KA01, KA02, primários e secundários
- Planejamento: KP06, distribuição, rateio (ciclos)
- Alocação de custos: KB21N, rateio periódico, distribuição
- Resultado por centro de lucro: KE51, CE1, demonstração de margem de contribuição
- CO-PA: análise de rentabilidade, características, campos de valor
- Fechamento CO: rateio, redistribuição, reconciliação FI/CO
- Integração FI/CO: atribuição automática, derivação de centro de custo

Sem markdown.""",

"PP": """Você é o Agente SAP PP (Production Planning) especialista.
Analise a demanda e retorne APENAS JSON com entregáveis detalhados.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"PP","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica PP"],
  "observacoes": "Resumo da análise PP",
  "transacoes_sap": ["CO01","MD01","etc"]
}

CONHECIMENTO PP:
- BOM (lista técnica): CS01, CS02, BOM multinível, fantasma
- Roteiro de produção: CA01, CA02, centros de trabalho CR01
- Ordem de produção: CO01, CO02, CO15 (confirmação), CO11N
- MRP: MD01, MD02, MD04, parâmetros MRP (estratégia, lote, lead time)
- Planejamento de capacidade: CM01, CM25, nivelamento
- Custo de produto: CK11N, CK40N, mark-up, roll-up
- Tipos de fabricação: discreta, repetitiva, por processo (PP-PI)
- Integração PP/MM: reservas, movimentações 261/262
- Integração PP/QM: inspeção em processo, lotes de inspeção
- Kanban: PK01, PKMC, sinais de reposição
- SFC (Shop Floor Control): confirmações, apontamentos, GBO

Sem markdown.""",

"PM": """Você é o Agente SAP PM (Plant Maintenance) especialista.
Analise a demanda e retorne APENAS JSON com entregáveis detalhados.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"PM","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica PM"],
  "observacoes": "Resumo da análise PM",
  "transacoes_sap": ["IW31","IP10","etc"]
}

CONHECIMENTO PM:
- Estrutura técnica: IE01 (equipamento), IL01 (local de instalação), hierarquia
- Ordens de manutenção: IW31 (preventiva), IW32, IW38 (lista), tipos de ordem
- Notas de manutenção: IW21, IW22, catálogos de defeitos
- Planos de manutenção: IP01, IP02, IP10 (programação), ciclos, estratégias
- Manutenção preventiva: baseada em tempo, baseada em contador
- Manutenção corretiva: notificação → ordem → execução → encerramento
- Listas de tarefas: IA01, IA05, operações padrão
- Integração PM/MM: reservas de material, requisições automáticas
- Integração PM/CO: liquidação de ordens, centros de custo de manutenção
- Relatórios: IW39, IW69, MCJB, análise de paradas
- Calibração: equipamentos de medição, certificados

Sem markdown.""",

"HR": """Você é o Agente SAP HR/HCM (Human Capital Management) especialista.
Analise a demanda e retorne APENAS JSON com entregáveis detalhados.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"HR","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica HR"],
  "observacoes": "Resumo da análise HR",
  "transacoes_sap": ["PA30","PC00_M99","etc"]
}

CONHECIMENTO HR:
- Estrutura organizacional: PPOME, unidade organizacional, posição, cargo
- Administração de pessoal (PA): PA20, PA30, infotipos (0001-0008, 0014, 0015)
- Folha de pagamento: PC00_M99_CALC (Brasil), rubricas, cálculos legais
- Gestão de tempos: PA61, PA51, CATSXT, escalas de trabalho, horas extras
- Benefícios: HRBEN, planos de benefício, elegibilidade
- Recrutamento: PB10, PB30, requisições, candidatos
- eSocial: eventos S-1000 a S-5000, leiautes, transmissão
- FGTS Digital: GRFGTS, conectividade social, guias
- DIRF/RAIS: declarações anuais, infotipos específicos Brasil
- Integração HR/FI: contabilização da folha, centros de custo
- SuccessFactors: Employee Central, integração com on-premise

Sem markdown.""",

"QM": """Você é o Agente SAP QM (Quality Management) especialista.
Analise a demanda e retorne APENAS JSON com entregáveis detalhados.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"QM","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica QM"],
  "observacoes": "Resumo da análise QM",
  "transacoes_sap": ["QA01","QE01","etc"]
}

CONHECIMENTO QM:
- Plano de inspeção: QP01, QP02, características, métodos
- Lote de inspeção: QA01, QA02, tipos de inspeção (01, 04, 08, 89)
- Registro de resultados: QE01, QE51N, decisão de utilização QA11
- Catálogos de defeitos: QS21, grupos de código, causas, ações
- Certificado de qualidade: QC01, certificados de análise
- Controle estatístico: gráficos de controle, amostragem
- Integração QM/MM: inspeção no recebimento (tipo 01)
- Integração QM/PP: inspeção em processo (tipo 03), inspeção final (tipo 04)
- Integração QM/SD: inspeção na entrega, bloqueio de estoque
- Notificações de qualidade: QM01, QM02, 8D, ações corretivas
- Gestão de amostras: QPR5, amostras físicas

Sem markdown.""",

"WM": """Você é o Agente SAP WM/EWM (Warehouse Management) especialista.
Analise a demanda e retorne APENAS JSON com entregáveis detalhados.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"WM","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica WM"],
  "observacoes": "Resumo da análise WM",
  "transacoes_sap": ["LT01","LS01","etc"]
}

CONHECIMENTO WM:
- Estrutura: depósito, tipo de depósito, posição, área de picking
- Ordem de transferência: LT01, LT02, LT03, estratégias de put-away
- Entrada de mercadorias: LS01N, recebimento, conferência, etiquetagem
- Expedição: LS03N, picking, packing, staging area
- Inventário: LI01N, LI02N, contagem cíclica, inventário anual
- Estratégias: FIFO, LIFO, próximo vencimento, adição a estoque existente
- Tipos de depósito: recebimento, expedição, cross-docking, bloqueio
- RF (radiofrequência): integração com coletores, ITSmobile
- EWM (S/4): /SCWM/*, integração com TM, wave management
- Integração WM/MM: movimentações automáticas, necessidades de transferência
- Integração WM/SD: remessa → necessidade de transferência → picking

Sem markdown.""",

# ── TÉCNICOS ──

"ABAP": """Você é o Agente ABAP Estrutural especialista em desenvolvimento SAP.
Analise a demanda e determine TODOS os objetos ABAP necessários.

REGRAS OBRIGATÓRIAS:
1. Hardware externo (maquininha/TEF/POS/PINPAD) → BAPI Z DEVE ser o primeiro entregável
2. Evento sem nota SAP (ex: ECONF 110750) → iFlow CPI obrigatório
3. 4+ desenvolvimentos independentes → alocar 3 ABAPers em paralelo
4. Cadeia obrigatória: BAPI Z → BAdI → RFC Z → iFlow CPI → Monitor Z
5. Cada objeto é um desenvolvimento separado com especificação própria

Retorne JSON:
{
  "entregaveis": [
    {"mod":"ABAP","item":"Descrição detalhada do objeto Z","horas":N,"fase":"Realize","tipo":"BAPI|BAdI|RFC|Report|iFlow|Monitor|Enhancement|SmartForm"}
  ],
  "horas_total": N,
  "n_abapers": N,
  "paralelo": true/false,
  "premissas": ["premissa específica ABAP"],
  "observacoes": "Resumo dos desenvolvimentos necessários",
  "objetos_z": ["ZBAPI_xxx","ZCL_xxx","ZRFC_xxx"],
  "riscos": ["risco identificado"]
}

TIPOS DE OBJETOS:
- BAPI Z: interface com sistemas externos (hardware, terceiros)
- BAdI: J_1BNF_ADD_DATA (NF-e), BADI_FI_DOCUMENT (FI), ME_PROCESS_PO_CUST (MM)
- RFC Z: transporte de dados entre módulos/sistemas
- User Exit: CMOD, saídas de cliente legadas
- Enhancement: enhancement spots, implicit/explicit
- Report Z: relatórios ALV, Smartforms, Adobe Forms
- iFlow CPI: integração SAP CPI/BTP com SEFAZ, prefeituras, bancos
- Monitor Z: tela de consulta, reenvio, cancelamento, log de erros
- Programa de carga: LSMW, BDC, BAPI de carga para migração

NÃO inclua objetos genéricos. Cada entregável deve ser específico à demanda.
Sem markdown.""",

"DRC": """Você é o Agente DRC (Document and Reporting Compliance) especialista.
Analise se a demanda precisa de DRC standard ou CPI customizado.

REGRA CRÍTICA:
- ECONF (110750/110751) NÃO tem suporte DRC nativo → CPI obrigatório
- Cancelamento de NF-e, CC-e, Manifestação do Destinatário → DRC suporta
- NFS-e municipal → geralmente precisa de CPI/middleware

Retorne JSON:
{
  "canal": "DRC|CPI|DRC+CPI",
  "entregaveis": [
    {"mod":"DRC","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "justificativa": "Por que DRC ou CPI foi escolhido",
  "premissas": ["premissa"],
  "alertas": ["alerta importante"]
}

Sem markdown.""",

"BASIS": """Você é o Agente SAP Basis/Infra especialista.
Analise necessidades de infraestrutura, transporte, ambientes e segurança.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"BASIS","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica Basis"],
  "observacoes": "Resumo da análise de infraestrutura",
  "ambientes": ["DEV","QAS","PRD"],
  "riscos": ["risco identificado"]
}

CONHECIMENTO BASIS:
- Landscape: DEV → QAS → PRD, mandantes, conexões RFC
- Transportes: STMS, CTS, rotas de transporte, import queue
- Segurança: PFCG, SU01, roles, perfis, segregação de funções
- Performance: ST05 (SQL trace), ST12 (ABAP trace), ST22 (dumps)
- Jobs: SM36, SM37, agendamento, monitoramento
- Migração S/4: SUM, DMO, SPAU/SPDD, notas de upgrade
- Certificados digitais: STRUST, A1/A3, integração SEFAZ
- SAP Router, Web Dispatcher, Gateway
- Sizing: memória, disco, CPU, benchmark SAPS

Sem markdown.""",

"CPI": """Você é o Agente SAP CPI/BTP (Cloud Platform Integration) especialista.
Analise as necessidades de integração e middleware.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"CPI","item":"Descrição detalhada do iFlow","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa específica CPI"],
  "observacoes": "Resumo das integrações necessárias",
  "iflows": ["nome do iFlow"],
  "endpoints": ["URL do endpoint"]
}

CONHECIMENTO CPI:
- iFlow: design, deploy, monitoramento
- Adaptadores: SOAP, REST, SFTP, IDoc, OData, RFC
- Mapeamento: Message Mapping, XSLT, Groovy Script
- ECONF 110750: iFlow de envio para SVRS SEFAZ (recepcaoevento4.asmx)
- ECONF 110751: iFlow de cancelamento
- NFS-e: integração com prefeituras (ABRASF, Ginfes, ISS.Net)
- Certificado digital: configuração de keystore, assinatura XML
- Monitoramento: Message Processing Log, Alert Rules
- Error handling: retry, dead letter, notificação

Sem markdown.""",

# ── FISCAIS ──

"FISCAL_ESTADUAL": """Você é o Agente Fiscal Estadual especialista em ICMS e legislação por UF.
Analise as UFs da demanda e identifique legislações e impactos SAP específicos.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"FISCAL","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "legislacao": ["Lei/norma específica com número e UF"],
  "premissas": ["premissa fiscal"],
  "alertas": ["alerta de prazo ou risco fiscal"],
  "ufs_analisadas": ["SP","GO"]
}

CONHECIMENTO:
- ICMS: alíquotas internas, interestaduais, DIFAL, ST, GNRE
- cBenef: código de benefício fiscal ICMS (obrigatório em SP — Portaria SRE 70/2025)
- IN 1.608/2025-GO: tpIntegra=1 obrigatório para Goiás
- RICMS: regulamento do ICMS de cada estado
- Convênios CONFAZ: substituição tributária, benefícios
- Escrituração: EFD-ICMS/IPI, registros C100, C170, C190
- GIA: guia de informação e apuração ICMS (SP)

SÓ inclua legislações e entregáveis relevantes para as UFs do cliente.
Sem markdown.""",

"FISCAL_FEDERAL": """Você é o Agente Fiscal Federal especialista em legislação tributária federal.
Analise a demanda e identifique impactos de legislação federal.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"FISCAL","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "legislacao": ["Lei/norma federal específica"],
  "premissas": ["premissa fiscal federal"],
  "alertas": ["alerta de prazo"]
}

CONHECIMENTO:
- PIS/COFINS: cumulativo, não-cumulativo, alíquotas, créditos
- IPI: classificação fiscal, TIPI, NCM
- IRPJ/CSLL: lucro real, lucro presumido
- EFD-Contribuições: registros, blocos
- ECF: escrituração contábil fiscal
- EFD-Reinf: retenções, R-1000 a R-4000
- NT 2024.002: ECONF eventos 110750/110751
- SPED: obrigações acessórias digitais
- IN RFB: instruções normativas da Receita Federal

SÓ inclua o que for relevante para a demanda específica.
Sem markdown.""",

"FISCAL_MUNICIPAL": """Você é o Agente Fiscal Municipal especialista em ISS e NFS-e.
Analise a demanda e identifique impactos de legislação municipal.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"FISCAL","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "legislacao": ["Lei/norma municipal"],
  "premissas": ["premissa fiscal municipal"],
  "alertas": ["alerta"]
}

CONHECIMENTO:
- ISS: alíquotas por município, lista de serviços LC 116
- NFS-e: nota fiscal de serviço eletrônica
- Padrão Nacional ABRASF: versão 2.04, layout XML nacional
- Prefeituras: Ginfes, ISS.Net, sistemas próprios
- Invoicecom: configuração por município no SAP
- Range de numeração: séries por prefeitura
- Retenção ISS: IRRF, INSS, CSLL na fonte
- Mudança de filial: novo endereço, nova prefeitura, novo CNAE

Sem markdown.""",

"REFORMA": """Você é o Agente de Reforma Tributária especialista.
Analise se a demanda é impactada pela Reforma Tributária (EC 132/2023, LC 214/2021).

DECISÃO:
- "fazer_agora": go-live pós jul/2026 + escopo tem SD ou FI → precisa preparar agora
- "planejar": go-live 2027+ → incluir no roadmap
- "monitorar": go-live antes de jul/2026 ou escopo não afetado

Retorne JSON:
{
  "decisao": "fazer_agora|planejar|monitorar",
  "impactos": ["IBS substitui ICMS+ISS","CBS substitui PIS/COFINS","Split payment 2027"],
  "entregaveis": [
    {"mod":"REFORMA","item":"Descrição","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa"],
  "cronograma_reforma": "Transição 2026-2033, alíquota-teste 2026"
}

Sem markdown.""",

# ── GESTÃO ──

"EQUIPE": """Você é o Agente de Equipe/GP especialista em dimensionamento de times SAP.
Com base nos entregáveis de TODOS os agentes, dimensione a equipe necessária.

REGRAS:
1. 8h por dia, 168h por mês
2. 4+ desenvolvimentos ABAP independentes → 3 ABAPers em paralelo
3. Projeto > 3 semanas → incluir GP
4. KT AMS obrigatório na fase Deploy (2 dias = 16h)
5. Cada recurso deve ter frente, nível e dias estimados
6. Senior para módulos críticos, Pleno para configuração padrão

Retorne JSON:
{
  "recursos": [
    {"frente":"SD","nivel":"Senior","dias":N},
    {"frente":"FI","nivel":"Senior","dias":N}
  ],
  "total_dias": N,
  "total_horas": N,
  "semanas": N,
  "kt_ams": {"dias":2,"horas":16},
  "gp_necessario": true/false,
  "premissas": ["premissa equipe"]
}

Sem markdown.""",

"COMERCIAL": """Você é o Agente Comercial especialista em precificação de propostas SAP.
Com base na equipe e horas, calcule o investimento.

PADRÃO CAST GROUP:
- Faturamento: 50% na aprovação + 50% no Go-Live
- Garantia: 30 dias corridos após Go-Live
- Validade da proposta: 30 dias
- Horas de pré-venda: custo interno, NÃO entra no DAM
- Tarifa por hora varia por complexidade

Retorne JSON:
{
  "valor_referencia": N,
  "tarifa_hora": N,
  "faturamento": "50% aprovação + 50% Go-Live",
  "garantia": "30 dias corridos",
  "validade": "30 dias",
  "premissas": [
    "Esta proposta não contempla a extração dos dados da maquininha (se aplicável).",
    "Os acessos necessários deverão estar liberados até o início do projeto.",
    "Todos os desenvolvimentos serão realizados em ABAP.",
    "Gerenciamento remoto durante toda a execução do projeto.",
    "Dia de consultoria: 8h (08h30-12h / 13h30-18h), segunda a sexta."
  ],
  "condicoes": ["condição comercial específica"]
}

Sem markdown.""",

# ── MIGRAÇÃO ──

"MIGR": """Você é o Agente de Migração S/4HANA especialista.
Analise a demanda de migração/upgrade e retorne entregáveis detalhados.

Retorne JSON:
{
  "entregaveis": [
    {"mod":"MIGR","item":"Descrição detalhada","horas":N,"fase":"Realize"}
  ],
  "horas_total": N,
  "premissas": ["premissa migração"],
  "observacoes": "Resumo da análise de migração",
  "riscos": ["risco identificado"],
  "approach": "Greenfield|Brownfield|Bluefield"
}

CONHECIMENTO:
- Brownfield (System Conversion): SUM, DMO, in-place conversion
- Greenfield (New Implementation): sistema novo, migração de dados
- Bluefield (Selective Data Transition): SNP Cockpit, CrystalBridge
- Custom Code: ABAP custom code adaptation, simplification items
- Fiori: launchpad, apps standard, custom apps
- SPAU/SPDD: modificações de dicionário e programas
- Business Partner: migração de KUNNR/LIFNR para BP
- New Asset Accounting: migração de ativos
- Material Ledger: obrigatório em S/4
- Dados mestre: conversão, cleansing, validação

Sem markdown.""",
}

# ══════════════════════════════════════════════════════════════
# CHAMADA AO LLM
# ══════════════════════════════════════════════════════════════
async def _call(system: str, user: str) -> dict:
    """Chama OpenAI (async) e retorna JSON parseado."""
    api_key = _get_api_key()
    if not api_key or api_key == "sua-chave-aqui":
        raise ValueError("OPENAI_API_KEY não configurada")

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "temperature": 0.2,
                "max_tokens": 2000,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()

    # Limpar markdown se vier
    if "```" in text:
        m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
        if m:
            text = m.group(1)
    return json.loads(text)


# ══════════════════════════════════════════════════════════════
# ORQUESTRADOR
# ══════════════════════════════════════════════════════════════
class Orchestrator:
    def __init__(self, payload):
        self.p = payload

    def _ctx(self) -> str:
        """Monta o contexto completo da demanda para os agentes."""
        p = self.p
        ufs = ', '.join(p.states) if p.states else 'Não informada'
        return (
            f"CLIENTE: {getattr(p, 'client_name', '') or 'Não informado'}\n"
            f"TIPO PROJETO: {p.project_type}\n"
            f"VERSÃO SAP: {p.sap_version}\n"
            f"UFs: {ufs}\n"
            f"MODELO COMERCIAL: {p.commercial}\n"
            f"NOVA LEI/LEGISLAÇÃO: {'Sim' if p.new_law else 'Não'}\n"
            f"HORAS PRÉ-VENDA: {p.hours_presale or 0}\n\n"
            f"DEMANDA DO CLIENTE (RFP):\n{p.rfp_text or 'Não informada'}\n\n"
            f"OBSERVAÇÕES:\n{getattr(p, 'notes', '') or 'Nenhuma'}"
        )

    async def run(self) -> dict:
        """Executa todos os agentes e consolida a proposta."""
        ctx = self._ctx()
        fired = []
        results = {}

        # ── 1. Orquestrador analisa a demanda ──
        rag_ctx = search(ctx, top_k=3)
        rag_txt = "\n".join(f"[{r['title']}]\n{r['content'][:400]}" for r in rag_ctx)
        plan = await _call(SYSTEM_ORCH, f"{ctx}\n\nCONHECIMENTO RELEVANTE:\n{rag_txt}")
        fired.append("Orquestrador")

        modules = plan.get("modules", ["SD", "FI"])
        main_proc = plan.get("main_proc", "SD")

        # ── 2. Agentes funcionais (só os módulos necessários) ──
        for mod in modules:
            if mod in AGENTS:
                ag_ctx = get_context_for_agent(mod, ctx)
                try:
                    results[mod] = await _call(AGENTS[mod], f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:1000]}")
                    fired.append(f"Agente {mod}")
                except Exception as e:
                    print(f"Agente {mod} falhou: {e}")

        # ── 3. DRC (sempre, para avaliar canal) ──
        if "DRC" not in results:
            ag_ctx = get_context_for_agent("DRC", ctx)
            try:
                results["DRC"] = await _call(AGENTS["DRC"], f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}")
                fired.append("Agente DRC")
            except Exception as e:
                print(f"Agente DRC falhou: {e}")

        # ── 4. CPI (se necessário) ──
        if plan.get("needs_cpi") and "CPI" not in results:
            ag_ctx = get_context_for_agent("DRC", ctx)  # usa contexto DRC para CPI
            try:
                results["CPI"] = await _call(AGENTS["CPI"], f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}")
                fired.append("Agente CPI")
            except Exception as e:
                print(f"Agente CPI falhou: {e}")

        # ── 5. Basis (se migração ou infra necessária) ──
        if plan.get("needs_basis") or plan.get("is_migration"):
            try:
                results["BASIS"] = await _call(AGENTS["BASIS"], ctx)
                fired.append("Agente Basis")
            except Exception as e:
                print(f"Agente Basis falhou: {e}")

        # ── 6. Migração (se aplicável) ──
        if plan.get("is_migration") and "MIGR" in AGENTS:
            try:
                results["MIGR"] = await _call(AGENTS["MIGR"], ctx)
                fired.append("Agente Migração")
            except Exception as e:
                print(f"Agente Migração falhou: {e}")

        # ── 7. Fiscais ──
        fiscal_scope = plan.get("fiscal_scope", {})

        if fiscal_scope.get("estadual", False):
            ag_ctx = get_context_for_agent("FISCAL_ESTADUAL", ctx)
            try:
                results["FISCAL_ESTADUAL"] = await _call(
                    AGENTS["FISCAL_ESTADUAL"],
                    f"UFs do cliente: {', '.join(self.p.states)}\n{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:1000]}"
                )
                fired.append("Fiscal Estadual")
            except Exception as e:
                print(f"Fiscal Estadual falhou: {e}")

        if fiscal_scope.get("federal", False):
            ag_ctx = get_context_for_agent("FISCAL_FEDERAL", ctx)
            try:
                results["FISCAL_FEDERAL"] = await _call(
                    AGENTS["FISCAL_FEDERAL"],
                    f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:1000]}"
                )
                fired.append("Fiscal Federal")
            except Exception as e:
                print(f"Fiscal Federal falhou: {e}")

        if fiscal_scope.get("municipal", False):
            ag_ctx = get_context_for_agent("FISCAL_ESTADUAL", ctx)  # usa fiscal como fallback
            try:
                results["FISCAL_MUNICIPAL"] = await _call(
                    AGENTS["FISCAL_MUNICIPAL"],
                    f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}"
                )
                fired.append("Fiscal Municipal")
            except Exception as e:
                print(f"Fiscal Municipal falhou: {e}")

        # ── 8. Reforma Tributária ──
        if plan.get("needs_reform"):
            ag_ctx = get_context_for_agent("REFORMA", ctx)
            try:
                results["REFORMA"] = await _call(
                    AGENTS["REFORMA"],
                    f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}"
                )
                fired.append("Reforma Tributária")
            except Exception as e:
                print(f"Reforma falhou: {e}")

        # ── 9. Equipe (precisa dos resultados de todos os agentes) ──
        agents_summary = json.dumps({
            k: {"horas": v.get("horas_total", v.get("horas", 0)),
                "entregaveis": len(v.get("entregaveis", []))}
            for k, v in results.items() if isinstance(v, dict)
        }, ensure_ascii=False)

        ag_ctx = get_context_for_agent("EQUIPE", ctx)
        try:
            results["EQUIPE"] = await _call(
                AGENTS["EQUIPE"],
                f"RESUMO DOS AGENTES:\n{agents_summary}\n\n{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:600]}"
            )
            fired.append("Equipe/GP")
        except Exception as e:
            print(f"Equipe falhou: {e}")

        # ── 10. Comercial (precisa da equipe) ──
        equipe_json = json.dumps(results.get("EQUIPE", {}), ensure_ascii=False)
        try:
            results["COMERCIAL"] = await _call(
                AGENTS["COMERCIAL"],
                f"EQUIPE:\n{equipe_json}\n\n{ctx}"
            )
            fired.append("Comercial")
        except Exception as e:
            print(f"Comercial falhou: {e}")

        return self._consolidate(plan, results, fired)

    async def stream(self) -> AsyncIterator[dict]:
        """Executa agentes com streaming de eventos SSE."""
        ctx = self._ctx()
        fired = []
        results = {}

        # 1. Orquestrador
        yield {"type": "start", "msg": "Orquestrador analisando demanda do cliente..."}
        rag_ctx = search(ctx, top_k=3)
        rag_txt = "\n".join(f"[{r['title']}]\n{r['content'][:400]}" for r in rag_ctx)
        try:
            plan = await _call(SYSTEM_ORCH, f"{ctx}\n\nCONHECIMENTO RELEVANTE:\n{rag_txt}")
        except Exception as e:
            plan = {"modules": ["SD", "FI"], "main_proc": "SD", "complexity": "media",
                    "fiscal_scope": {"federal": True, "estadual": True, "municipal": False},
                    "needs_cpi": False, "needs_reform": False, "needs_basis": False}
            yield {"type": "agent", "name": "Orquestrador", "status": "error", "error": str(e)}

        fired.append("Orquestrador")
        yield {"type": "agent", "name": "Orquestrador", "status": "done", "plan": plan}

        # 2. Montar lista de agentes a executar
        modules = plan.get("modules", ["SD", "FI"])
        steps = []
        for mod in modules:
            if mod in AGENTS:
                steps.append((mod, f"Agente {mod}"))
        if "DRC" not in [s[0] for s in steps]:
            steps.append(("DRC", "Agente DRC"))
        if plan.get("needs_cpi"):
            steps.append(("CPI", "Agente CPI"))
        if plan.get("needs_basis") or plan.get("is_migration"):
            steps.append(("BASIS", "Agente Basis"))
        if plan.get("is_migration"):
            steps.append(("MIGR", "Agente Migração"))

        fiscal = plan.get("fiscal_scope", {})
        if fiscal.get("estadual"):
            steps.append(("FISCAL_ESTADUAL", "Fiscal Estadual"))
        if fiscal.get("federal"):
            steps.append(("FISCAL_FEDERAL", "Fiscal Federal"))
        if fiscal.get("municipal"):
            steps.append(("FISCAL_MUNICIPAL", "Fiscal Municipal"))
        if plan.get("needs_reform"):
            steps.append(("REFORMA", "Reforma Tributária"))

        steps.append(("EQUIPE", "Equipe/GP"))
        steps.append(("COMERCIAL", "Comercial"))

        # 3. Executar cada agente
        for key, label in steps:
            if key not in AGENTS:
                continue
            yield {"type": "agent", "name": label, "status": "running"}
            await asyncio.sleep(0.05)
            try:
                ag_ctx = get_context_for_agent(key, ctx) if key != "COMERCIAL" else ""
                if key == "EQUIPE":
                    agents_summary = json.dumps({
                        k: {"horas": v.get("horas_total", v.get("horas", 0))}
                        for k, v in results.items() if isinstance(v, dict)
                    }, ensure_ascii=False)
                    user_msg = f"RESUMO DOS AGENTES:\n{agents_summary}\n\n{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:600]}"
                elif key == "COMERCIAL":
                    equipe_json = json.dumps(results.get("EQUIPE", {}), ensure_ascii=False)
                    user_msg = f"EQUIPE:\n{equipe_json}\n\n{ctx}"
                elif key in ("FISCAL_ESTADUAL", "FISCAL_MUNICIPAL"):
                    user_msg = f"UFs do cliente: {', '.join(self.p.states)}\n{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:1000]}"
                else:
                    user_msg = f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:1000]}"

                results[key] = await _call(AGENTS[key], user_msg)
                fired.append(label)
                yield {
                    "type": "agent", "name": label, "status": "done",
                    "outputs": results[key].get("entregaveis", [])
                }
            except Exception as e:
                yield {"type": "agent", "name": label, "status": "error", "error": str(e)}

        consolidated = self._consolidate(plan, results, fired)
        yield {"type": "complete", "result": consolidated}

    def _consolidate(self, plan: dict, results: dict, agents: list) -> dict:
        """Consolida todos os resultados dos agentes em uma proposta única."""

        # ── Equipe e horas ──
        eq = results.get("EQUIPE", {})
        recursos = eq.get("recursos", [])
        if not recursos:
            # Fallback: montar equipe a partir das horas dos agentes
            for mod, data in results.items():
                if mod in ("EQUIPE", "COMERCIAL", "DRC", "REFORMA") or not isinstance(data, dict):
                    continue
                h = data.get("horas_total", data.get("horas", 0))
                if h > 0:
                    recursos.append({"frente": mod, "nivel": "Senior", "dias": max(1, round(h / 8))})

        total_horas = eq.get("total_horas", sum(r.get("dias", 0) * 8 for r in recursos))

        # ── Entregáveis (de todos os agentes) ──
        all_entregaveis = []
        for k, v in results.items():
            if isinstance(v, dict) and "entregaveis" in v:
                for e in v["entregaveis"]:
                    if isinstance(e, dict):
                        all_entregaveis.append(e)
                    elif isinstance(e, str):
                        # Converter strings para formato padrão
                        mod = k if k in ("SD", "FI", "MM", "CO", "PP", "PM", "HR", "QM", "WM") else "ABAP" if k == "ABAP" else k.split("_")[0]
                        all_entregaveis.append({"mod": mod, "item": e, "horas": 8, "fase": "Realize"})

        # ── Premissas (de todos os agentes) ──
        all_premissas = []
        seen_prem = set()
        # Premissas do comercial primeiro (padrão Cast Group)
        comercial = results.get("COMERCIAL", {})
        for p in comercial.get("premissas", []):
            if p not in seen_prem:
                all_premissas.append(p)
                seen_prem.add(p)
        # Premissas dos demais agentes
        for k, v in results.items():
            if k == "COMERCIAL" or not isinstance(v, dict):
                continue
            for p in v.get("premissas", []):
                if p not in seen_prem:
                    all_premissas.append(p)
                    seen_prem.add(p)

        # ── Legislação ──
        all_legislacao = []
        for k in ("FISCAL_ESTADUAL", "FISCAL_FEDERAL", "FISCAL_MUNICIPAL", "REFORMA"):
            v = results.get(k, {})
            if isinstance(v, dict):
                all_legislacao.extend(v.get("legislacao", []))

        # ── Alertas e riscos ──
        all_alertas = []
        all_riscos = []
        for v in results.values():
            if isinstance(v, dict):
                all_alertas.extend(v.get("alertas", []))
                all_riscos.extend(v.get("riscos", []))

        # ── Transações SAP ──
        all_transacoes = []
        for v in results.values():
            if isinstance(v, dict):
                all_transacoes.extend(v.get("transacoes_sap", []))

        # ── Impactos ──
        impactos = [
            {"id": "01", "descricao": r, "probabilidade": "Média", "impacto": "Médio",
             "classificacao": "Moderado", "solucao": "Monitorar e mitigar"}
            for r in all_riscos[:5]
        ] if all_riscos else [
            {"id": "01", "descricao": "Erros durante o Go-Live", "probabilidade": "Baixa",
             "impacto": "Gravíssimo", "classificacao": "Extremo",
             "solucao": "Recuperação do backup antes da solução"},
        ]

        # ── Comercial ──
        valor = comercial.get("valor_referencia", 0)
        tarifa = comercial.get("tarifa_hora", 230)
        if not valor and total_horas:
            valor = round(total_horas * tarifa)

        # ── Título ──
        titulo = plan.get("titulo_proposta", "")
        if not titulo:
            rfp_curto = (self.p.rfp_text or "Proposta SAP")[:60]
            ufs_str = ", ".join(self.p.states) if self.p.states else ""
            titulo = f"DAM — {rfp_curto} ({ufs_str})" if ufs_str else f"DAM — {rfp_curto}"

        ver_label = {
            "ecc604": "ECC ≤ 6.04", "ecc605": "ECC 6.05+",
            "s4op": "S/4HANA On-premise", "s4cloud": "S/4HANA Cloud"
        }.get(self.p.sap_version, self.p.sap_version)

        # ── Montar DAM ──
        dam = {
            "titulo": titulo,
            "cliente": getattr(self.p, 'client_name', '') or '',
            "tipo_projeto": self.p.project_type,
            "versao_sap": ver_label,
            "ufs": self.p.states,
            "necessidade": self.p.rfp_text or "Adequação conforme demanda do cliente.",
            "entregaveis": all_entregaveis,
            "premissas": all_premissas,
            "equipe": recursos,
            "total_horas": total_horas,
            "impactos": impactos,
            "transacoes_sap": list(set(all_transacoes)),
            "alertas": list(set(all_alertas)),
            "plano": {
                "needs_cpi": plan.get("needs_cpi", False),
                "main_proc": plan.get("main_proc", "SD"),
                "modules": plan.get("modules", []),
                "complexity": plan.get("complexity", "media"),
                "needs_abap": "ABAP" in plan.get("modules", []),
            },
            "reforma": results.get("REFORMA", {"decisao": "monitorar"}),
            "fiscal": {
                "legislacao": list(set(all_legislacao)),
                "estadual": results.get("FISCAL_ESTADUAL", {}),
                "federal": results.get("FISCAL_FEDERAL", {}),
                "municipal": results.get("FISCAL_MUNICIPAL", {}),
            },
            "comercial": {
                "valor_referencia": valor,
                "tarifa_hora": tarifa,
                "faturamento": comercial.get("faturamento", "50% aprovação + 50% Go-Live"),
                "garantia": comercial.get("garantia", "30 dias corridos"),
                "validade": comercial.get("validade", "30 dias"),
            },
            "drc": results.get("DRC", {}),
        }

        # ── Confidence scores baseados na qualidade dos resultados ──
        n_agents = len([v for v in results.values() if isinstance(v, dict) and v.get("entregaveis")])
        rfp_len = len(self.p.rfp_text or "")
        confidence = {
            "escopo": min(0.95, 0.60 + (rfp_len / 500) * 0.20 + (n_agents / 10) * 0.15),
            "horas": min(0.92, 0.70 + (n_agents / 10) * 0.22),
            "legislacao": 0.91 if all_legislacao else 0.72,
            "comercial": 0.95,
        }

        return {
            "main_proc": plan.get("main_proc", "SD"),
            "total_hours": total_horas,
            "wp_resources": recursos,
            "confidence": confidence,
            "agents_fired": agents,
            "dam": dam,
        }
