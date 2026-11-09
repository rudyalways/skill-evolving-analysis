import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { V2Pipeline } from '../src/core/v2-pipeline.ts'
import { RunController } from '../src/core/run-controller.ts'
import { CapabilityRegistry, providerPlugin } from '../src/core/capabilities.ts'
import { InMemoryTraceSource } from '../src/capabilities/providers.ts'
import {
  DeterministicVerifier,
  InMemoryPublisher,
  KeywordFindingDetector,
} from '../src/providers/low-cost.ts'
import { TwoStageRouter, type DecisionProvider } from '../src/router/two-stage-router.ts'
import { openStudyStore } from '../src/store/study-store.ts'
import { DeterministicPreflight, DeterministicResourcePlanner } from '../src/providers/v2.ts'
import { runId, skillId, traceId } from '../src/contracts/ids.ts'

const decisionProvider: DecisionProvider = {
  async decide() {
    return {
      kind: 'update',
      skillId: 'existing-skill',
      failureFamilyId: 'unit-harmonization',
      confidence: 0.9,
      rationale: 'reuse the existing unit harmonization skill with a bounded update',
      usage: { tokens: 12, latencyMs: 1 },
    }
  },
}

function router() {
  return new TwoStageRouter({
    inventory: {
      skills: [{
        skillId: skillId('existing-skill'),
        name: 'Unit harmonization',
        description: 'Harmonize lab units with schema references and range checks',
        family: 'unit-harmonization',
        intents: ['evolve-skill'],
        actions: ['update'],
        keywords: ['unit', 'harmonize', 'range'],
      }],
      failureFamilies: [{
        familyId: 'unit-harmonization',
        family: 'unit-harmonization',
        description: 'Schema-driven unit harmonization and physiological range checks',
        intents: ['evolve-skill'],
        actions: ['update'],
        keywords: ['unit', 'harmonize'],
      }],
    },
    config: {
      thresholds: {
        minimumCombined: 0.1,
        minimumEvidence: 0.1,
        minimumIntentAction: 0.1,
        minimumFamily: 0.5,
      },
    },
    decisionProvider,
  })
}

describe('durable v2 pipeline slice', () => {
  it('routes, plans, preflights, verifies, publishes, and replays from the store', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'pipeline-v2-'))
    const store = await openStudyStore(dir)
    const ctx = new Context()
    const registry = await ctx.plugin(CapabilityRegistry)
    const trace = traceId('trace-v2-1')
    const source = await ctx.plugin(providerPlugin('traceSource', new InMemoryTraceSource([{
      id: trace,
      source: 'fixture',
      turns: ['The unit conversion failed with an error; retry after harmonizing units'],
    }])))
    const detector = await ctx.plugin(providerPlugin('findingDetector', new KeywordFindingDetector()))
    const verifier = await ctx.plugin(providerPlugin('verifier', new DeterministicVerifier()))
    const publisher = await ctx.plugin(providerPlugin('publisher', new InMemoryPublisher()))
    const routerFiber = await ctx.plugin(providerPlugin('router', router()))
    const plannerFiber = await ctx.plugin(providerPlugin('resourcePlanner', new DeterministicResourcePlanner()))
    const preflightFiber = await ctx.plugin(providerPlugin('preflight', new DeterministicPreflight()))
    const pipeline = new V2Pipeline(
      ctx,
      new RunController(runId('v2-run-1')),
      store,
    )
    const result = await pipeline.execute({
      traceId: trace,
      taskId: 'task-v2-1',
      objective: 'improve unit handling',
      profile: 'low-cost-v2',
      at: '2026-11-09T10:00:00.000Z',
      family: 'unit-harmonization',
      routerBudget: { maxCandidates: 3, maxCalls: 1, maxTokens: 1024, maxLatencyMs: 1000 },
      existingBundle: {
        'SKILL.md': '---\nname: unit-harmonization\ndescription: Existing unit skill\n---\n\n# Unit harmonization\n',
      },
    })
    expect(result.route?.decision.kind).toBe('update')
    expect(result.preflight?.verdict).toBe('accept')
    expect(result.publication?.channel).toBe('provisional')
    expect(result.projection.status).toBe('completed')
    expect(result.projection.operations['v2-run-1:operation:1']?.status).toBe('published')
    expect(await store.replay('v2-run-1')).toEqual(result.projection)
    expect((await store.verifyIntegrity()).ok).toBe(true)
    expect(Object.values(store.getState().skillExposures)).toHaveLength(1)

    await preflightFiber.dispose()
    await plannerFiber.dispose()
    await routerFiber.dispose()
    await publisher.dispose()
    await verifier.dispose()
    await detector.dispose()
    await source.dispose()
    await registry.dispose()
    await rm(dir, { recursive: true, force: true })
  }, 20_000)
})

describe('v2 preflight rejection', () => {
  it('rejects the operation without publication when preflight rejects', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'pipeline-v2-reject-'))
    const store = await openStudyStore(dir)
    const ctx = new Context()
    const registry = await ctx.plugin(CapabilityRegistry)
    const trace = traceId('trace-v2-2')
    const source = await ctx.plugin(providerPlugin('traceSource', new InMemoryTraceSource([{
      id: trace,
      source: 'fixture',
      turns: ['unit conversion failed with an error; retry'],
    }])))
    const detector = await ctx.plugin(providerPlugin('findingDetector', new KeywordFindingDetector()))
    const verifier = await ctx.plugin(providerPlugin('verifier', new DeterministicVerifier()))
    const publisher = await ctx.plugin(providerPlugin('publisher', new InMemoryPublisher()))
    const routerFiber = await ctx.plugin(providerPlugin('router', router()))
    const plannerFiber = await ctx.plugin(providerPlugin('resourcePlanner', new DeterministicResourcePlanner()))
    const preflightFiber = await ctx.plugin(providerPlugin('preflight', new DeterministicPreflight()))
    const pipeline = new V2Pipeline(ctx, new RunController(runId('v2-run-2')), store)
    const result = await pipeline.execute({
      traceId: trace,
      taskId: 'task-v2-2',
      objective: 'improve unit handling',
      profile: 'low-cost-v2',
      at: '2026-11-09T10:00:00.000Z',
      family: 'unit-harmonization',
      routerBudget: { maxCandidates: 3, maxCalls: 1, maxTokens: 1024, maxLatencyMs: 1000 },
      existingBundle: {
        'SKILL.md': '---\nname: unit-harmonization\ndescription: Existing unit skill\n---\n\n# Unit harmonization\n',
      },
      preflightPolicy: { maximumPromptTokens: 1 },
    })
    expect(result.preflight?.verdict).toBe('reject')
    expect(result.publication).toBeUndefined()
    expect(result.projection.operations['v2-run-2:operation:1']?.status).toBe('rejected')
    expect(result.projection.status).toBe('completed')
    await preflightFiber.dispose()
    await plannerFiber.dispose()
    await routerFiber.dispose()
    await publisher.dispose()
    await verifier.dispose()
    await detector.dispose()
    await source.dispose()
    await registry.dispose()
    await store.close()
    await rm(dir, { recursive: true, force: true })
  }, 20_000)
})

describe('v2 abstention', () => {
  it('completes without an operation or publication when the router abstains', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'pipeline-v2-abstain-'))
    const store = await openStudyStore(dir)
    const ctx = new Context()
    const registry = await ctx.plugin(CapabilityRegistry)
    const trace = traceId('trace-v2-3')
    const source = await ctx.plugin(providerPlugin('traceSource', new InMemoryTraceSource([{
      id: trace,
      source: 'fixture',
      turns: ['unit conversion failed with an error; retry'],
    }])))
    const detector = await ctx.plugin(providerPlugin('findingDetector', new KeywordFindingDetector()))
    const verifier = await ctx.plugin(providerPlugin('verifier', new DeterministicVerifier()))
    const publisher = await ctx.plugin(providerPlugin('publisher', new InMemoryPublisher()))
    const routerFiber = await ctx.plugin(providerPlugin('router', router()))
    const plannerFiber = await ctx.plugin(providerPlugin('resourcePlanner', new DeterministicResourcePlanner()))
    const preflightFiber = await ctx.plugin(providerPlugin('preflight', new DeterministicPreflight()))
    const pipeline = new V2Pipeline(ctx, new RunController(runId('v2-run-3')), store)
    const result = await pipeline.execute({
      traceId: trace,
      taskId: 'task-v2-3',
      objective: 'improve financial reconciliation',
      profile: 'low-cost-v2',
      at: '2026-11-09T10:00:00.000Z',
      family: 'financial-reconciliation',
      routerBudget: { maxCandidates: 3, maxCalls: 1, maxTokens: 1024, maxLatencyMs: 1000 },
    })
    expect(result.route?.decision.kind).toBe('abstain')
    expect(result.projection.status).toBe('completed')
    expect(result.projection.operations).toEqual({})
    expect(result.publication).toBeUndefined()
    await preflightFiber.dispose()
    await plannerFiber.dispose()
    await routerFiber.dispose()
    await publisher.dispose()
    await verifier.dispose()
    await detector.dispose()
    await source.dispose()
    await registry.dispose()
    await store.close()
    await rm(dir, { recursive: true, force: true })
  }, 20_000)
})
