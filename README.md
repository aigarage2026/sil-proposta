# sil-proposta

Multi-tenant SaaS for SAP project proposal generation, powered by a multi-agent AI orchestrator.

> **Status:** active refactor. The current code lives in [`sap-proposal-app/`](sap-proposal-app/) (will be renamed to `sil-proposta-app/`). The original monolith is archived under [`legacy/`](legacy/).

## Repository layout

```
sil-proposta/
├── docs/                              SaaS v2 architecture and alignment plan
│   ├── ARCHITECTURE_PORTAL_SAAS_v2.md     Reference architecture for the platform (Control Plane + product modules)
│   └── PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md Plan to align sil-proposta with the platform (7 waves, ~12 weeks)
│
├── sap-proposal-app/                  Current refactor — multi-tenant scaffold (will be renamed sil-proposta-app/)
│   ├── backend/                       FastAPI + SQLAlchemy + Alembic (Tenant / Company / User / Proposal models)
│   ├── frontend/                      React + Vite + TypeScript + Tailwind
│   └── deployment/                    Docker, Compose, Nginx, target Cloud Run
│
└── legacy/                            Archived — see legacy/README.md
    └── sil-proposta-monolith/         Previous FastAPI + vanilla HTML monolith (no auth, no multi-tenancy)
```

## Where to start

| If you want to... | Read |
|---|---|
| Understand the platform vision | [`docs/ARCHITECTURE_PORTAL_SAAS_v2.md`](docs/ARCHITECTURE_PORTAL_SAAS_v2.md) |
| See what changes to align sil-proposta | [`docs/PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md`](docs/PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md) |
| Run the current backend | [`sap-proposal-app/README.md`](sap-proposal-app/README.md) |
| See what was retired and why | [`legacy/README.md`](legacy/README.md) |

## Conventions

- New code goes in `sap-proposal-app/` (soon `sil-proposta-app/`).
- Migrations to extract pieces from `legacy/` happen across Wave 5 of the alignment plan.
- The whole `legacy/` folder is removed in Wave 7.
- Multi-tenant by row-level `tenant_id` (TenantMixin), no Postgres RLS.
- JWT validation against the Portal's JWKS once Wave 1 lands; until then, local HS256 (legacy mode).

## Rollback

A pre-reorganization snapshot is tagged as `backup/pre-org-2026-05-14`. Restore the original `Porposta Full/` layout with:

```bash
git checkout backup/pre-org-2026-05-14
```

## Remote

`https://github.com/aigarage2026/sil-proposta`
