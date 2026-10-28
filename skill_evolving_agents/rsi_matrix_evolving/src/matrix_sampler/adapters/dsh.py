from __future__ import annotations

import asyncio
import os
from pathlib import Path

from matrix_sampler.models import AdapterCapabilities, CanonicalEvent, CanonicalRequest, HealthResult, stable_id, utcnow


DEFAULT_DSH = "/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"


class DSHAdapter:
    """Run one isolated DeepSeek Harness headless turn per sample."""

    name = "dsh"

    def __init__(self, patch: str | Path, binary: str | Path = DEFAULT_DSH, profile: str = "headless", timeout: float = 300, cwd: str | Path | None = None):
        self.binary = str(Path(binary).expanduser())
        self.patch = str(Path(patch).expanduser().resolve())
        self.profile = profile
        self.timeout = timeout
        self.cwd = str(Path(cwd).resolve()) if cwd else None
        self.processes: dict[str, asyncio.subprocess.Process] = {}

    async def health(self):
        healthy = os.access(self.binary, os.X_OK) and Path(self.patch).is_file()
        return HealthResult(healthy, f"binary={self.binary}; patch={self.patch}")

    async def capabilities(self):
        return AdapterCapabilities(streaming=False, cancellation=True, tools=True)

    async def invoke(self, request: CanonicalRequest):
        task = "\n\n".join(str(message.get("content", "")) for message in request.messages)
        prompt = (
            "This is a short capability-evaluation prompt. Answer directly in at most 200 words. "
            "Do not inspect or modify files, run commands, call tools, or create artifacts. "
            "If the prompt is underspecified, state reasonable assumptions briefly.\n\n"
            + task
        )
        command = [self.binary, "--profile", self.profile, "--patch", self.patch, prompt]
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.processes[request.run_id] = proc
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), self.timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        finally:
            self.processes.pop(request.run_id, None)
        text = stdout.decode(errors="replace").strip()
        error = stderr.decode(errors="replace").strip()
        if proc.returncode:
            raise RuntimeError(f"DSH exited {proc.returncode}: {error[:1000]}")
        yield CanonicalEvent(
            1,
            stable_id("evt", [request.run_id, "completed"]),
            request.run_id,
            "response.completed",
            utcnow(),
            {"text": text, "structured": {"success": True}, "stderr": error},
            {"adapter": self.name, "profile": self.profile, "patch": self.patch},
        )

    async def cancel(self, run_id: str):
        proc = self.processes.get(run_id)
        if proc and proc.returncode is None:
            proc.terminate()
