# Deploy Sil-Proposta no Railway

## Passo 1 — Criar conta no GitHub
Acesse: https://github.com e crie uma conta se não tiver.

## Passo 2 — Criar repositório
1. Clique em "New repository"
2. Nome: `sil-proposta`
3. Visibilidade: Private
4. Clique "Create repository"

## Passo 3 — Enviar os arquivos
Na pasta do projeto, abra o terminal (cmd) e rode:
```
git init
git add .
git commit -m "Sil-Proposta v3 — backend com banco de dados"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/sil-proposta.git
git push -u origin main
```

## Passo 4 — Deploy no Railway
1. Acesse: https://railway.app
2. Faça login com sua conta GitHub
3. Clique "New Project"
4. Escolha "Deploy from GitHub repo"
5. Selecione o repositório `sil-proposta`
6. Railway detecta o Dockerfile automaticamente

## Passo 5 — Configurar variáveis (opcional)
No Railway, vá em Settings > Variables e adicione:
- `OPENAI_API_KEY` = sua chave OpenAI (se quiser IA real)
- Sem essa chave, o sistema usa a engine interna (funciona sempre)

## Passo 6 — Obter URL pública
1. No Railway, vá em Settings > Networking
2. Clique "Generate Domain"
3. Sua URL será algo como: `https://sil-proposta.up.railway.app`

## Resultado
- Frontend: `https://sil-proposta.up.railway.app/app`
- API: `https://sil-proposta.up.railway.app/api/health`
- Docs: `https://sil-proposta.up.railway.app/docs`

## Banco de dados
O Railway usa SQLite por padrão (dados persistem no container).
Para maior durabilidade, adicione um PostgreSQL:
1. No Railway, clique "+ New" > "Database" > "PostgreSQL"
2. Copie a variável `DATABASE_URL`
3. Adicione em Settings > Variables do seu app

## Suporte
- Railway gratuito: 500 horas/mês
- Plano pago ($5/mês): sem limite
