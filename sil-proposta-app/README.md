# Sil-Proposta SaaS

Gerador de Propostas SAP com IA Multi-Agente — Plataforma SaaS AI Garage.

## Quick Start (Dev)

```bash
# 1. Subir banco e redis
make dev

# 2. Configurar ambiente
cp backend/.env.example backend/.env

# 3. Instalar dependencias
cd backend && pip install -e ".[dev]"

# 4. Rodar migrations
make migrate

# 5. Seed de dados
make seed

# 6. Iniciar backend
make dev-backend
```

## Arquitetura

```
sil-proposta-app/
├── backend/          # FastAPI + SQLAlchemy + Alembic
│   ├── core/         # Config, database, security, middleware
│   ├── models/       # SQLAlchemy models (base + dominio)
│   ├── schemas/      # Pydantic schemas
│   ├── services/     # Business logic + 10 agentes IA
│   ├── apis/         # REST endpoints v1
│   └── integrations/ # Portal client
├── frontend/         # React + Vite + TypeScript (Fase 4)
├── deployment/       # Docker, nginx, Dockerfiles
└── docs/             # Arquitetura e planos
```

## Stack

- **Backend:** Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic
- **Database:** PostgreSQL 16 + Redis 7
- **Frontend:** React 19 + Vite + TypeScript + Tailwind + shadcn/ui
- **IA:** 10 agentes SAP especializados via Claude (Agent Hub)
- **Deploy:** Docker Compose + Nginx
