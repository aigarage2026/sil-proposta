"""
Base agent — classe base para todos os agentes SAP.
Cada agente herda e implementa _system_prompt() e _parse_result().
"""
import json
import re
import time

from core.config import get_settings
from core.logger import get_logger

settings = get_settings()
logger = get_logger()


class BaseAgent:
    """Agente base com chamada LLM, parsing JSON e logging."""

    name: str = "Base"
    agent_id: str = "base"

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def _system_prompt(self) -> str:
        raise NotImplementedError

    def _parse_result(self, raw: dict) -> dict:
        return raw

    async def execute(self, context: str, rag_context: str = "") -> dict:
        """Executa o agente: chama LLM, parseia JSON, loga."""
        start = time.monotonic()
        user_msg = context
        if rag_context:
            user_msg += f"\n\nCONTEXTO RAG:\n{rag_context[:800]}"

        try:
            result = self._call_llm(self._system_prompt(), user_msg)
            parsed = self._parse_result(result)
            duration = int((time.monotonic() - start) * 1000)
            logger.info(f"Agent {self.name} completed", duration_ms=duration)
            return parsed
        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            logger.error(f"Agent {self.name} failed", error=str(e), duration_ms=duration)
            raise

    def _call_llm(self, system: str, user: str) -> dict:
        """Chama Claude e parseia resposta JSON."""
        resp = self._get_client().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = resp.content[0].text.strip()

        # Limpar markdown
        if "```" in text:
            m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
            if m:
                text = m.group(1)

        return json.loads(text)
