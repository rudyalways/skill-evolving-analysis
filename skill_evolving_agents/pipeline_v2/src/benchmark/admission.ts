/**
 * Benchmark admission for paired baseline/treatment cells.
 *
 * Admission is the gate between raw runner output and any benchmark statistic.
 * A cell is admitted into the raw paired view only when the pair is structurally
 * unique, free of contamination and infrastructure failure, and its treatment
 * exposure agrees with the router decision.  The same admitted cell can then be
 * read through three intentionally separate views:
 *
 * - raw paired: every admitted cell, using the treatment as it actually ran;
 * - activated-skill causal: selected cells whose skill exposure was verified;
 * - selective full policy: selected cells plus abstentions, where an abstention
 *   inherits the baseline outcome and is never counted as an activated treatment.
 *
 * Contaminated, infrastructure-failed, duplicate, and exposure-invalid cells are
 * excluded with structured reasons rather than silently dropped or coerced.
 */

/** Version of the benchmark admission result. */
export const BENCHMARK_ADMISSION_VERSION = 1 as const

/** Skill mode reported by the runner for one benchmark condition. */
export type SkillMode = 'with-skill' | 'without-skill'

/** Observable evidence that a skill was exposed to the agent. */
export type SkillActivationMode = 'read' | 'injected'

/** One condition's skill-exposure audit. */
export interface SkillExposureAudit {
  /** Skill mode the runner claims it used. */
  readonly skillMode: SkillMode
  /** Whether the trajectory audit completed and produced a verdict. */
  readonly verified: boolean
  /** Whether the audit observed a SKILL.md read or full skill injection. */
  readonly activated: boolean
  /** How activation was observed; null when no skill exposure was observed. */
  readonly activationMode: SkillActivationMode | null
}

/** One measured condition (baseline or treatment) in a paired cell. */
export interface ConditionObservation {
  /** Whether the task verifier marked this condition as passed. */
  readonly passed: boolean
  /** Partial verifier reward when available. */
  readonly reward?: number
  /** Number of tool calls made by the agent. */
  readonly toolCalls: number
  /** Agent execution latency in milliseconds. */
  readonly latencyMs: number
  /** Agent cost in US dollars; null or omitted means unavailable. */
  readonly costUsd?: number | null
  /** Whether a hard efficiency budget classified this condition as a failure. */
  readonly efficiencyFailure: boolean
  /** Skill mode and trajectory exposure evidence for this condition. */
  readonly exposure: SkillExposureAudit
  /** Contamination reason codes found by the trial validity audit. */
  readonly contamination: readonly string[]
  /** Infrastructure failure message, or null when the condition ran normally. */
  readonly infrastructureError: string | null
}

/** One paired baseline/treatment benchmark observation. */
export interface BenchmarkObservation {
  /** Stable identity of this paired cell. */
  readonly observationId: string
  /** Benchmark task identity. */
  readonly taskId: string
  /** Deterministic repetition ordinal within the task. */
  readonly trial: number
  /** Domain used for coverage and per-domain reporting. */
  readonly domain: string
  /** Whether the selective router chose to apply a skill for this task. */
  readonly routerSelected: boolean
  /** Baseline condition, normally run without a skill. */
  readonly baseline: ConditionObservation
  /** Treatment condition, run with or without a skill according to the policy. */
  readonly treatment: ConditionObservation
}

/** Stable codes explaining why a paired observation was excluded. */
export type AdmissionReasonCode =
  | 'duplicate-observation'
  | 'contaminated-observation'
  | 'infrastructure-error'
  | 'selected-treatment-not-run-with-skill'
  | 'treatment-exposure-unverified'
  | 'treatment-skill-not-activated'
  | 'abstained-treatment-ran-with-skill'
  | 'abstained-treatment-activated'
  | 'contradictory-exposure-evidence'

/** Condition a structured admission reason applies to. */
export type ObservationConditionName = 'baseline' | 'treatment' | 'pair'

/** Structured reason for excluding a paired observation. */
export interface AdmissionReason {
  readonly code: AdmissionReasonCode
  readonly condition: ObservationConditionName
  readonly detail: string
}

/** Primary class of an admission exclusion. */
export type ExclusionCategory =
  | 'duplicate-observation'
  | 'contamination'
  | 'infrastructure-error'
  | 'invalid-exposure'

/** A paired observation rejected by admission. */
export interface ObservationExclusion {
  readonly observationId: string
  readonly taskId: string
  readonly trial: number
  readonly domain: string
  readonly categories: readonly ExclusionCategory[]
  readonly reasons: readonly AdmissionReason[]
}

/** A condition normalized into the admitted benchmark shape. */
export interface AdmittedCondition {
  readonly passed: boolean
  readonly reward: number | null
  readonly toolCalls: number
  readonly latencyMs: number
  readonly costUsd: number | null
  readonly efficiencyFailure: boolean
  readonly skillMode: SkillMode
  readonly activationMode: SkillActivationMode | null
}

/** One admitted paired observation used by the raw paired and causal views. */
export interface AdmittedObservation {
  readonly observationId: string
  readonly taskId: string
  readonly trial: number
  readonly domain: string
  readonly routerSelected: boolean
  /** True only for a selected treatment with verified skill activation. */
  readonly activated: boolean
  readonly baseline: AdmittedCondition
  readonly treatment: AdmittedCondition
}

/** One cell of the selective full-policy view. */
export interface SelectivePolicyCell {
  readonly observationId: string
  readonly taskId: string
  readonly trial: number
  readonly domain: string
  /** Whether the effective outcome came from activation or baseline inheritance. */
  readonly source: 'activated-treatment' | 'baseline-abstention'
  readonly baseline: AdmittedCondition
  /** Effective policy condition: treatment for selected cells, baseline for abstentions. */
  readonly effective: AdmittedCondition
}

/** Aggregate admission counts for one benchmark report. */
export interface AdmissionCounts {
  readonly submitted: number
  readonly rawPaired: number
  readonly activated: number
  readonly abstained: number
  readonly selectiveCells: number
  readonly excluded: number
  readonly invalidExposures: number
  readonly contaminationExclusions: number
  readonly infrastructureErrors: number
  readonly duplicates: number
}

/** Admission result separating the raw, activated, and selective views. */
export interface AdmissionResult {
  readonly schemaVersion: typeof BENCHMARK_ADMISSION_VERSION
  /** Admitted pairs, using the treatment outcome exactly as it ran. */
  readonly rawPaired: readonly AdmittedObservation[]
  /** Selected pairs with verified activation; causal skill-effect population. */
  readonly activated: readonly AdmittedObservation[]
  /** Valid abstentions; their treatment run is not an activated treatment. */
  readonly abstained: readonly AdmittedObservation[]
  /** Full selective policy, with abstentions inheriting the baseline outcome. */
  readonly selective: readonly SelectivePolicyCell[]
  readonly exclusions: readonly ObservationExclusion[]
  readonly invalidExposures: readonly ObservationExclusion[]
  readonly contaminationExclusions: readonly ObservationExclusion[]
  readonly infrastructureExclusions: readonly ObservationExclusion[]
  readonly duplicateExclusions: readonly ObservationExclusion[]
  readonly counts: AdmissionCounts
}

const CONDITIONS = ['baseline', 'treatment'] as const

const EXCLUSION_CATEGORY_ORDER: readonly ExclusionCategory[] = [
  'duplicate-observation',
  'contamination',
  'infrastructure-error',
  'invalid-exposure',
]

function reason(
  code: AdmissionReasonCode,
  condition: ObservationConditionName,
  detail: string,
): AdmissionReason {
  return { code, condition, detail }
}

function contaminationReasons(observation: BenchmarkObservation): AdmissionReason[] {
  const reasons: AdmissionReason[] = []
  for (const condition of CONDITIONS) {
    for (const code of observation[condition].contamination) {
      reasons.push(reason(
        'contaminated-observation',
        condition,
        code.trim().length > 0 ? code : 'contaminated trial',
      ))
    }
  }
  return reasons
}

function infrastructureReasons(observation: BenchmarkObservation): AdmissionReason[] {
  const reasons: AdmissionReason[] = []
  for (const condition of CONDITIONS) {
    const failure = observation[condition].infrastructureError
    if (failure !== null && failure.trim().length > 0) {
      reasons.push(reason('infrastructure-error', condition, failure))
    }
  }
  return reasons
}

function exposureReasons(observation: BenchmarkObservation): AdmissionReason[] {
  const exposure = observation.treatment.exposure
  const reasons: AdmissionReason[] = []
  const contradictions: string[] = []
  const hasSkillEvidence = exposure.activated || exposure.activationMode !== null
  if (hasSkillEvidence && exposure.skillMode !== 'with-skill') {
    contradictions.push('skill activation evidence present while skill_mode is without-skill')
  }
  if (exposure.activated && exposure.activationMode === null) {
    contradictions.push('skill activation reported without an activation mode')
  }
  if (!exposure.activated && exposure.activationMode !== null) {
    contradictions.push('activation mode reported without observed skill activation')
  }
  if (exposure.activated && !exposure.verified) {
    contradictions.push('skill activation reported without a completed exposure audit')
  }
  if (!observation.routerSelected && exposure.skillMode === 'with-skill') {
    contradictions.push('router abstained while treatment skill_mode is with-skill')
  }
  if (!observation.routerSelected && exposure.activated) {
    contradictions.push('router abstained but treatment activated a skill')
  }
  if (contradictions.length > 0) {
    reasons.push(reason('contradictory-exposure-evidence', 'treatment', contradictions.join('; ')))
  }

  if (observation.routerSelected) {
    if (exposure.skillMode !== 'with-skill') {
      reasons.push(reason(
        'selected-treatment-not-run-with-skill',
        'treatment',
        `selected treatment ran with skill_mode=${exposure.skillMode}`,
      ))
    }
    if (!exposure.verified) {
      reasons.push(reason(
        'treatment-exposure-unverified',
        'treatment',
        'selected treatment exposure audit did not complete',
      ))
    }
    if (exposure.verified && !exposure.activated) {
      reasons.push(reason(
        'treatment-skill-not-activated',
        'treatment',
        'selected with-skill treatment showed no SKILL.md read or full skill injection',
      ))
    }
  } else {
    if (exposure.skillMode === 'with-skill') {
      reasons.push(reason(
        'abstained-treatment-ran-with-skill',
        'treatment',
        'router abstained but treatment ran with skill_mode=with-skill',
      ))
    }
    if (exposure.activated) {
      reasons.push(reason(
        'abstained-treatment-activated',
        'treatment',
        'router abstained but treatment showed an activated skill',
      ))
    }
  }
  return reasons
}

function categoriesFor(reasons: readonly AdmissionReason[]): ExclusionCategory[] {
  const categories = new Set<ExclusionCategory>()
  for (const item of reasons) {
    switch (item.code) {
      case 'duplicate-observation':
        categories.add('duplicate-observation')
        break
      case 'contaminated-observation':
        categories.add('contamination')
        break
      case 'infrastructure-error':
        categories.add('infrastructure-error')
        break
      default:
        categories.add('invalid-exposure')
        break
    }
  }
  return EXCLUSION_CATEGORY_ORDER.filter(category => categories.has(category))
}

function exclusionFor(
  observation: BenchmarkObservation,
  reasons: readonly AdmissionReason[],
): ObservationExclusion {
  return {
    observationId: observation.observationId,
    taskId: observation.taskId,
    trial: observation.trial,
    domain: observation.domain,
    categories: categoriesFor(reasons),
    reasons,
  }
}

function normalizeCondition(condition: ConditionObservation): AdmittedCondition {
  return {
    passed: condition.passed,
    reward: condition.reward ?? null,
    toolCalls: condition.toolCalls,
    latencyMs: condition.latencyMs,
    costUsd: condition.costUsd ?? null,
    efficiencyFailure: condition.efficiencyFailure,
    skillMode: condition.exposure.skillMode,
    activationMode: condition.exposure.activationMode,
  }
}

function admittedFor(observation: BenchmarkObservation): AdmittedObservation {
  return {
    observationId: observation.observationId,
    taskId: observation.taskId,
    trial: observation.trial,
    domain: observation.domain,
    routerSelected: observation.routerSelected,
    activated: observation.routerSelected && observation.treatment.exposure.activated,
    baseline: normalizeCondition(observation.baseline),
    treatment: normalizeCondition(observation.treatment),
  }
}

function selectiveCellFor(observation: AdmittedObservation): SelectivePolicyCell {
  const inherited = !observation.routerSelected
  return {
    observationId: observation.observationId,
    taskId: observation.taskId,
    trial: observation.trial,
    domain: observation.domain,
    source: inherited ? 'baseline-abstention' : 'activated-treatment',
    baseline: observation.baseline,
    effective: inherited ? observation.baseline : observation.treatment,
  }
}

function hasCategory(
  exclusion: ObservationExclusion,
  category: ExclusionCategory,
): boolean {
  return exclusion.categories.includes(category)
}

/**
 * Admit paired benchmark observations.
 *
 * Duplicate cells are rejected rather than averaged: the first occurrence of an
 * observation id or task/trial pair is kept and every later occurrence is
 * reported as a duplicate exclusion.  This makes pairing explicit and avoids
 * inflating sample size or confidence.
 */
export function admitObservations(
  observations: readonly BenchmarkObservation[],
): AdmissionResult {
  const rawPaired: AdmittedObservation[] = []
  const activated: AdmittedObservation[] = []
  const abstained: AdmittedObservation[] = []
  const exclusions: ObservationExclusion[] = []
  const seenObservationIds = new Set<string>()
  const seenPairs = new Set<string>()

  for (const observation of observations) {
    const pairKey = `${observation.taskId}\u0000${observation.trial}`
    if (seenObservationIds.has(observation.observationId) || seenPairs.has(pairKey)) {
      exclusions.push(exclusionFor(observation, [reason(
        'duplicate-observation',
        'pair',
        `duplicate paired cell for task=${observation.taskId} trial=${observation.trial}`,
      )]))
      continue
    }
    seenObservationIds.add(observation.observationId)
    seenPairs.add(pairKey)

    const reasons = [
      ...contaminationReasons(observation),
      ...infrastructureReasons(observation),
      ...exposureReasons(observation),
    ]
    if (reasons.length > 0) {
      exclusions.push(exclusionFor(observation, reasons))
      continue
    }

    const admitted = admittedFor(observation)
    rawPaired.push(admitted)
    if (admitted.activated) activated.push(admitted)
    if (!admitted.routerSelected) abstained.push(admitted)
  }

  const selective = rawPaired.map(selectiveCellFor)
  const invalidExposures = exclusions.filter(item => hasCategory(item, 'invalid-exposure'))
  const contaminationExclusions = exclusions.filter(item => hasCategory(item, 'contamination'))
  const infrastructureExclusions = exclusions.filter(item => hasCategory(item, 'infrastructure-error'))
  const duplicateExclusions = exclusions.filter(item => hasCategory(item, 'duplicate-observation'))

  return {
    schemaVersion: BENCHMARK_ADMISSION_VERSION,
    rawPaired,
    activated,
    abstained,
    selective,
    exclusions,
    invalidExposures,
    contaminationExclusions,
    infrastructureExclusions,
    duplicateExclusions,
    counts: {
      submitted: observations.length,
      rawPaired: rawPaired.length,
      activated: activated.length,
      abstained: abstained.length,
      selectiveCells: selective.length,
      excluded: exclusions.length,
      invalidExposures: invalidExposures.length,
      contaminationExclusions: contaminationExclusions.length,
      infrastructureErrors: infrastructureExclusions.length,
      duplicates: duplicateExclusions.length,
    },
  }
}
