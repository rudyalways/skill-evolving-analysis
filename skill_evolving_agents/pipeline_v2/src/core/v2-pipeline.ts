import type { Context } from '@deepseek-ai/cordis'
import type { EventOf, EventPayloadMap, PipelineEvent, PipelineEventType } from '../contracts/events.ts'
import { operationId, skillId, type TraceId } from '../contracts/ids.ts'
import type { Operation, PublicationReceipt } from '../contracts/operations.ts'
import type { PublicationReceiptDocument, PublicationResult } from '../publication/publisher.ts'
import type {
  PreflightPolicyOverrides,
  PreflightReport,
  ScriptRunner,
} from '../preflight/preflight.ts'
import type { FailureFamily, SkillBundle, SkillPlan } from '../resources/planner.ts'
import { InvalidResourcePlanError } from '../resources/planner.ts'
import type { RouterBudget, RouterResult } from '../router/two-stage-router.ts'
import type { StudyStore } from '../store/study-store.ts'
import { hashContent } from '../store/study-store.ts'
import type { RunProjection } from './projections.ts'
import { RunController } from './run-controller.ts'

/** Input to one durable v2 pipeline run. */
export interface V2PipelineRequest {
  readonly traceId: TraceId
  readonly taskId: string
  readonly objective: string
  readonly profile: string
  readonly at: string
  readonly family: FailureFamily
  readonly routerBudget: RouterBudget
  readonly existingBundle?: SkillBundle
  readonly preflightPolicy?: PreflightPolicyOverrides
  readonly scriptRunner?: ScriptRunner
  readonly policyVersion?: string
  readonly configVersion?: string
}

/** Outcome of one v2 run, including the evidence needed for audit. */
export interface V2PipelineResult {
  readonly projection: RunProjection
  readonly route?: RouterResult
  readonly plan?: SkillPlan
  readonly preflight?: PreflightReport
  readonly publication?: PublicationReceipt
  readonly publicationReceipt?: PublicationReceiptDocument
  readonly publicationReceiptPath?: string
  readonly reason?: string
}

/** Coordinates the deterministic v2 phases over Cordis capability providers. */
export class V2Pipeline {
  constructor(
    private readonly ctx: Context,
    private readonly run: RunController,
    private readonly store?: StudyStore,
  ) {}

  private async persist(event: PipelineEvent): Promise<void> {
    if (this.store) await this.store.appendEvent(event)
  }

  private async append<T extends PipelineEventType>(
    type: T,
    payload: EventPayloadMap[T],
    at: string,
  ): Promise<EventOf<T>> {
    const event = this.run.append(type, payload, at)
    await this.persist(event as PipelineEvent)
    return event
  }

  private async complete(summary: string, at: string): Promise<RunProjection> {
    await this.append('run/completed', { summary }, at)
    return this.store ? this.store.replay(String(this.run.runId)) : this.run.snapshot()
  }

  private async reject(operation: Operation, reason: string, at: string): Promise<RunProjection> {
    await this.append('verification/completed', {
      operationId: operation.id,
      status: 'fail',
      summary: reason,
    }, at)
    await this.append('operation/rejected', { operationId: operation.id, reason }, at)
    return this.complete(reason, at)
  }

  private async fail(error: unknown, at: string): Promise<void> {
    const reason = error instanceof Error && error.message.length > 0
      ? error.message
      : 'unknown pipeline failure'
    try {
      await this.append('run/failed', { reason }, at)
    } catch {
      // Preserve the original failure when the run was already terminal.
    }
  }

  private operationFor(route: RouterResult, findingId: Operation['findingId']): Operation | undefined {
    const decision = route.decision
    const kind = decision.kind === 'create'
      ? 'create'
      : decision.kind === 'update'
        ? 'update'
        : decision.kind === 'merge'
          ? 'merge'
          : decision.kind === 'reuse'
            ? 'no_change'
            : undefined
    if (kind === undefined) return undefined
    const skill = decision.skillId ?? skillId(`${this.run.runId}:generated-skill`)
    return {
      id: operationId(`${this.run.runId}:operation:1`),
      kind,
      skillId: skill,
      findingId,
      summary: decision.rationale,
    }
  }

  private async plan(
    request: V2PipelineRequest,
    operation: Operation,
    findingId: Operation['findingId'],
  ): Promise<SkillPlan> {
    const finding = {
      id: findingId,
      traceId: request.traceId,
      detector: 'v2-router',
      confidence: 1,
      summary: operation.summary,
    }
    return this.ctx.capabilities.require('resourcePlanner').plan({
      operation,
      finding,
      family: request.family,
      ...(request.existingBundle === undefined ? {} : { existingBundle: request.existingBundle }),
    })
  }

  async execute(request: V2PipelineRequest): Promise<V2PipelineResult> {
    await this.persist(this.run.start(request.objective, request.profile, request.at))
    try {
      const trace = await this.ctx.capabilities.require('traceSource').read(request.traceId)
      if (trace.id !== request.traceId) {
        throw new Error(`trace source returned ${String(trace.id)} for ${String(request.traceId)}`)
      }
      await this.append('trace/ingested', {
        traceId: trace.id,
        source: trace.source,
        turns: trace.turns.length,
      }, request.at)
      if (this.store) {
        await this.store.recordTraceIdentity({
          runId: String(this.run.runId),
          traceId: String(trace.id),
          source: trace.source,
          turns: trace.turns.length,
          contentHash: hashContent(trace.turns.join('\n')),
        })
      }

      const findings = await this.ctx.capabilities.require('findingDetector').detect(trace)
      for (const finding of findings) {
        if (finding.traceId !== trace.id) {
          throw new Error(`finding ${String(finding.id)} belongs to unexpected trace ${String(finding.traceId)}`)
        }
        await this.append('finding/detected', {
          findingId: finding.id,
          traceId: finding.traceId,
          detector: finding.detector,
          confidence: finding.confidence,
          summary: finding.summary,
        }, request.at)
      }
      const finding = findings[0]
      if (!finding) {
        const projection = await this.complete('no reusable finding', request.at)
        return { projection, reason: 'no reusable finding' }
      }

      const route = await this.ctx.capabilities.require('router').route({
        taskId: request.taskId,
        text: trace.turns.join('\n'),
        family: request.family,
        intent: 'evolve-skill',
        action: 'update',
      }, request.routerBudget)
      if (this.store) {
        await this.store.recordRouterCandidates({
          runId: String(this.run.runId),
          traceId: String(trace.id),
          candidates: route.retrieval.skills.map(candidate => ({
            skillId: String(candidate.skillId),
            score: candidate.scores.combined,
            reason: `lexical=${candidate.scores.lexical.toFixed(3)} embedding=${candidate.scores.embedding.toFixed(3)} family=${candidate.scores.family.toFixed(3)}`,
          })),
        })
      }
      await this.append('candidate/recalled', {
        skillIds: route.retrieval.skills.map(candidate => candidate.skillId),
      }, request.at)
      if (route.decision.skillId) {
        await this.append('candidate/selected', {
          skillId: route.decision.skillId,
          score: route.decision.confidence,
        }, request.at)
      }
      await this.append('diagnosis/recorded', {
        findingId: finding.id,
        summary: `${route.decision.kind}: ${route.decision.rationale}`,
      }, request.at)

      if (route.decision.kind === 'abstain') {
        const projection = await this.complete(`router abstained: ${route.decision.rationale}`, request.at)
        return { projection, route, reason: 'router abstained' }
      }
      const operation = this.operationFor(route, finding.id)
      if (!operation) {
        const projection = await this.complete(`unsupported router decision: ${route.decision.kind}`, request.at)
        return { projection, route, reason: `unsupported router decision: ${route.decision.kind}` }
      }
      if (operation.kind === 'no_change' && request.existingBundle === undefined) {
        const projection = await this.complete('reuse decision has no existing bundle to verify', request.at)
        return { projection, route, reason: 'reuse decision has no existing bundle to verify' }
      }

      await this.append('goal/proposed', {
        goalHash: hashContent(`${String(operation.id)}:${route.decision.rationale}`),
        operationCount: 1,
      }, request.at)
      await this.append('operation/planned', { operation }, request.at)

      let plan: SkillPlan
      try {
        plan = await this.plan(request, operation, finding.id)
      } catch (error) {
        const reason = error instanceof InvalidResourcePlanError
          ? error.message
          : error instanceof Error ? error.message : 'resource planning failed'
        const projection = await this.reject(operation, reason, request.at)
        return { projection, route, reason }
      }

      if (operation.kind !== 'no_change') {
        for (const planned of plan.resources) {
          await this.append('resource/generated', { resource: planned.resource }, request.at)
        }
      }

      const preflightReport = await this.ctx.capabilities.require('preflight').run({
        bundle: plan.bundle,
        plan,
        ...(request.scriptRunner === undefined ? {} : { runner: request.scriptRunner }),
        ...(request.preflightPolicy === undefined ? {} : { policy: request.preflightPolicy }),
      })
      if (preflightReport.verdict !== 'accept') {
        const reason = `preflight ${preflightReport.verdict}: ${[
          ...preflightReport.rejectReasons,
          ...preflightReport.repairReasons,
        ].map(item => item.code).join(', ') || 'no reason'}`
        const projection = await this.reject(operation, reason, request.at)
        return { projection, route, plan, preflight: preflightReport, reason }
      }

      const verification = await this.ctx.capabilities.require('verifier').verify(operation, {
        plan,
        bundle: plan.bundle,
        preflight: preflightReport,
      })
      await this.append('verification/completed', {
        operationId: operation.id,
        status: verification.status,
        summary: verification.summary,
        evidenceHash: hashContent(JSON.stringify(verification)),
      }, request.at)
      if (verification.status !== 'pass') {
        await this.append('operation/rejected', {
          operationId: operation.id,
          reason: verification.summary,
        }, request.at)
        const projection = await this.complete(verification.summary, request.at)
        return { projection, route, plan, preflight: preflightReport, reason: verification.summary }
      }

      await this.append('operation/accepted', {
        operationId: operation.id,
        reason: 'preflight and verification passed',
      }, request.at)
      const planPublisher = this.ctx.capabilities.get('skillPublisher')
      let publication: PublicationReceipt | undefined
      let publicationResult: PublicationResult | undefined
      if (planPublisher) {
        publicationResult = await planPublisher.publish({
          operation,
          plan,
          bundle: plan.bundle,
          preflight: preflightReport,
          sourceTraceIds: [trace.id],
          policyVersion: request.policyVersion ?? 'v2-policy-default',
          configVersion: request.configVersion ?? request.profile,
          channel: 'provisional',
        })
        await this.append('publication/completed', {
          operationId: operation.id,
          releaseId: publicationResult.releaseId,
          channel: publicationResult.receipt.channel,
        }, request.at)
      } else {
        publication = await this.ctx.capabilities.require('publisher').publish(operation)
        await this.append('publication/completed', {
          operationId: publication.operationId,
          releaseId: publication.releaseId,
          channel: publication.channel,
        }, request.at)
      }
      if (this.store) {
        await this.store.recordSkillExposure({
          runId: String(this.run.runId),
          skillId: String(operation.skillId),
          exposed: true,
          activated: true,
          source: 'v2-pipeline',
        })
      }
      const projection = await this.complete(`published ${String(operation.id)}`, request.at)
      return {
        projection,
        route,
        plan,
        preflight: preflightReport,
        ...(publication === undefined ? {} : { publication }),
        ...(publicationResult === undefined
          ? {}
          : {
              publicationReceipt: publicationResult.receipt,
              publicationReceiptPath: publicationResult.receiptPath,
            }),
      }
    } catch (error) {
      await this.fail(error, request.at)
      throw error
    }
  }
}
