"""Dependency-free client for the embedding service protocol."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any


class EmbeddingServiceError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(self, endpoint: str, timeout_ms: int = 1500):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout_ms / 1000

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        request = urllib.request.Request(
            self.endpoint + path,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": request_id,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                value = json.loads(response.read().decode())
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as error:
            raise EmbeddingServiceError(f"embedding request failed: {error}") from error
        if not isinstance(value, dict) or not value.get("model_revision"):
            raise EmbeddingServiceError("embedding response is missing model_revision")
        return value

    def embeddings(self, texts: list[str], model: str | None = None) -> dict[str, Any]:
        return self._post("/v1/embeddings", {"texts": texts, "model": model})

    def classify(
        self, texts: list[str], categories: dict[str, str], *, top_k: int = 5
    ) -> dict[str, Any]:
        return self._post(
            "/v1/classify",
            {"texts": texts, "categories": categories, "top_k": top_k},
        )

    def search(
        self, queries: list[str], documents: dict[str, str], *, top_k: int = 10
    ) -> dict[str, Any]:
        return self._post(
            "/v1/search",
            {"queries": queries, "documents": documents, "top_k": top_k},
        )

