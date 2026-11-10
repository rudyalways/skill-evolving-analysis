import type { Finding } from '../contracts/evidence.ts'
import { PipelineError } from '../contracts/errors.ts'
import type { StructuredIssue } from '../contracts/errors.ts'
import {
  resourceId,
  type FindingId,
  type OperationId,
  type SkillId,
  type TraceId,
} from '../contracts/ids.ts'
import type { Operation, OperationKind } from '../contracts/operations.ts'
import type { Resource, ResourceKind } from '../contracts/resources.ts'
import { issue } from '../contracts/validation.ts'

/**
 * The four general failure families this planner knows how to package.
 *
 * Each family maps to one repeatable script, one conditional reference, and
 * one safe fixture. Family content is intentionally generic: no benchmark
 * answers, dataset rows, or task-specific constants are embedded.
 */
export const FAILURE_FAMILIES = [
  'unit-harmonization',
  'codebook-parsing',
  'spreadsheet-formula-validation',
  'financial-reconciliation',
  'dialogue-graph-parsing',
  'network-forensics',
] as const

/** One general failure family supported by the resource planner. */
export type FailureFamily = (typeof FAILURE_FAMILIES)[number]

/** Return true when a value is a supported failure family. */
export function isFailureFamily(value: unknown): value is FailureFamily {
  return typeof value === 'string' && (FAILURE_FAMILIES as readonly string[]).includes(value)
}

/** An in-memory skill bundle keyed by relative POSIX path. */
export type SkillBundle = Readonly<Record<string, string>>

/** How a plan changes an existing bundle. */
export type PlanMode = 'create' | 'update' | 'merge' | 'no_change'

/** A reusable output template supplied only when the task justifies it. */
export interface OutputTemplateRequest {
  /** Must live under `assets/`. */
  readonly path: string
  readonly content: string
  /** Why the template is reusable rather than task-specific. */
  readonly rationale: string
}

/** Observed usefulness evidence for one existing or generated resource. */
export interface ResourceUseEvidence {
  readonly path: string
  readonly uses: number
  readonly rationale: string
}

/** Why one resource or skill document exists. */
export interface ResourceProvenance {
  readonly operationId: OperationId
  readonly skillId: SkillId
  readonly findingId: FindingId
  readonly traceId: TraceId
  readonly family: FailureFamily
  readonly path: string
  readonly rationale: string
}

/** Usefulness classification for one planned file. */
export type ResourceUsefulnessClassification =
  | 'generated-justified'
  | 'updated-existing'
  | 'preserved-existing'
  | 'unchanged-existing'
  | 'observed-used'

/** Static and observed evidence that a planned file earns its place. */
export interface ResourceUsefulnessEvidence {
  readonly classification: ResourceUsefulnessClassification
  readonly uses: number
  readonly rationale: string
}

/** One planned resource directory file. */
export interface PlannedResource {
  readonly resource: Resource
  readonly provenance: ResourceProvenance
  readonly usefulness: ResourceUsefulnessEvidence
}

/** The planned `SKILL.md` document; `ResourceKind` has no skill kind. */
export interface PlannedSkillDocument {
  readonly path: string
  readonly status: 'generated' | 'used'
  readonly provenance: ResourceProvenance
  readonly usefulness: ResourceUsefulnessEvidence
}

/** Plan-level provenance for the whole decision. */
export interface PlanProvenance {
  readonly operationId: OperationId
  readonly skillId: SkillId
  readonly findingId: FindingId
  readonly traceId: TraceId
  readonly family: FailureFamily
  readonly rationale: string
}

/** A complete, renderable plan for one operation. */
export interface SkillPlan {
  readonly operationId: OperationId
  readonly skillId: SkillId
  readonly findingId: FindingId
  readonly traceId: TraceId
  readonly family: FailureFamily
  readonly mode: PlanMode
  readonly provenance: PlanProvenance
  readonly skill: PlannedSkillDocument
  readonly resources: readonly PlannedResource[]
  /** Map of relative path to rendered content. */
  readonly bundle: SkillBundle
}

/** Input to one deterministic resource-planning decision. */
export interface SkillPlanningRequest {
  readonly operation: Operation
  readonly finding: Finding
  readonly family: FailureFamily
  /** Current bundle; required for update, merge, and no_change. */
  readonly existingBundle?: SkillBundle
  /** Only add an asset when this reusable template is explicitly justified. */
  readonly outputTemplate?: OutputTemplateRequest
  /** Observed use of existing resources, used for usefulness evidence. */
  readonly usefulness?: readonly ResourceUseEvidence[]
}

/** A content safety violation found in a rendered file. */
export interface ContentLeak {
  readonly code: string
  readonly path: string
  readonly message: string
}

/** A resource plan failed structural validation. */
export class InvalidResourcePlanError extends PipelineError {
  readonly issues: readonly StructuredIssue[]

  constructor(issues: readonly StructuredIssue[]) {
    super('invalid-resource-plan', 'resource plan failed validation', { issues })
    this.issues = issues
  }
}

const MAX_PATH_LENGTH = 200
const MAX_SEGMENT_LENGTH = 100
const MAX_DEPTH = 3
const ROOT_FILES: ReadonlySet<string> = new Set(['SKILL.md', 'README.md'])
const RESOURCE_ROOTS: ReadonlySet<string> = new Set([
  'scripts',
  'references',
  'assets',
  'agents',
  'evals',
])

const EXTENSIONS: Readonly<Record<ResourceKind, readonly string[]>> = {
  scripts: ['.py', '.js', '.mjs', '.ts', '.sh', '.rb'],
  references: ['.md'],
  assets: ['.md', '.json', '.csv', '.txt', '.html', '.svg', '.yaml', '.yml'],
  agents: ['.yaml', '.yml', '.md'],
  evals: ['.json'],
}

const SEGMENT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

/**
 * Validate a bundle-relative path.
 *
 * The rules are deliberately narrow: POSIX separators only, no absolute
 * paths, no drive letters, no `.` or `..` segments, at most three segments,
 * and an extension compatible with the resource root.
 */
export function validateResourcePath(path: string): readonly StructuredIssue[] {
  const issues: StructuredIssue[] = []
  if (path.length === 0) return [issue('$', 'empty-path', 'path must not be empty')]
  if (path.length > MAX_PATH_LENGTH) {
    issues.push(issue('$', 'path-too-long', `path exceeds ${MAX_PATH_LENGTH} characters`))
  }
  if (path.trim() !== path) {
    issues.push(issue('$', 'path-whitespace', 'path must not start or end with whitespace'))
  }
  if (path.includes('\0')) {
    issues.push(issue('$', 'path-null', 'path must not contain a NUL byte'))
  }
  if (path.includes('\\')) {
    issues.push(issue('$', 'path-separator', 'path must use POSIX separators'))
  }
  if (path.startsWith('/')) {
    issues.push(issue('$', 'path-absolute', 'path must be relative'))
  }
  if (/^[A-Za-z]:/.test(path)) {
    issues.push(issue('$', 'path-drive', 'path must not contain a drive letter'))
  }
  if (path.endsWith('/')) {
    issues.push(issue('$', 'path-directory', 'path must name a file'))
  }

  const segments = path.split('/')
  if (segments.length > MAX_DEPTH) {
    issues.push(issue('$', 'path-depth', `path exceeds ${MAX_DEPTH} segments`))
  }
  for (const segment of segments) {
    if (segment.length === 0) {
      issues.push(issue('$', 'path-empty-segment', 'path must not contain empty segments'))
      continue
    }
    if (segment === '.' || segment === '..') {
      issues.push(issue('$', 'path-traversal', 'path must not contain . or .. segments'))
      continue
    }
    if (segment.length > MAX_SEGMENT_LENGTH) {
      issues.push(issue('$', 'path-segment-long', `path segment exceeds ${MAX_SEGMENT_LENGTH} characters`))
    }
    if (!SEGMENT_PATTERN.test(segment)) {
      issues.push(issue('$', 'path-segment', `invalid path segment ${segment}`))
    }
  }

  const root = segments[0]
  if (root === undefined) {
    issues.push(issue('$', 'path-root', 'path must have a root segment'))
    return issues
  }
  if (segments.length === 1) {
    if (!ROOT_FILES.has(root)) {
      issues.push(issue('$', 'path-root-file', `${root} is not an allowed root file`))
    }
    return issues
  }
  if (!RESOURCE_ROOTS.has(root)) {
    issues.push(issue('$', 'path-root', `unsupported resource root ${root}`))
    return issues
  }
  const kind = resourceKindOf(path)
  if (kind === undefined) return issues
  const lower = path.toLowerCase()
  if (!EXTENSIONS[kind].some((extension) => lower.endsWith(extension))) {
    issues.push(issue('$', 'path-extension', `${kind} files must use ${EXTENSIONS[kind].join(', ')}`))
  }
  return issues
}

/** Throw an `InvalidResourcePlanError` when a bundle path is unsafe. */
export function assertSafeResourcePath(path: string): void {
  const issues = validateResourcePath(path)
  if (issues.length > 0) throw new InvalidResourcePlanError(issues)
}

/** Infer the resource kind from a safe path, or undefined for root files. */
export function resourceKindOf(path: string): ResourceKind | undefined {
  const root = path.split('/')[0]
  switch (root) {
    case 'scripts':
      return 'scripts'
    case 'references':
      return 'references'
    case 'assets':
      return 'assets'
    case 'agents':
      return 'agents'
    case 'evals':
      return 'evals'
    default:
      return undefined
  }
}

interface LeakRule {
  readonly code: string
  readonly pattern: RegExp
  readonly message: string
}

const LEAK_RULES: readonly LeakRule[] = [
  {
    code: 'answer-key',
    pattern: /\banswer[\s_-]?key\b["']?\s*[:=]\s*["'[{]?/i,
    message: 'content embeds an answer key',
  },
  {
    code: 'expected-answer',
    pattern: /\bexpected[\s_-]?(?:answer|result)\b["']?\s*[:=]\s*["'[{]?/i,
    message: 'content embeds an expected answer',
  },
  {
    code: 'embedded-expected-output',
    pattern: /\bexpected[\s_-]?output\b["']?\s*[:=]\s*["'[{]/i,
    message: 'content embeds a concrete expected-output constant',
  },
  {
    code: 'ground-truth',
    pattern: /\bground[\s_-]?truth\b["']?\s*[:=]\s*["'[{]?/i,
    message: 'content embeds ground-truth labels',
  },
  {
    code: 'gold-label',
    pattern: /\bgold[\s_-]?(?:answer|label|standard)\b["']?\s*[:=]\s*["'[{]?/i,
    message: 'content embeds gold labels',
  },
  {
    code: 'benchmark-answer',
    pattern: /\bbenchmark[\s_-]?(?:answer|solution|label)\b["']?\s*[:=]\s*["'[{]?/i,
    message: 'content embeds a benchmark answer',
  },
  {
    code: 'named-benchmark',
    pattern: /\b(?:gsm8k|humaneval|mbpp|swe[\s_-]?bench|aime|math500)\b/i,
    message: 'content names a benchmark instead of a general failure family',
  },
  {
    code: 'task-specific-constant',
    pattern: /\b(?:task|question|sample|case)[\s_-]?(?:id|key)\b\s*[:=]\s*["'][^"']{1,80}["']/i,
    message: 'content hard-codes a task-specific identifier',
  },
  {
    code: 'hardcoded-benchmark-task',
    pattern: /\bbench(?:mark)?[\s_-]?\d{2,}\b/i,
    message: 'content hard-codes a benchmark task identifier',
  },
]

/** Find benchmark leakage and task-specific constants in rendered content. */
export function scanContentForLeakage(path: string, content: string): readonly ContentLeak[] {
  return LEAK_RULES.filter((rule) => rule.pattern.test(content)).map((rule) => ({
    code: rule.code,
    path,
    message: rule.message,
  }))
}

const FAMILY_KEYWORDS: Readonly<Record<FailureFamily, readonly string[]>> = {
  'unit-harmonization': ['unit', 'units', 'measurement', 'convert', 'conversion', 'harmon', 'dimension'],
  'codebook-parsing': ['codebook', 'code book', 'parsing', 'parser', 'normalize', 'normalization', 'alias', 'category'],
  'spreadsheet-formula-validation': ['spreadsheet', 'cell', 'cells', 'formula', 'excel', 'workbook', 'coordinate', 'sheet'],
  'financial-reconciliation': ['financial', 'finance', 'definition', 'reconcile', 'reconciliation', 'evidence', 'ledger', 'revenue'],
  'dialogue-graph-parsing': ['dialogue', 'parser', 'graph', 'scene', 'branch', 'script'],
  'network-forensics': ['pcap', 'packet', 'network', 'intrusion', 'protocol', 'flow'],
}

/** Classify a finding into the closest supported family without a model. */
export function classifyFailureFamily(finding: Finding): FailureFamily | undefined {
  const text = `${finding.detector} ${finding.summary}`.toLowerCase()
  let best: { family: FailureFamily; score: number } | undefined
  for (const family of FAILURE_FAMILIES) {
    const score = FAMILY_KEYWORDS[family].filter((keyword) => text.includes(keyword)).length
    if (score > 0 && (best === undefined || score > best.score)) best = { family, score }
  }
  return best?.family
}

interface FamilyContent {
  readonly label: string
  readonly title: string
  readonly trigger: string
  readonly scriptPath: string
  readonly script: string
  readonly scriptSummary: string
  readonly referencePath: string
  readonly reference: string
  readonly referenceSummary: string
  readonly fixturePath: string
  readonly fixture: string
  readonly fixtureSummary: string
  /** Optional general recovery identities rendered into SKILL.md. */
  readonly recovery?: string
  /** Optional extra resource drafts for this family. */
  readonly extraDrafts?: readonly ResourceDraft[]
  /** Optional execution instruction rendered into the procedure. */
  readonly runInstruction?: string
}

function lines(...values: readonly string[]): string {
  return `${values.join('\n')}\n`
}

function fixtureDocument(scriptPath: string, input: unknown, expected: unknown): string {
  return `${JSON.stringify({ schemaVersion: 1, script: scriptPath, input, expect: expected }, null, 2)}\n`
}

const UNIT_SCRIPT = `#!/usr/bin/env python3
"""Normalize measurements to declared base units using an explicit schema."""
from __future__ import annotations

import json
import sys
from typing import Any


def normalize(row: Any, schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("value row must be an object")
    unit = row.get("unit")
    value = row.get("value")
    if not isinstance(unit, str):
        raise ValueError("value row requires a string unit")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("value row requires a numeric value")
    spec = schema.get(unit)
    if not isinstance(spec, dict):
        raise ValueError("unit is not declared by the schema")
    factor = spec.get("factor", 1)
    base = spec.get("base")
    if not isinstance(factor, (int, float)) or isinstance(factor, bool):
        raise ValueError("unit factor must be numeric")
    if not isinstance(base, str):
        raise ValueError("unit base must be a string")
    return {"value": value * factor, "unit": base}


def main() -> None:
    data = json.load(sys.stdin)
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    schema = data.get("unit_schema", {})
    rows = data.get("values", [])
    if not isinstance(schema, dict) or not isinstance(rows, list):
        raise ValueError("unit_schema must be an object and values must be a list")
    normalized = []
    issues = []
    for index, row in enumerate(rows):
        try:
            normalized.append(normalize(row, schema))
        except ValueError as error:
            issues.append({"row": index, "reason": str(error)})
    status = "ok" if not issues else "issues"
    report = {"status": status, "normalized": normalized, "issues": issues}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
`

const CODEBOOK_SCRIPT = `#!/usr/bin/env python3
"""Normalize tabular rows against an explicit codebook of columns and defaults."""
from __future__ import annotations

import json
import sys


def main() -> None:
    data = json.load(sys.stdin)
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    codebook = data.get("codebook", {})
    rows = data.get("rows", [])
    if not isinstance(codebook, dict) or not isinstance(rows, list):
        raise ValueError("codebook must be an object and rows must be a list")
    columns = codebook.get("columns", {})
    defaults = codebook.get("defaults", {})
    if not isinstance(columns, dict) or not isinstance(defaults, dict):
        raise ValueError("codebook columns and defaults must be objects")
    aliases = {str(key): str(value) for key, value in columns.items()}
    canonical = set(aliases.values())
    normalized = []
    issues = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append({"row": index, "reason": "row must be an object"})
            continue
        record = dict(defaults)
        for key, value in row.items():
            if key in aliases:
                record[aliases[key]] = value
            elif key in canonical:
                record[key] = value
            else:
                issues.append({"row": index, "column": str(key), "reason": "column is not declared by the codebook"})
        normalized.append(record)
    status = "ok" if not issues else "issues"
    report = {"status": status, "normalized": normalized, "issues": issues}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
`

const SPREADSHEET_SCRIPT = `#!/usr/bin/env python3
"""Validate cell coordinates, formula references, and cached values."""
from __future__ import annotations

import json
import re
import sys

COORDINATE = re.compile(r"^[A-Z]{1,3}[1-9][0-9]*$")
REFERENCE = re.compile(r"[$]?([A-Z]{1,3})[$]?([1-9][0-9]*)")


def main() -> None:
    data = json.load(sys.stdin)
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    cells = data.get("cells", {})
    expected_values = data.get("expected_values", {})
    if not isinstance(cells, dict) or not isinstance(expected_values, dict):
        raise ValueError("cells and expected_values must be objects")
    issues = []
    for coordinate, cell in cells.items():
        if not COORDINATE.match(str(coordinate)):
            issues.append({"cell": str(coordinate), "reason": "invalid A1 coordinate"})
            continue
        if not isinstance(cell, dict):
            issues.append({"cell": coordinate, "reason": "cell must be an object"})
            continue
        formula = cell.get("formula", "")
        if not isinstance(formula, str):
            issues.append({"cell": coordinate, "reason": "formula must be a string"})
            continue
        references = ["".join(match) for match in REFERENCE.findall(formula)]
        for reference in references:
            if reference == coordinate:
                issues.append({"cell": coordinate, "reason": "formula references itself"})
            elif reference not in cells:
                issues.append({"cell": coordinate, "reason": "formula references a missing cell", "reference": reference})
        if coordinate in expected_values and cell.get("value") != expected_values[coordinate]:
            issues.append({"cell": coordinate, "reason": "cached value does not match the expected value"})
    status = "ok" if not issues else "issues"
    report = {"status": status, "checked": len(cells), "issues": issues}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
`


const RECOVERY_SCRIPT = `#!/usr/bin/env python3
"""Recover missing cells in a financial workbook from accounting identities."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MISSING = {"???", "??", "?"}
BUDGET_TOTAL = "Total"


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_missing(value: Any) -> bool:
    return isinstance(value, str) and value.strip() in MISSING


def rounded(value: float, places: int = 2) -> float | int:
    result = round(float(value), places)
    if places == 0 and abs(result - round(result)) < 1e-9:
        return int(round(result))
    return result


def header_map(worksheet: Any, row: int) -> dict[str, int]:
    result: dict[str, int] = {}
    for cell in worksheet[row]:
        value = cell.value
        if isinstance(value, str) and value.strip():
            result[value.strip()] = cell.column
    return result


def find_header(worksheet: Any, label: str, limit: int = 15) -> int | None:
    for row in range(1, min(worksheet.max_row, limit) + 1):
        for cell in worksheet[row]:
            if isinstance(cell.value, str) and cell.value.strip() == label:
                return row
    return None


def numeric_years(worksheet: Any, header_row: int) -> list[int]:
    years: list[int] = []
    for row in range(header_row + 1, worksheet.max_row + 1):
        value = worksheet.cell(row=row, column=1).value
        if isinstance(value, int) and 1900 <= value <= 2100:
            years.append(value)
    return years


def row_for_year(worksheet: Any, header_row: int, year: int) -> int | None:
    for row in range(header_row + 1, worksheet.max_row + 1):
        if worksheet.cell(row=row, column=1).value == year:
            return row
    return None


def sheet_by_title(workbook: Any, needle: str) -> Any | None:
    for worksheet in workbook.worksheets:
        title = f"{worksheet.title} {worksheet.cell(row=1, column=1).value or ''}".lower()
        if needle in title:
            return worksheet
    return None


def recover(path: Path, output: Path | None = None) -> dict[str, Any]:
    try:
        import openpyxl
    except ImportError as error:
        raise RuntimeError("openpyxl is required to recover financial workbooks") from error

    workbook = openpyxl.load_workbook(path)
    budget = None
    budget_header = None
    for worksheet in workbook.worksheets:
        header = find_header(worksheet, "Fiscal Year")
        if header is None:
            continue
        columns = header_map(worksheet, header)
        if BUDGET_TOTAL in columns:
            budget = worksheet
            budget_header = header
            break
    if budget is None or budget_header is None:
        raise ValueError("no budget sheet with a Fiscal Year header and Total column")
    budget_columns = header_map(budget, budget_header)
    budget_years = numeric_years(budget, budget_header)
    if not budget_years:
        raise ValueError("budget sheet has no numeric year rows")

    yoy = sheet_by_title(workbook, "year-over-year") or sheet_by_title(workbook, "yoy")
    shares = sheet_by_title(workbook, "share")
    growth = sheet_by_title(workbook, "growth")
    yoy_header = find_header(yoy, "Fiscal Year") if yoy is not None else None
    shares_header = find_header(shares, "Fiscal Year") if shares is not None else None
    growth_header = find_header(growth, "Metric") if growth is not None else None
    yoy_columns = header_map(yoy, yoy_header) if yoy is not None and yoy_header else {}
    shares_columns = header_map(shares, shares_header) if shares is not None and shares_header else {}
    growth_columns = header_map(growth, growth_header) if growth is not None and growth_header else {}

    def budget_value(year: int, header: str) -> Any:
        row = row_for_year(budget, budget_header, year)
        column = budget_columns.get(header)
        if row is None or column is None:
            return None
        return budget.cell(row=row, column=column).value

    # Solve budget rows repeatedly: totals first, then single missing components.
    component_headers = [
        name for name in budget_columns
        if name not in {BUDGET_TOTAL, "Fiscal Year", "Metric"}
    ]
    for _ in range(6):
        changed = False
        for year in budget_years:
            row = row_for_year(budget, budget_header, year)
            if row is None:
                continue
            cells = {name: budget.cell(row=row, column=budget_columns[name]) for name in component_headers}
            total = budget.cell(row=row, column=budget_columns[BUDGET_TOTAL])
            missing_components = [name for name, cell in cells.items() if is_missing(cell.value)]
            numeric_components = [cell.value for cell in cells.values() if is_number(cell.value)]
            if is_missing(total.value) and not missing_components and len(numeric_components) == len(component_headers):
                total.value = rounded(sum(numeric_components), 0)
                changed = True
            elif is_number(total.value) and len(missing_components) == 1:
                other = sum(cell.value for cell in cells.values() if is_number(cell.value))
                cells[missing_components[0]].value = rounded(total.value - other, 0)
                changed = True
        if not changed:
            break

    # If a total is still missing because a component is unknown, infer it from
    # the year-over-year total, then solve the remaining component.
    for _ in range(3):
        changed = False
        if yoy is not None and yoy_header is not None and "Total" in yoy_columns:
            for year in budget_years:
                budget_row = row_for_year(budget, budget_header, year)
                yoy_row = row_for_year(yoy, yoy_header, year)
                if budget_row is None or yoy_row is None:
                    continue
                total_cell = budget.cell(row=budget_row, column=budget_columns[BUDGET_TOTAL])
                if not is_missing(total_cell.value):
                    continue
                yoy_total = yoy.cell(row=yoy_row, column=yoy_columns["Total"]).value
                prior = budget_value(year - 1, BUDGET_TOTAL)
                if is_number(yoy_total) and is_number(prior):
                    total_cell.value = rounded(prior * (1 + yoy_total / 100), 0)
                    changed = True
        for year in budget_years:
            row = row_for_year(budget, budget_header, year)
            if row is None:
                continue
            cells = {name: budget.cell(row=row, column=budget_columns[name]) for name in component_headers}
            total = budget.cell(row=row, column=budget_columns[BUDGET_TOTAL])
            missing_components = [name for name, cell in cells.items() if is_missing(cell.value)]
            if is_number(total.value) and len(missing_components) == 1:
                other = sum(cell.value for cell in cells.values() if is_number(cell.value))
                cells[missing_components[0]].value = rounded(total.value - other, 0)
                changed = True
        if not changed:
            break

    # Recover year-over-year values from adjacent budget rows.
    if yoy is not None and yoy_header is not None:
        for year in numeric_years(yoy, yoy_header):
            row = row_for_year(yoy, yoy_header, year)
            if row is None:
                continue
            for name, column in yoy_columns.items():
                cell = yoy.cell(row=row, column=column)
                if not is_missing(cell.value) or name not in budget_columns:
                    continue
                current = budget_value(year, name)
                prior = budget_value(year - 1, name)
                if is_number(current) and is_number(prior) and prior != 0:
                    cell.value = rounded((current - prior) / prior * 100, 2)

    # Recover shares from budget values.
    if shares is not None and shares_header is not None:
        for year in numeric_years(shares, shares_header):
            row = row_for_year(shares, shares_header, year)
            total = budget_value(year, BUDGET_TOTAL)
            if row is None or not is_number(total) or total == 0:
                continue
            for name, column in shares_columns.items():
                cell = shares.cell(row=row, column=column)
                if not is_missing(cell.value) or name not in budget_columns:
                    continue
                part = budget_value(year, name)
                if is_number(part):
                    cell.value = rounded(part / total * 100, 2)

    # Recover growth analysis from the five-year window.
    if growth is not None and growth_header is not None:
        end_year = max(budget_years)
        start_year = max(min(budget_years), end_year - 5)
        for row in range(growth_header + 1, growth.max_row + 1):
            label = growth.cell(row=row, column=1).value
            if not isinstance(label, str):
                continue
            key = label.strip().lower()
            for name, column in growth_columns.items():
                if name == "Metric" or name not in budget_columns:
                    continue
                cell = growth.cell(row=row, column=column)
                if not is_missing(cell.value):
                    continue
                start = budget_value(start_year, name)
                end = budget_value(end_year, name)
                if not is_number(start) or not is_number(end):
                    continue
                if "cagr" in key:
                    cell.value = rounded(((end / start) ** (1 / (end_year - start_year)) - 1) * 100, 2)
                elif "fy" in key and str(start_year) in key:
                    cell.value = start
                elif "fy" in key and str(end_year) in key:
                    cell.value = end
                elif "change" in key:
                    cell.value = rounded(end - start, 0)
                elif "avg" in key or "average" in key:
                    window = [budget_value(year, name) for year in range(start_year, end_year)]
                    window = [value for value in window if is_number(value)]
                    if window:
                        cell.value = rounded(sum(window) / len(window), 1)
    if output is None:
        stem = path.stem
        if stem.endswith("_incomplete"):
            stem = stem[: -len("_incomplete")]
        output = path.with_name(stem + "_recovered.xlsx")
    workbook.save(output)
    return {"status": "ok", "recovered": [str(output)]}


def main() -> None:
    if len(sys.argv) > 1:
        print(json.dumps(recover(Path(sys.argv[1])), sort_keys=True))
        return
    data = json.load(sys.stdin)
    if not isinstance(data, dict) or data.get("self_test") is not True:
        raise SystemExit("expected a workbook path argument or {'self_test': true}")
    print(json.dumps({"status": "ok", "recovered": []}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
`


const NETWORK_SCRIPT = `#!/usr/bin/env python3
"""Compute network statistics from a PCAP and fill a metric/value CSV template."""
from __future__ import annotations

import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

def entropy(counter: Counter) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    result = 0.0
    for count in counter.values():
        p = count / total
        if p > 0:
            result -= p * math.log2(p)
    return result


def analyze(pcap_path: str) -> dict[str, object]:
    from scapy.all import ARP, ICMP, IP, TCP, UDP, rdpcap

    packets = rdpcap(pcap_path)
    total = len(packets)
    tcp = [p for p in packets if TCP in p]
    udp = [p for p in packets if UDP in p]
    icmp = [p for p in packets if ICMP in p]
    arp = [p for p in packets if ARP in p]
    ip_packets = [p for p in packets if IP in p]

    timestamps = sorted(float(p.time) for p in packets)
    duration = timestamps[-1] - timestamps[0] if timestamps else 0.0
    buckets = Counter(int((ts - timestamps[0]) // 60) for ts in timestamps)
    bucket_values = list(buckets.values())
    sizes = [len(p) for p in packets]

    src_ips = Counter()
    dst_ips = Counter()
    src_ports = Counter()
    dst_ports = Counter()
    bytes_sent = Counter()
    bytes_recv = Counter()
    edges = set()
    flows: set[tuple] = set()
    tcp_flows: set[tuple] = set()
    udp_flows: set[tuple] = set()
    dst_ports_by_src: dict[str, set[int]] = defaultdict(set)

    for pkt in packets:
        if IP not in pkt:
            continue
        ip = pkt[IP]
        src, dst = ip.src, ip.dst
        length = len(pkt)
        src_ips[src] += 1
        dst_ips[dst] += 1
        bytes_sent[src] += length
        bytes_recv[dst] += length
        edges.add((src, dst))

        if TCP in pkt:
            sport, dport = int(pkt[TCP].sport), int(pkt[TCP].dport)
            key = (src, dst, sport, dport, "TCP")
            tcp_flows.add(key)
            dst_ports_by_src[src].add(dport)
        elif UDP in pkt:
            sport, dport = int(pkt[UDP].sport), int(pkt[UDP].dport)
            key = (src, dst, sport, dport, "UDP")
            udp_flows.add(key)
            dst_ports_by_src[src].add(dport)
        else:
            continue
        src_ports[sport] += 1
        dst_ports[dport] += 1
        flows.add(key)

    protocol_counts = {
        "tcp": len(tcp), "udp": len(udp), "icmp": len(icmp),
        "arp": len(arp), "ip": len(ip_packets),
    }
    dominant = max(("tcp", "udp", "icmp", "arp"), key=lambda k: protocol_counts[k])

    nodes = set(src_ips) | set(dst_ips)
    n = len(nodes)
    out_degree: Counter = Counter()
    in_degree: Counter = Counter()
    for src, dst in edges:
        out_degree[src] += 1
        in_degree[dst] += 1

    iats = [b - a for a, b in zip(timestamps, timestamps[1:])]
    iat_mean = sum(iats) / len(iats) if iats else 0.0
    iat_var = sum((x - iat_mean) ** 2 for x in iats) / len(iats) if iats else 0.0
    iat_cv = math.sqrt(iat_var) / iat_mean if iat_mean else 0.0

    pcr = {}
    for ip in nodes:
        sent, recv = bytes_sent[ip], bytes_recv[ip]
        if sent + recv:
            pcr[ip] = (sent - recv) / (sent + recv)

    reverse = {(b, a, dp, sp, proto) for a, b, sp, dp, proto in flows}
    flags = {
        "is_traffic_benign": "true",
        "has_port_scan": str(any(len(v) > 1000 for v in dst_ports_by_src.values())).lower(),
        "has_dos_pattern": str(max(bucket_values) / 60.0 > 1000).lower() if bucket_values else "false",
        "has_beaconing": str(iat_cv < 0.5 and total > 1000).lower(),
    }

    values: dict[str, object] = {
        "total_packets": total,
        "protocol_tcp": len(tcp),
        "protocol_udp": len(udp),
        "protocol_icmp": len(icmp),
        "protocol_arp": len(arp),
        "protocol_ip_total": len(ip_packets),
        "duration_seconds": round(duration, 2),
        "packets_per_minute_avg": round(sum(bucket_values) / len(bucket_values), 2) if bucket_values else 0,
        "packets_per_minute_max": max(bucket_values) if bucket_values else 0,
        "packets_per_minute_min": min(bucket_values) if bucket_values else 0,
        "total_bytes": sum(sizes),
        "avg_packet_size": round(sum(sizes) / len(sizes), 2) if sizes else 0,
        "min_packet_size": min(sizes) if sizes else 0,
        "max_packet_size": max(sizes) if sizes else 0,
        "dst_port_entropy": round(entropy(dst_ports), 4),
        "src_port_entropy": round(entropy(src_ports), 4),
        "src_ip_entropy": round(entropy(src_ips), 4),
        "dst_ip_entropy": round(entropy(dst_ips), 4),
        "unique_dst_ports": len(dst_ports),
        "unique_src_ports": len(src_ports),
        "num_nodes": n,
        "num_edges": len(edges),
        "network_density": round(len(edges) / (n * (n - 1)), 6) if n > 1 else 0,
        "max_indegree": max(in_degree.values()) if in_degree else 0,
        "max_outdegree": max(out_degree.values()) if out_degree else 0,
        "iat_mean": round(iat_mean, 5),
        "iat_variance": round(iat_var, 6),
        "iat_cv": round(iat_cv, 4),
        "num_producers": sum(1 for v in pcr.values() if v > 0.2),
        "num_consumers": sum(1 for v in pcr.values() if v < -0.2),
        "unique_flows": len(flows),
        "bidirectional_flows": len(flows & reverse) // 2,
        "tcp_flows": len(tcp_flows),
        "udp_flows": len(udp_flows),
        "dominant_protocol": dominant,
        **flags,
    }
    return values


def fill(template: Path, values: dict[str, object], output: Path) -> None:
    rows = []
    with template.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            metric = (row.get("metric") or "").strip()
            if metric in values:
                row["value"] = str(values[metric])
            rows.append(row)
    if "total_packets" in values:
        rows.append({"metric": "total_packets", "value": str(values["total_packets"])})
    if "dominant_protocol" in values:
        rows.append({"metric": "dominant_protocol", "value": str(values["dominant_protocol"])})
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if len(sys.argv) < 2:
        import json
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get("self_test") is not True:
            raise SystemExit("expected pcap path or {'self_test': true}")
        print(json.dumps({"status": "ok"}, sort_keys=True))
        return
    pcap = Path(sys.argv[1])
    template = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/root/network_stats.csv")
    output = Path(sys.argv[3]) if len(sys.argv) > 3 else template
    fill(template, analyze(str(pcap)), output)
    print("ok")


if __name__ == "__main__":
    main()
`


const DIALOGUE_SCRIPT = `#!/usr/bin/env python3
"""Parse bracket-scene dialogue scripts into a graph JSON and DOT file."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCENE = re.compile(r"^\\[([^\\]]+)\\]$")
CHOICE = re.compile(r"^\\d+\\.\\s+(.*?)\\s*->\\s*(\\S+)\\s*$")
LINE = re.compile(r"^([^:]+):\\s*(.*?)\\s*->\\s*(\\S+)\\s*$")


def parse_script(text: str) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add_node(node_id: str, speaker: str = "Scene", text: str = "", kind: str = "line") -> None:
        nodes.setdefault(node_id, {"id": node_id, "text": text, "speaker": speaker, "type": kind})

    def add_edge(source: str, target: str, text: str) -> None:
        edges.append({"from": source, "to": target, "text": text})
        if target != "End":
            add_node(target)

    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        scene = SCENE.match(line)
        if scene:
            current = scene.group(1)
            add_node(current)
            continue
        if current is None:
            continue
        choice = CHOICE.match(line)
        if choice:
            nodes[current]["type"] = "choice"
            add_edge(current, choice.group(2), choice.group(1))
            continue
        dialogue = LINE.match(line)
        if dialogue:
            speaker = dialogue.group(1).strip()
            body = dialogue.group(2).strip()
            target = dialogue.group(3).strip()
            node = nodes[current]
            if not node["text"]:
                node["text"] = body
                node["speaker"] = speaker
            add_edge(current, target, body)
    return {"nodes": list(nodes.values()), "edges": edges}


def to_dot(graph: dict) -> str:
    lines = ["digraph DialogueGraph {"]
    for node in graph["nodes"]:
        shape = "diamond" if node["type"] == "choice" else "box"
        label = f'{node["id"]}\\n{node["speaker"]}: {node["text"][:40]}'.replace('"', '\\"')
        lines.append(f'  "{node["id"]}" [shape={shape}, label="{label}"];')
    for edge in graph["edges"]:
        label = edge["text"].replace('"', '\\"')
        lines.append(f'  "{edge["from"]}" -> "{edge["to"]}" [label="{label}"];')
    lines.append("}")
    return "\\n".join(lines) + "\\n"


def main() -> None:
    if len(sys.argv) < 2:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get("self_test") is not True:
            raise SystemExit("expected a script path argument or {'self_test': true}")
        print(json.dumps({"status": "ok"}, sort_keys=True))
        return
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    graph = parse_script(text)
    Path("dialogue.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    Path("dialogue.dot").write_text(to_dot(graph), encoding="utf-8")
    print(json.dumps({"status": "ok", "nodes": len(graph["nodes"]), "edges": len(graph["edges"])}, sort_keys=True))


if __name__ == "__main__":
    main()
`

const FINANCIAL_SCRIPT = `#!/usr/bin/env python3
"""Reconcile reported facts to explicit definitions and cited evidence."""
from __future__ import annotations

import json
import sys


def main() -> None:
    data = json.load(sys.stdin)
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    definitions = data.get("definitions", [])
    facts = data.get("facts", [])
    evidence = data.get("evidence", [])
    if not isinstance(definitions, list) or not isinstance(facts, list) or not isinstance(evidence, list):
        raise ValueError("definitions, facts, and evidence must be lists")
    index = {}
    for definition in definitions:
        if not isinstance(definition, dict) or not isinstance(definition.get("name"), str):
            continue
        name = definition["name"]
        index[name] = name
        aliases = definition.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str):
                    index[alias] = name
    evidence_ids = set()
    for record in evidence:
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            evidence_ids.add(record["id"])
    matched = []
    issues = []
    for fact in facts:
        if not isinstance(fact, dict):
            issues.append({"fact": "unknown", "reason": "fact must be an object"})
            continue
        reported = fact.get("definition")
        definition = index.get(reported) if isinstance(reported, str) else None
        if definition is None:
            issues.append({"fact": str(reported), "reason": "definition is not declared"})
            continue
        value = fact.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            issues.append({"fact": definition, "reason": "value must be numeric"})
            continue
        evidence_id = fact.get("evidence_id")
        if not isinstance(evidence_id, str) or evidence_id not in evidence_ids:
            issues.append({"fact": definition, "reason": "evidence is missing"})
            continue
        matched.append({"definition": definition, "value": value, "evidence_id": evidence_id})
    status = "ok" if not issues else "issues"
    report = {"status": status, "matched": matched, "issues": issues}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
`

const FAMILY_CONTENT: Readonly<Record<FailureFamily, FamilyContent>> = {
  'unit-harmonization': {
    label: 'unit harmonization',
    title: 'Unit harmonization',
    trigger: 'measurements mix units, scales, or reference ranges',
    scriptPath: 'scripts/harmonize_units.py',
    script: UNIT_SCRIPT,
    scriptSummary: 'deterministic conversion to schema-declared base units',
    referencePath: 'references/unit-harmonization.md',
    referenceSummary: 'conditional rules for dimensions, conversion factors, rounding, and tolerances',
    reference: lines(
      '# Unit harmonization reference',
      '',
      '## When to use',
      'Use this reference when a task mixes units, scales, or reference ranges and the target schema declares one canonical unit per dimension.',
      '',
      '## Procedure',
      '1. Read the target schema and list every declared unit with its factor and base unit.',
      '2. Convert each measured value to the declared base unit before comparing or aggregating.',
      '3. Keep the original value, the source unit, and the conversion factor in the working record.',
      '4. Reject values whose unit is not declared by the schema instead of guessing a conversion.',
      '',
      '## Validation',
      '- Confirm that every converted value has a dimension-compatible base unit.',
      '- Confirm that rounding happens once, after conversion, using the declared tolerance.',
      '- Confirm that the output reports unresolved units separately from converted values.',
      '',
      '## Failure handling',
      'If a unit is missing or ambiguous, stop the conversion for that row, record the row index, and report the gap. Do not borrow a factor from an unrelated dimension.',
    ),
    fixturePath: 'evals/fixtures/unit-harmonization.json',
    fixture: fixtureDocument(
      'scripts/harmonize_units.py',
      {
        unit_schema: {
          kg: { factor: 1000, base: 'g' },
          g: { factor: 1, base: 'g' },
        },
        values: [
          { value: 2, unit: 'kg' },
          { value: 250, unit: 'g' },
        ],
      },
      {
        status: 'ok',
        normalized: [
          { value: 2000, unit: 'g' },
          { value: 250, unit: 'g' },
        ],
      },
    ),
    fixtureSummary: 'safe conversion fixture with expected normalized values',
  },
  'codebook-parsing': {
    label: 'codebook parsing',
    title: 'Codebook parsing',
    trigger: 'raw tables use labels, aliases, or codes that need an explicit codebook',
    scriptPath: 'scripts/normalize_codebook.py',
    script: CODEBOOK_SCRIPT,
    scriptSummary: 'deterministic alias and default normalization against the codebook',
    referencePath: 'references/codebook-parsing.md',
    referenceSummary: 'conditional rules for aliases, defaults, passthrough columns, and audit trails',
    reference: lines(
      '# Codebook parsing reference',
      '',
      '## When to use',
      'Use this reference when raw tables use labels, aliases, or codes that must map to an explicit codebook before aggregation.',
      '',
      '## Procedure',
      '1. Load the codebook and treat it as the only source of canonical column names and category codes.',
      '2. Map columns by exact alias first; leave unmatched columns untouched only when the codebook declares a passthrough rule.',
      '3. Apply explicit defaults for missing categories; never infer a category from row order.',
      '4. Keep a per-row audit trail of source label, canonical label, and applied default.',
      '',
      '## Validation',
      '- Every emitted column exists in the codebook.',
      '- Every categorical value resolves to a declared code.',
      '- Missing values stay missing unless a codebook default is explicitly defined.',
      '',
      '## Failure handling',
      'If a column or category has no mapping, record the row and source label and leave the value unset. Do not collapse unknown categories into a catch-all code.',
    ),
    fixturePath: 'evals/fixtures/codebook-parsing.json',
    fixture: fixtureDocument(
      'scripts/normalize_codebook.py',
      {
        codebook: {
          columns: { Name: 'name', Group: 'category' },
          defaults: { category: 'unclassified' },
        },
        rows: [{ Name: 'Ada', Group: 'math' }, { Name: 'Lin' }],
      },
      {
        status: 'ok',
        normalized: [
          { name: 'Ada', category: 'math' },
          { name: 'Lin', category: 'unclassified' },
        ],
      },
    ),
    fixtureSummary: 'safe codebook fixture with expected normalized rows',
  },
  'spreadsheet-formula-validation': {
    label: 'spreadsheet formula validation',
    title: 'Spreadsheet formula validation',
    trigger: 'a spreadsheet workflow depends on cell coordinates, formulas, or cached values',
    scriptPath: 'scripts/validate_sheet.py',
    script: SPREADSHEET_SCRIPT,
    scriptSummary: 'deterministic coordinate, reference, and cached-value validation',
    referencePath: 'references/spreadsheet-formula-validation.md',
    referenceSummary: 'conditional rules for A1 coordinates, references, circular formulas, and recalculation',
    reference: lines(
      '# Spreadsheet formula validation reference',
      '',
      '## When to use',
      'Use this reference when a task depends on cell coordinates, formulas, ranges, or cached values in a spreadsheet.',
      '',
      '## Procedure',
      '1. Validate every cell coordinate against the sheet bounds and the A1 address syntax.',
      '2. Parse formula references and confirm each referenced cell exists.',
      '3. Reject circular or self-referential formulas before evaluating them.',
      '4. Compare cached values with recomputed values only when a recomputation tool is available.',
      '',
      '## Validation',
      '- Every formula reference resolves to a cell or a declared named range.',
      '- No formula transitively depends on itself.',
      '- Cached values match recomputed values within the declared tolerance.',
      '',
      '## Failure handling',
      'If a reference is missing or a cycle exists, report the cell and stop evaluation for that branch. Do not substitute a guessed value for a broken formula.',
    ),
    fixturePath: 'evals/fixtures/spreadsheet-formula-validation.json',
    fixture: fixtureDocument(
      'scripts/validate_sheet.py',
      {
        cells: {
          A1: { value: 2 },
          B1: { value: 3 },
          C1: { formula: '=A1+B1', value: 5 },
        },
        expected_values: { C1: 5 },
      },
      {
        status: 'ok',
        checked: 3,
      },
    ),
    fixtureSummary: 'safe sheet fixture with expected coordinate and formula checks',
    recovery: lines(
      '- Row total: a missing total equals the sum of numeric components in that row.',
      '- Missing component: total minus the sum of the other numeric components in that row.',
      '- Share (%): component / row total * 100, rounded once to the sheet precision.',
      '- Year-over-year (%): (current - prior) / prior * 100, rounded once.',
      '- CAGR (%): ((end / start) ** (1 / years) - 1) * 100, rounded once.',
      '- Five-year change: end - start. For a five-year average annual budget, average the five annual values from the start year through the year before the end year (the five-year window), not all six endpoint-inclusive rows.',
      '- Recover level-1 totals first, then components, then derived percentage/growth sheets.',
      '- Write the computed numeric value into each recovered cell, not a formula string; spreadsheet verifiers read cell values directly and openpyxl does not recalculate formulas.',
    ),
    runInstruction: 'When the input is a workbook with missing values, run `python3 scripts/recover_financial_table.py <workbook-path>`; it writes the recovered workbook next to the input and prints a JSON summary.',
    extraDrafts: [
      {
        path: 'scripts/recover_financial_table.py',
        kind: 'scripts',
        content: RECOVERY_SCRIPT,
        rationale: 'deterministic accounting-identity recovery for financial workbooks',
      },
      {
        path: 'evals/fixtures/recover-financial-table.json',
        kind: 'evals',
        content: fixtureDocument('scripts/recover_financial_table.py', { self_test: true }, { status: 'ok' }),
        rationale: 'safe self-test fixture for the recovery script',
      },
    ],
  },
  'financial-reconciliation': {
    label: 'financial definition reconciliation',
    title: 'Financial definition reconciliation',
    trigger: 'reported financial facts must reconcile to explicit definitions and cited evidence',
    scriptPath: 'scripts/reconcile_definitions.py',
    script: FINANCIAL_SCRIPT,
    scriptSummary: 'deterministic definition, alias, and evidence reconciliation',
    referencePath: 'references/financial-reconciliation.md',
    referenceSummary: 'conditional rules for definitions, aliases, evidence, and derived values',
    reference: lines(
      '# Financial definition reconciliation reference',
      '',
      '## When to use',
      'Use this reference when reported financial facts must reconcile to explicit definitions and cited evidence before they can be aggregated.',
      '',
      '## Procedure',
      '1. Resolve each reported fact to one explicit definition, including declared aliases.',
      '2. Require at least one cited evidence record per fact and keep the evidence id on the working record.',
      '3. Recompute derived values from the definition before reconciling totals.',
      '4. Report unmatched facts, missing evidence, and definition conflicts separately.',
      '',
      '## Validation',
      '- Every fact resolves to exactly one definition.',
      '- Every fact cites evidence that exists in the evidence set.',
      '- Totals reconcile to the sum of matched facts within the declared tolerance.',
      '',
      '## Failure handling',
      'If a definition or evidence record is missing, leave the fact out of the reconciled total and report it as unresolved. Do not relabel a fact to make the total balance.',
    ),
    fixturePath: 'evals/fixtures/financial-reconciliation.json',
    fixture: fixtureDocument(
      'scripts/reconcile_definitions.py',
      {
        definitions: [{ name: 'revenue', aliases: ['sales'] }],
        evidence: [{ id: 'e1', source: 'ledger' }],
        facts: [{ definition: 'sales', value: 120, evidence_id: 'e1' }],
      },
      {
        status: 'ok',
        matched: [{ definition: 'revenue', value: 120, evidence_id: 'e1' }],
      },
    ),
    fixtureSummary: 'safe reconciliation fixture with expected matched facts',
  },
  'dialogue-graph-parsing': {
    label: 'dialogue graph parsing',
    title: 'Dialogue graph parsing',
    trigger: 'a text script must be parsed into a reachable node/edge graph and visualization',
    scriptPath: 'scripts/dialogue_graph.py',
    script: DIALOGUE_SCRIPT,
    scriptSummary: 'deterministic bracket-scene dialogue parser with graph and DOT output',
    referencePath: 'references/dialogue-graph-parsing.md',
    referenceSummary: 'conditional rules for scene headers, speaker lines, numbered choices, reachability, and DOT output',
    reference: lines(
      '# Dialogue graph parsing reference',
      '',
      '## When to use',
      'Use this reference when a dialogue script uses bracketed scene headers, speaker lines, and numbered choices that must become a reachable directed graph.',
      '',
      '## Procedure',
      '1. Treat each bracketed `[Scene]` header as a node id.',
      '2. Parse `Speaker: text -> Target` as the scene text and a directed edge.',
      '3. Parse `1. choice text -> Target` as a choice node and a directed edge.',
      '4. Create placeholder nodes for targets, except the terminal `End` node.',
      '5. Emit `dialogue.json` with nodes and edges plus a DOT graph; choice nodes must be diamonds.',
      '',
      '## Validation',
      '- Every edge target exists except `End`.',
      '- Every non-End node is reachable from the first scene.',
      '- Choice scenes have their full branch set.',
      '- DOT contains `digraph`, braces, directed edges, and diamond choice nodes.',
      '',
      '## Failure handling',
      'If a line cannot be parsed, leave it out of the graph and report the source line. Do not invent dialogue text or targets.',
    ),
    fixturePath: 'evals/fixtures/dialogue-graph-parsing.json',
    fixture: fixtureDocument(
      'scripts/dialogue_graph.py',
      { self_test: true },
      { status: 'ok' },
    ),
    fixtureSummary: 'safe parser self-test fixture',
    runInstruction: 'When the task requires `solution.py`, copy the `parse_script` implementation from `scripts/dialogue_graph.py` into `solution.py`, then run the script on the input script to emit `dialogue.json` and `dialogue.dot`.',
  },
  'network-forensics': {
    label: 'network forensics',
    title: 'Network forensics',
    trigger: 'a packet capture must be summarized with protocol, size, entropy, graph, timing, or flow metrics',
    scriptPath: 'scripts/network_stats.py',
    script: NETWORK_SCRIPT,
    scriptSummary: 'deterministic Scapy PCAP metric extractor that fills a metric/value CSV template',
    referencePath: 'references/network-forensics.md',
    referenceSummary: 'pcap metric definitions, entropy/graph/flow rules, and analysis-flag thresholds',
    reference: lines(
      '# Network forensics reference',
      '',
      '## When to use',
      'Use this reference when a PCAP must be reduced to a metric/value CSV covering protocol counts, sizes, entropy, graph topology, inter-arrival timing, producer/consumer ratios, and 5-tuple flows.',
      '',
      '## Procedure',
      '1. Preserve the supplied CSV comments and metric column; replace only values.',
      '2. Count packets by TCP/UDP/ICMP/ARP and IP presence separately.',
      '3. Build per-minute buckets from the first timestamp, not absolute epoch boundaries.',
      '4. Compute Shannon entropy over observed IP and port frequencies.',
      '5. Build a directed IP graph and count distinct directed edges.',
      '6. Compute PCR as (sent - recv) / (sent + recv); producers > 0.2, consumers < -0.2.',
      '7. Count each bidirectional flow once; compare the reverse 5-tuple.',
      '8. Report analysis flags from the computed evidence, never from filenames.',
      '',
      '## Validation',
      '- Recompute totals and confirm packet, byte, and flow counts.',
      '- Check entropy is non-negative.',
      '- Check density uses n * (n - 1).',
      '- Confirm the output CSV still parses and comments are preserved.',
    ),
    fixturePath: 'evals/fixtures/network-forensics.json',
    fixture: fixtureDocument(
      'scripts/network_stats.py',
      { self_test: true },
      { status: 'ok' },
    ),
    fixtureSummary: 'safe PCAP metric extractor self-test fixture',
    runInstruction: 'Run `scripts/network_stats.py <pcap> <template.csv> <output.csv>` and preserve all comment rows and the metric column. Use the script output verbatim for every value, including `is_traffic_benign`, `has_port_scan`, `has_dos_pattern`, and `has_beaconing`; do not replace those flags with a subjective reclassification.',
  },
}

function skillSlug(skillIdValue: SkillId): string {
  const slug = skillIdValue
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug.length > 0 ? slug : 'evolved-skill'
}

function describeResource(path: string, content: FamilyContent): string {
  if (path === content.scriptPath) return content.scriptSummary
  if (path === content.referencePath) return content.referenceSummary
  if (path === content.fixturePath) return content.fixtureSummary
  if (path.startsWith('assets/')) return 'reusable output template'
  const kind = resourceKindOf(path)
  switch (kind) {
    case 'scripts':
      return 'deterministic helper script'
    case 'references':
      return 'conditional guidance'
    case 'evals':
      return 'safe fixture'
    case 'assets':
      return 'reusable output template'
    case 'agents':
      return 'delegated instructions'
    default:
      return 'supporting file'
  }
}

function renderSkillDocument(
  content: FamilyContent,
  slug: string,
  description: string,
  resourcePaths: readonly string[],
): string {
  const resourceLines = resourcePaths.map(
    (path) => `- \`${path}\` - ${describeResource(path, content)}`,
  )
  return lines(
    '---',
    `name: ${slug}`,
    `description: ${description}`,
    '---',
    '',
    `# ${content.title}`,
    '',
    `Use this skill when ${content.trigger}. The workflow is deterministic: normalize the input, apply the declared rules, and report unresolved gaps instead of guessing.`,
    '',
    '## Procedure',
    '',
    '1. Read the conditional reference before choosing a normalization path.',
    '2. Run the deterministic script with the task input encoded as JSON on standard input.',
    ...(content.runInstruction === undefined ? [] : [content.runInstruction]),
    '3. Compare the script report with the safe fixture before using any derived value.',
    '4. Report unresolved issues explicitly; never replace a missing value with a guess.',
    '',
    ...(content.recovery === undefined ? [] : ['## Recovery identities', '', content.recovery, '']),
    '## Resource map',
    '',
    ...resourceLines,
    '',
    '## Boundaries',
    '',
    '- Keep every intermediate value traceable to its source field or evidence record.',
    '- Do not call network, model, embedding, or paid services.',
    '- Do not invent benchmark answers or task-specific constants.',
    '',
  )
}

function ensureFrontmatter(skill: string, slug: string, description: string): string {
  const normalized = skill.replace(/\r\n/g, '\n')
  if (normalized.startsWith('---\n')) return normalized
  return `---\nname: ${slug}\ndescription: ${description}\n---\n\n${normalized}`
}

function appendResourceIndex(skill: string, resourcePaths: readonly string[]): string {
  const missing = resourcePaths.filter((path) => !skill.includes(path))
  if (missing.length === 0) return skill
  return lines(
    skill.replace(/\n+$/, ''),
    '',
    '## Resource index',
    '',
    ...missing.map((path) => `- \`${path}\``),
    '',
  )
}

interface ResourceDraft {
  readonly path: string
  readonly kind: ResourceKind
  readonly content: string
  readonly rationale: string
}

type Disposition = 'generated' | 'updated' | 'preserved' | 'unchanged'

function dispositionClassification(disposition: Disposition): ResourceUsefulnessClassification {
  switch (disposition) {
    case 'generated':
      return 'generated-justified'
    case 'updated':
      return 'updated-existing'
    case 'preserved':
      return 'preserved-existing'
    case 'unchanged':
      return 'unchanged-existing'
  }
}

function provenanceFor(
  request: SkillPlanningRequest,
  path: string,
  rationale: string,
): ResourceProvenance {
  return {
    operationId: request.operation.id,
    skillId: request.operation.skillId,
    findingId: request.finding.id,
    traceId: request.finding.traceId,
    family: request.family,
    path,
    rationale,
  }
}

function usefulnessFor(
  request: SkillPlanningRequest,
  path: string,
  disposition: Disposition,
  rationale: string,
): ResourceUsefulnessEvidence {
  const observed = request.usefulness?.find((row) => row.path === path)
  const uses = observed?.uses ?? 0
  if (uses > 0) {
    return {
      classification: 'observed-used',
      uses,
      rationale: observed?.rationale ?? rationale,
    }
  }
  return {
    classification: dispositionClassification(disposition),
    uses: 0,
    rationale,
  }
}

function sortedBundle(entries: Record<string, string>): SkillBundle {
  return Object.fromEntries(
    Object.entries(entries).sort(([left], [right]) => left.localeCompare(right)),
  )
}

function planMode(kind: OperationKind): PlanMode {
  switch (kind) {
    case 'create':
      return 'create'
    case 'update':
      return 'update'
    case 'merge':
      return 'merge'
    case 'no_change':
      return 'no_change'
    case 'split':
    case 'delete':
      throw new InvalidResourcePlanError([
        issue('$.operation.kind', 'unsupported-operation', `resource planning does not support ${kind}`),
      ])
  }
}

function buildDrafts(
  content: FamilyContent,
  request: SkillPlanningRequest,
): { drafts: ResourceDraft[]; issues: StructuredIssue[] } {
  const drafts: ResourceDraft[] = [
    {
      path: content.scriptPath,
      kind: 'scripts',
      content: content.script,
      rationale: `deterministic execution for ${content.label}`,
    },
    {
      path: content.referencePath,
      kind: 'references',
      content: content.reference,
      rationale: `substantial conditional knowledge for ${content.label}`,
    },
    {
      path: content.fixturePath,
      kind: 'evals',
      content: content.fixture,
      rationale: `safe expected-output fixture for ${content.scriptPath}`,
    },
  ]
  drafts.push(...(content.extraDrafts ?? []))
  const template = request.outputTemplate
  if (template !== undefined) {
    drafts.push({
      path: template.path,
      kind: 'assets',
      content: template.content,
      rationale: template.rationale,
    })
  }
  const issues: StructuredIssue[] = []
  const seen = new Set<string>()
  for (const draft of drafts) {
    if (seen.has(draft.path)) {
      issues.push(issue(draft.path, 'duplicate-path', `duplicate planned path ${draft.path}`))
    }
    seen.add(draft.path)
    issues.push(...validateResourcePath(draft.path))
    if (draft.content.trim().length === 0) {
      issues.push(issue(draft.path, 'empty-content', 'planned content must not be empty'))
    }
    for (const leak of scanContentForLeakage(draft.path, draft.content)) {
      issues.push(issue(draft.path, leak.code, leak.message))
    }
  }
  if (template !== undefined) {
    if (!template.path.startsWith('assets/')) {
      issues.push(issue(template.path, 'asset-path', 'an output template must live under assets/'))
    }
    if (template.rationale.trim().length === 0) {
      issues.push(issue(template.path, 'asset-rationale', 'an output template requires a reuse rationale'))
    }
    for (const leak of scanContentForLeakage(template.path, template.rationale)) {
      issues.push(issue(template.path, leak.code, `template rationale: ${leak.message}`))
    }
  }
  return { drafts, issues }
}

/**
 * Plan and render the resource bundle for one operation.
 *
 * `create` requires an empty existing bundle. `update` preserves unrelated
 * files and rewrites generated files that changed. `merge` never replaces an
 * existing resource file; both update and merge append missing resource links
 * to `SKILL.md` so every planned path stays discoverable.
 */
export function planSkillResources(request: SkillPlanningRequest): SkillPlan {
  const { operation, finding, family } = request
  const content = FAMILY_CONTENT[family]
  if (content === undefined) {
    throw new InvalidResourcePlanError([
      issue('$.family', 'unsupported-family', `unsupported failure family ${String(family)}`),
    ])
  }
  const mode = planMode(operation.kind)
  const existing = request.existingBundle ?? {}
  const issues: StructuredIssue[] = []

  for (const [path, fileContent] of Object.entries(existing)) {
    issues.push(...validateResourcePath(path))
    if (typeof fileContent !== 'string') {
      issues.push(issue(path, 'invalid-content', 'bundle content must be a string'))
    }
    for (const leak of scanContentForLeakage(path, fileContent)) {
      issues.push(issue(path, leak.code, leak.message))
    }
  }
  const existingPaths = Object.keys(existing)
  if (mode === 'create' && existingPaths.length > 0) {
    issues.push(issue('$.existingBundle', 'existing-bundle', 'create requires an empty existing bundle'))
  }
  if (mode !== 'create' && !existingPaths.includes('SKILL.md')) {
    issues.push(issue('$.existingBundle', 'missing-skill', `${mode} requires an existing SKILL.md`))
  }
  if (issues.length > 0) throw new InvalidResourcePlanError(issues)

  const existingResourcePaths = existingPaths
    .filter((path) => path !== 'SKILL.md' && resourceKindOf(path) !== undefined)
    .sort((left, right) => left.localeCompare(right))
  const slug = skillSlug(operation.skillId)
  const description = `Deterministic ${content.label} workflow with checked scripts, conditional references, and safe fixtures.`

  if (mode === 'no_change') {
    const skill = existing['SKILL.md'] ?? ''
    const skillProvenance = provenanceFor(request, 'SKILL.md', 'preserved unchanged skill document')
    const resources = existingResourcePaths.map((path) => ({
      resource: {
        id: resourceId(`${operation.id}:${path}`),
        operationId: operation.id,
        skillId: operation.skillId,
        kind: resourceKindOf(path) ?? 'references',
        path,
        status: 'used' as const,
      },
      provenance: provenanceFor(request, path, 'preserved unchanged resource'),
      usefulness: usefulnessFor(request, path, 'unchanged', 'preserved unchanged resource'),
    }))
    return {
      operationId: operation.id,
      skillId: operation.skillId,
      findingId: finding.id,
      traceId: finding.traceId,
      family,
      mode,
      provenance: {
        operationId: operation.id,
        skillId: operation.skillId,
        findingId: finding.id,
        traceId: finding.traceId,
        family,
        rationale: `no resource change for ${content.label}`,
      },
      skill: {
        path: 'SKILL.md',
        status: 'used',
        provenance: skillProvenance,
        usefulness: usefulnessFor(request, 'SKILL.md', 'unchanged', 'preserved unchanged skill document'),
      },
      resources,
      bundle: sortedBundle({ ...existing, 'SKILL.md': skill }),
    }
  }

  const built = buildDrafts(content, request)
  if (built.issues.length > 0) throw new InvalidResourcePlanError(built.issues)

  const indexPaths = [...new Set([
    ...existingResourcePaths,
    ...built.drafts.map((draft) => draft.path),
  ])].sort((left, right) => left.localeCompare(right))

  let skillContent: string
  let skillDisposition: Disposition
  const existingSkill = existing['SKILL.md']
  if (existingSkill === undefined) {
    skillContent = renderSkillDocument(content, slug, description, indexPaths)
    skillDisposition = 'generated'
  } else {
    const indexed = appendResourceIndex(
      ensureFrontmatter(existingSkill, slug, description),
      indexPaths,
    )
    skillContent = indexed
    skillDisposition = indexed === existingSkill ? 'unchanged' : 'updated'
  }

  const bundleEntries: Record<string, string> = { ...existing }
  bundleEntries['SKILL.md'] = skillContent
  const dispositions = new Map<string, Disposition>()
  dispositions.set('SKILL.md', skillDisposition)

  for (const draft of built.drafts) {
    const before = existing[draft.path]
    if (mode === 'create' || before === undefined) {
      bundleEntries[draft.path] = draft.content
      dispositions.set(draft.path, 'generated')
      continue
    }
    if (mode === 'merge') {
      dispositions.set(draft.path, 'preserved')
      continue
    }
    if (before === draft.content) {
      dispositions.set(draft.path, 'unchanged')
      continue
    }
    bundleEntries[draft.path] = draft.content
    dispositions.set(draft.path, 'updated')
  }
  for (const path of existingResourcePaths) {
    if (!dispositions.has(path)) dispositions.set(path, 'preserved')
  }

  const resourceRows: PlannedResource[] = []
  const draftByPath = new Map(built.drafts.map((draft) => [draft.path, draft]))
  const orderedPaths = [
    ...built.drafts.map((draft) => draft.path),
    ...existingResourcePaths.filter(
      (path) => !built.drafts.some((draft) => draft.path === path),
    ),
  ]
  for (const path of orderedPaths) {
    const kind = resourceKindOf(path)
    if (kind === undefined) continue
    const disposition = dispositions.get(path) ?? 'preserved'
    const status = disposition === 'generated' || disposition === 'updated' ? 'generated' : 'used'
    const draft = draftByPath.get(path)
    const rationale = disposition === 'generated'
      ? draft?.rationale ?? `generated ${kind} resource for ${content.label}`
      : disposition === 'updated'
        ? `updated existing ${kind} resource: ${draft?.rationale ?? content.label}`
        : `preserved existing ${kind} resource`
    resourceRows.push({
      resource: {
        id: resourceId(`${operation.id}:${path}`),
        operationId: operation.id,
        skillId: operation.skillId,
        kind,
        path,
        status,
      },
      provenance: provenanceFor(request, path, rationale),
      usefulness: usefulnessFor(request, path, disposition, rationale),
    })
  }

  const skillStatus = skillDisposition === 'unchanged' ? 'used' : 'generated'
  const skillRationale = skillDisposition === 'generated'
    ? `rendered skill document for ${content.label}`
    : skillDisposition === 'updated'
      ? `updated skill document for ${content.label}`
      : 'preserved unchanged skill document'

  return {
    operationId: operation.id,
    skillId: operation.skillId,
    findingId: finding.id,
    traceId: finding.traceId,
    family,
    mode,
    provenance: {
      operationId: operation.id,
      skillId: operation.skillId,
      findingId: finding.id,
      traceId: finding.traceId,
      family,
      rationale: `plan ${content.label} resources for ${mode} operation ${operation.id}`,
    },
    skill: {
      path: 'SKILL.md',
      status: skillStatus,
      provenance: provenanceFor(request, 'SKILL.md', skillRationale),
      usefulness: usefulnessFor(request, 'SKILL.md', skillDisposition, skillRationale),
    },
    resources: resourceRows,
    bundle: sortedBundle(bundleEntries),
  }
}
