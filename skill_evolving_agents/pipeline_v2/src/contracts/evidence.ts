import type { FindingId, SkillId, TraceId } from './ids.ts'

/** A durable observation extracted from one trace. */
export interface Finding {
  readonly id: FindingId
  readonly traceId: TraceId
  readonly detector: string
  readonly confidence: number
  readonly summary: string
}

/** One recalled skill candidate and its deterministic score. */
export interface Candidate {
  readonly skillId: SkillId
  readonly score: number
  readonly reason?: string
}

/** A verification outcome, including budget exhaustion. */
export type VerificationStatus = 'pass' | 'fail' | 'efficiency_failure'

/** Evidence returned by a verifier provider. */
export interface VerificationEvidence {
  readonly status: VerificationStatus
  readonly summary: string
  readonly details?: Readonly<Record<string, unknown>>
}
