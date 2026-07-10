#!/usr/bin/env python3
"""Serve skill-evolving-analysis workspace over HTTP."""

from __future__ import annotations

import argparse
import http.server
import os
import socket
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".md": "text/markdown; charset=utf-8",
        ".yaml": "text/yaml; charset=utf-8",
        ".yml": "text/yaml; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".jsonl": "application/jsonl; charset=utf-8",
    }

    def _redirect_md_to_html(self) -> bool:
        """Browser navigation to *.md → pre-rendered HTML (no raw markdown in UI)."""
        clean = self.path.split("?", 1)[0]
        accept = self.headers.get("Accept", "")
        if not clean.endswith(".md"):
            return False
        if "text/html" not in accept and "*/*" not in accept:
            return False
        rel = clean.lstrip("/")
        is_zh = rel.endswith(".zh.md")
        if is_zh:
            base = rel[: -len(".zh.md")]
            html_rel = f"html/site/zh/{base}.html"
        else:
            html_rel = f"html/site/{rel[:-3]}.html"
        if (ROOT / html_rel).is_file():
            target = f"/{html_rel}"
        else:
            from urllib.parse import quote

            target = f"/html/viewer.html?path={quote(rel)}"
        self.send_response(302)
        self.send_header("Location", target)
        self.end_headers()
        return True

    def do_GET(self) -> None:
        if self._redirect_md_to_html():
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if self._redirect_md_to_html():
            return
        super().do_HEAD()

    def end_headers(self) -> None:
        # Allow local dev fetches if needed
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write(f"[serve] {self.address_string()} - {format % args}\n")


def pick_port(host: str, preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("could not bind to a port")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    os.chdir(ROOT)
    port = pick_port(args.host, args.port)
    server = http.server.ThreadingHTTPServer(
        (args.host, port),
        partial(Handler, directory=str(ROOT)),
    )

    dashboard = f"http://{args.host}:{port}/html/index.html"
    print(f"Serving {ROOT}")
    print(f"Dashboard: {dashboard}")
    print(f"Root:      http://{args.host}:{port}/")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
