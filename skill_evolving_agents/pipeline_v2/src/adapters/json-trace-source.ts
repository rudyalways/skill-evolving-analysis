import { readFile } from 'node:fs/promises'
import type { TraceSource, Trace } from '../capabilities/definitions.ts'
import { traceId, type TraceId } from '../contracts/ids.ts'
import { isNonEmptyString, isRecord } from '../contracts/validation.ts'
import { PipelineError } from '../contracts/errors.ts'

/** A trace file failed validation. */
export class InvalidTraceFileError extends PipelineError {
  constructor(message: string, details: Readonly<Record<string, unknown>> = {}) {
    super('invalid-trace-file', message, details)
  }
}

/** One JSON trace fixture with turns. */
export interface JsonTraceFile {
  readonly id: string
  readonly source: string
  readonly turns: readonly string[]
}

/** Read a trace JSON file with an id, source, and string turns. */
export async function readJsonTraceFile(path: string): Promise<Trace> {
  let parsed: unknown
  try {
    parsed = JSON.parse(await readFile(path, 'utf8'))
  } catch (error) {
    throw new InvalidTraceFileError(`cannot read trace file ${path}`, {
      cause: error instanceof Error ? error.message : String(error),
    })
  }
  if (!isRecord(parsed)) throw new InvalidTraceFileError('trace file must be a JSON object')
  if (!isNonEmptyString(parsed.id)) throw new InvalidTraceFileError('trace id must be a non-empty string')
  if (!isNonEmptyString(parsed.source)) throw new InvalidTraceFileError('trace source must be a non-empty string')
  if (!Array.isArray(parsed.turns) || parsed.turns.some(turn => typeof turn !== 'string')) {
    throw new InvalidTraceFileError('trace turns must be an array of strings')
  }
  return {
    id: traceId(parsed.id),
    source: parsed.source,
    turns: parsed.turns,
  }
}

/** Trace source backed by one validated JSON file. */
export class JsonFileTraceSource implements TraceSource {
  private readonly trace: Trace
  constructor(trace: Trace) {
    this.trace = trace
  }

  static async open(path: string): Promise<JsonFileTraceSource> {
    return new JsonFileTraceSource(await readJsonTraceFile(path))
  }

  async list(): Promise<readonly TraceId[]> {
    return [this.trace.id]
  }

  async read(id: TraceId): Promise<Trace> {
    if (id !== this.trace.id) throw new InvalidTraceFileError(`unknown trace ${id}`)
    return this.trace
  }
}
