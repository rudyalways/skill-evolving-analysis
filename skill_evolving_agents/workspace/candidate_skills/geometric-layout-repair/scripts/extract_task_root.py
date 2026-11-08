#!/usr/bin/env python3
"""One-command task-root adapter for the architectural DXF extractor.

The adapter resolves the conventional harness layout once:

    <task-root>/input/<plan>.dxf
    <task-root>/input/layer_schema.json
    <task-root>/input/plan_view_rules.json
        or a single <task-root>/input/*_rules.json such as ada_rules.json

It normalizes nested extractor rules and flat benchmark aliases (``unit`` /
``units``, ``turning_space.diameter``, ``turning_circle_diameter_min``, and
``plan_requirements.turning_space.diameter_min``), then invokes
``extract_architectural_dxf.py`` with the bundled normalization schema
(``scripts/schemas/normalized_extraction.schema.json``) and writes the
normalized document to ``output/extracted_geometry.json`` plus an execution
receipt to ``output/extraction_receipt.json``.

The task root's ``output_schema/`` directory, when present, describes final
deliverables and is deliberately ignored; it is not an extractor schema.  The
adapter never generates an ad-hoc probe or a replacement schema.  A missing
conventional input is one ``missing_conventional_input`` failure, and an
unsupported entity is the extractor's single terminal diagnostic.  Neither
failure publishes a normalized document or a receipt.

The child interpreter is resolved portably: ``sys.executable`` is used only
when it is non-empty and executable, otherwise ``python3`` and then ``python``
are discovered on ``PATH``.  The receipt records the interpreter actually
used, so an embedded or relocatable harness cannot silently skip the bundled
extractor.

Usage:
    python3 scripts/extract_task_root.py [<task-root>] [--output PATH]
        [--receipt PATH] [--extractor PATH]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

INPUT_DIR = "input"
OUTPUT_DIR = "output"
NORMALIZED_JSON_FILE = "extracted_geometry.json"
RECEIPT_FILE = "extraction_receipt.json"
LAYER_SCHEMA_FILE = "layer_schema.json"
RULES_FILE = "plan_view_rules.json"
BUNDLED_SCHEMA = Path(__file__).resolve().parent / "schemas" / (
    "normalized_extraction.schema.json"
)


class AdapterFailure(Exception):
    """One explicit terminal failure with a machine-readable payload."""

    def __init__(self, code: int, error: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.payload: dict[str, Any] = {
            "error": error,
            "message": message,
            **details,
        }

    def emit(self) -> int:
        print(json.dumps(self.payload, sort_keys=True), file=sys.stderr)
        return self.code


def _is_executable_file(candidate: str) -> bool:
    return bool(candidate) and os.path.isfile(candidate) and os.access(
        candidate, os.X_OK
    )


def resolve_python_interpreter() -> str:
    """Return a usable child interpreter without assuming ``sys.executable``.

    ``sys.executable`` is empty in an embedded interpreter and can point at a
    non-executable stub in a relocatable harness.  Use it only when it is a
    real executable; otherwise fall back to ``python3`` and then ``python`` on
    ``PATH`` so the bundled extractor still runs as a child process.
    """
    if _is_executable_file(sys.executable):
        return sys.executable
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found and _is_executable_file(found):
            return found
    raise AdapterFailure(
        2,
        "missing_python_interpreter",
        "no executable Python interpreter: sys.executable is empty or "
        "non-executable and neither python3 nor python is on PATH",
        mode="task-root-adapter",
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _record(path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": _relative(path, root),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _missing(root: Path, expected: str) -> AdapterFailure:
    return AdapterFailure(
        2,
        "missing_conventional_input",
        f"task root {root} is missing conventional input {expected}",
        mode="task-root-adapter",
        task_root=root.as_posix(),
        missing_input=expected,
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_rules(rules: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Map flat benchmark aliases onto the extractor's nested rules shape."""
    normalized = copy.deepcopy(rules)
    aliases: list[str] = []
    if "units" not in normalized and "unit" in normalized:
        normalized["units"] = normalized["unit"]
        aliases.append("unit -> units")

    turning = normalized.get("turning_space")
    if not isinstance(turning, dict):
        turning = None
    solver_keys = (
        "wall_clearance",
        "search_step",
        "max_candidates",
        "max_grid_points",
        "allowed_overlap_layers",
    )
    if turning is None:
        flat_solver = {
            key: normalized[key] for key in solver_keys if key in normalized
        }
        if flat_solver:
            turning = flat_solver
            normalized["turning_space"] = turning

    candidates: list[tuple[str, int | float]] = []
    if turning is not None and _is_number(turning.get("diameter_min")):
        candidates.append(
            (
                "turning_space.diameter_min -> turning_space.diameter",
                turning["diameter_min"],
            )
        )
    if _is_number(normalized.get("turning_circle_diameter_min")):
        candidates.append(
            (
                "turning_circle_diameter_min -> turning_space.diameter",
                normalized["turning_circle_diameter_min"],
            )
        )
    if _is_number(normalized.get("turning_space.diameter_min")):
        candidates.append(
            (
                "turning_space.diameter_min -> turning_space.diameter",
                normalized["turning_space.diameter_min"],
            )
        )
    if _is_number(normalized.get("turning_space.diameter")):
        candidates.append(
            (
                "turning_space.diameter -> turning_space.diameter",
                normalized["turning_space.diameter"],
            )
        )
    plan = normalized.get("plan_requirements")
    plan_turning = plan.get("turning_space") if isinstance(plan, dict) else None
    plan_diameter = (
        plan_turning.get("diameter_min")
        if isinstance(plan_turning, dict)
        else None
    )
    if _is_number(plan_diameter):
        candidates.append(
            (
                "plan_requirements.turning_space.diameter_min"
                " -> turning_space.diameter",
                plan_diameter,
            )
        )
    if isinstance(plan_turning, dict) and _is_number(
        plan_turning.get("diameter")
    ):
        candidates.append(
            (
                "plan_requirements.turning_space.diameter"
                " -> turning_space.diameter",
                plan_turning["diameter"],
            )
        )
    if _is_number(normalized.get("plan_requirements.turning_space.diameter_min")):
        candidates.append(
            (
                "plan_requirements.turning_space.diameter_min"
                " -> turning_space.diameter",
                normalized["plan_requirements.turning_space.diameter_min"],
            )
        )
    if _is_number(normalized.get("plan_requirements.turning_space.diameter")):
        candidates.append(
            (
                "plan_requirements.turning_space.diameter"
                " -> turning_space.diameter",
                normalized["plan_requirements.turning_space.diameter"],
            )
        )

    chosen: int | float | None = None
    if turning is not None and _is_number(turning.get("diameter")):
        chosen = turning["diameter"]
    elif candidates:
        chosen = candidates[0][1]
        if turning is None:
            turning = {}
            normalized["turning_space"] = turning
        turning["diameter"] = chosen
    if chosen is not None:
        aliases.extend(
            label for label, value in candidates if value == chosen
        )
    return normalized, aliases


ROLE_BY_LAYER_TYPE = {
    "wall": "room",
    "walls": "room",
    "space_boundary": "room",
    "space-boundary": "room",
    "spaceboundary": "room",
    "room": "room",
    "rooms": "room",
    "door": "door",
    "doors": "door",
    "door_opening": "door",
    "toilet": "fixture",
    "wc": "fixture",
    "water_closet": "fixture",
    "lavatory": "fixture",
    "lav": "fixture",
    "bathtub": "fixture",
    "tub": "fixture",
    "fixture": "fixture",
    "fixtures": "fixture",
    "grab_bar": "grab_bar",
    "grab-bar": "grab_bar",
    "grabbar": "grab_bar",
    "grab_bars": "grab_bar",
    "annotation": "ignore",
    "annotations": "ignore",
    "text": "ignore",
    "label": "ignore",
    "dimension": "ignore",
    "dimensions": "ignore",
    "dim": "ignore",
    "ignore": "ignore",
}

FIXTURE_TYPE_BY_LAYER_TYPE = {
    "toilet": "wc",
    "wc": "wc",
    "water_closet": "wc",
    "lavatory": "lav",
    "lav": "lav",
    "bathtub": "tub",
    "tub": "tub",
}

LAYER_METADATA_KEYS = {
    "canonical",
    "aliases",
    "version",
    "schema_version",
    "units",
    "unit",
}


def _canonical_type(definition: dict[str, Any]) -> Optional[str]:
    for key in ("type", "layer_type", "canonical_type", "kind", "semantic_role"):
        value = definition.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower().replace(" ", "_")
    canonical = definition.get("canonical")
    if isinstance(canonical, str) and canonical.strip().lower() in ROLE_BY_LAYER_TYPE:
        return canonical.strip().lower().replace(" ", "_")
    return None


VALID_ROLES = {"room", "door", "fixture", "grab_bar", "ignore"}


def _layer_role(definition: dict[str, Any]) -> Optional[str]:
    role = definition.get("role")
    if isinstance(role, str) and role.strip():
        clean = role.strip().lower().replace(" ", "_")
        if clean in VALID_ROLES:
            return clean
        mapped = ROLE_BY_LAYER_TYPE.get(clean)
        if mapped is not None:
            return mapped
    layer_type = _canonical_type(definition)
    if layer_type is not None:
        return ROLE_BY_LAYER_TYPE.get(layer_type)
    return None


def _fixture_type(
    name: str, definition: dict[str, Any], layer_type: Optional[str]
) -> Optional[str]:
    explicit = definition.get("fixture_type")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if layer_type in FIXTURE_TYPE_BY_LAYER_TYPE:
        return FIXTURE_TYPE_BY_LAYER_TYPE[layer_type]
    canonical = definition.get("canonical")
    if isinstance(canonical, str):
        key = canonical.strip().lower().replace(" ", "_")
        if key in FIXTURE_TYPE_BY_LAYER_TYPE:
            return FIXTURE_TYPE_BY_LAYER_TYPE[key]
    key = name.strip().lower().replace(" ", "_")
    if key in FIXTURE_TYPE_BY_LAYER_TYPE:
        return FIXTURE_TYPE_BY_LAYER_TYPE[key]
    if key.startswith("a-") and key[2:] in FIXTURE_TYPE_BY_LAYER_TYPE:
        return FIXTURE_TYPE_BY_LAYER_TYPE[key[2:]]
    return None


def _alias_names(definition: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for key in ("aliases", "alias", "names", "layer_names"):
        value = definition.get(key)
        if isinstance(value, str):
            aliases.append(value)
        elif isinstance(value, list):
            aliases.extend(
                item for item in value if isinstance(item, str) and item.strip()
            )
    canonical = definition.get("canonical")
    if isinstance(canonical, str) and canonical.strip():
        aliases.append(canonical)
    return [alias.strip() for alias in aliases if alias.strip()]


def _expand_layer_schema(
    layer_schema: Any,
) -> tuple[dict[str, Any], list[str]]:
    """Expand type/canonical/aliases layer schemas into role/fixture_type records.

    Every source layer name is retained and every canonical name and alias is
    duplicated as its own record.  This keeps the extractor's simple contract
    while accepting the common harness layer-schema dialects.
    """
    if not isinstance(layer_schema, dict):
        return layer_schema, []
    raw_layers = layer_schema.get("layers")
    if isinstance(raw_layers, list):
        raw_layers = {
            str(entry.get("name") or entry.get("layer")): entry
            for entry in raw_layers
            if isinstance(entry, dict)
            and isinstance(entry.get("name") or entry.get("layer"), str)
        }
    if not isinstance(raw_layers, dict):
        nested = layer_schema.get("layer_schema")
        if isinstance(nested, dict):
            nested_layers = nested.get("layers")
            raw_layers = (
                nested_layers if isinstance(nested_layers, dict) else nested
            )
    if not isinstance(raw_layers, dict):
        raw_layers = {
            name: definition
            for name, definition in layer_schema.items()
            if name not in LAYER_METADATA_KEYS and isinstance(definition, dict)
        }
    mapping: dict[str, Any] = {}
    expanded: list[str] = []

    def add_record(name: str, definition: dict[str, Any]) -> None:
        role = _layer_role(definition)
        if role is None:
            return
        layer_type = _canonical_type(definition)
        record = {
            "role": role,
            "fixture_type": _fixture_type(name, definition, layer_type),
        }
        mapping[name] = record
        if name.upper() != name:
            mapping[name.upper()] = record

    for name, definition in raw_layers.items():
        if not isinstance(name, str) or not isinstance(definition, dict):
            continue
        add_record(name, definition)
        for alias in _alias_names(definition):
            if alias in raw_layers:
                continue
            add_record(alias, definition)
            expanded.append(f"{alias} -> {name}")

    top_aliases = layer_schema.get("aliases")
    if isinstance(top_aliases, dict):
        for alias, target in top_aliases.items():
            if not isinstance(alias, str):
                continue
            if isinstance(target, str) and target in raw_layers:
                add_record(alias, raw_layers[target])
                expanded.append(f"{alias} -> {target}")
            elif isinstance(target, list):
                for alias_name in target:
                    if isinstance(alias_name, str) and alias in raw_layers:
                        add_record(alias_name, raw_layers[alias])
                        expanded.append(f"{alias_name} -> {alias}")

    top_canonical = layer_schema.get("canonical")
    if isinstance(top_canonical, dict):
        for name, target in top_canonical.items():
            if not isinstance(name, str) or not isinstance(target, str):
                continue
            if target in raw_layers and name not in raw_layers:
                add_record(name, raw_layers[target])
                expanded.append(f"{name} -> {target}")
            elif name in raw_layers and target not in raw_layers:
                add_record(target, raw_layers[name])
                expanded.append(f"{target} -> {name}")

    if not mapping:
        return layer_schema, []
    return {"layers": mapping}, expanded


def _load_layer_schema(
    path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    try:
        layer_schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterFailure(
            2,
            "invalid_configuration",
            f"cannot read layer schema {path}: {error}",
            mode="task-root-adapter",
            input=path.as_posix(),
        ) from error
    if not isinstance(layer_schema, dict):
        raise AdapterFailure(
            2,
            "invalid_configuration",
            f"layer schema {path} must be a JSON object",
            mode="task-root-adapter",
            input=path.as_posix(),
        )
    normalized, aliases = _expand_layer_schema(layer_schema)
    return layer_schema, normalized, aliases


def _load_rules(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterFailure(
            2,
            "invalid_configuration",
            f"cannot read plan-view rules {path}: {error}",
            mode="task-root-adapter",
            input=path.as_posix(),
        ) from error
    if not isinstance(rules, dict):
        raise AdapterFailure(
            2,
            "invalid_configuration",
            f"plan-view rules {path} must be a JSON object",
            mode="task-root-adapter",
            input=path.as_posix(),
        )
    return _normalize_rules(rules)


def _discover(root: Path) -> tuple[Path, Path, Path]:
    """Resolve exactly one DXF, layer schema, and rules file under input/."""
    input_dir = root / INPUT_DIR
    if not input_dir.is_dir():
        raise _missing(root, f"{INPUT_DIR}/<plan>.dxf")

    dxf_candidates = sorted(
        path for path in input_dir.glob("*.dxf") if path.is_file()
    )
    if not dxf_candidates:
        raise _missing(root, f"{INPUT_DIR}/<plan>.dxf")
    if len(dxf_candidates) > 1:
        raise AdapterFailure(
            2,
            "ambiguous_conventional_input",
            f"task root {root} contains {len(dxf_candidates)} DXF inputs under "
            f"{INPUT_DIR}/; the conventional contract requires exactly one",
            mode="task-root-adapter",
            task_root=root.as_posix(),
            dxf_candidates=[path.name for path in dxf_candidates],
        )
    dxf = dxf_candidates[0]

    layer_schema = input_dir / LAYER_SCHEMA_FILE
    if not layer_schema.is_file():
        raise _missing(root, f"{INPUT_DIR}/{LAYER_SCHEMA_FILE}")

    preferred = input_dir / RULES_FILE
    if preferred.is_file():
        rules = preferred
    else:
        rules_candidates = sorted(
            path for path in input_dir.glob("*_rules.json") if path.is_file()
        )
        if not rules_candidates:
            raise _missing(
                root, f"{INPUT_DIR}/{RULES_FILE} or {INPUT_DIR}/*_rules.json"
            )
        if len(rules_candidates) > 1:
            raise AdapterFailure(
                2,
                "ambiguous_conventional_input",
                f"task root {root} contains {len(rules_candidates)} rule files "
                f"under {INPUT_DIR}/ and no {RULES_FILE}",
                mode="task-root-adapter",
                task_root=root.as_posix(),
                rules_candidates=[path.name for path in rules_candidates],
            )
        rules = rules_candidates[0]
    return dxf, layer_schema, rules


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _resolve_task_root(root: Path) -> Path:
    """Resolve a task root or a conventional input/ or output/ directory.

    Only the conventional parent layout is accepted; the adapter never scans
    sibling or alternate roots for plausible-looking inputs.
    """
    root = root.resolve()
    if (root / INPUT_DIR).is_dir():
        return root
    if root.name in (INPUT_DIR, OUTPUT_DIR) and (root.parent / INPUT_DIR).is_dir():
        return root.parent
    return root


def extract(
    root: Path,
    output: Optional[Path] = None,
    receipt: Optional[Path] = None,
    extractor: Optional[Path] = None,
) -> dict[str, Any]:
    """Run the existing extractor once and write an execution receipt."""
    root = _resolve_task_root(root)
    dxf, layer_schema_path, rules = _discover(root)
    source_layer_schema, normalized_layers, layer_aliases = _load_layer_schema(
        layer_schema_path
    )
    normalized_layers_text = json.dumps(
        normalized_layers, sort_keys=True, separators=(",", ":")
    )
    normalized_rules, rules_aliases = _load_rules(rules)
    normalized_rules_text = json.dumps(
        normalized_rules, sort_keys=True, separators=(",", ":")
    )
    extractor_path = (
        extractor.resolve()
        if extractor is not None
        else Path(__file__).resolve().parent / "extract_architectural_dxf.py"
    )
    if not extractor_path.is_file():
        raise AdapterFailure(
            2,
            "missing_extractor",
            f"bundled extractor not found at {extractor_path}",
            mode="task-root-adapter",
            task_root=root.as_posix(),
        )
    if not BUNDLED_SCHEMA.is_file():
        raise AdapterFailure(
            2,
            "missing_bundled_schema",
            f"bundled normalization schema not found at {BUNDLED_SCHEMA}",
            mode="task-root-adapter",
            task_root=root.as_posix(),
        )

    normalized_path = output or (root / OUTPUT_DIR / NORMALIZED_JSON_FILE)
    receipt_path = receipt or (root / OUTPUT_DIR / RECEIPT_FILE)
    python_interpreter = resolve_python_interpreter()
    command = [
        python_interpreter,
        str(extractor_path),
        str(dxf),
        "--layer-schema",
        normalized_layers_text,
        "--output-schema",
        str(BUNDLED_SCHEMA),
        "--plan-view-rules",
        normalized_rules_text,
        "--output",
        str(normalized_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        diagnostic = result.stderr.strip()
        if not diagnostic:
            diagnostic = json.dumps(
                {
                    "error": "extractor_failed",
                    "message": f"extractor exited {result.returncode} without a diagnostic",
                },
                sort_keys=True,
            )
        print(diagnostic, file=sys.stderr)
        return result.returncode

    if not normalized_path.is_file():
        raise AdapterFailure(
            2,
            "extractor_missing_output",
            f"extractor reported success but wrote no {normalized_path}",
            mode="task-root-adapter",
            task_root=root.as_posix(),
        )
    try:
        normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterFailure(
            2,
            "extractor_output_unreadable",
            f"normalized output is not valid JSON: {error}",
            mode="task-root-adapter",
            task_root=root.as_posix(),
        ) from error
    if not isinstance(normalized, dict):
        raise AdapterFailure(
            2,
            "extractor_output_unreadable",
            "normalized output is not a JSON object",
            mode="task-root-adapter",
            task_root=root.as_posix(),
        )

    normalized_record = _record(normalized_path, root)
    receipt_relative = _relative(receipt_path, root)
    receipt_payload: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "success",
        "mode": "task-root-adapter",
        "invocation": {
            "adapter": _relative(Path(__file__), root),
            "adapter_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "extractor": _relative(extractor_path, root),
            "extractor_sha256": hashlib.sha256(
                extractor_path.read_bytes()
            ).hexdigest(),
            "child_interpreter": python_interpreter,
            "child_interpreter_source": (
                "sys.executable"
                if python_interpreter == sys.executable
                else "PATH"
            ),
            "arguments": [str(arg) for arg in [sys.argv[0], *sys.argv[1:]]],
            "extractor_command": [str(arg) for arg in command],
        },
        "inputs": {
            "dxf": _record(dxf, root),
            "layer_schema": _record(layer_schema_path, root),
            "plan_view_rules": _record(rules, root),
            "output_schema": _record(BUNDLED_SCHEMA, root),
        },
        "layer_schema_normalization": {
            "source": _relative(layer_schema_path, root),
            "normalized_sha256": hashlib.sha256(
                normalized_layers_text.encode("utf-8")
            ).hexdigest(),
            "source_layer_count": len(
                source_layer_schema.get("layers", source_layer_schema)
                if isinstance(source_layer_schema, dict)
                else {}
            ),
            "expanded_aliases": layer_aliases,
        },
        "rules_normalization": {
            "source": _relative(rules, root),
            "normalized_sha256": hashlib.sha256(
                normalized_rules_text.encode("utf-8")
            ).hexdigest(),
            "aliases_applied": rules_aliases,
        },
        "outputs": {
            "normalized_json": normalized_record,
            "execution_receipt": {"path": receipt_relative},
        },
        "required_outputs": [
            {"role": "normalized_json", **normalized_record},
            {"role": "execution_receipt", "path": receipt_relative},
        ],
        "ignored_entities": normalized.get("ignored_entities", []),
        "derived_rooms": normalized.get("derived_rooms", []),
        "search_miss": normalized.get("turning_space", {}).get("search_miss"),
        "summary": {
            "rooms": len(normalized.get("rooms", [])),
            "doors": len(normalized.get("doors", [])),
            "fixtures": len(normalized.get("fixtures", [])),
            "grab_bars": len(normalized.get("grab_bars", [])),
            "turning_space_status": normalized.get("turning_space", {}).get(
                "status"
            ),
            "output_schema_count": 1,
            "ignored_entities": sum(
                int(item.get("count", 0))
                for item in normalized.get("ignored_entities", [])
                if isinstance(item, dict)
            ),
            "derived_rooms": len(normalized.get("derived_rooms", [])),
        },
    }
    _write_atomic(receipt_path, receipt_payload)
    return receipt_payload


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task_root",
        nargs="?",
        default=".",
        help="task root containing input/ (default: current directory)",
    )
    parser.add_argument(
        "--output",
        help="normalized JSON path (default: <root>/output/extracted_geometry.json)",
    )
    parser.add_argument(
        "--receipt",
        help="receipt path (default: <root>/output/extraction_receipt.json)",
    )
    parser.add_argument(
        "--extractor",
        help="extractor path (default: scripts/extract_architectural_dxf.py)",
    )
    args = parser.parse_args(argv)
    try:
        result = extract(
            Path(args.task_root),
            output=Path(args.output) if args.output else None,
            receipt=Path(args.receipt) if args.receipt else None,
            extractor=Path(args.extractor) if args.extractor else None,
        )
        return result if isinstance(result, int) else 0
    except AdapterFailure as error:
        return error.emit()


if __name__ == "__main__":
    raise SystemExit(main())
