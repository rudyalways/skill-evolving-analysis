/** A scalar or categorical configuration value. */
export type KnobValue = string | number | boolean

/** One bounded configuration knob. */
export interface KnobDomain {
  readonly name: string
  readonly defaultValue: KnobValue
  readonly values: readonly KnobValue[]
}

/** Prior validation evidence available to search. */
export interface SearchHistory {
  readonly overrides: Readonly<Record<string, KnobValue>>
  readonly validationReward: number
  readonly stage: 'validation'
  readonly samples: number
}

/** Input to one bounded search batch. */
export interface SearchRequest {
  readonly domains: readonly KnobDomain[]
  readonly count: number
  readonly seed: number
  readonly history: readonly SearchHistory[]
}

/** One auditable candidate proposed by one or more strategies. */
export interface SearchCandidate {
  readonly candidateId: string
  readonly overrides: Readonly<Record<string, KnobValue>>
  readonly sources: readonly ('wide' | 'deep' | 'mcts' | 'random')[]
}

/** Experimental stage; holdout is sealed from search feedback. */
export type EvaluationStage = 'train' | 'validation' | 'holdout'

/** One matched benchmark observation. */
export interface GeneralizationObservation {
  readonly stage: EvaluationStage
  readonly taskId: string
  readonly groupId?: string
  readonly domain: string
  readonly baselinePassed: boolean
  readonly treatmentPassed: boolean
  readonly baselineToolCalls: number
  readonly treatmentToolCalls: number
  readonly efficiencyFailure: boolean
}

/** Frozen generalization and efficiency gates. */
export interface GeneralizationPolicy {
  readonly targetPassRate: number
  readonly minimumValidationTasks: number
  readonly minimumValidationDomains: number
  readonly minimumHoldoutTasks: number
  readonly minimumHoldoutDomains: number
  readonly maximumRegressions: number
  readonly maximumEfficiencyFailureRate: number
  readonly minimumAbsoluteLift: number
}

/** Metrics for one experimental stage. */
export interface StageMetrics {
  readonly tasks: number
  readonly domains: number
  readonly baselinePassRate: number
  readonly treatmentPassRate: number
  readonly absoluteLift: number
  readonly regressions: number
  readonly efficiencyFailureRate: number
  readonly meanToolCallDelta: number
  readonly liftDomainConcentration: number
}

/** Leakage-safe decision returned by the evaluator. */
export interface GeneralizationDecision {
  readonly decision: 'continue_search' | 'advance_to_sealed_holdout' | 'target_met'
  readonly validationReward: number
  readonly validationEligible: boolean
  readonly milestoneMet: boolean
  readonly holdoutBackpropagated: false
  readonly stages: Readonly<Record<EvaluationStage, StageMetrics>>
}
