import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { basename, resolve, sep } from 'node:path'
import type { VerificationContext, Verifier } from '../capabilities/definitions.ts'
import type {
  VerificationEvidence,
  VerificationStatus,
} from '../contracts/evidence.ts'
import type { Operation } from '../contracts/operations.ts'
import { isRecord } from '../contracts/validation.ts'
import type { PreflightReport, PreflightVerdict } from '../preflight/preflight.ts'
import {
  scanContentForLeakage,
  validateResourcePath,
  type SkillBundle,
  type SkillPlan,
} from '../resources/planner.ts'

/**
 * Advisory network policy for the subprocess runner.
 *
 * `advisory-deny` removes proxy variables and does not configure any network
 * access, but it is NOT an OS-level network sandbox: an executed script can
 * still open sockets. Real network isolation requires a container, network
 * namespace, or firewall outside this process. Callers that need a hard
 * guarantee must enforce it at the host/container boundary.
 */
export type ReplayNetworkPolicy = 'advisory-deny' | 'unrestricted'

/** Configuration for the isolated subprocess runner. */
export interface SubprocessScriptRunnerOptions {
  /** Interpreter executable. Defaults to `python3`. Treat this as trusted config. */
  readonly executable?: string
  /** Pass `-I` (Python isolated mode) to the interpreter. Defaults to true. */
  readonly isolated?: boolean
  /** Hard per-process wall clock ceiling. Defaults to 5000ms. */
  readonly maximumWallMs?: number
  /** Maximum captured stdout bytes before the process is killed. Defaults to 64 KiB. */
  readonly maximumStdoutBytes?: number
  /** Maximum captured stderr bytes before the process is killed. Defaults to 64 KiB. */
  readonly maximumStderrBytes?: number
  /** Maximum stdin bytes accepted by the runner. Defaults to 1 MiB. */
  readonly maximumInputBytes?: number
  /**
   * Optional host roots that a replay staging directory must live under.
   *
   * The runner never reads the real inventory: it receives script content and
   * writes a fresh copy into a private temp directory. When provided, this
   * option constrains where that temp directory may be created.
   */
  readonly allowedRoots?: readonly string[]
  /** Advisory only; see {@link ReplayNetworkPolicy}. Defaults to `advisory-deny`. */
  readonly networkPolicy?: ReplayNetworkPolicy
  /** Extra sanitized environment entries; values are never interpolated into a shell. */
  readonly environment?: Readonly<Record<string, string>>
  /** Base directory for the per-run staging directory. Defaults to `os.tmpdir()`. */
  readonly temporaryDirectory?: string
}

/** One isolated script execution request. */
export interface IsolatedScriptRequest {
  /** Bundle-relative script path; only used to name the staged copy. */
  readonly scriptPath: string
  /** Script source written into the staging directory. */
  readonly scriptContent: string
  /** Bytes piped to the process on standard input. */
  readonly stdin: string
  /** Requested wall clock timeout. Clamped by the runner ceiling. */
  readonly timeoutMs: number
}

/** One isolated script execution result. */
export interface IsolatedScriptResult {
  readonly exitCode: number | null
  readonly signal: NodeJS.Signals | null
  readonly stdout: string
  readonly stderr: string
  readonly wallMs: number
  readonly timedOut: boolean
  readonly stdoutBytes: number
  readonly stderrBytes: number
  readonly stdoutTruncated: boolean
  readonly stderrTruncated: boolean
  readonly outputLimitExceeded: boolean
  /** SHA-256 of the captured stdout bytes. */
  readonly outputHash: string
  /** SHA-256 of the captured stderr bytes. */
  readonly stderrHash: string
}

/** Injection boundary; the verifier can be tested with a deterministic fake. */
export interface ReplayScriptRunner {
  run(request: IsolatedScriptRequest): Promise<IsolatedScriptResult>
}

/** A runner rejected a request for policy or staging reasons. */
export class ReplayScriptError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'ReplayScriptError'
    this.code = code
  }
}

/** SHA-256 of a UTF-8 string, hex encoded. */
export function hashText(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex')
}

function hashBuffer(buffer: Buffer): string {
  return createHash('sha256').update(buffer).digest('hex')
}

const SCRIPT_EXTENSIONS = ['.py', '.js', '.mjs', '.ts', '.sh', '.rb'] as const
const FIXTURE_PATH_PATTERN = /^evals\/fixtures\/[^/]+\.json$/
const PROXY_ENVIRONMENT_KEYS = [
  'HTTP_PROXY',
  'HTTPS_PROXY',
  'ALL_PROXY',
  'NO_PROXY',
  'http_proxy',
  'https_proxy',
  'all_proxy',
  'no_proxy',
] as const

const NETWORK_PATTERNS: readonly RegExp[] = [
  /^\s*(?:import|from)\s+(?:socket|ssl|http|urllib|requests|httpx|aiohttp|ftplib|telnetlib|smtplib)\b/m,
  /\b(?:socket\.socket|urllib\.request|http\.client|requests\.(?:get|post|put|delete)|httpx\.|aiohttp\.)/,
]

const DESTRUCTIVE_PATTERNS: readonly RegExp[] = [
  /\bsubprocess\.(?:run|call|Popen|check_output|check_call|getoutput)\s*\(/,
  /\bos\.(?:system|popen|remove|unlink|rmdir|removedirs|rename|replace|chmod|chown)\s*\(/,
  /\bshutil\.(?:rmtree|move|copy)\s*\(/,
  /\bpathlib\.Path\([^)]*\)\.(?:unlink|rmdir|write_text|write_bytes)\s*\(/,
  /\b(?:rm|mv|dd|mkfs|shutdown|reboot)\s+-/,
]

function isScriptPath(path: string): boolean {
  if (!path.startsWith('scripts/')) return false
  const lower = path.toLowerCase()
  return SCRIPT_EXTENSIONS.some((extension) => lower.endsWith(extension))
}

function isWithin(root: string, candidate: string): boolean {
  const resolvedRoot = resolve(root)
  const resolvedCandidate = resolve(candidate)
  return resolvedCandidate === resolvedRoot
    || resolvedCandidate.startsWith(`${resolvedRoot}${sep}`)
}

function positiveInteger(value: number, name: string): number {
  if (!Number.isFinite(value) || value <= 0) {
    throw new ReplayScriptError('invalid-limit', `${name} must be a positive finite number`)
  }
  return Math.max(1, Math.floor(value))
}

function assertSafeScriptPath(scriptPath: string): void {
  if (!isScriptPath(scriptPath)) {
    throw new ReplayScriptError(
      'unsupported-script',
      `refusing to execute ${scriptPath}; only scripts/*.{py,js,mjs,ts,sh,rb} may be staged`,
    )
  }
  const issues = validateResourcePath(scriptPath)
  if (issues.length > 0) {
    throw new ReplayScriptError(
      'unsafe-script-path',
      `refusing to stage unsafe script path ${scriptPath}: ${issues.map((entry) => entry.code).join(', ')}`,
    )
  }
}

function killProcessTree(child: ChildProcessWithoutNullStreams, signal: NodeJS.Signals): void {
  const pid = child.pid
  if (pid === undefined) return
  try {
    if (process.platform !== 'win32') {
      process.kill(-pid, signal)
      return
    }
  } catch {
    // Fall through to killing the direct child only.
  }
  try {
    child.kill(signal)
  } catch {
    // The process already exited.
  }
}

function buildEnvironment(
  stagingDirectory: string,
  options: {
    readonly networkPolicy: ReplayNetworkPolicy
    readonly extra: Readonly<Record<string, string>> | undefined
  },
): NodeJS.ProcessEnv {
  const environment: NodeJS.ProcessEnv = {
    PATH: process.env.PATH ?? '/usr/local/bin:/usr/bin:/bin',
    HOME: stagingDirectory,
    TMPDIR: stagingDirectory,
    TEMP: stagingDirectory,
    TMP: stagingDirectory,
    LANG: 'C.UTF-8',
    LC_ALL: 'C.UTF-8',
    PYTHONIOENCODING: 'utf-8',
    PYTHONHASHSEED: '0',
    PYTHONDONTWRITEBYTECODE: '1',
    PYTHONNOUSERSITE: '1',
    PYTHONUTF8: '1',
  }
  if (options.extra !== undefined) {
    for (const [key, value] of Object.entries(options.extra)) {
      if (key.length > 0) environment[key] = value
    }
  }
  if (options.networkPolicy === 'advisory-deny') {
    for (const key of PROXY_ENVIRONMENT_KEYS) delete environment[key]
  }
  return environment
}

/**
 * Runs one script in a fresh temporary directory with a sanitized environment.
 *
 * Isolation properties:
 * - `spawn` is used with `shell: false`; no bundle content is ever interpolated
 *   into a command line.
 * - the interpreter runs with `-I` by default and a private `HOME`/`TMPDIR`;
 * - only the staged script and the fixture stdin file are written to the temp
 *   directory, which is deleted afterwards;
 * - stdout/stderr are byte-capped and the process group is killed on timeout or
 *   output overflow.
 *
 * Not provided: an OS-level network or filesystem sandbox. The child inherits
 * the host user's filesystem permissions. Use a container or namespace when a
 * hard guarantee is required.
 */
export class SubprocessScriptRunner implements ReplayScriptRunner {
  private readonly executable: string
  private readonly isolated: boolean
  private readonly maximumWallMs: number
  private readonly maximumStdoutBytes: number
  private readonly maximumStderrBytes: number
  private readonly maximumInputBytes: number
  private readonly allowedRoots: readonly string[] | undefined
  private readonly networkPolicy: ReplayNetworkPolicy
  private readonly environment: Readonly<Record<string, string>> | undefined
  private readonly temporaryDirectory: string

  constructor(options: SubprocessScriptRunnerOptions = {}) {
    this.executable = options.executable ?? 'python3'
    this.isolated = options.isolated ?? true
    this.maximumWallMs = positiveInteger(options.maximumWallMs ?? 5000, 'maximumWallMs')
    this.maximumStdoutBytes = positiveInteger(options.maximumStdoutBytes ?? 65_536, 'maximumStdoutBytes')
    this.maximumStderrBytes = positiveInteger(options.maximumStderrBytes ?? 65_536, 'maximumStderrBytes')
    this.maximumInputBytes = positiveInteger(options.maximumInputBytes ?? 1_048_576, 'maximumInputBytes')
    this.allowedRoots = options.allowedRoots
    this.networkPolicy = options.networkPolicy ?? 'advisory-deny'
    this.environment = options.environment
    this.temporaryDirectory = options.temporaryDirectory ?? tmpdir()
    if (this.executable.trim().length === 0) {
      throw new ReplayScriptError('invalid-executable', 'executable must not be empty')
    }
  }

  async run(request: IsolatedScriptRequest): Promise<IsolatedScriptResult> {
    assertSafeScriptPath(request.scriptPath)
    if (request.scriptContent.trim().length === 0) {
      throw new ReplayScriptError('empty-script', `${request.scriptPath} has no content to stage`)
    }
    const timeoutMs = positiveInteger(
      Math.min(request.timeoutMs, this.maximumWallMs),
      'timeoutMs',
    )
    const inputBuffer = Buffer.from(request.stdin, 'utf8')
    if (inputBuffer.byteLength > this.maximumInputBytes) {
      throw new ReplayScriptError(
        'input-limit',
        `fixture stdin is ${inputBuffer.byteLength} bytes, above the ${this.maximumInputBytes} byte limit`,
      )
    }

    const stagingDirectory = await mkdtemp(resolve(this.temporaryDirectory, 'skill-replay-'))
    try {
      if (this.allowedRoots !== undefined) {
        const allowed = this.allowedRoots.some((root) => isWithin(root, stagingDirectory))
        if (!allowed) {
          throw new ReplayScriptError(
            'staging-root-denied',
            `staging directory ${stagingDirectory} is outside the configured allowed roots`,
          )
        }
      }
      const scriptDirectory = resolve(stagingDirectory, 'scripts')
      const scriptTarget = resolve(scriptDirectory, basename(request.scriptPath))
      if (!isWithin(stagingDirectory, scriptTarget)) {
        throw new ReplayScriptError('unsafe-script-path', 'staged script escaped its staging directory')
      }
      await mkdir(scriptDirectory, { recursive: true, mode: 0o700 })
      await writeFile(scriptTarget, request.scriptContent, { encoding: 'utf8', mode: 0o600 })
      await writeFile(resolve(stagingDirectory, 'input.json'), inputBuffer, { mode: 0o600 })
      return await this.execute(stagingDirectory, scriptTarget, inputBuffer, timeoutMs)
    } finally {
      await rm(stagingDirectory, { recursive: true, force: true }).catch(() => undefined)
    }
  }

  private async execute(
    stagingDirectory: string,
    scriptTarget: string,
    inputBuffer: Buffer,
    timeoutMs: number,
  ): Promise<IsolatedScriptResult> {
    const environment = buildEnvironment(stagingDirectory, {
      networkPolicy: this.networkPolicy,
      extra: this.environment,
    })
    const args = this.isolated ? ['-I', scriptTarget] : [scriptTarget]
    const startedAt = Date.now()
    const child = spawn(this.executable, args, {
      cwd: stagingDirectory,
      env: environment,
      shell: false,
      stdio: ['pipe', 'pipe', 'pipe'],
      detached: process.platform !== 'win32',
    })

    return await new Promise<IsolatedScriptResult>((resolvePromise, rejectPromise) => {
      const stdoutChunks: Buffer[] = []
      const stderrChunks: Buffer[] = []
      let stdoutBytes = 0
      let stderrBytes = 0
      let stdoutTruncated = false
      let stderrTruncated = false
      let timedOut = false
      let settled = false
      let timer: NodeJS.Timeout | undefined

      const finish = (build: () => IsolatedScriptResult): void => {
        if (settled) return
        settled = true
        if (timer !== undefined) clearTimeout(timer)
        resolvePromise(build())
      }
      const fail = (error: Error): void => {
        if (settled) return
        settled = true
        if (timer !== undefined) clearTimeout(timer)
        rejectPromise(error)
      }

      child.stdout.on('data', (chunk: Buffer) => {
        if (stdoutTruncated) return
        const seen = stdoutBytes + chunk.length
        if (seen > this.maximumStdoutBytes) {
          const remaining = Math.max(0, this.maximumStdoutBytes - stdoutBytes)
          if (remaining > 0) stdoutChunks.push(chunk.subarray(0, remaining))
          stdoutBytes = seen
          stdoutTruncated = true
          killProcessTree(child, 'SIGKILL')
          return
        }
        stdoutBytes = seen
        stdoutChunks.push(chunk)
      })
      child.stderr.on('data', (chunk: Buffer) => {
        if (stderrTruncated) return
        const seen = stderrBytes + chunk.length
        if (seen > this.maximumStderrBytes) {
          const remaining = Math.max(0, this.maximumStderrBytes - stderrBytes)
          if (remaining > 0) stderrChunks.push(chunk.subarray(0, remaining))
          stderrBytes = seen
          stderrTruncated = true
          killProcessTree(child, 'SIGKILL')
          return
        }
        stderrBytes = seen
        stderrChunks.push(chunk)
      })
      child.stdin.on('error', () => undefined)
      child.once('error', (error: Error) => {
        fail(new ReplayScriptError('spawn-failed', `failed to start ${this.executable}: ${error.message}`))
      })
      child.once('close', (code: number | null, signal: NodeJS.Signals | null) => {
        const stdoutBuffer = Buffer.concat(stdoutChunks)
        const stderrBuffer = Buffer.concat(stderrChunks)
        finish(() => ({
          exitCode: code,
          signal,
          stdout: stdoutBuffer.toString('utf8'),
          stderr: stderrBuffer.toString('utf8'),
          wallMs: Math.max(0, Date.now() - startedAt),
          timedOut,
          stdoutBytes,
          stderrBytes,
          stdoutTruncated,
          stderrTruncated,
          outputLimitExceeded: stdoutTruncated || stderrTruncated,
          outputHash: hashBuffer(stdoutBuffer),
          stderrHash: hashBuffer(stderrBuffer),
        }))
      })

      timer = setTimeout(() => {
        timedOut = true
        killProcessTree(child, 'SIGKILL')
      }, timeoutMs)
      child.stdin.end(inputBuffer)
    })
  }
}

/** Replay budget, enforced before and during execution. */
export interface ReplayLimits {
  readonly scriptTimeoutMs: number
  readonly maximumProcesses: number
  readonly maximumTotalWallMs: number
  readonly maximumStdoutBytes: number
  readonly maximumStderrBytes: number
}

/** Default replay budgets for planner-sized bundles. */
export const DEFAULT_REPLAY_LIMITS: ReplayLimits = {
  scriptTimeoutMs: 5000,
  maximumProcesses: 64,
  maximumTotalWallMs: 120_000,
  maximumStdoutBytes: 65_536,
  maximumStderrBytes: 65_536,
}

/** Safety and determinism policy applied by the verifier. */
export interface ReplayPolicy {
  /** Number of identical-fixture runs used to prove determinism. Defaults to 2. */
  readonly determinismRuns: number
  /** Reject scripts that import network clients before spawning. Defaults to true. */
  readonly denyNetwork: boolean
  /** Reject scripts that invoke process/shell/filesystem destruction before spawning. Defaults to true. */
  readonly denyDestructiveCommands: boolean
  /** Require every script to have at least one fixture. Defaults to true. */
  readonly requireFixturePerScript: boolean
  /** Script extensions the configured interpreter can execute. Defaults to `.py`. */
  readonly supportedScriptExtensions: readonly string[]
}

/** Default replay policy. */
export const DEFAULT_REPLAY_POLICY: ReplayPolicy = {
  determinismRuns: 2,
  denyNetwork: true,
  denyDestructiveCommands: true,
  requireFixturePerScript: true,
  supportedScriptExtensions: ['.py'],
}

/** An already-computed preflight receipt supplied as replay evidence. */
export interface ReplayPreflightReceipt {
  readonly verdict: PreflightVerdict
  readonly reportHash?: string
  readonly rejectCodes?: readonly string[]
  readonly repairCodes?: readonly string[]
}

/** Plan, bundle, and preflight context accepted by the verifier. */
export interface ReplayContext extends VerificationContext {
  readonly preflightReceipt?: ReplayPreflightReceipt
}

/** Per-call Verifier context, including runner and budget overrides. */
export interface ReplayCallContext extends ReplayContext {
  readonly runner?: ReplayScriptRunner
  readonly limits?: Partial<ReplayLimits>
  readonly policy?: Partial<ReplayPolicy>
}

/** Explicit replay request. `bundle` wins over `plan.bundle` when both are supplied. */
export interface ReplayRequest extends ReplayContext {
  readonly operation: Operation
  readonly runner?: ReplayScriptRunner
  readonly limits?: Partial<ReplayLimits>
  readonly policy?: Partial<ReplayPolicy>
}

/** Construct options for a reusable verifier instance. */
export interface ReplayVerifierOptions extends ReplayContext {
  readonly runner?: ReplayScriptRunner
  readonly limits?: Partial<ReplayLimits>
  readonly policy?: Partial<ReplayPolicy>
}

/** Which part of replay produced a reason. */
export type ReplayReasonArea =
  | 'context'
  | 'safety'
  | 'structure'
  | 'reference'
  | 'leakage'
  | 'execution'
  | 'output'
  | 'determinism'
  | 'efficiency'

/** Whether a failure can be repaired inside the pipeline or is terminal. */
export type ReplayReasonClassification = 'repairable' | 'terminal'

/** One structured verification reason. */
export interface ReplayReason {
  readonly code: string
  readonly message: string
  readonly area: ReplayReasonArea
  readonly classification: ReplayReasonClassification
  readonly path?: string
  readonly details?: Readonly<Record<string, unknown>>
}

/** One recorded process execution. */
export interface ReplayRunRecord {
  readonly scriptPath: string
  readonly fixturePath: string
  readonly runIndex: number
  readonly exitCode: number | null
  readonly signal: string | null
  readonly durationMs: number
  readonly stdout: string
  readonly stderr: string
  readonly stdoutHash: string
  readonly stderrHash: string
  readonly outputHash: string
  readonly stdoutBytes: number
  readonly stderrBytes: number
  readonly timedOut: boolean
  readonly outputLimitExceeded: boolean
  readonly stdoutTruncated: boolean
  readonly stderrTruncated: boolean
  readonly parsed: boolean
  readonly expectedMatched: boolean
}

interface ReplayReasonInput {
  readonly code: string
  readonly message: string
  readonly area: ReplayReasonArea
  readonly classification: ReplayReasonClassification
  readonly path?: string
  readonly details?: Readonly<Record<string, unknown>>
}

function replayReason(input: ReplayReasonInput): ReplayReason {
  return {
    code: input.code,
    message: input.message,
    area: input.area,
    classification: input.classification,
    ...(input.path === undefined ? {} : { path: input.path }),
    ...(input.details === undefined ? {} : { details: input.details }),
  }
}

function resolveLimits(overrides: Partial<ReplayLimits> | undefined): ReplayLimits {
  const requested = {
    scriptTimeoutMs: overrides?.scriptTimeoutMs ?? DEFAULT_REPLAY_LIMITS.scriptTimeoutMs,
    maximumProcesses: overrides?.maximumProcesses ?? DEFAULT_REPLAY_LIMITS.maximumProcesses,
    maximumTotalWallMs: overrides?.maximumTotalWallMs ?? DEFAULT_REPLAY_LIMITS.maximumTotalWallMs,
    maximumStdoutBytes: overrides?.maximumStdoutBytes ?? DEFAULT_REPLAY_LIMITS.maximumStdoutBytes,
    maximumStderrBytes: overrides?.maximumStderrBytes ?? DEFAULT_REPLAY_LIMITS.maximumStderrBytes,
  }
  for (const [name, value] of Object.entries(requested)) {
    if (!Number.isFinite(value) || value <= 0) {
      throw new ReplayScriptError('invalid-limit', `${name} must be a positive finite number`)
    }
  }
  return {
    scriptTimeoutMs: positiveInteger(requested.scriptTimeoutMs, 'scriptTimeoutMs'),
    maximumProcesses: positiveInteger(requested.maximumProcesses, 'maximumProcesses'),
    maximumTotalWallMs: positiveInteger(requested.maximumTotalWallMs, 'maximumTotalWallMs'),
    maximumStdoutBytes: positiveInteger(requested.maximumStdoutBytes, 'maximumStdoutBytes'),
    maximumStderrBytes: positiveInteger(requested.maximumStderrBytes, 'maximumStderrBytes'),
  }
}

function resolvePolicy(overrides: Partial<ReplayPolicy> | undefined): ReplayPolicy {
  const policy: ReplayPolicy = {
    determinismRuns: overrides?.determinismRuns ?? DEFAULT_REPLAY_POLICY.determinismRuns,
    denyNetwork: overrides?.denyNetwork ?? DEFAULT_REPLAY_POLICY.denyNetwork,
    denyDestructiveCommands:
      overrides?.denyDestructiveCommands ?? DEFAULT_REPLAY_POLICY.denyDestructiveCommands,
    requireFixturePerScript:
      overrides?.requireFixturePerScript ?? DEFAULT_REPLAY_POLICY.requireFixturePerScript,
    supportedScriptExtensions:
      overrides?.supportedScriptExtensions ?? DEFAULT_REPLAY_POLICY.supportedScriptExtensions,
  }
  if (!Number.isInteger(policy.determinismRuns) || policy.determinismRuns < 1) {
    throw new ReplayScriptError('invalid-policy', 'determinismRuns must be a positive integer')
  }
  return policy
}

/** Extract safe bundle-relative references from rendered content. */
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

/** Partial structural comparison used by fixtures: every expected key must match. */
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

interface ParsedFixture {
  readonly path: string
  readonly script: string
  readonly input: Readonly<Record<string, unknown>>
  readonly expected: Readonly<Record<string, unknown>>
}

type ParseFixtureResult =
  | { readonly ok: true; readonly fixture: ParsedFixture }
  | { readonly ok: false; readonly reason: ReplayReason }

function parseFixture(path: string, content: string): ParseFixtureResult {
  let value: unknown
  try {
    value = JSON.parse(content)
  } catch {
    return {
      ok: false,
      reason: replayReason({
        code: 'invalid-fixture-json',
        message: `${path} must contain valid JSON`,
        area: 'structure',
        classification: 'repairable',
        path,
      }),
    }
  }
  if (!isRecord(value)) {
    return {
      ok: false,
      reason: replayReason({
        code: 'invalid-fixture',
        message: `${path} must contain a JSON object`,
        area: 'structure',
        classification: 'repairable',
        path,
      }),
    }
  }
  if (value.schemaVersion !== undefined && value.schemaVersion !== 1) {
    return {
      ok: false,
      reason: replayReason({
        code: 'unsupported-fixture-version',
        message: `${path} schemaVersion must be 1 when present`,
        area: 'structure',
        classification: 'repairable',
        path,
      }),
    }
  }
  const script = value.script
  if (typeof script !== 'string' || script.trim().length === 0) {
    return {
      ok: false,
      reason: replayReason({
        code: 'fixture-script',
        message: `${path} must declare a script path`,
        area: 'structure',
        classification: 'repairable',
        path,
      }),
    }
  }
  const scriptIssues = validateResourcePath(script)
  if (!script.startsWith('scripts/') || scriptIssues.length > 0) {
    return {
      ok: false,
      reason: replayReason({
        code: 'unsafe-fixture-script',
        message: `${path} declares an unsafe script path ${script}`,
        area: 'safety',
        classification: 'terminal',
        path,
      }),
    }
  }
  const input = value.input
  if (!isRecord(input)) {
    return {
      ok: false,
      reason: replayReason({
        code: 'fixture-input',
        message: `${path} input must be a JSON object`,
        area: 'structure',
        classification: 'repairable',
        path,
      }),
    }
  }
  const expected = value.expect
  if (!isRecord(expected)) {
    return {
      ok: false,
      reason: replayReason({
        code: 'fixture-expect',
        message: `${path} expect must be a JSON object`,
        area: 'structure',
        classification: 'repairable',
        path,
      }),
    }
  }
  return { ok: true, fixture: { path, script, input, expected } }
}

function matchesAnyPattern(content: string, patterns: readonly RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(content))
}

function clipUtf8(text: string, maximumBytes: number): string {
  const buffer = Buffer.from(text, 'utf8')
  if (buffer.byteLength <= maximumBytes) return text
  return buffer.subarray(0, maximumBytes).toString('utf8')
}

function countByClassification(
  reasons: readonly ReplayReason[],
  classification: ReplayReasonClassification,
): number {
  return reasons.filter((reason) => reason.classification === classification).length
}

function statusFor(reasons: readonly ReplayReason[]): VerificationStatus {
  if (countByClassification(reasons, 'terminal') > 0) return 'fail'
  if (reasons.some((reason) => reason.area === 'efficiency')) return 'efficiency_failure'
  if (reasons.length > 0) return 'fail'
  return 'pass'
}

function summaryFor(
  status: VerificationStatus,
  reasons: readonly ReplayReason[],
  executed: number,
  fixtures: number,
): string {
  if (status === 'pass') {
    return `replay verified ${executed} process run(s) across ${fixtures} fixture(s) with deterministic output`
  }
  const first = reasons[0]
  const code = first?.code ?? 'unknown'
  if (status === 'efficiency_failure') {
    return `replay exhausted a process, wall, or output budget: ${code}`
  }
  return `replay failed verification: ${code}`
}

interface MutableReplayState {
  readonly reasons: ReplayReason[]
  readonly runs: ReplayRunRecord[]
  readonly seenReasons: Set<string>
  executed: number
  totalWallMs: number
}

function addReason(
  state: MutableReplayState,
  reason: ReplayReason,
  dedupeKey?: string,
): void {
  const key = dedupeKey ?? `${reason.code}:${reason.path ?? ''}`
  if (state.seenReasons.has(key)) return
  state.seenReasons.add(key)
  state.reasons.push(reason)
}

/**
 * Real replay verification: stages planner scripts, executes each fixture in a
 * sanitized subprocess, compares declared expected output, checks repeat
 * determinism, resolves references, scans for leakage, and enforces budgets.
 *
 * Failure classification is exposed in `details.repairableReasons` and
 * `details.terminalReasons`; `details.reasons` carries the full structured
 * record. Timeout, output-limit, process-limit, and total-wall overruns produce
 * `efficiency_failure`; unsafe paths, forbidden network/destructive scripts,
 * and process failures are terminal `fail` reasons.
 */
export class ReplayVerifier implements Verifier {
  private readonly runner: ReplayScriptRunner
  private readonly context: ReplayContext
  private readonly limits: ReplayLimits
  private readonly policy: ReplayPolicy

  constructor(options: ReplayVerifierOptions = {}) {
    this.runner = options.runner ?? new SubprocessScriptRunner()
    this.context = {
      ...(options.plan === undefined ? {} : { plan: options.plan }),
      ...(options.bundle === undefined ? {} : { bundle: options.bundle }),
      ...(options.preflight === undefined ? {} : { preflight: options.preflight }),
      ...(options.preflightReceipt === undefined
        ? {}
        : { preflightReceipt: options.preflightReceipt }),
    }
    this.limits = resolveLimits(options.limits)
    this.policy = resolvePolicy(options.policy)
  }

  /** Implement the `Verifier` boundary; context may be supplied per call. */
  async verify(operation: Operation, context?: ReplayCallContext): Promise<VerificationEvidence> {
    return await this.replay({
      operation,
      ...this.context,
      ...(context ?? {}),
    })
  }

  /** Run a complete replay with explicit or instance-level context. */
  async replay(request: ReplayRequest): Promise<VerificationEvidence> {
    const limits = resolveLimits({ ...this.limits, ...(request.limits ?? {}) })
    const policy = resolvePolicy({ ...this.policy, ...(request.policy ?? {}) })
    const runner = request.runner ?? this.runner
    const plan = request.plan ?? this.context.plan
    const bundle = request.bundle
      ?? request.plan?.bundle
      ?? this.context.bundle
      ?? plan?.bundle
    const preflight = request.preflight ?? this.context.preflight
    const preflightReceipt = request.preflightReceipt ?? this.context.preflightReceipt
    const state: MutableReplayState = {
      reasons: [],
      runs: [],
      seenReasons: new Set<string>(),
      executed: 0,
      totalWallMs: 0,
    }

    const contextReady = this.checkContext(request.operation, plan, bundle, state)
    if (contextReady && bundle !== undefined) {
      this.checkPaths(bundle, state)
      this.checkPlanResources(bundle, plan, state)
      this.checkReferences(bundle, state)
      this.checkLeakage(bundle, state)
      this.checkPreflight(preflight, preflightReceipt, state)
      this.checkScriptSafety(bundle, policy, state)
    }

    const hasTerminal = state.reasons.some((reason) => reason.classification === 'terminal')
    if (!contextReady || bundle === undefined || hasTerminal) {
      return this.evidence(request.operation, plan, preflight, state, limits, 0)
    }

    const scripts = Object.keys(bundle).filter(isScriptPath)
    if (scripts.length === 0) {
      if (request.operation.kind !== 'no_change') {
        addReason(state, replayReason({
          code: 'missing-script',
          message: 'bundle has no executable scripts to replay',
          area: 'structure',
          classification: 'repairable',
          path: 'scripts/',
        }))
      }
      return this.evidence(request.operation, plan, preflight, state, limits, 0)
    }

    const fixtures = this.parseFixtures(bundle, state)
    const fixturesByScript = new Map<string, ParsedFixture[]>()
    for (const fixture of fixtures) {
      if (!Object.prototype.hasOwnProperty.call(bundle, fixture.script)) {
        addReason(state, replayReason({
          code: 'orphan-fixture',
          message: `fixture ${fixture.path} targets missing script ${fixture.script}`,
          area: 'structure',
          classification: 'repairable',
          path: fixture.path,
        }), `orphan:${fixture.path}`)
        continue
      }
      const rows = fixturesByScript.get(fixture.script) ?? []
      rows.push(fixture)
      fixturesByScript.set(fixture.script, rows)
    }

    for (const scriptPath of scripts) {
      if (policy.requireFixturePerScript && !fixturesByScript.has(scriptPath)) {
        addReason(state, replayReason({
          code: 'missing-fixture',
          message: `script ${scriptPath} has no executable fixture`,
          area: 'structure',
          classification: 'repairable',
          path: scriptPath,
        }), `missing-fixture:${scriptPath}`)
      }
    }

    const plannedProcesses = [...fixturesByScript.values()]
      .reduce((total, rows) => total + rows.length * policy.determinismRuns, 0)
    if (plannedProcesses > limits.maximumProcesses) {
      addReason(state, replayReason({
        code: 'process-budget',
        message: `replay needs ${plannedProcesses} process run(s), above the ${limits.maximumProcesses} limit`,
        area: 'efficiency',
        classification: 'repairable',
        details: { plannedProcesses, maximumProcesses: limits.maximumProcesses },
      }))
      return this.evidence(request.operation, plan, preflight, state, limits, 0)
    }

    let stopAll = false
    for (const scriptPath of scripts) {
      const fixtureRows = fixturesByScript.get(scriptPath) ?? []
      if (fixtureRows.length === 0) continue
      const scriptContent = bundle[scriptPath]
      if (scriptContent === undefined) continue
      for (const fixture of fixtureRows) {
        if (stopAll) break
        let stopFixture = false
        for (let runIndex = 0; runIndex < policy.determinismRuns; runIndex += 1) {
          if (stopFixture || stopAll) break
          if (state.executed >= limits.maximumProcesses) {
            addReason(state, replayReason({
              code: 'process-budget',
              message: `replay reached the ${limits.maximumProcesses} process limit`,
              area: 'efficiency',
              classification: 'repairable',
              details: { maximumProcesses: limits.maximumProcesses },
            }))
            stopAll = true
            break
          }
          state.executed += 1
          let result: IsolatedScriptResult
          try {
            result = await runner.run({
              scriptPath,
              scriptContent,
              stdin: `${JSON.stringify(fixture.input)}\n`,
              timeoutMs: limits.scriptTimeoutMs,
            })
          } catch (error) {
            const code = error instanceof ReplayScriptError ? error.code : 'runner-error'
            const efficiency = code === 'input-limit' || code === 'invalid-limit'
            addReason(state, replayReason({
              code,
              message: error instanceof Error && error.message.length > 0
                ? error.message
                : 'script runner failed without a message',
              area: efficiency ? 'efficiency' : 'execution',
              classification: efficiency ? 'repairable' : 'terminal',
              path: scriptPath,
              details: { fixturePath: fixture.path, runIndex },
            }))
            stopFixture = true
            stopAll = true
            break
          }

          state.totalWallMs += result.wallMs
          const parsed = this.parseOutput(result)
          const outputLimited =
            result.outputLimitExceeded || result.stdoutTruncated || result.stderrTruncated
          const record: ReplayRunRecord = {
            scriptPath,
            fixturePath: fixture.path,
            runIndex,
            exitCode: result.exitCode,
            signal: result.signal,
            durationMs: result.wallMs,
            stdout: clipUtf8(result.stdout, limits.maximumStdoutBytes),
            stderr: clipUtf8(result.stderr, limits.maximumStderrBytes),
            stdoutHash: hashText(result.stdout),
            stderrHash: hashText(result.stderr),
            outputHash: hashText(result.stdout),
            stdoutBytes: result.stdoutBytes,
            stderrBytes: result.stderrBytes,
            timedOut: result.timedOut,
            outputLimitExceeded: outputLimited,
            stdoutTruncated: result.stdoutTruncated,
            stderrTruncated: result.stderrTruncated,
            parsed: parsed.ok,
            expectedMatched: parsed.ok && matchesExpected(parsed.value, fixture.expected),
          }
          state.runs.push(record)

          if (result.timedOut || result.wallMs > limits.scriptTimeoutMs) {
            addReason(state, replayReason({
              code: 'script-timeout',
              message: `${scriptPath} exceeded the ${limits.scriptTimeoutMs}ms wall limit`,
              area: 'efficiency',
              classification: 'repairable',
              path: scriptPath,
              details: { fixturePath: fixture.path, durationMs: result.wallMs, timeoutMs: limits.scriptTimeoutMs },
            }), `timeout:${scriptPath}:${fixture.path}`)
            stopFixture = true
            break
          }
          if (outputLimited) {
            addReason(state, replayReason({
              code: 'output-limit',
              message: `${scriptPath} exceeded the ${limits.maximumStdoutBytes}/${limits.maximumStderrBytes} byte output limit`,
              area: 'efficiency',
              classification: 'repairable',
              path: scriptPath,
              details: {
                fixturePath: fixture.path,
                stdoutBytes: result.stdoutBytes,
                stderrBytes: result.stderrBytes,
                maximumStdoutBytes: limits.maximumStdoutBytes,
                maximumStderrBytes: limits.maximumStderrBytes,
              },
            }), `output-limit:${scriptPath}:${fixture.path}`)
            stopFixture = true
            break
          }
          if (result.exitCode !== 0) {
            addReason(state, replayReason({
              code: 'script-failed',
              message: `${scriptPath} exited with code ${String(result.exitCode)}: ${result.stderr.trim().slice(0, 160)}`,
              area: 'execution',
              classification: 'terminal',
              path: scriptPath,
              details: { fixturePath: fixture.path, exitCode: result.exitCode, signal: result.signal },
            }), `script-failed:${scriptPath}:${fixture.path}`)
            stopFixture = true
            break
          }
          if (!parsed.ok) {
            addReason(state, replayReason({
              code: 'invalid-output',
              message: `${scriptPath} stdout is not a JSON object for ${fixture.path}`,
              area: 'output',
              classification: 'repairable',
              path: scriptPath,
              details: { fixturePath: fixture.path, stdout: record.stdout.slice(0, 160) },
            }), `invalid-output:${scriptPath}:${fixture.path}`)
            continue
          }
          if (!record.expectedMatched) {
            addReason(state, replayReason({
              code: 'output-mismatch',
              message: `${scriptPath} output does not match ${fixture.path}`,
              area: 'output',
              classification: 'repairable',
              path: scriptPath,
              details: { fixturePath: fixture.path, expectedKeys: Object.keys(fixture.expected) },
            }), `output-mismatch:${scriptPath}:${fixture.path}`)
          }
          if (state.totalWallMs > limits.maximumTotalWallMs) {
            addReason(state, replayReason({
              code: 'total-wall-budget',
              message: `replay used ${state.totalWallMs}ms, above the ${limits.maximumTotalWallMs}ms total wall limit`,
              area: 'efficiency',
              classification: 'repairable',
              details: { totalWallMs: state.totalWallMs, maximumTotalWallMs: limits.maximumTotalWallMs },
            }), 'total-wall-budget')
            stopFixture = true
            stopAll = true
            break
          }
        }

        if (!stopFixture && !stopAll) {
          this.checkDeterminism(state, scriptPath, fixture.path)
        }
      }
    }

    return this.evidence(request.operation, plan, preflight, state, limits, fixtures.length)
  }

  private checkContext(
    operation: Operation,
    plan: SkillPlan | undefined,
    bundle: SkillBundle | undefined,
    state: MutableReplayState,
  ): boolean {
    let ready = true
    if (bundle === undefined) {
      addReason(state, replayReason({
        code: 'missing-context',
        message: 'replay requires a plan or bundle to verify',
        area: 'context',
        classification: 'terminal',
      }))
      ready = false
    }
    if (plan === undefined && bundle === undefined) {
      return false
    }
    if (plan !== undefined) {
      if (plan.operationId !== operation.id) {
        addReason(state, replayReason({
          code: 'operation-mismatch',
          message: `plan belongs to operation ${String(plan.operationId)}, not ${String(operation.id)}`,
          area: 'context',
          classification: 'terminal',
          details: { planOperationId: String(plan.operationId), operationId: String(operation.id) },
        }))
        ready = false
      }
      if (plan.skillId !== operation.skillId) {
        addReason(state, replayReason({
          code: 'skill-mismatch',
          message: `plan belongs to skill ${String(plan.skillId)}, not ${String(operation.skillId)}`,
          area: 'context',
          classification: 'terminal',
          details: { planSkillId: String(plan.skillId), skillId: String(operation.skillId) },
        }))
        ready = false
      }
    }
    return ready
  }

  private checkPaths(bundle: SkillBundle, state: MutableReplayState): void {
    for (const path of Object.keys(bundle)) {
      for (const issue of validateResourcePath(path)) {
        addReason(state, replayReason({
          code: issue.code,
          message: issue.message,
          area: 'safety',
          classification: 'terminal',
          path,
        }), `path:${path}:${issue.code}`)
      }
    }
  }

  private checkPlanResources(
    bundle: SkillBundle,
    plan: SkillPlan | undefined,
    state: MutableReplayState,
  ): void {
    if (plan === undefined) return
    const planned = new Set<string>([
      plan.skill.path,
      ...plan.resources.map((row) => row.resource.path),
    ])
    for (const path of planned) {
      if (!Object.prototype.hasOwnProperty.call(bundle, path)) {
        addReason(state, replayReason({
          code: 'missing-planned-resource',
          message: `planned resource ${path} is absent from the replay bundle`,
          area: 'structure',
          classification: 'repairable',
          path,
        }), `planned:${path}`)
      }
    }
  }

  private checkReferences(bundle: SkillBundle, state: MutableReplayState): void {
    for (const [path, content] of Object.entries(bundle)) {
      for (const reference of extractReferences(content)) {
        if (reference === path) continue
        if (validateResourcePath(reference).length > 0) {
          addReason(state, replayReason({
            code: 'unsafe-reference',
            message: `${path} references unsafe bundle path ${reference}`,
            area: 'reference',
            classification: 'repairable',
            path,
            details: { reference },
          }), `unsafe-reference:${path}:${reference}`)
          continue
        }
        if (!Object.prototype.hasOwnProperty.call(bundle, reference)) {
          addReason(state, replayReason({
            code: 'unresolved-reference',
            message: `${path} references ${reference}, which is not present in the bundle`,
            area: 'reference',
            classification: 'repairable',
            path,
            details: { reference },
          }), `unresolved-reference:${path}:${reference}`)
        }
      }
    }
  }

  private checkLeakage(bundle: SkillBundle, state: MutableReplayState): void {
    for (const [path, content] of Object.entries(bundle)) {
      for (const leak of scanContentForLeakage(path, content)) {
        addReason(state, replayReason({
          code: leak.code,
          message: leak.message,
          area: 'leakage',
          classification: 'repairable',
          path,
        }), `leak:${path}:${leak.code}`)
      }
    }
  }

  private checkPreflight(
    preflight: PreflightReport | undefined,
    receipt: ReplayPreflightReceipt | undefined,
    state: MutableReplayState,
  ): void {
    if (preflight !== undefined) {
      const hash = hashText(JSON.stringify(preflight))
      if (receipt?.reportHash !== undefined && receipt.reportHash !== hash) {
        addReason(state, replayReason({
          code: 'preflight-receipt-mismatch',
          message: 'preflight receipt does not match the supplied preflight report',
          area: 'context',
          classification: 'terminal',
          details: { expectedHash: receipt.reportHash, actualHash: hash },
        }), 'preflight-receipt-mismatch')
      }
      if (preflight.verdict === 'reject') {
        addReason(state, replayReason({
          code: 'preflight-rejected',
          message: 'preflight rejected the bundle; replay cannot accept it',
          area: 'structure',
          classification: 'repairable',
          details: { codes: preflight.rejectReasons.map((reason) => reason.code) },
        }), 'preflight-rejected')
      }
      const leakageCheck = preflight.checks.find((check) => check.name === 'benchmark-leakage')
      if (leakageCheck?.status === 'fail') {
        addReason(state, replayReason({
          code: 'preflight-leakage',
          message: 'preflight detected benchmark leakage',
          area: 'leakage',
          classification: 'repairable',
          details: { codes: leakageCheck.reasons.map((reason) => reason.code) },
        }), 'preflight-leakage')
      }
    }
    if (receipt !== undefined && receipt.verdict === 'reject') {
      addReason(state, replayReason({
        code: 'preflight-receipt-rejected',
        message: 'preflight receipt reports rejection',
        area: 'structure',
        classification: 'repairable',
        details: { codes: receipt.rejectCodes ?? [] },
      }), 'preflight-receipt-rejected')
    }
  }

  private checkScriptSafety(
    bundle: SkillBundle,
    policy: ReplayPolicy,
    state: MutableReplayState,
  ): void {
    for (const [path, content] of Object.entries(bundle)) {
      if (!isScriptPath(path)) continue
      const lower = path.toLowerCase()
      const supported = policy.supportedScriptExtensions.some((extension) => lower.endsWith(extension))
      if (!supported) {
        addReason(state, replayReason({
          code: 'unsupported-script-language',
          message: `${path} cannot be executed by the configured replay interpreter`,
          area: 'execution',
          classification: 'terminal',
          path,
        }), `language:${path}`)
      }
      if (policy.denyNetwork && matchesAnyPattern(content, NETWORK_PATTERNS)) {
        addReason(state, replayReason({
          code: 'network-not-allowed',
          message: `${path} contains a network client; replay refuses to execute it`,
          area: 'safety',
          classification: 'terminal',
          path,
        }), `network:${path}`)
      }
      if (policy.denyDestructiveCommands && matchesAnyPattern(content, DESTRUCTIVE_PATTERNS)) {
        addReason(state, replayReason({
          code: 'destructive-command-not-allowed',
          message: `${path} contains a destructive process or filesystem command; replay refuses to execute it`,
          area: 'safety',
          classification: 'terminal',
          path,
        }), `destructive:${path}`)
      }
    }
  }

  private parseFixtures(bundle: SkillBundle, state: MutableReplayState): readonly ParsedFixture[] {
    const fixtures: ParsedFixture[] = []
    for (const [path, content] of Object.entries(bundle)) {
      if (!FIXTURE_PATH_PATTERN.test(path)) continue
      const parsed = parseFixture(path, content)
      if (parsed.ok) {
        fixtures.push(parsed.fixture)
      } else {
        addReason(state, parsed.reason, `fixture:${path}:${parsed.reason.code}`)
      }
    }
    return fixtures
  }

  private parseOutput(
    result: IsolatedScriptResult,
  ): { readonly ok: true; readonly value: unknown } | { readonly ok: false } {
    try {
      const value: unknown = JSON.parse(result.stdout)
      if (!isRecord(value)) return { ok: false }
      return { ok: true, value }
    } catch {
      return { ok: false }
    }
  }

  private checkDeterminism(
    state: MutableReplayState,
    scriptPath: string,
    fixturePath: string,
  ): void {
    const fixtureRuns = state.runs.filter(
      (run) => run.scriptPath === scriptPath && run.fixturePath === fixturePath,
    )
    if (fixtureRuns.length < 2) return
    const first = fixtureRuns[0]
    const second = fixtureRuns[1]
    if (first === undefined || second === undefined) return
    if (first.timedOut || second.timedOut) return
    if (first.outputLimitExceeded || second.outputLimitExceeded) return
    if (first.exitCode !== 0 || second.exitCode !== 0) return
    if (first.outputHash === second.outputHash) return
    addReason(state, replayReason({
      code: 'nondeterministic-output',
      message: `${scriptPath} produced different stdout hashes for ${fixturePath}`,
      area: 'determinism',
      classification: 'repairable',
      path: scriptPath,
      details: {
        fixturePath,
        firstHash: first.outputHash,
        secondHash: second.outputHash,
      },
    }), `nondeterministic:${scriptPath}:${fixturePath}`)
  }

  private evidence(
    operation: Operation,
    plan: SkillPlan | undefined,
    preflight: PreflightReport | undefined,
    state: MutableReplayState,
    limits: ReplayLimits,
    fixtureCount: number,
  ): VerificationEvidence {
    const status = statusFor(state.reasons)
    const details: Record<string, unknown> = {
      operationId: String(operation.id),
      operationKind: operation.kind,
      skillId: String(operation.skillId),
      ...(plan === undefined
        ? {}
        : {
            family: plan.family,
            planMode: plan.mode,
            plannedResources: plan.resources.length,
          }),
      reasons: state.reasons,
      repairableReasons: state.reasons
        .filter((reason) => reason.classification === 'repairable')
        .map((reason) => reason.code),
      terminalReasons: state.reasons
        .filter((reason) => reason.classification === 'terminal')
        .map((reason) => reason.code),
      runs: state.runs,
      outputHashes: state.runs.map((run) => ({
        scriptPath: run.scriptPath,
        fixturePath: run.fixturePath,
        runIndex: run.runIndex,
        outputHash: run.outputHash,
      })),
      executedProcesses: state.executed,
      totalWallMs: state.totalWallMs,
      fixtures: fixtureCount,
      checks: {
        pathSafety: state.reasons.some((reason) => reason.area === 'safety') ? 'fail' : 'pass',
        references: state.reasons.some((reason) => reason.area === 'reference') ? 'fail' : 'pass',
        leakage: state.reasons.some((reason) => reason.area === 'leakage') ? 'fail' : 'pass',
        execution: state.reasons.some((reason) => reason.area === 'execution') ? 'fail' : 'pass',
        expectedOutputs: state.reasons.some((reason) => reason.area === 'output') ? 'fail' : 'pass',
        determinism: state.reasons.some((reason) => reason.area === 'determinism') ? 'fail' : 'pass',
        efficiency: state.reasons.some((reason) => reason.area === 'efficiency') ? 'fail' : 'pass',
      },
      limits,
      sandbox: {
        stagedCopy: true,
        freshTemporaryDirectory: true,
        isolatedMode: true,
        shell: false,
        osNetworkIsolation: false,
        networkPolicyNote:
          'Advisory only: scripts run without an OS network namespace or firewall. Use a container for a hard guarantee.',
      },
      ...(preflight === undefined
        ? {}
        : {
            preflight: {
              verdict: preflight.verdict,
              reportHash: hashText(JSON.stringify(preflight)),
              rejectCodes: preflight.rejectReasons.map((reason) => reason.code),
              repairCodes: preflight.repairReasons.map((reason) => reason.code),
            },
          }),
    }
    return {
      status,
      summary: summaryFor(status, state.reasons, state.executed, fixtureCount),
      details,
    }
  }
}
