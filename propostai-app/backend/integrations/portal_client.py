"""
Portal client — integracao com a plataforma AI Garage.
LLM, billing, provisioning.
"""
import httpx

from core.config import get_settings
from core.logger import get_logger

settings = get_settings()
logger = get_logger()


class PortalClient:
    """Client para comunicacao com Portal."""

    def __init__(self):
        self.base_url = settings.PORTAL_API_URL
        self.api_key = settings.PORTAL_API_KEY
        self.timeout = settings.SAP_AGENT_TIMEOUT_SECONDS

    async def execute_agent_task(self, task: str, payload: dict) -> dict:
        """Envia tarefa para o Agent Hub (LLM)."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/v1/external-chat/message",
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "message": str(payload),
                    "metadata": {"task": task},
                },
            )
            r.raise_for_status()
            return r.json()

    async def get_subscription(self, tenant_id: str) -> dict:
        """Consulta subscription do tenant no Portal."""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{self.base_url}/api/v1/billing/subscription/{tenant_id}",
                headers={"X-API-Key": self.api_key},
            )
            r.raise_for_status()
            return r.json()

    async def report_usage(self, tenant_id: str, metric: str, value: int) -> None:
        """Reporta uso ao Portal."""
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self.base_url}/api/v1/billing/usage",
                headers={"X-API-Key": self.api_key},
                json={"tenant_id": tenant_id, "metric": metric, "value": value},
            )


def get_portal_client() -> PortalClient:
    return PortalClient()
