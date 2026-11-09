import type {
  CandidateRecall,
  FeedbackInput,
  FeedbackLearner,
  FindingDetector,
  GoalDecision,
  GoalPlanner,
  MutationResult,
  Publisher,
  RecallRequest,
  SkillMutator,
  Trace,
  Verifier,
} from '../capabilities/definitions.ts'
import type { Candidate, Finding, VerificationEvidence } from '../contracts/evidence.ts'
import { findingId, operationId, resourceId, skillId, type SkillId } from '../contracts/ids.ts'
import type { Operation, PublicationReceipt } from '../contracts/operations.ts'

/** Detects repeated failure and correction language without a model call. */
export class KeywordFindingDetector implements FindingDetector {
  async detect(trace: Trace): Promise<readonly Finding[]> {
    const text = trace.turns.join('\n').toLowerCase()
    const matches = ['retry', 'failed', 'error', 'again', 'wrong', 'timeout']
      .filter(token => text.includes(token))
    if (matches.length === 0) return []
    return [{
      id: findingId(`${trace.id}:keyword-failure`),
      traceId: trace.id,
      detector: 'keyword-failure-v1',
      confidence: Math.min(0.95, 0.65 + matches.length * 0.05),
      summary: `repeated failure evidence: ${matches.join(', ')}`,
    }]
  }
}

/** Recalls skills by deterministic token overlap. */
export class LexicalCandidateRecall implements CandidateRecall {
  constructor(private readonly inventory: Readonly<Record<string, string>>) {}

  async recall(request: RecallRequest): Promise<readonly Candidate[]> {
    const query = `${request.trace.turns.join(' ')} ${request.findings.map(row => row.summary).join(' ')}`
      .toLowerCase().split(/\W+/).filter(token => token.length > 2)
    const queryTokens = new Set(query)
    return Object.entries(this.inventory).map(([id, document]) => {
      const tokens = new Set(document.toLowerCase().split(/\W+/).filter(token => token.length > 2))
      const overlap = [...queryTokens].filter(token => tokens.has(token)).length
      return { skillId: skillId(id), score: overlap / Math.max(queryTokens.size, 1) }
    }).filter(row => row.score > 0).sort((left, right) =>
      right.score - left.score || left.skillId.localeCompare(right.skillId)
    ).slice(0, request.limit)
  }
}

/** Plans one bounded update only when recall found a candidate. */
export class DeterministicGoalPlanner implements GoalPlanner {
  async plan(request: Parameters<GoalPlanner['plan']>[0]): Promise<GoalDecision> {
    const candidate = request.candidates[0]
    if (!candidate) return { summary: 'no matching skill', operations: [] }
    return {
      summary: 'add deterministic failure-recovery guidance',
      operations: [{
        id: operationId(`${request.finding.id}:update:${candidate.skillId}`),
        kind: 'update',
        skillId: candidate.skillId,
        findingId: request.finding.id,
        summary: request.finding.summary,
      }],
    }
  }
}

/** Produces one eval resource as an isolated mutation result. */
export class InMemorySkillMutator implements SkillMutator {
  async mutate(operation: Operation): Promise<MutationResult> {
    return {
      changed: operation.kind !== 'no_change',
      resources: operation.kind === 'no_change' ? [] : [{
        id: resourceId(`${operation.id}:eval`),
        operationId: operation.id,
        skillId: operation.skillId,
        kind: 'evals',
        path: `evals/${operation.id}.json`,
        status: 'generated',
      }],
    }
  }
}

/** Accepts changed operations for the deterministic offline slice. */
export class DeterministicVerifier implements Verifier {
  async verify(operation: Operation): Promise<VerificationEvidence> {
    return operation.kind === 'no_change'
      ? { status: 'fail', summary: 'no mutation to verify' }
      : { status: 'pass', summary: 'deterministic fixture verification passed' }
  }
}

/** Returns immutable in-memory publication receipts. */
export class InMemoryPublisher implements Publisher {
  async publish(operation: Operation): Promise<PublicationReceipt> {
    return {
      operationId: operation.id,
      releaseId: `release:${operation.id}`,
      channel: 'provisional',
    }
  }
}

/** Captures feedback for tests and offline comparison. */
export class InMemoryFeedbackLearner implements FeedbackLearner {
  readonly observations: FeedbackInput[] = []

  async record(input: FeedbackInput): Promise<void> {
    this.observations.push(input)
  }
}

/** Construct a small inventory entry without leaking string branding to callers. */
export function inventorySkill(value: string): SkillId {
  return skillId(value)
}
