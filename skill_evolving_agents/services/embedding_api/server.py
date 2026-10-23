#!/usr/bin/env python3
"""Reference embedding service; swap HashingBackend for a managed model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


TOKEN = re.compile(r"[\w-]+", re.UNICODE)


class HashingBackend:
    """Small deterministic reference backend, not a semantic production model."""

    name = "hashing-reference"
    revision = "1"

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN.findall(text.casefold()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += -1.0 if digest[4] & 1 else 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def embed_query(self, text: str) -> list[float]:
        return self.embed(text)


class SentenceTransformerBackend:
    """Lazy local backend for the selected Qwen embedding model."""

    def __init__(
        self,
        model: str,
        revision: str,
        *,
        device: str = "cpu",
        dimensions: int = 1024,
        query_instruction: str = "Retrieve the relevant skill or finding for this query",
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "sentence-transformers is required for the qwen backend"
            ) from error
        self.name = model
        self.revision = revision
        self.dimensions = dimensions
        self.query_instruction = query_instruction
        self.model = SentenceTransformer(
            model,
            revision=revision,
            device=device,
            trust_remote_code=True,
        )

    def _encode(self, text: str) -> list[float]:
        vector = self.model.encode(
            [text],
            normalize_embeddings=True,
            truncate_dim=self.dimensions,
            show_progress_bar=False,
        )[0]
        return [float(value) for value in vector]

    def embed(self, text: str) -> list[float]:
        return self._encode(text)

    def embed_query(self, text: str) -> list[float]:
        instructed = f"Instruct: {self.query_instruction}\nQuery: {text}"
        return self._encode(instructed)


BACKEND = HashingBackend()


def configure_backend(config: dict[str, Any]) -> None:
    global BACKEND
    backend = config.get("backend", "hashing-reference")
    if backend == "hashing-reference":
        BACKEND = HashingBackend(int(config.get("dimensions", 256)))
        return
    if backend == "sentence-transformers":
        BACKEND = SentenceTransformerBackend(
            str(config["model"]),
            str(config["revision"]),
            device=str(config.get("device", "cpu")),
            dimensions=int(config.get("dimensions", 1024)),
            query_instruction=str(
                config.get(
                    "query_instruction",
                    "Retrieve the relevant skill or finding for this query",
                )
            ),
        )
        return
    raise ValueError(f"unknown embedding backend {backend!r}")


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def ranked(queries: list[str], candidates: dict[str, str], top_k: int) -> list[dict[str, Any]]:
    candidate_vectors = {key: BACKEND.embed(text) for key, text in candidates.items()}
    output = []
    for query in queries:
        vector = BACKEND.embed_query(query)
        matches = sorted(
            (
                {"id": key, "score": round(cosine(vector, candidate), 6)}
                for key, candidate in candidate_vectors.items()
            ),
            key=lambda row: (-row["score"], row["id"]),
        )[:top_k]
        output.append({"matches": matches})
    return output


class Handler(BaseHTTPRequestHandler):
    server_version = "SkillEvolverEmbedding/1"

    def _write(self, status: int, value: dict[str, Any]) -> None:
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._write(200, {"status": "ok", "model_revision": BACKEND.revision})
        elif self.path == "/v1/models":
            self._write(200, {"models": [{"name": BACKEND.name, "revision": BACKEND.revision, "dimensions": BACKEND.dimensions}]})
        else:
            self._write(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        started = time.perf_counter_ns()
        request_id = self.headers.get("X-Request-ID") or uuid.uuid4().hex
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 2_000_000:
                raise ValueError("request size must be between 1 and 2000000 bytes")
            payload = json.loads(self.rfile.read(size))
            texts = payload.get("texts") if self.path != "/v1/search" else payload.get("queries")
            if not isinstance(texts, list) or not texts or not all(isinstance(text, str) for text in texts):
                raise ValueError("texts or queries must be a non-empty string array")
            if self.path == "/v1/embeddings":
                data: Any = [BACKEND.embed(text) for text in texts]
                key = "embeddings"
            elif self.path in {"/v1/classify", "/v1/search"}:
                candidates = payload.get("categories" if self.path == "/v1/classify" else "documents")
                if not isinstance(candidates, dict) or not candidates or not all(isinstance(k, str) and isinstance(v, str) for k, v in candidates.items()):
                    raise ValueError("categories or documents must be a non-empty string map")
                top_k = int(payload.get("top_k", 5))
                if top_k < 1 or top_k > 100:
                    raise ValueError("top_k must be between 1 and 100")
                data = ranked(texts, candidates, top_k)
                key = "results"
            else:
                self._write(404, {"error": "not_found", "request_id": request_id})
                return
            self._write(200, {"request_id": request_id, "model": BACKEND.name, "model_revision": BACKEND.revision, "index_revision": "request-local", "service_ms": round((time.perf_counter_ns() - started) / 1e6, 3), key: data})
        except (ValueError, json.JSONDecodeError) as error:
            self._write(400, {"error": str(error), "request_id": request_id})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend", default="hashing-reference")
    parser.add_argument("--model")
    parser.add_argument("--revision")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--dimensions", type=int, default=1024)
    parser.add_argument(
        "--query-instruction",
        default="Retrieve the relevant skill or finding for this query",
    )
    args = parser.parse_args()
    config = vars(args)
    if args.backend != "hashing-reference" and (not args.model or not args.revision):
        parser.error("non-reference backend requires --model and --revision")
    configure_backend(config)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

