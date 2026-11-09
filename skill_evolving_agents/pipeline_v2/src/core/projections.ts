import type {
  PipelineEvent,
  PipelineEventType,
} from '../contracts/events.ts'
import type { VerificationStatus } from '../contracts/evidence.ts'
import type { OperationKind } from '../contracts/operations.ts'
import type { ResourceKind } from '../contracts/resources.ts'

/** Current run state derived only from durable events. */
export type RunStatus = 'not_started' | 'running' | 'completed' | 'failed'

/** Operation state in a projection. */
export type ProjectedOperationStatus =
  | 'planned'
  | 'verified_pass'
  | 'verified_fail'
  | 'accepted'
  | 'rejected'
  | 'published'

/** One operation folded from the event sequence. */
export interface OperationProjection {
  readonly id: string
  readonly kind: OperationKind
  readonly skillId: string
  readonly findingId: string
  readonly summary: string
  readonly status: ProjectedOperationStatus
  readonly verificationStatus?: VerificationStatus
}

/** One resource folded from the event sequence. */
export interface ResourceProjection {
  readonly id: string
  readonly operationId: string
  readonly skillId: string
  readonly kind: ResourceKind
  readonly path: string
  readonly status: 'generated' | 'used' | 'rejected'
}

/** A structured failure visible in the run projection. */
export interface FailureRecord {
  readonly eventId: string
  readonly type: PipelineEventType
  readonly code: string
  readonly message: string
}

/** Counts for the deterministic funnel. */
export interface FunnelProjection {
  readonly tracesIngested: number
  readonly findingsDetected: number
  readonly candidatesRecalled: number
  readonly candidatesSelected: number
  readonly diagnosesRecorded: number
  readonly goalsProposed: number
  readonly operationsPlanned: number
  readonly verificationsCompleted: number
  readonly verificationsPassed: number
  readonly verificationsFailed: number
  readonly efficiencyFailures: number
  readonly operationsAccepted: number
  readonly operationsRejected: number
  readonly publicationsCompleted: number
  readonly benchmarksCompleted: number
  readonly feedbackRecorded: number
}

/** Resource counts by status and kind. */
export interface ResourceUseProjection {
  readonly generated: number
  readonly used: number
  readonly rejected: number
  readonly byKind: Readonly<Record<ResourceKind, number>>
}

/** Complete deterministic projection of one run. */
export interface RunProjection {
  readonly runId?: string
  readonly status: RunStatus
  readonly startedAt?: string
  readonly endedAt?: string
  readonly eventCount: number
  readonly lastEventId?: string
  readonly funnel: FunnelProjection
  readonly operations: Readonly<Record<string, OperationProjection>>
  readonly resources: Readonly<Record<string, ResourceProjection>>
  readonly resourceUse: ResourceUseProjection
  readonly failures: readonly FailureRecord[]
}

const EMPTY_FUNNEL: FunnelProjection = {
  tracesIngested: 0,
  findingsDetected: 0,
  candidatesRecalled: 0,
  candidatesSelected: 0,
  diagnosesRecorded: 0,
  goalsProposed: 0,
  operationsPlanned: 0,
  verificationsCompleted: 0,
  verificationsPassed: 0,
  verificationsFailed: 0,
  efficiencyFailures: 0,
  operationsAccepted: 0,
  operationsRejected: 0,
  publicationsCompleted: 0,
  benchmarksCompleted: 0,
  feedbackRecorded: 0,
}

function sorted<T>(values: Map<string, T>): Readonly<Record<string, T>> {
  return Object.fromEntries([...values.entries()].sort(([a], [b]) => a.localeCompare(b)))
}

/** Fold the append-only sequence into the canonical run view. */
export function projectEvents(events: readonly PipelineEvent[]): RunProjection {
  const funnel: { -readonly [K in keyof FunnelProjection]: number } = { ...EMPTY_FUNNEL }
  const operations = new Map<string, OperationProjection>()
  const resources = new Map<string, ResourceProjection>()
  const failures: FailureRecord[] = []
  let status: RunStatus = 'not_started'
  let startedAt: string | undefined
  let endedAt: string | undefined
  let runId: string | undefined

  for (const event of events) {
    runId ??= event.runId
    switch (event.type) {
      case 'run/started':
        status = 'running'
        startedAt = event.at
        break
      case 'run/completed':
        status = 'completed'
        endedAt = event.at
        break
      case 'run/failed':
        status = 'failed'
        endedAt = event.at
        failures.push({
          eventId: event.id,
          type: event.type,
          code: 'run-failed',
          message: event.payload.reason,
        })
        break
      case 'trace/ingested':
        funnel.tracesIngested += 1
        break
      case 'finding/detected':
        funnel.findingsDetected += 1
        break
      case 'candidate/recalled':
        funnel.candidatesRecalled += event.payload.skillIds.length
        break
      case 'candidate/selected':
        funnel.candidatesSelected += 1
        break
      case 'diagnosis/recorded':
        funnel.diagnosesRecorded += 1
        break
      case 'goal/proposed':
        funnel.goalsProposed += 1
        break
      case 'operation/planned': {
        funnel.operationsPlanned += 1
        const operation = event.payload.operation
        operations.set(operation.id, {
          id: operation.id,
          kind: operation.kind,
          skillId: operation.skillId,
          findingId: operation.findingId,
          summary: operation.summary,
          status: 'planned',
        })
        break
      }
      case 'resource/generated': {
        const resource = event.payload.resource
        resources.set(resource.id, {
          id: resource.id,
          operationId: resource.operationId,
          skillId: resource.skillId,
          kind: resource.kind,
          path: resource.path,
          status: resource.status,
        })
        break
      }
      case 'verification/completed': {
        funnel.verificationsCompleted += 1
        if (event.payload.status === 'pass') funnel.verificationsPassed += 1
        if (event.payload.status === 'fail') funnel.verificationsFailed += 1
        if (event.payload.status === 'efficiency_failure') funnel.efficiencyFailures += 1
        const operation = operations.get(event.payload.operationId)
        if (operation) {
          operations.set(operation.id, {
            ...operation,
            status: event.payload.status === 'pass' ? 'verified_pass' : 'verified_fail',
            verificationStatus: event.payload.status,
          })
        }
        if (event.payload.status !== 'pass') {
          failures.push({
            eventId: event.id,
            type: event.type,
            code: event.payload.status === 'efficiency_failure' ? 'efficiency-failure' : 'verification-failed',
            message: event.payload.summary,
          })
        }
        break
      }
      case 'operation/accepted': {
        funnel.operationsAccepted += 1
        const operation = operations.get(event.payload.operationId)
        if (operation) operations.set(operation.id, { ...operation, status: 'accepted' })
        break
      }
      case 'operation/rejected': {
        funnel.operationsRejected += 1
        const operation = operations.get(event.payload.operationId)
        if (operation) operations.set(operation.id, { ...operation, status: 'rejected' })
        failures.push({
          eventId: event.id,
          type: event.type,
          code: 'operation-rejected',
          message: event.payload.reason,
        })
        break
      }
      case 'publication/completed': {
        funnel.publicationsCompleted += 1
        const operation = operations.get(event.payload.operationId)
        if (operation) operations.set(operation.id, { ...operation, status: 'published' })
        break
      }
      case 'benchmark/completed':
        funnel.benchmarksCompleted += 1
        break
      case 'feedback/recorded':
        funnel.feedbackRecorded += 1
        break
      default: {
        const exhaustive: never = event
        void exhaustive
      }
    }
  }

  const resourceValues = [...resources.values()]
  const byKind: Record<ResourceKind, number> = {
    scripts: 0,
    references: 0,
    assets: 0,
    agents: 0,
    evals: 0,
  }
  for (const resource of resourceValues) byKind[resource.kind] += 1

  const lastEvent = events[events.length - 1]
  return {
    ...(runId === undefined ? {} : { runId }),
    status,
    ...(startedAt === undefined ? {} : { startedAt }),
    ...(endedAt === undefined ? {} : { endedAt }),
    eventCount: events.length,
    ...(lastEvent ? { lastEventId: lastEvent.id } : {}),
    funnel,
    operations: sorted(operations),
    resources: sorted(resources),
    resourceUse: {
      generated: resourceValues.filter((resource) => resource.status === 'generated').length,
      used: resourceValues.filter((resource) => resource.status === 'used').length,
      rejected: resourceValues.filter((resource) => resource.status === 'rejected').length,
      byKind,
    },
    failures,
  }
}
