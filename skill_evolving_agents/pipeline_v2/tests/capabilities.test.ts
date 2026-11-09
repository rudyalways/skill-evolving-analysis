import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { CapabilityRegistry, providerPlugin } from '../src/core/capabilities.ts'
import {
  CapabilityMissingError,
  DuplicateCapabilityError,
} from '../src/contracts/errors.ts'
import { InMemoryTraceSource, UnknownTraceError } from '../src/capabilities/providers.ts'
import { traceId } from '../src/contracts/ids.ts'

function source(label: string) {
  return new InMemoryTraceSource([
    { id: traceId(`${label}-trace`), source: label, turns: ['one'] },
  ])
}

describe('Cordis capability lifecycle', () => {
  it('mounts and disposes a provider without leaving a registration', async () => {
    const ctx = new Context()
    const registryFiber = await ctx.plugin(CapabilityRegistry)
    const provider = source('a')
    const fiber = await ctx.plugin(providerPlugin('traceSource', provider))
    expect(ctx.capabilities.get('traceSource')).toBe(provider)
    expect(ctx.capabilities.names()).toEqual(['traceSource'])

    await fiber.dispose()
    expect(ctx.capabilities.get('traceSource')).toBeUndefined()
    expect(ctx.capabilities.size).toBe(0)

    await registryFiber.dispose()
    expect(ctx.capabilities).toBeUndefined()
  })

  it('replaces a provider and preserves the replacement when the old fiber disposes', async () => {
    const ctx = new Context()
    const registryFiber = await ctx.plugin(CapabilityRegistry)
    const first = source('first')
    const second = source('second')
    const firstFiber = await ctx.plugin(providerPlugin('traceSource', first))
    const secondFiber = await ctx.plugin(
      providerPlugin('traceSource', second, { replace: true }),
    )
    expect(ctx.capabilities.get('traceSource')).toBe(second)

    await firstFiber.dispose()
    expect(ctx.capabilities.get('traceSource')).toBe(second)
    await secondFiber.dispose()
    expect(ctx.capabilities.get('traceSource')).toBeUndefined()
    await registryFiber.dispose()
  })

  it('fails a duplicate registration with a structured error', async () => {
    const ctx = new Context()
    const registryFiber = await ctx.plugin(CapabilityRegistry)
    const first = source('first')
    await ctx.plugin(providerPlugin('traceSource', first))
    await expect(
      ctx.plugin(providerPlugin('traceSource', source('second'))),
    ).rejects.toBeInstanceOf(DuplicateCapabilityError)
    expect(ctx.capabilities.get('traceSource')).toBe(first)
    await registryFiber.dispose()
  })

  it('fails require() when a capability is missing', async () => {
    const ctx = new Context()
    const registryFiber = await ctx.plugin(CapabilityRegistry)
    expect(() => ctx.capabilities.require('verifier')).toThrow(CapabilityMissingError)
    await registryFiber.dispose()
  })

  it('uses deterministic in-memory trace behavior and structured unknown-trace failures', async () => {
    const provider = source('fixture')
    const id = traceId('fixture-trace')
    expect(await provider.list()).toEqual([id])
    expect((await provider.read(id)).source).toBe('fixture')
    await expect(provider.read(traceId('missing'))).rejects.toBeInstanceOf(
      UnknownTraceError,
    )
  })
})
