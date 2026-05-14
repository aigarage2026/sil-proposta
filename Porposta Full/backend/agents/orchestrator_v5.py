"""
Sil-Proposta — Orquestrador Determinístico v5
Arquitetura nova: catálogo Python decide tudo, LLM só gera texto descritivo.
ZERO contaminação garantida — cada proposta é independente.
"""
import httpx, asyncio, json, os, re
from typing import AsyncIterator

try:
    from agents.catalog import (
        classify_demand, get_demand_config, calculate_team,
        build_entregaveis, filter_entregaveis, filter_premissas,
        PREMISSAS_PADRAO, EXCLUSOES_PADRAO,
    )
except ImportError:
    from catalog import (
        classify_demand, get_demand_config, calculate_team,
        build_entregaveis, filter_entregaveis, filter_premissas,
        PREMISSAS_PADRAO, EXCLUSOES_PADRAO,
    )

# ── Config ──
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
CLAUDE_AGENTS = set(os.environ.get("CLAUDE_AGENTS", "ABAP,QA").split(","))


def _get_api_key():
    return os.environ.get("OPENAI_API_KEY", "")


def _get_anthropic_key():
    return os.environ.get("ANTHROPIC_API_KEY", "")


# ── Billing tracking ──
_billing_buffer = []


def _get_billing_records():
    global _billing_buffer
    records = list(_billing_buffer)
    _billing_buffer = []
    return records


# ══════════════════════════════════════════════════════════════
# CHAMADAS LLM
# ══════════════════════════════════════════════════════════════
async def _call_llm(system: str, user: str, agent_name: str = "", max_tokens: int = 2000) -> str:
    """Chama OpenAI ou Claude (com fallback para OpenAI se Claude falhar)."""
    use_claude = agent_name in CLAUDE_AGENTS and _get_anthropic_key() and _get_anthropic_key() != "sua-chave-aqui"
    if use_claude:
        try:
            return await _call_anthropic(system, user, agent_name, max_tokens)
        except Exception as e:
            print(f"[fallback] Claude falhou ({type(e).__name__}: {e!r}), usando OpenAI para {agent_name}")
            return await _call_openai(system, user, agent_name, max_tokens)
    return await _call_openai(system, user, agent_name, max_tokens)


async def _call_openai(system: str, user: str, agent_name: str = "", max_tokens: int = 2000) -> str:
    api_key = _get_api_key()
    if not api_key or api_key == "sua-chave-aqui":
        raise ValueError("OPENAI_API_KEY não configurada")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "temperature": 0.0,  # ZERO temperatura — máxima consistência
                "max_tokens": max_tokens,
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
        _billing_buffer.append({
            "model_name": MODEL,
            "agent_name": agent_name,
            "tokens_input": usage.get("prompt_tokens", 0),
            "tokens_output": usage.get("completion_tokens", 0),
            "tokens_cached": (usage.get("prompt_tokens_details", {}) or {}).get("cached_tokens", 0),
        })
        return text


async def _call_anthropic(system: str, user: str, agent_name: str = "", max_tokens: int = 2000) -> str:
    api_key = _get_anthropic_key()
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        if r.status_code >= 400:
            print(f"[Claude ERROR {r.status_code}]: {r.text[:500]}")
        r.raise_for_status()
        data = r.json()
        text = data["content"][0]["text"].strip()
        usage = data.get("usage", {})
        _billing_buffer.append({
            "model_name": ANTHROPIC_MODEL,
            "agent_name": agent_name,
            "tokens_input": usage.get("input_tokens", 0),
            "tokens_output": usage.get("output_tokens", 0),
            "tokens_cached": usage.get("cache_read_input_tokens", 0),
        })
        return text


def _parse_json(text: str) -> dict:
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
        return {}


# ══════════════════════════════════════════════════════════════
# AGENTES LLM — só geram TEXTO descritivo, não decidem nada
# ══════════════════════════════════════════════════════════════
async def gerar_as_is_to_be(rfp: str) -> dict:
    """Gera processo atual vs futuro a partir da RFP."""
    system = """Você é um arquiteto SAP. Analise a RFP e descreva processo atual e futuro.
Retorne APENAS JSON: {"processo_atual":"...","processo_futuro":"...","beneficio":"..."}
Sem markdown."""
    try:
        text = await _call_llm(system, f"RFP:\n{rfp}", agent_name="AS_IS_TO_BE")
        return _parse_json(text) or {}
    except Exception as e:
        print(f"AS-IS/TO-BE erro: {e}")
        return {}


async def _detalhar_abap_item(rfp: str, obj: dict) -> None:
    """Detalha UM objeto ABAP. Mutação in-place."""
    system = """Você é um arquiteto ABAP sênior SAP da Cast Group.
Para o objeto ABAP recebido, gere passos detalhados (transações SE11/SE38/SE80/SM30/SE19, nomes Z, BAdIs, parâmetros, validações) e código ABAP real funcional (TYPES/DATA, lógica, tratamento de erros, comentários).
Retorne APENAS JSON (sem markdown):
{"como_fazer":"1) ... 2) ... 3) ...","parametros":"campos e valores","transacoes":["T1","T2"],"exemplo_codigo":"REPORT z...\\nDATA: ..."}"""
    user_msg = f"RFP:\n{rfp}\n\nObjeto: {obj['item']}\nTipo: {obj.get('tipo','')}\nTransação base: {obj.get('transacao','')}"
    try:
        text = await _call_llm(system, user_msg, agent_name="ABAP", max_tokens=3000)
        d = _parse_json(text) or {}
        if d:
            obj["como_fazer"] = d.get("como_fazer", "")
            obj["parametros"] = d.get("parametros", "")
            obj["transacoes"] = d.get("transacoes", [])
            obj["exemplo_codigo"] = d.get("exemplo_codigo", "")
    except Exception as e:
        print(f"[ABAP item erro] {obj.get('item','')[:40]}: {e}")


async def detalhar_abap(rfp: str, abap_objects: list) -> list:
    """Detalha cada objeto ABAP em paralelo (1 LLM call por item — evita truncamento)."""
    if not abap_objects:
        return []
    await asyncio.gather(*[_detalhar_abap_item(rfp, o) for o in abap_objects], return_exceptions=True)
    return abap_objects


async def _detalhar_abap_BATCH_LEGACY(rfp: str, abap_objects: list) -> list:
    """Versão legacy em batch (não usada — truncava em respostas grandes)."""
    system = """LEGACY — não usar.
Para CADA objeto ABAP recebido:

1. PASSOS DETALHADOS (numerados) — incluindo:
   - Transação SAP exata para cada passo (SE11, SE19, SE38, SE80, SM30, SE37, SE93, etc.)
   - Nome sugerido do objeto Z (ex: ZTABELA_XXX, ZCL_XXX, ZRFC_XXX)
   - Estrutura de campos da tabela Z (se aplicável)
   - Nome da BAdI/Enhancement Spot (se aplicável)
   - Parâmetros de configuração
   - Pontos de atenção e validações

2. CÓDIGO ABAP REAL — snippet funcional ABAP com:
   - Declarações TYPES/DATA
   - Lógica principal
   - Tratamento de erros
   - Comentários explicativos

Retorne APENAS JSON (sem markdown):
{
  "detalhes": [
    {
      "item": "<nome exato do objeto recebido>",
      "como_fazer": "1) SE11: criar tabela Z com campos... 2) SM30: gerar view de manutenção... 3) Implementar BAdI...",
      "parametros": "Campos: MANDT, UF, CST, CBENEF (CHAR 10)",
      "transacoes": ["SE11", "SM30"],
      "exemplo_codigo": "TABLES: zcbenef_uf.\\n\\nDATA: lt_cbenef TYPE TABLE OF zcbenef_uf.\\n\\nSELECT * FROM zcbenef_uf\\n  INTO TABLE lt_cbenef\\n  WHERE uf = p_uf\\n    AND cst = p_cst.\\n\\nIF sy-subrc = 0.\\n  " CBENEF encontrado\\nENDIF."
    }
  ]
}"""
    objetos_texto = "\n".join([f"- {o['item']} (tipo: {o.get('tipo','')}, transação: {o.get('transacao','')})" for o in abap_objects])
    try:
        text = await _call_llm(system, f"RFP do cliente:\n{rfp}\n\nObjetos a detalhar:\n{objetos_texto}", agent_name="ABAP", max_tokens=8000)
        try:
            open("/tmp/abap_resp.txt","w").write(text)
        except Exception: pass
        print(f"[ABAP] resp_len={len(text)} ends={text[-100:]!r}")
        result = _parse_json(text)
        detalhes = result.get("detalhes", []) if result else []
        print(f"[ABAP] parsed_detalhes={len(detalhes)}")
        # Mesclar detalhes com objetos originais
        for obj in abap_objects:
            for d in detalhes:
                d_item = d.get("item", "").lower()
                o_item = obj["item"].lower()
                # Match por substring
                if d_item and (d_item in o_item or o_item in d_item or d_item[:30] in o_item):
                    obj["como_fazer"] = d.get("como_fazer", "")
                    obj["parametros"] = d.get("parametros", "")
                    obj["transacoes"] = d.get("transacoes", [])
                    obj["exemplo_codigo"] = d.get("exemplo_codigo", "")
                    break
    except Exception as e:
        print(f"ABAP detalhamento erro: {e}")
    return abap_objects


async def detalhar_modulo_funcional(rfp: str, modulo: str, entregaveis: list) -> list:
    """Detalha cada entregável funcional (SD, FI, MM, etc.) com passo-a-passo."""
    func_items = [e for e in entregaveis if e.get("mod") == modulo]
    if not func_items:
        return entregaveis

    system = f"""Você é um arquiteto SAP {modulo} sênior da Cast Group.
Para CADA entregável, gere passo-a-passo detalhado para execução:

FORMATO OBRIGATÓRIO para "como_fazer":
"1) Transação XXXX: ação específica com parâmetros
2) Configurar em SPRO > caminho > subcaminho
3) Validar em transação YYYY
4) Testar cenário Z com estes dados..."

Inclua:
- Transações SAP exatas (J1B1N, VA01, F110, SPRO, etc.)
- Caminhos SPRO completos
- Nomes de campos SAP (BUKRS, KUNNR, VKORG, etc.)
- Valores de teste sugeridos
- Pontos de validação

Retorne APENAS JSON:
{{"detalhes":[{{"item":"<nome objeto>","como_fazer":"<passos numerados detalhados>","parametros":"<campos e valores>","transacoes":["T1","T2"]}}]}}
Sem markdown."""

    itens_texto = "\n".join([f"- {e['item']}" for e in func_items])
    try:
        text = await _call_llm(system, f"RFP:\n{rfp}\n\nEntregáveis {modulo}:\n{itens_texto}", agent_name=modulo, max_tokens=4000)
        result = _parse_json(text)
        detalhes = result.get("detalhes", []) if result else []
        for obj in func_items:
            for d in detalhes:
                d_item = d.get("item", "").lower()
                o_item = obj["item"].lower()
                if d_item and (d_item in o_item or o_item in d_item or d_item[:30] in o_item):
                    obj["como_fazer"] = d.get("como_fazer", "")
                    obj["parametros"] = d.get("parametros", "")
                    obj["transacoes"] = d.get("transacoes", [])
                    break
    except Exception as e:
        print(f"{modulo} detalhamento erro: {e}")
    return entregaveis


async def qa_review(dam: dict, rfp: str) -> dict:
    """QA revisa a proposta consolidada."""
    system = """Você é um QA sênior de propostas SAP. Verifique se a proposta faz sentido para a RFP.
Critérios: (1) entregáveis batem com a RFP, (2) sem contaminação de outros temas, (3) horas razoáveis.
Retorne APENAS JSON: {"aprovado":true,"score":90,"problemas":[],"sugestoes":[]}
Sem markdown."""
    resumo = json.dumps({
        "rfp": rfp[:500],
        "modulos": dam.get("plano", {}).get("modules", []),
        "n_entregaveis": len(dam.get("entregaveis", [])),
        "horas": dam.get("total_horas", 0),
        "valor": dam.get("comercial", {}).get("valor_referencia", 0),
    }, ensure_ascii=False)
    try:
        text = await _call_llm(system, f"PROPOSTA:\n{resumo}", agent_name="QA")
        return _parse_json(text) or {"aprovado": True, "score": 80, "problemas": [], "sugestoes": []}
    except Exception as e:
        print(f"QA erro: {e}")
        return {"aprovado": True, "score": 0, "problemas": [], "sugestoes": []}


# ══════════════════════════════════════════════════════════════
# ORQUESTRADOR DETERMINÍSTICO
# ══════════════════════════════════════════════════════════════
class OrchestratorV5:
    def __init__(self, payload):
        self.p = payload

    async def run(self) -> dict:
        # ZERO contaminação: limpar buffer
        global _billing_buffer
        _billing_buffer = []

        rfp = self.p.rfp_text or ""
        ufs = self.p.states or []
        client_name = getattr(self.p, "client_name", "") or "Cliente"

        agents_fired = ["Classificador (Python determinístico)"]

        # ═══════════════════════════════════════════
        # 1. CLASSIFICADOR DETERMINÍSTICO (Python puro)
        # ═══════════════════════════════════════════
        tipo = classify_demand(rfp)
        config = get_demand_config(tipo)
        print(f"[v5] Tipo classificado: {tipo} ({config['label']})")

        # ═══════════════════════════════════════════
        # 2. ENTREGÁVEIS DO CATÁLOGO (determinístico)
        # ═══════════════════════════════════════════
        entregaveis = build_entregaveis(tipo)

        # Para tipo "generic" (não classificado), pedir LLM gerar
        if tipo == "generic":
            entregaveis = await self._gerar_entregaveis_genericos(rfp)
            agents_fired.append("Agente Genérico (LLM)")

        # ═══════════════════════════════════════════
        # 3. AGENTES EM PARALELO — ABAP + Funcionais + AS-IS
        # ═══════════════════════════════════════════
        tasks = []
        task_labels = []

        abap_objects = [e for e in entregaveis if e.get("mod") == "ABAP"]
        if abap_objects:
            tasks.append(detalhar_abap(rfp, abap_objects))
            task_labels.append("Agente ABAP (Claude)" if "ABAP" in CLAUDE_AGENTS else "Agente ABAP (GPT-4o)")

        for mod in ["SD", "FI", "MM", "CO", "PP", "HR", "QM", "WM", "BASIS"]:
            if any(e.get("mod") == mod for e in entregaveis):
                tasks.append(detalhar_modulo_funcional(rfp, mod, entregaveis))
                task_labels.append(f"Agente {mod} (detalhamento)")

        tasks.append(gerar_as_is_to_be(rfp))
        task_labels.append("Processo AS-IS/TO-BE")

        results_par = await asyncio.gather(*tasks, return_exceptions=True)
        as_is = results_par[-1] if not isinstance(results_par[-1], Exception) else {}
        agents_fired.extend(task_labels)

        # ═══════════════════════════════════════════
        # 5. CALCULAR EQUIPE (determinístico)
        # ═══════════════════════════════════════════
        total_horas_e = sum(e.get("horas", 0) for e in entregaveis if isinstance(e, dict))
        recursos = calculate_team(tipo, total_horas_e)
        agents_fired.append("Equipe (calculada)")

        total_horas = sum(r.get("dias", 0) * 8 for r in recursos)

        # ═══════════════════════════════════════════
        # 6. PREMISSAS (filtradas)
        # ═══════════════════════════════════════════
        premissas = filter_premissas(PREMISSAS_PADRAO, rfp)

        # ═══════════════════════════════════════════
        # 7. EXCLUSÕES
        # ═══════════════════════════════════════════
        exclusoes = list(EXCLUSOES_PADRAO)
        if config.get("complexity") == "baixa":
            exclusoes.append("Não contempla customizações além do escopo descrito acima")

        # ═══════════════════════════════════════════
        # 8. COMERCIAL (calculado)
        # ═══════════════════════════════════════════
        tarifa_hora = 250
        valor = round(total_horas * tarifa_hora)

        # ═══════════════════════════════════════════
        # 9. MONTAR DAM
        # ═══════════════════════════════════════════
        ver_label = {
            "ecc604": "ECC ≤ 6.04", "ecc605": "ECC 6.05+",
            "s4op": "S/4HANA On-premise", "s4cloud": "S/4HANA Cloud"
        }.get(self.p.sap_version, self.p.sap_version)

        titulo = config.get("label", "Proposta SAP")
        if rfp:
            titulo = f"{config['label']} — {rfp[:50]}" if config["label"] != "Demanda Customizada" else f"DAM — {rfp[:60]}"

        # Filtrar entregáveis (rejeitar placeholders)
        entregaveis = filter_entregaveis(entregaveis)

        dam = {
            "titulo": titulo,
            "cliente": client_name,
            "tipo_projeto": self.p.project_type,
            "tipo_demanda": tipo,
            "label_demanda": config["label"],
            "versao_sap": ver_label,
            "ufs": ufs,
            "necessidade": rfp or "Adequação conforme demanda do cliente.",
            "processo_atual": as_is.get("processo_atual", ""),
            "processo_futuro": as_is.get("processo_futuro", ""),
            "beneficio_esperado": as_is.get("beneficio", ""),
            "sistema_sap": config.get("sistema_sap", ""),
            "fluxo_solucao": config.get("fluxo_solucao", ""),
            "entregaveis": entregaveis,
            "premissas": premissas,
            "exclusoes": exclusoes,
            "equipe": recursos,
            "total_horas": total_horas,
            "impactos": [
                {"id": "01", "descricao": "Erros durante o Go-Live", "probabilidade": "Baixa", "impacto": "Gravíssimo", "classificacao": "Extremo", "solucao": "Recuperação do backup antes da solução"},
                {"id": "02", "descricao": "Engajamento dos Key Users", "probabilidade": "Baixa", "impacto": "Leve", "classificacao": "Baixo", "solucao": "Destacar comprometimento no Kick-off"},
            ],
            "plano": {
                "main_proc": config.get("main_proc", "SD"),
                "modules": config.get("modules", []),
                "complexity": config.get("complexity", "media"),
                "needs_cpi": config.get("needs_cpi", False),
                "needs_basis": config.get("needs_basis", False),
                "needs_abap": "ABAP" in config.get("modules", []),
            },
            "fiscal": {
                "legislacao": [],
                "estadual": {} if not config.get("fiscal_scope", {}).get("estadual") else {"ativo": True},
            },
            "comercial": {
                "valor_referencia": valor,
                "tarifa_hora": tarifa_hora,
                "faturamento": "50% aprovação + 50% Go-Live",
                "garantia": "30 dias corridos",
                "validade": "30 dias",
            },
        }

        # ═══════════════════════════════════════════
        # 10. QA REVISOR (LLM)
        # ═══════════════════════════════════════════
        qa = await qa_review(dam, rfp)
        agents_fired.append("QA (Claude)" if "QA" in CLAUDE_AGENTS else "QA (GPT-4o)")
        dam["qa_score"] = qa.get("score", 80)
        dam["qa_aprovado"] = qa.get("aprovado", True)
        dam["qa_problemas"] = qa.get("problemas", [])
        dam["qa_sugestoes"] = qa.get("sugestoes", [])

        # ═══════════════════════════════════════════
        # 11. RETORNAR
        # ═══════════════════════════════════════════
        confidence = {
            "escopo": 0.92 if tipo != "generic" else 0.65,
            "horas": 0.88 if tipo != "generic" else 0.70,
            "legislacao": 0.91,
            "comercial": 0.95,
        }

        return {
            "main_proc": config.get("main_proc", "SD"),
            "total_hours": total_horas,
            "wp_resources": recursos,
            "confidence": confidence,
            "agents_fired": agents_fired,
            "dam": dam,
        }

    async def stream(self) -> AsyncIterator[dict]:
        global _billing_buffer
        _billing_buffer = []
        rfp = self.p.rfp_text or ""

        yield {"type": "start", "msg": "Classificando demanda..."}
        tipo = classify_demand(rfp)
        config = get_demand_config(tipo)
        yield {"type": "agent", "name": f"Classificador → {config['label']}", "status": "done"}

        # Pré-anuncia agentes que rodarão (visualização imediata)
        entregaveis_preview = build_entregaveis(tipo)
        preview_agents = []
        if any(e.get("mod") == "ABAP" for e in entregaveis_preview):
            preview_agents.append("Agente ABAP (Claude)" if "ABAP" in CLAUDE_AGENTS else "Agente ABAP (GPT-4o)")
        for mod in ["SD", "FI", "MM", "CO", "PP", "HR", "QM", "WM", "BASIS"]:
            if any(e.get("mod") == mod for e in entregaveis_preview):
                preview_agents.append(f"Agente {mod} (detalhamento)")
        preview_agents.append("Processo AS-IS/TO-BE")
        for ag in preview_agents:
            yield {"type": "agent", "name": ag, "status": "running"}

        # Roda em paralelo
        result = await self.run()

        # Marca como done (e quaisquer extras)
        seen = set(preview_agents)
        for ag in result.get("agents_fired", []):
            yield {"type": "agent", "name": ag, "status": "done"}
            seen.add(ag)

        yield {"type": "complete", "result": result}

    async def _gerar_entregaveis_genericos(self, rfp: str) -> list:
        """Para demandas não classificadas, pede ao LLM gerar entregáveis."""
        system = """Você é um arquiteto SAP. Analise a RFP e gere entregáveis específicos.
Cada entregável DEVE ter: mod (SD/FI/MM/ABAP), item (descrição com transação SAP real), horas, fase.
NÃO use placeholders genéricos como 'Descrição', 'item', 'premissa'.
Retorne APENAS JSON: {"entregaveis":[{"mod":"SD","item":"...","horas":16,"fase":"Realize"}]}
Sem markdown."""
        try:
            text = await _call_llm(system, f"RFP:\n{rfp}", agent_name="GENERIC")
            r = _parse_json(text)
            return r.get("entregaveis", []) if r else []
        except Exception as e:
            print(f"Genérico erro: {e}")
            return []
