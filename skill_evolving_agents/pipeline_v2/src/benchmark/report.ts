/**
 * Benchmark validity report for paired skill evaluations.
 *
 * The report intentionally keeps three populations separate:
 *
 * - raw paired: every admitted baseline/treatment pair as the treatment ran;
 * - activated-skill: selected cells with verified skill activation (the causal
 *   comparison);
 * - selective policy: the deployed router policy, where selected cells use the
 *   activated treatment and abstentions inherit the baseline outcome.
 *
 * The report has no holdout or tuning fields.  It is a frozen read of one
 * admitted benchmark cohort, not an input to search.
 */

import type {
  AdmissionCounts,
  AdmittedCondition,
  AdmittedObservation,
  BenchmarkObservation,
  ObservationExclusion,
  SelectivePolicyCell,
} from './admission.ts'
import { admitObservations } from './admission.ts'

/** Version of the benchmark validity report. */
export const BENCHMARK_REPORT_VERSION = 1 as const

/** Closed Wilson interval for a pass rate. */
export interface WilsonInterval {
  readonly lower: number
  readonly upper: number
}

/** The three separable benchmark views. */
export type BenchmarkViewKind = 'raw-paired' | 'activated-skill' | 'selective-policy'

/** Paired accuracy statistics for one view. */
export interface AccuracyMetrics {
  readonly cells: number
  readonly baselinePasses: number
  readonly treatmentPasses: number
  readonly baselineFailures: number
  readonly treatmentFailures: number
  readonly baselinePassRate: number | null
  readonly treatmentPassRate: number | null
  readonly absoluteLift: number | null
  readonly lifts: number
  readonly regressions: number
  readonly unchanged: number
  readonly unchangedFailures: number
  readonly baselineWilson95: WilsonInterval | null
  readonly treatmentWilson95: WilsonInterval | null
  readonly exactSignTestPValue: number | null
}

/** Cost, latency, tool-call, and efficiency-budget statistics for one view. */
export interface EfficiencyMetrics {
  readonly cells: number
  readonly baselineToolCalls: number
  readonly treatmentToolCalls: number
  readonly totalToolCalls: number
  readonly meanToolCallDelta: number | null
  readonly baselineLatencyMs: number
  readonly treatmentLatencyMs: number
  readonly totalLatencyMs: number
  readonly meanLatencyMsDelta: number | null
  readonly baselineCostUsd: number
  readonly treatmentCostUsd: number
  readonly totalCostUsd: number
  /** Cells where both baseline and treatment reported a cost. */
  readonly costAvailableCells: number
  /** Cells where at least one condition omitted cost. */
  readonly costUnavailableCells: number
  /** Mean treatment-minus-baseline cost over cells with paired cost only. */
  readonly meanCostUsdDelta: number | null
  readonly baselineEfficiencyFailures: number
  readonly treatmentEfficiencyFailures: number
  readonly treatmentEfficiencyFailureRate: number | null
}

/** Aggregated metrics for one view. */
export interface BenchmarkViewMetrics {
  readonly view: BenchmarkViewKind
  readonly cells: number
  readonly domains: number
  readonly accuracy: AccuracyMetrics
  readonly efficiency: EfficiencyMetrics
}

/** One admitted pair rendered for audit. */
export interface ObservationReportRow {
  readonly observationId: string
  readonly taskId: string
  readonly trial: number
  readonly domain: string
  readonly routerSelected: boolean
  readonly activated: boolean
  readonly baselinePassed: boolean
  readonly treatmentPassed: boolean
  /** Outcome counted by the selective policy: baseline when abstained. */
  readonly selectiveOutcomePassed: boolean
  readonly lift: boolean
  readonly regression: boolean
  readonly baselineEfficiencyFailure: boolean
  readonly treatmentEfficiencyFailure: boolean
  readonly baselineToolCalls: number
  readonly treatmentToolCalls: number
  readonly baselineLatencyMs: number
  readonly treatmentLatencyMs: number
  readonly baselineCostUsd: number | null
  readonly treatmentCostUsd: number | null
}

/** Abstentions and their baseline inheritance. */
export interface AbstentionReport {
  readonly count: number
  readonly baselinePasses: number
  readonly baselinePassRate: number | null
  /** Abstentions always take the baseline outcome for selective scoring. */
  readonly inheritedBaseline: true
  /** An abstention is never treated as an activated treatment. */
  readonly countedAsActivated: false
}

/** Structured exclusions kept outside every scored view. */
export interface ExclusionReport {
  readonly invalidExposures: readonly ObservationExclusion[]
  readonly contaminationExclusions: readonly ObservationExclusion[]
  readonly infrastructureErrors: readonly ObservationExclusion[]
  readonly duplicates: readonly ObservationExclusion[]
}

/** Domain coverage for the admitted cohort. */
export interface DomainCoverage {
  readonly domains: number
  readonly tasks: number
  readonly pairedCells: number
  readonly activatedCells: number
  readonly selectiveCells: number
  readonly activatedDomains: number
  readonly selectiveDomains: number
  readonly tasksByDomain: Readonly<Record<string, number>>
  readonly cellsByDomain: Readonly<Record<string, number>>
}

/** Per-domain report retaining the three view split. */
export interface DomainReport {
  readonly domain: string
  readonly rawPaired: BenchmarkViewMetrics
  readonly activatedSkill: BenchmarkViewMetrics
  readonly selectivePolicy: BenchmarkViewMetrics
}

/** The three views of one benchmark cohort. */
export interface BenchmarkViews {
  /** Every admitted pair, using the treatment exactly as it ran. */
  readonly rawPaired: BenchmarkViewMetrics
  /** Selected pairs with verified activation; the causal skill-effect view. */
  readonly activatedSkill: BenchmarkViewMetrics
  /** Full router policy; abstentions inherit the baseline outcome. */
  readonly selectivePolicy: BenchmarkViewMetrics
}

/** Frozen benchmark validity/admission report. */
export interface BenchmarkReport {
  readonly schemaVersion: typeof BENCHMARK_REPORT_VERSION
  readonly benchmark: string
  readonly cohort: string
  readonly admission: AdmissionCounts
  readonly views: BenchmarkViews
  readonly abstentions: AbstentionReport
  readonly exclusions: ExclusionReport
  readonly coverage: DomainCoverage
  readonly byDomain: readonly DomainReport[]
  readonly observations: readonly ObservationReportRow[]
}

/** Input for a benchmark validity report. */
export interface BenchmarkReportInput {
  readonly benchmark: string
  readonly cohort: string
  readonly observations: readonly BenchmarkObservation[]
}

interface ViewSample {
  readonly domain: string
  readonly baseline: AdmittedCondition
  readonly treatment: AdmittedCondition
}

const Z_95 = 1.959963984540054

function round6(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000
}

function rate(numerator: number, denominator: number): number | null {
  return denominator === 0 ? null : round6(numerator / denominator)
}

/** Closed Wilson score interval for a binomial pass rate. */
export function wilsonInterval(
  successes: number,
  total: number,
  z: number = Z_95,
): WilsonInterval | null {
  if (total <= 0) return null
  const proportion = successes / total
  const denominator = 1 + (z * z) / total
  const centre = (proportion + (z * z) / (2 * total)) / denominator
  const spread = (z * Math.sqrt(
    (proportion * (1 - proportion)) / total + (z * z) / (4 * total * total),
  )) / denominator
  return {
    lower: round6(Math.max(0, centre - spread)),
    upper: round6(Math.min(1, centre + spread)),
  }
}

/**
 * Two-sided exact sign/binomial test for paired lifts versus regressions.
 *
 * Ties are excluded, matching the exact sign test used by the Python report.
 */
export function twoSidedSignTest(lifts: number, regressions: number): number | null {
  const trials = lifts + regressions
  if (trials === 0) return null
  const tailCount = Math.min(lifts, regressions)
  let term = 1 / 2 ** trials
  let tail = 0
  for (let k = 0; k <= tailCount; k += 1) {
    tail += term
    if (k < tailCount) term *= (trials - k) / (k + 1)
  }
  return round6(Math.min(1, 2 * tail))
}

function sampleFromAdmitted(observation: AdmittedObservation): ViewSample {
  return {
    domain: observation.domain,
    baseline: observation.baseline,
    treatment: observation.treatment,
  }
}

function sampleFromSelective(cell: SelectivePolicyCell): ViewSample {
  return {
    domain: cell.domain,
    baseline: cell.baseline,
    treatment: cell.effective,
  }
}

function accuracyMetrics(samples: readonly ViewSample[]): AccuracyMetrics {
  const cells = samples.length
  const baselinePasses = samples.filter(sample => sample.baseline.passed).length
  const treatmentPasses = samples.filter(sample => sample.treatment.passed).length
  const lifts = samples.filter(
    sample => !sample.baseline.passed && sample.treatment.passed,
  ).length
  const regressions = samples.filter(
    sample => sample.baseline.passed && !sample.treatment.passed,
  ).length
  const unchangedFailures = samples.filter(
    sample => !sample.baseline.passed && !sample.treatment.passed,
  ).length
  return {
    cells,
    baselinePasses,
    treatmentPasses,
    baselineFailures: cells - baselinePasses,
    treatmentFailures: cells - treatmentPasses,
    baselinePassRate: rate(baselinePasses, cells),
    treatmentPassRate: rate(treatmentPasses, cells),
    absoluteLift: cells === 0 ? null : round6((treatmentPasses - baselinePasses) / cells),
    lifts,
    regressions,
    unchanged: cells - lifts - regressions,
    unchangedFailures,
    baselineWilson95: wilsonInterval(baselinePasses, cells),
    treatmentWilson95: wilsonInterval(treatmentPasses, cells),
    exactSignTestPValue: twoSidedSignTest(lifts, regressions),
  }
}

function efficiencyMetrics(samples: readonly ViewSample[]): EfficiencyMetrics {
  const cells = samples.length
  let baselineToolCalls = 0
  let treatmentToolCalls = 0
  let baselineLatencyMs = 0
  let treatmentLatencyMs = 0
  let baselineCostUsd = 0
  let treatmentCostUsd = 0
  let costAvailableCells = 0
  let costDelta = 0
  let baselineEfficiencyFailures = 0
  let treatmentEfficiencyFailures = 0
  for (const sample of samples) {
    baselineToolCalls += sample.baseline.toolCalls
    treatmentToolCalls += sample.treatment.toolCalls
    baselineLatencyMs += sample.baseline.latencyMs
    treatmentLatencyMs += sample.treatment.latencyMs
    if (sample.baseline.costUsd !== null) baselineCostUsd += sample.baseline.costUsd
    if (sample.treatment.costUsd !== null) treatmentCostUsd += sample.treatment.costUsd
    if (sample.baseline.costUsd !== null && sample.treatment.costUsd !== null) {
      costAvailableCells += 1
      costDelta += sample.treatment.costUsd - sample.baseline.costUsd
    }
    if (sample.baseline.efficiencyFailure) baselineEfficiencyFailures += 1
    if (sample.treatment.efficiencyFailure) treatmentEfficiencyFailures += 1
  }
  const toolCallDelta = treatmentToolCalls - baselineToolCalls
  const latencyDelta = treatmentLatencyMs - baselineLatencyMs
  return {
    cells,
    baselineToolCalls,
    treatmentToolCalls,
    totalToolCalls: baselineToolCalls + treatmentToolCalls,
    meanToolCallDelta: cells === 0 ? null : round6(toolCallDelta / cells),
    baselineLatencyMs,
    treatmentLatencyMs,
    totalLatencyMs: baselineLatencyMs + treatmentLatencyMs,
    meanLatencyMsDelta: cells === 0 ? null : round6(latencyDelta / cells),
    baselineCostUsd: round6(baselineCostUsd),
    treatmentCostUsd: round6(treatmentCostUsd),
    totalCostUsd: round6(baselineCostUsd + treatmentCostUsd),
    costAvailableCells,
    costUnavailableCells: cells - costAvailableCells,
    meanCostUsdDelta: costAvailableCells === 0
      ? null
      : round6(costDelta / costAvailableCells),
    baselineEfficiencyFailures,
    treatmentEfficiencyFailures,
    treatmentEfficiencyFailureRate: rate(treatmentEfficiencyFailures, cells),
  }
}

function viewMetrics(
  view: BenchmarkViewKind,
  samples: readonly ViewSample[],
): BenchmarkViewMetrics {
  return {
    view,
    cells: samples.length,
    domains: new Set(samples.map(sample => sample.domain)).size,
    accuracy: accuracyMetrics(samples),
    efficiency: efficiencyMetrics(samples),
  }
}

function observationRow(observation: AdmittedObservation): ObservationReportRow {
  return {
    observationId: observation.observationId,
    taskId: observation.taskId,
    trial: observation.trial,
    domain: observation.domain,
    routerSelected: observation.routerSelected,
    activated: observation.activated,
    baselinePassed: observation.baseline.passed,
    treatmentPassed: observation.treatment.passed,
    selectiveOutcomePassed: observation.routerSelected
      ? observation.treatment.passed
      : observation.baseline.passed,
    lift: !observation.baseline.passed && observation.treatment.passed,
    regression: observation.baseline.passed && !observation.treatment.passed,
    baselineEfficiencyFailure: observation.baseline.efficiencyFailure,
    treatmentEfficiencyFailure: observation.treatment.efficiencyFailure,
    baselineToolCalls: observation.baseline.toolCalls,
    treatmentToolCalls: observation.treatment.toolCalls,
    baselineLatencyMs: observation.baseline.latencyMs,
    treatmentLatencyMs: observation.treatment.latencyMs,
    baselineCostUsd: observation.baseline.costUsd,
    treatmentCostUsd: observation.treatment.costUsd,
  }
}

function domainCoverage(
  raw: readonly AdmittedObservation[],
  activated: readonly AdmittedObservation[],
  selective: readonly SelectivePolicyCell[],
): DomainCoverage {
  const domainNames = [...new Set(raw.map(observation => observation.domain))].sort()
  const tasksByDomain: Record<string, number> = {}
  const cellsByDomain: Record<string, number> = {}
  for (const domain of domainNames) {
    const rows = raw.filter(observation => observation.domain === domain)
    cellsByDomain[domain] = rows.length
    tasksByDomain[domain] = new Set(rows.map(observation => observation.taskId)).size
  }
  return {
    domains: domainNames.length,
    tasks: new Set(raw.map(observation => observation.taskId)).size,
    pairedCells: raw.length,
    activatedCells: activated.length,
    selectiveCells: selective.length,
    activatedDomains: new Set(activated.map(observation => observation.domain)).size,
    selectiveDomains: new Set(selective.map(cell => cell.domain)).size,
    tasksByDomain,
    cellsByDomain,
  }
}

function abstentionReport(abstained: readonly AdmittedObservation[]): AbstentionReport {
  const baselinePasses = abstained.filter(observation => observation.baseline.passed).length
  return {
    count: abstained.length,
    baselinePasses,
    baselinePassRate: rate(baselinePasses, abstained.length),
    inheritedBaseline: true,
    countedAsActivated: false,
  }
}

function exclusionReport(
  invalidExposures: readonly ObservationExclusion[],
  contaminationExclusions: readonly ObservationExclusion[],
  infrastructureErrors: readonly ObservationExclusion[],
  duplicates: readonly ObservationExclusion[],
): ExclusionReport {
  return { invalidExposures, contaminationExclusions, infrastructureErrors, duplicates }
}

/**
 * Build a frozen validity report from paired benchmark observations.
 *
 * Duplicate task/trial cells are rejected by admission, so the raw paired,
 * activated, selective, and per-domain statistics all share one unambiguous
 * pairing.  No holdout, search, or tuning fields are emitted.
 */
export function buildBenchmarkReport(input: BenchmarkReportInput): BenchmarkReport {
  const admission = admitObservations(input.observations)
  const rawObservations = admission.rawPaired
  const activated = admission.activated
  const selective = admission.selective

  const rawSamples = rawObservations.map(sampleFromAdmitted)
  const activatedSamples = activated.map(sampleFromAdmitted)
  const selectiveSamples = selective.map(sampleFromSelective)

  const domains = [...new Set(rawSamples.map(sample => sample.domain))].sort()
  const byDomain = domains.map(domain => ({
    domain,
    rawPaired: viewMetrics(
      'raw-paired',
      rawSamples.filter(sample => sample.domain === domain),
    ),
    activatedSkill: viewMetrics(
      'activated-skill',
      activatedSamples.filter(sample => sample.domain === domain),
    ),
    selectivePolicy: viewMetrics(
      'selective-policy',
      selectiveSamples.filter(sample => sample.domain === domain),
    ),
  }))

  return {
    schemaVersion: BENCHMARK_REPORT_VERSION,
    benchmark: input.benchmark,
    cohort: input.cohort,
    admission: admission.counts,
    views: {
      rawPaired: viewMetrics('raw-paired', rawSamples),
      activatedSkill: viewMetrics('activated-skill', activatedSamples),
      selectivePolicy: viewMetrics('selective-policy', selectiveSamples),
    },
    abstentions: abstentionReport(admission.abstained),
    exclusions: exclusionReport(
      admission.invalidExposures,
      admission.contaminationExclusions,
      admission.infrastructureExclusions,
      admission.duplicateExclusions,
    ),
    coverage: domainCoverage(rawObservations, activated, selective),
    byDomain,
    observations: rawObservations.map(observationRow),
  }
}
