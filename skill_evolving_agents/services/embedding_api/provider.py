"""Embedding transport facade: remote API, managed local process, or library."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from .client import EmbeddingClient
from . import server as embedding_server


class EmbeddingProvider:
    def __init__(self, config: dict[str, Any], server_script: Path):
        self.config = config
        self.transport = str(config.get("transport", "remote_api"))
        self.server_script = server_script
        self.process: subprocess.Popen[str] | None = None
        host = str(config.get("host", "127.0.0.1"))
        port = int(config.get("port", 8080))
        endpoint = str(config.get("endpoint") or f"http://{host}:{port}")
        self.endpoint = endpoint.rstrip("/")
        self.client = EmbeddingClient(
            self.endpoint, int(config.get("timeout_ms", 1500))
        )
        if self.transport == "in_process":
            embedding_server.configure_backend(config)

    def start(self) -> None:
        if self.transport != "local_process":
            return
        host = str(self.config.get("host", "127.0.0.1"))
        port = int(self.config.get("port", 8080))
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(self.server_script),
                "--host",
                host,
                "--port",
                str(port),
                "--backend",
                str(self.config.get("backend", "hashing-reference")),
                "--dimensions",
                str(self.config.get("dimensions", 1024)),
                "--device",
                str(self.config.get("device", "cpu")),
                *(
                    ["--model", str(self.config["model"])]
                    if self.config.get("model")
                    else []
                ),
                *(
                    ["--revision", str(self.config["revision"])]
                    if self.config.get("revision")
                    else []
                ),
                *(
                    ["--query-instruction", str(self.config["query_instruction"])]
                    if self.config.get("query_instruction")
                    else []
                ),
            ],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + float(
            self.config.get("startup_timeout_seconds", 10)
        )
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stderr = self.process.stderr.read() if self.process.stderr else ""
                raise RuntimeError(f"local embedding service exited: {stderr.strip()}")
            try:
                with urllib.request.urlopen(self.endpoint + "/healthz", timeout=0.25):
                    return
            except OSError:
                time.sleep(0.05)
        self.stop()
        raise RuntimeError("local embedding service did not become healthy")

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.process.stderr is not None:
            self.process.stderr.close()
        self.process = None

    def __enter__(self) -> "EmbeddingProvider":
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop()

    def embeddings(self, texts: list[str]) -> dict[str, Any]:
        if self.transport == "in_process":
            return self._local("embeddings", texts=texts)
        return self.client.embeddings(texts)

    def classify(
        self, texts: list[str], categories: dict[str, str], *, top_k: int
    ) -> dict[str, Any]:
        if self.transport == "in_process":
            return self._local(
                "results", results=embedding_server.ranked(texts, categories, top_k)
            )
        return self.client.classify(texts, categories, top_k=top_k)

    def search(
        self, queries: list[str], documents: dict[str, str], *, top_k: int
    ) -> dict[str, Any]:
        if self.transport == "in_process":
            return self._local(
                "results", results=embedding_server.ranked(queries, documents, top_k)
            )
        return self.client.search(queries, documents, top_k=top_k)

    def _local(self, key: str, **values: Any) -> dict[str, Any]:
        started = time.perf_counter_ns()
        if key == "embeddings":
            values = {
                "embeddings": [
                    embedding_server.BACKEND.embed(text) for text in values["texts"]
                ]
            }
        return {
            "request_id": "in-process",
            "model": embedding_server.BACKEND.name,
            "model_revision": embedding_server.BACKEND.revision,
            "index_revision": "request-local",
            "service_ms": round((time.perf_counter_ns() - started) / 1e6, 3),
            "transport": self.transport,
            **values,
        }


def validate_embedding_runtime(config: dict[str, Any]) -> None:
    transport = config.get("transport", "remote_api")
    if transport not in {"remote_api", "local_process", "in_process"}:
        raise ValueError(
            "embedding transport must be remote_api, local_process, or in_process"
        )
    if transport == "remote_api" and not isinstance(config.get("endpoint"), str):
        raise ValueError("remote_api embedding transport requires endpoint")
    if transport == "local_process":
        port = config.get("port", 8080)
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError("local_process embedding port must be from 1 to 65535")
    backend = config.get("backend", "hashing-reference")
    if backend not in {"hashing-reference", "sentence-transformers"}:
        raise ValueError("unknown embedding backend")
    if backend == "sentence-transformers":
        for field in ("model", "revision"):
            if not isinstance(config.get(field), str) or not config[field]:
                raise ValueError(
                    f"sentence-transformers embedding backend requires {field}"
                )
        dimensions = config.get("dimensions", 1024)
        if (
            not isinstance(dimensions, int)
            or isinstance(dimensions, bool)
            or not 32 <= dimensions <= 1024
        ):
            raise ValueError("Qwen3-Embedding-0.6B dimensions must be 32..1024")
