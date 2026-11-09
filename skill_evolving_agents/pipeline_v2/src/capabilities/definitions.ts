import type { Candidate, Finding, VerificationEvidence } from '../contracts/evidence.ts'
import type { Operation, PublicationReceipt } from '../contracts/operations.ts'
import type { Resource } from '../contracts/resources.ts'
import type { SkillId, TraceId } from '../contracts/ids.ts'

/** One normalized trace available to later phases. */
export interface Trace {
  readonly id: TraceId
  readonly source: string
  readonly turns: readonly string[]
}

/** A provider that discovers and reads traces. */
export interface TraceSource {
  /** List available traces. */
  list(): Promise<readonly TraceId[]>
  /** Read one trace, failing structurally when it is unknown. */
  read(id: TraceId): Promise<Trace>
}

/** A provider that detects reusable findings in one trace. */
export interface FindingDetector {
  /** Detect findings in a trace. */
  detect(trace: Trace): Promise<readonly Finding[]>
}

/** Input for candidate recall. */
export interface RecallRequest {
  readonly trace: Trace
  readonly findings: readonly Finding[]
  readonly limit: number
}

/** A provider that recalls candidate skills. */
export interface CandidateRecall {
  /** Recall candidates in deterministic rank order. */
  recall(request: RecallRequest): Promise<readonly Candidate[]>
}

/** A decision made by a goal planner. */
export interface GoalDecision {
  readonly summary: string
  readonly operations: readonly Operation[]
}

/** Input for goal planning. */
export interface GoalRequest {
  readonly finding: Finding
  readonly candidates: readonly Candidate[]
}

/** A provider that turns a finding and candidates into planned operations. */
export interface GoalPlanner {
  /** Plan one decision; it may return no operations. */
  plan(request: GoalRequest): Promise<GoalDecision>
}

/** Result of a skill mutation. */
export interface MutationResult {
  readonly changed: boolean
  readonly resources: readonly Resource[]
}

/** A provider that applies a planned operation to a candidate workspace. */
export interface SkillMutator {
  /** Apply one operation; providers must be side-effect isolated by the caller. */
  mutate(operation: Operation): Promise<MutationResult>
}

/** A provider that verifies an operation against its declared evidence. */
export interface Verifier {
  /** Verify one operation. */
  verify(operation: Operation): Promise<VerificationEvidence>
}

/** A provider that publishes or stages an accepted operation. */
export interface Publisher {
  /** Publish one accepted operation and return its immutable receipt. */
  publish(operation: Operation): Promise<PublicationReceipt>
}

/** Feedback input emitted after a benchmark or local comparison. */
export interface FeedbackInput {
  readonly taskId: string
  readonly skillId: SkillId
  readonly rewardDelta: number
  readonly baselineToolCalls: number
  readonly treatmentToolCalls: number
}

/** A provider that records calibrated feedback. */
export interface FeedbackLearner {
  /** Record one feedback observation without mutating global state directly. */
  record(input: FeedbackInput): Promise<void>
}

/** Capability names and their provider interfaces. */
export interface CapabilityMap {
  traceSource: TraceSource
  findingDetector: FindingDetector
  candidateRecall: CandidateRecall
  goalPlanner: GoalPlanner
  skillMutator: SkillMutator
  verifier: Verifier
  publisher: Publisher
  feedbackLearner: FeedbackLearner
}

/** Every mountable capability name. */
export type CapabilityName = keyof CapabilityMap
