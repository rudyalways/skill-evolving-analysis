import { InvalidComparisonReportError } from './errors.ts'
import type { StructuredIssue } from './errors.ts'
import { isFiniteNumber, isNonEmptyString, isRecord, issue } from './validation.ts'

/** Version of the legacy/v2 comparison report. */
export const COMPARISON_REPORT_VERSION = 1 as const

/** Resource row included in a comparison report. */
export interface ComparisonResource {
  readonly kind: string
  readonly path: string
  readonly status: string
}

/** One frozen comparison between the legacy pipeline and v2. */
export interface LegacyComparisonReport {
  readonly schemaVersion: typeof COMPARISON_REPORT_VERSION
  readonly runId: string
  readonly traceId: string
  readonly eventCount: number
  readonly eventIds: readonly string[]
  readonly projectionStatus: 'not_started' | 'running' | 'completed' | 'failed'
  readonly projection: Readonly<Record<string, unknown>>
  readonly selectedSkillId: string | null
  readonly operationId: string | null
  readonly resources: readonly ComparisonResource[]
  readonly replay: {
    readonly available: boolean
    readonly status: 'pass' | 'fail' | 'not_run'
    readonly evidenceHash?: string
  }
  readonly usage: {
    readonly agentCalls: number
    readonly tokens: number
    readonly costUsd: number | null
  }
  readonly output: {
    readonly equivalence: 'equivalent' | 'different' | 'unverified'
    readonly notes: string
  }
  readonly cleanup: {
    readonly disposed: boolean
    readonly leakedRegistrations: number
  }
}

function validateReplay(value: unknown): StructuredIssue[] {
  if (!isRecord(value)) return [issue('$.replay', 'invalid', 'replay must be an object')]
  const issues: StructuredIssue[] = []
  if (typeof value.available !== 'boolean') {
    issues.push(issue('$.replay.available', 'invalid', 'available must be boolean'))
  }
  if (value.status !== 'pass' && value.status !== 'fail' && value.status !== 'not_run') {
    issues.push(issue('$.replay.status', 'invalid', 'replay status is not supported'))
  }
  if (value.evidenceHash !== undefined && !isNonEmptyString(value.evidenceHash)) {
    issues.push(issue('$.replay.evidenceHash', 'invalid', 'evidenceHash must be a string when present'))
  }
  return issues
}

function validateUsage(value: unknown): StructuredIssue[] {
  if (!isRecord(value)) return [issue('$.usage', 'invalid', 'usage must be an object')]
  const issues: StructuredIssue[] = []
  for (const field of ['agentCalls', 'tokens'] as const) {
    if (!isFiniteNumber(value[field]) || value[field] < 0) {
      issues.push(issue(`$.usage.${field}`, 'invalid', `${field} must be a non-negative number`))
    }
  }
  if (value.costUsd !== null && (!isFiniteNumber(value.costUsd) || value.costUsd < 0)) {
    issues.push(issue('$.usage.costUsd', 'invalid', 'costUsd must be null or a non-negative number'))
  }
  return issues
}

/** Validate a legacy comparison report at a file/worker boundary. */
export function validateComparisonReport(value: unknown): StructuredIssue[] {
  if (!isRecord(value)) return [issue('$', 'invalid', 'report must be an object')]
  const issues: StructuredIssue[] = []
  if (value.schemaVersion !== COMPARISON_REPORT_VERSION) {
    issues.push(issue('$.schemaVersion', 'unsupported', 'unsupported comparison report version'))
  }
  for (const field of ['runId', 'traceId'] as const) {
    if (!isNonEmptyString(value[field])) {
      issues.push(issue(`$.${field}`, 'invalid', `${field} must be a non-empty string`))
    }
  }
  if (!isFiniteNumber(value.eventCount) || !Number.isInteger(value.eventCount) || value.eventCount < 0) {
    issues.push(issue('$.eventCount', 'invalid', 'eventCount must be a non-negative integer'))
  }
  if (!Array.isArray(value.eventIds) || value.eventIds.some((id) => !isNonEmptyString(id))) {
    issues.push(issue('$.eventIds', 'invalid', 'eventIds must be an array of non-empty strings'))
  }
  if (!isRecord(value.projection)) {
    issues.push(issue('$.projection', 'invalid', 'projection must be an object'))
  }
  if (!['not_started', 'running', 'completed', 'failed'].includes(String(value.projectionStatus))) {
    issues.push(issue('$.projectionStatus', 'invalid', 'projectionStatus is not supported'))
  }
  for (const field of ['selectedSkillId', 'operationId'] as const) {
    if (value[field] !== null && !isNonEmptyString(value[field])) {
      issues.push(issue(`$.${field}`, 'invalid', `${field} must be null or a non-empty string`))
    }
  }
  if (!Array.isArray(value.resources)) {
    issues.push(issue('$.resources', 'invalid', 'resources must be an array'))
  } else {
    value.resources.forEach((resource, index) => {
      if (!isRecord(resource)) {
        issues.push(issue(`$.resources[${index}]`, 'invalid', 'resource must be an object'))
        return
      }
      for (const field of ['kind', 'path', 'status'] as const) {
        if (!isNonEmptyString(resource[field])) {
          issues.push(issue(`$.resources[${index}].${field}`, 'invalid', `${field} must be a non-empty string`))
        }
      }
    })
  }
  issues.push(...validateReplay(value.replay))
  issues.push(...validateUsage(value.usage))
  if (!isRecord(value.output)) {
    issues.push(issue('$.output', 'invalid', 'output must be an object'))
  } else {
    if (!['equivalent', 'different', 'unverified'].includes(String(value.output.equivalence))) {
      issues.push(issue('$.output.equivalence', 'invalid', 'equivalence is not supported'))
    }
    if (!isNonEmptyString(value.output.notes)) {
      issues.push(issue('$.output.notes', 'invalid', 'notes must be a non-empty string'))
    }
  }
  if (!isRecord(value.cleanup)) {
    issues.push(issue('$.cleanup', 'invalid', 'cleanup must be an object'))
  } else {
    if (typeof value.cleanup.disposed !== 'boolean') {
      issues.push(issue('$.cleanup.disposed', 'invalid', 'disposed must be boolean'))
    }
    if (!isFiniteNumber(value.cleanup.leakedRegistrations) || value.cleanup.leakedRegistrations !== 0) {
      issues.push(issue('$.cleanup.leakedRegistrations', 'invalid', 'leakedRegistrations must be 0'))
    }
  }
  return issues
}

/** Validate and return a comparison report, or throw a structured error. */
export function assertComparisonReport(value: unknown): LegacyComparisonReport {
  const issues = validateComparisonReport(value)
  if (issues.length > 0) throw new InvalidComparisonReportError(issues)
  return value as LegacyComparisonReport
}
