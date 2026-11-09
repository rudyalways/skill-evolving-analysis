import { Context } from '@deepseek-ai/cordis'
import type { TraceId } from '../contracts/ids.ts'
import { RunController } from './run-controller.ts'
import type { RunProjection } from './projections.ts'

function stableGoalHash(value: unknown): string {
  const text = JSON.stringify(value)
  let hash = 2166136261
  for (const character of text) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return `goal-${(hash >>> 0).toString(16).padStart(8, '0')}`
}

/** Input to one deterministic v2 run. */
export interface PipelineRunRequest {
  readonly traceId: TraceId
  readonly objective: string
  readonly profile: string
  readonly at: string
  readonly recallLimit: number
}

/** Executes the mounted capability graph and writes every decision as an event. */
export class PipelineController {
  constructor(
    private readonly ctx: Context,
    private readonly run: RunController,
  ) {}

  async execute(request: PipelineRunRequest): Promise<RunProjection> {
    this.run.start(request.objective, request.profile, request.at)
    try {
      const trace = await this.ctx.capabilities.require('traceSource').read(request.traceId)
      if (trace.id !== request.traceId) {
        throw new Error(`trace source returned ${trace.id} for ${request.traceId}`)
      }
      this.run.append('trace/ingested', {
        traceId: trace.id,
        source: trace.source,
        turns: trace.turns.length,
      }, request.at)
      const findings = await this.ctx.capabilities.require('findingDetector').detect(trace)
      for (const finding of findings) {
        if (finding.traceId !== trace.id) {
          throw new Error(`finding ${finding.id} belongs to unexpected trace ${finding.traceId}`)
        }
        this.run.append('finding/detected', {
          findingId: finding.id,
          traceId: finding.traceId,
          detector: finding.detector,
          confidence: finding.confidence,
          summary: finding.summary,
        }, request.at)
      }
      if (findings.length === 0) {
        this.run.append('run/completed', { summary: 'no reusable finding' }, request.at)
        return this.run.snapshot()
      }
      const candidates = await this.ctx.capabilities.require('candidateRecall').recall({
        trace,
        findings,
        limit: request.recallLimit,
      })
      this.run.append('candidate/recalled', { skillIds: candidates.map(row => row.skillId) }, request.at)
      const firstCandidate = candidates[0]
      if (firstCandidate) {
        this.run.append('candidate/selected', {
          skillId: firstCandidate.skillId,
          score: firstCandidate.score,
        }, request.at)
      }
      const finding = findings[0]!
      this.run.append('diagnosis/recorded', {
        findingId: finding.id,
        summary: finding.summary,
      }, request.at)
      const goal = await this.ctx.capabilities.require('goalPlanner').plan({ finding, candidates })
      this.run.append('goal/proposed', {
        goalHash: stableGoalHash(goal),
        operationCount: goal.operations.length,
      }, request.at)
      for (const operation of goal.operations) {
        this.run.append('operation/planned', { operation }, request.at)
        const mutation = await this.ctx.capabilities.require('skillMutator').mutate(operation)
        if (!mutation.changed) {
          this.run.append('verification/completed', {
            operationId: operation.id,
            status: 'fail',
            summary: 'mutator reported no change',
          }, request.at)
          this.run.append('operation/rejected', {
            operationId: operation.id,
            reason: 'mutator reported no change',
          }, request.at)
          continue
        }
        for (const resource of mutation.resources) {
          this.run.append('resource/generated', { resource }, request.at)
        }
        const verification = await this.ctx.capabilities.require('verifier').verify(operation)
        this.run.append('verification/completed', {
          operationId: operation.id,
          status: verification.status,
          summary: verification.summary,
        }, request.at)
        if (verification.status !== 'pass') {
          this.run.append('operation/rejected', {
            operationId: operation.id,
            reason: verification.summary,
          }, request.at)
          continue
        }
        this.run.append('operation/accepted', {
          operationId: operation.id,
          reason: 'verification passed',
        }, request.at)
        const receipt = await this.ctx.capabilities.require('publisher').publish(operation)
        this.run.append('publication/completed', {
          operationId: receipt.operationId,
          releaseId: receipt.releaseId,
          channel: receipt.channel,
        }, request.at)
      }
      this.run.append('run/completed', {
        summary: `processed ${goal.operations.length} operation(s)`,
      }, request.at)
      return this.run.snapshot()
    } catch (error) {
      this.run.append('run/failed', {
        reason: error instanceof Error && error.message
          ? error.message
          : 'unknown pipeline failure',
      }, request.at)
      throw error
    }
  }
}
