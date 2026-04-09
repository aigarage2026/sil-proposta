"""
Orquestrador Sil-Proposta v2 — com RAG integrado
"""
import anthropic, asyncio, json, os
from typing import AsyncIterator

_client = None
def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client

# ── RAG ──
try:
    from agents.rag import get_context_for_agent, search
except ImportError:
    from rag import get_context_for_agent, search

SYSTEM_ORCH = """Você é o orquestrador do Sil-Proposta. Analise o intake e retorne APENAS JSON:
{
  "modules": ["SD","FI","ABAP"],
  "fiscal_agents": ["estadual","federal"],
  "needs_cpi": true,
  "needs_reform": false,
  "hardware_integration": true,
  "abap_objects": ["BAPI","BAdI","RFC","iFlow","Monitor"],
  "abap_parallelism": 3,
  "reasoning": "explicação em 1-2 linhas"
}
Sem markdown, sem texto fora do JSON."""

AGENTS = {
"SD": """Agente SAP SD. Analise o escopo e retorne JSON:
{"entregaveis":["item1","item2"],"horas":72,"premissas":["premissa1"],"observacoes":"resumo"}
Inclua: faturamento, NF-e saída, Grupo YA, BAdI NF-e, tpIntegra=1 quando GO/IN1608.
Sem markdown.""",

"FI": """Agente SAP FI. Retorne JSON:
{"entregaveis":["item1"],"horas":88,"premissas":["premissa1"],"observacoes":"resumo"}
Inclua: conciliação bancária, trigger ECONF, baixa de título, contas a receber.
Sem markdown.""",

"ABAP": """Agente ABAP Estrutural. REGRAS OBRIGATÓRIAS:
- Hardware externo (maquininha/TEF/POS) → BAPI Z como primeiro entregável
- Evento sem nota SAP → iFlow CPI obrigatório
- 4+ desenvolvimentos independentes → n_abapers=3
- Cadeia: BAPI → BAdI → RFC → iFlow CPI → Monitor Z (objetos distintos)
Retorne JSON:
{"entregaveis":["BAPI Z","BAdI","RFC Z","iFlow CPI","Monitor Z"],
 "horas_por_abaper":112,"n_abapers":3,"total_horas":336,"paralelo":true,"premissas":["..."]}
Sem markdown.""",

"DRC": """Agente DRC. REGRA CRÍTICA: ECONF (110750/110751) NÃO tem suporte DRC nativo → CPI obrigatório.
Retorne JSON:
{"canal":"CPI","entregaveis":["iFlow ECONF 110750","iFlow cancelamento 110751","config canais CPI"],
 "horas":0,"justificativa":"ECONF sem nota SAP — CPI obrigatório"}
Sem markdown.""",

"FISCAL_ESTADUAL": """Agente Fiscal Estadual. Conhece ICMS/RICMS 27 UFs, cBenef, IN 1.608/2025-GO (tpIntegra=1).
Retorne JSON:
{"legislacao":["IN 1.608/2025-GSE"],"entregaveis":["BAdI cBenef","tabela Z cBenef"],
 "horas":8,"alertas":["tpIntegra=1 obrigatório GO"]}
Sem markdown.""",

"FISCAL_FEDERAL": """Agente Fiscal Federal. IPI, PIS/COFINS, Reforma Tributária LC 214.
Retorne JSON:
{"legislacao":["NT 2024.002"],"entregaveis":["apuração fiscal"],"horas":8,"alertas":[]}
Sem markdown.""",

"REFORMA": """Agente Reforma Tributária. LC 214/2021, EC 132/2023, IBS/CBS/IS.
Decisão: fazer_agora (go-live pós jul/2026 + escopo SD/FI) | planejar | monitorar.
Retorne JSON:
{"decisao":"monitorar","impactos":["IBS/CBS afeta SD/FI"],"entregaveis":[],"horas":0}
Sem markdown.""",

"EQUIPE": """Agente Equipe. REGRA: 4+ ABAP independentes → 3 ABAPers paralelos. GP se projeto >3 semanas.
Retorne JSON:
{"recursos":[{"frente":"SD","nivel":"Senior","dias":9},{"frente":"FI","nivel":"Senior","dias":11},
 {"frente":"GP","nivel":"Senior","dias":4},{"frente":"ABAP 1","nivel":"Senior","dias":14},
 {"frente":"ABAP 2","nivel":"Senior","dias":14},{"frente":"ABAP 3","nivel":"Senior","dias":14}],
 "total_dias":66,"semanas":4,"gp":true}
Sem markdown.""",

"COMERCIAL": """Agente Comercial. Padrão Cast Group: valor fechado, 50%/50%, garantia 30d, validade 30d.
Retorne JSON:
{"faturamento":"50%/50%","garantia":"30 dias","validade":"30 dias",
 "premissas":["Esta proposta não contempla a extração dos dados da maquininha.",
              "Todos os desenvolvimentos em ABAP.","Gerenciamento remoto durante toda a execução."]}
Sem markdown.""",
}

def _call(system: str, user: str) -> dict:
    resp = client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=system,
        messages=[{"role":"user","content":user}]
    )
    text = resp.content[0].text.strip()
    # Limpar markdown se vier
    if "```" in text:
        import re
        m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
        if m: text = m.group(1)
    return json.loads(text)

class Orchestrator:
    def __init__(self, payload):
        self.p = payload

    def _ctx(self) -> str:
        p = self.p
        return (f"Tipo: {p.project_type} | SAP: {p.sap_version} | "
                f"UFs: {', '.join(p.states)} | Comercial: {p.commercial} | "
                f"Reforma: {p.tax_reform} | Nova lei: {p.new_law} | "
                f"Horas pré-venda: {p.hours_presale}\n\n"
                f"RFP:\n{p.rfp_text or 'Não informada'}\n\n"
                f"Obs: {p.notes or 'Nenhuma'}")

    async def run(self) -> dict:
        ctx     = self._ctx()
        fired   = []
        results = {}

        # 1. Orquestrador
        rag_ctx = search(ctx, top_k=2)
        rag_txt = "\n".join(f"[{r['title']}]\n{r['content'][:300]}" for r in rag_ctx)
        plan    = _call(SYSTEM_ORCH, f"{ctx}\n\nCONHECIMENTO RELEVANTE:\n{rag_txt}")
        fired.append("Orquestrador")

        # 2. Agentes funcionais
        for mod in plan.get("modules", ["SD","FI","ABAP"]):
            if mod in AGENTS:
                ag_ctx = get_context_for_agent(mod, ctx)
                results[mod] = _call(AGENTS[mod], f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}")
                fired.append(mod)

        # 3. DRC sempre
        ag_ctx = get_context_for_agent("DRC", ctx)
        results["DRC"] = _call(AGENTS["DRC"], f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}")
        fired.append("DRC")

        # 4. Fiscais
        for uf in self.p.states:
            if uf in ["GO","SP","MG","RJ","PR","RS","SC"]:
                ag_ctx = get_context_for_agent("FISCAL_ESTADUAL", f"UF: {uf}\n{ctx}")
                results["FISCAL_ESTADUAL"] = _call(AGENTS["FISCAL_ESTADUAL"],
                    f"UF: {uf}\n{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}")
                fired.append(f"Fiscal {uf}")
                break
        ag_ctx = get_context_for_agent("FISCAL_FEDERAL", ctx)
        results["FISCAL_FEDERAL"] = _call(AGENTS["FISCAL_FEDERAL"],
            f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}")
        fired.append("Fiscal Federal")

        # 5. Reforma
        if plan.get("needs_reform") or self.p.tax_reform in ["yes","auto"]:
            ag_ctx = get_context_for_agent("REFORMA", ctx)
            results["REFORMA"] = _call(AGENTS["REFORMA"],
                f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:800]}")
            fired.append("Reforma Tributária")

        # 6. Equipe
        ag_ctx = get_context_for_agent("EQUIPE", ctx)
        results["EQUIPE"] = _call(AGENTS["EQUIPE"],
            f"ABAP: {json.dumps(results.get('ABAP',{}))}\n{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:600]}")
        fired.append("Equipe/GP")

        # 7. Comercial
        ag_ctx = get_context_for_agent("COMERCIAL", ctx)
        results["COMERC"] = _call(AGENTS["COMERCIAL"],
            f"Recursos: {json.dumps(results.get('EQUIPE',{}))}\n{ctx}")
        fired.append("Comercial")

        return self._consolidate(plan, results, fired)

    async def stream(self) -> AsyncIterator[dict]:
        ctx  = self._ctx()
        fired= []
        results = {}

        yield {"type":"start","msg":"Orquestrador analisando intake..."}
        plan = _call(SYSTEM_ORCH, ctx)
        fired.append("Orquestrador")
        yield {"type":"agent","name":"Orquestrador","status":"done","plan":plan}

        steps = [
            ("SD",       "SD"),
            ("FI",       "FI"),
            ("DRC",      "DRC"),
            ("ABAP",     "ABAP Estrutural"),
            ("FISCAL_ESTADUAL", f"Fiscal {self.p.states[0] if self.p.states else 'GO'}"),
            ("FISCAL_FEDERAL",  "Fiscal Federal"),
            ("EQUIPE",   "Equipe/GP"),
            ("COMERC",   "Comercial"),
        ]
        for key, label in steps:
            if key not in AGENTS:
                continue
            yield {"type":"agent","name":label,"status":"running"}
            await asyncio.sleep(0.1)
            try:
                ag_ctx = get_context_for_agent(key, ctx)
                results[key] = _call(AGENTS[key],
                    f"{ctx}\n\nCONTEXTO RAG:\n{ag_ctx[:600]}")
                fired.append(label)
                yield {"type":"agent","name":label,"status":"done",
                       "outputs":results[key].get("entregaveis",[])}
            except Exception as e:
                yield {"type":"agent","name":label,"status":"error","error":str(e)}

        consolidated = self._consolidate(plan, results, fired)
        yield {"type":"complete","result":consolidated}

    def _consolidate(self, plan, results, agents):
        eq  = results.get("EQUIPE", {})
        res = eq.get("recursos", [
            {"frente":"SD","nivel":"Senior","dias":9},
            {"frente":"FI","nivel":"Senior","dias":11},
            {"frente":"GP","nivel":"Senior","dias":4},
            {"frente":"ABAP 1","nivel":"Senior","dias":14},
            {"frente":"ABAP 2","nivel":"Senior","dias":14},
            {"frente":"ABAP 3","nivel":"Senior","dias":14},
        ])
        th  = sum(r["dias"]*8 for r in res)

        all_e   = []
        all_p   = []
        for k, v in results.items():
            if isinstance(v, dict):
                all_e.extend(v.get("entregaveis", []))
                all_p.extend(v.get("premissas",   []))

        BASE_PREMISSAS = [
            "Esta proposta não contempla a extração dos dados da maquininha.",
            "Os acessos necessários deverão estar liberados até o início do projeto.",
            "Todos os desenvolvimentos serão realizados em ABAP.",
            "O início das atividades somente após aprovação formal do cronograma.",
            "Gerenciamento remoto durante toda a execução do projeto.",
            "Dia de consultoria: 8h (08h30-12h / 13h30-18h), segunda a sexta.",
        ]
        premissas = BASE_PREMISSAS + [p for p in all_p if p not in BASE_PREMISSAS]

        dam = {
            "titulo":       f"DAM — {(self.p.rfp_text or 'Proposta SAP')[:60]}",
            "tipo_projeto": self.p.project_type,
            "versao_sap":   self.p.sap_version,
            "ufs":          self.p.states,
            "necessidade":  results.get("SD",{}).get("observacoes","Adequação fiscal e operacional."),
            "entregaveis":  list(dict.fromkeys(all_e)),
            "premissas":    premissas,
            "equipe":       res,
            "total_horas":  th,
            "plano":        plan,
            "reforma":      results.get("REFORMA", {"decisao":"monitorar"}),
            "fiscal":       results.get("FISCAL_ESTADUAL", {}),
            "comercial":    results.get("COMERC", {}),
        }

        confidence = {
            "escopo":     0.88 if self.p.rfp_text else 0.65,
            "horas":      0.82,
            "legislacao": 0.91 if self.p.states else 0.70,
            "comercial":  0.95,
        }
        return {"dam":dam,"wp":res,"total_hours":th,
                "confidence":confidence,"agents":agents}
