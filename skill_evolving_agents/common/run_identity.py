"""Safe validation and resolution for pipeline run identifiers.

Runs are moved to ``<run-id>@YYYY-MM-DDTHH:MM`` after their first start.  The
``@`` was previously rejected outside ``--from``, so an interrupted stamped run
could not be continued through the normal CLI without recreating it.  Validation
here is path-based: the resolved run directory must remain a direct child of the
configured runs root.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

STAMP_SUFFIX = (
    r"@[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2})?(?:-[0-9]+)?"
)
RUN_ID_PATTERN = re.compile(
    rf"^[A-Za-z0-9][A-Za-z0-9_.-]{{0,127}}(?:{STAMP_SUFFIX})?$"
)
STAMPED_PATTERN = re.compile(
    rf"^[A-Za-z0-9][A-Za-z0-9_.-]{{0,127}}{STAMP_SUFFIX}$"
)


def is_stamped(value: str) -> bool:
    return bool(STAMPED_PATTERN.fullmatch(value))


def validate_run_id(value: str, *, require_stamped: bool = False) -> str:
    """Return a normalized run id or raise ``ValueError``.

    Only letters, digits, dot, underscore, dash, and one optional timestamp
    suffix are accepted.  The first character must be alphanumeric so a run id
    cannot become a hidden path or an option.
    """
    if not isinstance(value, str) or not value:
        raise ValueError("run id must be a non-empty string")
    if "/" in value or "\\" in value or ".." in value:
        raise ValueError("run id may not contain path separators or '..'")
    if not RUN_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "run id must be <name> optionally followed by "
            "@YYYY-MM-DDTHH:MM[:SS][-N]"
        )
    if require_stamped and not is_stamped(value):
        raise ValueError("a stamped run id is required, such as name@2026-11-08T20:52")
    if is_stamped(value):
        stamp = value.rsplit("@", 1)[1]
        stamp = re.sub(r"-[0-9]+$", "", stamp)
        try:
            datetime.fromisoformat(stamp)
        except ValueError as error:
            raise ValueError(f"run id has an invalid timestamp: {error}") from error
    return value


def resolve_run_workspace(runs_root: Path, run_id: str) -> Path:
    """Resolve a run id inside ``runs_root`` and reject any escape."""
    identifier = validate_run_id(run_id)
    root = runs_root.resolve()
    candidate = (root / identifier).resolve()
    if candidate.parent != root:
        raise ValueError(f"run id escapes the runs root: {run_id}")
    return candidate


def session_slug(value: str) -> str:
    """Filesystem-safe session label for stamped run ids."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
