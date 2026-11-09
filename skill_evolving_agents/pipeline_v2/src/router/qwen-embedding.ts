import { createHash, randomUUID } from 'node:crypto'
import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { MessageChannel, receiveMessageOnPort, Worker } from 'node:worker_threads'
import type { MessagePort } from 'node:worker_threads'

import { PipelineError } from '../contracts/errors.ts'
import type { StructuredIssue } from '../contracts/errors.ts'
import { isFiniteNumber, isNonEmptyString, isRecord, issue } from '../contracts/validation.ts'
import { DeterministicEmbeddingProvider } from './two-stage-router.ts'
import type { EmbeddingProvider } from './two-stage-router.ts'

/**
 * A real semantic embedding provider for a locally hosted, OpenAI-compatible
 * Qwen embedding server (vLLM, TEI, llama.cpp, etc.).
 *
 * The router's `EmbeddingProvider` seam is synchronous, so this module offers
 * two paths:
 *
 * - `embed()` / `embedWithReport()` are synchronous. They serve cache hits
 *   directly and, on a miss, make a bounded HTTP request through a dedicated
 *   worker thread while the caller blocks with `Atomics.wait`. This keeps the
 *   existing router interface usable without changing `two-stage-router.ts`.
 * - `embedAsync()` / `embedAsyncWithReport()` are fully asynchronous and never
 *   block the event loop. Prefer them for pipelines that can await.
 *
 * Blocking HTTP is only safe when the embedding server runs in another process
 * or thread. If the server shares this process's event loop, `embed()` will
 * time out and degrade. Callers can disable blocking with
 * `syncTransport: 'disabled'`, in which case `embed()` uses the deterministic
 * fallback and records the degradation reason.
 *
 * When the model is unavailable, times out, or returns a malformed response,
 * the whole batch is embedded by a deterministic lexical/hash fallback. The
 * fallback is never cached under a Qwen cache key and vectors from different
 * providers are never mixed in one batch. The router's own `embeddingDegraded`
 * flag only observes thrown provider failures, so consumers that need to know
 * about vector provenance should read `lastReport().degraded` as well.
 *
 * Disk-cache I/O is synchronous (small, sharded JSON files), so it is intended
 * for local deployments. Model requests themselves are bounded by `timeoutMs`
 * per batch; a call with many batches can take up to `batches * timeoutMs`.
 */

export const DEFAULT_QWEN_BASE_URL = 'http://127.0.0.1:8000/v1'
export const DEFAULT_QWEN_MODEL = 'Qwen3-Embedding-0.6B'
export const DEFAULT_QWEN_REVISION = 'main'
export const DEFAULT_QWEN_BATCH_SIZE = 16
export const DEFAULT_QWEN_TIMEOUT_MS = 5_000
export const DEFAULT_QWEN_EMBEDDINGS_PATH = '/embeddings'
export const DEFAULT_QWEN_HEALTH_PATH = '/health'
export const DEFAULT_QWEN_CACHE_ENTRIES = 512

/** Identity recorded when deterministic fallback vectors are returned. */
export const FALLBACK_EMBEDDING_MODEL = 'deterministic-lexical-hash'
export const FALLBACK_EMBEDDING_REVISION = 'v1'

const CACHE_FILE_VERSION = 1
const MAX_EMBEDDING_DIMENSIONS = 65_536
const SYNC_HTTP_POLL_MS = 2
const SYNC_HTTP_GRACE_MS = 500
const BODY_PREVIEW_CHARS = 500

/** Selected execution mode after `auto` resolution. */
export type EmbeddingRuntime = 'http' | 'in-process'
/** How the synchronous facade reaches the HTTP server. */
export type EmbeddingSyncTransport = 'worker' | 'disabled'
/** Which producer supplied the vectors returned by one call. */
export type EmbeddingSource = 'qwen' | 'in-process' | 'fallback'

/** Why one call returned deterministic fallback vectors instead of model vectors. */
export type EmbeddingDegradationReason =
  | 'http-unavailable'
  | 'http-timeout'
  | 'malformed-response'
  | 'sync-transport-disabled'
  | 'in-process-unavailable'
  | 'in-process-error'

/**
 * Optional content-addressed disk cache. Files are sharded by the first two
 * hex characters of the SHA-256 cache key.
 */
export interface QwenEmbeddingCacheOptions {
  /** Maximum in-memory vectors; defaults to {@link DEFAULT_QWEN_CACHE_ENTRIES}. */
  readonly maxEntries?: number
  /** Enables a durable on-disk cache under this directory. */
  readonly directory?: string
}

/** Construction options for {@link QwenEmbeddingProvider}. */
export interface QwenEmbeddingOptions {
  /** OpenAI-compatible base URL, for example `http://127.0.0.1:8000/v1`. */
  readonly baseUrl?: string
  /** Exact model identifier sent to the server. */
  readonly model?: string
  /** Model revision/commit. Sent as `x-embedding-revision` and used in cache keys. */
  readonly revision?: string
  /** Path appended to `baseUrl`; defaults to `/embeddings`. */
  readonly embeddingsPath?: string
  /** Health probe path appended to `baseUrl`; defaults to `/health`. */
  readonly healthPath?: string
  /** Optional bearer token for the local server. */
  readonly apiKey?: string
  /** Maximum inputs per HTTP request; defaults to 16. */
  readonly batchSize?: number
  /** Per-request timeout in milliseconds; defaults to 5000. */
  readonly timeoutMs?: number
  /** Optional expected vector width. Mismatches are rejected as malformed. */
  readonly expectedDimensions?: number
  /** L2-normalize vectors; defaults to true. */
  readonly normalize?: boolean
  /**
   * `http` prefers HTTP. `in-process` requires an explicit `inProcess`
   * adapter backed by an installed local runtime. `auto` (default) selects
   * in-process only when `inProcess` is supplied and no explicit `baseUrl` is
   * given; otherwise it uses HTTP.
   */
  readonly runtime?: 'http' | 'in-process' | 'auto'
  /** How `embed()` reaches HTTP; defaults to `worker`. */
  readonly syncTransport?: EmbeddingSyncTransport
  /**
   * In-memory cache is on by default; pass `false` to disable all caching.
   * Disk files are unbounded; caller manages the directory lifecycle.
   */
  readonly cache?: QwenEmbeddingCacheOptions | false
  /** Deterministic fallback adapter; defaults to the router's hash provider. */
  readonly fallback?: EmbeddingProvider
  /** In-process embedding adapter. Must be backed by an installed runtime. */
  readonly inProcess?: EmbeddingProvider
  /** Injectable clock used only for reported latency, never for timeouts. */
  readonly clock?: () => number
}

/** Per-call observability record. */
export interface EmbeddingCallReport {
  readonly source: EmbeddingSource
  /** Producer identity; the fallback constant when `source` is `fallback`. */
  readonly model: string
  readonly revision: string
  /** Configured Qwen identity, retained even when the call degraded. */
  readonly requestedModel: string
  readonly requestedRevision: string
  readonly degraded: boolean
  readonly degradationReason: EmbeddingDegradationReason | null
  readonly error: string | null
  /**
   * Unique inputs with an in-memory or disk entry found during planning.
   * On a degraded call these entries are ignored because the whole batch is
   * produced by the fallback; `source` disambiguates that case.
   */
  readonly cacheHits: number
  /** Unique inputs with no cache entry that required the model or fallback. */
  readonly cacheMisses: number
  /** Subset of `cacheHits` loaded from disk. */
  readonly diskHits: number
  readonly batches: number
  readonly latencyMs: number
  readonly dimensions: number
}

/** Cumulative provider counters. */
export interface EmbeddingProviderStats {
  readonly calls: number
  readonly batches: number
  readonly cacheHits: number
  readonly cacheMisses: number
  readonly diskHits: number
  readonly degradedCalls: number
  readonly failures: number
  readonly totalLatencyMs: number
  readonly lastLatencyMs: number
  readonly cacheErrors: number
  readonly model: string
  readonly revision: string
  readonly runtime: EmbeddingRuntime
  readonly degraded: boolean
}

/** Result of a health probe. A failed probe resolves with `ok: false`. */
export interface EmbeddingHealth {
  readonly ok: boolean
  readonly model: string
  readonly revision: string
  readonly degraded: boolean
  readonly latencyMs: number
  readonly status: number | null
  readonly error: string | null
}

/** What local in-process embedding runtimes are installed in this process. */
export interface InProcessEmbeddingProbe {
  readonly available: boolean
  readonly modules: readonly string[]
  readonly checked: readonly string[]
  readonly reason: string
}

/** Provider capabilities, primarily for diagnostics and startup logging. */
export interface QwenEmbeddingCapabilities {
  readonly runtime: EmbeddingRuntime
  readonly syncHttp: boolean
  readonly asyncHttp: boolean
  readonly diskCache: boolean
  readonly inProcess: InProcessEmbeddingProbe
}

/** Vectors plus their per-call provenance report. */
export interface EmbeddingBatchResult {
  readonly vectors: readonly (readonly number[])[]
  readonly report: EmbeddingCallReport
}

/** Structured provider failure with a stable code. */
export class QwenEmbeddingError extends PipelineError {
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

const IN_PROCESS_MODULES = [
  '@huggingface/transformers',
  '@xenova/transformers',
  'onnxruntime-node',
  'node-llama-cpp',
] as const

const requireFromHere = createRequire(import.meta.url)

/**
 * Probe for an installed local embedding runtime. This package does not bundle
 * a model runtime; when nothing is installed, in-process mode is reported as
 * unavailable and the provider falls back instead of fabricating vectors.
 */
export function probeInProcessEmbeddingRuntime(): InProcessEmbeddingProbe {
  const modules: string[] = []
  for (const moduleName of IN_PROCESS_MODULES) {
    try {
      requireFromHere.resolve(moduleName)
      modules.push(moduleName)
    } catch {
      // Not installed; keep probing the other candidate runtimes.
    }
  }
  return {
    available: modules.length > 0,
    modules,
    checked: IN_PROCESS_MODULES,
    reason: modules.length === 0
      ? 'no local embedding runtime is installed'
      : `found local runtime ${modules.join(', ')}; an inProcess adapter must be supplied to use it`,
  }
}

/**
 * Content-addressed embedding cache key. It covers every input that changes a
 * vector: runtime, model, revision, normalization, and the exact text.
 */
export function embeddingCacheKey(
  runtime: EmbeddingRuntime,
  model: string,
  revision: string,
  normalize: boolean,
  text: string,
): string {
  return createHash('sha256')
    .update(JSON.stringify([CACHE_FILE_VERSION, runtime, model, revision, normalize, text]))
    .digest('hex')
}

interface ResolvedQwenEmbeddingConfig {
  readonly baseUrl: string
  readonly embeddingsUrl: string
  readonly healthUrl: string
  readonly model: string
  readonly revision: string
  readonly apiKey: string | null
  readonly batchSize: number
  readonly timeoutMs: number
  readonly expectedDimensions: number | null
  readonly normalize: boolean
  readonly runtime: EmbeddingRuntime
  readonly syncTransport: EmbeddingSyncTransport
  readonly cacheEnabled: boolean
  readonly cacheMaxEntries: number
  readonly cacheDirectory: string | null
}

interface MutableStats {
  calls: number
  batches: number
  cacheHits: number
  cacheMisses: number
  diskHits: number
  degradedCalls: number
  failures: number
  totalLatencyMs: number
  lastLatencyMs: number
  cacheErrors: number
  lastReport: EmbeddingCallReport | null
}

interface CacheMiss {
  readonly text: string
  readonly key: string
}

interface CachePlan {
  readonly keyByText: ReadonlyMap<string, string>
  readonly cached: ReadonlyMap<string, readonly number[]>
  readonly misses: readonly CacheMiss[]
  readonly cacheHits: number
  readonly diskHits: number
  readonly cacheMisses: number
  /** Width anchored by the first usable cache hit, if any. */
  readonly dimensions: number | null
}

interface HttpResponse {
  readonly status: number
  readonly body: string
}

interface SyncHttpRequest {
  readonly url: string
  readonly method: 'GET' | 'POST'
  readonly headers: Readonly<Record<string, string>>
  readonly body: string | null
  readonly timeoutMs: number
}

interface SyncHttpMessage {
  readonly id: number
  readonly ok: boolean
  readonly status: number
  readonly body: string
  readonly error: string | null
  readonly timedOut: boolean
}

function invalidConfig(message: string, path: string): never {
  throw new QwenEmbeddingError(
    'invalid-embedding-config',
    'qwen embedding configuration is invalid',
    [issue(path, 'invalid-embedding-config', message)],
  )
}

function invalidInput(path: string, message: string): never {
  throw new QwenEmbeddingError(
    'invalid-embedding-input',
    'embedding input is invalid',
    [issue(path, 'invalid-embedding-input', message)],
  )
}

function timeoutError(timeoutMs: number): QwenEmbeddingError {
  return new QwenEmbeddingError(
    'embedding-timeout',
    `embedding request exceeded ${timeoutMs}ms`,
    [],
    { timeoutMs },
  )
}

function httpStatusError(response: HttpResponse): QwenEmbeddingError {
  return new QwenEmbeddingError(
    'embedding-http',
    `embedding endpoint returned HTTP ${response.status}`,
    [],
    { status: response.status, bodyPreview: response.body.slice(0, BODY_PREVIEW_CHARS) },
  )
}

function malformedError(message: string, path = 'response'): QwenEmbeddingError {
  return new QwenEmbeddingError(
    'embedding-malformed',
    message,
    [issue(path, 'malformed-embedding-response', message)],
  )
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function errorCode(error: unknown): string | null {
  if (error instanceof Error && 'code' in error) {
    const code: unknown = error.code
    return typeof code === 'string' ? code : null
  }
  return null
}

function degradationReason(error: unknown): EmbeddingDegradationReason {
  if (error instanceof QwenEmbeddingError) {
    if (error.code === 'embedding-timeout') return 'http-timeout'
    if (error.code === 'embedding-malformed') return 'malformed-response'
    if (error.code === 'embedding-transport-disabled') return 'sync-transport-disabled'
  }
  return 'http-unavailable'
}

function normalizeVector(values: readonly number[]): readonly number[] {
  let squaredNorm = 0
  for (const value of values) squaredNorm += value * value
  if (!(squaredNorm > 0)) throw malformedError('embedding vector must not be all zeros')
  const norm = Math.sqrt(squaredNorm)
  return values.map(value => value / norm)
}

function positiveInteger(
  value: number,
  fallback: number,
  path: string,
  label: string,
  issues: StructuredIssue[],
): number {
  if (!Number.isInteger(value) || value < 1) {
    issues.push(issue(path, 'invalid-embedding-config', `${label} must be a positive integer`))
    return fallback
  }
  return value
}

function positiveNumber(
  value: number,
  fallback: number,
  path: string,
  label: string,
  issues: StructuredIssue[],
): number {
  if (!isFiniteNumber(value) || value <= 0) {
    issues.push(issue(path, 'invalid-embedding-config', `${label} must be a positive finite number`))
    return fallback
  }
  return value
}

function resolvePath(
  value: string,
  fallback: string,
  path: string,
  label: string,
  issues: StructuredIssue[],
): string {
  if (!isNonEmptyString(value) || !value.startsWith('/')) {
    issues.push(issue(path, 'invalid-embedding-config', `${label} must be an absolute path starting with /`))
    return fallback
  }
  return value
}

function resolveOptions(options: QwenEmbeddingOptions): ResolvedQwenEmbeddingConfig {
  const issues: StructuredIssue[] = []

  const rawBaseUrl = options.baseUrl ?? DEFAULT_QWEN_BASE_URL
  let baseUrl: string | null = null
  try {
    const parsed = new URL(rawBaseUrl)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      issues.push(issue('baseUrl', 'invalid-embedding-config', 'baseUrl must use http or https'))
    } else if (parsed.search.length > 0 || parsed.hash.length > 0) {
      issues.push(issue('baseUrl', 'invalid-embedding-config', 'baseUrl must not contain a query or fragment'))
    } else {
      baseUrl = parsed.toString().replace(/\/+$/, '')
    }
  } catch {
    issues.push(issue('baseUrl', 'invalid-embedding-config', 'baseUrl must be an absolute URL'))
  }

  const model = options.model ?? DEFAULT_QWEN_MODEL
  if (!isNonEmptyString(model)) {
    issues.push(issue('model', 'invalid-embedding-config', 'model must be a non-empty string'))
  }

  const revision = options.revision ?? DEFAULT_QWEN_REVISION
  if (!isNonEmptyString(revision)) {
    issues.push(issue('revision', 'invalid-embedding-config', 'revision must be a non-empty string'))
  }

  const embeddingsPath = resolvePath(
    options.embeddingsPath ?? DEFAULT_QWEN_EMBEDDINGS_PATH,
    DEFAULT_QWEN_EMBEDDINGS_PATH,
    'embeddingsPath',
    'embeddingsPath',
    issues,
  )
  const healthPath = resolvePath(
    options.healthPath ?? DEFAULT_QWEN_HEALTH_PATH,
    DEFAULT_QWEN_HEALTH_PATH,
    'healthPath',
    'healthPath',
    issues,
  )

  let apiKey: string | null = null
  if (options.apiKey !== undefined) {
    if (typeof options.apiKey !== 'string') {
      issues.push(issue('apiKey', 'invalid-embedding-config', 'apiKey must be a string'))
    } else if (options.apiKey.trim().length > 0) {
      apiKey = options.apiKey.trim()
    }
  }

  const batchSize = positiveInteger(
    options.batchSize ?? DEFAULT_QWEN_BATCH_SIZE,
    DEFAULT_QWEN_BATCH_SIZE,
    'batchSize',
    'batchSize',
    issues,
  )
  const timeoutMs = positiveNumber(
    options.timeoutMs ?? DEFAULT_QWEN_TIMEOUT_MS,
    DEFAULT_QWEN_TIMEOUT_MS,
    'timeoutMs',
    'timeoutMs',
    issues,
  )

  let expectedDimensions: number | null = null
  if (options.expectedDimensions !== undefined) {
    if (!Number.isInteger(options.expectedDimensions) || options.expectedDimensions < 1) {
      issues.push(issue('expectedDimensions', 'invalid-embedding-config', 'expectedDimensions must be a positive integer'))
    } else {
      expectedDimensions = options.expectedDimensions
    }
  }

  const normalize = options.normalize ?? true
  if (typeof normalize !== 'boolean') {
    issues.push(issue('normalize', 'invalid-embedding-config', 'normalize must be a boolean'))
  }

  const requestedRuntime = options.runtime ?? 'auto'
  if (requestedRuntime !== 'auto' && requestedRuntime !== 'http' && requestedRuntime !== 'in-process') {
    issues.push(issue('runtime', 'invalid-embedding-config', 'runtime must be auto, http, or in-process'))
  }
  const runtime: EmbeddingRuntime = requestedRuntime === 'in-process'
    || (requestedRuntime === 'auto' && options.inProcess !== undefined && options.baseUrl === undefined)
    ? 'in-process'
    : 'http'

  const syncTransport = options.syncTransport ?? 'worker'
  if (syncTransport !== 'worker' && syncTransport !== 'disabled') {
    issues.push(issue('syncTransport', 'invalid-embedding-config', 'syncTransport must be worker or disabled'))
  }

  let cacheEnabled = true
  let cacheMaxEntries = DEFAULT_QWEN_CACHE_ENTRIES
  let cacheDirectory: string | null = null
  if (options.cache === false) {
    cacheEnabled = false
    cacheMaxEntries = 0
  } else if (options.cache !== undefined) {
    const cache = options.cache
    if (typeof cache !== 'object' || cache === null) {
      issues.push(issue('cache', 'invalid-embedding-config', 'cache must be an object or false'))
    } else {
      cacheMaxEntries = positiveInteger(
        cache.maxEntries ?? DEFAULT_QWEN_CACHE_ENTRIES,
        DEFAULT_QWEN_CACHE_ENTRIES,
        'cache.maxEntries',
        'cache.maxEntries',
        issues,
      )
      if (cache.directory !== undefined) {
        if (!isNonEmptyString(cache.directory)) {
          issues.push(issue('cache.directory', 'invalid-embedding-config', 'cache.directory must be a non-empty string'))
        } else {
          cacheDirectory = cache.directory
        }
      }
    }
  }

  if (issues.length > 0) {
    throw new QwenEmbeddingError('invalid-embedding-config', 'qwen embedding configuration is invalid', issues)
  }
  if (baseUrl === null) invalidConfig('baseUrl must be an absolute URL', 'baseUrl')

  return {
    baseUrl,
    embeddingsUrl: `${baseUrl}${embeddingsPath}`,
    healthUrl: `${baseUrl}${healthPath}`,
    model,
    revision,
    apiKey,
    batchSize,
    timeoutMs,
    expectedDimensions,
    normalize,
    runtime,
    syncTransport,
    cacheEnabled,
    cacheMaxEntries,
    cacheDirectory,
  }
}

function chunk<T>(items: readonly T[], size: number): readonly (readonly T[])[] {
  const batches: (readonly T[])[] = []
  for (let index = 0; index < items.length; index += size) {
    batches.push(items.slice(index, index + size))
  }
  return batches
}

function parseEmbeddingPayload(body: string, count: number, normalize: boolean, expectedDimensions: number | null): readonly (readonly number[])[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(body)
  } catch {
    throw malformedError('embedding response is not valid JSON')
  }
  if (!isRecord(parsed)) throw malformedError('embedding response must be a JSON object')
  const data = parsed.data
  if (!Array.isArray(data)) throw malformedError('embedding response must contain a data array')
  if (data.length !== count) {
    throw malformedError(`embedding response returned ${data.length} vectors for ${count} inputs`, 'response.data')
  }

  const vectors: (readonly number[])[] = new Array<readonly number[]>(count)
  let dimensions = expectedDimensions ?? -1

  for (let position = 0; position < data.length; position += 1) {
    const item: unknown = data[position]
    if (!isRecord(item)) throw malformedError('embedding item must be an object', `response.data[${position}]`)

    let index = position
    const rawIndex = item.index
    if (rawIndex !== undefined) {
      if (typeof rawIndex !== 'number' || !Number.isInteger(rawIndex) || rawIndex < 0 || rawIndex >= count) {
        throw malformedError('embedding item index is out of range', `response.data[${position}].index`)
      }
      index = rawIndex
    }
    if (vectors[index] !== undefined) {
      throw malformedError(`embedding response contains duplicate index ${index}`, 'response.data')
    }

    const embedding = item.embedding
    if (!Array.isArray(embedding) || embedding.length === 0) {
      throw malformedError('embedding item must contain a non-empty vector', `response.data[${position}].embedding`)
    }
    if (embedding.length > MAX_EMBEDDING_DIMENSIONS) {
      throw malformedError(`embedding vector exceeds ${MAX_EMBEDDING_DIMENSIONS} dimensions`, `response.data[${position}].embedding`)
    }
    if (dimensions < 0) dimensions = embedding.length
    else if (embedding.length !== dimensions) {
      throw malformedError(
        `embedding vector width ${embedding.length} does not match ${dimensions}`,
        `response.data[${position}].embedding`,
      )
    }

    const values: number[] = []
    for (const value of embedding) {
      if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw malformedError('embedding vector contains a non-finite value', `response.data[${position}].embedding`)
      }
      values.push(value)
    }
    vectors[index] = normalize ? normalizeVector(values) : validateFiniteVector(values)
  }

  for (let index = 0; index < count; index += 1) {
    if (vectors[index] === undefined) throw malformedError(`embedding response is missing index ${index}`, 'response.data')
  }
  return vectors
}

function validateFiniteVector(values: readonly number[]): readonly number[] {
  let squaredNorm = 0
  for (const value of values) squaredNorm += value * value
  if (!(squaredNorm > 0)) throw malformedError('embedding vector must not be all zeros')
  return values
}

function parseSyncHttpMessage(value: unknown): SyncHttpMessage {
  if (!isRecord(value)) throw new QwenEmbeddingError('embedding-unavailable', 'synchronous embedding worker returned an invalid message')
  const id = value.id
  const ok = value.ok
  const status = value.status
  const body = value.body
  const error = value.error
  const timedOut = value.timedOut
  if (typeof id !== 'number' || !Number.isInteger(id) || id < 0) {
    throw new QwenEmbeddingError('embedding-unavailable', 'synchronous embedding worker returned an invalid request id')
  }
  if (typeof ok !== 'boolean') {
    throw new QwenEmbeddingError('embedding-unavailable', 'synchronous embedding worker returned an invalid status flag')
  }
  if (typeof status !== 'number' || !Number.isInteger(status) || status < 0) {
    throw new QwenEmbeddingError('embedding-unavailable', 'synchronous embedding worker returned an invalid HTTP status')
  }
  if (typeof body !== 'string') {
    throw new QwenEmbeddingError('embedding-unavailable', 'synchronous embedding worker returned an invalid body')
  }
  if (error !== null && typeof error !== 'string') {
    throw new QwenEmbeddingError('embedding-unavailable', 'synchronous embedding worker returned an invalid error')
  }
  if (typeof timedOut !== 'boolean') {
    throw new QwenEmbeddingError('embedding-unavailable', 'synchronous embedding worker returned an invalid timeout flag')
  }
  return { id, ok, status, body, error, timedOut }
}

/**
 * Worker source for the blocking bridge. It uses the worker's own event loop
 * for `fetch`, so the main thread can block in `Atomics.wait` without starving
 * the request. The source is intentionally dependency-free and uses CommonJS,
 * which is how `Worker` evaluates `eval: true` scripts.
 */
const SYNC_HTTP_WORKER_SOURCE = `
const { workerData } = require('node:worker_threads')
const port = workerData.port
port.on('message', (request) => {
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, request.timeoutMs)
  const init = {
    method: request.method,
    headers: request.headers,
    signal: controller.signal,
  }
  if (request.body !== null) init.body = request.body
  fetch(request.url, init)
    .then(async (response) => {
      const body = await response.text()
      clearTimeout(timer)
      port.postMessage({
        id: request.id,
        ok: true,
        status: response.status,
        body,
        error: null,
        timedOut: false,
      })
    })
    .catch((error) => {
      clearTimeout(timer)
      port.postMessage({
        id: request.id,
        ok: false,
        status: 0,
        body: '',
        error: error && error.message ? String(error.message) : String(error),
        timedOut,
      })
    })
})
`

/** Bounded sync-over-async HTTP over a dedicated worker thread. */
class SyncHttpTransport {
  private worker: Worker | null = null
  private port: MessagePort | null = null
  private readonly signal = new Int32Array(new SharedArrayBuffer(4))
  private nextRequestId = 1

  request(input: SyncHttpRequest): HttpResponse {
    const port = this.ensurePort()
    const id = this.nextRequestId
    this.nextRequestId += 1
    port.postMessage({
      id,
      url: input.url,
      method: input.method,
      headers: input.headers,
      body: input.body,
      timeoutMs: input.timeoutMs,
    })

    // Deadlines always use the real clock; the injected clock is only for
    // reported latency, so a test clock cannot cause an infinite wait.
    const deadline = Date.now() + input.timeoutMs + SYNC_HTTP_GRACE_MS
    for (;;) {
      const received = receiveMessageOnPort(port)
      if (received !== undefined) {
        const message = parseSyncHttpMessage(received.message)
        if (message.id !== id) {
          throw new QwenEmbeddingError('embedding-unavailable', 'synchronous embedding transport received an out-of-order response')
        }
        if (message.timedOut) {
          this.reset()
          throw timeoutError(input.timeoutMs)
        }
        if (!message.ok) {
          throw new QwenEmbeddingError(
            'embedding-unavailable',
            `synchronous embedding request failed: ${message.error ?? 'unknown error'}`,
            [],
            { error: message.error },
          )
        }
        return { status: message.status, body: message.body }
      }
      if (Date.now() >= deadline) {
        this.reset()
        throw timeoutError(input.timeoutMs)
      }
      Atomics.wait(this.signal, 0, 0, SYNC_HTTP_POLL_MS)
    }
  }

  reset(): void {
    const worker = this.worker
    const port = this.port
    this.worker = null
    this.port = null
    if (port !== null) port.close()
    if (worker !== null) void worker.terminate()
  }

  close(): void {
    this.reset()
  }

  private ensurePort(): MessagePort {
    if (this.port !== null) return this.port
    const channel = new MessageChannel()
    const worker = new Worker(SYNC_HTTP_WORKER_SOURCE, {
      eval: true,
      workerData: { port: channel.port2 },
      transferList: [channel.port2],
    })
    worker.unref()
    channel.port1.unref()
    this.worker = worker
    this.port = channel.port1
    return channel.port1
  }
}

/**
 * Semantic Qwen embedding provider with batching, normalization, health
 * checks, and a content-addressed memory/disk cache.
 */
export class QwenEmbeddingProvider implements EmbeddingProvider {
  private readonly config: ResolvedQwenEmbeddingConfig
  private readonly fallback: EmbeddingProvider
  private readonly inProcess: EmbeddingProvider | null
  private readonly inProcessProbe: InProcessEmbeddingProbe
  private readonly clock: () => number
  private readonly memory = new Map<string, readonly number[]>()
  private readonly syncHttp: SyncHttpTransport | null
  private readonly state: MutableStats

  constructor(options: QwenEmbeddingOptions = {}) {
    this.config = resolveOptions(options)
    this.fallback = options.fallback ?? new DeterministicEmbeddingProvider()
    this.inProcess = options.inProcess ?? null
    this.inProcessProbe = probeInProcessEmbeddingRuntime()
    this.clock = options.clock ?? (() => Date.now())
    this.syncHttp = this.config.runtime === 'http' && this.config.syncTransport === 'worker'
      ? new SyncHttpTransport()
      : null
    this.state = {
      calls: 0,
      batches: 0,
      cacheHits: 0,
      cacheMisses: 0,
      diskHits: 0,
      degradedCalls: 0,
      failures: 0,
      totalLatencyMs: 0,
      lastLatencyMs: 0,
      cacheErrors: 0,
      lastReport: null,
    }
  }

  get model(): string {
    return this.config.model
  }

  get revision(): string {
    return this.config.revision
  }

  get baseUrl(): string {
    return this.config.baseUrl
  }

  /** Provider capabilities, including whether a local runtime was found. */
  capabilities(): QwenEmbeddingCapabilities {
    return {
      runtime: this.config.runtime,
      syncHttp: this.syncHttp !== null,
      asyncHttp: this.config.runtime === 'http',
      diskCache: this.config.cacheDirectory !== null,
      inProcess: this.inProcessProbe,
    }
  }

  /** Synchronous router seam. Blocks up to `timeoutMs` plus a small grace period. */
  embed(texts: readonly string[]): readonly (readonly number[])[] {
    return this.embedWithReport(texts).vectors
  }

  /** Async router-friendly path; never blocks the event loop. */
  async embedAsync(texts: readonly string[]): Promise<readonly (readonly number[])[]> {
    return (await this.embedAsyncWithReport(texts)).vectors
  }

  /** Synchronous call with provenance and cache accounting. */
  embedWithReport(texts: readonly string[]): EmbeddingBatchResult {
    this.assertTexts(texts)
    const startedAt = this.clock()
    const plan = this.buildPlan(texts)
    if (plan.misses.length === 0) {
      return this.finishSuccess(texts, plan, new Map(), startedAt, this.activeSource(), 0)
    }
    if (this.config.runtime === 'in-process') {
      return this.embedInProcess(texts, plan, startedAt)
    }
    if (this.syncHttp === null) {
      return this.fallbackResult(
        texts,
        plan,
        startedAt,
        'sync-transport-disabled',
        'synchronous HTTP transport is disabled for this provider',
        0,
      )
    }

    let batches = 0
    try {
      const fresh = new Map<string, readonly number[]>()
      for (const batch of chunk(plan.misses, this.config.batchSize)) {
        batches += 1
        const response = this.syncHttp.request(this.embeddingRequest(batch.map(miss => miss.text)))
        if (response.status < 200 || response.status >= 300) throw httpStatusError(response)
        const vectors = parseEmbeddingPayload(
          response.body,
          batch.length,
          this.config.normalize,
          this.config.expectedDimensions ?? plan.dimensions,
        )
        for (let index = 0; index < batch.length; index += 1) {
          const miss = batch[index]
          const vector = vectors[index]
          if (miss === undefined || vector === undefined) {
            throw new QwenEmbeddingError('embedding-internal', 'embedding batch lost a vector')
          }
          fresh.set(miss.key, vector)
        }
      }
      return this.finishSuccess(texts, plan, fresh, startedAt, 'qwen', batches)
    } catch (error) {
      return this.fallbackResult(
        texts,
        plan,
        startedAt,
        degradationReason(error),
        errorMessage(error),
        batches,
      )
    }
  }

  /** Async call with provenance and cache accounting. */
  async embedAsyncWithReport(texts: readonly string[]): Promise<EmbeddingBatchResult> {
    this.assertTexts(texts)
    const startedAt = this.clock()
    const plan = this.buildPlan(texts)
    if (plan.misses.length === 0) {
      return this.finishSuccess(texts, plan, new Map(), startedAt, this.activeSource(), 0)
    }
    if (this.config.runtime === 'in-process') {
      return this.embedInProcess(texts, plan, startedAt)
    }

    let batches = 0
    try {
      const fresh = new Map<string, readonly number[]>()
      for (const batch of chunk(plan.misses, this.config.batchSize)) {
        batches += 1
        const response = await this.requestHttp(
          this.config.embeddingsUrl,
          'POST',
          this.embeddingRequestBody(batch.map(miss => miss.text)),
          this.config.timeoutMs,
        )
        if (response.status < 200 || response.status >= 300) throw httpStatusError(response)
        const vectors = parseEmbeddingPayload(
          response.body,
          batch.length,
          this.config.normalize,
          this.config.expectedDimensions ?? plan.dimensions,
        )
        for (let index = 0; index < batch.length; index += 1) {
          const miss = batch[index]
          const vector = vectors[index]
          if (miss === undefined || vector === undefined) {
            throw new QwenEmbeddingError('embedding-internal', 'embedding batch lost a vector')
          }
          fresh.set(miss.key, vector)
        }
      }
      return this.finishSuccess(texts, plan, fresh, startedAt, 'qwen', batches)
    } catch (error) {
      return this.fallbackResult(
        texts,
        plan,
        startedAt,
        degradationReason(error),
        errorMessage(error),
        batches,
      )
    }
  }

  /** Last per-call report, or null before the first call. */
  lastReport(): EmbeddingCallReport | null {
    return this.state.lastReport
  }

  /** Cumulative counters plus the configured provider identity. */
  stats(): EmbeddingProviderStats {
    return {
      calls: this.state.calls,
      batches: this.state.batches,
      cacheHits: this.state.cacheHits,
      cacheMisses: this.state.cacheMisses,
      diskHits: this.state.diskHits,
      degradedCalls: this.state.degradedCalls,
      failures: this.state.failures,
      totalLatencyMs: this.state.totalLatencyMs,
      lastLatencyMs: this.state.lastLatencyMs,
      cacheErrors: this.state.cacheErrors,
      model: this.config.model,
      revision: this.config.revision,
      runtime: this.config.runtime,
      degraded: this.state.lastReport?.degraded ?? false,
    }
  }

  /** Probe the local model endpoint. Failures resolve with `ok: false`. */
  async health(): Promise<EmbeddingHealth> {
    const startedAt = this.clock()
    if (this.config.runtime === 'in-process') {
      const ok = this.inProcess !== null
      return {
        ok,
        model: this.config.model,
        revision: this.config.revision,
        degraded: !ok,
        latencyMs: this.elapsed(startedAt),
        status: null,
        error: ok ? null : this.inProcessProbe.reason,
      }
    }
    try {
      const response = await this.requestHttp(
        this.config.healthUrl,
        'GET',
        null,
        this.config.timeoutMs,
      )
      const ok = response.status >= 200 && response.status < 300
      return {
        ok,
        model: this.config.model,
        revision: this.config.revision,
        degraded: !ok,
        latencyMs: this.elapsed(startedAt),
        status: response.status,
        error: ok ? null : `health endpoint returned HTTP ${response.status}`,
      }
    } catch (error) {
      return {
        ok: false,
        model: this.config.model,
        revision: this.config.revision,
        degraded: true,
        latencyMs: this.elapsed(startedAt),
        status: null,
        error: errorMessage(error),
      }
    }
  }

  /** Release the blocking transport worker. Caches and counters are retained. */
  close(): void {
    this.syncHttp?.close()
  }

  private activeSource(): EmbeddingSource {
    return this.config.runtime === 'in-process' ? 'in-process' : 'qwen'
  }

  private elapsed(startedAt: number): number {
    return Math.max(0, this.clock() - startedAt)
  }

  private assertTexts(texts: readonly string[]): void {
    if (!Array.isArray(texts)) invalidInput('texts', 'texts must be an array of strings')
    const issues: StructuredIssue[] = []
    texts.forEach((text, index) => {
      if (typeof text !== 'string') {
        issues.push(issue(`texts[${index}]`, 'invalid-embedding-input', 'each input must be a string'))
      }
    })
    if (issues.length > 0) {
      throw new QwenEmbeddingError('invalid-embedding-input', 'embedding input is invalid', issues)
    }
  }

  private buildPlan(texts: readonly string[]): CachePlan {
    const keyByText = new Map<string, string>()
    const cached = new Map<string, readonly number[]>()
    const misses: CacheMiss[] = []
    const seen = new Set<string>()
    let cacheHits = 0
    let diskHits = 0
    let cacheMisses = 0
    let dimensions: number | null = null

    for (const text of texts) {
      if (seen.has(text)) continue
      seen.add(text)
      const key = embeddingCacheKey(
        this.config.runtime,
        this.config.model,
        this.config.revision,
        this.config.normalize,
        text,
      )
      keyByText.set(text, key)
      if (!this.config.cacheEnabled) {
        cacheMisses += 1
        misses.push({ text, key })
        continue
      }
      const memory = this.memoryGet(key)
      if (memory !== null && this.acceptCachedVector(memory, dimensions)) {
        dimensions = memory.length
        cached.set(key, memory)
        cacheHits += 1
        continue
      }
      const disk = this.readDiskCache(key)
      if (disk !== null && this.acceptCachedVector(disk, dimensions)) {
        dimensions = disk.length
        this.memorySet(key, disk)
        cached.set(key, disk)
        cacheHits += 1
        diskHits += 1
        continue
      }
      cacheMisses += 1
      misses.push({ text, key })
    }

    return { keyByText, cached, misses, cacheHits, diskHits, cacheMisses, dimensions }
  }

  private acceptCachedVector(vector: readonly number[], dimensions: number | null): boolean {
    if (dimensions !== null && vector.length !== dimensions) {
      this.state.cacheErrors += 1
      return false
    }
    if (this.config.expectedDimensions !== null && vector.length !== this.config.expectedDimensions) {
      this.state.cacheErrors += 1
      return false
    }
    return true
  }

  private finishSuccess(
    texts: readonly string[],
    plan: CachePlan,
    fresh: ReadonlyMap<string, readonly number[]>,
    startedAt: number,
    source: EmbeddingSource,
    batches: number,
  ): EmbeddingBatchResult {
    const resolved = new Map<string, readonly number[]>(plan.cached)
    for (const [key, vector] of fresh) resolved.set(key, vector)
    const vectors = this.assemble(texts, plan, resolved)
    const dimensions = vectors[0]?.length ?? 0
    for (const vector of vectors) {
      if (vector.length !== dimensions) {
        throw malformedError('embedding vectors within one call have inconsistent widths')
      }
    }
    if (vectors.length > 0
      && this.config.expectedDimensions !== null
      && dimensions !== this.config.expectedDimensions) {
      throw malformedError(
        `embedding width ${dimensions} does not match configured expectedDimensions ${this.config.expectedDimensions}`,
      )
    }
    for (const [key, vector] of fresh) {
      this.memorySet(key, vector)
      this.writeDiskCache(key, vector)
    }
    const report: EmbeddingCallReport = {
      source,
      model: this.config.model,
      revision: this.config.revision,
      requestedModel: this.config.model,
      requestedRevision: this.config.revision,
      degraded: false,
      degradationReason: null,
      error: null,
      cacheHits: plan.cacheHits,
      cacheMisses: plan.cacheMisses,
      diskHits: plan.diskHits,
      batches,
      latencyMs: this.elapsed(startedAt),
      dimensions,
    }
    this.record(report, false)
    return { vectors, report }
  }

  private fallbackResult(
    texts: readonly string[],
    plan: CachePlan,
    startedAt: number,
    reason: EmbeddingDegradationReason,
    error: string | null,
    batches: number,
  ): EmbeddingBatchResult {
    const vectors = this.fallbackVectors(texts)
    const report: EmbeddingCallReport = {
      source: 'fallback',
      model: FALLBACK_EMBEDDING_MODEL,
      revision: FALLBACK_EMBEDDING_REVISION,
      requestedModel: this.config.model,
      requestedRevision: this.config.revision,
      degraded: true,
      degradationReason: reason,
      error,
      cacheHits: plan.cacheHits,
      cacheMisses: plan.cacheMisses,
      diskHits: plan.diskHits,
      batches,
      latencyMs: this.elapsed(startedAt),
      dimensions: vectors[0]?.length ?? 0,
    }
    this.record(report, true)
    return { vectors, report }
  }

  private embedInProcess(
    texts: readonly string[],
    plan: CachePlan,
    startedAt: number,
  ): EmbeddingBatchResult {
    if (this.inProcess === null) {
      const message = this.inProcessProbe.available
        ? `${this.inProcessProbe.reason}; supply an inProcess adapter to use in-process mode`
        : this.inProcessProbe.reason
      return this.fallbackResult(texts, plan, startedAt, 'in-process-unavailable', message, 0)
    }
    try {
      const matrix = this.inProcess.embed(plan.misses.map(miss => miss.text))
      const vectors = this.validateProviderVectors(
        matrix,
        plan.misses.length,
        this.config.normalize,
        'in-process',
        this.config.expectedDimensions ?? plan.dimensions,
      )
      const fresh = new Map<string, readonly number[]>()
      for (let index = 0; index < plan.misses.length; index += 1) {
        const miss = plan.misses[index]
        const vector = vectors[index]
        if (miss === undefined || vector === undefined) {
          throw new QwenEmbeddingError('embedding-internal', 'in-process embedding lost a vector')
        }
        fresh.set(miss.key, vector)
      }
      return this.finishSuccess(texts, plan, fresh, startedAt, 'in-process', 0)
    } catch (error) {
      return this.fallbackResult(texts, plan, startedAt, 'in-process-error', errorMessage(error), 0)
    }
  }

  private fallbackVectors(texts: readonly string[]): readonly (readonly number[])[] {
    let matrix: readonly (readonly number[])[]
    try {
      matrix = this.fallback.embed(texts)
    } catch (error) {
      throw new QwenEmbeddingError(
        'embedding-fallback-failed',
        `deterministic embedding fallback failed: ${errorMessage(error)}`,
      )
    }
    return this.validateProviderVectors(
      matrix,
      texts.length,
      false,
      'fallback',
      null,
    )
  }

  private validateProviderVectors(
    matrix: readonly (readonly number[])[],
    expectedCount: number,
    normalize: boolean,
    label: string,
    expectedDimensions: number | null,
  ): readonly (readonly number[])[] {
    if (!Array.isArray(matrix) || matrix.length !== expectedCount) {
      throw new QwenEmbeddingError(
        'embedding-fallback-failed',
        `${label} provider returned ${Array.isArray(matrix) ? matrix.length : 'invalid'} vectors for ${expectedCount} inputs`,
      )
    }
    let dimensions = expectedDimensions ?? -1
    const vectors: (readonly number[])[] = []
    for (const vector of matrix) {
      if (!Array.isArray(vector) || vector.length === 0 || vector.length > MAX_EMBEDDING_DIMENSIONS) {
        throw new QwenEmbeddingError('embedding-fallback-failed', `${label} provider returned an invalid vector width`)
      }
      if (dimensions < 0) dimensions = vector.length
      else if (vector.length !== dimensions) {
        throw new QwenEmbeddingError('embedding-fallback-failed', `${label} provider returned inconsistent vector widths`)
      }
      const values: number[] = []
      let squaredNorm = 0
      for (const value of vector) {
        if (typeof value !== 'number' || !Number.isFinite(value)) {
          throw new QwenEmbeddingError('embedding-fallback-failed', `${label} provider returned a non-finite value`)
        }
        values.push(value)
        squaredNorm += value * value
      }
      if (!(squaredNorm > 0)) {
        throw new QwenEmbeddingError('embedding-fallback-failed', `${label} provider returned an all-zero vector`)
      }
      vectors.push(normalize ? normalizeVector(values) : values)
    }
    return vectors
  }

  private assemble(
    texts: readonly string[],
    plan: CachePlan,
    resolved: ReadonlyMap<string, readonly number[]>,
  ): readonly (readonly number[])[] {
    return texts.map((text, position) => {
      const key = plan.keyByText.get(text)
      if (key === undefined) {
        throw new QwenEmbeddingError('embedding-internal', `no cache key for input ${position}`)
      }
      const vector = resolved.get(key)
      if (vector === undefined) {
        throw new QwenEmbeddingError('embedding-internal', `no vector for input ${position}`)
      }
      return vector
    })
  }

  private embeddingRequestBody(input: readonly string[]): string {
    return JSON.stringify({ model: this.config.model, input })
  }

  private embeddingRequest(input: readonly string[]): SyncHttpRequest {
    const headers: Record<string, string> = {
      accept: 'application/json',
      'content-type': 'application/json',
    }
    const body = this.embeddingRequestBody(input)
    if (this.config.apiKey !== null) headers.authorization = `Bearer ${this.config.apiKey}`
    headers['x-embedding-revision'] = this.config.revision
    return {
      url: this.config.embeddingsUrl,
      method: 'POST',
      headers,
      body,
      timeoutMs: this.config.timeoutMs,
    }
  }

  private async requestHttp(
    url: string,
    method: 'GET' | 'POST',
    body: string | null,
    timeoutMs: number,
  ): Promise<HttpResponse> {
    const headers: Record<string, string> = { accept: 'application/json' }
    if (body !== null) headers['content-type'] = 'application/json'
    if (this.config.apiKey !== null) headers.authorization = `Bearer ${this.config.apiKey}`
    if (this.config.revision.length > 0) headers['x-embedding-revision'] = this.config.revision

    const controller = new AbortController()
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, timeoutMs)
    const init: RequestInit = { method, headers, signal: controller.signal }
    if (body !== null) init.body = body
    try {
      const response = await fetch(url, init)
      const text = await response.text()
      return { status: response.status, body: text }
    } catch (error) {
      if (timedOut) throw timeoutError(timeoutMs)
      throw new QwenEmbeddingError(
        'embedding-unavailable',
        `embedding request failed: ${errorMessage(error)}`,
        [],
        { url },
      )
    } finally {
      clearTimeout(timer)
    }
  }

  private memoryGet(key: string): readonly number[] | null {
    if (!this.config.cacheEnabled) return null
    const vector = this.memory.get(key)
    if (vector === undefined) return null
    this.memory.delete(key)
    this.memory.set(key, vector)
    return vector
  }

  private memorySet(key: string, vector: readonly number[]): void {
    if (!this.config.cacheEnabled || this.config.cacheMaxEntries < 1) return
    this.memory.set(key, vector)
    while (this.memory.size > this.config.cacheMaxEntries) {
      const oldest = this.memory.keys().next().value
      if (oldest === undefined) break
      this.memory.delete(oldest)
    }
  }

  private readDiskCache(key: string): readonly number[] | null {
    const directory = this.config.cacheDirectory
    if (directory === null) return null
    const target = join(directory, key.slice(0, 2), `${key}.json`)
    let raw: string
    try {
      raw = readFileSync(target, 'utf8')
    } catch (error) {
      if (errorCode(error) !== 'ENOENT') this.state.cacheErrors += 1
      return null
    }
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      this.state.cacheErrors += 1
      return null
    }
    const vector = this.parseCacheRecord(parsed, key)
    if (vector === null) this.state.cacheErrors += 1
    return vector
  }

  private parseCacheRecord(value: unknown, key: string): readonly number[] | null {
    if (!isRecord(value)) return null
    if (value.version !== CACHE_FILE_VERSION) return null
    if (value.key !== key) return null
    if (value.runtime !== this.config.runtime) return null
    if (value.model !== this.config.model || value.revision !== this.config.revision) return null
    if (value.normalize !== this.config.normalize) return null
    const rawVector = value.vector
    if (!Array.isArray(rawVector) || rawVector.length === 0 || rawVector.length > MAX_EMBEDDING_DIMENSIONS) {
      return null
    }
    if (this.config.expectedDimensions !== null && rawVector.length !== this.config.expectedDimensions) {
      return null
    }
    const vector: number[] = []
    let squaredNorm = 0
    for (const item of rawVector) {
      if (typeof item !== 'number' || !Number.isFinite(item)) return null
      vector.push(item)
      squaredNorm += item * item
    }
    if (!(squaredNorm > 0)) return null
    return vector
  }

  private writeDiskCache(key: string, vector: readonly number[]): void {
    const directory = this.config.cacheDirectory
    if (directory === null) return
    let temporary: string | null = null
    try {
      const shard = join(directory, key.slice(0, 2))
      mkdirSync(shard, { recursive: true })
      temporary = join(shard, `${key}.${randomUUID()}.tmp`)
      writeFileSync(temporary, JSON.stringify({
        version: CACHE_FILE_VERSION,
        key,
        runtime: this.config.runtime,
        model: this.config.model,
        revision: this.config.revision,
        normalize: this.config.normalize,
        vector,
      }), 'utf8')
      renameSync(temporary, join(shard, `${key}.json`))
      temporary = null
    } catch {
      this.state.cacheErrors += 1
      if (temporary !== null) {
        try {
          rmSync(temporary, { force: true })
        } catch {
          // Best-effort cleanup of a partial cache write.
        }
      }
    }
  }

  private record(report: EmbeddingCallReport, failed: boolean): void {
    const state = this.state
    state.calls += 1
    state.batches += report.batches
    state.cacheHits += report.cacheHits
    state.cacheMisses += report.cacheMisses
    state.diskHits += report.diskHits
    state.totalLatencyMs += report.latencyMs
    state.lastLatencyMs = report.latencyMs
    state.lastReport = report
    if (report.degraded) state.degradedCalls += 1
    if (failed) state.failures += 1
  }
}
