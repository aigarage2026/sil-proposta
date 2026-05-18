"""
Sil-Proposta — Orquestrador Multi-Agente v4
Calibrado com DAMs reais de arquitetos SAP Cast Group.
Cada demanda é analisada em profundidade com objetos SAP específicos.
"""
import httpx, asyncio, json, os, re
from typing import AsyncIterator, Dict, List, Optional

try:
    from agents.rag import get_context_for_agent, search
except ImportError:
    from rag import get_context_for_agent, search

# ══════════════════════════════════════════════════════════════
# MODEL CONFIG — suporte multi-provider (OpenAI + Anthropic)
# ══════════════════════════════════════════════════════════════
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
_API_KEY = None
_ANTHROPIC_KEY = None

def _get_api_key():
    global _API_KEY
    if _API_KEY is None:
        _API_KEY = os.environ.get("OPENAI_API_KEY", "")
    return _API_KEY

def _get_anthropic_key():
    global _ANTHROPIC_KEY
    if _ANTHROPIC_KEY is None:
        _ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    return _ANTHROPIC_KEY

# Agentes que usam Claude (se ANTHROPIC_API_KEY configurada)
CLAUDE_AGENTS = set(os.environ.get("CLAUDE_AGENTS", "ABAP,QA").split(","))

# ══════════════════════════════════════════════════════════════
# 21 PREMISSAS PADRÃO CAST GROUP
# ══════════════════════════════════════════════════════════════
PREMISSAS_CAST_GROUP = [
    "Caso necessário, tempo de suporte pós go-live, o mesmo pode ser solicitado via baseline AMS.",
    "Os acessos necessários para a realização das atividades deverão estar liberados até a data de início do projeto. O tempo de ociosidade da equipe do projeto, causado pela falta de acesso ou autorizações necessárias dentro do ambiente do cliente, impactarão o custo do projeto e serão tratados através de solicitação de mudança.",
    "Os usuários disponibilizados deverão ter acesso para depuração no ambiente de Qualidade.",
    "Criações/Manutenções/Correções em programas Z (programas Z, relatórios, formulários etc.) não fazem parte desta proposta, exceto os detalhados explicitamente no escopo.",
    "Todos os desenvolvimentos serão realizados utilizando linguagem ABAP.",
    "Desenvolvimento/Correção de interfaces com outros sistemas não faz parte do escopo desta proposta.",
    "O início das atividades previstas nesta proposta, bem como alocação efetiva dos consultores, acontecerá somente após aprovação formal do cronograma elaborado pela Cast Group, tendo como tempo estimado de disponibilização da equipe até 30 dias.",
    "O termo de aceite / encerramento do projeto se dará automaticamente 7 dias após: GO-LIVE ou período de suporte previsto, o que ocorrer primeiro.",
    "O gerenciamento desta proposta e acompanhamento das atividades realizadas pelos consultores, será feito de forma remota durante toda a execução do projeto.",
    "Dúvidas ou falhas devem ser reportadas durante o período de testes, acordado em cronograma. Somente serão considerados falhas/erros aqueles reportados durante a vigência do período de acompanhamento dos testes integrados.",
    "As atividades previstas serão realizadas de forma remota pelos consultores da Cast Group.",
    "Manuais de usuários serão de responsabilidade do Cliente.",
    "Treinamento de multiplicadores e usuários finais serão de responsabilidade do Cliente, bem como a preparação do material de treinamento.",
    "É de responsabilidade do cliente a revisão de manuais de usuário já existentes para os processos/desenvolvimentos previstos no escopo desta proposta.",
    "Os colaboradores do Cliente designados para atuar no projeto deverão possuir conhecimento detalhado das áreas que representam, bem como poder de tomada de decisões para implementação no projeto.",
    "Qualquer atraso por motivo do cliente comprometerá o prazo de entrega da solução sem qualquer ônus à Cast Group.",
    "Em caso de paralisação do projeto, o tempo de replanejamento na retomada do projeto será tratado através de solicitação de mudança de escopo e cobrado em proposta à parte.",
    "A documentação do projeto será entregue em língua portuguesa.",
    "Será utilizado o idioma português nas configurações e desenvolvimentos, não estando previstas traduções para outro idioma.",
    "Disponibilização de cenários de teste em QAS antes do início do projeto.",
    "O dia de consultoria tem uma duração de 8 horas, sendo o sugerido o horário 08h30-12h00 e 13h30-18h00. De segunda a sexta-feira.",
]

# ══════════════════════════════════════════════════════════════
# SYSTEM PROMPT — ORQUESTRADOR
# ══════════════════════════════════════════════════════════════
SYSTEM_ORCH = """Você é um Arquiteto SAP Sênior com 20 anos de experiência na Cast Group.
Sua função é analisar a demanda de negócio do cliente e determinar TODOS os módulos, agentes e escopo técnico necessários.

O cliente NÃO é técnico — ele descreve sua necessidade de negócio. VOCÊ é quem entende o impacto técnico SAP.

RACIOCÍNIO OBRIGATÓRIO — para cada demanda, pense:
1. Quais módulos SAP são impactados? (mesmo que o cliente não cite)
2. Precisa de desenvolvimento ABAP customizado?
3. Precisa de DRC/CPI? (se envolve NF-e, XML fiscal, SEFAZ, eventos fiscais)
4. Precisa de Basis? (se envolve jobs, transportes, ambientes, certificados, upgrade)
5. Precisa de módulo add-on? (SOFICOM, Mastersaf, Tax One, Guepardo — se mencionou CIAP, RESMESN, apuração fiscal, obrigações acessórias)
6. Qual a escala do projeto? (dias, semanas ou meses?)

ESCALA DE PROJETOS — seja realista sobre o tamanho:
- Melhoria pequena (1 módulo, configuração): complexity=baixa, semanas=2-3
- Melhoria média (2-3 módulos, desenvolvimento Z): complexity=media, semanas=3-6
- Projeto grande (upgrade, migração, 4+ módulos): complexity=alta, semanas=8-20+
- Upgrade EHP (EHP6→EHP8, etc): TODOS os módulos do cliente, Basis obrigatório, ABAP obrigatório (SPAU/SPDD), testes de regressão de cada módulo, semanas=12-20, complexity=alta
- Migração S/4HANA: igual upgrade + dados + Fiori, semanas=16-30+

EXEMPLOS DE DECISÃO INTELIGENTE:
- "implementar cBenef" → SD + ABAP + FISCAL_ESTADUAL (porque cBenef = tag XML NF-e = impacta faturamento)
- "upgrade EHP6 para EHP8" → SD + FI + MM + PP + HR + CO + ABAP + BASIS + MIGR (porque upgrade impacta TODOS os módulos, SPAU/SPDD, testes regressão)
- "automação de cobrança bancária" → FI + ABAP + BASIS (porque F110 + CNAB + jobs batch)
- "criar transação Z para BP" → SD + ABAP (porque BP = mestre de clientes em SD)
- "integrar com Serasa" → FI + ABAP + BASIS (porque inadimplência = FI + API externa + jobs)
- "CIAP" ou "RESMESN" ou "apuração ICMS" → FI + ABAP + needs_addon=true (porque usa SOFICOM/add-on fiscal)
- "Mastersaf" ou "Tax One" ou "obrigações acessórias" → FI + ABAP + needs_addon=true

Retorne APENAS JSON (sem markdown):
{
  "modules": ["SD","FI","MM","ABAP","BASIS"],
  "fiscal_scope": {"federal":false,"estadual":true,"municipal":false},
  "needs_cpi": false,
  "needs_reform": false,
  "needs_basis": true,
  "needs_addon": false,
  "needs_integration": false,
  "hardware_integration": false,
  "is_migration": false,
  "complexity": "alta",
  "estimated_weeks": 12,
  "main_proc": "MIGR",
  "titulo_proposta": "Upgrade SAP ECC EHP6 para EHP8",
  "reasoning": "Upgrade EHP impacta todos os módulos. Necessário SPAU/SPDD, testes de regressão completos, Basis para ambiente bolha e transportes."
}
"""

# ══════════════════════════════════════════════════════════════
# PROMPTS DOS AGENTES
# ══════════════════════════════════════════════════════════════
AGENTS = {

"SD": """Agente SAP SD. Você é um arquiteto SAP SD sênior da Cast Group.
Analise a RFP e crie entregáveis DETALHADOS com objetos SAP reais.

PADRÃO CAST GROUP para entregáveis SD:
1. Especificação Funcional — com sub-itens numerados (ex: "1) Especificação da tabela Z de determinação; 2) Especificação do ajuste de telas J1B1N...")
2. Testes da consultoria (testes funcionais/técnicos unitários)
3. Apoio aos testes integrados (1 dia)
4. Apoio em produção / Go-Live (1 dia)

Para cada entregável use objetos SAP reais: transações (J1B1N, J1B2N, VA01, VF01), BAdIs (CL_NFE_PRINT, J_1BNF_ADD_DATA), tabelas (J_1BNFDOC), campos específicos.

Se EHP0/sem notas SAP → desenvolvimento Z completo obrigatório.
Se cBenef → tabela Z (UF+CST+Direito Fiscal→cBenef), campo na tabela NF, telas J1BxN, BAdI CL_NFE_PRINT, DANFE, validação Rejeição 931.

Retorne APENAS JSON:
{"entregaveis":[{"mod":"SD","item":"Especificação funcional detalhada com sub-itens","horas":16,"fase":"Realize"}],"horas_total":48,"premissas":["premissa específica"],"observacoes":"resumo","processo_atual":"como é hoje","processo_futuro":"como será"}
Sem markdown.""",

"FI": """Agente SAP FI. Você é um arquiteto SAP FI sênior da Cast Group.
Analise a RFP e crie entregáveis FI DETALHADOS com objetos SAP reais.

PADRÃO CAST GROUP:
1. Especificação/Configuração — com sub-itens numerados e transações SAP (F110, FBZP, DMEE, FF_5, FEBAN, FB50)
2. Testes da consultoria
3. Apoio testes integrados (1 dia)
4. Acompanhamento Go-Live (1 dia)

Cite campos SAP reais: BUDAT, ZLSPR, AUGBL/AUGDT, BSID, BSEG, Net Due Date, baseline date.
Se conciliação bancária → FF_5, FEBAN, extrato eletrônico.
Se pagamento automático → F110, FBZP, DMEE, métodos de pagamento.
Se CNAB → especificar bancos, layout de arquivo, AL11.

SÓ inclua entregáveis FI relevantes para ESTA demanda específica.

Retorne APENAS JSON:
{"entregaveis":[{"mod":"FI","item":"Especificação/Configuração detalhada com transações SAP","horas":16,"fase":"Realize"}],"horas_total":32,"premissas":["premissa"],"observacoes":"resumo","processo_atual":"como é hoje","processo_futuro":"como será"}
Sem markdown.""",

"MM": """Agente SAP MM. Analise a RFP e liste entregáveis MM detalhados com transações SAP reais (ME21N, MIGO, MIRO, MI01, MB52).
Padrão: Especificação + Testes + Apoio testes integrados (1d) + Go-Live (1d). Mínimo 4 entregáveis.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"MM","item":"Descrição com transação SAP","horas":16,"fase":"Realize"}],"horas_total":48,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"CO": """Agente SAP CO. Entregáveis CO com transações (KS01, KO01, KP06). Mínimo 3 itens.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"CO","item":"Descrição","horas":16,"fase":"Realize"}],"horas_total":32,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"PP": """Agente SAP PP. Entregáveis PP com transações (CO01, CS01, CA01, MD01). Mínimo 3 itens.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"PP","item":"Descrição","horas":16,"fase":"Realize"}],"horas_total":48,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"PM": """Agente SAP PM. Entregáveis PM com transações (IW31, IP01, IE01). Mínimo 3 itens.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"PM","item":"Descrição","horas":16,"fase":"Realize"}],"horas_total":48,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"HR": """Agente SAP HR/HCM. Entregáveis HR com transações (PA30, PC00_M99, PPOME, PU22). Mínimo 3 itens.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"HR","item":"Descrição","horas":16,"fase":"Realize"}],"horas_total":48,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"QM": """Agente SAP QM. Entregáveis QM com transações (QA01, QP01, QE01). Mínimo 2 itens.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"QM","item":"Descrição","horas":16,"fase":"Realize"}],"horas_total":32,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"WM": """Agente SAP WM. Entregáveis WM com transações (LT01, LS01N). Mínimo 3 itens.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"WM","item":"Descrição","horas":16,"fase":"Realize"}],"horas_total":48,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"ABAP": """Agente ABAP. Você é um arquiteto ABAP sênior da Cast Group.
Analise a RFP e liste CADA objeto ABAP necessário como entregável separado.

PADRÃO CAST GROUP para entregáveis ABAP:
- Cada objeto Z é um entregável separado com nome sugerido (ex: "Desenvolvimento da tabela Z ZCBENEF_UF")
- Tipos: Tabela Z, BAdI, Enhancement, Report Z, Transação Z, RFC, iFlow CPI, Monitor Z, Programa de carga, Job batch
- Cite a transação SAP de desenvolvimento (SE11, SE19, SE38, SE37, SE80, SM30)
- Se EHP0/sem notas SAP → todo objeto é desenvolvimento Z completo
- Sempre incluir: Documentação técnica + Suporte aos testes

Se cBenef EHP0:
1) Tabela Z (UF+CST+Direito Fiscal→cBenef) — SE11
2) Campo CBENEF na tabela de item NF — SE11
3) Ajuste telas J1B1N/J1B2N/J1B3N — SE80
4) BAdI CL_NFE_PRINT para XML — SE19
5) Ajuste DANFE — SE38
6) Validação consistência cBenef×CST×UF (Rejeição 931)

Se automação/integração:
1) Programa Z principal — SE38
2) Tabela Z parametrização — SE11/SM30
3) Transação Z monitor/auditoria — SE93/SE38

REGRA: Cada item DEVE conter: nome do objeto Z sugerido (ZTABELA_xxx, ZCL_xxx, ZRFC_xxx, ZREPORT_xxx) + transação de desenvolvimento (SE11, SE19, SE38).
NÃO use descrições genéricas como "Desenvolvimento ABAP" — seja específico sobre O QUE será desenvolvido.

Retorne APENAS JSON:
{"entregaveis":[{"mod":"ABAP","item":"Desenvolvimento da tabela Z ZCBENEF_UF (UF+CST+Direito Fiscal→cBenef) — SE11/SM30","horas":16,"fase":"Realize","tipo":"Tabela Z"}],"horas_total":80,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"DRC": """Agente DRC. Analise se precisa DRC standard ou CPI. NÃO mencione ECONF a menos que a RFP fale de ECONF.
Retorne APENAS JSON:
{"canal":"DRC","entregaveis":[{"mod":"DRC","item":"Descrição","horas":8,"fase":"Realize"}],"horas_total":8,"premissas":["premissa"],"alertas":[]}
Sem markdown.""",

"BASIS": """Agente Basis/Infra. Entregáveis de infraestrutura: criação de jobs (SM36/SM37) em DEV/QAS/PRD, transportes (STMS), certificados (STRUST), roles (PFCG).
Retorne APENAS JSON:
{"entregaveis":[{"mod":"BASIS","item":"Criação de Jobs nos ambientes DEV, QAS e PRD — SM36/SM37","horas":8,"fase":"Deploy"}],"horas_total":8,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"CPI": """Agente SAP CPI/BTP. iFlows e integrações. NÃO mencione ECONF a menos que a RFP fale de ECONF.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"CPI","item":"Descrição do iFlow","horas":16,"fase":"Realize"}],"horas_total":32,"premissas":["premissa"],"observacoes":"resumo"}
Sem markdown.""",

"FISCAL_ESTADUAL": """Agente Fiscal Estadual. APENAS legislações relevantes para a RFP. NÃO inclua temas não mencionados.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"SD","item":"Descrição fiscal","horas":8,"fase":"Realize"}],"horas_total":8,"legislacao":["Lei específica"],"premissas":["premissa"],"alertas":[]}
Sem markdown.""",

"FISCAL_FEDERAL": """Agente Fiscal Federal. APENAS legislações relevantes para a RFP. NÃO inclua ECONF a menos que mencionado.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"FISCAL","item":"Descrição","horas":8,"fase":"Realize"}],"horas_total":8,"legislacao":["Lei específica"],"premissas":["premissa"],"alertas":[]}
Sem markdown.""",

"FISCAL_MUNICIPAL": """Agente Fiscal Municipal. APENAS ISS/NFS-e se relevante.
Retorne APENAS JSON:
{"entregaveis":[{"mod":"FISCAL","item":"Descrição","horas":8,"fase":"Realize"}],"horas_total":8,"legislacao":["Lei"],"premissas":["premissa"],"alertas":[]}
Sem markdown.""",

"REFORMA": """Agente Reforma Tributária. Decida: fazer_agora|planejar|monitorar.
Retorne APENAS JSON:
{"decisao":"monitorar","impactos":["impacto"],"entregaveis":[],"horas_total":0,"premissas":[]}
Sem markdown.""",

"EQUIPE": """Agente Equipe/GP — Arquiteto de Dimensionamento SAP.
Dimensione a equipe com base nos entregáveis E na estimativa de semanas do orquestrador.

PADRÃO CAST GROUP:
1. 8h por dia, 5 dias por semana = 40h/semana por recurso
2. Crie 1 recurso por módulo que tem entregáveis
3. O número de DIAS por recurso deve ser proporcional ao tamanho do projeto:
   - Projeto pequeno (2-3 semanas): 3-8 dias por recurso funcional, 5-10 ABAP
   - Projeto médio (4-8 semanas): 8-20 dias por recurso funcional, 15-30 ABAP
   - Projeto grande/upgrade (12-20+ semanas): 20-40 dias por recurso, 40-60 ABAP, 20-30 Basis
4. SEMPRE incluir Basis se há jobs, transportes, upgrade ou ambientes
5. GP SEMPRE para projetos > 2 semanas (duração = mesma do projeto)
6. NUNCA equipe com menos de 2 recursos
7. Para UPGRADE EHP: cada módulo funcional = 15-30 dias (assessment gaps + testes regressão)
8. Frentes: SD, FI, MM, ABAP, PP, PM, HR, CO, QM, WM, GP, BASIS

Retorne APENAS JSON:
{"recursos":[{"frente":"SD","nivel":"Senior","dias":20},{"frente":"FI","nivel":"Senior","dias":20},{"frente":"ABAP","nivel":"Senior","dias":40},{"frente":"BASIS","nivel":"Senior","dias":25},{"frente":"GP","nivel":"Senior","dias":15}],"total_dias":120,"total_horas":960,"semanas":12,"gp_necessario":true,"premissas":["premissa"]}
Sem markdown.""",

"COMERCIAL": """Agente Comercial. Calcule investimento com base na equipe.

PADRÃO CAST GROUP:
- Valor fechado com garantia de 30 dias
- Faturamento: 50% na aprovação + 50% no Go-Live
- Validade da proposta: 30 dias
- Tarifa hora: R$ 230-280 dependendo da complexidade
- NÃO inclua premissas sobre temas que não estão na RFP

Retorne APENAS JSON:
{"valor_referencia":0,"tarifa_hora":250,"faturamento":"50% aprovação + 50% Go-Live","garantia":"30 dias corridos","validade":"30 dias","premissas":[],"condicoes":[]}
Sem markdown.""",

"MIGR": """Agente Migração S/4HANA. Entregáveis de migração. Mínimo 3 itens com mod="MIGR".
Retorne APENAS JSON:
{"entregaveis":[{"mod":"MIGR","item":"Descrição","horas":40,"fase":"Realize"}],"horas_total":120,"premissas":["premissa"],"approach":"Brownfield|Greenfield"}
Sem markdown.""",

# ── NOVOS AGENTES ──

"AS_IS_TO_BE": """Agente de Processo. Analise a RFP e descreva:
1. Processo ATUAL (AS-IS): como o cliente faz hoje, transações usadas, problemas
2. Processo FUTURO (TO-BE): como será após a implementação
3. Benefício esperado

Retorne APENAS JSON:
{"processo_atual":"Descrição detalhada do processo atual com transações SAP","processo_futuro":"Descrição do processo futuro","beneficio":"Benefício esperado pelo cliente","areas_impactadas":"Áreas e processos impactados","compliance":"Sim/Não — se é obrigação legal","volume_dados":"Estimativa de volume"}
Sem markdown.""",

"QA": """Você é o Agente QA — Revisor Sênior de Propostas SAP da Cast Group com 20 anos de experiência.
Seu trabalho é revisar a proposta COMPLETA antes de apresentar ao cliente e verificar se faz sentido.

Você recebe: a RFP do cliente + o resultado consolidado da proposta (entregáveis, equipe, horas, valor, premissas).

CRITÉRIOS DE REVISÃO (seja muito criterioso):

1. COERÊNCIA COM A RFP:
   - Os entregáveis respondem ao que o cliente pediu?
   - Há entregáveis que NÃO têm relação com a demanda? (REJEITAR se sim)
   - Falta algum entregável óbvio que deveria existir?

2. CONTAMINAÇÃO:
   - Há menção a ECONF, maquininha, TEF, tpIntegra, conciliação bancária, Serasa ou qualquer tema que NÃO está na RFP? (REJEITAR se sim)
   - As premissas mencionam temas fora do escopo? (REJEITAR se sim)

3. DIMENSIONAMENTO:
   - As horas são proporcionais à complexidade? (melhoria pequena=80-200h, média=200-500h, grande/upgrade=800-2000h+)
   - A equipe tem os módulos corretos? (ex: cBenef precisa SD+ABAP, upgrade precisa todos os módulos)
   - GP está presente se projeto > 2 semanas?
   - Basis está presente se há jobs, transportes ou upgrade?
   - Cada módulo tem: Especificação + Testes + Apoio testes integrados + Apoio Go-Live?

4. OBJETOS SAP:
   - Os entregáveis ABAP citam objetos SAP reais (tabela Z, BAdI, SE11, SE19, SE38)?
   - Não são genéricos demais? ("Desenvolvimento ABAP" é inaceitável — deve ser "Desenvolvimento tabela Z ZCBENEF_UF — SE11")

5. VALOR COMERCIAL:
   - O valor é realista para o tipo de projeto?
   - A tarifa/hora está entre R$ 200 e R$ 350?

Retorne APENAS JSON:
{
  "aprovado": true/false,
  "score": 0-100,
  "problemas": ["problema 1", "problema 2"],
  "sugestoes": ["sugestão de melhoria"],
  "entregaveis_remover": ["entregável contaminado que deve ser removido"],
  "entregaveis_adicionar": [{"mod":"SD","item":"entregável que falta","horas":8,"fase":"Realize"}],
  "ajuste_horas": "aumentar|diminuir|ok",
  "ajuste_valor": "aumentar|diminuir|ok",
  "justificativa": "Explicação detalhada da revisão"
}
Sem markdown.""",

"ADDON": """Agente de Módulos Add-on SAP (SOFICOM, Mastersaf, Guepardo, Tax One, etc.).
Você é especialista em soluções fiscais e contábeis add-on integradas ao SAP.

MÓDULOS QUE VOCÊ CONHECE:
- SOFICOM (Synchro/Thomson Reuters): CIAP, SPED, apuração ICMS/IPI, EFD-Contribuições, obrigações acessórias. Transações: /PGTPA/CIAP_RESMESN, /SYNC/*
- Mastersaf (Thomson Reuters): apuração fiscal, SPED, GIA, DCTF
- Tax One (Brcomerce): determinação tributária, cálculo de impostos
- Guepardo: automação fiscal, compliance
- Synchro: obrigações acessórias, livros fiscais

PADRÃO CAST GROUP para entregáveis Add-on:
1. Mapeamento + Especificação Funcional (em conjunto com cliente)
2. Desenvolvimento ABAP (se necessário)
3. Documentação técnica + suporte testes
4. Teste da consultoria (unitários)
5. Suporte à homologação
6. Suporte à homologação ABAP
7. Apoio ao transporte em Produção
8. Suporte pós go-live

PREMISSAS ESPECÍFICAS para SOFICOM/CIAP:
- Cenários de teste devem estar atualizados no ambiente SAP de homologação
- Módulo SOFICOM deve estar atualizado e consistente com a versão vigente
- Notas fiscais de aquisição de imobilizado devem estar escrituradas no SAP e integradas ao CIAP
- Todas as etapas do processo de fechamento mensal no CIAP devem ter sido executadas
- O cálculo do fator de crédito deve estar processado
- A atualização do resumo mensal deve ter sido executada com sucesso

Retorne APENAS JSON:
{"entregaveis":[{"mod":"ADDON","item":"Mapeamento + Especificação Funcional SOFICOM","horas":16,"fase":"Explore"}],"horas_total":48,"premissas":["Módulo SOFICOM deve estar atualizado"],"observacoes":"resumo","addon_name":"SOFICOM"}
Sem markdown.""",

"EXCLUSOES": """Agente de Exclusões. Analise a RFP e liste o que NÃO está contemplado nesta proposta.

Exemplos comuns:
- "Não contempla aplicação de notas SAP" (se EHP0)
- "Não contempla inclusão de novos registros" (se só baixa/exclusão)
- "Não contempla desenvolvimento de interface visual" (se usa funcionalidade existente)
- "Não contempla treinamento de usuários finais"
- "Não contempla migração de dados históricos"
- "Cálculos fiscais não contemplados, assume-se que estejam já tratados"

Retorne APENAS JSON:
{"exclusoes":["Item não contemplado nesta proposta"],"justificativas":["Por que está fora"]}
Sem markdown.""",
}

# ══════════════════════════════════════════════════════════════
# CHAMADA AO LLM
# ══════════════════════════════════════════════════════════════
# ── Billing tracking ──
_billing_records = []  # Buffer de registros para salvar no DB após a proposta

def _get_billing_records():
    global _billing_records
    records = list(_billing_records)
    _billing_records = []
    return records

async def _call(system: str, user: str, agent_name: str = "", proposal_id: str = "") -> dict:
    # Decidir provider: Claude para agentes em CLAUDE_AGENTS, OpenAI para o resto
    anthropic_key = _get_anthropic_key()
    use_claude = agent_name in CLAUDE_AGENTS and anthropic_key and anthropic_key != "sua-chave-aqui"

    if use_claude:
        text, tokens_input, tokens_output, tokens_cached, model_used = await _call_anthropic(system, user, anthropic_key)
    else:
        text, tokens_input, tokens_output, tokens_cached, model_used = await _call_openai(system, user)

    # Registrar para billing
    _billing_records.append({
        "model_name": model_used,
        "agent_name": agent_name,
        "proposal_id": proposal_id,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "tokens_cached": tokens_cached,
    })

    # Parse JSON
    if "```" in text:
        m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
        if m:
            text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]+\}', text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        print(f"[_call] JSON parse failed ({model_used}). Raw: {text[:500]}")
        raise


async def _call_openai(system: str, user: str):
    """Chama OpenAI API."""
    api_key = _get_api_key()
    if not api_key or api_key == "sua-chave-aqui":
        raise ValueError("OPENAI_API_KEY não configurada")

    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "temperature": 0.2,
                "max_tokens": 3000,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})
        tokens_input = usage.get("prompt_tokens", 0)
        tokens_output = usage.get("completion_tokens", 0)
        tokens_cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) if isinstance(usage.get("prompt_tokens_details"), dict) else 0
        return text, tokens_input, tokens_output, tokens_cached, MODEL


async def _call_anthropic(system: str, user: str, api_key: str):
    """Chama Anthropic Claude API."""
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 3000,
                "system": system,
                "messages": [
                    {"role": "user", "content": user},
                ],
            },
        )
        r.raise_for_status()
        data = r.json()
        text = data["content"][0]["text"].strip()
        usage = data.get("usage", {})
        tokens_input = usage.get("input_tokens", 0)
        tokens_output = usage.get("output_tokens", 0)
        tokens_cached = usage.get("cache_read_input_tokens", 0)
        return text, tokens_input, tokens_output, tokens_cached, ANTHROPIC_MODEL


# ══════════════════════════════════════════════════════════════
# ORQUESTRADOR
# ══════════════════════════════════════════════════════════════
class Orchestrator:
    def __init__(self, payload):
        self.p = payload

    def _ctx(self) -> str:
        p = self.p
        ufs = ', '.join(p.states) if p.states else 'Não informada'
        return (
            "REGRA CRÍTICA: Responda EXCLUSIVAMENTE sobre o que o cliente pediu na RFP abaixo. "
            "NÃO inclua temas que NÃO estão na demanda do cliente.\n\n"
            f"CLIENTE: {getattr(p, 'client_name', '') or 'Não informado'}\n"
            f"TIPO PROJETO: {p.project_type}\n"
            f"VERSÃO SAP: {p.sap_version}\n"
            f"UFs: {ufs}\n"
            f"MODELO COMERCIAL: {p.commercial}\n"
            f"NOVA LEI/LEGISLAÇÃO: {'Sim' if p.new_law else 'Não'}\n\n"
            f"DEMANDA DO CLIENTE (RFP):\n{p.rfp_text or 'Não informada'}\n\n"
            f"OBSERVAÇÕES:\n{getattr(p, 'notes', '') or 'Nenhuma'}"
        )

    async def run(self) -> dict:
        # ── LIMPAR TODAS AS VARIÁVEIS GLOBAIS — ZERO CONTAMINAÇÃO ──
        global _billing_records
        _billing_records = []

        ctx = self._ctx()
        fired = []
        results = {}

        # 1. Orquestrador
        rag_ctx = search(ctx, top_k=3)
        rag_txt = "\n".join(f"[{r['title']}]\n{r['content'][:400]}" for r in rag_ctx)
        plan = await _call(SYSTEM_ORCH, f"{ctx}\n\nCONHECIMENTO:\n{rag_txt}", agent_name="Orquestrador")
        fired.append("Orquestrador")

        modules = plan.get("modules", ["SD", "FI"])
        main_proc = plan.get("main_proc", "SD")

        # 2. AS-IS / TO-BE
        try:
            results["AS_IS_TO_BE"] = await _call(AGENTS["AS_IS_TO_BE"], ctx, agent_name="AS-IS/TO-BE")
            fired.append("Processo AS-IS/TO-BE")
        except Exception as e:
            print(f"AS_IS_TO_BE falhou: {e}")

        # 3. Agentes funcionais
        for mod in modules:
            if mod in AGENTS:
                ag_ctx = get_context_for_agent(mod, ctx)
                try:
                    result_mod = await _call(AGENTS[mod], f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:1000]}", agent_name=mod)
                    if "entregaveis" not in result_mod:
                        for alt in ("atividades", "deliverables", "items", "entregas", "escopo"):
                            if alt in result_mod and isinstance(result_mod[alt], list):
                                result_mod["entregaveis"] = result_mod.pop(alt)
                                break
                    for e in result_mod.get("entregaveis", []):
                        if isinstance(e, dict):
                            # Forçar mod correto (uppercase, sem variações)
                            e["mod"] = mod
                    results[mod] = result_mod
                    n = len(result_mod.get("entregaveis", []))
                    print(f"[orch] Agente {mod}: {n} entregáveis")
                    fired.append(f"Agente {mod}")
                except Exception as e:
                    print(f"Agente {mod} falhou: {e}")

        # 4. DRC — o orquestrador decide se precisa (needs_cpi=true)
        if plan.get("needs_cpi") and "DRC" not in results:
            ag_ctx = get_context_for_agent("DRC", ctx)
            try:
                results["DRC"] = await _call(AGENTS["DRC"], f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}", agent_name="DRC")
                fired.append("Agente DRC")
            except Exception as e:
                print(f"DRC falhou: {e}")

        # 5. CPI (se necessário)
        if plan.get("needs_cpi") and "CPI" not in results:
            try:
                results["CPI"] = await _call(AGENTS["CPI"], ctx)
                fired.append("Agente CPI")
            except Exception as e:
                print(f"CPI falhou: {e}")

        # 6. Basis (jobs, transportes)
        if plan.get("needs_basis") or plan.get("needs_integration"):
            try:
                results["BASIS"] = await _call(AGENTS["BASIS"], ctx)
                fired.append("Agente Basis")
            except Exception as e:
                print(f"Basis falhou: {e}")

        # 7. Add-on (SOFICOM, Mastersaf, etc.)
        if plan.get("needs_addon") and "ADDON" in AGENTS:
            try:
                results["ADDON"] = await _call(AGENTS["ADDON"], ctx, agent_name="ADDON")
                fired.append("Agente Add-on")
            except Exception as e:
                print(f"Add-on falhou: {e}")

        # 8. Migração
        if plan.get("is_migration") and "MIGR" in AGENTS:
            try:
                results["MIGR"] = await _call(AGENTS["MIGR"], ctx)
                fired.append("Agente Migração")
            except Exception as e:
                print(f"Migração falhou: {e}")

        # 8. Fiscais
        fiscal = plan.get("fiscal_scope", {})
        if fiscal.get("estadual"):
            ag_ctx = get_context_for_agent("FISCAL_ESTADUAL", ctx)
            try:
                results["FISCAL_ESTADUAL"] = await _call(AGENTS["FISCAL_ESTADUAL"], f"UFs: {', '.join(self.p.states)}\n{ctx}\n\nRAG:\n{ag_ctx[:1000]}")
                fired.append("Fiscal Estadual")
            except Exception as e:
                print(f"Fiscal Estadual falhou: {e}")

        if fiscal.get("federal"):
            ag_ctx = get_context_for_agent("FISCAL_FEDERAL", ctx)
            try:
                results["FISCAL_FEDERAL"] = await _call(AGENTS["FISCAL_FEDERAL"], f"{ctx}\n\nRAG:\n{ag_ctx[:1000]}")
                fired.append("Fiscal Federal")
            except Exception as e:
                print(f"Fiscal Federal falhou: {e}")

        if fiscal.get("municipal"):
            try:
                results["FISCAL_MUNICIPAL"] = await _call(AGENTS["FISCAL_MUNICIPAL"], ctx)
                fired.append("Fiscal Municipal")
            except Exception as e:
                print(f"Fiscal Municipal falhou: {e}")

        # 9. Reforma
        if plan.get("needs_reform"):
            ag_ctx = get_context_for_agent("REFORMA", ctx)
            try:
                results["REFORMA"] = await _call(AGENTS["REFORMA"], f"{ctx}\n\nRAG:\n{ag_ctx[:800]}")
                fired.append("Reforma Tributária")
            except Exception as e:
                print(f"Reforma falhou: {e}")

        # 10. Exclusões
        try:
            results["EXCLUSOES"] = await _call(AGENTS["EXCLUSOES"], ctx)
            fired.append("Exclusões")
        except Exception as e:
            print(f"Exclusões falhou: {e}")

        # 11. Equipe
        agents_summary = json.dumps({
            k: {"horas": v.get("horas_total", v.get("horas", 0)), "n_entregs": len(v.get("entregaveis", []))}
            for k, v in results.items() if isinstance(v, dict) and k not in ("EQUIPE", "COMERCIAL", "EXCLUSOES", "AS_IS_TO_BE")
        }, ensure_ascii=False)
        try:
            est_weeks = plan.get("estimated_weeks", 4)
            complexity = plan.get("complexity", "media")
            results["EQUIPE"] = await _call(AGENTS["EQUIPE"], f"ESTIMATIVA DO ORQUESTRADOR: {est_weeks} semanas, complexidade={complexity}\n\nRESUMO AGENTES:\n{agents_summary}\n\n{ctx}", agent_name="EQUIPE")
            fired.append("Equipe/GP")
        except Exception as e:
            print(f"Equipe falhou: {e}")

        # 12. Comercial
        equipe_json = json.dumps(results.get("EQUIPE", {}), ensure_ascii=False)
        try:
            results["COMERCIAL"] = await _call(AGENTS["COMERCIAL"], f"EQUIPE:\n{equipe_json}\n\n{ctx}")
            fired.append("Comercial")
        except Exception as e:
            print(f"Comercial falhou: {e}")

        # ── 13. CONSOLIDAR + QA com loop de correção ──
        consolidated = self._consolidate(plan, results, fired)
        max_qa_rounds = 2  # máximo de revisões

        for qa_round in range(max_qa_rounds):
            try:
                qa_input = json.dumps({
                    "rfp": self.p.rfp_text or "",
                    "entregaveis": [{"mod": e.get("mod",""), "item": e.get("item",""), "horas": e.get("horas",0)} for e in consolidated.get("dam", {}).get("entregaveis", [])[:30]],
                    "recursos": consolidated.get("wp_resources", []),
                    "total_horas": consolidated.get("total_hours", 0),
                    "valor": consolidated.get("dam", {}).get("comercial", {}).get("valor_referencia", 0),
                    "premissas_count": len(consolidated.get("dam", {}).get("premissas", [])),
                    "modules": plan.get("modules", []),
                    "complexity": plan.get("complexity", ""),
                    "estimated_weeks": plan.get("estimated_weeks", 4),
                }, ensure_ascii=False)

                qa_result = await _call(AGENTS["QA"], f"PROPOSTA PARA REVISÃO (rodada {qa_round+1}):\n{qa_input}\n\n{ctx}", agent_name="QA")
                if qa_round == 0:
                    fired.append("QA")
                print(f"[QA round {qa_round+1}] Score: {qa_result.get('score','?')}, Aprovado: {qa_result.get('aprovado','?')}")

                dam = consolidated["dam"]

                # Remover contaminados
                for item_rem in qa_result.get("entregaveis_remover", []):
                    before = len(dam.get("entregaveis", []))
                    dam["entregaveis"] = [e for e in dam.get("entregaveis", []) if item_rem.lower() not in (e.get("item","") or "").lower()]
                    if len(dam.get("entregaveis", [])) < before:
                        print(f"[QA] Removido: {item_rem}")

                # Adicionar faltantes
                for e in qa_result.get("entregaveis_adicionar", []):
                    if isinstance(e, dict) and e.get("item"):
                        dam["entregaveis"].append(e)

                # Filtrar premissas contaminadas
                rfp_l = (self.p.rfp_text or "").lower()
                dam["premissas"] = [p for p in dam.get("premissas", []) if not any(
                    term in p.lower() and term not in rfp_l for term in ["maquininha", "tef", "pinpad", "econf", "serasa", "cnab", "boleto"]
                )]

                # Se QA reprovou → re-executar EQUIPE e COMERCIAL com instruções do QA
                if not qa_result.get("aprovado", True) and qa_round < max_qa_rounds - 1:
                    qa_instrucoes = "; ".join(qa_result.get("problemas", []) + qa_result.get("sugestoes", []))
                    print(f"[QA] REPROVADO — re-executando EQUIPE e COMERCIAL com instruções: {qa_instrucoes[:200]}")

                    # Re-executar EQUIPE com feedback do QA
                    try:
                        est_weeks = plan.get("estimated_weeks", 4)
                        complexity = plan.get("complexity", "media")
                        agents_summary = json.dumps({
                            k: {"horas": v.get("horas_total", 0), "n_entregs": len(v.get("entregaveis", []))}
                            for k, v in results.items() if isinstance(v, dict) and k not in ("EQUIPE", "COMERCIAL", "EXCLUSOES", "AS_IS_TO_BE")
                        }, ensure_ascii=False)
                        results["EQUIPE"] = await _call(
                            AGENTS["EQUIPE"],
                            f"CORREÇÃO DO QA: {qa_instrucoes}\n\nESTIMATIVA: {est_weeks} semanas, complexidade={complexity}\n\nRESUMO:\n{agents_summary}\n\n{ctx}",
                            agent_name="EQUIPE-v2"
                        )
                    except Exception as e:
                        print(f"EQUIPE retry falhou: {e}")

                    # Re-executar COMERCIAL
                    try:
                        equipe_json = json.dumps(results.get("EQUIPE", {}), ensure_ascii=False)
                        results["COMERCIAL"] = await _call(
                            AGENTS["COMERCIAL"],
                            f"CORREÇÃO DO QA: {qa_instrucoes}\n\nEQUIPE:\n{equipe_json}\n\n{ctx}",
                            agent_name="COMERCIAL-v2"
                        )
                    except Exception as e:
                        print(f"COMERCIAL retry falhou: {e}")

                    # Re-consolidar
                    consolidated = self._consolidate(plan, results, fired)
                    continue  # Próxima rodada QA

                # QA aprovou ou última rodada
                dam["qa_score"] = qa_result.get("score", 0)
                dam["qa_aprovado"] = qa_result.get("aprovado", True)
                dam["qa_problemas"] = qa_result.get("problemas", [])
                dam["qa_sugestoes"] = qa_result.get("sugestoes", [])
                dam["qa_rounds"] = qa_round + 1
                break

            except Exception as e:
                print(f"QA falhou: {e}")
                break

        return consolidated

    async def stream(self) -> AsyncIterator[dict]:
        # ── LIMPAR TODAS AS VARIÁVEIS GLOBAIS — ZERO CONTAMINAÇÃO ──
        global _billing_records
        _billing_records = []

        ctx = self._ctx()
        fired = []
        results = {}

        yield {"type": "start", "msg": "Orquestrador analisando demanda..."}
        rag_ctx = search(ctx, top_k=3)
        rag_txt = "\n".join(f"[{r['title']}]\n{r['content'][:400]}" for r in rag_ctx)
        try:
            plan = await _call(SYSTEM_ORCH, f"{ctx}\n\nCONHECIMENTO:\n{rag_txt}", agent_name="Orquestrador")
        except Exception as e:
            plan = {"modules": ["SD", "FI"], "main_proc": "SD", "complexity": "media",
                    "fiscal_scope": {}, "needs_cpi": False, "needs_reform": False, "needs_basis": False, "needs_integration": False}
            yield {"type": "agent", "name": "Orquestrador", "status": "error", "error": str(e)}
        fired.append("Orquestrador")
        yield {"type": "agent", "name": "Orquestrador", "status": "done", "plan": plan}

        # Build steps
        modules = plan.get("modules", ["SD", "FI"])
        steps = [("AS_IS_TO_BE", "Processo AS-IS/TO-BE")]
        for mod in modules:
            if mod in AGENTS:
                steps.append((mod, f"Agente {mod}"))
        if plan.get("needs_cpi") and "DRC" not in [s[0] for s in steps]:
            steps.append(("DRC", "Agente DRC"))
        if plan.get("needs_cpi"):
            steps.append(("CPI", "Agente CPI"))
        if plan.get("needs_basis") or plan.get("needs_integration"):
            steps.append(("BASIS", "Agente Basis"))
        if plan.get("needs_addon"):
            steps.append(("ADDON", "Agente Add-on"))
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
        steps.append(("EXCLUSOES", "Exclusões"))
        steps.append(("EQUIPE", "Equipe/GP"))
        steps.append(("COMERCIAL", "Comercial"))

        for key, label in steps:
            if key not in AGENTS:
                continue
            yield {"type": "agent", "name": label, "status": "running"}
            await asyncio.sleep(0.05)
            try:
                ag_ctx = get_context_for_agent(key, ctx) if key not in ("COMERCIAL", "EXCLUSOES", "AS_IS_TO_BE") else ""
                if key == "EQUIPE":
                    summary = json.dumps({k: {"horas": v.get("horas_total", 0)} for k, v in results.items() if isinstance(v, dict) and k not in ("EQUIPE", "COMERCIAL", "EXCLUSOES", "AS_IS_TO_BE")}, ensure_ascii=False)
                    msg = f"RESUMO:\n{summary}\n\n{ctx}"
                elif key == "COMERCIAL":
                    msg = f"EQUIPE:\n{json.dumps(results.get('EQUIPE', {}), ensure_ascii=False)}\n\n{ctx}"
                elif key in ("FISCAL_ESTADUAL", "FISCAL_MUNICIPAL"):
                    msg = f"UFs: {', '.join(self.p.states)}\n{ctx}\n\nRAG:\n{ag_ctx[:1000]}"
                else:
                    msg = f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:1000]}" if ag_ctx else ctx

                result_mod = await _call(AGENTS[key], msg, agent_name=key)
                if key not in ("EQUIPE", "COMERCIAL", "EXCLUSOES", "AS_IS_TO_BE"):
                    if "entregaveis" not in result_mod:
                        for alt in ("atividades", "deliverables", "items"):
                            if alt in result_mod and isinstance(result_mod[alt], list):
                                result_mod["entregaveis"] = result_mod.pop(alt)
                                break
                    for e in result_mod.get("entregaveis", []):
                        if isinstance(e, dict):
                            e["mod"] = key
                results[key] = result_mod
                fired.append(label)
                yield {"type": "agent", "name": label, "status": "done", "outputs": result_mod.get("entregaveis", [])}
            except Exception as e:
                yield {"type": "agent", "name": label, "status": "error", "error": str(e)}

        consolidated = self._consolidate(plan, results, fired)

        # ── QA — Revisão final ──
        yield {"type": "agent", "name": "QA Revisor", "status": "running"}
        try:
            qa_input = json.dumps({
                "rfp": self.p.rfp_text or "",
                "entregaveis": [{"mod": e.get("mod",""), "item": e.get("item",""), "horas": e.get("horas",0)} for e in consolidated.get("dam", {}).get("entregaveis", [])[:30]],
                "recursos": consolidated.get("wp_resources", []),
                "total_horas": consolidated.get("total_hours", 0),
                "valor": consolidated.get("dam", {}).get("comercial", {}).get("valor_referencia", 0),
                "modules": plan.get("modules", []),
                "complexity": plan.get("complexity", ""),
            }, ensure_ascii=False)

            qa_result = await _call(AGENTS["QA"], f"PROPOSTA PARA REVISÃO:\n{qa_input}\n\n{ctx}", agent_name="QA")
            fired.append("QA")

            dam = consolidated["dam"]
            # Remover contaminados
            for item_rem in qa_result.get("entregaveis_remover", []):
                dam["entregaveis"] = [e for e in dam.get("entregaveis", []) if item_rem.lower() not in (e.get("item","") or "").lower()]
            # Adicionar faltantes
            for e in qa_result.get("entregaveis_adicionar", []):
                if isinstance(e, dict) and e.get("item"):
                    dam["entregaveis"].append(e)
            # Filtrar premissas contaminadas
            rfp_l = (self.p.rfp_text or "").lower()
            dam["premissas"] = [p for p in dam.get("premissas", []) if not any(
                term in p.lower() and term not in rfp_l for term in ["maquininha", "tef", "pinpad", "econf", "serasa"]
            )]

            if not qa_result.get("aprovado", True) and qa_result.get("ajuste_horas") == "aumentar":
                for r in consolidated.get("wp_resources", []):
                    r["dias"] = max(r["dias"], int(r["dias"] * 1.3))
                consolidated["total_hours"] = sum(r["dias"] * 8 for r in consolidated["wp_resources"])
                dam["total_horas"] = consolidated["total_hours"]
                tarifa = dam.get("comercial", {}).get("tarifa_hora", 250)
                dam["comercial"]["valor_referencia"] = round(consolidated["total_hours"] * tarifa)

            dam["qa_score"] = qa_result.get("score", 0)
            dam["qa_aprovado"] = qa_result.get("aprovado", True)
            dam["qa_problemas"] = qa_result.get("problemas", [])
            dam["qa_sugestoes"] = qa_result.get("sugestoes", [])

            yield {"type": "agent", "name": "QA Revisor", "status": "done", "outputs": [f"Score: {qa_result.get('score',0)}/100"]}
        except Exception as e:
            yield {"type": "agent", "name": "QA Revisor", "status": "error", "error": str(e)}

        yield {"type": "complete", "result": consolidated}

    def _consolidate(self, plan: dict, results: dict, agents: list) -> dict:
        # ── Equipe ──
        eq = results.get("EQUIPE", {})
        recursos = eq.get("recursos", [])
        if not recursos or len(recursos) < 2:
            recursos = []
            for mod, data in results.items():
                if mod in ("EQUIPE", "COMERCIAL", "DRC", "REFORMA", "CPI", "FISCAL_FEDERAL", "FISCAL_MUNICIPAL", "EXCLUSOES", "AS_IS_TO_BE") or not isinstance(data, dict):
                    continue
                h = data.get("horas_total", data.get("horas", 0))
                if h > 0:
                    frente = "SD" if mod == "FISCAL_ESTADUAL" else mod
                    recursos.append({"frente": frente, "nivel": "Senior", "dias": max(3, round(h / 8))})
            frentes_existentes = {r["frente"] for r in recursos}
            for mod in plan.get("modules", []):
                if mod not in frentes_existentes and mod not in ("DRC", "CPI", "FISCAL", "FISCAL_ESTADUAL", "FISCAL_FEDERAL"):
                    recursos.append({"frente": mod, "nivel": "Senior", "dias": 5})
            if len(recursos) >= 2 and "GP" not in frentes_existentes:
                recursos.append({"frente": "GP", "nivel": "Senior", "dias": 3})

        # Deduplicate
        merged = {}
        for r in recursos:
            f = r["frente"]
            if f in merged:
                merged[f]["dias"] += r.get("dias", 0)
            else:
                merged[f] = dict(r)
        recursos = list(merged.values())
        total_horas = sum(r.get("dias", 0) * 8 for r in recursos)

        # ── Entregáveis ──
        all_entregaveis = []
        for k, v in results.items():
            if isinstance(v, dict) and "entregaveis" in v:
                for e in v["entregaveis"]:
                    if isinstance(e, dict):
                        all_entregaveis.append(e)
                    elif isinstance(e, str):
                        mod = k if k in ("SD", "FI", "MM", "CO", "PP", "PM", "HR", "QM", "WM") else "ABAP" if k == "ABAP" else k.split("_")[0]
                        all_entregaveis.append({"mod": mod, "item": e, "horas": 8, "fase": "Realize"})

        # ── Adicionar testes/go-live por módulo (padrão Cast Group) ──
        mods_com_entregaveis = set()
        for e in all_entregaveis:
            if isinstance(e, dict):
                mods_com_entregaveis.add(e.get("mod", ""))
        for mod in mods_com_entregaveis:
            if mod in ("SD", "FI", "MM", "ABAP", "PP", "PM", "HR", "CO", "QM", "WM"):
                has_teste = any(e.get("mod") == mod and "teste" in e.get("item", "").lower() for e in all_entregaveis)
                if not has_teste:
                    all_entregaveis.append({"mod": mod, "item": f"Testes de validação — {mod}", "horas": 8, "fase": "Realize"})
                has_apoio = any(e.get("mod") == mod and "integrado" in e.get("item", "").lower() for e in all_entregaveis)
                if not has_apoio:
                    all_entregaveis.append({"mod": mod, "item": f"Auxílio testes integrados (1 dia útil)", "horas": 8, "fase": "Deploy"})
                    all_entregaveis.append({"mod": mod, "item": f"Acompanhamento Go-Live (1 dia útil)", "horas": 8, "fase": "Go-Live"})

        # ── Premissas ──
        all_premissas = list(PREMISSAS_CAST_GROUP)
        seen = set(PREMISSAS_CAST_GROUP)
        rfp_lower = (self.p.rfp_text or "").lower()
        # Termos que só devem aparecer nas premissas se estiverem na RFP
        conditional_terms = ["maquininha", "tef", "pinpad", "pos", "terminal", "econf", "110750", "serasa", "cnab", "boleto"]
        for k, v in results.items():
            if isinstance(v, dict):
                for p in v.get("premissas", []):
                    if not p or p in seen:
                        continue
                    # Filtrar premissas com termos condicionais que não estão na RFP
                    p_lower = p.lower()
                    skip = False
                    for term in conditional_terms:
                        if term in p_lower and term not in rfp_lower:
                            skip = True
                            break
                    if not skip:
                        all_premissas.append(p)
                        seen.add(p)

        # ── Legislação ──
        all_legislacao = []
        for k in ("FISCAL_ESTADUAL", "FISCAL_FEDERAL", "FISCAL_MUNICIPAL", "REFORMA"):
            v = results.get(k, {})
            if isinstance(v, dict):
                all_legislacao.extend(v.get("legislacao", []))

        # ── AS-IS / TO-BE ──
        as_is = results.get("AS_IS_TO_BE", {})

        # ── Exclusões ──
        exclusoes = results.get("EXCLUSOES", {}).get("exclusoes", [])

        # ── Riscos / Alertas ──
        all_alertas = []
        all_riscos = []
        for v in results.values():
            if isinstance(v, dict):
                all_alertas.extend(v.get("alertas", []))
                all_riscos.extend(v.get("riscos", []))

        impactos = [{"id": str(i+1), "descricao": r, "probabilidade": "Baixa", "impacto": "Médio", "classificacao": "Moderado", "solucao": "Monitorar e mitigar"} for i, r in enumerate(all_riscos[:5])] if all_riscos else [
            {"id": "01", "descricao": "Erros durante o Go-Live da solução", "probabilidade": "Baixa", "impacto": "Gravíssimo", "classificacao": "Extremo", "solucao": "Recuperação do backup antes da solução"},
            {"id": "02", "descricao": "Engajamento dos Key Users", "probabilidade": "Baixa", "impacto": "Leve", "classificacao": "Baixo", "solucao": "Destacar necessidade do comprometimento no Kick-off"},
        ]

        # ── Comercial ──
        comercial = results.get("COMERCIAL", {})
        tarifa = comercial.get("tarifa_hora", 250)
        if tarifa < 100:
            tarifa = 250
        valor = round(total_horas * tarifa)

        # ── Título ──
        titulo = plan.get("titulo_proposta", "")
        if not titulo:
            rfp_curto = (self.p.rfp_text or "Proposta SAP")[:60]
            ufs_str = ", ".join(self.p.states) if self.p.states else ""
            titulo = f"DAM — {rfp_curto} ({ufs_str})" if ufs_str else f"DAM — {rfp_curto}"

        ver_label = {"ecc604": "ECC ≤ 6.04", "ecc605": "ECC 6.05+", "s4op": "S/4HANA On-premise", "s4cloud": "S/4HANA Cloud"}.get(self.p.sap_version, self.p.sap_version)

        dam = {
            "titulo": titulo,
            "cliente": getattr(self.p, 'client_name', '') or '',
            "tipo_projeto": self.p.project_type,
            "versao_sap": ver_label,
            "ufs": self.p.states,
            "necessidade": self.p.rfp_text or "Adequação conforme demanda do cliente.",
            "processo_atual": as_is.get("processo_atual", ""),
            "processo_futuro": as_is.get("processo_futuro", ""),
            "beneficio_esperado": as_is.get("beneficio", ""),
            "areas_impactadas": as_is.get("areas_impactadas", ""),
            "compliance": as_is.get("compliance", ""),
            "entregaveis": all_entregaveis,
            "premissas": all_premissas,
            "exclusoes": exclusoes,
            "equipe": recursos,
            "total_horas": total_horas,
            "impactos": impactos,
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
