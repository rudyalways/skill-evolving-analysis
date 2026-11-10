import { describe, expect, it } from 'vitest'
import type { Finding } from '../src/contracts/evidence.ts'
import { findingId, operationId, skillId, traceId } from '../src/contracts/ids.ts'
import type { Operation } from '../src/contracts/operations.ts'
import { isRecord } from '../src/contracts/validation.ts'
import {
  PREFLIGHT_CHECKS,
  preflight,
  type PreflightCheckName,
  type PreflightReport,
  type ScriptRunner,
} from '../src/preflight/preflight.ts'
import {
  FAILURE_FAMILIES,
  planSkillResources,
  type FailureFamily,
  type SkillBundle,
  type SkillPlan,
} from '../src/resources/planner.ts'

const FAMILY_LABEL: Readonly<Record<FailureFamily, string>> = {
  'unit-harmonization': 'unit harmonization',
  'codebook-parsing': 'codebook parsing',
  'spreadsheet-formula-validation': 'spreadsheet formula validation',
  'financial-reconciliation': 'financial definition reconciliation',
  'dialogue-graph-parsing': 'dialogue graph parsing',
}

function makeFinding(family: FailureFamily): Finding {
  return {
    id: findingId(`finding:${family}`),
    traceId: traceId(`trace:${family}`),
    detector: `detector-${family}`,
    confidence: 0.9,
    summary: `repeated ${FAMILY_LABEL[family]} failure`,
  }
}

function makeOperation(family: FailureFamily): Operation {
  return {
    id: operationId(`create:${family}`),
    kind: 'create',
    skillId: skillId(`skill-${family}`),
    findingId: findingId(`finding:${family}`),
    summary: `apply ${FAMILY_LABEL[family]} guidance`,
  }
}

function cleanPlan(family: FailureFamily = 'unit-harmonization'): SkillPlan {
  return planSkillResources({
    operation: makeOperation(family),
    finding: makeFinding(family),
    family,
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
      wallMs: 5,
    }
  },
}

function check(report: PreflightReport, name: PreflightCheckName) {
  return report.checks.find((row) => row.name === name)
}

function withFile(bundle: SkillBundle, path: string, content: string): SkillBundle {
  return { ...bundle, [path]: content }
}

function withoutFile(bundle: SkillBundle, path: string): SkillBundle {
  return Object.fromEntries(Object.entries(bundle).filter(([key]) => key !== path))
}

function resourcePath(plan: SkillPlan, kind: 'scripts' | 'references' | 'evals'): string {
  return plan.resources.find((row) => row.resource.kind === kind)!.resource.path
}

describe('executable preflight clean bundles', () => {
  for (const family of FAILURE_FAMILIES) {
    it(`accepts a clean, executable ${family} bundle`, async () => {
      const plan = cleanPlan(family)
      const report = await preflight({
        bundle: plan.bundle,
        plan,
        runner: passingRunner,
      })

      expect(report.verdict).toBe('accept')
      expect(report.rejectReasons).toEqual([])
      expect(report.repairReasons).toEqual([])
      expect(report.checks).toHaveLength(PREFLIGHT_CHECKS.length)
      expect(report.checks.every((row) => row.status === 'pass')).toBe(true)
      expect(check(report, 'script-execution')?.status).toBe('pass')
      expect(check(report, 'expected-outputs')?.status).toBe('pass')
      expect(report.metrics.scripts).toBe(
        plan.resources.filter((row) => row.resource.kind === 'scripts').length,
      )
      expect(report.metrics.fixtures).toBe(
        plan.resources.filter((row) => row.resource.kind === 'evals').length,
      )
    })
  }

  it('skips execution checks when no runner is supplied', async () => {
    const plan = cleanPlan()
    const report = await preflight({ bundle: plan.bundle, plan })
    expect(report.verdict).toBe('accept')
    expect(check(report, 'script-execution')?.status).toBe('skipped')
    expect(check(report, 'expected-outputs')?.status).toBe('skipped')
  })

  it('accepts an updated bundle that preserves authored resources', async () => {
    const family: FailureFamily = 'codebook-parsing'
    const created = cleanPlan(family)
    const operation: Operation = {
      ...makeOperation(family),
      id: operationId(`update:${family}`),
      kind: 'update',
    }
    const updated = planSkillResources({
      operation,
      finding: makeFinding(family),
      family,
      existingBundle: {
        ...created.bundle,
        'references/existing.md': '# Existing notes\n\nKeep this authored note.\n',
      },
    })
    const report = await preflight({
      bundle: updated.bundle,
      plan: updated,
      runner: passingRunner,
    })
    expect(report.verdict).toBe('accept')
    expect(check(report, 'planned-resources')?.status).toBe('pass')
    expect(check(report, 'unused-resources')?.status).toBe('pass')
  })
})

describe('executable preflight structural failures', () => {
  it('fails when a planned resource is missing from the bundle', async () => {
    const plan = cleanPlan()
    const report = await preflight({
      bundle: withoutFile(plan.bundle, resourcePath(plan, 'scripts')),
      plan,
      runner: passingRunner,
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'planned-resources')?.status).toBe('fail')
    expect(check(report, 'planned-resources')?.reasons.some(
      (row) => row.code === 'missing-planned-file',
    )).toBe(true)
  })

  it('fails on a path escape', async () => {
    const plan = cleanPlan()
    const report = await preflight({
      bundle: withFile(plan.bundle, '../evil.py', 'print("escape")\n'),
      plan,
      runner: passingRunner,
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'path-safety')?.status).toBe('fail')
  })

  it('fails on missing metadata', async () => {
    const plan = cleanPlan()
    const report = await preflight({
      bundle: withoutFile(plan.bundle, 'SKILL.md'),
      plan,
      runner: passingRunner,
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'metadata')?.status).toBe('fail')
    expect(check(report, 'directory-structure')?.status).toBe('fail')
  })
})

describe('executable preflight safety and execution failures', () => {
  it('fails on benchmark leakage or task-specific constants', async () => {
    const plan = cleanPlan()
    const referencePath = resourcePath(plan, 'references')
    const report = await preflight({
      bundle: withFile(
        plan.bundle,
        referencePath,
        `${plan.bundle[referencePath] ?? ''}\nanswer_key: 42\n`,
      ),
      plan,
      runner: passingRunner,
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'benchmark-leakage')?.status).toBe('fail')
  })

  it('fails when a script exits non-zero', async () => {
    const plan = cleanPlan()
    const failingRunner: ScriptRunner = {
      run: () => ({ exitCode: 2, stdout: '', stderr: 'fixture exploded', wallMs: 5 }),
    }
    const report = await preflight({
      bundle: plan.bundle,
      plan,
      runner: failingRunner,
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'script-execution')?.status).toBe('fail')
    expect(check(report, 'script-execution')?.reasons.some(
      (row) => row.code === 'script-failed',
    )).toBe(true)
  })

  it('fails when script output does not match the expected fixture schema', async () => {
    const plan = cleanPlan()
    const mismatchedRunner: ScriptRunner = {
      run: () => ({ exitCode: 0, stdout: '{"status":"ok"}', stderr: '', wallMs: 5 }),
    }
    const report = await preflight({
      bundle: plan.bundle,
      plan,
      runner: mismatchedRunner,
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'expected-outputs')?.status).toBe('fail')
    expect(check(report, 'expected-outputs')?.reasons.some(
      (row) => row.code === 'output-mismatch',
    )).toBe(true)
  })

  it('fails when execution is required but no runner is supplied', async () => {
    const plan = cleanPlan()
    const report = await preflight({
      bundle: plan.bundle,
      plan,
      policy: { requireScriptExecution: true },
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'script-execution')?.status).toBe('fail')
  })
})

describe('executable preflight budget and content checks', () => {
  it('fails when the prompt budget is too small', async () => {
    const plan = cleanPlan()
    const report = await preflight({
      bundle: plan.bundle,
      plan,
      runner: passingRunner,
      policy: { maximumPromptTokens: 10 },
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'prompt-budget')?.status).toBe('fail')
    expect(check(report, 'prompt-budget')?.reasons.some(
      (row) => row.code === 'prompt-too-large',
    )).toBe(true)
  })

  it('fails when tool-call or wall-time feasibility is exceeded', async () => {
    const plan = cleanPlan()
    const report = await preflight({
      bundle: plan.bundle,
      plan,
      runner: passingRunner,
      policy: { maximumToolCalls: 1, maximumWallMs: 1 },
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'tool-feasibility')?.status).toBe('fail')
    expect(check(report, 'tool-feasibility')?.reasons.some(
      (row) => row.code === 'tool-budget',
    )).toBe(true)
    expect(check(report, 'tool-feasibility')?.reasons.some(
      (row) => row.code === 'wall-budget',
    )).toBe(true)
  })

  it('fails on duplicate content', async () => {
    const plan = cleanPlan()
    const referencePath = resourcePath(plan, 'references')
    const report = await preflight({
      bundle: withFile(plan.bundle, referencePath, plan.bundle['SKILL.md'] ?? ''),
      plan,
      runner: passingRunner,
    })
    expect(report.verdict).toBe('reject')
    expect(check(report, 'duplicate-content')?.status).toBe('fail')
    expect(check(report, 'duplicate-content')?.reasons.some(
      (row) => row.code === 'duplicate-content',
    )).toBe(true)
  })

  it('warns or fails on an unused resource according to policy', async () => {
    const plan = cleanPlan()
    const bundle = withFile(
      plan.bundle,
      'references/orphan.md',
      '# Orphan notes\n\nThis file is never referenced by the skill or its resources.\n',
    )
    const warned = await preflight({ bundle, plan, runner: passingRunner })
    expect(warned.verdict).toBe('repair')
    expect(check(warned, 'unused-resources')?.status).toBe('warn')
    expect(warned.repairReasons.some((row) => row.code === 'unused-resource')).toBe(true)

    const rejected = await preflight({
      bundle,
      plan,
      runner: passingRunner,
      policy: { unusedResource: 'fail' },
    })
    expect(rejected.verdict).toBe('reject')
    expect(check(rejected, 'unused-resources')?.status).toBe('fail')
  })
})
