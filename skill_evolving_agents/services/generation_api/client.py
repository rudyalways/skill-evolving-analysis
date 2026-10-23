"""Client for small-LLM and JEV structured generation services."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any


class GenerationServiceError(RuntimeError):
    pass


class GenerationClient:
    def __init__(self, endpoint: str, timeout_ms: int = 5000):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout_ms / 1000

    def generate_json(
        self,
        *,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
        instruction: str,
        model: str | None = None,
        method: str = "json",
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            self.endpoint + "/v1/generate-json",
            data=json.dumps(
                {
                    "input": input_data,
                    "output_schema": output_schema,
                    "instruction": instruction,
                    "model": model,
                    "method": method,
                }
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": uuid.uuid4().hex,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                value = json.loads(response.read().decode())
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as error:
            raise GenerationServiceError(f"generation request failed: {error}") from error
        if not isinstance(value, dict) or not isinstance(value.get("output"), dict):
            raise GenerationServiceError("generation response must contain object output")
        for field in ("request_id", "model_revision", "method"):
            if not isinstance(value.get(field), str) or not value[field]:
                raise GenerationServiceError(f"generation response is missing {field}")
        return value

