"""
Configuracao centralizada da aplicacao via Pydantic Settings.
Todas as variaveis de ambiente sao lidas aqui.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "sap_proposal"
    APP_NAME_HUMAN: str = "Sil-Proposta"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    TIMEZONE: str = "America/Sao_Paulo"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://sap_proposal:secret@localhost:5432/sap_proposal"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str = "CHANGE-ME-IN-PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MIN: int = 60
    REFRESH_TOKEN_EXPIRES_DAYS: int = 30

    # Encryption
    FERNET_KEY: str = ""

    # Agent Hub
    AGENT_HUB_API_URL: str = "https://app.ai-garage.com.br"
    AGENT_HUB_API_KEY: str = ""
    AGENT_HUB_HMAC_SECRET: str = ""
    AGENT_HUB_CIRCUIT_BREAKER_THRESHOLD: int = 5
    AGENT_HUB_CIRCUIT_BREAKER_TIMEOUT: int = 60
    AGENT_HUB_CACHE_TTL_SECONDS: int = 300

    # Storage
    STORAGE_BASE_PATH: str = "/data/sap_proposal"
    MAX_UPLOAD_SIZE_MB: int = 25

    # SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@sap-proposal.ai-garage.com.br"
    SMTP_FROM_NAME: str = "Sil-Proposta"

    # Rate Limiting
    RATE_LIMIT_AUTH: str = "5/second"
    RATE_LIMIT_API_GENERAL: str = "20/second"
    RATE_LIMIT_CHAT: str = "10/second"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,https://sap-proposal.ai-garage.com.br"

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
    QDRANT_COLLECTION_PREFIX: str = "sap_proposal"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
