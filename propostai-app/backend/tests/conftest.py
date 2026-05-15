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
    """Mundo completo PropostAI para testes integrados."""
    tenant = await make_tenant("Direto ao Ponto Test")
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


# ── Isolation-test scaffolding (H6 risk in MIGRATION_PLAN) ──────────────────


@pytest.fixture
def make_proposal(db):
    """Minimal Proposal factory — only what the endpoints need to load+respond."""
    async def _make(tenant_id, company_id, user_id, *, title="Test Proposal", status="draft"):
        from models.propostai.proposal import Proposal
        p = Proposal(
            tenant_id=tenant_id,
            company_id=company_id,
            created_by=user_id,
            title=title,
            project_type="Adequação Fiscal",
            sap_version="ecc605",
            states=["SP"],
            commercial_model="fixed",
            rfp_text="RFP de teste.",
            new_law=False,
            hours_presale=0,
            notes=None,
            lang="pt",
            status=status,
            main_proc="SD",
            needs_cpi=False,
            total_hours=80,
            valor=20000,
        )
        db.add(p)
        await db.flush()
        return p
    return _make


@pytest.fixture
async def two_tenants(db, make_tenant, make_user, make_company, make_proposal):
    """Two isolated tenant worlds A and B, each with one user + company + proposal.

    Use this to assert that user A authenticated against the API CANNOT
    read or mutate anything owned by tenant B.
    """
    tenant_a = await make_tenant("Tenant A Ltd", slug="tenant-a")
    user_a = await make_user(tenant_a.id, "owner@a.com", "owner")
    company_a = await make_company(tenant_a.id, "Cliente A")
    proposal_a = await make_proposal(tenant_a.id, company_a.id, user_a.id, title="Proposta A")

    tenant_b = await make_tenant("Tenant B SA", slug="tenant-b")
    user_b = await make_user(tenant_b.id, "owner@b.com", "owner")
    company_b = await make_company(tenant_b.id, "Cliente B")
    proposal_b = await make_proposal(tenant_b.id, company_b.id, user_b.id, title="Proposta B")

    await db.commit()
    return {
        "a": {"tenant": tenant_a, "user": user_a, "company": company_a, "proposal": proposal_a},
        "b": {"tenant": tenant_b, "user": user_b, "company": company_b, "proposal": proposal_b},
    }


@pytest.fixture
def mint_token():
    """Mint a real v3-shaped access token for a User row."""
    def _mint(user):
        from core.security import create_access_token
        return create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            role=user.role,
            is_platform_admin=user.is_platform_admin,
        )
    return _mint


@pytest.fixture
def auth_headers(mint_token):
    def _make(user):
        return {"Authorization": f"Bearer {mint_token(user)}"}
    return _make


@pytest.fixture
def isolation_client(client):
    """Wrap `client` with a subscription-middleware shim so every tenant
    reads as `is_active=True` (no DB lookup). Without this the middleware
    would query the production engine — which the test DB shim doesn't
    override.

    Use this fixture wherever the test needs authenticated proposal-API
    access. Cleans the shim on teardown.
    """
    from main import app

    def _always_active(_tenant_id):
        return (True, None)

    app.state.subscription_state_loader = _always_active
    yield client
    if hasattr(app.state, "subscription_state_loader"):
        delattr(app.state, "subscription_state_loader")
