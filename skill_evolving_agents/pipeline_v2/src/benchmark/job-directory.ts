/**
 * Import real SkillsBench/BenchFlow job directories into the native v2
 * benchmark observation shape.
 *
 * A job directory captured by the runner is a file-system artifact, not a
 * trusted benchmark cell.  This adapter reads and cross-checks the artifact so
 * that a cell enters {@link admitObservations} only when its evidence is
 * complete and internally consistent:
 *
 * - `result.json` supplies task/rollout identity, skill mode, supplied skill
 *   directories, counters, tokens, cost, and structured errors;
 * - `verifier/reward.txt` is the authoritative outcome; only `reward >= 1.0`
 *   counts as a complete pass and partial rewards stay visible;
 * - `timing.json` (or `result.json`'s embedded timing) supplies agent
 *   execution latency in seconds;
 * - the ACP/LLM trajectory (or an ATIF document) supplies skill activation and
 *   contamination evidence.
 *
 * Missing or contradictory evidence becomes a structured exclusion reason.
 * Values are never guessed: a missing cost stays `null` (distinct from `0`),
 * a missing tool-call count or latency blocks the cell, and skill activation is
 * never inferred from `requested_skills_dir` / `effective_skills_dir` or from
 * the runner's `n_skill_invocations` counter.
 *
 * Every import is historical benchmark material.  The returned provenance
 * marks it as ineligible for search feedback, so a holdout cohort can never be
 * routed back into the search loop through this adapter.
 */

import { createHash } from 'node:crypto'
import type { Dirent } from 'node:fs'
import { createReadStream } from 'node:fs'
import { readFile, readdir, stat } from 'node:fs/promises'
import { basename, dirname, join, resolve } from 'node:path'
import { createInterface } from 'node:readline'

import {
  admitObservations,
  type AdmissionReasonCode,
  type BenchmarkObservation,
  type ConditionObservation,
  type ObservationConditionName,
  type SkillActivationMode,
  type SkillExposureAudit,
  type SkillMode,
} from './admission.ts'
import { isFiniteNumber, isRecord } from '../contracts/validation.ts'

/** Provenance kind tag for every historical job-directory import. */
export const JOB_DIRECTORY_PROVENANCE_KIND = 'historical-job-directory' as const

/** Default hard efficiency budget, mirroring `evaluation/trial-budgets.json`. */
export interface JobDirectoryBudget {
  readonly wallSeconds: number
  readonly toolCalls: number
  readonly costUsd: number
}

/** Hard wall/tool/cost ceilings applied to one imported condition. */
export const DEFAULT_JOB_EFFICIENCY_BUDGET: JobDirectoryBudget = {
  wallSeconds: 900,
  toolCalls: 120,
  costUsd: 2,
}

/** Historical import provenance: never eligible as search feedback. */
export interface JobDirectoryProvenance {
  readonly kind: typeof JOB_DIRECTORY_PROVENANCE_KIND
  readonly source: 'skillsbench-job-directory'
  /** Imported cohorts are audit inputs only; they never feed skill search. */
  readonly searchFeedbackEligible: false
}

const JOB_DIRECTORY_PROVENANCE: JobDirectoryProvenance = {
  kind: JOB_DIRECTORY_PROVENANCE_KIND,
  source: 'skillsbench-job-directory',
  searchFeedbackEligible: false,
}

/** Formats the trajectory reader understands. */
export type JobDirectoryTrajectoryFormat = 'acp-jsonl' | 'llm-jsonl' | 'atif-json'

/** One non-fatal observation about otherwise readable evidence. */
export interface JobDirectoryIssue {
  readonly code: string
  readonly detail: string
}

/** Task and rollout identity read from the runner artifact. */
export interface JobDirectoryIdentity {
  readonly taskName: string
  readonly rolloutName: string
  /** Basename of the rollout directory; may be a human rename, not identity. */
  readonly directoryName: string
  /** Run timestamp directory when the job follows the runner layout. */
  readonly timestamp: string | null
  /** SHA-256 over the small identity-bearing files in the directory. */
  readonly artifactHash: string
}

/** Verifier outcome read from `verifier/reward.txt` and result.json. */
export interface JobDirectoryReward {
  /** Trimmed text of `verifier/reward.txt`, or null when the file is absent. */
  readonly raw: string | null
  /** Parsed verifier reward, or null when absent/unreadable. */
  readonly value: number | null
  /** Reward reported in `result.json` (`rewards.reward`) for cross-checking. */
  readonly reported: number | null
  /** True only for a complete verifier pass (`value >= 1.0`). */
  readonly complete: boolean
}

/** Token counters normalized from `agent_result` / `final_metrics`. */
export interface JobDirectoryTokens {
  readonly input: number | null
  readonly output: number | null
  readonly cacheRead: number | null
  readonly total: number | null
}

/** One hard-budget ceiling crossed by an imported condition. */
export type JobDirectoryBudgetMetric = 'wall-seconds' | 'tool-calls' | 'cost-usd'

/** One hard-budget violation. */
export interface JobDirectoryBudgetViolation {
  readonly metric: JobDirectoryBudgetMetric
  readonly limit: number
  readonly observed: number
}

/** Hard-budget verdict for one imported condition. */
export interface JobDirectoryEfficiency {
  readonly failure: boolean
  readonly withinBudget: boolean
  readonly violations: readonly JobDirectoryBudgetViolation[]
}

/** Trajectory audit result; activation is derived only from the trajectory. */
export interface JobDirectoryTrajectoryAudit {
  readonly path: string | null
  readonly format: JobDirectoryTrajectoryFormat | null
  /** True when the trajectory was read and every parsed event was usable. */
  readonly verified: boolean
  readonly activated: boolean
  readonly activationMode: SkillActivationMode | null
  /** Skill names with an observed SKILL.md read. */
  readonly readSkills: readonly string[]
  /** Skill names observed mounted/injected into the prompt. */
  readonly injectedSkills: readonly string[]
  readonly events: number
  readonly parseErrors: number
}

/** Trial-validity findings emitted as native contamination codes. */
export type JobDirectoryContaminationReason =
  | 'remote-answer-discovery'
  | 'task-specific-answer-artifact'

/** One contaminated trajectory event kept for audit. */
export interface JobDirectoryContaminationMatch {
  /** 1-based event ordinal within the audited trajectory. */
  readonly event: number
  readonly tool: string | null
  readonly reason: JobDirectoryContaminationReason
}

/** Complete evidence read from one job directory. */
export interface JobDirectoryEvidence {
  readonly directory: string
  readonly identity: JobDirectoryIdentity
  readonly reward: JobDirectoryReward
  /** True only for a complete verifier pass (`reward >= 1.0`). */
  readonly passed: boolean
  /** True when `0 < reward < 1`; partial rewards are preserved, not rounded. */
  readonly partialReward: boolean
  readonly skillMode: SkillMode | null
  readonly rawSkillMode: string | null
  readonly requestedSkillsDir: string | null
  readonly effectiveSkillsDir: string | null
  readonly skillSource: string | null
  readonly toolCalls: number | null
  readonly skillInvocations: number | null
  readonly tokens: JobDirectoryTokens
  readonly costUsd: number | null
  readonly latencyMs: number | null
  readonly efficiency: JobDirectoryEfficiency
  /** Native exposure audit; null when `skill_mode` is absent/unrecognized. */
  readonly exposure: SkillExposureAudit | null
  readonly trajectory: JobDirectoryTrajectoryAudit
  /** Contamination codes found by the trial-validity scan. */
  readonly contamination: readonly string[]
  /** Event-level contamination evidence backing `contamination`. */
  readonly contaminationMatches: readonly JobDirectoryContaminationMatch[]
  /** Structured runner/verifier failures; null when the condition ran cleanly. */
  readonly infrastructureError: string | null
  /** Individual failure descriptions backing `infrastructureError`. */
  readonly errors: readonly string[]
  readonly issues: readonly JobDirectoryIssue[]
  readonly provenance: JobDirectoryProvenance
}

/** Input for the pure observation assembler. */
export interface BuildBenchmarkObservationInput {
  readonly baseline: JobDirectoryEvidence
  readonly treatment: JobDirectoryEvidence
  readonly taskId: string
  readonly trial: number
  readonly domain: string
  readonly routerSelected: boolean
}

/** Input for {@link readPairedJobDirectories}. */
export interface ReadPairedJobDirectoriesOptions {
  readonly baseline: string
  readonly treatment: string
  readonly taskId: string
  readonly trial: number
  readonly domain: string
  readonly routerSelected: boolean
  readonly budget?: JobDirectoryBudget
}

/**
 * Exclusion codes emitted by this adapter.
 *
 * Native admission codes are reused verbatim so callers can consume pair-level
 * and admission-level reasons through one vocabulary.
 */
export type JobDirectoryExclusionCode =
  | AdmissionReasonCode
  | 'copied-baseline-treatment'
  | 'task-identity-mismatch'
  | 'missing-required-evidence'
  | 'missing-skill-mode'
  | 'malformed-job-directory'
  | 'missing-job-directory'
  | 'ambiguous-job-directory'
  | 'contradictory-reward-evidence'
  | 'invalid-pair-request'

/** One structured reason a pair could not produce a benchmark observation. */
export interface JobDirectoryExclusionReason {
  readonly code: JobDirectoryExclusionCode
  readonly condition: ObservationConditionName
  readonly detail: string
}

/** Result of importing one paired baseline/treatment cell. */
export interface ReadPairedJobDirectoriesResult {
  /** Present only when the pair passed adapter checks and native admission. */
  readonly observation?: BenchmarkObservation
  readonly exclusionReasons: readonly JobDirectoryExclusionReason[]
  readonly provenance: JobDirectoryProvenance
  /** True when the treatment evidence is an explicit abstention reusing baseline. */
  readonly baselineInherited: boolean
  readonly baseline: JobDirectoryEvidence | null
  readonly treatment: JobDirectoryEvidence | null
}

/** Fatal reason a job directory could not be turned into evidence. */
export type JobDirectoryErrorCode =
  | 'missing-job-directory'
  | 'ambiguous-job-directory'
  | 'missing-required-file'
  | 'malformed-json'
  | 'invalid-result'
  | 'invalid-pair-request'
  | 'missing-skill-mode'
  | 'missing-measurement'
  | 'task-identity-mismatch'
  | 'invalid-trial'

/** Structured error raised by the job-directory reader. */
export class JobDirectoryError extends Error {
  readonly code: JobDirectoryErrorCode
  readonly directory: string | null
  readonly condition: ObservationConditionName | null
  readonly detail: string

  constructor(
    code: JobDirectoryErrorCode,
    directory: string | null,
    detail: string,
    condition: ObservationConditionName | null = null,
  ) {
    super(`${code}: ${detail}`)
    this.name = 'JobDirectoryError'
    this.code = code
    this.directory = directory
    this.condition = condition
    this.detail = detail
  }
}

const TIMESTAMP_DIRECTORY = /^\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2}$/
const MAX_BUFFERED_TRAJECTORY_BYTES = 8 * 1024 * 1024
const REWARD_TOLERANCE = 1e-6

const MOUNTED_SKILL =
  /<mounted-skill\s+path=(?:\/skills|\/\.agents\/skills|\/\.claude\/skills|\/\.codex\/skills)\/([a-z0-9][a-z0-9._-]*)\/SKILL\.md>/i
const SKILL_FRONTMATTER =
  /^---\s*$.*?^name:\s*([a-z0-9][a-z0-9._-]*)\s*$.*?^description:\s*\S/ims

const REMOTE_TOOL = /\b(curl|wget|git\s+clone|google|duckduckgo|github)\b/i
const ANSWER_MARKER =
  /(?:artifacts\/(?:skills|solutions?)\/|(?:^|\/)oracle(?:\/|\b)|(?:^|\/)solution(?:\/|\b)|benchmark.{0,30}(?:answer|solution))/i

const FAILURE_FIELDS: readonly { readonly key: string; readonly label: string }[] = [
  { key: 'error', label: 'error' },
  { key: 'error_category', label: 'error-category' },
  { key: 'export_error', label: 'export-error' },
  { key: 'verifier_error', label: 'verifier-error' },
  { key: 'verifier_error_category', label: 'verifier-error-category' },
  { key: 'agent_timeout_info', label: 'agent-timeout' },
  { key: 'verifier_timeout_info', label: 'verifier-timeout' },
  { key: 'idle_timeout_info', label: 'idle-timeout' },
  { key: 'sandbox_startup_info', label: 'sandbox-startup' },
  { key: 'transport_error_info', label: 'transport-error' },
  { key: 'api_error_info', label: 'api-error' },
  { key: 'suspected_api_error_info', label: 'suspected-api-error' },
]

const TRAJECTORY_CANDIDATES: readonly {
  readonly relativePath: string
  readonly format: JobDirectoryTrajectoryFormat
}[] = [
  { relativePath: 'trajectory/acp_trajectory.jsonl', format: 'acp-jsonl' },
  { relativePath: 'trajectory/atif.json', format: 'atif-json' },
  { relativePath: 'trainer/atif.json', format: 'atif-json' },
  { relativePath: 'trajectory/llm_trajectory.jsonl', format: 'llm-jsonl' },
  { relativePath: 'agent/acp_trajectory.jsonl', format: 'acp-jsonl' },
]

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function optionalString(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length === 0 ? null : trimmed
}

function requiredString(value: unknown): string | null {
  return optionalString(value)
}

function numberOrNull(value: unknown): number | null {
  return isFiniteNumber(value) ? value : null
}

function nonNegativeNumber(value: unknown): number | null {
  const parsed = numberOrNull(value)
  return parsed !== null && parsed >= 0 ? parsed : null
}

function countOrNull(value: unknown): number | null {
  const parsed = nonNegativeNumber(value)
  return parsed !== null && Number.isInteger(parsed) ? parsed : null
}

function firstNonNegativeNumber(...values: readonly unknown[]): number | null {
  for (const value of values) {
    const parsed = nonNegativeNumber(value)
    if (parsed !== null) return parsed
  }
  return null
}

function normalizeSkillMode(raw: string | null): SkillMode | null {
  if (raw === null) return null
  const normalized = raw.trim().toLowerCase()
  if (normalized === 'with-skill') return 'with-skill'
  if (
    normalized === 'without-skill'
    || normalized === 'no-skill'
    || normalized === 'none'
  ) {
    return 'without-skill'
  }
  return null
}

function validateBudget(budget: JobDirectoryBudget): JobDirectoryBudget {
  const values = [budget.wallSeconds, budget.toolCalls, budget.costUsd]
  for (const value of values) {
    if (!Number.isFinite(value) || value < 0) {
      throw new JobDirectoryError(
        'invalid-pair-request',
        null,
        'efficiency budget limits must be finite non-negative numbers',
        'pair',
      )
    }
  }
  return budget
}

async function isFile(path: string): Promise<boolean> {
  try {
    return (await stat(path)).isFile()
  } catch {
    return false
  }
}

async function isDirectory(path: string): Promise<boolean> {
  try {
    return (await stat(path)).isDirectory()
  } catch {
    return false
  }
}

async function fileSize(path: string): Promise<number | null> {
  try {
    return (await stat(path)).size
  } catch {
    return null
  }
}

async function readOptionalText(path: string): Promise<string | null> {
  try {
    return await readFile(path, 'utf8')
  } catch {
    return null
  }
}

async function readRequiredText(
  path: string,
  directory: string,
  label: string,
): Promise<string> {
  try {
    return await readFile(path, 'utf8')
  } catch (error) {
    throw new JobDirectoryError(
      'missing-required-file',
      directory,
      `${label} is unreadable: ${messageOf(error)}`,
    )
  }
}

function parseJsonObject(text: string, path: string, directory: string): Record<string, unknown> {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (error) {
    throw new JobDirectoryError(
      'malformed-json',
      directory,
      `${path} is not valid JSON: ${messageOf(error)}`,
    )
  }
  if (!isRecord(parsed)) {
    throw new JobDirectoryError(
      'invalid-result',
      directory,
      `${path} must contain a JSON object`,
    )
  }
  return parsed
}

async function discoverRolloutDirectories(root: string, depth: number): Promise<string[]> {
  if (depth > 2) return []
  let entries: Dirent[]
  try {
    entries = await readdir(root, { withFileTypes: true })
  } catch {
    return []
  }
  if (entries.some(entry => entry.name === 'result.json' && entry.isFile())) {
    return [root]
  }
  const found: string[] = []
  const ordered = [...entries].sort((left, right) => left.name.localeCompare(right.name))
  for (const entry of ordered) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue
    found.push(...await discoverRolloutDirectories(join(root, entry.name), depth + 1))
  }
  return found
}

/**
 * Resolve a job directory to the single rollout directory that holds
 * `result.json`.
 *
 * Passing the rollout directory itself is the common case; passing the job or
 * timestamp directory is supported only when exactly one rollout exists, so an
 * ambiguous multi-rollout job is rejected instead of silently picking a cell.
 */
async function resolveJobDirectory(path: string): Promise<string> {
  if (path.trim().length === 0) {
    throw new JobDirectoryError('missing-job-directory', null, 'job directory path is empty')
  }
  const absolute = resolve(path)
  if (!(await isDirectory(absolute))) {
    throw new JobDirectoryError(
      'missing-job-directory',
      absolute,
      `job directory does not exist: ${absolute}`,
    )
  }
  if (await isFile(join(absolute, 'result.json'))) return absolute

  const discovered = await discoverRolloutDirectories(absolute, 0)
  const unique = [...new Set(discovered)].sort()
  if (unique.length === 1) {
    const only = unique[0]
    if (only !== undefined) return only
  }
  if (unique.length === 0) {
    throw new JobDirectoryError(
      'missing-job-directory',
      absolute,
      `no result.json found under ${absolute}`,
    )
  }
  throw new JobDirectoryError(
    'ambiguous-job-directory',
    absolute,
    `multiple rollout directories found under ${absolute}: ${unique.join(', ')}`,
  )
}

async function hashJobDirectoryIdentity(directory: string): Promise<string> {
  const hash = createHash('sha256')
  const files = ['result.json', 'timing.json', 'config.json', 'verifier/reward.txt'] as const
  for (const file of files) {
    hash.update(file)
    hash.update('\u0000')
    const text = await readOptionalText(join(directory, file))
    hash.update(text === null ? '\u0001missing' : text)
    hash.update('\u0000')
  }
  return `sha256:${hash.digest('hex')}`
}

function readTokens(
  result: Record<string, unknown>,
  agentResult: Record<string, unknown> | null,
  finalMetrics: Record<string, unknown> | null,
): JobDirectoryTokens {
  return {
    input: firstNonNegativeNumber(agentResult?.['n_input_tokens'], finalMetrics?.['total_prompt_tokens']),
    output: firstNonNegativeNumber(
      agentResult?.['n_output_tokens'],
      finalMetrics?.['total_completion_tokens'],
    ),
    cacheRead: firstNonNegativeNumber(
      agentResult?.['n_cache_read_tokens'],
      finalMetrics?.['total_cached_tokens'],
    ),
    total: firstNonNegativeNumber(agentResult?.['total_tokens'], result['total_tokens']),
  }
}

function readCostUsd(
  agentResult: Record<string, unknown> | null,
  finalMetrics: Record<string, unknown> | null,
): number | null {
  const agentCost = nonNegativeNumber(agentResult?.['cost_usd'])
  if (agentCost !== null) return agentCost
  return nonNegativeNumber(finalMetrics?.['total_cost_usd'])
}

function describeFailure(value: unknown): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return optionalString(value)
  if (isRecord(value)) {
    for (const key of ['message', 'error', 'detail', 'reason']) {
      const text = optionalString(value[key])
      if (text !== null) return text
    }
    try {
      const serialized = JSON.stringify(value)
      if (serialized === undefined) return null
      return serialized.length > 300 ? `${serialized.slice(0, 300)}...` : serialized
    } catch {
      return null
    }
  }
  return String(value)
}

function collectErrors(result: Record<string, unknown>): string[] {
  const errors: string[] = []
  const seen = new Set<string>()
  for (const field of FAILURE_FIELDS) {
    const detail = describeFailure(result[field.key])
    if (detail === null) continue
    const rendered = `${field.label}: ${detail}`
    if (seen.has(rendered)) continue
    seen.add(rendered)
    errors.push(rendered)
  }
  return errors
}

function evaluateEfficiency(
  budget: JobDirectoryBudget,
  latencyMs: number | null,
  toolCalls: number | null,
  costUsd: number | null,
): JobDirectoryEfficiency {
  const violations: JobDirectoryBudgetViolation[] = []
  const wallSeconds = latencyMs === null ? null : latencyMs / 1000
  if (wallSeconds !== null && wallSeconds > budget.wallSeconds) {
    violations.push({ metric: 'wall-seconds', limit: budget.wallSeconds, observed: wallSeconds })
  }
  if (toolCalls !== null && toolCalls > budget.toolCalls) {
    violations.push({ metric: 'tool-calls', limit: budget.toolCalls, observed: toolCalls })
  }
  if (costUsd !== null && costUsd > budget.costUsd) {
    violations.push({ metric: 'cost-usd', limit: budget.costUsd, observed: costUsd })
  }
  return {
    failure: violations.length > 0,
    withinBudget: violations.length === 0,
    violations,
  }
}

interface TrajectorySource {
  readonly path: string
  readonly format: JobDirectoryTrajectoryFormat
}

interface TrajectoryPayload {
  readonly events: readonly Record<string, unknown>[]
  readonly parseErrors: number
}

async function locateTrajectory(directory: string): Promise<TrajectorySource | null> {
  for (const candidate of TRAJECTORY_CANDIDATES) {
    const path = join(directory, candidate.relativePath)
    if (await isFile(path)) return { path, format: candidate.format }
  }
  return null
}

function matchAll(regex: RegExp, text: string): RegExpExecArray[] {
  const flags = regex.flags.includes('g') ? regex.flags : `${regex.flags}g`
  return [...text.matchAll(new RegExp(regex.source, flags))]
}

function stringsOf(value: unknown): string[] {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) {
    const out: string[] = []
    for (const item of value) out.push(...stringsOf(item))
    return out
  }
  if (isRecord(value)) {
    const out: string[] = []
    for (const item of Object.values(value)) out.push(...stringsOf(item))
    return out
  }
  return []
}

function normalizeAtifSteps(steps: readonly unknown[]): Record<string, unknown>[] {
  const events: Record<string, unknown>[] = []
  for (const step of steps) {
    if (!isRecord(step)) continue
    const source = optionalString(step['source'])
    const type = source === 'user'
      ? 'user_message'
      : source === 'agent'
        ? 'agent_message'
        : source
    events.push({ ...step, type })
    const calls = step['tool_calls']
    if (!Array.isArray(calls)) continue
    for (const call of calls) {
      if (!isRecord(call)) continue
      const extra = isRecord(call['extra']) ? call['extra'] : null
      events.push({
        type: 'tool_call',
        kind: call['function_name'] ?? null,
        title: extra?.['title'] ?? null,
        status: extra?.['status'] ?? null,
        content: step['observation'] ?? call['arguments'] ?? null,
      })
    }
  }
  return events
}

function isAtifDocument(value: unknown): value is { readonly steps: readonly unknown[] } {
  return isRecord(value) && Array.isArray(value['steps'])
}

function parseJsonLines(text: string): TrajectoryPayload {
  const events: Record<string, unknown>[] = []
  let parseErrors = 0
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (trimmed.length === 0) continue
    try {
      const parsed: unknown = JSON.parse(trimmed)
      if (isRecord(parsed)) events.push(parsed)
      else parseErrors += 1
    } catch {
      parseErrors += 1
    }
  }
  return { events, parseErrors }
}

async function streamJsonLines(path: string): Promise<TrajectoryPayload> {
  const events: Record<string, unknown>[] = []
  let parseErrors = 0
  const input = createReadStream(path, { encoding: 'utf8' })
  const lines = createInterface({ input, crlfDelay: Number.POSITIVE_INFINITY })
  try {
    for await (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.length === 0) continue
      try {
        const parsed: unknown = JSON.parse(trimmed)
        if (isRecord(parsed)) events.push(parsed)
        else parseErrors += 1
      } catch {
        parseErrors += 1
      }
    }
  } catch {
    parseErrors += 1
  } finally {
    lines.close()
  }
  return { events, parseErrors }
}

async function readTrajectoryPayload(source: TrajectorySource): Promise<TrajectoryPayload> {
  if (source.format === 'atif-json') {
    const text = await readOptionalText(source.path)
    if (text === null) return { events: [], parseErrors: 1 }
    try {
      const parsed: unknown = JSON.parse(text)
      if (isAtifDocument(parsed)) return { events: normalizeAtifSteps(parsed.steps), parseErrors: 0 }
      if (Array.isArray(parsed)) {
        const events: Record<string, unknown>[] = []
        let parseErrors = 0
        for (const item of parsed) {
          if (isRecord(item)) events.push(item)
          else parseErrors += 1
        }
        return { events, parseErrors }
      }
      return { events: [], parseErrors: 1 }
    } catch {
      return { events: [], parseErrors: 1 }
    }
  }

  const size = await fileSize(source.path)
  if (size !== null && size > MAX_BUFFERED_TRAJECTORY_BYTES) {
    return streamJsonLines(source.path)
  }
  const text = await readOptionalText(source.path)
  if (text === null) return { events: [], parseErrors: 1 }
  try {
    const parsed: unknown = JSON.parse(text)
    if (isAtifDocument(parsed)) return { events: normalizeAtifSteps(parsed.steps), parseErrors: 0 }
    if (Array.isArray(parsed)) {
      const events: Record<string, unknown>[] = []
      let parseErrors = 0
      for (const item of parsed) {
        if (isRecord(item)) events.push(item)
        else parseErrors += 1
      }
      return { events, parseErrors }
    }
    // A single JSON object in a `.jsonl` file is one event, not a document.
    return parseJsonLines(text)
  } catch {
    return parseJsonLines(text)
  }
}

function contaminationCodes(
  event: Record<string, unknown>,
  taskToken: string,
): JobDirectoryContaminationReason[] {
  if (event['type'] !== 'tool_call') return []
  let raw: string
  try {
    raw = JSON.stringify(event)
  } catch {
    return []
  }
  const lower = raw.toLowerCase().replaceAll('_', '-')
  const remote = REMOTE_TOOL.test(raw)
  const answer = ANSWER_MARKER.test(raw)
  if (remote && (lower.includes(taskToken) || answer)) {
    return ['remote-answer-discovery']
  }
  if (lower.includes(taskToken) && answer) {
    return ['task-specific-answer-artifact']
  }
  return []
}

function contaminationTool(event: Record<string, unknown>): string | null {
  return optionalString(event['title']) ?? optionalString(event['kind'])
}

async function auditTrajectory(
  directory: string,
  taskName: string,
): Promise<{
  readonly trajectory: JobDirectoryTrajectoryAudit
  readonly contamination: readonly string[]
  readonly contaminationMatches: readonly JobDirectoryContaminationMatch[]
}> {
  const source = await locateTrajectory(directory)
  if (source === null) {
    return {
      trajectory: {
        path: null,
        format: null,
        verified: false,
        activated: false,
        activationMode: null,
        readSkills: [],
        injectedSkills: [],
        events: 0,
        parseErrors: 0,
      },
      contamination: [],
      contaminationMatches: [],
    }
  }

  const payload = await readTrajectoryPayload(source)
  const readSkills = new Set<string>()
  const injectedSkills = new Set<string>()
  const contamination = new Set<string>()
  const contaminationMatches: JobDirectoryContaminationMatch[] = []
  const taskToken = taskName.toLowerCase().replaceAll('_', '-')

  for (const [index, event] of payload.events.entries()) {
    const eventType = event['type']
    const strings = stringsOf(event)
    const eventText = strings.join('\n')
    const mountedNames = new Set<string>()
    for (const match of matchAll(MOUNTED_SKILL, eventText)) {
      const name = match[1]
      if (name !== undefined) mountedNames.add(name)
    }
    for (const name of mountedNames) injectedSkills.add(name)
    for (const text of strings) {
      for (const match of matchAll(SKILL_FRONTMATTER, text)) {
        const name = match[1]
        if (name === undefined) continue
        if (mountedNames.has(name) || eventType === 'user_message') {
          injectedSkills.add(name)
        } else {
          readSkills.add(name)
        }
      }
    }
    for (const reason of contaminationCodes(event, taskToken)) {
      contamination.add(reason)
      contaminationMatches.push({
        event: index + 1,
        tool: contaminationTool(event),
        reason,
      })
    }
  }

  const read = [...readSkills].sort()
  const injected = [...injectedSkills].sort()
  const activated = read.length > 0 || injected.length > 0
  return {
    trajectory: {
      path: source.path,
      format: source.format,
      verified: payload.parseErrors === 0,
      activated,
      activationMode: read.length > 0 ? 'read' : injected.length > 0 ? 'injected' : null,
      readSkills: read,
      injectedSkills: injected,
      events: payload.events.length,
      parseErrors: payload.parseErrors,
    },
    contamination: [...contamination].sort(),
    contaminationMatches,
  }
}

interface OptionalJsonObject {
  readonly value: Record<string, unknown> | null
  readonly state: 'ok' | 'missing' | 'malformed'
}

async function readOptionalJsonObject(path: string): Promise<OptionalJsonObject> {
  let text: string
  try {
    text = await readFile(path, 'utf8')
  } catch {
    return { value: null, state: 'missing' }
  }
  try {
    const parsed: unknown = JSON.parse(text)
    return isRecord(parsed)
      ? { value: parsed, state: 'ok' }
      : { value: null, state: 'malformed' }
  } catch {
    return { value: null, state: 'malformed' }
  }
}

function buildIssues(evidence: {
  readonly rawSkillMode: string | null
  readonly skillMode: SkillMode | null
  readonly requestedSkillsDir: string | null
  readonly effectiveSkillsDir: string | null
  readonly skillInvocations: number | null
  readonly toolCalls: number | null
  readonly latencyMs: number | null
  readonly reward: JobDirectoryReward
  readonly trajectory: JobDirectoryTrajectoryAudit
  readonly partialTrajectory: boolean
  readonly timingState: OptionalJsonObject['state']
}): JobDirectoryIssue[] {
  const issues: JobDirectoryIssue[] = []
  if (evidence.rawSkillMode === null) {
    issues.push({ code: 'missing-skill-mode', detail: 'result.json has no skill_mode field' })
  } else if (evidence.skillMode === null) {
    issues.push({
      code: 'unrecognized-skill-mode',
      detail: `result.json skill_mode=${JSON.stringify(evidence.rawSkillMode)} is not recognized`,
    })
  }
  if (
    evidence.requestedSkillsDir !== null
    && evidence.effectiveSkillsDir !== null
    && evidence.requestedSkillsDir !== evidence.effectiveSkillsDir
  ) {
    issues.push({
      code: 'requested-effective-skills-dir-mismatch',
      detail: 'requested_skills_dir differs from effective_skills_dir',
    })
  }
  if (evidence.effectiveSkillsDir !== null && !evidence.trajectory.activated) {
    issues.push({
      code: 'supplied-skills-dir-without-observed-activation',
      detail: 'a skills directory was supplied but the trajectory shows no SKILL.md read or injection',
    })
  }
  if (
    evidence.skillInvocations !== null
    && evidence.skillInvocations > 0
    && !evidence.trajectory.activated
  ) {
    issues.push({
      code: 'skill-invocations-without-observed-activation',
      detail: 'n_skill_invocations is positive but the trajectory shows no SKILL.md read or injection',
    })
  }
  if (evidence.trajectory.path === null) {
    issues.push({ code: 'trajectory-unavailable', detail: 'no ACP/LLM/ATIF trajectory was found' })
  } else if (evidence.trajectory.parseErrors > 0) {
    issues.push({
      code: 'trajectory-parse-errors',
      detail: `${evidence.trajectory.parseErrors} trajectory events could not be parsed`,
    })
  }
  if (evidence.partialTrajectory) {
    issues.push({ code: 'partial-trajectory', detail: 'result.json marks the trajectory as partial' })
  }
  if (evidence.reward.value === null) {
    issues.push({
      code: 'verifier-reward-unavailable',
      detail: 'verifier/reward.txt is missing or does not contain a finite number',
    })
  } else if (
    evidence.reward.reported !== null
    && Math.abs(evidence.reward.value - evidence.reward.reported) > REWARD_TOLERANCE
  ) {
    issues.push({
      code: 'reward-mismatch',
      detail: `verifier reward ${evidence.reward.value} differs from result.json reward ${evidence.reward.reported}`,
    })
  }
  if (evidence.toolCalls === null) {
    issues.push({ code: 'tool-calls-unavailable', detail: 'result.json has no usable n_tool_calls' })
  }
  if (evidence.latencyMs === null) {
    issues.push({
      code: 'agent-execution-timing-unavailable',
      detail: 'neither timing.json nor result.timing reports agent_execution',
    })
  }
  if (evidence.timingState === 'malformed') {
    issues.push({ code: 'timing-json-malformed', detail: 'timing.json exists but is not a JSON object' })
  }
  return issues
}

/**
 * Read one job directory and expose validated evidence without admitting it.
 *
 * The directory may be the rollout directory itself, or a job/timestamp
 * directory containing exactly one rollout.  Malformed or missing mandatory
 * files raise {@link JobDirectoryError}; missing optional evidence is preserved
 * as `null` and explained in `issues`.
 */
export async function readJobDirectory(
  path: string,
  budget: JobDirectoryBudget = DEFAULT_JOB_EFFICIENCY_BUDGET,
): Promise<JobDirectoryEvidence> {
  const activeBudget = validateBudget(budget)
  const directory = await resolveJobDirectory(path)
  const resultPath = join(directory, 'result.json')
  const resultText = await readRequiredText(resultPath, directory, 'result.json')
  const result = parseJsonObject(resultText, resultPath, directory)

  const taskName = requiredString(result['task_name'])
  if (taskName === null) {
    throw new JobDirectoryError('invalid-result', directory, 'result.json has no task_name')
  }
  const rolloutName = requiredString(result['rollout_name'])
  if (rolloutName === null) {
    throw new JobDirectoryError('invalid-result', directory, 'result.json has no rollout_name')
  }

  const directoryName = basename(directory)
  const parentName = basename(dirname(directory))
  const timestamp = TIMESTAMP_DIRECTORY.test(parentName) ? parentName : null

  const rewardText = await readOptionalText(join(directory, 'verifier', 'reward.txt'))
  const rawReward = rewardText === null ? null : rewardText.trim()
  const parsedReward = rawReward === null || rawReward.length === 0 ? null : Number(rawReward)
  const rewardValue = parsedReward !== null && Number.isFinite(parsedReward) ? parsedReward : null
  const rewards = isRecord(result['rewards']) ? result['rewards'] : null
  const reportedReward = numberOrNull(rewards?.['reward'])
  const complete = rewardValue !== null && rewardValue >= 1.0
  const partialReward = rewardValue !== null && rewardValue > 0 && rewardValue < 1.0

  const timingState = await readOptionalJsonObject(join(directory, 'timing.json'))
  const resultTiming = isRecord(result['timing']) ? result['timing'] : null
  const timingSeconds = firstNonNegativeNumber(
    timingState.value?.['agent_execution'],
    resultTiming?.['agent_execution'],
  )
  const latencyMs = timingSeconds === null ? null : Math.round(timingSeconds * 1000)

  const agentResult = isRecord(result['agent_result']) ? result['agent_result'] : null
  const finalMetrics = isRecord(result['final_metrics']) ? result['final_metrics'] : null
  const toolCalls = countOrNull(result['n_tool_calls'])
    ?? countOrNull(agentResult?.['n_tool_calls'])
  const skillInvocations = countOrNull(result['n_skill_invocations'])
    ?? countOrNull(agentResult?.['n_skill_invocations'])
  const tokens = readTokens(result, agentResult, finalMetrics)
  const costUsd = readCostUsd(agentResult, finalMetrics)

  const rawSkillMode = optionalString(result['skill_mode'])
  const skillMode = normalizeSkillMode(rawSkillMode)
  const requestedSkillsDir = optionalString(result['requested_skills_dir'])
  const effectiveSkillsDir = optionalString(result['effective_skills_dir'])
  const skillSource = optionalString(result['skill_source'])

  const errors = collectErrors(result)
  const partialTrajectory = result['partial_trajectory'] === true
  const audit = await auditTrajectory(directory, taskName)

  const exposure: SkillExposureAudit | null = skillMode === null
    ? null
    : {
        skillMode,
        verified: audit.trajectory.verified,
        activated: audit.trajectory.activated,
        activationMode: audit.trajectory.activationMode,
      }

  const reward: JobDirectoryReward = {
    raw: rawReward,
    value: rewardValue,
    reported: reportedReward,
    complete,
  }

  const issues = buildIssues({
    rawSkillMode,
    skillMode,
    requestedSkillsDir,
    effectiveSkillsDir,
    skillInvocations,
    toolCalls,
    latencyMs,
    reward,
    trajectory: audit.trajectory,
    partialTrajectory,
    timingState: timingState.state,
  })

  return {
    directory,
    identity: {
      taskName,
      rolloutName,
      directoryName,
      timestamp,
      artifactHash: await hashJobDirectoryIdentity(directory),
    },
    reward,
    passed: complete,
    partialReward,
    skillMode,
    rawSkillMode,
    requestedSkillsDir,
    effectiveSkillsDir,
    skillSource,
    toolCalls,
    skillInvocations,
    tokens,
    costUsd,
    latencyMs,
    efficiency: evaluateEfficiency(activeBudget, latencyMs, toolCalls, costUsd),
    exposure,
    trajectory: audit.trajectory,
    contamination: audit.contamination,
    contaminationMatches: audit.contaminationMatches,
    infrastructureError: errors.length === 0 ? null : errors.join('; '),
    errors,
    issues,
    provenance: JOB_DIRECTORY_PROVENANCE,
  }
}

function requireMeasuredNumber(
  value: number | null,
  field: string,
  evidence: JobDirectoryEvidence,
  condition: ObservationConditionName,
): number {
  if (value === null) {
    throw new JobDirectoryError(
      'missing-measurement',
      evidence.directory,
      `${field} is missing from the job directory`,
      condition,
    )
  }
  return value
}

function buildCondition(
  evidence: JobDirectoryEvidence,
  condition: ObservationConditionName,
): ConditionObservation {
  if (evidence.skillMode === null || evidence.exposure === null) {
    const detail = evidence.rawSkillMode === null
      ? 'result.json has no skill_mode'
      : `result.json skill_mode=${JSON.stringify(evidence.rawSkillMode)} is not recognized`
    throw new JobDirectoryError('missing-skill-mode', evidence.directory, detail, condition)
  }
  const reward = requireMeasuredNumber(
    evidence.reward.value,
    'verifier/reward.txt',
    evidence,
    condition,
  )
  return {
    passed: evidence.passed,
    reward,
    toolCalls: requireMeasuredNumber(evidence.toolCalls, 'n_tool_calls', evidence, condition),
    latencyMs: requireMeasuredNumber(
      evidence.latencyMs,
      'agent_execution timing',
      evidence,
      condition,
    ),
    costUsd: evidence.costUsd,
    efficiencyFailure: evidence.efficiency.failure,
    exposure: evidence.exposure,
    contamination: evidence.contamination,
    infrastructureError: evidence.infrastructureError,
  }
}

/**
 * Assemble a native {@link BenchmarkObservation} from already-read evidence.
 *
 * This function is intentionally pure and strict: it throws a structured
 * {@link JobDirectoryError} rather than inventing a missing skill mode, reward,
 * tool-call count, or latency.  Contradictory exposure evidence is preserved
 * verbatim so {@link admitObservations} can reject it with its native reason
 * codes.
 */
export function buildBenchmarkObservation(
  input: BuildBenchmarkObservationInput,
): BenchmarkObservation {
  const taskId = input.taskId.trim()
  if (taskId.length === 0) {
    throw new JobDirectoryError(
      'invalid-pair-request',
      null,
      'taskId must be a non-empty string',
      'pair',
    )
  }
  if (!Number.isInteger(input.trial) || input.trial < 1) {
    throw new JobDirectoryError(
      'invalid-trial',
      null,
      `trial must be a positive integer, received ${String(input.trial)}`,
      'pair',
    )
  }
  const domain = input.domain.trim()
  if (domain.length === 0) {
    throw new JobDirectoryError(
      'invalid-pair-request',
      null,
      'domain must be a non-empty string',
      'pair',
    )
  }

  const pairs: readonly [ObservationConditionName, JobDirectoryEvidence][] = [
    ['baseline', input.baseline],
    ['treatment', input.treatment],
  ]
  for (const [condition, evidence] of pairs) {
    if (evidence.identity.taskName !== taskId) {
      throw new JobDirectoryError(
        'task-identity-mismatch',
        evidence.directory,
        `${condition} task_name=${evidence.identity.taskName} does not match requested taskId=${taskId}`,
        condition,
      )
    }
  }

  return {
    observationId: [
      'job',
      taskId,
      `trial-${input.trial}`,
      input.baseline.identity.rolloutName,
      input.treatment.identity.rolloutName,
    ].join(':'),
    taskId,
    trial: input.trial,
    domain,
    routerSelected: input.routerSelected,
    baseline: buildCondition(input.baseline, 'baseline'),
    treatment: buildCondition(input.treatment, 'treatment'),
  }
}

function exclusionCodeForError(code: JobDirectoryErrorCode): JobDirectoryExclusionCode {
  switch (code) {
    case 'missing-job-directory':
      return 'missing-job-directory'
    case 'ambiguous-job-directory':
      return 'ambiguous-job-directory'
    case 'malformed-json':
    case 'invalid-result':
      return 'malformed-job-directory'
    case 'missing-required-file':
    case 'missing-measurement':
      return 'missing-required-evidence'
    case 'missing-skill-mode':
      return 'missing-skill-mode'
    case 'task-identity-mismatch':
      return 'task-identity-mismatch'
    case 'invalid-pair-request':
    case 'invalid-trial':
      return 'invalid-pair-request'
  }
}

function reasonsForError(
  error: unknown,
  defaultCondition: ObservationConditionName,
): JobDirectoryExclusionReason[] {
  if (!(error instanceof JobDirectoryError)) {
    return [{
      code: 'missing-required-evidence',
      condition: defaultCondition,
      detail: `unexpected job-directory failure: ${messageOf(error)}`,
    }]
  }
  return [{
    code: exclusionCodeForError(error.code),
    condition: error.condition ?? defaultCondition,
    detail: error.detail,
  }]
}

function rewardContradiction(
  evidence: JobDirectoryEvidence,
  condition: ObservationConditionName,
): JobDirectoryExclusionReason | null {
  const { value, reported } = evidence.reward
  if (value === null || reported === null) return null
  if (Math.abs(value - reported) <= REWARD_TOLERANCE) return null
  return {
    code: 'contradictory-reward-evidence',
    condition,
    detail: `verifier/reward.txt=${value} disagrees with result.json rewards.reward=${reported}`,
  }
}

function validatePairRequest(
  options: ReadPairedJobDirectoriesOptions,
): JobDirectoryExclusionReason[] {
  const reasons: JobDirectoryExclusionReason[] = []
  if (typeof options.baseline !== 'string' || options.baseline.trim().length === 0) {
    reasons.push({
      code: 'invalid-pair-request',
      condition: 'baseline',
      detail: 'baseline path must be a non-empty string',
    })
  }
  if (typeof options.treatment !== 'string' || options.treatment.trim().length === 0) {
    reasons.push({
      code: 'invalid-pair-request',
      condition: 'treatment',
      detail: 'treatment path must be a non-empty string',
    })
  }
  if (typeof options.taskId !== 'string' || options.taskId.trim().length === 0) {
    reasons.push({
      code: 'invalid-pair-request',
      condition: 'pair',
      detail: 'taskId must be a non-empty string',
    })
  }
  if (!Number.isInteger(options.trial) || options.trial < 1) {
    reasons.push({
      code: 'invalid-pair-request',
      condition: 'pair',
      detail: `trial must be a positive integer, received ${String(options.trial)}`,
    })
  }
  if (typeof options.domain !== 'string' || options.domain.trim().length === 0) {
    reasons.push({
      code: 'invalid-pair-request',
      condition: 'pair',
      detail: 'domain must be a non-empty string',
    })
  }
  if (typeof options.routerSelected !== 'boolean') {
    reasons.push({
      code: 'invalid-pair-request',
      condition: 'pair',
      detail: 'routerSelected must be a boolean',
    })
  }
  return reasons
}

function pairFailure(
  reasons: readonly JobDirectoryExclusionReason[],
  baseline: JobDirectoryEvidence | null,
  treatment: JobDirectoryEvidence | null,
  baselineInherited: boolean,
): ReadPairedJobDirectoriesResult {
  return {
    exclusionReasons: reasons,
    provenance: JOB_DIRECTORY_PROVENANCE,
    baselineInherited,
    baseline,
    treatment,
  }
}

/**
 * Read a baseline/treatment pair and return either an admitted observation or
 * structured exclusion reasons.
 *
 * Only a router-selected cell needs a genuine with-skill treatment run.  An
 * explicit abstention (`routerSelected: false`) may reuse the baseline
 * directory: the shared rollout identity is accepted, the treatment exposure
 * must still show `without-skill` with no activation, and the native selective
 * view inherits the baseline outcome.  A selected cell whose treatment is a
 * copied baseline is rejected instead of being reported as a skill lift.
 */
export async function readPairedJobDirectories(
  options: ReadPairedJobDirectoriesOptions,
): Promise<ReadPairedJobDirectoriesResult> {
  const requestReasons = validatePairRequest(options)
  if (requestReasons.length > 0) {
    return pairFailure(requestReasons, null, null, false)
  }

  const reasons: JobDirectoryExclusionReason[] = []
  let baseline: JobDirectoryEvidence | null = null
  let treatment: JobDirectoryEvidence | null = null

  try {
    baseline = await readJobDirectory(options.baseline, options.budget)
  } catch (error) {
    reasons.push(...reasonsForError(error, 'baseline'))
  }
  try {
    treatment = await readJobDirectory(options.treatment, options.budget)
  } catch (error) {
    reasons.push(...reasonsForError(error, 'treatment'))
  }
  if (baseline === null || treatment === null) {
    return pairFailure(reasons, baseline, treatment, false)
  }

  const taskId = options.taskId.trim()
  if (baseline.identity.taskName !== treatment.identity.taskName) {
    reasons.push({
      code: 'task-identity-mismatch',
      condition: 'pair',
      detail: `baseline task_name=${baseline.identity.taskName} differs from treatment task_name=${treatment.identity.taskName}`,
    })
  }
  for (const [condition, evidence] of [
    ['baseline', baseline],
    ['treatment', treatment],
  ] as const) {
    if (evidence.identity.taskName !== taskId) {
      reasons.push({
        code: 'task-identity-mismatch',
        condition,
        detail: `${condition} task_name=${evidence.identity.taskName} does not match requested taskId=${taskId}`,
      })
    }
    const contradiction = rewardContradiction(evidence, condition)
    if (contradiction !== null) reasons.push(contradiction)
  }
  if (reasons.length > 0) return pairFailure(reasons, baseline, treatment, false)

  const sharedRollout = baseline.identity.rolloutName === treatment.identity.rolloutName
  const sharedHash = baseline.identity.artifactHash === treatment.identity.artifactHash
  const copied = sharedRollout || sharedHash
  const baselineInherited = copied && !options.routerSelected
  if (copied && options.routerSelected) {
    const evidence = sharedRollout
      ? `rollout_name ${treatment.identity.rolloutName} is shared by baseline and treatment`
      : `baseline and treatment share artifact hash ${baseline.identity.artifactHash}`
    reasons.push({
      code: 'copied-baseline-treatment',
      condition: 'pair',
      detail: `${evidence}; a selected treatment must come from a genuine with-skill run`,
    })
    return pairFailure(reasons, baseline, treatment, false)
  }

  let observation: BenchmarkObservation
  try {
    observation = buildBenchmarkObservation({
      baseline,
      treatment,
      taskId,
      trial: options.trial,
      domain: options.domain.trim(),
      routerSelected: options.routerSelected,
    })
  } catch (error) {
    reasons.push(...reasonsForError(error, 'pair'))
    return pairFailure(reasons, baseline, treatment, baselineInherited)
  }

  const admission = admitObservations([observation])
  const exclusion = admission.exclusions[0]
  if (exclusion !== undefined) {
    for (const reason of exclusion.reasons) {
      reasons.push({
        code: reason.code,
        condition: reason.condition,
        detail: reason.detail,
      })
    }
    return pairFailure(reasons, baseline, treatment, baselineInherited)
  }
  if (admission.rawPaired.length !== 1) {
    reasons.push({
      code: 'missing-required-evidence',
      condition: 'pair',
      detail: 'paired observation was not admitted by the native admission gate',
    })
    return pairFailure(reasons, baseline, treatment, baselineInherited)
  }

  return {
    observation,
    exclusionReasons: [],
    provenance: JOB_DIRECTORY_PROVENANCE,
    baselineInherited,
    baseline,
    treatment,
  }
}
