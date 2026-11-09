import { readFile } from 'node:fs/promises'
import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { InMemoryTraceSource } from '../src/capabilities/providers.ts'
import { runId, traceId } from '../src/contracts/ids.ts'
import { CapabilityRegistry, providerPlugin } from '../src/core/capabilities.ts'
import { PipelineController } from '../src/core/pipeline-controller.ts'
import { RunController } from '../src/core/run-controller.ts'
import {
  DeterministicGoalPlanner,
  DeterministicVerifier,
  InMemoryPublisher,
  InMemorySkillMutator,
  KeywordFindingDetector,
  LexicalCandidateRecall,
} from '../src/providers/low-cost.ts'

interface TraceFixture {
  readonly id: string
  readonly source: string
  readonly turns: readonly string[]
}

function parseFixture(value: unknown): TraceFixture {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('trace fixture must be an object')
  }
  const row = value as Partial<TraceFixture>
  if (typeof row.id !== 'string' || !row.id.trim()) throw new Error('trace fixture id is required')
  if (typeof row.source !== 'string' || !row.source.trim()) throw new Error('trace fixture source is required')
  if (!Array.isArray(row.turns) || !row.turns.every(turn => typeof turn === 'string')) {
    throw new Error('trace fixture turns must be strings')
  }
  return { id: row.id, source: row.source, turns: row.turns }
}

describe('JSON fixture entrypoint', () => {
  it('runs a frozen JSON trace through the low-cost Cordis slice', async () => {
    const raw = await readFile(new URL('./fixtures/low-cost-retry.trace.json', import.meta.url), 'utf8')
    const fixture = parseFixture(JSON.parse(raw))
    const id = traceId(fixture.id)
    const ctx = new Context()
    const registry = await ctx.plugin(CapabilityRegistry)
    const fibers = await Promise.all([
      ctx.plugin(providerPlugin('traceSource', new InMemoryTraceSource([{
        id,
        source: fixture.source,
        turns: fixture.turns,
      }]))),
      ctx.plugin(providerPlugin('findingDetector', new KeywordFindingDetector())),
      ctx.plugin(providerPlugin('candidateRecall', new LexicalCandidateRecall({
        'retry-guard': 'retry failed command error recovery',
      }))),
      ctx.plugin(providerPlugin('goalPlanner', new DeterministicGoalPlanner())),
      ctx.plugin(providerPlugin('skillMutator', new InMemorySkillMutator())),
      ctx.plugin(providerPlugin('verifier', new DeterministicVerifier())),
      ctx.plugin(providerPlugin('publisher', new InMemoryPublisher())),
    ])
    try {
      const result = await new PipelineController(
        ctx,
        new RunController(runId('fixture-run')),
      ).execute({
        traceId: id,
        objective: 'run one frozen trace',
        profile: 'low-cost-v2',
        at: '2026-11-09T10:00:00.000Z',
        recallLimit: 3,
      })
      expect(result.status).toBe('completed')
      expect(result.funnel.publicationsCompleted).toBe(1)
    } finally {
      for (const fiber of fibers.reverse()) await fiber.dispose()
      await registry.dispose()
    }
  })
})
