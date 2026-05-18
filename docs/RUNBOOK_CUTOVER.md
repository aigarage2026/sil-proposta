# Runbook de Cutover — PropostAI (Onda 7)

**Objetivo:** sair do monorepo atual (`propostai` contendo backend +
frontend + legacy) para um repositório dedicado `github.com/ai-garage/propostai-app`,
com DNS apontando para Cloud Run e smoke E2E em sandbox por 7 dias antes
do go-live.

Este runbook complementa [`RUNBOOK_ROLLBACK.md`](RUNBOOK_ROLLBACK.md) —
o de rollback cobre regressões pós-deploy; este aqui cobre a *transição*.

## 0. Pré-condições

Marque cada item antes de iniciar:

- [ ] Ondas 0–5 ✅ DONE (suite de testes verde, `MIGRATION_PLAN.md §5.1`).
- [ ] Onda 6 ✅ — frontend mountado em `agn-portal` sob `/propostai/*` com
      `agn-ui.AuthContext` funcionando ponta a ponta no Portal SPA.
- [ ] Repositório destino `github.com/ai-garage/propostai-app` criado e
      vazio (sem commit inicial — o split traz o histórico).
- [ ] Cloud Run em ambiente `stg` recebendo deploys via `.github/workflows/deploy.yml`
      há pelo menos uma semana sem incidente.
- [ ] D3 (Postgres compartilhado) provisionado e migração rodada com sucesso.
- [ ] Plano de comunicação alinhado: product owner + tech lead do Portal +
      um arquiteto SAP de plantão da Direto ao Ponto.
- [ ] Janela de manutenção combinada (sugestão: 2h fora do horário comercial).

## 1. Subtree split — extração do `propostai-app`

```bash
# A partir do repo monorepo atual, na branch main já com Ondas 0–6 mergeadas:
cd /path/to/monorepo
git checkout main
git pull --ff-only origin main

# Cria uma branch local com APENAS o histórico de propostai-app/:
git subtree split --prefix=propostai-app -b export/propostai-app

# Adiciona o remote do repo destino e empurra:
git remote add propostai-destination git@github.com:ai-garage/propostai-app.git
git push propostai-destination export/propostai-app:main
```

**Validações pós-split:**

```bash
# Clona o repo novo num diretório separado e roda CI local:
git clone git@github.com:ai-garage/propostai-app.git /tmp/propostai-fresh
cd /tmp/propostai-fresh/backend
pip install -e ".[dev]"
ruff check . && pytest -q
# Esperado: ruff clean, 196+ tests green.
```

Se algum import estourar com `ModuleNotFoundError`, é porque um arquivo do
backend ainda referenciava o monorepo. Voltar, corrigir no monorepo, rebatchar
o split.

## 2. Limpeza do monorepo

Após o repo destino estar verde:

```bash
cd /path/to/monorepo
git checkout -b chore/remove-propostai-app
# Remove o subprojeto, o legacy archive e os docs já replicados:
git rm -r propostai-app/
git rm -r legacy/sil-proposta-monolith/   # historical archive — kept old name
# docs/ARCHITECTURE_PORTAL_SAAS_v3.md fica no monorepo — é guia da plataforma.
# Marca o ponto:
git commit -m "chore: split propostai-app to its own repo"
git push origin chore/remove-propostai-app
# Abrir PR de limpeza no monorepo, mergear após smoke do repo novo (§5).
```

## 3. CI/CD no repo novo

O workflow `ci.yml` continua igual — só ajustar paths se necessário (os
nossos já usavam paths relativos a `propostai-app/`, então no repo
novo eles passam a ser raiz). Mesma coisa para `deploy.yml`.

Após o push inicial:

- [ ] Adicionar secrets no repo novo: `GCP_PROJECT_ID`, `GCP_REGION`,
      `GCP_WORKLOAD_IDENTITY_PROV`, `GCP_DEPLOY_SA` (mesmos valores que
      estavam no monorepo — não precisa criar novos no GCP).
- [ ] Habilitar branch protection em `main`: PRs obrigatórios, status
      check `Backend (lint + test)` + `Frontend (build + lint)` required,
      pelo menos 1 review aprovado.
- [ ] Rodar manualmente o `deploy.yml` apontando para o ambiente `stg`
      antes de qualquer push para `main` no repo novo.

## 4. DNS

Hoje (durante Ondas 0–5):
- Backend sandbox vive na URL bruta do Cloud Run.
- Frontend sandbox vive no Vite dev server local.

Cutover esperado (§16.7 do guia):
- `propostai.ai-garage.com.br` → CloudFlare → Cloud Run (PRD)
- `propostai.dev.ai-garage.com.br` → CloudFlare → Cloud Run (DEV)

Etapas:

1. **Cloudflare tunnel:** criar um tunnel apontando para o serviço Cloud Run.
   O time da plataforma rodou esse passo para outros produtos — solicitar
   replicação para `propostai`.
2. **DNS:** registro `CNAME` apontando para o tunnel.
3. **TLS:** terminação no Cloudflare; o backend serve HTTP plain entre
   Cloudflare e Cloud Run (default da plataforma).
4. **CORS:** atualizar `CORS_ORIGINS` no Cloud Run para incluir o novo
   hostname antes do switch.
5. **Validação:** `curl -fsS https://propostai.dev.ai-garage.com.br/health`
   precisa retornar `{"status":"healthy"}` com o overall=`healthy`.

## 5. Smoke E2E em sandbox (7 dias)

Antes do switch para PRD, manter o ambiente `stg` rodando por **7 dias
corridos** sob carga sintética. Roteiro mínimo:

- [ ] Cron diário disparando `POST /api/v1/proposals` com um payload de RFP
      real (uma das demandas do catálogo — `cbenef`, `econf_goias`, etc.).
- [ ] Cron diário disparando `GET /api/v1/proposals/{id}/export/dam`.
- [ ] Cron diário disparando `GET /api/v1/proposals/{id}/export/wp`.
- [ ] Cron diário chamando `POST /api/v1/integrations/portal/sync-tenant`
      (simula evento `tenant.suspended` + reativação) para exercitar o
      `SubscriptionMiddleware`.
- [ ] Cron diário chamando `POST /api/v1/lgpd/export-tenant` (HMAC) para
      um tenant de teste.
- [ ] Verificar **diariamente**:
      - Sem entradas `ERROR` em Sentry com tag `service=propostai`.
      - Latência p95 de `proposals_generated` < 60s no Prometheus.
      - `tenant_id` aparecendo nas labels de `http_requests_total`
        (sinal de que o `MetricsMiddleware` decodifica os JWTs).
      - Eventos `usage.metric` aparecendo no stream do Portal (ou no
        endpoint REST fallback se o stream ainda não existir).

## 6. Go-live (switch PRD)

Critério: 7 dias de smoke E2E sem incidente classe Sev-1 ou Sev-2.

Etapas (na janela de manutenção):

1. **Snapshot** do banco PRD se já existe carga real. `gcloud sql backups create`.
2. **DNS switch**: registro `CNAME` de `propostai.ai-garage.com.br`
   apontando para o tunnel PRD.
3. **Smoke imediato pós-switch:**
   - `GET /health` retorna 200 com `status=healthy`
   - `POST /auth/login` com credenciais de um usuário de teste retorna 200
   - `GET /api/v1/proposals` retorna 200 + lista esperada
   - `/metrics` é scrapeado pelo Prometheus do Portal
4. **Notificar** product owner + arquitetos SAP + canal #plataforma no Slack.
5. **Monitorar por 24h**: dashboard do Cloud Run + Sentry releases + Prometheus
   alerts. Se algo aparecer, executar [`RUNBOOK_ROLLBACK.md`](RUNBOOK_ROLLBACK.md).

## 7. Pós-go-live

- [ ] Tag git no repo novo: `v1.0.0-ga`.
- [ ] Arquivar a branch `feat/onda-1-align-v3` no monorepo (não deletar).
- [ ] Atualizar [`MIGRATION_PLAN.md`](../propostai-app/docs/MIGRATION_PLAN.md)
      marcando Onda 7 como ✅ DONE.
- [ ] Post-mortem leve: o que funcionou, o que demorou mais que o estimado,
      decisões em aberto que ficaram para revisitar.
- [ ] Documentar **calibration profiles** dos primeiros 10 propostas de
      arquitetos reais (memória [Upgrade Proposal Gap]) — alimenta o
      ajuste de horas/equipe pré-GA do próximo produto.

## 8. Rollback de cutover (se o switch DNS der ruim)

1. Reverter o `CNAME` para o registro anterior.
2. Comunicar imediatamente o canal #plataforma + product owner.
3. Investigar: Cloud Run logs, Sentry, Prometheus alerts.
4. Causa raiz documentada; replanejar nova janela.

O backend Cloud Run e o banco continuam intactos durante um rollback de
DNS — é só roteamento.

---

*Este runbook é parte da implantação do plano v3 e deve ser atualizado
quando as etapas externas (Portal SPA, Cloud SQL, Cloudflare tunnel) forem
de fato executadas.*
