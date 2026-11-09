import { createHash, randomBytes } from 'node:crypto'
import {
  mkdir,
  mkdtemp,
  open,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  stat,
} from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, isAbsolute, join, parse, relative, resolve, sep } from 'node:path'
import { PipelineError } from '../contracts/errors.ts'
import type { StructuredIssue } from '../contracts/errors.ts'
import type { Operation, OperationKind } from '../contracts/operations.ts'
import type { OperationId, SkillId, TraceId } from '../contracts/ids.ts'
import type { VerificationEvidence } from '../contracts/evidence.ts'
import { isNonEmptyString, isRecord, issue } from '../contracts/validation.ts'
import type { PreflightReport, PreflightVerdict } from '../preflight/preflight.ts'
import { resourceKindOf, validateResourcePath } from '../resources/planner.ts'
import type { PlanMode, SkillBundle, SkillPlan } from '../resources/planner.ts'

/** Publication channel recorded on every receipt. */
export type PublicationChannel = 'provisional' | 'canary' | 'accepted'

/** A clock supplied by the caller so receipts are deterministic in tests. */
export type PublicationClock = () => Date | string

/** Hard bounds applied before anything touches the filesystem. */
export interface PublicationLimits {
  readonly maxFiles: number
  readonly maxFileBytes: number
  readonly maxTotalBytes: number
  readonly maxVersionDepth: number
}

/** Default publication bounds; deliberately below the preflight prompt budget. */
export const DEFAULT_PUBLICATION_LIMITS: PublicationLimits = {
  maxFiles: 512,
  maxFileBytes: 1_048_576,
  maxTotalBytes: 16_777_216,
  maxVersionDepth: 8,
}

/** Constructor options for a workspace publisher. */
export interface WorkspacePublisherOptions {
  /** Dedicated validation inventory root. Exactly one root spelling is required. */
  readonly inventoryRoot?: string
  /** Alias for `inventoryRoot`. */
  readonly validationRoot?: string
  /** Alias for `inventoryRoot`. */
  readonly root?: string
  /** Optional deterministic clock returning a `Date` or ISO timestamp. */
  readonly clock?: PublicationClock
  /** Alias for `clock`. */
  readonly now?: PublicationClock
  /** Default channel; a request may override it. */
  readonly channel?: PublicationChannel
  /** Additional roots that must never be used as the validation inventory. */
  readonly protectedRoots?: readonly string[]
  /** Overrides for the publication bounds. */
  readonly limits?: Partial<PublicationLimits>
}

/** An explicit pass receipt supplied by the verifier or a human reviewer. */
export interface AcceptanceReceipt {
  readonly operationId: OperationId | string
  readonly status?: 'pass'
  readonly verdict?: 'pass'
  readonly acceptedAt?: string
  readonly evidenceHash?: string
}

/** Input to one publication attempt. */
export interface PublicationRequest {
  readonly operation: Operation
  /** The accepted plan. Optional when a complete `bundle` is supplied. */
  readonly plan?: SkillPlan
  /** Complete bundle. When a plan is present it must match `plan.bundle`. */
  readonly bundle?: SkillBundle
  readonly preflight?: PreflightReport
  /** Alias for `preflight`. */
  readonly preflightReport?: PreflightReport
  readonly sourceTraceIds?: readonly (TraceId | string)[]
  readonly sourceTraceId?: TraceId | string
  readonly policyVersion: string
  readonly configVersion: string
  readonly channel?: PublicationChannel
  /** Accepted-by-exception receipt, required when preflight says `repair`. */
  readonly acceptedReceipt?: AcceptanceReceipt
  /** Alias for `acceptedReceipt`. */
  readonly acceptance?: AcceptanceReceipt
  /** Optional independent verification; when present it must have passed. */
  readonly verification?: VerificationEvidence
}

/** One content-addressed file entry in a receipt. */
export interface PublicationFileRecord {
  readonly path: string
  readonly sha256: string
  readonly bytes: number
}

/** JSON receipt persisted for one accepted publication. */
export interface PublicationReceiptDocument {
  readonly schemaVersion: 1
  readonly operationId: string
  readonly skillId: string
  readonly operationKind: OperationKind
  readonly mode: PlanMode
  readonly channel: PublicationChannel
  readonly sourceTraceIds: readonly string[]
  readonly policyVersion: string
  readonly configVersion: string
  readonly preflightVerdict: PreflightVerdict
  readonly preflightHash: string
  readonly files: readonly PublicationFileRecord[]
  readonly fileCount: number
  readonly totalBytes: number
  readonly treeHash: string
  readonly releaseId: string
  readonly timestamp: string
  readonly previousVersion: string | null
  readonly previousTreeHash: string | null
  readonly rollbackTo: string | null
  readonly fingerprint: string
}

/** One release retained on disk for rollback and audit. */
export interface PublishedRelease {
  readonly releaseId: string
  readonly treeHash: string
  readonly operationId: string
  readonly publishedAt: string
  readonly receiptPath: string
  readonly fileCount: number
  readonly totalBytes: number
}

/** One rollback audit record. */
export interface PublicationRollbackRecord {
  readonly from: string
  readonly to: string
  readonly at: string
}

/** Durable current/previous pointer state for one skill. */
export interface SkillPublicationState {
  readonly schemaVersion: 1
  readonly skillId: string
  readonly current: PublishedRelease
  readonly previous: PublishedRelease | null
  readonly releases: readonly PublishedRelease[]
  readonly rollbacks: readonly PublicationRollbackRecord[]
}

/** Result of a successful `publish` call. */
export interface PublicationResult {
  readonly receipt: PublicationReceiptDocument
  readonly receiptPath: string
  readonly releaseId: string
  readonly treeHash: string
  readonly versionPath: string
  readonly statePath: string
  readonly previousVersion: string | null
  readonly idempotent: boolean
  readonly created: boolean
}

/** Current publication resolved from durable state. */
export interface CurrentPublication {
  readonly skillId: string
  readonly releaseId: string
  readonly treeHash: string
  readonly operationId: string
  readonly publishedAt: string
  readonly versionPath: string
  readonly receiptPath: string
  readonly statePath: string
}

/** Rollback input; `releaseId` defaults to the previous release. */
export interface RollbackRequest {
  readonly skillId: SkillId | string
  readonly releaseId?: string
}

/** Result of one rollback. */
export interface RollbackResult {
  readonly skillId: string
  readonly releaseId: string
  readonly treeHash: string
  readonly versionPath: string
  readonly receiptPath: string
  readonly statePath: string
  readonly previousVersion: string
  readonly idempotent: boolean
}

/** Base class for every structured publication failure. */
export class PublicationError extends PipelineError {
  readonly issues: readonly StructuredIssue[]

  constructor(
    code: string,
    message: string,
    issues: readonly StructuredIssue[] = [],
    details: Readonly<Record<string, unknown>> = {},
  ) {
    super(code, message, { ...details, issues })
    this.issues = issues
  }
}

/** The configured inventory root is not a dedicated validation root. */
export class PublicationConfigurationError extends PublicationError {
  constructor(message: string, issues: readonly StructuredIssue[] = []) {
    super('invalid-inventory-root', message, issues)
  }
}

/** The operation, plan, bundle, or receipt input failed validation. */
export class PublicationValidationError extends PublicationError {
  constructor(issues: readonly StructuredIssue[]) {
    super('invalid-publication', 'publication request failed validation', issues)
  }
}

/** The operation kind cannot be materialized by this publisher. */
export class UnsupportedPublicationOperationError extends PublicationError {
  constructor(kind: string) {
    super('unsupported-operation', `operation kind ${kind} cannot be published`, [
      issue('$.operation.kind', 'unsupported-operation', `unsupported operation kind ${kind}`),
    ])
  }
}

/** Preflight did not accept the bundle and no accepted receipt was supplied. */
export class PublicationPreflightError extends PublicationError {
  constructor(message: string, details: Readonly<Record<string, unknown>> = {}) {
    super('preflight-rejected', message, [], details)
  }
}

/** Independent verification reported a non-pass status. */
export class PublicationVerificationError extends PublicationError {
  constructor(status: string) {
    super('verification-not-passed', `verification status ${status} is not publishable`, [], {
      status,
    })
  }
}

/** A release would overwrite different content or reuse a receipt inconsistently. */
export class PublicationConflictError extends PublicationError {
  constructor(message: string, issues: readonly StructuredIssue[] = []) {
    super('publication-conflict', message, issues)
  }
}

/** A rollback target is unavailable or corrupt. */
export class PublicationRollbackError extends PublicationError {
  constructor(message: string, details: Readonly<Record<string, unknown>> = {}) {
    super('rollback-unavailable', message, [], details)
  }
}

/** Durable publication state or a receipt could not be interpreted. */
export class CorruptPublicationError extends PublicationError {
  constructor(message: string, details: Readonly<Record<string, unknown>> = {}) {
    super('corrupt-publication', message, [], details)
  }
}

/** A filesystem operation failed during staging, rename, or state update. */
export class PublicationIOError extends PublicationError {
  constructor(message: string, details: Readonly<Record<string, unknown>> = {}) {
    super('publication-io', message, [], details)
  }
}

const MARKER_FILE = '.skill-evolving-validation-root.json'
const STATE_FILE = 'state.json'
const SCHEMA_VERSION = 1

const SUPPORTED_KINDS: ReadonlySet<OperationKind> = new Set([
  'create',
  'update',
  'merge',
  'no_change',
])

const DEFAULT_PROTECTED_ROOTS: readonly string[] = [
  join(homedir(), '.claude', 'skills'),
  join(homedir(), '.claude', 'plugins'),
  join(homedir(), '.codex', 'skills'),
  join(homedir(), '.agents', 'skills'),
  join(homedir(), '.cursor', 'skills'),
  join(homedir(), '.gemini', 'skills'),
  join(homedir(), '.copilot', 'skills'),
  join(homedir(), '.windsurf', 'skills'),
  join(homedir(), '.config', 'agents', 'skills'),
  join(homedir(), '.config', 'claude', 'skills'),
  join(homedir(), '.config', 'opencode', 'skills'),
  join(homedir(), 'skills'),
]

function sha256Hex(content: string): string {
  return createHash('sha256').update(content, 'utf8').digest('hex')
}

/** Hash one UTF-8 file payload; exported so callers can verify receipts. */
export function hashPublicationContent(content: string): string {
  return sha256Hex(content)
}

/** Hash a preflight report in a canonical, key-order-independent form. */
export function hashPreflightReport(report: PreflightReport): string {
  return sha256Hex(canonicalJson(report))
}

/** Compute the complete tree hash from sorted file records. */
export function computeTreeHash(files: readonly PublicationFileRecord[]): string {
  const ordered = [...files].sort(comparePaths)
  const lines = ordered.map((file) => `${file.path}\u0000${file.sha256}\u0000${file.bytes}\n`)
  return sha256Hex(lines.join(''))
}

/** Deterministic JSON used for hashes and fingerprints. */
export function canonicalJson(value: unknown): string {
  if (value === null) return 'null'
  if (value === undefined) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new PublicationValidationError([
      issue('$', 'invalid-json-number', 'canonical JSON cannot encode a non-finite number'),
    ])
    return String(value)
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(',')}]`
  }
  if (isRecord(value)) {
    const keys = Object.keys(value).sort(compareStrings)
    const entries = keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    return `{${entries.join(',')}}`
  }
  throw new PublicationValidationError([
    issue('$', 'invalid-json-value', `canonical JSON cannot encode ${typeof value}`),
  ])
}

/** Resolve the safe on-disk directory name for one arbitrary skill id. */
export function skillDirectoryName(value: string): string {
  const normalized = value.normalize('NFKD').toLowerCase()
  const slug = normalized.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48)
  const prefix = slug.length > 0 ? slug : 'skill'
  return `${prefix}-${sha256Hex(value).slice(0, 16)}`
}

function compareStrings(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0
}

function comparePaths(
  left: PublicationFileRecord,
  right: PublicationFileRecord,
): number {
  return compareStrings(left.path, right.path)
}

function isSameOrInside(parent: string, child: string): boolean {
  const rel = relative(parent, child)
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
}

function errnoCode(error: unknown): string | undefined {
  if (error !== null && typeof error === 'object' && 'code' in error) {
    const code = error.code
    if (typeof code === 'string') return code
  }
  return undefined
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function wrapIoError(error: unknown, action: string, path: string): PublicationError {
  if (error instanceof PublicationError) return error
  return new PublicationIOError(`${action} failed for ${path}: ${errorMessage(error)}`, {
    action,
    path,
    cause: errorMessage(error),
  })
}

function normalizeRelativePath(value: string): string {
  return value.split(sep).join('/')
}

interface PreparedRequest {
  readonly operation: Operation
  readonly plan: SkillPlan | undefined
  readonly bundle: SkillBundle
  readonly mode: PlanMode
  readonly preflight: PreflightReport
  readonly preflightHash: string
  readonly sourceTraceIds: readonly string[]
  readonly policyVersion: string
  readonly configVersion: string
  readonly channel: PublicationChannel
}

interface PreparedBundle {
  readonly entries: readonly (readonly [string, string])[]
  readonly files: readonly PublicationFileRecord[]
  readonly treeHash: string
  readonly totalBytes: number
}

interface LocatedSkill {
  readonly root: string
  readonly skillId: string
  readonly skillDir: string
  readonly statePath: string
  readonly versionsPath: string
  readonly receiptsPath: string
}

function planModeFor(kind: OperationKind): PlanMode | undefined {
  switch (kind) {
    case 'create':
      return 'create'
    case 'update':
      return 'update'
    case 'merge':
      return 'merge'
    case 'no_change':
      return 'no_change'
    default:
      return undefined
  }
}

function channelOf(value: unknown, fallback: PublicationChannel): PublicationChannel {
  if (value === undefined) return fallback
  if (value === 'provisional' || value === 'canary' || value === 'accepted') return value
  throw new PublicationValidationError([
    issue('$.channel', 'invalid-channel', `unsupported publication channel ${String(value)}`),
  ])
}

function preflightVerdictOf(report: PreflightReport): PreflightVerdict {
  const verdict: unknown = report.verdict
  if (verdict === 'accept' || verdict === 'repair' || verdict === 'reject') return verdict
  throw new PublicationValidationError([
    issue('$.preflight.verdict', 'invalid-verdict', 'preflight report has no valid verdict'),
  ])
}

function reportRejectReasons(report: PreflightReport): readonly string[] {
  const reasons: unknown = report.rejectReasons
  if (!Array.isArray(reasons)) return []
  return reasons.flatMap((row) => {
    if (isRecord(row) && typeof row.code === 'string') return [row.code]
    return []
  })
}

function acceptanceFrom(
  request: PublicationRequest,
  operation: Operation,
): AcceptanceReceipt | undefined {
  const receipt = request.acceptedReceipt ?? request.acceptance
  if (receipt === undefined) return undefined
  const issues: StructuredIssue[] = []
  if (receipt.operationId !== operation.id) {
    issues.push(issue(
      '$.acceptedReceipt.operationId',
      'acceptance-operation-mismatch',
      'accepted receipt belongs to a different operation',
    ))
  }
  if (receipt.status !== 'pass' && receipt.verdict !== 'pass') {
    issues.push(issue(
      '$.acceptedReceipt.status',
      'acceptance-not-pass',
      'accepted receipt must carry a pass status',
    ))
  }
  if (issues.length > 0) throw new PublicationValidationError(issues)
  return receipt
}

function resolvePreflightRequest(
  request: PublicationRequest,
): PreflightReport {
  const direct = request.preflight
  const alias = request.preflightReport
  if (direct === undefined && alias === undefined) {
    throw new PublicationValidationError([
      issue('$.preflight', 'missing-preflight', 'a preflight report is required'),
    ])
  }
  if (direct !== undefined && alias !== undefined) {
    if (hashPreflightReport(direct) !== hashPreflightReport(alias)) {
      throw new PublicationValidationError([
        issue(
          '$.preflightReport',
          'preflight-alias-mismatch',
          'preflight and preflightReport describe different reports',
        ),
      ])
    }
  }
  const chosen = direct ?? alias
  if (chosen === undefined) {
    throw new PublicationValidationError([
      issue('$.preflight', 'missing-preflight', 'a preflight report is required'),
    ])
  }
  return chosen
}

function resolveSourceTraceIds(
  request: PublicationRequest,
  plan: SkillPlan | undefined,
): readonly string[] {
  const provided = request.sourceTraceIds
  const single = request.sourceTraceId
  if (provided === undefined && single === undefined) {
    if (plan === undefined) {
      throw new PublicationValidationError([
        issue(
          '$.sourceTraceIds',
          'missing-source-trace',
          'source trace ids are required when no plan supplies a trace',
        ),
      ])
    }
    return [plan.traceId]
  }
  const values: string[] = []
  if (single !== undefined) values.push(String(single))
  if (provided !== undefined) {
    if (!Array.isArray(provided)) {
      throw new PublicationValidationError([
        issue('$.sourceTraceIds', 'invalid-source-traces', 'sourceTraceIds must be an array'),
      ])
    }
    for (const value of provided) values.push(String(value))
  }
  const seen = new Set<string>()
  const unique: string[] = []
  for (const value of values) {
    if (!isNonEmptyString(value)) {
      throw new PublicationValidationError([
        issue('$.sourceTraceIds', 'invalid-source-trace', 'source trace ids must be non-empty'),
      ])
    }
    if (seen.has(value)) continue
    seen.add(value)
    unique.push(value)
  }
  if (unique.length === 0) {
    throw new PublicationValidationError([
      issue('$.sourceTraceIds', 'missing-source-trace', 'at least one source trace id is required'),
    ])
  }
  return unique
}

function validateOperation(operation: Operation): StructuredIssue[] {
  const issues: StructuredIssue[] = []
  if (!isNonEmptyString(operation.id)) {
    issues.push(issue('$.operation.id', 'invalid-operation-id', 'operation id must be non-empty'))
  }
  if (!isNonEmptyString(operation.skillId)) {
    issues.push(issue('$.operation.skillId', 'invalid-skill-id', 'skill id must be non-empty'))
  }
  if (!isNonEmptyString(operation.findingId)) {
    issues.push(issue('$.operation.findingId', 'invalid-finding-id', 'finding id must be non-empty'))
  }
  if (!isNonEmptyString(operation.summary)) {
    issues.push(issue('$.operation.summary', 'invalid-summary', 'operation summary must be non-empty'))
  }
  return issues
}

function validatePlan(operation: Operation, plan: SkillPlan): StructuredIssue[] {
  const issues: StructuredIssue[] = []
  if (plan.operationId !== operation.id) {
    issues.push(issue(
      '$.plan.operationId',
      'plan-operation-mismatch',
      'plan belongs to a different operation',
    ))
  }
  if (plan.skillId !== operation.skillId) {
    issues.push(issue(
      '$.plan.skillId',
      'plan-skill-mismatch',
      'plan belongs to a different skill',
    ))
  }
  if (plan.findingId !== operation.findingId) {
    issues.push(issue(
      '$.plan.findingId',
      'plan-finding-mismatch',
      'plan belongs to a different finding',
    ))
  }
  const expectedMode = planModeFor(operation.kind)
  if (expectedMode !== undefined && plan.mode !== expectedMode) {
    issues.push(issue(
      '$.plan.mode',
      'plan-mode-mismatch',
      `plan mode ${plan.mode} does not match operation kind ${operation.kind}`,
    ))
  }
  if (plan.skill.path !== 'SKILL.md') {
    issues.push(issue(
      '$.plan.skill.path',
      'plan-skill-path',
      'the planned skill document must be SKILL.md',
    ))
  }
  const plannedRows = [plan.skill, ...plan.resources]
  for (const planned of plannedRows) {
    const path = 'resource' in planned ? planned.resource.path : planned.path
    for (const problem of validateResourcePath(path)) {
      issues.push(issue(`$.plan:${path}`, problem.code, problem.message))
    }
    if (path.includes('/')) {
      const kind = resourceKindOf(path)
      const expectedKind = 'resource' in planned ? planned.resource.kind : 'skill'
      if (expectedKind !== 'skill' && kind !== expectedKind) {
        issues.push(issue(
          `$.plan:${path}`,
          'plan-kind-mismatch',
          `resource kind ${expectedKind} does not match path root ${String(kind)}`,
        ))
      }
    }
  }
  const seen = new Set<string>()
  for (const planned of plannedRows) {
    const path = 'resource' in planned ? planned.resource.path : planned.path
    if (seen.has(path)) {
      issues.push(issue(
        `$.plan:${path}`,
        'duplicate-plan-path',
        `plan lists ${path} more than once`,
      ))
    }
    seen.add(path)
    if ('resource' in planned) {
      if (planned.resource.operationId !== operation.id) {
        issues.push(issue(
          `$.plan:${path}`,
          'resource-operation-mismatch',
          'resource belongs to a different operation',
        ))
      }
      if (planned.resource.skillId !== operation.skillId) {
        issues.push(issue(
          `$.plan:${path}`,
          'resource-skill-mismatch',
          'resource belongs to a different skill',
        ))
      }
    }
  }
  return issues
}

function bundleEquals(left: SkillBundle, right: SkillBundle): boolean {
  const leftEntries = Object.entries(left)
  const rightEntries = Object.entries(right)
  if (leftEntries.length !== rightEntries.length) return false
  const byPath = new Map(rightEntries)
  for (const [path, content] of leftEntries) {
    if (byPath.get(path) !== content) return false
  }
  return true
}

function prepareBundle(
  bundle: SkillBundle,
  limits: PublicationLimits,
): PreparedBundle {
  const issues: StructuredIssue[] = []
  const entries: [string, string][] = []
  const files: PublicationFileRecord[] = []
  const normalizedPaths = new Map<string, string>()
  let totalBytes = 0

  if (!Object.prototype.hasOwnProperty.call(bundle, 'SKILL.md')) {
    issues.push(issue('$.bundle', 'missing-skill', 'bundle must contain SKILL.md'))
  }

  for (const [path, content] of Object.entries(bundle)) {
    const contentIssues = validateResourcePath(path)
    for (const problem of contentIssues) {
      issues.push(issue(path, problem.code, problem.message))
    }
    if (path.includes('/')) {
      const segments = path.split('/')
      if (segments.includes('..')) {
        issues.push(issue(path, 'path-traversal', 'path must not contain .. segments'))
      }
    }
    if (isAbsolute(path)) {
      issues.push(issue(path, 'path-absolute', 'published paths must be relative'))
    }
    if (typeof content !== 'string') {
      issues.push(issue(path, 'invalid-content', 'file content must be a string'))
      continue
    }
    const normalized = path.normalize('NFKC').toLowerCase()
    const previous = normalizedPaths.get(normalized)
    if (previous !== undefined) {
      issues.push(issue(
        path,
        'duplicate-path',
        `path collides with ${previous} after case and Unicode normalization`,
      ))
    } else {
      normalizedPaths.set(normalized, path)
    }
    const bytes = Buffer.byteLength(content, 'utf8')
    if (bytes > limits.maxFileBytes) {
      issues.push(issue(
        path,
        'file-too-large',
        `file exceeds ${limits.maxFileBytes} bytes`,
      ))
    }
    totalBytes += bytes
    entries.push([path, content])
    files.push({ path, sha256: sha256Hex(content), bytes })
  }

  for (const path of normalizedPaths.keys()) {
    const segments = path.split('/')
    for (let index = 1; index < segments.length; index += 1) {
      const prefix = segments.slice(0, index).join('/')
      const owner = normalizedPaths.get(prefix)
      if (owner !== undefined) {
        issues.push(issue(
          path,
          'path-collision',
          `${owner} is both a file and a directory`,
        ))
      }
    }
  }

  if (entries.length > limits.maxFiles) {
    issues.push(issue(
      '$.bundle',
      'too-many-files',
      `bundle exceeds ${limits.maxFiles} files`,
    ))
  }
  if (totalBytes > limits.maxTotalBytes) {
    issues.push(issue(
      '$.bundle',
      'bundle-too-large',
      `bundle exceeds ${limits.maxTotalBytes} bytes`,
    ))
  }
  if (issues.length > 0) throw new PublicationValidationError(issues)

  entries.sort((left, right) => compareStrings(left[0], right[0]))
  files.sort(comparePaths)
  return {
    entries,
    files,
    treeHash: computeTreeHash(files),
    totalBytes,
  }
}

async function readText(path: string): Promise<string | undefined> {
  try {
    return await readFile(path, 'utf8')
  } catch (error) {
    if (errnoCode(error) === 'ENOENT') return undefined
    throw wrapIoError(error, 'read', path)
  }
}

async function readJson(path: string): Promise<unknown | undefined> {
  const text = await readText(path)
  if (text === undefined) return undefined
  try {
    const value: unknown = JSON.parse(text)
    return value
  } catch (error) {
    throw new CorruptPublicationError(`could not parse JSON at ${path}`, {
      path,
      cause: errorMessage(error),
    })
  }
}

async function syncDirectory(path: string): Promise<void> {
  try {
    const handle = await open(path, 'r')
    try {
      await handle.sync()
    } finally {
      await handle.close()
    }
  } catch (error) {
    const code = errnoCode(error)
    if (code === 'EINVAL' || code === 'EISDIR' || code === 'EPERM' || code === 'EBADF') {
      return
    }
    throw error
  }
}

async function writeAtomic(path: string, content: string): Promise<void> {
  const temporary = join(
    dirname(path),
    `.${process.pid}-${randomBytes(8).toString('hex')}.tmp`,
  )
  try {
    const handle = await open(temporary, 'wx', 0o600)
    try {
      await handle.writeFile(content, 'utf8')
      await handle.sync()
    } finally {
      await handle.close()
    }
    await rename(temporary, path)
    await syncDirectory(dirname(path))
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => undefined)
    throw error
  }
}

async function writeAtomicJson(path: string, value: unknown): Promise<void> {
  await writeAtomic(path, `${JSON.stringify(value, null, 2)}\n`)
}

function readString(value: unknown): string | undefined {
  return isNonEmptyString(value) ? value : undefined
}

function readCount(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
    ? value
    : undefined
}

function readRelease(value: unknown): PublishedRelease | undefined {
  if (!isRecord(value)) return undefined
  const releaseId = readString(value.releaseId)
  const treeHash = readString(value.treeHash)
  const operationId = readString(value.operationId)
  const publishedAt = readString(value.publishedAt)
  const receiptPath = readString(value.receiptPath)
  const fileCount = readCount(value.fileCount)
  const totalBytes = readCount(value.totalBytes)
  if (
    releaseId === undefined
    || treeHash === undefined
    || operationId === undefined
    || publishedAt === undefined
    || receiptPath === undefined
    || fileCount === undefined
    || totalBytes === undefined
  ) {
    return undefined
  }
  return { releaseId, treeHash, operationId, publishedAt, receiptPath, fileCount, totalBytes }
}

function readRollback(value: unknown): PublicationRollbackRecord | undefined {
  if (!isRecord(value)) return undefined
  const from = readString(value.from)
  const to = readString(value.to)
  const at = readString(value.at)
  if (from === undefined || to === undefined || at === undefined) return undefined
  return { from, to, at }
}

function parseState(value: unknown, skillId: string): SkillPublicationState {
  if (!isRecord(value)) {
    throw new CorruptPublicationError('publication state is not an object', { skillId })
  }
  const version = readCount(value.schemaVersion)
  const storedSkill = readString(value.skillId)
  const current = readRelease(value.current)
  const previous = value.previous === null || value.previous === undefined
    ? null
    : readRelease(value.previous)
  if (version !== SCHEMA_VERSION) {
    throw new CorruptPublicationError('publication state has an unsupported schema version', {
      skillId,
      version: String(value.schemaVersion),
    })
  }
  if (storedSkill === undefined || storedSkill !== skillId) {
    throw new CorruptPublicationError('publication state belongs to a different skill', {
      skillId,
      storedSkill: String(value.skillId),
    })
  }
  if (current === undefined) {
    throw new CorruptPublicationError('publication state has no current release', { skillId })
  }
  if (previous === undefined) {
    throw new CorruptPublicationError('publication state has an invalid previous release', {
      skillId,
    })
  }
  const releasesValue: unknown = value.releases
  const releases: PublishedRelease[] = []
  if (Array.isArray(releasesValue)) {
    for (const row of releasesValue) {
      const release = readRelease(row)
      if (release === undefined) {
        throw new CorruptPublicationError('publication state has an invalid release record', {
          skillId,
        })
      }
      releases.push(release)
    }
  }
  if (releases.length === 0) releases.push(current)
  const rollbacksValue: unknown = value.rollbacks
  const rollbacks: PublicationRollbackRecord[] = []
  if (Array.isArray(rollbacksValue)) {
    for (const row of rollbacksValue) {
      const rollback = readRollback(row)
      if (rollback === undefined) {
        throw new CorruptPublicationError('publication state has an invalid rollback record', {
          skillId,
        })
      }
      rollbacks.push(rollback)
    }
  }
  return {
    schemaVersion: SCHEMA_VERSION,
    skillId,
    current,
    previous,
    releases,
    rollbacks,
  }
}

function readReceiptFileRecord(value: unknown): PublicationFileRecord | undefined {
  if (!isRecord(value)) return undefined
  const path = readString(value.path)
  const sha256 = readString(value.sha256)
  const bytes = readCount(value.bytes)
  if (path === undefined || sha256 === undefined || bytes === undefined) return undefined
  return { path, sha256, bytes }
}

function parseReceipt(value: unknown, path: string): PublicationReceiptDocument {
  if (!isRecord(value)) {
    throw new CorruptPublicationError(`publication receipt at ${path} is not an object`, { path })
  }
  const operationId = readString(value.operationId)
  const skillId = readString(value.skillId)
  const releaseId = readString(value.releaseId)
  const treeHash = readString(value.treeHash)
  const fingerprint = readString(value.fingerprint)
  const filesValue: unknown = value.files
  if (
    operationId === undefined
    || skillId === undefined
    || releaseId === undefined
    || treeHash === undefined
    || fingerprint === undefined
    || !Array.isArray(filesValue)
  ) {
    throw new CorruptPublicationError(`publication receipt at ${path} is incomplete`, { path })
  }
  const files: PublicationFileRecord[] = []
  for (const row of filesValue) {
    const file = readReceiptFileRecord(row)
    if (file === undefined) {
      throw new CorruptPublicationError(`publication receipt at ${path} has an invalid file record`, {
        path,
      })
    }
    files.push(file)
  }
  // The remaining fields are read defensively; a receipt written by this class always has them.
  const operationKindValue = value.operationKind
  const operationKind: OperationKind = operationKindValue === 'update'
    || operationKindValue === 'merge'
    || operationKindValue === 'no_change'
    || operationKindValue === 'delete'
    || operationKindValue === 'split'
    ? operationKindValue
    : 'create'
  const modeValue = value.mode
  const mode: PlanMode = modeValue === 'update' || modeValue === 'merge' || modeValue === 'no_change'
    ? modeValue
    : 'create'
  const channelValue = value.channel
  const channel: PublicationChannel = channelValue === 'canary' || channelValue === 'accepted'
    ? channelValue
    : 'provisional'
  const sourceValue: unknown = value.sourceTraceIds
  const sourceTraceIds = Array.isArray(sourceValue)
    ? sourceValue.flatMap((row) => (typeof row === 'string' ? [row] : []))
    : []
  const verdictValue = value.preflightVerdict
  const preflightVerdict: PreflightVerdict = verdictValue === 'repair' || verdictValue === 'reject'
    ? verdictValue
    : 'accept'
  return {
    schemaVersion: SCHEMA_VERSION,
    operationId,
    skillId,
    operationKind,
    mode,
    channel,
    sourceTraceIds,
    policyVersion: readString(value.policyVersion) ?? '',
    configVersion: readString(value.configVersion) ?? '',
    preflightVerdict,
    preflightHash: readString(value.preflightHash) ?? '',
    files,
    fileCount: readCount(value.fileCount) ?? files.length,
    totalBytes: readCount(value.totalBytes) ?? files.reduce((sum, file) => sum + file.bytes, 0),
    treeHash,
    releaseId,
    timestamp: readString(value.timestamp) ?? '',
    previousVersion: value.previousVersion === null ? null : readString(value.previousVersion) ?? null,
    previousTreeHash: value.previousTreeHash === null
      ? null
      : readString(value.previousTreeHash) ?? null,
    rollbackTo: value.rollbackTo === null ? null : readString(value.rollbackTo) ?? null,
    fingerprint,
  }
}

function cloneBundle(bundle: SkillBundle): Record<string, string> {
  return { ...bundle }
}

function mergeBundles(current: SkillBundle, incoming: SkillBundle): SkillBundle {
  const merged = cloneBundle(current)
  const conflicts: StructuredIssue[] = []
  for (const [path, content] of Object.entries(incoming)) {
    const existing = merged[path]
    if (existing === undefined || path === 'SKILL.md') {
      merged[path] = content
      continue
    }
    if (existing !== content) {
      conflicts.push(issue(
        path,
        'merge-overwrite',
        'merge may not replace an existing resource file',
      ))
    }
  }
  if (conflicts.length > 0) {
    throw new PublicationConflictError('merge would overwrite published content', conflicts)
  }
  return merged
}

function fingerprintOf(input: {
  readonly operationId: string
  readonly skillId: string
  readonly mode: PlanMode
  readonly channel: PublicationChannel
  readonly sourceTraceIds: readonly string[]
  readonly policyVersion: string
  readonly configVersion: string
  readonly preflightVerdict: PreflightVerdict
  readonly preflightHash: string
  readonly treeHash: string
}): string {
  return sha256Hex(canonicalJson({
    operationId: input.operationId,
    skillId: input.skillId,
    mode: input.mode,
    channel: input.channel,
    sourceTraceIds: [...input.sourceTraceIds].sort(compareStrings),
    policyVersion: input.policyVersion,
    configVersion: input.configVersion,
    preflightVerdict: input.preflightVerdict,
    preflightHash: input.preflightHash,
    treeHash: input.treeHash,
  }))
}

function receiptPathFor(skillDir: string, operationId: string): string {
  return join(skillDir, 'receipts', `${sha256Hex(operationId)}.json`)
}

async function readVersionBundle(
  versionPath: string,
  limits: PublicationLimits,
  prefix = '',
  depth = 0,
): Promise<SkillBundle> {
  if (depth > limits.maxVersionDepth) {
    throw new CorruptPublicationError('published version exceeds the maximum directory depth', {
      versionPath,
    })
  }
  let entries
  try {
    entries = await readdir(versionPath, { withFileTypes: true })
  } catch (error) {
    throw wrapIoError(error, 'readdir', versionPath)
  }
  const bundle: Record<string, string> = {}
  for (const entry of entries) {
    const path = prefix.length === 0 ? entry.name : `${prefix}/${entry.name}`
    if (entry.isSymbolicLink()) {
      throw new CorruptPublicationError('published versions must not contain symbolic links', {
        path,
      })
    }
    if (entry.isDirectory()) {
      const nested = await readVersionBundle(join(versionPath, entry.name), limits, path, depth + 1)
      for (const [nestedPath, content] of Object.entries(nested)) bundle[nestedPath] = content
      continue
    }
    if (!entry.isFile()) {
      throw new CorruptPublicationError('published versions may contain only regular files', {
        path,
      })
    }
    try {
      bundle[path] = await readFile(join(versionPath, entry.name), 'utf8')
    } catch (error) {
      throw wrapIoError(error, 'read', join(versionPath, entry.name))
    }
    if (Object.keys(bundle).length > limits.maxFiles) {
      throw new CorruptPublicationError('published version exceeds the maximum file count', {
        versionPath,
      })
    }
  }
  for (const path of Object.keys(bundle)) {
    const problems = validateResourcePath(path)
    if (problems.length > 0) {
      throw new CorruptPublicationError(`published version contains an unsafe path ${path}`, {
        path,
      })
    }
  }
  return bundle
}

function prepareFromBundle(bundle: SkillBundle): PreparedBundle {
  const files = Object.entries(bundle)
    .map(([path, content]) => ({
      path,
      sha256: sha256Hex(content),
      bytes: Buffer.byteLength(content, 'utf8'),
    }))
    .sort(comparePaths)
  return {
    entries: Object.entries(bundle).sort((left, right) => compareStrings(left[0], right[0])),
    files,
    treeHash: computeTreeHash(files),
    totalBytes: files.reduce((sum, file) => sum + file.bytes, 0),
  }
}

function assertDedicatedPath(root: string, protectedRoots: readonly string[]): void {
  if (root === parse(root).root) {
    throw new PublicationConfigurationError('the filesystem root cannot be a validation inventory')
  }
  if (root === resolve(homedir())) {
    throw new PublicationConfigurationError('the home directory cannot be a validation inventory')
  }
  if (root === resolve(process.cwd())) {
    throw new PublicationConfigurationError(
      'the current working directory cannot be a validation inventory root',
    )
  }
  for (const protectedRoot of protectedRoots) {
    const resolved = resolve(protectedRoot)
    if (isSameOrInside(resolved, root) || isSameOrInside(root, resolved)) {
      throw new PublicationConfigurationError(
        `refusing to publish into or above a primary skill inventory: ${resolved}`,
        [issue('$.inventoryRoot', 'protected-root', 'root overlaps a primary skill inventory')],
      )
    }
  }
}

/**
 * Content-addressed, atomic publisher for a dedicated validation inventory.
 *
 * Layout per skill:
 * `skills/<slug>-<hash>/state.json`, `versions/<treeHash>/`, and
 * `receipts/<operationHash>.json`. A release directory is staged, fsynced,
 * and renamed into place; the current pointer and receipt are then written
 * atomically. Releases are immutable and never deleted, so `previous` always
 * remains available for rollback.
 */
export class WorkspacePublisher {
  readonly inventoryRoot: string

  private readonly defaultChannel: PublicationChannel
  private readonly clock: PublicationClock
  private readonly limits: PublicationLimits
  private readonly protectedRoots: readonly string[]
  private readonly locks = new Map<string, Promise<void>>()

  constructor(options: WorkspacePublisherOptions) {
    const declared = [options.inventoryRoot, options.validationRoot, options.root]
      .filter((value): value is string => value !== undefined)
    if (declared.length !== 1) {
      throw new PublicationConfigurationError(
        'exactly one dedicated validation inventory root must be supplied',
        [issue('$.inventoryRoot', 'invalid-root', 'inventoryRoot is required')],
      )
    }
    const candidate = declared[0]
    if (candidate === undefined || !isNonEmptyString(candidate)) {
      throw new PublicationConfigurationError('inventory root must be a non-empty path')
    }
    if (!isAbsolute(candidate)) {
      throw new PublicationConfigurationError(
        `inventory root must be an absolute path, received ${candidate}`,
      )
    }
    this.inventoryRoot = resolve(candidate)
    this.protectedRoots = [...DEFAULT_PROTECTED_ROOTS, ...(options.protectedRoots ?? [])]
    assertDedicatedPath(this.inventoryRoot, this.protectedRoots)

    const clock = options.clock ?? options.now
    if (clock !== undefined && typeof clock !== 'function') {
      throw new PublicationConfigurationError('clock must be a function')
    }
    this.clock = clock ?? (() => new Date())
    this.defaultChannel = channelOf(options.channel, 'provisional')

    const configured = options.limits
    const limits: PublicationLimits = {
      maxFiles: configured?.maxFiles ?? DEFAULT_PUBLICATION_LIMITS.maxFiles,
      maxFileBytes: configured?.maxFileBytes ?? DEFAULT_PUBLICATION_LIMITS.maxFileBytes,
      maxTotalBytes: configured?.maxTotalBytes ?? DEFAULT_PUBLICATION_LIMITS.maxTotalBytes,
      maxVersionDepth: configured?.maxVersionDepth ?? DEFAULT_PUBLICATION_LIMITS.maxVersionDepth,
    }
    if (
      !Number.isSafeInteger(limits.maxFiles)
      || limits.maxFiles <= 0
      || !Number.isSafeInteger(limits.maxFileBytes)
      || limits.maxFileBytes <= 0
      || !Number.isSafeInteger(limits.maxTotalBytes)
      || limits.maxTotalBytes <= 0
      || !Number.isSafeInteger(limits.maxVersionDepth)
      || limits.maxVersionDepth <= 0
    ) {
      throw new PublicationConfigurationError('publication limits must be positive integers')
    }
    if (limits.maxFileBytes > limits.maxTotalBytes) {
      throw new PublicationConfigurationError('maxFileBytes must not exceed maxTotalBytes')
    }
    this.limits = limits
  }

  /** Publish one accepted plan or bundle atomically. */
  async publish(request: PublicationRequest): Promise<PublicationResult> {
    const prepared = this.prepareRequest(request)
    const located = await this.locate(prepared.operation)
    return this.withLock(located.skillDir, async () => {
      try {
        return await this.publishLocked(prepared, located)
      } catch (error) {
        if (error instanceof PublicationError) throw error
        throw wrapIoError(error, 'publish', located.skillDir)
      }
    })
  }

  /** Resolve the currently published release for one skill. */
  async getCurrent(value: SkillId | string): Promise<CurrentPublication | undefined> {
    const skillId = String(value)
    const located = this.locatePaths(skillId)
    const state = await this.loadState(located)
    if (state === undefined) return undefined
    return {
      skillId,
      releaseId: state.current.releaseId,
      treeHash: state.current.treeHash,
      operationId: state.current.operationId,
      publishedAt: state.current.publishedAt,
      versionPath: join(located.versionsPath, state.current.releaseId),
      receiptPath: join(located.skillDir, state.current.receiptPath),
      statePath: located.statePath,
    }
  }

  /** Read the currently published bundle, or undefined when none exists. */
  async readCurrentBundle(value: SkillId | string): Promise<SkillBundle | undefined> {
    const current = await this.getCurrent(value)
    if (current === undefined) return undefined
    return readVersionBundle(current.versionPath, this.limits)
  }

  /** Restore a previously published release as the current release. */
  async rollback(
    input: RollbackRequest | SkillId | string,
    releaseId?: string,
  ): Promise<RollbackResult> {
    const request: RollbackRequest = typeof input === 'string'
      ? { skillId: input, ...(releaseId === undefined ? {} : { releaseId }) }
      : input
    const skillId = String(request.skillId)
    if (!isNonEmptyString(skillId)) {
      throw new PublicationValidationError([
        issue('$.skillId', 'invalid-skill-id', 'skill id must be non-empty'),
      ])
    }
    const located = await this.locatePathsOnly(skillId)
    return this.withLock(located.skillDir, async () => {
      try {
        return await this.rollbackLocked(skillId, request.releaseId, located)
      } catch (error) {
        if (error instanceof PublicationError) throw error
        throw wrapIoError(error, 'rollback', located.skillDir)
      }
    })
  }

  private prepareRequest(request: PublicationRequest): PreparedRequest {
    const operation = request.operation
    const issues = validateOperation(operation)
    if (issues.length > 0) throw new PublicationValidationError(issues)

    if (!SUPPORTED_KINDS.has(operation.kind)) {
      throw new UnsupportedPublicationOperationError(operation.kind)
    }
    const mode = planModeFor(operation.kind)
    if (mode === undefined) throw new UnsupportedPublicationOperationError(operation.kind)

    const plan = request.plan
    if (plan !== undefined) {
      const planIssues = validatePlan(operation, plan)
      if (planIssues.length > 0) throw new PublicationValidationError(planIssues)
    }

    let bundle: SkillBundle
    if (plan !== undefined && request.bundle !== undefined) {
      if (!bundleEquals(plan.bundle, request.bundle)) {
        throw new PublicationValidationError([
          issue(
            '$.bundle',
            'bundle-plan-mismatch',
            'explicit bundle does not match plan.bundle',
          ),
        ])
      }
      bundle = request.bundle
    } else if (plan !== undefined) {
      bundle = plan.bundle
    } else if (request.bundle !== undefined) {
      bundle = request.bundle
    } else {
      throw new PublicationValidationError([
        issue('$.bundle', 'missing-bundle', 'a skill plan or bundle is required'),
      ])
    }

    const preflight = resolvePreflightRequest(request)
    const preflightHash = hashPreflightReport(preflight)
    const verdict = preflightVerdictOf(preflight)
    const acceptance = acceptanceFrom(request, operation)

    if (request.verification !== undefined && request.verification.status !== 'pass') {
      throw new PublicationVerificationError(request.verification.status)
    }
    if (verdict === 'reject') {
      throw new PublicationPreflightError('preflight rejected the bundle', {
        verdict,
        reasons: reportRejectReasons(preflight),
        preflightHash,
      })
    }
    if (verdict === 'repair' && acceptance === undefined) {
      throw new PublicationPreflightError(
        'preflight requires repair; an accepted receipt is required to publish',
        { verdict, reasons: reportRejectReasons(preflight), preflightHash },
      )
    }

    if (!isNonEmptyString(request.policyVersion)) {
      throw new PublicationValidationError([
        issue('$.policyVersion', 'invalid-policy-version', 'policy version must be non-empty'),
      ])
    }
    if (!isNonEmptyString(request.configVersion)) {
      throw new PublicationValidationError([
        issue('$.configVersion', 'invalid-config-version', 'config version must be non-empty'),
      ])
    }
    const channel = channelOf(request.channel, this.defaultChannel)
    const sourceTraceIds = resolveSourceTraceIds(request, plan)
    if (plan !== undefined) {
      const missing: StructuredIssue[] = []
      for (const planned of [plan.skill, ...plan.resources]) {
        const path = 'resource' in planned ? planned.resource.path : planned.path
        if (!Object.prototype.hasOwnProperty.call(bundle, path)) {
          missing.push(issue(
            `$.bundle:${path}`,
            'missing-planned-file',
            `planned file ${path} is absent from the bundle`,
          ))
        }
      }
      if (missing.length > 0) throw new PublicationValidationError(missing)
    }
    // Validate the request bundle before any filesystem side effect.
    prepareBundle(bundle, this.limits)

    return {
      operation,
      plan,
      bundle,
      mode,
      preflight,
      preflightHash,
      sourceTraceIds,
      policyVersion: request.policyVersion,
      configVersion: request.configVersion,
      channel,
    }
  }

  private async locate(operation: Operation): Promise<LocatedSkill> {
    await this.ensureInventoryRoot()
    return this.locatePaths(String(operation.skillId))
  }

  private async locatePathsOnly(skillId: string): Promise<LocatedSkill> {
    await this.ensureInventoryRoot()
    return this.locatePaths(skillId)
  }

  private locatePaths(skillId: string): LocatedSkill {
    const skillDir = join(this.inventoryRoot, 'skills', skillDirectoryName(skillId))
    return {
      root: this.inventoryRoot,
      skillId,
      skillDir,
      statePath: join(skillDir, STATE_FILE),
      versionsPath: join(skillDir, 'versions'),
      receiptsPath: join(skillDir, 'receipts'),
    }
  }

  private async ensureInventoryRoot(): Promise<void> {
    const root = this.inventoryRoot
    let info
    try {
      info = await stat(root)
    } catch (error) {
      if (errnoCode(error) === 'ENOENT') {
        try {
          await mkdir(root, { recursive: true })
          const canonical = await realpath(root)
          assertDedicatedPath(canonical, this.protectedRoots)
          await this.writeMarker(root)
          return
        } catch (inner) {
          throw wrapIoError(inner, 'initialize inventory root', root)
        }
      }
      throw wrapIoError(error, 'stat inventory root', root)
    }
    if (!info.isDirectory()) {
      throw new PublicationConfigurationError(`inventory root is not a directory: ${root}`)
    }
    let canonical
    try {
      canonical = await realpath(root)
    } catch (error) {
      throw wrapIoError(error, 'resolve inventory root', root)
    }
    assertDedicatedPath(canonical, this.protectedRoots)
    let entries
    try {
      entries = await readdir(root)
    } catch (error) {
      throw wrapIoError(error, 'read inventory root', root)
    }
    const markerPath = join(root, MARKER_FILE)
    if (!entries.includes(MARKER_FILE)) {
      if (entries.length > 0) {
        throw new PublicationConfigurationError(
          `refusing to use a non-empty directory without a validation marker: ${root}`,
          [issue('$.inventoryRoot', 'unmarked-root', 'root is not a dedicated validation inventory')],
        )
      }
      await this.writeMarker(root)
      return
    }
    const marker = await readJson(markerPath)
    if (!isRecord(marker) || marker.kind !== 'validation') {
      throw new PublicationConfigurationError(
        `inventory marker does not declare a validation root: ${markerPath}`,
      )
    }
  }

  private async writeMarker(root: string): Promise<void> {
    const markerPath = join(root, MARKER_FILE)
    const marker = {
      schemaVersion: SCHEMA_VERSION,
      kind: 'validation',
      createdAt: this.timestamp(),
    }
    try {
      await writeAtomicJson(markerPath, marker)
    } catch (error) {
      throw wrapIoError(error, 'write inventory marker', markerPath)
    }
  }

  private timestamp(): string {
    const value = this.clock()
    const date = value instanceof Date ? value : new Date(value)
    if (Number.isNaN(date.getTime())) {
      throw new PublicationValidationError([
        issue('$.clock', 'invalid-clock', 'clock returned an invalid date'),
      ])
    }
    return date.toISOString()
  }

  private async loadState(located: LocatedSkill): Promise<SkillPublicationState | undefined> {
    const value = await readJson(located.statePath)
    if (value === undefined) return undefined
    return parseState(value, located.skillId)
  }

  private async publishLocked(
    prepared: PreparedRequest,
    located: LocatedSkill,
  ): Promise<PublicationResult> {
    const skillId = String(prepared.operation.skillId)
    const state = await this.loadState(located)
    let effectiveBundle = prepared.bundle
    if (prepared.mode === 'merge' && state !== undefined) {
      const current = await readVersionBundle(
        join(located.versionsPath, state.current.releaseId),
        this.limits,
      )
      effectiveBundle = mergeBundles(current, prepared.bundle)
    }
    const effective = prepareBundle(effectiveBundle, this.limits)
    const verdict = preflightVerdictOf(prepared.preflight)
    const fingerprint = fingerprintOf({
      operationId: String(prepared.operation.id),
      skillId,
      mode: prepared.mode,
      channel: prepared.channel,
      sourceTraceIds: prepared.sourceTraceIds,
      policyVersion: prepared.policyVersion,
      configVersion: prepared.configVersion,
      preflightVerdict: verdict,
      preflightHash: prepared.preflightHash,
      treeHash: effective.treeHash,
    })
    const receiptPath = receiptPathFor(located.skillDir, String(prepared.operation.id))
    const timestamp = this.timestamp()

    if (state !== undefined) {
      if (prepared.mode === 'create' && state.current.treeHash !== effective.treeHash) {
        throw new PublicationConflictError(
          `skill ${skillId} already has a published release`,
          [issue('$.operation.kind', 'create-conflict', 'create cannot replace an existing release')],
        )
      }
      if (prepared.mode === 'no_change' && state.current.treeHash !== effective.treeHash) {
        throw new PublicationConflictError(
          'no_change publication does not match the current release',
          [issue('$.bundle', 'no-change-mismatch', 'bundle differs from the current release')],
        )
      }
    } else if (prepared.mode === 'no_change') {
      throw new PublicationConflictError(
        'no_change publication requires an existing release',
        [issue('$.operation.kind', 'no-change-missing', 'no release exists to keep unchanged')],
      )
    }

    const existingReceipt = await this.readReceipt(receiptPath)
    if (existingReceipt !== undefined) {
      if (existingReceipt.fingerprint !== fingerprint) {
        throw new PublicationConflictError(
          'operation already published with different content or metadata',
          [issue('$', 'operation-already-published', 'receipt fingerprint does not match')],
        )
      }
      if (state === undefined || state.current.releaseId !== existingReceipt.releaseId) {
        throw new PublicationConflictError(
          'operation receipt exists but is not the current release',
          [issue('$', 'receipt-not-current', 'receipt does not match the current pointer')],
        )
      }
      return {
        receipt: existingReceipt,
        receiptPath,
        releaseId: existingReceipt.releaseId,
        treeHash: existingReceipt.treeHash,
        versionPath: join(located.versionsPath, existingReceipt.releaseId),
        statePath: located.statePath,
        previousVersion: existingReceipt.previousVersion,
        idempotent: true,
        created: false,
      }
    }

    if (state !== undefined && state.current.treeHash === effective.treeHash) {
      const receipt = this.buildReceipt({
        prepared,
        skillId,
        treeHash: effective.treeHash,
        fileCount: effective.files.length,
        totalBytes: effective.totalBytes,
        files: effective.files,
        timestamp,
        fingerprint,
        previous: state.previous,
        verdict,
      })
      const release = this.releaseFrom(receipt, located)
      const nextState: SkillPublicationState = {
        schemaVersion: SCHEMA_VERSION,
        skillId,
        current: release,
        previous: state.previous,
        releases: [...state.releases.filter((row) => row.releaseId !== release.releaseId), release],
        rollbacks: state.rollbacks,
      }
      await mkdir(located.receiptsPath, { recursive: true })
      try {
        await writeAtomicJson(receiptPath, receipt)
        await writeAtomicJson(located.statePath, nextState)
      } catch (error) {
        await rm(receiptPath, { force: true }).catch(() => undefined)
        throw wrapIoError(error, 'write identical publication receipt', receiptPath)
      }
      return {
        receipt,
        receiptPath,
        releaseId: release.releaseId,
        treeHash: release.treeHash,
        versionPath: join(located.versionsPath, release.releaseId),
        statePath: located.statePath,
        previousVersion: receipt.previousVersion,
        idempotent: true,
        created: false,
      }
    }

    const versionPath = join(located.versionsPath, effective.treeHash)
    const existingVersion = await this.pathExists(versionPath)
    let createdVersion = false
    let createdSkillDir = false
    let receiptWritten = false
    let stagePath: string | undefined

    try {
      if (existingVersion) {
        await this.verifyVersion(versionPath, effective.treeHash)
      } else {
        const exists = await this.pathExists(located.skillDir)
        await mkdir(located.versionsPath, { recursive: true })
        await mkdir(located.receiptsPath, { recursive: true })
        createdSkillDir = !exists
        if (createdSkillDir) {
          await syncDirectory(located.skillDir)
          await syncDirectory(join(located.root, 'skills'))
          await syncDirectory(located.root)
        }
        stagePath = await mkdtemp(join(located.skillDir, '.publish-'))
        await this.materialize(stagePath, effective.entries)
        try {
          await rename(stagePath, versionPath)
          stagePath = undefined
          createdVersion = true
        } catch (error) {
          if (errnoCode(error) === 'EEXIST' || errnoCode(error) === 'ENOTEMPTY') {
            await this.verifyVersion(versionPath, effective.treeHash)
            if (stagePath !== undefined) {
              await rm(stagePath, { recursive: true, force: true }).catch(() => undefined)
              stagePath = undefined
            }
          } else {
            throw error
          }
        }
        await syncDirectory(located.versionsPath)
        await syncDirectory(located.skillDir)
      }

      const receipt = this.buildReceipt({
        prepared,
        skillId,
        treeHash: effective.treeHash,
        fileCount: effective.files.length,
        totalBytes: effective.totalBytes,
        files: effective.files,
        timestamp,
        fingerprint,
        previous: state?.current ?? null,
        verdict,
      })
      const release = this.releaseFrom(receipt, located)
      const nextState: SkillPublicationState = {
        schemaVersion: SCHEMA_VERSION,
        skillId,
        current: release,
        previous: state?.current ?? null,
        releases: [...(state?.releases ?? []).filter(
          (row) => row.releaseId !== release.releaseId,
        ), release],
        rollbacks: state?.rollbacks ?? [],
      }
      await writeAtomicJson(receiptPath, receipt)
      receiptWritten = true
      await writeAtomicJson(located.statePath, nextState)
      return {
        receipt,
        receiptPath,
        releaseId: release.releaseId,
        treeHash: release.treeHash,
        versionPath,
        statePath: located.statePath,
        previousVersion: receipt.previousVersion,
        idempotent: false,
        created: createdVersion,
      }
    } catch (error) {
      if (stagePath !== undefined) {
        await rm(stagePath, { recursive: true, force: true }).catch(() => undefined)
      }
      if (receiptWritten) {
        await rm(receiptPath, { force: true }).catch(() => undefined)
      }
      if (createdVersion) {
        await rm(versionPath, { recursive: true, force: true }).catch(() => undefined)
      }
      if (createdSkillDir) {
        await rm(located.skillDir, { recursive: true, force: true }).catch(() => undefined)
      }
      throw error instanceof PublicationError
        ? error
        : wrapIoError(error, 'publish release', versionPath)
    }
  }

  private async rollbackLocked(
    skillId: string,
    requestedRelease: string | undefined,
    located: LocatedSkill,
  ): Promise<RollbackResult> {
    const state = await this.loadState(located)
    if (state === undefined) {
      throw new PublicationRollbackError('no publication state exists for this skill', {
        skillId,
        statePath: located.statePath,
      })
    }
    const targetId = requestedRelease ?? state.previous?.releaseId
    if (targetId === undefined) {
      throw new PublicationRollbackError('no previous release is available to roll back to', {
        skillId,
      })
    }
    if (targetId === state.current.releaseId) {
      return {
        skillId,
        releaseId: state.current.releaseId,
        treeHash: state.current.treeHash,
        versionPath: join(located.versionsPath, state.current.releaseId),
        receiptPath: join(located.skillDir, state.current.receiptPath),
        statePath: located.statePath,
        previousVersion: state.previous?.releaseId ?? state.current.releaseId,
        idempotent: true,
      }
    }
    const target = state.releases.find((row) => row.releaseId === targetId)
      ?? (state.previous?.releaseId === targetId ? state.previous : undefined)
    if (target === undefined) {
      throw new PublicationRollbackError(`release ${targetId} is not retained`, {
        skillId,
        releaseId: targetId,
      })
    }
    const versionPath = join(located.versionsPath, target.releaseId)
    await this.verifyVersion(versionPath, target.treeHash)
    const nextState: SkillPublicationState = {
      schemaVersion: SCHEMA_VERSION,
      skillId,
      current: target,
      previous: state.current,
      releases: state.releases,
      rollbacks: [...state.rollbacks, {
        from: state.current.releaseId,
        to: target.releaseId,
        at: this.timestamp(),
      }].slice(-100),
    }
    await writeAtomicJson(located.statePath, nextState)
    return {
      skillId,
      releaseId: target.releaseId,
      treeHash: target.treeHash,
      versionPath,
      receiptPath: join(located.skillDir, target.receiptPath),
      statePath: located.statePath,
      previousVersion: state.current.releaseId,
      idempotent: false,
    }
  }

  private buildReceipt(input: {
    readonly prepared: PreparedRequest
    readonly skillId: string
    readonly treeHash: string
    readonly fileCount: number
    readonly totalBytes: number
    readonly files: readonly PublicationFileRecord[]
    readonly timestamp: string
    readonly fingerprint: string
    readonly previous: PublishedRelease | null
    readonly verdict: PreflightVerdict
  }): PublicationReceiptDocument {
    return {
      schemaVersion: SCHEMA_VERSION,
      operationId: String(input.prepared.operation.id),
      skillId: input.skillId,
      operationKind: input.prepared.operation.kind,
      mode: input.prepared.mode,
      channel: input.prepared.channel,
      sourceTraceIds: input.prepared.sourceTraceIds,
      policyVersion: input.prepared.policyVersion,
      configVersion: input.prepared.configVersion,
      preflightVerdict: input.verdict,
      preflightHash: input.prepared.preflightHash,
      files: input.files,
      fileCount: input.fileCount,
      totalBytes: input.totalBytes,
      treeHash: input.treeHash,
      releaseId: input.treeHash,
      timestamp: input.timestamp,
      previousVersion: input.previous?.releaseId ?? null,
      previousTreeHash: input.previous?.treeHash ?? null,
      rollbackTo: input.previous?.releaseId ?? null,
      fingerprint: input.fingerprint,
    }
  }

  private releaseFrom(
    receipt: PublicationReceiptDocument,
    located: LocatedSkill,
  ): PublishedRelease {
    const receiptPath = normalizeRelativePath(relative(located.skillDir, receiptPathFor(
      located.skillDir,
      receipt.operationId,
    )))
    return {
      releaseId: receipt.releaseId,
      treeHash: receipt.treeHash,
      operationId: receipt.operationId,
      publishedAt: receipt.timestamp,
      receiptPath,
      fileCount: receipt.fileCount,
      totalBytes: receipt.totalBytes,
    }
  }

  private async readReceipt(path: string): Promise<PublicationReceiptDocument | undefined> {
    const value = await readJson(path)
    if (value === undefined) return undefined
    return parseReceipt(value, path)
  }

  private async materialize(
    stagePath: string,
    entries: readonly (readonly [string, string])[],
  ): Promise<void> {
    const directories = new Set<string>([stagePath])
    for (const [path, content] of entries) {
      const target = resolve(stagePath, ...path.split('/'))
      if (!isSameOrInside(stagePath, target)) {
        throw new PublicationValidationError([
          issue(path, 'path-escape', 'published path escapes the staging directory'),
        ])
      }
      await mkdir(dirname(target), { recursive: true })
      directories.add(dirname(target))
      const handle = await open(target, 'wx', 0o644)
      try {
        await handle.writeFile(content, 'utf8')
        await handle.sync()
      } finally {
        await handle.close()
      }
    }
    const ordered = [...directories].sort((left, right) => right.length - left.length)
    for (const directory of ordered) {
      await syncDirectory(directory)
    }
  }

  private async verifyVersion(versionPath: string, expectedTreeHash: string): Promise<void> {
    const exists = await this.pathExists(versionPath)
    if (!exists) {
      throw new CorruptPublicationError(`release directory is missing: ${versionPath}`, {
        versionPath,
        expectedTreeHash,
      })
    }
    const bundle = await readVersionBundle(versionPath, this.limits)
    const prepared = prepareFromBundle(bundle)
    if (prepared.treeHash !== expectedTreeHash) {
      throw new CorruptPublicationError(
        `release content does not match its content address: ${versionPath}`,
        { versionPath, expectedTreeHash, actualTreeHash: prepared.treeHash },
      )
    }
  }

  private async pathExists(path: string): Promise<boolean> {
    try {
      await stat(path)
      return true
    } catch (error) {
      if (errnoCode(error) === 'ENOENT') return false
      throw wrapIoError(error, 'stat', path)
    }
  }

  private withLock<T>(key: string, action: () => Promise<T>): Promise<T> {
    const previous = this.locks.get(key) ?? Promise.resolve()
    const run = previous.then(action, action)
    const tail = run.then(() => undefined, () => undefined)
    this.locks.set(key, tail)
    return run.finally(() => {
      if (this.locks.get(key) === tail) this.locks.delete(key)
    })
  }
}
