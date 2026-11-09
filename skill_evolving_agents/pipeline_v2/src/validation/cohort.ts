import { createHash } from 'node:crypto'

import { PipelineError } from '../contracts/errors.ts'
import type { StructuredIssue } from '../contracts/errors.ts'
import { isNonEmptyString, issue } from '../contracts/validation.ts'

/**
 * Leakage-safe validation cohort construction and audit.
 *
 * The cohort is selected from task metadata only. It never reads benchmark
 * outcomes, heldout labels, or verifier results. `groupId` and every entry in
 * `families` share one membership namespace: a task is disjoint from training
 * when neither its task id nor any group/family id appears in the training
 * membership.
 *
 * Policies mirrored from the Python evaluation rules:
 * - train, validation, and holdout task ids and group/family ids are disjoint;
 * - `groupId` is used for related variants originating from one template,
 *   source trace, or task family;
 * - a repeated id across stages is a hard error.
 *
 * A pool may contain several variants that share a `groupId`; the selected
 * cohort keeps at most one task per group/family, so a validation group can
 * never be duplicated. `auditCohort` reports a duplicated validation group if
 * a caller proposes one anyway.
 */

/** Smallest validation cohort accepted by the benchmark policy. */
export const MIN_VALIDATION_TASKS = 4

/** Largest validation cohort accepted by the benchmark policy. */
export const MAX_VALIDATION_TASKS = 8

/** Minimum distinct domains required for a validation cohort. */
export const MIN_VALIDATION_DOMAINS = 3

/**
 * Reserved family tag marking a task that is likely to make the router
 * abstain. Tags beginning with `abstention:` or `abstention-` are accepted too.
 */
export const ABSTENTION_FAMILY = 'abstention'

/** Metadata for one task that may enter a validation cohort. */
export interface CohortTask {
  readonly taskId: string
  readonly groupId: string
  readonly domain: string
  readonly families?: readonly string[]
}

/** Request for a deterministic, leakage-safe validation cohort. */
export interface BuildCohortRequest {
  /** Candidate validation tasks. Every candidate must already be disjoint from training. */
  readonly tasks: readonly CohortTask[]
  /** Task ids used for generation, mining, or training. */
  readonly trainTaskIds: readonly string[]
  /** Group and family ids used for generation, mining, or training. */
  readonly trainGroupIds: readonly string[]
  /** Number of validation tasks to select. Must be between 4 and 8. */
  readonly validationSize: number
  /** Deterministic selection seed. */
  readonly seed: number
  /** Minimum distinct domains. Must be at least 3 and no larger than `validationSize`. */
  readonly requireDomains: number
  /**
   * When true, fail if no selected task carries abstention metadata. When
   * omitted or false, an abstention candidate is still preferred when the
   * metadata provides one, but it is not mandatory.
   */
  readonly requireAbstentionCandidate?: boolean
}

/** One auditable cohort selection. */
export interface ValidationCohort {
  readonly tasks: readonly CohortTask[]
  readonly taskIds: readonly string[]
  /** Group and family ids of the selected tasks, sorted and unique. */
  readonly groupIds: readonly string[]
  readonly domains: readonly string[]
  readonly seed: number
  readonly requireDomains: number
  readonly membershipHash: string
  /** Selected tasks carrying abstention metadata, sorted by task id. */
  readonly abstentionTaskIds: readonly string[]
  readonly abstentionSatisfied: boolean
}

/** Sorted membership identity for one experimental stage. */
export interface CohortMembership {
  readonly taskIds: readonly string[]
  readonly groupIds: readonly string[]
  readonly membershipHash: string
}

/** Explicit cross-stage overlaps found by `auditCohort`. */
export interface CohortOverlaps {
  readonly tasks: readonly string[]
  readonly groups: readonly string[]
}

/** Diagnostic report for one proposed validation membership. */
export interface CohortAudit {
  readonly ok: boolean
  /** True when any task id or group/family id appears in both stages. */
  readonly crossStageLeakage: boolean
  readonly train: CohortMembership
  readonly validation: CohortMembership
  readonly overlaps: CohortOverlaps
  /** Group/family ids assigned to more than one validation task. */
  readonly duplicateValidationGroups: readonly string[]
  readonly unknownValidationTaskIds: readonly string[]
  readonly issues: readonly StructuredIssue[]
}

/** A set of task and group/family ids that can be hashed as one membership. */
export interface MembershipIdSet {
  readonly taskIds: readonly string[]
  readonly groupIds: readonly string[]
}

/** Task metadata was missing, duplicated, or internally inconsistent. */
export class CohortMetadataError extends PipelineError {
  readonly issues: readonly StructuredIssue[]

  constructor(issues: readonly StructuredIssue[]) {
    super('invalid-cohort-metadata', 'validation cohort metadata is invalid', { issues })
    this.issues = issues
  }
}

/** A candidate or selected validation task overlaps generation/training membership. */
export class CohortLeakageError extends PipelineError {
  readonly taskIds: readonly string[]
  readonly groupIds: readonly string[]

  constructor(taskIds: readonly string[], groupIds: readonly string[]) {
    super('cohort-leakage', 'cross-stage cohort leakage', { taskIds, groupIds })
    this.taskIds = taskIds
    this.groupIds = groupIds
  }
}

/** No cohort can satisfy the requested size, domain, abstention, or disjointness rules. */
export class CohortInfeasibleError extends PipelineError {
  constructor(reason: string, details: Readonly<Record<string, unknown>> = {}) {
    super('cohort-infeasible', reason, details)
  }
}

interface TaskCatalog {
  readonly tasks: readonly CohortTask[]
  readonly byTaskId: ReadonlyMap<string, CohortTask>
  readonly identities: ReadonlyMap<string, readonly string[]>
}

interface SuffixState {
  readonly domains: ReadonlySet<string>
  readonly abstentions: number
}

interface SearchOutcome {
  readonly selected: readonly CohortTask[] | undefined
  readonly exhausted: boolean
}

/** Deterministic non-locale string ordering. */
function compareIds(left: string, right: string): number {
  if (left < right) return -1
  if (left > right) return 1
  return 0
}

function sortedUnique(values: readonly string[]): readonly string[] {
  return [...new Set(values)].sort(compareIds)
}

function stableHash(text: string): string {
  return createHash('sha256').update(text).digest('hex')
}

function seededOrderKey(seed: number, value: string): string {
  return stableHash(`cohort/v1|${String(seed)}|${value}`)
}

function identitiesOf(task: CohortTask): readonly string[] {
  return [task.groupId, ...(task.families ?? [])]
}

/**
 * Return true when task metadata marks a likely router abstention candidate.
 *
 * This is metadata-only inference. It is deliberately not derived from
 * benchmark outcomes, holdout labels, or selection reports.
 */
export function isAbstentionCandidate(task: CohortTask): boolean {
  return (task.families ?? []).some(family => {
    const normalized = family.trim().toLowerCase()
    return normalized === ABSTENTION_FAMILY
      || normalized.startsWith(`${ABSTENTION_FAMILY}:`)
      || normalized.startsWith(`${ABSTENTION_FAMILY}-`)
  })
}

/**
 * Deterministic membership hash over sorted task and group/family ids.
 *
 * The hash uses set semantics: input order and repeated ids do not change the
 * result. Task and group namespaces remain distinct.
 */
export function membershipHash(ids: MembershipIdSet): string
export function membershipHash(
  taskIds: readonly string[],
  groupIds: readonly string[],
): string
export function membershipHash(
  idsOrTaskIds: MembershipIdSet | readonly string[],
  maybeGroupIds?: readonly string[],
): string {
  let taskIds: readonly string[]
  let groupIds: readonly string[]
  if (isMembershipIdSet(idsOrTaskIds)) {
    taskIds = idsOrTaskIds.taskIds
    groupIds = idsOrTaskIds.groupIds
  } else {
    taskIds = idsOrTaskIds
    groupIds = maybeGroupIds ?? []
  }
  const canonical = [
    'cohort-membership/v1',
    'tasks',
    ...sortedUnique(taskIds),
    'groups',
    ...sortedUnique(groupIds),
  ].join('\n')
  return stableHash(canonical)
}

function isMembershipIdSet(
  value: MembershipIdSet | readonly string[],
): value is MembershipIdSet {
  return !Array.isArray(value)
}

function collectIds(
  values: readonly string[],
  path: string,
  issues: StructuredIssue[],
): readonly string[] {
  const unique = new Set<string>()
  values.forEach((value, index) => {
    if (!isNonEmptyString(value)) {
      issues.push(issue(`${path}[${index}]`, 'invalid', 'id must be a non-empty string'))
      return
    }
    if (unique.has(value)) {
      issues.push(issue(`${path}[${index}]`, 'duplicate', `duplicate id ${value}`))
      return
    }
    unique.add(value)
  })
  return [...unique].sort(compareIds)
}

function indexTasks(tasks: readonly CohortTask[], issues: StructuredIssue[]): TaskCatalog {
  const byTaskId = new Map<string, CohortTask>()
  const identities = new Map<string, readonly string[]>()
  const valid: CohortTask[] = []
  const domainByGroup = new Map<string, string>()

  tasks.forEach((task, index) => {
    const path = `$.tasks[${index}]`
    const taskId = isNonEmptyString(task.taskId) ? task.taskId : undefined
    const groupId = isNonEmptyString(task.groupId) ? task.groupId : undefined
    const domain = isNonEmptyString(task.domain) ? task.domain : undefined
    if (taskId === undefined) {
      issues.push(issue(`${path}.taskId`, 'invalid', 'taskId must be a non-empty string'))
    }
    if (groupId === undefined) {
      issues.push(issue(`${path}.groupId`, 'missing', 'groupId is required'))
    }
    if (domain === undefined) {
      issues.push(issue(`${path}.domain`, 'missing', 'domain is required'))
    }

    const families: string[] = []
    let familiesValid = true
    if (task.families !== undefined) {
      if (!Array.isArray(task.families)) {
        issues.push(
          issue(`${path}.families`, 'invalid', 'families must be an array of non-empty strings'),
        )
        familiesValid = false
      } else {
        task.families.forEach((family, familyIndex) => {
          if (!isNonEmptyString(family)) {
            issues.push(
              issue(
                `${path}.families[${familyIndex}]`,
                'invalid',
                'family must be a non-empty string',
              ),
            )
            familiesValid = false
            return
          }
          families.push(family)
        })
        const uniqueFamilies = new Set<string>()
        for (const family of families) {
          if (uniqueFamilies.has(family)) {
            issues.push(issue(`${path}.families`, 'duplicate', `duplicate family ${family}`))
            familiesValid = false
          }
          uniqueFamilies.add(family)
        }
      }
    }
    if (groupId !== undefined && families.includes(groupId)) {
      issues.push(
        issue(`${path}.families`, 'duplicate-group', 'families must not repeat the task groupId'),
      )
      familiesValid = false
    }
    if (
      taskId === undefined ||
      groupId === undefined ||
      domain === undefined ||
      !familiesValid
    ) {
      return
    }

    if (byTaskId.has(taskId)) {
      issues.push(issue(`${path}.taskId`, 'duplicate', `duplicate taskId ${taskId}`))
      return
    }

    const existingDomain = domainByGroup.get(groupId)
    if (existingDomain !== undefined && existingDomain !== domain) {
      issues.push(
        issue(
          `${path}.groupId`,
          'duplicate-group',
          `groupId ${groupId} spans domains ${existingDomain} and ${domain}`,
        ),
      )
    } else if (existingDomain === undefined) {
      domainByGroup.set(groupId, domain)
    }

    const normalized: CohortTask = {
      taskId,
      groupId,
      domain,
      ...(families.length === 0 ? {} : { families }),
    }
    byTaskId.set(taskId, normalized)
    identities.set(taskId, [groupId, ...families])
    valid.push(normalized)
  })

  return { tasks: valid, byTaskId, identities }
}

function validateBuildRequest(request: BuildCohortRequest): void {
  const issues: StructuredIssue[] = []
  const sizeValid = Number.isSafeInteger(request.validationSize)
  if (
    !sizeValid ||
    request.validationSize < MIN_VALIDATION_TASKS ||
    request.validationSize > MAX_VALIDATION_TASKS
  ) {
    issues.push(
      issue(
        '$.validationSize',
        'invalid',
        `validationSize must be an integer between ${MIN_VALIDATION_TASKS} and ${MAX_VALIDATION_TASKS}`,
      ),
    )
  }
  if (!Number.isSafeInteger(request.seed)) {
    issues.push(issue('$.seed', 'invalid', 'seed must be a safe integer'))
  }
  if (!Number.isSafeInteger(request.requireDomains)) {
    issues.push(issue('$.requireDomains', 'invalid', 'requireDomains must be a safe integer'))
  } else {
    if (request.requireDomains < MIN_VALIDATION_DOMAINS) {
      issues.push(
        issue(
          '$.requireDomains',
          'invalid',
          `requireDomains must be at least ${MIN_VALIDATION_DOMAINS}`,
        ),
      )
    }
    if (sizeValid && request.requireDomains > request.validationSize) {
      issues.push(
        issue('$.requireDomains', 'invalid', 'requireDomains cannot exceed validationSize'),
      )
    }
  }
  if (
    request.requireAbstentionCandidate !== undefined
    && typeof request.requireAbstentionCandidate !== 'boolean'
  ) {
    issues.push(
      issue('$.requireAbstentionCandidate', 'invalid', 'requireAbstentionCandidate must be boolean'),
    )
  }
  if (issues.length > 0) {
    throw new CohortInfeasibleError('invalid cohort build request', { issues })
  }
}

/**
 * Interleave seeded task order across domains so a prefix of the order already
 * covers many domains, then put abstention candidates first inside each domain.
 * This keeps the bounded search small without looking at any outcome data.
 */
function interleaveCandidates(
  candidates: readonly CohortTask[],
  seed: number,
  preferAbstention: boolean,
): readonly CohortTask[] {
  const byDomain = new Map<string, CohortTask[]>()
  for (const task of candidates) {
    const list = byDomain.get(task.domain)
    if (list === undefined) byDomain.set(task.domain, [task])
    else list.push(task)
  }

  const compareTasks = (left: CohortTask, right: CohortTask): number => {
    if (preferAbstention) {
      const leftRank = isAbstentionCandidate(left) ? 0 : 1
      const rightRank = isAbstentionCandidate(right) ? 0 : 1
      if (leftRank !== rightRank) return leftRank - rightRank
    }
    return compareIds(
      seededOrderKey(seed, left.taskId),
      seededOrderKey(seed, right.taskId),
    ) || compareIds(left.taskId, right.taskId)
  }
  for (const list of byDomain.values()) list.sort(compareTasks)

  const domainOrder = [...byDomain.keys()].sort(
    (left, right) =>
      compareIds(
        seededOrderKey(seed, `domain:${left}`),
        seededOrderKey(seed, `domain:${right}`),
      ) || compareIds(left, right),
  )

  const ordered: CohortTask[] = []
  if (candidates.length === 0) return ordered
  for (let cursor = 0; cursor < candidates.length; cursor += 1) {
    let added = false
    for (const domain of domainOrder) {
      const list = byDomain.get(domain)
      if (list === undefined) continue
      const task = list[cursor]
      if (task === undefined) continue
      ordered.push(task)
      added = true
    }
    if (!added) break
  }
  return ordered
}

function countNewDomains(
  available: ReadonlySet<string>,
  selected: ReadonlySet<string>,
): number {
  let count = 0
  for (const domain of available) {
    if (!selected.has(domain)) count += 1
  }
  return count
}

const SEARCH_NODE_LIMIT = 200_000

/**
 * Bounded deterministic search for exactly `size` pairwise-disjoint tasks that
 * cover `domainMinimum` domains and, when requested, at least one abstention
 * candidate. Candidates are pre-interleaved across domains so the search finds
 * a valid prefix quickly.
 */
function searchCohort(
  candidates: readonly CohortTask[],
  size: number,
  domainMinimum: number,
  requireAbstention: boolean,
  seed: number,
): SearchOutcome {
  const ordered = interleaveCandidates(candidates, seed, requireAbstention)
  const suffix: SuffixState[] = []
  const suffixDomains = new Set<string>()
  let suffixAbstentions = 0
  for (let index = ordered.length - 1; index >= 0; index -= 1) {
    const task = ordered[index]
    if (task !== undefined) {
      suffixDomains.add(task.domain)
      if (isAbstentionCandidate(task)) suffixAbstentions += 1
    }
    suffix[index] = {
      domains: new Set(suffixDomains),
      abstentions: suffixAbstentions,
    }
  }

  let visited = 0
  let exhausted = false

  const visit = (
    index: number,
    selected: readonly CohortTask[],
    used: ReadonlySet<string>,
    domains: ReadonlySet<string>,
    abstentions: number,
  ): readonly CohortTask[] | undefined => {
    visited += 1
    if (visited > SEARCH_NODE_LIMIT) {
      exhausted = true
      return undefined
    }
    if (selected.length === size) {
      if (domains.size < domainMinimum) return undefined
      if (requireAbstention && abstentions === 0) return undefined
      return selected
    }
    if (index >= ordered.length) return undefined
    if (selected.length + (ordered.length - index) < size) return undefined

    const suffixState = suffix[index]
    if (suffixState !== undefined) {
      if (domains.size + countNewDomains(suffixState.domains, domains) < domainMinimum) {
        return undefined
      }
      if (requireAbstention && abstentions === 0 && suffixState.abstentions === 0) {
        return undefined
      }
    }

    const task = ordered[index]
    if (task === undefined) return undefined
    const taskIdentities = identitiesOf(task)
    const conflicts = taskIdentities.some(identity => used.has(identity))
    if (!conflicts) {
      const nextUsed = new Set(used)
      for (const identity of taskIdentities) nextUsed.add(identity)
      const nextDomains = new Set(domains)
      nextDomains.add(task.domain)
      const included = visit(
        index + 1,
        [...selected, task],
        nextUsed,
        nextDomains,
        abstentions + (isAbstentionCandidate(task) ? 1 : 0),
      )
      if (included !== undefined) return included
      if (exhausted) return undefined
    }
    return visit(index + 1, selected, used, domains, abstentions)
  }

  return {
    selected: visit(0, [], new Set<string>(), new Set<string>(), 0),
    exhausted,
  }
}

/**
 * Build a deterministic, leakage-safe validation cohort.
 *
 * Candidate metadata is required to be clean: duplicate task ids, missing
 * domains/groups, group ids spanning domains, and any candidate that overlaps
 * `trainTaskIds` or `trainGroupIds` are rejected rather than silently dropped.
 * Selection is seeded, limited to 4-8 tasks, pairwise disjoint by task id and
 * group/family, covers at least `requireDomains` distinct domains, and prefers
 * one abstention candidate when metadata marks one.
 *
 * @throws CohortInfeasibleError when the request bounds or pool cannot satisfy
 * the rules.
 * @throws CohortMetadataError when task or membership metadata is malformed.
 * @throws CohortLeakageError when a candidate overlaps training membership.
 */
export function buildCohort(request: BuildCohortRequest): ValidationCohort {
  validateBuildRequest(request)

  const issues: StructuredIssue[] = []
  const catalog = indexTasks(request.tasks, issues)
  const trainTaskIds = collectIds(request.trainTaskIds, '$.trainTaskIds', issues)
  const trainGroupIds = collectIds(request.trainGroupIds, '$.trainGroupIds', issues)
  if (issues.length > 0) throw new CohortMetadataError(issues)

  const trainTasks = new Set(trainTaskIds)
  const trainGroups = new Set(trainGroupIds)
  const leakedTaskIds: string[] = []
  const leakedGroupIds = new Set<string>()
  for (const task of catalog.tasks) {
    if (trainTasks.has(task.taskId)) leakedTaskIds.push(task.taskId)
    for (const identity of catalog.identities.get(task.taskId) ?? [task.groupId]) {
      if (trainGroups.has(identity)) leakedGroupIds.add(identity)
    }
  }
  if (leakedTaskIds.length > 0 || leakedGroupIds.size > 0) {
    throw new CohortLeakageError(sortedUnique(leakedTaskIds), sortedUnique([...leakedGroupIds]))
  }

  if (catalog.tasks.length < request.validationSize) {
    throw new CohortInfeasibleError('not enough candidate tasks for the requested cohort', {
      available: catalog.tasks.length,
      validationSize: request.validationSize,
    })
  }
  const availableDomains = new Set(catalog.tasks.map(task => task.domain))
  if (availableDomains.size < request.requireDomains) {
    throw new CohortInfeasibleError('not enough distinct domains for the requested cohort', {
      availableDomains: [...availableDomains].sort(compareIds),
      requireDomains: request.requireDomains,
    })
  }

  const abstentionCandidates = catalog.tasks.filter(isAbstentionCandidate)
  const abstentionRequired = request.requireAbstentionCandidate === true
  if (abstentionRequired && abstentionCandidates.length === 0) {
    throw new CohortInfeasibleError(
      'requireAbstentionCandidate is set but no task carries abstention metadata',
      { abstentionFamily: ABSTENTION_FAMILY },
    )
  }

  let outcome: SearchOutcome = { selected: undefined, exhausted: false }
  if (abstentionCandidates.length > 0) {
    outcome = searchCohort(
      catalog.tasks,
      request.validationSize,
      request.requireDomains,
      true,
      request.seed,
    )
  }
  if (outcome.selected === undefined && !abstentionRequired) {
    outcome = searchCohort(
      catalog.tasks,
      request.validationSize,
      request.requireDomains,
      false,
      request.seed,
    )
  }
  if (outcome.selected === undefined) {
    throw new CohortInfeasibleError(
      outcome.exhausted
        ? 'cohort selection search exceeded its deterministic node limit'
        : 'no validation cohort satisfies size, domain, abstention, and disjointness constraints',
      {
        availableTasks: catalog.tasks.length,
        validationSize: request.validationSize,
        requireDomains: request.requireDomains,
        abstentionCandidates: abstentionCandidates.length,
      },
    )
  }

  const selectedTasks = [...outcome.selected].sort(
    (left, right) => compareIds(left.taskId, right.taskId),
  )
  const selectedTaskIds = selectedTasks.map(task => task.taskId)
  const selectedGroupIds = sortedUnique(selectedTasks.flatMap(task => [...identitiesOf(task)]))
  const selectedDomains = sortedUnique(selectedTasks.map(task => task.domain))
  const abstentionTaskIds = selectedTasks
    .filter(isAbstentionCandidate)
    .map(task => task.taskId)

  const audit = auditCohort(
    request.tasks,
    trainTaskIds,
    trainGroupIds,
    selectedTaskIds,
  )
  if (audit.overlaps.tasks.length > 0 || audit.overlaps.groups.length > 0) {
    throw new CohortLeakageError(audit.overlaps.tasks, audit.overlaps.groups)
  }
  if (!audit.ok) {
    throw new CohortMetadataError(audit.issues)
  }
  if (abstentionRequired && abstentionTaskIds.length === 0) {
    throw new CohortInfeasibleError('selected cohort has no abstention candidate')
  }

  return {
    tasks: selectedTasks,
    taskIds: selectedTaskIds,
    groupIds: selectedGroupIds,
    domains: selectedDomains,
    seed: request.seed,
    requireDomains: request.requireDomains,
    membershipHash: membershipHash(selectedTaskIds, selectedGroupIds),
    abstentionTaskIds,
    abstentionSatisfied: abstentionTaskIds.length > 0,
  }
}

/**
 * Audit a proposed validation membership against training membership.
 *
 * The audit is diagnostic: it returns explicit task and group/family overlaps
 * instead of throwing, so callers can persist a rejection report. `ok` is true
 * only when the cohort is metadata-clean, has no duplicate validation groups,
 * has no unknown validation task ids, and has no cross-stage overlap.
 */
export function auditCohort(
  tasks: readonly CohortTask[],
  trainIds: readonly string[],
  trainGroups: readonly string[],
  validationIds: readonly string[],
): CohortAudit {
  const issues: StructuredIssue[] = []
  const catalog = indexTasks(tasks, issues)
  const trainTaskIds = collectIds(trainIds, '$.trainIds', issues)
  const trainGroupIds = collectIds(trainGroups, '$.trainGroups', issues)
  const validationTaskIds = collectIds(validationIds, '$.validationIds', issues)

  const trainGroupSet = new Set<string>(trainGroupIds)
  for (const taskId of trainTaskIds) {
    for (const identity of catalog.identities.get(taskId) ?? []) {
      trainGroupSet.add(identity)
    }
  }

  const validationTaskSet = new Set(validationTaskIds)
  const validationGroupSet = new Set<string>()
  const groupUsers = new Map<string, Set<string>>()
  const unknownValidationTaskIds: string[] = []
  for (const taskId of validationTaskIds) {
    const task = catalog.byTaskId.get(taskId)
    if (task === undefined) {
      unknownValidationTaskIds.push(taskId)
      issues.push(
        issue('$.validationIds', 'unknown-task', `validation task ${taskId} is not in the catalog`),
      )
      continue
    }
    for (const identity of catalog.identities.get(taskId) ?? [task.groupId]) {
      validationGroupSet.add(identity)
      const users = groupUsers.get(identity) ?? new Set<string>()
      users.add(taskId)
      groupUsers.set(identity, users)
    }
  }

  const duplicateValidationGroups = [...groupUsers.entries()]
    .filter(([, users]) => users.size > 1)
    .map(([identity]) => identity)
    .sort(compareIds)
  for (const identity of duplicateValidationGroups) {
    const users = groupUsers.get(identity)
    const taskList = users === undefined ? '' : `: ${[...users].sort(compareIds).join(', ')}`
    issues.push(
      issue(
        '$.validationIds',
        'duplicate-group',
        `validation group ${identity} is assigned to more than one task${taskList}`,
      ),
    )
  }

  const taskOverlaps = sortedUnique(trainTaskIds.filter(taskId => validationTaskSet.has(taskId)))
  const groupOverlaps = sortedUnique(
    [...validationGroupSet].filter(identity => trainGroupSet.has(identity)),
  )
  for (const taskId of taskOverlaps) {
    issues.push(
      issue(
        '$.validationIds',
        'cross-stage-overlap',
        `task ${taskId} is present in both training and validation`,
      ),
    )
  }
  for (const identity of groupOverlaps) {
    issues.push(
      issue(
        '$.validationGroups',
        'cross-stage-overlap',
        `group ${identity} is present in both training and validation`,
      ),
    )
  }

  const trainMembership: CohortMembership = {
    taskIds: trainTaskIds,
    groupIds: sortedUnique([...trainGroupSet]),
    membershipHash: membershipHash(trainTaskIds, sortedUnique([...trainGroupSet])),
  }
  const validationMembership: CohortMembership = {
    taskIds: validationTaskIds,
    groupIds: sortedUnique([...validationGroupSet]),
    membershipHash: membershipHash(validationTaskIds, sortedUnique([...validationGroupSet])),
  }

  return {
    ok: issues.length === 0,
    crossStageLeakage: taskOverlaps.length > 0 || groupOverlaps.length > 0,
    train: trainMembership,
    validation: validationMembership,
    overlaps: { tasks: taskOverlaps, groups: groupOverlaps },
    duplicateValidationGroups,
    unknownValidationTaskIds: sortedUnique(unknownValidationTaskIds),
    issues,
  }
}
