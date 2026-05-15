# Plano de Migração — Sil-Proposta

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
| Nome humano | Sil-Proposta |
| Slug canônico | `sil-proposta` |
| Domínio PRD | `sil-proposta.ai-garage.com.br` |
| Domínio DEV | `sil-proposta.dev.ai-garage.com.br` |
| Database | `sil_proposta` (renomear para `sil_proposta_db` quando migrar pro cluster compartilhado) |
| Coleção Qdrant | `sil_proposta_kb` |
| Stream Redis | `sil-proposta:events` |

---

## 2. Origem do código

| Campo | Valor |
|---|---|
| Repo de origem (atual) | `github.com/aigarage2026/sil-proposta` (monorepo) |
| Branch base | `main` |
| Stack atual | FastAPI + SQLAlchemy 2 + Alembic + asyncpg / React 19 + Vite 7 + Tailwind + TypeScript / Postgres 16 + Redis 7 + Qdrant 1.12 |
| Em produção hoje? | **Não.** O monolito legado (Railway + Vercel) está em [`/legacy/sil-proposta-monolith/`](../../legacy/sil-proposta-monolith/), não tem deploy ativo |
| Volume estimado de dados | Zero (greenfield + seed do tenant Cast Group Demo) |

---

## 3. Decisões fechadas (cópia da §4.5 do guia v3)

### 3.1 Grupo A — Acesso

| # | Decisão | Valor |
|---|---|---|
| A1 | Acesso ao `agent-hub` de referência | **PENDENTE** — não localizei o repo. Tentei `github.com/ai-garage` (vazio) e `github.com/aigarage2026` (6 repos, nenhum com `agent` ou `portal`). Provável que esteja em org privada (`ai-garage-inf` está vazia). **Risco:** sem o código de referência, podemos divergir do padrão. |
| A2 | Repo de origem | `github.com/aigarage2026/sil-proposta` |
| A3 | Branch base | `main` |
| A4 | Validador técnico | Rogerio Ribeiro |

### 3.2 Grupo B — Dependências da plataforma (cruzando com §1.5 do guia)

| # | Componente | Status §1.5 | Decisão deste produto |
|---|---|---|---|
| B1 | `agn-shared` (Python: `agn-core`, `agn-auth`, `agn-billing`, `agn-middleware`, `agn-audit`) | 🟡 Em construção | **Fallback:** código copiado/duplicado dentro do `sil-proposta-app/backend/` (já é o caso). Refatorar para `agn-shared` quando estável (Onda 4 — postergada). |
| B2 | `agn-portal` (control plane) | 🟡 Em construção, parcialmente operacional | **Fallback:** Wiremock para mock de Portal API; auth local HS256 mantido até cutover. |
| B3 | JWT RS256 + JWKS público | 🔴 Planejado | **Fallback:** **HS256 atual mantido** com flag `JWT_LEGACY_MODE=true` para sinalizar dívida. Migrar para validação RS256 contra JWKS quando o Portal expor o endpoint. |
| B4 | Redis Streams `portal.events` | 🔴 Planejado | **Fallback:** Não consumir eventos por enquanto. Tenant criado manualmente via seed local. Quando Portal emitir, adicionar consumer. |
| B5 | `agn-deploy` (Dockerfile/Terraform) | 🟡 Em construção | **Já temos:** Dockerfiles próprios em `sil-proposta-app/deployment/` funcionais. Migrar para template `agn-deploy` quando publicado. |
| B6 | OAuth Google/Microsoft + MFA | 🔴 Planejado | **Fallback:** Email/senha bcrypt apenas (já implementado). Sem MFA. Adicionar quando Portal centralizar. |

### 3.3 Grupo C — Conflitos arquiteturais

| # | Decisão | Decisão tomada |
|---|---|---|
| C1 | Frontend próprio | **Manter próprio** (5 páginas React/Vite/TS) durante Ondas 0–6 — Cenário B do §17.4 do guia. Migrar para módulo lazy do Portal SPA na Onda 6 (quando Portal SPA existir). |
| C2 | Repositório separado já ou monorepo | **Monorepo temporário** até Onda 6. Split via `git subtree split` para repo próprio `ai-garage/sil-proposta-app` na Onda 7. |
| C3 | App em deploy ativo em outro provedor | **Não.** Legado Railway+Vercel já desativado e arquivado em `legacy/`. Sem janela de freeze necessária. |

### 3.4 Grupo D — Infraestrutura (só divergências dos defaults da §16.7 do guia)

Adoto **todos os defaults** sem divergência:
- Cloud Run (D1) ✅
- GCP Artifact Registry (D2) ✅
- Postgres cluster compartilhado, DB lógica `sil_proposta_db` (D3) ✅ — **a confirmar provisionamento com plataforma**
- VPC Connector + Private IP (D4) ✅
- GCS bucket compartilhado, prefixo `sil-proposta/` por tenant (D5) ✅
- Qdrant compartilhado, coleção `sil_proposta_kb` (D6) ✅
- GCP Secret Manager (D7) ✅

### 3.5 Grupo E — Decisões de domínio

| # | Pergunta | Decisão |
|---|---|---|
| E1 | Embeddings | **Curto prazo:** OpenAI `text-embedding-3-large` direto (sem proxy). **Longo prazo:** Voyage-3 via Portal proxy quando este existir. |
| E2 | Anonimização LGPD antes de mandar pra LLM | **Configurável por tenant.** Default: anonimizar **CPF, CNPJ, nomes próprios, endereços, e-mails de pessoas físicas**. Plano `enterprise` permite desativar. |
| E3 | Limites por plano (fonte da verdade) | **Portal envia `subscription.upgraded`** via Redis Stream; produto cacheia em `tenants.max_*`. Enquanto Portal não emite, valor vem do seed. |
| E4 | Versão do código legado a herdar | **`orchestrator_v5.py`** (mais recente, descartar `orchestrator.py` v1). |
| E5 | Cutover de RAG legado vs novo | **Feature flag** `RAG_PROVIDER=qdrant\|fake`. Default `qdrant` em dev/prod, `fake` apenas para testes determinísticos. Hash-based RAG removido após Onda 5. |
| E6 | Dados legados (`legacy/.../proposals.json`) | **Descartar.** Eram propostas demo do desenvolvimento, não dados reais. Sem migração de produção. |
| E7 | Geração de propostas — modo síncrono ou async? | **Async via WebSocket** (`ws_generation.py` já existe). Stream de eventos por agente. |
| E8 | Modelo LLM padrão para os 8 agentes IA | **Claude Sonnet 4** (Anthropic) — já configurado em `pyproject.toml`. OpenAI como fallback opcional por tenant. |
| E9 | Calibração dos agentes (gap memória [DAM Quality](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-sil-proposta\memory\feedback_dam_quality.md), [Upgrade Proposal](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-sil-proposta\memory\feedback_upgrade_proposal.md)) | **Per-tenant calibration profiles** (ex.: "conservative", "aggressive") configuráveis via `tenants.features.agent_profile`. Validar contra DAMs reais (passo final da Onda 5). |

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
| G1 | Slug canônico | `sil-proposta` ✅ (já feito na Onda 0) |
| G2 | Domínio público | `sil-proposta.ai-garage.com.br` ✅ |
| G3 | Nome humano | "Sil-Proposta" ✅ |

### 3.8 Grupo H — Riscos específicos identificados

Ver Seção 6 abaixo.

---

## 4. Cronograma proposto

Base: matriz §18.0.1 do guia, perfil "1 dev sênior + apoio". Estimativas com folga 1.5× (F3). Datas indicativas — ajustar conforme execução.

| Onda | Escopo | Estimativa | Status | Dependência crítica |
|---|---|---|---|---|
| **0** | Consolidação: rename `sap-proposal-app` → `sil-proposta-app`, mover legado pra `legacy/`, baseline Alembic, smoke test local | 1 sem | ✅ **DONE** (16 commits em `main`, tag `backup/pre-org-2026-05-14`) | — |
| **1** | Auth federado: aceitar JWT do Portal via JWKS RS256 (com fallback HS256). Renomear `AGENT_HUB_*` → `PORTAL_*`. Implementar `core/jwks_client.py`, `core/permissions.py` (`@require_product`). | 2–3 sem | ✅ **DONE** | B3 🔴 → modo dual HS256/RS256 desde já |
| **2** | Contratos Portal: implementar `POST /integrations/portal/provision` (HMAC), `POST /deprovision`, `GET /api/v1/dashboard/summary` (cache 60s), `GET /health` enriquecido (DB+Redis+Qdrant), `POST /lgpd/delete-tenant`, `POST /lgpd/export-tenant`. SubscriptionMiddleware. | 3 sem | ✅ **DONE** | B2 🟡 → testar contra Wiremock até Portal estar pronto |
| **3** | Eventos Redis Streams: consumer de `portal.events` (handlers `tenant.created`, `subscription.upgraded`, etc.). Publisher de `usage.metric`, `audit.action`. Audit central via `POST /api/portal/audit/events` (com fallback REST). | 2 sem | ✅ **DONE** | B4 🔴 → fallback REST `POST /usage/events` no Portal |
| **4** | **PULAR/POSTERGAR** — `agn-shared` ainda 🟡. Manter código duplicado em `sil-proposta-app/backend/core/`. Revisitar pós-GA. | (postergada) | — | B1 🟡 |
| **5** | Domínio + infra prod: migrar RAG real (Qdrant + OpenAI embeddings), DAM Word generator, WP Excel generator, orchestrator_v5 do legacy. Anonimização LGPD. Sentry + Prometheus. Cloud Run deploy. CI/CD GitHub Actions. | 3 sem | pending | D3 (Postgres compartilhado) precisa estar provisionado |
| **6** | Frontend integrado no Portal SPA: migrar 5 páginas como módulos lazy (`agn-portal/src/products/sil-proposta/`). Adotar `agn-ui` (AuthContext, ProductSwitcher, httpClient). Branding via tenant. i18n hierárquico. | 3 sem | pending | Portal SPA precisa existir em ambiente acessível |
| **7** | Cutover & split: `git subtree split --prefix=sil-proposta-app` para `github.com/ai-garage/sil-proposta-app`. Remover `legacy/`. DNS para Cloud Run. Smoke test E2E em sandbox por 7 dias. | 1 sem | pending | Ondas 1-6 completas |

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

## 6. Riscos específicos deste produto

| # | Risco | Probabilidade | Impacto | Plano B |
|---|---|---|---|---|
| H1 | `agn-shared` não pronto a tempo da Onda 4 | Alta (já 🟡) | Médio | Manter código duplicado em `sil-proposta-app/backend/core/`, refatorar pós-GA |
| H2 | Anonimização degrada qualidade do output (memória [DAM Quality Gap](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-sil-proposta\memory\feedback_dam_quality.md)) | Alta | Alto | Anonimizar **só** na saída para LLM externo. Dados completos no DB do tenant. Validar com 5 propostas reais antes de habilitar em prod. |
| H3 | Estimativa de propostas grandes subdimensionada (memória [Upgrade Proposal Gap](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-sil-proposta\memory\feedback_upgrade_proposal.md): upgrade EHP real = R$427k, IA subestima) | Alta | Alto | Calibration profiles per-tenant (E9). Coletar feedback dos arquitetos SAP da Cast Group em pelo menos 10 propostas antes de GA. |
| H4 | Portal SaaS v2 atrasa muito → produto fica em limbo (HS256 + sem eventos) | Média | Alto | MVP enxuto sai em sandbox sem Portal. Onda 6 (frontend integrado) só acontece quando Portal SPA existir. |
| H5 | Sem acesso ao `agent-hub` (A1) → drift do padrão | Média | Médio | Solicitar acesso antes de começar Onda 1. Se não conseguir, divergir conscientemente e documentar para reconciliar quando o repo for liberado. |
| H6 | Multi-tenancy quebra isolamento (tenant A vê dados de tenant B) | Baixa (TenantMixin já força) | Crítico | Suite obrigatória `tests/test_tenant_isolation.py` na Onda 4 (ou Onda 1 se postergar 4). Cobertura ≥90% de modelos de domínio. |
| H7 | Bcrypt 4.1+ quebra passlib (já vimos!) | (já corrigido) | — | Pin `bcrypt<4.1` no `pyproject.toml` (commit `ff98e7d`) |
| H8 | Permissões WSL bloqueiam workflow (root no `sap-proposal-app/`, root no `legacy/...docs/`) | Média | Baixo (mitigado) | Documentado em [memory/reference_wsl_permissions.md](C:\Users\Rogerio Ribeiro\.claude\projects\--wsl-localhost-Ubuntu-home-rogerio-ribeiro-sil-proposta\memory\reference_wsl_permissions.md). Sempre verificar `ls -la` antes de mexer. |

---

## 7. Decisões em aberto (default temporário aceito)

| Decisão | Default temporário | Quando revisitar |
|---|---|---|
| A1 — acesso ao agent-hub | Seguir só com o guia v3, sem código de referência | Antes da Onda 2 (contratos Portal) — onde vamos precisar saber padrões reais |
| D3 — Postgres compartilhado provisionado pela plataforma | Postgres local em Docker (`silp-postgres:5433`) | Onda 5 (deploy GCP) |
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
