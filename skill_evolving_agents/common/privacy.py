"""Deterministic trace DLP and tenant-boundary helpers."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


REDACTED = "[REDACTED]"
SENSITIVE_KEYS = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth(?:orization)?|password|passwd|secret|"
    r"private[_-]?key|client[_-]?secret|cookie|session[_-]?token)$",
    re.IGNORECASE,
)
PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\b(?:sk|pk|api|key)-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+"),
)
TENANT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def redact_text(value: str) -> tuple[str, int]:
    """Redact common credentials and direct identifiers without interpreting text."""
    count = 0
    for pattern in PATTERNS:
        value, matches = pattern.subn(REDACTED, value)
        count += matches
    return value, count


def redact(value: Any, *, key: str | None = None) -> tuple[Any, int]:
    """Recursively redact a JSON-compatible value and return its redaction count."""
    if key and SENSITIVE_KEYS.search(key):
        return REDACTED, 1
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        output, count = [], 0
        for item in value:
            clean, found = redact(item)
            output.append(clean)
            count += found
        return output, count
    if isinstance(value, dict):
        output, count = {}, 0
        for child_key, item in value.items():
            clean, found = redact(item, key=str(child_key))
            output[child_key] = clean
            count += found
        return output, count
    return value, 0


def validate_tenant_id(tenant_id: str) -> str:
    if not TENANT.fullmatch(tenant_id) or tenant_id in {".", ".."}:
        raise ValueError(f"invalid tenant id: {tenant_id!r}")
    return tenant_id


def tenant_root(base: Path, tenant_id: str) -> Path:
    """Resolve a tenant directory and prove it cannot escape the tenant store."""
    tenant_id = validate_tenant_id(tenant_id)
    root = base.resolve()
    target = (root / tenant_id).resolve()
    target.relative_to(root)
    return target


def tenant_fingerprint(tenant_id: str) -> str:
    return hashlib.sha256(validate_tenant_id(tenant_id).encode()).hexdigest()[:16]
