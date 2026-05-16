# Plano de Migração — PropostAI

**Versão:** 1.0
**Data:** 2026-05-15
**Responsável técnico:** Rogerio Ribeiro (Direto ao Ponto / AI Garage)
**Status do produto na plataforma:** em-migração (Onda 0 concluída; Onda 1 a iniciar)
**Guia de referência:** [`/docs/ARCHITECTURE_PORTAL_SAAS_v3.md`](../../docs/ARCHITECTURE_PORTAL_SAAS_v3.md)

> Substitui o plano anterior `PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md` (escrito contra v2 do guia). Este documento usa o **template do Apêndice D do v3** preenchido com as decisões reais já tomadas e as pendentes.

---

## 1. Identidade do produto

| Campo | Valor |
|---|---|
| Nome humano | PropostAI |
| Slug canônico | `propostai` |
| Domínio PRD | `propostai.ai-garage.com.br` |
| Domínio DEV | `propostai.dev.ai-garage.com.br` |
| Database | `propostai` (renomear para `propostai_db` quando migrar pro cluster compartilhado) |
| Coleção Qdrant | `propostai_kb` |
| Stream Redis | `propostai:events` |

---

## 2. Origem do código

| Campo | Valor |
|---|---|
| Repo de origem (atual) | `github.com/aigarage2026/propostai` (monorepo) |
| Branch base | `main` |
| Stack atual | FastAPI + SQLAlchemy 2 + Alembic + asyncpg / React 19 + Vite 7 + Tailwind + TypeScript / Postgres 16 + Redis 7 + Qdrant 1.12 |
| Em produção hoje? | **Não.** O monolito legado (Railway + Vercel) está em [`/legacy/propostai-monolith/`](../../legacy/propostai-monolith/), não tem deploy ativo |
| Volume estimado de dados | Zero (greenfield + seed do tenant Direto ao Ponto Demo) |

---

## 3. Decisões fechadas (cópia da §4.5 do guia v3)

### 3.1 Grupo A — Acesso

| # | Decisão | Valor |
|---|---|---|
| A1 | Acesso ao `agent-hub` de referência | **PENDENTE** — não localizei o repo. Tentei `github.com/ai-garage` (vazio) e `github.com/aigarage2026` (6 repos, nenhum com `agent` ou `portal`). Provável que esteja em org privada (`ai-garage-inf` está vazia). **Risco:** sem o código de referência, podemos divergir do padrão. |
| A2 | Repo de origem | `github.com/aigarage2026/propostai` |
| A3 | Branch base | `main` |
| A4 | Validador técnico | Rogerio Ribeiro |

### 3.2 Grupo B — Dependências da plataforma (cruzando com §1.5 do guia)

| # | Componente | Status §1.5 | Decisão deste produto |
|---|---|---|---|
| B1 | `agn-shared` (Python: `agn-core`, `agn-auth`, `agn-billing`, `agn-middleware`, `agn-audit`) | 🟡 Em construção | **Fallback:** código copiado/duplicado dentro do `propostai-app/backend/` (já é o caso). Refatorar para `agn-shared` quando estável (Onda 4 — postergada). |
| B2 | `agn-portal` (control plane) | 🟡 Em construção, parcialmente operacional | **Fallback:** Wiremock para mock de Portal API; auth local HS256 mantido até cutover. |
| B3 | JWT RS256 + JWKS público | 🔴 Planejado | **Fallback:** **HS256 atual mantido** com flag `JWT_LEGACY_MODE=true` para sinalizar dívida. Migrar para validação RS256 contra JWKS quando o Portal expor o endpoint. |
| B4 | Redis Streams `portal.events` | 🔴 Planejado | **Fallback:** Não consumir eventos por enquanto. Tenant criado manualmente via seed local. Quando Portal emitir, adicionar consumer. |
| B5 | `agn-deploy` (Dockerfile/Terraform) | 🟡 Em construção | **Já temos:** Dockerfiles próprios em `propostai-app/deployment/` funcionais. Migrar para template `agn-deploy` quando publicado. |
| B6 | OAuth Google/Microsoft + MFA | 🔴 Planejado | **Fallback:** Email/senha bcrypt apenas (já implementado). Sem MFA. Adicionar quando Portal centralizar. |

### 3.3 Grupo C — Conflitos arquiteturais

| # | Decisão | Decisão tomada |
|---|---|---|
| C1 | Frontend próprio | **Manter próprio** (5 páginas React/Vite/TS) durante Ondas 0–6 — Cenário B do §17.4 do guia. Migrar para módulo lazy do Portal SPA na Onda 6 (quando Portal SPA existir). |
| C2 | Repositório separado já ou monorepo | **Monorepo temporário** até Onda 6. Split via `git subtree split` para repo próprio `ai-garage/propostai-app` na Onda 7. |
| C3 | App em deploy ativo em outro provedor | **Não.** Legado Railway+Vercel já desativado e arquivado em `legacy/`. Sem janela de freeze necessária. |

### 3.4 Grupo D — Infraestrutura (só divergências dos defaults da §16.7 do guia)

Adoto **todos os defaults** sem divergência:
- Cloud Run (D1) ✅
- GCP Artifact Registry (D2) ✅
- Postgres cluster compartilhado, DB lógica `propostai_db` (D3) ✅ — **a confirmar provisionamento com plataforma**
- VPC Connector + Private IP (D4) ✅
- GCS bucket compartilhado, prefixo `propostai/` por tenant (D5) ✅
- Qdrant compartilhado, coleção `propostai_kb` (D6) ✅
- GCP Secret Manager (D7) ✅

### 3.5 Grupo E — Decisões de domínio

| # | Pergunta | Decisão |
|---|---|---|
| E1 | Embeddings | **Curto prazo:** OpenAI `text-embedding-3-large` direto (sem proxy). **Longo prazo:** Voyage-3 via Portal proxy quando este existir. |
| E2 | Anonimização LGPD antes de mandar pra LLM | **Configurável por tenant.** Default: anonimizar **CPF, CNPJ, nomes próprios, endereços, e-mails de pessoas físicas**. Plano `enterprise` permite desativar. |
| E3 | Limites por plano (fonte da verdade) | **Portal envia `subscription.upgraded`** via Redis Stream; produto cacheia em `tenants.max_*`. Enquanto Portal não emite, valor vem do seed. |
| E4 | Versão do código legado a herdar | **`orchestrator_v5.py`** (mais recente, descartar `orchestrator.py` v1). |
| E5 | Cutover de RAG legado vs novo | **Feature flag** `RAG_PROVIDER=qdrant\|fake` + **opt-in per-tenant** `features.rag_enabled` (default off — só liga quando o tenant tem corpus indexado). Hash-based RAG legado removido. RAG ligado ao OrchestratorV5 com fail-open na busca. |
| E6 | Dados legados (`legacy/.../proposals.json`) | **Descartar.** Eram propostas demo do desenvolvimento, não dados reais. Sem migração de produção. |
| E7 | Geração de propostas — modo síncrono ou async? | **Async via WebSocket** (`ws_generation.py` já existe). Stream de eventos por agente. |
| E8 | Modelo LLM padrão para os 8 agentes IA | **Claude Sonnet 4** (Anthropic) — já configurado em `pyproject.toml`. OpenAI como fallback opcional por tenant. |
| E9 | Calibração dos agentes (gap memória [DAM Quality](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-propostai\memory\feedback_dam_quality.md), [Upgrade Proposal](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-propostai\memory\feedback_upgrade_proposal.md)) | ✅ **Implementado** em `services/propostai/agents/profiles.py`. Três perfis built-in (`default`, `conservative` +50% / QA≥90 / -0.10 confiança, `aggressive` -15%) selecionáveis via `tenants.features.agent_profile`. Validação contra DAMs reais segue como ação de operação (não bloqueia o código). |

### 3.6 Grupo F — Execução

| # | Decisão | Valor |
|---|---|---|
| F1 | Tamanho do time | **1 dev sênior + Claude** (Rogerio). Equivalente a "1 dev part-time + apoio" da matriz §18.0.1. |
| F2 | Ordem das ondas | **Sequencial** com paralelização oportunista de Onda 2+3 quando backend estável. |
| F3 | Folga de prazo | **1.5× sobre nominal** — pressão moderada, qualidade prioritária. |
| F4 | Critério de "pronto" | **MVP enxuto (Ondas 0–3)** vai pra sandbox interno. Decisão de GA fica para depois de validação. |
| F5 | App em produção hoje? | **Não.** Sem janela de freeze necessária. |

### 3.7 Grupo G — Naming e branding

| # | Decisão | Valor |
|---|---|---|
| G1 | Slug canônico | `propostai` ✅ (já feito na Onda 0) |
| G2 | Domínio público | `propostai.ai-garage.com.br` ✅ |
| G3 | Nome humano | "PropostAI" ✅ |

### 3.8 Grupo H — Riscos específicos identificados

Ver Seção 6 abaixo.

---

## 4. Cronograma proposto

Base: matriz §18.0.1 do guia, perfil "1 dev sênior + apoio". Estimativas com folga 1.5× (F3). Datas indicativas — ajustar conforme execução.

| Onda | Escopo | Estimativa | Status | Dependência crítica |
|---|---|---|---|---|
| **0** | Consolidação: rename `sap-proposal-app` → `propostai-app`, mover legado pra `legacy/`, baseline Alembic, smoke test local | 1 sem | ✅ **DONE** (16 commits em `main`, tag `backup/pre-org-2026-05-14`) | — |
| **1** | Auth federado: aceitar JWT do Portal via JWKS RS256 (com fallback HS256). Renomear `AGENT_HUB_*` → `PORTAL_*`. Implementar `core/jwks_client.py`, `core/permissions.py` (`@require_product`). | 2–3 sem | ✅ **DONE** | B3 🔴 → modo dual HS256/RS256 desde já |
| **2** | Contratos Portal: implementar `POST /integrations/portal/provision` (HMAC), `POST /deprovision`, `GET /api/v1/dashboard/summary` (cache 60s), `GET /health` enriquecido (DB+Redis+Qdrant), `POST /lgpd/delete-tenant`, `POST /lgpd/export-tenant`. SubscriptionMiddleware. | 3 sem | ✅ **DONE** | B2 🟡 → testar contra Wiremock até Portal estar pronto |
| **3** | Eventos Redis Streams: consumer de `portal.events` (handlers `tenant.created`, `subscription.upgraded`, etc.). Publisher de `usage.metric`, `audit.action`. Audit central via `POST /api/portal/audit/events` (com fallback REST). | 2 sem | ✅ **DONE** | B4 🔴 → fallback REST `POST /usage/events` no Portal |
| **4** | **PULAR/POSTERGAR** — `agn-shared` ainda 🟡. Manter código duplicado em `propostai-app/backend/core/`. Revisitar pós-GA. | (postergada) | — | B1 🟡 |
| **5** | Domínio + infra prod: migrar RAG real (Qdrant + OpenAI embeddings), DAM Word generator, WP Excel generator, orchestrator_v5 do legacy. Anonimização LGPD. Sentry + Prometheus. Cloud Run deploy. CI/CD GitHub Actions. | 3 sem | ✅ **DONE** (código completo; deploy real depende de D3) | D3 (Postgres compartilhado) precisa estar provisionado |
| **6** | Frontend integrado no Portal SPA: migrar 5 páginas como módulos lazy (`agn-portal/src/products/propostai/`). Adotar `agn-ui` (AuthContext, ProductSwitcher, httpClient). Branding via tenant. i18n hierárquico. | 3 sem | 🟡 **PREP DONE** (lazy routes, namespace `products/propostai/`, AuthContext com claims v3, ESLint v9 flat-config); integração com `agn-ui` espera Portal SPA | Portal SPA precisa existir em ambiente acessível |
| **7** | Cutover & split: `git subtree split --prefix=propostai-app` para `github.com/ai-garage/propostai-app`. Remover `legacy/`. DNS para Cloud Run. Smoke test E2E em sandbox por 7 dias. | 1 sem | 🟡 **RUNBOOK DONE** (`docs/RUNBOOK_CUTOVER.md`); execução real espera Ondas 1–6 mergeadas + Cloud Run em sandbox | Ondas 1-6 completas |

**Total nominal:** 13–14 semanas
**Com folga 1.5×:** ~20 semanas (~5 meses)
**MVP enxuto (Ondas 0–3 + go-live parcial):** ~9–11 semanas

---

## 5. Checklist pré-Onda 1 (adaptado da §18.0.5)

> Onda 0 já concluída. Esta lista valida pré-requisitos da Onda 1.

- [x] §4.5 completa (este documento) revisada
- [x] §1.5 consultada e bloqueios mapeados (B3, B4, B6 = 🔴)
- [ ] **Acesso ao `agent-hub` de referência confirmado** — bloqueador **A1**
- [x] Sandbox provisionado (Docker compose local + override de portas)
- [x] Pessoa responsável por validação técnica nomeada (Rogerio)
- [N/A] Janela de freeze de produção (sem prod ativa)
- [x] **Plano de rollback escrito** — `docs/RUNBOOK_ROLLBACK.md` criado

**1 item pendente** antes de iniciar Onda 1.

---

## 5.1 Status de execução (Ondas 0–5)

Snapshot do código entregue na branch `feat/onda-1-align-v3` ao fim da
Onda 5:

| Onda | Highlights |
|---|---|
| 0 | Repo consolidado, `legacy/` isolado, Alembic baseline, smoke test |
| 1 | Dual JWT HS256/RS256 + JWKS, `core/permissions.py`, rename `AGENT_HUB_*→PORTAL_*` |
| 2 | LGPD delete/export-tenant (HMAC), Portal provision/deprovision, SubscriptionMiddleware (423 read-only quando suspended), dashboard summary, health enriquecido |
| 3 | Redis Streams: consumer de `portal.events` com 7 handlers idempotentes; publisher de `usage.metric`+`audit.action` com fallback REST; `/sync-tenant` REST stub (§21.2.3); audit wiring em todas as rotas de Proposal |
| 5a | Observabilidade: `/metrics` Prometheus + `MetricsMiddleware`, Sentry com tags `tenant_id`/`trace_id`/`user_id` |
| 5b | CI GitHub Actions (ruff + pytest backend + build/lint frontend) |
| 5c | DAM Word + WP Excel generators migrados do legado (template Direto ao Ponto) |
| 5d | LGPD anonimizer (CPF/CNPJ/e-mail/telefone) com flag por tenant |
| 5e | OrchestratorV5 catalog-first + LLMClient (OpenAI+Anthropic) + billing por execução; ligado em `generation_service` (legacy agents deletados) |
| 5f | RAG: Embedder OpenAI + Qdrant client multi-tenant + `RAGService` ligado ao `OrchestratorV5` (opt-in `tenant.features.rag_enabled`, fail-open, anonymized query, top-3 chunks viram preâmbulo nos prompts descritivos) |
| 5h | Calibration profiles per-tenant (E9 / H2 / H3): `services/propostai/agents/profiles.py` com `default`/`conservative`/`aggressive`, selecionável via `tenant.features.agent_profile`. Conservative multiplica horas/valor por 1.5×, penaliza confiança em 0.1 e exige QA ≥ 90. Endereça `feedback_dam_quality` + `feedback_upgrade_proposal`. |
| 5g | Deploy: `Dockerfile.cloudrun`, Terraform skeleton (Artifact Registry + Cloud Run + SA + Secret Manager bindings), workflow `.github/workflows/deploy.yml` |
| 6 (prep) | Frontend: ESLint v9 flat-config (`eslint.config.js`), `Suspense + React.lazy` por rota (chunks separados emitidos pelo vite), `frontend/src/products/propostai/routes.tsx` (namespace alinhado com §17.4), `AuthContext` enriquecido com `products[]` + `rolesByProduct` + `hasProduct()` + `roleFor()` (assinatura espelha o contrato esperado de `agn-ui`) |
| 7 (runbook) | `docs/RUNBOOK_CUTOVER.md` cobre subtree split, limpeza do monorepo, CI/CD no repo destino, DNS via Cloudflare tunnel, smoke E2E de 7 dias, go-live e rollback de cutover |

**Suite:** 216 testes verdes; ruff clean.

**Inclui agora:**
- `tests/isolation/test_tenant_isolation.py` (11 testes) — todas as rotas
  auth-protected de Proposal exercitadas com 2 tenants. Endereça H6
  (severidade *Crítico*).
- `RAGService.purge_tenant()` chamado pelo `POST /lgpd/delete-tenant`
  (best-effort: falha do Qdrant não bloqueia LGPD).
- `RAGService.search()` ligado ao `OrchestratorV5` via injeção (opt-in
  per-tenant via `features.rag_enabled`, fail-open, query anonimizada).
- Counters Prometheus `proposals_generated_total`/`dam_documents_exported_total`/`wp_documents_exported_total`
  incrementados nos endpoints reais — viraram observáveis.
- `services/propostai/agents/profiles.py`: calibration profiles
  per-tenant (`default`/`conservative`/`aggressive`) selecionáveis via
  `features.agent_profile`. Fecha E9 e mitiga H2 / H3 — tenants que
  fazem upgrades grandes (memória [Upgrade Proposal Gap]) ativam
  `conservative` e ganham +50% horas, confiança penalizada e QA ≥ 90.

**Debt restante:**
- Corpus real indexado por tenant — depende de produto (RAG está plumbed
  end-to-end, mas só agrega valor com legislação/templates ingeridos).

---

## 6. Riscos específicos deste produto

| # | Risco | Probabilidade | Impacto | Plano B |
|---|---|---|---|---|
| H1 | `agn-shared` não pronto a tempo da Onda 4 | Alta (já 🟡) | Médio | Manter código duplicado em `propostai-app/backend/core/`, refatorar pós-GA |
| H2 | Anonimização degrada qualidade do output (memória [DAM Quality Gap](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-propostai\memory\feedback_dam_quality.md)) | Alta | Alto | Anonimizar **só** na saída para LLM externo. Dados completos no DB do tenant. Validar com 5 propostas reais antes de habilitar em prod. |
| H3 | Estimativa de propostas grandes subdimensionada (memória [Upgrade Proposal Gap](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-propostai\memory\feedback_upgrade_proposal.md): upgrade EHP real = R$427k, IA subestima) | Alta | Alto | Calibration profiles per-tenant (E9). Coletar feedback dos arquitetos SAP da Direto ao Ponto em pelo menos 10 propostas antes de GA. |
| H4 | Portal SaaS v2 atrasa muito → produto fica em limbo (HS256 + sem eventos) | Média | Alto | MVP enxuto sai em sandbox sem Portal. Onda 6 (frontend integrado) só acontece quando Portal SPA existir. |
| H5 | Sem acesso ao `agent-hub` (A1) → drift do padrão | Média | Médio | Solicitar acesso antes de começar Onda 1. Se não conseguir, divergir conscientemente e documentar para reconciliar quando o repo for liberado. |
| H6 | Multi-tenancy quebra isolamento (tenant A vê dados de tenant B) | Baixa (TenantMixin já força) | Crítico | Suite obrigatória `tests/test_tenant_isolation.py` na Onda 4 (ou Onda 1 se postergar 4). Cobertura ≥90% de modelos de domínio. |
| H7 | Bcrypt 4.1+ quebra passlib (já vimos!) | (já corrigido) | — | Pin `bcrypt<4.1` no `pyproject.toml` (commit `ff98e7d`) |
| H8 | Permissões WSL bloqueiam workflow (root no `sap-proposal-app/`, root no `legacy/...docs/`) | Média | Baixo (mitigado) | Documentado em [memory/reference_wsl_permissions.md](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-propostai\memory\reference_wsl_permissions.md). Sempre verificar `ls -la` antes de mexer. |

---

## 7. Decisões em aberto (default temporário aceito)

| Decisão | Default temporário | Quando revisitar |
|---|---|---|
| A1 — acesso ao agent-hub | Seguir só com o guia v3, sem código de referência | Antes da Onda 2 (contratos Portal) — onde vamos precisar saber padrões reais |
| D3 — Postgres compartilhado provisionado pela plataforma | Postgres local em Docker (`propostai-postgres:5433`) | Onda 5 (deploy GCP) |
| E1 — provedor de embeddings | OpenAI `text-embedding-3-large` direto | Quando Portal expor proxy LLM |
| F4 — critério de pronto | MVP enxuto (Ondas 0–3) | Após Onda 3 — decisão de seguir para Completo |

---

## 8. Aprovações

| Papel | Pessoa | Data |
|---|---|---|
| Tech lead do produto | Rogerio Ribeiro | _aguardando assinatura_ |
| Arquiteto da plataforma | _a definir_ (responsável pelo agent-hub) | _aguardando_ |
| Product owner | _a definir_ | _aguardando_ |

---

## Anexo A — O que mudou em relação ao plano v2

O plano anterior ([`/docs/PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md`](../../docs/PLAN_SIL_PROPOSTA_ALIGN_SAAS_v2.md), 432 linhas) foi escrito contra o **v2 do guia**. As principais diferenças contra **v3**:

| Aspecto | v2 do plano | v3 (este) |
|---|---|---|
| **Estrutura** | Texto livre com 7 ondas | Template padrão do guia (Apêndice D) |
| **Estado da plataforma** | Assumido "tudo pronto" | Matriz §1.5 mostra B3, B4, B6, B8-B12 = 🔴 (não existem) |
| **Onda 4 (`agn-shared`)** | "obrigatória" | **POSTERGADA** — `agn-shared` 🟡, manter código duplicado |
| **Frontend** | "não devia existir, migrar" | Manter próprio durante Ondas 0–6 (Cenário B do §17.4), migrar para Portal SPA na Onda 6 |
| **Repo separado** | "extrair na Onda 7" | Confirmado: monorepo até Onda 6, `git subtree split` na Onda 7 |
| **Folha de decisões** | 35 perguntas isoladas | Estruturadas em 8 grupos (A–H) com defaults da plataforma |
| **Calibração de prazo** | "12 semanas" | 1.5× nominal = ~20 semanas (5 meses) para Completo, 9–11 sem para MVP |
| **Memórias DAM Quality + Upgrade Proposal** | Mencionadas como riscos | Endereçadas em E9 (calibration profiles per-tenant) e H2/H3 |

O plano v2 será **removido** após este v3 ser aprovado, para evitar duas fontes da verdade.

---

*Plano gerado em 2026-05-15 usando o template do Apêndice D do v3 do guia. Revisões devem ser commitadas com mensagem `docs(plan): ...` para rastreabilidade.*
