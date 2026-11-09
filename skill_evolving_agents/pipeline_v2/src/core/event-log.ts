import {
  DuplicateEventError,
  DuplicateResourceError,
  EventValidationError,
  InvalidTransitionError,
  RunIdMismatchError,
  UnsupportedEventVersionError,
} from '../contracts/errors.ts'
import type { StructuredIssue } from '../contracts/errors.ts'
import {
  EVENT_VERSION,
  isPipelineEventType,
  type PipelineEvent,
  type PipelineEventType,
} from '../contracts/events.ts'
import type { OperationKind } from '../contracts/operations.ts'
import type { ResourceKind } from '../contracts/resources.ts'
import { isFiniteNumber, isNonEmptyString, isRecord, issue } from '../contracts/validation.ts'

const OPERATION_KINDS: ReadonlySet<string> = new Set<OperationKind>([
  'create',
  'update',
  'merge',
  'split',
  'delete',
  'no_change',
])

const RESOURCE_KINDS: ReadonlySet<string> = new Set<ResourceKind>([
  'scripts',
  'references',
  'assets',
  'agents',
  'evals',
])

function validateStringArray(value: unknown, path: string): StructuredIssue[] {
  if (!Array.isArray(value) || value.some((item) => !isNonEmptyString(item))) {
    return [issue(path, 'invalid', 'must be an array of non-empty strings')]
  }
  return []
}

function validateOperation(value: unknown): StructuredIssue[] {
  if (!isRecord(value)) return [issue('$.payload.operation', 'invalid', 'operation must be an object')]
  const issues: StructuredIssue[] = []
  for (const field of ['id', 'skillId', 'findingId', 'summary'] as const) {
    if (!isNonEmptyString(value[field])) {
      issues.push(issue(`$.payload.operation.${field}`, 'invalid', `${field} must be a non-empty string`))
    }
  }
  if (!isNonEmptyString(value.kind) || !OPERATION_KINDS.has(value.kind)) {
    issues.push(issue('$.payload.operation.kind', 'invalid', 'kind is not supported'))
  }
  return issues
}

function validateResource(value: unknown): StructuredIssue[] {
  if (!isRecord(value)) return [issue('$.payload.resource', 'invalid', 'resource must be an object')]
  const issues: StructuredIssue[] = []
  for (const field of ['id', 'operationId', 'skillId', 'path'] as const) {
    if (!isNonEmptyString(value[field])) {
      issues.push(issue(`$.payload.resource.${field}`, 'invalid', `${field} must be a non-empty string`))
    }
  }
  if (!isNonEmptyString(value.kind) || !RESOURCE_KINDS.has(value.kind)) {
    issues.push(issue('$.payload.resource.kind', 'invalid', 'resource kind is not supported'))
  }
  if (value.status !== 'generated' && value.status !== 'used' && value.status !== 'rejected') {
    issues.push(issue('$.payload.resource.status', 'invalid', 'resource status is not supported'))
  }
  return issues
}

function validatePayload(type: PipelineEventType, payload: unknown): StructuredIssue[] {
  if (!isRecord(payload)) return [issue('$.payload', 'invalid', 'payload must be an object')]
  const issues: StructuredIssue[] = []
  switch (type) {
    case 'run/started':
      if (!isNonEmptyString(payload.objective)) issues.push(issue('$.payload.objective', 'invalid', 'objective must be a non-empty string'))
      if (!isNonEmptyString(payload.profile)) issues.push(issue('$.payload.profile', 'invalid', 'profile must be a non-empty string'))
      break
    case 'trace/ingested':
      if (!isNonEmptyString(payload.traceId)) issues.push(issue('$.payload.traceId', 'invalid', 'traceId must be a non-empty string'))
      if (!isNonEmptyString(payload.source)) issues.push(issue('$.payload.source', 'invalid', 'source must be a non-empty string'))
      if (!isFiniteNumber(payload.turns) || !Number.isInteger(payload.turns) || payload.turns < 0) issues.push(issue('$.payload.turns', 'invalid', 'turns must be a non-negative integer'))
      break
    case 'finding/detected':
      for (const field of ['findingId', 'traceId', 'detector', 'summary'] as const) {
        if (!isNonEmptyString(payload[field])) issues.push(issue(`$.payload.${field}`, 'invalid', `${field} must be a non-empty string`))
      }
      if (!isFiniteNumber(payload.confidence) || payload.confidence < 0 || payload.confidence > 1) issues.push(issue('$.payload.confidence', 'invalid', 'confidence must be between 0 and 1'))
      break
    case 'candidate/recalled':
      issues.push(...validateStringArray(payload.skillIds, '$.payload.skillIds'))
      break
    case 'candidate/selected':
      if (!isNonEmptyString(payload.skillId)) issues.push(issue('$.payload.skillId', 'invalid', 'skillId must be a non-empty string'))
      if (!isFiniteNumber(payload.score) || payload.score < 0 || payload.score > 1) issues.push(issue('$.payload.score', 'invalid', 'score must be between 0 and 1'))
      break
    case 'diagnosis/recorded':
      if (!isNonEmptyString(payload.findingId)) issues.push(issue('$.payload.findingId', 'invalid', 'findingId must be a non-empty string'))
      if (!isNonEmptyString(payload.summary)) issues.push(issue('$.payload.summary', 'invalid', 'summary must be a non-empty string'))
      break
    case 'goal/proposed':
      if (!isNonEmptyString(payload.goalHash)) issues.push(issue('$.payload.goalHash', 'invalid', 'goalHash must be a non-empty string'))
      if (!isFiniteNumber(payload.operationCount) || !Number.isInteger(payload.operationCount) || payload.operationCount < 0) issues.push(issue('$.payload.operationCount', 'invalid', 'operationCount must be a non-negative integer'))
      break
    case 'operation/planned':
      issues.push(...validateOperation(payload.operation))
      break
    case 'resource/generated':
      issues.push(...validateResource(payload.resource))
      break
    case 'verification/completed':
      if (!isNonEmptyString(payload.operationId)) issues.push(issue('$.payload.operationId', 'invalid', 'operationId must be a non-empty string'))
      if (payload.status !== 'pass' && payload.status !== 'fail' && payload.status !== 'efficiency_failure') issues.push(issue('$.payload.status', 'invalid', 'verification status is not supported'))
      if (!isNonEmptyString(payload.summary)) issues.push(issue('$.payload.summary', 'invalid', 'summary must be a non-empty string'))
      if (payload.evidenceHash !== undefined && !isNonEmptyString(payload.evidenceHash)) issues.push(issue('$.payload.evidenceHash', 'invalid', 'evidenceHash must be a non-empty string when present'))
      break
    case 'operation/accepted':
      if (!isNonEmptyString(payload.operationId)) issues.push(issue('$.payload.operationId', 'invalid', 'operationId must be a non-empty string'))
      if (payload.reason !== undefined && !isNonEmptyString(payload.reason)) issues.push(issue('$.payload.reason', 'invalid', 'reason must be a non-empty string when present'))
      break
    case 'operation/rejected':
      if (!isNonEmptyString(payload.operationId)) issues.push(issue('$.payload.operationId', 'invalid', 'operationId must be a non-empty string'))
      if (!isNonEmptyString(payload.reason)) issues.push(issue('$.payload.reason', 'invalid', 'reason must be a non-empty string'))
      break
    case 'publication/completed':
      if (!isNonEmptyString(payload.operationId)) issues.push(issue('$.payload.operationId', 'invalid', 'operationId must be a non-empty string'))
      if (!isNonEmptyString(payload.releaseId)) issues.push(issue('$.payload.releaseId', 'invalid', 'releaseId must be a non-empty string'))
      if (payload.channel !== 'provisional' && payload.channel !== 'canary' && payload.channel !== 'accepted') issues.push(issue('$.payload.channel', 'invalid', 'publication channel is not supported'))
      break
    case 'benchmark/completed':
      if (!isNonEmptyString(payload.taskId)) issues.push(issue('$.payload.taskId', 'invalid', 'taskId must be a non-empty string'))
      if (typeof payload.passed !== 'boolean') issues.push(issue('$.payload.passed', 'invalid', 'passed must be boolean'))
      if (!isFiniteNumber(payload.toolCalls) || !Number.isInteger(payload.toolCalls) || payload.toolCalls < 0) issues.push(issue('$.payload.toolCalls', 'invalid', 'toolCalls must be a non-negative integer'))
      break
    case 'feedback/recorded':
      if (!isNonEmptyString(payload.taskId)) issues.push(issue('$.payload.taskId', 'invalid', 'taskId must be a non-empty string'))
      if (!isNonEmptyString(payload.skillId)) issues.push(issue('$.payload.skillId', 'invalid', 'skillId must be a non-empty string'))
      if (!isFiniteNumber(payload.adjustment)) issues.push(issue('$.payload.adjustment', 'invalid', 'adjustment must be a finite number'))
      break
    case 'run/completed':
      if (!isNonEmptyString(payload.summary)) issues.push(issue('$.payload.summary', 'invalid', 'summary must be a non-empty string'))
      break
    case 'run/failed':
      if (!isNonEmptyString(payload.reason)) issues.push(issue('$.payload.reason', 'invalid', 'reason must be a non-empty string'))
      break
    default: {
      const exhaustive: never = type
      issues.push(issue('$.type', 'invalid', `unsupported event type ${String(exhaustive)}`))
    }
  }
  return issues
}

/** Validate one event without throwing. */
export function validateEvent(value: unknown): StructuredIssue[] {
  if (!isRecord(value)) return [issue('$', 'invalid', 'event must be an object')]
  const issues: StructuredIssue[] = []
  if (!isNonEmptyString(value.id)) issues.push(issue('$.id', 'invalid', 'id must be a non-empty string'))
  if (!isNonEmptyString(value.runId)) issues.push(issue('$.runId', 'invalid', 'runId must be a non-empty string'))
  if (!isNonEmptyString(value.at) || Number.isNaN(Date.parse(value.at))) issues.push(issue('$.at', 'invalid', 'at must be an ISO timestamp'))
  if (value.version !== EVENT_VERSION) issues.push(issue('$.version', 'unsupported', `version must be ${EVENT_VERSION}`))
  if (!isPipelineEventType(value.type)) {
    issues.push(issue('$.type', 'invalid', 'type is not a supported durable event'))
    return issues
  }
  issues.push(...validatePayload(value.type, value.payload))
  return issues
}

/** Validate and brand one event; a future version has its own structured error. */
export function assertEvent(value: unknown): PipelineEvent {
  if (isRecord(value) && value.version !== EVENT_VERSION) {
    throw new UnsupportedEventVersionError(value.type, value.version)
  }
  const issues = validateEvent(value)
  if (issues.length > 0) throw new EventValidationError(issues)
  return value as PipelineEvent
}

function runStatus(events: readonly PipelineEvent[]): 'not_started' | 'running' | 'completed' | 'failed' {
  if (events.length === 0) return 'not_started'
  if (events.some((event) => event.type === 'run/completed')) return 'completed'
  if (events.some((event) => event.type === 'run/failed')) return 'failed'
  return 'running'
}

function operationState(events: readonly PipelineEvent[], id: string): string | undefined {
  let state: string | undefined
  for (const event of events) {
    if (event.type === 'operation/planned' && event.payload.operation.id === id) state = 'planned'
    if (event.type === 'verification/completed' && event.payload.operationId === id) {
      state = event.payload.status === 'pass' ? 'verified_pass' : 'verified_fail'
    }
    if (event.type === 'operation/accepted' && event.payload.operationId === id) state = 'accepted'
    if (event.type === 'operation/rejected' && event.payload.operationId === id) state = 'rejected'
    if (event.type === 'publication/completed' && event.payload.operationId === id) state = 'published'
  }
  return state
}

function referencedOperationId(event: PipelineEvent): string | undefined {
  switch (event.type) {
    case 'resource/generated':
      return event.payload.resource.operationId
    case 'verification/completed':
    case 'operation/accepted':
    case 'operation/rejected':
    case 'publication/completed':
      return event.payload.operationId
    default:
      return undefined
  }
}

function assertTransition(events: readonly PipelineEvent[], event: PipelineEvent): void {
  const status = runStatus(events)
  const first = events[0]
  if (first && event.runId !== first.runId) {
    throw new RunIdMismatchError(first.runId, event.runId)
  }
  if (events.length === 0 && event.type !== 'run/started') {
    throw new InvalidTransitionError(event.type, status, 'the first durable event must be run/started')
  }
  if (event.type === 'run/started' && events.length > 0) {
    throw new InvalidTransitionError(event.type, status, 'run/started may appear only once')
  }
  if (status === 'completed' || status === 'failed') {
    throw new InvalidTransitionError(event.type, status, `run is already ${status}`)
  }
  if (
    (event.type === 'run/completed' || event.type === 'run/failed') &&
    status !== 'running'
  ) {
    throw new InvalidTransitionError(event.type, status, 'terminal event requires a running run')
  }
  if (event.type === 'resource/generated') {
    const resource = event.payload.resource
    const duplicate = events.some(
      (previous) =>
        previous.type === 'resource/generated' &&
        previous.payload.resource.id === resource.id,
    )
    if (duplicate) throw new DuplicateResourceError(resource.id)
  }
  if (event.type === 'operation/planned') {
    const id = event.payload.operation.id
    if (operationState(events, id) !== undefined) {
      throw new InvalidTransitionError(event.type, status, `operation ${id} was already planned`)
    }
  }
  const reference = referencedOperationId(event)
  if (reference !== undefined) {
    const state = operationState(events, reference)
    if (state === undefined) {
      throw new InvalidTransitionError(event.type, status, `operation ${reference} must be planned first`)
    }
    if (
      event.type === 'verification/completed' &&
      (state === 'verified_pass' ||
        state === 'verified_fail' ||
        state === 'accepted' ||
        state === 'rejected' ||
        state === 'published')
    ) {
      throw new InvalidTransitionError(event.type, state, 'operation verification is already final')
    }
    if (event.type === 'operation/accepted' && state !== 'verified_pass') {
      throw new InvalidTransitionError(event.type, state, 'operation may be accepted only after a passing verification')
    }
    if (event.type === 'operation/accepted' && (state === 'accepted' || state === 'published')) {
      throw new InvalidTransitionError(event.type, state, 'operation was already accepted')
    }
    if (event.type === 'operation/rejected' && (state === 'accepted' || state === 'published' || state === 'rejected')) {
      throw new InvalidTransitionError(event.type, state, 'operation was already finalised')
    }
    if (event.type === 'publication/completed' && state !== 'accepted') {
      throw new InvalidTransitionError(event.type, state, 'publication requires an accepted operation')
    }
  }
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value)
    for (const child of Object.values(value as object)) deepFreeze(child)
  }
  return value
}

/** Append-only in-memory event log with schema and transition validation. */
export class EventLog {
  private readonly entries: PipelineEvent[] = []
  private readonly ids = new Set<string>()

  /** Append one validated event and return the branded event. */
  append(value: unknown): PipelineEvent {
    const event = assertEvent(value)
    if (this.ids.has(event.id)) throw new DuplicateEventError(event.id)
    assertTransition(this.entries, event)
    const frozen = deepFreeze(event)
    this.entries.push(frozen)
    this.ids.add(event.id)
    return frozen
  }

  /** Append several events atomically with respect to validation failures. */
  appendAll(values: readonly unknown[]): readonly PipelineEvent[] {
    const appended: PipelineEvent[] = []
    for (const value of values) {
      try {
        appended.push(this.append(value))
      } catch (error) {
        for (const event of appended) {
          this.entries.pop()
          this.ids.delete(event.id)
        }
        throw error
      }
    }
    return appended
  }

  /** Read-only event sequence in append order. */
  get events(): readonly PipelineEvent[] {
    return [...this.entries]
  }

  /** Number of appended events. */
  get length(): number {
    return this.entries.length
  }
}
