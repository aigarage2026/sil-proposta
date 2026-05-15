"""
Sil-Proposta SaaS — Backend FastAPI
Gerador de Propostas SAP com IA Multi-Agente
Portal AI Garage (Agent-Hub)
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
import redis.asyncio as redis_lib
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.config import get_settings
from core.database import check_db, init_db, close_db
from core.jwks_client import get_jwks_client
from core.logger import setup_logging, get_logger
from core.metrics import render_metrics
from core.metrics_middleware import MetricsMiddleware
from core.rate_limiter import limiter
from core.sentry import SentryContextMiddleware, init_sentry
from core.subscription_middleware import SubscriptionMiddleware
from core.trace_middleware import TraceMiddleware

settings = get_settings()
logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    setup_logging()
    init_sentry()
    logger.info("Starting Sil-Proposta", version=settings.VERSION)
    if settings.DEBUG:
        await init_db()

    # portal.events consumer (Onda 3 — v3 §4.2)
    consumer_task = None
    if settings.EVENT_CONSUMER_ENABLED:
        from services.events.consumer import start_consumer
        consumer_task = start_consumer()
        logger.info("event_consumer_lifecycle_started")

    yield

    if consumer_task is not None:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    await close_db()
    logger.info("Sil-Proposta stopped")


app = FastAPI(
    title=settings.APP_NAME_HUMAN,
    description="Gerador de Propostas SAP com IA Multi-Agente — Plataforma SaaS AI Garage",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ── Middleware Stack ────────────────────────────────────────────────────
# Innermost → outermost (FastAPI applies the LAST add_middleware first):
#   TraceMiddleware           → bind trace_id to contextvars + request.state
#   SentryContextMiddleware   → push scope w/ tenant_id, trace_id, user_id
#   SubscriptionMiddleware    → 423 suspended writes
#   MetricsMiddleware         → record http_requests_total + duration
#   CORSMiddleware            → outermost

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(TraceMiddleware)
app.add_middleware(SentryContextMiddleware)
app.add_middleware(SubscriptionMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-ID", "Content-Disposition"],
)


# ── Health Check (v3 §4.1) ──────────────────────────────────────────────

async def _check_redis() -> str:
    try:
        client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            pong = await client.ping()
            return "ok" if pong else "down"
        finally:
            await client.aclose()
    except Exception as e:  # noqa: BLE001
        logger.warning("health_redis_failed", error=str(e))
        return "down"


async def _check_qdrant() -> str:
    try:
        async with httpx.AsyncClient(timeout=2.0) as http:
            r = await http.get(f"{settings.QDRANT_URL.rstrip('/')}/")
            return "ok" if r.status_code == 200 else "degraded"
    except Exception as e:  # noqa: BLE001
        logger.warning("health_qdrant_failed", error=str(e))
        return "down"


async def _check_portal_jwks() -> str:
    """Returns 'ok' / 'unreachable' / 'disabled'.
    Not a hard error — the dual-mode auth (v3 §6.5) tolerates this.
    """
    j = get_jwks_client()
    if not j.enabled:
        return "disabled"
    try:
        async with httpx.AsyncClient(timeout=2.0) as http:
            r = await http.get(j._jwks_url)
            return "ok" if r.status_code == 200 else "unreachable"
    except Exception:
        return "unreachable"


@app.get("/health")
async def health():
    """v3 §4.1: status + per-dependency health."""
    db_task = asyncio.create_task(check_db())
    redis_task = asyncio.create_task(_check_redis())
    qdrant_task = asyncio.create_task(_check_qdrant())
    jwks_task = asyncio.create_task(_check_portal_jwks())

    db_status, redis_status, qdrant_status, jwks_status = await asyncio.gather(
        db_task, redis_task, qdrant_task, jwks_task
    )

    deps = {
        "database": db_status,
        "redis": redis_status,
        "qdrant": qdrant_status,
        "portal_jwks": jwks_status,
    }
    # Overall status: healthy iff DB is connected and Redis is up.
    # JWKS being unreachable is acceptable (we fall back to local HS256).
    # Qdrant being down only degrades the RAG path, not auth/CRUD.
    is_healthy = db_status == "connected" and redis_status == "ok"
    overall = "healthy" if is_healthy else "degraded"

    return {
        "status": overall,
        "version": settings.VERSION,
        "app": settings.APP_NAME_HUMAN,
        "demo_mode": settings.SAP_DEMO_MODE_ENABLED,
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": deps,
    }


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME_HUMAN,
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else "disabled",
    }


# ── /.well-known/openapi.json (v3 §4.1) ─────────────────────────────────
# The Portal scrapes this during product registration; FastAPI exposes
# the spec at /openapi.json by default. The well-known alias is just a
# 301 to avoid duplicating the route.

@app.get("/.well-known/openapi.json", include_in_schema=False)
async def well_known_openapi():
    return RedirectResponse(url="/openapi.json", status_code=301)


# ── /metrics (Prometheus) — v3 §15.3 ────────────────────────────────────

@app.get("/metrics", include_in_schema=False)
async def metrics():
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


# ── Routers ─────────────────────────────────────────────────────────────

from apis.v1.auth import router as auth_router
from apis.v1.setup import router as setup_router
from apis.v1.sil_proposta.proposals import router as proposals_router
from apis.v1.integrations.portal import router as portal_integrations_router
from apis.v1.integrations.lgpd import router as lgpd_router
from apis.v1.dashboard import router as dashboard_router

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(setup_router, prefix="/setup", tags=["Setup"])
app.include_router(proposals_router, prefix="/api/v1/proposals", tags=["Proposals"])
app.include_router(
    portal_integrations_router,
    prefix="/api/v1/integrations/portal",
    tags=["Portal Integrations"],
)
app.include_router(lgpd_router, prefix="/api/v1/lgpd", tags=["LGPD"])
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["Dashboard"])
