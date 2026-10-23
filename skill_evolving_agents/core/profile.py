"""Load and validate deployment profiles without importing phase code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


MODES = {"enabled", "observe", "passthrough", "disabled"}
KINDS = {"deterministic", "embedding-service", "agent", "skill", "disabled"}
REQUIRED_PHASES = {
    "normalize",
    "detect",
    "semantic_prefilter",
    "diagnosis",
    "recall",
    "goal",
    "optimize",
    "verify",
    "publish",
}


class ProfileError(ValueError):
    """Raised when a deployment profile is unsafe or incomplete."""


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def validate_profile(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileError("profile must be an object")
    if value.get("schema_version") != 1:
        raise ProfileError("profile schema_version must be 1")
    if not isinstance(value.get("name"), str) or not value["name"].strip():
        raise ProfileError("profile name must be a non-empty string")
    phases = value.get("phases")
    if not isinstance(phases, dict):
        raise ProfileError("profile phases must be an object")
    missing = REQUIRED_PHASES - set(phases)
    if missing:
        raise ProfileError(f"profile is missing phases: {', '.join(sorted(missing))}")
    for phase, config in phases.items():
        if not isinstance(config, dict):
            raise ProfileError(f"phase {phase} must be an object")
        mode = config.get("mode")
        kind = config.get("kind")
        if mode not in MODES:
            raise ProfileError(f"phase {phase} has invalid mode {mode!r}")
        if kind not in KINDS:
            raise ProfileError(f"phase {phase} has invalid kind {kind!r}")
        if mode == "disabled" and kind != "disabled":
            raise ProfileError(f"disabled phase {phase} must use kind 'disabled'")
        if phase == "publish" and (kind != "deterministic" or mode != "enabled"):
            raise ProfileError("publish must remain deterministic and enabled")
        if phase in {"semantic_prefilter", "recall"} and kind == "embedding-service":
            reject = config.get("reject_below")
            accept = config.get("accept_at")
            if not isinstance(reject, (int, float)) or isinstance(reject, bool):
                raise ProfileError(f"phase {phase} requires numeric reject_below")
            if not isinstance(accept, (int, float)) or isinstance(accept, bool):
                raise ProfileError(f"phase {phase} requires numeric accept_at")
            if not -1 <= float(reject) < float(accept) <= 1:
                raise ProfileError(
                    f"phase {phase} thresholds must satisfy -1 <= reject_below "
                    "< accept_at <= 1"
                )
            for field in ("noise_accept_at", "minimum_margin", "minimum_score"):
                optional = config.get(field)
                if optional is None:
                    continue
                if not isinstance(optional, (int, float)) or isinstance(optional, bool):
                    raise ProfileError(f"phase {phase} requires numeric {field}")
                lower = 0.0 if field != "minimum_score" else -1.0
                if not lower <= float(optional) <= 1.0:
                    raise ProfileError(
                        f"phase {phase} {field} must be between {lower:g} and 1"
                    )
    normalized = json.loads(json.dumps(value))
    normalized["config_digest"] = _digest(value)
    return normalized


def load_profile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as error:
        raise ProfileError(f"profile not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ProfileError(f"invalid profile JSON {path}: {error}") from error
    return validate_profile(value)


def resolve_profile(root: Path, name_or_path: str) -> tuple[Path, dict[str, Any]]:
    candidate = Path(name_or_path)
    if candidate.is_absolute() or candidate.parent != Path(".") or candidate.is_file():
        path = candidate
    else:
        filename = name_or_path if candidate.suffix == ".json" else f"{name_or_path}.json"
        path = root / "profiles" / filename
    return path.resolve(), load_profile(path.resolve())

