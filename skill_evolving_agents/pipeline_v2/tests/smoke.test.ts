import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { CapabilityRegistry } from '../src/core/capabilities.ts'

describe('cordis smoke', () => {
  it('mounts the capability registry', async () => {
    const ctx = new Context()
    await ctx.plugin(CapabilityRegistry)
    expect(ctx.capabilities.size).toBe(0)
  })
})
