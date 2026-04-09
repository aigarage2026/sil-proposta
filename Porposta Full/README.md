# Sil-Proposta v1.0

Sistema inteligente de geração de propostas SAP com 18 agentes especialistas.

## Estrutura

```
sil-proposta-full/
├── frontend/
│   └── index.html          ← UI completa (PT/EN/ES), todas as fases
├── backend/
│   ├── main.py             ← FastAPI endpoints
│   ├── requirements.txt
│   ├── agents/
│   │   ├── __init__.py
│   │   └── orchestrator.py ← 18 agentes + orquestrador
│   └── generators/
│       ├── __init__.py
│       ├── dam.py          ← Gerador DAM Word (python-docx)
│       └── wp.py           ← Gerador WP Excel (openpyxl)
```

## Setup Backend

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload --port 8000
```

## Setup Frontend

Abrir `frontend/index.html` diretamente no browser, ou servir com:
```bash
cd frontend && python -m http.server 3000
```

## API Endpoints

- `POST /api/generate`        → Gera proposta completa (JSON)
- `POST /api/generate/stream` → SSE com progresso dos agentes em tempo real
- `POST /api/download/dam`    → Baixa DAM Word (.docx)
- `POST /api/download/wp`     → Baixa WP Excel (.xlsx)
- `GET  /api/health`          → Health check

## Fases implementadas

### Fase 1 — Fundação e MVP ✅
- Tela de intake multi-língua (PT-BR, EN, ES)
- Switcher de idioma no topo, padrão PT-BR
- 5 campos obrigatórios + 3 opcionais
- Horas de coleta: custo interno separado (não entra no DAM/WP)
- Barra de progresso + botão ativo apenas quando campos preenchidos
- Simulação de geração com agentes em sequência

### Fase 2 — Agentes especialistas ✅
- 18 agentes: SD, MM, PP, FI, CO, WM, PM, HR, BW, ABAP, Basis
- Agente DRC com regra: evento sem nota SAP → CPI obrigatório
- 3 agentes fiscais: Municipal, Estadual (27 UFs + tpIntegra GO), Federal
- Agente Reforma Tributária (LC 214) com lógica fazer/planejar/monitorar
- Agente versão SAP, equipe (paralelismo ABAPers), estimativa, comercial
- Regras de derivação ABAP: BAPI Z hardware → BAdI → RFC → iFlow → Monitor

### Fase 3 — Output e proposta final ✅
- Rascunho v1 editável com painel de confiança (4 dimensões)
- Gerador DAM Word no template Cast Group (python-docx)
- Gerador WP Excel com fases SAP Activate + KT AMS (openpyxl)
- Cálculo interno: horas faturáveis vs horas pré-venda vs % custo oculto
- Workflow: rascunho v1 → revisão → aprovação → proposta final v2

### Fase 4 — Inteligência e escala ✅ (estrutura)
- Histórico de propostas na sidebar
- Analytics: métricas de conversão, horas médias, custo pré-venda
- Gráfico de distribuição de horas por frente
- Base para feedback loop (propostas ganhas/perdidas)

## Deploy sugerido

- Frontend: Vercel (static)
- Backend: Railway ou Fly.io
- DB: Supabase + pgvector (RAG)
- Files: Cloudflare R2

## Variáveis de ambiente

```
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
```
