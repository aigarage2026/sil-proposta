"""
Sil-Proposta SaaS — Backend FastAPI
Gerador de Propostas SAP com IA Multi-Agente
Plataforma AI Garage
"""
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.config import get_settings
from core.database import check_db, init_db, close_db
from core.logger import setup_logging, get_logger
from core.rate_limiter import limiter
from core.trace_middleware import TraceMiddleware

settings = get_settings()
logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    setup_logging()
    logger.info("Starting Sil-Proposta", version=settings.VERSION)
    if settings.DEBUG:
        await init_db()
    yield
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

# ── Middleware Stack (ordem: SlowAPI → Trace → CORS → Handler) ──────────

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(TraceMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-ID", "Content-Disposition"],
)


# ── Health Check ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    db_status = await check_db()
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "version": settings.VERSION,
        "app": settings.APP_NAME_HUMAN,
        "database": db_status,
        "demo_mode": settings.SAP_DEMO_MODE_ENABLED,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME_HUMAN,
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else "disabled",
    }


# ── Routers ─────────────────────────────────────────────────────────────

from apis.v1.auth import router as auth_router
from apis.v1.setup import router as setup_router
from apis.v1.sap_proposal.proposals import router as proposals_router

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(setup_router, prefix="/setup", tags=["Setup"])
app.include_router(proposals_router, prefix="/api/v1/proposals", tags=["Proposals"])
