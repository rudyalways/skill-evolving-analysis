import { PipelineError } from '../contracts/errors.ts'
import type { TraceId } from '../contracts/ids.ts'
import type { Trace, TraceSource } from './definitions.ts'

/** A trace id was requested from a source that does not know it. */
export class UnknownTraceError extends PipelineError {
  constructor(id: TraceId) {
    super('unknown-trace', `unknown trace ${id}`, { traceId: id })
  }
}

/** Deterministic in-memory trace source used by offline tests and fixtures. */
export class InMemoryTraceSource implements TraceSource {
  private readonly traces = new Map<TraceId, Trace>()

  constructor(initial: readonly Trace[] = []) {
    for (const trace of initial) this.traces.set(trace.id, trace)
  }

  /** Add or replace one trace without creating any external state. */
  add(trace: Trace): void {
    this.traces.set(trace.id, trace)
  }

  async list(): Promise<readonly TraceId[]> {
    return [...this.traces.keys()].sort()
  }

  async read(id: TraceId): Promise<Trace> {
    const trace = this.traces.get(id)
    if (!trace) throw new UnknownTraceError(id)
    return trace
  }
}
