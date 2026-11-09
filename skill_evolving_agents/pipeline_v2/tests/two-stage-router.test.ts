import { describe, expect, it } from 'vitest'
import { skillId } from '../src/contracts/ids.ts'
import {
  RouterError,
  TwoStageRouter,
  computeRouterMetrics,
  parseDecisionOutput,
  type CandidateComponentScores,
  type DecisionProvider,
  type DecisionProviderRequest,
  type EmbeddingProvider,
  type FailureFamilyDocument,
  type RouterBudget,
  type RouterDecision,
  type RouterEvaluationRow,
  type RouterResult,
  type RouterTask,
  type SkillCandidate,
  type SkillDocument,
} from '../src/router/two-stage-router.ts'

const REPORT_EXPORT: SkillDocument = {
  skillId: skillId('skill:report-export'),
  name: 'Report export',
  description: 'Export a structured report to CSV with stable column ordering.',
  family: 'reporting',
  intents: ['export', 'publish'],
  actions: ['export'],
  keywords: ['csv', 'report', 'export', 'columns'],
}

const LEDGER_SYNC: SkillDocument = {
  skillId: skillId('skill:ledger-sync'),
  name: 'Financial record synchronization',
  description: 'Synchronize financial records across the accounting system.',
  family: 'finance',
  intents: ['reconcile'],
  actions: ['synchronize'],
  keywords: ['records', 'accounting'],
}

const WALL_PAINT: SkillDocument = {
  skillId: skillId('skill:wall-paint'),
  name: 'Wall painting',
  description: 'Paint interior walls with a consistent finish.',
  family: 'home',
  intents: ['paint'],
  actions: ['paint'],
}

const FAILURE_FAMILIES: readonly FailureFamilyDocument[] = [
  {
    familyId: 'family:report-columns',
    family: 'reporting',
    description: 'Report export fails when the column ordering is unstable.',
    intents: ['export'],
    actions: ['export'],
  },
  {
    familyId: 'family:ledger-mismatch',
    family: 'finance',
    description: 'Ledger reconciliation fails when records disagree.',
    intents: ['reconcile'],
    actions: ['synchronize'],
  },
]

const INVENTORY = {
  skills: [REPORT_EXPORT, LEDGER_SYNC, WALL_PAINT],
  failureFamilies: FAILURE_FAMILIES,
}

const BUDGET: RouterBudget = {
  maxCandidates: 4,
  maxCalls: 2,
  maxTokens: 4000,
  maxLatencyMs: 5000,
}

const REUSE_TASK: RouterTask = {
  taskId: 'task:report-export',
  text: 'Export the quarterly report to CSV with stable columns.',
  family: 'reporting',
  intent: 'export',
  action: 'export',
}

const UNRELATED_TASK: RouterTask = {
  taskId: 'task:podcast-summary',
  text: 'Summarize a podcast episode into bullet points.',
  family: 'media',
  intent: 'summarize',
  action: 'summarize',
}

const DISAGREEMENT_TASK: RouterTask = {
  taskId: 'task:ledger-reconcile',
  text: 'Reconcile the ledger entries for the month.',
  family: 'finance',
  intent: 'reconcile',
  action: 'synchronize',
}

class StaticDecisionProvider implements DecisionProvider {
  readonly requests: DecisionProviderRequest[] = []

  constructor(private readonly output: unknown) {}

  async decide(request: DecisionProviderRequest): Promise<unknown> {
    this.requests.push(request)
    return this.output
  }
}

class RecordingDecisionProvider implements DecisionProvider {
  calls = 0

  async decide(): Promise<unknown> {
    this.calls += 1
    return { kind: 'abstain', confidence: 0.1, rationale: 'should not be called' }
  }
}

/** A test seam that maps concepts with no shared tokens to the same direction. */
class ConceptEmbeddingProvider implements EmbeddingProvider {
  embed(texts: readonly string[]): readonly (readonly number[])[] {
    return texts.map(text => {
      const lower = text.toLowerCase()
      if (lower.includes('reconcile') || lower.includes('synchronize')) return [1, 0, 0]
      if (lower.includes('paint')) return [0, 1, 0]
      return [0, 0, 1]
    })
  }
}

function componentScores(combined: number): CandidateComponentScores {
  return { lexical: combined, embedding: combined, intentAction: combined, family: combined, combined }
}

function candidate(value: string, combined = 0.9): SkillCandidate {
  return { skillId: skillId(value), scores: componentScores(combined) }
}

function decisionFor(kind: 'reuse' | 'abstain', selected: string | null): RouterDecision {
  return {
    kind,
    skillId: selected === null ? null : skillId(selected),
    failureFamilyId: null,
    confidence: 0.8,
    rationale: 'test decision',
    source: 'fallback',
    fallbackReason: null,
  }
}

function resultFor(task: RouterTask, skills: readonly SkillCandidate[], decision: RouterDecision): RouterResult {
  return {
    task,
    retrieval: {
      skills,
      failureFamilies: [],
      queryTokenCount: 3,
      embeddingDegraded: false,
    },
    decision,
    usage: { calls: 0, tokens: 0, latencyMs: 0, exhausted: false },
  }
}

function labeledRow(
  taskId: string,
  skills: readonly SkillCandidate[],
  decision: RouterDecision,
  useful: readonly string[],
  baselinePassed: boolean,
  treatmentPassed: boolean,
  costUsd: number,
  latencyMs: number,
): RouterEvaluationRow {
  const task: RouterTask = {
    taskId,
    text: `text for ${taskId}`,
    family: 'test',
    intent: 'test',
    action: 'test',
  }
  return {
    observation: {
      task,
      usefulSkillIds: useful.map(value => skillId(value)),
      baselinePassed,
      treatmentPassed,
      costUsd,
      latencyMs,
    },
    result: resultFor(task, skills, decision),
  }
}

describe('stage one retrieval', () => {
  it('reuses a well-matched skill through a validated provider decision', async () => {
    const provider = new StaticDecisionProvider({
      kind: 'reuse',
      skillId: 'skill:report-export',
      confidence: 0.91,
      rationale: 'same family, intent, and action',
      usage: { tokens: 10 },
    })
    const router = new TwoStageRouter({
      inventory: INVENTORY,
      decisionProvider: provider,
      clock: () => 0,
    })
    const result = await router.route(REUSE_TASK, BUDGET)

    expect(result.retrieval.skills[0]?.skillId).toBe(REPORT_EXPORT.skillId)
    expect(result.retrieval.skills[0]?.scores.family).toBe(1)
    expect(result.decision).toMatchObject({
      kind: 'reuse',
      skillId: 'skill:report-export',
      source: 'provider',
      fallbackReason: null,
    })
    expect(provider.requests).toHaveLength(1)
    expect(provider.requests[0]?.skills.length).toBeGreaterThan(0)
    expect(provider.requests[0]?.skills[0]?.summary).toBe(REPORT_EXPORT.description)
  })

  it('abstains when no candidate has enough evidence', async () => {
    const router = new TwoStageRouter({ inventory: INVENTORY, clock: () => 0 })
    const result = await router.route(UNRELATED_TASK, BUDGET)

    expect(result.decision.kind).toBe('abstain')
    expect(result.decision.skillId).toBeNull()
    expect(result.decision.fallbackReason).toBe('provider-unavailable')
    expect(result.usage.calls).toBe(0)
  })

  it('refuses an activation whose task family does not match', async () => {
    const provider = new StaticDecisionProvider({
      kind: 'reuse',
      skillId: 'skill:report-export',
      confidence: 0.99,
      rationale: 'forced reuse',
    })
    const router = new TwoStageRouter({
      inventory: INVENTORY,
      decisionProvider: provider,
      clock: () => 0,
    })
    const mismatched: RouterTask = { ...REUSE_TASK, taskId: 'task:family-mismatch', family: 'media' }
    const result = await router.route(mismatched, BUDGET)

    expect(result.retrieval.skills[0]?.skillId).toBe(REPORT_EXPORT.skillId)
    expect(result.retrieval.skills[0]?.scores.family).toBe(0)
    expect(result.decision.kind).toBe('abstain')
    expect(result.decision.source).toBe('fallback')
    expect(result.decision.fallbackReason).toBe('unsafe-decision')
  })

  it('uses embedding recall when lexical evidence disagrees', async () => {
    const router = new TwoStageRouter({
      inventory: INVENTORY,
      embedding: new ConceptEmbeddingProvider(),
      clock: () => 0,
    })
    const result = await router.route(DISAGREEMENT_TASK, BUDGET)
    const top = result.retrieval.skills[0]

    expect(top?.skillId).toBe(LEDGER_SYNC.skillId)
    expect(top?.scores.lexical).toBe(0)
    expect(top?.scores.embedding).toBe(1)
    expect(result.decision.kind).toBe('reuse')
    expect(result.decision.skillId).toBe(LEDGER_SYNC.skillId)
  })

  it('ranks deterministically regardless of inventory order', async () => {
    const first = new TwoStageRouter({ inventory: INVENTORY, clock: () => 0 })
    const second = new TwoStageRouter({ inventory: INVENTORY, clock: () => 0 })
    const reversed = new TwoStageRouter({
      inventory: {
        skills: [...INVENTORY.skills].reverse(),
        failureFamilies: [...INVENTORY.failureFamilies].reverse(),
      },
      clock: () => 0,
    })

    const left = await first.retrieve(REUSE_TASK)
    const right = await second.retrieve(REUSE_TASK)
    const flipped = await reversed.retrieve(REUSE_TASK)

    expect(right).toEqual(left)
    expect(flipped.skills).toEqual(left.skills)
    expect(flipped.failureFamilies).toEqual(left.failureFamilies)
  })
})

describe('stage two bounds and safety', () => {
  it('falls back deterministically when the call or token budget is exhausted', async () => {
    const provider = new RecordingDecisionProvider()
    const router = new TwoStageRouter({
      inventory: INVENTORY,
      decisionProvider: provider,
      clock: () => 0,
    })

    const noCalls = await router.route(REUSE_TASK, { ...BUDGET, maxCalls: 0 })
    expect(provider.calls).toBe(0)
    expect(noCalls.decision).toMatchObject({
      kind: 'reuse',
      source: 'fallback',
      fallbackReason: 'budget-exhausted',
    })
    expect(noCalls.usage).toMatchObject({ calls: 0, exhausted: true })

    const noTokens = await router.route(REUSE_TASK, { ...BUDGET, maxTokens: 0 })
    expect(provider.calls).toBe(0)
    expect(noTokens.decision.fallbackReason).toBe('budget-exhausted')
    expect(noTokens.usage.exhausted).toBe(true)
  })

  it('falls back when the provider exceeds the time budget', async () => {
    let now = 0
    const provider: DecisionProvider = {
      async decide() {
        now = 10
        return {
          kind: 'reuse',
          skillId: 'skill:report-export',
          confidence: 0.9,
          rationale: 'slow but valid',
        }
      },
    }
    const router = new TwoStageRouter({
      inventory: INVENTORY,
      decisionProvider: provider,
      clock: () => now,
    })
    const result = await router.route(REUSE_TASK, { ...BUDGET, maxLatencyMs: 5 })

    expect(result.decision.fallbackReason).toBe('budget-exhausted')
    expect(result.usage).toMatchObject({ calls: 1, latencyMs: 10, exhausted: true })
  })

  it('rejects invalid budgets and duplicate candidates with structured errors', async () => {
    const router = new TwoStageRouter({ inventory: INVENTORY, clock: () => 0 })

    await expect(router.route(REUSE_TASK, { ...BUDGET, maxCalls: -1 }))
      .rejects.toMatchObject({ code: 'invalid-budget' })

    expect(() => new TwoStageRouter({
      inventory: { skills: [REPORT_EXPORT, REPORT_EXPORT], failureFamilies: [] },
    })).toThrowError(RouterError)

    expect(() => parseDecisionOutput({
      kind: 'reuse',
      skillId: 'skill:not-offered',
      confidence: 0.5,
      rationale: 'unknown candidate',
    }, {
      skillIds: [REPORT_EXPORT.skillId],
      failureFamilyIds: [],
    })).toThrowError(RouterError)
  })
})

describe('labeled router metrics', () => {
  it('computes recall, precision, abstention, lift, cost, latency, and regressions', () => {
    const rows: readonly RouterEvaluationRow[] = [
      labeledRow('row-1', [candidate('skill:a'), candidate('skill:b')], decisionFor('reuse', 'skill:a'), ['skill:a'], false, true, 0.1, 100),
      labeledRow('row-2', [candidate('skill:b')], decisionFor('abstain', null), ['skill:a'], true, true, 0.2, 200),
      labeledRow('row-3', [candidate('skill:a')], decisionFor('reuse', 'skill:a'), [], true, false, 0.3, 300),
      labeledRow('row-4', [], decisionFor('abstain', null), [], false, false, 0.4, 400),
    ]
    const metrics = computeRouterMetrics(rows, { recallK: 1 })

    expect(metrics.observations).toBe(4)
    expect(metrics.usefulObservations).toBe(2)
    expect(metrics.noSkillObservations).toBe(2)
    expect(metrics.activations).toBe(2)
    expect(metrics.abstentions).toBe(2)
    expect(metrics.activationRate).toBe(0.5)
    expect(metrics.usefulSkillRecallAtK).toBe(0.5)
    expect(metrics.activationPrecision).toBe(0.5)
    expect(metrics.falseAbstentionRate).toBe(0.5)
    expect(metrics.falseActivationRate).toBe(0.5)
    expect(metrics.passLiftPerActivation).toBe(0)
    expect(metrics.meanCostUsd).toBeCloseTo(0.25)
    expect(metrics.meanLatencyMs).toBeCloseTo(250)
    expect(metrics.costPerActivation).toBeCloseTo(0.2)
    expect(metrics.latencyPerActivation).toBeCloseTo(200)
    expect(metrics.regressions).toBe(1)
  })
})
