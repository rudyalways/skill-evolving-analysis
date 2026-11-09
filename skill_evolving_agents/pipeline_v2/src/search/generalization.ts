import type { GeneralizationEvaluator } from '../capabilities/definitions.ts'
import type {
  EvaluationStage,
  GeneralizationDecision,
  GeneralizationObservation,
  GeneralizationPolicy,
  StageMetrics,
} from './contracts.ts'

const STAGES = ['train', 'validation', 'holdout'] as const

function summarize(rows: readonly GeneralizationObservation[]): StageMetrics {
  const total = rows.length
  const baseline = rows.filter(row => row.baselinePassed).length
  const treatment = rows.filter(row => row.treatmentPassed).length
  const lifts = rows.filter(row => !row.baselinePassed && row.treatmentPassed)
  const liftDomains = new Map<string, number>()
  for (const row of lifts) liftDomains.set(row.domain, (liftDomains.get(row.domain) ?? 0) + 1)
  return {
    tasks: total,
    domains: new Set(rows.map(row => row.domain)).size,
    baselinePassRate: total ? baseline / total : 0,
    treatmentPassRate: total ? treatment / total : 0,
    absoluteLift: total ? (treatment - baseline) / total : 0,
    regressions: rows.filter(row => row.baselinePassed && !row.treatmentPassed).length,
    efficiencyFailureRate: total ? rows.filter(row => row.efficiencyFailure).length / total : 0,
    meanToolCallDelta: total
      ? rows.reduce((sum, row) => sum + row.treatmentToolCalls - row.baselineToolCalls, 0) / total
      : 0,
    liftDomainConcentration: lifts.length
      ? Math.max(...liftDomains.values()) / lifts.length
      : 0,
  }
}

/** Evaluates validation reward while keeping holdout sealed from learning. */
export class SealedGeneralizationEvaluator implements GeneralizationEvaluator {
  evaluate(
    observations: readonly GeneralizationObservation[],
    policy: GeneralizationPolicy,
  ): GeneralizationDecision {
    const memberships = new Map<string, Set<EvaluationStage>>()
    const observationsByStage = new Set<string>()
    for (const row of observations) {
      const observationKey = `${row.stage}:${row.taskId}`
      if (observationsByStage.has(observationKey)) {
        throw new Error(`duplicate benchmark observation: ${observationKey}`)
      }
      observationsByStage.add(observationKey)
      for (const key of [`task:${row.taskId}`, ...(row.groupId ? [`group:${row.groupId}`] : [])]) {
        const stages = memberships.get(key) ?? new Set<EvaluationStage>()
        stages.add(row.stage)
        memberships.set(key, stages)
      }
    }
    const leak = [...memberships].find(([, stages]) => stages.size > 1)
    if (leak) throw new Error(`cross-stage benchmark leakage: ${leak[0]}`)
    const stages = Object.fromEntries(
      STAGES.map(stage => [stage, summarize(observations.filter(row => row.stage === stage))]),
    ) as Record<EvaluationStage, StageMetrics>
    const validation = stages.validation
    const validationReward = validation.treatmentPassRate + validation.absoluteLift
      - 2 * validation.regressions / Math.max(validation.tasks, 1)
      - validation.efficiencyFailureRate
      - 0.25 * validation.liftDomainConcentration
      - 0.001 * Math.max(validation.meanToolCallDelta, 0)
    const validationEligible = validation.tasks >= policy.minimumValidationTasks
      && validation.domains >= policy.minimumValidationDomains
      && validation.regressions <= policy.maximumRegressions
      && validation.efficiencyFailureRate <= policy.maximumEfficiencyFailureRate
      && validation.absoluteLift > 0
    const holdout = stages.holdout
    const milestoneMet = validationEligible
      && holdout.tasks >= policy.minimumHoldoutTasks
      && holdout.domains >= policy.minimumHoldoutDomains
      && holdout.treatmentPassRate >= policy.targetPassRate
      && holdout.absoluteLift >= policy.minimumAbsoluteLift
      && holdout.regressions <= policy.maximumRegressions
      && holdout.efficiencyFailureRate <= policy.maximumEfficiencyFailureRate
    return {
      decision: milestoneMet ? 'target_met'
        : validationEligible && holdout.tasks === 0 ? 'advance_to_sealed_holdout'
        : 'continue_search',
      validationReward,
      validationEligible,
      milestoneMet,
      holdoutBackpropagated: false,
      stages,
    }
  }
}
