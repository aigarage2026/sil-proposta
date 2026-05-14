# Arquitetura: Portal SaaS v2 (Control Plane + Produtos Modulares)

> **Versao:** 2.0
> **Data:** 2026-04-08
> **Status:** Proposta para retomada do estudo (apos planos HR Recruitment e ITSM)
> **Predecessor:** [ARCHITECTURE_PORTAL_SAAS.md v1.0](ARCHITECTURE_PORTAL_SAAS.md) (mar/2026) — preservado como historico
> **Documentos relacionados:**
> - [ARCHITECTURE_HR_RECRUITMENT.md](ARCHITECTURE_HR_RECRUITMENT.md) — primeiro produto modular
> - [ARCHITECTURE_ITSM.md](ARCHITECTURE_ITSM.md) — segundo produto modular

---

## Sumario Executivo

Esta v2 evolui o estudo original do Portal SaaS, consolidando-o como **arquitetura-alvo** com:

1. **Boas praticas pesquisadas (2025-2026):** AWS SaaS Lens (silo/pool/bridge), Control Plane / Application Plane separation, Cell-based architecture, JWT/JWKS para identidade federada, Stripe multi-product subscriptions, microfrontend trade-offs.
2. **Modelo arquitetural-alvo** consolidado em 22 secoes com diagramas, contratos de API e decisao explicita sobre 10 perguntas que ficaram em aberto no v1.
3. **10 ADRs** justificando trade-offs com referencia direta as fontes.
4. **Plano de migracao em 10 fases** a partir do estado atual do `agent-hub`, com mapeamento concreto de paths reais (services, models, APIs, frontend pages) para cada repositorio destino. Estrategia escalonada: Timesheet (piloto) → HR → ITSM → Scheduling → Chatbot, preservando a aplicacao atual em operacao ate validacao completa.
5. **Tabela antes vs depois** cobrindo performance, manutencao, escalabilidade, blast radius, isolamento, time-to-market, cross-sell e custo.

A v2 NAO substitui a v1 — convivem no diretorio `pending/`. A v1 mantem-se como registro do raciocinio inicial; a v2 e o documento operacional para execucao.

---

## 1. Principios Arquiteturais

| Principio | Descricao |
|-----------|-----------|
| **Control Plane / Application Plane separation** | O Portal e o **control plane** (gerencia tenants, billing, auth, observabilidade). Os produtos sao **application planes** que entregam valor de negocio multi-tenant. Padrao canonico AWS/Azure 2025. |
| **Bridge Isolation Model** | Portal em **pool** (eficiencia operacional), produtos em **silo logico** via database-per-product (blast radius minimo). Combina o melhor dos dois mundos. |
| **API-First** | Portal e produtos comunicam-se exclusivamente via REST documentado + JWT. **Proibido** acesso direto ao DB de outro servico. |
| **Database-per-Product** | Cada produto tem sua propria database (logica ou fisica). Migrations isoladas, backups independentes, schemas livres para evoluir. |
| **Identidade Federada (JWKS RS256)** | Portal e o unico emissor de JWT, assinados com chave **assimetrica**. Produtos validam localmente via JWKS publico. Rotacao sem redeploy. |
| **Shared Libraries (`agn-*`)** | Pacotes Python/TS internos para evitar drift entre servicos. Mesmos pacotes definidos nos planos HR e ITSM. |
| **Multi-repo** | Portal + cada produto em repositorio separado. Shared libs como Git submodule (curto prazo) → registry privado (longo prazo). |
| **Migracao gradual (sem big-bang)** | API Gateway na frente permite extracao incremental do agent-hub legacy. Feature flags + dual-mode auth garantem zero downtime. |
| **Observabilidade desde dia zero** | Trace ID propagado end-to-end, structured logging, audit central, healthcheck consolidado. |
| **Security by Default** | Cada servico atras do Gateway, rate limiting, mTLS opcional, secrets via vault, RLS substituido por enforcement no service layer + isolation tests. |
| **Evolucao para Cell-Based** | Quando atingir >100 tenants, considerar agrupamento em celulas independentes para enterprise/compliance. ADR aberto. |

---

## 2. Modelo-Alvo (Diagrama de Componentes)

```
                              ┌────────────────────────┐
                              │ Cloudflare (SSL/DDoS)  │
                              └───────────┬────────────┘
                                          │
                              ┌───────────┴────────────┐
                              │  Nginx (API Gateway)   │
                              │  - Rate limiting       │
                              │  - JWT pre-validation  │
                              │  - Routing por prefix  │
                              │  - WAF + headers       │
                              └─┬────┬────┬────┬────┬─┘
                                │    │    │    │    │
        ┌───────────────────────┘    │    │    │    └───────────────┐
        │                            │    │    │                    │
        │         ┌──────────────────┘    │    └─────────────┐      │
        │         │                       │                  │      │
   ┌────┴────┐ ┌──┴──────┐ ┌──────────┐ ┌─┴────────┐ ┌──────┴───┐ ┌┴────────┐
   │ Portal  │ │Schedul. │ │Timesheet │ │   HR     │ │  ITSM    │ │ Chatbot │
   │Frontend │ │ Backend │ │ Backend  │ │ Backend  │ │ Backend  │ │ Backend │
   │  (SPA)  │ │         │ │          │ │          │ │          │ │         │
   └─────────┘ └───┬─────┘ └───┬──────┘ └───┬──────┘ └───┬──────┘ └───┬─────┘
                  │            │            │            │            │
   ┌─────────┐    │            │            │            │            │
   │ Portal  │    │            │            │            │            │
   │ Backend │◄───┴────────────┴────────────┴────────────┴────────────┘
   │ (Control│      (auth via JWKS, billing API, audit, usage events)
   │  Plane) │
   └────┬────┘
        │
   ┌────┴─────┬──────────┬──────────┬──────────┬──────────┬──────────┐
   │          │          │          │          │          │          │
┌──┴──┐ ┌─────┴────┐ ┌───┴────┐ ┌───┴────┐ ┌───┴────┐ ┌───┴────┐ ┌───┴───┐
│Portal│ │Scheduling│ │Timeshet│ │   HR   │ │  ITSM  │ │Chatbot │ │Stripe │
│  DB  │ │    DB    │ │   DB   │ │   DB   │ │   DB   │ │   DB   │ │       │
└──────┘ └──────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └───────┘
   ↑         ↑           ↑          ↑          ↑          ↑
   │         │           │          │          │          │
   └─────────┴───────────┴──────────┴──────────┴──────────┘
        Redis (compartilhado, namespaced por servico)
        Qdrant (compartilhado ou dedicado conforme produto)
```

### 2.1 Componentes

| Componente | Responsabilidade | Stack |
|-----------|------------------|-------|
| **Cloudflare** | DNS, SSL termination, DDoS, WAF, bot management | - |
| **Nginx Gateway** | Reverse proxy, rate limit, routing por prefix, security headers, WS upgrade | nginx 1.25 |
| **Portal Frontend** | SPA unico React com lazy modules por produto. Roteamento via React Router. Gating por `jwt.products[]`. | React 19 + Vite 7 + Tailwind + shadcn/ui + i18next |
| **Portal Backend (Control Plane)** | Auth/JWKS, Onboarding, Stripe billing, Tenant/Company/User CRUD, Audit central, Backup orchestration, Healthcheck aggregator, Usage tracking, Catalogo de produtos, Platform admin | FastAPI + SQLAlchemy + Postgres + Redis |
| **Product Backends** | Cada produto: dominio especifico, propria DB, propria CI/CD, proprio container, proprio scaling | FastAPI + SQLAlchemy + Postgres (DB-per-product) |
| **Stripe** | Pagamentos. Single subscription com multi-line items. Webhook unico no Portal. | Stripe Billing |
| **Redis** | Cache, sessions, rate limiting, JWKS cache, event streams (Redis Streams). Namespaced por servico (`portal:*`, `scheduling:*`, etc.) | Redis 7 |
| **Qdrant** | Busca semantica. Compartilhado entre produtos com collections nomeadas, ou dedicado para produtos com requisitos altos (ITSM KB, HR CV) | Qdrant 1.12+ |
| **Postgres** | Inicialmente cluster compartilhado com **databases logicas separadas** por produto. Enterprise tenants migram para clusters dedicados (silo total). | Postgres 16 |

### 2.2 Tres Modos de Acoplamento entre Servicos

1. **Sincrono (REST + JWT):** chamadas diretas entre Portal ↔ Produto. Latencia p50 < 50ms intra-cluster. Para queries de billing, validacao de tenant, fan-out de healthcheck.
2. **Assincrono (Redis Streams):** eventos cross-product. Portal publica `tenant.created`, `subscription.upgraded`, `user.role_changed`; produtos consomem. Eventos sao **at-least-once** + idempotente.
3. **Compartilhamento de bibliotecas (`agn-*`):** zero acoplamento de runtime, mas mesmo codigo Python/TS para auth, models base, billing client, etc.

**Proibido:**
- Acesso direto ao DB de outro servico (regra arquitetural — bloqueada por network policy + code review).
- JOIN cross-product no banco.
- Compartilhamento de chave HMAC (substituido por JWKS RS256).

---

## 3. Control Plane (Portal): Responsabilidades Detalhadas

### 3.1 Identidade

- Auth (signup, login, refresh, logout, recovery)
- Google/Microsoft OAuth
- MFA (TOTP) e OTP por email/SMS
- JWT issuance (RS256) + JWKS publico
- RBAC base (super_admin, platform_admin, tenant_admin, owner, admin, user)
- Roles **por produto** (ex.: `roles.scheduling = ["admin"]`, `roles.itsm = ["agent"]`)
- Brute force protection (Redis-backed)
- Sessoes / refresh tokens

### 3.2 Tenant Lifecycle

- Onboarding centralizado (signup → checkout → criacao do tenant)
- Setup wizard delegado (Portal coordena, produtos contribuem com steps proprios)
- Provisionamento de produtos via HMAC token (reaproveita pattern de [backend/services/itsm_provisioning_service.py](../../../backend/services/itsm_provisioning_service.py))
- Upgrade/downgrade de planos
- Cancelamento (com periodo de retencao configuravel)
- Soft delete e hard delete (LGPD)

### 3.3 Billing Unificado

- Single Stripe Subscription por tenant
- `subscription.items[]` com 1 line item por produto contratado
- Mixed interval support (alguns produtos mensais, outros anuais)
- Webhook unico no Portal → fan-out de eventos para cada produto
- Stripe Billing Portal embedado para self-service
- Free trial cross-product (14 dias na ativacao)
- Usage-based billing: produtos enviam eventos via `POST /api/portal/usage/events`

### 3.4 Catalogo de Produtos

- Produtos cadastrados na tabela `products` (slug, nome, descricao, planos, features)
- Frontend exibe os disponiveis no dashboard, indicando ativos vs disponiveis
- Cliente ativa um produto com 1 clique → Portal chama provisioning hook do produto

### 3.5 Users & Companies

- CRUD central
- Convites por email
- Roles por tenant + por produto
- Companies como sub-divisoes do tenant (ex.: matriz + filiais)
- User-company-product mapping

### 3.6 Dashboard Geral Consolidado

- `/api/portal/dashboard/aggregate` faz fan-out para `{produto}/api/v1/dashboard/summary`
- Cada produto retorna metricas resumidas + alertas + MRR contribuido
- Cache Redis 60s
- Frontend renderiza com 1 card por produto + drill-down navega para a area do produto
- Charts agregados (MRR total, tickets total, agendamentos total, etc.)

### 3.7 Healthcheck Consolidado

- `HealthAggregator` no Portal sondagem todos os produtos paralelamente (timeout 2s)
- `/api/portal/health/all` retorna status individual + agregado
- Status: green (todos OK), yellow (>=1 degraded), red (>=1 down)
- Page admin `/platform/health` mostra historico (24h) com grafico
- Alertas via Slack/PagerDuty quando algo cair
- Integracao opcional com Prometheus/Grafana

### 3.8 Branding/Themes

- CSS variables centralizadas no Portal
- Cada tenant configura cores, logo, favicon, fonte
- Frontend SPA aplica theme global; produtos herdam via context
- Suporte a dark mode + temas customizados (Onda 3 do plano ITSM ja preve isso)

### 3.9 Audit Log Central

- Cada produto envia eventos via `POST /api/portal/audit/events` (fire-and-forget queue)
- Tabela `audit_logs` no Portal acumula tudo
- Visao cross-product no admin
- Filtros por tenant, usuario, produto, acao, data
- Retencao configuravel por plano

### 3.10 Backup Orchestration

- Portal coordena, mas cada produto faz seu proprio dump
- `BackupCoordinator` chama `{produto}/api/v1/backup/snapshot` em paralelo
- Resultado consolidado armazenado em storage cifrado
- Restore tambem orquestrado (preview antes de aplicar)

### 3.11 Platform Admin

- Visao super_admin cross-tenant
- Lista de tenants ativos, MRR, usage, healthcheck
- Acoes: suspender, dar refund, forcar upgrade, simular logon
- Audit logs de tudo que platform admin faz

### 3.12 Invite Codes

- Codigos de convite para signup controlado
- Por plano, por produto, com validade e quota
- Reaproveita pattern existente em [backend/models/invite_code.py](../../../backend/models/invite_code.py)

### 3.13 i18n Base

- Idiomas globais (pt-BR, en, es) gerenciados no Portal
- Cada produto tem namespaces proprios (`scheduling`, `itsm.tickets`, etc.)
- Resolucao hierarquica: tenant > company > user > default

### 3.14 Settings Globais

- `platform_settings` table
- Configuracoes de plataforma (limites globais, feature flags, modo de manutencao)
- Editavel por super_admin via UI

---

## 4. Application Planes (Produtos): Especificacao

Cada produto tem o mesmo "esqueleto" e atende ao mesmo contrato de integracao com o Portal.

### 4.1 Contrato Comum a Todo Produto

| Endpoint | Metodo | Quem chama | Proposito |
|----------|--------|-----------|-----------|
| `POST /api/v1/integrations/portal/provision` | Portal → Produto | Portal | Cria tenant local com defaults (HMAC token validado) |
| `POST /api/v1/integrations/portal/deprovision` | Portal → Produto | Portal | Soft delete do tenant local quando produto desativado |
| `GET /api/v1/dashboard/summary` | Produto | Portal (fan-out) | Retorna metricas resumidas para o dashboard agregado |
| `GET /health` | Produto | Portal (HealthAggregator) | Status do produto + dependencias |
| `POST /api/v1/backup/snapshot` | Portal → Produto | Portal (BackupCoordinator) | Gera dump local e retorna handle |
| `POST /api/v1/restore` | Portal → Produto | Portal | Aplica restore a partir de handle |
| `GET /.well-known/openapi.json` | Produto | Portal/devs | OpenAPI spec do produto |

### 4.2 Eventos que o Produto Consome do Portal (Redis Streams)

| Evento | Acao no Produto |
|--------|-----------------|
| `tenant.created` | Cria tenant local (alternativa ao provisioning sincrono) |
| `tenant.suspended` | Bloqueia acesso (read-only) |
| `tenant.deleted` | Soft delete; agenda hard delete |
| `subscription.upgraded` | Atualiza limits/features locais |
| `subscription.downgraded` | Aplica downgrade local apos validacao |
| `subscription.canceled` | Marca tenant para deprovision em D+30 |
| `user.created` | Cria user local opcional (lazy) |
| `user.role_changed` | Atualiza permissoes locais |

### 4.3 Eventos que o Produto Emite

| Evento | Quem consome | Proposito |
|--------|-------------|-----------|
| `usage.metric` | Portal (billing) | Reporta uso para usage-based billing |
| `audit.action` | Portal (audit central) | Registra acao do usuario para audit log |
| `health.degraded` | Portal (alerting) | Notifica degradacao de dependencia |
| `tenant.feature_used` | Portal (analytics) | Tracking de adocao de features |

### 4.4 Inventario de Produtos

| Produto | Status | Fase | Origem | Plano detalhado |
|---------|--------|------|--------|----------------|
| **portal** | A criar | Fase 1 | Extraido do agent-hub atual | Este documento |
| **timesheet-app** | A extrair (piloto) | Fase 3 | `backend/services/timesheet/*`, `backend/models/timesheet/*`, `backend/apis/v1/timesheet*.py` | A criar |
| **hr-recruitment** | Em desenvolvimento | Fase 4 | Nasce ja no padrao novo (apos finalizacao de ajustes na app atual) | [ARCHITECTURE_HR_RECRUITMENT.md](ARCHITECTURE_HR_RECRUITMENT.md) |
| **itsm-app** | Em planejamento | Fase 5 | Nasce ja no padrao novo (apos finalizacao de ajustes na app atual) | [ARCHITECTURE_ITSM.md](ARCHITECTURE_ITSM.md) |
| **scheduling-app** | A extrair | Fase 6 | `backend/services/scheduling*`, `backend/models/scheduling/*`, `backend/apis/v1/scheduling.py` | A criar (analogo ao plano HR) |
| **chatbot-app** | A extrair | Fase 7 | `backend/services/chat_service.py`, RAG, voice, WhatsApp | A criar |

---

## 5. Modelo de Isolamento (Bridge)

### 5.1 Decisao

A plataforma adota o **Bridge Model** do AWS SaaS Lens — combinacao de **pool** para o Portal e **silo logico** para os produtos.

| Camada | Modelo | Justificativa |
|--------|--------|---------------|
| **Portal (control plane)** | Pool | Operacoes de control plane (auth, billing, onboarding) sao caras de duplicar; pool maximiza eficiencia operacional. |
| **Produtos (application plane)** | Silo logico (DB-per-product) | Blast radius minimo, schemas isolados, migrations independentes, escala independente, backups independentes. |
| **Tenants dentro de cada produto** | Pool com TenantMixin | Reaproveita pattern validado no agent-hub atual. Para enterprise, evolui para cluster dedicado (silo total). |

### 5.2 Implementacao Inicial vs Evolucao

```
Inicial (Fase 1-10):
  Cluster Postgres unico
   ├── portal_db          (schema portal)
   ├── scheduling_db      (database logicamente separada)
   ├── timesheet_db
   ├── hr_db
   ├── itsm_db
   └── chatbot_db

Evolucao (>50 tenants enterprise ou compliance):
  Cluster compartilhado (tenants padrao)
   ├── portal_db
   ├── scheduling_db
   └── ...

  Cluster dedicado por enterprise tenant
   ├── enterprise_acme_scheduling_db
   ├── enterprise_acme_itsm_db
   └── ...
```

### 5.3 Por que NAO Pool puro

- Bug em scheduling pode afetar timesheet (mesmo schema, mesmo cluster)
- Migration falha em um produto bloqueia outros
- Performance issue de uma query trava toda a plataforma
- Vazamento de dados cross-tenant via bug de filter pode atravessar produtos

### 5.4 Por que NAO Silo puro (database-per-tenant)

- Custo (N tenants × M produtos = N×M databases)
- Operacao complexa (backup, monitoring, migrations)
- Onboarding lento (provisioning de cluster)
- Overkill para tenants pequenos

### 5.5 Por que NAO Cell-Based agora

- Recomendacao da AWS: cell-based e para escala muito grande (>10k tenants)
- Ainda nao temos o problema de noisy neighbor cross-tenant
- Adicionar cell awareness exigiria refatorar onboarding, routing e tooling
- Fica como ADR de evolucao para quando atingir massa critica

---

## 6. Identidade Compartilhada (JWKS)

### 6.1 Decisao Critica vs v1

**v1:** propunha JWT HS256 com `JWT_SECRET` compartilhado entre Portal e produtos.
**v2:** adota **JWT RS256 + JWKS publico**.

Motivacao:
- HS256 exige distribuir o segredo por todos os servicos → vazamento em qualquer servico compromete toda a plataforma
- Rotacao de chave HS256 exige redeploy coordenado de todos os servicos
- RS256 + JWKS permite que cada produto valide tokens **localmente** sem chamar o Portal e sem conhecer a chave privada

### 6.2 Fluxo

```
1. Portal gera par de chaves RS256 (private em Secret Manager, public em /.well-known/jwks.json)
2. Usuario faz login no Portal → Portal assina JWT com private key
3. JWT e armazenado no frontend (httpOnly cookie ou localStorage)
4. Frontend faz request para /api/scheduling/* com Authorization: Bearer <jwt>
5. Nginx Gateway encaminha para scheduling-backend
6. scheduling-backend valida o JWT:
   a. Le o `kid` do header
   b. Busca a public key correspondente no cache local (TTL 24h)
   c. Se kid nao esta em cache, refetch /.well-known/jwks.json do Portal
   d. Valida assinatura, exp, iss, aud
   e. Extrai claims: sub, tenant_id, products[], roles{by_product}
7. scheduling-backend processa o request com o tenant_id e roles validados
```

### 6.3 JWT Claims

```json
{
  "sub": "user-uuid",
  "email": "user@empresa.com.br",
  "tenant_id": "tenant-uuid",
  "products": ["scheduling", "hr", "itsm"],
  "roles": {
    "platform": "tenant_admin",
    "scheduling": "admin",
    "hr": "viewer",
    "itsm": "agent"
  },
  "exp": 1736341200,
  "iat": 1736337600,
  "iss": "https://app.ai-garage.com.br",
  "aud": ["scheduling", "hr", "itsm", "portal"],
  "kid": "key-2026-04",
  "trace_id": "..."
}
```

### 6.4 Rotacao de Chaves (Sem Downtime)

```
Dia 0:    JWKS expoe { kid_old }
Dia 1:    Portal gera kid_new. JWKS expoe { kid_old, kid_new }. Portal continua assinando com kid_old.
Dia 2:    Portal comeca a assinar com kid_new. JWKS continua expondo ambos.
Dia 7:    Tokens antigos expirados. Portal remove kid_old do JWKS. Apenas kid_new ativo.
```

### 6.5 Migration Path do HS256 Atual

Durante a Fase 1-2 da migracao, o Portal deve aceitar **dual-mode**:
- Tokens HS256 emitidos pelo agent-hub legacy → validados via secret compartilhado
- Tokens RS256 emitidos pelo novo Portal → validados via JWKS

Apos cutover completo, remover suporte HS256.

---

## 7. Billing Multi-Produto (Stripe)

### 7.1 Modelo

```
Stripe Customer (1 por tenant)
  └── Stripe Subscription (1 por tenant)
       ├── SubscriptionItem 1: Portal Base (R$0 — incluso, gating)
       ├── SubscriptionItem 2: Scheduling Professional (R$197/mes)
       ├── SubscriptionItem 3: HR Recruitment Starter (R$397/mes)
       ├── SubscriptionItem 4: ITSM Professional (R$497/mes)
       └── SubscriptionItem 5 (usage): API Calls Overage ($0.001/call)
```

Fatura unica: R$1.091/mes (caso ciclos coincidam).

### 7.2 Tabelas no Portal

```python
class Subscription(Base, UUIDMixin, TimestampMixin):
    tenant_id = Column(ForeignKey("tenants.id"), nullable=False, unique=True)
    stripe_customer_id = Column(String(64))
    stripe_subscription_id = Column(String(64))
    status = Column(String(20))  # active, past_due, canceled, paused
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)


class SubscriptionItem(Base, UUIDMixin, TimestampMixin):
    subscription_id = Column(ForeignKey("subscriptions.id"))
    product_slug = Column(String(50), nullable=False, index=True)  # scheduling, hr, itsm, ...
    plan_id = Column(ForeignKey("plans.id"))
    stripe_subscription_item_id = Column(String(64))
    status = Column(String(20))  # active, trialing, canceled
    quantity = Column(Integer, default=1)
    activated_at = Column(DateTime)
    canceled_at = Column(DateTime)
    trial_ends_at = Column(DateTime)


class Plan(Base, UUIDMixin, TimestampMixin):
    product_slug = Column(String(50), nullable=False, index=True)
    slug = Column(String(50), nullable=False)  # starter, professional, enterprise
    name = Column(String(255))
    description = Column(Text)
    price_monthly = Column(Numeric(12, 2))
    price_yearly = Column(Numeric(12, 2))
    stripe_price_id_monthly = Column(String(64))
    stripe_price_id_yearly = Column(String(64))
    limits = Column(JSON)  # product-specific limits
    features = Column(JSON)  # feature flags
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer)


class UsageEvent(Base, UUIDMixin, TimestampMixin):
    """Eventos brutos enviados pelos produtos."""
    tenant_id = Column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_slug = Column(String(50), nullable=False)
    metric = Column(String(50), nullable=False)  # tickets_created, ai_resolutions, kb_articles, ...
    value = Column(BigInteger, default=1)
    metadata_json = Column("metadata", JSON)
    occurred_at = Column(DateTime, nullable=False, index=True)


class UsageAggregate(Base, UUIDMixin, TimestampMixin):
    """Agregados diarios/mensais para billing e dashboard."""
    tenant_id = Column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_slug = Column(String(50), nullable=False)
    metric = Column(String(50), nullable=False)
    period_type = Column(String(10))  # daily, monthly
    period_key = Column(String(20))   # 2026-04-08 ou 2026-04
    total = Column(BigInteger)
```

### 7.3 Webhook Stripe

`POST /api/portal/webhooks/stripe` — unico endpoint, valida signature.

Eventos tratados:
- `customer.subscription.created` → cria `Subscription` local
- `customer.subscription.updated` → atualiza items, dispara fan-out de eventos para produtos
- `customer.subscription.deleted` → marca canceled, agenda deprovision
- `invoice.paid` → registra Invoice
- `invoice.payment_failed` → entra em dunning workflow
- `customer.subscription.trial_will_end` → notifica tenant

### 7.4 Mixed Interval

Stripe permite items com periodos diferentes (mensal e anual no mesmo subscription). Quando os ciclos divergem, Stripe gera **faturas separadas**. Quando coincidem, **fatura unica**.

### 7.5 Self-Service

Frontend embeda Stripe Billing Portal via `POST /api/portal/billing/portal` que retorna URL de sessao. Cliente gerencia metodo de pagamento, troca de plano, downgrade, sem precisar tocar no Portal backend.

---

## 8. Onboarding e Provisionamento de Produtos

### 8.1 Fluxo Completo

```
1. Visitante acessa landing page do Portal
2. Clica "Comecar gratis" → Signup (email, senha, nome empresa, [invite_code])
3. Verificacao de email
4. Wizard de planos: seleciona produtos desejados (multi-select)
5. Stripe Checkout (com trial 14 dias)
6. Portal apos pagamento confirmado:
   a. Cria Tenant + Owner User
   b. Cria Subscription + SubscriptionItems
   c. Para CADA produto contratado:
      i.  Gera HMAC provisioning_token (TTL 5 min)
      ii. POST {product}/api/v1/integrations/portal/provision
          Body: {token, tenant_id, plan_slug, owner_email, defaults}
      iii. Produto valida HMAC, cria tenant local + defaults
      iv. Produto retorna {ok, internal_tenant_id, setup_url}
   d. Portal armazena referencias em ProductInstallation
   e. Portal redireciona usuario para o dashboard com cards de produtos ativos
7. Setup wizard: usuario configura cada produto sequencialmente
   - Steps comuns (empresa, branding, usuarios) ficam no Portal
   - Steps especificos (catalogo de servicos do ITSM, pipeline do HR) sao iframes ou paginas do produto
8. Setup completo → tenant marcado como onboarded
```

### 8.2 Tabela ProductInstallation

```python
class ProductInstallation(Base, UUIDMixin, TimestampMixin):
    tenant_id = Column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_slug = Column(String(50), nullable=False)
    status = Column(String(20))  # provisioning, active, deprovisioning, deprovisioned
    internal_tenant_id = Column(String(36))  # ID do tenant no produto
    provisioned_at = Column(DateTime)
    deprovisioned_at = Column(DateTime)
    last_health_check_at = Column(DateTime)
    last_health_status = Column(String(20))
    metadata_json = Column("metadata", JSON)

    __table_args__ = (
        UniqueConstraint("tenant_id", "product_slug", name="uq_tenant_product"),
    )
```

### 8.3 Provisioning Token (HMAC)

```python
# portal/services/provisioning.py
import hmac, hashlib, json, time, secrets

def generate_provisioning_token(tenant_id: str, product_slug: str, plan_slug: str) -> str:
    nonce = secrets.token_hex(16)
    expires_at = int(time.time()) + 300  # 5 min
    payload = {
        "tenant_id": tenant_id,
        "product_slug": product_slug,
        "plan_slug": plan_slug,
        "nonce": nonce,
        "expires_at": expires_at,
    }
    payload_json = json.dumps(payload, sort_keys=True)
    signature = hmac.new(
        settings.PROVISIONING_HMAC_SECRET.encode(),
        payload_json.encode(),
        hashlib.sha256,
    ).hexdigest()
    return base64url_encode(json.dumps({"payload": payload, "signature": signature}))
```

Cada produto valida com mesmo segredo (rotacionavel) e armazena `nonce` em Redis para anti-replay.

### 8.4 Setup Wizard Delegado

Wizard universal no Portal com steps comuns (empresa, branding, convidar usuarios). Cada produto registra **steps adicionais** via callback:

```python
# Cada produto, ao se registrar no Portal:
{
  "product_slug": "itsm",
  "name": "ITSM Service Desk",
  "wizard_steps": [
    {
      "key": "categories",
      "title": "Categorias de Servico",
      "url": "https://itsm.ai-garage.com.br/wizard/categories",
      "order": 10
    },
    {
      "key": "sla",
      "title": "Configurar SLA",
      "url": "https://itsm.ai-garage.com.br/wizard/sla",
      "order": 20
    }
  ]
}
```

Frontend Portal renderiza um wizard unico que carrega cada step (iframe ou redirect intermediado) na ordem correta.

---

## 9. Dashboard Geral Consolidado

### 9.1 Endpoint

```
GET /api/portal/dashboard/aggregate
Authorization: Bearer <jwt>
```

### 9.2 Implementacao

```python
# portal/services/dashboard_aggregator.py
async def aggregate_dashboard(tenant_id: str) -> dict:
    installations = get_active_installations(tenant_id)
    tasks = []
    for inst in installations:
        product = product_registry.get(inst.product_slug)
        tasks.append(fetch_product_summary(product.base_url, tenant_id))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    aggregate = {
        "tenant_id": tenant_id,
        "products": [],
        "totals": {"mrr": 0, "active_users": 0, "alerts": 0},
        "fetched_at": datetime.utcnow().isoformat(),
    }

    for inst, result in zip(installations, results):
        if isinstance(result, Exception):
            aggregate["products"].append({
                "slug": inst.product_slug,
                "status": "unavailable",
                "error": str(result),
            })
            continue

        aggregate["products"].append({
            "slug": inst.product_slug,
            "status": "ok",
            "metrics": result.get("metrics", {}),
            "alerts": result.get("alerts", []),
            "highlights": result.get("highlights", []),
        })
        aggregate["totals"]["mrr"] += result.get("mrr", 0)
        aggregate["totals"]["active_users"] += result.get("active_users", 0)
        aggregate["totals"]["alerts"] += len(result.get("alerts", []))

    return aggregate
```

### 9.3 Cache

```python
@cache.memoize(timeout=60)  # Redis cache 60s
async def fetch_product_summary(base_url: str, tenant_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{base_url}/api/v1/dashboard/summary",
            headers={"X-Tenant-ID": tenant_id, "X-Service-Token": SERVICE_TOKEN},
            timeout=2.0,
        )
        r.raise_for_status()
        return r.json()
```

### 9.4 Frontend

Cards por produto com metricas resumidas, alertas em destaque, e botao "Abrir [Produto]" que faz lazy load do modulo do produto sem perder contexto.

---

## 10. Healthcheck Consolidado

### 10.1 Endpoint Individual de Cada Produto

```python
# {produto}/main.py
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "scheduling-backend",
        "version": settings.VERSION,
        "checks": {
            "database": check_db(),
            "redis": check_redis(),
            "qdrant": check_qdrant(),
            "portal_api": await check_portal_reachable(),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
```

### 10.2 Endpoint Agregador no Portal

```
GET /api/portal/health/all
```

Implementacao: paralelo, timeout 2s por produto, agregacao com status global.

```python
async def aggregate_health() -> dict:
    products = product_registry.list_active()
    tasks = [check_product_health(p) for p in products]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    statuses = []
    for product, result in zip(products, results):
        if isinstance(result, Exception):
            statuses.append({"product": product.slug, "status": "down", "error": str(result)})
        else:
            statuses.append({"product": product.slug, **result})

    overall = compute_overall_status(statuses)
    return {"overall": overall, "products": statuses, "ts": datetime.utcnow().isoformat()}


def compute_overall_status(statuses: list[dict]) -> str:
    if any(s["status"] == "down" for s in statuses):
        return "red"
    if any(s["status"] == "degraded" for s in statuses):
        return "yellow"
    return "green"
```

### 10.3 Page Admin

`/platform/health` mostra:
- Status global atual (cor + texto)
- Cards por produto com checks individuais
- Grafico das ultimas 24h (snapshots a cada 1 minuto, persistidos em Postgres)
- Botao "Forcar refresh"

### 10.4 Alertas

- Webhook Slack/PagerDuty quando status muda para `red`
- Email para super_admin
- Integracao opcional com Prometheus Alertmanager

---

## 11. Frontend Strategy (SPA Monolitico Modular)

### 11.1 Decisao

**SPA monolitico** com **lazy-loaded modules** por produto. Microfrontends ficam como evolucao futura quando equipe crescer (>6 devs) e produtos ganharem releases verdadeiramente independentes.

Justificativa (ADR-004):
- Equipe atual e pequena (1-3 devs)
- Backend ainda nao esta totalmente separado (migracao gradual)
- Microfrontends introduzem complexidade (orquestracao, FOUC, state cross-MFE)
- Lazy loading + code splitting via Vite ja entrega ganhos similares sem o overhead

### 11.2 Estrutura de Pastas

```
portal-frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx                       # router raiz
│   ├── shared/                       # cross-product
│   │   ├── components/               # Header, Sidebar, ProductSwitcher
│   │   ├── contexts/                 # AuthContext, ThemeContext, TenantContext
│   │   ├── hooks/
│   │   ├── lib/                      # httpClient, jwt utils, error handling
│   │   ├── services/                 # portal API clients
│   │   └── ui/                       # shadcn/ui base
│   ├── portal/                       # paginas do control plane
│   │   ├── pages/
│   │   │   ├── LandingPage.tsx
│   │   │   ├── Dashboard.tsx          # dashboard agregado
│   │   │   ├── Billing.tsx
│   │   │   ├── Users.tsx
│   │   │   ├── Companies.tsx
│   │   │   ├── ProductCatalog.tsx
│   │   │   ├── Audit.tsx
│   │   │   ├── PlatformHealth.tsx
│   │   │   └── admin/
│   │   └── ...
│   ├── products/                     # paginas dos produtos (lazy)
│   │   ├── scheduling/
│   │   │   ├── routes.tsx            # rotas filhas de /scheduling/*
│   │   │   ├── pages/
│   │   │   ├── components/
│   │   │   ├── services/
│   │   │   └── i18n/
│   │   ├── timesheet/
│   │   ├── hr/
│   │   ├── itsm/
│   │   └── chatbot/
│   └── i18n/
└── vite.config.ts
```

### 11.3 Roteamento com Lazy Load

```typescript
// App.tsx
import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

const SchedulingModule = lazy(() => import("./products/scheduling"));
const TimesheetModule = lazy(() => import("./products/timesheet"));
const HRModule = lazy(() => import("./products/hr"));
const ITSMModule = lazy(() => import("./products/itsm"));
const ChatbotModule = lazy(() => import("./products/chatbot"));

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<PortalShell />}>
        <Route index element={<Dashboard />} />
        <Route path="billing/*" element={<Billing />} />
        <Route path="users/*" element={<Users />} />
        <Route path="platform/*" element={<PlatformAdmin />} />

        <Route
          path="scheduling/*"
          element={
            <ProductGuard product="scheduling">
              <Suspense fallback={<ProductLoader />}>
                <SchedulingModule />
              </Suspense>
            </ProductGuard>
          }
        />
        {/* idem para os demais produtos */}
      </Route>
    </Routes>
  );
}
```

### 11.4 ProductGuard

```typescript
function ProductGuard({ product, children }: { product: string; children: ReactNode }) {
  const { jwt } = useAuth();
  if (!jwt.products.includes(product)) {
    return <ProductNotActivated product={product} />;
  }
  return <>{children}</>;
}
```

### 11.5 Code Splitting Natural

Vite gera 1 chunk por modulo lazy. Bundle inicial contem apenas:
- Portal shell (auth, dashboard, billing, users)
- Shared lib (`agn-ui`)
- React + dependencias core

Cada produto e baixado sob demanda na primeira navegacao para `/scheduling/*`, etc. Cache no service worker.

### 11.6 Compartilhamento de State

- AuthContext, TenantContext, ThemeContext sao globais (em `shared/`)
- Cada produto pode ter contexts proprios (ex.: `ClinicContext` em `products/scheduling/contexts/`)
- Comunicacao entre produtos via React Router state, query params, ou eventos no Portal

---

## 12. Integracao entre Produtos (quando necessario)

### 12.1 Quando Produtos Precisam Conversar

Cenarios reais:
- ITSM cria ticket que requer agendamento → chama Scheduling para criar appointment
- HR contrata candidato → Scheduling cria treinamento de onboarding
- Timesheet aprova horas → ITSM fecha ticket relacionado
- Chatbot WhatsApp dispara workflow no Scheduling

### 12.2 Mecanismos

| Mecanismo | Uso | Exemplo |
|-----------|-----|---------|
| **REST sincrono (com JWT do tenant + service token)** | Quando precisa de resposta imediata | `POST scheduling/api/v1/appointments` chamado pelo ITSM |
| **Eventos assincronos (Redis Streams)** | Quando produto B precisa reagir a evento de A mas A nao espera resposta | `ticket.resolved` no ITSM → Timesheet agrega horas |
| **Webhooks do tenant** | Quando integracao e cross-tenant ou externa | Tenant configura webhook que dispara em `tenant.user.created` |
| **Acesso direto ao DB** | **PROIBIDO** | Bloqueado por network policy |

### 12.3 Service Tokens

Para chamadas servico-a-servico sem usuario:

```python
# scheduling chama itsm
async def link_appointment_to_ticket(appointment_id, ticket_id, tenant_id):
    service_jwt = generate_service_token(
        issuer="scheduling",
        audience="itsm",
        tenant_id=tenant_id,
        scope=["tickets:write"],
        ttl=60,  # 1 min
    )
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{ITSM_BASE_URL}/api/v1/tickets/{ticket_id}/link",
            headers={"Authorization": f"Bearer {service_jwt}"},
            json={"appointment_id": appointment_id},
        )
```

Service tokens sao JWTs RS256 assinados pela mesma chave do Portal (ou chave de servico dedicada), com claims `iss`, `aud`, `scope`, `tenant_id`, TTL curto.

### 12.4 Redis Streams

```python
# scheduling publica
await redis.xadd(
    "scheduling.events",
    {
        "type": "appointment.created",
        "tenant_id": tenant_id,
        "appointment_id": appt.id,
        "trace_id": trace_id,
    },
)

# itsm consome (consumer group)
async def consume_scheduling_events():
    while True:
        messages = await redis.xreadgroup(
            "itsm-consumers", "itsm-1", {"scheduling.events": ">"}, count=10, block=5000,
        )
        for _, msgs in messages:
            for msg_id, data in msgs:
                await process_event(data)
                await redis.xack("scheduling.events", "itsm-consumers", msg_id)
```

Garantias: at-least-once, idempotencia obrigatoria no consumidor.

---

## 13. Database-per-Product

### 13.1 Decisao (ADR-002)

- **Default:** cada produto tem sua propria **database logica** no mesmo cluster Postgres
- **Enterprise tenants:** opcao de migrar para **cluster dedicado** (silo total)
- **Schema isolation:** schemas Postgres separados para cada produto, mesmo dentro da mesma database (futuro fallback se quiser reduzir custo)

### 13.2 Implementacao

```yaml
# deployment-portal/docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_MULTIPLE_DATABASES: portal_db,scheduling_db,timesheet_db,hr_db,itsm_db,chatbot_db
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init-multiple-dbs.sh:/docker-entrypoint-initdb.d/init.sh
```

```bash
# init-multiple-dbs.sh
#!/bin/bash
for db in $(echo $POSTGRES_MULTIPLE_DATABASES | tr ',' ' '); do
    psql -U postgres <<-EOSQL
        CREATE DATABASE $db;
        GRANT ALL PRIVILEGES ON DATABASE $db TO postgres;
EOSQL
done
```

Cada produto recebe sua URL via env:
```
DATABASE_URL=postgresql://postgres:secret@postgres:5432/scheduling_db
```

### 13.3 Vantagens

- Migrations alembic isoladas por produto (sem conflito de revisoes)
- Pode dropar/recriar BD de um produto sem afetar outros
- Backup/restore granular
- Schema evolution livre por produto
- Pode mover produto para cluster dedicado mudando apenas a env var
- Esquemas com mesmos nomes (ex.: `tenants`) nao colidem porque sao databases diferentes

### 13.4 Cross-Database Queries (Quando Necessario)

**Resposta:** nao fazer. Cada produto e responsavel pelo seu dado. Para juntar dados, o Portal faz fan-out via API.

Exemplo: dashboard agregado nao faz `JOIN itsm.tickets x scheduling.appointments`. Em vez disso, o Portal chama `itsm/dashboard/summary` e `scheduling/dashboard/summary`, agrega no Python e retorna ao frontend.

### 13.5 Tabelas Comuns

Apenas a tabela `tenants` e duplicada (porque cada produto precisa do seu local). A duplicacao e mantida via:
- Provisioning sincrono (criacao)
- Eventos `tenant.updated` (mudancas de nome, status)
- Tabelas de cada produto referenciam `tenant_id` por valor (sem FK fisica para tabela do Portal)

---

## 14. Shared Libraries (`agn-*`)

Reaproveita inteiramente a §17 dos planos HR Recruitment e ITSM. Os pacotes sao **pre-requisito** para a extracao do Portal.

| Pacote | Conteudo | Quem consome |
|--------|----------|--------------|
| **agn-core** | UUIDMixin, TimestampMixin, TenantMixin, Tenant/User/Company models, database config, BaseSettings | Portal + todos os produtos |
| **agn-auth** | JWT (RS256), JWKS validator, password hash, brute force, rate limit presets, encryption Fernet, dependencies (`get_current_user`, `require_role`, `get_current_tenant_id`) | Portal + todos os produtos |
| **agn-billing** | Plan, Subscription, Invoice models + Stripe client + webhook handlers + usage tracking. **No Portal:** modo servidor. **Nos produtos:** modo cliente (consulta Portal via API) | Portal (servidor) + produtos (cliente) |
| **agn-middleware** | SubscriptionMiddleware, TraceMiddleware, CircuitBreaker, CORS helpers | Portal + todos os produtos |
| **agn-audit** | AuditLog model + service + structlog config + audit event publisher | Portal (servidor) + produtos (publisher) |
| **agn-platform** | InviteCode, PlatformSettings, PlatformWaitlist + servicos | Portal apenas |
| **agn-onboarding** | TenantSetupStatus + base service + provisioning HMAC helpers | Portal + produtos (provisioning hook) |
| **agn-ui** (TS) | AuthContext, ThemeContext, CompanyContext, ProductSwitcher, ProtectedRoute, httpClient (Axios + interceptors + refresh JWKS), shadcn/ui base, toast helpers | Portal Frontend + frontends de produtos (se microfrontends no futuro) |
| **agn-deploy** | Nginx config templates, Dockerfile templates, entrypoints, docker-compose base, Terraform modules | Portal + todos os produtos |

### 14.1 Distribuicao

- **MVP:** Monorepo com `pip install -e ../shared` e `npm link`
- **Curto prazo:** Git submodules em cada repo
- **Longo prazo:** Pip privado / npm privado (registry)

### 14.2 Versionamento

Semver. Breaking changes em major. Cada produto fixa a versao no seu `requirements.txt` / `package.json` e atualiza quando convem.

---

## 15. Observabilidade Cross-Product

### 15.1 Trace ID End-to-End

```
Cliente → Nginx (gera X-Trace-ID se ausente) → Portal → Produto A → Produto B
                                                       │
                                                       └──> Stripe (X-Trace-ID metadata)
```

Todo log estruturado inclui `trace_id`. Permite rastrear uma operacao end-to-end mesmo cruzando servicos.

### 15.2 Structured Logging

```python
# agn-audit.logger
import structlog

logger = structlog.get_logger()

logger.info(
    "ticket_created",
    tenant_id=tenant_id,
    user_id=user_id,
    product="itsm",
    ticket_id=ticket.id,
    trace_id=trace_id,
)
```

Saida JSON, ingerida por Loki/ELK/Datadog/CloudWatch.

### 15.3 Metricas Prometheus

Cada produto expoe `/metrics`. Portal coleta via Prometheus (push gateway opcional para jobs).

Metricas-chave:
- `{produto}_http_requests_total{method, path, status, tenant_id}`
- `{produto}_http_request_duration_seconds_bucket{path}`
- `{produto}_business_metric_*` (ex.: `scheduling_appointments_created_total`)
- `{produto}_db_query_duration_seconds`
- `portal_health_check_seconds{product, check}`

### 15.4 Audit Centralizado

Cada produto chama `audit_log_publisher.emit(action, ...)` que enfileira em Redis Streams. Worker do Portal consome e persiste em `audit_logs`.

### 15.5 Sentry / Erro Tracking

Cada servico envia exceptions para Sentry com tags `service`, `tenant_id`, `trace_id`. Sentry agrupa por servico e permite drill down.

---

## 16. Seguranca Cross-Product

### 16.1 Network

- Apenas Nginx Gateway exposto a internet
- Produtos apenas em rede interna (Docker network ou VPC privada)
- Network policy bloqueia acesso direto a portas dos produtos
- mTLS opcional entre servicos (evolucao futura)

### 16.2 Secrets

- Local: `.env` files (gitignored)
- Producao: GCP Secret Manager / HashiCorp Vault
- Rotacao automatica para chaves de DB
- Chaves RS256 do Portal: rotacao manual com overlap de 7 dias (§6.4)

### 16.3 Rate Limiting

- Borda: Cloudflare global
- Gateway: Nginx por rota e por IP
- Aplicacao: SlowAPI por endpoint e por API key (no API Gateway dos produtos)
- Fail-closed: erro de redis no rate limiter retorna 503

### 16.4 RBAC Cross-Product

- Roles **base** definidas no Portal (super_admin, platform_admin, tenant_admin)
- Roles **por produto** definidas pelo proprio produto e armazenadas no JWT (`roles.scheduling = "admin"`)
- Cada produto valida suas proprias roles localmente (sem chamar Portal)

### 16.5 LGPD

- Right to delete: Portal coordena, cada produto deleta seus dados via `POST /api/v1/lgpd/delete-tenant`
- Right to export: Portal coordena, cada produto exporta seus dados via `POST /api/v1/lgpd/export-tenant`
- Audit log de tudo
- Encryption em repouso (Postgres TDE ou disk encryption)

### 16.6 Isolamento Cross-Tenant

Substituicao de RLS por enforcement em service layer + isolation tests obrigatorios (mesma decisao dos planos HR e ITSM, ADR-010 daqueles documentos).

---

## 17. Repositorios e Layout

### 17.1 Multi-Repo (ADR-005 reaproveitada)

```
ai-garage/
├── agn-shared/                 # repo: shared libs (Python + TS + deploy templates)
│   ├── python/
│   │   ├── agn-core/
│   │   ├── agn-auth/
│   │   ├── agn-billing/
│   │   ├── agn-middleware/
│   │   ├── agn-audit/
│   │   ├── agn-platform/
│   │   └── agn-onboarding/
│   ├── typescript/
│   │   └── agn-ui/
│   └── deploy/
│       └── agn-deploy/
│
├── agn-portal/                 # repo: control plane
│   ├── backend/
│   ├── frontend/               # SPA monolitico modular (todos os produtos)
│   ├── deployment/
│   ├── terraform/
│   ├── tests/
│   └── docs/
│
├── scheduling-app/             # repo: produto scheduling
│   ├── backend/
│   ├── deployment/
│   ├── tests/
│   ├── shared/                 # submodule -> agn-shared
│   └── docs/
│
├── timesheet-app/              # repo: produto timesheet
│
├── hr-recruitment/             # repo: produto HR (ja em planejamento)
│
├── itsm-app/                   # repo: produto ITSM (ja em planejamento)
│
└── chatbot-app/                # repo: produto chatbot generico
```

### 17.2 Frontend: Único ou Multi?

**Decisao:** o frontend SPA vive **dentro do agn-portal**. Os produtos NAO tem frontend proprio (apenas backend).

Justificativa:
- Coesao de UX
- 1 deploy de frontend
- Lazy loading entrega o ganho de modularidade
- Quando equipe crescer, podemos extrair products/* para repos proprios e usar Module Federation

### 17.3 Shared Libs como Submodule

Cada repo de produto tem `shared/` como submodule apontando para `agn-shared`. Updates propagados via:
```bash
cd shared && git pull origin main && cd .. && git add shared && git commit -m "bump shared libs"
```

---

## 18. Plano de Migracao (do agent-hub atual)

### 18.1 Visao Geral

```
Estado atual:                    Estado-alvo:
                                 
agent-hub (monolito)             agn-portal (control plane) + N produtos
   │                             ─ scheduling-app
   ├─ auth                       ─ timesheet-app
   ├─ billing                    ─ hr-recruitment
   ├─ tenants                    ─ itsm-app
   ├─ scheduling/                ─ chatbot-app
   ├─ timesheet/                 + agn-shared (libs)
   ├─ hr_recruiter_agent/
   ├─ chat (chatbot)
   └─ ...
```

### 18.2 Fases

#### **Fase 0 — Preparacao: Extrair Shared Libs (2-3 semanas)**

Objetivo: criar `agn-shared/` com os 7 pacotes Python + 1 TS + 1 deploy, instalados localmente via `pip install -e` no agent-hub atual. Sem mudancas funcionais.

Tarefas:
- [ ] Criar repo `agn-shared`
- [ ] Mover [backend/models/base.py](../../../backend/models/base.py) → `agn-core/models/base.py`
- [ ] Mover [backend/core/security.py](../../../backend/core/security.py) → `agn-auth/security.py`
- [ ] Mover [backend/services/auth_service.py](../../../backend/services/auth_service.py) → `agn-auth/services/auth_service.py`
- [ ] Mover [backend/services/stripe_service.py](../../../backend/services/stripe_service.py) → `agn-billing/services/stripe_service.py`
- [ ] Mover [backend/services/tenant_onboarding_service.py](../../../backend/services/tenant_onboarding_service.py) → `agn-onboarding/services/base.py`
- [ ] Mover [backend/services/audit_log_service.py](../../../backend/services/audit_log_service.py) → `agn-audit/services/audit_log_service.py`
- [ ] Mover middlewares ([backend/core/subscription_middleware.py](../../../backend/core/subscription_middleware.py), trace, circuit breaker) → `agn-middleware/`
- [ ] Empacotar como `pip install -e ../agn-shared/python/agn-core` (etc.)
- [ ] Atualizar imports do agent-hub atual para usar os novos paths
- [ ] CI: lint, typecheck, testes do agent-hub continuam passando

**Saida:** agent-hub continua funcionando 100% com codigo importado dos pacotes shared.

---

#### **Fase 1 — Criar agn-portal e Mover Codigo Cross-Product (3-4 semanas)**

Objetivo: criar repo `agn-portal/` rodando lado a lado com o agent-hub legacy. Portal contem auth, billing, tenant, company, user, audit, themes, invite codes, platform admin. **Nao mexe** ainda nos produtos (scheduling, timesheet, etc. continuam no agent-hub).

Tarefas:
- [ ] Criar repo `agn-portal` com estrutura padrao (backend, frontend, deployment, tests)
- [ ] Copiar models cross-product do agent-hub: tenant, user, company, billing, audit_log, invite_code, platform_*, theme, language
- [ ] Copiar services correspondentes
- [ ] Copiar APIs: `auth.py`, `apis/v1/{tenants, companies, users, billing, audit_logs, invite_codes, themes, languages, backups, platform_admin}.py`
- [ ] **Trocar JWT HS256 → RS256** com JWKS endpoint
- [ ] Setup database `portal_db` (PostgreSQL)
- [ ] Migrations alembic isoladas
- [ ] Onboarding service estendido com `ProductInstallation` table
- [ ] Stripe webhook unico no Portal
- [ ] CI/CD proprio para `agn-portal`
- [ ] Deploy em ambiente staging com domain `portal-staging.ai-garage.com.br`

**Saida:** Portal funcional rodando standalone em staging. agent-hub legacy continua intocado em producao.

---

#### **Fase 2 — API Gateway na Frente + Dual-Mode Auth (1-2 semanas)**

Objetivo: por o Portal entre o cliente e o agent-hub. Cliente passa a usar URLs `/api/portal/*` para Portal e `/api/legacy/*` para tudo que ainda nao foi migrado. JWT compartilhado funciona via dual-mode (HS256 legacy + RS256 novo).

Tarefas:
- [ ] Configurar Nginx Gateway com routing por prefix
- [ ] Portal aceita ambos os tokens (dual-mode validator)
- [ ] agent-hub legacy aceita ambos tambem (importa validator do `agn-auth`)
- [ ] Frontend agent-hub atualizado para chamar `/api/portal/*` para auth/billing/users
- [ ] Smoke tests end-to-end
- [ ] Cutover em producao com janela de manutencao curta (rollback plan)

**Saida:** cliente acessa Portal sem perceber a divisao. Auth funcionando com ambos os tokens.

---

#### **Fase 3 — Extrair timesheet-app [PILOTO DE EXTRACAO] (3-4 semanas)**

Objetivo: primeira extracao do monolito. Timesheet e o modulo mais simples e com menos acoplamentos cross-product, servindo como prova de conceito do processo de extracao antes dos modulos mais complexos. Nao esta sendo avaliado por clientes ativos, minimizando risco.

Tarefas:
- [ ] Criar repo `timesheet-app/` com estrutura padrao
- [ ] Copiar `services/timesheet/`, `models/timesheet/`, `apis/v1/timesheet*.py`
- [ ] Migrations alembic isoladas (renumerar a partir de 001)
- [ ] Database `timesheet_db` criada
- [ ] Implementar provisioning hook `POST /api/v1/integrations/portal/provision`
- [ ] Implementar `GET /api/v1/dashboard/summary`
- [ ] Implementar `GET /health`
- [ ] **Migrar dados:** script Python que le do agent-hub e escreve no `timesheet_db`
- [ ] Dual-write durante 1-2 semanas (escreve em ambos para validar)
- [ ] Switch routing: `/api/v1/timesheet/*` agora aponta para `timesheet-app:8002`
- [ ] Remover codigo de timesheet do agent-hub
- [ ] Deploy producao
- [ ] **Retrospectiva:** documentar licoes aprendidas para aplicar nas Fases seguintes

**Saida:** timesheet rodando standalone. Processo de extracao validado end-to-end.

---

#### **Fase 4 — Migrar hr-recruitment para padrao novo (4-5 semanas)**

Objetivo: apos finalizar os ajustes pendentes na aplicacao HR atual, migrar para o padrao novo com repositorio e DB independentes. HR ja nasce parcialmente no padrao novo conforme [ARCHITECTURE_HR_RECRUITMENT.md](ARCHITECTURE_HR_RECRUITMENT.md), aproveitando o processo validado pelo Timesheet.

Pre-requisito: ajustes na app HR atual finalizados e estaveis.

Tarefas:
- [ ] Criar repo `hr-recruitment/` com estrutura padrao (ou reaproveitar se ja existir)
- [ ] Migrar codigo do agent-hub para repo proprio
- [ ] Database `hr_db` criada
- [ ] Implementar contrato comum (provisioning, dashboard/summary, health)
- [ ] Integracao com Portal via JWKS + Redis Streams
- [ ] Migrar dados (se houver dados em producao)
- [ ] Dual-write + switch routing
- [ ] Deploy producao

**Saida:** HR Recruitment rodando standalone no padrao novo.

---

#### **Fase 5 — Migrar itsm-app para padrao novo (4-5 semanas)**

Objetivo: apos finalizar os ajustes pendentes na aplicacao ITSM atual, migrar para o padrao novo. Segue o mesmo processo validado nas Fases 3 e 4, conforme [ARCHITECTURE_ITSM.md](ARCHITECTURE_ITSM.md).

Pre-requisito: ajustes na app ITSM atual finalizados e estaveis.

Tarefas:
- [ ] Criar repo `itsm-app/` com estrutura padrao (ou reaproveitar se ja existir)
- [ ] Migrar codigo do agent-hub para repo proprio
- [ ] Database `itsm_db` criada
- [ ] Implementar contrato comum (provisioning, dashboard/summary, health)
- [ ] Integracao com Portal via JWKS + Redis Streams
- [ ] Migrar dados (se houver dados em producao)
- [ ] Dual-write + switch routing
- [ ] Deploy producao

**Saida:** ITSM rodando standalone no padrao novo.

---

#### **Fase 6 — Extrair scheduling-app (4-5 semanas)**

Objetivo: criar `scheduling-app/` standalone com sua propria DB. Scheduling e mais complexo que timesheet por ter dependencias no chatbot (dispatcher, WhatsApp, voice), mas neste ponto a equipe ja domina o processo de extracao.

Tarefas:
- [ ] Criar repo `scheduling-app/` com estrutura padrao
- [ ] Copiar [backend/services/scheduling/](../../../backend/services/scheduling/) → `scheduling-app/backend/services/`
- [ ] Copiar [backend/services/scheduling_agent/](../../../backend/services/scheduling_agent/) → `scheduling-app/backend/services/agent/`
- [ ] Copiar [backend/models/scheduling/](../../../backend/models/scheduling/) → `scheduling-app/backend/models/`
- [ ] Copiar [backend/apis/v1/scheduling.py](../../../backend/apis/v1/scheduling.py) → `scheduling-app/backend/apis/v1/scheduling.py`
- [ ] Migrations alembic isoladas (renumerar a partir de 001)
- [ ] Database `scheduling_db` criada
- [ ] Implementar provisioning hook `POST /api/v1/integrations/portal/provision`
- [ ] Implementar `GET /api/v1/dashboard/summary`
- [ ] Implementar `GET /health`
- [ ] Resolver acoplamentos cross-product:
  - FK `Appointment → Agente`: substituir por `agente_id` (string, sem FK fisica)
  - Dispatcher de chat: ficar no chatbot-app, chamar scheduling via REST
- [ ] **Migrar dados:** script Python que le do agent-hub e escreve no `scheduling_db`
- [ ] Dual-write durante 1-2 semanas (escreve em ambos para validar)
- [ ] Switch routing: `/api/v1/scheduling/*` agora aponta para `scheduling-app:8001`
- [ ] Remover codigo de scheduling do agent-hub
- [ ] Deploy producao

**Saida:** scheduling rodando standalone. Frontend ainda no Portal (paginas em `products/scheduling/`).

---

#### **Fase 7 — Extrair chatbot-app (6-8 semanas)**

Esse e o coracao do agent-hub legacy. E a extracao mais complexa porque envolve:
- Chat service generico
- RAG (Qdrant, knowledge pipeline)
- Voice (S2S, providers)
- WhatsApp/Twilio integration
- Conversations / messages
- Topics / documents
- Agent registry e FSM dispatcher
- WebSocket realtime

Tarefas adicionais:
- [ ] Definir contratos de integracao entre chatbot-app e demais produtos (ex.: scheduling consome chatbot para conversar com paciente)
- [ ] Migrar embeddings/Qdrant collections
- [ ] Migrar audio files / uploads
- [ ] Twilio webhooks reconfigurados para apontar para chatbot-app

**Saida:** agent-hub legacy aposentado. Apenas Portal + 5 produtos rodando.

---

#### **Fase 8 — Frontend: Refatorar SPA Modular (4-6 semanas)**

Objetivo: reorganizar o frontend do Portal para a estrutura modular `src/products/{slug}/`. Migrar paginas existentes. Pode ser iniciada em paralelo a partir da Fase 6, quando a maioria dos backends ja estara standalone.

- [frontend/src/pages/clinic/](../../../frontend/src/pages/clinic/) → `portal-frontend/src/products/scheduling/pages/`
- [frontend/src/pages/timesheet/](../../../frontend/src/pages/timesheet/) → `portal-frontend/src/products/timesheet/pages/`
- Criar `products/hr/`, `products/itsm/`, `products/chatbot/` conforme produtos amadurecem
- React Router com lazy() + Suspense
- ProductGuard
- Code splitting

---

#### **Fase 9 — Observabilidade Production-Ready (2 semanas)**

- [ ] Trace ID propagado end-to-end
- [ ] Sentry em todos os servicos
- [ ] Prometheus + Grafana dashboards
- [ ] Loki para logs centralizados
- [ ] Alertmanager → Slack/PagerDuty
- [ ] Healthcheck dashboard no Portal
- [ ] Audit log central operacional
- [ ] Runbooks por produto

---

#### **Fase 10 — Deploy Independente (2-3 semanas)**

- [ ] CI/CD proprio para cada repo
- [ ] Docker images publicadas em registry
- [ ] Terraform GCP / Cloud Run / K8s para cada produto
- [ ] Network policies
- [ ] Secret Manager
- [ ] Backup automatizado e testado (restore drill)
- [ ] Disaster recovery plan
- [ ] Production launch checklist

### 18.3 Estimativas

| Cenario | Duracao Total |
|---------|---------------|
| 1 dev full-time | ~32-42 semanas (~8-10 meses) |
| 2 devs paralelos | ~20-26 semanas (~5-6 meses) |
| 3 devs paralelos (com fases 4+5 simultaneas apos Fase 3) | ~16-20 semanas (~4-5 meses) |

> **Nota:** Fases 4 e 5 (HR e ITSM) dependem da finalizacao dos ajustes nas aplicacoes atuais. O cronograma real pode variar conforme a estabilizacao dessas apps.

### 18.4 Dependencias entre Fases

```
Fase 0 ──> Fase 1 ──> Fase 2 ──> Fase 3 (Timesheet - piloto)
                                    │
                                    ├──> Fase 4 (HR)* ──┐
                                    ├──> Fase 5 (ITSM)* ┤
                                    │                    │
                                    └──> Fase 6 (Scheduling) ──> Fase 7 (Chatbot)
                                                                    │
                                                         Fase 8 (Frontend) ──> Fase 9 ──> Fase 10

* Fases 4 e 5 dependem tambem da finalizacao dos ajustes nas apps atuais.
  Podem rodar em paralelo entre si e em paralelo com Fase 6, se equipe permitir.
```

---

## 19. Vantagens e Trade-offs (Resumo Executivo)

| Dimensao | Antes (monolito agent-hub) | Depois (Portal + produtos) |
|----------|---------------------------|----------------------------|
| **Performance** | 1 processo Python; GIL afeta tudo; gargalo unico | Produtos escalam independentes; gargalo isolado a 1 produto; Python GIL nao cruza servicos |
| **Manutencao** | Mudanca em scheduling pode quebrar timesheet; deploy unico precisa testar tudo | Mudanca em scheduling nao afeta timesheet; CI/CD por produto; releases independentes |
| **Escalabilidade** | Vertical (mais CPU/RAM no container unico) | Horizontal por produto (scheduling pode ter 10 replicas, timesheet 2) |
| **Blast radius** | Erro fatal derruba **tudo** (todos tenants, todos produtos) | Erro derruba apenas 1 produto; outros continuam servindo |
| **Isolamento de dados** | Mesmo schema Postgres; risco de leak cross-tenant via bug de filter | Database-per-product elimina vazamento entre produtos |
| **Time-to-market novo produto** | Lento (refazer auth, billing, onboarding do zero) | Rapido (shared libs + provisioning hook + foco no dominio) |
| **Cross-sell** | Manual / tematica | Natural (catalogo no Portal, ativar com 1 clique) |
| **Compliance/audit** | Audit fragmentado | Audit central com origem por produto |
| **Custo de infra** | Baixo (1 container, 1 DB) | Medio (N containers, mas pode compartilhar 1 cluster Postgres com databases separadas) |
| **Onboarding de devs** | Curva alta (precisa entender tudo) | Curva baixa por produto (devs especializam) |
| **Recuperacao de desastre** | Restore monolitico (tudo ou nada) | Restore granular (1 produto por vez) |
| **Posicionamento comercial** | "Plataforma de chatbot com features extras" | "Plataforma de produtos SaaS para automacao empresarial" |
| **Flexibilidade de pricing** | Plan unico cobre tudo | Pricing por produto + bundles + usage-based |
| **Compliance enterprise (LGPD, ISO)** | Dificil (escopo amplo) | Mais facil (auditoria por produto, isolamento real) |

---

## 20. ADRs

### ADR-001: Bridge Isolation Model (Pool + Silo Logico)
- **Decisao:** Portal em pool, produtos em silo logico via DB-per-product.
- **Razao:** Pool puro nao protege blast radius; silo puro e caro demais. Bridge combina eficiencia com isolamento.
- **Fonte:** [AWS SaaS Lens — Silo, Pool, and Bridge Models](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html)

### ADR-002: Database-per-Product
- **Decisao:** Cada produto tem sua propria database (logica no inicio, fisica para enterprise).
- **Razao:** Migrations isoladas, schemas livres, blast radius minimo, backup granular.
- **Trade-off aceito:** Custo maior (mitigado por compartilhar cluster no inicio).
- **Fonte:** [AWS SaaS Storage Strategies](https://docs.aws.amazon.com/whitepapers/latest/multi-tenant-saas-storage-strategies/saas-partitioning-models.html)

### ADR-003: Control Plane / Application Plane Separation
- **Decisao:** Portal e o control plane (gerencia multi-tenancy); produtos sao application planes (entregam valor multi-tenant).
- **Razao:** Padrao canonico AWS/Azure 2025. Limites naturais entre administracao e operacao. Seguranca e compliance reforcados.
- **Fonte:** [AWS — Control plane vs application plane](https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/control-plane-vs.-application-plane.html)

### ADR-004: SPA Monolitico com Lazy Modules (NAO Microfrontends)
- **Decisao:** Frontend unico no Portal com modules lazy-loaded por produto. Microfrontends ficam para evolucao futura.
- **Razao:** Equipe atual pequena (1-3 devs); microfrontends agregam complexidade desnecessaria sem ganho real. Lazy loading entrega ja a maioria dos beneficios.
- **Trade-off aceito:** Escalar equipe para >6 devs no mesmo SPA pode dar friccao; quando isso acontecer, migrar para Module Federation.
- **Fonte:** [Bitovi — Should Your Team Be Using Micro Frontends?](https://www.bitovi.com/blog/should-your-team-be-using-micro-frontends-and-module-federation), [Feature-Sliced Design — Micro-Frontends in 2025](https://feature-sliced.design/blog/micro-frontend-architecture)

### ADR-005: Multi-Repo (Portal + 1 repo por produto)
- **Decisao:** Cada produto em repositorio separado, shared libs como Git submodule.
- **Razao:** Reaproveita ADR dos planos HR e ITSM. Releases independentes, equipes potencialmente diferentes, ciclos distintos.

### ADR-006: JWT RS256 + JWKS (NAO HS256 compartilhado)
- **Decisao:** Portal emite JWT assinado com chave assimetrica RS256. Expoe `/.well-known/jwks.json`. Produtos validam localmente.
- **Razao:**
  - HS256 exige distribuir o segredo por todos os servicos (vazamento em qualquer um compromete todos)
  - RS256 + JWKS permite rotacao sem redeploy
  - Padrao Auth0/Okta/Cognito
- **Migration path:** Dual-mode validation por 2 semanas durante a Fase 1-2.
- **Fonte:** [microservices.io — Authentication with JWT](https://microservices.io/post/architecture/2025/05/28/microservices-authn-authz-part-2-authentication.html), [Securing Microservices with Asymmetric JWTs](https://medium.com/swlh/securing-microservices-with-assymetric-jwts-88aebb7114fd)

### ADR-007: Stripe Single Subscription com Multi-Line Items
- **Decisao:** 1 customer + 1 subscription por tenant, com multiplos `subscription.items[]` (1 por produto).
- **Razao:** Fatura unica, prorating automatico, cross-sell natural, mixed interval support.
- **Trade-off:** Quando ciclos divergem, Stripe gera faturas separadas (aceitavel).
- **Fonte:** [Stripe — Multiple products](https://docs.stripe.com/billing/subscriptions/multiple-products), [Stripe — Mixed interval subscriptions](https://docs.stripe.com/billing/subscriptions/mixed-interval), [Stripe — SaaS billing best practices](https://stripe.com/resources/more/best-practices-for-saas-billing)

### ADR-008: Async Events via Redis Streams (NAO Kafka)
- **Decisao:** Comunicacao assincrona cross-product via Redis Streams.
- **Razao:** Redis ja esta em uso; volume atual nao justifica overhead operacional do Kafka; Redis Streams suporta consumer groups, at-least-once, replay.
- **Evolucao:** Migrar para Kafka quando volume passar de ~1M eventos/dia ou multi-region.

### ADR-009: Migracao Gradual com API Gateway na Frente (NAO Big-Bang)
- **Decisao:** Portal e produtos extraidos um por vez, com Nginx routing por prefix. Dual-mode auth garante zero downtime.
- **Razao:** Big-bang e arriscado e bloqueia features. Gradual permite validacao continua e rollback granular.

### ADR-010: Portal NAO Acessa BD dos Produtos Diretamente
- **Decisao:** Toda comunicacao Portal ↔ Produto e via REST + JWT (ou eventos). Acesso direto a outro DB e proibido por design.
- **Razao:** Garantir baixo acoplamento, schemas livres por produto, permite mover produto para cluster dedicado sem refatoracao.
- **Enforcement:** Code review + network policy + nenhum produto recebe credenciais de outro DB.

### ADR-011 (FUTURO): Cell-Based Architecture
- **Decisao:** NAO adotar agora. Reconsiderar quando atingir >100 tenants ou tiver requisitos enterprise/compliance.
- **Razao:** Cell-based exige refatorar onboarding, routing e tooling. Overhead so se justifica em escala alta.
- **Fonte:** [AWS re:Invent 2024 — SaaS meets cell-based architecture](https://danguisinger.com/solutions/cellular-architecture/), [DZone — Cell-Based Architecture Guide](https://dzone.com/articles/grokking-cell-based-architecture)

---

## 21. Riscos e Mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| Migracao paralela cria duplicacao de codigo | Alta | Medio | Shared libs primeiro (Fase 0); feature flags |
| Quebra de auth durante mudanca HS256 → RS256 | Media | Alto | Dual-mode validation por 2 semanas; rollback documentado |
| Dados de scheduling/timesheet com FKs cross-domain | Alta | Medio | Introduzir IDs logicos sem FK fisica antes da extracao |
| Custo de N clusters Postgres | Media | Baixo | Comecar todos no mesmo cluster com databases separadas |
| Complexidade operacional cresce | Alta | Medio | Observabilidade desde Fase 1; runbooks por produto; healthcheck consolidado |
| Team velocity cai durante migracao | Alta | Alto | Manter releases do agent-hub durante a migracao; nao bloquear features novas; trabalhar em paralelo |
| Migracao de dados com perda | Baixa | Critico | Dual-write por 1-2 semanas em cada extracao; checksums; backup pre-migracao; rollback plan |
| Cliente percebe inconsistencia entre dashboards | Media | Medio | Dashboard agregado com fan-out + cache + indicador "atualizado ha X segundos" |
| JWKS endpoint cai e produtos nao validam tokens | Baixa | Alto | Cache local de 24h em cada produto; failover via secondary Portal replica |
| Acoplamento implicito via Agente.type_config | Alta | Medio | TypedDict por produto; validacao estrita; testes |

---

## 22. Decisoes Resolvidas vs v1.0

| Decisao em aberto v1 | Resolucao v2 | Secao/ADR |
|---------------------|--------------|-----------|
| Frontend: SPA unico vs microfrontends? | **SPA unico com lazy modules**; microfrontends como evolucao futura | §11, ADR-004 |
| Database: schema separado vs instancias separadas? | **Database logica separada no mesmo cluster** (start); cluster dedicado para enterprise | §13, ADR-002 |
| Portal: repo separado vs monorepo? | **Repo separado** + shared libs como Git submodule | §17, ADR-005 |
| Stripe: multi-product subscription vs subscriptions separadas? | **Single subscription com multi-line items** | §7, ADR-007 |
| Onboarding: wizard unico ou wizard por produto? | **Wizard delegado**: Portal coordena steps comuns; cada produto contribui com steps proprios via callback | §8.4 |
| Quando iniciar a extracao do Portal? | **Apos Fase 0 (shared libs)**. Timesheet como piloto de extracao (Fase 3), depois HR (Fase 4) e ITSM (Fase 5) apos finalizacao dos ajustes nas apps atuais. | §18 |
| Database: como migrar dados sem downtime? | **Dual-write por 1-2 semanas** em cada extracao + checksums + rollback plan | §18, §21 |
| JWT: HS256 compartilhado ou estrategia diferente? | **RS256 + JWKS** (mudanca critica vs v1) | §6, ADR-006 |
| Cross-product communication: REST sincrono ou eventos? | **Hibrido**: REST para resposta imediata, Redis Streams para eventos assincronos | §12, ADR-008 |
| Cell-based architecture: adotar agora? | **NAO**. Reconsiderar quando atingir >100 tenants. ADR aberto. | §5.5, ADR-011 |

---

## Apendice A: Mapeamento agent-hub → Portal + Produtos

### A.1 Backend → Portal (`agn-portal/backend/`)

| Origem (agent-hub) | Destino (agn-portal) |
|--------------------|---------------------|
| [backend/services/auth_service.py](../../../backend/services/auth_service.py) | `services/auth_service.py` (importa de `agn-auth`) |
| [backend/services/tenant_onboarding_service.py](../../../backend/services/tenant_onboarding_service.py) | `services/onboarding_service.py` (estende `agn-onboarding`) |
| [backend/services/stripe_service.py](../../../backend/services/stripe_service.py) | `services/stripe_service.py` (importa de `agn-billing`) |
| [backend/services/company_service.py](../../../backend/services/company_service.py) | `services/company_service.py` |
| [backend/services/tenant_service.py](../../../backend/services/tenant_service.py) | `services/tenant_service.py` |
| [backend/services/user_company_access_service.py](../../../backend/services/user_company_access_service.py) | `services/user_company_access_service.py` |
| [backend/services/audit_log_service.py](../../../backend/services/audit_log_service.py) | `services/audit_log_service.py` (importa de `agn-audit`) |
| [backend/services/backup_service.py](../../../backend/services/backup_service.py) | `services/backup_orchestrator.py` |
| [backend/services/invite_code_service.py](../../../backend/services/invite_code_service.py) | `services/invite_code_service.py` (importa de `agn-platform`) |
| [backend/services/platform_admin_service.py](../../../backend/services/platform_admin_service.py) | `services/platform_admin_service.py` |
| [backend/services/platform_settings_service.py](../../../backend/services/platform_settings_service.py) | `services/platform_settings_service.py` |
| [backend/services/platform_waitlist_service.py](../../../backend/services/platform_waitlist_service.py) | `services/platform_waitlist_service.py` |
| [backend/services/usage_tracking_service.py](../../../backend/services/usage_tracking_service.py) | `services/usage_tracking_service.py` |
| [backend/services/usage_aggregation_service.py](../../../backend/services/usage_aggregation_service.py) | `services/usage_aggregation_service.py` |
| [backend/services/usage_limit_service.py](../../../backend/services/usage_limit_service.py) | `services/usage_limit_service.py` |
| [backend/services/language_service.py](../../../backend/services/language_service.py) | `services/language_service.py` |
| [backend/services/translation_service.py](../../../backend/services/translation_service.py) | `services/translation_service.py` |
| [backend/services/itsm_provisioning_service.py](../../../backend/services/itsm_provisioning_service.py) | `services/provisioning_service.py` (generalizado para todos os produtos) |
| [backend/services/agent_registry.py](../../../backend/services/agent_registry.py) | `services/product_registry.py` (renomeado, generalizado) |
| [backend/services/fsm_agent_registry.py](../../../backend/services/fsm_agent_registry.py) | Portal core ou shared lib (decisao em §4.5 do plano) |
| [backend/apis/auth.py](../../../backend/apis/auth.py) | `apis/auth.py` |
| [backend/apis/v1/tenants.py](../../../backend/apis/v1/tenants.py) | `apis/v1/tenants.py` |
| [backend/apis/v1/companies.py](../../../backend/apis/v1/companies.py) | `apis/v1/companies.py` |
| [backend/apis/v1/users.py](../../../backend/apis/v1/users.py) | `apis/v1/users.py` |
| [backend/apis/v1/billing.py](../../../backend/apis/v1/billing.py) | `apis/v1/billing.py` |
| [backend/apis/v1/audit_logs.py](../../../backend/apis/v1/audit_logs.py) | `apis/v1/audit_logs.py` |
| [backend/apis/v1/invite_codes.py](../../../backend/apis/v1/invite_codes.py) | `apis/v1/invite_codes.py` |
| [backend/apis/v1/platform_admin.py](../../../backend/apis/v1/platform_admin.py) | `apis/v1/platform_admin.py` |
| [backend/apis/v1/themes.py](../../../backend/apis/v1/themes.py) | `apis/v1/themes.py` |
| [backend/apis/v1/languages.py](../../../backend/apis/v1/languages.py) | `apis/v1/languages.py` |
| [backend/apis/v1/backups.py](../../../backend/apis/v1/backups.py) | `apis/v1/backups.py` |
| [backend/apis/v1/agentes.py](../../../backend/apis/v1/agentes.py) | `apis/v1/products.py` (catalogo de produtos generalizado) |
| [backend/models/tenant.py](../../../backend/models/tenant.py) | `models/tenant.py` (importa de `agn-core`) |
| [backend/models/user.py](../../../backend/models/user.py) | `models/user.py` |
| [backend/models/company.py](../../../backend/models/company.py) | `models/company.py` |
| [backend/models/billing.py](../../../backend/models/billing.py) | `models/billing.py` (importa de `agn-billing`) |
| [backend/models/audit_log.py](../../../backend/models/audit_log.py) | `models/audit_log.py` |
| [backend/models/theme.py](../../../backend/models/theme.py) | `models/theme.py` |
| [backend/models/invite_code.py](../../../backend/models/invite_code.py) | `models/invite_code.py` |
| [backend/models/platform_settings.py](../../../backend/models/platform_settings.py) | `models/platform_settings.py` |
| [backend/models/platform_waitlist.py](../../../backend/models/platform_waitlist.py) | `models/platform_waitlist.py` |
| [backend/models/platform_admin_action.py](../../../backend/models/platform_admin_action.py) | `models/platform_admin_action.py` |
| [backend/models/agente.py](../../../backend/models/agente.py) | `models/product.py` + `models/product_installation.py` (refatorado) |
| [backend/models/agent_api_key.py](../../../backend/models/agent_api_key.py) | `models/api_key.py` |
| [backend/models/usage.py](../../../backend/models/usage.py) | `models/usage.py` |
| [backend/models/tenant_limit.py](../../../backend/models/tenant_limit.py) | `models/tenant_limit.py` |
| [backend/models/language.py](../../../backend/models/language.py) | `models/language.py` |

### A.2 Backend → scheduling-app

| Origem (agent-hub) | Destino (scheduling-app) |
|--------------------|--------------------------|
| [backend/services/scheduling/](../../../backend/services/scheduling/) | `backend/services/` (toda a pasta) |
| [backend/services/scheduling_agent/](../../../backend/services/scheduling_agent/) | `backend/services/agent/` |
| [backend/models/scheduling/](../../../backend/models/scheduling/) | `backend/models/` |
| [backend/apis/v1/scheduling.py](../../../backend/apis/v1/scheduling.py) | `backend/apis/v1/scheduling.py` |
| Migrations alembic do scheduling | `backend/migrations/versions/` (renumerar) |

### A.3 Backend → timesheet-app

| Origem (agent-hub) | Destino (timesheet-app) |
|--------------------|-------------------------|
| [backend/services/timesheet/](../../../backend/services/timesheet/) | `backend/services/` |
| [backend/models/timesheet/](../../../backend/models/timesheet/) | `backend/models/` |
| [backend/apis/v1/timesheet.py](../../../backend/apis/v1/timesheet.py) | `backend/apis/v1/timesheet.py` |
| `backend/apis/v1/timesheet_external.py` (se existir) | `backend/apis/v1/external.py` |
| Migrations timesheet | `backend/migrations/` |

### A.4 Backend → chatbot-app

| Origem (agent-hub) | Destino (chatbot-app) |
|--------------------|----------------------|
| [backend/services/chat_service.py](../../../backend/services/chat_service.py) | `backend/services/chat_service.py` |
| [backend/services/external_chat_service.py](../../../backend/services/external_chat_service.py) | `backend/services/external_chat_service.py` |
| [backend/services/embed_chat_service.py](../../../backend/services/embed_chat_service.py) | `backend/services/embed_chat_service.py` |
| [backend/services/qdrant_service.py](../../../backend/services/qdrant_service.py) | `backend/services/qdrant_service.py` |
| [backend/services/knowledge_pipeline_service.py](../../../backend/services/knowledge_pipeline_service.py) | `backend/services/knowledge_pipeline_service.py` |
| [backend/services/semantic_search_service.py](../../../backend/services/semantic_search_service.py) | `backend/services/semantic_search_service.py` |
| [backend/services/sparse_embeddings_service.py](../../../backend/services/sparse_embeddings_service.py) | `backend/services/sparse_embeddings_service.py` |
| [backend/services/voice/](../../../backend/services/voice/) | `backend/services/voice/` |
| [backend/services/whatsapp/](../../../backend/services/whatsapp/) | `backend/services/whatsapp/` |
| [backend/services/realtime_session_manager.py](../../../backend/services/realtime_session_manager.py) | `backend/services/realtime_session_manager.py` |
| [backend/db/models/](../../../backend/db/models/) (conversation, message, custom_intent, intent_phrase) | `backend/models/` |
| [backend/apis/chat.py](../../../backend/apis/chat.py) | `backend/apis/chat.py` |
| [backend/apis/v1/external_chat.py](../../../backend/apis/v1/external_chat.py) | `backend/apis/v1/external_chat.py` |
| [backend/apis/v1/embed_chat.py](../../../backend/apis/v1/embed_chat.py) | `backend/apis/v1/embed_chat.py` |
| [backend/apis/v1/whatsapp_webhook.py](../../../backend/apis/v1/whatsapp_webhook.py) | `backend/apis/v1/whatsapp_webhook.py` |
| [backend/apis/v1/whatsapp_config.py](../../../backend/apis/v1/whatsapp_config.py) | `backend/apis/v1/whatsapp_config.py` |
| [backend/apis/v1/documents.py](../../../backend/apis/v1/documents.py) | `backend/apis/v1/documents.py` |
| [backend/apis/v1/intents.py](../../../backend/apis/v1/intents.py) | `backend/apis/v1/intents.py` |
| Topics, vector_store APIs | `backend/apis/v1/topics.py`, `backend/apis/v1/vector_store.py` |
| [backend/services/hr_recruiter_agent/](../../../backend/services/hr_recruiter_agent/) | Migra para `hr-recruitment/` (ja em planejamento) |

### A.5 Frontend (todos os produtos no Portal SPA)

| Origem (agent-hub) | Destino (agn-portal/frontend) |
|--------------------|-------------------------------|
| [frontend/src/pages/](../../../frontend/src/pages/) (admin, auth, landing, etc.) | `src/portal/pages/` |
| [frontend/src/pages/clinic/](../../../frontend/src/pages/clinic/) | `src/products/scheduling/pages/` |
| [frontend/src/pages/timesheet/](../../../frontend/src/pages/timesheet/) | `src/products/timesheet/pages/` |
| [frontend/src/contexts/](../../../frontend/src/contexts/) (Auth, Theme, Tenant) | `src/shared/contexts/` |
| [frontend/src/contexts/ClinicContext.tsx](../../../frontend/src/contexts/ClinicContext.tsx) | `src/products/scheduling/contexts/` |
| [frontend/src/contexts/TimesheetContext.tsx](../../../frontend/src/contexts/TimesheetContext.tsx) | `src/products/timesheet/contexts/` |
| [frontend/src/services/](../../../frontend/src/services/) (apis cross-product) | `src/shared/services/` (auth, billing, tenant, user, audit) |
| `frontend/src/services/clinic/` | `src/products/scheduling/services/` |
| `frontend/src/services/timesheet*` | `src/products/timesheet/services/` |
| [frontend/src/components/](../../../frontend/src/components/) (UI base) | `src/shared/components/` |
| Componentes especificos de scheduling/timesheet | `src/products/{slug}/components/` |

### A.6 Tabelas que NAO Migram (consumidas via API do Portal)

Pela ADR-010, produtos NAO acessam diretamente as seguintes tabelas — consomem via API do Portal:

- `tenants` (replica local mantida via provisioning + eventos)
- `users`
- `companies`
- `subscriptions`, `subscription_items`, `plans`, `invoices`
- `audit_logs` (cada produto envia eventos via API)
- `themes`
- `invite_codes`
- `platform_settings`, `platform_admin_actions`, `platform_waitlist`

---

## Apendice B: Acoplamentos Criticos a Quebrar

| # | Acoplamento | Localizacao | Acao na Migracao |
|---|------------|-------------|------------------|
| 1 | FK `Appointment → Agente` | `backend/models/scheduling/appointment.py` | Substituir FK por `agente_id: str` (sem FK fisica). Validacao via API call ao registry no Portal. |
| 2 | `chat_service.py` dispatcha por `agente.type_config` mas mistura responsabilidades | [backend/services/chat_service.py](../../../backend/services/chat_service.py) | Refinar `agent_registry`: chat_service apenas roteia para handler registrado; cada produto registra seu handler via callback. |
| 3 | `apis/v1/agentes.py` importa 5+ models cross-domain | [backend/apis/v1/agentes.py](../../../backend/apis/v1/agentes.py) | Renomear para `apis/v1/products.py` no Portal; produtos especificos sao registrados, nao acoplados. |
| 4 | `apis/v1/scheduling.py` mistura agente + scheduling + WhatsApp | [backend/apis/v1/scheduling.py](../../../backend/apis/v1/scheduling.py) | Quebrar em camadas: API → SchedulingFacade → services. WhatsApp continua no chatbot-app, scheduling-app chama via REST quando precisa. |
| 5 | Migrations alembic com tabelas multi-dominio | `backend/migrations/versions/063_seed_scheduling_and_itsm_plans.py` | Cada produto tera seu proprio Alembic numerado a partir de 001 quando extraido. |
| 6 | `models/__init__.py` importa tudo (circular import risk) | [backend/models/__init__.py](../../../backend/models/__init__.py) | Lazy import via `__getattr__`; ou `models/{portal,scheduling,timesheet,...}/__init__.py`. |
| 7 | `whatsapp_webhook.py` aceita qualquer agente_id sem validar tipo | [backend/apis/v1/whatsapp_webhook.py](../../../backend/apis/v1/whatsapp_webhook.py) | Validar `agente.agent_type` antes de processar; routing explicito. |
| 8 | Frontend `/admin/SchedulingDashboard.tsx` mistura admin Portal com admin clinic | [frontend/src/pages/admin/SchedulingDashboard.tsx](../../../frontend/src/pages/admin/SchedulingDashboard.tsx) | Mover para `src/products/scheduling/pages/admin/Dashboard.tsx`. Portal dashboard chama via fan-out. |
| 9 | `Agente.type_config` permite qualquer JSON sem validacao | [backend/models/agente.py](../../../backend/models/agente.py) | Criar `TypedDict` por produto + validacao Pydantic estrita. |
| 10 | Chat routing via agente type sem fail-fast | [backend/services/chat_service.py](../../../backend/services/chat_service.py) | Lancar erro se handler obrigatorio nao registrado, em vez de cair em pipeline generico. |

---

## Apendice C: Fontes da Pesquisa

### Modelos de Isolamento e SaaS Patterns
- [AWS SaaS Lens — Silo, Pool, and Bridge Models](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html)
- [AWS Whitepaper — SaaS Tenant Isolation Strategies (PDF)](https://d1.awsstatic.com/whitepapers/saas-tenant-isolation-strategies.pdf)
- [AWS — Multi-Tenant SaaS Storage Strategies](https://docs.aws.amazon.com/whitepapers/latest/multi-tenant-saas-storage-strategies/saas-partitioning-models.html)
- [AWS — Guidance for Multi-Tenant Architectures](https://aws.amazon.com/solutions/guidance/multi-tenant-architectures-on-aws/)

### Control Plane / Application Plane
- [AWS — Control plane vs. application plane](https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/control-plane-vs.-application-plane.html)
- [The New Stack — Why Decoupling Control and Data Planes Is the Future of SaaS](https://thenewstack.io/why-decoupling-control-and-data-planes-is-the-future-of-saas/)
- [Azure — Considerations for Multitenant Control Planes](https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/control-planes)
- [Azure — Architectural Approaches for Control Planes](https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/approaches/control-planes)

### Cell-Based Architecture
- [AWS re:Invent 2024 — SaaS meets cell-based architecture (PDF)](https://d1.awsstatic.com/onedam/marketing-channels/website/aws/en_US/events/approved/reinvent-2025/reinvent/2024/slides/sas/SAS315_SaaS-meets-cell-based-architecture-A-natural-multi-tenant-fit.pdf)
- [Cellular Architecture for Multi-Tenant SaaS — Dan Guisinger](https://danguisinger.com/solutions/cellular-architecture/)
- [DZone — Cell-Based Architecture: Comprehensive Guide](https://dzone.com/articles/grokking-cell-based-architecture)

### JWT / JWKS / Identity
- [microservices.io — Authentication and authorization Part 2](https://microservices.io/post/architecture/2025/05/28/microservices-authn-authz-part-2-authentication.html)
- [microservices.io — Implementing authorization using JWT-based access tokens (Part 3)](https://microservices.io/post/architecture/2025/07/22/microservices-authn-authz-part-3-jwt-authorization.html)
- [Securing Microservices With Asymmetric JWTs](https://medium.com/swlh/securing-microservices-with-assymetric-jwts-88aebb7114fd)
- [FusionAuth — JWT authorization in a microservices gateway](https://fusionauth.io/blog/jwt-authorization-microservices-gateway)

### Microfrontends vs SPA
- [Bitovi — Should Your Team Be Using Micro Frontends and Module Federation?](https://www.bitovi.com/blog/should-your-team-be-using-micro-frontends-and-module-federation)
- [Feature-Sliced Design — Micro-Frontends: Are They Still Worth It in 2025?](https://feature-sliced.design/blog/micro-frontend-architecture)
- [Elysiate — Micro-Frontends Architecture with Module Federation (2025)](https://www.elysiate.com/blog/micro-frontends-architecture-module-federation-2025)

### Stripe Multi-Product Billing
- [Stripe — Set product or subscription quantities (multiple products)](https://docs.stripe.com/billing/subscriptions/multiple-products)
- [Stripe — Mixed interval subscriptions](https://docs.stripe.com/billing/subscriptions/mixed-interval)
- [Stripe — Best practices for SaaS billing](https://stripe.com/resources/more/best-practices-for-saas-billing)
- [Stripe — Sell subscriptions as a SaaS startup](https://docs.stripe.com/get-started/use-cases/saas-subscriptions)
- [Stripe — Build a SaaS platform](https://docs.stripe.com/connect/saas)

---

*Documento gerado em 2026-04-08. Substitui v1 como referencia operacional. v1 preservada como historico do raciocinio inicial. Mudancas materiais devem ser registradas como ADRs adicionais nesta v2 ou em uma futura v3.*
