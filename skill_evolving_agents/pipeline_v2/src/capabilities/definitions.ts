import type { Candidate, Finding, VerificationEvidence } from '../contracts/evidence.ts'
import type { Operation, PublicationReceipt } from '../contracts/operations.ts'
import type { Resource } from '../contracts/resources.ts'
import type { SkillId, TraceId } from '../contracts/ids.ts'
import type {
  PreflightReport,
  PreflightRequest,
} from '../preflight/preflight.ts'
import type {
  SkillPlan,
  SkillPlanningRequest,
} from '../resources/planner.ts'
import type {
  RouterBudget,
  RouterResult,
  RouterRetrieval,
  RouterTask,
} from '../router/two-stage-router.ts'
import type {
  GeneralizationDecision,
  GeneralizationObservation,
  GeneralizationPolicy,
  SearchCandidate,
  SearchRequest,
} from '../search/contracts.ts'

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

/** A provider that proposes bounded pipeline configuration candidates. */
export interface ConfigurationSearch {
  /** Propose a deterministic, diverse candidate batch. */
  search(request: SearchRequest): readonly SearchCandidate[]
}

/** A provider that scores validation without learning from sealed holdout. */
export interface GeneralizationEvaluator {
  /** Evaluate disjoint train, validation, and holdout observations. */
  evaluate(
    observations: readonly GeneralizationObservation[],
    policy: GeneralizationPolicy,
  ): GeneralizationDecision
}

/** A provider that retrieves and decides skill actions with bounded evidence. */
export interface RouterCapability {
  retrieve(task: RouterTask): Promise<RouterRetrieval>
  route(task: RouterTask, budget: RouterBudget): Promise<RouterResult>
}

/** A provider that renders a complete resource plan for one operation. */
export interface ResourcePlannerCapability {
  plan(request: SkillPlanningRequest): SkillPlan
}

/** A provider that executes deterministic preflight checks. */
export interface PreflightCapability {
  run(request: PreflightRequest): Promise<PreflightReport>
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
  router: RouterCapability
  resourcePlanner: ResourcePlannerCapability
  preflight: PreflightCapability
  configurationSearch: ConfigurationSearch
  generalizationEvaluator: GeneralizationEvaluator
}

/** Every mountable capability name. */
export type CapabilityName = keyof CapabilityMap
