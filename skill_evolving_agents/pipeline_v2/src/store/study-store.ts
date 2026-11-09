import { createHash } from 'node:crypto'
import { mkdir, open, readFile, rename, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { isDeepStrictEqual } from 'node:util'

import { DuplicateEventError, PipelineError } from '../contracts/errors.ts'
import type { StructuredIssue } from '../contracts/errors.ts'
import type { VerificationStatus } from '../contracts/evidence.ts'
import type { PipelineEvent } from '../contracts/events.ts'
import {
  runId as brandRunId,
  skillId as brandSkillId,
  traceId as brandTraceId,
} from '../contracts/ids.ts'
import type { EventId, FindingId, OperationId, RunId, SkillId, TraceId } from '../contracts/ids.ts'
import { isFiniteNumber, isNonEmptyString, isRecord, issue } from '../contracts/validation.ts'
import { assertEvent, EventLog } from '../core/event-log.ts'
import { projectEvents } from '../core/projections.ts'
import type { RunProjection, RunStatus } from '../core/projections.ts'
import type { EvaluationStage } from '../search/contracts.ts'

/**
 * Storage layout (a store directory):
 *
 * - `manifest.json` holds the store schema version and backend marker;
 * - `study.jsonl` is the append-only source of truth (event and record
 *   envelopes in commit order);
 * - `snapshot.json` is an atomically renamed derived index;
 * - `events.jsonl` is read once when migrating a version 1 event-only store
 *   and is deliberately left untouched for rollback evidence.
 *
 * Migration seam: bump `STUDY_STORE_SCHEMA_VERSION`, add a `migrateVersionN`
 * step that rewrites the log ahead of the manifest, and keep the `StudyStore`
 * facade unchanged. A future SQLite backend can implement the same facade while
 * retaining the schema version in the manifest.
 */

/** Current on-disk study-store schema. Version 1 is the legacy event-only layout. */
export const STUDY_STORE_SCHEMA_VERSION = 2 as const

/** Durable backend marker stored in the manifest. */
export const STUDY_STORE_BACKEND = 'jsonl-snapshot' as const

const MANIFEST_FILE = 'manifest.json'
const LOG_FILE = 'study.jsonl'
const SNAPSHOT_FILE = 'snapshot.json'
const LEGACY_EVENTS_FILE = 'events.jsonl'

/** A JSON-safe value accepted by policy and configuration version snapshots. */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue }

/** Experimental stages; only train and validation may feed search learning. */
export type SearchStage = 'train' | 'validation'

/** Discriminator for every non-event durable study record. */
export type StudyRecordKind =
  | 'trace/identity'
  | 'router/candidates'
  | 'benchmark/observation'
  | 'membership'
  | 'feedback/search'
  | 'skill/exposure'
  | 'policy/version'
  | 'config/version'

/** One routed skill and its deterministic score. */
export interface RouterCandidate {
  readonly skillId: SkillId
  readonly score: number
  readonly reason?: string
}

/** One side of a paired baseline/treatment observation. */
export interface BenchmarkArm {
  readonly passed: boolean
  readonly skillId?: SkillId
  readonly toolCalls: number
  readonly latencyMs?: number
  readonly costUsd?: number
  readonly failures?: number
}

/** Durable trace identity plus the hash of the trace content. */
export interface TraceIdentityRecord {
  readonly kind: 'trace/identity'
  readonly recordId: string
  readonly at: string
  readonly runId: RunId
  readonly traceId: TraceId
  readonly source: string
  readonly turns: number
  readonly contentHash: string
}

/** Durable router candidate batch. Order is the router rank order. */
export interface RouterCandidatesRecord {
  readonly kind: 'router/candidates'
  readonly recordId: string
  readonly at: string
  readonly runId: RunId
  readonly traceId?: TraceId
  readonly candidates: readonly RouterCandidate[]
}

/** One paired observation. Baseline and treatment always travel together. */
export interface BenchmarkObservationRecord {
  readonly kind: 'benchmark/observation'
  readonly recordId: string
  readonly at: string
  readonly runId: RunId
  readonly stage: EvaluationStage
  readonly taskId: string
  readonly groupId?: string
  readonly domain: string
  readonly baseline: BenchmarkArm
  readonly treatment: BenchmarkArm
  readonly efficiencyFailure: boolean
  readonly candidateId?: string
  readonly policyVersion?: string
  readonly configVersion?: string
}

/** One task's experimental membership. A task belongs to exactly one stage. */
export interface MembershipRecord {
  readonly kind: 'membership'
  readonly recordId: string
  readonly at: string
  readonly taskId: string
  readonly stage: EvaluationStage
  readonly groupId?: string
}

/** Calibrated feedback that may enter search history. Holdout is not representable. */
export interface SearchFeedbackRecord {
  readonly kind: 'feedback/search'
  readonly recordId: string
  readonly at: string
  readonly runId?: RunId
  readonly taskId: string
  readonly skillId: SkillId
  readonly adjustment: number
  readonly stage: SearchStage
  readonly source?: string
}

/** Whether a skill was exposed to, and activated by, a run. */
export interface SkillExposureRecord {
  readonly kind: 'skill/exposure'
  readonly recordId: string
  readonly at: string
  readonly runId: RunId
  readonly skillId: SkillId
  readonly exposed: boolean
  readonly activated: boolean
  readonly source?: string
}

/** One frozen policy or configuration version. */
export interface VersionRecord {
  readonly kind: 'policy/version' | 'config/version'
  readonly recordId: string
  readonly at: string
  readonly version: string
  readonly contentHash: string
  readonly payload?: JsonValue
}

/** The closed union of durable non-event study records. */
export type StudyRecord =
  | TraceIdentityRecord
  | RouterCandidatesRecord
  | BenchmarkObservationRecord
  | MembershipRecord
  | SearchFeedbackRecord
  | SkillExposureRecord
  | VersionRecord

/** Deterministic run summary derived from durable events. */
export interface RunSummary {
  readonly runId: RunId
  readonly status: RunStatus
  readonly eventCount: number
  readonly startedAt?: string
  readonly endedAt?: string
  readonly lastEventId?: string
  readonly traceIds: readonly TraceId[]
  readonly findingIds: readonly FindingId[]
}

/** A run summary plus its deterministic projection. */
export interface StudyRun extends RunSummary {
  readonly projection: RunProjection
}

/** One trace seen in a run, optionally carrying its content hash. */
export interface TraceState {
  readonly traceId: TraceId
  readonly runId: RunId
  readonly source: string
  readonly turns: number
  readonly at: string
  readonly contentHash?: string
}

/** One detected finding. */
export interface FindingState {
  readonly findingId: FindingId
  readonly runId: RunId
  readonly traceId: TraceId
  readonly detector: string
  readonly confidence: number
  readonly summary: string
  readonly eventId: EventId
  readonly at: string
}

/** One recorded diagnosis. */
export interface DiagnosisState {
  readonly findingId: FindingId
  readonly summary: string
  readonly eventId: EventId
  readonly at: string
}

/** One verification result derived from the event history. */
export interface VerificationState {
  readonly operationId: OperationId
  readonly status: VerificationStatus
  readonly summary: string
  readonly evidenceHash?: string
  readonly eventId: EventId
  readonly at: string
}

/** Aggregated benchmark cost, latency, tool calls, and failures for one run. */
export interface RunUsageSummary {
  readonly runId: RunId
  readonly observations: number
  readonly baselineToolCalls: number
  readonly treatmentToolCalls: number
  readonly baselineLatencyMs: number
  readonly treatmentLatencyMs: number
  readonly baselineCostUsd: number
  readonly treatmentCostUsd: number
  readonly failures: number
  readonly efficiencyFailures: number
}

/**
 * Complete deterministic state of a study store.
 *
 * Events remain the source of truth for runs, operations, resources, and
 * verifications; the projection is available through `getRun`/`replay`.
 */
export interface StudyState {
  readonly schemaVersion: typeof STUDY_STORE_SCHEMA_VERSION
  readonly runs: Readonly<Record<string, RunSummary>>
  readonly traces: Readonly<Record<string, TraceState>>
  readonly findings: Readonly<Record<string, FindingState>>
  readonly diagnoses: readonly DiagnosisState[]
  readonly verifications: readonly VerificationState[]
  readonly routerCandidates: readonly RouterCandidatesRecord[]
  readonly benchmarks: Readonly<Record<string, BenchmarkObservationRecord>>
  readonly memberships: Readonly<Record<string, MembershipRecord>>
  readonly feedback: readonly SearchFeedbackRecord[]
  readonly policyVersions: Readonly<Record<string, VersionRecord>>
  readonly configVersions: Readonly<Record<string, VersionRecord>>
  readonly skillExposures: Readonly<Record<string, SkillExposureRecord>>
  readonly usage: Readonly<Record<string, RunUsageSummary>>
}

/** Atomic snapshot/index persisted beside the append-only log. */
export interface StudySnapshot {
  readonly schemaVersion: typeof STUDY_STORE_SCHEMA_VERSION
  readonly generation: number
  readonly eventCount: number
  readonly recordCount: number
  readonly stateHash: string
  readonly updatedAt: string
  readonly state: StudyState
}

/** One integrity problem found by `verifyIntegrity`. */
export interface IntegrityIssue {
  readonly line: number
  readonly code: string
  readonly message: string
}

/** Integrity report for the durable log and its snapshot index. */
export interface IntegrityReport {
  readonly ok: boolean
  readonly schemaVersion: typeof STUDY_STORE_SCHEMA_VERSION
  readonly eventCount: number
  readonly recordCount: number
  readonly runIds: readonly string[]
  readonly snapshotMatches: boolean
  readonly issues: readonly IntegrityIssue[]
}

/** Options accepted by `openStudyStore`. */
export interface OpenStudyStoreOptions {
  /** Timestamp source for records and snapshots; tests may freeze it. */
  readonly clock?: () => string
}

/** Input for `recordTraceIdentity`. */
export interface TraceIdentityInput {
  readonly runId: string
  readonly traceId: string
  readonly source: string
  readonly turns: number
  readonly contentHash: string
}

/** Input candidate for `recordRouterCandidates`. */
export interface RouterCandidateInput {
  readonly skillId: string
  readonly score: number
  readonly reason?: string
}

/** Input for `recordRouterCandidates`. */
export interface RouterCandidatesInput {
  readonly runId: string
  readonly traceId?: string
  readonly candidates: readonly RouterCandidateInput[]
}

/** Input arm for `recordBenchmarkObservation`. */
export interface BenchmarkArmInput {
  readonly passed: boolean
  readonly skillId?: string
  readonly toolCalls: number
  readonly latencyMs?: number
  readonly costUsd?: number
  readonly failures?: number
}

/** Input for `recordBenchmarkObservation`. */
export interface BenchmarkObservationInput {
  readonly runId: string
  readonly stage: EvaluationStage
  readonly taskId: string
  readonly groupId?: string
  readonly domain: string
  readonly baseline: BenchmarkArmInput
  readonly treatment: BenchmarkArmInput
  readonly efficiencyFailure: boolean
  readonly candidateId?: string
  readonly policyVersion?: string
  readonly configVersion?: string
}

/** Input for `recordMembership`. */
export interface MembershipInput {
  readonly taskId: string
  readonly stage: EvaluationStage
  readonly groupId?: string
}

/** Input for `recordFeedback`, the search-learning boundary. */
export interface SearchFeedbackInput {
  readonly taskId: string
  readonly skillId: string
  readonly adjustment: number
  readonly stage: EvaluationStage
  readonly runId?: string
  readonly source?: string
}

/** Input for `recordSkillExposure`. */
export interface SkillExposureInput {
  readonly runId: string
  readonly skillId: string
  readonly exposed: boolean
  readonly activated: boolean
  readonly source?: string
}

/** Input for `recordPolicyVersion` and `recordConfigVersion`. */
export interface VersionInput {
  readonly version: string
  readonly payload?: JsonValue
}

/** The store path is not a directory or its manifest is unreadable. */
export class StoreCorruptionError extends PipelineError {
  constructor(message: string, details: Readonly<Record<string, unknown>> = {}) {
    super('store-corruption', message, details)
  }
}

/** A manifest declared a schema version this build cannot interpret. */
export class UnsupportedStoreSchemaVersionError extends PipelineError {
  constructor(found: number) {
    super('unsupported-store-schema-version', `unsupported study store schema version ${found}`, {
      found: String(found),
      supported: String(STUDY_STORE_SCHEMA_VERSION),
    })
  }
}

/** A batch attempted to append events from more than one run. */
export class MixedRunBatchError extends PipelineError {
  constructor(runIds: readonly string[]) {
    super('mixed-run-batch', 'an event batch must belong to exactly one run', { runIds })
  }
}

/** A record id was reused for different content. */
export class RecordConflictError extends PipelineError {
  constructor(kind: string, recordId: string) {
    super('record-conflict', `record ${recordId} already exists with different content`, {
      kind,
      recordId,
    })
  }
}

/** A trace identity was reused with a different hash or source. */
export class TraceIdentityConflictError extends PipelineError {
  constructor(traceKey: string) {
    super('trace-identity-conflict', 'trace identity already has different content', { traceKey })
  }
}

/** A benchmark task was observed twice with different data. */
export class DuplicateBenchmarkObservationError extends PipelineError {
  constructor(observationKey: string) {
    super('duplicate-benchmark-observation', 'benchmark observation key already exists', {
      observationKey,
    })
  }
}

/** A task or group tried to move to a different evaluation stage. */
export class MembershipConflictError extends PipelineError {
  constructor(taskId: string, existing: string, incoming: string) {
    super('membership-conflict', 'task membership conflicts with the recorded stage', {
      taskId,
      existing,
      incoming,
    })
  }
}

/** A task family would appear in two evaluation stages. */
export class StageLeakageError extends PipelineError {
  constructor(groupKey: string, stages: readonly string[]) {
    super('stage-leakage', 'task family appears in more than one evaluation stage', {
      groupKey,
      stages,
    })
  }
}

/** A policy or configuration version was reused with a different payload. */
export class VersionConflictError extends PipelineError {
  constructor(kind: string, version: string) {
    super('version-conflict', `version ${version} already has different content`, {
      kind,
      version,
    })
  }
}

/** A record referenced a run that has no durable event history. */
export class UnknownRunError extends PipelineError {
  constructor(runId: string) {
    super('unknown-run', `run ${runId} is not present in the study store`, { runId })
  }
}

/** A feedback write tried to move holdout evidence into search learning. */
export class HoldoutFeedbackRejectedError extends PipelineError {
  constructor(taskId: string, reason: string) {
    super('holdout-feedback-rejected', 'holdout feedback is sealed from search learning', {
      taskId,
      reason,
    })
  }
}

/** A record failed structural validation before it could be appended. */
export class InvalidRecordError extends PipelineError {
  readonly issues: readonly StructuredIssue[]

  constructor(kind: string, issues: readonly StructuredIssue[]) {
    super('invalid-record', `invalid study record ${kind}`, { kind, issues })
    this.issues = issues
  }
}

/** The store was used after `close()`. */
export class StoreClosedError extends PipelineError {
  constructor() {
    super('store-closed', 'study store is closed', {})
  }
}

/** An append, rename, or snapshot write failed. */
export class StorePersistenceError extends PipelineError {
  constructor(operation: string, cause: unknown) {
    super('store-persistence', `study store ${operation} failed`, {
      operation,
      cause: describeError(cause),
    })
  }
}

interface StoreManifest {
  readonly schemaVersion: number
  readonly backend: string
  readonly createdAt: string
}

interface LogEventEntry {
  readonly kind: 'event'
  readonly event: PipelineEvent
}

interface LogRecordEntry {
  readonly kind: 'record'
  readonly record: StudyRecord
}

type LogEntry = LogEventEntry | LogRecordEntry

interface RawEntry {
  readonly line: number
  readonly value: unknown
}

interface ReplayResult {
  readonly state: StudyState
  readonly logs: Map<string, EventLog>
  readonly eventsByRun: Map<string, PipelineEvent[]>
  readonly events: PipelineEvent[]
  readonly records: StudyRecord[]
  readonly eventIndex: Map<string, PipelineEvent>
  readonly recordIndex: Map<string, StudyRecord>
}

interface SnapshotMeta {
  readonly schemaVersion: number
  readonly generation: number
  readonly eventCount: number
  readonly recordCount: number
  readonly stateHash: string
}

interface ParsedRecord {
  readonly ok: boolean
  readonly record?: StudyRecord
  readonly issues: readonly StructuredIssue[]
}

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

function hashText(text: string): string {
  return createHash('sha256').update(text).digest('hex')
}

/** Hash arbitrary trace content so callers can record a stable identity. */
export function hashContent(content: string): string {
  return hashText(content)
}

function stableStringify(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (typeof value === 'object') {
    const entries: [string, unknown][] = Object.entries(value)
    const fields = entries
      .filter(([, child]) => child !== undefined)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, child]) => `${JSON.stringify(key)}:${stableStringify(child)}`)
    return `{${fields.join(',')}}`
  }
  return 'null'
}

function hashState(state: StudyState): string {
  return hashText(stableStringify(state))
}

/** Key of one task's membership. */
export function membershipKey(taskId: string): string {
  return taskId
}

/** Key of one paired benchmark observation. */
export function observationKey(stage: EvaluationStage, taskId: string): string {
  return `${stage}:${taskId}`
}

/** Key of one trace inside one run. */
export function traceKey(runId: string, traceId: string): string {
  return `${runId}::${traceId}`
}

/** Key of one skill exposure inside one run. */
export function exposureKey(runId: string, skillId: string): string {
  return `${runId}:${skillId}`
}

function makeRecordId(material: string): string {
  return `rec-${hashText(material).slice(0, 24)}`
}

function recordIdOf(record: StudyRecord): string {
  switch (record.kind) {
    case 'trace/identity':
      return makeRecordId(`trace/identity|${record.runId}|${record.traceId}`)
    case 'router/candidates':
      return makeRecordId(
        `router/candidates|${record.runId}|${record.traceId ?? ''}|${stableStringify(record.candidates)}`,
      )
    case 'benchmark/observation':
      return makeRecordId(`benchmark/observation|${record.stage}|${record.taskId}`)
    case 'membership':
      return makeRecordId(`membership|${record.taskId}`)
    case 'feedback/search':
      return makeRecordId(
        `feedback/search|${record.runId ?? ''}|${record.taskId}|${record.skillId}|${String(record.adjustment)}|${record.stage}|${record.source ?? ''}`,
      )
    case 'skill/exposure':
      return makeRecordId(
        `skill/exposure|${record.runId}|${record.skillId}|${String(record.exposed)}|${String(record.activated)}|${record.source ?? ''}`,
      )
    case 'policy/version':
    case 'config/version':
      return makeRecordId(`${record.kind}|${record.version}`)
    default: {
      const exhaustive: never = record
      void exhaustive
      return makeRecordId('unknown')
    }
  }
}

function assignRecordId(record: StudyRecord): StudyRecord {
  return { ...record, recordId: recordIdOf(record) }
}

function withoutAt(record: StudyRecord): object {
  const copy: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(record)) {
    if (key !== 'at') copy[key] = value
  }
  return copy
}

function sameRecordPayload(left: StudyRecord, right: StudyRecord): boolean {
  return isDeepStrictEqual(withoutAt(left), withoutAt(right))
}

function conflictForRecord(existing: StudyRecord, incoming: StudyRecord): PipelineError {
  switch (incoming.kind) {
    case 'benchmark/observation':
      return new DuplicateBenchmarkObservationError(observationKey(incoming.stage, incoming.taskId))
    case 'membership': {
      const existingStage = existing.kind === 'membership' ? existing.stage : 'unknown'
      return new MembershipConflictError(incoming.taskId, existingStage, incoming.stage)
    }
    case 'trace/identity':
      return new TraceIdentityConflictError(traceKey(incoming.runId, incoming.traceId))
    case 'policy/version':
    case 'config/version':
      return new VersionConflictError(incoming.kind, incoming.version)
    default:
      return new RecordConflictError(incoming.kind, incoming.recordId)
  }
}

function emptyState(): StudyState {
  return {
    schemaVersion: STUDY_STORE_SCHEMA_VERSION,
    runs: {},
    traces: {},
    findings: {},
    diagnoses: [],
    verifications: [],
    routerCandidates: [],
    benchmarks: {},
    memberships: {},
    feedback: [],
    policyVersions: {},
    configVersions: {},
    skillExposures: {},
    usage: {},
  }
}

function requireRun(state: StudyState, runId: RunId): void {
  if (state.runs[runId] === undefined) throw new UnknownRunError(runId)
}

function withRunTrace(state: StudyState, runId: RunId, trace: TraceId): StudyState {
  const run = state.runs[runId]
  if (run === undefined || run.traceIds.includes(trace)) return state
  return {
    ...state,
    runs: { ...state.runs, [runId]: { ...run, traceIds: [...run.traceIds, trace] } },
  }
}

function withRunFinding(state: StudyState, runId: RunId, finding: FindingId): StudyState {
  const run = state.runs[runId]
  if (run === undefined || run.findingIds.includes(finding)) return state
  return {
    ...state,
    runs: { ...state.runs, [runId]: { ...run, findingIds: [...run.findingIds, finding] } },
  }
}

function applyEvent(state: StudyState, event: PipelineEvent): StudyState {
  const runIdValue = event.runId
  const previous: RunSummary = state.runs[runIdValue] ?? {
    runId: runIdValue,
    status: 'not_started',
    eventCount: 0,
    traceIds: [],
    findingIds: [],
  }
  let run: RunSummary = {
    ...previous,
    eventCount: previous.eventCount + 1,
    lastEventId: event.id,
  }
  if (event.type === 'run/started') {
    run = { ...run, status: 'running', startedAt: event.at }
  } else if (event.type === 'run/completed') {
    run = { ...run, status: 'completed', endedAt: event.at }
  } else if (event.type === 'run/failed') {
    run = { ...run, status: 'failed', endedAt: event.at }
  }

  let traces = state.traces
  let findings = state.findings
  let diagnoses = state.diagnoses
  let verifications = state.verifications

  if (event.type === 'trace/ingested') {
    const key = traceKey(runIdValue, event.payload.traceId)
    const existing = traces[key]
    if (
      existing !== undefined &&
      existing.contentHash !== undefined &&
      (existing.source !== event.payload.source || existing.turns !== event.payload.turns)
    ) {
      throw new TraceIdentityConflictError(key)
    }
    const contentHash = existing?.contentHash
    const trace: TraceState = {
      traceId: event.payload.traceId,
      runId: runIdValue,
      source: event.payload.source,
      turns: event.payload.turns,
      at: event.at,
      ...(contentHash === undefined ? {} : { contentHash }),
    }
    traces = { ...traces, [key]: trace }
  } else if (event.type === 'finding/detected') {
    const finding: FindingState = {
      findingId: event.payload.findingId,
      runId: runIdValue,
      traceId: event.payload.traceId,
      detector: event.payload.detector,
      confidence: event.payload.confidence,
      summary: event.payload.summary,
      eventId: event.id,
      at: event.at,
    }
    findings = { ...findings, [event.payload.findingId]: finding }
  } else if (event.type === 'diagnosis/recorded') {
    diagnoses = [
      ...diagnoses,
      {
        findingId: event.payload.findingId,
        summary: event.payload.summary,
        eventId: event.id,
        at: event.at,
      },
    ]
  } else if (event.type === 'verification/completed') {
    const evidenceHash = event.payload.evidenceHash
    verifications = [
      ...verifications,
      {
        operationId: event.payload.operationId,
        status: event.payload.status,
        summary: event.payload.summary,
        eventId: event.id,
        at: event.at,
        ...(evidenceHash === undefined ? {} : { evidenceHash }),
      },
    ]
  }

  let next: StudyState = {
    ...state,
    runs: { ...state.runs, [runIdValue]: run },
    traces,
    findings,
    diagnoses,
    verifications,
  }
  if (event.type === 'trace/ingested') {
    next = withRunTrace(next, runIdValue, event.payload.traceId)
  }
  if (event.type === 'finding/detected') {
    next = withRunFinding(next, runIdValue, event.payload.findingId)
  }
  return next
}

function ensureMembership(
  state: StudyState,
  taskId: string,
  groupId: string | undefined,
  stage: EvaluationStage,
  at: string,
): StudyState {
  const existing = state.memberships[taskId]
  if (existing !== undefined) {
    if (existing.stage !== stage) {
      throw new MembershipConflictError(taskId, existing.stage, stage)
    }
    if (existing.groupId === groupId) return state
    if (existing.groupId !== undefined && groupId !== undefined) {
      throw new MembershipConflictError(taskId, existing.stage, stage)
    }
    for (const row of Object.values(state.memberships)) {
      if (row.taskId !== taskId && groupId !== undefined && row.groupId === groupId && row.stage !== stage) {
        throw new StageLeakageError(`group:${groupId}`, [row.stage, stage])
      }
    }
    const updated: MembershipRecord = { ...existing, ...(groupId === undefined ? {} : { groupId }) }
    return { ...state, memberships: { ...state.memberships, [taskId]: updated } }
  }
  for (const row of Object.values(state.memberships)) {
    if (groupId !== undefined && row.groupId === groupId && row.stage !== stage) {
      throw new StageLeakageError(`group:${groupId}`, [row.stage, stage])
    }
  }
  const draft: MembershipRecord = {
    kind: 'membership',
    recordId: '',
    at,
    taskId,
    stage,
    ...(groupId === undefined ? {} : { groupId }),
  }
  const membership: MembershipRecord = { ...draft, recordId: recordIdOf(draft) }
  return { ...state, memberships: { ...state.memberships, [taskId]: membership } }
}

function addUsage(state: StudyState, record: BenchmarkObservationRecord): StudyState {
  const previous: RunUsageSummary = state.usage[record.runId] ?? {
    runId: record.runId,
    observations: 0,
    baselineToolCalls: 0,
    treatmentToolCalls: 0,
    baselineLatencyMs: 0,
    treatmentLatencyMs: 0,
    baselineCostUsd: 0,
    treatmentCostUsd: 0,
    failures: 0,
    efficiencyFailures: 0,
  }
  const next: RunUsageSummary = {
    ...previous,
    observations: previous.observations + 1,
    baselineToolCalls: previous.baselineToolCalls + record.baseline.toolCalls,
    treatmentToolCalls: previous.treatmentToolCalls + record.treatment.toolCalls,
    baselineLatencyMs: previous.baselineLatencyMs + (record.baseline.latencyMs ?? 0),
    treatmentLatencyMs: previous.treatmentLatencyMs + (record.treatment.latencyMs ?? 0),
    baselineCostUsd: previous.baselineCostUsd + (record.baseline.costUsd ?? 0),
    treatmentCostUsd: previous.treatmentCostUsd + (record.treatment.costUsd ?? 0),
    failures: previous.failures + (record.baseline.failures ?? 0) + (record.treatment.failures ?? 0),
    efficiencyFailures: previous.efficiencyFailures + (record.efficiencyFailure ? 1 : 0),
  }
  return { ...state, usage: { ...state.usage, [record.runId]: next } }
}

function applyVersion(state: StudyState, record: VersionRecord): StudyState {
  const versions = record.kind === 'policy/version' ? state.policyVersions : state.configVersions
  const existing = versions[record.version]
  if (existing !== undefined) {
    if (existing.contentHash !== record.contentHash) {
      throw new VersionConflictError(record.kind, record.version)
    }
    return state
  }
  const nextVersions = { ...versions, [record.version]: record }
  return record.kind === 'policy/version'
    ? { ...state, policyVersions: nextVersions }
    : { ...state, configVersions: nextVersions }
}

function isSearchStage(value: unknown): value is SearchStage {
  return value === 'train' || value === 'validation'
}

function applyRecord(state: StudyState, record: StudyRecord): StudyState {
  switch (record.kind) {
    case 'trace/identity': {
      requireRun(state, record.runId)
      const key = traceKey(record.runId, record.traceId)
      const existing = state.traces[key]
      const existingHash = existing?.contentHash
      if (
        existing !== undefined &&
        (existing.source !== record.source ||
          existing.turns !== record.turns ||
          (existingHash !== undefined && existingHash !== record.contentHash))
      ) {
        throw new TraceIdentityConflictError(key)
      }
      const trace: TraceState = {
        traceId: record.traceId,
        runId: record.runId,
        source: record.source,
        turns: record.turns,
        at: record.at,
        contentHash: record.contentHash,
      }
      const next: StudyState = { ...state, traces: { ...state.traces, [key]: trace } }
      return withRunTrace(next, record.runId, record.traceId)
    }
    case 'router/candidates': {
      requireRun(state, record.runId)
      return { ...state, routerCandidates: [...state.routerCandidates, record] }
    }
    case 'benchmark/observation': {
      requireRun(state, record.runId)
      const key = observationKey(record.stage, record.taskId)
      if (state.benchmarks[key] !== undefined) {
        throw new DuplicateBenchmarkObservationError(key)
      }
      const withMembership = ensureMembership(
        state,
        record.taskId,
        record.groupId,
        record.stage,
        record.at,
      )
      return {
        ...withMembership,
        benchmarks: { ...withMembership.benchmarks, [key]: record },
        usage: addUsage(withMembership, record).usage,
      }
    }
    case 'membership':
      return ensureMembership(state, record.taskId, record.groupId, record.stage, record.at)
    case 'feedback/search': {
      if (!isSearchStage(record.stage)) {
        throw new HoldoutFeedbackRejectedError(
          record.taskId,
          'holdout feedback cannot be represented as search feedback',
        )
      }
      const membership = state.memberships[record.taskId]
      if (membership?.stage === 'holdout') {
        throw new HoldoutFeedbackRejectedError(record.taskId, 'task membership is sealed holdout')
      }
      if (membership !== undefined && membership.stage !== record.stage) {
        throw new MembershipConflictError(record.taskId, membership.stage, record.stage)
      }
      return { ...state, feedback: [...state.feedback, record] }
    }
    case 'skill/exposure': {
      requireRun(state, record.runId)
      if (record.activated && !record.exposed) {
        throw new InvalidRecordError('skill/exposure', [
          issue('$.activated', 'invalid', 'activated requires exposed'),
        ])
      }
      const key = exposureKey(record.runId, record.skillId)
      return { ...state, skillExposures: { ...state.skillExposures, [key]: record } }
    }
    case 'policy/version':
    case 'config/version':
      return applyVersion(state, record)
    default: {
      const exhaustive: never = record
      void exhaustive
      return state
    }
  }
}

function readString(value: unknown, path: string, issues: StructuredIssue[]): string {
  if (!isNonEmptyString(value)) {
    issues.push(issue(path, 'invalid', 'must be a non-empty string'))
    return ''
  }
  return value
}

function readOptionalString(
  value: unknown,
  path: string,
  issues: StructuredIssue[],
): string | undefined {
  if (value === undefined) return undefined
  if (!isNonEmptyString(value)) {
    issues.push(issue(path, 'invalid', 'must be a non-empty string when present'))
    return undefined
  }
  return value
}

function readTimestamp(value: unknown, path: string, issues: StructuredIssue[]): string {
  const text = readString(value, path, issues)
  if (text.length > 0 && Number.isNaN(Date.parse(text))) {
    issues.push(issue(path, 'invalid', 'must be an ISO timestamp'))
  }
  return text
}

function readBoolean(value: unknown, path: string, issues: StructuredIssue[]): boolean {
  if (typeof value !== 'boolean') {
    issues.push(issue(path, 'invalid', 'must be boolean'))
    return false
  }
  return value
}

function readNonNegativeInteger(value: unknown, path: string, issues: StructuredIssue[]): number {
  if (!isFiniteNumber(value) || !Number.isInteger(value) || value < 0) {
    issues.push(issue(path, 'invalid', 'must be a non-negative integer'))
    return 0
  }
  return value
}

function readNonNegativeFinite(value: unknown, path: string, issues: StructuredIssue[]): number {
  if (!isFiniteNumber(value) || value < 0) {
    issues.push(issue(path, 'invalid', 'must be a non-negative finite number'))
    return 0
  }
  return value
}

function readFiniteNumber(value: unknown, path: string, issues: StructuredIssue[]): number {
  if (!isFiniteNumber(value)) {
    issues.push(issue(path, 'invalid', 'must be a finite number'))
    return 0
  }
  return value
}

function readOptionalNonNegativeFinite(
  value: unknown,
  path: string,
  issues: StructuredIssue[],
): number | undefined {
  if (value === undefined) return undefined
  return readNonNegativeFinite(value, path, issues)
}

function readOptionalNonNegativeInteger(
  value: unknown,
  path: string,
  issues: StructuredIssue[],
): number | undefined {
  if (value === undefined) return undefined
  return readNonNegativeInteger(value, path, issues)
}

function readRunId(value: unknown, path: string, issues: StructuredIssue[]): RunId | undefined {
  if (!isNonEmptyString(value)) {
    issues.push(issue(path, 'invalid', 'must be a non-empty string'))
    return undefined
  }
  return brandRunId(value)
}

function readTraceId(
  value: unknown,
  path: string,
  issues: StructuredIssue[],
): TraceId | undefined {
  if (!isNonEmptyString(value)) {
    issues.push(issue(path, 'invalid', 'must be a non-empty string'))
    return undefined
  }
  return brandTraceId(value)
}

function readSkillId(
  value: unknown,
  path: string,
  issues: StructuredIssue[],
): SkillId | undefined {
  if (!isNonEmptyString(value)) {
    issues.push(issue(path, 'invalid', 'must be a non-empty string'))
    return undefined
  }
  return brandSkillId(value)
}

function readOptionalSkillId(
  value: unknown,
  path: string,
  issues: StructuredIssue[],
): SkillId | undefined {
  if (value === undefined) return undefined
  return readSkillId(value, path, issues)
}

function readStage(
  value: unknown,
  path: string,
  issues: StructuredIssue[],
): EvaluationStage | undefined {
  if (value === 'train' || value === 'validation' || value === 'holdout') return value
  issues.push(issue(path, 'invalid', 'stage must be train, validation, or holdout'))
  return undefined
}

function readSearchStage(
  value: unknown,
  path: string,
  issues: StructuredIssue[],
): SearchStage | undefined {
  if (value === 'train' || value === 'validation') return value
  issues.push(issue(path, 'invalid', 'search feedback stage must be train or validation'))
  return undefined
}

function readArm(value: unknown, path: string, issues: StructuredIssue[]): BenchmarkArm {
  if (!isRecord(value)) {
    issues.push(issue(path, 'invalid', 'benchmark arm must be an object'))
    return { passed: false, toolCalls: 0 }
  }
  const passed = readBoolean(value.passed, `${path}.passed`, issues)
  const toolCalls = readNonNegativeInteger(value.toolCalls, `${path}.toolCalls`, issues)
  const skillIdValue = readOptionalSkillId(value.skillId, `${path}.skillId`, issues)
  const latencyMs = readOptionalNonNegativeFinite(value.latencyMs, `${path}.latencyMs`, issues)
  const costUsd = readOptionalNonNegativeFinite(value.costUsd, `${path}.costUsd`, issues)
  const failures = readOptionalNonNegativeInteger(value.failures, `${path}.failures`, issues)
  return {
    passed,
    toolCalls,
    ...(skillIdValue === undefined ? {} : { skillId: skillIdValue }),
    ...(latencyMs === undefined ? {} : { latencyMs }),
    ...(costUsd === undefined ? {} : { costUsd }),
    ...(failures === undefined ? {} : { failures }),
  }
}

function readCandidates(value: unknown, issues: StructuredIssue[]): readonly RouterCandidate[] {
  if (!Array.isArray(value)) {
    issues.push(issue('$.candidates', 'invalid', 'candidates must be an array'))
    return []
  }
  const candidates: RouterCandidate[] = []
  value.forEach((candidate, index) => {
    const path = `$.candidates[${index}]`
    if (!isRecord(candidate)) {
      issues.push(issue(path, 'invalid', 'candidate must be an object'))
      return
    }
    const skill = readSkillId(candidate.skillId, `${path}.skillId`, issues)
    if (skill === undefined) return
    const score = candidate.score
    if (!isFiniteNumber(score) || score < 0 || score > 1) {
      issues.push(issue(`${path}.score`, 'invalid', 'score must be between 0 and 1'))
      return
    }
    const reason = readOptionalString(candidate.reason, `${path}.reason`, issues)
    candidates.push({
      skillId: skill,
      score,
      ...(reason === undefined ? {} : { reason }),
    })
  })
  const skills = new Set<string>()
  for (const candidate of candidates) {
    if (skills.has(candidate.skillId)) {
      issues.push(issue('$.candidates', 'invalid', 'candidate skill ids must be unique'))
    }
    skills.add(candidate.skillId)
  }
  return candidates
}

function readJsonValue(value: unknown, path: string, issues: StructuredIssue[]): JsonValue {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      issues.push(issue(path, 'invalid', 'number must be finite'))
      return 0
    }
    return value
  }
  if (Array.isArray(value)) {
    return value.map((child, index) => readJsonValue(child, `${path}[${index}]`, issues))
  }
  if (isRecord(value)) {
    const result: Record<string, JsonValue> = {}
    for (const [key, child] of Object.entries(value)) {
      result[key] = readJsonValue(child, `${path}.${key}`, issues)
    }
    return result
  }
  issues.push(issue(path, 'invalid', 'value must be JSON-serializable'))
  return null
}

function readRecordKind(value: unknown, issues: StructuredIssue[]): StudyRecordKind | undefined {
  if (
    value === 'trace/identity' ||
    value === 'router/candidates' ||
    value === 'benchmark/observation' ||
    value === 'membership' ||
    value === 'feedback/search' ||
    value === 'skill/exposure' ||
    value === 'policy/version' ||
    value === 'config/version'
  ) {
    return value
  }
  issues.push(issue('$.kind', 'invalid', 'record kind is not supported'))
  return undefined
}

function parseStudyRecord(value: unknown): ParsedRecord {
  if (!isRecord(value)) {
    return { ok: false, issues: [issue('$', 'invalid', 'record must be an object')] }
  }
  const issues: StructuredIssue[] = []
  const kind = readRecordKind(value.kind, issues)
  const recordId = readString(value.recordId, '$.recordId', issues)
  const at = readTimestamp(value.at, '$.at', issues)
  if (kind === undefined) return { ok: false, issues }

  let record: StudyRecord
  switch (kind) {
    case 'trace/identity': {
      const run = readRunId(value.runId, '$.runId', issues)
      const trace = readTraceId(value.traceId, '$.traceId', issues)
      const source = readString(value.source, '$.source', issues)
      const turns = readNonNegativeInteger(value.turns, '$.turns', issues)
      const contentHash = readString(value.contentHash, '$.contentHash', issues)
      if (run === undefined || trace === undefined) return { ok: false, issues }
      record = { kind, recordId, at, runId: run, traceId: trace, source, turns, contentHash }
      break
    }
    case 'router/candidates': {
      const run = readRunId(value.runId, '$.runId', issues)
      const trace = value.traceId === undefined
        ? undefined
        : readTraceId(value.traceId, '$.traceId', issues)
      const candidates = readCandidates(value.candidates, issues)
      if (run === undefined) return { ok: false, issues }
      record = {
        kind,
        recordId,
        at,
        runId: run,
        ...(trace === undefined ? {} : { traceId: trace }),
        candidates,
      }
      break
    }
    case 'benchmark/observation': {
      const run = readRunId(value.runId, '$.runId', issues)
      const stage = readStage(value.stage, '$.stage', issues)
      const taskId = readString(value.taskId, '$.taskId', issues)
      const groupId = readOptionalString(value.groupId, '$.groupId', issues)
      const domain = readString(value.domain, '$.domain', issues)
      const baseline = readArm(value.baseline, '$.baseline', issues)
      const treatment = readArm(value.treatment, '$.treatment', issues)
      const efficiencyFailure = readBoolean(value.efficiencyFailure, '$.efficiencyFailure', issues)
      const candidateId = readOptionalString(value.candidateId, '$.candidateId', issues)
      const policyVersion = readOptionalString(value.policyVersion, '$.policyVersion', issues)
      const configVersion = readOptionalString(value.configVersion, '$.configVersion', issues)
      if (run === undefined || stage === undefined) return { ok: false, issues }
      record = {
        kind,
        recordId,
        at,
        runId: run,
        stage,
        taskId,
        domain,
        baseline,
        treatment,
        efficiencyFailure,
        ...(groupId === undefined ? {} : { groupId }),
        ...(candidateId === undefined ? {} : { candidateId }),
        ...(policyVersion === undefined ? {} : { policyVersion }),
        ...(configVersion === undefined ? {} : { configVersion }),
      }
      break
    }
    case 'membership': {
      const taskId = readString(value.taskId, '$.taskId', issues)
      const stage = readStage(value.stage, '$.stage', issues)
      const groupId = readOptionalString(value.groupId, '$.groupId', issues)
      if (stage === undefined) return { ok: false, issues }
      record = {
        kind,
        recordId,
        at,
        taskId,
        stage,
        ...(groupId === undefined ? {} : { groupId }),
      }
      break
    }
    case 'feedback/search': {
      const taskId = readString(value.taskId, '$.taskId', issues)
      const skill = readSkillId(value.skillId, '$.skillId', issues)
      const adjustment = readFiniteNumber(value.adjustment, '$.adjustment', issues)
      const stage = readSearchStage(value.stage, '$.stage', issues)
      const run = value.runId === undefined ? undefined : readRunId(value.runId, '$.runId', issues)
      const source = readOptionalString(value.source, '$.source', issues)
      if (skill === undefined || stage === undefined) return { ok: false, issues }
      record = {
        kind,
        recordId,
        at,
        taskId,
        skillId: skill,
        adjustment,
        stage,
        ...(run === undefined ? {} : { runId: run }),
        ...(source === undefined ? {} : { source }),
      }
      break
    }
    case 'skill/exposure': {
      const run = readRunId(value.runId, '$.runId', issues)
      const skill = readSkillId(value.skillId, '$.skillId', issues)
      const exposed = readBoolean(value.exposed, '$.exposed', issues)
      const activated = readBoolean(value.activated, '$.activated', issues)
      const source = readOptionalString(value.source, '$.source', issues)
      if (run === undefined || skill === undefined) return { ok: false, issues }
      record = {
        kind,
        recordId,
        at,
        runId: run,
        skillId: skill,
        exposed,
        activated,
        ...(source === undefined ? {} : { source }),
      }
      break
    }
    case 'policy/version':
    case 'config/version': {
      const version = readString(value.version, '$.version', issues)
      const contentHash = readString(value.contentHash, '$.contentHash', issues)
      const payload = value.payload === undefined
        ? undefined
        : readJsonValue(value.payload, '$.payload', issues)
      const expectedContentHash = hashText(
        stableStringify(payload === undefined ? null : payload),
      )
      if (contentHash !== expectedContentHash) {
        issues.push(issue('$.contentHash', 'invalid', 'contentHash does not match the payload'))
      }
      record = {
        kind,
        recordId,
        at,
        version,
        contentHash,
        ...(payload === undefined ? {} : { payload }),
      }
      break
    }
    default: {
      const exhaustive: never = kind
      issues.push(issue('$.kind', 'invalid', `unsupported record kind ${String(exhaustive)}`))
      return { ok: false, issues }
    }
  }

  const expected = recordIdOf(record)
  if (recordId !== expected) {
    issues.push(issue('$.recordId', 'invalid', 'recordId does not match the record content'))
  }
  if (issues.length > 0) return { ok: false, issues }
  return { ok: true, record, issues }
}

/** Validate one durable study record without throwing. */
export function validateStudyRecord(value: unknown): readonly StructuredIssue[] {
  const parsed = parseStudyRecord(value)
  return parsed.ok ? [] : parsed.issues
}

/** Validate and return one durable study record, or throw a structured error. */
export function assertStudyRecord(value: unknown): StudyRecord {
  const parsed = parseStudyRecord(value)
  if (!parsed.ok || parsed.record === undefined) {
    throw new InvalidRecordError('unknown', parsed.issues)
  }
  return parsed.record
}

function parseRawEntries(text: string): RawEntry[] {
  const entries: RawEntry[] = []
  const lines = text.split(/\r?\n/)
  for (const [index, line] of lines.entries()) {
    if (line.trim().length === 0) continue
    let value: unknown
    try {
      value = JSON.parse(line)
    } catch (error) {
      throw new StoreCorruptionError('log line is not valid JSON', {
        line: index + 1,
        cause: describeError(error),
      })
    }
    entries.push({ line: index + 1, value })
  }
  return entries
}

function validateReplayEvent(value: unknown, line: number): PipelineEvent {
  try {
    return assertEvent(value)
  } catch (error) {
    if (error instanceof PipelineError) {
      throw new StoreCorruptionError('event failed validation during replay', {
        line,
        code: error.code,
        message: error.message,
      })
    }
    throw error
  }
}

function validateReplayRecord(value: unknown, line: number): StudyRecord {
  try {
    return assertStudyRecord(value)
  } catch (error) {
    if (error instanceof PipelineError) {
      throw new StoreCorruptionError('record failed validation during replay', {
        line,
        code: error.code,
        message: error.message,
      })
    }
    throw error
  }
}

function replayLog(entries: readonly RawEntry[]): ReplayResult {
  let state = emptyState()
  const logs = new Map<string, EventLog>()
  const eventsByRun = new Map<string, PipelineEvent[]>()
  const events: PipelineEvent[] = []
  const records: StudyRecord[] = []
  const eventIndex = new Map<string, PipelineEvent>()
  const recordIndex = new Map<string, StudyRecord>()

  for (const entry of entries) {
    const value = entry.value
    if (!isRecord(value) || (value.kind !== 'event' && value.kind !== 'record')) {
      throw new StoreCorruptionError('log entry must be an event or record envelope', {
        line: entry.line,
      })
    }
    if (value.kind === 'event') {
      const event = validateReplayEvent(value.event, entry.line)
      if (eventIndex.has(event.id)) {
        throw new StoreCorruptionError('duplicate event id in durable log', {
          line: entry.line,
          eventId: event.id,
        })
      }
      const log = logs.get(event.runId) ?? new EventLog()
      try {
        log.append(event)
      } catch (error) {
        throw new StoreCorruptionError('event transition failed during replay', {
          line: entry.line,
          cause: describeError(error),
        })
      }
      logs.set(event.runId, log)
      const runEvents = eventsByRun.get(event.runId)
      if (runEvents === undefined) eventsByRun.set(event.runId, [event])
      else runEvents.push(event)
      events.push(event)
      eventIndex.set(event.id, event)
      state = applyEvent(state, event)
    } else {
      const record = validateReplayRecord(value.record, entry.line)
      const existing = recordIndex.get(record.recordId)
      if (existing !== undefined) {
        if (sameRecordPayload(existing, record)) continue
        throw conflictForRecord(existing, record)
      }
      state = applyRecord(state, record)
      records.push(record)
      recordIndex.set(record.recordId, record)
    }
  }

  return { state, logs, eventsByRun, events, records, eventIndex, recordIndex }
}

function serializeLogEntry(entry: LogEntry): string {
  const serialized = JSON.stringify(entry)
  if (serialized === undefined) {
    throw new StorePersistenceError('log', new Error('log entry is not serializable'))
  }
  return serialized
}

async function readText(path: string): Promise<string | undefined> {
  try {
    return await readFile(path, 'utf8')
  } catch (error) {
    if (error instanceof Error && 'code' in error && error.code === 'ENOENT') return undefined
    throw new StorePersistenceError('read', error)
  }
}

async function writeAtomic(target: string, content: string): Promise<void> {
  const temporary = `${target}.tmp-${process.pid}-${Math.floor(Math.random() * 1_000_000)}`
  try {
    const handle = await open(temporary, 'w')
    try {
      await handle.writeFile(content, 'utf8')
      await handle.sync()
    } finally {
      await handle.close()
    }
    await rename(temporary, target)
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => undefined)
    throw error
  }
}

async function appendDurable(target: string, content: string): Promise<void> {
  const handle = await open(target, 'a')
  try {
    await handle.writeFile(content, 'utf8')
    await handle.sync()
  } finally {
    await handle.close()
  }
}

async function ensureDirectory(path: string): Promise<void> {
  try {
    await mkdir(path, { recursive: true })
  } catch (error) {
    throw new StorePersistenceError('mkdir', error)
  }
}

async function ensureFile(path: string): Promise<void> {
  try {
    const handle = await open(path, 'a')
    await handle.close()
  } catch (error) {
    throw new StorePersistenceError('create', error)
  }
}

function serializeManifest(createdAt: string): string {
  const manifest: StoreManifest = {
    schemaVersion: STUDY_STORE_SCHEMA_VERSION,
    backend: STUDY_STORE_BACKEND,
    createdAt,
  }
  const serialized = JSON.stringify(manifest, undefined, 2)
  if (serialized === undefined) {
    throw new StorePersistenceError('manifest', new Error('manifest is not serializable'))
  }
  return `${serialized}\n`
}

async function readManifest(storePath: string): Promise<StoreManifest | undefined> {
  const path = join(storePath, MANIFEST_FILE)
  const text = await readText(path)
  if (text === undefined) return undefined
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch (error) {
    throw new StoreCorruptionError('manifest is not valid JSON', {
      path,
      cause: describeError(error),
    })
  }
  if (!isRecord(value)) throw new StoreCorruptionError('manifest must be an object', { path })
  if (!isFiniteNumber(value.schemaVersion) || !Number.isInteger(value.schemaVersion)) {
    throw new StoreCorruptionError('manifest schemaVersion must be an integer', { path })
  }
  return {
    schemaVersion: value.schemaVersion,
    backend: isNonEmptyString(value.backend) ? value.backend : 'unknown',
    // Older manifests may omit createdAt; opening supplies the current clock.
    createdAt: isNonEmptyString(value.createdAt) ? value.createdAt : '',
  }
}

async function migrateVersionOne(
  storePath: string,
  createdAt: string,
): Promise<void> {
  const legacyPath = join(storePath, LEGACY_EVENTS_FILE)
  const legacyText = await readText(legacyPath)
  if (legacyText === undefined) {
    throw new StoreCorruptionError('v1 store is missing its legacy event file', {
      path: legacyPath,
    })
  }
  const entries = parseRawEntries(legacyText)
  const logs = new Map<string, EventLog>()
  const migrated: LogEntry[] = []
  for (const entry of entries) {
    let event: PipelineEvent
    try {
      event = assertEvent(entry.value)
    } catch (error) {
      throw new StoreCorruptionError('v1 event failed validation', {
        line: entry.line,
        cause: describeError(error),
      })
    }
    const log = logs.get(event.runId) ?? new EventLog()
    try {
      log.append(event)
    } catch (error) {
      throw new StoreCorruptionError('v1 event transition failed', {
        line: entry.line,
        cause: describeError(error),
      })
    }
    logs.set(event.runId, log)
    migrated.push({ kind: 'event', event })
  }
  const logText = migrated.map(serializeLogEntry).join('\n')
  await writeAtomic(join(storePath, LOG_FILE), logText.length === 0 ? '' : `${logText}\n`)
  await writeAtomic(join(storePath, MANIFEST_FILE), serializeManifest(createdAt))
}

function parseSnapshotMeta(text: string): SnapshotMeta | undefined {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    return undefined
  }
  if (!isRecord(value)) return undefined
  const { schemaVersion, generation, eventCount, recordCount, stateHash } = value
  if (!isFiniteNumber(schemaVersion) || !Number.isInteger(schemaVersion)) return undefined
  if (!isFiniteNumber(generation) || !Number.isInteger(generation) || generation < 0) return undefined
  if (!isFiniteNumber(eventCount) || !Number.isInteger(eventCount) || eventCount < 0) return undefined
  if (!isFiniteNumber(recordCount) || !Number.isInteger(recordCount) || recordCount < 0) return undefined
  if (!isNonEmptyString(stateHash)) return undefined
  return { schemaVersion, generation, eventCount, recordCount, stateHash }
}

/**
 * Durable, append-oriented study store.
 *
 * The append-only `study.jsonl` log is the source of truth. `snapshot.json` is
 * an atomically rewritten index derived from it; opening replays the log and
 * verifies/rebuilds the snapshot, so a crash between the two is recoverable.
 */
export class StudyStore {
  readonly schemaVersion = STUDY_STORE_SCHEMA_VERSION
  readonly storePath: string
  readonly createdAt: string
  readonly migratedFrom: number | undefined

  private readonly clock: () => string
  private readonly logs: Map<string, EventLog>
  private readonly eventsByRun: Map<string, PipelineEvent[]>
  private readonly allEvents: PipelineEvent[]
  private readonly records: StudyRecord[]
  private readonly eventIndex: Map<string, PipelineEvent>
  private readonly recordIndex: Map<string, StudyRecord>
  private state: StudyState
  private generation = 0
  private closed = false
  private snapshotDirty = false
  private queue: Promise<void> = Promise.resolve()

  private constructor(
    storePath: string,
    clock: () => string,
    createdAt: string,
    migratedFrom: number | undefined,
    replay: ReplayResult,
  ) {
    this.storePath = storePath
    this.clock = clock
    this.createdAt = createdAt
    this.migratedFrom = migratedFrom
    this.logs = replay.logs
    this.eventsByRun = replay.eventsByRun
    this.allEvents = replay.events
    this.records = replay.records
    this.eventIndex = replay.eventIndex
    this.recordIndex = replay.recordIndex
    this.state = replay.state
  }

  /** Open or create a durable store rooted at `storePath`. */
  static async open(
    storePath: string,
    options: OpenStudyStoreOptions = {},
  ): Promise<StudyStore> {
    if (!isNonEmptyString(storePath)) {
      throw new StoreCorruptionError('store path must be a non-empty string')
    }
    await ensureDirectory(storePath)
    const clock = options.clock ?? (() => new Date().toISOString())
    let manifest = await readManifest(storePath)
    let migratedFrom: number | undefined

    if (manifest === undefined) {
      const legacyPath = join(storePath, LEGACY_EVENTS_FILE)
      const legacy = await readText(legacyPath)
      if (legacy !== undefined) {
        await migrateVersionOne(storePath, clock())
        migratedFrom = 1
      } else {
        const existingLog = await readText(join(storePath, LOG_FILE))
        const existingSnapshot = await readText(join(storePath, SNAPSHOT_FILE))
        if (existingLog !== undefined || existingSnapshot !== undefined) {
          throw new StoreCorruptionError('store contains data but no manifest', {
            path: storePath,
          })
        }
        await writeAtomic(join(storePath, MANIFEST_FILE), serializeManifest(clock()))
      }
      manifest = await readManifest(storePath)
      if (manifest === undefined) {
        throw new StoreCorruptionError('manifest was not created', { path: storePath })
      }
    }

    const createdAt = manifest.createdAt.length > 0 ? manifest.createdAt : clock()
    if (manifest.schemaVersion === 1) {
      await migrateVersionOne(storePath, createdAt)
      migratedFrom = 1
      manifest = await readManifest(storePath)
      if (manifest === undefined) {
        throw new StoreCorruptionError('manifest was not migrated', { path: storePath })
      }
    }
    if (manifest.schemaVersion !== STUDY_STORE_SCHEMA_VERSION) {
      throw new UnsupportedStoreSchemaVersionError(manifest.schemaVersion)
    }

    await ensureFile(join(storePath, LOG_FILE))
    const logText = await readText(join(storePath, LOG_FILE))
    const replay = replayLog(parseRawEntries(logText ?? ''))
    const store = new StudyStore(storePath, clock, createdAt, migratedFrom, replay)
    await store.initialize()
    return store
  }

  private async initialize(): Promise<void> {
    const snapshotText = await readText(join(this.storePath, SNAPSHOT_FILE))
    const meta = snapshotText === undefined ? undefined : parseSnapshotMeta(snapshotText)
    const matches =
      meta !== undefined &&
      meta.schemaVersion === this.schemaVersion &&
      meta.stateHash === hashState(this.state) &&
      meta.eventCount === this.allEvents.length &&
      meta.recordCount === this.records.length
    if (matches && meta !== undefined) {
      this.generation = meta.generation
      return
    }
    this.generation = meta?.generation ?? 0
    await this.writeSnapshot()
  }

  private ensureOpen(): void {
    if (this.closed) throw new StoreClosedError()
  }

  private withLock<T>(operation: () => Promise<T>): Promise<T> {
    const run = this.queue.then(operation, operation)
    this.queue = run.then(
      () => undefined,
      () => undefined,
    )
    return run
  }

  private async writeSnapshot(): Promise<void> {
    const generation = this.generation + 1
    const snapshot: StudySnapshot = {
      schemaVersion: this.schemaVersion,
      generation,
      eventCount: this.allEvents.length,
      recordCount: this.records.length,
      stateHash: hashState(this.state),
      updatedAt: this.clock(),
      state: this.state,
    }
    const serialized = JSON.stringify(snapshot, undefined, 2)
    if (serialized === undefined) {
      throw new StorePersistenceError('snapshot', new Error('snapshot is not serializable'))
    }
    try {
      await writeAtomic(join(this.storePath, SNAPSHOT_FILE), `${serialized}\n`)
    } catch (error) {
      this.snapshotDirty = true
      throw new StorePersistenceError('snapshot', error)
    }
    this.generation = generation
    this.snapshotDirty = false
  }

  private async appendEntries(entries: readonly LogEntry[]): Promise<void> {
    if (entries.length === 0) return
    const text = `${entries.map(serializeLogEntry).join('\n')}\n`
    try {
      await appendDurable(join(this.storePath, LOG_FILE), text)
    } catch (error) {
      throw new StorePersistenceError('append', error)
    }
  }

  /** Append one event. An identical duplicate id is an idempotent no-op. */
  appendEvent(value: unknown): Promise<PipelineEvent> {
    return this.withLock(async () => {
      this.ensureOpen()
      const event = assertEvent(value)
      const existing = this.eventIndex.get(event.id)
      if (existing !== undefined) {
        if (isDeepStrictEqual(existing, event)) {
          if (this.snapshotDirty) await this.writeSnapshot()
          return existing
        }
        throw new DuplicateEventError(event.id)
      }
      const runEvents = this.eventsByRun.get(event.runId) ?? []
      const staged = new EventLog()
      for (const prior of runEvents) staged.append(prior)
      staged.append(event)
      const nextState = applyEvent(this.state, event)
      await this.appendEntries([{ kind: 'event', event }])
      this.logs.set(event.runId, staged)
      this.eventsByRun.set(event.runId, [...runEvents, event])
      this.allEvents.push(event)
      this.eventIndex.set(event.id, event)
      this.state = nextState
      await this.writeSnapshot()
      return event
    })
  }

  /**
   * Append a batch of events atomically. Every event must belong to one run and
   * the whole batch is rejected before anything is written if one event is
   * invalid, duplicated with different content, or mixed across runs.
   */
  appendEvents(values: readonly unknown[]): Promise<readonly PipelineEvent[]> {
    return this.withLock(async () => {
      this.ensureOpen()
      if (values.length === 0) return []
      const events = values.map(value => assertEvent(value))
      const first = events[0]
      if (first === undefined) return []
      const runIdValue = first.runId
      if (events.some(event => event.runId !== runIdValue)) {
        throw new MixedRunBatchError([...new Set(events.map(event => event.runId))])
      }
      const accepted: PipelineEvent[] = []
      const seen = new Map<string, PipelineEvent>()
      for (const event of events) {
        const existing = this.eventIndex.get(event.id) ?? seen.get(event.id)
        if (existing !== undefined) {
          if (isDeepStrictEqual(existing, event)) continue
          throw new DuplicateEventError(event.id)
        }
        seen.set(event.id, event)
        accepted.push(event)
      }
      if (accepted.length === 0) {
        if (this.snapshotDirty) await this.writeSnapshot()
        return []
      }
      const runEvents = this.eventsByRun.get(runIdValue) ?? []
      const staged = new EventLog()
      for (const prior of runEvents) staged.append(prior)
      staged.appendAll(accepted)
      let nextState = this.state
      for (const event of accepted) nextState = applyEvent(nextState, event)
      await this.appendEntries(accepted.map(event => ({ kind: 'event', event })))
      this.logs.set(runIdValue, staged)
      this.eventsByRun.set(runIdValue, [...runEvents, ...accepted])
      for (const event of accepted) {
        this.allEvents.push(event)
        this.eventIndex.set(event.id, event)
      }
      this.state = nextState
      await this.writeSnapshot()
      return accepted
    })
  }

  /** Read one run with its deterministic projection. */
  getRun(runIdValue: string): StudyRun | undefined {
    this.ensureOpen()
    const summary = this.state.runs[runIdValue]
    if (summary === undefined) return undefined
    const events = this.eventsByRun.get(runIdValue)
    if (events === undefined) {
      throw new StoreCorruptionError('run has no durable event log', { runId: runIdValue })
    }
    return { ...summary, projection: projectEvents(events) }
  }

  /** List every durable run in deterministic start-time order. */
  listRuns(): readonly StudyRun[] {
    this.ensureOpen()
    return Object.values(this.state.runs)
      .sort(
        (left, right) =>
          (left.startedAt ?? '').localeCompare(right.startedAt ?? '') ||
          left.runId.localeCompare(right.runId),
      )
      .map(summary => {
        const events = this.eventsByRun.get(summary.runId) ?? []
        return { ...summary, projection: projectEvents(events) }
      })
  }

  /** Replay one run from its durable events. */
  replay(runIdValue: string): RunProjection {
    this.ensureOpen()
    const events = this.eventsByRun.get(runIdValue)
    if (events === undefined) throw new UnknownRunError(runIdValue)
    return projectEvents(events)
  }

  /** Read the full deterministic study state. */
  getState(): StudyState {
    this.ensureOpen()
    return structuredClone(this.state)
  }

  /**
   * Search-learning history. By construction this view cannot contain holdout
   * feedback; `recordFeedback` rejects it and memberships seal holdout tasks.
   */
  searchHistory(): readonly SearchFeedbackRecord[] {
    this.ensureOpen()
    return structuredClone(this.state.feedback)
  }

  /** Record the hash and identity of one trace in one run. */
  async recordTraceIdentity(input: TraceIdentityInput): Promise<TraceIdentityRecord> {
    const draft: TraceIdentityRecord = {
      kind: 'trace/identity',
      recordId: '',
      at: this.clock(),
      runId: brandRunId(input.runId),
      traceId: brandTraceId(input.traceId),
      source: input.source,
      turns: input.turns,
      contentHash: input.contentHash,
    }
    const committed = await this.commitRecord(draft)
    if (committed.kind !== 'trace/identity') {
      throw new StoreCorruptionError('record kind changed after commit', {
        expected: 'trace/identity',
        actual: committed.kind,
      })
    }
    return committed
  }

  /** Record one router candidate batch with scores and rank order. */
  async recordRouterCandidates(
    input: RouterCandidatesInput,
  ): Promise<RouterCandidatesRecord> {
    const candidates: RouterCandidate[] = input.candidates.map(candidate => ({
      skillId: brandSkillId(candidate.skillId),
      score: candidate.score,
      ...(candidate.reason === undefined ? {} : { reason: candidate.reason }),
    }))
    const draft: RouterCandidatesRecord = {
      kind: 'router/candidates',
      recordId: '',
      at: this.clock(),
      runId: brandRunId(input.runId),
      ...(input.traceId === undefined ? {} : { traceId: brandTraceId(input.traceId) }),
      candidates,
    }
    const committed = await this.commitRecord(draft)
    if (committed.kind !== 'router/candidates') {
      throw new StoreCorruptionError('record kind changed after commit', {
        expected: 'router/candidates',
        actual: committed.kind,
      })
    }
    return committed
  }

  /** Record one paired baseline/treatment benchmark observation. */
  async recordBenchmarkObservation(
    input: BenchmarkObservationInput,
  ): Promise<BenchmarkObservationRecord> {
    const baseline = toBenchmarkArm(input.baseline)
    const treatment = toBenchmarkArm(input.treatment)
    const draft: BenchmarkObservationRecord = {
      kind: 'benchmark/observation',
      recordId: '',
      at: this.clock(),
      runId: brandRunId(input.runId),
      stage: input.stage,
      taskId: input.taskId,
      domain: input.domain,
      baseline,
      treatment,
      efficiencyFailure: input.efficiencyFailure,
      ...(input.groupId === undefined ? {} : { groupId: input.groupId }),
      ...(input.candidateId === undefined ? {} : { candidateId: input.candidateId }),
      ...(input.policyVersion === undefined ? {} : { policyVersion: input.policyVersion }),
      ...(input.configVersion === undefined ? {} : { configVersion: input.configVersion }),
    }
    const committed = await this.commitRecord(draft)
    if (committed.kind !== 'benchmark/observation') {
      throw new StoreCorruptionError('record kind changed after commit', {
        expected: 'benchmark/observation',
        actual: committed.kind,
      })
    }
    return committed
  }

  /** Record a task's train, validation, or holdout membership. */
  async recordMembership(input: MembershipInput): Promise<MembershipRecord> {
    const draft: MembershipRecord = {
      kind: 'membership',
      recordId: '',
      at: this.clock(),
      taskId: input.taskId,
      stage: input.stage,
      ...(input.groupId === undefined ? {} : { groupId: input.groupId }),
    }
    const committed = await this.commitRecord(draft)
    if (committed.kind !== 'membership') {
      throw new StoreCorruptionError('record kind changed after commit', {
        expected: 'membership',
        actual: committed.kind,
      })
    }
    return committed
  }

  /**
   * Record search-learning feedback.
   *
   * This is the dedicated search-learning boundary: holdout feedback is
   * rejected outright, and a task whose membership is holdout is rejected even
   * if the caller claims another stage. Holdout can therefore never enter
   * `searchHistory()`.
   */
  async recordFeedback(input: SearchFeedbackInput): Promise<SearchFeedbackRecord> {
    if (input.stage === 'holdout') {
      throw new HoldoutFeedbackRejectedError(
        input.taskId,
        'holdout stage is sealed from search learning',
      )
    }
    const draft: SearchFeedbackRecord = {
      kind: 'feedback/search',
      recordId: '',
      at: this.clock(),
      taskId: input.taskId,
      skillId: brandSkillId(input.skillId),
      adjustment: input.adjustment,
      stage: input.stage,
      ...(input.runId === undefined ? {} : { runId: brandRunId(input.runId) }),
      ...(input.source === undefined ? {} : { source: input.source }),
    }
    const committed = await this.commitRecord(draft)
    if (committed.kind !== 'feedback/search') {
      throw new StoreCorruptionError('record kind changed after commit', {
        expected: 'feedback/search',
        actual: committed.kind,
      })
    }
    return committed
  }

  /** Record whether a skill was exposed to and activated by a run. */
  async recordSkillExposure(input: SkillExposureInput): Promise<SkillExposureRecord> {
    const draft: SkillExposureRecord = {
      kind: 'skill/exposure',
      recordId: '',
      at: this.clock(),
      runId: brandRunId(input.runId),
      skillId: brandSkillId(input.skillId),
      exposed: input.exposed,
      activated: input.activated,
      ...(input.source === undefined ? {} : { source: input.source }),
    }
    const committed = await this.commitRecord(draft)
    if (committed.kind !== 'skill/exposure') {
      throw new StoreCorruptionError('record kind changed after commit', {
        expected: 'skill/exposure',
        actual: committed.kind,
      })
    }
    return committed
  }

  /** Record one frozen policy version. */
  recordPolicyVersion(input: VersionInput): Promise<VersionRecord> {
    return this.recordVersion('policy/version', input)
  }

  /** Record one frozen configuration version. */
  recordConfigVersion(input: VersionInput): Promise<VersionRecord> {
    return this.recordVersion('config/version', input)
  }

  private async recordVersion(
    kind: 'policy/version' | 'config/version',
    input: VersionInput,
  ): Promise<VersionRecord> {
    const contentHash = hashText(stableStringify(input.payload === undefined ? null : input.payload))
    const draft: VersionRecord = {
      kind,
      recordId: '',
      at: this.clock(),
      version: input.version,
      contentHash,
      ...(input.payload === undefined ? {} : { payload: input.payload }),
    }
    const committed = await this.commitRecord(draft)
    if (committed.kind !== 'policy/version' && committed.kind !== 'config/version') {
      throw new StoreCorruptionError('record kind changed after commit', {
        expected: kind,
        actual: committed.kind,
      })
    }
    return committed
  }

  private async commitRecord(record: StudyRecord): Promise<StudyRecord> {
    return this.withLock(async () => {
      this.ensureOpen()
      const candidate = assignRecordId(record)
      const parsed = parseStudyRecord(candidate)
      if (!parsed.ok || parsed.record === undefined) {
        throw new InvalidRecordError(candidate.kind, parsed.issues)
      }
      const normalized = parsed.record
      const existing = this.recordIndex.get(normalized.recordId)
      if (existing !== undefined) {
        if (sameRecordPayload(existing, normalized)) {
          if (this.snapshotDirty) await this.writeSnapshot()
          return existing
        }
        throw conflictForRecord(existing, normalized)
      }
      const nextState = applyRecord(this.state, normalized)
      await this.appendEntries([{ kind: 'record', record: normalized }])
      this.records.push(normalized)
      this.recordIndex.set(normalized.recordId, normalized)
      this.state = nextState
      await this.writeSnapshot()
      return normalized
    })
  }

  /**
   * Re-read the durable log, replay it, and compare the result and the snapshot
   * index with the live in-memory state.
   */
  verifyIntegrity(): Promise<IntegrityReport> {
    return this.withLock(async () => {
      this.ensureOpen()
      const issues: IntegrityIssue[] = []
      const logPath = join(this.storePath, LOG_FILE)
      const logText = await readText(logPath)
      let replayed: ReplayResult | undefined
      if (logText === undefined) {
        issues.push({ line: 0, code: 'missing-log', message: `${LOG_FILE} is missing` })
      } else {
        try {
          replayed = replayLog(parseRawEntries(logText))
        } catch (error) {
          const line = error instanceof PipelineError && typeof error.details.line === 'number'
            ? error.details.line
            : 0
          issues.push({
            line,
            code: error instanceof PipelineError ? error.code : 'replay-failed',
            message: describeError(error),
          })
        }
      }
      if (replayed !== undefined) {
        if (replayed.events.length !== this.allEvents.length) {
          issues.push({
            line: 0,
            code: 'event-count-mismatch',
            message: `durable log has ${replayed.events.length} events, memory has ${this.allEvents.length}`,
          })
        }
        if (replayed.records.length !== this.records.length) {
          issues.push({
            line: 0,
            code: 'record-count-mismatch',
            message: `durable log has ${replayed.records.length} records, memory has ${this.records.length}`,
          })
        }
        if (hashState(replayed.state) !== hashState(this.state)) {
          issues.push({
            line: 0,
            code: 'state-diverged',
            message: 'replayed state does not match the live state',
          })
        }
      }

      const snapshotText = await readText(join(this.storePath, SNAPSHOT_FILE))
      let snapshotMatches = false
      if (snapshotText === undefined) {
        issues.push({ line: 0, code: 'missing-snapshot', message: `${SNAPSHOT_FILE} is missing` })
      } else {
        const meta = parseSnapshotMeta(snapshotText)
        if (meta === undefined) {
          issues.push({
            line: 0,
            code: 'invalid-snapshot',
            message: `${SNAPSHOT_FILE} cannot be parsed`,
          })
        } else {
          snapshotMatches =
            meta.schemaVersion === this.schemaVersion &&
            meta.stateHash === hashState(this.state) &&
            meta.eventCount === this.allEvents.length &&
            meta.recordCount === this.records.length
          if (!snapshotMatches) {
            issues.push({
              line: 0,
              code: 'snapshot-mismatch',
              message: 'snapshot index does not match the durable state',
            })
          }
        }
      }

      return {
        ok: issues.length === 0,
        schemaVersion: this.schemaVersion,
        eventCount: this.allEvents.length,
        recordCount: this.records.length,
        runIds: Object.keys(this.state.runs).sort(),
        snapshotMatches,
        issues,
      }
    })
  }

  /** Flush the snapshot index and close the store. */
  close(): Promise<void> {
    return this.withLock(async () => {
      if (this.closed) return
      await this.writeSnapshot()
      this.closed = true
    })
  }
}

function toBenchmarkArm(input: BenchmarkArmInput): BenchmarkArm {
  return {
    passed: input.passed,
    toolCalls: input.toolCalls,
    ...(input.skillId === undefined ? {} : { skillId: brandSkillId(input.skillId) }),
    ...(input.latencyMs === undefined ? {} : { latencyMs: input.latencyMs }),
    ...(input.costUsd === undefined ? {} : { costUsd: input.costUsd }),
    ...(input.failures === undefined ? {} : { failures: input.failures }),
  }
}

/** Open or create a durable study store whose path is a directory. */
export function openStudyStore(
  storePath: string,
  options: OpenStudyStoreOptions = {},
): Promise<StudyStore> {
  return StudyStore.open(storePath, options)
}
