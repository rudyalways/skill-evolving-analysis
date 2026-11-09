import { describe, expect, it } from 'vitest'

import {
  ABSTENTION_FAMILY,
  auditCohort,
  buildCohort,
  CohortInfeasibleError,
  CohortLeakageError,
  CohortMetadataError,
  isAbstentionCandidate,
  membershipHash,
  MAX_VALIDATION_TASKS,
  MIN_VALIDATION_DOMAINS,
} from '../src/validation/cohort.ts'
import type { BuildCohortRequest, CohortTask } from '../src/validation/cohort.ts'

function cohortTask(
  taskId: string,
  groupId: string,
  domain: string,
  families?: readonly string[],
): CohortTask {
  return {
    taskId,
    groupId,
    domain,
    ...(families === undefined ? {} : { families }),
  }
}

const POOL: readonly CohortTask[] = [
  cohortTask('task-data-1', 'group-data-1', 'data'),
  cohortTask('task-design-1', 'group-design-1', 'design'),
  cohortTask('task-finance-1', 'group-finance-1', 'finance'),
  cohortTask('task-finance-2', 'group-finance-2', 'finance'),
  cohortTask('task-finance-3', 'group-finance-3', 'finance'),
  cohortTask('task-legal-1', 'group-legal-1', 'legal'),
  cohortTask('task-legal-2', 'group-legal-2', 'legal'),
  cohortTask('task-ops-1', 'group-ops-1', 'ops'),
  cohortTask('task-ops-2', 'group-ops-2', 'ops', [ABSTENTION_FAMILY]),
  cohortTask('task-science-1', 'group-science-1', 'science'),
  cohortTask('task-science-2', 'group-science-2', 'science'),
]

const REQUEST: BuildCohortRequest = {
  tasks: POOL,
  trainTaskIds: ['train-task-1'],
  trainGroupIds: ['train-group-1'],
  validationSize: 4,
  seed: 17,
  requireDomains: 3,
}

function captureError(run: () => unknown): Error {
  try {
    run()
  } catch (error) {
    if (error instanceof Error) return error
    throw error
  }
  throw new Error('expected the operation to throw')
}

function expectMetadataError(run: () => unknown): CohortMetadataError {
  const error = captureError(run)
  if (!(error instanceof CohortMetadataError)) {
    throw new Error(`expected CohortMetadataError, received ${error.name}: ${error.message}`)
  }
  return error
}

describe('validation cohort selection', () => {
  it('builds a pairwise-disjoint cohort with domain coverage and an abstention candidate', () => {
    const cohort = buildCohort(REQUEST)
    expect(cohort.tasks).toHaveLength(REQUEST.validationSize)
    expect(cohort.taskIds).toHaveLength(REQUEST.validationSize)
    expect(new Set(cohort.taskIds).size).toBe(cohort.taskIds.length)
    expect(cohort.domains.length).toBeGreaterThanOrEqual(MIN_VALIDATION_DOMAINS)

    const identities = cohort.tasks.flatMap(task => [task.groupId, ...(task.families ?? [])])
    expect(new Set(identities).size).toBe(identities.length)
    for (const groupId of cohort.groupIds) {
      expect(REQUEST.trainGroupIds).not.toContain(groupId)
    }
    for (const taskId of cohort.taskIds) {
      expect(REQUEST.trainTaskIds).not.toContain(taskId)
    }

    expect(cohort.abstentionSatisfied).toBe(true)
    expect(cohort.abstentionTaskIds).toEqual(['task-ops-2'])
    expect(cohort.membershipHash).toMatch(/^[0-9a-f]{64}$/)
  })

  it('produces a clean audit for the selected cohort', () => {
    const cohort = buildCohort(REQUEST)
    const audit = auditCohort(
      POOL,
      REQUEST.trainTaskIds,
      REQUEST.trainGroupIds,
      cohort.taskIds,
    )
    expect(audit.ok).toBe(true)
    expect(audit.crossStageLeakage).toBe(false)
    expect(audit.overlaps.tasks).toEqual([])
    expect(audit.overlaps.groups).toEqual([])
    expect(audit.duplicateValidationGroups).toEqual([])
    expect(audit.unknownValidationTaskIds).toEqual([])
    expect(audit.validation.taskIds).toEqual(cohort.taskIds)
    expect(audit.validation.groupIds).toEqual(cohort.groupIds)
    expect(audit.validation.membershipHash).toBe(cohort.membershipHash)
  })

  it('is deterministic for one seed and independent of pool order', () => {
    const first = buildCohort(REQUEST)
    const second = buildCohort(REQUEST)
    const reversedPool = buildCohort({ ...REQUEST, tasks: [...POOL].reverse() })
    expect(second).toEqual(first)
    expect(reversedPool).toEqual(first)

    const otherSeed = buildCohort({ ...REQUEST, seed: 99 })
    expect(otherSeed.taskIds).not.toEqual(first.taskIds)
  })

  it('enforces the 4-8 task bounds and request consistency', () => {
    const tooSmall = captureError(() => buildCohort({ ...REQUEST, validationSize: 3 }))
    expect(tooSmall).toBeInstanceOf(CohortInfeasibleError)
    const tooLarge = captureError(() => buildCohort({ ...REQUEST, validationSize: 9 }))
    expect(tooLarge).toBeInstanceOf(CohortInfeasibleError)

    const largest = buildCohort({ ...REQUEST, validationSize: MAX_VALIDATION_TASKS })
    expect(largest.tasks).toHaveLength(MAX_VALIDATION_TASKS)
    expect(largest.domains.length).toBeGreaterThanOrEqual(MIN_VALIDATION_DOMAINS)

    const domainTooLow = captureError(() => buildCohort({ ...REQUEST, requireDomains: 2 }))
    expect(domainTooLow).toBeInstanceOf(CohortInfeasibleError)
    const domainAboveSize = captureError(() => buildCohort({ ...REQUEST, requireDomains: 5 }))
    expect(domainAboveSize).toBeInstanceOf(CohortInfeasibleError)
  })

  it('rejects a pool with too few distinct domains', () => {
    const twoDomains = [
      cohortTask('task-a-1', 'group-a-1', 'finance'),
      cohortTask('task-a-2', 'group-a-2', 'finance'),
      cohortTask('task-b-1', 'group-b-1', 'legal'),
      cohortTask('task-b-2', 'group-b-2', 'legal'),
    ]
    const error = captureError(() => buildCohort({ ...REQUEST, tasks: twoDomains }))
    expect(error).toBeInstanceOf(CohortInfeasibleError)
    expect(error.message).toMatch(/domains/)
  })

  it('selects only one task per group/family even when the pool has variants', () => {
    const variants = [
      cohortTask('task-v1', 'group-shared', 'finance', ['variant:one']),
      cohortTask('task-v2', 'group-shared', 'finance', ['variant:two']),
      cohortTask('task-other-1', 'group-other-1', 'legal'),
      cohortTask('task-other-2', 'group-other-2', 'science'),
      cohortTask('task-other-3', 'group-other-3', 'ops'),
    ]
    const cohort = buildCohort({ ...REQUEST, tasks: variants })
    const selectedFromShared = cohort.tasks.filter(task => task.groupId === 'group-shared')
    expect(selectedFromShared).toHaveLength(1)
  })
})

describe('validation cohort leakage rejection', () => {
  it('rejects a candidate whose group is used for training', () => {
    const leaked = [...POOL, cohortTask('task-leak-group', 'train-group-1', 'finance')]
    const error = captureError(() => buildCohort({ ...REQUEST, tasks: leaked }))
    if (!(error instanceof CohortLeakageError)) {
      throw new Error(`expected CohortLeakageError, received ${error.name}: ${error.message}`)
    }
    expect(error.groupIds).toContain('train-group-1')
    expect(error.taskIds).toEqual([])
  })

  it('rejects a candidate whose family is used for training', () => {
    const leaked = [
      ...POOL,
      cohortTask('task-leak-family', 'group-leak-family', 'finance', ['train-group-1']),
    ]
    const error = captureError(() => buildCohort({ ...REQUEST, tasks: leaked }))
    expect(error).toBeInstanceOf(CohortLeakageError)
  })

  it('rejects a candidate task id that was used for training', () => {
    const leaked = [...POOL, cohortTask('train-task-1', 'group-leak-task', 'finance')]
    const error = captureError(() => buildCohort({ ...REQUEST, tasks: leaked }))
    if (!(error instanceof CohortLeakageError)) {
      throw new Error(`expected CohortLeakageError, received ${error.name}: ${error.message}`)
    }
    expect(error.taskIds).toEqual(['train-task-1'])
  })

  it('reports explicit cross-stage overlaps in the audit instead of throwing', () => {
    const tasks = [
      cohortTask('train-a', 'train-g', 'finance'),
      cohortTask('val-a', 'val-g', 'legal'),
      cohortTask('val-b', 'train-g', 'science'),
    ]

    const groupAudit = auditCohort(tasks, ['train-a'], ['train-g'], ['val-a', 'val-b'])
    expect(groupAudit.ok).toBe(false)
    expect(groupAudit.crossStageLeakage).toBe(true)
    expect(groupAudit.overlaps.tasks).toEqual([])
    expect(groupAudit.overlaps.groups).toEqual(['train-g'])
    expect(groupAudit.issues.some(row => row.code === 'cross-stage-overlap')).toBe(true)

    const taskAudit = auditCohort(tasks, ['train-a'], ['train-g'], ['train-a', 'val-a'])
    expect(taskAudit.ok).toBe(false)
    expect(taskAudit.crossStageLeakage).toBe(true)
    expect(taskAudit.overlaps.tasks).toEqual(['train-a'])
    expect(taskAudit.overlaps.groups).toEqual(['train-g'])
  })
})

describe('validation cohort metadata rejection', () => {
  it('rejects duplicate task ids', () => {
    const duplicated = [...POOL, cohortTask('task-finance-1', 'group-another', 'finance')]
    const error = expectMetadataError(() => buildCohort({ ...REQUEST, tasks: duplicated }))
    expect(error.issues.some(row => row.code === 'duplicate')).toBe(true)
    expect(error.issues.some(row => row.path.includes('taskId'))).toBe(true)
  })

  it('rejects duplicate training group ids', () => {
    const error = expectMetadataError(() =>
      buildCohort({ ...REQUEST, trainGroupIds: ['train-group-1', 'train-group-1'] })
    )
    expect(error.issues.some(row => row.code === 'duplicate')).toBe(true)
  })

  it('rejects tasks missing a domain or group', () => {
    const missingDomain = expectMetadataError(() =>
      buildCohort({
        ...REQUEST,
        tasks: [...POOL, cohortTask('task-missing-domain', 'group-missing-domain', '')],
      })
    )
    expect(missingDomain.issues.some(row => row.path.endsWith('.domain'))).toBe(true)

    const missingGroup = expectMetadataError(() =>
      buildCohort({
        ...REQUEST,
        tasks: [...POOL, cohortTask('task-missing-group', '', 'finance')],
      })
    )
    expect(missingGroup.issues.some(row => row.path.endsWith('.groupId'))).toBe(true)
  })

  it('rejects a group id that spans more than one domain', () => {
    const conflicting = [
      cohortTask('task-span-a', 'group-span', 'finance'),
      cohortTask('task-span-b', 'group-span', 'legal'),
    ]
    const error = expectMetadataError(() =>
      buildCohort({ ...REQUEST, tasks: conflicting })
    )
    expect(error.issues.some(row => row.code === 'duplicate-group')).toBe(true)
  })

  it('flags duplicate validation groups in the audit', () => {
    const audit = auditCohort(
      [
        cohortTask('task-a', 'group-shared', 'finance'),
        cohortTask('task-b', 'group-shared', 'finance'),
      ],
      [],
      [],
      ['task-a', 'task-b'],
    )
    expect(audit.ok).toBe(false)
    expect(audit.duplicateValidationGroups).toEqual(['group-shared'])
    expect(audit.issues.some(row => row.code === 'duplicate-group')).toBe(true)
  })

  it('flags unknown validation task ids in the audit', () => {
    const audit = auditCohort(
      [cohortTask('task-a', 'group-a', 'finance')],
      [],
      [],
      ['task-a', 'task-missing'],
    )
    expect(audit.ok).toBe(false)
    expect(audit.unknownValidationTaskIds).toEqual(['task-missing'])
    expect(audit.issues.some(row => row.code === 'unknown-task')).toBe(true)
  })
})

describe('validation cohort abstention metadata', () => {
  it('recognizes the reserved abstention family tags', () => {
    expect(isAbstentionCandidate(cohortTask('a', 'ga', 'd', [ABSTENTION_FAMILY]))).toBe(true)
    expect(isAbstentionCandidate(cohortTask('a', 'ga', 'd', ['abstention:novel']))).toBe(true)
    expect(isAbstentionCandidate(cohortTask('a', 'ga', 'd', ['abstention-candidate']))).toBe(
      true,
    )
    expect(isAbstentionCandidate(cohortTask('a', 'ga', 'd', ['finance']))).toBe(false)
    expect(isAbstentionCandidate(cohortTask('a', 'ga', 'd'))).toBe(false)
  })

  it('requires an abstention candidate when the flag is set', () => {
    const cohort = buildCohort({ ...REQUEST, requireAbstentionCandidate: true })
    expect(cohort.abstentionSatisfied).toBe(true)
    expect(cohort.abstentionTaskIds).toEqual(['task-ops-2'])
  })

  it('prefers but does not require abstention metadata by default', () => {
    const withoutMetadata = POOL.map(task =>
      cohortTask(task.taskId, task.groupId, task.domain)
    )
    const cohort = buildCohort({ ...REQUEST, tasks: withoutMetadata })
    expect(cohort.abstentionSatisfied).toBe(false)
    expect(cohort.abstentionTaskIds).toEqual([])
  })

  it('fails when abstention is required and no metadata marks a candidate', () => {
    const withoutMetadata = POOL.map(task =>
      cohortTask(task.taskId, task.groupId, task.domain)
    )
    const error = captureError(() =>
      buildCohort({
        ...REQUEST,
        tasks: withoutMetadata,
        requireAbstentionCandidate: true,
      })
    )
    expect(error).toBeInstanceOf(CohortInfeasibleError)
    expect(error.message).toMatch(/abstention/)
  })
})

describe('membership hashing', () => {
  it('is stable over sorted ids and ignores order and duplicates', () => {
    const first = membershipHash(['task-b', 'task-a'], ['group-2', 'group-1'])
    const second = membershipHash(['task-a', 'task-b', 'task-a'], ['group-1', 'group-2'])
    const objectForm = membershipHash({
      taskIds: ['task-b', 'task-a'],
      groupIds: ['group-2', 'group-1'],
    })
    expect(first).toBe(second)
    expect(objectForm).toBe(first)
    expect(first).toMatch(/^[0-9a-f]{64}$/)
    expect(membershipHash(['task-a'], ['group-1'])).not.toBe(first)
  })

  it('matches the cohort and audit membership hashes', () => {
    const cohort = buildCohort(REQUEST)
    expect(cohort.membershipHash).toBe(membershipHash(cohort.taskIds, cohort.groupIds))
    expect(cohort.membershipHash).toBe(
      membershipHash({ taskIds: cohort.taskIds, groupIds: cohort.groupIds }),
    )

    const forward = auditCohort(POOL, REQUEST.trainTaskIds, REQUEST.trainGroupIds, cohort.taskIds)
    const reversed = auditCohort(
      POOL,
      [...REQUEST.trainTaskIds].reverse(),
      [...REQUEST.trainGroupIds].reverse(),
      [...cohort.taskIds].reverse(),
    )
    expect(reversed.validation.membershipHash).toBe(forward.validation.membershipHash)
    expect(reversed.train.membershipHash).toBe(forward.train.membershipHash)
    expect(forward.validation.membershipHash).toBe(cohort.membershipHash)
  })
})
