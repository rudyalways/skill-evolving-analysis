import { Context, Service } from '@deepseek-ai/cordis'
import type { Disposable, Plugin } from '@deepseek-ai/cordis'
import {
  CapabilityMissingError,
  DuplicateCapabilityError,
} from '../contracts/errors.ts'
import type {
  CapabilityMap,
  CapabilityName,
} from '../capabilities/definitions.ts'

/** A registry of capability providers whose entries are reversed on disposal. */
export class CapabilityRegistry extends Service {
  private readonly entries = new Map<CapabilityName, CapabilityMap[CapabilityName]>()

  constructor(ctx: Context) {
    super(ctx, 'capabilities')
  }

  /** Number of mounted providers. */
  get size(): number {
    return this.entries.size
  }

  /** Register one provider; a second registration without replacement fails. */
  register<K extends CapabilityName>(name: K, provider: CapabilityMap[K]): Disposable {
    if (this.entries.has(name)) throw new DuplicateCapabilityError(name)
    this.entries.set(name, provider)
    return () => {
      if (this.entries.get(name) === provider) this.entries.delete(name)
    }
  }

  /** Replace one provider, disposing the previous registration first. */
  replace<K extends CapabilityName>(name: K, provider: CapabilityMap[K]): Disposable {
    const previous = this.entries.get(name)
    if (previous) {
      this.entries.delete(name)
    }
    return this.register(name, provider)
  }

  /** Read one provider without requiring it. */
  get<K extends CapabilityName>(name: K): CapabilityMap[K] | undefined {
    return this.entries.get(name) as CapabilityMap[K] | undefined
  }

  /** Read one provider or fail with a structured missing-capability error. */
  require<K extends CapabilityName>(name: K): CapabilityMap[K] {
    const provider = this.get(name)
    if (!provider) throw new CapabilityMissingError(name)
    return provider
  }

  /** Mounted capability names in stable order. */
  names(): readonly CapabilityName[] {
    return [...this.entries.keys()].sort()
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    capabilities: CapabilityRegistry
  }
}

/** Options for mounting one provider as a Cordis plugin. */
export interface ProviderPluginOptions {
  /** Replace an existing provider instead of failing as a duplicate. */
  readonly replace?: boolean
}

/**
 * Create a Cordis plugin that registers one capability provider as an effect.
 *
 * Disposing the plugin fiber runs the effect disposer, so the provider entry
 * disappears without affecting a later replacement.
 */
export function providerPlugin<K extends CapabilityName>(
  name: K,
  provider: CapabilityMap[K],
  options: ProviderPluginOptions = {},
): Plugin.Object<void> {
  return {
    name: `pipeline-v2/provider/${name}`,
    inject: ['capabilities'],
    apply(ctx) {
      ctx.effect(() => {
        const registry = ctx.capabilities
        return options.replace
          ? registry.replace(name, provider)
          : registry.register(name, provider)
      }, `pipeline-v2/provider/${name}`)
    },
  }
}
