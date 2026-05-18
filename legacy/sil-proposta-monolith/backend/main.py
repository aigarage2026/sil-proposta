"""
Sil-Proposta — Backend FastAPI v3
Banco de dados real (SQLite local / PostgreSQL producao)
"""
from dotenv import load_dotenv
load_dotenv(override=True)

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import asyncio, json, uuid, os, io, sys
from datetime import datetime
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(__file__))
from database import init_db, get_db
from demo_engine import gerar_proposta_demo
from agents.orchestrator_v5 import OrchestratorV5 as Orchestrator, _get_billing_records

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Sil-Proposta API", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["Content-Disposition"])

# Servir frontend
# Servir frontend — busca index.html na mesma pasta do backend
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_frontend_candidates = [
    os.path.join(_backend_dir),                          # backend/index.html
    os.path.join(_backend_dir, "..", "frontend"),        # frontend/index.html
]
for _fdir in _frontend_candidates:
    if os.path.isfile(os.path.join(_fdir, "index.html")):
        app.mount("/app", StaticFiles(directory=_fdir, html=True), name="frontend")
        print(f"Frontend servido de: {_fdir}")
        break

class IntakePayload(BaseModel):
    project_type:  str
    sap_version:   str
    client_name:   str = ""
    states:        List[str]
    commercial:    str
    tax_reform:    str = "auto"
    rfp_text:      Optional[str]  = None
    new_law:       Optional[bool] = None
    hours_presale: Optional[int]  = 0
    notes:         Optional[str]  = None
    lang:          str = "pt"

def _get_engine():
    """Determina qual engine usar: orchestrator (OpenAI) > demo."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key and openai_key != "sua-chave-aqui":
        return "orchestrator", openai_key
    return "demo", ""

@app.get("/api/health")
async def health():
    engine, _ = _get_engine()
    return {"status": "ok", "version": "4.0.0",
            "ts": datetime.utcnow().isoformat(),
            "engine": engine,
            "api_key": "configured" if engine != "demo" else "demo_mode",
            "db": "connected"}

@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app")

@app.post("/api/upload-rfp")
async def upload_rfp(file: UploadFile = File(...)):
    content = await file.read()
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    text = ""
    try:
        if ext in ("txt", "eml", "md"):
            text = content.decode("utf-8", errors="replace")
        elif ext == "docx":
            from docx import Document as D
            doc = D(io.BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        else:
            text = content.decode("utf-8", errors="replace")[:8000]
    except Exception as ex:
        text = f"[Erro: {ex}]"
    return {"filename": filename, "ext": ext, "chars": len(text),
            "preview": text[:300], "text": text[:8000]}

@app.post("/api/generate")
async def generate(payload: IntakePayload, db=Depends(get_db)):
    # ── LIMPAR estado global — ZERO contaminação entre propostas ──
    pass  # v5 limpa internamente

    engine, api_key = _get_engine()
    result = None

    # 1. Orchestrator multi-agente (OpenAI GPT-4o)
    if engine == "orchestrator":
        try:
            print(f"[generate] Usando orchestrator multi-agente (OpenAI)")
            orch = Orchestrator(payload)
            result = await orch.run()
        except Exception as ex:
            print(f"[generate] Orchestrator error: {ex} — fallback demo")
            result = None

    # 2. Fallback: demo engine (sem API key)
    if result is None:
        print(f"[generate] Usando demo engine")
        result = gerar_proposta_demo(payload)

    # ── Recalcular valor com taxas dos profissionais cadastrados ──
    try:
        taxas = await db.get_taxa_por_frente()
        if taxas:
            recursos = result.get("wp_resources", [])
            valor_calc = 0
            for r in recursos:
                frente = r.get("frente", "")
                nivel = r.get("nivel", "Senior")
                horas = r.get("dias", 0) * 8
                taxa = taxas.get(f"{frente}_{nivel}", taxas.get(frente, 230))
                r["taxa_hora"] = taxa
                r["valor"] = round(horas * taxa)
                valor_calc += r["valor"]
            if valor_calc > 0:
                result["dam"]["comercial"]["valor_referencia"] = valor_calc
                result["dam"]["comercial"]["tarifa_hora"] = round(valor_calc / max(1, result.get("total_hours", 1)))
    except Exception as ex:
        print(f"[generate] Erro ao aplicar taxas: {ex}")

    pid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    prop_number = await db.get_next_proposal_number(datetime.utcnow().year)
    client_name = payload.client_name or "Cliente"
    title = f"{client_name} — {prop_number}"
    await db.save_proposal({
        "id": pid, "created_at": now, "updated_at": now,
        "title": title,
        "client_name": client_name,
        "proposal_number": prop_number,
        "version": 1,
        "rfp_text": payload.rfp_text or "",
        "project_type": payload.project_type,
        "sap_version": payload.sap_version,
        "states": json.dumps(payload.states),
        "commercial": payload.commercial,
        "new_law": payload.new_law or False,
        "hours_presale": payload.hours_presale or 0,
        "status": "draft",
        "main_proc": result.get("main_proc", "SD"),
        "needs_cpi": result["dam"].get("plano", {}).get("needs_cpi", False),
        "total_hours": result["total_hours"],
        "valor": result["dam"]["comercial"].get("valor_referencia", 0),
        "resources_json":    json.dumps(result["wp_resources"]),
        "entregaveis_json":  json.dumps(result["dam"].get("entregaveis", [])),
        "premissas_json":    json.dumps(result["dam"].get("premissas", [])),
        "legislacao_json":   json.dumps(result["dam"].get("fiscal", {}).get("legislacao", [])),
        "dam_json":          json.dumps(result["dam"]),
        "confidence_json":   json.dumps(result.get("confidence", {})),
        "lang": payload.lang,
    })
    result["proposal_id"] = pid
    result["title"] = title
    result["status"] = "draft"
    result["version"] = 1
    result["client_name"] = client_name
    result["proposal_number"] = prop_number
    result["saved_to_db"] = True

    # ── Salvar billing usage ──
    try:
        billing_records = _get_billing_records()
        if billing_records:
            pricing = await db.get_llm_price(billing_records[0].get("model_name", ""))
            price_input = pricing.get("price_input", 0) if pricing else 0
            price_output = pricing.get("price_output", 0) if pricing else 0
            price_cached = pricing.get("price_cached", 0) if pricing else 0
            for rec in billing_records:
                ti = rec.get("tokens_input", 0)
                to = rec.get("tokens_output", 0)
                tc = rec.get("tokens_cached", 0)
                ci = round(ti * price_input / 1_000_000, 6)
                co = round(to * price_output / 1_000_000, 6)
                cc = round(tc * price_cached / 1_000_000, 6)
                await db.save_billing_usage({
                    "id": str(uuid.uuid4()),
                    "created_at": datetime.utcnow().isoformat(),
                    "proposal_id": pid,
                    "model_name": rec.get("model_name", ""),
                    "agent_name": rec.get("agent_name", ""),
                    "tokens_input": ti,
                    "tokens_output": to,
                    "tokens_cached": tc,
                    "cost_input": ci,
                    "cost_output": co,
                    "cost_cached": cc,
                    "cost_total": round(ci + co + cc, 6),
                })
    except Exception as ex:
        print(f"[billing] Erro: {ex}")

    return result

@app.post("/api/generate/stream")
async def generate_stream(payload: IntakePayload, db=Depends(get_db)):
    async def stream():
        # ── LIMPAR estado global — ZERO contaminação ──
        pass  # v5 limpa internamente

        engine, api_key = _get_engine()
        result = None

        # Orchestrator com streaming real dos agentes
        if engine == "orchestrator":
            try:
                orch = Orchestrator(payload)
                async for event in orch.stream():
                    if event.get("type") == "complete":
                        result = event["result"]
                    else:
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as ex:
                print(f"[stream] Orchestrator error: {ex}")
                yield f"data: {json.dumps({'type':'agent','name':'Orquestrador','status':'error','error':str(ex)})}\n\n"

        # Fallback: demo engine com animação simulada
        if result is None:
            agents_sim = [
                ("orch","Orquestrador"),("sd","Agente SD"),("fi","Agente FI"),
                ("abap","ABAP Estrutural"),("drc","Agente DRC"),
                ("fest","Fiscal Estadual"),("ffed","Fiscal Federal"),
                ("eq","Equipe/GP"),("com","Comercial"),
            ]
            yield f"data: {json.dumps({'type':'start','msg':'Analisando demanda...'})}\n\n"
            for ag_id, ag_name in agents_sim:
                yield f"data: {json.dumps({'type':'agent','id':ag_id,'name':ag_name,'status':'running'})}\n\n"
                await asyncio.sleep(0.3)
                yield f"data: {json.dumps({'type':'agent','id':ag_id,'name':ag_name,'status':'done'})}\n\n"

            result = gerar_proposta_demo(payload)

        # Salvar no banco
        pid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        prop_number = await db.get_next_proposal_number(datetime.utcnow().year)
        client_name = payload.client_name or "Cliente"
        title = f"{client_name} — {prop_number}"
        await db.save_proposal({
            "id": pid, "created_at": now, "updated_at": now,
            "title": title,
            "client_name": client_name,
            "proposal_number": prop_number,
            "version": 1,
            "rfp_text": payload.rfp_text or "",
            "project_type": payload.project_type,
            "sap_version": payload.sap_version,
            "states": json.dumps(payload.states),
            "commercial": payload.commercial,
            "new_law": payload.new_law or False,
            "hours_presale": payload.hours_presale or 0,
            "status": "draft",
            "main_proc": result.get("main_proc","SD"),
            "needs_cpi": result.get("dam",{}).get("plano",{}).get("needs_cpi",False),
            "total_hours": result.get("total_hours",0),
            "valor": result.get("dam",{}).get("comercial",{}).get("valor_referencia",0),
            "resources_json":   json.dumps(result.get("wp_resources",[])),
            "entregaveis_json": json.dumps(result.get("dam",{}).get("entregaveis",[])),
            "premissas_json":   json.dumps(result.get("dam",{}).get("premissas",[])),
            "legislacao_json":  json.dumps(result.get("dam",{}).get("fiscal",{}).get("legislacao",[])),
            "dam_json":         json.dumps(result.get("dam",{})),
            "confidence_json":  json.dumps(result.get("confidence",{})),
            "lang": payload.lang,
        })
        result["proposal_id"] = pid
        result["title"] = title
        result["client_name"] = client_name
        result["proposal_number"] = prop_number
        result["saved_to_db"] = True

        # ── Salvar billing usage (stream) ──
        try:
            billing_records = _get_billing_records()
            if billing_records:
                pricing = await db.get_llm_price(billing_records[0].get("model_name", ""))
                price_input = pricing.get("price_input", 0) if pricing else 0
                price_output = pricing.get("price_output", 0) if pricing else 0
                price_cached = pricing.get("price_cached", 0) if pricing else 0
                for rec in billing_records:
                    ti = rec.get("tokens_input", 0)
                    to_ = rec.get("tokens_output", 0)
                    tc = rec.get("tokens_cached", 0)
                    ci = round(ti * price_input / 1_000_000, 6)
                    co = round(to_ * price_output / 1_000_000, 6)
                    cc = round(tc * price_cached / 1_000_000, 6)
                    await db.save_billing_usage({
                        "id": str(uuid.uuid4()),
                        "created_at": datetime.utcnow().isoformat(),
                        "proposal_id": pid,
                        "model_name": rec.get("model_name", ""),
                        "agent_name": rec.get("agent_name", ""),
                        "tokens_input": ti,
                        "tokens_output": to_,
                        "tokens_cached": tc,
                        "cost_input": ci,
                        "cost_output": co,
                        "cost_cached": cc,
                        "cost_total": round(ci + co + cc, 6),
                    })
        except Exception as ex:
            print(f"[billing-stream] Erro: {ex}")

        yield f"data: {json.dumps({'type':'complete','result':result}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.get("/api/proposals")
async def list_proposals(db=Depends(get_db)):
    proposals = await db.list_proposals()
    return {"proposals": proposals, "total": len(proposals)}

@app.get("/api/proposals/{pid}")
async def get_proposal(pid: str, db=Depends(get_db)):
    p = await db.get_proposal(pid)
    if not p:
        raise HTTPException(404, f"Proposta {pid} nao encontrada")
    return p

@app.patch("/api/proposals/{pid}/approve")
async def approve_proposal(pid: str, db=Depends(get_db)):
    ok = await db.update_proposal(pid, {"status":"approved","updated_at":datetime.utcnow().isoformat()})
    if not ok:
        raise HTTPException(404, "Proposta nao encontrada")
    return {"ok": True, "proposal_id": pid, "status": "approved"}

@app.patch("/api/proposals/{pid}/approve-architect")
async def approve_architect(pid: str, db=Depends(get_db)):
    p = await db.get_proposal(pid)
    if not p:
        raise HTTPException(404, "Proposta nao encontrada")
    if p.get("status") not in ("draft", None, ""):
        raise HTTPException(400, f"Proposta precisa estar em rascunho (status atual: {p.get('status')})")
    ok = await db.update_proposal(pid, {"status": "architect_approved", "updated_at": datetime.utcnow().isoformat()})
    return {"ok": ok, "proposal_id": pid, "status": "architect_approved"}

@app.patch("/api/proposals/{pid}/approve-client")
async def approve_client(pid: str, db=Depends(get_db)):
    p = await db.get_proposal(pid)
    if not p:
        raise HTTPException(404, "Proposta nao encontrada")
    if p.get("status") != "architect_approved":
        raise HTTPException(400, "Proposta precisa ter aprovacao do arquiteto primeiro")
    ok = await db.update_proposal(pid, {"status": "client_approved", "updated_at": datetime.utcnow().isoformat()})
    return {"ok": ok, "proposal_id": pid, "status": "client_approved"}

@app.post("/api/proposals/{pid}/regenerate")
async def regenerate_proposal(pid: str, payload: IntakePayload, db=Depends(get_db)):
    """Re-generate proposal, incrementing version."""
    old = await db.get_proposal(pid)
    if not old:
        raise HTTPException(404, "Proposta nao encontrada")

    engine, api_key = _get_engine()
    result = None

    if engine == "orchestrator":
        try:
            orch = Orchestrator(payload)
            result = await orch.run()
        except Exception as ex:
            print(f"[regenerate] Orchestrator error: {ex}")

    if result is None:
        result = gerar_proposta_demo(payload)

    now = datetime.utcnow().isoformat()
    new_version = (old.get("version") or 1) + 1
    client_name = payload.client_name or old.get("client_name") or "Cliente"
    prop_number = old.get("proposal_number") or ""
    title = f"{client_name} — {prop_number}" if prop_number else old.get("title", "Proposta")

    total_hours = result.get("total_hours", 0)
    await db.update_proposal(pid, {
        "updated_at": now,
        "title": title,
        "client_name": client_name,
        "version": new_version,
        "status": "draft",
        "rfp_text": payload.rfp_text or "",
        "project_type": payload.project_type,
        "sap_version": payload.sap_version,
        "states": json.dumps(payload.states),
        "commercial": payload.commercial,
        "new_law": 1 if payload.new_law else 0,
        "main_proc": result.get("main_proc", "SD"),
        "needs_cpi": 1 if result.get("dam", {}).get("plano", {}).get("needs_cpi") else 0,
        "total_hours": total_hours,
        "valor": result.get("dam", {}).get("comercial", {}).get("valor_referencia", 0),
        "resources_json": json.dumps(result.get("wp_resources", [])),
        "entregaveis_json": json.dumps(result.get("dam", {}).get("entregaveis", [])),
        "premissas_json": json.dumps(result.get("dam", {}).get("premissas", [])),
        "legislacao_json": json.dumps(result.get("dam", {}).get("fiscal", {}).get("legislacao", [])),
        "dam_json": json.dumps(result.get("dam", {})),
        "confidence_json": json.dumps(result.get("confidence", {})),
    })

    result["proposal_id"] = pid
    result["title"] = title
    result["status"] = "draft"
    result["version"] = new_version
    result["client_name"] = client_name
    result["proposal_number"] = prop_number
    return result

@app.get("/api/dashboard")
async def dashboard(db=Depends(get_db)):
    stats = await db.get_dashboard_stats()
    return stats

# ════════════════════════════════════════════════════════
# CLIENTES
# ════════════════════════════════════════════════════════
@app.get("/api/clientes")
async def list_clientes(db=Depends(get_db)):
    items = await db.list_clientes()
    return {"clientes": items, "total": len(items)}

@app.post("/api/clientes")
async def save_cliente(data: dict, db=Depends(get_db)):
    cid = data.get("id") or str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    record = {
        "id": cid,
        "created_at": data.get("created_at", now),
        "updated_at": now,
        "nome": data.get("nome", ""),
        "cnpj": data.get("cnpj", ""),
        "razao_social": data.get("razao_social", ""),
        "contato_nome": data.get("contato_nome", ""),
        "contato_email": data.get("contato_email", ""),
        "contato_fone": data.get("contato_fone", ""),
        "endereco": data.get("endereco", ""),
        "cidade": data.get("cidade", ""),
        "uf": data.get("uf", ""),
        "sap_version": data.get("sap_version", ""),
        "observacoes": data.get("observacoes", ""),
    }
    ok = await db.save_cliente(record)
    return {"ok": ok, "id": cid}

@app.delete("/api/clientes/{cid}")
async def delete_cliente(cid: str, db=Depends(get_db)):
    ok = await db.delete_cliente(cid)
    if not ok:
        raise HTTPException(404, "Cliente não encontrado")
    return {"ok": True}

# ════════════════════════════════════════════════════════
# PROFISSIONAIS
# ════════════════════════════════════════════════════════
@app.get("/api/profissionais")
async def list_profissionais(db=Depends(get_db)):
    items = await db.list_profissionais()
    return {"profissionais": items, "total": len(items)}

@app.post("/api/profissionais")
async def save_profissional(data: dict, db=Depends(get_db)):
    pid = data.get("id") or str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    record = {
        "id": pid,
        "created_at": data.get("created_at", now),
        "updated_at": now,
        "nome": data.get("nome", ""),
        "frente": data.get("frente", "SD"),
        "nivel": data.get("nivel", "Senior"),
        "taxa_hora": float(data.get("taxa_hora", 230)),
        "email": data.get("email", ""),
        "disponivel": 1 if data.get("disponivel", True) else 0,
        "observacoes": data.get("observacoes", ""),
    }
    ok = await db.save_profissional(record)
    return {"ok": ok, "id": pid}

@app.delete("/api/profissionais/{pid}")
async def delete_profissional(pid: str, db=Depends(get_db)):
    ok = await db.delete_profissional(pid)
    if not ok:
        raise HTTPException(404, "Profissional não encontrado")
    return {"ok": True}

@app.get("/api/profissionais/taxas")
async def get_taxas(db=Depends(get_db)):
    """Retorna taxas por frente/nível para uso no cálculo."""
    taxas = await db.get_taxa_por_frente()
    return {"taxas": taxas}

# ════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════
# BILLING — LLM Pricing + Usage
# ════════════════════════════════════════════════════════
@app.get("/api/billing/pricing")
async def list_llm_pricing(db=Depends(get_db)):
    items = await db.list_llm_pricing()
    return {"pricing": items, "total": len(items)}

@app.post("/api/billing/pricing")
async def save_llm_pricing(data: dict, db=Depends(get_db)):
    pid = data.get("id") or str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    record = {
        "id": pid,
        "created_at": data.get("created_at", now),
        "updated_at": now,
        "model_name": data.get("model_name", ""),
        "provider": data.get("provider", "OpenAI"),
        "price_input": float(data.get("price_input", 0)),
        "price_cached": float(data.get("price_cached", 0)),
        "price_output": float(data.get("price_output", 0)),
        "ativo": 1 if data.get("ativo", True) else 0,
    }
    ok = await db.save_llm_pricing(record)
    return {"ok": ok, "id": pid}

@app.delete("/api/billing/pricing/{pid}")
async def delete_llm_pricing(pid: str, db=Depends(get_db)):
    ok = await db.delete_llm_pricing(pid)
    if not ok:
        raise HTTPException(404, "LLM não encontrada")
    return {"ok": True}

@app.get("/api/billing/usage")
async def list_billing_usage(db=Depends(get_db)):
    items = await db.list_billing_usage(limit=200)
    return {"usage": items, "total": len(items)}

@app.get("/api/billing/summary")
async def get_billing_summary(db=Depends(get_db)):
    summary = await db.get_billing_summary()
    return {"summary": summary}

# LEGISLAÇÃO
# ════════════════════════════════════════════════════════
@app.get("/api/legislacao")
async def list_legislacao(tipo: str = None, db=Depends(get_db)):
    items = await db.list_legislacao(tipo)
    return {"items": items, "total": len(items)}

@app.post("/api/legislacao")
async def create_legislacao(data: dict, db=Depends(get_db)):
    lid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    record = {
        "id": lid,
        "created_at": now,
        "updated_at": now,
        "tipo": data.get("tipo", "federal"),
        "nome": data.get("nome", ""),
        "descricao": data.get("descricao", ""),
        "url_fonte": data.get("url_fonte", ""),
        "texto_completo": data.get("texto_completo", ""),
        "data_publicacao": data.get("data_publicacao", now[:10]),
        "data_limite_homo": data.get("data_limite_homo", ""),
        "data_limite_prod": data.get("data_limite_prod", ""),
        "ufs_afetadas": json.dumps(data.get("ufs_afetadas", ["TODAS"])),
        "setores": json.dumps(data.get("setores", [])),
        "impacto_sap": json.dumps(data.get("impacto_sap", [])),
        "status": "nova",
        "proposal_id": "",
        "fonte": data.get("fonte", "manual"),
    }
    ok = await db.save_legislacao(record)
    return {"ok": ok, "id": lid}

@app.delete("/api/legislacao")
async def delete_all_legislacao(db=Depends(get_db)):
    count = await db.delete_all_legislacao()
    return {"ok": True, "deleted": count}

@app.delete("/api/legislacao/{lid}")
async def delete_legislacao(lid: str, db=Depends(get_db)):
    ok = await db.delete_legislacao(lid)
    if not ok:
        raise HTTPException(404, "Legislacao nao encontrada")
    return {"ok": True}

@app.post("/api/legislacao/scrape")
async def scrape_legislacao(db=Depends(get_db)):
    """Run scrapers to fetch new legislation from government portals."""
    from scraper import run_full_scrape
    api_key = os.environ.get("OPENAI_API_KEY", "")
    try:
        items = await run_full_scrape(api_key)
        saved = 0
        for item in items:
            lid = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            record = {
                "id": lid,
                "created_at": now,
                "updated_at": now,
                "tipo": item.get("tipo", "federal"),
                "nome": item.get("nome", "")[:200],
                "descricao": item.get("descricao", "")[:1000],
                "url_fonte": item.get("url_fonte", ""),
                "texto_completo": "",
                "data_publicacao": item.get("data_publicacao", now[:10]),
                "data_limite_homo": item.get("data_limite_homo") or "",
                "data_limite_prod": item.get("data_limite_prod") or "",
                "ufs_afetadas": json.dumps(item.get("ufs_afetadas", ["TODAS"])) if isinstance(item.get("ufs_afetadas"), list) else json.dumps(["TODAS"]),
                "setores": json.dumps(item.get("setores", [])) if isinstance(item.get("setores"), list) else json.dumps([]),
                "impacto_sap": json.dumps(item.get("impacto_sap", [])) if isinstance(item.get("impacto_sap"), list) else json.dumps([]),
                "status": "nova",
                "proposal_id": "",
                "fonte": item.get("fonte", "scraper"),
            }
            ok = await db.save_legislacao(record)
            if ok:
                saved += 1
        return {"ok": True, "scraped": len(items), "saved": saved}
    except Exception as ex:
        raise HTTPException(500, f"Erro no scraping: {ex}")

@app.post("/api/legislacao/scrape-url")
async def scrape_legislacao_url(data: dict, db=Depends(get_db)):
    """Scrape specific URLs provided by the user."""
    from scraper import scrape_urls, classify_with_ai
    urls = data.get("urls", [])
    if not urls:
        raise HTTPException(400, "Nenhuma URL fornecida")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    try:
        items = await scrape_urls(urls)
        if api_key and items:
            items = await classify_with_ai(items, api_key)
        saved = 0
        for item in items:
            lid = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            record = {
                "id": lid,
                "created_at": now,
                "updated_at": now,
                "tipo": item.get("tipo", "federal"),
                "nome": item.get("nome", "")[:200],
                "descricao": item.get("descricao", "")[:1000],
                "url_fonte": item.get("url_fonte", ""),
                "texto_completo": item.get("texto_completo", "")[:5000],
                "data_publicacao": item.get("data_publicacao", now[:10]),
                "data_limite_homo": item.get("data_limite_homo") or "",
                "data_limite_prod": item.get("data_limite_prod") or "",
                "ufs_afetadas": json.dumps(item.get("ufs_afetadas", ["TODAS"])) if isinstance(item.get("ufs_afetadas"), list) else json.dumps(["TODAS"]),
                "setores": json.dumps(item.get("setores", [])) if isinstance(item.get("setores"), list) else json.dumps([]),
                "impacto_sap": json.dumps(item.get("impacto_sap", [])) if isinstance(item.get("impacto_sap"), list) else json.dumps([]),
                "status": "nova",
                "proposal_id": "",
                "fonte": "url",
            }
            ok = await db.save_legislacao(record)
            if ok:
                saved += 1
        return {"ok": True, "scraped": len(items), "saved": saved}
    except Exception as ex:
        raise HTTPException(500, f"Erro ao buscar URLs: {ex}")

@app.delete("/api/proposals/{pid}")
async def delete_proposal(pid: str, db=Depends(get_db)):
    ok = await db.delete_proposal(pid)
    if not ok:
        raise HTTPException(404, "Proposta nao encontrada")
    return {"ok": True, "proposal_id": pid}

@app.get("/api/proposals/{pid}/download/dam")
async def download_dam(pid: str, db=Depends(get_db)):
    p = await db.get_proposal(pid)
    if not p:
        raise HTTPException(404, "Proposta nao encontrada")
    try:
        from generators.dam import generate_dam
        dam_data = json.loads(p.get("dam_json") or "{}")
        buf = generate_dam(dam_data, p)
        import unicodedata
        raw_title = str(p.get('title','Proposta'))[:30].replace(' ','_')
        fname = unicodedata.normalize('NFKD', raw_title).encode('ascii', 'ignore').decode('ascii')
        fname = f"DAM_{fname or 'Proposta'}.docx"
        return StreamingResponse(buf,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    except Exception as ex:
        raise HTTPException(500, f"Erro ao gerar DAM: {ex}")

async def _gerar_com_llm(payload: IntakePayload, api_key: str) -> dict:
    import httpx
    ctx = f"Tipo:{payload.project_type} SAP:{payload.sap_version} UFs:{','.join(payload.states)}\nRFP:{payload.rfp_text or 'Adequacao fiscal.'}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model":"gpt-4o-mini","max_tokens":1500,"temperature":0.2,
                  "messages":[
                      {"role":"system","content":"""Arquiteto SAP senior Cast Group. Retorne APENAS JSON:
{"titulo":"DAM — <resumo> (<UFs>)","necessidade":"<desc>","main_proc":"MM|SD|FI|PP|HR|PM|FISCAL|MIGR",
"needs_cpi":bool,"entregaveis":[{"mod":"SD","item":"..."}],"equipe":[{"frente":"SD","nivel":"Senior","dias":N}],
"total_horas":N,"valor":N,"premissas":["..."],"legislacao":["..."]}"""},
                      {"role":"user","content":ctx}]})
        data = r.json()
        txt = data["choices"][0]["message"]["content"].strip()
        import re as re2
        m = re2.search(r"```(?:json)?\s*([\s\S]+?)\s*```", txt)
        if m: txt = m.group(1)
        llm = json.loads(txt)

    ufs = payload.states or ["SP"]
    th  = llm.get("total_horas", 128)
    res = llm.get("equipe",[{"frente":"SD","nivel":"Senior","dias":10},{"frente":"FI","nivel":"Senior","dias":8}])
    return {
        "main_proc": llm.get("main_proc","SD"),
        "total_hours": th,
        "wp_resources": res,
        "confidence": {"escopo":0.88,"horas":0.82,"legislacao":0.78,"comercial":0.95},
        "agents_fired": ["Orquestrador","SD","FI","ABAP","DRC","Fiscal","Equipe","Comercial"],
        "dam": {
            "titulo": llm.get("titulo", f"DAM — {(payload.rfp_text or '')[:50]} ({','.join(ufs)})"),
            "tipo_projeto": payload.project_type, "versao_sap": payload.sap_version, "ufs": ufs,
            "necessidade": llm.get("necessidade", payload.rfp_text or ""),
            "entregaveis": llm.get("entregaveis",[]),
            "premissas": llm.get("premissas",[]),
            "equipe": res, "total_horas": th,
            "plano": {"needs_cpi": llm.get("needs_cpi",False),"modules":[]},
            "reforma": {"decisao":"monitorar"},
            "fiscal": {"legislacao": llm.get("legislacao",[])},
            "comercial": {"valor_referencia": llm.get("valor", th*230)},
        },
    }
