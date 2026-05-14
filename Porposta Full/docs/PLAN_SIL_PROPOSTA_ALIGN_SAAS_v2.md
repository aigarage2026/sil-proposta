# PLAN: Alinhar sil-proposta à Arquitetura SaaS v2 da Plataforma AI Garage

> **Versão:** 1.0
> **Data:** 2026-05-14
> **Autor:** AI Garage Engineering
> **Status:** Plano Pendente de Aprovação
> **Referência:** [`ARCHITECTURE_PORTAL_SAAS_v2.md`](./ARCHITECTURE_PORTAL_SAAS_v2.md)
> **Objetivo:** Trazer o produto **sil-proposta** ao padrão de "produto modular" definido pela plataforma SaaS v2 (Control Plane + Application Planes), com multi-tenancy, multi-empresa, JWT RS256/JWKS, contratos Portal, eventos Redis Streams e shared libs `agn-*`.

---

## Sumário Executivo

Hoje a sil-proposta existe como **duas implementações paralelas** no monorepo:

| Pasta | Estado | Stack | Multi-tenant? | Auth? |
|-------|--------|-------|---------------|-------|
| [`Porposta Full/`](../) | MVP legado funcional, mas monolítico | FastAPI + HTML vanilla 1686 linhas + SQLite | **Não** | **Nenhum** |
| [`sap-proposal-app/`](../../sap-proposal-app/) | Refatoração em andamento (esqueleto) | FastAPI + SQLAlchemy + Alembic + React/Vite/Tailwind | **Parcial — modelos prontos, isolamento parcial** | JWT HS256 local + bcrypt |

A **boa notícia**: `sap-proposal-app/` já tem o **scaffold multi-tenant + multi-empresa correto** (Tenant, Company, User, UserCompanyAccess, TenantMixin, RBAC owner/admin/editor/viewer, branding, plan_slug). É a base certa para evoluir.

A **má notícia**: ainda faltam **9 frentes** para se considerar um produto SaaS v2 conforme [`ARCHITECTURE_PORTAL_SAAS_v2.md`](./ARCHITECTURE_PORTAL_SAAS_v2.md):

1. JWT RS256 + JWKS federado (hoje HS256 local)
2. Contratos obrigatórios do Portal (`provision/deprovision/dashboard/summary/health/lgpd/backup`)
3. Eventos Redis Streams (consumir `tenant.created`, emitir `usage.metric`/`audit.action`)
4. Shared libs `agn-core`/`agn-auth`/`agn-middleware`/`agn-audit` (hoje código duplicado local)
5. SubscriptionMiddleware para gating por plano/feature
6. OAuth Google/Microsoft + MFA TOTP
7. Frontend padrão `agn-ui` (ProductSwitcher, AuthContext, httpClient com refresh)
8. Database próprio isolado (`sil_proposta_db`) e repositório separado (`sil-proposta-app/`)
9. RAG real com Qdrant + geradores DAM/WP (migrar do Porposta Full e descontinuar legado)

**Recomendação macro**: consolidar tudo em **`sil-proposta-app/`** (renomeado de `sap-proposal-app/`), aplicar 7 ondas de ajuste, descontinuar `Porposta Full/` ao final.

---

## 1. Comparação As-Is vs Plataforma SaaS v2

### 1.1 Tabela de Gaps

| Dimensão | Plataforma SaaS v2 (target) | sap-proposal-app atual | Porposta Full atual | Gap |
|----------|------------------------------|------------------------|---------------------|-----|
| **Multi-tenant** | Bridge model: Pool no Portal, Silo lógico (DB-per-product) | TenantMixin presente; DB único `sap_proposal` | Não existe | 🟡 Falta DB próprio isolado |
| **Multi-empresa** | Tenant → Company → User (N:N via user_company_access) + roles por company | Implementado nos models | Não existe | ✅ OK |
| **Hierarquia roles** | `super_admin`, `platform_admin`, `tenant_admin`, `<produto>:admin/editor/viewer` | `owner/admin/editor/viewer` + `is_platform_admin` flag | Nenhum | 🟡 Falta roles por produto no JWT |
| **JWT** | RS256, chave privada no Portal, JWKS público em `/.well-known/jwks.json` | HS256 local com `JWT_SECRET` no .env | Nenhum | 🔴 Crítico — incompatível federação |
| **Claims JWT** | `{ sub, email, tenant_id, products[], roles{by_product} }` | `{ sub, email, tenant_id, role, is_platform_admin }` | N/A | 🔴 Falta `products[]` e `roles{by_product}` |
| **Auth providers** | local + Google OAuth + Microsoft OAuth + MFA TOTP | local + bcrypt apenas (campo `auth_provider` existe mas só "local") | Nenhum | 🔴 Faltam OAuth e MFA |
| **Shared libs** | `agn-core`, `agn-auth`, `agn-middleware`, `agn-audit`, `agn-billing`, `agn-ui` (npm/pip ou submodule) | Código duplicado em `core/` (mixins, security, trace_middleware) | N/A | 🟡 Aceitável no MVP, refatorar onda 4 |
| **Contrato `POST /api/v1/integrations/portal/provision`** | Obrigatório, validado por HMAC do Portal | Ausente | Ausente | 🔴 Crítico |
| **Contrato `POST /api/v1/integrations/portal/deprovision`** | Obrigatório (soft delete tenant) | Ausente | Ausente | 🔴 Crítico |
| **Contrato `GET /api/v1/dashboard/summary`** | Obrigatório (Portal faz fan-out paralelo, cache 60s) | Ausente | Ausente | 🔴 Crítico |
| **Contrato `GET /health`** | Obrigatório com status dependências | `/health` simples (DB only) presente | `/health` simples | 🟡 Enriquecer com Redis, Qdrant, Portal |
| **Contrato `POST /api/v1/lgpd/delete-tenant`** | Obrigatório (LGPD compliance) | Ausente | Ausente | 🔴 Crítico para produção |
| **Contrato `POST /api/v1/lgpd/export-tenant`** | Obrigatório | Ausente | Ausente | 🔴 Crítico para produção |
| **Contrato `POST /api/v1/backup/snapshot`** | Obrigatório (Portal coordena) | Ausente | Ausente | 🟡 Pode ser onda posterior |
| **Contrato `POST /api/v1/restore`** | Obrigatório | Ausente | Ausente | 🟡 Pode ser onda posterior |
| **Eventos consumidos** | Redis Streams: `tenant.created`, `tenant.suspended`, `subscription.upgraded`, `user.role_changed` | Nenhum consumer | Nenhum | 🔴 Crítico — sem isso, tenant criado no Portal nunca aparece no produto |
| **Eventos emitidos** | `usage.metric`, `audit.action`, `health.degraded`, `tenant.feature_used` | Nenhum publisher | Nenhum | 🔴 Crítico para billing usage-based + auditoria |
| **Audit central** | `POST /api/portal/audit/events` (fire-and-forget) | Model `AuditLog` local existe, mas não publica | Não existe | 🟡 Implementar publisher |
| **SubscriptionMiddleware** | Gating de features baseado em plano/limite | Ausente (campos `plan_slug`, `features` existem em `Tenant`, mas não há middleware) | N/A | 🔴 Crítico — sem gating, todo tenant tem acesso total |
| **Stack backend** | Python 3.11+ / FastAPI / SQLAlchemy / Alembic | ✅ Python + FastAPI + SQLAlchemy + Alembic | Python + FastAPI sem ORM | ✅ OK em sap-proposal-app |
| **Stack frontend** | React 19 + Vite 7 + Tailwind + shadcn/ui + i18next | React + Vite + Tailwind + TS (versões a confirmar) + i18n próprio | HTML/JS vanilla 1686 linhas | ✅ Estrutura OK; verificar versões React 19 / Vite 7 |
| **Banco** | Postgres 16, **DB lógico próprio por produto** | Postgres `sap_proposal` (compartilhado?) | SQLite/PostgreSQL | 🟡 Garantir DB próprio `sil_proposta_db` |
| **Cache/Sessão** | Redis 7 namespaced (`<produto>:*`) | Redis configurado mas uso atual incerto | Nenhum | 🟡 Padronizar namespace `sil_proposta:*` |
| **Busca semântica** | Qdrant 1.12+, coleções nomeadas | Qdrant configurado em `Settings` (`QDRANT_URL`, `QDRANT_COLLECTION_PREFIX`) mas RAG real não conectado | RAG **fake** (hash-based, 26 docs hardcoded em `agents/rag.py`) | 🔴 Migrar RAG do legado e plugar Qdrant real |
| **Geração de propostas** | (próprio do produto) | `services/sap_proposal/generation_service.py` em desenvolvimento | `agents/orchestrator.py`, `agents/orchestrator_v5.py`, `demo_engine.py`, `generators/dam.py`, `generators/wp.py` | 🟡 Migrar geradores DAM/WP e orchestrator do Porposta Full para sap-proposal-app |
| **Rate limiting** | SlowAPI + Nginx | SlowAPI configurado | Nenhum | ✅ OK |
| **Trace ID** | Header `X-Trace-ID` end-to-end | TraceMiddleware presente | Nenhum | ✅ OK |
| **Logging estruturado** | structlog JSON + tags `service/tenant_id/trace_id` | structlog configurado | logging stdlib | ✅ OK; validar tags |
| **Repositório** | Cada produto em repo próprio `<produto>-app/` | Está dentro do monorepo `sil-proposta` | Está dentro do monorepo `sil-proposta` | 🟡 Decisão: manter monorepo no MVP ou separar |
| **Naming/canônico** | Slug do produto consistente (`sil-proposta` no Portal) | Pasta `sap-proposal-app/`, settings `APP_NAME=sap_proposal` | Pasta `Porposta Full/` (typo) | 🔴 Renomear para `sil-proposta` consistente |
| **Pasta legada** | N/A | N/A | Existe — `Porposta Full/` confunde colaboradores e tem código duplicado (`main[1].py`, `database[1].py`) | 🔴 Descontinuar |

### 1.2 Resumo numérico

- **9 gaps críticos (🔴)**: precisam ser resolvidos para o produto ser publicável no Portal SaaS v2
- **9 gaps menores (🟡)**: aceitáveis no MVP, mas devem ser endereçados antes de GA
- **8 itens já alinhados (✅)**: aproveitar e não tocar

---

## 2. Decisões Arquiteturais (ADRs deste plano)

### ADR-LP-001: `sap-proposal-app/` é a base, `Porposta Full/` será descontinuado
**Contexto**: duas implementações coexistem, com código duplicado e arquiteturas incompatíveis.
**Decisão**: toda evolução acontece em `sap-proposal-app/`. `Porposta Full/` entra em modo "extract & retire" — só serve como fonte de funcionalidades a portar (RAG, DAM, WP, scrapers).
**Consequência**: contribuições novas no `Porposta Full/` ficam proibidas a partir da Onda 0.

### ADR-LP-002: renomear para `sil-proposta-app/` (canônico da plataforma)
**Contexto**: o Portal e o documento [`ARCHITECTURE_PORTAL_SAAS_v2.md`](./ARCHITECTURE_PORTAL_SAAS_v2.md) usam o padrão `<produto>-app/`. Hoje o código está em `sap-proposal-app/` mas o produto é referenciado externamente como `sil-proposta`.
**Decisão**: renomear pasta, settings (`APP_NAME=sil_proposta`), domínio (`sil-proposta.ai-garage.com.br`), DB (`sil_proposta_db`), Redis namespace (`sil_proposta:*`), Qdrant prefix (`sil_proposta`).
**Consequência**: alinhamento total com o resto da plataforma; trade-off é ter que rodar migration de rename no DB existente (se houver).

### ADR-LP-003: adotar shared libs `agn-*` via git submodule no MVP
**Contexto**: o documento referência manda usar `agn-core`, `agn-auth`, `agn-middleware`, `agn-audit`, mas instalar via Pip privado leva tempo.
**Decisão**: criar pasta `shared/` como **git submodule** apontando para o repo `agn-shared` (path interno). MVP usa `pip install -e ../shared/agn-core` etc. Plus tarde: pacotes Pip privados.
**Consequência**: dependência de existir o repo `agn-shared` — se ainda não existir, criar primeiro como pré-requisito.

### ADR-LP-004: JWT RS256 + JWKS validation contra Portal (matar HS256 local)
**Contexto**: HS256 com chave compartilhada exige sincronizar segredo entre todos os produtos — viola §6 do doc referência.
**Decisão**: `sil-proposta-app/` valida tokens **lendo JWKS público do Portal** (`{PORTAL_URL}/.well-known/jwks.json`), cache 24h, RS256.
**Consequência**: o produto **NÃO emite tokens** — só valida. Login passa pelo Portal (`POST {PORTAL_URL}/auth/login`) que retorna JWT assinado por RS256. Endpoint `/auth/login` local pode ser mantido como fallback durante a migração e depois removido.

### ADR-LP-005: Database próprio isolado (`sil_proposta_db`), zero acesso cross-product
**Contexto**: o doc referência (§13, ADR-010) proíbe cross-product DB FK.
**Decisão**: a `sil-proposta-app/` tem seu próprio Postgres database (lógico ou cluster, conforme tenant). Não há FK para `tenants` ou `companies` do Portal — esses dados são **replicados localmente** via consumer de eventos `tenant.created`/`company.created`.
**Consequência**: a tabela local `tenants` é **réplica eventually-consistent** do Portal. Conflito de "source of truth" resolvido com regra: Portal é mestre, produto refresca por evento.

### ADR-LP-006: subscription gating é responsabilidade do produto via SubscriptionMiddleware
**Contexto**: Portal cobra, mas produto precisa **respeitar** os limites (max_proposals_per_month, features ativadas).
**Decisão**: implementar `SubscriptionMiddleware` que lê o JWT claim `products[]` (ou consulta cache local) e bloqueia 402 Payment Required quando o tenant não tem acesso ao produto/feature.
**Consequência**: cada endpoint deve declarar `@requires_feature("rag_advanced")` quando aplicável.

### ADR-LP-007: monorepo permanecível no MVP, separar repositório só na Onda 7
**Contexto**: separar agora atrasa onda 0–4 sem ganho real.
**Decisão**: durante ondas 0–6, manter `sil-proposta-app/` dentro de `sil-proposta` (monorepo atual). Na Onda 7, mover para repo próprio com `git subtree split`.
**Consequência**: o CI/CD da Onda 1–6 roda no monorepo; pipeline final será migrado.

---

## 3. Plano de Ajuste em Ondas

> **Convenção**: cada onda termina com **critérios de aceitação verificáveis** (testes ou manual). Estimativas em semanas-pessoa para 1 dev sênior full-time.

### Onda 0 — Consolidação e Rename (1 semana)

**Objetivo**: parar a sangria, eleger `sil-proposta-app/` como única base, renomear.

| # | Tarefa | Arquivo/Comando |
|---|--------|-----------------|
| 0.1 | Renomear `sap-proposal-app/` → `sil-proposta-app/` | `git mv` |
| 0.2 | Trocar `APP_NAME=sap_proposal` → `sil_proposta` | [`backend/core/config.py`](../../sap-proposal-app/backend/core/config.py) |
| 0.3 | Trocar `DATABASE_URL` default para `sil_proposta` | mesmo arquivo |
| 0.4 | Renomear `QDRANT_COLLECTION_PREFIX=sap_proposal` → `sil_proposta` | mesmo arquivo |
| 0.5 | Renomear `SMTP_FROM=noreply@sap-proposal...` → `noreply@sil-proposta...` | mesmo arquivo |
| 0.6 | Renomear `models/sap_proposal/` → `models/sil_proposta/` (e imports) | grep + sed |
| 0.7 | Renomear `services/sap_proposal/` → `services/sil_proposta/` | grep + sed |
| 0.8 | Renomear `apis/v1/sap_proposal/` → `apis/v1/sil_proposta/` | grep + sed |
| 0.9 | Adicionar `[ARCHIVED]` no [`Porposta Full/README.md`](../README.md) e proibir novas commits via `.github/CODEOWNERS` | manual |
| 0.10 | Atualizar `Porposta Full/backend/docs/plans/pending/ARCHITECTURE_SAP_PROPOSAL.md` para `[SUPERSEDED by PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md]` | edit |

**Critérios de aceitação**:
- ✅ `grep -r "sap_proposal\|sap-proposal" sil-proposta-app/` retorna 0 ocorrências (exceto histórico git)
- ✅ Backend sobe localmente (`uvicorn main:app`) e responde `GET /health`
- ✅ Frontend builda (`npm run build`)
- ✅ README do Porposta Full diz "ARCHIVED — see sil-proposta-app/"

---

### Onda 1 — JWT RS256 + JWKS contra Portal (1–2 semanas)

**Objetivo**: parar de assinar tokens local; validar contra Portal via JWKS.

| # | Tarefa | Arquivo |
|---|--------|---------|
| 1.1 | Adicionar setting `PORTAL_URL=https://portal.ai-garage.com.br` | [`core/config.py`](../../sap-proposal-app/backend/core/config.py) |
| 1.2 | Adicionar setting `JWT_ALGORITHM=RS256`, remover `JWT_SECRET` | mesmo arquivo |
| 1.3 | Implementar `core/jwks.py`: client async que faz `GET {PORTAL_URL}/.well-known/jwks.json`, cacheia 24h em Redis | novo |
| 1.4 | Refatorar `core/security.py::decode_token()` para validar RS256 com JWK do Portal (usar `python-jose` ou `pyjwt[crypto]`) | [`core/security.py`](../../sap-proposal-app/backend/core/security.py) |
| 1.5 | Remover funções `create_access_token()` e `create_refresh_token()` (Portal emite) | mesmo arquivo |
| 1.6 | Atualizar `apis/v1/auth.py`: deprecar `/login` local; adicionar `/me` que apenas decodifica JWT do Portal | [`apis/v1/auth.py`](../../sap-proposal-app/backend/apis/v1/auth.py) |
| 1.7 | Estender JWT claim parsing para `products[]` e `roles{by_product}` | `core/security.py` |
| 1.8 | Adicionar dependency `require_product("sil_proposta")` que checa se o tenant tem o produto no claim | novo módulo `core/permissions.py` |
| 1.9 | Frontend: remover login local, redirecionar para `{PORTAL_URL}/login?redirect=...` | [`frontend/src/pages/LoginPage.tsx`](../../sap-proposal-app/frontend/src/pages/LoginPage.tsx) |
| 1.10 | Frontend: implementar refresh automático via httpClient (Axios interceptor) chamando `{PORTAL_URL}/auth/refresh` | `frontend/src/lib/httpClient.ts` (novo) |
| 1.11 | Tests: validar que token HS256 antigo **não** é mais aceito; validar token RS256 do Portal é aceito; validar `require_product` bloqueia 403 se produto ausente | `tests/test_auth_jwks.py` |

**Critérios de aceitação**:
- ✅ Token HS256 falha com 401 "invalid algorithm"
- ✅ Token RS256 emitido pelo Portal valida com sucesso
- ✅ Token sem `products: ["sil_proposta"]` recebe 403 nos endpoints `/api/v1/proposals/*`
- ✅ JWKS é cacheado em Redis com TTL 24h (verificar via `redis-cli ttl jwks:portal`)
- ✅ Frontend redireciona para Portal quando JWT expira

---

### Onda 2 — Contratos Portal (provision/deprovision/dashboard/lgpd) (2 semanas)

**Objetivo**: implementar os endpoints obrigatórios que o Portal chama.

| # | Tarefa | Arquivo |
|---|--------|---------|
| 2.1 | Criar `apis/v1/integrations/portal.py` com router `/api/v1/integrations/portal/*` | novo |
| 2.2 | Implementar `POST /provision` validando HMAC do Portal (header `X-Portal-Signature`) | mesmo |
| 2.3 | `POST /provision` cria `Tenant` local com defaults (plano, features) e dispara seed de Company default | mesmo |
| 2.4 | Implementar `POST /deprovision` (soft delete: marca `tenants.suspended_at`) | mesmo |
| 2.5 | Criar `apis/v1/dashboard/summary.py` retornando: `{ total_proposals, proposals_by_status, last_30d_count, mrr_contribution_estimate, last_activity_at }` | novo |
| 2.6 | Cache do summary em Redis 60s | mesmo |
| 2.7 | Criar `apis/v1/lgpd.py` com `POST /delete-tenant` (hard delete: cascata tudo do tenant) e `POST /export-tenant` (gera ZIP com JSON + arquivos do tenant) | novo |
| 2.8 | Enriquecer `GET /health`: testar Postgres + Redis + Qdrant + JWKS reachability; retornar `{ status, dependencies: { postgres, redis, qdrant, portal } }` | [`main.py`](../../sap-proposal-app/backend/main.py) |
| 2.9 | (Stretch) `POST /api/v1/backup/snapshot` e `POST /api/v1/restore` (pg_dump → S3, restore com preview) | novo |
| 2.10 | Tests de cada endpoint, incluindo: HMAC inválido → 401; provision idempotente; export gera ZIP válido | `tests/test_portal_contracts.py` |

**Critérios de aceitação**:
- ✅ Portal consegue chamar `POST /provision` e ver Tenant criado no DB do produto
- ✅ `GET /api/v1/dashboard/summary` retorna em <500ms (cache hit) e <2s (cache miss)
- ✅ `POST /lgpd/delete-tenant` apaga 100% das proposals, companies, users do tenant
- ✅ `GET /health` reporta degradação se Qdrant cair
- ✅ HMAC inválido em `/provision` retorna 401

---

### Onda 3 — Eventos Redis Streams + Audit Central (1 semana)

**Objetivo**: tornar o produto reativo aos eventos do Portal e parar de fazer "polling" mental.

| # | Tarefa | Arquivo |
|---|--------|---------|
| 3.1 | Criar `core/events/consumer.py`: worker assíncrono que faz `XREADGROUP portal.events sil-proposta-consumers c1` | novo |
| 3.2 | Implementar handlers para: `tenant.created`, `tenant.suspended`, `subscription.upgraded`, `user.role_changed`, `company.created` | mesmo |
| 3.3 | Criar `core/events/publisher.py`: helper `publish_event(stream, type, payload)` | novo |
| 3.4 | Emitir `usage.metric` em cada `POST /api/v1/proposals` (proposta gerada) | [`apis/v1/sap_proposal/proposals.py`](../../sap-proposal-app/backend/apis/v1/sap_proposal/proposals.py) |
| 3.5 | Emitir `audit.action` em ações sensíveis (login, delete, export, mudança de role) | múltiplos |
| 3.6 | Substituir gravação em `audit_logs` local por chamada `POST {PORTAL_URL}/api/portal/audit/events` (fire-and-forget) — deletar tabela local na Onda 4 | `services/audit_service.py` (novo) |
| 3.7 | Worker de eventos roda como processo separado (`python -m core.events.consumer`) ou background task no `main.py` lifespan | `main.py` |
| 3.8 | Tests: simular `XADD portal.events` com `tenant.created` → tenant local criado | `tests/test_events_consumer.py` |

**Critérios de aceitação**:
- ✅ Quando Portal emite `tenant.created`, o tenant aparece em `sil_proposta_db.tenants` em <5s
- ✅ `usage.metric` emitido com cada proposta (verificar com `XRANGE produtos.events`)
- ✅ Portal recebe `POST /api/portal/audit/events` ao logar (verificar logs do Portal)
- ✅ Consumer reinicia sem perder mensagens (consumer group pendentes processados)

---

### Onda 4 — Shared Libs `agn-*` + Limpeza (2 semanas)

**Objetivo**: parar de duplicar código que é comum à plataforma.

| # | Tarefa | Arquivo |
|---|--------|---------|
| 4.1 | Adicionar `shared/` como git submodule apontando para `agn-shared` (criar repo se não existir) | `.gitmodules` |
| 4.2 | Mover `models/mixins.py` (UUIDMixin, TimestampMixin, TenantMixin) → `agn-core` | refactor |
| 4.3 | Mover `core/security.py` (JWT, password) → `agn-auth` | refactor |
| 4.4 | Mover `core/trace_middleware.py` → `agn-middleware` | refactor |
| 4.5 | Mover `core/logger.py` (structlog setup) → `agn-core` | refactor |
| 4.6 | Mover `services/audit_service.py` (publisher) → `agn-audit` | refactor |
| 4.7 | `pyproject.toml` adicionar `agn-core`, `agn-auth`, `agn-middleware`, `agn-audit` como dependências locais (`pip install -e ../shared/agn-*`) | `pyproject.toml` |
| 4.8 | Remover arquivos duplicados; substituir imports `from core.security` → `from agn_auth` | grep + sed |
| 4.9 | Drop tabela `audit_logs` local na migration (auditoria agora central no Portal) | nova alembic migration |
| 4.10 | Frontend: adicionar pacote `agn-ui` (npm) ou submodule equivalente; usar `<AuthContext>`, `<ProtectedRoute>`, `httpClient` | `frontend/package.json` |

**Critérios de aceitação**:
- ✅ `find sil-proposta-app/backend -name mixins.py` retorna 0
- ✅ Suite de testes ainda passa após substituições de import
- ✅ `pyproject.toml` declara as 4 deps `agn-*`
- ✅ Frontend usa `<AuthContext>` do `agn-ui`

---

### Onda 5 — Migrar RAG Real (Qdrant) + Geradores DAM/WP do Legado (2 semanas)

**Objetivo**: parar de usar o RAG fake e o orchestrator do `Porposta Full/`; trazer o que tem valor para o app novo.

| # | Tarefa | Arquivo origem (legado) | Arquivo destino |
|---|--------|--------------------------|-----------------|
| 5.1 | Portar `agents/orchestrator_v5.py` para `services/sil_proposta/agents/orchestrator.py` (com TenantMixin nas execuções) | [`Porposta Full/backend/agents/orchestrator_v5.py`](../backend/agents/orchestrator_v5.py) | novo |
| 5.2 | Portar `generators/dam.py` (Word) para `services/sil_proposta/export/dam_generator.py` | `Porposta Full/backend/generators/dam.py` | novo |
| 5.3 | Portar `generators/wp.py` (Excel) para `services/sil_proposta/export/wp_generator.py` | `Porposta Full/backend/generators/wp.py` | novo |
| 5.4 | Substituir `agents/rag.py` (in-memory fake) por novo `services/sil_proposta/rag/qdrant_rag.py` que usa Qdrant real | `Porposta Full/backend/agents/rag.py` | novo |
| 5.5 | Pipeline de ingestão: ler `data/proposals.json` + `data/legislation/*` (do legado) e indexar no Qdrant com embeddings (modelo a definir, ex: voyage-3 ou OpenAI text-embedding-3-large via Portal) | múltiplos |
| 5.6 | Adicionar setting `RAG_EMBEDDING_PROVIDER=portal` (Portal proxia LLM/embeddings) | `core/config.py` |
| 5.7 | Atualizar `KnowledgeDocument` model para refletir source/checksum/embedding_status | [`models/sap_proposal/knowledge_document.py`](../../sap-proposal-app/backend/models/sap_proposal/knowledge_document.py) |
| 5.8 | Tests: ingestar 5 docs sample, query "férias UF SP" retorna doc relevante com score >0.7 | `tests/test_rag_qdrant.py` |
| 5.9 | Anonimização: aplicar regras de anonimização (CNPJ, CPF, nomes próprios) **antes** de enviar para Portal/Anthropic — alinhar com requisitos LGPD do tenant | novo `services/sil_proposta/anonymization/` |

**Critérios de aceitação**:
- ✅ Orchestrator gera proposta usando Qdrant real (não hash fake)
- ✅ `services/sil_proposta/export/` produz DAM Word + WP Excel idênticos aos do legado em testes de regressão (3 propostas seed)
- ✅ Documentos com CPF/CNPJ são anonimizados antes de sair do produto
- ✅ Query semântica em base de 50+ docs retorna em <1s

---

### Onda 6 — OAuth, MFA, Frontend Padrão `agn-ui` (2 semanas)

**Objetivo**: subir o nível de auth e padronizar UX com a plataforma.

| # | Tarefa | Arquivo |
|---|--------|---------|
| 6.1 | OAuth Google: implementação NÃO é local — Portal cuida; produto só recebe JWT com `auth_provider=google` no claim | (zero código no produto, doc atualizada) |
| 6.2 | OAuth Microsoft: idem | (zero código) |
| 6.3 | MFA TOTP: idem (Portal valida) | (zero código) |
| 6.4 | Frontend: adicionar `<ProductSwitcher />` do `agn-ui` no header (mostra outros produtos do tenant) | `frontend/src/layouts/MainLayout.tsx` |
| 6.5 | Frontend: aplicar branding dinâmico (cores, logo) lido do `tenant.branding` | mesmo |
| 6.6 | Frontend: i18n hierárquico (tenant > company > user > default) | `frontend/src/i18n/index.ts` |
| 6.7 | Dark mode toggle (CSS variables centralizadas) | global |
| 6.8 | Subscription gating no frontend: ocultar botão "Gerar Proposta" se `tenant.usage.proposals_this_month >= tenant.max_proposals_per_month` | `frontend/src/pages/IntakeForm.tsx` |

**Critérios de aceitação**:
- ✅ Login via Google funciona (testado em staging com Portal real)
- ✅ Tenant de plano "trial" vê banner de upgrade e botão de gerar proposta desabilitado ao atingir limite
- ✅ Header mostra logo do tenant
- ✅ ProductSwitcher mostra "Sil-Proposta" + outros produtos contratados

---

### Onda 7 — Descontinuar `Porposta Full/` + Repo Próprio (1 semana)

**Objetivo**: dar tchau ao legado e (opcionalmente) separar o repositório.

| # | Tarefa |
|---|--------|
| 7.1 | Confirmar que **nada** em produção ainda aponta para `Porposta Full/` (verificar Railway, Vercel, DNS) |
| 7.2 | `git rm -r 'Porposta Full/'` (manter histórico via tag `legacy/porposta-full-final`) |
| 7.3 | `git subtree split --prefix=sil-proposta-app -b sil-proposta-only` |
| 7.4 | Push da branch `sil-proposta-only` para novo repo `ai-garage/sil-proposta-app` |
| 7.5 | CI/CD migrado: GitHub Actions, Cloud Run deploy, secret rotation |
| 7.6 | DNS `sil-proposta.ai-garage.com.br` → Cloud Run service novo |
| 7.7 | Atualizar entry no Portal `products` table: `slug=sil-proposta`, `wizard_steps=[...]`, `webhook_secret=<rotated>` |
| 7.8 | Smoke test end-to-end: criar tenant via Portal → produto provisionado → proposta gerada → audit no Portal |

**Critérios de aceitação**:
- ✅ Pasta `Porposta Full/` não existe mais no `main`
- ✅ Tag `legacy/porposta-full-final` aponta para o último commit válido
- ✅ Smoke test passa em staging (provision → proposal → audit)

---

## 4. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|----------------|---------|-----------|
| **Portal não existe ainda em produção** | Alta | Alto | Mockar Portal em staging com Wiremock + chave RS256 fake durante Onda 1–3; integrar real só na Onda 7 |
| **`agn-shared` não existe ainda como repo** | Alta | Médio | Criar como pré-requisito; se atrasar, na Onda 4 manter código duplicado e fazer extração depois |
| **Migração de DB existente (rename `sap_proposal` → `sil_proposta`)** | Média | Alto | Se já há dados em produção: criar script `pg_dump` + restore para nova DB; coordenar janela com usuários |
| **Anonimização (Onda 5.9) impacta qualidade da proposta gerada (memória [DAM Quality Gap](../../../C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-sil-proposta\memory\feedback_dam_quality.md))** | Alta | Alto | Anonimizar **só** o que sai do tenant; manter dados completos no DB do tenant. Validar qualidade com 5 propostas reais antes de habilitar em prod. |
| **Subestimação de esforço (memória [Upgrade Proposal Gap](../../../C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-sil-proposta\memory\feedback_upgrade_proposal.md))** | Alta | Médio | Estimativas em semanas-pessoa são otimistas; multiplicar por 1.5x para projeto realista |
| **Refresh token endpoint do Portal não pronto** | Média | Médio | Onda 1 pode usar long-lived JWT (24h) temporariamente; refactor quando Portal pronto |
| **Eventos Redis Streams sem consumer ack adequado** | Média | Alto | Usar `XACK` explícito após handler succeed; reprocessar mensagens pendentes no startup |

---

## 5. Dependências Externas (bloqueadores)

1. **Portal SaaS v2 deployado** (mesmo que em staging) com `/auth/login`, `/.well-known/jwks.json`, `/api/portal/audit/events`, `POST` HMAC para `/integrations/portal/provision`
2. **Repositório `agn-shared`** com pelo menos `agn-core` e `agn-auth` publicáveis
3. **Stream Redis `portal.events`** existente com producer no Portal emitindo `tenant.created`, etc.
4. **Stripe webhook do Portal** funcionando para `subscription.upgraded` (alimenta o stream)
5. **Cloud Run / Cloudflare DNS** com permissão de criar serviço novo

---

## 6. Critérios de "Pronto para Produção" (Definition of Done)

Apenas quando **todos** os critérios abaixo passam, o sil-proposta pode ser publicado no catálogo do Portal:

- [ ] JWT RS256 + JWKS funcionando, HS256 morto (Onda 1)
- [ ] 5 contratos Portal implementados: `provision`, `deprovision`, `dashboard/summary`, `lgpd/delete-tenant`, `lgpd/export-tenant` (Onda 2)
- [ ] `/health` reporta status real de Postgres + Redis + Qdrant + Portal (Onda 2)
- [ ] Consumer Redis processa `tenant.created`, `subscription.upgraded` em <5s (Onda 3)
- [ ] Eventos `usage.metric` e `audit.action` emitidos corretamente (Onda 3)
- [ ] Shared libs `agn-core`/`agn-auth`/`agn-middleware`/`agn-audit` em uso (Onda 4)
- [ ] RAG real Qdrant + anonimização antes de export (Onda 5)
- [ ] OAuth + MFA via Portal funcionam (Onda 6)
- [ ] SubscriptionMiddleware bloqueia 402 quando feature/limite excedido (Onda 6)
- [ ] `Porposta Full/` removido (Onda 7)
- [ ] Isolation tests passam: tenant A não vê dados de tenant B (qualquer onda)
- [ ] Smoke test end-to-end passa em staging (Onda 7)
- [ ] Documentação `README.md` do `sil-proposta-app/` atualizada com setup, contratos, eventos
- [ ] Runbook em `docs/runbooks/` para: provision manual, restaurar tenant deletado, recuperar consumer pendente

---

## 7. Estimativa Total e Sequenciamento

| Onda | Esforço (1 dev) | Pode paralelizar? |
|------|-----------------|-------------------|
| 0    | 1 semana | Não (bloqueador de tudo) |
| 1    | 1–2 semanas | Não (depende de 0) |
| 2    | 2 semanas | Pode iniciar contratos em paralelo com 1 |
| 3    | 1 semana | Pode iniciar em paralelo com 2 |
| 4    | 2 semanas | Bloqueada por 1, 2, 3 (precisa shared libs estáveis) |
| 5    | 2 semanas | Pode rodar **em paralelo** com 4 (dev separado) |
| 6    | 2 semanas | Depende de 1, 4 |
| 7    | 1 semana | Final |

**Total sequencial:** 12 semanas (3 meses) com 1 dev sênior.
**Total com 2 devs em paralelo:** 8–9 semanas.

⚠️ **Calibração realista** (memória [Upgrade Proposal Gap](../../../C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-sil-proposta\memory\feedback_upgrade_proposal.md)): multiplicar por 1.5x para imprevistos. **Prazo recomendado: 4–5 meses.**

---

## 8. Próximos Passos Imediatos

1. **Aprovação deste plano** — confirmar ADRs LP-001 a LP-007
2. **Validar pré-requisitos** com time da plataforma:
   - Portal SaaS v2 está em qual estado? (não-existente, em dev, staging, prod)
   - Repo `agn-shared` existe?
   - Eventos `portal.events` no Redis estão sendo emitidos?
3. **Spawn da Onda 0** assim que respondido item 1
4. **Setup de Wiremock** para Portal mockado (Onda 1) caso Portal real não esteja pronto

---

## 9. Anexos

### 9.1 Mapeamento de Arquivos do Legado a Migrar (Onda 5)

| Legado | Status | Ação |
|--------|--------|------|
| `Porposta Full/backend/agents/orchestrator_v5.py` | Mais recente, melhor que v1 | Portar |
| `Porposta Full/backend/agents/orchestrator.py` | Antigo | Descartar |
| `Porposta Full/backend/agents/rag.py` | RAG fake hash-based | Substituir por Qdrant |
| `Porposta Full/backend/agents/catalog.py` | Catálogo de agentes | Portar como `services/sil_proposta/agents/catalog.py` |
| `Porposta Full/backend/generators/dam.py` | Gerador Word | Portar como `services/sil_proposta/export/dam_generator.py` |
| `Porposta Full/backend/generators/wp.py` | Gerador Excel | Portar como `services/sil_proposta/export/wp_generator.py` |
| `Porposta Full/backend/demo_engine.py` | Fallback determinístico | Portar como `services/sil_proposta/demo_engine.py` (já existe parcial em `demo_generation_service.py` — consolidar) |
| `Porposta Full/backend/scraper.py` | Scrapers de legislação | Portar como `services/sil_proposta/scrapers/` |
| `Porposta Full/backend/data/*.json` | Dados sample | Migrar para fixtures de teste + seed do Qdrant |
| `Porposta Full/backend/main[1].py`, `database[1].py`, `demo_engine[1].py` | Duplicatas espúrias | **Deletar** (são downloads duplicados do navegador) |
| `Porposta Full/backend/index.html`, `index[1].html`, `agents-viz.html` | HTML legado | **Deletar** (substituído pelo React/Vite) |
| `Porposta Full/frontend/index.html`, `agents-viz.html` | Mais HTML legado | **Deletar** |

### 9.2 Glossário

- **Control Plane (Portal)**: SaaS central que gerencia tenants, billing, auth, catálogo
- **Application Plane (Produto)**: aplicação de domínio (sil-proposta, scheduling, etc.)
- **Bridge Isolation Model**: Pool no control plane + Silo lógico (DB-per-product) nos produtos
- **Tenant**: cliente raiz da plataforma (consultoria SAP, ex: Cast Group)
- **Company**: cliente final do tenant (empresa com CNPJ que receberá a proposta)
- **JWKS**: JSON Web Key Set publicado pelo Portal em `/.well-known/jwks.json` para validar tokens RS256
- **Provision/Deprovision**: ciclo de criação/desativação de tenant local quando Portal sinaliza
- **`agn-*`**: shared libs da AI Garage (`agn-core`, `agn-auth`, `agn-middleware`, `agn-audit`, `agn-billing`, `agn-ui`)

---

**Fim do plano.**
