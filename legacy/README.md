# Legacy

> **Status:** ARCHIVED — read-only. **Do not add new features here.**

This directory holds the previous-generation implementation of sil-proposta:

| Folder | What it is |
|---|---|
| [`sil-proposta-monolith/`](sil-proposta-monolith/) | The original FastAPI + vanilla HTML monolith (formerly `Porposta Full/` at the repo root). Single-tenant, no auth, no migrations. Still functional but superseded. |

## Why it's still here

Some pieces of the monolith have not yet been migrated to the new
[`sap-proposal-app/`](../sap-proposal-app/) (will be renamed `sil-proposta-app/`):

- The multi-agent **orchestrator** (latest is `orchestrator_v5.py`)
- The **DAM** (Word) and **WP** (Excel) generators
- The **legislation scrapers**
- The hash-based **RAG** (placeholder until Qdrant integration)

These are extracted into the new app over the course of Wave 5 of
[`/docs/PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md`](../docs/PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md).

## Rules while it lives here

1. No new features. Bug fixes only if production deploy of the monolith is still live.
2. New work goes in `sap-proposal-app/` (soon `sil-proposta-app/`).
3. When everything in Wave 5 is migrated and validated, this whole folder is deleted (Wave 7).

## Recovering anything

Pre-reorganization snapshot tag: `backup/pre-org-2026-05-14`

```bash
# inspect any file at its original path
git show backup/pre-org-2026-05-14:"Porposta Full/backend/agents/rag.py"

# restore a single file
git checkout backup/pre-org-2026-05-14 -- "Porposta Full/backend/agents/rag.py"
```

## Final removal

When ready (Wave 7):

```bash
# tag last functional state for posterity
git tag legacy/sil-proposta-monolith-final -m "Last commit before legacy removal"

# remove
git rm -r legacy/sil-proposta-monolith
git commit -m "chore: remove legacy/sil-proposta-monolith — superseded by sil-proposta-app"
```

History stays in `git log` regardless.
