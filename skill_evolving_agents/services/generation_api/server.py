#!/usr/bin/env python3
"""Reference tier-2 API server for integration tests and provider adapters."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class Handler(BaseHTTPRequestHandler):
    server_version = "SkillEvolverGeneration/1"

    def _write(self, status: int, value: dict[str, Any]) -> None:
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._write(200, {"status": "ok", "model_revision": "reference-1"})
        else:
            self._write(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        request_id = self.headers.get("X-Request-ID") or uuid.uuid4().hex
        started = time.perf_counter_ns()
        if self.path != "/v1/generate-json":
            self._write(404, {"error": "not_found", "request_id": request_id})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 2_000_000:
                raise ValueError("invalid request size")
            value = json.loads(self.rfile.read(size))
            method = value.get("method", "json")
            if method not in {"json", "jev"}:
                raise ValueError("method must be json or jev")
            # The reference provider deliberately performs no model inference.
            # A caller may supply a fixture output only for protocol/e2e tests.
            output = value.get("input", {}).get("_reference_output")
            if not isinstance(output, dict):
                raise ValueError(
                    "reference server requires input._reference_output; "
                    "configure a real small-model provider for inference"
                )
            self._write(
                200,
                {
                    "request_id": request_id,
                    "model": "reference-no-inference",
                    "model_revision": "reference-1",
                    "method": method,
                    "service_ms": round((time.perf_counter_ns() - started) / 1e6, 3),
                    "output": output,
                    "usage": {"input_tokens": None, "output_tokens": None, "cost_usd": 0},
                },
            )
        except (ValueError, json.JSONDecodeError) as error:
            self._write(400, {"error": str(error), "request_id": request_id})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

