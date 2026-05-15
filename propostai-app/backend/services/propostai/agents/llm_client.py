"""
LLM client used by orchestrator_v5 — OpenAI + Anthropic HTTP (v3 Onda 5).

Two design choices intentionally kept from the legacy port:
  - Direct HTTP calls (httpx), no SDK. Keeps the dependency surface small
    and lets us swap providers without an SDK upgrade dance.
  - Per-instance billing records — replaces the legacy `_billing_buffer`
    global. Each LLMClient holds its own records list; the orchestrator
    drains it at the end of run().

Anonymization (v3 §4.5.5 E2): the orchestrator decides whether to mask
the RFP before constructing the user prompt. This module is *not* aware
of LGPD by design — it just sends what it's given. Passing through
already-anonymized strings keeps the cost model simple.

Routing: if `agent_name` is in `claude_agents` AND `anthropic_key` is set,
Anthropic gets the call; otherwise OpenAI. Errors from Anthropic fall
through to OpenAI (best-effort), unless `prefer_openai=True`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

from core.config import get_settings
from core.logger import get_logger

logger = get_logger()


@dataclass
class BillingRecord:
    """One call's token accounting, stored in LLMClient.billing."""
    model_name: str
    agent_name: str
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cached: int = 0


@dataclass
class LLMClient:
    """Per-orchestrator-run LLM gateway.

    Pass a custom `http_factory` in tests to short-circuit the network —
    it must be a callable taking no args and returning something with a
    `post(url, json=, headers=)` coroutine returning a response whose
    `.status_code`, `.raise_for_status()`, and `.json()` work like httpx.
    """

    openai_key: Optional[str] = None
    anthropic_key: Optional[str] = None
    openai_model: Optional[str] = None
    anthropic_model: Optional[str] = None
    claude_agents: frozenset[str] = frozenset()
    openai_timeout: int = 60
    anthropic_timeout: int = 300
    http_factory: Optional[object] = None

    billing: list[BillingRecord] = field(default_factory=list)

    @classmethod
    def from_settings(cls) -> "LLMClient":
        s = get_settings()
        agents = frozenset(a.strip() for a in (s.CLAUDE_AGENTS or "").split(",") if a.strip())
        return cls(
            openai_key=s.OPENAI_API_KEY or None,
            anthropic_key=s.ANTHROPIC_API_KEY or None,
            openai_model=s.OPENAI_MODEL,
            anthropic_model=s.ANTHROPIC_MODEL,
            claude_agents=agents,
            openai_timeout=s.LLM_TIMEOUT_OPENAI,
            anthropic_timeout=s.LLM_TIMEOUT_ANTHROPIC,
        )

    # ── public API ──────────────────────────────────────────────────────

    async def call(
        self,
        *,
        system: str,
        user: str,
        agent_name: str = "",
        max_tokens: int = 2000,
    ) -> str:
        """Route + call. Returns the assistant text (already stripped).

        Anthropic-routed calls fall back to OpenAI if Anthropic raises and
        OpenAI is configured. If neither path is configured the call
        raises ValueError so the orchestrator can react.
        """
        try_claude = (
            agent_name in self.claude_agents
            and self.anthropic_key
            and self.anthropic_key != "sua-chave-aqui"
        )
        if try_claude:
            try:
                return await self._call_anthropic(system, user, agent_name, max_tokens)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "llm_anthropic_failed_fallback_openai",
                    agent=agent_name,
                    error=str(exc),
                )
                # fall through to OpenAI
        return await self._call_openai(system, user, agent_name, max_tokens)

    # ── providers ───────────────────────────────────────────────────────

    def _http(self, timeout: float):
        if self.http_factory is not None:
            return self.http_factory()
        return httpx.AsyncClient(timeout=timeout)

    async def _call_openai(
        self, system: str, user: str, agent_name: str, max_tokens: int
    ) -> str:
        if not self.openai_key or self.openai_key == "sua-chave-aqui":
            raise ValueError("OPENAI_API_KEY not configured")
        async with self._http(self.openai_timeout) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.openai_model,
                    "temperature": 0.0,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {}) or {}
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            self.billing.append(
                BillingRecord(
                    model_name=self.openai_model or "",
                    agent_name=agent_name,
                    tokens_input=usage.get("prompt_tokens", 0),
                    tokens_output=usage.get("completion_tokens", 0),
                    tokens_cached=cached,
                )
            )
            return text

    async def _call_anthropic(
        self, system: str, user: str, agent_name: str, max_tokens: int
    ) -> str:
        if not self.anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        async with self._http(self.anthropic_timeout) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.anthropic_model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            r.raise_for_status()
            data = r.json()
            text = data["content"][0]["text"].strip()
            usage = data.get("usage", {}) or {}
            self.billing.append(
                BillingRecord(
                    model_name=self.anthropic_model or "",
                    agent_name=agent_name,
                    tokens_input=usage.get("input_tokens", 0),
                    tokens_output=usage.get("output_tokens", 0),
                    tokens_cached=usage.get("cache_read_input_tokens", 0),
                )
            )
            return text


# ── parse helpers ───────────────────────────────────────────────────────────


def parse_llm_json(text: str) -> dict:
    """Tolerant JSON extractor for LLM responses.

    Handles three shapes:
      - clean JSON
      - markdown-fenced ```json blocks
      - prose with a single JSON object embedded

    Returns {} on failure — callers should treat empty as "LLM didn't
    produce structured output" and use catalog defaults.
    """
    if not text:
        return {}
    s = text
    if "```" in s:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", s)
        if m:
            s = m.group(1)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]+\}", s)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}
