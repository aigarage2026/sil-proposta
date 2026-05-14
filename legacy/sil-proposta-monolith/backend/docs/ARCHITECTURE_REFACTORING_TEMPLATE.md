# Documento de Arquitetura: Template de Refatoracao SaaS

> **Versao:** 1.1
> **Data:** 2026-04-09
> **Autor:** AI Garage Engineering
> **Status:** Template — derivado de [ARCHITECTURE_ITSM.md](./ARCHITECTURE_ITSM.md)
> **Base de Referencia:** Agent Hub Platform (agent-hub) + ARCHITECTURE_HR_RECRUITMENT.md + ARCHITECTURE_ITSM.md + [MULTI_TENANT_ARCHITECTURE_GUIDE_RH.md](../refatoracao/MULTI_TENANT_ARCHITECTURE_GUIDE_RH.md)
> **Objetivo:** servir como ponto de partida padronizado para refatorar qualquer aplicacao legada (Lovable/Supabase, Next/Firebase, monolitos PHP, etc.) na plataforma SaaS AI Garage.

---

## Como Usar Este Documento

Este e um **template generico** de arquitetura para refatorar aplicacoes existentes que serao migradas para o padrao tecnologico da plataforma SaaS AI Garage (FastAPI + SQLAlchemy + Postgres + React/Vite, com integracao com Agent Hub).

### Fluxo recomendado

1. **Copie** este arquivo para `docs/plans/pending/ARCHITECTURE_{APP_NAME}.md`.
2. **Substitua** todos os placeholders entre chaves (ver tabela §0.2).
3. **Preencha** a Secao 0 (Caracterizacao do As-Is) com base em uma analise tecnica do legado (apoie-se no doc fonte do projeto, geralmente em `docs/refatoracao/...`).
4. **Mantenha** intactas as secoes "Replicar do Agent Hub" — sao padroes ja validados em producao.
5. **Especialize** apenas as secoes marcadas com `[ESPECIALIZAR]`: dominio (§3), FSM (§8), endpoints (§9), telas (§10), variaveis ambiente (§24), seed (§26), checklist (§27) e apendices (A/B).
6. **Registre** desvios em ADRs novas (§28). Toda decisao que se afaste do padrao deve estar justificada.
7. **Revise** com o time antes de iniciar a Fase 1.

### 0.1 Placeholders padrao

| Placeholder | Significado | Exemplo |
|-------------|-------------|---------|
| `{APP_NAME}` | Nome curto, lowercase, slug-friendly | `itsm`, `crm`, `hr_recruiter` |
| `{APP_NAME_HUMAN}` | Nome para exibicao | "ITSM", "CRM Vendas" |
| `{APP_DOMAIN}` | Subdominio publico | `itsm.ai-garage.com.br` |
| `{APP_DESCRIPTION}` | Frase resumindo a aplicacao | "Service desk para hospitais e MSPs" |
| `{LEGACY_STACK}` | Stack do as-is | "React + Supabase + Edge Functions Deno" |
| `{LEGACY_DOC_PATH}` | Caminho do doc de origem do as-is | `docs/refatoracao/...md` |
| `{TARGET_PERSONAS}` | Quem usa | "agentes de suporte, gerentes de TI" |
| `{CORE_DOMAIN_ENTITY}` | Entidade central do dominio | `Ticket`, `Candidate`, `Lead` |
| `{DOMAIN_PILLARS}` | Pilares funcionais do dominio | "Incident, Problem, Change, KB" |
| `{N_LEGACY_TABLES}` | Quantas tabelas o as-is tem | `~100` |
| `{N_LEGACY_FUNCTIONS}` | Quantas edge functions / jobs | `32` |

### 0.2 Diretrizes editoriais

- **Sempre cite arquivos com path relativo ao repo Agent Hub** quando referenciar codigo existente que sera reaproveitado.
- **Use tabelas** para mapeamentos as-is → refatorado e para responsabilidades.
- **Evite hardcoding de regras de negocio especificas no documento** — deixe que o leitor especialize nos modelos.
- **Marque toda secao especializavel com `[ESPECIALIZAR]`** no titulo para facilitar buscas.

---

## 0. Caracterizacao do As-Is `[ESPECIALIZAR]`

> Preenchimento obrigatorio antes de iniciar o desenho. Sintetize do `{LEGACY_DOC_PATH}`.

| Item | Conteudo |
|------|----------|
| **Stack atual** | `{LEGACY_STACK}` |
| **Banco** | (ex.: Postgres Supabase com 439 RLS policies) |
| **Tabelas** | `{N_LEGACY_TABLES}` agrupadas em N dominios |
| **Funcoes serverless / cron** | `{N_LEGACY_FUNCTIONS}` (descrever brevemente) |
| **Auth atual** | (ex.: Supabase Auth com JWT proprio) |
| **Multi-tenant atual?** | Sim/Nao — qual mecanismo |
| **Storage** | (ex.: Supabase Storage / S3) |
| **Busca/IA** | (ex.: pgvector + tsvector) |
| **i18n** | Quantos idiomas, namespaces |
| **Integracoes externas** | Stripe, Twilio, SendGrid, etc. |
| **Volume estimado** | Tenants, requests/mes, GB armazenados |
| **Riscos identificados** | Acoplamento, RLS sprawl, falta de testes, etc. |
| **Funcionalidades a NAO migrar** | (ex.: billing centralizado vai para Agent Hub) |

---

## Sumario Executivo `[ESPECIALIZAR]`

A refatoracao de **{APP_NAME_HUMAN}** ({APP_DESCRIPTION}) substitui a aplicacao atual ({LEGACY_STACK}) por uma plataforma SaaS independente sobre o stack padrao da AI Garage: FastAPI + SQLAlchemy + Postgres + React/Vite. A nova versao tera **codigo, banco, deploy e dominio proprios** ({APP_DOMAIN}), integrando com o Agent Hub apenas via API para:

- **Onboarding e billing centralizados** (Stripe, planos, checkout, upgrade/downgrade);
- **LLM/conversacional** (todas as chamadas a modelos GPT/Gemini/Claude passam pelo Agent Hub);
- **Funcionalidades cross-app** especificas (a definir por aplicacao).

Recursos pesados que **nao** dependem do Agent Hub (busca semantica, CRUD de dominio, dashboards, FSM proprio) sao executados localmente.

A migracao e executada em **ondas** (MVP-1 → MVP-2 → ondas N+) para reduzir risco e acelerar o primeiro deploy.

---

## 1. Visao Geral da Arquitetura

### 1.1 Principios Arquiteturais

| Principio | Descricao |
|-----------|-----------|
| **Isolamento Total** | Banco, deploy, dominio e ciclo de release separados do Agent Hub |
| **Multi-Tenancy** | Isolamento logico por `tenant_id` (TenantMixin) com cascade delete |
| **Shared-Nothing** | Nenhum recurso compartilhado em runtime com Agent Hub |
| **Shared Libraries** | Pacotes Python/TS internos (`agn-*`) para reutilizar padroes validados |
| **API-First** | Toda funcionalidade exposta via REST documentada (FastAPI + OpenAPI) |
| **Security by Default** | Rate limiting, brute force, encryption, isolation tests obrigatorios |
| **Domain-Driven** | Modelos e servicos organizados pelos pilares funcionais do dominio (`{DOMAIN_PILLARS}`) |
| **Migracao em Ondas** | MVP-1 entregue rapido, demais funcionalidades por valor decrescente |

### 1.2 Diagrama de Alto Nivel

```
                    ┌─────────────────────────────────────────┐
                    │           Cloudflare (SSL/DDoS)         │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────────┐
                    │         Nginx (Reverse Proxy)           │
                    │  - Rate Limiting (por rota)             │
                    │  - Security Headers                     │
                    │  - Gzip / Static caching                │
                    │  - WebSocket Upgrade                    │
                    └───────┬─────────────────┬───────────────┘
                            │                 │
                   ┌────────┴───────┐  ┌──────┴──────────┐
                   │  Frontend SPA  │  │   Backend API   │
                   │  React + Vite  │  │  FastAPI + SA   │
                   └────────────────┘  └───────┬─────────┘
                                               │
        ┌──────────────┬──────────┬────────────┼────────────┬──────────────┐
  ┌─────┴─────┐ ┌─────┴────┐ ┌───┴────┐ ┌─────┴────┐ ┌────┴─────┐ ┌─────┴──────┐
  │ Postgres   │ │  Redis   │ │ Qdrant │ │  Stripe  │ │ Agent    │ │ SMTP /     │
  │ ({APP})    │ │ (Cache/  │ │ (opt.) │ │(via Hub) │ │ Hub API  │ │ Twilio /   │
  │            │ │ Sessions)│ │        │ │          │ │ (LLM)    │ │ Slack/Teams│
  └────────────┘ └──────────┘ └────────┘ └──────────┘ └──────────┘ └────────────┘
```

> **Qdrant e opcional.** So inclua se a aplicacao tiver busca semantica nativa (ex.: KB, biblioteca de documentos, matching). Caso contrario, remova.

### 1.3 Stack Tecnologico

| Camada | Tecnologia | Versao | Justificativa |
|--------|-----------|--------|---------------|
| **Backend** | Python + FastAPI | 3.11 / 0.115+ | Padrao validado, async nativo |
| **ORM** | SQLAlchemy | 2.0+ | Mapeamento relacional robusto |
| **Migrations** | Alembic | 1.13+ | Versionamento de schema |
| **Database** | PostgreSQL | 16 | ACID, JSON nativo, fulltext |
| **Cache/Sessions** | Redis | 7 | Rate limiting, sessoes, filas |
| **Vector DB (opt.)** | Qdrant | 1.12+ | Busca semantica local (so se necessario) |
| **Frontend** | React + TypeScript | 19 / 5.9 | SPA responsivo, tipagem forte |
| **Build** | Vite | 7+ | Build rapido, HMR |
| **UI** | Tailwind + shadcn/ui | 3.4 / latest | Padrao do Agent Hub, transferivel |
| **Forms** | React Hook Form + Zod | 7.x / 3.x | Validacao tipada |
| **Tables/Data** | TanStack Query + Table | 5.x | Data fetching + grids |
| **i18n** | i18next + react-i18next | 25.x | pt/en/es por padrao |
| **HTTP Client** | httpx (BE) / Axios (FE) | latest | Async + interceptors |
| **WebSockets** | Starlette WebSocket | nativo | Realtime, chat, notificacoes |
| **Containerizacao** | Docker + Docker Compose | 24+ / v2 | Deploy uniforme |
| **Proxy/Gateway** | Nginx | 1.25 | Rate limiting, SSL, proxy, WS upgrade |
| **SSL/DDoS** | Cloudflare | - | Protecao na borda |
| **Pagamento** | Stripe (via Agent Hub) | API v2024+ | Centralizado |
| **CI/CD** | GitHub Actions | - | Build, test, deploy |
| **IaC** | Terraform | 1.5+ | GCP/AWS |

> **Componentes opcionais** (incluir somente se justificado): TipTap (editor WYSIWYG), Recharts (graficos avancados), Twilio (WhatsApp/SMS), MinIO/S3 (storage objeto), Prometheus/Grafana (observabilidade).

### 1.4 O Que NAO Esta no Escopo

- **Stripe direto:** nenhum app refatorado implementa checkout/portal/webhooks Stripe diretamente. Esses fluxos vivem no Agent Hub.
- **LLM gateway proprio:** todo acesso a modelos passa pelo Agent Hub.
- **Onboarding white-label proprio:** tenant nasce no Agent Hub e e provisionado no app via HMAC token.
- `[ESPECIALIZAR]` Outras funcionalidades a manter centralizadas (ex.: sistema de planos compartilhados, gerenciamento de usuarios cross-app, etc.).

---

## 2. Multi-Tenancy e Isolamento de Dados

### 2.1 Hierarquia de 3 Niveis (Obrigatoria)

Toda aplicacao SaaS da plataforma segue a hierarquia **Tenant → Company → Recursos Operacionais**. Este e o erro mais comum em aplicacoes geradas por IA: modelar `Empresa 1:1 Tenant`. O modelo correto e:

```
┌─────────────────────────────────────────────────────────┐
│  TENANT  (workspace / holding / cliente SaaS)           │
│  - Unidade de cobranca e isolamento de dados            │
│  - Possui o plano, limites, branding, subscription      │
│  - Recursos compartilhados entre Companies              │
│  - 1 tenant = 1 cliente da plataforma                   │
└──────────────┬──────────────────────────────────────────┘
               │ 1:N
       ┌───────▼─────────────────────────┐
       │  COMPANY  (empresa / unidade)   │
       │  - CNPJ, razao social, fiscal   │
       │  - N companies por tenant       │
       └───────┬─────────────────────────┘
               │ 1:N
       ┌───────▼─────────────────────────┐
       │  RECURSOS OPERACIONAIS          │
       │  (entidades de dominio          │
       │   especificas de cada app)      │
       └─────────────────────────────────┘
```

**Conceitos-chave:**

| Conceito | Regra |
|----------|-------|
| **Tenant** | Raiz da multi-tenancy. Carrega plano, billing, branding. **NAO** carrega CNPJ — CNPJ e da Company. 1 tenant pode representar uma holding com varias empresas. |
| **Company** | Pessoa juridica (CNPJ, razao social, fiscal). Sempre com `tenant_id` obrigatorio. Recursos operacionais sao filhos da Company, nao do Tenant. Uma Company tem `is_default=true` (primeira criada no onboarding). |
| **User** | Pertence ao Tenant (`tenant_id` obrigatorio), NAO a uma Company. Tem role no nivel do tenant. Owner tem acesso implicito a todas as Companies (sem `UserCompanyAccess`). Demais users precisam de registro explicito. |
| **UserCompanyAccess** | N:N User ↔ Company com `role` por company. `tenant_id` denormalizado para queries. Constraint unica: `(user_id, company_id)`. Owners nao precisam desta tabela. |
| **Platform Admin** | `User.is_platform_admin = true` — flag cross-tenant para operadores da plataforma SaaS (time do produto, NAO clientes). |
| **Ator Externo (opcional)** | Entidades como Candidato, Paciente, Solicitante que NAO sao `User`. Tem auth propria, conta em limites proprios (`max_candidates`, `max_contacts`), nao em `max_users`. JWT separado com `aud` especifico. **Nunca modele atores externos como User.** |

**Cardinalidade correta (ajustar ao dominio):**

| Relacao | Cardinalidade |
|---------|---------------|
| Tenant → Company | **1 : N** |
| Tenant → User (interno) | **1 : N** |
| Tenant → {Ator Externo} (opcional) | **1 : N** (escopo de tenant, compartilhado entre Companies) |
| Company → Recursos operacionais | **1 : N** |
| User ↔ Company (acesso) | **N : N** via `UserCompanyAccess` com role |

### 2.2 Estrategia de Isolamento

Substituir mecanismos do as-is (RLS Supabase, schemas dedicados, app-id implicit) por **isolamento logico por row** com `tenant_id` em todas as tabelas de dominio + filtragem manual no service layer + testes contratuais cross-tenant. Padrao validado pelo Agent Hub.

```python
# agn_core.models.base
class UUIDMixin:
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), nullable=False)

class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class TenantMixin:
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
```

**Modelos SEM TenantMixin** (excecoes — entidades de plataforma):
- `Tenant` (a raiz)
- `Plan` / catalogo de planos
- `InviteCode` (codigos de convite globais)
- Tabelas de billing global, feature flags da plataforma

### 2.3 Regras de Isolamento

| Camada | Mecanismo |
|--------|-----------|
| **Database** | TenantMixin em todas as tabelas de dominio; CASCADE delete |
| **Query** | TODOS os queries filtram por `tenant_id` (manual no service layer) — validado por testes |
| **API** | `get_current_tenant_id()` extrai tenant do JWT (dependency). **NUNCA** aceitar `tenant_id` do body/query — sempre do token |
| **Storage** | `/data/{APP_NAME}/{tenant_id}/{namespace}/` |
| **Vector Store (opt.)** | Collections Qdrant: `{APP_NAME}_{tenant_id}_{namespace}` |
| **Redis** | Keys prefixadas: `{APP_NAME}:{tenant_id}:{namespace}:{id}` |
| **Logs** | Trace ID + tenant_id em todo log estruturado (structlog) |
| **Observabilidade** | Metricas Prometheus carregam label `tenant_id` |
| **URLs assinadas** | Incluir `tenant_id` na assinatura e validar no servidor antes de servir downloads |

### 2.4 Constraints de Unicidade por Tenant

Identificadores "amigaveis" (slug, codigo, numero) precisam ser unicos **dentro do tenant**, nao globalmente:

```python
__table_args__ = (
    UniqueConstraint("tenant_id", "slug", name="uq_{table}_tenant_slug"),
    UniqueConstraint("tenant_id", "code", name="uq_{table}_tenant_code"),
)
```

Aplicar a: codigo de registro, email de ator externo, slug de portal, numero sequencial de entidades.

### 2.5 Filtragem Obrigatoria no Service Layer (Barreira 1)

**Decisao critica (ADR-010):** a filtragem por `tenant_id` acontece no service layer Python.

1. Toda funcao de service que recebe `db: Session` tambem recebe `tenant_id: str` e aplica `.filter(Model.tenant_id == tenant_id)` em CADA query.
2. O `tenant_id` vem do JWT/sessao do usuario autenticado, **nunca** do payload da request — caso contrario cria vulnerabilidade de IDOR cross-tenant.
3. Endpoints recebem `company_id` quando a operacao e escopada a uma unidade; **validar que a company pertence ao tenant do usuario** antes de qualquer operacao.
4. Existem testes obrigatorios de isolamento (`TestXxxIsolation` por modelo) que tentam acesso cross-tenant e esperam 404 (NAO 403 — nao vazar existencia).
5. Pull requests sao bloqueados se um modelo novo nao tiver teste de isolamento (CI check).

```python
# Padrao obrigatorio de query
db.query(Entity).filter(
    Entity.tenant_id == current_tenant_id,  # SEMPRE primeiro
    Entity.id == entity_id,
).first()
```

### 2.6 Row Level Security (RLS) — Barreira 2 (Defesa em Profundidade)

RLS e a **segunda barreira** contra vazamento cross-tenant. O filtro `tenant_id` no service layer e a primeira; o RLS garante que, mesmo se um desenvolvedor esquecer o filtro, o banco bloqueia.

> **Quando usar RLS:** aplicacoes que armazenam **dados regulados** (LGPD, HIPAA) — dados de candidatos, pacientes, informacoes financeiras de terceiros — **devem** habilitar RLS como segunda barreira. Para apps com dados menos sensiveis, RLS e opcional (ver ADR-010/ADR-013).

#### 2.6.1 Como funciona

1. Toda tabela com `tenant_id` recebe `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`.
2. Politica compara `tenant_id` da linha com variavel de sessao PostgreSQL (`app.current_tenant`).
3. Middleware da aplicacao define essa variavel **no inicio de cada request**, com o `tenant_id` extraido do JWT.
4. Toda query subsequente naquela conexao so enxerga linhas do tenant correto.

#### 2.6.2 Migration de RLS

```sql
-- Habilitar RLS em tabela tenant-scoped
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;

-- Politica de isolamento
CREATE POLICY tenant_isolation_{table_name} ON {table_name}
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- (Opcional) bypass para Platform Admins via role separado
CREATE POLICY platform_admin_bypass_{table_name} ON {table_name}
    TO platform_admin_role
    USING (true)
    WITH CHECK (true);
```

Repetir para **todas** as tabelas com `TenantMixin`. Recomendado: gerar via script/migration que itera sobre todas as tabelas marcadas.

#### 2.6.3 Middleware FastAPI para RLS

```python
@app.middleware("http")
async def set_tenant_context(request: Request, call_next):
    tenant_id = extract_tenant_from_jwt(request)  # do token, NUNCA do payload
    if tenant_id:
        # SET LOCAL: dura so ate o fim da transacao (nunca SET — vazaria entre requests no pool)
        db.execute(text("SET LOCAL app.current_tenant = :tid"), {"tid": tenant_id})
    return await call_next(request)
```

**Pontos criticos:**
- Use `SET LOCAL` (escopo de transacao), **nunca** `SET` (escopo de sessao) — evita vazar contexto entre requests no pool de conexoes.
- Defina antes de qualquer SELECT/INSERT/UPDATE/DELETE.
- Pool de conexoes deve resetar a variavel ao devolver conexao (`RESET app.current_tenant` no `on_checkin`).
- **Endpoints publicos** (portal externo, webhooks) tambem precisam setar `app.current_tenant` — derivado do slug do tenant na URL ou do `tenant_id` da entidade acessada.

#### 2.6.4 Bypass para Platform Admins

Duas estrategias:

**A) Role PostgreSQL separado** (mais seguro):
- App usa `app_user` por padrao (sujeito ao RLS).
- Endpoints de Platform Admin usam conexao com role `platform_admin_role` (com `BYPASSRLS`).

**B) Variavel de sessao de bypass**:
- `SET LOCAL app.is_platform_admin = 'true'`.
- Politica inclui: `USING (... OR current_setting('app.is_platform_admin', true) = 'true')`.

Em ambos os casos, **toda acao de Platform Admin que mexe em dados de cliente deve gerar audit log**.

#### 2.6.5 Tabelas que NAO devem ter RLS

`tenants`, `plans`, `invite_codes`, tabelas de billing global, feature flags da plataforma — entidades sem `tenant_id`.

#### 2.6.6 Testes obrigatorios de RLS

- Criar 2 tenants, inserir dados em ambos, verificar que cada um so le os proprios.
- `UPDATE` cross-tenant deve afetar 0 linhas.
- `DELETE` cross-tenant deve afetar 0 linhas.
- Sem `app.current_tenant` setado, queries retornam vazio (falha segura, nao erro).
- Ator externo do tenant A nunca aparece em busca/listagem do tenant B.

### 2.7 Anti-Padroes de Multi-Tenancy

| # | Anti-padrao | Consequencia |
|---|------------|-------------|
| 1 | **Tenant 1:1 Company** | Impossibilita holdings com multiplos CNPJs e recursos compartilhados |
| 2 | **CNPJ no Tenant** | Fiscal pertence a Company, nao ao workspace |
| 3 | **User vinculado a uma unica Company** | User pertence ao Tenant; acesso a Companies e via N:N |
| 4 | **Ator externo modelado como User** | Confunde RBAC, conta em `max_users` errado, mistura auth de admin com auth publica |
| 5 | **`tenant_id` opcional** | Sempre `nullable=False` (exceto entidades de plataforma) |
| 6 | **Aceitar `tenant_id` no payload da request** | Vetor de IDOR cross-tenant — sempre do JWT |
| 7 | **Filtrar so por `id` sem `tenant_id` no WHERE** | Vetor de IDOR — `tenant_id` sempre presente |
| 8 | **Constraints unicas globais** | Devem ser compostas com `tenant_id` |
| 9 | **CASCADE delete ausente** | Deletar Tenant deve apagar tudo (`ondelete="CASCADE"`) |
| 10 | **Storage compartilhado sem prefixo de tenant** | Vazamento de arquivos entre clientes |
| 11 | **Owner precisando de UserCompanyAccess** | Owner tem acesso implicito a tudo |
| 12 | **Retornar 403 para recurso de outro tenant** | Deve ser **404** (nao vazar existencia) |
| 13 | **Download sem assinatura/validacao de tenant** | Qualquer um com a URL acessa o arquivo |
| 14 | **Nao auditar acesso a dados sensiveis** | LGPD/compliance exigem rastreabilidade |
| 15 | **Nao modelar consentimento e retencao** | Base legal (LGPD) precisa estar registrada por ator externo |

### 2.8 Modelos Base (Vem do Agent Hub via Shared Libs)

Replicar exatamente do Agent Hub via `agn-core` / `agn-billing` / `agn-platform`:

- **Tenant** — Raiz do multi-tenancy (name, slug, plan_slug, features, limits, branding)
- **User** — Usuarios com RBAC
- **Company** — Unidade de negocio dentro do tenant
- **UserCompanyAccess** — N:N User ↔ Company com role
- **Subscription / Plan / Invoice** — Vivem no Agent Hub; consumidos via `agn-billing` client
- **TenantLimit** — Override de limites do plano
- **TenantSetupStatus** — Progresso do onboarding do app
- **Theme** — Configuracao visual por tenant/empresa
- **AuditLog** — Log de auditoria append-only

---

## 3. Modelo de Dados — Dominio `[ESPECIALIZAR]`

Esta secao e o coracao da especializacao. Substitua tudo abaixo pelos modelos especificos do seu dominio. Use o **metodo descrito abaixo** para garantir consistencia com o padrao.

### 3.1 Metodologia de Modelagem

1. **Liste as ~N tabelas do as-is** organizadas por pilar funcional (`{DOMAIN_PILLARS}`).
2. **Classifique cada tabela em uma onda de migracao** (MVP-1 / MVP-2 / Onda 3+ / NAO migrar).
3. **Identifique tabelas que vao virar shared lib** (`agn-core`: tenant, user, company, role, audit). Essas NAO sao redefinidas no app.
4. **Identifique tabelas que NAO sao migradas** (planos, assinaturas, invoices, invite codes — consumidas via Agent Hub).
5. **Para cada tabela restante**, defina um modelo SQLAlchemy seguindo o template abaixo.
6. **Documente o mapeamento completo** no Apendice A.

#### Template de modelo

```python
class {EntityName}(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """{Descricao curta da entidade}."""
    __tablename__ = "{snake_case_plural}"

    # FKs
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    # ... outras FKs

    # Campos de negocio
    name = Column(String(255), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="active")
    # ...

    # Metadados/JSON livre
    tags = Column(JSON)
    custom_fields = Column(JSON)

    # Relacionamentos
    # ...

    __table_args__ = (
        Index("ix_{table}_tenant_status", "tenant_id", "status"),
        # Sempre indexar por (tenant_id, <coluna mais filtrada>)
    )
```

#### Convencoes obrigatorias

| Convencao | Regra |
|-----------|-------|
| **Heranca** | Sempre `Base, UUIDMixin, TimestampMixin, TenantMixin` (salvo entidades platform-level) |
| **Tipos** | `String(36)` para UUID, `JSON` para estruturas, `Text` para texto longo, `DateTime` (UTC, naive) |
| **Indices compostos** | Sempre incluir `tenant_id` como primeira coluna |
| **Cascade** | `ondelete="CASCADE"` em FKs internas do dominio |
| **Unique constraints** | Sempre escopadas por `tenant_id` (`UniqueConstraint("tenant_id", "code", ...)`) |
| **Encryption** | Campos sensiveis (PII, segredos) → `LargeBinary` com Fernet (`agn-auth.encryption`) |
| **Status enum** | Use `String(30)` + lista validada via Pydantic, NAO Postgres ENUM (evita migrations dolorosas) |
| **Soft delete (opcional)** | Coluna `deleted_at` quando precisar; NUNCA `is_deleted` boolean isolado |

### 3.2 Ondas de Migracao `[ESPECIALIZAR]`

| Onda | Dominios | Objetivo |
|------|---------|----------|
| **MVP-1** | (listar pilares minimos para o primeiro deploy) | Primeiro valor entregavel |
| **MVP-2** | (proximas funcionalidades de operacao) | Operacao completa |
| **Onda 3** | (engajamento, customizacao, gamificacao) | Refinamento |
| **Onda 4** | (API publica, webhooks, auditoria avancada) | Conformidade e integracoes |
| **Plataforma** | Billing/Onboarding/Invite Codes | NAO migrar — consumir via Agent Hub |

### 3.3 Diagrama Logico de Entidades MVP-1 `[ESPECIALIZAR]`

> Substitua pelo diagrama ASCII das entidades centrais do dominio. Veja `ARCHITECTURE_ITSM.md §3.2` como exemplo de layout.

### 3.4 Indices Criticos para Performance `[ESPECIALIZAR]`

Liste os indices compostos esperados (todos com `tenant_id` como primeira coluna). Considere:

- Coluna mais filtrada (`status`, `assigned_to`, `due_at`)
- Colunas de busca por usuario (`email`, `phone`, `code`)
- Colunas para relatorios/dashboards (datas, agregacoes)

---

## 4. Seguranca

### 4.1 Camadas de Seguranca (Replicar do Agent Hub)

```
┌─────────────────────────────────────────────────────────┐
│ Camada 1: BORDA (Cloudflare)                            │
│  - DDoS Layer 3/4/7, WAF, SSL/TLS, Bot Management       │
├─────────────────────────────────────────────────────────┤
│ Camada 2: GATEWAY (Nginx)                               │
│  - Auth: 5 req/s/IP        - API geral: 20 req/s/IP     │
│  - Chat/IA: 10 req/s/IP    - Upload: 10 req/s/IP        │
│  - WebSocket: 3 conn/s/IP  - Conn limit: 50/IP          │
│  - Security headers (XSS, MIME, Clickjack, Referrer)    │
│  - Body limit: 50KB endpoints publicos / 25MB upload    │
├─────────────────────────────────────────────────────────┤
│ Camada 3: APLICACAO (FastAPI)                           │
│  - JWT (HS256, exp configurable)                        │
│  - Brute force protection (Redis-backed)                │
│  - SlowAPI rate limiting por endpoint                   │
│  - Subscription middleware                              │
│  - Trace middleware (X-Trace-ID)                        │
├─────────────────────────────────────────────────────────┤
│ Camada 4: DOMINIO                                       │
│  - Pydantic validation em todos os payloads             │
│  - Tenant isolation enforcement no service layer        │
│  - Encryption (Fernet) em campos sensiveis              │
│  - Hash + prefixo visivel para API keys                 │
├─────────────────────────────────────────────────────────┤
│ Camada 5: DADOS                                         │
│  - TenantMixin (CASCADE delete)                         │
│  - Filtragem por aplicacao (NAO RLS nativo)             │
│  - Backup criptografado, restore com preview            │
│  - Cross-tenant tests obrigatorios                      │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Substituicao de Mecanismos Legados

| As-Is | Refatorado |
|-------|------------|
| RLS / policies do banco | Filtragem `WHERE tenant_id = :tenant_id` no service |
| Funcoes `SECURITY DEFINER` | Dependency `get_current_tenant_id()` no FastAPI |
| `is_super_admin()` | `get_platform_admin()` dependency |
| `has_role()` | `require_role([...])` dependency |
| Triggers de seed automatico | Onboarding service cria associacoes na criacao do user |

### 4.3 Seguranca Especifica `[ESPECIALIZAR]`

| Aspecto | Tratamento |
|---------|-----------|
| **Anexos / uploads** | Storage em `/data/{APP_NAME}/{tenant_id}/`; download via endpoint autenticado que valida tenant + permissao |
| **Dados sensiveis (PII)** | Tabela separada com encryption Fernet em colunas sensiveis |
| **API Keys (onda publica)** | SHA-256 hash + prefixo visivel; nunca armazenar plaintext |
| **Credenciais externas** | `LargeBinary` com Fernet |
| **Logs de erro** | Sem PII; sanitizacao de stacktraces |
| **Cross-tenant detection** | Hash SHA-256 de email para detectar tentativa cross-tenant |
| **Endpoints publicos** | Rate limiting agressivo + body limit pequeno + captcha |

---

## 5. Autenticacao e Autorizacao

### 5.1 Fluxo de Autenticacao

```
1. Tenant nasce no Agent Hub (signup + checkout Stripe).
2. Agent Hub gera provisioning_token HMAC e POSTa /api/v1/integrations/agent-hub/provision.
3. {APP_NAME} cria Tenant + Owner User + defaults.
4. Usuario faz login direto no {APP_NAME} (POST /auth/login).
5. {APP_NAME} emite JWT proprio (HS256, 1h exp + refresh 30d).
6. Frontend armazena JWT, faz requests com Authorization: Bearer ...
7. Cada request: get_current_user() valida JWT → extrai tenant_id + user_id + role.
```

> Decisao registrada como **ADR-009** (ver §28). Cada app emite JWT proprio (em vez de SSO federado) para preservar independencia de runtime.

### 5.2 RBAC em 3 Camadas Independentes

A autorizacao tem **tres camadas** que se combinam. Erro comum: misturar tudo em um unico campo `role`.

```
┌─────────────────────────────────────────────────────────┐
│ CAMADA 1 — PLATAFORMA                                   │
│ User.is_platform_admin (boolean)                        │
│ → Operadores da plataforma SaaS (cross-tenant)          │
│ → NAO e cliente; e o time do produto                    │
└─────────────────────────────────────────────────────────┘
                       │ (independente)
┌─────────────────────────────────────────────────────────┐
│ CAMADA 2 — TENANT (workspace)                           │
│ User.role: owner | admin | editor | viewer              │
│ → Define poderes do usuario DENTRO do tenant dele       │
└─────────────────────────────────────────────────────────┘
                       │ (granularidade adicional)
┌─────────────────────────────────────────────────────────┐
│ CAMADA 3 — COMPANY (unidade de negocio)                 │
│ UserCompanyAccess.role: admin | editor | viewer         │
│ → Define poderes do usuario em UMA company especifica   │
└─────────────────────────────────────────────────────────┘
```

#### 5.2.1 Camada 1 — Platform Admin

- Flag booleano `User.is_platform_admin`. **Cross-tenant**: enxerga todos os tenants.
- NAO acessa dados de cliente diretamente — entra via **modo view** (token com `viewing_tenant_id` + `is_view_only=true`; mutacoes bloqueadas).
- Toda acao deve ser auditada — especialmente leitura de dados sensiveis (LGPD).
- Implementacao: `get_platform_admin` + `create_tenant_view_token` / `verify_tenant_view_token` (de [backend/core/security.py](../../../backend/core/security.py)).

**Operacoes tipicas:** criar/suspender tenants, billing global, reset senha, suporte em modo view, gerar invite codes, atender solicitacoes LGPD.

#### 5.2.2 Camada 2 — Roles de Tenant

Campo `User.role` (string) com 4 valores hierarquicos:

| Role | Poderes |
|------|---------|
| `owner` | Tudo no tenant. Acesso implicito a **todas** as Companies (sem `UserCompanyAccess`). Unico que pode deletar o tenant, trocar plano. |
| `admin` | Gerenciar usuarios, companies, configuracoes do tenant, templates. |
| `editor` | Operar recursos nas Companies onde tem acesso. NAO gerencia usuarios nem config de tenant. |
| `viewer` | Somente leitura. |

**Regra de ouro:** Owner nao precisa de `UserCompanyAccess` — tem acesso a tudo. Todos os outros precisam de registro explicito por Company.

#### 5.2.3 Camada 3 — Roles de Company (UserCompanyAccess)

Tabela `user_company_access` (N:N) carrega `role` por company:

| Role | Poderes na company |
|------|-------------------|
| `admin` | Gerenciar recursos da company, convidar usuarios |
| `editor` | Criar/editar recursos operacionais |
| `viewer` | Somente leitura |

**Regras de verificacao ao acessar recurso de Company X:**
1. Recurso pertence ao mesmo `tenant_id` do usuario? Se nao → **404** (nao vazar existencia).
2. Usuario e `owner` do tenant? → autorizado.
3. Existe `UserCompanyAccess(user_id, company_id)`? Se nao → 403.
4. O `role` permite a acao? Se nao → 403.
5. O **role do tenant e teto** do role da company: um `viewer` no tenant nao pode ser `admin` de uma company.

#### 5.2.4 Camada Adicional — Roles de Dominio `[ESPECIALIZAR]`

Dominios complexos (RH, ITSM, CRM) tem perfis funcionais que **nao substituem** as 3 camadas acima — eles **complementam** com permissoes especificas:

```python
# Exemplo: tabela de roles de dominio
class User{Domain}Role(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "user_{domain}_roles"
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    {domain}_role = Column(String(50), nullable=False)
    # ex.: "recruiter", "hiring_manager", "agent", "supervisor"
```

**Implementacao recomendada:**
- Service de permissao centralizado (`{domain}_permission_service`) que valida acao × perfil × recurso, em vez de checks espalhados.
- Constantes/enum centralizando nomes de roles — sem strings hardcoded.
- MFA obrigatorio para `owner`, `is_platform_admin` e roles de compliance.

#### 5.2.5 Matriz de Decisao (Modelo)

| Cenario | Onde checar |
|---------|------------|
| "Pode criar um novo tenant?" | `is_platform_admin == true` |
| "Pode trocar o plano?" | `User.role == 'owner'` ou `is_platform_admin` |
| "Pode convidar usuario?" | `User.role in ('owner','admin')` |
| "Pode criar Company?" | `User.role in ('owner','admin')` |
| "Pode operar recurso na Company X?" | mesmo tenant **E** (owner OU `UserCompanyAccess.role in ('admin','editor')`) |
| "Pode ver dados de outro tenant?" | `is_platform_admin` **E** modo view ativo |

#### 5.2.6 Anti-Padroes de RBAC

1. **Misturar Platform Admin com role de tenant** — camadas diferentes.
2. **Hardcode de role em strings espalhadas** — centralize em constantes/enum.
3. **Checar role so no frontend** — sempre dupla checagem no backend via dependency FastAPI.
4. **Permitir mudanca de role sem audit log** — toda elevacao de privilegio auditada.
5. **Owner sem MFA** — owners e platform admins devem ter MFA obrigatorio.
6. **Platform Admin sem modo view** — ele NAO deve ter `tenant_id` ativo diretamente.
7. **403 quando deveria ser 404** — recurso de outro tenant → 404.
8. **Confiar no `tenant_id` do payload** — sempre do JWT.
9. **Modelar ator externo como User** — auth, lifecycle e regulacao distintos (ver §2.1).

### 5.3 Auth de Ator Externo (Separada do RBAC) `[ESPECIALIZAR se aplicavel]`

Se a aplicacao tem atores externos (candidatos, pacientes, solicitantes), eles **NAO usam o RBAC acima**:

- **Identificacao:** email + magic link, OTP por WhatsApp/SMS, OAuth social, ou sessao anonima durante chat com agente conversacional.
- **Token:** JWT separado, com `aud: "{app_name}-portal"`, `tenant_id`, `{actor}_id`, **sem** role de workspace.
- **Endpoints:** prefixo `/portal/{actor}/*` — nunca usam `get_current_user` (que e para User do workspace).
- **Permissao:** ator so ve/edita os proprios dados (`WHERE {actor}_id = current_{actor}_id AND tenant_id = current_tenant_id`).
- **Storage:** uploads isolados por tenant; validacao de tipo, tamanho, antivirus opcional.
- **LGPD:** endpoint de exportacao dos proprios dados + endpoint de solicitacao de exclusao (right to be forgotten).

### 5.4 JWT Claims

```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "tenant_id": "tenant-uuid",
  "company_id": "company-uuid",
  "roles": ["..."],
  "global_role": null,
  "exp": 0,
  "iat": 0,
  "trace_id": "..."
}
```

**JWT de Ator Externo (portal):**

```json
{
  "sub": "{actor}-uuid",
  "aud": "{app_name}-portal",
  "tenant_id": "tenant-uuid",
  "{actor}_id": "actor-uuid",
  "exp": 0,
  "iat": 0
}
```

---

## 6. Onboarding de Clientes

### 6.1 Fluxo de Onboarding (Agent Hub → {APP_NAME})

```
1. Landing page Agent Hub → seleciona plano "{APP_NAME_HUMAN} Professional"
2. Signup + checkout Stripe
3. Pagamento confirmado → Agent Hub:
   a. Cria Tenant central
   b. Cria Subscription
   c. Gera provisioning_token HMAC (TTL 5 min)
   d. POST https://{APP_DOMAIN}/api/v1/integrations/agent-hub/provision
4. {APP_NAME} valida HMAC → {APP_NAME}OnboardingService.create_tenant_with_defaults()
5. {APP_NAME} retorna { app_login_url, owner_invitation_link }
6. Usuario completa Setup Wizard no {APP_NAME}
```

**Padrao do receptor:** estender [backend/apis/v1/itsm_integration.py](../../../backend/apis/v1/itsm_integration.py) ja implementado parcialmente como referencia.

### 6.2 Setup Status

```python
class TenantSetupStatus(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "tenant_setup_status"
    # [ESPECIALIZAR] um boolean por passo do wizard
    step_company_done = Column(Boolean, default=False)
    step_users_done = Column(Boolean, default=False)
    # ...
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
```

### 6.3 Defaults Criados no Onboarding `[ESPECIALIZAR]`

`{APP_NAME}OnboardingService.create_tenant_with_defaults()` cria tudo o que o tenant precisa para comecar a usar a aplicacao no minuto seguinte ao login. Liste os recursos default em uma tabela:

| Recurso | Default |
|---------|---------|
| **Tenant** | Nome, slug, plan_slug, branding |
| **Owner User** | tenant_admin + admin |
| **Company** | Empresa primaria |
| **{Catalogo basico}** | (categorias / templates / etapas iniciais) |
| **{Notificacoes}** | Templates de email pre-aprovados |
| **TenantSetupStatus** | Tudo `false` |
| **Theme** | Skin default |

### 6.4 Criacao Atomica do Tenant (Pseudocodigo)

**Tudo em UMA transacao** — qualquer falha gera rollback completo. Nao pode existir tenant sem owner, owner sem company, etc.

```python
def create_tenant_with_defaults(
    db: Session,
    *,
    company_name: str,
    owner_email: str,
    owner_full_name: str,
    owner_password_hash: Optional[str],
    owner_auth_provider: str,  # "local" | "google" | "linkedin"
    invite_code: Optional[str] = None,
) -> dict:
    try:
        # 0. Validar invite code (se exigido) — consumir so apos sucesso
        if INVITE_CODE_REQUIRED:
            invite = validate_invite_code(db, invite_code)

        # 1. Resolver plano (default: trial)
        plan = db.query(Plan).filter(Plan.slug == "trial").first()

        # 2. Gerar slug unico do tenant
        slug = slugify(company_name)
        slug = ensure_unique_tenant_slug(db, slug)  # sufixar -2, -3 se colisao

        # 3. Criar Tenant (sem CNPJ — fica na Company)
        tenant = Tenant(name=company_name, slug=slug, plan="trial", ...)
        db.add(tenant); db.flush()  # flush para obter ID, NAO commit

        # 4. Subscription trial
        subscription = Subscription(tenant_id=tenant.id, plan_id=plan.id, status="trial", ...)
        db.add(subscription); db.flush()

        # 5. Company default (is_default=true) — CNPJ vazio ate wizard
        company = Company(tenant_id=tenant.id, name=company_name, is_default=True, ...)
        db.add(company); db.flush()

        # 6. User owner (role=owner)
        user = User(tenant_id=tenant.id, email=owner_email, role="owner",
                    is_email_verified=(owner_auth_provider != "local"), ...)
        db.add(user); db.flush()

        # 7. UserCompanyAccess (owner como admin da company default)
        db.add(UserCompanyAccess(tenant_id=tenant.id, user_id=user.id,
                                 company_id=company.id, role="admin"))

        # 8. Theme default + templates + defaults do dominio
        db.add(Theme(tenant_id=tenant.id, config=DEFAULT_THEME_CONFIG, is_default=True))
        create_default_domain_resources(db, tenant.id)  # [ESPECIALIZAR]

        # 9. TenantSetupStatus (wizard pos-signup)
        setup_status = TenantSetupStatus(tenant_id=tenant.id, ...)
        db.add(setup_status)

        # 10. TenantLimit (usa defaults do plano)
        db.add(TenantLimit(tenant_id=tenant.id, is_active=True))

        # 11. Audit log inicial
        log_audit(db, tenant_id=tenant.id, user_id=user.id,
                  action="tenant_created", entity="tenant", entity_id=tenant.id)

        # 12. Consumir invite code (so agora — depois de tudo dar certo)
        if invite_code:
            consume_invite_code(db, invite, consumed_by=user.id)

        db.commit()
        return {"tenant": tenant, "company": company, "user": user, ...}

    except Exception as e:
        db.rollback()
        raise
```

**Pontos criticos:**
- **`db.flush()` (nao commit)** entre passos para obter IDs gerados; commit so no final.
- **Invite code consumido por ultimo** — caso contrario, falha intermediaria queima o codigo.
- **Sem CNPJ no signup**: `Company.cnpj` fica NULL ate o wizard. Pedir CNPJ no signup aumenta abandono.
- **Email de verificacao e assincrono** e fora da transacao — se SMTP cair, a conta ja existe.

### 6.5 OAuth Social (Google / LinkedIn / etc.)

```python
# POST /api/v1/auth/oauth/{provider}
{
  "id_token": "<token do provedor>",
  "company_name": "Empresa SA",
  "invite_code": "ABC123",
  "accept_terms": true
}
```

Fluxo:
1. Verificar `id_token` via biblioteca oficial do provedor.
2. Extrair email, nome do payload.
3. Email ja tem conta? → login. Nao? → `create_tenant_with_defaults` com `auth_provider`, sem senha, `is_email_verified=True`.

### 6.6 Convite de Usuarios Adicionais (Pos-Signup)

Owner/admin convida mais usuarios:

```python
# POST /api/v1/users/invite
{
  "email": "usuario@empresa.com",
  "full_name": "Nome",
  "tenant_role": "editor",
  "company_access": [
    {"company_id": "<uuid>", "company_role": "editor"}
  ]
}
```

Fluxo:
1. Validar que solicitante e `owner` ou `admin` do tenant.
2. Validar que `company_id`s pertencem ao mesmo tenant.
3. Criar `User` com `is_active=False`, sem senha, gerar token de invite (7 dias).
4. Criar `UserCompanyAccess` correspondentes.
5. Enviar email com link `/accept-invite?token=<jwt>`.
6. Convidado abre link, define senha (ou OAuth), ativa conta.
7. Audit log: `user_invited` + `user_invite_accepted`.

### 6.7 Criacao de Companies Adicionais

Owner/admin cria mais Companies dentro do mesmo Tenant:
- `POST /api/v1/companies` — CNPJ **e obrigatorio** aqui (diferente do signup).
- Owner ja tem acesso implicito; outros users precisam de `UserCompanyAccess` explicito.
- Audit log: `company_created`.

### 6.8 Anti-Padroes de Onboarding

1. **Pedir CNPJ no signup** — aumenta abandono; deixar para o wizard.
2. **Entidades em transacoes separadas** — risco de tenant orfao sem owner.
3. **Nao validar slug duplicado** — colisao silenciosa entre tenants.
4. **Email de verificacao sincrono** — se SMTP falhar, signup inteiro falha. Sempre assincrono.
5. **Mensagens que revelam existencia de email** ("este email ja esta cadastrado") — vetor de enumeracao; usar mensagem generica.
6. **Consumir invite code antes do tenant ser criado** — em caso de falha, codigo fica queimado.
7. **Owner sem `is_email_verified` para OAuth** — OAuth garante email verificado; marcar direto.
8. **Wizard sem opcao de pular** — oferecer "pular por enquanto".
9. **Nao registrar consentimento LGPD** (termos, DPA, marketing) com timestamp e versao.
10. **Criar recursos automaticamente** — melhor levar o usuario a tela de criacao no wizard.

### 6.9 Tratamento de Erros de Signup

| Erro | HTTP | Mensagem | Acao |
|------|------|----------|------|
| Email ja existe | 409 | "Nao foi possivel criar conta" (generica) | Nao revelar |
| Senha fraca | 422 | "Senha nao atende requisitos: ..." | Listar regras |
| Invite code invalido | 400 | "Codigo de convite invalido" | — |
| Slug duplicado | — | (interno) | Sufixar `-2`, `-3` automaticamente |
| Falha no meio | 500 | "Erro temporario, tente novamente" | Rollback automatico |

### 6.10 Setup Wizard (Frontend) `[ESPECIALIZAR]`

Liste os passos sequenciais (recomendado: 5 a 8 passos). Exemplo:

1. Empresa (nome, CNPJ, dominio email)
2. Convidar usuarios
3. Configuracao basica do dominio
4. Branding
5. Habilitar agente IA (token Agent Hub)
6. Conclusao

A tabela `tenant_setup_status` rastreia: quais steps foram concluidos, `current_step`, `progress_percent`, `setup_skipped`, `setup_completed`.

---

## 7. Pricing e Billing

### 7.1 Estrategia: Centralizado no Agent Hub

O app **nao** implementa Stripe diretamente. O Agent Hub e a unica fonte de verdade. O app consome via `agn-billing` client (cache Redis 5 min).

```python
# {app_name}/integrations/agent_hub_billing_client.py
class AgentHubBillingClient:
    async def get_subscription(self, tenant_id: str) -> SubscriptionDTO: ...
    async def get_limits(self, tenant_id: str) -> TenantLimitsDTO: ...
    async def get_features(self, tenant_id: str) -> dict: ...
    async def report_usage(self, tenant_id: str, metric: str, value: int) -> None: ...
```

### 7.2 Planos `[ESPECIALIZAR]`

Defina os planos e seus limites no Agent Hub. Exemplo de tabela:

| Plano | Limite quantitativo principal | Usuarios | Storage | API keys | Webhooks | Features |
|-------|------------------------------|----------|---------|----------|----------|----------|
| **Starter** | ... | ... | ... | 0 | 0 | ... |
| **Professional** | ... | ... | ... | ... | ... | ... |
| **Enterprise** | Ilimitado | Ilimitado | Ilimitado | ... | ... | Tudo |

### 7.3 Limites Especificos `[ESPECIALIZAR]`

```python
@dataclass
class {AppName}Limits:
    # quotas quantitativas
    max_{recurso_principal}_per_month: int
    max_users: int
    max_storage_gb: int
    max_api_keys: int
    max_webhook_endpoints: int

    # feature flags
    feature_ai_assistant: bool
    feature_api_gateway: bool
    feature_webhooks: bool
    feature_custom_skins: bool
    feature_advanced_audit: bool
```

### 7.4 Usage Tracking

Eventos `usage_metrics` enviados ao Agent Hub. Liste os eventos relevantes para o dominio.

```python
async def record_{event}(tenant_id: str, ...): ...
```

Agregacao diaria (cron) → emissao mensal para Agent Hub via `report_usage()`.

---

## 8. FSM — Agente Conversacional `[ESPECIALIZAR]`

> **Inclua esta secao apenas se a aplicacao tiver um agente conversacional** (chat IA, auto-atendimento, qualificacao). Aplicacoes puramente CRUD podem omitir.

### 8.1 Arquitetura

Mesmo padrao validado em [backend/services/hr_recruiter_agent/](../../../backend/services/hr_recruiter_agent/) e [backend/services/fsm_agent_registry.py](../../../backend/services/fsm_agent_registry.py).

```
Usuario (Web/WhatsApp/Teams)
    ↓
{APP_NAME} Backend
    ↓
┌────────────────────────────────────────────┐
│  {APP_NAME} FSM                            │
│                                            │
│  GREETING → COLLECT_INPUT → PROCESS → END  │
│                                            │
└────────────────────────────────────────────┘
    ↓ (LLM para gerar texto)
Agent Hub API
```

### 8.2 FSM States `[ESPECIALIZAR]`

```python
class {AppName}State(str, Enum):
    GREETING = "greeting"
    # ... outros states do fluxo
    END = "end"
```

### 8.3 Comportamento

Descreva o fluxo principal: gatilho, transicoes, side flows (handoff humano, retry, etc.), criterios de sucesso.

### 8.4 Registro no FSM Agent Registry

```python
# {app_name}/services/fsm_agent_registry.py
from {app_name}.services.{agent}.agent import {AgentClass}

FSM_AGENT_REGISTRY = {
    "{handler_key}": {AgentClass},
}
```

### 8.5 Metricas de Eficiencia `[ESPECIALIZAR]`

Liste KPIs do agente: taxa de conclusao automatica, tempo medio, NPS pos-interacao, top intents resolvidos.

---

## 9. APIs — Endpoints do Backend `[ESPECIALIZAR]`

> Substitua pelos endpoints reais. Mantenha as 4 secoes "padrao" abaixo (Auth, Setup, Billing, Integration) — sao identicas em todo app.

### 9.1 Auth e Tenant (Padrao)

```
POST   /auth/register              # Apenas via invite (provisionado pelo Agent Hub)
POST   /auth/login                 # email/senha
POST   /auth/refresh               # Refresh JWT
GET    /auth/me                    # Info do usuario atual
POST   /auth/logout
```

### 9.2 Setup / Onboarding (Padrao)

```
GET    /setup/status
POST   /setup/step
POST   /setup/complete
```

### 9.3 Billing (Padrao — proxy para Agent Hub)

```
GET    /billing/subscription
GET    /billing/limits
GET    /billing/features
POST   /billing/usage              # Reporte interno
```

### 9.4 Integracao Agent Hub (Padrao)

```
POST   /api/v1/integrations/agent-hub/provision    # HMAC
POST   /api/v1/integrations/agent-hub/webhook      # Eventos cross-app
```

### 9.5 Endpoints de Dominio `[ESPECIALIZAR]`

Liste por pilar funcional. Use convencoes REST e versionamento `/api/v1/`. Exemplos:

```
# {Pilar 1}
GET    /api/v1/{recurso}
POST   /api/v1/{recurso}
GET    /api/v1/{recurso}/{id}
PUT    /api/v1/{recurso}/{id}
DELETE /api/v1/{recurso}/{id}

# {Pilar 2}
# ...
```

### 9.6 Portal Publico (se aplicavel) `[ESPECIALIZAR]`

```
GET    /portal/{recurso}           # Endpoints sem auth ou com auth simplificada
POST   /portal/{recurso}           # Rate limit agressivo
```

### 9.7 API Gateway Publico (Onda Final) `[ESPECIALIZAR]`

```
ANY    /api/v1/gateway/*           # Autenticado por X-API-Key + scopes
```

---

## 10. Frontend — Estrutura de Paginas `[ESPECIALIZAR]`

### 10.1 Stack

React 19 + Vite 7 + TypeScript 5.9 + Tailwind 3.4 + shadcn/ui + i18next 25 + TanStack Query/Table + React Hook Form + Zod.

### 10.2 Layouts

| Layout | Uso |
|--------|-----|
| **AuthLayout** | Login, registro, refresh |
| **AdminLayout** | tenant_admin, admin |
| **OperationalLayout** | Operacao do dia a dia (agent/recruiter/etc.) |
| **PortalLayout** | Portal publico de usuarios finais |
| **WizardLayout** | Setup inicial |

### 10.3 Rotas `[ESPECIALIZAR]`

Liste rotas agrupadas por layout. Exemplo:

```
/login
/setup/wizard/:step

# Admin
/admin/dashboard
/admin/users
/admin/billing
/admin/settings

# Operacional
/{recurso}/list
/{recurso}/:id
```

### 10.4 Contexts (React)

Reaproveitar de `agn-ui`: `AuthContext`, `ThemeContext`, `CompanyContext`, `TenantViewContext`, `ProtectedRoute`.

### 10.5 i18n

Padrao: pt-BR (default), en-US, es-ES. Namespaces organizados por feature (`common`, `auth`, `dashboard`, `errors`, `validation`, `enums`, + 1 namespace por pilar de dominio).

---

## 11. Deploy e Infraestrutura

### 11.1 Stack Docker Compose Dedicada

`{app_name}-app/deployment/docker-compose.yml` (separado e independente do Agent Hub):

```yaml
version: "3.9"
networks:
  {app_name}-network:
    driver: bridge

volumes:
  {app_name}_pgdata:
  {app_name}_redisdata:
  {app_name}_qdrantdata:    # opcional
  {app_name}_documents:
  {app_name}_uploads:

services:
  postgres-{app_name}:
    image: postgres:16-alpine
    networks: [{app_name}-network]
    volumes: [{app_name}_pgdata:/var/lib/postgresql/data]
    healthcheck: ...

  redis-{app_name}:
    image: redis:7-alpine
    command: redis-server --appendonly yes

  qdrant-{app_name}:        # opcional
    image: qdrant/qdrant:v1.12.4

  migration:
    build: { context: ../backend, dockerfile: ../deployment/backend.Dockerfile }
    command: alembic upgrade head
    depends_on: { postgres-{app_name}: { condition: service_healthy } }

  backend-{app_name}:
    build: { context: ../backend, dockerfile: ../deployment/backend.Dockerfile }
    depends_on:
      migration: { condition: service_completed_successfully }
    environment:
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://redis-{app_name}:6379/0
      - AGENT_HUB_API_URL=https://app.ai-garage.com.br
      - AGENT_HUB_API_KEY=${AGENT_HUB_API_KEY}
      - JWT_SECRET=${JWT_SECRET}
      - STORAGE_BASE_PATH=/data/{app_name}
    volumes:
      - {app_name}_documents:/data/{app_name}
      - {app_name}_uploads:/app/uploads

  frontend-{app_name}:
    build: { context: ../frontend, dockerfile: ../deployment/frontend.Dockerfile }
    ports: ["80:80", "443:443"]
    depends_on: [backend-{app_name}]
```

### 11.2 Nginx Config (Replicar do Agent Hub)

`{app_name}-app/deployment/nginx.conf` espelha [deployment/nginx.conf](../../../deployment/nginx.conf) com:

- Rate limiting por rota
- Security headers
- Gzip compression
- Static asset caching
- WebSocket upgrade para `/ws/*`
- `X-Forwarded-Proto` para o backend reconstruir HTTPS atras de proxy

### 11.3 CI/CD (GitHub Actions)

```yaml
jobs:
  lint:        ruff + mypy
  test:        pytest -m "unit or integration" --cov-fail-under=70
  security:    trivy + gitleaks
  build:       docker build + push
  deploy-staging:
    if: github.ref == 'refs/heads/main'
    - ssh deploy@staging "cd /opt/{app_name} && docker compose pull && docker compose up -d"
```

### 11.4 Infraestrutura Cloud (Terraform)

Mesmo template GCP/AWS do Agent Hub: VPC + Cloud SQL + Memorystore + Cloud Run + Cloud Storage + Artifact Registry + Secret Manager.

### 11.5 Background Jobs (APScheduler)

> **Critico (lessons-learned do Agent Hub):** sempre usar `MemoryJobStore()` (NAO SQLite — container nao-root nao escreve). Jobs sao re-agendados em cada startup (stateless).

```python
# backend/services/scheduler/jobs.py
@scheduler.scheduled_job("interval", minutes=N, id="{job_name}")
def {job_name}(): ...
```

`[ESPECIALIZAR]` Liste os jobs especificos do dominio com periodicidade.

---

## 12. Integracao com Agent Hub (API)

### 12.1 Pontos de Integracao

| Funcionalidade | Direcao | Mecanismo |
|---------------|---------|-----------|
| Provisionamento de tenant | Agent Hub → {APP_NAME} | HMAC token + POST `/api/v1/integrations/agent-hub/provision` |
| Billing/limites/features | {APP_NAME} → Agent Hub | `agn-billing` client + cache Redis 5min |
| LLM (chat, classificacao, geracao) | {APP_NAME} → Agent Hub | `POST /api/v1/external-chat/message` com `X-API-Key` |
| Webhooks de eventos cross-app | {APP_NAME} → Agent Hub | `webhook_deliveries` |
| **NAO via Agent Hub:** | | |
| CRUD de dominio | Local | Postgres do app |
| Upload de anexos | Local | Storage local |
| Busca semantica (se houver) | Local | Qdrant local |

### 12.2 Configuracao do Agente no Agent Hub

```python
# Criado uma vez por tenant via UI ou API
Agente(
    tenant_id=...,
    name="{APP_NAME_HUMAN} Assistant",
    agent_type="ai_assistant",
    type_config={"{handler_key}": True},
    enable_external_api=True,
    enable_rag=False,  # RAG/busca local no app
    system_prompt="""...
    Tarefas:
    - {task_1}: ...
    - {task_2}: ...
    """
)
```

### 12.3 Client SDK

```python
# {app_name}/integrations/agent_hub_client.py
class AgentHubClient:
    def __init__(self, base_url: str, api_key: str): ...

    async def {task_name}(self, ...) -> dict: ...

    async def _post(self, task: str, payload: dict) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base_url}/api/v1/external-chat/message",
                headers={"X-API-Key": self.api_key},
                json={"message": json.dumps(payload), "metadata": {"task": task}},
                timeout=30.0,
            )
            r.raise_for_status()
            return r.json()
```

### 12.4 Resilience

- **Circuit breaker** (tenacity) — 5 falhas consecutivas → abre por 60s
- **Cache de billing** — Redis 5 min, fallback para grace period
- **Fallback de LLM** — categoria default + prioridade media quando offline
- **Trace ID** propagado no header `X-Trace-ID` para correlacao cross-app

---

## 13. Middleware Stack (Ordem de Execucao)

```python
app = FastAPI(...)
app.add_middleware(CORSMiddleware, ...)            # 1. CORS
app.add_middleware(SubscriptionMiddleware, ...)    # 2. Verifica plano via Agent Hub
app.add_middleware(TraceMiddleware)                # 3. X-Trace-ID
app.add_middleware(SlowAPIMiddleware)              # 4. Rate limit

# Ordem no request: SlowAPI → Trace → Subscription → CORS → Handler
```

### 13.1 Rotas Isentas do Subscription Check

```python
EXEMPT_ROUTES = [
    "/health",
    "/auth/",
    "/api/v1/integrations/agent-hub/",
    "/portal/",
    "/docs",
    "/openapi.json",
]
```

---

## 14. Logging e Observabilidade

### 14.1 Structured Logging (structlog)

```python
import structlog
logger = structlog.get_logger()
# Inclui automaticamente: trace_id, tenant_id, user_id, ISO 8601 timestamp,
# service: "{APP_NAME}-backend"
```

### 14.2 Health Check

```python
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "database": check_db(),
        "redis": check_redis(),
        "qdrant": check_qdrant(),  # opcional
        "agent_hub": await check_agent_hub_reachable(),
        "timestamp": datetime.utcnow().isoformat(),
    }
```

### 14.3 Metricas (Prometheus opcional) `[ESPECIALIZAR]`

Padrao de naming: `{app_name}_{recurso}_{acao}_{unit}{labels}`

```
{app_name}_{recurso}_created_total{tenant_id, type}
{app_name}_{recurso}_duration_seconds_bucket{tenant_id, status}
{app_name}_agent_hub_call_seconds_bucket{task, status}
```

---

## 15. Convencoes de Timezone

Replicar do Agent Hub:

| Operacao | Regra |
|----------|-------|
| **Armazenamento** | Sempre UTC (naive datetime) |
| **Input do usuario** | BRT → UTC antes de salvar |
| **Display** | UTC → BRT antes de exibir |
| **Queries** | Comparar com `datetime.utcnow()` |
| **Helpers** | `_brt_to_utc()`, `_to_brazil()`, `_format_brt()`, `_brt_business_hours_to_utc()` |

> Reaproveitar do scheduling agent existente em [backend/services/scheduling_agent/state_machine.py](../../../backend/services/scheduling_agent/state_machine.py).

---

## 16. Repositorio e Estrutura de Diretorios

**Decisao (ADR-005):** Repositorio separado `{app_name}-app/`. Shared libs como Git submodule apontando para `agn-shared` ate evoluir para registry privado.

```
{app_name}-app/
├── backend/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py             # (importa de agn-auth)
│   │   ├── encryption.py
│   │   ├── rate_limiter.py
│   │   ├── trace_middleware.py
│   │   ├── subscription_middleware.py
│   │   ├── circuit_breaker.py
│   │   ├── logger.py
│   │   └── scheduler.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tenant.py               # (importa de agn-core)
│   │   ├── user.py
│   │   ├── company.py
│   │   ├── audit_log.py
│   │   ├── tenant_setup_status.py
│   │   ├── theme.py
│   │   └── {app_name}/             # [ESPECIALIZAR] modelos do dominio
│   ├── schemas/                    # Pydantic
│   ├── services/
│   │   ├── auth_service.py         # (de agn-auth)
│   │   ├── onboarding_service.py
│   │   ├── notification_service.py
│   │   └── {app_name}/             # [ESPECIALIZAR] services do dominio
│   ├── apis/
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── setup.py
│   │       ├── billing.py
│   │       └── {app_name}/         # [ESPECIALIZAR] routers
│   ├── integrations/
│   │   └── agent_hub_client.py
│   ├── migrations/                 # Alembic
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── api/
│   │   └── isolation/              # 1 file por modelo TenantMixin
│   └── scripts/
│       └── seed_{app_name}_platform.py
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── routes/
│   │   ├── layouts/
│   │   ├── components/
│   │   ├── pages/                  # [ESPECIALIZAR]
│   │   ├── contexts/               # (de agn-ui)
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── i18n/
│   └── public/locales/{pt,en,es}/
├── shared/                         # Submodule agn-shared
├── deployment/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   ├── nginx.conf
│   └── DEPLOY.md
├── terraform/
├── .github/workflows/
│   ├── ci.yml
│   └── deploy.yml
├── docs/
│   ├── ARCHITECTURE.md             # Este documento especializado
│   ├── API.md
│   └── runbooks/
├── Makefile
└── README.md
```

---

## 17. Bibliotecas Compartilhadas (Shared Libraries)

### 17.1 Estrategia

Replicar a estrategia do plano HR Recruitment / ITSM. Os pacotes Python + TS sao **os mesmos** — esta refatoracao **usa** os pacotes ja extraidos pelos planos anteriores (ou consolida a extracao se ainda nao foi feita).

### 17.2 Inventario

| Pacote | Conteudo principal |
|--------|--------------------|
| **agn-core** | UUIDMixin, TimestampMixin, TenantMixin, Tenant, User, Company, UserCompanyAccess, database config, BaseSettings |
| **agn-auth** | JWT, password hashing, `get_current_user`, `require_role`, brute force, rate limit presets, encryption (Fernet) |
| **agn-billing** | Plan, Subscription, Invoice models + Stripe client + webhook handlers + usage tracking — **usado em modo cliente** |
| **agn-middleware** | SubscriptionMiddleware, TraceMiddleware, CircuitBreaker, CORS helpers |
| **agn-audit** | AuditLog model + service + structlog config |
| **agn-platform** | InviteCode, PlatformSettings, PlatformWaitlist + servicos |
| **agn-onboarding** | TenantSetupStatus + base service (estendido por `{AppName}OnboardingService`) |
| **agn-ui** (TS) | AuthContext, ThemeContext, CompanyContext, TenantViewContext, ProtectedRoute, httpClient, shadcn/ui base |
| **agn-deploy** | Nginx template, Dockerfile templates, docker-compose base, Terraform modules |

### 17.3 Origens em Agent Hub a Extrair

| Origem | Destino |
|--------|---------|
| [backend/models/base.py](../../../backend/models/base.py) | `agn-core` |
| [backend/core/security.py](../../../backend/core/security.py) | `agn-auth` |
| [backend/services/auth_service.py](../../../backend/services/auth_service.py) | `agn-auth` |
| [backend/services/stripe_service.py](../../../backend/services/stripe_service.py) | `agn-billing` |
| [backend/services/tenant_onboarding_service.py](../../../backend/services/tenant_onboarding_service.py) | `agn-onboarding` (base) |
| [deployment/nginx.conf](../../../deployment/nginx.conf) | `agn-deploy` |
| [deployment/docker-compose.yml](../../../deployment/docker-compose.yml) | `agn-deploy` (template) |

### 17.4 Distribuicao

- **MVP:** Monorepo com `pip install -e ../shared`
- **Curto prazo:** Git submodules
- **Longo prazo:** Pip privado / npm privado

---

## 18. Estrategia de Testes (pytest)

### 18.1 Infraestrutura

- **Unit:** SQLite in-memory (rapido, sem infra)
- **Integration / API:** Postgres docker (compatibilidade real com JSONB, indexes, constraints)
- **CI:** Postgres docker + Redis docker + Qdrant docker (se aplicavel)
- **conftest.py raiz:** fixtures `db`, `client`, `auth_headers_admin`, `auth_headers_{role_operacional}`, `auth_headers_user`

### 18.2 Markers (pytest.ini)

```ini
markers =
    unit: testes unitarios isolados
    integration: testes com banco real
    api: testes de endpoint via TestClient
    service: testes de service layer
    isolation: testes de isolamento cross-tenant (obrigatorio por modelo)
    {app_name}: testes do dominio
    fsm: state machine do agente IA (se houver)
    ai: integracao com Agent Hub
    slow: testes lentos (> 1s)
    regression: bugs ja corrigidos
```

### 18.3 Fixture Central: `{app_name}_world` `[ESPECIALIZAR]`

```python
@pytest.fixture
def {app_name}_world(db) -> dict:
    """Mundo {APP_NAME_HUMAN} completo para testes integrados."""
    tenant = make_tenant(db, name="...")
    owner = make_user(db, tenant_id=tenant.id, role="tenant_admin")
    operator = make_user(db, tenant_id=tenant.id, role="{role_operacional}")
    user = make_user(db, tenant_id=tenant.id, role="user")
    company = make_company(db, tenant_id=tenant.id)
    # ... resto das entidades centrais do dominio
    return {"tenant": tenant, "owner": owner, ...}
```

### 18.4 Testes de Isolamento (Obrigatorios)

Para cada modelo com `TenantMixin` deve existir uma classe `TestXxxIsolation` em `tests/isolation/test_{model}_isolation.py`:

```python
@pytest.mark.isolation
class Test{Entity}Isolation:
    def test_get_{entity}_from_other_tenant_returns_404(self, db, client): ...
    def test_list_{entity}_excludes_other_tenant(self, ...): ...
    def test_update_{entity}_from_other_tenant_returns_404(self, ...): ...
    def test_delete_{entity}_from_other_tenant_returns_404(self, ...): ...
```

CI bloqueia merge se faltarem testes de isolamento para um novo modelo.

### 18.5 Coverage Targets

- Servicos: ≥ 80%
- Total: ≥ 70%
- Modelos com TenantMixin: 100% cobertos por isolation tests

### 18.6 Mocks

```python
@pytest.fixture
def mock_agent_hub_client(monkeypatch):
    client = AsyncMock(spec=AgentHubClient)
    client.{task}.return_value = {...}
    monkeypatch.setattr("{app_name}.integrations.agent_hub_client.get_client", lambda: client)
    return client
```

---

## 19. Internacionalizacao (i18n)

### 19.1 Sistema de Idiomas

3 idiomas (pt-BR padrao, en-US, es-ES). Numero de namespaces depende do dominio. Padrao minimo:

```
public/locales/
├── pt/   (padrao)
│   ├── auth.json
│   ├── common.json
│   ├── dashboard.json
│   ├── enums.json
│   ├── errors.json
│   ├── navigation.json
│   ├── settings.json
│   ├── validation.json
│   └── {namespaces do dominio}.json
├── en/
└── es/
```

### 19.2 Backend i18n

Mensagens do sistema (notifications, e-mail templates, FSM responses) tambem precisam de i18n. Reaproveitar pattern de [backend/services/i18n_message_service.py](../../../backend/services/i18n_message_service.py).

### 19.3 Resolucao Hierarquica de Mensagens

`Tenant.preferences.language` > `Company.preferences.language` > `User.language` > default `pt-BR`.

---

## 20. Backup e Restore

### 20.1 Sistema

Replicar pattern do Agent Hub:
- **Daily:** dump automatico (cron 03:00 BRT) → storage cifrado
- **Monthly:** snapshot completo retencao 12 meses
- **On-demand:** botao admin → gera dump sob demanda
- **Conteudo:** Postgres dump + collections Qdrant (se aplicavel) + arquivos `/data/{app_name}/`
- **Restore:** preview com diff de schema/quantidade de registros antes de aplicar

### 20.2 Tabelas

```python
class BackupJob(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "backup_jobs"
    type = Column(String(20))      # daily, monthly, on_demand
    status = Column(String(20))    # pending, running, completed, failed
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    storage_path = Column(String(500))
    size_bytes = Column(BigInteger)
    error = Column(Text)
```

---

## 21. Busca Semantica (Opcional) `[ESPECIALIZAR]`

> **Inclua esta secao apenas se a aplicacao precisar de busca semantica** (KB, biblioteca de documentos, matching CV, etc.). Caso contrario, remova.

### 21.1 Qdrant Local

**Decisao (ADR-007):** Qdrant local no proprio app para latencia <100ms e conformidade LGPD.

```python
collection_name = f"{app_name}_{tenant_id}_{namespace}"
qdrant.create_collection(
    collection_name=collection_name,
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)
```

### 21.2 Fluxo de Indexacao

```
1. Usuario publica/cria item indexavel
2. EmbeddingService chunkifica texto (overlap 100, chunks 800 tokens)
3. Para cada chunk: gera embedding (text-embedding-3-small via Agent Hub OU OpenAI direto)
4. Insere ponto em Qdrant + cria metadata local
5. Atualiza tsvector Postgres (GIN index)
```

### 21.3 Busca Hibrida

```python
async def hybrid_search(tenant_id: str, query: str, top_k: int = 10) -> list:
    # 1. Busca vetorial (Qdrant)
    # 2. Busca fulltext (Postgres tsvector)
    # 3. Reciprocal Rank Fusion (RRF)
    # 4. Re-ranking opcional via Agent Hub LLM (se confidence baixa)
    ...
```

---

## 22. Sistema de Notificacoes

### 22.1 Canais

- **E-mail** (SMTP proprio, ADR-008 — nao compartilha com Agent Hub)
- **In-app** (`notifications` table + WebSocket)
- **Webhook** (onda 4)
- **Slack/Teams** (onda 4)
- **WhatsApp** (opcional — via Twilio)

### 22.2 Templates Pre-configurados no Onboarding `[ESPECIALIZAR]`

| Slug | Trigger | Canal |
|------|---------|-------|
| `welcome` | Usuario criado | email |
| `password_reset` | Reset senha | email |
| `{evento_dominio_1}` | ... | ... |
| `{evento_dominio_2}` | ... | ... |

### 22.3 Variaveis de Templates `[ESPECIALIZAR]`

`{{user.name}}, {{tenant.name}}, {{company.name}}, ...` + variaveis especificas do dominio.

---

## 23. Makefile

```makefile
# === Production ===
prod-up:        docker compose -f deployment/docker-compose.yml up -d
prod-down:      docker compose -f deployment/docker-compose.yml down
prod-logs:      docker compose -f deployment/docker-compose.yml logs -f
prod-rebuild:   docker compose -f deployment/docker-compose.yml up --build -d

# === Development ===
dev:            docker compose -f deployment/docker-compose.dev.yml up -d
dev-backend:    cd backend && uvicorn main:app --reload --port 8000
dev-frontend:   cd frontend && npm run dev

# === Database ===
migrate:        cd backend && alembic upgrade head
migrate-down:   cd backend && alembic downgrade -1
migration:      cd backend && alembic revision --autogenerate -m "$(name)"
seed:           cd backend && python scripts/seed_{app_name}_platform.py

# === Testing ===
test:           cd backend && pytest
test-unit:      cd backend && pytest -m unit
test-integration: cd backend && pytest -m integration
test-isolation: cd backend && pytest -m isolation
test-cov:       cd backend && pytest --cov=. --cov-report=html

# === Quality ===
lint:           cd backend && ruff check . && cd ../frontend && npm run lint
typecheck:      cd backend && mypy .
format:         cd backend && ruff format .
security:       trivy fs . && gitleaks detect

# === Utilities ===
backup:         ./scripts/backup.sh
restore:        ./scripts/restore.sh $(file)
```

---

## 24. Configuracao de Ambiente (Settings) `[ESPECIALIZAR parcialmente]`

### 24.1 Variaveis de Ambiente

```bash
# === App ===
APP_ENV=production
APP_NAME={app_name}
VERSION=1.0.0
DEBUG=false
TIMEZONE=America/Sao_Paulo

# === Server ===
HOST=0.0.0.0
PORT=8000
WORKERS=4

# === Database ===
DATABASE_URL=postgresql://{app_name}:secret@postgres-{app_name}:5432/{app_name}
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# === Redis ===
REDIS_URL=redis://redis-{app_name}:6379/0
REDIS_POOL_SIZE=10

# === Qdrant (opcional) ===
QDRANT_URL=http://qdrant-{app_name}:6333
QDRANT_API_KEY=

# === JWT ===
JWT_SECRET=...
JWT_ALGORITHM=HS256
JWT_EXPIRES_MIN=60
REFRESH_TOKEN_EXPIRES_DAYS=30

# === Encryption (Fernet) ===
FERNET_KEY=...

# === Agent Hub Integration ===
AGENT_HUB_API_URL=https://app.ai-garage.com.br
AGENT_HUB_API_KEY=agk_xxxxxxxxxxxxxxxxxxxx
AGENT_HUB_HMAC_SECRET=...
AGENT_HUB_CIRCUIT_BREAKER_THRESHOLD=5
AGENT_HUB_CIRCUIT_BREAKER_TIMEOUT=60
AGENT_HUB_CACHE_TTL_SECONDS=300

# === Storage ===
STORAGE_BASE_PATH=/data/{app_name}
MAX_UPLOAD_SIZE_MB=25

# === SMTP ===
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=...
SMTP_FROM=noreply@{app_domain}
SMTP_FROM_NAME="{APP_NAME_HUMAN}"

# === Twilio (opcional) ===
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=

# === Embeddings (opcional, alternativa direta a Agent Hub) ===
OPENAI_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536

# === Rate Limiting ===
RATE_LIMIT_AUTH=5/second
RATE_LIMIT_API_GENERAL=20/second
RATE_LIMIT_CHAT=10/second
RATE_LIMIT_PORTAL=3/second
RATE_LIMIT_GATEWAY_DEFAULT=100/minute

# === CORS ===
CORS_ORIGINS=https://{app_domain},https://app.ai-garage.com.br

# === Observability ===
LOG_LEVEL=INFO
LOG_FORMAT=json
TRACE_HEADER=X-Trace-ID
PROMETHEUS_ENABLED=true

# === Backup ===
BACKUP_BASE_PATH=/backups
BACKUP_RETENTION_DAYS=30
BACKUP_ENCRYPTION_KEY=...

# === Frontend (build-time) ===
VITE_API_URL=https://{app_domain}/api
VITE_WS_URL=wss://{app_domain}/ws
VITE_AGENT_HUB_PORTAL_URL=https://app.ai-garage.com.br

# === Variaveis especificas do dominio [ESPECIALIZAR] ===
# ...
```

---

## 25. CORS e WebSocket

### 25.1 CORS

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-ID"],
)

# IMPORTANTE: Exception handlers DEVEM incluir CORS headers
# para que erros 4xx/5xx tambem tenham headers corretos.
```

### 25.2 WebSocket `[ESPECIALIZAR]`

```python
@app.websocket("/ws/{namespace}/{id}/...")
async def {handler}(ws: WebSocket, ...): ...
```

### 25.3 Nginx WebSocket Config

```nginx
location /ws/ {
    proxy_pass http://backend-{app_name}:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}
```

---

## 26. Seed de Dados da Plataforma

### 26.1 Script: `seed_{app_name}_platform.py` `[ESPECIALIZAR]`

Idempotente, executado uma vez por ambiente:

```python
def seed_platform():
    seed_languages()                  # pt-BR, en-US, es-ES
    seed_role_definitions()           # Roles RBAC do app
    seed_default_notification_templates()
    seed_default_ai_agent_credentials()  # Vazio, configurado por tenant
    seed_platform_settings()          # Versionamento
    # ... seeds especificos do dominio
```

### 26.2 Versionamento

`PlatformSettings.seed_version` controla execucao incremental: cada `seed_*()` verifica se ja rodou na versao atual antes de executar.

---

## 27. Checklist de Implementacao

> Reaproveite as fases abaixo. Adapte as duracoes ao porte do app.

### Fase 1: Fundacao
- [ ] Criar repositorio `{app_name}-app`
- [ ] Consolidar/extrair shared libs (`agn-core`, `agn-auth`, `agn-billing`, `agn-middleware`, `agn-audit`, `agn-platform`, `agn-onboarding`)
- [ ] Setup FastAPI + SQLAlchemy + Alembic
- [ ] Modelos base (Tenant, User, Company) via `agn-core`
- [ ] Auth (register, login, JWT, RBAC) via `agn-auth`
- [ ] Middleware stack (CORS, Trace, RateLimit, Subscription)
- [ ] Docker Compose (postgres, redis, [qdrant], backend)
- [ ] Health check + structured logging
- [ ] pytest + conftest + fixtures base + isolation tests scaffolding
- [ ] CI pipeline (GitHub Actions: lint, typecheck, test, security)
- [ ] Makefile

### Fase 2: Onboarding e Plataforma
- [ ] Receptor `/api/v1/integrations/agent-hub/provision` + validacao HMAC
- [ ] `{AppName}OnboardingService.create_tenant_with_defaults()`
- [ ] Setup wizard backend
- [ ] `agn-billing` client em modo cliente
- [ ] Subscription middleware lendo do Agent Hub via cache
- [ ] Seed platform data
- [ ] Backup/Restore service
- [ ] i18n backend
- [ ] Settings completas + `.env.production.example`
- [ ] Testes: onboarding, billing client, seed, isolation base

### Fase 3: Dominio MVP-1 `[ESPECIALIZAR]`
- [ ] Models do dominio (listar todos)
- [ ] Services do dominio (listar todos)
- [ ] APIs MVP-1 (listar)
- [ ] FSM agent (se aplicavel)
- [ ] Schedulers (listar jobs)
- [ ] Sistema de notificacoes
- [ ] Storage de anexos com path por tenant
- [ ] Testes: world fixture, services, APIs, **isolation tests para todos os modelos**
- [ ] Coverage: ≥ 80% services MVP-1

### Fase 4: Frontend MVP-1 `[ESPECIALIZAR]`
- [ ] React 19 + Vite + Tailwind + shadcn/ui + i18next setup
- [ ] Auth flow (login, refresh, ProtectedRoute)
- [ ] Layouts
- [ ] Dashboards
- [ ] CRUD telas do dominio
- [ ] Setup Wizard frontend
- [ ] WebSocket para realtime
- [ ] i18n completo nos namespaces

### Fase 5+: Ondas seguintes `[ESPECIALIZAR]`
- [ ] Funcionalidades MVP-2
- [ ] Funcionalidades Onda 3 (engajamento, customizacao)
- [ ] Funcionalidades Onda 4 (API publica, webhooks, auditoria)

### Fase Final: Polish, LGPD e Deploy
- [ ] Refinamento i18n (en/es completo)
- [ ] LGPD: export, delete, consent, audit
- [ ] Nginx config + security headers + rate limit final
- [ ] Frontend Dockerfile + runtime config injection
- [ ] CI/CD completo (deploy staging + producao)
- [ ] Terraform GCP/AWS
- [ ] E2E tests (Playwright opcional)
- [ ] Coverage final ≥ 80% services / ≥ 70% total
- [ ] Documentacao runbooks
- [ ] Dry-run de migracao (importar dataset real do legado em staging)
- [ ] Deploy producao

---

## 28. Decisoes Arquiteturais (ADRs)

> ADRs 001-012 sao **herdadas** dos planos HR Recruitment / ITSM. Nao precisam ser re-justificadas — apenas referenciadas. ADRs novas devem ser numeradas a partir de 013.

### ADR-001: Aplicacao Separada vs Modulo no Agent Hub
- **Decisao:** Aplicacao separada (repositorio, banco, deploy, dominio).
- **Razao:** Reducao de blast-radius, ciclo de release independente, dominio funcional distinto.

### ADR-002: Shared Libraries vs Copia de Codigo
- **Decisao:** Shared libraries (`agn-*`).
- **Razao:** Evita drift entre implementacoes, facilita bug fixes globais.

### ADR-003: IA via API do Agent Hub vs LLM Direto
- **Decisao:** Hibrido — Agent Hub para LLM, processamento local para resto.
- **Razao:** Reusa LLM gateway, mantem latencia baixa em dados sensiveis.

### ADR-004: TenantMixin vs Schema-per-Tenant vs DB-per-Tenant
- **Decisao:** TenantMixin (row-level) com filtragem em service layer.
- **Razao:** Validado em producao, custo/isolamento adequado.

### ADR-005: Monorepo vs Multi-repo
- **Decisao:** Multi-repo. Shared libs como submodule.
- **Razao:** Deploy independente, reducao de impacto de mudancas.

### ADR-006: SQLite in-memory para testes vs PostgreSQL de teste
- **Decisao:** SQLite in-memory para unit, Postgres docker para integration/CI.
- **Razao:** Velocidade nos unit tests + compatibilidade real no CI.

### ADR-007: Qdrant local vs via API do Agent Hub (quando ha busca semantica)
- **Decisao:** Qdrant local no proprio app.
- **Razao:** Latencia <100ms, dados sensiveis nao trafegam entre apps (LGPD).

### ADR-008: Email provider proprio vs compartilhado
- **Decisao:** SMTP/SendGrid proprio do app.
- **Razao:** Volume distinto, dominio de envio proprio, conformidade SPF/DKIM.

### ADR-009: JWT proprio vs SSO Federado com Agent Hub
- **Decisao:** App emite seu proprio JWT apos provisioning HMAC.
- **Razao:** Independencia de runtime, menor acoplamento de release, auditoria local.

### ADR-010: Substituicao de RLS por Service Layer
- **Decisao:** Filtragem por tenant_id no Python service layer + isolation tests obrigatorios.
- **Razao:** Padrao validado, simplicidade operacional, testavel em CI.

### ADR-011: Migracao em Ondas
- **Decisao:** MVP-1 → MVP-2 → Ondas N+.
- **Razao:** Time-to-value rapido, reducao de risco, foco da equipe.

### ADR-012: Edge Functions / Serverless → Servicos Python + APScheduler
- **Decisao:** Toda funcao serverless do legado vira service Python comum + jobs APScheduler para os recorrentes.
- **Razao:** Padrao unico (todo backend em Python), sem cold-start, tracing unificado.

### ADR-013: RLS Habilitado vs Desabilitado `[DECIDIR POR APP]`
- **Opcao A (ITSM):** NAO usar RLS — filtragem apenas no service layer + isolation tests obrigatorios. Simplicidade operacional, evita sincronizar policies em cada migration.
- **Opcao B (RH/apps com dados LGPD regulados):** RLS habilitado como segunda barreira. Necessario quando dados de atores externos (candidatos, pacientes) sao sensiveis e regulados.
- **Registre a decisao** aqui com justificativa.

### ADR-014+ `[ESPECIALIZAR]`
- Registre aqui ADRs especificas do app (decisoes que se afastem do padrao ou novas escolhas tecnologicas).

---

## 29. Migracao de Banco de Dados para PostgreSQL

Esta secao orienta a migracao do banco legado (Supabase/PostgreSQL com RLS, Firebase/Firestore, MySQL, MongoDB, SQLite, etc.) para o PostgreSQL padrao da plataforma com SQLAlchemy + Alembic.

### 29.1 Estrategia Geral

| Etapa | Acao | Ferramenta |
|-------|------|-----------|
| 1. **Inventario** | Levantar todas as tabelas/collections, colunas, tipos, constraints, indices, triggers, views, functions, RLS policies | `pg_dump --schema-only`, Supabase Dashboard, Firebase Console |
| 2. **Classificacao** | Classificar cada tabela em: migrar (dominio), shared lib (agn-core), nao migrar (agent-hub), descartavel | Apendice A deste doc |
| 3. **Mapeamento de Tipos** | Converter tipos do legado para SQLAlchemy (ver §29.2) | Tabela de equivalencia |
| 4. **Modelagem SQLAlchemy** | Escrever modelos Python seguindo convencoes do §3 | `backend/models/{app_name}/` |
| 5. **Migration Alembic** | Gerar migrations `alembic revision --autogenerate` | Alembic |
| 6. **Seed** | Script idempotente para dados iniciais da plataforma | `scripts/seed_{app_name}_platform.py` |
| 7. **Migracao de Dados** | Script ETL para mover dados do legado para o novo banco | `scripts/migrate_legacy_data.py` |
| 8. **Validacao** | Comparar contagens, checksums, testes de integridade | pytest + queries de validacao |

### 29.2 Mapeamento de Tipos: Legado → SQLAlchemy/PostgreSQL

#### Supabase/PostgreSQL → SQLAlchemy

| Supabase / PostgreSQL | SQLAlchemy | Observacoes |
|-----------------------|------------|-------------|
| `uuid` | `String(36)` | Padrao da plataforma: UUID como string, nao tipo nativo `UUID` |
| `text` | `Text` | Texto longo sem limite |
| `varchar(N)` | `String(N)` | |
| `integer` / `bigint` | `Integer` / `BigInteger` | |
| `numeric(P,S)` | `Numeric(P,S)` | Valores monetarios, percentuais |
| `boolean` | `Boolean` | |
| `timestamp with time zone` | `DateTime` | **Armazenar como UTC naive** (sem timezone). Converter BRT→UTC antes de salvar |
| `date` | `Date` | |
| `jsonb` | `JSON` | PostgreSQL usa `JSONB` automaticamente. Aceita dicts/lists Python direto |
| `text[]` | `JSON` | Arrays viram `JSON` (compatibilidade SQLite para testes) |
| `bytea` | `LargeBinary` | Campos criptografados (Fernet) |
| `tsvector` | — | Gerenciado via `func.to_tsvector()` em queries, nao como coluna de modelo |
| `serial` / `bigserial` | Nao usar | UUIDs via `UUIDMixin`, nao auto-increment |

#### Firebase/Firestore → SQLAlchemy

| Firestore | SQLAlchemy | Observacoes |
|-----------|------------|-------------|
| Document ID | `String(36)` via `UUIDMixin` | Gerar novo UUID, nao reutilizar IDs do Firestore |
| `string` | `String(N)` ou `Text` | Definir tamanho maximo |
| `number` (int) | `Integer` | |
| `number` (float) | `Numeric(P,S)` | Nao usar `Float` para valores monetarios |
| `boolean` | `Boolean` | |
| `timestamp` | `DateTime` | Converter para UTC naive |
| `map` (objeto) | `JSON` | |
| `array` | `JSON` | |
| `reference` | `String(36)` + `ForeignKey` | Converter referencia em FK explicita |
| Subcollection | Tabela separada com FK | Desnormalizar subcollections em tabelas filhas |
| Security Rules | Service layer + RLS (opcional) | Nao ha equivalente direto; regras viram logica Python |

#### MySQL → SQLAlchemy

| MySQL | SQLAlchemy | Observacoes |
|-------|------------|-------------|
| `int AUTO_INCREMENT` | `String(36)` via `UUIDMixin` | Migrar para UUIDs |
| `varchar(N)` | `String(N)` | |
| `longtext` | `Text` | |
| `datetime` | `DateTime` | Converter timezone para UTC naive |
| `json` | `JSON` | Nativo no PostgreSQL (JSONB) |
| `enum('a','b','c')` | `String(30)` | **NAO** usar ENUM nativo — dificulta migrations |
| `tinyint(1)` | `Boolean` | |
| `decimal(P,S)` | `Numeric(P,S)` | |

#### MongoDB → SQLAlchemy

| MongoDB | SQLAlchemy | Observacoes |
|---------|------------|-------------|
| `_id` (ObjectId) | `String(36)` via `UUIDMixin` | Gerar novo UUID |
| Embedded document | `JSON` ou tabela separada | Avaliar: se tem queries frequentes, normalizar em tabela |
| Array of references | Tabela N:N | Criar tabela associativa |
| Collection | Tabela | 1 collection = 1 tabela (geralmente) |
| Schema-less fields | `JSON` column `custom_fields` | Para dados dinamicos; campos frequentes viram colunas |
| `$lookup` (join) | `relationship()` + `ForeignKey` | Normalizar relacoes |

### 29.3 Eliminacao de Mecanismos Legados

| Mecanismo Legado | Substituicao | Onde |
|------------------|-------------|------|
| **RLS Policies (Supabase)** | Filtragem `tenant_id` no service layer + RLS opcional (§2.6) | Service + migration |
| **`SECURITY DEFINER` functions** | Dependencies FastAPI (`get_current_tenant_id`, `require_role`) | `core/security.py` |
| **Triggers de audit** | `AuditLog` service explicito (mais controlavel) | `services/audit_service.py` |
| **Triggers de default values** | `default=` no modelo SQLAlchemy ou no `OnboardingService` | Models + onboarding |
| **Views materializadas** | Queries com cache Redis ou tabelas de agregacao (cron) | Services + scheduler |
| **Edge Functions (Deno/Node)** | Services Python + APScheduler jobs (ver Apendice B) | `services/` + `scheduler/` |
| **Supabase Realtime** | WebSocket Starlette | `apis/v1/websocket*.py` |
| **Supabase Storage** | Filesystem local `/data/{app_name}/` ou S3 | `services/storage_service.py` |
| **Supabase Auth** | JWT proprio (`agn-auth`) | `core/security.py` |
| **Firebase Auth** | JWT proprio (`agn-auth`) | `core/security.py` |
| **Firebase Cloud Functions** | Services Python + APScheduler jobs | `services/` |
| **Firebase Firestore Security Rules** | Service layer + RLS opcional | Service + migration |
| **pgvector** | Qdrant local (§21) | `services/embedding_service.py` |

### 29.4 Script de Migracao de Dados (ETL)

```python
# scripts/migrate_legacy_data.py
"""
Migra dados do banco legado para o novo PostgreSQL.
Executar em staging ANTES de producao. Idempotente (re-executavel).
"""

def migrate():
    # 1. Conectar ao banco legado (read-only)
    legacy_db = connect_legacy()

    # 2. Conectar ao novo banco
    new_db = get_session()

    # 3. Migrar por onda (MVP-1 primeiro)
    with new_db.begin():
        # a) Tenants — converter "empresas 1:1" em Tenant + Company
        migrate_tenants_and_companies(legacy_db, new_db)

        # b) Users — preservar emails, gerar novos UUIDs, mapear roles
        migrate_users(legacy_db, new_db)

        # c) Dados de dominio — preservar relacoes, converter tipos
        migrate_domain_data(legacy_db, new_db)

        # d) Atores externos — deduplicar se necessario
        migrate_external_actors(legacy_db, new_db)

    # 4. Validar
    validate_migration(legacy_db, new_db)

def validate_migration(legacy_db, new_db):
    """Compara contagens e checksums entre bancos."""
    for table in MIGRATION_TABLES:
        legacy_count = legacy_db.execute(f"SELECT count(*) FROM {table}").scalar()
        new_count = new_db.query(func.count(Model.id)).scalar()
        assert new_count == legacy_count, f"Mismatch in {table}: {legacy_count} vs {new_count}"
```

### 29.5 Plano de Migracao de Dados (Checklist)

- [ ] **Inventariar** todas as tabelas/collections do legado com contagens
- [ ] **Classificar** em: migrar / shared lib / nao migrar / descartar
- [ ] **Mapear IDs**: decidir se reutiliza IDs antigos ou gera novos UUIDs (recomendado: novos UUIDs + tabela de mapeamento `legacy_id_map`)
- [ ] **Converter hierarchy**: se o legado tinha `Empresa 1:1 Tenant`, converter para `1 Tenant + N Companies`
- [ ] **Deduplicar atores externos**: se existiam em "tenants" diferentes do mesmo cliente, consolidar
- [ ] **Converter tipos** conforme §29.2
- [ ] **Converter timezones**: todo `timestamp with time zone` → UTC naive
- [ ] **Converter ENUMs**: `ENUM` PostgreSQL ou MySQL → `String(30)` com validacao Pydantic
- [ ] **Converter arrays**: `text[]`, `integer[]` → `JSON`
- [ ] **Converter campos criptografados**: re-criptografar com Fernet da nova plataforma
- [ ] **Recriar indices compostos** com `tenant_id` como primeira coluna
- [ ] **Script de migracao** idempotente e testado em staging
- [ ] **Validacao**: contagens, checksums, queries de sanidade, testes de integridade referencial
- [ ] **Plano LGPD de migracao**: comunicar atores externos sobre mudanca de controlador (se aplicavel), consolidar consentimentos
- [ ] **Dry-run completo** em staging com dataset real antes de producao
- [ ] **Rollback plan**: manter banco legado read-only por 30 dias apos migracao

### 29.6 Migration Alembic — Boas Praticas

```python
# backend/migrations/versions/001_initial_schema.py
"""Primeiro schema completo da aplicacao."""

def upgrade():
    # Criar tabelas na ordem de dependencia (FKs)
    op.create_table("tenants", ...)
    op.create_table("companies", ...)
    op.create_table("users", ...)
    op.create_table("user_company_access", ...)
    # ... tabelas de dominio

    # Indices compostos com tenant_id
    op.create_index("ix_{table}_tenant_status", "{table}", ["tenant_id", "status"])

    # RLS (se habilitado — ver ADR-013)
    # op.execute("ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    # op.execute("ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    # op.execute("CREATE POLICY tenant_isolation_{table} ON {table} ...")

def downgrade():
    # Reverter na ordem inversa
    ...
```

**Regras de migration:**
- Numerar sequencialmente: `001_`, `002_`, etc.
- Uma migration por feature/grupo logico (nao uma por tabela)
- Sempre incluir `downgrade()` funcional
- Testar `upgrade` + `downgrade` + `upgrade` (roundtrip) em CI
- **NUNCA** usar `ENUM` nativo do PostgreSQL — dificulta migrations futuras

---

## Apendice A: Mapeamento de Tabelas Legado → SQLAlchemy `[ESPECIALIZAR]`

> Cobertura **completa** das tabelas do legado. Coluna **Onda** indica em qual fase a tabela e introduzida. Coluna **Origem** indica onde o modelo vive: `{app_name}` (modelos do dominio), `agn-core` (shared lib base), `agent-hub` (consumido via API, nao replicado).

### A.1 {Pilar 1}

| Tabela Legado | Modelo SQLAlchemy | Onda | Origem | Observacoes |
|---------------|-------------------|------|--------|-------------|
| ... | ... | MVP-1 | {app_name} | ... |

### A.2 {Pilar 2}

| Tabela Legado | Modelo SQLAlchemy | Onda | Origem | Observacoes |
|---------------|-------------------|------|--------|-------------|
| ... | ... | MVP-1 | {app_name} | ... |

### A.N: Organizacional / Multi-Tenant (Padrao)

| Tabela Legado | Modelo SQLAlchemy | Onda | Origem | Observacoes |
|---------------|-------------------|------|--------|-------------|
| `tenants` | `Tenant` | Fase 1 | agn-core | Replicado da shared lib |
| `companies` | `Company` | Fase 1 | agn-core | |
| `profiles` / `users` | `User` | Fase 1 | agn-core | Mesclado em User |
| `user_roles` | `UserRole` | Fase 1 | agn-core | NUNCA em users |
| `user_tenants` | `UserTenant` | Fase 1 | agn-core | N:N |
| `user_companies` | `UserCompanyAccess` | Fase 1 | agn-core | N:N |
| `role_definitions` | `RoleDefinition` | Fase 1 | agn-core | Seed no onboarding |

### A.N+1: SaaS e Comercial (NAO migrar — consumir via Agent Hub)

| Tabela Legado | Acao | Origem | Observacoes |
|---------------|------|--------|-------------|
| `subscription_plans` | NAO migrar | agent-hub | Consumir via `agn-billing` client |
| `tenant_subscriptions` | NAO migrar | agent-hub | |
| `usage_metrics` | NAO migrar | agent-hub | App emite eventos via `report_usage()` |
| `invite_codes` | NAO migrar | agent-hub | Portal de signup central |
| `invitations` | NAO migrar | agent-hub | |
| `provisioning_tokens_used` | NAO migrar | agent-hub | Anti-replay do HMAC token |

> **Observacao final do Apendice A:** se durante a Fase 1 forem identificadas tabelas adicionais ao introspectar o schema real do legado, essas devem ser adicionadas a este apendice via PR contra este documento, classificadas em onda apropriada.

---

## Apendice B: Funcoes / Jobs Legado → Servicos Python `[ESPECIALIZAR]`

> Mapeamento completo das edge functions / cloud functions / cron jobs do legado para servicos Python equivalentes. Coluna **Mecanismo** indica como sera implementado: endpoint REST, WebSocket, APScheduler job, webhook receiver.

| Funcao Legado | Auth? | Servico Python equivalente | Mecanismo | Onda |
|---------------|-------|----------------------------|-----------|------|
| `{nome_legado}` | sim/nao | `services/{nome}.py` | endpoint / job interval N / WS | MVP-1 |
| ... | ... | ... | ... | ... |

> **Total:** N funcoes mapeadas. M nao sao migradas porque pertencem ao dominio de billing/onboarding centralizado no Agent Hub.

---

*Documento gerado em 2026-04-09. Template derivado de ARCHITECTURE_ITSM.md v1.0. Sujeito a revisoes a cada novo refactor que descobrir lacunas no template. Mudancas materiais devem ser registradas como ADRs adicionais.*
