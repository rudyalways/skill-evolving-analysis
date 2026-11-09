import { isRecord } from '../contracts/validation.ts'
import {
  scanContentForLeakage,
  validateResourcePath,
  type SkillBundle,
  type SkillPlan,
} from '../resources/planner.ts'

/** One check performed by the executable preflight. */
export const PREFLIGHT_CHECKS = [
  'path-safety',
  'metadata',
  'directory-structure',
  'planned-resources',
  'resource-references',
  'script-execution',
  'expected-outputs',
  'duplicate-content',
  'unused-resources',
  'benchmark-leakage',
  'prompt-budget',
  'tool-feasibility',
] as const

/** Name of one preflight check. */
export type PreflightCheckName = (typeof PREFLIGHT_CHECKS)[number]

/** Outcome of one check. */
export type PreflightCheckStatus = 'pass' | 'warn' | 'fail' | 'skipped'

/** Severity of one structured reason. */
export type PreflightReasonSeverity = 'error' | 'warning' | 'info'

/** Overall preflight verdict. */
export type PreflightVerdict = 'accept' | 'repair' | 'reject'

/** One structured reason attached to a check. */
export interface PreflightReason {
  readonly code: string
  readonly message: string
  readonly severity: PreflightReasonSeverity
  readonly path?: string
}

/** A metric value safe for reports and logs. */
export type PreflightMetricValue = string | number | boolean

/** Structured result of one preflight check. */
export interface PreflightCheck {
  readonly name: PreflightCheckName
  readonly status: PreflightCheckStatus
  readonly reasons: readonly PreflightReason[]
  readonly metrics: Readonly<Record<string, PreflightMetricValue>>
}

/** Bundle-level metrics computed without executing anything. */
export interface PreflightMetrics {
  readonly files: number
  readonly bytes: number
  readonly resources: number
  readonly scripts: number
  readonly fixtures: number
  readonly skillTokens: number
  readonly disclosedTokens: number
  readonly totalTokens: number
  readonly promptExpansionRatio: number
  readonly estimatedToolCalls: number
  readonly estimatedWallMs: number
}

/** Complete executable preflight report. */
export interface PreflightReport {
  readonly verdict: PreflightVerdict
  readonly checks: readonly PreflightCheck[]
  readonly metrics: PreflightMetrics
  readonly rejectReasons: readonly PreflightReason[]
  readonly repairReasons: readonly PreflightReason[]
}

/** One script invocation against one safe fixture. */
export interface ScriptRunRequest {
  readonly scriptPath: string
  readonly scriptContent: string
  readonly fixturePath: string
  readonly fixture: Readonly<Record<string, unknown>>
  readonly timeoutMs: number
}

/** Result returned by an injected script runner. */
export interface ScriptRunResult {
  readonly exitCode: number
  readonly stdout: string
  readonly stderr: string
  readonly wallMs: number
}

/** Injected runner boundary; preflight never executes files itself. */
export interface ScriptRunner {
  run(request: ScriptRunRequest): ScriptRunResult | Promise<ScriptRunResult>
}

/** Frozen feasibility policy for one preflight invocation. */
export interface PreflightPolicy {
  readonly maximumPromptTokens: number
  readonly maximumExpansionRatio: number
  readonly maximumToolCalls: number
  readonly maximumWallMs: number
  readonly unusedResource: 'warn' | 'fail'
  readonly maximumDuplicateContentPairs: number
  readonly requireScriptExecution: boolean
}

/** Partial policy overrides accepted at the call boundary. */
export type PreflightPolicyOverrides = Partial<PreflightPolicy>

/** Input to one executable preflight. */
export interface PreflightRequest {
  readonly bundle: SkillBundle
  readonly plan: SkillPlan
  readonly runner?: ScriptRunner
  readonly policy?: PreflightPolicyOverrides
  readonly scriptTimeoutMs?: number
}

/** Default feasibility policy. */
export const DEFAULT_PREFLIGHT_POLICY: PreflightPolicy = {
  maximumPromptTokens: 4000,
  maximumExpansionRatio: 8,
  maximumToolCalls: 24,
  maximumWallMs: 120_000,
  unusedResource: 'warn',
  maximumDuplicateContentPairs: 0,
  requireScriptExecution: false,
}

/** Default per-script timeout handed to an injected runner. */
export const DEFAULT_SCRIPT_TIMEOUT_MS = 5000

const RESOURCE_ROOTS: ReadonlySet<string> = new Set([
  'scripts',
  'references',
  'assets',
  'agents',
  'evals',
])
const ROOT_FILES: ReadonlySet<string> = new Set(['SKILL.md', 'README.md'])
const SCRIPT_EXTENSIONS = ['.py', '.js', '.mjs', '.ts', '.sh', '.rb'] as const
const FIXTURE_PATH_PATTERN = /^evals\/fixtures\/[^/]+\.json$/

function reason(
  code: string,
  message: string,
  severity: PreflightReasonSeverity,
  path?: string,
): PreflightReason {
  return { code, message, severity, ...(path === undefined ? {} : { path }) }
}

function resolvePolicy(overrides: PreflightPolicyOverrides | undefined): PreflightPolicy {
  return {
    maximumPromptTokens: overrides?.maximumPromptTokens ?? DEFAULT_PREFLIGHT_POLICY.maximumPromptTokens,
    maximumExpansionRatio: overrides?.maximumExpansionRatio ?? DEFAULT_PREFLIGHT_POLICY.maximumExpansionRatio,
    maximumToolCalls: overrides?.maximumToolCalls ?? DEFAULT_PREFLIGHT_POLICY.maximumToolCalls,
    maximumWallMs: overrides?.maximumWallMs ?? DEFAULT_PREFLIGHT_POLICY.maximumWallMs,
    unusedResource: overrides?.unusedResource ?? DEFAULT_PREFLIGHT_POLICY.unusedResource,
    maximumDuplicateContentPairs:
      overrides?.maximumDuplicateContentPairs ?? DEFAULT_PREFLIGHT_POLICY.maximumDuplicateContentPairs,
    requireScriptExecution:
      overrides?.requireScriptExecution ?? DEFAULT_PREFLIGHT_POLICY.requireScriptExecution,
  }
}

function isScriptPath(path: string): boolean {
  if (!path.startsWith('scripts/')) return false
  const lower = path.toLowerCase()
  return SCRIPT_EXTENSIONS.some((extension) => lower.endsWith(extension))
}

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4)
}

function utf8Bytes(text: string): number {
  return Buffer.byteLength(text, 'utf8')
}

interface BundleTotals {
  readonly files: number
  readonly bytes: number
  readonly scripts: number
  readonly fixtures: number
  readonly skillTokens: number
  readonly disclosedTokens: number
  readonly totalTokens: number
  readonly promptExpansionRatio: number
}

function bundleTotals(entries: readonly (readonly [string, string])[]): BundleTotals {
  let bytes = 0
  let totalTokens = 0
  let disclosedTokens = 0
  let skillTokens = 0
  let scripts = 0
  let fixtures = 0
  for (const [path, content] of entries) {
    bytes += utf8Bytes(content)
    const tokens = estimateTokens(content)
    totalTokens += tokens
    if (path === 'SKILL.md') skillTokens = tokens
    if (path === 'SKILL.md' || path.startsWith('references/') || path.startsWith('assets/')) {
      disclosedTokens += tokens
    }
    if (isScriptPath(path)) scripts += 1
    if (FIXTURE_PATH_PATTERN.test(path)) fixtures += 1
  }
  return {
    files: entries.length,
    bytes,
    scripts,
    fixtures,
    skillTokens,
    disclosedTokens,
    totalTokens,
    promptExpansionRatio: disclosedTokens / Math.max(skillTokens, 1),
  }
}

function buildCheck(
  name: PreflightCheckName,
  errors: readonly PreflightReason[],
  warnings: readonly PreflightReason[],
  metrics: Record<string, PreflightMetricValue>,
  skippedReason?: string,
): PreflightCheck {
  const status: PreflightCheckStatus = errors.length > 0
    ? 'fail'
    : warnings.length > 0
      ? 'warn'
      : skippedReason !== undefined
        ? 'skipped'
        : 'pass'
  const reasons = [
    ...errors,
    ...warnings,
    ...(skippedReason === undefined
      ? []
      : [reason('skipped', skippedReason, 'info')]),
  ]
  return { name, status, reasons, metrics }
}

function checkPathSafety(entries: readonly (readonly [string, string])[]): PreflightCheck {
  const errors: PreflightReason[] = []
  for (const [path] of entries) {
    for (const issue of validateResourcePath(path)) {
      errors.push(reason(issue.code, issue.message, 'error', path))
    }
  }
  return buildCheck('path-safety', errors, [], { files: entries.length })
}

interface Frontmatter {
  readonly fields: Readonly<Record<string, string>>
}

function parseFrontmatter(text: string): Frontmatter | undefined {
  const normalized = text.replace(/\r\n/g, '\n')
  if (!normalized.startsWith('---\n')) return undefined
  const end = normalized.indexOf('\n---', 4)
  if (end < 0) return undefined
  const fields: Record<string, string> = {}
  for (const line of normalized.slice(4, end).split('\n')) {
    const match = /^([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*$/.exec(line)
    if (!match) continue
    const key = match[1]
    const value = match[2]
    if (key === undefined || value === undefined) continue
    fields[key] = value.replace(/^["']|["']$/g, '')
  }
  return { fields }
}

function checkMetadata(bundle: SkillBundle): PreflightCheck {
  const errors: PreflightReason[] = []
  const metrics: Record<string, PreflightMetricValue> = { present: false, descriptionLength: 0 }
  const skill = bundle['SKILL.md']
  if (skill === undefined) {
    errors.push(reason('missing-skill', 'bundle must contain SKILL.md', 'error', 'SKILL.md'))
    return buildCheck('metadata', errors, [], metrics)
  }
  metrics.present = true
  const frontmatter = parseFrontmatter(skill)
  if (frontmatter === undefined) {
    errors.push(reason('missing-frontmatter', 'SKILL.md must start with YAML frontmatter', 'error', 'SKILL.md'))
    return buildCheck('metadata', errors, [], metrics)
  }
  const name = frontmatter.fields.name
  const description = frontmatter.fields.description
  if (name === undefined || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name)) {
    errors.push(reason('invalid-name', 'frontmatter name must be a kebab-case slug', 'error', 'SKILL.md'))
  }
  if (description === undefined || description.trim().length < 10) {
    errors.push(reason('invalid-description', 'frontmatter description must be a meaningful sentence', 'error', 'SKILL.md'))
  } else {
    metrics.descriptionLength = description.trim().length
  }
  return buildCheck('metadata', errors, [], metrics)
}

function checkStructure(bundle: SkillBundle): PreflightCheck {
  const errors: PreflightReason[] = []
  for (const path of Object.keys(bundle)) {
    const root = path.split('/')[0]
    if (root === undefined) {
      errors.push(reason('invalid-root', 'path has no root segment', 'error', path))
      continue
    }
    if (path.includes('/')) {
      if (!RESOURCE_ROOTS.has(root)) {
        errors.push(reason('unknown-root', `unsupported top-level directory ${root}`, 'error', path))
      }
    } else if (!ROOT_FILES.has(root)) {
      errors.push(reason('unknown-root-file', `unsupported root file ${root}`, 'error', path))
    }
  }
  if (!Object.prototype.hasOwnProperty.call(bundle, 'SKILL.md')) {
    errors.push(reason('missing-skill', 'bundle must contain SKILL.md', 'error', 'SKILL.md'))
  }
  return buildCheck('directory-structure', errors, [], { files: Object.keys(bundle).length })
}

function checkPlannedResources(bundle: SkillBundle, plan: SkillPlan): PreflightCheck {
  const errors: PreflightReason[] = []
  const plannedPaths = [plan.skill.path, ...plan.resources.map((row) => row.resource.path)]
  const seen = new Set<string>()
  for (const path of plannedPaths) {
    if (seen.has(path)) {
      errors.push(reason('duplicate-plan-path', `plan lists ${path} more than once`, 'error', path))
      continue
    }
    seen.add(path)
    if (!Object.prototype.hasOwnProperty.call(bundle, path)) {
      errors.push(reason('missing-planned-file', `planned file ${path} is absent from the bundle`, 'error', path))
    }
  }
  for (const row of plan.resources) {
    for (const issue of validateResourcePath(row.resource.path)) {
      errors.push(reason(issue.code, issue.message, 'error', row.resource.path))
    }
    const root = row.resource.path.split('/')[0]
    if (root !== row.resource.kind) {
      errors.push(reason(
        'kind-path-mismatch',
        `resource kind ${row.resource.kind} does not match path root ${String(root)}`,
        'error',
        row.resource.path,
      ))
    }
  }
  return buildCheck('planned-resources', errors, [], {
    planned: plannedPaths.length,
    resources: plan.resources.length,
  })
}

function extractReferences(content: string): readonly string[] {
  const pattern = /(?:^|[^A-Za-z0-9._/-])((?:\.\/)?(?:scripts|references|assets|agents|evals)\/[A-Za-z0-9._/-]+)/g
  const found = new Set<string>()
  for (const match of content.matchAll(pattern)) {
    const raw = match[1]
    if (raw === undefined) continue
    const path = raw.replace(/^\.\//, '').replace(/[.,;:]+$/, '')
    if (path.length > 0) found.add(path)
  }
  return [...found].sort((left, right) => left.localeCompare(right))
}

function checkReferences(bundle: SkillBundle): PreflightCheck {
  const errors: PreflightReason[] = []
  const seen = new Set<string>()
  let referenceCount = 0
  for (const [path, content] of Object.entries(bundle)) {
    for (const reference of extractReferences(content)) {
      referenceCount += 1
      if (reference === path) continue
      const key = `${path}->${reference}`
      if (seen.has(key)) continue
      seen.add(key)
      if (validateResourcePath(reference).length > 0) {
        errors.push(reason(
          'unsafe-reference',
          `reference ${reference} is not a safe bundle path`,
          'error',
          path,
        ))
        continue
      }
      if (!Object.prototype.hasOwnProperty.call(bundle, reference)) {
        errors.push(reason(
          'unresolved-reference',
          `reference ${reference} does not resolve to a bundle file`,
          'error',
          path,
        ))
      }
    }
  }
  return buildCheck('resource-references', errors, [], {
    references: referenceCount,
    unresolved: errors.length,
  })
}

function parseJson(text: string): { readonly ok: true; readonly value: unknown } | { readonly ok: false } {
  try {
    const value: unknown = JSON.parse(text)
    return { ok: true, value }
  } catch {
    return { ok: false }
  }
}

interface ParsedFixture {
  readonly path: string
  readonly script: string
  readonly raw: Readonly<Record<string, unknown>>
  readonly expected: Readonly<Record<string, unknown>>
}

type ParseFixtureResult =
  | { readonly ok: true; readonly fixture: ParsedFixture }
  | { readonly ok: false; readonly reasons: readonly PreflightReason[] }

function parseFixture(path: string, content: string): ParseFixtureResult {
  const parsed = parseJson(content)
  if (!parsed.ok || !isRecord(parsed.value)) {
    return {
      ok: false,
      reasons: [reason('invalid-fixture-json', `${path} must contain a JSON object`, 'error', path)],
    }
  }
  const raw = parsed.value
  const reasons: PreflightReason[] = []
  if (raw.schemaVersion !== undefined && raw.schemaVersion !== 1) {
    reasons.push(reason('unsupported-fixture-version', 'fixture schemaVersion must be 1 when present', 'error', path))
  }
  const scriptValue = raw.script
  if (typeof scriptValue !== 'string' || scriptValue.trim().length === 0) {
    return {
      ok: false,
      reasons: [...reasons, reason('fixture-script', 'fixture must declare a script path', 'error', path)],
    }
  }
  const script = scriptValue
  if (!script.startsWith('scripts/')) {
    reasons.push(reason('fixture-script-root', 'fixture script must live under scripts/', 'error', path))
  }
  for (const issue of validateResourcePath(script)) {
    reasons.push(reason(issue.code, issue.message, 'error', path))
  }
  const input = raw.input
  if (!isRecord(input)) {
    return {
      ok: false,
      reasons: [...reasons, reason('fixture-input', 'fixture input must be a JSON object', 'error', path)],
    }
  }
  const expected = raw.expect
  if (!isRecord(expected)) {
    return {
      ok: false,
      reasons: [...reasons, reason('fixture-expect', 'fixture expect must be a JSON object', 'error', path)],
    }
  }
  if (reasons.length > 0) return { ok: false, reasons }
  return { ok: true, fixture: { path, script, raw, expected } }
}

function matchesExpected(actual: unknown, expected: unknown): boolean {
  if (isRecord(expected)) {
    if (!isRecord(actual)) return false
    return Object.entries(expected).every(
      ([key, value]) => Object.prototype.hasOwnProperty.call(actual, key)
        && matchesExpected(actual[key], value),
    )
  }
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || actual.length !== expected.length) return false
    return expected.every((value, index) => matchesExpected(actual[index], value))
  }
  return actual === expected
}

interface ScriptRunRecord {
  readonly scriptPath: string
  readonly fixturePath: string
  readonly expected: Readonly<Record<string, unknown>>
  readonly outcome: 'ran' | 'runner-error'
  readonly result?: ScriptRunResult
  readonly error?: PreflightReason
}

interface ExecutionState {
  readonly fixtures: readonly ParsedFixture[]
  readonly fixtureErrors: readonly PreflightReason[]
  readonly records: readonly ScriptRunRecord[]
  readonly missingFixtures: readonly string[]
  readonly orphanFixtures: readonly string[]
  readonly scriptCount: number
  readonly runnerMissing: boolean
}

async function executeScripts(
  entries: readonly (readonly [string, string])[],
  runner: ScriptRunner | undefined,
  timeoutMs: number,
): Promise<ExecutionState> {
  const fileMap = new Map(entries)
  const fixtures: ParsedFixture[] = []
  const fixtureErrors: PreflightReason[] = []
  for (const [path, content] of entries) {
    if (!FIXTURE_PATH_PATTERN.test(path)) continue
    const parsed = parseFixture(path, content)
    if (parsed.ok) fixtures.push(parsed.fixture)
    else fixtureErrors.push(...parsed.reasons)
  }

  const fixtureByScript = new Map<string, ParsedFixture[]>()
  const orphanFixtures: string[] = []
  for (const fixture of fixtures) {
    if (!fileMap.has(fixture.script)) {
      orphanFixtures.push(fixture.path)
      continue
    }
    const rows = fixtureByScript.get(fixture.script) ?? []
    rows.push(fixture)
    fixtureByScript.set(fixture.script, rows)
  }

  const scripts = entries.filter(([path]) => isScriptPath(path))
  const missingFixtures = scripts
    .filter(([path]) => !fixtureByScript.has(path))
    .map(([path]) => path)
  const records: ScriptRunRecord[] = []
  if (runner !== undefined) {
    for (const [scriptPath, scriptContent] of scripts) {
      for (const fixture of fixtureByScript.get(scriptPath) ?? []) {
        try {
          const result = await runner.run({
            scriptPath,
            scriptContent,
            fixturePath: fixture.path,
            fixture: fixture.raw,
            timeoutMs,
          })
          records.push({
            scriptPath,
            fixturePath: fixture.path,
            expected: fixture.expected,
            outcome: 'ran',
            result,
          })
        } catch (error) {
          records.push({
            scriptPath,
            fixturePath: fixture.path,
            expected: fixture.expected,
            outcome: 'runner-error',
            error: reason(
              'runner-error',
              error instanceof Error && error.message.length > 0
                ? `runner failed: ${error.message}`
                : 'runner failed without a message',
              'error',
              scriptPath,
            ),
          })
        }
      }
    }
  }

  return {
    fixtures,
    fixtureErrors,
    records,
    missingFixtures,
    orphanFixtures,
    scriptCount: scripts.length,
    runnerMissing: scripts.length > 0 && runner === undefined,
  }
}

function checkScriptExecution(
  state: ExecutionState,
  policy: PreflightPolicy,
  timeoutMs: number,
): PreflightCheck {
  const errors: PreflightReason[] = []
  for (const scriptPath of state.missingFixtures) {
    errors.push(reason('missing-fixture', `script ${scriptPath} has no safe fixture`, 'error', scriptPath))
  }
  if (state.runnerMissing && policy.requireScriptExecution) {
    errors.push(reason('runner-required', 'policy requires a script runner', 'error'))
  }
  let failed = 0
  for (const record of state.records) {
    if (record.outcome === 'runner-error') {
      failed += 1
      if (record.error) errors.push(record.error)
      continue
    }
    const result = record.result
    if (result === undefined) continue
    if (result.exitCode !== 0) {
      failed += 1
      errors.push(reason(
        'script-failed',
        `script exited with code ${result.exitCode}: ${result.stderr.trim().slice(0, 160)}`,
        'error',
        record.scriptPath,
      ))
    } else if (result.wallMs > timeoutMs) {
      failed += 1
      errors.push(reason(
        'script-timeout',
        `script used ${result.wallMs}ms, above the ${timeoutMs}ms limit`,
        'error',
        record.scriptPath,
      ))
    }
  }
  const skipped = state.runnerMissing && !policy.requireScriptExecution && errors.length === 0
  if (skipped) {
    return buildCheck('script-execution', errors, [], {
      scripts: state.scriptCount,
      fixtures: state.fixtures.length,
      executed: 0,
      failed: 0,
    }, 'no script runner supplied; execution checks were skipped')
  }
  return buildCheck('script-execution', errors, [], {
    scripts: state.scriptCount,
    fixtures: state.fixtures.length,
    executed: state.records.filter((record) => record.outcome === 'ran').length,
    failed,
  })
}

function checkExpectedOutputs(state: ExecutionState): PreflightCheck {
  const errors: PreflightReason[] = [...state.fixtureErrors]
  for (const fixturePath of state.orphanFixtures) {
    errors.push(reason('orphan-fixture', `fixture ${fixturePath} targets a missing script`, 'error', fixturePath))
  }
  let checked = 0
  let matched = 0
  for (const record of state.records) {
    if (record.outcome !== 'ran' || record.result === undefined) continue
    if (record.result.exitCode !== 0) continue
    checked += 1
    const parsed = parseJson(record.result.stdout)
    if (!parsed.ok || !isRecord(parsed.value)) {
      errors.push(reason(
        'invalid-script-output',
        'script stdout must be a JSON object',
        'error',
        record.scriptPath,
      ))
      continue
    }
    if (!matchesExpected(parsed.value, record.expected)) {
      errors.push(reason(
        'output-mismatch',
        `script output does not match ${record.fixturePath}`,
        'error',
        record.scriptPath,
      ))
      continue
    }
    matched += 1
  }
  const skipped = state.runnerMissing
    && state.fixtureErrors.length === 0
    && state.orphanFixtures.length === 0
  if (skipped) {
    return buildCheck('expected-outputs', errors, [], {
      fixtures: state.fixtures.length,
      checked: 0,
      matched: 0,
    }, 'no script runner supplied; expected outputs were not checked')
  }
  return buildCheck('expected-outputs', errors, [], {
    fixtures: state.fixtures.length,
    checked,
    matched,
  })
}

function normalizeContent(content: string): string {
  return content
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n+/g, '\n')
    .trim()
}

function checkDuplicates(
  entries: readonly (readonly [string, string])[],
  policy: PreflightPolicy,
): PreflightCheck {
  const errors: PreflightReason[] = []
  const warnings: PreflightReason[] = []
  const groups = new Map<string, string[]>()
  for (const [path, content] of entries) {
    const normalized = normalizeContent(content)
    if (normalized.length === 0) continue
    const paths = groups.get(normalized) ?? []
    paths.push(path)
    groups.set(normalized, paths)
  }
  let duplicatePairs = 0
  for (const paths of groups.values()) {
    if (paths.length < 2) continue
    duplicatePairs += (paths.length * (paths.length - 1)) / 2
    if (duplicatePairs > policy.maximumDuplicateContentPairs) {
      errors.push(reason(
        'duplicate-content',
        `identical normalized content in ${paths.join(', ')}`,
        'error',
        paths[0],
      ))
    }
  }

  const linesByPath = new Map<string, Set<string>>()
  for (const [path, content] of entries) {
    for (const line of content.split('\n')) {
      const normalized = line.replace(/\s+/g, ' ').trim()
      if (normalized.length < 60) continue
      const paths = linesByPath.get(normalized) ?? new Set<string>()
      paths.add(path)
      linesByPath.set(normalized, paths)
    }
  }
  let duplicateLines = 0
  for (const [line, paths] of linesByPath) {
    if (paths.size < 2) continue
    duplicateLines += 1
    warnings.push(reason(
      'duplicate-line',
      `repeated line across ${[...paths].sort().join(', ')}: ${line.slice(0, 80)}`,
      'warning',
      [...paths][0],
    ))
  }

  return buildCheck('duplicate-content', errors, warnings, {
    duplicatePairs,
    duplicateLines,
    files: entries.length,
  })
}

function checkUnused(
  entries: readonly (readonly [string, string])[],
  policy: PreflightPolicy,
): PreflightCheck {
  const referenced = new Set<string>()
  for (const [path, content] of entries) {
    for (const reference of extractReferences(content)) {
      if (reference !== path) referenced.add(reference)
    }
  }
  const errors: PreflightReason[] = []
  const warnings: PreflightReason[] = []
  const severity: PreflightReasonSeverity = policy.unusedResource === 'fail' ? 'error' : 'warning'
  let unused = 0
  for (const [path] of entries) {
    if (path === 'SKILL.md') continue
    const root = path.split('/')[0]
    if (root === undefined || !RESOURCE_ROOTS.has(root)) continue
    if (root === 'evals') continue
    if (referenced.has(path)) continue
    unused += 1
    const entry = reason(
      'unused-resource',
      `${path} is not referenced by SKILL.md or another resource`,
      severity,
      path,
    )
    if (severity === 'error') errors.push(entry)
    else warnings.push(entry)
  }
  return buildCheck('unused-resources', errors, warnings, { unused, files: entries.length })
}

function checkLeakage(entries: readonly (readonly [string, string])[]): PreflightCheck {
  const errors: PreflightReason[] = []
  for (const [path, content] of entries) {
    for (const leak of scanContentForLeakage(path, content)) {
      errors.push(reason(leak.code, leak.message, 'error', leak.path))
    }
  }
  return buildCheck('benchmark-leakage', errors, [], {
    leaks: errors.length,
    files: entries.length,
  })
}

function checkPromptBudget(totals: BundleTotals, policy: PreflightPolicy): PreflightCheck {
  const errors: PreflightReason[] = []
  if (totals.disclosedTokens > policy.maximumPromptTokens) {
    errors.push(reason(
      'prompt-too-large',
      `estimated prompt is ${totals.disclosedTokens} tokens, above the ${policy.maximumPromptTokens} token budget`,
      'error',
      'SKILL.md',
    ))
  }
  if (totals.promptExpansionRatio > policy.maximumExpansionRatio) {
    errors.push(reason(
      'prompt-expansion',
      `prompt expansion ratio ${totals.promptExpansionRatio.toFixed(2)} exceeds ${policy.maximumExpansionRatio}`,
      'error',
      'SKILL.md',
    ))
  }
  return buildCheck('prompt-budget', errors, [], {
    skillTokens: totals.skillTokens,
    disclosedTokens: totals.disclosedTokens,
    totalTokens: totals.totalTokens,
    expansionRatio: Number(totals.promptExpansionRatio.toFixed(3)),
    maximumPromptTokens: policy.maximumPromptTokens,
  })
}

function estimatedWallMs(
  totals: BundleTotals,
  plan: SkillPlan,
  timeoutMs: number,
): number {
  const runs = Math.max(totals.scripts, totals.fixtures)
  return runs * timeoutMs + plan.resources.length * 250
}

function checkToolFeasibility(
  totals: BundleTotals,
  plan: SkillPlan,
  timeoutMs: number,
  policy: PreflightPolicy,
): PreflightCheck {
  const estimatedToolCalls = plan.resources.length + totals.scripts + totals.fixtures
  const wallEstimate = estimatedWallMs(totals, plan, timeoutMs)
  const errors: PreflightReason[] = []
  if (estimatedToolCalls > policy.maximumToolCalls) {
    errors.push(reason(
      'tool-budget',
      `estimated ${estimatedToolCalls} tool calls exceed the ${policy.maximumToolCalls} call budget`,
      'error',
    ))
  }
  if (wallEstimate > policy.maximumWallMs) {
    errors.push(reason(
      'wall-budget',
      `estimated ${wallEstimate}ms exceeds the ${policy.maximumWallMs}ms wall budget`,
      'error',
    ))
  }
  return buildCheck('tool-feasibility', errors, [], {
    estimatedToolCalls,
    estimatedWallMs: wallEstimate,
    scripts: totals.scripts,
    fixtures: totals.fixtures,
    maximumToolCalls: policy.maximumToolCalls,
    maximumWallMs: policy.maximumWallMs,
  })
}

function finalizeReport(
  checks: readonly PreflightCheck[],
  metrics: PreflightMetrics,
): PreflightReport {
  const rejectReasons = checks.flatMap(
    (check) => check.reasons.filter((entry) => entry.severity === 'error'),
  )
  const repairReasons = checks.flatMap(
    (check) => check.reasons.filter((entry) => entry.severity === 'warning'),
  )
  const verdict: PreflightVerdict = rejectReasons.length > 0
    ? 'reject'
    : repairReasons.length > 0
      ? 'repair'
      : 'accept'
  return { verdict, checks, metrics, rejectReasons, repairReasons }
}

/**
 * Run every executable preflight check against a rendered bundle.
 *
 * The function is offline and model-free. Scripts are executed only through an
 * injected `ScriptRunner`; when no runner is supplied, execution and expected
 * output checks are reported as skipped unless policy requires execution.
 */
export async function preflight(request: PreflightRequest): Promise<PreflightReport> {
  const policy = resolvePolicy(request.policy)
  const timeoutMs = request.scriptTimeoutMs ?? DEFAULT_SCRIPT_TIMEOUT_MS
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new Error('scriptTimeoutMs must be a positive finite number')
  }
  const entries = Object.entries(request.bundle)
    .sort(([left], [right]) => left.localeCompare(right))
  const totals = bundleTotals(entries)
  const metrics: PreflightMetrics = {
    files: totals.files,
    bytes: totals.bytes,
    resources: request.plan.resources.length,
    scripts: totals.scripts,
    fixtures: totals.fixtures,
    skillTokens: totals.skillTokens,
    disclosedTokens: totals.disclosedTokens,
    totalTokens: totals.totalTokens,
    promptExpansionRatio: Number(totals.promptExpansionRatio.toFixed(3)),
    estimatedToolCalls: request.plan.resources.length + totals.scripts + totals.fixtures,
    estimatedWallMs: estimatedWallMs(totals, request.plan, timeoutMs),
  }
  const execution = await executeScripts(entries, request.runner, timeoutMs)
  const checks: PreflightCheck[] = [
    checkPathSafety(entries),
    checkMetadata(request.bundle),
    checkStructure(request.bundle),
    checkPlannedResources(request.bundle, request.plan),
    checkReferences(request.bundle),
    checkScriptExecution(execution, policy, timeoutMs),
    checkExpectedOutputs(execution),
    checkDuplicates(entries, policy),
    checkUnused(entries, policy),
    checkLeakage(entries),
    checkPromptBudget(totals, policy),
    checkToolFeasibility(totals, request.plan, timeoutMs, policy),
  ]
  return finalizeReport(checks, metrics)
}
