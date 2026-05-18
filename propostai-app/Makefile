# PropostAI SaaS — Makefile

# === Production ===
prod-up:
	docker compose -f deployment/docker-compose.yml up -d

prod-down:
	docker compose -f deployment/docker-compose.yml down

prod-logs:
	docker compose -f deployment/docker-compose.yml logs -f

prod-rebuild:
	docker compose -f deployment/docker-compose.yml up --build -d

# === Development ===
dev:
	docker compose -f deployment/docker-compose.dev.yml up -d

dev-backend:
	cd backend && uvicorn main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# === Database ===
migrate:
	cd backend && alembic upgrade head

migrate-down:
	cd backend && alembic downgrade -1

migration:
	cd backend && alembic revision --autogenerate -m "$(name)"

seed:
	cd backend && python scripts/seed_propostai_platform.py

# === Testing ===
test:
	cd backend && pytest

test-unit:
	cd backend && pytest -m unit

test-integration:
	cd backend && pytest -m integration

test-isolation:
	cd backend && pytest -m isolation

test-cov:
	cd backend && pytest --cov=. --cov-report=html

# === Quality ===
lint:
	cd backend && ruff check .

format:
	cd backend && ruff format .

typecheck:
	cd backend && mypy .

# === Utilities ===
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
