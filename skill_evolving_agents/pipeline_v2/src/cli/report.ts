/**
 * Frozen JSON and Markdown experiment reports for the v2 command line.
 *
 * The report is a read-only snapshot of one admitted experiment.  It separates
 * four populations that are easy to conflate:
 *
 * - baseline conditions;
 * - treatment conditions as they actually ran;
 * - the selective router policy, where abstentions inherit the baseline;
 * - the activated-skill effect, where activation was verified.
 *
 * Three honesty rules are enforced by construction:
 *
 * 1. no value is invented: missing cost is `null`, never `0`;
 * 2. empty cohorts produce `null` rates and totals rather than zeroed metrics;
 * 3. holdout readiness is caller-attested and never inferred from validation.
 *
 * JSON output uses a recursively sorted key order, so the same report always
 * serializes to the same bytes.  Markdown output labels unmeasured cost
 * explicitly instead of rendering a misleading dollar amount.
 */

import { mkdir, rename, rm, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'

import type {
  AdmissionCounts,
  AdmittedObservation,
  BenchmarkObservation,
  ObservationExclusion,
} from '../benchmark/admission.ts'
import { admitObservations } from '../benchmark/admission.ts'
import { twoSidedSignTest } from '../benchmark/report.ts'
import { PipelineError } from '../contracts/errors.ts'
import type { StructuredIssue } from '../contracts/errors.ts'
import type { VerificationStatus } from '../contracts/evidence.ts'
import type { PublicationReceipt } from '../contracts/operations.ts'
import type { ResourceKind } from '../contracts/resources.ts'
import { isFiniteNumber, isNonEmptyString, isRecord, issue } from '../contracts/validation.ts'
import type { PreflightReport } from '../preflight/preflight.ts'
import type { EvaluationStage } from '../search/contracts.ts'
import { hashContent } from '../store/study-store.ts'
import type { CliOptions } from './args.ts'
import { canonicalOptions } from './args.ts'

/** Version of the experiment report schema. */
export const EXPERIMENT_REPORT_VERSION = 1 as const

/** Stages that can be reported as the current experiment stage. */
export type ExperimentReportStage = 'train' | 'validation'

/** Completeness of the measured cost. */
export type ReportCostStatus = 'measured' | 'partial' | 'unmeasured'

/** Severity of one recorded defect. */
export type DefectSeverity = 'info' | 'warning' | 'error'

/** One explicit task included in the experiment. */
export interface ExperimentTaskInput {
  readonly taskId: string
  readonly domain: string
  readonly groupId?: string | null
  readonly stage?: ExperimentReportStage | null
}

/** One task-stage membership used to derive membership hashes. */
export interface MembershipInput {
  readonly taskId: string
  readonly stage: EvaluationStage
  readonly contentHash?: string | null
}

/** One retrieved candidate score retained for audit. */
export interface CandidateScoreInput {
  readonly taskId: string
  readonly skillId: string
  readonly score: number
  readonly reason?: string | null
}

/** One generated or used resource. */
export interface ExperimentResourceInput {
  readonly kind: ResourceKind
  readonly path: string
  readonly status: 'generated' | 'used' | 'rejected'
  readonly contentHash?: string | null
  readonly operationId?: string | null
  readonly skillId?: string | null
}

/** One verification result. */
export interface VerificationInput {
  readonly status: VerificationStatus
  readonly summary: string
  readonly evidenceHash?: string | null
  readonly operationId?: string | null
}

/** One defect or unresolved issue found during the experiment. */
export interface DefectInput {
  readonly code: string
  readonly message: string
  readonly severity?: DefectSeverity
  readonly taskId?: string | null
}

/**
 * Input to one deterministic report build.
 *
 * Only `observations` can influence outcome statistics.  Everything else is
 * copied or summarized, so the report cannot silently derive a benchmark
 * number from a membership file or a router candidate.
 */
export interface ExperimentReportInput {
  readonly runId: string
  readonly stage: ExperimentReportStage
  readonly startedAt: string
  readonly finishedAt: string | null
  readonly options: CliOptions
  readonly memberships?: readonly MembershipInput[]
  /** Precomputed stage hashes, e.g. from a validation cohort audit. */
  readonly membershipHashes?: Partial<Record<EvaluationStage, string>>
  readonly tasks?: readonly ExperimentTaskInput[]
  readonly observations?: readonly BenchmarkObservation[]
  readonly candidateScores?: readonly CandidateScoreInput[]
  readonly resources?: readonly ExperimentResourceInput[]
  readonly receipts?: readonly PublicationReceipt[]
  readonly preflight?: PreflightReport | null
  readonly verification?: VerificationInput | null
  readonly defects?: readonly DefectInput[]
  /** Caller-attested; the report never infers holdout readiness. */
  readonly holdoutReady?: boolean
  readonly limitations?: readonly string[]
}

/** One stage's membership identity. */
export interface MembershipStageReport {
  readonly tasks: number
  readonly taskIds: readonly string[]
  /** Hash of the sorted membership; null when the stage is empty. */
  readonly hash: string | null
  /** Optional per-task content hashes supplied by the caller. */
  readonly contentHashes: Readonly<Record<string, string>>
}

/** Membership identity for every experimental stage. */
export interface MembershipReport {
  readonly train: MembershipStageReport
  readonly validation: MembershipStageReport
  readonly holdout: MembershipStageReport
  readonly combinedHash: string | null
}

/** One task row in the report. */
export interface ExperimentTaskReport {
  readonly taskId: string
  readonly domain: string
  readonly stage: ExperimentReportStage
  readonly groupId: string | null
  readonly trials: readonly number[]
  readonly submittedObservations: number
  readonly admittedCells: number
  readonly selectedCells: number
  readonly abstainedCells: number
}

/** Task coverage for the experiment. */
export interface TasksReport {
  readonly total: number
  readonly byStage: Readonly<Record<ExperimentReportStage, number>>
  readonly byDomain: Readonly<Record<string, number>>
  readonly taskIds: readonly string[]
  readonly rows: readonly ExperimentTaskReport[]
}

/** Router selection and abstention counts over admitted cells. */
export interface RoutingReport {
  readonly selectedCells: number
  readonly abstainedCells: number
  readonly selectedTaskIds: readonly string[]
  readonly abstainedTaskIds: readonly string[]
  /** Selected cells divided by admitted cells; null for an empty cohort. */
  readonly selectionRate: number | null
}

/** One candidate score row. */
export interface CandidateScoreReport {
  readonly taskId: string
  readonly skillId: string
  readonly score: number
  readonly reason: string | null
}

/** Aggregated metrics for one condition (baseline or treatment). */
export interface ConditionMetrics {
  readonly cells: number
  readonly passes: number
  readonly passRate: number | null
  readonly efficiencyFailures: number
  readonly toolCalls: number | null
  readonly meanToolCalls: number | null
  readonly latencyMs: number | null
  readonly meanLatencyMs: number | null
  readonly costUsd: number | null
  readonly costMeasuredCells: number
  readonly costUnmeasuredCells: number
}

/** Selective-policy metrics: abstentions inherit the baseline outcome. */
export interface PolicyMetrics {
  readonly cells: number
  readonly selectedCells: number
  readonly abstainedCells: number
  readonly inheritedBaselineCells: number
  readonly baselinePasses: number
  readonly baselinePassRate: number | null
  readonly policyPasses: number
  readonly policyPassRate: number | null
  /** Policy pass rate minus baseline pass rate; null for an empty cohort. */
  readonly absoluteLift: number | null
  readonly lifts: number
  readonly regressions: number
}

/** Effect over cells whose skill activation was verified. */
export interface ActivatedEffectReport {
  readonly scope: 'verified-activation'
  readonly cells: number
  readonly baselinePasses: number
  readonly treatmentPasses: number
  readonly baselinePassRate: number | null
  readonly treatmentPassRate: number | null
  readonly absoluteLift: number | null
  readonly lifts: number
  readonly regressions: number
  readonly unchanged: number
  readonly exactSignTestPValue: number | null
}

/** One resource row in the report. */
export interface ResourceReport {
  readonly kind: ResourceKind
  readonly path: string
  readonly status: 'generated' | 'used' | 'rejected'
  readonly contentHash: string | null
  readonly operationId: string | null
  readonly skillId: string | null
}

/** One verification row in the report. */
export interface VerificationReport {
  readonly status: VerificationStatus
  readonly summary: string
  readonly evidenceHash: string | null
  readonly operationId: string | null
}

/** One defect row in the report. */
export interface DefectReport {
  readonly code: string
  readonly message: string
  readonly severity: DefectSeverity
  readonly taskId: string | null
}

/** Cost for the whole admitted cohort. */
export interface CostReport {
  readonly currency: 'USD'
  readonly status: ReportCostStatus
  readonly baselineUsd: number | null
  readonly treatmentUsd: number | null
  /** Only a complete cohort has a total; partial totals are not claimed. */
  readonly totalUsd: number | null
  readonly measuredConditions: number
  readonly unmeasuredConditions: number
  readonly totalConditions: number
  readonly note: string
}

/** Latency for the whole admitted cohort. */
export interface LatencyReport {
  readonly conditions: number
  readonly baselineMs: number | null
  readonly treatmentMs: number | null
  readonly totalMs: number | null
  readonly meanDeltaMs: number | null
}

/** Tool-call usage for the whole admitted cohort. */
export interface ToolCallReport {
  readonly conditions: number
  readonly baselineCalls: number | null
  readonly treatmentCalls: number | null
  readonly totalCalls: number | null
  readonly meanDeltaCalls: number | null
}

/** Structured exclusions kept outside every scored view. */
export interface ExclusionsReport {
  readonly total: number
  readonly invalidExposures: readonly ObservationExclusion[]
  readonly contamination: readonly ObservationExclusion[]
  readonly infrastructureErrors: readonly ObservationExclusion[]
  readonly duplicates: readonly ObservationExclusion[]
  readonly all: readonly ObservationExclusion[]
}

/** Frozen experiment report. */
export interface ExperimentReport {
  readonly schemaVersion: typeof EXPERIMENT_REPORT_VERSION
  readonly runId: string
  readonly stage: ExperimentReportStage
  readonly startedAt: string
  readonly finishedAt: string | null
  readonly options: CliOptions
  readonly membership: MembershipReport
  readonly tasks: TasksReport
  readonly routing: RoutingReport
  readonly candidateScores: readonly CandidateScoreReport[]
  readonly admission: AdmissionCounts
  readonly baseline: ConditionMetrics
  readonly treatment: ConditionMetrics
  readonly policy: PolicyMetrics
  readonly activatedEffect: ActivatedEffectReport
  readonly resources: readonly ResourceReport[]
  readonly receipts: readonly PublicationReceipt[]
  readonly preflight: PreflightReport | null
  readonly verification: VerificationReport | null
  readonly cost: CostReport
  readonly latency: LatencyReport
  readonly toolCalls: ToolCallReport
  readonly exclusions: ExclusionsReport
  readonly defects: readonly DefectReport[]
  readonly holdoutReady: boolean
  readonly limitations: readonly string[]
}

/** An experiment report input failed structural validation. */
export class InvalidExperimentReportError extends PipelineError {
  readonly issues: readonly StructuredIssue[]

  constructor(issues: readonly StructuredIssue[]) {
    super('invalid-experiment-report', 'experiment report failed validation', { issues })
    this.issues = issues
  }
}

const STAGES: readonly EvaluationStage[] = ['train', 'validation', 'holdout']
const VERIFICATION_STATUSES: readonly VerificationStatus[] = [
  'pass',
  'fail',
  'efficiency_failure',
]
const DEFECT_SEVERITIES: readonly DefectSeverity[] = ['info', 'warning', 'error']
const RESOURCE_KINDS: readonly ResourceKind[] = [
  'scripts',
  'references',
  'assets',
  'agents',
  'evals',
]

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0
}

function round6(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000
}

function rate(numerator: number, denominator: number): number | null {
  return denominator === 0 ? null : round6(numerator / denominator)
}

function mean(total: number, count: number): number | null {
  return count === 0 ? null : round6(total / count)
}

function uniqueSorted(values: readonly string[]): string[] {
  return [...new Set(values)].sort(compareText)
}

function sum(values: readonly number[]): number {
  let total = 0
  for (const value of values) total += value
  return total
}

function isReportStage(value: unknown): value is ExperimentReportStage {
  return value === 'train' || value === 'validation'
}

function isEvaluationStage(value: unknown): value is EvaluationStage {
  return value === 'train' || value === 'validation' || value === 'holdout'
}

function validateInput(input: ExperimentReportInput): StructuredIssue[] {
  const issues: StructuredIssue[] = []

  if (!isNonEmptyString(input.runId)) {
    issues.push(issue('$.runId', 'invalid', 'runId must be a non-empty string'))
  }
  if (!isReportStage(input.stage)) {
    issues.push(issue('$.stage', 'invalid', 'stage must be train or validation'))
  }
  if (!isNonEmptyString(input.startedAt)) {
    issues.push(issue('$.startedAt', 'invalid', 'startedAt must be a non-empty string'))
  }
  if (input.finishedAt !== null && !isNonEmptyString(input.finishedAt)) {
    issues.push(issue('$.finishedAt', 'invalid', 'finishedAt must be null or a non-empty string'))
  }
  if (!isRecord(input.options)) {
    issues.push(issue('$.options', 'invalid', 'options must be an object'))
  }
  if (input.holdoutReady !== undefined && typeof input.holdoutReady !== 'boolean') {
    issues.push(issue('$.holdoutReady', 'invalid', 'holdoutReady must be a boolean'))
  }

  const memberships = input.memberships ?? []
  const seenMemberships = new Map<string, EvaluationStage>()
  memberships.forEach((membership, index) => {
    const path = `$.memberships[${index}]`
    if (!isNonEmptyString(membership.taskId)) {
      issues.push(issue(`${path}.taskId`, 'invalid', 'taskId must be a non-empty string'))
    }
    if (!isEvaluationStage(membership.stage)) {
      issues.push(issue(`${path}.stage`, 'invalid', 'stage must be train, validation, or holdout'))
    }
    if (membership.contentHash !== undefined
      && membership.contentHash !== null
      && !isNonEmptyString(membership.contentHash)) {
      issues.push(issue(`${path}.contentHash`, 'invalid', 'contentHash must be null or a non-empty string'))
    }
    const previous = seenMemberships.get(membership.taskId)
    if (previous !== undefined && previous !== membership.stage) {
      issues.push(issue(
        path,
        'conflict',
        `task ${membership.taskId} belongs to both ${previous} and ${membership.stage}`,
      ))
    }
    seenMemberships.set(membership.taskId, membership.stage)
  })

  if (input.membershipHashes !== undefined) {
    for (const stage of STAGES) {
      const hash = input.membershipHashes[stage]
      if (hash !== undefined && !isNonEmptyString(hash)) {
        issues.push(issue(`$.membershipHashes.${stage}`, 'invalid', 'membership hash must be a non-empty string'))
      }
    }
  }

  const tasks = input.tasks ?? []
  tasks.forEach((task, index) => {
    const path = `$.tasks[${index}]`
    if (!isNonEmptyString(task.taskId)) {
      issues.push(issue(`${path}.taskId`, 'invalid', 'taskId must be a non-empty string'))
    }
    if (!isNonEmptyString(task.domain)) {
      issues.push(issue(`${path}.domain`, 'invalid', 'domain must be a non-empty string'))
    }
    if (task.stage !== undefined && task.stage !== null && !isReportStage(task.stage)) {
      issues.push(issue(`${path}.stage`, 'invalid', 'stage must be train or validation'))
    }
  })

  const observations = input.observations ?? []
  observations.forEach((observation, index) => {
    const path = `$.observations[${index}]`
    if (!isNonEmptyString(observation.observationId)) {
      issues.push(issue(`${path}.observationId`, 'invalid', 'observationId must be a non-empty string'))
    }
    if (!isNonEmptyString(observation.taskId)) {
      issues.push(issue(`${path}.taskId`, 'invalid', 'taskId must be a non-empty string'))
    }
    if (!isNonEmptyString(observation.domain)) {
      issues.push(issue(`${path}.domain`, 'invalid', 'domain must be a non-empty string'))
    }
    if (!Number.isInteger(observation.trial) || observation.trial < 0) {
      issues.push(issue(`${path}.trial`, 'invalid', 'trial must be a non-negative integer'))
    }
    for (const conditionName of ['baseline', 'treatment'] as const) {
      const condition = observation[conditionName]
      const conditionPath = `${path}.${conditionName}`
      if (!isFiniteNumber(condition.toolCalls) || condition.toolCalls < 0) {
        issues.push(issue(`${conditionPath}.toolCalls`, 'invalid', 'toolCalls must be non-negative'))
      }
      if (!isFiniteNumber(condition.latencyMs) || condition.latencyMs < 0) {
        issues.push(issue(`${conditionPath}.latencyMs`, 'invalid', 'latencyMs must be non-negative'))
      }
      if (condition.costUsd !== undefined
        && condition.costUsd !== null
        && (!isFiniteNumber(condition.costUsd) || condition.costUsd < 0)) {
        issues.push(issue(`${conditionPath}.costUsd`, 'invalid', 'costUsd must be null or non-negative'))
      }
    }
  })

  const candidates = input.candidateScores ?? []
  candidates.forEach((candidate, index) => {
    const path = `$.candidateScores[${index}]`
    if (!isNonEmptyString(candidate.taskId)) {
      issues.push(issue(`${path}.taskId`, 'invalid', 'taskId must be a non-empty string'))
    }
    if (!isNonEmptyString(candidate.skillId)) {
      issues.push(issue(`${path}.skillId`, 'invalid', 'skillId must be a non-empty string'))
    }
    if (!isFiniteNumber(candidate.score)) {
      issues.push(issue(`${path}.score`, 'invalid', 'score must be finite'))
    }
  })

  const resources = input.resources ?? []
  resources.forEach((resource, index) => {
    const path = `$.resources[${index}]`
    if (!RESOURCE_KINDS.includes(resource.kind)) {
      issues.push(issue(`${path}.kind`, 'invalid', 'unsupported resource kind'))
    }
    if (!isNonEmptyString(resource.path)) {
      issues.push(issue(`${path}.path`, 'invalid', 'path must be a non-empty string'))
    }
    if (!['generated', 'used', 'rejected'].includes(resource.status)) {
      issues.push(issue(`${path}.status`, 'invalid', 'unsupported resource status'))
    }
  })

  const receipts = input.receipts ?? []
  receipts.forEach((receipt, index) => {
    const path = `$.receipts[${index}]`
    if (!isNonEmptyString(receipt.operationId)) {
      issues.push(issue(`${path}.operationId`, 'invalid', 'operationId must be a non-empty string'))
    }
    if (!isNonEmptyString(receipt.releaseId)) {
      issues.push(issue(`${path}.releaseId`, 'invalid', 'releaseId must be a non-empty string'))
    }
    if (!['provisional', 'canary', 'accepted'].includes(receipt.channel)) {
      issues.push(issue(`${path}.channel`, 'invalid', 'unsupported receipt channel'))
    }
  })

  if (input.verification !== undefined && input.verification !== null) {
    if (!VERIFICATION_STATUSES.includes(input.verification.status)) {
      issues.push(issue('$.verification.status', 'invalid', 'unsupported verification status'))
    }
    if (!isNonEmptyString(input.verification.summary)) {
      issues.push(issue('$.verification.summary', 'invalid', 'summary must be a non-empty string'))
    }
  }

  const defects = input.defects ?? []
  defects.forEach((defect, index) => {
    const path = `$.defects[${index}]`
    if (!isNonEmptyString(defect.code)) {
      issues.push(issue(`${path}.code`, 'invalid', 'code must be a non-empty string'))
    }
    if (!isNonEmptyString(defect.message)) {
      issues.push(issue(`${path}.message`, 'invalid', 'message must be a non-empty string'))
    }
    if (defect.severity !== undefined && !DEFECT_SEVERITIES.includes(defect.severity)) {
      issues.push(issue(`${path}.severity`, 'invalid', 'severity must be info, warning, or error'))
    }
  })

  const limitations = input.limitations ?? []
  limitations.forEach((limitation, index) => {
    if (!isNonEmptyString(limitation)) {
      issues.push(issue(`$.limitations[${index}]`, 'invalid', 'limitation must be a non-empty string'))
    }
  })

  return issues
}

function membershipStage(
  stage: EvaluationStage,
  entries: readonly MembershipInput[],
  override: string | undefined,
): MembershipStageReport {
  const rows = entries.filter((entry) => entry.stage === stage)
  const taskIds = uniqueSorted(rows.map((entry) => entry.taskId))
  const hashes: Record<string, string> = {}
  for (const taskId of taskIds) {
    const supplied = rows
      .filter((entry) => entry.taskId === taskId)
      .map((entry) => entry.contentHash ?? null)
      .find((hash) => hash !== null)
    if (supplied !== undefined && supplied !== null) hashes[taskId] = supplied
  }
  const sortedHashes = Object.fromEntries(
    Object.entries(hashes).sort(([left], [right]) => compareText(left, right)),
  )
  return {
    tasks: taskIds.length,
    taskIds,
    hash: override ?? (taskIds.length === 0
      ? null
      : hashContent(`${stage}\n${taskIds.join('\n')}`)),
    contentHashes: sortedHashes,
  }
}

function buildMembership(
  entries: readonly MembershipInput[],
  overrides: Partial<Record<EvaluationStage, string>>,
): MembershipReport {
  const train = membershipStage('train', entries, overrides.train)
  const validation = membershipStage('validation', entries, overrides.validation)
  const holdout = membershipStage('holdout', entries, overrides.holdout)
  const components = [
    `train:${train.hash ?? ''}`,
    `validation:${validation.hash ?? ''}`,
    `holdout:${holdout.hash ?? ''}`,
  ]
  const empty = train.hash === null && validation.hash === null && holdout.hash === null
  return {
    train,
    validation,
    holdout,
    combinedHash: empty ? null : hashContent(components.join('\n')),
  }
}

interface MutableTaskRow {
  taskId: string
  domain: string
  stage: ExperimentReportStage
  groupId: string | null
  trials: Set<number>
  submittedObservations: number
  admittedCells: number
  selectedCells: number
  abstainedCells: number
}

function buildTasks(
  input: ExperimentReportInput,
  observations: readonly BenchmarkObservation[],
  admitted: readonly AdmittedObservation[],
): TasksReport {
  const rows = new Map<string, MutableTaskRow>()

  function ensure(taskId: string, domain: string): MutableTaskRow {
    const existing = rows.get(taskId)
    if (existing !== undefined) return existing
    const row: MutableTaskRow = {
      taskId,
      domain,
      stage: input.stage,
      groupId: null,
      trials: new Set<number>(),
      submittedObservations: 0,
      admittedCells: 0,
      selectedCells: 0,
      abstainedCells: 0,
    }
    rows.set(taskId, row)
    return row
  }

  for (const task of input.tasks ?? []) {
    const row = ensure(task.taskId, task.domain)
    row.domain = task.domain
    row.stage = task.stage ?? input.stage
    row.groupId = task.groupId ?? null
  }

  for (const observation of observations) {
    const row = ensure(observation.taskId, observation.domain)
    row.trials.add(observation.trial)
    row.submittedObservations += 1
  }

  for (const observation of admitted) {
    const row = ensure(observation.taskId, observation.domain)
    row.admittedCells += 1
    if (observation.routerSelected) row.selectedCells += 1
    else row.abstainedCells += 1
  }

  const taskRows = [...rows.values()]
    .sort((left, right) => compareText(left.taskId, right.taskId))
    .map((row): ExperimentTaskReport => ({
      taskId: row.taskId,
      domain: row.domain,
      stage: row.stage,
      groupId: row.groupId,
      trials: [...row.trials].sort((left, right) => left - right),
      submittedObservations: row.submittedObservations,
      admittedCells: row.admittedCells,
      selectedCells: row.selectedCells,
      abstainedCells: row.abstainedCells,
    }))

  const byDomain: Record<string, number> = {}
  for (const row of taskRows) {
    byDomain[row.domain] = (byDomain[row.domain] ?? 0) + 1
  }
  const sortedByDomain = Object.fromEntries(
    Object.entries(byDomain).sort(([left], [right]) => compareText(left, right)),
  )

  return {
    total: taskRows.length,
    byStage: {
      train: taskRows.filter((row) => row.stage === 'train').length,
      validation: taskRows.filter((row) => row.stage === 'validation').length,
    },
    byDomain: sortedByDomain,
    taskIds: taskRows.map((row) => row.taskId),
    rows: taskRows,
  }
}

function buildRouting(admitted: readonly AdmittedObservation[]): RoutingReport {
  const selected = admitted.filter((observation) => observation.routerSelected)
  const abstained = admitted.filter((observation) => !observation.routerSelected)
  return {
    selectedCells: selected.length,
    abstainedCells: abstained.length,
    selectedTaskIds: uniqueSorted(selected.map((observation) => observation.taskId)),
    abstainedTaskIds: uniqueSorted(abstained.map((observation) => observation.taskId)),
    selectionRate: rate(selected.length, admitted.length),
  }
}

function buildCandidateScores(
  candidates: readonly CandidateScoreInput[],
): CandidateScoreReport[] {
  return [...candidates]
    .sort((left, right) => (
      compareText(left.taskId, right.taskId)
      || compareText(left.skillId, right.skillId)
      || left.score - right.score
      || compareText(left.reason ?? '', right.reason ?? '')
    ))
    .map((candidate) => ({
      taskId: candidate.taskId,
      skillId: candidate.skillId,
      score: candidate.score,
      reason: candidate.reason ?? null,
    }))
}

type ConditionName = 'baseline' | 'treatment'

function buildConditionMetrics(
  observations: readonly AdmittedObservation[],
  condition: ConditionName,
): ConditionMetrics {
  const cells = observations.length
  const passes = observations.filter((observation) => observation[condition].passed).length
  const efficiencyFailures = observations.filter(
    (observation) => observation[condition].efficiencyFailure,
  ).length
  const toolCalls = observations.map((observation) => observation[condition].toolCalls)
  const latencies = observations.map((observation) => observation[condition].latencyMs)
  const costs = observations
    .map((observation) => observation[condition].costUsd ?? null)
    .filter((cost): cost is number => cost !== null)
  return {
    cells,
    passes,
    passRate: rate(passes, cells),
    efficiencyFailures,
    toolCalls: cells === 0 ? null : sum(toolCalls),
    meanToolCalls: mean(sum(toolCalls), cells),
    latencyMs: cells === 0 ? null : sum(latencies),
    meanLatencyMs: mean(sum(latencies), cells),
    costUsd: costs.length === 0 ? null : round6(sum(costs)),
    costMeasuredCells: costs.length,
    costUnmeasuredCells: cells - costs.length,
  }
}

function buildPolicy(admission: ReturnType<typeof admitObservations>): PolicyMetrics {
  const cells = admission.selective
  const selected = cells.filter((cell) => cell.source === 'activated-treatment')
  const inherited = cells.filter((cell) => cell.source === 'baseline-abstention')
  const baselinePasses = cells.filter((cell) => cell.baseline.passed).length
  const policyPasses = cells.filter((cell) => cell.effective.passed).length
  const lifts = cells.filter(
    (cell) => !cell.baseline.passed && cell.effective.passed,
  ).length
  const regressions = cells.filter(
    (cell) => cell.baseline.passed && !cell.effective.passed,
  ).length
  const baselinePassRate = rate(baselinePasses, cells.length)
  const policyPassRate = rate(policyPasses, cells.length)
  return {
    cells: cells.length,
    selectedCells: selected.length,
    abstainedCells: inherited.length,
    inheritedBaselineCells: inherited.length,
    baselinePasses,
    baselinePassRate,
    policyPasses,
    policyPassRate,
    absoluteLift: baselinePassRate === null || policyPassRate === null
      ? null
      : round6(policyPassRate - baselinePassRate),
    lifts,
    regressions,
  }
}

function buildActivatedEffect(
  admission: ReturnType<typeof admitObservations>,
): ActivatedEffectReport {
  const cells = admission.activated
  const baselinePasses = cells.filter((cell) => cell.baseline.passed).length
  const treatmentPasses = cells.filter((cell) => cell.treatment.passed).length
  const lifts = cells.filter(
    (cell) => !cell.baseline.passed && cell.treatment.passed,
  ).length
  const regressions = cells.filter(
    (cell) => cell.baseline.passed && !cell.treatment.passed,
  ).length
  const baselinePassRate = rate(baselinePasses, cells.length)
  const treatmentPassRate = rate(treatmentPasses, cells.length)
  return {
    scope: 'verified-activation',
    cells: cells.length,
    baselinePasses,
    treatmentPasses,
    baselinePassRate,
    treatmentPassRate,
    absoluteLift: baselinePassRate === null || treatmentPassRate === null
      ? null
      : round6(treatmentPassRate - baselinePassRate),
    lifts,
    regressions,
    unchanged: cells.length - lifts - regressions,
    exactSignTestPValue: twoSidedSignTest(lifts, regressions),
  }
}

function costNote(
  status: ReportCostStatus,
  measured: number,
  unmeasured: number,
  total: number,
): string {
  if (total === 0) {
    return 'unmeasured: no paired benchmark observations were available'
  }
  if (status === 'unmeasured') {
    return 'unmeasured: no cost values were supplied; missing cost is not reported as zero'
  }
  if (status === 'partial') {
    return `partial: ${measured} of ${total} conditions reported cost; ${unmeasured} unmeasured conditions are excluded from totals rather than treated as zero`
  }
  return `measured: ${measured} of ${total} conditions reported cost`
}

function buildCost(admitted: readonly AdmittedObservation[]): CostReport {
  const totalConditions = admitted.length * 2
  const all = admitted.flatMap((observation) => [
    observation.baseline.costUsd ?? null,
    observation.treatment.costUsd ?? null,
  ])
  const measured = all.filter((cost): cost is number => cost !== null)
  const unmeasured = totalConditions - measured.length
  const status: ReportCostStatus = measured.length === 0
    ? 'unmeasured'
    : measured.length === totalConditions
      ? 'measured'
      : 'partial'
  const baselineCosts = admitted
    .map((observation) => observation.baseline.costUsd ?? null)
    .filter((cost): cost is number => cost !== null)
  const treatmentCosts = admitted
    .map((observation) => observation.treatment.costUsd ?? null)
    .filter((cost): cost is number => cost !== null)
  return {
    currency: 'USD',
    status,
    baselineUsd: baselineCosts.length === 0 ? null : round6(sum(baselineCosts)),
    treatmentUsd: treatmentCosts.length === 0 ? null : round6(sum(treatmentCosts)),
    totalUsd: status === 'measured' ? round6(sum(measured)) : null,
    measuredConditions: measured.length,
    unmeasuredConditions: unmeasured,
    totalConditions,
    note: costNote(status, measured.length, unmeasured, totalConditions),
  }
}

function buildLatency(admitted: readonly AdmittedObservation[]): LatencyReport {
  const conditions = admitted.length
  if (conditions === 0) {
    return {
      conditions: 0,
      baselineMs: null,
      treatmentMs: null,
      totalMs: null,
      meanDeltaMs: null,
    }
  }
  const baselineMs = sum(admitted.map((observation) => observation.baseline.latencyMs))
  const treatmentMs = sum(admitted.map((observation) => observation.treatment.latencyMs))
  return {
    conditions,
    baselineMs,
    treatmentMs,
    totalMs: baselineMs + treatmentMs,
    meanDeltaMs: round6((treatmentMs - baselineMs) / conditions),
  }
}

function buildToolCalls(admitted: readonly AdmittedObservation[]): ToolCallReport {
  const conditions = admitted.length
  if (conditions === 0) {
    return {
      conditions: 0,
      baselineCalls: null,
      treatmentCalls: null,
      totalCalls: null,
      meanDeltaCalls: null,
    }
  }
  const baselineCalls = sum(admitted.map((observation) => observation.baseline.toolCalls))
  const treatmentCalls = sum(admitted.map((observation) => observation.treatment.toolCalls))
  return {
    conditions,
    baselineCalls,
    treatmentCalls,
    totalCalls: baselineCalls + treatmentCalls,
    meanDeltaCalls: round6((treatmentCalls - baselineCalls) / conditions),
  }
}

function buildResources(resources: readonly ExperimentResourceInput[]): ResourceReport[] {
  return [...resources]
    .sort((left, right) => (
      compareText(left.path, right.path)
      || compareText(left.kind, right.kind)
      || compareText(left.status, right.status)
    ))
    .map((resource) => ({
      kind: resource.kind,
      path: resource.path,
      status: resource.status,
      contentHash: resource.contentHash ?? null,
      operationId: resource.operationId ?? null,
      skillId: resource.skillId ?? null,
    }))
}

function sortReceipts(receipts: readonly PublicationReceipt[]): PublicationReceipt[] {
  return [...receipts].sort((left, right) => (
    compareText(left.releaseId, right.releaseId)
    || compareText(left.operationId, right.operationId)
    || compareText(left.channel, right.channel)
  ))
}

function sortExclusions(exclusions: readonly ObservationExclusion[]): ObservationExclusion[] {
  return [...exclusions].sort((left, right) => (
    compareText(left.observationId, right.observationId)
    || compareText(left.taskId, right.taskId)
    || left.trial - right.trial
  ))
}

function buildExclusions(
  admission: ReturnType<typeof admitObservations>,
): ExclusionsReport {
  return {
    total: admission.exclusions.length,
    invalidExposures: sortExclusions(admission.invalidExposures),
    contamination: sortExclusions(admission.contaminationExclusions),
    infrastructureErrors: sortExclusions(admission.infrastructureExclusions),
    duplicates: sortExclusions(admission.duplicateExclusions),
    all: sortExclusions(admission.exclusions),
  }
}

function buildDefects(defects: readonly DefectInput[]): DefectReport[] {
  return [...defects]
    .map((defect) => ({
      code: defect.code,
      message: defect.message,
      severity: defect.severity ?? 'warning',
      taskId: defect.taskId ?? null,
    }))
    .sort((left, right) => (
      compareText(left.code, right.code)
      || compareText(left.taskId ?? '', right.taskId ?? '')
      || compareText(left.message, right.message)
    ))
}

function buildVerification(
  verification: VerificationInput | null | undefined,
): VerificationReport | null {
  if (verification === undefined || verification === null) return null
  return {
    status: verification.status,
    summary: verification.summary,
    evidenceHash: verification.evidenceHash ?? null,
    operationId: verification.operationId ?? null,
  }
}

function buildLimitations(
  input: ExperimentReportInput,
  report: Omit<ExperimentReport, 'limitations'>,
): string[] {
  const limitations: string[] = []
  const seen = new Set<string>()
  function add(limitation: string): void {
    const trimmed = limitation.trim()
    if (trimmed.length === 0 || seen.has(trimmed)) return
    seen.add(trimmed)
    limitations.push(trimmed)
  }

  for (const limitation of input.limitations ?? []) add(limitation)

  if (report.baseline.cells === 0) {
    add('No paired observations were admitted; baseline, treatment, policy, and activated metrics are unmeasured.')
  } else if (report.activatedEffect.cells === 0) {
    add('No verified activated-treatment cells were available; the activated effect is unmeasured.')
  }

  if (report.cost.status === 'unmeasured') {
    add('Cost is unmeasured because no cost values were supplied; cost is reported as null rather than zero.')
  } else if (report.cost.status === 'partial') {
    add('Cost is partially measured; unmeasured conditions are excluded from cost totals rather than treated as zero.')
  }

  if (!report.holdoutReady) {
    add('The sealed holdout is not ready; no holdout result is claimed.')
  } else {
    add('Holdout readiness is caller-attested; holdout observations are not part of this report.')
  }

  if (report.admission.excluded > 0) {
    add(`${report.admission.excluded} observation(s) were excluded from every scored view; see exclusions.`)
  }
  if (report.preflight === null) {
    add('No preflight result was supplied; preflight is unmeasured.')
  }
  if (report.verification === null) {
    add('No verification result was supplied; verification is unmeasured.')
  }
  if (report.defects.some((defect) => defect.severity === 'error')) {
    add('At least one error-severity defect was recorded; the report is not a clean release candidate.')
  }

  return limitations
}

/**
 * Build one deterministic experiment report.
 *
 * Admission is the only path from observations to statistics.  Excluded cells
 * never enter the baseline, treatment, policy, or activated views, and the
 * report keeps their structured reasons beside every metric.
 */
export function buildExperimentReport(input: ExperimentReportInput): ExperimentReport {
  const issues = validateInput(input)
  if (issues.length > 0) throw new InvalidExperimentReportError(issues)

  const options = canonicalOptions(input.options)
  const observations = input.observations ?? []
  const admission = admitObservations(observations)
  const admitted = admission.rawPaired

  const partial = {
    schemaVersion: EXPERIMENT_REPORT_VERSION,
    runId: input.runId,
    stage: input.stage,
    startedAt: input.startedAt,
    finishedAt: input.finishedAt,
    options,
    membership: buildMembership(input.memberships ?? [], input.membershipHashes ?? {}),
    tasks: buildTasks(input, observations, admitted),
    routing: buildRouting(admitted),
    candidateScores: buildCandidateScores(input.candidateScores ?? []),
    admission: admission.counts,
    baseline: buildConditionMetrics(admitted, 'baseline'),
    treatment: buildConditionMetrics(admitted, 'treatment'),
    policy: buildPolicy(admission),
    activatedEffect: buildActivatedEffect(admission),
    resources: buildResources(input.resources ?? []),
    receipts: sortReceipts(input.receipts ?? []),
    preflight: input.preflight ?? null,
    verification: buildVerification(input.verification),
    cost: buildCost(admitted),
    latency: buildLatency(admitted),
    toolCalls: buildToolCalls(admitted),
    exclusions: buildExclusions(admission),
    defects: buildDefects(input.defects ?? []),
    holdoutReady: input.holdoutReady === true,
  } satisfies Omit<ExperimentReport, 'limitations'>

  return {
    ...partial,
    limitations: buildLimitations(input, partial),
  }
}

/**
 * Serialize a report to recursively key-sorted JSON with a trailing newline.
 *
 * `JSON.stringify` preserves insertion order, which makes report bytes depend
 * on how a caller happened to assemble an object.  Sorting here makes the
 * output a pure function of the report values.
 */
export function stableStringify(value: unknown): string {
  return stableJson(value, 0)
}

function stableJson(value: unknown, depth: number): string {
  const indent = '  '.repeat(depth)
  const childIndent = '  '.repeat(depth + 1)

  if (value === null) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError('cannot serialize a non-finite number')
    return JSON.stringify(value)
  }
  if (typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    if (value.length === 0) return '[]'
    const items = value.map((item) => {
      const serialized = item === undefined ? 'null' : stableJson(item, depth + 1)
      return `${childIndent}${serialized}`
    })
    return `[\n${items.join(',\n')}\n${indent}]`
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value)
      .filter(([, child]) => child !== undefined)
      .sort(([left], [right]) => compareText(left, right))
    if (entries.length === 0) return '{}'
    const fields = entries.map(([key, child]) => (
      `${childIndent}${JSON.stringify(key)}: ${stableJson(child, depth + 1)}`
    ))
    return `{\n${fields.join(',\n')}\n${indent}}`
  }
  return 'null'
}

/** Return the canonical pretty JSON bytes for a report. */
export function serializeExperimentReport(report: ExperimentReport): string {
  return `${stableStringify(report)}\n`
}

/**
 * Write one report atomically as canonical JSON.
 *
 * The temporary file lives beside the destination so the rename stays on one
 * filesystem.  The final content is independent of the temporary file name.
 */
export async function writeJsonReport(
  report: ExperimentReport,
  path: string,
): Promise<void> {
  if (path.trim().length === 0) throw new TypeError('json report path must be non-empty')
  const directory = dirname(path)
  const temporary = `${path}.${process.pid}.${Date.now()}.tmp`
  await mkdir(directory, { recursive: true })
  try {
    await writeFile(temporary, serializeExperimentReport(report), { encoding: 'utf8' })
    await rename(temporary, path)
  } catch (error) {
    await rm(temporary, { force: true })
    throw error
  }
}

function formatNumber(value: number): string {
  const rounded = Math.round(value * 1_000_000) / 1_000_000
  return String(rounded)
}

function formatUsd(value: number | null): string {
  return value === null ? 'unmeasured' : `$${formatNumber(value)}`
}

function formatRate(value: number | null): string {
  return value === null ? 'unmeasured' : `${formatNumber(value * 100)}%`
}

function formatPValue(value: number | null): string {
  return value === null ? 'unmeasured' : formatNumber(value)
}

function formatCount(value: number | null): string {
  return value === null ? 'unmeasured' : String(value)
}

function mdCell(value: string): string {
  return value.replace(/\|/g, '\\|').replace(/\r?\n/g, ' ')
}

function mdTable(
  lines: string[],
  headers: readonly string[],
  rows: readonly (readonly string[])[],
): void {
  lines.push(`| ${headers.map(mdCell).join(' | ')} |`)
  lines.push(`| ${headers.map(() => '---').join(' | ')} |`)
  for (const row of rows) {
    lines.push(`| ${row.map((cell) => mdCell(cell)).join(' | ')} |`)
  }
}

function reasonsText(exclusion: ObservationExclusion): string {
  return exclusion.reasons
    .map((reason) => reason.code)
    .filter((code, index, codes) => codes.indexOf(code) === index)
    .sort(compareText)
    .join(', ')
}

/**
 * Render a conservative Markdown report.
 *
 * The renderer never turns a missing measurement into a zero, never describes
 * a descriptive lift as a proven improvement, and always states the holdout
 * readiness boundary.
 */
export function renderMarkdownReport(report: ExperimentReport): string {
  const lines: string[] = []
  const finished = report.finishedAt ?? 'not finished'

  lines.push(`# Experiment report: ${report.runId}`)
  lines.push('')
  lines.push(`- Schema version: ${report.schemaVersion}`)
  lines.push(`- Stage: ${report.stage}`)
  lines.push(`- Started: ${report.startedAt}`)
  lines.push(`- Finished: ${finished}`)
  lines.push(`- Holdout ready: ${report.holdoutReady ? 'yes' : 'no'}`)
  lines.push('')
  lines.push(
    'This report describes one admitted cohort. Unmeasured values are labeled '
    + '`unmeasured`; they are never replaced with zero. Lifts are descriptive '
    + 'for the cells shown and are not a holdout claim.',
  )
  lines.push('')

  lines.push('## Options')
  lines.push('')
  lines.push('```json')
  lines.push(stableStringify(report.options))
  lines.push('```')
  lines.push('')

  lines.push('## Membership')
  lines.push('')
  mdTable(
    lines,
    ['Stage', 'Tasks', 'Membership hash'],
    STAGES.map((stage) => {
      const membership = report.membership[stage]
      return [stage, String(membership.tasks), membership.hash ?? 'unmeasured']
    }),
  )
  lines.push('')
  lines.push(`Combined membership hash: ${report.membership.combinedHash ?? 'unmeasured'}`)
  lines.push('')

  lines.push('## Tasks')
  lines.push('')
  lines.push(`- Total tasks: ${report.tasks.total}`)
  lines.push(`- Train tasks: ${report.tasks.byStage.train}`)
  lines.push(`- Validation tasks: ${report.tasks.byStage.validation}`)
  lines.push('')
  if (report.tasks.rows.length === 0) {
    lines.push('No tasks were supplied or observed.')
  } else {
    mdTable(
      lines,
      ['Task', 'Domain', 'Stage', 'Trials', 'Submitted', 'Admitted', 'Selected', 'Abstained'],
      report.tasks.rows.map((task) => [
        task.taskId,
        task.domain,
        task.stage,
        task.trials.length === 0 ? 'none' : task.trials.join(', '),
        String(task.submittedObservations),
        String(task.admittedCells),
        String(task.selectedCells),
        String(task.abstainedCells),
      ]),
    )
  }
  lines.push('')

  lines.push('## Routing')
  lines.push('')
  lines.push(`- Selected cells: ${report.routing.selectedCells}`)
  lines.push(`- Abstained cells: ${report.routing.abstainedCells}`)
  lines.push(`- Selection rate: ${formatRate(report.routing.selectionRate)}`)
  lines.push(`- Selected task ids: ${report.routing.selectedTaskIds.join(', ') || 'none'}`)
  lines.push(`- Abstained task ids: ${report.routing.abstainedTaskIds.join(', ') || 'none'}`)
  lines.push('')

  lines.push('## Candidate scores')
  lines.push('')
  if (report.candidateScores.length === 0) {
    lines.push('No candidate scores were supplied.')
  } else {
    mdTable(
      lines,
      ['Task', 'Skill', 'Score', 'Reason'],
      report.candidateScores.map((candidate) => [
        candidate.taskId,
        candidate.skillId,
        formatNumber(candidate.score),
        candidate.reason ?? '',
      ]),
    )
  }
  lines.push('')

  lines.push('## Admission')
  lines.push('')
  mdTable(
    lines,
    ['Measure', 'Count'],
    [
      ['Submitted', String(report.admission.submitted)],
      ['Raw paired', String(report.admission.rawPaired)],
      ['Activated', String(report.admission.activated)],
      ['Abstained', String(report.admission.abstained)],
      ['Selective cells', String(report.admission.selectiveCells)],
      ['Excluded', String(report.admission.excluded)],
      ['Invalid exposures', String(report.admission.invalidExposures)],
      ['Contamination', String(report.admission.contaminationExclusions)],
      ['Infrastructure errors', String(report.admission.infrastructureErrors)],
      ['Duplicates', String(report.admission.duplicates)],
    ],
  )
  lines.push('')

  lines.push('## Outcomes')
  lines.push('')
  mdTable(
    lines,
    ['Condition', 'Cells', 'Passes', 'Pass rate', 'Efficiency failures', 'Tool calls', 'Latency (ms)'],
    [
      [
        'Baseline',
        String(report.baseline.cells),
        String(report.baseline.passes),
        formatRate(report.baseline.passRate),
        String(report.baseline.efficiencyFailures),
        formatCount(report.baseline.toolCalls),
        formatCount(report.baseline.latencyMs),
      ],
      [
        'Treatment (as run)',
        String(report.treatment.cells),
        String(report.treatment.passes),
        formatRate(report.treatment.passRate),
        String(report.treatment.efficiencyFailures),
        formatCount(report.treatment.toolCalls),
        formatCount(report.treatment.latencyMs),
      ],
    ],
  )
  lines.push('')
  lines.push('### Selective policy')
  lines.push('')
  mdTable(
    lines,
    ['Measure', 'Value'],
    [
      ['Cells', String(report.policy.cells)],
      ['Selected cells', String(report.policy.selectedCells)],
      ['Abstained cells', String(report.policy.abstainedCells)],
      ['Inherited baseline cells', String(report.policy.inheritedBaselineCells)],
      ['Baseline passes', String(report.policy.baselinePasses)],
      ['Baseline pass rate', formatRate(report.policy.baselinePassRate)],
      ['Policy passes', String(report.policy.policyPasses)],
      ['Policy pass rate', formatRate(report.policy.policyPassRate)],
      ['Absolute lift', formatRate(report.policy.absoluteLift)],
      ['Lifts', String(report.policy.lifts)],
      ['Regressions', String(report.policy.regressions)],
    ],
  )
  lines.push('')
  lines.push('### Activated effect (verified activation only)')
  lines.push('')
  mdTable(
    lines,
    ['Measure', 'Value'],
    [
      ['Scope', report.activatedEffect.scope],
      ['Cells', String(report.activatedEffect.cells)],
      ['Baseline passes', String(report.activatedEffect.baselinePasses)],
      ['Baseline pass rate', formatRate(report.activatedEffect.baselinePassRate)],
      ['Treatment passes', String(report.activatedEffect.treatmentPasses)],
      ['Treatment pass rate', formatRate(report.activatedEffect.treatmentPassRate)],
      ['Absolute lift', formatRate(report.activatedEffect.absoluteLift)],
      ['Lifts', String(report.activatedEffect.lifts)],
      ['Regressions', String(report.activatedEffect.regressions)],
      ['Unchanged', String(report.activatedEffect.unchanged)],
      ['Exact sign-test p-value', formatPValue(report.activatedEffect.exactSignTestPValue)],
    ],
  )
  lines.push('')

  lines.push('## Cost')
  lines.push('')
  lines.push(`Cost status: **${report.cost.status}** — ${report.cost.note}.`)
  lines.push('')
  mdTable(
    lines,
    ['Measure', 'Value'],
    [
      ['Baseline cost', formatUsd(report.cost.baselineUsd)],
      ['Treatment cost', formatUsd(report.cost.treatmentUsd)],
      ['Complete total', formatUsd(report.cost.totalUsd)],
      ['Measured conditions', String(report.cost.measuredConditions)],
      ['Unmeasured conditions', String(report.cost.unmeasuredConditions)],
      ['Total conditions', String(report.cost.totalConditions)],
    ],
  )
  lines.push('')

  lines.push('## Latency and tool calls')
  lines.push('')
  mdTable(
    lines,
    ['Measure', 'Baseline', 'Treatment', 'Total', 'Mean delta'],
    [
      [
        'Latency (ms)',
        formatCount(report.latency.baselineMs),
        formatCount(report.latency.treatmentMs),
        formatCount(report.latency.totalMs),
        formatCount(report.latency.meanDeltaMs),
      ],
      [
        'Tool calls',
        formatCount(report.toolCalls.baselineCalls),
        formatCount(report.toolCalls.treatmentCalls),
        formatCount(report.toolCalls.totalCalls),
        formatCount(report.toolCalls.meanDeltaCalls),
      ],
    ],
  )
  lines.push('')

  lines.push('## Resources')
  lines.push('')
  if (report.resources.length === 0) {
    lines.push('No resources were supplied.')
  } else {
    mdTable(
      lines,
      ['Kind', 'Path', 'Status', 'Content hash', 'Operation', 'Skill'],
      report.resources.map((resource) => [
        resource.kind,
        resource.path,
        resource.status,
        resource.contentHash ?? '',
        resource.operationId ?? '',
        resource.skillId ?? '',
      ]),
    )
  }
  lines.push('')

  lines.push('## Publication receipts')
  lines.push('')
  if (report.receipts.length === 0) {
    lines.push('No publication receipts were supplied.')
  } else {
    mdTable(
      lines,
      ['Operation', 'Release', 'Channel'],
      report.receipts.map((receipt) => [
        receipt.operationId,
        receipt.releaseId,
        receipt.channel,
      ]),
    )
  }
  lines.push('')

  lines.push('## Preflight')
  lines.push('')
  if (report.preflight === null) {
    lines.push('No preflight result was supplied; preflight is unmeasured.')
  } else {
    lines.push(`- Verdict: ${report.preflight.verdict}`)
    lines.push(`- Reject reasons: ${report.preflight.rejectReasons.length}`)
    lines.push(`- Repair reasons: ${report.preflight.repairReasons.length}`)
    lines.push('')
    mdTable(
      lines,
      ['Check', 'Status', 'Reasons'],
      report.preflight.checks.map((check) => [
        check.name,
        check.status,
        check.reasons.map((reason) => `${reason.severity}:${reason.code}`).join(', '),
      ]),
    )
  }
  lines.push('')

  lines.push('## Verification')
  lines.push('')
  if (report.verification === null) {
    lines.push('No verification result was supplied; verification is unmeasured.')
  } else {
    lines.push(`- Status: ${report.verification.status}`)
    lines.push(`- Summary: ${report.verification.summary}`)
    lines.push(`- Evidence hash: ${report.verification.evidenceHash ?? 'unmeasured'}`)
    lines.push(`- Operation: ${report.verification.operationId ?? 'unmeasured'}`)
  }
  lines.push('')

  lines.push('## Exclusions')
  lines.push('')
  lines.push(`Total exclusions: ${report.exclusions.total}`)
  lines.push('')
  if (report.exclusions.total === 0) {
    lines.push('No observations were excluded.')
  } else {
    mdTable(
      lines,
      ['Observation', 'Task', 'Trial', 'Categories', 'Reasons'],
      report.exclusions.all.map((exclusion) => [
        exclusion.observationId,
        exclusion.taskId,
        String(exclusion.trial),
        exclusion.categories.join(', '),
        reasonsText(exclusion),
      ]),
    )
  }
  lines.push('')

  lines.push('## Defects')
  lines.push('')
  if (report.defects.length === 0) {
    lines.push('No defects were supplied.')
  } else {
    mdTable(
      lines,
      ['Severity', 'Code', 'Task', 'Message'],
      report.defects.map((defect) => [
        defect.severity,
        defect.code,
        defect.taskId ?? '',
        defect.message,
      ]),
    )
  }
  lines.push('')

  lines.push('## Limitations')
  lines.push('')
  if (report.limitations.length === 0) {
    lines.push('No limitations were recorded.')
  } else {
    for (const limitation of report.limitations) {
      lines.push(`- ${limitation}`)
    }
  }
  lines.push('')

  return `${lines.join('\n')}\n`
}
