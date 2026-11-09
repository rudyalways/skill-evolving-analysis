import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import type {
  BenchmarkObservation,
  ConditionObservation,
  SkillExposureAudit,
} from '../src/benchmark/admission.ts'
import { operationId } from '../src/contracts/ids.ts'
import { canonicalOptions } from '../src/cli/args.ts'
import {
  EXPERIMENT_REPORT_VERSION,
  InvalidExperimentReportError,
  buildExperimentReport,
  renderMarkdownReport,
  serializeExperimentReport,
  stableStringify,
  writeJsonReport,
} from '../src/cli/report.ts'
import type { ExperimentReportInput } from '../src/cli/report.ts'
import { hashContent } from '../src/store/study-store.ts'

const WITHOUT_SKILL: SkillExposureAudit = {
  skillMode: 'without-skill',
  verified: false,
  activated: false,
  activationMode: null,
}

const WITH_SKILL: SkillExposureAudit = {
  skillMode: 'with-skill',
  verified: true,
  activated: true,
  activationMode: 'read',
}

const temporaryDirectories: string[] = []

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })),
  )
})

interface ConditionOptions {
  readonly passed: boolean
  readonly toolCalls?: number
  readonly latencyMs?: number
  readonly costUsd?: number | null
  readonly exposure: SkillExposureAudit
  readonly efficiencyFailure?: boolean
  readonly contamination?: readonly string[]
  readonly infrastructureError?: string | null
}

function condition(options: ConditionOptions): ConditionObservation {
  return {
    passed: options.passed,
    toolCalls: options.toolCalls ?? 3,
    latencyMs: options.latencyMs ?? 1000,
    costUsd: options.costUsd ?? null,
    efficiencyFailure: options.efficiencyFailure ?? false,
    exposure: options.exposure,
    contamination: options.contamination ?? [],
    infrastructureError: options.infrastructureError ?? null,
  }
}

interface ObservationOptions {
  readonly observationId: string
  readonly taskId: string
  readonly trial?: number
  readonly domain?: string
  readonly selected: boolean
  readonly baselinePassed: boolean
  readonly treatmentPassed: boolean
  readonly baselineCostUsd?: number | null
  readonly treatmentCostUsd?: number | null
  readonly contamination?: readonly string[]
}

function observation(options: ObservationOptions): BenchmarkObservation {
  return {
    observationId: options.observationId,
    taskId: options.taskId,
    trial: options.trial ?? 0,
    domain: options.domain ?? 'finance',
    routerSelected: options.selected,
    baseline: condition({
      passed: options.baselinePassed,
      costUsd: options.baselineCostUsd ?? null,
      exposure: WITHOUT_SKILL,
      contamination: options.contamination ?? [],
    }),
    treatment: condition({
      passed: options.treatmentPassed,
      costUsd: options.treatmentCostUsd ?? null,
      exposure: options.selected ? WITH_SKILL : WITHOUT_SKILL,
      contamination: options.contamination ?? [],
    }),
  }
}

function baseOptions() {
  return canonicalOptions({
    traceFile: 'trace.jsonl',
    stage: 'validation',
    runId: 'run-1',
    seed: 17,
    publishRoot: 'publish',
    router: 'hybrid',
    embedding: 'qwen-http',
    embeddingUrl: 'http://127.0.0.1:9000/embed',
  })
}

function fullInput(): ExperimentReportInput {
  return {
    runId: 'run-1',
    stage: 'validation',
    startedAt: '2026-01-01T00:00:00.000Z',
    finishedAt: '2026-01-01T00:05:00.000Z',
    options: baseOptions(),
    memberships: [
      { taskId: 'task-2', stage: 'validation', contentHash: 'sha256:task-2' },
      { taskId: 'task-1', stage: 'validation', contentHash: 'sha256:task-1' },
    ],
    tasks: [
      { taskId: 'task-2', domain: 'accounting', groupId: 'group-b' },
      { taskId: 'task-1', domain: 'finance', groupId: 'group-a' },
    ],
    observations: [
      observation({
        observationId: 'obs-1',
        taskId: 'task-1',
        selected: true,
        baselinePassed: false,
        treatmentPassed: true,
      }),
      observation({
        observationId: 'obs-2',
        taskId: 'task-2',
        selected: false,
        baselinePassed: true,
        treatmentPassed: false,
      }),
    ],
    candidateScores: [
      { taskId: 'task-2', skillId: 'skill-b', score: 0.4, reason: 'lower' },
      { taskId: 'task-1', skillId: 'skill-b', score: 0.5 },
      { taskId: 'task-1', skillId: 'skill-a', score: 0.9, reason: 'best' },
    ],
    resources: [
      { kind: 'scripts', path: 'scripts/guard.py', status: 'generated' },
      { kind: 'references', path: 'references/guide.md', status: 'used', contentHash: 'sha256:guide' },
    ],
    receipts: [
      { operationId: operationId('op-1'), releaseId: 'rel-1', channel: 'provisional' },
    ],
    verification: {
      status: 'pass',
      summary: 'verification passed',
      evidenceHash: 'sha256:evidence',
      operationId: 'op-1',
    },
    defects: [
      { code: 'D-2', message: 'second defect', severity: 'warning' },
      { code: 'D-1', message: 'first defect', severity: 'error', taskId: 'task-1' },
    ],
    holdoutReady: false,
    limitations: ['Only one seed was run.'],
  }
}

describe('experiment report', () => {
  it('builds the four honest populations from admitted observations', () => {
    const report = buildExperimentReport(fullInput())

    expect(report.schemaVersion).toBe(EXPERIMENT_REPORT_VERSION)
    expect(report.runId).toBe('run-1')
    expect(report.stage).toBe('validation')
    expect(report.admission).toMatchObject({
      submitted: 2,
      rawPaired: 2,
      activated: 1,
      abstained: 1,
      selectiveCells: 2,
      excluded: 0,
    })

    expect(report.baseline.cells).toBe(2)
    expect(report.baseline.passes).toBe(1)
    expect(report.baseline.passRate).toBe(0.5)
    expect(report.treatment.cells).toBe(2)
    expect(report.treatment.passes).toBe(1)
    expect(report.treatment.passRate).toBe(0.5)

    expect(report.policy.cells).toBe(2)
    expect(report.policy.selectedCells).toBe(1)
    expect(report.policy.abstainedCells).toBe(1)
    expect(report.policy.inheritedBaselineCells).toBe(1)
    expect(report.policy.policyPasses).toBe(2)
    expect(report.policy.policyPassRate).toBe(1)
    expect(report.policy.absoluteLift).toBe(0.5)
    expect(report.policy.lifts).toBe(1)
    expect(report.policy.regressions).toBe(0)

    expect(report.activatedEffect.scope).toBe('verified-activation')
    expect(report.activatedEffect.cells).toBe(1)
    expect(report.activatedEffect.baselinePassRate).toBe(0)
    expect(report.activatedEffect.treatmentPassRate).toBe(1)
    expect(report.activatedEffect.absoluteLift).toBe(1)
    expect(report.activatedEffect.exactSignTestPValue).toBe(1)
  })

  it('derives deterministic membership hashes and sorted task rows', () => {
    const report = buildExperimentReport(fullInput())

    expect(report.membership.validation.taskIds).toEqual(['task-1', 'task-2'])
    expect(report.membership.validation.hash).toBe(hashContent('validation\ntask-1\ntask-2'))
    expect(report.membership.validation.contentHashes).toEqual({
      'task-1': 'sha256:task-1',
      'task-2': 'sha256:task-2',
    })
    expect(report.membership.train.hash).toBeNull()
    expect(report.membership.holdout.hash).toBeNull()
    expect(report.membership.combinedHash).not.toBeNull()

    expect(report.tasks.total).toBe(2)
    expect(report.tasks.rows.map((task) => task.taskId)).toEqual(['task-1', 'task-2'])
    expect(report.tasks.byStage).toEqual({ train: 0, validation: 2 })
    expect(report.tasks.byDomain).toEqual({ accounting: 1, finance: 1 })
    expect(report.tasks.rows[0]?.selectedCells).toBe(1)
    expect(report.tasks.rows[1]?.abstainedCells).toBe(1)
  })

  it('uses a precomputed cohort membership hash when supplied', () => {
    const report = buildExperimentReport({
      ...fullInput(),
      membershipHashes: { validation: 'sha256:cohort-membership' },
    })
    expect(report.membership.validation.hash).toBe('sha256:cohort-membership')
    expect(report.membership.validation.taskIds).toEqual(['task-1', 'task-2'])
  })

  it('sorts routing, candidates, resources, receipts, and defects deterministically', () => {
    const report = buildExperimentReport(fullInput())

    expect(report.routing.selectedCells).toBe(1)
    expect(report.routing.abstainedCells).toBe(1)
    expect(report.routing.selectionRate).toBe(0.5)
    expect(report.routing.selectedTaskIds).toEqual(['task-1'])
    expect(report.routing.abstainedTaskIds).toEqual(['task-2'])

    expect(report.candidateScores.map((candidate) => `${candidate.taskId}:${candidate.skillId}`))
      .toEqual(['task-1:skill-a', 'task-1:skill-b', 'task-2:skill-b'])
    expect(report.resources.map((resource) => resource.path))
      .toEqual(['references/guide.md', 'scripts/guard.py'])
    expect(report.receipts.map((receipt) => receipt.releaseId)).toEqual(['rel-1'])
    expect(report.defects.map((defect) => defect.code)).toEqual(['D-1', 'D-2'])
  })

  it('keeps missing cost null, labels it unmeasured, and never prints $0', () => {
    const report = buildExperimentReport(fullInput())

    expect(report.cost.status).toBe('unmeasured')
    expect(report.baseline.costUsd).toBeNull()
    expect(report.treatment.costUsd).toBeNull()
    expect(report.cost.baselineUsd).toBeNull()
    expect(report.cost.treatmentUsd).toBeNull()
    expect(report.cost.totalUsd).toBeNull()
    expect(report.cost.measuredConditions).toBe(0)
    expect(report.cost.unmeasuredConditions).toBe(4)
    expect(report.cost.note).toContain('unmeasured')

    const markdown = renderMarkdownReport(report)
    expect(markdown).toContain('Cost status: **unmeasured**')
    expect(markdown).toContain('Complete total | unmeasured')
    expect(markdown).not.toContain('$0')
    expect(markdown).not.toMatch(/improved/i)
  })

  it('reports a partially measured cost without claiming a complete total', () => {
    const input: ExperimentReportInput = {
      ...fullInput(),
      observations: [
        observation({
          observationId: 'obs-1',
          taskId: 'task-1',
          selected: true,
          baselinePassed: false,
          treatmentPassed: true,
          baselineCostUsd: 0.1,
          treatmentCostUsd: null,
        }),
        observation({
          observationId: 'obs-2',
          taskId: 'task-2',
          selected: false,
          baselinePassed: true,
          treatmentPassed: false,
          baselineCostUsd: 0.2,
          treatmentCostUsd: 0.3,
        }),
      ],
    }
    const report = buildExperimentReport(input)

    expect(report.cost.status).toBe('partial')
    expect(report.cost.measuredConditions).toBe(3)
    expect(report.cost.unmeasuredConditions).toBe(1)
    expect(report.cost.baselineUsd).toBe(0.3)
    expect(report.cost.treatmentUsd).toBe(0.3)
    expect(report.cost.totalUsd).toBeNull()
    expect(report.cost.note).toContain('partial')
    expect(report.cost.note).toContain('rather than treated as zero')

    const markdown = renderMarkdownReport(report)
    expect(markdown).toContain('Cost status: **partial**')
    expect(markdown).toContain('Unmeasured conditions | 1')
  })

  it('reports a fully measured cost only when every condition has cost', () => {
    const input: ExperimentReportInput = {
      ...fullInput(),
      observations: [
        observation({
          observationId: 'obs-1',
          taskId: 'task-1',
          selected: true,
          baselinePassed: false,
          treatmentPassed: true,
          baselineCostUsd: 0.1,
          treatmentCostUsd: 0.2,
        }),
        observation({
          observationId: 'obs-2',
          taskId: 'task-2',
          selected: false,
          baselinePassed: true,
          treatmentPassed: false,
          baselineCostUsd: 0.3,
          treatmentCostUsd: 0.4,
        }),
      ],
    }
    const report = buildExperimentReport(input)

    expect(report.cost.status).toBe('measured')
    expect(report.cost.baselineUsd).toBe(0.4)
    expect(report.cost.treatmentUsd).toBe(0.6)
    expect(report.cost.totalUsd).toBe(1)
    expect(report.cost.note).toContain('measured')
  })

  it('does not invent metrics for an empty cohort', () => {
    const report = buildExperimentReport({
      ...fullInput(),
      observations: [],
      tasks: [],
      memberships: [],
      candidateScores: [],
      resources: [],
      receipts: [],
      verification: null,
      defects: [],
    })

    expect(report.baseline.cells).toBe(0)
    expect(report.baseline.passRate).toBeNull()
    expect(report.baseline.toolCalls).toBeNull()
    expect(report.baseline.latencyMs).toBeNull()
    expect(report.treatment.passRate).toBeNull()
    expect(report.policy.policyPassRate).toBeNull()
    expect(report.policy.absoluteLift).toBeNull()
    expect(report.activatedEffect.absoluteLift).toBeNull()
    expect(report.activatedEffect.exactSignTestPValue).toBeNull()
    expect(report.routing.selectionRate).toBeNull()
    expect(report.latency.baselineMs).toBeNull()
    expect(report.latency.totalMs).toBeNull()
    expect(report.toolCalls.baselineCalls).toBeNull()
    expect(report.toolCalls.totalCalls).toBeNull()
    expect(report.cost.status).toBe('unmeasured')
    expect(report.cost.totalUsd).toBeNull()
    expect(report.membership.combinedHash).toBeNull()
    expect(report.limitations.join('\n')).toContain('No paired observations')

    const markdown = renderMarkdownReport(report)
    expect(markdown).toContain('| Baseline pass rate | unmeasured |')
    expect(markdown).toContain('No preflight result was supplied')
  })

  it('renders preflight, verification, receipts, defects, and holdout conservatively', () => {
    const report = buildExperimentReport({
      ...fullInput(),
      preflight: {
        verdict: 'accept',
        checks: [],
        metrics: {
          files: 2,
          bytes: 100,
          resources: 2,
          scripts: 1,
          fixtures: 0,
          skillTokens: 20,
          disclosedTokens: 10,
          totalTokens: 30,
          promptExpansionRatio: 3,
          estimatedToolCalls: 2,
          estimatedWallMs: 1000,
        },
        rejectReasons: [],
        repairReasons: [],
      },
    })

    expect(report.preflight?.verdict).toBe('accept')
    expect(report.verification?.status).toBe('pass')
    expect(report.holdoutReady).toBe(false)

    const markdown = renderMarkdownReport(report)
    expect(markdown).toContain('# Experiment report: run-1')
    expect(markdown).toContain('Stage: validation')
    expect(markdown).toContain('Holdout ready: no')
    expect(markdown).toContain('## Preflight')
    expect(markdown).toContain('Verdict: accept')
    expect(markdown).toContain('Status: pass')
    expect(markdown).toContain('rel-1')
    expect(markdown).toContain('D-1')
    expect(markdown).toContain('Only one seed was run.')
    expect(markdown).toContain('not a holdout claim')
  })

  it('rejects structurally invalid input with structured issues', () => {
    try {
      buildExperimentReport({
        ...fullInput(),
        observations: [
          observation({
            observationId: 'obs-1',
            taskId: 'task-1',
            selected: true,
            baselinePassed: false,
            treatmentPassed: true,
            baselineCostUsd: -1,
          }),
        ],
      })
      throw new Error('expected InvalidExperimentReportError')
    } catch (error) {
      expect(error).toBeInstanceOf(InvalidExperimentReportError)
      const issues = (error as InvalidExperimentReportError).issues
      expect(issues.some((item) => item.path.endsWith('.costUsd'))).toBe(true)
    }
  })

  it('rejects a task that appears in two conflicting membership stages', () => {
    expect(() => buildExperimentReport({
      ...fullInput(),
      memberships: [
        { taskId: 'task-1', stage: 'train' },
        { taskId: 'task-1', stage: 'validation' },
      ],
    })).toThrow(InvalidExperimentReportError)
  })

  it('serializes the same report to identical canonical JSON bytes', () => {
    const original = fullInput()
    const first = buildExperimentReport(original)
    const reorderedInput: ExperimentReportInput = {
      limitations: original.limitations ?? [],
      holdoutReady: false,
      options: baseOptions(),
      runId: 'run-1',
      finishedAt: '2026-01-01T00:05:00.000Z',
      startedAt: '2026-01-01T00:00:00.000Z',
      stage: 'validation',
      observations: original.observations ?? [],
      tasks: original.tasks ?? [],
      memberships: original.memberships ?? [],
      candidateScores: original.candidateScores ?? [],
      resources: original.resources ?? [],
      receipts: original.receipts ?? [],
      verification: original.verification ?? null,
      defects: original.defects ?? [],
    }
    const second = buildExperimentReport(reorderedInput)

    expect(serializeExperimentReport(first)).toBe(serializeExperimentReport(second))
    expect(serializeExperimentReport(first).endsWith('\n')).toBe(true)
    expect(stableStringify({ b: 1, a: { d: 2, c: 3 } }))
      .toBe(stableStringify({ a: { c: 3, d: 2 }, b: 1 }))
  })

  it('writes canonical JSON to disk', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'experiment-report-'))
    temporaryDirectories.push(directory)
    const path = join(directory, 'report.json')
    const report = buildExperimentReport(fullInput())

    await writeJsonReport(report, path)
    const first = await readFile(path, 'utf8')
    await writeJsonReport(report, path)
    const second = await readFile(path, 'utf8')

    expect(first).toBe(serializeExperimentReport(report))
    expect(second).toBe(first)
    const parsed = JSON.parse(first) as { runId: string }
    expect(parsed.runId).toBe('run-1')
    expect(Object.keys(parsed)).toEqual([...Object.keys(parsed)].sort())
  })
})
