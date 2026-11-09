import type { Context, Fiber } from '@deepseek-ai/cordis'
import type {
  FindingDetector,
  Publisher,
  SkillPublisherCapability,
  TraceSource,
  Verifier,
} from '../capabilities/definitions.ts'
import { V2Pipeline } from '../core/v2-pipeline.ts'
import { RunController } from '../core/run-controller.ts'
import { CapabilityRegistry, providerPlugin } from '../core/capabilities.ts'
import {
  KeywordFindingDetector,
  DeterministicVerifier,
  InMemoryPublisher,
} from '../providers/low-cost.ts'
import { DeterministicPreflight, DeterministicResourcePlanner } from '../providers/v2.ts'
import type {
  DecisionProvider,
  EmbeddingProvider,
  RouterConfig,
  RouterInventory,
} from '../router/two-stage-router.ts'
import { TwoStageRouter } from '../router/two-stage-router.ts'
import type { StudyStore } from '../store/study-store.ts'

/** Providers and knobs composed by the low-cost v2 profile. */
export interface LowCostV2ProfileOptions {
  readonly inventory: RouterInventory
  readonly traceSource: TraceSource
  readonly findingDetector?: FindingDetector
  readonly verifier?: Verifier
  readonly publisher?: Publisher
  readonly skillPublisher?: SkillPublisherCapability
  readonly routerConfig?: Partial<RouterConfig>
  readonly embedding?: EmbeddingProvider
  readonly decisionProvider?: DecisionProvider
}

/** A mounted profile and its coordinated disposer. */
export interface LowCostV2Profile {
  readonly pipeline: (run: RunController, store?: StudyStore) => V2Pipeline
  dispose(): Promise<void>
}

async function disposeAll(fibers: readonly Fiber[]): Promise<void> {
  for (const fiber of [...fibers].reverse()) await fiber.dispose()
}

/** Mount the deterministic low-cost graph through real Cordis providers. */
export async function mountLowCostV2Profile(
  ctx: Context,
  options: LowCostV2ProfileOptions,
): Promise<LowCostV2Profile> {
  const fibers: Fiber[] = []
  try {
    if (!ctx.capabilities) fibers.push(await ctx.plugin(CapabilityRegistry))
    fibers.push(await ctx.plugin(providerPlugin('traceSource', options.traceSource)))
    fibers.push(await ctx.plugin(providerPlugin(
      'findingDetector',
      options.findingDetector ?? new KeywordFindingDetector(),
    )))
    fibers.push(await ctx.plugin(providerPlugin(
      'verifier',
      options.verifier ?? new DeterministicVerifier(),
    )))
    fibers.push(await ctx.plugin(providerPlugin(
      'publisher',
      options.publisher ?? new InMemoryPublisher(),
    )))
    fibers.push(await ctx.plugin(providerPlugin('router', new TwoStageRouter({
      inventory: options.inventory,
      ...(options.routerConfig === undefined ? {} : { config: options.routerConfig }),
      ...(options.embedding === undefined ? {} : { embedding: options.embedding }),
      ...(options.decisionProvider === undefined ? {} : { decisionProvider: options.decisionProvider }),
    }))))
    fibers.push(await ctx.plugin(providerPlugin('resourcePlanner', new DeterministicResourcePlanner())))
    fibers.push(await ctx.plugin(providerPlugin('preflight', new DeterministicPreflight())))
    if (options.skillPublisher) {
      fibers.push(await ctx.plugin(providerPlugin('skillPublisher', options.skillPublisher)))
    }
    let disposed = false
    return {
      pipeline: (run, store) => new V2Pipeline(ctx, run, store),
      async dispose() {
        if (disposed) return
        disposed = true
        await disposeAll(fibers)
      },
    }
  } catch (error) {
    await disposeAll(fibers)
    throw error
  }
}
