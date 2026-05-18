"""
Tests for services/propostai/agents/profiles — calibration profile
resolution from a tenant's features dict.

Coverage:
  - DEFAULT_PROFILE used when tenant is None / features missing / unknown name
  - Built-in conservative & aggressive profiles return the expected knobs
  - Typos / unknown names never raise — fall back silently
"""
from types import SimpleNamespace

import pytest

from services.propostai.agents.profiles import (
    AGGRESSIVE_PROFILE,
    CONSERVATIVE_PROFILE,
    DEFAULT_PROFILE,
    PROFILES,
    resolve_profile_for_tenant,
)

pytestmark = pytest.mark.unit


def _tenant(**features):
    return SimpleNamespace(features=features)


def test_none_tenant_returns_default():
    assert resolve_profile_for_tenant(None) is DEFAULT_PROFILE


def test_tenant_without_features_returns_default():
    assert resolve_profile_for_tenant(SimpleNamespace(features=None)) is DEFAULT_PROFILE
    assert resolve_profile_for_tenant(SimpleNamespace(features={})) is DEFAULT_PROFILE


def test_explicit_default_resolves_to_default():
    assert resolve_profile_for_tenant(_tenant(agent_profile="default")) is DEFAULT_PROFILE


def test_conservative_profile_returns_inflated_estimates():
    p = resolve_profile_for_tenant(_tenant(agent_profile="conservative"))
    assert p is CONSERVATIVE_PROFILE
    assert p.hours_multiplier == 1.5
    assert p.qa_min_score == 90
    assert p.confidence_penalty == 0.1


def test_aggressive_profile_returns_deflated_estimates():
    p = resolve_profile_for_tenant(_tenant(agent_profile="aggressive"))
    assert p is AGGRESSIVE_PROFILE
    assert p.hours_multiplier == 0.85


def test_unknown_profile_name_falls_back_to_default():
    # Typo or future name that never shipped → must not blow up generation.
    p = resolve_profile_for_tenant(_tenant(agent_profile="ultra-mega-conservative"))
    assert p is DEFAULT_PROFILE


def test_profiles_registry_contains_all_built_ins():
    # Sanity: every built-in is wired into PROFILES under its own name.
    for built_in in (DEFAULT_PROFILE, CONSERVATIVE_PROFILE, AGGRESSIVE_PROFILE):
        assert PROFILES[built_in.name] is built_in


def test_default_profile_is_no_op():
    assert DEFAULT_PROFILE.hours_multiplier == 1.0
    assert DEFAULT_PROFILE.confidence_penalty == 0.0
