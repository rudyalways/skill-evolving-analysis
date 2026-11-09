import { describe, expect, it } from 'vitest'
import { EventLog } from '../src/core/event-log.ts'
import { projectEvents } from '../src/core/projections.ts'

const AT = '2026-11-09T00:00:00.000Z'

function event(id: string, type: string, payload: Record<string, unknown>) {
  return { id, runId: 'run-1', type, version: 1, at: AT, payload }
}

function successfulSequence() {
  return [
    event('evt-1', 'run/started', { objective: 'improve', profile: 'default' }),
    event('evt-2', 'trace/ingested', { traceId: 'trace-1', source: 'fixture', turns: 2 }),
    event('evt-3', 'finding/detected', {
      findingId: 'finding-1',
      traceId: 'trace-1',
      detector: 'rules',
      confidence: 0.9,
      summary: 'retry loop',
    }),
    event('evt-4', 'candidate/recalled', { skillIds: ['skill-1', 'skill-2'] }),
    event('evt-5', 'candidate/selected', { skillId: 'skill-1', score: 0.8 }),
    event('evt-6', 'diagnosis/recorded', { findingId: 'finding-1', summary: 'missing guard' }),
    event('evt-7', 'goal/proposed', { goalHash: 'goal-1', operationCount: 1 }),
    event('evt-8', 'operation/planned', {
      operation: {
        id: 'op-1',
        kind: 'update',
        skillId: 'skill-1',
        findingId: 'finding-1',
        summary: 'add guard',
      },
    }),
    event('evt-9', 'resource/generated', {
      resource: {
        id: 'res-1',
        operationId: 'op-1',
        skillId: 'skill-1',
        kind: 'scripts',
        path: 'scripts/guard.py',
        status: 'generated',
      },
    }),
    event('evt-10', 'verification/completed', {
      operationId: 'op-1',
      status: 'pass',
      summary: 'checker passed',
    }),
    event('evt-11', 'operation/accepted', { operationId: 'op-1', reason: 'verified' }),
    event('evt-12', 'publication/completed', {
      operationId: 'op-1',
      releaseId: 'release-1',
      channel: 'provisional',
    }),
    event('evt-13', 'benchmark/completed', { taskId: 'task-1', passed: true, toolCalls: 12 }),
    event('evt-14', 'feedback/recorded', {
      taskId: 'task-1',
      skillId: 'skill-1',
      adjustment: 0.1,
    }),
    event('evt-15', 'run/completed', { summary: 'done' }),
  ]
}

describe('deterministic projections', () => {
  it('folds a complete sequence into a stable run view', () => {
    const log = new EventLog()
    for (const value of successfulSequence()) log.append(value)
    const projection = projectEvents(log.events)
    expect(projection.runId).toBe('run-1')
    expect(projection.status).toBe('completed')
    expect(projection.startedAt).toBe(AT)
    expect(projection.endedAt).toBe(AT)
    expect(projection.eventCount).toBe(15)
    expect(projection.funnel.tracesIngested).toBe(1)
    expect(projection.funnel.findingsDetected).toBe(1)
    expect(projection.funnel.candidatesRecalled).toBe(2)
    expect(projection.funnel.candidatesSelected).toBe(1)
    expect(projection.funnel.operationsPlanned).toBe(1)
    expect(projection.funnel.verificationsPassed).toBe(1)
    expect(projection.funnel.operationsAccepted).toBe(1)
    expect(projection.funnel.publicationsCompleted).toBe(1)
    expect(projection.operations['op-1']?.status).toBe('published')
    expect(projection.resources['res-1']?.path).toBe('scripts/guard.py')
    expect(projection.resourceUse.byKind.scripts).toBe(1)
    expect(projection.failures).toEqual([])
  })

  it('produces identical projection bytes for the same event sequence', () => {
    const first = new EventLog()
    const second = new EventLog()
    for (const value of successfulSequence()) {
      first.append(value)
      second.append(value)
    }
    expect(JSON.stringify(projectEvents(first.events))).toBe(
      JSON.stringify(projectEvents(second.events)),
    )
  })

  it('records verification and rejection failures in event order', () => {
    const log = new EventLog()
    log.append(event('evt-1', 'run/started', { objective: 'improve', profile: 'default' }))
    log.append(event('evt-2', 'operation/planned', {
      operation: {
        id: 'op-1',
        kind: 'update',
        skillId: 'skill-1',
        findingId: 'finding-1',
        summary: 'change',
      },
    }))
    log.append(event('evt-3', 'verification/completed', {
      operationId: 'op-1',
      status: 'efficiency_failure',
      summary: 'tool-call budget exceeded',
    }))
    log.append(event('evt-4', 'operation/rejected', {
      operationId: 'op-1',
      reason: 'efficiency failure',
    }))
    log.append(event('evt-5', 'run/failed', { reason: 'no accepted operation' }))
    const projection = projectEvents(log.events)
    expect(projection.status).toBe('failed')
    expect(projection.funnel.efficiencyFailures).toBe(1)
    expect(projection.failures.map((failure) => failure.code)).toEqual([
      'efficiency-failure',
      'operation-rejected',
      'run-failed',
    ])
  })
})
