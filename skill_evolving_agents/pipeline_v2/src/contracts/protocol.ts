import { WorkerProtocolError } from './errors.ts'
import type { StructuredIssue } from './errors.ts'
import { isFiniteNumber, isNonEmptyString, isRecord, issue } from './validation.ts'

/** Version of the JSON request/result protocol used by future Python workers. */
export const WORKER_PROTOCOL_VERSION = 1 as const

/** Hard limits the parent process imposes on one worker invocation. */
export interface WorkerLimits {
  readonly wallSeconds: number
  readonly outputBytes: number
}

/** One versioned worker request. */
export interface WorkerRequest {
  readonly protocolVersion: typeof WORKER_PROTOCOL_VERSION
  readonly requestId: string
  readonly operation: string
  readonly input: Readonly<Record<string, unknown>>
  readonly limits: WorkerLimits
}

/** Structured worker failure. */
export interface WorkerError {
  readonly code: string
  readonly message: string
  readonly details?: Readonly<Record<string, unknown>>
}

/** Optional measured usage returned by a worker. */
export interface WorkerUsage {
  readonly wallSeconds?: number
  readonly tokens?: number
  readonly costUsd?: number
}

/** One versioned worker result. */
export type WorkerResult =
  | {
      readonly protocolVersion: typeof WORKER_PROTOCOL_VERSION
      readonly requestId: string
      readonly status: 'ok'
      readonly output: Readonly<Record<string, unknown>>
      readonly usage?: WorkerUsage
    }
  | {
      readonly protocolVersion: typeof WORKER_PROTOCOL_VERSION
      readonly requestId: string
      readonly status: 'error'
      readonly error: WorkerError
      readonly usage?: WorkerUsage
    }

function validateLimits(value: unknown): StructuredIssue[] {
  if (!isRecord(value)) return [issue('$.limits', 'missing', 'limits must be an object')]
  const issues: StructuredIssue[] = []
  if (!isFiniteNumber(value.wallSeconds) || value.wallSeconds <= 0) {
    issues.push(issue('$.limits.wallSeconds', 'invalid', 'wallSeconds must be a positive number'))
  }
  if (!isFiniteNumber(value.outputBytes) || value.outputBytes <= 0) {
    issues.push(issue('$.limits.outputBytes', 'invalid', 'outputBytes must be a positive number'))
  }
  return issues
}

function readUsage(value: unknown): WorkerUsage | undefined {
  if (!isRecord(value)) return undefined
  const usage: { wallSeconds?: number; tokens?: number; costUsd?: number } = {}
  if (isFiniteNumber(value.wallSeconds)) usage.wallSeconds = value.wallSeconds
  if (isFiniteNumber(value.tokens)) usage.tokens = value.tokens
  if (isFiniteNumber(value.costUsd)) usage.costUsd = value.costUsd
  return Object.keys(usage).length === 0 ? undefined : usage
}

/** Parse and validate one worker request at the process/wire boundary. */
export function parseWorkerRequest(value: unknown): WorkerRequest {
  if (!isRecord(value)) {
    throw new WorkerProtocolError([issue('$', 'invalid', 'request must be a JSON object')])
  }
  const issues: StructuredIssue[] = []
  const requestId = value.requestId
  const operation = value.operation
  const input = value.input
  if (value.protocolVersion !== WORKER_PROTOCOL_VERSION) {
    issues.push(issue('$.protocolVersion', 'unsupported', 'unsupported worker protocol version'))
  }
  if (!isNonEmptyString(requestId)) {
    issues.push(issue('$.requestId', 'invalid', 'requestId must be a non-empty string'))
  }
  if (!isNonEmptyString(operation)) {
    issues.push(issue('$.operation', 'invalid', 'operation must be a non-empty string'))
  }
  if (!isRecord(input)) {
    issues.push(issue('$.input', 'invalid', 'input must be a JSON object'))
  }
  issues.push(...validateLimits(value.limits))
  if (issues.length > 0) throw new WorkerProtocolError(issues)
  const limits = value.limits as Record<string, unknown>
  return {
    protocolVersion: WORKER_PROTOCOL_VERSION,
    requestId: requestId as string,
    operation: operation as string,
    input: input as Readonly<Record<string, unknown>>,
    limits: {
      wallSeconds: limits.wallSeconds as number,
      outputBytes: limits.outputBytes as number,
    },
  }
}

/** Parse and validate one worker result at the process/wire boundary. */
export function parseWorkerResult(value: unknown): WorkerResult {
  if (!isRecord(value)) {
    throw new WorkerProtocolError([issue('$', 'invalid', 'result must be a JSON object')])
  }
  const issues: StructuredIssue[] = []
  const requestId = value.requestId
  if (value.protocolVersion !== WORKER_PROTOCOL_VERSION) {
    issues.push(issue('$.protocolVersion', 'unsupported', 'unsupported worker protocol version'))
  }
  if (!isNonEmptyString(requestId)) {
    issues.push(issue('$.requestId', 'invalid', 'requestId must be a non-empty string'))
  }
  if (value.status === 'ok') {
    if (!isRecord(value.output)) {
      issues.push(issue('$.output', 'invalid', 'output must be an object when status is ok'))
    }
    if (issues.length > 0) throw new WorkerProtocolError(issues)
    return {
      protocolVersion: WORKER_PROTOCOL_VERSION,
      requestId: requestId as string,
      status: 'ok',
      output: value.output as Readonly<Record<string, unknown>>,
      ...(readUsage(value.usage) ? { usage: readUsage(value.usage) } : {}),
    }
  }
  if (value.status === 'error') {
    const error = value.error
    if (!isRecord(error)) {
      issues.push(issue('$.error', 'invalid', 'error must be an object when status is error'))
    } else {
      if (!isNonEmptyString(error.code)) {
        issues.push(issue('$.error.code', 'invalid', 'error code must be a non-empty string'))
      }
      if (!isNonEmptyString(error.message)) {
        issues.push(issue('$.error.message', 'invalid', 'error message must be a non-empty string'))
      }
    }
    if (issues.length > 0) throw new WorkerProtocolError(issues)
    const normalized = error as Record<string, unknown>
    return {
      protocolVersion: WORKER_PROTOCOL_VERSION,
      requestId: requestId as string,
      status: 'error',
      error: {
        code: normalized.code as string,
        message: normalized.message as string,
        ...(isRecord(normalized.details)
          ? { details: normalized.details as Readonly<Record<string, unknown>> }
          : {}),
      },
      ...(readUsage(value.usage) ? { usage: readUsage(value.usage) } : {}),
    }
  }
  issues.push(issue('$.status', 'invalid', 'status must be ok or error'))
  throw new WorkerProtocolError(issues)
}
