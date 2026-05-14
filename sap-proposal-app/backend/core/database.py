"""
SQLAlchemy async engine + session factory.
Padrao AI Garage: pool configuravel, health check integrado.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependency FastAPI — yield async session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db() -> str:
    """Health check do banco."""
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return "connected"
    except Exception as e:
        return f"error: {e}"


async def init_db():
    """Cria tabelas (dev only — em prod usar Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Fecha engine na finalizacao."""
    await engine.dispose()
