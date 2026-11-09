import type { EventId, FindingId, OperationId, RunId, SkillId, TraceId } from './ids.ts'
import type { Operation } from './operations.ts'
import type { Resource } from './resources.ts'
import type { VerificationStatus } from './evidence.ts'

/** Schema version of every durable v2 event. */
export const EVENT_VERSION = 1 as const

/** Payloads keyed by their durable event discriminator. */
export interface EventPayloadMap {
  'run/started': { readonly objective: string; readonly profile: string }
  'trace/ingested': {
    readonly traceId: TraceId
    readonly source: string
    readonly turns: number
  }
  'finding/detected': {
    readonly findingId: FindingId
    readonly traceId: TraceId
    readonly detector: string
    readonly confidence: number
    readonly summary: string
  }
  'candidate/recalled': { readonly skillIds: readonly SkillId[] }
  'candidate/selected': { readonly skillId: SkillId; readonly score: number }
  'diagnosis/recorded': { readonly findingId: FindingId; readonly summary: string }
  'goal/proposed': { readonly goalHash: string; readonly operationCount: number }
  'operation/planned': { readonly operation: Operation }
  'resource/generated': { readonly resource: Resource }
  'verification/completed': {
    readonly operationId: OperationId
    readonly status: VerificationStatus
    readonly summary: string
    readonly evidenceHash?: string
  }
  'operation/accepted': { readonly operationId: OperationId; readonly reason?: string }
  'operation/rejected': { readonly operationId: OperationId; readonly reason: string }
  'publication/completed': {
    readonly operationId: OperationId
    readonly releaseId: string
    readonly channel: 'provisional' | 'canary' | 'accepted'
  }
  'benchmark/completed': {
    readonly taskId: string
    readonly passed: boolean
    readonly toolCalls: number
  }
  'feedback/recorded': {
    readonly taskId: string
    readonly skillId: SkillId
    readonly adjustment: number
  }
  'run/completed': { readonly summary: string }
  'run/failed': { readonly reason: string }
}

/** All durable event discriminators. */
export type PipelineEventType = keyof EventPayloadMap

/** One versioned durable event carrying a run id and frozen payload. */
export type EventOf<T extends PipelineEventType> = {
  readonly id: EventId
  readonly runId: RunId
  readonly type: T
  readonly version: typeof EVENT_VERSION
  readonly at: string
  readonly payload: EventPayloadMap[T]
}

/** The closed union of supported durable events. */
export type PipelineEvent = {
  [T in PipelineEventType]: EventOf<T>
}[PipelineEventType]

/** Runtime list used by validation and tests. */
export const PIPELINE_EVENT_TYPES = [
  'run/started',
  'trace/ingested',
  'finding/detected',
  'candidate/recalled',
  'candidate/selected',
  'diagnosis/recorded',
  'goal/proposed',
  'operation/planned',
  'resource/generated',
  'verification/completed',
  'operation/accepted',
  'operation/rejected',
  'publication/completed',
  'benchmark/completed',
  'feedback/recorded',
  'run/completed',
  'run/failed',
] as const satisfies readonly PipelineEventType[]

const EVENT_TYPE_SET: ReadonlySet<string> = new Set(PIPELINE_EVENT_TYPES)

/** Return true for a supported durable event discriminator. */
export function isPipelineEventType(value: unknown): value is PipelineEventType {
  return typeof value === 'string' && EVENT_TYPE_SET.has(value)
}
