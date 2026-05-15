"""
OpenAI embeddings client — minimal HTTP wrapper. (v3 Onda 5)

Direct httpx instead of the OpenAI SDK for the same reason orchestrator_v5
uses raw HTTP: small surface, easy to mock in tests, no SDK version dance.

batch limit: OpenAI accepts up to 2048 input strings per call, but we cap
at 100 to keep request bodies reasonable. Callers that need more should
slice and call repeatedly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import httpx

from core.config import get_settings
from core.logger import get_logger

logger = get_logger()

_MAX_BATCH = 100


@dataclass
class Embedder:
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout: float = 30.0
    http_factory: Optional[object] = None

    @classmethod
    def from_settings(cls) -> "Embedder":
        s = get_settings()
        return cls(
            api_key=s.OPENAI_API_KEY or None,
            model=s.OPENAI_EMBED_MODEL,
        )

    def _http(self):
        if self.http_factory is not None:
            return self.http_factory()
        return httpx.AsyncClient(timeout=self.timeout)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Returns one vector per input text. Empty input → empty list."""
        if not texts:
            return []
        if not self.api_key or self.api_key == "sua-chave-aqui":
            raise ValueError("OPENAI_API_KEY not configured")

        out: list[list[float]] = []
        for chunk_start in range(0, len(texts), _MAX_BATCH):
            chunk = texts[chunk_start : chunk_start + _MAX_BATCH]
            async with self._http() as client:
                r = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self.model, "input": chunk},
                )
                r.raise_for_status()
                data = r.json()
            for item in data.get("data", []):
                out.append(item["embedding"])
        return out


async def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Convenience: build an Embedder from settings and embed once."""
    return await Embedder.from_settings().embed(list(texts))
