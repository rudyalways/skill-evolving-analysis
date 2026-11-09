import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { V2Pipeline } from '../src/core/v2-pipeline.ts'
import { RunController } from '../src/core/run-controller.ts'
import { CapabilityRegistry, providerPlugin } from '../src/core/capabilities.ts'
import { InMemoryTraceSource } from '../src/capabilities/providers.ts'
import { KeywordFindingDetector } from '../src/providers/low-cost.ts'
import { DeterministicPreflight, DeterministicResourcePlanner } from '../src/providers/v2.ts'
import { TwoStageRouter, type DecisionProvider } from '../src/router/two-stage-router.ts'
import { ReplayVerifier } from '../src/verification/replay-verifier.ts'
import { WorkspacePublisher } from '../src/publication/publisher.ts'
import { openStudyStore } from '../src/store/study-store.ts'
import { runId, skillId, traceId } from '../src/contracts/ids.ts'

const decisionProvider: DecisionProvider = {
  async decide() {
    return {
      kind: 'update',
      skillId: 'unit-harmonization',
      failureFamilyId: 'unit-harmonization',
      confidence: 0.92,
      rationale: 'reuse and update the unit harmonization skill',
      usage: { tokens: 10, latencyMs: 1 },
    }
  },
}

function router() {
  return new TwoStageRouter({
    inventory: {
      skills: [{
        skillId: skillId('unit-harmonization'),
        name: 'Unit harmonization',
        description: 'Convert lab units with schema references and range checks',
        family: 'unit-harmonization',
        intents: ['evolve-skill'],
        actions: ['update'],
        keywords: ['unit', 'harmonize', 'range'],
      }],
      failureFamilies: [{
        familyId: 'unit-harmonization',
        family: 'unit-harmonization',
        description: 'Schema-driven unit harmonization',
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

describe('real v2 publication', () => {
  it('executes replay verification and writes an atomic content-addressed release', async () => {
    const storeDir = await mkdtemp(join(tmpdir(), 'v2-real-store-'))
    const publishRoot = await mkdtemp(join(tmpdir(), 'v2-real-publish-'))
    const store = await openStudyStore(storeDir)
    const ctx = new Context()
    const registry = await ctx.plugin(CapabilityRegistry)
    const trace = traceId('real-train-trace')
    const source = await ctx.plugin(providerPlugin('traceSource', new InMemoryTraceSource([{
      id: trace,
      source: 'workspace/runs/schema-live-officeval',
      turns: ['The spreadsheet formula failed with an error; retry the unit-normalized values'],
    }])))
    const detector = await ctx.plugin(providerPlugin('findingDetector', new KeywordFindingDetector()))
    const verifier = await ctx.plugin(providerPlugin('verifier', new ReplayVerifier()))
    const routerFiber = await ctx.plugin(providerPlugin('router', router()))
    const plannerFiber = await ctx.plugin(providerPlugin('resourcePlanner', new DeterministicResourcePlanner()))
    const preflightFiber = await ctx.plugin(providerPlugin('preflight', new DeterministicPreflight()))
    const publisher = await ctx.plugin(providerPlugin('skillPublisher', new WorkspacePublisher({
      inventoryRoot: publishRoot,
    })))
    const pipeline = new V2Pipeline(ctx, new RunController(runId('v2-real-run-1')), store)
    const result = await pipeline.execute({
      traceId: trace,
      taskId: 'train-officeval-spreadsheet',
      objective: 'generate a verified unit harmonization skill',
      profile: 'low-cost-v2',
      at: '2026-11-09T22:50:00.000Z',
      family: 'unit-harmonization',
      routerBudget: { maxCandidates: 3, maxCalls: 1, maxTokens: 1024, maxLatencyMs: 1000 },
      existingBundle: {
        'SKILL.md': '---\nname: unit-harmonization\ndescription: Existing unit skill\n---\n\n# Unit harmonization\n',
      },
      policyVersion: 'policy-v2-validation-1',
      configVersion: 'config-v2-validation-1',
    })
    expect(result.preflight?.verdict).toBe('accept')
    expect(result.publicationReceipt).toBeDefined()
    expect(result.projection.operations['v2-real-run-1:operation:1']?.status).toBe('published')
    const receipt = result.publicationReceipt!
    expect(receipt.treeHash).toMatch(/^[a-f0-9]{64}$/)
    expect(receipt.files.some(file => file.path === 'SKILL.md')).toBe(true)
    expect(receipt.files.some(file => file.path.startsWith('scripts/'))).toBe(true)
    expect(receipt.files.some(file => file.path.startsWith('evals/'))).toBe(true)
    const receiptFile = await readFile(result.publicationReceiptPath!, 'utf8')
    expect(JSON.parse(receiptFile).treeHash).toBe(receipt.treeHash)
    const skillDir = join(publishRoot, 'skills')
    expect((await readdir(skillDir)).length).toBeGreaterThan(0)
    expect(await store.replay('v2-real-run-1')).toEqual(result.projection)
    await publisher.dispose()
    await preflightFiber.dispose()
    await plannerFiber.dispose()
    await routerFiber.dispose()
    await verifier.dispose()
    await detector.dispose()
    await source.dispose()
    await registry.dispose()
    await store.close()
    await rm(storeDir, { recursive: true, force: true })
    await rm(publishRoot, { recursive: true, force: true })
  }, 30_000)
})
