"""
Configuracao centralizada da aplicacao via Pydantic Settings.
Todas as variaveis de ambiente sao lidas aqui.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "sil_proposta"
    APP_NAME_HUMAN: str = "Sil-Proposta"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    TIMEZONE: str = "America/Sao_Paulo"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://sil_proposta:secret@localhost:5432/sil_proposta"
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
    PRODUCT_SLUG: str = "sil-proposta"
    # JWT_ISSUER: who issued the token. Until the Portal emits RS256 tokens,
    # this product issues its own with iss=https://sil-proposta.ai-garage.com.br.
    # When the Portal is ready, switch to validating tokens issued by it.
    JWT_ISSUER: str = "https://sil-proposta.ai-garage.com.br"
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
    OPENAI_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-4-7"
    # Agents routed through Claude (comma-separated; rest go to OpenAI).
    # Default mirrors the legacy: ABAP + QA get Claude when the key is set.
    CLAUDE_AGENTS: str = "ABAP,QA"
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
    STORAGE_BASE_PATH: str = "/data/sil_proposta"
    MAX_UPLOAD_SIZE_MB: int = 25

    # SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@sil-proposta.ai-garage.com.br"
    SMTP_FROM_NAME: str = "Sil-Proposta"

    # Rate Limiting
    RATE_LIMIT_AUTH: str = "5/second"
    RATE_LIMIT_API_GENERAL: str = "20/second"
    RATE_LIMIT_CHAT: str = "10/second"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,https://sil-proposta.ai-garage.com.br"

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

    # Qdrant (optional — MVP-2)
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION_PREFIX: str = "sil_proposta"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
