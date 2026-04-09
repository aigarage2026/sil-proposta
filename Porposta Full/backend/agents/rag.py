"""
Sil-Proposta — Pipeline RAG
Indexação de fontes SAP, fiscais e NT no pgvector (Supabase)
Funciona também em modo local com in-memory store quando sem Supabase
"""
import os, json, hashlib, asyncio
from typing import List, Dict, Optional
from datetime import datetime

# ── Cliente Anthropic para embeddings ──
import anthropic
_client = None

def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client

# ══════════════════════════════════════
# IN-MEMORY STORE (fallback sem Supabase)
# ══════════════════════════════════════
_memory_store: List[Dict] = []

def _embed_text(text: str) -> List[float]:
    """Gera embedding via Claude (simplificado — usa hash como proxy para testes)"""
    # Em produção: usar text-embedding-3-small da OpenAI ou Voyage AI
    # Por ora: vetor hash determinístico para testes sem custo
    import hashlib, struct
    h = hashlib.sha256(text.encode()).digest()
    vec = []
    for i in range(0, min(len(h), 64), 4):
        val = struct.unpack('>f', h[i:i+4])[0]
        if not (val != val):  # nan check
            vec.append(max(-1.0, min(1.0, val / 1e38)))
    while len(vec) < 16:
        vec.append(0.0)
    return vec[:16]

def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x*y for x,y in zip(a,b))
    na  = sum(x*x for x in a) ** .5
    nb  = sum(x*x for x in b) ** .5
    if na == 0 or nb == 0: return 0.0
    return dot / (na * nb)

# ══════════════════════════════════════
# DOCUMENTOS DE CONHECIMENTO BASE
# ══════════════════════════════════════
SAP_KNOWLEDGE_BASE = [
    # ── SAP DRC / GRC ──
    {"id":"drc-econf-001","source":"SAP Community","category":"DRC",
     "title":"ECONF evento 110750 — sem suporte DRC nativo",
     "content":"""O evento ECONF (Evento de Conciliação Financeira, código 110750) da Nota Técnica 2024.002
não possui suporte nativo no SAP Document and Reporting Compliance (DRC) nem no SAP GRC/NFe.
Diferente de eventos como cancelamento, CC-e e Manifestação do Destinatário que foram incorporados
ao standard SAP, o ECONF ainda não tem nota SAP publicada para ECC nem S/4HANA.
A arquitetura correta é: SAP CPI como middleware — o ECC/FI gera o payload via ABAP Z,
o CPI monta o XML conforme NT 2024.002, assina com certificado digital e transmite ao
Web Service SVRS SEFAZ (recepcaoevento4.asmx).
Endpoint SVRS: https://nfe.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx"""},

    {"id":"drc-cbenef-001","source":"SAP Notes","category":"DRC",
     "title":"cBenef — Código de Benefício Fiscal ICMS — BAdI J_1BNF_ADD_DATA",
     "content":"""Para implementar o preenchimento automático do cBenef (Código de Benefício Fiscal ICMS)
no SAP ECC, a solução técnica padrão utiliza a BAdI J_1BNF_ADD_DATA (ou CL_NFE_PRINT em releases
superiores). É necessário criar uma tabela Z de mapeamento CST × UF × cBenef manutenível via SM30,
sem necessidade de ABAP a cada atualização de código.
Premissas críticas: ECC releases menores que 6.05 não têm as notas SAP para cBenef disponíveis,
exigindo desenvolvimento Z completo. Risco de conflito entre BAdIs quando há múltiplas
implementações ativas — verificar no filtro de BAdIs.
Rejeição 930: campo cBenef inválido. Rejeição 931: combinação CST × cBenef × UF inválida."""},

    {"id":"abap-chain-001","source":"Sil-Proposta Rules","category":"ABAP",
     "title":"Cadeia de objetos ABAP — regra de derivação obrigatória",
     "content":"""Regra de derivação ABAP Estrutural do Sil-Proposta:
1. BAPI Z: sempre que o escopo envolver hardware externo (terminal TEF, POS, maquininha,
   PINPAD), uma BAPI Z deve ser o primeiro entregável. Ela recebe os dados do terminal.
   Premissa obrigatória: 'não contempla a extração dos dados da maquininha'.
2. BAdI: mapeia as estruturas de dados (ex: Grupo YA da NF-e, tpIntegra=1).
3. RFC Z: transporta os dados mapeados para o XML da NF-e no momento da geração.
4. iFlow CPI: quando o evento não tem suporte SAP nativo → CPI transmite para SEFAZ.
5. Monitor Z: tela de consulta, reenvio, cancelamento, status SEFAZ, erros/rejeições.
Paralelismo: 4+ desenvolvimentos ABAP independentes → alocar 3 ABAPers em paralelo."""},

    # ── Fiscal Estadual — Goiás ──
    {"id":"go-in1608-001","source":"SEFAZ-GO","category":"Fiscal Estadual",
     "title":"IN 1.608/2025-GSE Goiás — vinculação meios de pagamento NF-e",
     "content":"""Instrução Normativa nº 1.608/2025-GSE (Goiás) regulamenta a vinculação obrigatória
dos meios de pagamento eletrônico nas NF-e emitidas no estado.
Campos obrigatórios: tpIntegra="1" (Pagamento integrado) é obrigatório para indicar que
a transação está tecnologicamente integrada ao sistema emissor da NF-e.
Cenário 1 (pagamento imediato): Grupo YA preenchido no XML da NF-e com IndPag, tpIntegra=1,
CNPJ beneficiário, ID transação, código do terminal.
Cenário 2 (pagamento posterior): Evento ECONF (110750) enviado após a baixa financeira.
Prazo: escalonado por faixa de faturamento. IN 1.623/2026 prorrogou alguns prazos."""},

    {"id":"go-in1608-002","source":"SEFAZ-GO","category":"Fiscal Estadual",
     "title":"ECONF Goiás — campo tpIntegra=1 obrigatório",
     "content":"""Para clientes em Goiás com IN 1.608/2025-GSE, o campo tpIntegra="1" é obrigatório
tanto no Grupo YA da NF-e (Cenário 1) quanto no payload do ECONF (Cenário 2).
Sem este campo, a SEFAZ-GO pode rejeitar o documento ou considerar a operação como
pagamento não integrado, gerando exposição fiscal.
O campo indica que o sistema de pagamento está diretamente integrado ao ERP emissor,
sem intervenção manual na captura dos dados financeiros."""},

    # ── Fiscal Estadual — São Paulo ──
    {"id":"sp-cbenef-001","source":"SEFAZ-SP","category":"Fiscal Estadual",
     "title":"cBenef SP — Portaria SRE nº 70/2025",
     "content":"""A Portaria SRE nº 70/2025 de São Paulo exige o preenchimento do código cBenef
nas NF-e de saída sempre que há benefício fiscal ICMS aplicável.
São Paulo tem 310 códigos cBenef ativos. A tabela oficial é publicada no portal SEFAZ-SP
e deve ser mantida atualizada (cron semanal recomendado).
Campos da tabela Z SAP: CST ICMS, UF destino, código cBenef, vigência inicial, vigência final.
Transações SAP para manutenção: J1B1N (saída), J1B2N (entrada), J1B3N (outros).
Impacto no DANFE: o campo cBenef deve aparecer nos dados complementares.
Rejeição SEFAZ: 930 (campo inválido), 931 (combinação CST×cBenef×UF inválida)."""},

    # ── NT 2024.002 — ECONF ──
    {"id":"nt2024002-001","source":"Portal NF-e","category":"Legislação Federal",
     "title":"NT 2024.002 — Evento ECONF (110750/110751)",
     "content":"""A Nota Técnica 2024.002 versão 1.00 institui o Evento de Conciliação Financeira (ECONF):
- Evento 110750: ECONF — Conciliação Financeira
- Evento 110751: Cancelamento de Conciliação Financeira
O ECONF é enviado pelo emitente da NF-e para informar a transação financeira da operação.
É facultativo na maioria dos estados, mas obrigatório em Goiás (IN 1.608/2025-GSE).
Para NF-e modelo 55: Web Service SVRS (todas as UFs).
URL: https://nfe.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx
cOrgao=92 para eventos nacionais via SVRS.
Campos principais: indPag, tPag, vPag, dPag, CNPJPag, UFPag, tpIntegra."""},

    # ── Reforma Tributária ──
    {"id":"reforma-001","source":"LC 214/2021","category":"Reforma Tributária",
     "title":"LC 214/2021 — IBS/CBS/IS — impacto SAP",
     "content":"""A Lei Complementar 214/2021 (regulamentação da EC 132/2023) institui:
IBS (Imposto sobre Bens e Serviços) — substitui ICMS estadual e ISS municipal
CBS (Contribuição sobre Bens e Serviços) — substitui PIS e COFINS federais
IS (Imposto Seletivo) — incide sobre produtos prejudiciais à saúde e ao meio ambiente
Vigência: transição 2026-2033. Alíquota-teste em 2026 (0,1% CBS + 0,05% IBS).
Split payment obrigatório a partir de 2027: recolhimento na fonte pelo intermediário financeiro.
Impacto SAP: módulos SD (NF-e com novos campos IBS/CBS), FI (contas contábeis separadas),
MM (NF entrada), CO (novos centros de custo), SPED (novos registros).
Lógica Sil-Proposta: go-live pós jul/2026 + escopo SD/FI → fazer agora."""},

    # ── SAP Activate ──
    {"id":"activate-001","source":"SAP Activate","category":"Metodologia",
     "title":"SAP Activate — fases e estimativas de horas",
     "content":"""Metodologia SAP Activate — fases padrão para projetos:
Prepare: aprovação, kick-off, planejamento. 1-2 semanas.
Explore: levantamento de requisitos, especificação funcional, confirmação de escopo. 1-3 semanas.
Realize: desenvolvimento, configuração, testes unitários. Bulk do projeto.
Deploy (Homologação): testes integrados, KT AMS, cutover, go-live. 1-2 semanas.
Go Live: acompanhamento inicial. 3-5 dias.
Suporte pós Go-Live: estabilização. 1-2 semanas.
KT AMS (Knowledge Transfer): obrigatório na fase Deploy. Transferência para time de sustentação.
Horas padrão: 8h/dia, 168h/mês."""},

    # ── Padrão Cast Group ──
    {"id":"cast-dam-001","source":"Cast Group","category":"Padrão Proposta",
     "title":"Estrutura DAM Cast Group — padrão obrigatório",
     "content":"""O DAM (Documento de Arquitetura de Melhoria) da Cast Group segue estrutura obrigatória:
1. Capa com dados do cliente, arquiteto, data e código PMS
2. Sumário automático
3. Necessidade: processo atual, processo futuro, benefício esperado
4. Solução: resumo técnico, escopo por módulo (tabela Mód/Entregável/Escopo/Premissas)
5. Premissas gerais (21 itens padrão)
6. Equipe do projeto
7. Análise de impactos
8. Cronograma (macro)
9. Investimento: valor total em tabela
10. Condições de faturamento: 50%/50% (aprovação/go-live), garantia 30 dias, validade 30 dias.
Horas de pré-venda NÃO entram no DAM nem no WP — são custo interno apenas."""},

    {"id":"cast-wp-001","source":"Cast Group","category":"Padrão Proposta",
     "title":"Work Package Cast Group — estrutura obrigatória",
     "content":"""O WP (Work Package) da Cast Group é uma planilha Excel com:
- Aba WP_RFP
- Fases SAP Activate: Prepare, Explore, Realize, Homologação, Deploy, Go Live, Suporte
- Recursos: frente (SD/FI/ABAP/GP), nível (Sênior/Pleno), dias por semana
- KT AMS obrigatório no Deploy
- 8h por dia, 168h por mês
- Totalizadores automáticos por recurso e por fase
- Horas de pré-venda separadas (não faturáveis) — custo interno de margem
Referência ECONF Goiás: SD 9 dias + FI 11 dias + GP 4 dias + 3×ABAP 14 dias = 66 dias = 528h"""},
]

# ══════════════════════════════════════
# INDEXAÇÃO
# ══════════════════════════════════════
def index_knowledge_base():
    """Indexa a base de conhecimento SAP no store em memória"""
    global _memory_store
    _memory_store = []
    for doc in SAP_KNOWLEDGE_BASE:
        text    = f"{doc['title']}\n\n{doc['content']}"
        vec     = _embed_text(text)
        _memory_store.append({**doc, "embedding": vec, "indexed_at": datetime.utcnow().isoformat()})
    return len(_memory_store)

# ══════════════════════════════════════
# BUSCA
# ══════════════════════════════════════
def search(query: str, top_k: int = 4, category: Optional[str] = None) -> List[Dict]:
    """Busca semântica na base de conhecimento"""
    if not _memory_store:
        index_knowledge_base()

    q_vec   = _embed_text(query)
    results = []
    for doc in _memory_store:
        if category and doc.get("category") != category:
            continue
        score = _cosine(q_vec, doc["embedding"])
        results.append({**doc, "score": score})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

def get_context_for_agent(agent_type: str, intake_text: str) -> str:
    """Monta contexto RAG personalizado por tipo de agente"""
    category_map = {
        "DRC":             "DRC",
        "ABAP":            "ABAP",
        "FISCAL_ESTADUAL": "Fiscal Estadual",
        "FISCAL_FEDERAL":  "Legislação Federal",
        "REFORMA":         "Reforma Tributária",
        "EQUIPE":          "Metodologia",
        "COMERCIAL":       "Padrão Proposta",
    }
    cat     = category_map.get(agent_type)
    results = search(intake_text, top_k=3, category=cat)

    if not results:
        results = search(intake_text, top_k=3)

    context = "\n\n---\n\n".join(
        f"[{r['source']} | {r['title']}]\n{r['content']}"
        for r in results
    )
    return context

# Indexar ao importar
try:
    n = index_knowledge_base()
except Exception:
    pass
