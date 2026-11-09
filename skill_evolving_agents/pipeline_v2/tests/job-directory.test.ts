import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { admitObservations } from '../src/benchmark/admission.ts'
import {
  JobDirectoryError,
  buildBenchmarkObservation,
  readJobDirectory,
  readPairedJobDirectories,
} from '../src/benchmark/job-directory.ts'
import type {
  ReadPairedJobDirectoriesOptions,
  ReadPairedJobDirectoriesResult,
} from '../src/benchmark/job-directory.ts'

const FIXTURE_ROOT = fileURLToPath(new URL('./fixtures/job-directory/', import.meta.url))

function job(name: string): string {
  return join(FIXTURE_ROOT, name)
}

function pair(
  treatment: string,
  routerSelected: boolean,
): ReadPairedJobDirectoriesOptions {
  return {
    baseline: job('baseline-r1'),
    treatment: job(treatment),
    taskId: 'sanitized-report',
    trial: 1,
    domain: 'spreadsheet',
    routerSelected,
  }
}

function codes(result: ReadPairedJobDirectoriesResult): string[] {
  return result.exclusionReasons.map(reason => reason.code)
}

function observationOf(result: ReadPairedJobDirectoriesResult) {
  const observation = result.observation
  if (observation === undefined) {
    throw new Error(`expected an observation, got exclusions: ${JSON.stringify(result.exclusionReasons)}`)
  }
  return observation
}

describe('readJobDirectory', () => {
  it('reads identity, reward, usage, timing, cost, and provenance from a real-shaped baseline', async () => {
    const evidence = await readJobDirectory(job('baseline-r1'))

    expect(evidence.identity.taskName).toBe('sanitized-report')
    expect(evidence.identity.rolloutName).toBe('sanitized-report__0a1b2c3d')
    expect(evidence.identity.directoryName).toBe('sanitized-report__0a1b2c3d')
    expect(evidence.identity.timestamp).toBe('2026-11-09__15-10-17')
    expect(evidence.identity.artifactHash).toMatch(/^sha256:[0-9a-f]{64}$/)

    expect(evidence.rawSkillMode).toBe('no-skill')
    expect(evidence.skillMode).toBe('without-skill')
    expect(evidence.requestedSkillsDir).toBeNull()
    expect(evidence.effectiveSkillsDir).toBeNull()

    expect(evidence.reward.value).toBe(0.5)
    expect(evidence.reward.reported).toBe(0.5)
    expect(evidence.reward.complete).toBe(false)
    expect(evidence.passed).toBe(false)
    expect(evidence.partialReward).toBe(true)

    expect(evidence.toolCalls).toBe(241)
    expect(evidence.skillInvocations).toBe(0)
    expect(evidence.tokens.input).toBe(12000)
    expect(evidence.tokens.output).toBe(800)
    expect(evidence.tokens.cacheRead).toBe(4000)
    expect(evidence.tokens.total).toBe(12800)
    expect(evidence.costUsd).toBe(0.25)

    expect(evidence.latencyMs).toBe(900100)
    expect(evidence.efficiency.failure).toBe(true)
    expect(evidence.efficiency.violations.map(item => item.metric)).toEqual(
      expect.arrayContaining(['wall-seconds', 'tool-calls']),
    )

    expect(evidence.trajectory.verified).toBe(true)
    expect(evidence.trajectory.activated).toBe(false)
    expect(evidence.trajectory.activationMode).toBeNull()
    expect(evidence.exposure?.activated).toBe(false)
    expect(evidence.contamination).toEqual([])
    expect(evidence.infrastructureError).toBeNull()
    expect(evidence.errors).toEqual([])

    expect(evidence.provenance.kind).toBe('historical-job-directory')
    expect(evidence.provenance.source).toBe('skillsbench-job-directory')
    expect(evidence.provenance.searchFeedbackEligible).toBe(false)
  })

  it('falls back to result.json timing when timing.json is absent', async () => {
    const evidence = await readJobDirectory(job('treatment-valid-r1'))
    expect(evidence.latencyMs).toBe(300500)
    expect(evidence.efficiency.failure).toBe(false)
  })

  it('keeps a missing cost as null rather than zero', async () => {
    const evidence = await readJobDirectory(job('treatment-valid-r1'))
    expect(evidence.costUsd).toBeNull()
    expect(evidence.costUsd).not.toBe(0)
  })

  it('never infers activation from a supplied skills directory', async () => {
    const evidence = await readJobDirectory(job('treatment-supplied-only-r1'))

    expect(evidence.skillMode).toBe('with-skill')
    expect(evidence.requestedSkillsDir).not.toBeNull()
    expect(evidence.effectiveSkillsDir).not.toBeNull()
    expect(evidence.skillInvocations).toBe(3)
    expect(evidence.trajectory.activated).toBe(false)
    expect(evidence.exposure?.activated).toBe(false)
    expect(evidence.issues.map(item => item.code)).toEqual(
      expect.arrayContaining([
        'supplied-skills-dir-without-observed-activation',
        'skill-invocations-without-observed-activation',
      ]),
    )
  })

  it('rejects malformed result.json with a structured error', async () => {
    let failure: unknown
    try {
      await readJobDirectory(job('malformed-r1'))
    } catch (error) {
      failure = error
    }
    expect(failure).toBeInstanceOf(JobDirectoryError)
    if (failure instanceof JobDirectoryError) {
      expect(failure.code).toBe('malformed-json')
    }
  })
})

describe('readPairedJobDirectories', () => {
  it('admits a valid selected with-skill pair', async () => {
    const result = await readPairedJobDirectories(pair('treatment-valid-r1', true))

    expect(result.exclusionReasons).toEqual([])
    expect(result.baselineInherited).toBe(false)
    expect(result.provenance.searchFeedbackEligible).toBe(false)

    const observation = observationOf(result)
    expect(observation.taskId).toBe('sanitized-report')
    expect(observation.trial).toBe(1)
    expect(observation.domain).toBe('spreadsheet')
    expect(observation.routerSelected).toBe(true)

    expect(observation.baseline.exposure.skillMode).toBe('without-skill')
    expect(observation.baseline.exposure.activated).toBe(false)
    expect(observation.baseline.passed).toBe(false)
    expect(observation.baseline.costUsd).toBe(0.25)

    expect(observation.treatment.exposure.skillMode).toBe('with-skill')
    expect(observation.treatment.exposure.verified).toBe(true)
    expect(observation.treatment.exposure.activated).toBe(true)
    expect(observation.treatment.exposure.activationMode).toBe('read')
    expect(observation.treatment.passed).toBe(true)
    expect(observation.treatment.reward).toBe(1)
    expect(observation.treatment.toolCalls).toBe(118)
    expect(observation.treatment.latencyMs).toBe(300500)
    expect(observation.treatment.costUsd).toBeNull()
    expect(observation.treatment.contamination).toEqual([])
    expect(observation.treatment.infrastructureError).toBeNull()
  })

  it('rejects a selected treatment that is a copied baseline', async () => {
    const result = await readPairedJobDirectories(pair('treatment-copied-r1', true))

    expect(result.observation).toBeUndefined()
    expect(result.baselineInherited).toBe(false)
    expect(codes(result)).toContain('copied-baseline-treatment')
    expect(result.exclusionReasons[0]?.condition).toBe('pair')
  })

  it('rejects a selected treatment with no skill_mode', async () => {
    const result = await readPairedJobDirectories(pair('treatment-missing-mode-r1', true))

    expect(result.observation).toBeUndefined()
    expect(codes(result)).toContain('missing-skill-mode')
  })

  it('lets an explicit abstention inherit the baseline without marking it activated', async () => {
    const result = await readPairedJobDirectories(pair('treatment-copied-r1', false))

    expect(result.exclusionReasons).toEqual([])
    expect(result.baselineInherited).toBe(true)

    const observation = observationOf(result)
    expect(observation.routerSelected).toBe(false)
    expect(observation.treatment.exposure.skillMode).toBe('without-skill')
    expect(observation.treatment.exposure.activated).toBe(false)
    expect(observation.treatment.exposure.activationMode).toBeNull()
    expect(observation.treatment.passed).toBe(observation.baseline.passed)
    expect(observation.treatment.reward).toBe(observation.baseline.reward)
    expect(observation.treatment.toolCalls).toBe(observation.baseline.toolCalls)
    expect(observation.treatment.latencyMs).toBe(observation.baseline.latencyMs)
    expect(observation.treatment.efficiencyFailure).toBe(true)

    const admission = admitObservations([observation])
    expect(admission.rawPaired).toHaveLength(1)
    expect(admission.activated).toEqual([])
    expect(admission.abstained).toHaveLength(1)
    expect(admission.selective).toHaveLength(1)
    expect(admission.selective[0]?.source).toBe('baseline-abstention')
    expect(admission.selective[0]?.effective).toEqual(admission.selective[0]?.baseline)
  })

  it('rejects contradictory activation evidence for a selected cell', async () => {
    const result = await readPairedJobDirectories(pair('treatment-contradictory-r1', true))

    expect(result.observation).toBeUndefined()
    expect(codes(result)).toContain('contradictory-exposure-evidence')
    expect(codes(result)).toContain('selected-treatment-not-run-with-skill')
  })

  it('rejects a contaminated trial', async () => {
    const result = await readPairedJobDirectories(pair('treatment-contaminated-r1', false))

    expect(result.observation).toBeUndefined()
    expect(codes(result)).toContain('contaminated-observation')

    const evidence = await readJobDirectory(job('treatment-contaminated-r1'))
    expect(evidence.contamination).toContain('remote-answer-discovery')
    expect(evidence.contaminationMatches).toEqual([
      { event: 2, tool: 'execute', reason: 'remote-answer-discovery' },
    ])
    // A reported zero cost stays zero; only an absent cost becomes null.
    expect(evidence.costUsd).toBe(0)
  })

  it('preserves a partial reward without treating it as a pass', async () => {
    const result = await readPairedJobDirectories(pair('treatment-partial-r1', true))

    expect(result.exclusionReasons).toEqual([])
    const observation = observationOf(result)
    expect(observation.treatment.passed).toBe(false)
    expect(observation.treatment.reward).toBe(0.417)
    expect(observation.treatment.exposure.activated).toBe(true)

    const evidence = await readJobDirectory(job('treatment-partial-r1'))
    expect(evidence.partialReward).toBe(true)
    expect(evidence.passed).toBe(false)
  })

  it('rejects a selected treatment that only has a supplied skills dir', async () => {
    const result = await readPairedJobDirectories(pair('treatment-supplied-only-r1', true))

    expect(result.observation).toBeUndefined()
    expect(codes(result)).toContain('treatment-skill-not-activated')
  })

  it('turns malformed JSON into structured pair exclusions', async () => {
    const result = await readPairedJobDirectories(pair('malformed-r1', true))

    expect(result.observation).toBeUndefined()
    expect(codes(result)).toContain('malformed-job-directory')
    expect(result.baseline).not.toBeNull()
    expect(result.treatment).toBeNull()
  })
})

describe('buildBenchmarkObservation', () => {
  it('assembles a stable native observation directly from evidence', async () => {
    const baseline = await readJobDirectory(job('baseline-r1'))
    const treatment = await readJobDirectory(
      job('treatment-valid-r1/2026-11-09__15-10-18/sanitized-report__4d5e6f70'),
    )
    const observation = buildBenchmarkObservation({
      baseline,
      treatment,
      taskId: 'sanitized-report',
      trial: 2,
      domain: 'spreadsheet',
      routerSelected: true,
    })

    expect(observation.observationId).toBe(
      'job:sanitized-report:trial-2:sanitized-report__0a1b2c3d:sanitized-report__4d5e6f70',
    )
    expect(observation.trial).toBe(2)
    expect(observation.baseline.passed).toBe(false)
    expect(observation.baseline.reward).toBe(0.5)
    expect(observation.treatment.passed).toBe(true)
    expect(observation.treatment.reward).toBe(1)
  })
})
