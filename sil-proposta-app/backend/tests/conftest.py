"""
Fixtures globais para testes.
"""
import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.database import Base

# Engine SQLite in-memory para testes unitarios
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_db():
    """Cria e destroi tabelas a cada teste."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db():
    """Sessao de banco para testes."""
    async with TestSession() as session:
        yield session


@pytest.fixture
async def client(db):
    """HTTP client para testes de API."""
    from core.database import get_db
    from main import app

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


# ── Factories ────────────────────────────────────────────────────────────────

@pytest.fixture
def make_tenant(db):
    async def _make(name="Test Tenant", slug=None):
        from models.tenant import Tenant
        t = Tenant(name=name, slug=slug or f"test-{uuid4().hex[:8]}")
        db.add(t)
        await db.flush()
        return t
    return _make


@pytest.fixture
def make_user(db):
    async def _make(tenant_id, email=None, role="editor", is_platform_admin=False):
        from core.security import hash_password
        from models.user import User
        u = User(
            tenant_id=tenant_id,
            email=email or f"user-{uuid4().hex[:8]}@test.com",
            full_name="Test User",
            password_hash=hash_password("test123"),
            role=role,
            is_platform_admin=is_platform_admin,
            is_active=True,
            is_email_verified=True,
        )
        db.add(u)
        await db.flush()
        return u
    return _make


@pytest.fixture
def make_company(db):
    async def _make(tenant_id, name="Test Company"):
        from models.company import Company
        c = Company(tenant_id=tenant_id, name=name, is_default=True)
        db.add(c)
        await db.flush()
        return c
    return _make


@pytest.fixture
async def sap_world(db, make_tenant, make_user, make_company):
    """Mundo completo Sil-Proposta para testes integrados."""
    tenant = await make_tenant("Cast Group Test")
    owner = await make_user(tenant.id, "owner@cast.com", "owner")
    editor = await make_user(tenant.id, "editor@cast.com", "editor")
    company = await make_company(tenant.id, "Cliente ABC")
    await db.commit()
    return {
        "tenant": tenant,
        "owner": owner,
        "editor": editor,
        "company": company,
    }
