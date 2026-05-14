# sil-proposta

Multi-tenant SaaS for SAP project proposal generation, powered by a multi-agent AI orchestrator. A product module of the AI Garage SaaS v2 platform.

## Repository layout

```
sil-proposta/
├── docs/                                          Platform architecture and alignment plan
│   ├── ARCHITECTURE_PORTAL_SAAS_v3.md             Reference architecture (Control Plane + product modules)
│   └── PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md         7-wave plan to align this product (will be revised against v3)
│
├── sil-proposta-app/                              Active code — multi-tenant scaffold
│   ├── backend/                                   FastAPI + SQLAlchemy + Alembic (Tenant / Company / User / Proposal)
│   ├── frontend/                                  React + Vite + TypeScript + Tailwind
│   └── deployment/                                Docker, Compose, Nginx, target Cloud Run
│
└── legacy/                                        Archived — see legacy/README.md
    └── sil-proposta-monolith/                     Previous FastAPI + vanilla HTML monolith (no auth, no multi-tenancy)
```

## Where to start

| If you want to... | Read |
|---|---|
| Understand the platform vision | [`docs/ARCHITECTURE_PORTAL_SAAS_v3.md`](docs/ARCHITECTURE_PORTAL_SAAS_v3.md) |
| See what changes to align sil-proposta with the platform | [`docs/PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md`](docs/PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md) |
| Run the current backend | [`sil-proposta-app/README.md`](sil-proposta-app/README.md) |
| See what was retired and why | [`legacy/README.md`](legacy/README.md) |

## Conventions

- New code goes in `sil-proposta-app/`.
- Migration of useful pieces from `legacy/` happens across Wave 5 of the alignment plan.
- The whole `legacy/` folder is removed in Wave 7.
- Multi-tenant by row-level `tenant_id` (TenantMixin), no Postgres RLS.
- JWT validated against the Portal's JWKS once Wave 1 lands; until then, local HS256 (legacy mode).

## Rollback

A pre-reorganization snapshot is tagged as `backup/pre-org-2026-05-14`. Restore the original `Porposta Full/` layout with:

```bash
git checkout backup/pre-org-2026-05-14
```

## Remote

`https://github.com/aigarage2026/sil-proposta`
