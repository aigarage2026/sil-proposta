# Build context is the sil-proposta-app/ root (set in docker-compose.yml)
# so paths are prefixed with backend/ — leaves room to also COPY shared/
# libraries later without changing the context.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml .
RUN pip install --no-cache-dir .

COPY backend/ .

RUN mkdir -p /data/sil_proposta

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
