import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from 'node:fs/promises'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import type { Finding } from '../src/contracts/evidence.ts'
import { findingId, operationId, skillId, traceId, type TraceId } from '../src/contracts/ids.ts'
import type { Operation } from '../src/contracts/operations.ts'
import { isRecord } from '../src/contracts/validation.ts'
import {
  preflight,
  type PreflightReport,
  type ScriptRunner,
} from '../src/preflight/preflight.ts'
import {
  planSkillResources,
  type FailureFamily,
  type SkillBundle,
  type SkillPlan,
} from '../src/resources/planner.ts'
import {
  CorruptPublicationError,
  PublicationConfigurationError,
  PublicationConflictError,
  PublicationPreflightError,
  PublicationValidationError,
  PublicationVerificationError,
  UnsupportedPublicationOperationError,
  WorkspacePublisher,
  computeTreeHash,
  hashPreflightReport,
  hashPublicationContent,
  skillDirectoryName,
  type PublicationReceiptDocument,
} from '../src/publication/publisher.ts'

const FAMILY_LABEL: Readonly<Record<FailureFamily, string>> = {
  'unit-harmonization': 'unit harmonization',
  'codebook-parsing': 'codebook parsing',
  'spreadsheet-formula-validation': 'spreadsheet formula validation',
  'financial-reconciliation': 'financial definition reconciliation',
}

const FIXED_TIME = '2026-02-03T04:05:06.000Z'

const tempRoots: string[] = []

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((path) => rm(path, { recursive: true, force: true })))
})

function makeFinding(family: FailureFamily): Finding {
  return {
    id: findingId(`finding:${family}`),
    traceId: traceId(`trace:${family}`),
    detector: `detector-${family}`,
    confidence: 0.9,
    summary: `repeated ${FAMILY_LABEL[family]} failure`,
  }
}

function makeOperation(
  family: FailureFamily,
  kind: Operation['kind'] = 'create',
  overrides: { readonly skill?: string; readonly id?: string } = {},
): Operation {
  const finding = makeFinding(family)
  return {
    id: operationId(overrides.id ?? `${kind}:${family}`),
    kind,
    skillId: skillId(overrides.skill ?? `skill-${family}`),
    findingId: finding.id,
    summary: `apply ${FAMILY_LABEL[family]} guidance`,
  }
}

function makePlan(
  operation: Operation,
  family: FailureFamily,
  options: {
    readonly existingBundle?: SkillBundle
    readonly assetPath?: string
  } = {},
): SkillPlan {
  return planSkillResources({
    operation,
    finding: makeFinding(family),
    family,
    ...(options.existingBundle === undefined ? {} : { existingBundle: options.existingBundle }),
    ...(options.assetPath === undefined
      ? {}
      : {
          outputTemplate: {
            path: options.assetPath,
            content: `# ${FAMILY_LABEL[family]} report\n\n- finding\n- evidence\n`,
            rationale: 'Teams reuse this report shape for every occurrence of this family.',
          },
        }),
  })
}

function expectedOf(fixture: Readonly<Record<string, unknown>>): Readonly<Record<string, unknown>> {
  const expected = fixture.expect
  if (!isRecord(expected)) throw new Error('fixture is missing an expect object')
  return expected
}

const passingRunner: ScriptRunner = {
  run(request) {
    return {
      exitCode: 0,
      stdout: JSON.stringify(expectedOf(request.fixture)),
      stderr: '',
      wallMs: 4,
    }
  },
}

const failingRunner: ScriptRunner = {
  run() {
    return { exitCode: 2, stdout: '', stderr: 'fixture failed', wallMs: 4 }
  },
}

async function acceptFor(plan: SkillPlan): Promise<PreflightReport> {
  const report = await preflight({ bundle: plan.bundle, plan, runner: passingRunner })
  expect(report.verdict).toBe('accept')
  return report
}

async function repairFor(plan: SkillPlan): Promise<{ report: PreflightReport; bundle: SkillBundle }> {
  const bundle: SkillBundle = {
    ...plan.bundle,
    'references/orphan.md': '# Orphan notes\n\nThis file is not referenced anywhere.\n',
  }
  const report = await preflight({ bundle, plan, runner: passingRunner })
  expect(report.verdict).toBe('repair')
  return { report, bundle }
}

async function readJson(path: string): Promise<unknown> {
  const text = await readFile(path, 'utf8')
  return JSON.parse(text)
}

function isReceipt(value: unknown): value is PublicationReceiptDocument {
  if (!isRecord(value)) return false
  return value.schemaVersion === 1
    && typeof value.operationId === 'string'
    && typeof value.skillId === 'string'
    && typeof value.operationKind === 'string'
    && typeof value.mode === 'string'
    && typeof value.channel === 'string'
    && Array.isArray(value.sourceTraceIds)
    && typeof value.policyVersion === 'string'
    && typeof value.configVersion === 'string'
    && typeof value.preflightVerdict === 'string'
    && typeof value.preflightHash === 'string'
    && Array.isArray(value.files)
    && typeof value.treeHash === 'string'
    && typeof value.releaseId === 'string'
    && typeof value.timestamp === 'string'
    && typeof value.fingerprint === 'string'
}

async function readReceipt(path: string): Promise<PublicationReceiptDocument> {
  const value = await readJson(path)
  if (!isReceipt(value)) throw new Error('receipt failed its test-side guard')
  return value
}

async function listFiles(directory: string, prefix = ''): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true })
  const files: string[] = []
  for (const entry of entries) {
    const path = prefix.length === 0 ? entry.name : `${prefix}/${entry.name}`
    if (entry.isDirectory()) {
      files.push(...await listFiles(join(directory, entry.name), path))
    } else {
      files.push(path)
    }
  }
  return files.sort()
}

function skillDir(root: string, value: string): string {
  return join(root, 'skills', skillDirectoryName(value))
}

async function versionIds(root: string, value: string): Promise<string[]> {
  return (await readdir(join(skillDir(root, value), 'versions'))).sort()
}

function requestFor(
  operation: Operation,
  plan: SkillPlan,
  report: PreflightReport,
  overrides: Partial<{
    channel: 'provisional' | 'canary' | 'accepted'
    sourceTraceIds: readonly TraceId[]
    policyVersion: string
    configVersion: string
  }> = {},
): Parameters<WorkspacePublisher['publish']>[0] {
  return {
    operation,
    plan,
    preflight: report,
    sourceTraceIds: overrides.sourceTraceIds ?? [plan.traceId],
    policyVersion: overrides.policyVersion ?? 'policy-v1',
    configVersion: overrides.configVersion ?? 'config-v1',
    ...(overrides.channel === undefined ? {} : { channel: overrides.channel }),
  }
}

async function newInventoryRoot(): Promise<string> {
  const parent = await mkdtemp(join(tmpdir(), 'pipeline-v2-publisher-'))
  tempRoots.push(parent)
  return join(parent, 'inventory')
}

function fixedClock(): () => Date {
  return () => new Date(FIXED_TIME)
}

function steppingClock(): () => Date {
  let step = 0
  return () => new Date(Date.parse(FIXED_TIME) + step++ * 1000)
}

describe('content-addressed workspace publication', () => {
  it('publishes every bundle file atomically and writes a matching receipt', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: fixedClock() })
    const operation = makeOperation('unit-harmonization')
    const plan = makePlan(operation, 'unit-harmonization')
    const report = await acceptFor(plan)

    const result = await publisher.publish(requestFor(operation, plan, report))

    expect(result.idempotent).toBe(false)
    expect(result.created).toBe(true)
    expect(result.releaseId).toBe(result.treeHash)
    expect(result.treeHash).toMatch(/^[0-9a-f]{64}$/)
    expect(result.previousVersion).toBeNull()
    expect(await listFiles(result.versionPath)).toEqual(Object.keys(plan.bundle).sort())
    for (const [path, content] of Object.entries(plan.bundle)) {
      expect(await readFile(join(result.versionPath, ...path.split('/')), 'utf8')).toBe(content)
    }
    expect(await readdir(result.versionPath)).not.toContain('SKILL.md.tmp')
    expect(await access(join(root, '.skill-evolving-validation-root.json'))).toBeUndefined()
    const skillEntries = await readdir(skillDir(root, String(operation.skillId)))
    expect(skillEntries.filter((entry) => entry.startsWith('.publish-'))).toEqual([])

    const receipt = await readReceipt(result.receiptPath)
    expect(receipt.operationId).toBe(String(operation.id))
    expect(receipt.skillId).toBe(String(operation.skillId))
    expect(receipt.sourceTraceIds).toEqual([String(plan.traceId)])
    expect(receipt.policyVersion).toBe('policy-v1')
    expect(receipt.configVersion).toBe('config-v1')
    expect(receipt.preflightVerdict).toBe('accept')
    expect(receipt.preflightHash).toBe(hashPreflightReport(report))
    expect(receipt.timestamp).toBe(FIXED_TIME)
    expect(receipt.previousVersion).toBeNull()
    expect(receipt.previousTreeHash).toBeNull()
    expect(receipt.rollbackTo).toBeNull()
    expect(receipt.channel).toBe('provisional')
    expect(receipt.files.map((file) => file.path)).toEqual(Object.keys(plan.bundle).sort())

    for (const file of receipt.files) {
      const content = await readFile(join(result.versionPath, ...file.path.split('/')), 'utf8')
      expect(hashPublicationContent(content)).toBe(file.sha256)
      expect(Buffer.byteLength(content, 'utf8')).toBe(file.bytes)
    }
    expect(computeTreeHash(receipt.files)).toBe(receipt.treeHash)
    expect(receipt.treeHash).toBe(result.treeHash)

    const current = await publisher.getCurrent(operation.skillId)
    expect(current?.releaseId).toBe(result.releaseId)
    expect(current?.treeHash).toBe(result.treeHash)
    expect(current?.versionPath).toBe(result.versionPath)
  })

  it('treats an identical republish as idempotent without rewriting the release', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: steppingClock() })
    const operation = makeOperation('codebook-parsing')
    const plan = makePlan(operation, 'codebook-parsing')
    const report = await acceptFor(plan)
    const request = requestFor(operation, plan, report)

    const first = await publisher.publish(request)
    const second = await publisher.publish(request)

    expect(second.idempotent).toBe(true)
    expect(second.created).toBe(false)
    expect(second.releaseId).toBe(first.releaseId)
    expect(second.treeHash).toBe(first.treeHash)
    expect(second.receiptPath).toBe(first.receiptPath)
    expect(second.receipt.timestamp).toBe(first.receipt.timestamp)
    expect(await versionIds(root, String(operation.skillId))).toEqual([first.releaseId])
    expect(await readdir(join(skillDir(root, String(operation.skillId)), 'receipts'))).toHaveLength(1)
  })

  it('rejects a create that would overwrite a different published release', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: steppingClock() })
    const first = makeOperation('unit-harmonization')
    const firstPlan = makePlan(first, 'unit-harmonization')
    const published = await publisher.publish(requestFor(first, firstPlan, await acceptFor(firstPlan)))

    const conflicting = makeOperation('codebook-parsing', 'create', {
      skill: String(first.skillId),
      id: 'create:conflicting',
    })
    const conflictingPlan = makePlan(conflicting, 'codebook-parsing')
    const error = await publisher
      .publish(requestFor(conflicting, conflictingPlan, await acceptFor(conflictingPlan)))
      .catch((cause: unknown) => cause)

    expect(error).toBeInstanceOf(PublicationConflictError)
    expect(error).toMatchObject({ code: 'publication-conflict' })
    expect(await versionIds(root, String(first.skillId))).toEqual([published.releaseId])
    const current = await publisher.getCurrent(first.skillId)
    expect(current?.releaseId).toBe(published.releaseId)
  })

  it('retains the previous version across an update and restores it on rollback', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: steppingClock() })
    const family: FailureFamily = 'unit-harmonization'
    const create = makeOperation(family)
    const createPlan = makePlan(create, family)
    const v1 = await publisher.publish(requestFor(create, createPlan, await acceptFor(createPlan)))

    const update = makeOperation(family, 'update', {
      skill: String(create.skillId),
      id: 'update:unit-harmonization',
    })
    const updatePlan = makePlan(update, family, {
      existingBundle: createPlan.bundle,
      assetPath: 'assets/unit-report.md',
    })
    const v2 = await publisher.publish(requestFor(update, updatePlan, await acceptFor(updatePlan)))

    expect(v2.previousVersion).toBe(v1.releaseId)
    expect(await versionIds(root, String(create.skillId))).toEqual([v1.releaseId, v2.releaseId].sort())
    const v2Receipt = await readReceipt(v2.receiptPath)
    expect(v2Receipt.previousVersion).toBe(v1.releaseId)
    expect(v2Receipt.rollbackTo).toBe(v1.releaseId)
    expect(await readFile(join(v2.versionPath, 'assets', 'unit-report.md'), 'utf8'))
      .toContain('unit harmonization report')

    const rollback = await publisher.rollback(create.skillId)
    expect(rollback.idempotent).toBe(false)
    expect(rollback.releaseId).toBe(v1.releaseId)
    expect(rollback.previousVersion).toBe(v2.releaseId)
    expect(await readFile(join(rollback.versionPath, 'SKILL.md'), 'utf8'))
      .toBe(createPlan.bundle['SKILL.md'])
    const current = await publisher.getCurrent(create.skillId)
    expect(current?.releaseId).toBe(v1.releaseId)
    expect(await versionIds(root, String(create.skillId))).toHaveLength(2)

    const backward = await publisher.rollback({ skillId: create.skillId, releaseId: v2.releaseId })
    expect(backward.releaseId).toBe(v2.releaseId)
    expect(await readFile(join(backward.versionPath, 'SKILL.md'), 'utf8'))
      .toBe(updatePlan.bundle['SKILL.md'])
  })

  it('merges new resources without replacing published ones', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: steppingClock() })
    const family: FailureFamily = 'codebook-parsing'
    const create = makeOperation(family)
    const createPlan = makePlan(create, family)
    const v1 = await publisher.publish(requestFor(create, createPlan, await acceptFor(createPlan)))

    const merge = makeOperation(family, 'merge', {
      skill: String(create.skillId),
      id: 'merge:codebook-parsing',
    })
    const mergePlan = makePlan(merge, family, {
      existingBundle: createPlan.bundle,
      assetPath: 'assets/merged-report.md',
    })
    const v2 = await publisher.publish(requestFor(merge, mergePlan, await acceptFor(mergePlan)))

    expect(v2.previousVersion).toBe(v1.releaseId)
    const merged = await publisher.readCurrentBundle(create.skillId)
    expect(merged).toBeDefined()
    for (const [path, content] of Object.entries(createPlan.bundle)) {
      if (path === 'SKILL.md') continue
      expect(merged?.[path]).toBe(content)
    }
    expect(merged?.['assets/merged-report.md']).toContain('codebook parsing report')
    expect(merged?.['SKILL.md']).toContain('assets/merged-report.md')
    expect(await versionIds(root, String(create.skillId))).toHaveLength(2)
  })

  it('rejects merge attempts that would overwrite published content', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: steppingClock() })
    const family: FailureFamily = 'unit-harmonization'
    const create = makeOperation(family)
    const createPlan = makePlan(create, family)
    await publisher.publish(requestFor(create, createPlan, await acceptFor(createPlan)))

    const merge = makeOperation(family, 'merge', {
      skill: String(create.skillId),
      id: 'merge:conflicting',
    })
    const mergePlan = makePlan(merge, family, { existingBundle: createPlan.bundle })
    const referencePath = 'references/unit-harmonization.md'
    const conflictedPlan: SkillPlan = {
      ...mergePlan,
      bundle: {
        ...mergePlan.bundle,
        [referencePath]: `${mergePlan.bundle[referencePath] ?? ''}\nchanged after publication\n`,
      },
    }
    const error = await publisher
      .publish(requestFor(merge, conflictedPlan, await acceptFor(conflictedPlan)))
      .catch((cause: unknown) => cause)

    expect(error).toBeInstanceOf(PublicationConflictError)
    expect(error).toMatchObject({ code: 'publication-conflict' })
    const issues = error instanceof PublicationConflictError ? error.issues : []
    expect(issues.some((row) => row.code === 'merge-overwrite')).toBe(true)
    expect(await versionIds(root, String(create.skillId))).toHaveLength(1)
    const entries = await readdir(skillDir(root, String(create.skillId)))
    expect(entries.filter((entry) => entry.startsWith('.publish-'))).toEqual([])
  })
})

describe('publication path and metadata safety', () => {
  it('rejects path escapes, absolute paths, duplicates, and leaves no tree behind', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: fixedClock() })
    const operation = makeOperation('unit-harmonization')
    const plan = makePlan(operation, 'unit-harmonization')
    const report = await acceptFor(plan)

    const escapes: readonly SkillBundle[] = [
      { ...plan.bundle, '../evil.py': 'print("escape")\n' },
      { ...plan.bundle, '/etc/evil.py': 'print("escape")\n' },
      { ...plan.bundle, 'scripts/Tool.py': 'print("a")\n', 'scripts/tool.py': 'print("b")\n' },
    ]
    for (const bundle of escapes) {
      const error = await publisher
        .publish({
          operation,
          bundle,
          preflight: report,
          sourceTraceIds: [plan.traceId],
          policyVersion: 'policy-v1',
          configVersion: 'config-v1',
        })
        .catch((cause: unknown) => cause)
      expect(error).toBeInstanceOf(PublicationValidationError)
    }

    await expect(stat(root)).rejects.toMatchObject({ code: 'ENOENT' })
  })

  it('rejects mismatched metadata, unsupported kinds, and missing versions', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: fixedClock() })
    const operation = makeOperation('unit-harmonization')
    const plan = makePlan(operation, 'unit-harmonization')
    const report = await acceptFor(plan)

    const mismatched = makeOperation('unit-harmonization', 'create', {
      skill: String(operation.skillId),
      id: 'create:mismatched',
    })
    const mismatchError = await publisher
      .publish(requestFor(mismatched, plan, report))
      .catch((cause: unknown) => cause)
    expect(mismatchError).toBeInstanceOf(PublicationValidationError)
    expect(mismatchError).toMatchObject({ code: 'invalid-publication' })

    const deleted = makeOperation('unit-harmonization', 'delete', {
      skill: String(operation.skillId),
      id: 'delete:unit',
    })
    const unsupported = await publisher
      .publish({
        operation: deleted,
        bundle: plan.bundle,
        preflight: report,
        sourceTraceIds: [plan.traceId],
        policyVersion: 'policy-v1',
        configVersion: 'config-v1',
      })
      .catch((cause: unknown) => cause)
    expect(unsupported).toBeInstanceOf(UnsupportedPublicationOperationError)
    expect(unsupported).toMatchObject({ code: 'unsupported-operation' })

    const noTrace = await publisher
      .publish({
        operation,
        bundle: plan.bundle,
        preflight: report,
        policyVersion: 'policy-v1',
        configVersion: 'config-v1',
      })
      .catch((cause: unknown) => cause)
    expect(noTrace).toBeInstanceOf(PublicationValidationError)
    expect(noTrace).toMatchObject({ code: 'invalid-publication' })
  })

  it('refuses preflight rejects, unaccepted repairs, and failed verification', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: fixedClock() })
    const operation = makeOperation('financial-reconciliation')
    const plan = makePlan(operation, 'financial-reconciliation')
    const rejected = await preflight({
      bundle: plan.bundle,
      plan,
      runner: failingRunner,
    })
    expect(rejected.verdict).toBe('reject')

    const rejectedError = await publisher
      .publish(requestFor(operation, plan, rejected))
      .catch((cause: unknown) => cause)
    expect(rejectedError).toBeInstanceOf(PublicationPreflightError)
    expect(rejectedError).toMatchObject({ code: 'preflight-rejected' })

    const repair = await repairFor(plan)
    const repairError = await publisher
      .publish({
        operation,
        bundle: repair.bundle,
        preflight: repair.report,
        sourceTraceIds: [plan.traceId],
        policyVersion: 'policy-v1',
        configVersion: 'config-v1',
      })
      .catch((cause: unknown) => cause)
    expect(repairError).toBeInstanceOf(PublicationPreflightError)

    const accepted = await publisher.publish({
      operation,
      bundle: repair.bundle,
      preflight: repair.report,
      acceptedReceipt: { operationId: operation.id, status: 'pass' },
      sourceTraceIds: [plan.traceId],
      policyVersion: 'policy-v1',
      configVersion: 'config-v1',
    })
    expect(accepted.receipt.preflightVerdict).toBe('repair')
    expect(accepted.receipt.files.some((file) => file.path === 'references/orphan.md')).toBe(true)

    const verifyOperation = makeOperation('unit-harmonization')
    const verifyPlan = makePlan(verifyOperation, 'unit-harmonization')
    const verifyReport = await acceptFor(verifyPlan)
    const verificationError = await publisher
      .publish({
        ...requestFor(verifyOperation, verifyPlan, verifyReport),
        verification: { status: 'fail', summary: 'replay diverged' },
      })
      .catch((cause: unknown) => cause)
    expect(verificationError).toBeInstanceOf(PublicationVerificationError)
    expect(verificationError).toMatchObject({ code: 'verification-not-passed' })
  })

  it('detects a tampered release before rolling back to it', async () => {
    const root = await newInventoryRoot()
    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: steppingClock() })
    const family: FailureFamily = 'unit-harmonization'
    const create = makeOperation(family)
    const createPlan = makePlan(create, family)
    const v1 = await publisher.publish(requestFor(create, createPlan, await acceptFor(createPlan)))

    const update = makeOperation(family, 'update', {
      skill: String(create.skillId),
      id: 'update:tamper',
    })
    const updatePlan = makePlan(update, family, {
      existingBundle: createPlan.bundle,
      assetPath: 'assets/tamper-report.md',
    })
    const v2 = await publisher.publish(requestFor(update, updatePlan, await acceptFor(updatePlan)))
    expect(v2.releaseId).not.toBe(v1.releaseId)

    await writeFile(join(v1.versionPath, 'SKILL.md'), '# tampered\n', 'utf8')
    const error = await publisher.rollback(create.skillId).catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(CorruptPublicationError)
    expect(error).toMatchObject({ code: 'corrupt-publication' })
    const current = await publisher.getCurrent(create.skillId)
    expect(current?.releaseId).toBe(v2.releaseId)
  })
})

describe('dedicated validation inventory root', () => {
  it('requires exactly one absolute root', async () => {
    expect(() => new WorkspacePublisher({})).toThrow(PublicationConfigurationError)
    expect(() => new WorkspacePublisher({ inventoryRoot: 'relative/path' }))
      .toThrow(PublicationConfigurationError)
    expect(() => new WorkspacePublisher({ inventoryRoot: '/tmp/a', root: '/tmp/b' }))
      .toThrow(PublicationConfigurationError)
    const unusedRoot = join(tmpdir(), `pipeline-v2-unused-${process.pid}-${Date.now()}`)
    await expect(new WorkspacePublisher({ inventoryRoot: unusedRoot }).getCurrent(
      skillId('unused'),
    )).resolves.toBeUndefined()
  })

  it('refuses primary user skill inventories and their ancestors', () => {
    for (const path of [
      join(homedir(), '.claude', 'skills'),
      join(homedir(), '.claude'),
      join(homedir(), '.codex', 'skills'),
      join(homedir(), '.agents', 'skills'),
      homedir(),
    ]) {
      expect(() => new WorkspacePublisher({ inventoryRoot: path }))
        .toThrow(PublicationConfigurationError)
    }
  })

  it('refuses a non-empty directory that is not marked as a validation inventory', async () => {
    const parent = await mkdtemp(join(tmpdir(), 'pipeline-v2-publisher-unmarked-'))
    tempRoots.push(parent)
    const root = join(parent, 'existing')
    await mkdir(root)
    await writeFile(join(root, 'authored-skill.md'), '# keep me\n', 'utf8')

    const publisher = new WorkspacePublisher({ inventoryRoot: root, clock: fixedClock() })
    const operation = makeOperation('unit-harmonization')
    const plan = makePlan(operation, 'unit-harmonization')
    const error = await publisher
      .publish(requestFor(operation, plan, await acceptFor(plan)))
      .catch((cause: unknown) => cause)

    expect(error).toBeInstanceOf(PublicationConfigurationError)
    expect(error).toMatchObject({ code: 'invalid-inventory-root' })
    expect(await readFile(join(root, 'authored-skill.md'), 'utf8')).toBe('# keep me\n')
  })
})
