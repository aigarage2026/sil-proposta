"""
Sil-Proposta — Persistência
Supabase quando configurado, JSON local como fallback
"""
import os, json, uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# ── Path do fallback local ──
_DATA_DIR = Path(__file__).parent.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
_PROPOSALS_FILE = _DATA_DIR / "proposals.json"

# ══════════════════════════════════
# FALLBACK LOCAL (JSON)
# ══════════════════════════════════
def _load_local() -> List[Dict]:
    if _PROPOSALS_FILE.exists():
        try:
            return json.loads(_PROPOSALS_FILE.read_text())
        except Exception:
            return []
    return []

def _save_local(proposals: List[Dict]):
    _PROPOSALS_FILE.write_text(json.dumps(proposals, ensure_ascii=False, indent=2))

# ══════════════════════════════════
# SUPABASE (quando configurado)
# ══════════════════════════════════
_sb = None

def _get_sb():
    global _sb
    if _sb is not None:
        return _sb
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _sb = create_client(url, key)
        return _sb
    except Exception:
        return None

# ══════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════
def save_proposal(proposal: Dict) -> str:
    """Salva proposta e retorna o ID."""
    pid = proposal.get("proposal_id") or str(uuid.uuid4())[:8]
    proposal["proposal_id"] = pid
    proposal["saved_at"]    = datetime.utcnow().isoformat()

    sb = _get_sb()
    if sb:
        try:
            sb.table("proposals").upsert({
                "id":         pid,
                "data":       json.dumps(proposal, ensure_ascii=False),
                "saved_at":   proposal["saved_at"],
                "project_type": proposal.get("dam_sections",{}).get("tipo_projeto",""),
                "total_hours":  proposal.get("total_hours", 0),
                "ufs":          json.dumps(proposal.get("dam_sections",{}).get("ufs",[])),
            }).execute()
            return pid
        except Exception as e:
            print(f"[Supabase] save falhou: {e} — usando fallback local")

    # Fallback local
    proposals = _load_local()
    proposals = [p for p in proposals if p.get("proposal_id") != pid]
    proposals.insert(0, proposal)
    proposals = proposals[:100]  # manter só as 100 mais recentes
    _save_local(proposals)
    return pid

def load_proposals(limit: int = 20) -> List[Dict]:
    """Carrega lista de propostas (mais recentes primeiro)."""
    sb = _get_sb()
    if sb:
        try:
            res = (sb.table("proposals")
                   .select("*")
                   .order("saved_at", desc=True)
                   .limit(limit)
                   .execute())
            return [json.loads(r["data"]) for r in (res.data or [])]
        except Exception as e:
            print(f"[Supabase] load falhou: {e} — usando fallback local")

    return _load_local()[:limit]

def get_proposal(pid: str) -> Optional[Dict]:
    """Busca proposta por ID."""
    sb = _get_sb()
    if sb:
        try:
            res = sb.table("proposals").select("*").eq("id", pid).execute()
            if res.data:
                return json.loads(res.data[0]["data"])
        except Exception:
            pass

    for p in _load_local():
        if p.get("proposal_id") == pid:
            return p
    return None

def delete_proposal(pid: str) -> bool:
    """Remove proposta."""
    sb = _get_sb()
    if sb:
        try:
            sb.table("proposals").delete().eq("id", pid).execute()
            return True
        except Exception:
            pass

    proposals = [p for p in _load_local() if p.get("proposal_id") != pid]
    _save_local(proposals)
    return True

# ══════════════════════════════════
# ANALYTICS
# ══════════════════════════════════
def get_analytics() -> Dict:
    """Calcula métricas de uso das propostas."""
    proposals = load_proposals(100)
    total = len(proposals)
    if total == 0:
        return {"total":0,"won":0,"conversion":0,"avg_hours":0,"avg_presale":0,"by_type":{}}

    won        = sum(1 for p in proposals if p.get("status") == "won")
    total_h    = sum(p.get("total_hours",0) for p in proposals)
    total_pre  = sum(p.get("presale_hours",0) for p in proposals)
    by_type: Dict[str,int] = {}
    for p in proposals:
        t = p.get("dam_sections",{}).get("tipo_projeto","unknown")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "total":       total,
        "won":         won,
        "conversion":  round(won/total*100, 1) if total else 0,
        "avg_hours":   round(total_h/total, 0) if total else 0,
        "avg_presale": round(total_pre/total, 1) if total else 0,
        "by_type":     by_type,
    }

# ══════════════════════════════════
# SQL para criar tabela no Supabase
# ══════════════════════════════════
SUPABASE_SCHEMA = """
-- Rodar no SQL Editor do Supabase:

CREATE TABLE IF NOT EXISTS proposals (
  id           TEXT PRIMARY KEY,
  data         JSONB NOT NULL,
  saved_at     TIMESTAMPTZ DEFAULT NOW(),
  project_type TEXT,
  total_hours  INTEGER DEFAULT 0,
  ufs          TEXT,
  status       TEXT DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS proposals_saved_at ON proposals(saved_at DESC);
CREATE INDEX IF NOT EXISTS proposals_project_type ON proposals(project_type);

-- Row Level Security (opcional para multi-tenant):
ALTER TABLE proposals ENABLE ROW LEVEL SECURITY;
"""
