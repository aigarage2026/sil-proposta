"""
Sil-Proposta — Database Layer
SQLite em desenvolvimento, PostgreSQL em producao
"""
import os, json, sqlite3, asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime

# Detectar se PostgreSQL esta disponivel
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL and DATABASE_URL.startswith("postgres"):
    DB_BACKEND = "postgres"
else:
    DB_BACKEND = "sqlite"
    SQLITE_PATH = os.environ.get("SQLITE_PATH",
                  os.path.join(os.path.dirname(__file__), "data", "proposals.db"))

# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────
async def init_db():
    if DB_BACKEND == "sqlite":
        os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id               TEXT PRIMARY KEY,
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                title            TEXT NOT NULL,
                rfp_text         TEXT,
                project_type     TEXT,
                sap_version      TEXT,
                states           TEXT,
                commercial       TEXT,
                new_law          INTEGER DEFAULT 0,
                hours_presale    INTEGER DEFAULT 0,
                status           TEXT DEFAULT 'draft',
                main_proc        TEXT DEFAULT 'SD',
                needs_cpi        INTEGER DEFAULT 0,
                total_hours      INTEGER DEFAULT 0,
                valor            REAL    DEFAULT 0,
                resources_json   TEXT,
                entregaveis_json TEXT,
                premissas_json   TEXT,
                legislacao_json  TEXT,
                dam_json         TEXT,
                confidence_json  TEXT,
                notes            TEXT,
                lang             TEXT DEFAULT 'pt'
            )
        """)
        conn.commit()
        conn.close()
        print(f"SQLite inicializado: {SQLITE_PATH}")
    else:
        import asyncpg
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id               TEXT PRIMARY KEY,
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                title            TEXT NOT NULL,
                rfp_text         TEXT,
                project_type     TEXT,
                sap_version      TEXT,
                states           TEXT,
                commercial       TEXT,
                new_law          BOOLEAN DEFAULT FALSE,
                hours_presale    INTEGER DEFAULT 0,
                status           TEXT DEFAULT 'draft',
                main_proc        TEXT DEFAULT 'SD',
                needs_cpi        BOOLEAN DEFAULT FALSE,
                total_hours      INTEGER DEFAULT 0,
                valor            FLOAT   DEFAULT 0,
                resources_json   TEXT,
                entregaveis_json TEXT,
                premissas_json   TEXT,
                legislacao_json  TEXT,
                dam_json         TEXT,
                confidence_json  TEXT,
                notes            TEXT,
                lang             TEXT DEFAULT 'pt'
            )
        """)
        await conn.close()
        print("PostgreSQL inicializado")


# ─────────────────────────────────────────────
# DB CLASS
# ─────────────────────────────────────────────
class ProposalDB:
    def __init__(self):
        self._conn = None

    async def save_proposal(self, data: Dict[str, Any]) -> bool:
        if DB_BACKEND == "sqlite":
            return self._sqlite_save(data)
        else:
            return await self._pg_save(data)

    async def list_proposals(self) -> List[Dict]:
        if DB_BACKEND == "sqlite":
            return self._sqlite_list()
        else:
            return await self._pg_list()

    async def get_proposal(self, pid: str) -> Optional[Dict]:
        if DB_BACKEND == "sqlite":
            return self._sqlite_get(pid)
        else:
            return await self._pg_get(pid)

    async def update_proposal(self, pid: str, updates: Dict) -> bool:
        if DB_BACKEND == "sqlite":
            return self._sqlite_update(pid, updates)
        else:
            return await self._pg_update(pid, updates)

    async def delete_proposal(self, pid: str) -> bool:
        if DB_BACKEND == "sqlite":
            return self._sqlite_delete(pid)
        else:
            return await self._pg_delete(pid)

    # ── SQLite ──
    def _sqlite_save(self, data: Dict) -> bool:
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            cols = ", ".join(data.keys())
            vals = ", ".join(["?" for _ in data])
            conn.execute(f"INSERT OR REPLACE INTO proposals ({cols}) VALUES ({vals})",
                         list(data.values()))
            conn.commit()
            conn.close()
            return True
        except Exception as ex:
            print(f"DB save error: {ex}")
            return False

    def _sqlite_list(self) -> List[Dict]:
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM proposals ORDER BY created_at DESC"
            ).fetchall()
            conn.close()
            return [self._row_to_dict(r) for r in rows]
        except Exception as ex:
            print(f"DB list error: {ex}")
            return []

    def _sqlite_get(self, pid: str) -> Optional[Dict]:
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
            conn.close()
            return self._row_to_dict(row) if row else None
        except Exception as ex:
            print(f"DB get error: {ex}")
            return None

    def _sqlite_update(self, pid: str, updates: Dict) -> bool:
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            sets = ", ".join(f"{k}=?" for k in updates)
            vals = list(updates.values()) + [pid]
            c = conn.execute(f"UPDATE proposals SET {sets} WHERE id=?", vals)
            conn.commit()
            conn.close()
            return c.rowcount > 0
        except Exception as ex:
            print(f"DB update error: {ex}")
            return False

    def _sqlite_delete(self, pid: str) -> bool:
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            c = conn.execute("DELETE FROM proposals WHERE id=?", (pid,))
            conn.commit()
            conn.close()
            return c.rowcount > 0
        except Exception as ex:
            print(f"DB delete error: {ex}")
            return False

    def _row_to_dict(self, row) -> Dict:
        d = dict(row)
        # Desserializar campos JSON
        for field in ("resources_json","entregaveis_json","premissas_json",
                      "legislacao_json","dam_json","confidence_json"):
            if d.get(field):
                try:
                    key = field.replace("_json","")
                    d[key] = json.loads(d[field])
                except:
                    d[key] = d[field]
        # Desserializar states
        if d.get("states"):
            try:
                d["states"] = json.loads(d["states"])
            except:
                pass
        return d

    # ── PostgreSQL ──
    async def _pg_save(self, data: Dict) -> bool:
        import asyncpg
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            cols = ", ".join(data.keys())
            nums = ", ".join(f"${i+1}" for i in range(len(data)))
            await conn.execute(
                f"INSERT INTO proposals ({cols}) VALUES ({nums}) ON CONFLICT (id) DO UPDATE SET "
                + ", ".join(f"{k}=EXCLUDED.{k}" for k in data),
                *list(data.values())
            )
            await conn.close()
            return True
        except Exception as ex:
            print(f"PG save error: {ex}")
            return False

    async def _pg_list(self) -> List[Dict]:
        import asyncpg
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            rows = await conn.fetch("SELECT * FROM proposals ORDER BY created_at DESC")
            await conn.close()
            return [self._row_to_dict(dict(r)) for r in rows]
        except Exception as ex:
            print(f"PG list error: {ex}")
            return []

    async def _pg_get(self, pid: str) -> Optional[Dict]:
        import asyncpg
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            row = await conn.fetchrow("SELECT * FROM proposals WHERE id=$1", pid)
            await conn.close()
            return self._row_to_dict(dict(row)) if row else None
        except Exception as ex:
            print(f"PG get error: {ex}")
            return None

    async def _pg_update(self, pid: str, updates: Dict) -> bool:
        import asyncpg
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            sets = ", ".join(f"{k}=${i+1}" for i,k in enumerate(updates))
            vals = list(updates.values()) + [pid]
            r = await conn.execute(
                f"UPDATE proposals SET {sets} WHERE id=${len(vals)}", *vals)
            await conn.close()
            return int(r.split()[-1]) > 0
        except Exception as ex:
            print(f"PG update error: {ex}")
            return False

    async def _pg_delete(self, pid: str) -> bool:
        import asyncpg
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            r = await conn.execute("DELETE FROM proposals WHERE id=$1", pid)
            await conn.close()
            return int(r.split()[-1]) > 0
        except Exception as ex:
            print(f"PG delete error: {ex}")
            return False


# Dependency injection
async def get_db():
    db = ProposalDB()
    try:
        yield db
    finally:
        pass
