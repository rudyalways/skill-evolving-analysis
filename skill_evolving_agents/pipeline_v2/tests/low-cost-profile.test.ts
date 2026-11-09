import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { InMemoryTraceSource } from '../src/capabilities/providers.ts'
import { mountLowCostV2Profile } from '../src/profiles/low-cost-v2.ts'
import { traceId } from '../src/contracts/ids.ts'

describe('low-cost v2 profile', () => {
  it('mounts every phase as a Cordis provider and disposes cleanly', async () => {
    const ctx = new Context()
    const profile = await mountLowCostV2Profile(ctx, {
      traceSource: new InMemoryTraceSource([{
        id: traceId('profile-trace'),
        source: 'fixture',
        turns: ['failed and retry'],
      }]),
      inventory: { skills: [], failureFamilies: [] },
    })
    expect(ctx.capabilities.names()).toEqual([
      'findingDetector',
      'preflight',
      'publisher',
      'resourcePlanner',
      'router',
      'traceSource',
      'verifier',
    ])
    await profile.dispose()
    expect(ctx.capabilities).toBeUndefined()
  })
})
