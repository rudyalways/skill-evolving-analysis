import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { CapabilityRegistry, providerPlugin } from '../src/core/capabilities.ts'
import { SealedGeneralizationEvaluator } from '../src/search/generalization.ts'
import { PortfolioConfigurationSearch } from '../src/search/portfolio.ts'
import type { GeneralizationObservation, GeneralizationPolicy } from '../src/search/contracts.ts'

const POLICY: GeneralizationPolicy = {
  targetPassRate: 0.6,
  minimumValidationTasks: 12,
  minimumValidationDomains: 6,
  minimumHoldoutTasks: 16,
  minimumHoldoutDomains: 8,
  maximumRegressions: 0,
  maximumEfficiencyFailureRate: 0.1,
  minimumAbsoluteLift: 0.05,
}

describe('configuration search portfolio', () => {
  it('mounts and disposes search providers through Cordis effects', async () => {
    const ctx = new Context()
    const registry = await ctx.plugin(CapabilityRegistry)
    const search = new PortfolioConfigurationSearch()
    const evaluator = new SealedGeneralizationEvaluator()
    const searchFiber = await ctx.plugin(providerPlugin('configurationSearch', search))
    const evaluatorFiber = await ctx.plugin(
      providerPlugin('generalizationEvaluator', evaluator),
    )
    expect(ctx.capabilities.require('configurationSearch')).toBe(search)
    expect(ctx.capabilities.require('generalizationEvaluator')).toBe(evaluator)
    await searchFiber.dispose()
    await evaluatorFiber.dispose()
    expect(ctx.capabilities.get('configurationSearch')).toBeUndefined()
    expect(ctx.capabilities.get('generalizationEvaluator')).toBeUndefined()
    await registry.dispose()
  })

  it('returns a deterministic diverse batch with strategy provenance', () => {
    const provider = new PortfolioConfigurationSearch()
    const request = {
      domains: [
        { name: 'recall.minimumScore', defaultValue: 0.35, values: [0.25, 0.35, 0.45] },
        { name: 'goal.minimumConfidence', defaultValue: 0.8, values: [0.7, 0.8, 0.9] },
      ],
      count: 8,
      seed: 17,
      history: [],
    }
    const first = provider.search(request)
    const second = provider.search(request)
    expect(first).toEqual(second)
    expect(first).toHaveLength(8)
    expect(new Set(first.map(row => row.candidateId)).size).toBe(8)
    expect(first.every(row => row.sources.length > 0)).toBe(true)
  })
})

function rows(stage: 'validation' | 'holdout', passes: number, total: number): GeneralizationObservation[] {
  return Array.from({ length: total }, (_, index) => ({
    stage,
    taskId: `${stage}-${index}`,
    domain: `domain-${index % 8}`,
    baselinePassed: index < 5,
    treatmentPassed: index < passes,
    baselineToolCalls: 20,
    treatmentToolCalls: 18,
    efficiencyFailure: false,
  }))
}

describe('sealed generalization evaluation', () => {
  it('recognizes 10/16 without backpropagating holdout', () => {
    const result = new SealedGeneralizationEvaluator().evaluate([
      ...rows('validation', 9, 12),
      ...rows('holdout', 10, 16),
    ], POLICY)
    expect(result.milestoneMet).toBe(true)
    expect(result.holdoutBackpropagated).toBe(false)
    expect(result.stages.holdout.treatmentPassRate).toBe(0.625)
  })

  it('keeps validation reward unchanged when holdout changes', () => {
    const evaluator = new SealedGeneralizationEvaluator()
    const validation = rows('validation', 9, 12)
    const good = evaluator.evaluate([...validation, ...rows('holdout', 10, 16)], POLICY)
    const bad = evaluator.evaluate([...validation, ...rows('holdout', 0, 16)], POLICY)
    expect(good.validationReward).toBe(bad.validationReward)
  })

  it('rejects task-family leakage across stages', () => {
    const evaluator = new SealedGeneralizationEvaluator()
    const validation = { ...rows('validation', 1, 1)[0]!, groupId: 'family-a' }
    const holdout = { ...rows('holdout', 1, 1)[0]!, groupId: 'family-a' }
    expect(() => evaluator.evaluate([validation, holdout], POLICY)).toThrow(
      'cross-stage benchmark leakage: group:family-a',
    )
  })

  it('rejects duplicate observations that inflate held-out sample size', () => {
    const evaluator = new SealedGeneralizationEvaluator()
    const duplicate = rows('holdout', 1, 1)[0]!
    expect(() => evaluator.evaluate([duplicate, duplicate], POLICY)).toThrow(
      'duplicate benchmark observation',
    )
  })
})
