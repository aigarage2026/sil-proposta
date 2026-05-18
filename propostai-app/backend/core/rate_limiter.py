"""
Rate limiting via SlowAPI.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_API_GENERAL],
    storage_uri=settings.REDIS_URL,
)
