import { InvalidIdError } from './errors.ts'

declare const idBrand: unique symbol

/** A string id that cannot be assigned from an unrelated string. */
export type Branded<T extends string, B extends string> = T & {
  readonly [idBrand]: B
}

/** A run identity. */
export type RunId = Branded<string, 'RunId'>
/** A source trace identity. */
export type TraceId = Branded<string, 'TraceId'>
/** A detected finding identity. */
export type FindingId = Branded<string, 'FindingId'>
/** A planned operation identity. */
export type OperationId = Branded<string, 'OperationId'>
/** A skill identity. */
export type SkillId = Branded<string, 'SkillId'>
/** A generated resource identity. */
export type ResourceId = Branded<string, 'ResourceId'>
/** An append-only event identity. */
export type EventId = Branded<string, 'EventId'>

/** Construct a branded id from a non-empty string. */
export function brandId<B extends string>(value: unknown, kind: string): Branded<string, B> {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new InvalidIdError(kind, value)
  }
  return value as Branded<string, B>
}

export const runId = (value: string): RunId => brandId<'RunId'>(value, 'run')
export const traceId = (value: string): TraceId => brandId<'TraceId'>(value, 'trace')
export const findingId = (value: string): FindingId => brandId<'FindingId'>(value, 'finding')
export const operationId = (value: string): OperationId => brandId<'OperationId'>(value, 'operation')
export const skillId = (value: string): SkillId => brandId<'SkillId'>(value, 'skill')
export const resourceId = (value: string): ResourceId => brandId<'ResourceId'>(value, 'resource')
export const eventId = (value: string): EventId => brandId<'EventId'>(value, 'event')
