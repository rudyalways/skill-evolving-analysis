import { describe, expect, it } from 'vitest'
import {
  admitObservations,
} from '../src/benchmark/admission.ts'
import type {
  BenchmarkObservation,
  ConditionObservation,
  ObservationExclusion,
  SkillActivationMode,
  SkillExposureAudit,
  SkillMode,
} from '../src/benchmark/admission.ts'
import {
  buildBenchmarkReport,
  wilsonInterval,
} from '../src/benchmark/report.ts'
import type { WilsonInterval } from '../src/benchmark/report.ts'

interface ExposureOptions {
  readonly verified?: boolean
  readonly activated?: boolean
  readonly activationMode?: SkillActivationMode | null
}

function exposure(
  skillMode: SkillMode,
  options: ExposureOptions = {},
): SkillExposureAudit {
  const activated = options.activated ?? (skillMode === 'with-skill')
  return {
    skillMode,
    verified: options.verified ?? true,
    activated,
    activationMode: options.activationMode === undefined
      ? (activated ? 'read' : null)
      : options.activationMode,
  }
}

interface ConditionOptions {
  readonly passed?: boolean
  readonly toolCalls?: number
  readonly latencyMs?: number
  readonly costUsd?: number | null
  readonly efficiencyFailure?: boolean
  readonly exposure?: SkillExposureAudit
  readonly contamination?: readonly string[]
  readonly infrastructureError?: string | null
}

function condition(options: ConditionOptions = {}): ConditionObservation {
  return {
    passed: options.passed ?? false,
    reward: options.passed === true ? 1 : 0,
    toolCalls: options.toolCalls ?? 10,
    latencyMs: options.latencyMs ?? 1_000,
    costUsd: options.costUsd === undefined ? 0.1 : options.costUsd,
    efficiencyFailure: options.efficiencyFailure ?? false,
    exposure: options.exposure ?? exposure('without-skill'),
    contamination: options.contamination ?? [],
    infrastructureError: options.infrastructureError === undefined
      ? null
      : options.infrastructureError,
  }
}

interface ObservationOptions {
  readonly observationId?: string
  readonly taskId?: string
  readonly trial?: number
  readonly domain?: string
  readonly routerSelected?: boolean
  readonly baseline?: ConditionObservation
  readonly treatment?: ConditionObservation
}

function observation(options: ObservationOptions = {}): BenchmarkObservation {
  const routerSelected = options.routerSelected ?? true
  const treatment = options.treatment ?? (routerSelected
    ? condition({ passed: true, exposure: exposure('with-skill') })
    : condition({ passed: false, exposure: exposure('without-skill') }))
  return {
    observationId: options.observationId ?? 'observation-1',
    taskId: options.taskId ?? 'task-1',
    trial: options.trial ?? 1,
    domain: options.domain ?? 'domain-1',
    routerSelected,
    baseline: options.baseline ?? condition({ passed: false }),
    treatment,
  }
}

function reasonCodes(exclusion: ObservationExclusion | undefined): readonly string[] {
  return exclusion === undefined ? [] : exclusion.reasons.map(reason => reason.code)
}

function requireInterval(interval: WilsonInterval | null): WilsonInterval {
  if (interval === null) throw new Error('expected a Wilson interval')
  return interval
}

describe('benchmark admission', () => {
  it('admits a selected with-skill cell as activated', () => {
    const result = admitObservations([observation({ observationId: 'cell-1' })])
    expect(result.counts).toMatchObject({
      submitted: 1,
      rawPaired: 1,
      activated: 1,
      abstained: 0,
      selectiveCells: 1,
      excluded: 0,
    })
    expect(result.rawPaired[0]?.activated).toBe(true)
    expect(result.activated).toHaveLength(1)
    expect(result.abstained).toHaveLength(0)
    expect(result.selective[0]?.source).toBe('activated-treatment')
    expect(result.selective[0]?.effective.passed).toBe(true)
    expect(result.exclusions).toHaveLength(0)
  })

  it('inherits the baseline outcome for an abstention without activating it', () => {
    const abstained = observation({
      observationId: 'cell-1',
      routerSelected: false,
      baseline: condition({ passed: true }),
      treatment: condition({ passed: false, exposure: exposure('without-skill') }),
    })
    const result = admitObservations([abstained])
    expect(result.activated).toHaveLength(0)
    expect(result.abstained).toHaveLength(1)
    expect(result.rawPaired[0]?.activated).toBe(false)
    expect(result.rawPaired[0]?.treatment.passed).toBe(false)
    expect(result.selective).toHaveLength(1)
    expect(result.selective[0]?.source).toBe('baseline-abstention')
    expect(result.selective[0]?.effective.passed).toBe(true)
  })

  it('rejects a selected treatment that did not run with-skill', () => {
    const result = admitObservations([observation({
      observationId: 'cell-1',
      treatment: condition({ exposure: exposure('without-skill') }),
    })])
    expect(result.counts.rawPaired).toBe(0)
    expect(result.invalidExposures).toHaveLength(1)
    expect(result.invalidExposures[0]?.categories).toContain('invalid-exposure')
    expect(reasonCodes(result.invalidExposures[0])).toContain(
      'selected-treatment-not-run-with-skill',
    )
  })

  it('rejects contradictory router and exposure evidence', () => {
    const abstainedWithSkill = observation({
      observationId: 'cell-1',
      routerSelected: false,
      baseline: condition({ passed: true }),
      treatment: condition({ passed: true, exposure: exposure('with-skill') }),
    })
    const abstainedResult = admitObservations([abstainedWithSkill])
    expect(reasonCodes(abstainedResult.invalidExposures[0])).toContain(
      'abstained-treatment-ran-with-skill',
    )
    expect(reasonCodes(abstainedResult.invalidExposures[0])).toContain(
      'contradictory-exposure-evidence',
    )

    const activatedWithoutSkill = observation({
      observationId: 'cell-2',
      treatment: condition({
        exposure: exposure('without-skill', { activated: true, activationMode: 'read' }),
      }),
    })
    const activatedResult = admitObservations([activatedWithoutSkill])
    expect(reasonCodes(activatedResult.invalidExposures[0])).toContain(
      'selected-treatment-not-run-with-skill',
    )
    expect(reasonCodes(activatedResult.invalidExposures[0])).toContain(
      'contradictory-exposure-evidence',
    )
  })

  it('rejects a with-skill treatment whose skill was not activated', () => {
    const result = admitObservations([observation({
      observationId: 'cell-1',
      treatment: condition({
        passed: true,
        exposure: exposure('with-skill', { activated: false }),
      }),
    })])
    expect(result.counts.rawPaired).toBe(0)
    expect(result.invalidExposures).toHaveLength(1)
    expect(reasonCodes(result.invalidExposures[0])).toContain(
      'treatment-skill-not-activated',
    )
  })

  it('rejects a with-skill treatment whose exposure audit is unverified', () => {
    const result = admitObservations([observation({
      observationId: 'cell-1',
      treatment: condition({
        passed: true,
        exposure: exposure('with-skill', { verified: false, activated: false }),
      }),
    })])
    expect(result.invalidExposures).toHaveLength(1)
    expect(reasonCodes(result.invalidExposures[0])).toContain(
      'treatment-exposure-unverified',
    )
  })

  it('rejects duplicate observation ids and duplicate task/trial pairs', () => {
    const cell = observation({ observationId: 'duplicate', taskId: 'task-dup', trial: 1 })
    const sameCell = admitObservations([cell, cell])
    expect(sameCell.counts.rawPaired).toBe(1)
    expect(sameCell.counts.duplicates).toBe(1)
    expect(sameCell.duplicateExclusions).toHaveLength(1)
    expect(reasonCodes(sameCell.duplicateExclusions[0])).toContain(
      'duplicate-observation',
    )
    expect(sameCell.duplicateExclusions[0]?.categories).toContain('duplicate-observation')

    const samePair = admitObservations([
      cell,
      observation({ observationId: 'duplicate-2', taskId: 'task-dup', trial: 1 }),
    ])
    expect(samePair.counts.rawPaired).toBe(1)
    expect(samePair.counts.duplicates).toBe(1)
  })

  it('excludes contaminated and infrastructure-failed pairs with structured reasons', () => {
    const contaminated = observation({
      observationId: 'contaminated',
      baseline: condition({
        contamination: ['answer-or-oracle-discovery'],
      }),
    })
    const infrastructure = observation({
      observationId: 'infrastructure',
      taskId: 'task-2',
      treatment: condition({
        exposure: exposure('with-skill'),
        infrastructureError: 'container exited 137',
      }),
    })
    const report = buildBenchmarkReport({
      benchmark: 'bench',
      cohort: 'cohort',
      observations: [contaminated, infrastructure],
    })
    expect(report.admission.rawPaired).toBe(0)
    expect(report.views.rawPaired.cells).toBe(0)
    expect(report.exclusions.contaminationExclusions).toHaveLength(1)
    expect(reasonCodes(report.exclusions.contaminationExclusions[0])).toContain(
      'contaminated-observation',
    )
    expect(report.exclusions.infrastructureErrors).toHaveLength(1)
    expect(reasonCodes(report.exclusions.infrastructureErrors[0])).toContain(
      'infrastructure-error',
    )
    expect(report.views.rawPaired.accuracy.baselinePassRate).toBeNull()
  })
})

describe('benchmark validity report', () => {
  const validA = observation({
    observationId: 'a',
    taskId: 'task-a',
    domain: 'domain-a',
    baseline: condition({ passed: false, toolCalls: 10, latencyMs: 1_000, costUsd: 0.1 }),
    treatment: condition({
      passed: true,
      toolCalls: 8,
      latencyMs: 900,
      costUsd: 0.2,
      exposure: exposure('with-skill'),
    }),
  })
  const validB = observation({
    observationId: 'b',
    taskId: 'task-b',
    domain: 'domain-b',
    baseline: condition({ passed: false, toolCalls: 12, latencyMs: 1_200, costUsd: 0.2 }),
    treatment: condition({
      passed: true,
      toolCalls: 10,
      latencyMs: 1_000,
      costUsd: null,
      exposure: exposure('with-skill'),
    }),
  })
  const abstained = observation({
    observationId: 'c',
    taskId: 'task-c',
    domain: 'domain-a',
    routerSelected: false,
    baseline: condition({ passed: true, toolCalls: 9, latencyMs: 800, costUsd: 0.3 }),
    treatment: condition({
      passed: false,
      toolCalls: 11,
      latencyMs: 1_100,
      costUsd: 0.4,
      exposure: exposure('without-skill'),
    }),
  })
  const invalid = observation({
    observationId: 'd',
    taskId: 'task-d',
    domain: 'domain-b',
    treatment: condition({ passed: true, exposure: exposure('without-skill') }),
  })

  const report = buildBenchmarkReport({
    benchmark: 'bench',
    cohort: 'cohort',
    observations: [validA, validB, abstained, invalid],
  })

  it('separates raw, activated, and selective populations', () => {
    expect(report.admission).toMatchObject({
      submitted: 4,
      rawPaired: 3,
      activated: 2,
      abstained: 1,
      selectiveCells: 3,
      excluded: 1,
      invalidExposures: 1,
    })
    expect(report.views.rawPaired.cells).toBe(3)
    expect(report.views.activatedSkill.cells).toBe(2)
    expect(report.views.selectivePolicy.cells).toBe(3)
    expect(report.abstentions).toMatchObject({
      count: 1,
      baselinePasses: 1,
      baselinePassRate: 1,
      inheritedBaseline: true,
      countedAsActivated: false,
    })
  })

  it('computes raw, activated, and selective pass rates and lifts', () => {
    const raw = report.views.rawPaired.accuracy
    expect(raw.baselinePasses).toBe(1)
    expect(raw.treatmentPasses).toBe(2)
    expect(raw.baselinePassRate).toBe(0.333333)
    expect(raw.treatmentPassRate).toBe(0.666667)
    expect(raw.absoluteLift).toBe(0.333333)
    expect(raw.lifts).toBe(2)
    expect(raw.regressions).toBe(1)
    expect(raw.baselineFailures).toBe(2)
    expect(raw.treatmentFailures).toBe(1)
    expect(raw.exactSignTestPValue).toBe(1)

    const activated = report.views.activatedSkill.accuracy
    expect(activated.baselinePasses).toBe(0)
    expect(activated.treatmentPasses).toBe(2)
    expect(activated.baselinePassRate).toBe(0)
    expect(activated.treatmentPassRate).toBe(1)
    expect(activated.absoluteLift).toBe(1)
    expect(activated.lifts).toBe(2)
    expect(activated.regressions).toBe(0)
    expect(activated.exactSignTestPValue).toBe(0.5)

    const selective = report.views.selectivePolicy.accuracy
    expect(selective.baselinePasses).toBe(1)
    expect(selective.treatmentPasses).toBe(3)
    expect(selective.baselinePassRate).toBe(0.333333)
    expect(selective.treatmentPassRate).toBe(1)
    expect(selective.absoluteLift).toBe(0.666667)
    expect(selective.lifts).toBe(2)
    expect(selective.regressions).toBe(0)
    expect(selective.exactSignTestPValue).toBe(0.5)
  })

  it('computes Wilson confidence intervals for both views', () => {
    const rawBaseline = requireInterval(report.views.rawPaired.accuracy.baselineWilson95)
    expect(rawBaseline.lower).toBe(0.061492)
    expect(rawBaseline.upper).toBe(0.79234)

    const activatedBaseline = requireInterval(
      report.views.activatedSkill.accuracy.baselineWilson95,
    )
    expect(activatedBaseline.lower).toBe(0)
    expect(activatedBaseline.upper).toBe(0.65762)

    const activatedTreatment = requireInterval(
      report.views.activatedSkill.accuracy.treatmentWilson95,
    )
    expect(activatedTreatment.lower).toBe(0.34238)
    expect(activatedTreatment.upper).toBe(1)

    const selectiveTreatment = requireInterval(
      report.views.selectivePolicy.accuracy.treatmentWilson95,
    )
    expect(selectiveTreatment.lower).toBe(0.438503)
    expect(selectiveTreatment.upper).toBe(1)

    expect(wilsonInterval(0, 0)).toBeNull()
  })

  it('classifies efficiency failures without erasing accuracy passes', () => {
    const efficiencyReport = buildBenchmarkReport({
      benchmark: 'bench',
      cohort: 'cohort',
      observations: [observation({
        observationId: 'efficient',
        baseline: condition({
          passed: true,
          toolCalls: 20,
          latencyMs: 2_000,
          costUsd: 0.2,
        }),
        treatment: condition({
          passed: true,
          toolCalls: 140,
          latencyMs: 9_500,
          costUsd: 2.5,
          efficiencyFailure: true,
          exposure: exposure('with-skill'),
        }),
      })],
    })
    const view = efficiencyReport.views.activatedSkill
    expect(view.accuracy.treatmentPasses).toBe(1)
    expect(view.accuracy.regressions).toBe(0)
    expect(view.efficiency.baselineEfficiencyFailures).toBe(0)
    expect(view.efficiency.treatmentEfficiencyFailures).toBe(1)
    expect(view.efficiency.treatmentEfficiencyFailureRate).toBe(1)
    expect(view.efficiency.baselineToolCalls).toBe(20)
    expect(view.efficiency.treatmentToolCalls).toBe(140)
    expect(view.efficiency.meanToolCallDelta).toBe(120)
    expect(view.efficiency.meanLatencyMsDelta).toBe(7_500)
    expect(view.efficiency.baselineCostUsd).toBe(0.2)
    expect(view.efficiency.treatmentCostUsd).toBe(2.5)
    expect(view.efficiency.costAvailableCells).toBe(1)
    expect(efficiencyReport.observations[0]?.treatmentEfficiencyFailure).toBe(true)
  })

  it('keeps abstention costs and outcomes in the selective view only', () => {
    const rawEfficiency = report.views.rawPaired.efficiency
    expect(rawEfficiency.costAvailableCells).toBe(2)
    expect(rawEfficiency.costUnavailableCells).toBe(1)
    expect(rawEfficiency.baselineCostUsd).toBe(0.6)
    expect(rawEfficiency.treatmentCostUsd).toBe(0.6)
    expect(rawEfficiency.meanCostUsdDelta).toBe(0.1)

    const activatedEfficiency = report.views.activatedSkill.efficiency
    expect(activatedEfficiency.costAvailableCells).toBe(1)
    expect(activatedEfficiency.costUnavailableCells).toBe(1)
    expect(activatedEfficiency.meanCostUsdDelta).toBe(0.1)

    const selectiveEfficiency = report.views.selectivePolicy.efficiency
    expect(selectiveEfficiency.costAvailableCells).toBe(2)
    expect(selectiveEfficiency.costUnavailableCells).toBe(1)
    expect(selectiveEfficiency.meanCostUsdDelta).toBe(0.05)

    const abstainedRow = report.observations.find(row => row.observationId === 'c')
    expect(abstainedRow?.routerSelected).toBe(false)
    expect(abstainedRow?.activated).toBe(false)
    expect(abstainedRow?.treatmentPassed).toBe(false)
    expect(abstainedRow?.selectiveOutcomePassed).toBe(true)
  })

  it('reports domain coverage and per-domain activated/selective metrics', () => {
    expect(report.coverage).toMatchObject({
      domains: 2,
      tasks: 3,
      pairedCells: 3,
      activatedCells: 2,
      selectiveCells: 3,
      activatedDomains: 2,
      selectiveDomains: 2,
    })
    expect(report.coverage.cellsByDomain).toEqual({ 'domain-a': 2, 'domain-b': 1 })
    expect(report.coverage.tasksByDomain).toEqual({ 'domain-a': 2, 'domain-b': 1 })

    const domainA = report.byDomain.find(row => row.domain === 'domain-a')
    if (domainA === undefined) throw new Error('expected domain-a')
    expect(domainA.rawPaired.cells).toBe(2)
    expect(domainA.rawPaired.accuracy.baselinePasses).toBe(1)
    expect(domainA.rawPaired.accuracy.treatmentPasses).toBe(1)
    expect(domainA.activatedSkill.cells).toBe(1)
    expect(domainA.activatedSkill.accuracy.treatmentPassRate).toBe(1)
    expect(domainA.selectivePolicy.cells).toBe(2)
    expect(domainA.selectivePolicy.accuracy.treatmentPasses).toBe(2)

    const domainB = report.byDomain.find(row => row.domain === 'domain-b')
    if (domainB === undefined) throw new Error('expected domain-b')
    expect(domainB.rawPaired.cells).toBe(1)
    expect(domainB.activatedSkill.cells).toBe(1)
    expect(domainB.selectivePolicy.cells).toBe(1)
  })

  it('exposes no holdout or tuning fields in the report', () => {
    expect(report).not.toHaveProperty('holdout')
    expect(report).not.toHaveProperty('validationReward')
    expect(report).not.toHaveProperty('stage')
    expect(report.views).not.toHaveProperty('holdout')
  })

  it('returns null rates and intervals for an empty admitted cohort', () => {
    const empty = buildBenchmarkReport({
      benchmark: 'bench',
      cohort: 'empty',
      observations: [],
    })
    expect(empty.admission.rawPaired).toBe(0)
    expect(empty.views.rawPaired.accuracy.baselinePassRate).toBeNull()
    expect(empty.views.rawPaired.accuracy.baselineWilson95).toBeNull()
    expect(empty.views.rawPaired.accuracy.exactSignTestPValue).toBeNull()
    expect(empty.views.rawPaired.efficiency.meanToolCallDelta).toBeNull()
    expect(empty.views.rawPaired.efficiency.meanCostUsdDelta).toBeNull()
    expect(empty.abstentions.baselinePassRate).toBeNull()
    expect(empty.byDomain).toEqual([])
  })
})

describe('unmeasured cost', () => {
  it('reports null cost totals rather than zero', () => {
    const report = buildBenchmarkReport({
      benchmark: 'bench',
      cohort: 'cohort',
      observations: [observation({
        observationId: 'unmeasured',
        baseline: condition({ passed: true, costUsd: null }),
        treatment: condition({ passed: false, costUsd: null }),
      })],
    })
    expect(report.views.rawPaired.efficiency.costAvailableCells).toBe(0)
    expect(report.views.rawPaired.efficiency.baselineCostUsd).toBeNull()
    expect(report.views.rawPaired.efficiency.treatmentCostUsd).toBeNull()
    expect(report.views.rawPaired.efficiency.totalCostUsd).toBeNull()
  })
})
