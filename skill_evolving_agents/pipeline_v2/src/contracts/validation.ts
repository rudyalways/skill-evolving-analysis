import type { StructuredIssue } from './errors.ts'

/** Return true for a non-array object. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Return true for a non-empty string. */
export function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

/** Return true for a finite number. */
export function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/** Build one structured validation issue. */
export function issue(path: string, code: string, message: string): StructuredIssue {
  return { path, code, message }
}
