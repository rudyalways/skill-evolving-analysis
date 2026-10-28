from __future__ import annotations

import asyncio
import json
import os
import tempfile

from matrix_sampler.models import AdapterCapabilities, CanonicalEvent, CanonicalRequest, HealthResult, stable_id, utcnow


class CLIHarnessAdapter:
    name = "cli_harness"

    def __init__(self, argv: list[str], timeout: float = 300, env_allowlist: list[str] | None = None):
        self.argv, self.timeout, self.env_allowlist, self.processes = argv, timeout, env_allowlist or [], {}

    async def health(self): return HealthResult(bool(self.argv), "argv configured")
    async def capabilities(self): return AdapterCapabilities(True, True, True)

    async def invoke(self, request: CanonicalRequest):
        env = {k: os.environ[k] for k in self.env_allowlist if k in os.environ}
        env["PATH"] = os.environ.get("PATH", "")
        with tempfile.TemporaryDirectory(prefix="matrix-sampler-") as cwd:
            proc = await asyncio.create_subprocess_exec(*self.argv, cwd=cwd, env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            self.processes[request.run_id] = proc
            payload = json.dumps({"messages": request.messages, "metadata": request.metadata}).encode()
            try: stdout, stderr = await asyncio.wait_for(proc.communicate(payload), self.timeout)
            except TimeoutError:
                proc.kill(); await proc.wait(); raise
            finally: self.processes.pop(request.run_id, None)
            for i, line in enumerate(stdout.decode(errors="replace").splitlines()):
                try: data = json.loads(line)
                except json.JSONDecodeError: data = {"text": line}
                yield CanonicalEvent(1, stable_id("evt", [request.run_id, i]), request.run_id, data.pop("event_type", "response.completed"), utcnow(), data, {"adapter": self.name})
            if proc.returncode: raise RuntimeError(f"CLI exited {proc.returncode}: {stderr.decode(errors='replace')[:500]}")

    async def cancel(self, run_id: str):
        proc = self.processes.get(run_id)
        if proc and proc.returncode is None: proc.terminate()

