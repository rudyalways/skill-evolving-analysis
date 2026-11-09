# pipeline_v2

Milestone 0 of the Cordis-native skill-evolution pipeline. This package is a
parallel implementation beside the existing Python pipeline; the Python code is
unchanged and remains the default runtime.

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

It intentionally contains **no model providers, no embedding providers, no
network calls, no Docker, no database, and no paid evaluation**.

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
src/core/        event log, projections, capability registry, run controller
src/capabilities/ capability interfaces and an in-memory trace fixture
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
../../../../oss/deepseek-harness/node_modules/.bin/tsc -p tsconfig.json
../../../../oss/deepseek-harness/node_modules/.bin/vitest run --config vitest.config.ts
```

The commands are offline. They read the Cordis source from the DSH checkout but
do not modify it. In a normal installed environment, use `npm run typecheck` and
`npm test` after installing the declared peer/dev dependencies.

## Milestone boundary

Milestone 0 stops at contracts, the event log, projections, provider lifecycle,
and the worker/comparison schemas. It does not add model-backed providers,
replay execution, publication receipts, or DSH bundle integration.
