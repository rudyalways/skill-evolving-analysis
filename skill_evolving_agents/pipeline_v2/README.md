# pipeline_v2

Milestones 0–2 of the Cordis-native skill-evolution pipeline. This package is
now the primary orchestration implementation for the new vertical slice; the
existing Python pipeline remains the compatibility baseline, trace/report
adapter, and comparison oracle until each provider is ported and verified.

## What Milestone 0 contains

- branded run, trace, finding, operation, skill, resource, and event ids;
- versioned durable event unions for the run lifecycle;
- an in-memory append-only event log with schema and transition validation,
  one-run identity enforcement, terminal operation closure, and duplicate
  resource rejection;
- deterministic projections for run status, funnel counts, operations,
  resource use, and failures;
- capability interfaces for every pipeline phase;
- a Cordis `CapabilityRegistry` service and provider plugin factory whose
  registrations are reversed through `ctx.effect()` disposers;
- a versioned JSON request/result protocol for future Python workers;
- a versioned legacy/v2 comparison-report schema.

The integrated slice adds:

- a durable append-only JSONL study store with atomic snapshots, restart/replay,
  idempotent writes, schema migration, duplicate/mixed-run protection, and
  hard rejection of holdout feedback into search;
- a two-stage router with deterministic lexical/embedding recall, bounded
  stage-two decisions, explicit budgets, abstention, and labeled metrics;
- a resource planner that renders justified `SKILL.md`, `scripts/`,
  `references/`, `evals/`, and conditional `assets/` bundles for the four
  general failure families;
- executable preflight with path, structure, resource, reference, script,
  leakage, duplicate, token, tool-call, and wall-time checks;
- benchmark admission/reporting that separates raw, activated-skill, and
  selective-policy views and excludes invalid exposure;
- `V2Pipeline`, which mounts every phase through Cordis capability providers
  and replays the result from the durable store.

It still contains **no model providers, no external embedding service, no
network calls, no Docker, and no paid evaluation**. The store is JSONL-backed;
SQLite remains a future backend behind the same facade.

## Milestone 1 search control plane

Configuration search and generalization evaluation now have native TypeScript
capability seams:

- `ConfigurationSearch` proposes a deterministic, diverse portfolio combining
  wide probes, validation-history exploitation, MCTS-style exploration, and
  seeded random exploration.
- `GeneralizationEvaluator` scores validation evidence, enforces disjoint task
  and task-family membership across stages, and treats holdout as a sealed final
  gate.
- Holdout results are never included in `validationReward`, so a feedback
  learner cannot backpropagate the final test cohort into search.
- The default acceptance contract is representable as 60% across at least 16
  held-out tasks and 8 domains, with zero regressions and bounded efficiency
  failures.

These providers are offline and have no Python dependency. The Python search
implementation remains a temporary comparison oracle until the v2 controller
and persistence provider consume these capabilities end to end.

## Why Cordis

The package uses the real Cordis runtime from the read-only DSH checkout rather
than reimplementing lifecycle semantics:

- `Context` owns the service repository;
- `CapabilityRegistry` is a `Service` claimed as `ctx.capabilities`;
- `providerPlugin()` mounts a provider with `ctx.plugin()`;
- the registration is created inside `ctx.effect()`;
- disposing the plugin fiber runs the effect disposer;
- replacement is explicit, and an old fiber cannot remove a newer provider.

This is the property the Python pipeline cannot currently provide: mount,
measure, replace, and remove a provider without leaking global registrations.

## Layout

```text
src/contracts/   ids, errors, events, evidence, operations, resources,
                 worker protocol, comparison report
src/core/        event log, projections, capability registry, run controller,
                 durable v2 pipeline
src/capabilities/ capability interfaces and an in-memory trace fixture
src/router/      two-stage recall and bounded decision
src/store/       durable JSONL study store with atomic snapshots
src/resources/   resource planning and in-memory skill bundle rendering
src/preflight/   executable preflight checks
src/benchmark/   admission, three-view report, Wilson/sign-test metrics
src/search/      portfolio search, successive halving, sealed generalization
src/adapters/    validated Python worker client seam
src/providers/   deterministic low-cost providers and new capability providers
src/vendor/      narrow ambient Cordis type boundary used only by tsc
src/index.ts     public package surface
tests/           focused offline lifecycle, validation, projection, protocol tests
```

The exact layout in the design note allowed per-capability files. Milestone 0
uses one `capabilities/definitions.ts` file to keep the slice small; the
interfaces are still independent of their providers.

`src/vendor/cordis.d.ts` is a narrow ambient declaration for the external
Cordis API. TypeScript compiles our package with full strict checks and does not
recompile the vendored source; Vitest resolves the same import to the real
Cordis source in the read-only DSH checkout. This keeps the vendor boundary out
of our strictness settings without changing runtime behavior.

## Using the package

A consumer mounts the registry and one provider:

```ts
import { Context } from '@deepseek-ai/cordis'
import { CapabilityRegistry, providerPlugin } from './src/core/capabilities.ts'
import { InMemoryTraceSource } from './src/capabilities/providers.ts'

const ctx = new Context()
await ctx.plugin(CapabilityRegistry)
const fiber = await ctx.plugin(
  providerPlugin('traceSource', new InMemoryTraceSource()),
)
await fiber.dispose()
// ctx.capabilities.get('traceSource') is undefined again
```

A run is written through `EventLog` or `RunController` and read through
`projectEvents`. Projection is a pure fold: the same event sequence produces the
same bytes. The log rejects mixed run ids, duplicate event ids, duplicate
resource ids, and any verification that would reopen an accepted, rejected, or
published operation.

`mountLowCostV2Profile()` mounts the deterministic trace, detector, router,
planner, preflight, verifier, and publisher providers through Cordis and returns
a disposer plus a `V2Pipeline` factory. `V2Pipeline` writes every phase to the
event log, mirrors it to the durable store, and replays the final projection
from disk.

## Worker boundary

`parseWorkerRequest` and `parseWorkerResult` validate protocol version `1`,
explicit limits, structured errors, and status-specific payloads. A future
Python worker only needs to read one JSON request and emit one JSON result; it
does not own pipeline-global state.

## Coexistence with the Python pipeline

- No Python module imports this package.
- No Python entrypoint selects v2.
- Both implementations can consume the same frozen trace fixtures.
- `LegacyComparisonReport` is the boundary for documenting event projections,
  selected operations, resources, replay, usage, output equivalence, and cleanup.
- A v2 provider must match or exceed frozen legacy behavior before it can replace
  a Python phase.

## Commands

From this directory, with the DSH checkout present at its documented path:

```sh
./node_modules/.bin/tsc -p tsconfig.json
./node_modules/.bin/vitest run --config vitest.config.ts
```

The commands are offline. Tests resolve Cordis from the read-only DSH checkout
through `vitest.config.ts`; `tsconfig.json` keeps its Node type root there.
Neither modifies the DSH checkout. In a normal installed environment, use
`pnpm run typecheck` and `pnpm test`.

## Milestone boundary

The durable v2 slice is implemented and offline-tested. It does **not** yet
include a real replay verifier, content-addressed publication receipts, a
benchmark observation producer for legacy job directories, model-backed
providers, or DSH bundle/profile packaging. No fresh sealed holdout has been
run against v2. The achieved benchmark result remains baseline `5/16` and
selective policy `6/16`; the 10/16 milestone is not claimed.
