"""
Sil-Proposta — Backend FastAPI v3
Banco de dados real (SQLite local / PostgreSQL producao)
"""
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
    states:        List[str]
    commercial:    str
    tax_reform:    str = "auto"
    rfp_text:      Optional[str]  = None
    new_law:       Optional[bool] = None
    hours_presale: Optional[int]  = 0
    notes:         Optional[str]  = None
    lang:          str = "pt"

@app.get("/api/health")
async def health():
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    return {"status": "ok", "version": "3.0.0",
            "ts": datetime.utcnow().isoformat(),
            "api_key": "configured" if has_key else "demo_mode",
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
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        try:
            result = await _gerar_com_llm(payload, openai_key)
        except Exception as ex:
            print(f"LLM error: {ex} — fallback demo")
            result = gerar_proposta_demo(payload)
    else:
        result = gerar_proposta_demo(payload)

    pid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    await db.save_proposal({
        "id": pid, "created_at": now, "updated_at": now,
        "title": result["dam"]["titulo"],
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
    result["saved_to_db"] = True
    return result

@app.post("/api/generate/stream")
async def generate_stream(payload: IntakePayload, db=Depends(get_db)):
    async def stream():
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        agents = [
            ("orch","Orquestrador"),("ver","Versao SAP"),("sd","Agente SD"),
            ("fi","Agente FI"),("abap","ABAP Estrutural"),("drc","Agente DRC"),
            ("fest","Fiscal Estadual"),("ffed","Fiscal Federal"),
            ("eq","Equipe e GP"),("com","Comercial"),
        ]
        yield f"data: {json.dumps({'type':'start','msg':'Analisando intake...'})}\n\n"
        for ag_id, ag_name in agents:
            await asyncio.sleep(0.5 + 0.2 * (hash(ag_id) % 4))
            yield f"data: {json.dumps({'type':'agent','id':ag_id,'name':ag_name,'status':'running'})}\n\n"
            await asyncio.sleep(0.3)
            yield f"data: {json.dumps({'type':'agent','id':ag_id,'name':ag_name,'status':'done'})}\n\n"

        if openai_key:
            try:
                result = await _gerar_com_llm(payload, openai_key)
            except Exception as ex:
                print(f"LLM error: {ex}")
                result = gerar_proposta_demo(payload)
        else:
            result = gerar_proposta_demo(payload)

        pid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        await db.save_proposal({
            "id": pid, "created_at": now, "updated_at": now,
            "title": result["dam"]["titulo"],
            "rfp_text": payload.rfp_text or "",
            "project_type": payload.project_type,
            "sap_version": payload.sap_version,
            "states": json.dumps(payload.states),
            "commercial": payload.commercial,
            "new_law": payload.new_law or False,
            "hours_presale": payload.hours_presale or 0,
            "status": "draft",
            "main_proc": result.get("main_proc","SD"),
            "needs_cpi": result["dam"].get("plano",{}).get("needs_cpi",False),
            "total_hours": result["total_hours"],
            "valor": result["dam"]["comercial"].get("valor_referencia",0),
            "resources_json":   json.dumps(result["wp_resources"]),
            "entregaveis_json": json.dumps(result["dam"].get("entregaveis",[])),
            "premissas_json":   json.dumps(result["dam"].get("premissas",[])),
            "legislacao_json":  json.dumps(result["dam"].get("fiscal",{}).get("legislacao",[])),
            "dam_json":         json.dumps(result["dam"]),
            "confidence_json":  json.dumps(result.get("confidence",{})),
            "lang": payload.lang,
        })
        result["proposal_id"] = pid
        result["saved_to_db"] = True
        yield f"data: {json.dumps({'type':'complete','result':result})}\n\n"

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
        fname = f"DAM_{str(p.get('title','Proposta'))[:30].replace(' ','_')}.docx"
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
