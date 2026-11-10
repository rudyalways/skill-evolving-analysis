import { describe, expect, it } from 'vitest'
import type { Finding } from '../src/contracts/evidence.ts'
import { findingId, skillId, traceId, operationId } from '../src/contracts/ids.ts'
import type { Operation, OperationKind } from '../src/contracts/operations.ts'
import {
  FAILURE_FAMILIES,
  InvalidResourcePlanError,
  classifyFailureFamily,
  planSkillResources,
  scanContentForLeakage,
  validateResourcePath,
  type FailureFamily,
  type SkillPlanningRequest,
} from '../src/resources/planner.ts'

const FAMILY_LABEL: Readonly<Record<FailureFamily, string>> = {
  'unit-harmonization': 'unit harmonization',
  'codebook-parsing': 'codebook parsing',
  'spreadsheet-formula-validation': 'spreadsheet formula validation',
  'financial-reconciliation': 'financial definition reconciliation',
  'dialogue-graph-parsing': 'dialogue graph parsing',
  'network-forensics': 'network forensics',
  'data-visualization': 'data visualization',
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

function makeOperation(family: FailureFamily, kind: OperationKind = 'create'): Operation {
  return {
    id: operationId(`${kind}:${family}`),
    kind,
    skillId: skillId(`skill-${family}`),
    findingId: findingId(`finding:${family}`),
    summary: `apply ${FAMILY_LABEL[family]} guidance`,
  }
}

function makeRequest(
  family: FailureFamily,
  kind: OperationKind = 'create',
): SkillPlanningRequest {
  return {
    operation: makeOperation(family, kind),
    finding: makeFinding(family),
    family,
  }
}

describe('resource planner failure families', () => {
  for (const family of FAILURE_FAMILIES) {
    it(`plans justified, renderable resources for ${family}`, () => {
      const plan = planSkillResources(makeRequest(family))
      const paths = plan.resources.map((row) => row.resource.path)

      expect(plan.family).toBe(family)
      expect(plan.mode).toBe('create')
      expect(plan.bundle['SKILL.md']).toBeDefined()
      expect(plan.bundle[plan.skill.path]).toBeDefined()
      expect(paths).toHaveLength(family === 'spreadsheet-formula-validation' ? 5 : 3)
      expect(paths.some((path) => path.startsWith('scripts/'))).toBe(true)
      expect(paths.some((path) => path.startsWith('references/'))).toBe(true)
      expect(paths.some((path) => path.startsWith('evals/'))).toBe(true)
      expect(paths.some((path) => path.startsWith('assets/'))).toBe(false)
      expect(new Set(paths).size).toBe(paths.length)
      expect(paths).not.toContain(plan.skill.path)

      for (const path of [plan.skill.path, ...paths]) {
        expect(validateResourcePath(path)).toEqual([])
      }
      for (const [path, content] of Object.entries(plan.bundle)) {
        expect(scanContentForLeakage(path, content)).toEqual([])
      }

      expect(plan.resources.every((row) => row.provenance.family === family)).toBe(true)
      expect(plan.resources.every((row) => row.provenance.traceId === makeFinding(family).traceId)).toBe(true)
      expect(plan.resources.every((row) => row.provenance.rationale.length > 0)).toBe(true)
      expect(plan.resources.every((row) => row.usefulness.rationale.length > 0)).toBe(true)
      expect(plan.skill.provenance.findingId).toBe(makeFinding(family).id)
      expect(plan.provenance.operationId).toBe(makeOperation(family).id)

      expect(planSkillResources(makeRequest(family))).toEqual(plan)
    })
  }

  it('classifies every supported family from finding language', () => {
    for (const family of FAILURE_FAMILIES) {
      expect(classifyFailureFamily(makeFinding(family))).toBe(family)
    }
  })
})

describe('resource planner assets', () => {
  it('does not fabricate assets without an explicit reusable template', () => {
    const plan = planSkillResources(makeRequest('financial-reconciliation'))
    expect(plan.resources.some((row) => row.resource.kind === 'assets')).toBe(false)
  })

  it('adds a justified reusable output template with provenance', () => {
    const plan = planSkillResources({
      ...makeRequest('financial-reconciliation'),
      outputTemplate: {
        path: 'assets/reconciliation-report.md',
        content: '# Reconciliation report\n\n- Definition\n- Value\n- Evidence\n',
        rationale: 'Teams reuse this report shape for every reconciliation task.',
      },
    })
    const asset = plan.resources.find(
      (row) => row.resource.path === 'assets/reconciliation-report.md',
    )
    expect(asset?.resource.kind).toBe('assets')
    expect(asset?.provenance.rationale).toContain('reuse')
    expect(plan.bundle['SKILL.md']).toContain('assets/reconciliation-report.md')
  })

  it('rejects a template outside assets or without a reuse rationale', () => {
    expect(() => planSkillResources({
      ...makeRequest('unit-harmonization'),
      outputTemplate: {
        path: 'scripts/report.md',
        content: '# Report\n',
        rationale: 'reused output shape',
      },
    })).toThrow(InvalidResourcePlanError)
    expect(() => planSkillResources({
      ...makeRequest('unit-harmonization'),
      outputTemplate: {
        path: 'assets/report.md',
        content: '# Report\n',
        rationale: '   ',
      },
    })).toThrow(InvalidResourcePlanError)
  })
})

describe('resource planner path bounds', () => {
  it('rejects escaping, absolute, unbounded, and malformed paths', () => {
    const rejected = [
      '../evil.sh',
      '/etc/passwd',
      'C:\\temp\\evil.py',
      'scripts/../../evil.py',
      'scripts//empty.py',
      'scripts/a/b/c/d.py',
      'scripts/.hidden.py',
      'scripts/guard.txt',
    ]
    for (const path of rejected) {
      expect(validateResourcePath(path).length).toBeGreaterThan(0)
    }
    expect(validateResourcePath('SKILL.md')).toEqual([])
    expect(validateResourcePath('README.md')).toEqual([])
    expect(validateResourcePath('scripts/harmonize.py')).toEqual([])
    expect(validateResourcePath('evals/fixtures/safe.json')).toEqual([])
  })

  it('rejects an escaped output-template path', () => {
    expect(() => planSkillResources({
      ...makeRequest('codebook-parsing'),
      outputTemplate: {
        path: 'assets/../../evil.md',
        content: '# Report\n',
        rationale: 'reused output shape',
      },
    })).toThrow(InvalidResourcePlanError)
  })
})

describe('resource planner update and merge', () => {
  it('updates an existing bundle without dropping authored files', () => {
    const family: FailureFamily = 'codebook-parsing'
    const created = planSkillResources(makeRequest(family))
    const plan = planSkillResources({
      operation: makeOperation(family, 'update'),
      finding: makeFinding(family),
      family,
      existingBundle: {
        ...created.bundle,
        'references/existing.md': '# Existing notes\n\nKeep this authored note.\n',
      },
    })

    expect(plan.mode).toBe('update')
    expect(plan.bundle['references/existing.md']).toContain('Keep this authored note.')
    expect(plan.bundle['SKILL.md']).toContain('references/existing.md')
    const existing = plan.resources.find(
      (row) => row.resource.path === 'references/existing.md',
    )
    expect(existing?.resource.status).toBe('used')
  })

  it('is idempotent when updating an already-current bundle', () => {
    const family: FailureFamily = 'unit-harmonization'
    const created = planSkillResources(makeRequest(family))
    const updated = planSkillResources({
      operation: makeOperation(family, 'update'),
      finding: makeFinding(family),
      family,
      existingBundle: created.bundle,
    })

    expect(updated.bundle).toEqual(created.bundle)
    expect(updated.skill.status).toBe('used')
    expect(updated.resources.every((row) => row.resource.status === 'used')).toBe(true)
  })

  it('merges without overwriting a conflicting authored resource', () => {
    const family: FailureFamily = 'unit-harmonization'
    const created = planSkillResources(makeRequest(family))
    const scriptPath = created.resources.find(
      (row) => row.resource.kind === 'scripts',
    )!.resource.path
    const authored = '#!/usr/bin/env python3\nprint("authored")\n'
    const existingBundle = { ...created.bundle, [scriptPath]: authored }

    const merged = planSkillResources({
      operation: makeOperation(family, 'merge'),
      finding: makeFinding(family),
      family,
      existingBundle,
    })
    expect(merged.mode).toBe('merge')
    expect(merged.bundle[scriptPath]).toBe(authored)
    expect(
      merged.resources.find((row) => row.resource.path === scriptPath)?.resource.status,
    ).toBe('used')

    const updated = planSkillResources({
      operation: makeOperation(family, 'update'),
      finding: makeFinding(family),
      family,
      existingBundle,
    })
    expect(updated.bundle[scriptPath]).toBe(created.bundle[scriptPath])
  })

  it('rejects unsupported operation kinds', () => {
    expect(() => planSkillResources(makeRequest('unit-harmonization', 'delete')))
      .toThrow(InvalidResourcePlanError)
    expect(() => planSkillResources(makeRequest('unit-harmonization', 'split')))
      .toThrow(InvalidResourcePlanError)
  })
})

describe('resource planner provenance and usefulness', () => {
  it('records observed use evidence for existing resources', () => {
    const family: FailureFamily = 'financial-reconciliation'
    const created = planSkillResources(makeRequest(family))
    const referencePath = created.resources.find(
      (row) => row.resource.kind === 'references',
    )!.resource.path
    const plan = planSkillResources({
      operation: makeOperation(family, 'update'),
      finding: makeFinding(family),
      family,
      existingBundle: created.bundle,
      usefulness: [{
        path: referencePath,
        uses: 3,
        rationale: 'observed in three prior traces',
      }],
    })
    const row = plan.resources.find((entry) => entry.resource.path === referencePath)!
    expect(row.usefulness.classification).toBe('observed-used')
    expect(row.usefulness.uses).toBe(3)
    expect(row.usefulness.rationale).toContain('three')
  })
})

describe('resource planner leakage safety', () => {
  it('detects benchmark answers and hard-coded task identifiers', () => {
    expect(scanContentForLeakage('scripts/leak.py', 'answer_key = "42"\n')
      .map((leak) => leak.code)).toContain('answer-key')
    expect(scanContentForLeakage('scripts/leak.py', 'TASK_ID = "bench-0042"\n')
      .map((leak) => leak.code)).toContain('task-specific-constant')
    expect(scanContentForLeakage('references/leak.md', 'See gsm8k solution.\n')
      .map((leak) => leak.code)).toContain('named-benchmark')
    expect(scanContentForLeakage('evals/leak.json', '{"expected_answer": 42}')
      .map((leak) => leak.code)).toContain('expected-answer')
  })

  it('does not flag legitimate expected-output prose', () => {
    expect(scanContentForLeakage(
      'references/guide.md',
      'Compare the expected output with the safe fixture before using a derived value.\n',
    )).toEqual([])
  })

  it('rejects a template that embeds benchmark leakage', () => {
    expect(() => planSkillResources({
      ...makeRequest('unit-harmonization'),
      outputTemplate: {
        path: 'assets/report.md',
        content: '# Report\n\nexpected_answer: 1\n',
        rationale: 'reused report shape',
      },
    })).toThrow(InvalidResourcePlanError)
  })

  it('does not embed task-specific constants in generated content', () => {
    for (const family of FAILURE_FAMILIES) {
      const plan = planSkillResources(makeRequest(family))
      const text = Object.values(plan.bundle).join('\n')
      expect(text).not.toMatch(/expected_answer|answer_key|ground_truth|gsm8k|humaneval|bench-\d{2,}/i)
    }
  })
})
