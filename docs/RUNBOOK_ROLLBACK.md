# Runbook de Rollback — PropostAI

**Objetivo:** documentar o processo seguro de reversão do ambiente de migração para `propostai-app` caso seja necessário retornar ao estado pré-refatoração.

## 1. Contexto

Este runbook cobre o rollback do projeto `propostai` no contexto da migração para o padrão Portal SaaS v3.

O plano de migração atual considera:
- `propostai-app/` como código ativo de migração
- `legacy/propostai-monolith/` como histórico arquivado
- `docs/ARCHITECTURE_PORTAL_SAAS_v3.md` como guia de arquitetura
- `docs/MIGRATION_PLAN.md` como plano de execução do produto

## 2. Critérios de rollback

Execute rollback quando qualquer uma das condições abaixo ocorrer:

- Deploy em sandbox ou cloud causar perda de dados irreversível impactando validação de tenant
- Autenticação/JWT legada falhar e não puder ser corrigida rapidamente
- Isolamento multi-tenant estiver comprometido em ambiente de prova de conceito
- Integração com o Portal (ou com mock do Portal) quebrar de forma que não seja possível entrega mínima do MVP
- O deploy do `propostai-app` em uma nuvem de teste causar degradação maior do que o aceitável para validação técnica

## 3. Rollback imediato (local / sandbox)

1. Parar containers ou processos do ambiente sandbox.
2. Restaurar a branch de trabalho para o último commit seguro, se necessário.
3. Se o rollback for um retorno ao estado pré-reorganização, usar o snapshot git:

```bash
git checkout backup/pre-org-2026-05-14
```

4. Verificar se as dependências estão na versão esperada:
- `python` / `fastapi` / `sqlalchemy` / `alembic`
- `node` / `vite` / `react` / `tailwind`

5. Recriar o ambiente local:

```bash
cd propostai-app
# ajuste conforme o ambiente local
poetry install
pytest
```

6. Resetar o banco local se necessário:

```bash
docker compose -f deployment/docker-compose.dev.yml down
docker compose -f deployment/docker-compose.dev.yml up -d
alembic downgrade base
alembic upgrade head
```

## 4. Rollback de deploy em nuvem

1. Identificar se o rollback deve ser no deployment Cloud Run / Railway / outro provedor.
2. Se houver snapshot ou tag de release anterior, restaurar a imagem/versão anterior.
3. Reaplicar configurações padrão de database e ambiente do `propostai-app`.
4. Validar com smoke tests:
- `/health`
- autenticação básica
- acesso ao CRUD de `Proposal`

## 5. Comunicação

- Notificar imediatamente o time técnico e o product owner.
- Especificar o motivo do rollback e a versão alvo.
- Atualizar `docs/MIGRATION_PLAN.md` e o ticket de trabalho com o resultado.

## 6. Lições aprendidas

Após rollback, realizar post-mortem simples:
- qual falha ocorreu?
- qual objectivo do deploy não foi atendido?
- o que precisa ser ajustado no `docs/MIGRATION_PLAN.md`?
- há necessidade de novo checkpoint ou revisão do `docs/ARCHITECTURE_PORTAL_SAAS_v3.md`?

---

*Este documento é parte do processo de implantação do plano de migração v3 e deve ser atualizado sempre que houver mudança no fluxo de rollback ou nos critérios de corte.*
