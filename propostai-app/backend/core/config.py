"""
Configuracao centralizada da aplicacao via Pydantic Settings.
Todas as variaveis de ambiente sao lidas aqui.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "propostai"
    APP_NAME_HUMAN: str = "PropostAI"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    TIMEZONE: str = "America/Sao_Paulo"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://propostai:secret@localhost:5432/propostai"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str = "CHANGE-ME-IN-PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MIN: int = 60
    REFRESH_TOKEN_EXPIRES_DAYS: int = 30

    # JWT identity claims (v3 §6.3)
    # PRODUCT_SLUG is the canonical product identifier in the platform.
    # It appears in `products[]` and as a key in `roles{by_product}`.
    PRODUCT_SLUG: str = "propostai"
    # JWT_ISSUER: who issued the token. Until the Portal emits RS256 tokens,
    # this product issues its own with iss=https://propostai.ai-garage.com.br.
    # When the Portal is ready, switch to validating tokens issued by it.
    JWT_ISSUER: str = "https://propostai.ai-garage.com.br"
    # JWT_KID: key id. With local HS256 we use a fixed marker; with RS256 from
    # Portal each rotated key has its own kid.
    JWT_KID: str = "local-hs256-default"
    # When True, decoding validates iss/aud strictly (production). When False,
    # iss/aud are accepted but not enforced (legacy tokens, dev convenience).
    JWT_STRICT_VALIDATION: bool = False

    # Encryption
    FERNET_KEY: str = ""

    # Agent Hub
    PORTAL_API_URL: str = "https://app.ai-garage.com.br"
    PORTAL_API_KEY: str = ""
    PORTAL_HMAC_SECRET: str = ""
    PORTAL_CIRCUIT_BREAKER_THRESHOLD: int = 5
    PORTAL_CIRCUIT_BREAKER_TIMEOUT: int = 60
    PORTAL_JWKS_CACHE_TTL_SECONDS: int = 300

    # LLM providers (orchestrator_v5 — Onda 5)
    # Empty defaults so tests / dev environments without keys can still import.
    # The orchestrator raises if a real call is attempted while the key is empty.
    OPENAI_API_KEY: str = ""
    # gpt-4o-mini é 16× mais barato que gpt-4o ($0.15/$0.60 vs $2.50/$10).
    # Usado pra agentes "leves" (AS_IS_TO_BE narrativo) e como fallback do
    # routing Anthropic. Pra qualidade máxima de prosa, voltar pra gpt-4o.
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    # Default da Anthropic agora é Sonnet 4.6 — 5× mais barato que Opus,
    # qualidade equivalente pros agentes funcionais (SD/FI/MM/etc).
    # Agentes que precisam de Opus ou Haiku declaram override em
    # CLAUDE_MODEL_BY_AGENT abaixo.
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    # Agents routed through Anthropic (comma-separated; rest go to OpenAI).
    # Default agora cobre praticamente todos os agentes SAP — Sonnet é
    # superior pro contexto técnico SAP a custo similar ao GPT-4o.
    # Apenas AS_IS_TO_BE fica no GPT (narrativa leve, gpt-4o-mini).
    CLAUDE_AGENTS: str = "ABAP,SD,FI,MM,CO,PP,HR,QM,WM,BASIS,GENERIC,QA,ANON_REVIEW"
    # Per-agent model override. JSON dict mapping agent_name → model_id.
    # Permite manter ABAP no Opus (qualidade máxima pra venda) e QA /
    # ANON_REVIEW no Haiku (tarefas estruturadas, baratas).
    # Agentes ausentes do dict caem no ANTHROPIC_MODEL default (Sonnet).
    CLAUDE_MODEL_BY_AGENT: str = (
        '{"ABAP":"claude-opus-4-7","QA":"claude-haiku-4-5","ANON_REVIEW":"claude-haiku-4-5"}'
    )
    # Timeouts for outbound LLM calls.
    LLM_TIMEOUT_OPENAI: int = 60
    LLM_TIMEOUT_ANTHROPIC: int = 300

    # Sentry (v3 §15.5) — disabled when DSN is empty (dev default).
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "dev"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0  # tracing off by default; opt-in per-env
    SENTRY_RELEASE: str = ""  # set at deploy time to the git sha

    # Events (v3 §12.4, §4.2, §4.3)
    # Set EVENT_CONSUMER_ENABLED=true in prod to start the portal.events
    # consumer in the lifespan. Default false to keep dev/test loops quiet
    # — the REST fallback /sync-tenant is always available when HMAC is set.
    EVENT_CONSUMER_ENABLED: bool = False
    # B4 escape hatch (§1.5 #6 / §21.2.3): when the portal.events stream
    # doesn't exist yet, prefer the REST fallback path on the Portal side.
    EVENT_PUBLISHER_PREFER_REST: bool = False

    # Storage
    STORAGE_BASE_PATH: str = "/data/propostai"
    MAX_UPLOAD_SIZE_MB: int = 25

    # SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@propostai.ai-garage.com.br"
    SMTP_FROM_NAME: str = "PropostAI"

    # Rate Limiting
    RATE_LIMIT_AUTH: str = "5/second"
    RATE_LIMIT_API_GENERAL: str = "20/second"
    RATE_LIMIT_CHAT: str = "10/second"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,https://propostai.ai-garage.com.br"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # SAP Domain
    SAP_DEFAULT_TARIFF_PER_HOUR: int = 230
    SAP_DEFAULT_WARRANTY_DAYS: int = 30
    SAP_DEFAULT_VALIDITY_DAYS: int = 30
    SAP_DEFAULT_BILLING_SPLIT: str = "50/50"
    SAP_MAX_AGENTS_PARALLEL: int = 4
    SAP_AGENT_TIMEOUT_SECONDS: int = 60
    SAP_DEMO_MODE_ENABLED: bool = True

    # Qdrant (RAG vector store — Onda 5)
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION_PREFIX: str = "propostai"
    QDRANT_API_KEY: str = ""  # empty in dev; cloud Qdrant requires it
    QDRANT_TIMEOUT_SECONDS: float = 10.0

    # OpenAI embeddings (RAG ingest + query path)
    OPENAI_EMBED_MODEL: str = "text-embedding-3-large"
    OPENAI_EMBED_DIM: int = 3072  # 3-large default; downstream collection size

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
