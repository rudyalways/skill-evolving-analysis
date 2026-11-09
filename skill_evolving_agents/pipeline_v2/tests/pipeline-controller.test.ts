import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { InMemoryTraceSource } from '../src/capabilities/providers.ts'
import { traceId, runId } from '../src/contracts/ids.ts'
import { CapabilityRegistry, providerPlugin } from '../src/core/capabilities.ts'
import { PipelineController } from '../src/core/pipeline-controller.ts'
import { RunController } from '../src/core/run-controller.ts'
import {
  DeterministicGoalPlanner,
  DeterministicVerifier,
  InMemoryFeedbackLearner,
  InMemoryPublisher,
  InMemorySkillMutator,
  KeywordFindingDetector,
  LexicalCandidateRecall,
} from '../src/providers/low-cost.ts'

describe('Cordis v2 executable slice', () => {
  it('runs one trace through detection, recall, mutation, verification, and publication', async () => {
    const ctx = new Context()
    const registry = await ctx.plugin(CapabilityRegistry)
    const trace = traceId('trace-retry')
    const feedback = new InMemoryFeedbackLearner()
    const fibers = await Promise.all([
      ctx.plugin(providerPlugin('traceSource', new InMemoryTraceSource([{
        id: trace,
        source: 'fixture',
        turns: ['command failed', 'retry again after the error'],
      }]))),
      ctx.plugin(providerPlugin('findingDetector', new KeywordFindingDetector())),
      ctx.plugin(providerPlugin('candidateRecall', new LexicalCandidateRecall({
        'retry-guard': 'retry failed command error recovery',
        'unrelated-skill': 'presentation typography',
      }))),
      ctx.plugin(providerPlugin('goalPlanner', new DeterministicGoalPlanner())),
      ctx.plugin(providerPlugin('skillMutator', new InMemorySkillMutator())),
      ctx.plugin(providerPlugin('verifier', new DeterministicVerifier())),
      ctx.plugin(providerPlugin('publisher', new InMemoryPublisher())),
      ctx.plugin(providerPlugin('feedbackLearner', feedback)),
    ])
    const run = new RunController(runId('run-low-cost-1'))
    const projection = await new PipelineController(ctx, run).execute({
      traceId: trace,
      objective: 'evolve reusable retry guidance',
      profile: 'low-cost-v2',
      at: '2026-11-09T10:00:00.000Z',
      recallLimit: 3,
    })
    expect(projection.status).toBe('completed')
    expect(projection.funnel.findingsDetected).toBe(1)
    expect(projection.funnel.candidatesSelected).toBe(1)
    expect(projection.funnel.operationsAccepted).toBe(1)
    expect(projection.funnel.publicationsCompleted).toBe(1)
    expect(projection.resourceUse.byKind.evals).toBe(1)
    expect(projection.operations['trace-retry:keyword-failure:update:retry-guard']?.status)
      .toBe('published')
    for (const fiber of fibers.reverse()) await fiber.dispose()
    expect(ctx.capabilities.size).toBe(0)
    await registry.dispose()
  })

  it('completes without agent work when deterministic detection finds nothing', async () => {
    const ctx = new Context()
    const registry = await ctx.plugin(CapabilityRegistry)
    const trace = traceId('trace-clean')
    const source = await ctx.plugin(providerPlugin('traceSource', new InMemoryTraceSource([{
      id: trace,
      source: 'fixture',
      turns: ['completed successfully'],
    }])))
    const detector = await ctx.plugin(
      providerPlugin('findingDetector', new KeywordFindingDetector()),
    )
    const projection = await new PipelineController(
      ctx,
      new RunController(runId('run-low-cost-clean')),
    ).execute({
      traceId: trace,
      objective: 'avoid unnecessary evolution',
      profile: 'low-cost-v2',
      at: '2026-11-09T10:00:00.000Z',
      recallLimit: 3,
    })
    expect(projection.status).toBe('completed')
    expect(projection.funnel.findingsDetected).toBe(0)
    expect(projection.funnel.operationsPlanned).toBe(0)
    await detector.dispose()
    await source.dispose()
    await registry.dispose()
  })
})
