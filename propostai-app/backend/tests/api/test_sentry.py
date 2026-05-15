"""
Sentry context propagation (v3 §15.5).

Strategy: replace sentry_sdk.new_scope with a stub that captures the
tag/user calls. The middleware itself must work whether or not Sentry is
initialized — when DSN is empty, sentry_sdk APIs are silent no-ops, and
our middleware still pushes the scope.

Init is unit-tested separately (small surface): empty DSN → False, set DSN
→ True (mocked sentry_sdk.init).
"""
from contextlib import contextmanager

import jwt
import pytest

from core import sentry as sentry_mod

pytestmark = pytest.mark.api


class _FakeScope:
    def __init__(self):
        self.tags: dict[str, str] = {}
        self.user: dict | None = None

    def set_tag(self, key, value):
        self.tags[key] = value

    def set_user(self, user):
        self.user = user


class _ScopeCapture:
    """Drop-in replacement for sentry_sdk.new_scope().

    Used as a context manager; records what the middleware did to the scope.
    """

    def __init__(self):
        self.scopes: list[_FakeScope] = []

    @contextmanager
    def __call__(self):
        scope = _FakeScope()
        self.scopes.append(scope)
        yield scope


@pytest.fixture
def captured_scope(monkeypatch):
    capture = _ScopeCapture()
    monkeypatch.setattr(sentry_mod.sentry_sdk, "new_scope", capture)
    return capture


def _token(tenant_id: str, sub: str = "u-1") -> str:
    return jwt.encode(
        {"sub": sub, "tenant_id": tenant_id, "exp": 9_999_999_999},
        "irrelevant",
        algorithm="HS256",
    )


# ── tagging ─────────────────────────────────────────────────────────────────


async def test_anonymous_request_tagged_anonymous(client, captured_scope):
    await client.get("/health")
    assert len(captured_scope.scopes) == 1
    assert captured_scope.scopes[0].tags["tenant_id"] == "anonymous"
    assert captured_scope.scopes[0].user is None


async def test_authenticated_request_tags_tenant_and_user(client, captured_scope):
    headers = {"Authorization": f"Bearer {_token('tenant-zzz', sub='user-abc')}"}
    await client.get("/health", headers=headers)
    scope = captured_scope.scopes[-1]
    assert scope.tags["tenant_id"] == "tenant-zzz"
    assert scope.user == {"id": "user-abc"}


async def test_trace_id_propagates_from_header(client, captured_scope):
    await client.get("/health", headers={"X-Trace-ID": "trace-from-client"})
    scope = captured_scope.scopes[-1]
    assert scope.tags.get("trace_id") == "trace-from-client"


async def test_invalid_token_falls_back_to_anonymous(client, captured_scope):
    await client.get("/health", headers={"Authorization": "Bearer not-a-jwt"})
    scope = captured_scope.scopes[-1]
    assert scope.tags["tenant_id"] == "anonymous"
    assert scope.user is None


# ── init helper ─────────────────────────────────────────────────────────────


def test_init_sentry_noop_when_dsn_empty(monkeypatch):
    settings = sentry_mod.settings
    monkeypatch.setattr(settings, "SENTRY_DSN", "")
    assert sentry_mod.init_sentry() is False


def test_init_sentry_calls_sdk_when_dsn_set(monkeypatch):
    captured = {}

    def fake_init(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(sentry_mod.sentry_sdk, "init", fake_init)
    monkeypatch.setattr(sentry_mod.sentry_sdk, "set_tag", lambda *_a, **_k: None)

    settings = sentry_mod.settings
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://example@sentry.io/0")
    monkeypatch.setattr(settings, "SENTRY_ENVIRONMENT", "test-env")
    monkeypatch.setattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.5)
    monkeypatch.setattr(settings, "SENTRY_RELEASE", "v1.2.3")

    assert sentry_mod.init_sentry() is True
    assert captured["dsn"] == "https://example@sentry.io/0"
    assert captured["environment"] == "test-env"
    assert captured["release"] == "v1.2.3"
    assert captured["traces_sample_rate"] == 0.5
    assert captured["send_default_pii"] is False
