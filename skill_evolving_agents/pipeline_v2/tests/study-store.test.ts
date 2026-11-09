import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

import { EVENT_VERSION } from '../src/contracts/events.ts'
import type { BenchmarkObservationInput } from '../src/store/study-store.ts'
import {
  HoldoutFeedbackRejectedError,
  MembershipConflictError,
  MixedRunBatchError,
  STUDY_STORE_SCHEMA_VERSION,
  StageLeakageError,
  UnsupportedStoreSchemaVersionError,
  hashContent,
  openStudyStore,
} from '../src/store/study-store.ts'

const AT = '2026-11-09T00:00:00.000Z'
const OWNED_DIRECTORIES: string[] = []

async function temporaryStore(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), 'pipeline-v2-study-store-'))
  OWNED_DIRECTORIES.push(directory)
  return directory
}

afterEach(async () => {
  const directories = OWNED_DIRECTORIES.splice(0)
  await Promise.all(
    directories.map(directory => rm(directory, { recursive: true, force: true })),
  )
})

function logPath(directory: string): string {
  return join(directory, 'study.jsonl')
}

function lineCount(text: string): number {
  const trimmed = text.trim()
  return trimmed.length === 0 ? 0 : trimmed.split('\n').length
}

async function durableLineCount(directory: string): Promise<number> {
  return lineCount(await readFile(logPath(directory), 'utf8'))
}

function started(id = 'evt-1', runId = 'run-1') {
  return {
    id,
    runId,
    type: 'run/started',
    version: EVENT_VERSION,
    at: AT,
    payload: { objective: 'durable study', profile: 'default' },
  }
}

function trace(id = 'evt-2', runId = 'run-1') {
  return {
    id,
    runId,
    type: 'trace/ingested',
    version: EVENT_VERSION,
    at: AT,
    payload: { traceId: 'trace-1', source: 'fixture', turns: 2 },
  }
}

function finding(id = 'evt-3', runId = 'run-1') {
  return {
    id,
    runId,
    type: 'finding/detected',
    version: EVENT_VERSION,
    at: AT,
    payload: {
      findingId: 'finding-1',
      traceId: 'trace-1',
      detector: 'rules',
      confidence: 0.9,
      summary: 'retry loop',
    },
  }
}

function operationPlanned(id = 'evt-4', runId = 'run-1') {
  return {
    id,
    runId,
    type: 'operation/planned',
    version: EVENT_VERSION,
    at: AT,
    payload: {
      operation: {
        id: 'op-1',
        kind: 'update',
        skillId: 'skill-1',
        findingId: 'finding-1',
        summary: 'tighten the retry guard',
      },
    },
  }
}

function verification(id = 'evt-5', runId = 'run-1') {
  return {
    id,
    runId,
    type: 'verification/completed',
    version: EVENT_VERSION,
    at: AT,
    payload: { operationId: 'op-1', status: 'pass', summary: 'checker passed' },
  }
}

function completed(id = 'evt-6', runId = 'run-1') {
  return {
    id,
    runId,
    type: 'run/completed',
    version: EVENT_VERSION,
    at: AT,
    payload: { summary: 'done' },
  }
}

function observation(overrides: Partial<BenchmarkObservationInput> = {}): BenchmarkObservationInput {
  return {
    runId: 'run-1',
    stage: 'validation',
    taskId: 'task-1',
    groupId: 'group-1',
    domain: 'domain-1',
    baseline: {
      passed: false,
      toolCalls: 4,
      latencyMs: 10,
      costUsd: 0.01,
      failures: 1,
    },
    treatment: {
      passed: true,
      skillId: 'skill-1',
      toolCalls: 3,
      latencyMs: 8,
      costUsd: 0.008,
      failures: 0,
    },
    efficiencyFailure: false,
    ...overrides,
  }
}

describe('durable study store', () => {
  it('restarts and replays the same events, records, and projection', async () => {
    const directory = await temporaryStore()
    const first = await openStudyStore(directory, { clock: () => AT })
    await first.appendEvents([started(), trace(), finding()])
    await first.appendEvent(completed('evt-4'))
    await first.recordTraceIdentity({
      runId: 'run-1',
      traceId: 'trace-1',
      source: 'fixture',
      turns: 2,
      contentHash: hashContent('trace body'),
    })
    await first.recordRouterCandidates({
      runId: 'run-1',
      traceId: 'trace-1',
      candidates: [
        { skillId: 'skill-1', score: 0.9, reason: 'best match' },
        { skillId: 'skill-2', score: 0.4 },
      ],
    })
    await first.recordMembership({ taskId: 'task-1', groupId: 'group-1', stage: 'validation' })
    await first.recordBenchmarkObservation(observation())
    await first.recordPolicyVersion({ version: 'policy-v1', payload: { targetPassRate: 0.6 } })
    await first.recordConfigVersion({ version: 'config-v1', payload: { maxToolCalls: 12 } })
    await first.recordSkillExposure({
      runId: 'run-1',
      skillId: 'skill-1',
      exposed: true,
      activated: true,
    })
    await first.recordFeedback({
      taskId: 'task-1',
      skillId: 'skill-1',
      adjustment: 0.25,
      stage: 'validation',
      runId: 'run-1',
    })

    const projectionBefore = first.replay('run-1')
    const projectionJson = JSON.stringify(projectionBefore)
    const stateBefore = first.getState()
    const runsBefore = first.listRuns()
    expect(projectionBefore.status).toBe('completed')
    expect(stateBefore.runs['run-1']?.eventCount).toBe(4)
    expect(stateBefore.traces['run-1::trace-1']?.contentHash).toBe(hashContent('trace body'))
    expect(stateBefore.findings['finding-1']?.summary).toBe('retry loop')
    expect(stateBefore.routerCandidates).toHaveLength(1)
    expect(stateBefore.memberships['task-1']?.stage).toBe('validation')
    expect(stateBefore.benchmarks['validation:task-1']?.baseline.passed).toBe(false)
    expect(stateBefore.feedback).toHaveLength(1)
    expect(stateBefore.policyVersions['policy-v1']?.contentHash).toBeDefined()
    expect(stateBefore.configVersions['config-v1']?.contentHash).toBeDefined()
    expect(stateBefore.skillExposures['run-1:skill-1']?.activated).toBe(true)
    expect(stateBefore.usage['run-1']).toMatchObject({
      observations: 1,
      baselineToolCalls: 4,
      treatmentToolCalls: 3,
      failures: 1,
      efficiencyFailures: 0,
    })
    expect(await durableLineCount(directory)).toBe(12)
    await first.close()

    const second = await openStudyStore(directory, { clock: () => AT })
    expect(second.schemaVersion).toBe(STUDY_STORE_SCHEMA_VERSION)
    expect(second.migratedFrom).toBeUndefined()
    expect(second.getState()).toEqual(stateBefore)
    expect(second.listRuns()).toEqual(runsBefore)
    expect(JSON.stringify(second.replay('run-1'))).toBe(projectionJson)
    const report = await second.verifyIntegrity()
    expect(report).toMatchObject({
      ok: true,
      schemaVersion: STUDY_STORE_SCHEMA_VERSION,
      eventCount: 4,
      recordCount: 8,
      snapshotMatches: true,
    })
    expect(report.runIds).toEqual(['run-1'])
    await second.close()
  })

  it('treats identical duplicate event writes as idempotent and rejects conflicting ids', async () => {
    const directory = await temporaryStore()
    const store = await openStudyStore(directory, { clock: () => AT })
    const first = started()
    await store.appendEvent(first)
    await store.appendEvent(first)
    await store.appendEvents([first, first])
    expect(store.getRun('run-1')?.eventCount).toBe(1)
    expect(await durableLineCount(directory)).toBe(1)

    await expect(
      store.appendEvent({
        ...first,
        payload: { objective: 'different objective', profile: 'default' },
      }),
    ).rejects.toMatchObject({ code: 'duplicate-event' })
    expect(await durableLineCount(directory)).toBe(1)
    await store.close()

    const reopened = await openStudyStore(directory, { clock: () => AT })
    await reopened.appendEvent(first)
    expect(reopened.getRun('run-1')?.eventCount).toBe(1)
    expect(await durableLineCount(directory)).toBe(1)
    await reopened.close()
  })

  it('rejects mixed-run batches and rolls back invalid batches', async () => {
    const directory = await temporaryStore()
    const store = await openStudyStore(directory, { clock: () => AT })
    await store.appendEvent(started())

    await expect(
      store.appendEvents([started('evt-2', 'run-2'), trace('evt-3', 'run-1')]),
    ).rejects.toBeInstanceOf(MixedRunBatchError)
    expect(store.listRuns().map(run => run.runId)).toEqual(['run-1'])

    await expect(
      store.appendEvents([started('evt-4', 'run-1')]),
    ).rejects.toMatchObject({ code: 'invalid-transition' })
    expect(store.getRun('run-1')?.eventCount).toBe(1)
    expect(await durableLineCount(directory)).toBe(1)

    await store.appendEvent(started('evt-5', 'run-2'))
    expect(store.listRuns()).toHaveLength(2)
    await store.close()
  })

  it('migrates a v1 event-only fixture to the current schema', async () => {
    const directory = await temporaryStore()
    await writeFile(
      join(directory, 'manifest.json'),
      JSON.stringify({ schemaVersion: 1, backend: 'jsonl' }),
      'utf8',
    )
    await writeFile(
      join(directory, 'events.jsonl'),
      `${[started(), trace()].map(event => JSON.stringify(event)).join('\n')}\n`,
      'utf8',
    )

    const store = await openStudyStore(directory, { clock: () => AT })
    expect(store.schemaVersion).toBe(STUDY_STORE_SCHEMA_VERSION)
    expect(store.migratedFrom).toBe(1)
    expect(store.createdAt).toBe(AT)
    expect(store.getRun('run-1')?.eventCount).toBe(2)

    const manifest: unknown = JSON.parse(
      await readFile(join(directory, 'manifest.json'), 'utf8'),
    )
    expect(manifest).toMatchObject({
      schemaVersion: STUDY_STORE_SCHEMA_VERSION,
      backend: 'jsonl-snapshot',
    })
    expect(await durableLineCount(directory)).toBe(2)
    const report = await store.verifyIntegrity()
    expect(report.ok).toBe(true)
    await store.close()

    const legacy = await readFile(join(directory, 'events.jsonl'), 'utf8')
    expect(lineCount(legacy)).toBe(2)
  })

  it('rejects an unsupported future store schema version', async () => {
    const directory = await temporaryStore()
    await writeFile(
      join(directory, 'manifest.json'),
      JSON.stringify({ schemaVersion: 99, backend: 'jsonl-snapshot', createdAt: AT }),
      'utf8',
    )
    await expect(openStudyStore(directory, { clock: () => AT })).rejects.toBeInstanceOf(
      UnsupportedStoreSchemaVersionError,
    )
  })

  it('seals holdout feedback from search history and rejects it before persistence', async () => {
    const directory = await temporaryStore()
    const store = await openStudyStore(directory, { clock: () => AT })
    await store.appendEvent(started())
    await store.recordMembership({
      taskId: 'task-holdout',
      groupId: 'group-holdout',
      stage: 'holdout',
    })
    const linesBefore = await durableLineCount(directory)

    await expect(
      store.recordFeedback({
        taskId: 'task-holdout',
        skillId: 'skill-1',
        adjustment: 0.5,
        stage: 'holdout',
      }),
    ).rejects.toBeInstanceOf(HoldoutFeedbackRejectedError)
    await expect(
      store.recordFeedback({
        taskId: 'task-holdout',
        skillId: 'skill-1',
        adjustment: 0.5,
        stage: 'train',
      }),
    ).rejects.toMatchObject({ code: 'holdout-feedback-rejected' })
    await expect(
      store.recordFeedback({
        taskId: 'task-holdout',
        skillId: 'skill-1',
        adjustment: 0.5,
        stage: 'validation',
      }),
    ).rejects.toMatchObject({ code: 'holdout-feedback-rejected' })

    expect(await durableLineCount(directory)).toBe(linesBefore)
    expect(store.searchHistory()).toHaveLength(0)
    expect(store.getState().feedback).toHaveLength(0)

    await store.recordMembership({
      taskId: 'task-validation',
      groupId: 'group-validation',
      stage: 'validation',
    })
    await store.recordFeedback({
      taskId: 'task-validation',
      skillId: 'skill-1',
      adjustment: 0.2,
      stage: 'validation',
    })
    expect(store.searchHistory().map(row => row.taskId)).toEqual(['task-validation'])
    await store.close()

    const reopened = await openStudyStore(directory, { clock: () => AT })
    expect(reopened.searchHistory().map(row => row.taskId)).toEqual(['task-validation'])
    await reopened.close()
  })

  it('rejects conflicting membership, stage leakage, and conflicting observations', async () => {
    const directory = await temporaryStore()
    const store = await openStudyStore(directory, { clock: () => AT })
    await store.appendEvent(started())
    await store.recordMembership({ taskId: 'task-1', groupId: 'group-1', stage: 'validation' })

    await expect(
      store.recordMembership({ taskId: 'task-1', stage: 'holdout' }),
    ).rejects.toBeInstanceOf(MembershipConflictError)
    await expect(
      store.recordMembership({ taskId: 'task-2', groupId: 'group-1', stage: 'holdout' }),
    ).rejects.toBeInstanceOf(StageLeakageError)

    await store.recordBenchmarkObservation(observation())
    await store.recordBenchmarkObservation(observation())
    expect(Object.keys(store.getState().benchmarks)).toEqual(['validation:task-1'])
    await expect(
      store.recordBenchmarkObservation(
        observation({ treatment: { passed: false, toolCalls: 9 } }),
      ),
    ).rejects.toMatchObject({ code: 'duplicate-benchmark-observation' })
    await store.close()
  })

  it('replays byte-identical projections across calls and store instances', async () => {
    const directory = await temporaryStore()
    const store = await openStudyStore(directory, { clock: () => AT })
    await store.appendEvents([
      started(),
      trace(),
      finding(),
      operationPlanned(),
      verification(),
      completed(),
    ])

    const first = JSON.stringify(store.replay('run-1'))
    const second = JSON.stringify(store.replay('run-1'))
    expect(second).toBe(first)
    const run = store.getRun('run-1')
    expect(run?.projection.status).toBe('completed')
    expect(run?.projection.funnel.verificationsPassed).toBe(1)
    expect(run?.projection.operations['op-1']?.status).toBe('verified_pass')
    await store.close()

    const reopened = await openStudyStore(directory, { clock: () => AT })
    expect(JSON.stringify(reopened.replay('run-1'))).toBe(first)
    await reopened.close()
  })
})
