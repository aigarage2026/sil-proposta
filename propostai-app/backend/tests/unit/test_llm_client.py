"""
Unit tests para LLMClient — per-agent model routing.

Cobre o caminho que importa pra venda: ABAP precisa cair no modelo
premium (Opus), QA/ANON_REVIEW caem no barato (Haiku), resto cai no
default (Sonnet). Erro de config (JSON corrompido) não pode quebrar
init — degrada silenciosamente pro default.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from services.propostai.agents.llm_client import LLMClient

pytestmark = pytest.mark.unit


@dataclass
class _CapturedRequest:
    url: str = ""
    json_body: dict = field(default_factory=dict)


@dataclass
class _FakeResponse:
    status_code: int = 200
    _data: dict = field(default_factory=dict)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._data


class _FakeClient:
    """Captura o último POST e devolve uma resposta Anthropic-shaped."""

    def __init__(self, captures: list[_CapturedRequest]):
        self.captures = captures

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, *, json=None, headers=None):  # noqa: A002
        self.captures.append(_CapturedRequest(url=url, json_body=json or {}))
        return _FakeResponse(
            200,
            {
                "content": [{"text": "ok"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )


def _client_with_overrides(overrides: dict[str, str]) -> tuple[LLMClient, list[_CapturedRequest]]:
    captures: list[_CapturedRequest] = []
    return (
        LLMClient(
            openai_key="sk-stub",
            anthropic_key="sk-ant-stub",
            openai_model="gpt-4o-mini",
            anthropic_model="claude-sonnet-4-6",
            claude_agents=frozenset({"ABAP", "QA", "ANON_REVIEW", "SD"}),
            claude_model_by_agent=overrides,
            http_factory=lambda: _FakeClient(captures),
        ),
        captures,
    )


async def test_abap_uses_per_agent_override_to_opus():
    client, captures = _client_with_overrides({
        "ABAP": "claude-opus-4-7",
        "QA": "claude-haiku-4-5",
    })
    await client.call(system="s", user="u", agent_name="ABAP")
    assert captures[0].json_body["model"] == "claude-opus-4-7"


async def test_qa_uses_per_agent_override_to_haiku():
    client, captures = _client_with_overrides({
        "ABAP": "claude-opus-4-7",
        "QA": "claude-haiku-4-5",
    })
    await client.call(system="s", user="u", agent_name="QA")
    assert captures[0].json_body["model"] == "claude-haiku-4-5"


async def test_anon_review_uses_per_agent_override_to_haiku():
    client, captures = _client_with_overrides({
        "ANON_REVIEW": "claude-haiku-4-5",
    })
    await client.call(system="s", user="u", agent_name="ANON_REVIEW")
    assert captures[0].json_body["model"] == "claude-haiku-4-5"


async def test_agent_without_override_falls_back_to_sonnet_default():
    client, captures = _client_with_overrides({
        "ABAP": "claude-opus-4-7",
    })
    await client.call(system="s", user="u", agent_name="SD")
    assert captures[0].json_body["model"] == "claude-sonnet-4-6"


async def test_billing_record_carries_the_chosen_model_not_the_default():
    client, _ = _client_with_overrides({"ABAP": "claude-opus-4-7"})
    await client.call(system="s", user="u", agent_name="ABAP")
    assert client.billing
    assert client.billing[0].model_name == "claude-opus-4-7"
    assert client.billing[0].agent_name == "ABAP"


def test_from_settings_tolerates_broken_json_in_override():
    # Acidente comum: alguém edita .env e quebra o JSON. Não pode derrubar
    # a aplicação — só desliga o override.
    import os
    os.environ["CLAUDE_MODEL_BY_AGENT"] = "not-a-json{}"
    try:
        # Forçar reload de get_settings
        from core import config as cfg
        cfg.get_settings.cache_clear()
        client = LLMClient.from_settings()
        assert client.claude_model_by_agent == {}
    finally:
        del os.environ["CLAUDE_MODEL_BY_AGENT"]
        from core import config as cfg
        cfg.get_settings.cache_clear()


def test_from_settings_loads_json_override_when_valid():
    import os
    os.environ["CLAUDE_MODEL_BY_AGENT"] = json.dumps({"ABAP": "claude-opus-4-7"})
    try:
        from core import config as cfg
        cfg.get_settings.cache_clear()
        client = LLMClient.from_settings()
        assert client.claude_model_by_agent == {"ABAP": "claude-opus-4-7"}
    finally:
        del os.environ["CLAUDE_MODEL_BY_AGENT"]
        from core import config as cfg
        cfg.get_settings.cache_clear()
