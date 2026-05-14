# Documento de Arquitetura: Refatoracao Sil-Proposta (SAP Proposal Generator)

> **Versao:** 1.0
> **Data:** 2026-04-10
> **Autor:** AI Garage Engineering
> **Status:** Plano Pendente
> **Base de Referencia:** ARCHITECTURE_REFACTORING_TEMPLATE.md v1.1
> **Objetivo:** Refatorar o Sil-Proposta (gerador de propostas SAP Cast Group) de aplicacao monolitica (FastAPI + HTML vanilla) para o padrao SaaS AI Garage: FastAPI + SQLAlchemy + Postgres + React/Vite, com integracao com Agent Hub.

---

## 0. Caracterizacao do As-Is

| Item | Conteudo |
|------|----------|
| **Stack atual** | FastAPI + vanilla HTML/JS (SPA em 1 arquivo) + SQLite/PostgreSQL |
| **Banco** | SQLite local (dev) / PostgreSQL (prod) — sem ORM, queries manuais |
| **Tabelas** | 1 tabela (`proposals`) com ~20 colunas, JSONs serializados como TEXT |
| **Funcoes serverless / cron** | 0 — tudo sincrono no request |
| **Auth atual** | Nenhuma — endpoints abertos, sem JWT, sem RBAC |
| **Multi-tenant atual?** | Nao — single-tenant, sem `tenant_id` |
| **Storage** | Documentos gerados em memoria (BytesIO), nao persistidos |
| **Busca/IA** | RAG in-memory (hash-based, sem embeddings reais) + Claude/OpenAI para LLM |
| **i18n** | Parcial no frontend (pt-BR, en, es via objeto JS) |
| **Integracoes externas** | OpenAI GPT-4o-mini, Anthropic Claude Sonnet 4, Supabase (opcional) |
| **Volume estimado** | Single-user, ~10-50 propostas/mes |
| **Riscos identificados** | Zero autenticacao, sem multi-tenancy, frontend monolitico (1686 linhas), backend e frontend duplicados (index.html em 2 pastas), sem testes, sem migrations, JSON serializado manualmente |
| **Funcionalidades a NAO migrar** | Billing/Stripe (Agent Hub), Onboarding centralizado (Agent Hub) |

### Inventario de Arquivos Legado

```
backend/
  main.py              — FastAPI app, 270 linhas, rotas + logica de geracao
  database.py          — CRUD manual SQLite/PostgreSQL, sem ORM
  demo_engine.py       — Gerador deterministico (fallback sem LLM), 386 linhas
  agents/
    orchestrator.py    — Orquestrador multi-agente com Claude, 269 linhas
    rag.py             — RAG in-memory com 26 documentos hardcoded, 247 linhas
  generators/
    dam.py             — Gerador de Word (python-docx), 334 linhas
    wp.py              — Gerador de Excel (openpyxl), 285 linhas
  db/
    persistence.py     — Camada Supabase/JSON (alternativa), 176 linhas
  data/
    proposals.json     — Dados sample
  Dockerfile           — Deploy Railway
frontend/
  index.html           — SPA completo, 1686 linhas, HTML+CSS+JS inline
  agents-viz.html      — Visualizacao de agentes (standalone)
```

**Total:** ~2,500 linhas de backend Python + ~1,900 linhas de frontend HTML/JS

---

## Sumario Executivo

A refatoracao do **Sil-Proposta** (Gerador de Propostas SAP Cast Group) substitui a aplicacao monolitica atual (FastAPI sem ORM + HTML vanilla) por uma plataforma SaaS independente sobre o stack padrao da AI Garage: **FastAPI + SQLAlchemy + Postgres + React/Vite**. A nova versao tera **codigo, banco, deploy e dominio proprios** (`sap-proposal.ai-garage.com.br`), integrando com o Agent Hub apenas via API para:

- **Onboarding e billing centralizados** (Stripe, planos, checkout);
- **LLM/conversacional** (chamadas a Claude/GPT passam pelo Agent Hub);
- **RAG com Qdrant** (busca semantica real substituindo o hash fake atual).

A migracao e executada em **4 ondas**: MVP-1 (geracao de propostas), MVP-2 (colaboracao e historico avancado), Onda 3 (templates customizaveis e analytics), Onda 4 (API publica e webhooks).

---

## 1. Placeholders Preenchidos

| Placeholder | Valor |
|-------------|-------|
| `{APP_NAME}` | `sap_proposal` |
| `{APP_NAME_HUMAN}` | "Sil-Proposta" |
| `{APP_DOMAIN}` | `sap-proposal.ai-garage.com.br` |
| `{APP_DESCRIPTION}` | "Gerador de propostas SAP com IA multi-agente para consultorias" |
| `{LEGACY_STACK}` | "FastAPI + HTML vanilla + SQLite/PostgreSQL + Claude/OpenAI" |
| `{TARGET_PERSONAS}` | "pre-vendas SAP, gerentes de projetos, diretores comerciais" |
| `{CORE_DOMAIN_ENTITY}` | `Proposal` |
| `{DOMAIN_PILLARS}` | "Intake, Generation, Review, Export, Analytics" |
| `{N_LEGACY_TABLES}` | 1 (proposals) + 1 opcional (Supabase JSONB) |
| `{N_LEGACY_FUNCTIONS}` | 0 (tudo sincrono) |

---

## 2. Multi-Tenancy — Hierarquia Aplicada

```
┌─────────────────────────────────────────────────────────┐
│  TENANT  (consultoria SAP cliente da plataforma)        │
│  Ex.: "Cast Group", "Accenture SAP", "Deloitte SAP"    │
│  - Plano, billing, branding, limites                    │
└──────────────┬──────────────────────────────────────────┘
               │ 1:N
       ┌───────▼─────────────────────────┐
       │  COMPANY  (cliente final)       │
       │  Ex.: "Empresa ABC - CNPJ X"   │
       │  - UFs, versao SAP, ambiente    │
       └───────┬─────────────────────────┘
               │ 1:N
       ┌───────▼─────────────────────────┐
       │  PROPOSAL (proposta SAP)        │
       │  - DAM, WP, entregaveis, horas │
       │  - Status: draft → review →     │
       │    approved → won/lost          │
       └─────────────────────────────────┘
```

**Aplicacao de regras §2:**
- `tenant_id` em TODAS as tabelas de dominio (TenantMixin)
- Filtragem obrigatoria no service layer
- Isolation tests por modelo
- ADR-013: **NAO usar RLS** (dados de propostas nao sao regulados LGPD)

---

## 3. Modelo de Dados — Dominio

### 3.1 Entidades do Dominio

```python
# ── INTAKE ──────────────────────────────────────────────

class Proposal(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Proposta SAP gerada pelo sistema."""
    __tablename__ = "proposals"

    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Intake
    title = Column(String(500), nullable=False)
    project_type = Column(String(30), nullable=False)        # ams, new, migration, support
    sap_version = Column(String(30), nullable=False)         # ecc604, ecc605, s4op, s4cloud
    states = Column(JSON, nullable=False)                     # ["SP","GO","RJ"]
    commercial_model = Column(String(30), nullable=False)     # fixed, t&m
    rfp_text = Column(Text)
    new_law = Column(Boolean, default=False)
    hours_presale = Column(Integer, default=0)
    notes = Column(Text)
    lang = Column(String(5), default="pt")

    # Generation result
    status = Column(String(30), nullable=False, default="draft")  # draft, review, approved, won, lost
    main_proc = Column(String(20))                            # SD, FI, MM, PP, etc.
    needs_cpi = Column(Boolean, default=False)
    total_hours = Column(Integer)
    valor = Column(Numeric(12,2))

    # Confidence scores
    confidence_escopo = Column(Numeric(3,2))
    confidence_horas = Column(Numeric(3,2))
    confidence_legislacao = Column(Numeric(3,2))
    confidence_comercial = Column(Numeric(3,2))

    # Generation metadata
    generation_mode = Column(String(20))                      # llm, demo, hybrid
    agents_fired = Column(JSON)                               # ["Orquestrador","SD","FI",...]
    generation_time_ms = Column(Integer)

    __table_args__ = (
        Index("ix_proposals_tenant_status", "tenant_id", "status"),
        Index("ix_proposals_tenant_company", "tenant_id", "company_id"),
        Index("ix_proposals_tenant_created", "tenant_id", "created_at"),
    )


class ProposalResource(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Recurso alocado no Work Package da proposta."""
    __tablename__ = "proposal_resources"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    frente = Column(String(50), nullable=False)               # SD, FI, GP, ABAP 1, ABAP 2
    nivel = Column(String(30), nullable=False)                # Senior, Pleno, Junior
    dias = Column(Integer, nullable=False)
    horas = Column(Integer, nullable=False)                   # dias * 8
    cost_rate = Column(Numeric(8,2))                          # custo/hora interno


class ProposalDeliverable(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Entregavel listado no DAM da proposta."""
    __tablename__ = "proposal_deliverables"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    module = Column(String(20), nullable=False)               # SD, FI, ABAP, DRC
    item = Column(String(500), nullable=False)
    hours = Column(Integer)
    sort_order = Column(Integer)


class ProposalPremise(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Premissa geral ou especifica da proposta."""
    __tablename__ = "proposal_premises"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    is_standard = Column(Boolean, default=False)              # premissa padrao Cast Group
    sort_order = Column(Integer)


class ProposalLegislation(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Legislacao fiscal identificada pela IA."""
    __tablename__ = "proposal_legislations"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(100), nullable=False)                # "IN 1.608/2025-GSE"
    description = Column(Text)
    uf = Column(String(2))
    scope = Column(String(20))                                # estadual, federal


class ProposalDam(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Dados completos do DAM (cache para geracao Word)."""
    __tablename__ = "proposal_dams"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False, unique=True)
    dam_json = Column(JSON, nullable=False)                   # JSON completo para gerar Word
    version = Column(Integer, default=1)


# ── KNOWLEDGE BASE (RAG) ───────────────────────────────

class KnowledgeDocument(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Documento da base de conhecimento para RAG."""
    __tablename__ = "knowledge_documents"

    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)             # fiscal, abap, methodology, cast_group
    tags = Column(JSON)
    is_global = Column(Boolean, default=False)                # docs globais da plataforma
    source = Column(String(100))                              # manual, imported, scraped

    __table_args__ = (
        Index("ix_knowledge_tenant_category", "tenant_id", "category"),
    )


# ── TEMPLATES ───────────────────────────────────────────

class ProposalTemplate(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Template customizavel de proposta."""
    __tablename__ = "proposal_templates"

    company_id = Column(String(36), ForeignKey("companies.id"))  # null = template do tenant
    name = Column(String(200), nullable=False)
    project_type = Column(String(30))
    default_premises = Column(JSON)
    default_resources = Column(JSON)
    branding = Column(JSON)                                   # logo, cores, rodape
    is_default = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_template_tenant_name"),
    )


# ── AGENT EXECUTION LOG ────────────────────────────────

class AgentExecution(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Log de execucao de cada agente IA."""
    __tablename__ = "agent_executions"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(50), nullable=False)           # Orquestrador, SD, FI, ABAP...
    status = Column(String(20), nullable=False)               # running, done, error
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    duration_ms = Column(Integer)
    result_json = Column(JSON)
    error_message = Column(Text)

    __table_args__ = (
        Index("ix_agent_exec_proposal", "proposal_id", "agent_name"),
    )
```

### 3.2 Diagrama Logico de Entidades

```
                    ┌──────────┐
                    │  Tenant  │
                    └─────┬────┘
                     1:N  │
              ┌───────────┼───────────────┐
              │           │               │
       ┌──────▼──┐  ┌─────▼────┐  ┌──────▼──────────┐
       │ Company │  │   User   │  │ KnowledgeDocument│
       └─────┬───┘  └──────────┘  └─────────────────┘
             │ 1:N
       ┌─────▼──────────┐
       │    Proposal     │
       └──┬──┬──┬──┬──┬─┘
          │  │  │  │  │
   ┌──────┘  │  │  │  └──────────────┐
   │         │  │  │                 │
┌──▼────┐ ┌──▼──┐ ┌▼──────┐ ┌───▼──────┐ ┌──▼────────────┐
│Resource│ │Deliv│ │Premise│ │Legislat. │ │AgentExecution │
└───────┘ └─────┘ └───────┘ └──────────┘ └───────────────┘
                                              │
                                         ┌────▼────┐
                                         │  DAM    │
                                         └─────────┘
```

### 3.3 Ondas de Migracao

| Onda | Dominios | Tabelas | Objetivo |
|------|---------|---------|----------|
| **MVP-1** | Intake + Generation + Export | Proposal, ProposalResource, ProposalDeliverable, ProposalPremise, ProposalLegislation, ProposalDam, AgentExecution | Primeiro valor: gerar propostas com IA |
| **MVP-2** | Knowledge + Templates | KnowledgeDocument, ProposalTemplate | RAG customizavel + templates por cliente |
| **Onda 3** | Analytics + Collaboration | ProposalComment, ProposalVersion, AnalyticsSnapshot | Workflow de aprovacao e dashboards |
| **Onda 4** | API publica + Webhooks | ApiKey, WebhookEndpoint, WebhookDelivery | Integracao com CRMs e ERPs |
| **Plataforma** | Billing/Onboarding | — | NAO migrar — consumir via Agent Hub |

---

## 4. Mapeamento As-Is → Refatorado

### 4.1 Tabela Principal

| Legado | Refatorado | Onda | Observacoes |
|--------|-----------|------|-------------|
| `proposals` (1 tabela monolitica, JSONs como TEXT) | `proposals` + `proposal_resources` + `proposal_deliverables` + `proposal_premises` + `proposal_legislations` + `proposal_dams` | MVP-1 | Desnormalizar JSONs em tabelas proprias |
| Nenhuma (RAG hardcoded) | `knowledge_documents` | MVP-2 | RAG real com Qdrant |
| Nenhuma | `proposal_templates` | MVP-2 | Templates por tenant/company |
| Nenhuma | `agent_executions` | MVP-1 | Log de execucao por agente |

### 4.2 Funcoes e Servicos

| Funcao Legado | Servico Python | Mecanismo | Onda |
|---------------|----------------|-----------|------|
| `main.py:generate()` | `services/proposal_generation_service.py` | endpoint POST | MVP-1 |
| `main.py:generate_stream()` | `services/proposal_generation_service.py` | WebSocket | MVP-1 |
| `main.py:_gerar_com_llm()` | `integrations/agent_hub_client.py` | Agent Hub API | MVP-1 |
| `demo_engine.py` | `services/demo_generation_service.py` | servico interno | MVP-1 |
| `orchestrator.py:Orchestrator` | `services/agents/orchestrator_service.py` | servico + Agent Hub | MVP-1 |
| `orchestrator.py:AGENTS{}` | `services/agents/{module}_agent.py` (1 por agente) | servico isolado | MVP-1 |
| `rag.py` | `services/knowledge_service.py` + Qdrant | Qdrant local | MVP-2 |
| `generators/dam.py` | `services/export/dam_generator.py` | servico | MVP-1 |
| `generators/wp.py` | `services/export/wp_generator.py` | servico | MVP-1 |
| `database.py` | `core/database.py` + SQLAlchemy + Alembic | ORM | MVP-1 |
| `db/persistence.py` | Eliminado (substituido por SQLAlchemy) | — | MVP-1 |

---

## 5. Endpoints do Backend (API v1)

### 5.1 Auth e Tenant (Padrao)

```
POST   /auth/register
POST   /auth/login
POST   /auth/refresh
GET    /auth/me
POST   /auth/logout
```

### 5.2 Setup / Onboarding (Padrao)

```
GET    /setup/status
POST   /setup/step
POST   /setup/complete
```

### 5.3 Billing (Padrao — proxy para Agent Hub)

```
GET    /billing/subscription
GET    /billing/limits
GET    /billing/features
```

### 5.4 Integracao Agent Hub (Padrao)

```
POST   /api/v1/integrations/agent-hub/provision
POST   /api/v1/integrations/agent-hub/webhook
```

### 5.5 Endpoints de Dominio — Propostas

```
# Proposals (CRUD + Generation)
GET    /api/v1/proposals                     # Listar propostas (tenant + company filter)
POST   /api/v1/proposals                     # Criar proposta (intake + gerar)
GET    /api/v1/proposals/{id}                # Detalhe da proposta
PUT    /api/v1/proposals/{id}                # Editar proposta (campos editaveis)
DELETE /api/v1/proposals/{id}                # Deletar proposta
PATCH  /api/v1/proposals/{id}/status         # Mudar status (draft→review→approved→won/lost)

# Generation
POST   /api/v1/proposals/{id}/regenerate     # Regenerar com novos parametros
WS     /ws/proposals/{id}/generate           # WebSocket streaming de geracao

# Export
GET    /api/v1/proposals/{id}/export/dam     # Download DAM Word
GET    /api/v1/proposals/{id}/export/wp      # Download WP Excel
GET    /api/v1/proposals/{id}/export/pdf     # Download PDF (futuro)

# Resources (Work Package)
GET    /api/v1/proposals/{id}/resources      # Listar recursos
PUT    /api/v1/proposals/{id}/resources      # Editar recursos (bulk)

# Deliverables
GET    /api/v1/proposals/{id}/deliverables   # Listar entregaveis
PUT    /api/v1/proposals/{id}/deliverables   # Editar entregaveis (bulk)

# Agent Executions (read-only)
GET    /api/v1/proposals/{id}/agents         # Log de agentes executados
```

### 5.6 Endpoints de Dominio — Knowledge Base (MVP-2)

```
GET    /api/v1/knowledge                     # Listar documentos
POST   /api/v1/knowledge                     # Criar documento
PUT    /api/v1/knowledge/{id}                # Editar documento
DELETE /api/v1/knowledge/{id}                # Deletar documento
POST   /api/v1/knowledge/search              # Busca semantica
POST   /api/v1/knowledge/bulk-import         # Import em lote
```

### 5.7 Endpoints de Dominio — Templates (MVP-2)

```
GET    /api/v1/templates                     # Listar templates
POST   /api/v1/templates                     # Criar template
PUT    /api/v1/templates/{id}                # Editar template
DELETE /api/v1/templates/{id}                # Deletar template
POST   /api/v1/templates/{id}/apply          # Aplicar template a uma proposta
```

### 5.8 Analytics (Onda 3)

```
GET    /api/v1/analytics/dashboard           # Metricas resumidas
GET    /api/v1/analytics/proposals           # Propostas por periodo/status/modulo
GET    /api/v1/analytics/agents              # Performance dos agentes IA
GET    /api/v1/analytics/conversion          # Taxa de conversao (draft→won)
```

---

## 6. Agentes IA — Refatoracao

### 6.1 De Monolito para Servicos Isolados

O `orchestrator.py` atual tem TUDO em 1 arquivo (269 linhas). Refatorar em:

```
services/agents/
  orchestrator_service.py      — Coordena execucao dos agentes
  base_agent.py                — Classe base com _call(), logging, error handling
  sd_agent.py                  — Agente SD (Sofia)
  fi_agent.py                  — Agente FI (Felix)
  abap_agent.py                — Agente ABAP (Axel)
  drc_agent.py                 — Agente DRC (Diana)
  fiscal_estadual_agent.py     — Agente Fiscal Estadual (Estela)
  fiscal_federal_agent.py      — Agente Fiscal Federal (Fabio)
  reforma_agent.py             — Agente Reforma Tributaria
  equipe_agent.py              — Agente Equipe/GP (Eduardo)
  comercial_agent.py           — Agente Comercial (Camila)
```

### 6.2 Execucao via Agent Hub

Substituir chamadas diretas ao Claude (`anthropic.Anthropic()`) por chamadas via Agent Hub:

```python
# ANTES (legado)
resp = client().messages.create(model="claude-sonnet-4-20250514", ...)

# DEPOIS (refatorado)
result = await agent_hub_client.execute_agent_task(
    task="sap_proposal_sd_analysis",
    payload={"intake": ctx, "rag_context": rag_ctx},
)
```

### 6.3 Execucao Paralela

Substituir execucao sequencial por paralela (asyncio.gather) quando agentes sao independentes:

```python
# Agentes SD, FI, ABAP podem rodar em paralelo
sd_result, fi_result, abap_result = await asyncio.gather(
    sd_agent.execute(ctx),
    fi_agent.execute(ctx),
    abap_agent.execute(ctx),
)
```

### 6.4 Logging de Execucao

Cada agente grava em `agent_executions` com tokens usados, duracao e resultado:

```python
class BaseAgent:
    async def execute(self, ctx: str) -> dict:
        start = time.monotonic()
        try:
            result = await self._call(ctx)
            await self._log(proposal_id, "done", result, duration_ms=...)
            return result
        except Exception as e:
            await self._log(proposal_id, "error", error_message=str(e))
            raise
```

---

## 7. Frontend — Estrutura React

### 7.1 Stack

React 19 + Vite 7 + TypeScript 5.9 + Tailwind 3.4 + shadcn/ui + i18next 25 + TanStack Query/Table + React Hook Form + Zod.

### 7.2 Layouts

| Layout | Uso |
|--------|-----|
| **AuthLayout** | Login, registro |
| **AdminLayout** | Configuracoes do tenant, usuarios, companies |
| **ProposalLayout** | Operacao principal: criar, gerar, revisar propostas |
| **WizardLayout** | Setup inicial do tenant |

### 7.3 Rotas

```
/login
/setup/wizard/:step

# Admin
/admin/dashboard
/admin/users
/admin/companies
/admin/billing
/admin/settings
/admin/knowledge                    # MVP-2

# Propostas (operacional)
/proposals                          # Lista
/proposals/new                      # Intake (formulario)
/proposals/:id                      # Detalhe / review
/proposals/:id/edit                 # Edicao
/proposals/:id/generate             # Visualizacao da geracao (agentes)
/proposals/:id/export               # Opcoes de export

# Analytics
/analytics/dashboard                # Onda 3
/analytics/agents                   # Onda 3

# Templates
/templates                          # MVP-2
/templates/:id                      # MVP-2
```

### 7.4 Paginas Principais

| Pagina | Descricao | Componentes-chave |
|--------|-----------|-------------------|
| **ProposalList** | Grid de propostas com filtros, busca, status badges | TanStack Table, StatusBadge, ProposalCard |
| **IntakeForm** | Formulario de entrada (5 campos obrigatorios + 3 opcionais) | React Hook Form, Zod, StepWizard |
| **GenerationView** | Visualizacao em tempo real dos agentes trabalhando | WebSocket, AgentCard, ConnectionLines, ChatBubbles, ProgressBar |
| **ProposalDetail** | Resumo, entregaveis, WP, premissas, comercial com botoes de detalhe | Tabs, DetailModal, CodeBlock (ABAP) |
| **ExportPreview** | Preview do DAM antes de baixar | DocumentPreview, DownloadButtons |
| **AnalyticsDash** | KPIs, graficos de conversao, horas por modulo | Recharts, KPICards |

### 7.5 Migracao do Frontend

| Componente Legado (index.html) | Componente React | Prioridade |
|-------------------------------|------------------|------------|
| `#pg-intake` (formulario inline) | `pages/IntakeForm.tsx` + `components/intake/*` | MVP-1 |
| `#pg-gen` (spinner de geracao) | `pages/GenerationView.tsx` + `components/agents/*` | MVP-1 |
| `#pg-draft` (resultado) | `pages/ProposalDetail.tsx` + `components/proposal/*` | MVP-1 |
| `#pg-proposals` (lista) | `pages/ProposalList.tsx` | MVP-1 |
| `#pg-analytics` (dashboard) | `pages/AnalyticsDash.tsx` | Onda 3 |
| `#pg-viz` (visualizacao agentes) | `pages/GenerationView.tsx` (integrado) | MVP-1 |
| `agents-viz.html` (standalone) | Integrado no GenerationView | MVP-1 |
| `showDetail()` (modal profissional) | `components/proposal/DetailModal.tsx` | MVP-1 |
| `DETAIL_DATA` (transacoes hardcoded) | `data/sap-transactions.ts` | MVP-1 |

---

## 8. Variaveis de Ambiente Especificas

```bash
# === App ===
APP_NAME=sap_proposal
VERSION=1.0.0

# === Dominio SAP ===
SAP_DEFAULT_TARIFF_PER_HOUR=230        # Tarifa padrao por hora
SAP_DEFAULT_WARRANTY_DAYS=30
SAP_DEFAULT_VALIDITY_DAYS=30
SAP_DEFAULT_BILLING_SPLIT=50/50
SAP_MAX_AGENTS_PARALLEL=4
SAP_AGENT_TIMEOUT_SECONDS=60
SAP_DEMO_MODE_ENABLED=true             # Habilita fallback sem LLM

# === RAG / Qdrant ===
QDRANT_URL=http://qdrant-sap-proposal:6333
QDRANT_COLLECTION_PREFIX=sap_proposal

# === Export ===
DAM_TEMPLATE_PATH=/data/sap_proposal/templates/dam_template.docx
WP_TEMPLATE_PATH=/data/sap_proposal/templates/wp_template.xlsx
EXPORT_STORAGE_PATH=/data/sap_proposal/exports
```

---

## 9. Estrutura de Diretorios Refatorada

```
sap-proposal-app/
├── backend/
│   ├── main.py
│   ├── core/
│   │   ├── config.py                     # BaseSettings + env vars
│   │   ├── database.py                   # SQLAlchemy engine + session
│   │   ├── security.py                   # JWT, RBAC (agn-auth)
│   │   ├── rate_limiter.py
│   │   ├── trace_middleware.py
│   │   ├── subscription_middleware.py
│   │   └── logger.py                     # structlog
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tenant.py                     # agn-core
│   │   ├── user.py                       # agn-core
│   │   ├── company.py                    # agn-core
│   │   ├── audit_log.py                  # agn-audit
│   │   └── sap_proposal/                 # DOMINIO
│   │       ├── proposal.py
│   │       ├── proposal_resource.py
│   │       ├── proposal_deliverable.py
│   │       ├── proposal_premise.py
│   │       ├── proposal_legislation.py
│   │       ├── proposal_dam.py
│   │       ├── knowledge_document.py
│   │       ├── proposal_template.py
│   │       └── agent_execution.py
│   ├── schemas/                          # Pydantic
│   │   ├── proposal.py
│   │   ├── intake.py
│   │   ├── resource.py
│   │   └── knowledge.py
│   ├── services/
│   │   ├── auth_service.py               # agn-auth
│   │   ├── onboarding_service.py
│   │   └── sap_proposal/
│   │       ├── proposal_service.py       # CRUD + business rules
│   │       ├── generation_service.py     # Orquestrar geracao
│   │       ├── demo_generation_service.py # Fallback sem LLM
│   │       ├── knowledge_service.py      # RAG + Qdrant
│   │       ├── export_service.py         # DAM + WP generation
│   │       └── agents/                   # 1 arquivo por agente
│   │           ├── base_agent.py
│   │           ├── orchestrator.py
│   │           ├── sd_agent.py
│   │           ├── fi_agent.py
│   │           ├── abap_agent.py
│   │           ├── drc_agent.py
│   │           ├── fiscal_estadual_agent.py
│   │           ├── fiscal_federal_agent.py
│   │           ├── reforma_agent.py
│   │           ├── equipe_agent.py
│   │           └── comercial_agent.py
│   ├── apis/
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── setup.py
│   │       ├── billing.py
│   │       └── sap_proposal/
│   │           ├── proposals.py
│   │           ├── knowledge.py
│   │           ├── templates.py
│   │           └── analytics.py
│   ├── integrations/
│   │   └── agent_hub_client.py
│   ├── data/
│   │   └── sap_knowledge_base.py         # 26 documentos iniciais (seed)
│   ├── migrations/                       # Alembic
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── api/
│   │   └── isolation/
│   └── scripts/
│       ├── seed_sap_proposal_platform.py
│       └── migrate_legacy_data.py        # ETL do banco antigo
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── routes/
│   │   ├── layouts/
│   │   ├── pages/
│   │   │   ├── IntakeForm.tsx
│   │   │   ├── GenerationView.tsx
│   │   │   ├── ProposalDetail.tsx
│   │   │   ├── ProposalList.tsx
│   │   │   └── AnalyticsDash.tsx
│   │   ├── components/
│   │   │   ├── agents/                   # AgentCard, AgentGrid, ChatBubble
│   │   │   ├── proposal/                 # DetailModal, CodeBlock, WPTable
│   │   │   ├── intake/                   # StepWizard, UfSelector
│   │   │   └── ui/                       # shadcn/ui components
│   │   ├── data/
│   │   │   └── sap-transactions.ts       # Migrar DETAIL_DATA do HTML
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── i18n/
│   └── public/locales/{pt,en,es}/
├── shared/                               # Submodule agn-shared
├── deployment/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── nginx.conf
├── docs/
│   └── ARCHITECTURE.md                   # Este documento
├── Makefile
└── README.md
```

---

## 10. Onboarding — Defaults

`SapProposalOnboardingService.create_tenant_with_defaults()`:

| Recurso | Default |
|---------|---------|
| **Tenant** | Nome, slug, plan_slug, branding |
| **Owner User** | Pre-vendas SAP como owner |
| **Company** | Consultoria principal |
| **ProposalTemplate** | Template padrao Cast Group (premissas, recursos, branding) |
| **KnowledgeDocument** | 26 documentos iniciais (fiscal, ABAP, metodologia SAP Activate) |
| **TenantSetupStatus** | Wizard: empresa → usuarios → template → branding → agente IA → conclusao |
| **Theme** | Skin default (cores Cast Group) |

---

## 11. Seed de Dados

### 11.1 Knowledge Base Inicial

Migrar os 26 documentos de `rag.py:KNOWLEDGE_BASE` para `scripts/seed_sap_proposal_platform.py`:

| Categoria | Docs | Exemplos |
|-----------|------|----------|
| fiscal | 8 | ECONF 110750, cBenef ICMS, IN 1.608/2025-GO, Portaria SRE 70/2025 SP |
| abap | 4 | Cadeia BAPI→BAdI→RFC→iFlow→Monitor, regra 4+ objetos = 3 ABAPers |
| methodology | 4 | SAP Activate, KT AMS, WP estrutura |
| cast_group | 4 | DAM estrutura, premissas padrao, modelo comercial |
| reform | 3 | LC 214, IBS/CBS, cronograma reforma |
| integration | 3 | DRC vs CPI, SVRS endpoints, ECONF canais |

### 11.2 Premissas Padrao

```python
DEFAULT_PREMISES = [
    "Os acessos necessarios deverao estar liberados ate o inicio do projeto.",
    "Os usuarios disponibilizados deverao ter acesso para depuracao no ambiente de Qualidade.",
    "Todos os desenvolvimentos serao realizados em ABAP.",
    "Gerenciamento remoto durante toda a execucao do projeto.",
    "Dia de consultoria: 8h (08h30-12h/13h30-18h), segunda a sexta.",
    "Duvidas ou falhas devem ser reportadas durante o periodo de testes.",
    "Qualquer atraso por motivo do cliente comprometera o prazo sem onus a Cast Group.",
    "A documentacao sera entregue em lingua portuguesa.",
]
```

---

## 12. Decisoes Arquiteturais (ADRs)

### ADR-001 a ADR-012: Herdadas do Template

(Ver ARCHITECTURE_REFACTORING_TEMPLATE.md §28)

### ADR-013: RLS Desabilitado

- **Decisao:** NAO usar RLS. Filtragem apenas no service layer + isolation tests.
- **Razao:** Dados de propostas SAP nao sao regulados LGPD (sao dados comerciais internos da consultoria). Simplicidade operacional.

### ADR-014: Demo Mode Preservado

- **Decisao:** Manter `demo_generation_service.py` como fallback quando Agent Hub / LLM esta offline.
- **Razao:** Permite demonstracoes para clientes sem depender de LLM. Feature flag `SAP_DEMO_MODE_ENABLED`.

### ADR-015: Agentes em Paralelo

- **Decisao:** Agentes SD, FI, ABAP rodam em paralelo via `asyncio.gather`. Equipe e Comercial aguardam os anteriores.
- **Razao:** Reduz tempo de geracao de ~45s (sequencial) para ~15s (paralelo parcial).

### ADR-016: Qdrant para RAG (MVP-2)

- **Decisao:** Qdrant local substituindo o RAG hash-based fake atual.
- **Razao:** Busca semantica real, latencia <100ms, dados sensiveis nao trafegam.

### ADR-017: Documentos Gerados Persistidos

- **Decisao:** DAM Word e WP Excel sao gerados sob demanda (nao persistidos como arquivo). DAM JSON e persistido em `proposal_dams`.
- **Razao:** Evita storage de binarios; Word/Excel sao regeneraveis a qualquer momento a partir do JSON.

---

## 13. Checklist de Implementacao

### Fase 1: Fundacao (Semana 1-2)
- [ ] Criar repositorio `sap-proposal-app`
- [ ] Setup FastAPI + SQLAlchemy + Alembic
- [ ] Modelos base (Tenant, User, Company) via agn-core
- [ ] Auth (register, login, JWT, RBAC) via agn-auth
- [ ] Middleware stack (CORS, Trace, RateLimit, Subscription)
- [ ] Docker Compose (postgres, redis, backend)
- [ ] Health check + structlog
- [ ] pytest + conftest + fixtures base
- [ ] CI pipeline (GitHub Actions)
- [ ] Makefile

### Fase 2: Onboarding e Plataforma (Semana 2-3)
- [ ] Receptor `/api/v1/integrations/agent-hub/provision`
- [ ] `SapProposalOnboardingService.create_tenant_with_defaults()`
- [ ] Setup wizard backend
- [ ] agn-billing client
- [ ] Subscription middleware
- [ ] Seed platform data (26 knowledge docs + premissas)
- [ ] Settings completas + `.env.production.example`
- [ ] Testes: onboarding, billing client, seed, isolation base

### Fase 3: Dominio MVP-1 — Propostas (Semana 3-5)
- [ ] Models: Proposal, ProposalResource, ProposalDeliverable, ProposalPremise, ProposalLegislation, ProposalDam, AgentExecution
- [ ] Alembic migration
- [ ] `proposal_service.py` (CRUD + business rules)
- [ ] `generation_service.py` (orquestrador)
- [ ] `demo_generation_service.py` (migrar demo_engine.py)
- [ ] Agentes individuais (10 arquivos)
- [ ] `agent_hub_client.py` (LLM via Agent Hub)
- [ ] `export_service.py` (migrar dam.py + wp.py)
- [ ] WebSocket para streaming de geracao
- [ ] APIs v1: proposals, resources, deliverables, agents
- [ ] Isolation tests para TODOS os modelos
- [ ] Coverage ≥ 80% services

### Fase 4: Frontend MVP-1 (Semana 5-7)
- [ ] React 19 + Vite + Tailwind + shadcn/ui + i18next
- [ ] Auth flow (login, refresh, ProtectedRoute)
- [ ] Layouts (Auth, Admin, Proposal)
- [ ] IntakeForm (migrar formulario do index.html)
- [ ] GenerationView (migrar agents-viz.html para React)
- [ ] ProposalDetail (migrar renderDraft + DetailModal)
- [ ] ProposalList (migrar pg-proposals)
- [ ] Export (download DAM/WP)
- [ ] i18n (pt-BR completo, en/es esqueleto)
- [ ] WebSocket integration para real-time generation

### Fase 5: MVP-2 — Knowledge + Templates (Semana 8-9)
- [ ] Models: KnowledgeDocument, ProposalTemplate
- [ ] Qdrant setup + embedding service
- [ ] Knowledge CRUD + search API
- [ ] Template CRUD + apply API
- [ ] Frontend: Knowledge management page
- [ ] Frontend: Template editor

### Fase 6: Onda 3 — Analytics + Collaboration (Semana 10-11)
- [ ] Analytics endpoints
- [ ] Frontend: AnalyticsDash (Recharts)
- [ ] ProposalComment, ProposalVersion models
- [ ] Workflow de aprovacao (status machine)

### Fase Final: Polish e Deploy (Semana 12)
- [ ] Nginx config + security headers
- [ ] Frontend Dockerfile
- [ ] CI/CD completo (deploy staging + producao)
- [ ] Dry-run migracao de dados do banco legado
- [ ] Rollback plan (manter SQLite legado 30 dias)
- [ ] Deploy producao

---

## 14. Migracao de Dados

### 14.1 Script ETL

```python
# scripts/migrate_legacy_data.py
def migrate():
    legacy_db = connect_sqlite("data/proposals.db")
    new_db = get_session()

    with new_db.begin():
        # 1. Criar tenant default (Cast Group)
        tenant = create_default_tenant(new_db)

        # 2. Criar company default
        company = create_default_company(new_db, tenant.id)

        # 3. Criar owner user
        owner = create_owner(new_db, tenant.id)

        # 4. Migrar proposals
        for row in legacy_db.execute("SELECT * FROM proposals"):
            proposal = Proposal(
                tenant_id=tenant.id,
                company_id=company.id,
                created_by=owner.id,
                title=row["title"],
                project_type=row["project_type"],
                sap_version=row["sap_version"],
                states=json.loads(row["states"]),
                # ...
            )
            new_db.add(proposal)
            new_db.flush()

            # Desnormalizar JSONs em tabelas
            for r in json.loads(row["resources_json"] or "[]"):
                new_db.add(ProposalResource(
                    tenant_id=tenant.id,
                    proposal_id=proposal.id,
                    frente=r["frente"],
                    nivel=r["nivel"],
                    dias=r["dias"],
                    horas=r["dias"] * 8,
                ))

            for e in json.loads(row["entregaveis_json"] or "[]"):
                new_db.add(ProposalDeliverable(
                    tenant_id=tenant.id,
                    proposal_id=proposal.id,
                    module=e.get("mod", ""),
                    item=e.get("item", ""),
                ))

            # ... premissas, legislacao, dam

    validate_migration(legacy_db, new_db)
```

### 14.2 Validacao

- Contar proposals: legado vs novo
- Verificar que todos os resources foram desnormalizados
- Verificar que todos os JSONs foram parseados corretamente
- Testar export DAM/WP a partir dos dados migrados

---

## 15. Riscos e Mitigacoes

| Risco | Impacto | Mitigacao |
|-------|---------|-----------|
| Agent Hub offline durante geracao | Alto | Demo mode como fallback (ADR-014) |
| Perda de dados na migracao | Alto | Script ETL idempotente + dry-run em staging + rollback plan 30 dias |
| Frontend React muito diferente do HTML atual | Medio | Migrar componente a componente, manter HTML legado ate MVP-1 completo |
| Regras de negocio SAP incorretas apos refactor | Alto | Testes com cenarios reais (GO+ECONF, SP+cBenef, migration S/4) |
| Performance de geracao com 10 agentes | Medio | Execucao paralela (ADR-015) + timeout por agente |

---

*Documento gerado em 2026-04-10. Especializado a partir de ARCHITECTURE_REFACTORING_TEMPLATE.md v1.1 para o dominio Sil-Proposta (SAP Proposal Generator). Sujeito a revisoes durante implementacao.*
