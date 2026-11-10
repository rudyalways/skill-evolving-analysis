import { describe, expect, it } from 'vitest'
import type { Finding, VerificationEvidence } from '../src/contracts/evidence.ts'
import { findingId, operationId, skillId, traceId } from '../src/contracts/ids.ts'
import type { Operation, OperationKind } from '../src/contracts/operations.ts'
import { isRecord } from '../src/contracts/validation.ts'
import {
  FAILURE_FAMILIES,
  planSkillResources,
  type FailureFamily,
  type SkillBundle,
  type SkillPlan,
} from '../src/resources/planner.ts'
import { preflight } from '../src/preflight/preflight.ts'
import {
  ReplayVerifier,
  SubprocessScriptRunner,
  hashText,
  type IsolatedScriptRequest,
  type IsolatedScriptResult,
  type ReplayScriptRunner,
} from '../src/verification/replay-verifier.ts'

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

function makeOperation(family: FailureFamily, kind: OperationKind = 'create'): Operation {
  return {
    id: operationId(`${kind}:${family}`),
    kind,
    skillId: skillId(`skill-${family}`),
    findingId: findingId(`finding:${family}`),
    summary: `apply ${FAMILY_LABEL[family]} guidance`,
  }
}

function planFor(family: FailureFamily): SkillPlan {
  return planSkillResources({
    operation: makeOperation(family),
    finding: makeFinding(family),
    family,
  })
}

function scriptPathOf(plan: SkillPlan): string {
  const row = plan.resources.find((resource) => resource.resource.kind === 'scripts')
  if (row === undefined) throw new Error('plan has no script')
  return row.resource.path
}

function fixturePathOf(plan: SkillPlan): string {
  const row = plan.resources.find((resource) => resource.resource.kind === 'evals')
  if (row === undefined) throw new Error('plan has no fixture')
  return row.resource.path
}

function replaceFile(bundle: SkillBundle, path: string, content: string): SkillBundle {
  return { ...bundle, [path]: content }
}

function detailsOf(evidence: VerificationEvidence): Readonly<Record<string, unknown>> {
  if (evidence.details === undefined) throw new Error('evidence has no details')
  return evidence.details
}

function runsOf(evidence: VerificationEvidence): readonly Readonly<Record<string, unknown>>[] {
  const runs = detailsOf(evidence).runs
  if (!Array.isArray(runs)) throw new Error('evidence has no runs array')
  const records: Readonly<Record<string, unknown>>[] = []
  for (const run of runs) {
    if (!isRecord(run)) throw new Error('run record is not an object')
    records.push(run)
  }
  return records
}

function reasonsOf(evidence: VerificationEvidence): readonly Readonly<Record<string, unknown>>[] {
  const reasons = detailsOf(evidence).reasons
  if (!Array.isArray(reasons)) throw new Error('evidence has no reasons array')
  const records: Readonly<Record<string, unknown>>[] = []
  for (const reason of reasons) {
    if (!isRecord(reason)) throw new Error('reason is not an object')
    records.push(reason)
  }
  return records
}

function codesOf(evidence: VerificationEvidence, key: 'repairableReasons' | 'terminalReasons'): readonly string[] {
  const value = detailsOf(evidence)[key]
  if (!Array.isArray(value)) return []
  return value.filter((entry): entry is string => typeof entry === 'string')
}

function areasOf(evidence: VerificationEvidence): readonly string[] {
  return reasonsOf(evidence)
    .filter((reason) => typeof reason.area === 'string')
    .map((reason) => String(reason.area))
}

function result(overrides: Partial<IsolatedScriptResult> = {}): IsolatedScriptResult {
  return {
    exitCode: 0,
    signal: null,
    stdout: '{}',
    stderr: '',
    wallMs: 1,
    timedOut: false,
    stdoutBytes: 2,
    stderrBytes: 0,
    stdoutTruncated: false,
    stderrTruncated: false,
    outputLimitExceeded: false,
    outputHash: hashText('{}'),
    stderrHash: hashText(''),
    ...overrides,
  }
}

/** A runner that records requests and never spawns a process. */
class RecordingRunner implements ReplayScriptRunner {
  readonly requests: IsolatedScriptRequest[] = []

  constructor(private readonly reply: IsolatedScriptResult = result()) {}

  async run(request: IsolatedScriptRequest): Promise<IsolatedScriptResult> {
    this.requests.push(request)
    return this.reply
  }
}

const runner = new SubprocessScriptRunner({ maximumWallMs: 3000 })

describe('ReplayVerifier executable planner bundles', () => {
  for (const family of FAILURE_FAMILIES) {
    it(`passes a generated, executable ${family} bundle`, async () => {
      const plan = planFor(family)
      const verifier = new ReplayVerifier({ runner })
      const evidence = await verifier.verify(makeOperation(family), { plan })

      expect(evidence.status).toBe('pass')
      expect(evidence.summary).toContain('verified')
      const runs = runsOf(evidence)
      expect(runs).toHaveLength(
        plan.resources.filter((row) => row.resource.kind === 'scripts').length * 2,
      )
      expect(detailsOf(evidence).repairableReasons).toEqual([])
      expect(detailsOf(evidence).terminalReasons).toEqual([])
      for (const run of runs) {
        expect(run.exitCode).toBe(0)
        expect(run.parsed).toBe(true)
        expect(run.expectedMatched).toBe(true)
        expect(typeof run.outputHash).toBe('string')
        expect(String(run.outputHash)).toHaveLength(64)
        expect(typeof run.durationMs).toBe('number')
        expect(String(run.stdoutHash)).toHaveLength(64)
        expect(String(run.stderrHash)).toHaveLength(64)
      }
      expect(runs[0]?.outputHash).toBe(runs[1]?.outputHash)
    }, 30_000)
  }

  it('accepts plan context supplied to the constructor through the Verifier boundary', async () => {
    const plan = planFor('unit-harmonization')
    const verifier = new ReplayVerifier({ runner, plan })
    const evidence = await verifier.verify(makeOperation('unit-harmonization'))
    expect(evidence.status).toBe('pass')
  })

  it('consumes an accepted preflight report and rejects a mismatched receipt', async () => {
    const plan = planFor('unit-harmonization')
    const report = await preflight({ bundle: plan.bundle, plan })
    expect(report.verdict).toBe('accept')

    const accepted = await new ReplayVerifier({ runner }).verify(
      makeOperation('unit-harmonization'),
      { plan, preflight: report },
    )
    expect(accepted.status).toBe('pass')

    const spy = new RecordingRunner()
    const mismatched = await new ReplayVerifier({ runner: spy }).verify(
      makeOperation('unit-harmonization'),
      {
        plan,
        preflight: report,
        preflightReceipt: { verdict: 'accept', reportHash: 'not-the-report-hash' },
      },
    )
    expect(mismatched.status).toBe('fail')
    expect(codesOf(mismatched, 'terminalReasons')).toContain('preflight-receipt-mismatch')
    expect(spy.requests).toEqual([])
  })
})

describe('ReplayVerifier execution failures', () => {
  it('returns fail when a script exits non-zero', async () => {
    const plan = planFor('unit-harmonization')
    const path = scriptPathOf(plan)
    const bundle = replaceFile(
      plan.bundle,
      path,
      'import sys\nsys.stderr.write("fixture exploded\\n")\nsys.exit(3)\n',
    )
    const evidence = await new ReplayVerifier({ runner }).verify(
      makeOperation('unit-harmonization'),
      { plan, bundle },
    )

    expect(evidence.status).toBe('fail')
    expect(codesOf(evidence, 'terminalReasons')).toContain('script-failed')
    const runs = runsOf(evidence)
    expect(runs).toHaveLength(1)
    expect(runs[0]?.exitCode).toBe(3)
    expect(String(runs[0]?.stderr)).toContain('fixture exploded')
  })

  it('marks an expected-output mismatch repairable', async () => {
    const plan = planFor('unit-harmonization')
    const path = scriptPathOf(plan)
    const bundle = replaceFile(
      plan.bundle,
      path,
      'import json\nprint(json.dumps({"status": "issues", "normalized": []}))\n',
    )
    const evidence = await new ReplayVerifier({ runner }).verify(
      makeOperation('unit-harmonization'),
      { plan, bundle },
    )

    expect(evidence.status).toBe('fail')
    expect(codesOf(evidence, 'repairableReasons')).toContain('output-mismatch')
    expect(codesOf(evidence, 'terminalReasons')).toEqual([])
    expect(runsOf(evidence)).toHaveLength(2)
    expect(areasOf(evidence)).toContain('output')
  })

  it('returns efficiency_failure when a script exceeds its wall limit', async () => {
    const plan = planFor('unit-harmonization')
    const path = scriptPathOf(plan)
    const bundle = replaceFile(
      plan.bundle,
      path,
      'import time\ntime.sleep(2)\nprint("{}")\n',
    )
    const evidence = await new ReplayVerifier({
      runner: new SubprocessScriptRunner({ maximumWallMs: 3000 }),
    }).verify(makeOperation('unit-harmonization'), {
      plan,
      bundle,
      limits: { scriptTimeoutMs: 100, maximumTotalWallMs: 60_000 },
    })

    expect(evidence.status).toBe('efficiency_failure')
    expect(codesOf(evidence, 'repairableReasons')).toContain('script-timeout')
    expect(areasOf(evidence)).toContain('efficiency')
    const runs = runsOf(evidence)
    expect(runs).toHaveLength(1)
    expect(runs[0]?.timedOut).toBe(true)
  })

  it('returns efficiency_failure when stdout exceeds the output limit', async () => {
    const plan = planFor('unit-harmonization')
    const path = scriptPathOf(plan)
    const bundle = replaceFile(plan.bundle, path, 'print("x" * 200000)\n')
    const evidence = await new ReplayVerifier({
      runner: new SubprocessScriptRunner({ maximumStdoutBytes: 256 }),
    }).verify(makeOperation('unit-harmonization'), {
      plan,
      bundle,
      limits: { maximumStdoutBytes: 256 },
    })

    expect(evidence.status).toBe('efficiency_failure')
    expect(codesOf(evidence, 'repairableReasons')).toContain('output-limit')
    const runs = runsOf(evidence)
    expect(runs).toHaveLength(1)
    expect(runs[0]?.outputLimitExceeded).toBe(true)
    expect(runs[0]?.stdoutTruncated).toBe(true)
  })

  it('returns efficiency_failure when the process budget is too small', async () => {
    const plan = planFor('codebook-parsing')
    const spy = new RecordingRunner()
    const evidence = await new ReplayVerifier({ runner: spy }).verify(
      makeOperation('codebook-parsing'),
      { plan, limits: { maximumProcesses: 1 } },
    )

    expect(evidence.status).toBe('efficiency_failure')
    expect(codesOf(evidence, 'repairableReasons')).toContain('process-budget')
    expect(spy.requests).toEqual([])
  })
})

describe('ReplayVerifier determinism', () => {
  it('records identical output hashes for repeated deterministic runs', async () => {
    const plan = planFor('unit-harmonization')
    const evidence = await new ReplayVerifier({ runner }).verify(
      makeOperation('unit-harmonization'),
      { plan },
    )

    const runs = runsOf(evidence)
    expect(runs).toHaveLength(2)
    expect(runs[0]?.outputHash).toBe(runs[1]?.outputHash)
    expect(runs[0]?.stdoutHash).toBe(runs[1]?.stdoutHash)
  })

  it('marks differing repeat output as a repairable determinism failure', async () => {
    const plan = planFor('unit-harmonization')
    const scriptPath = scriptPathOf(plan)
    const fixturePath = fixturePathOf(plan)
    const bundle = replaceFile(
      plan.bundle,
      scriptPath,
      'import json, time\nprint(json.dumps({"status": "ok", "nonce": time.time_ns()}))\n',
    )
    const narrowed = replaceFile(
      bundle,
      fixturePath,
      `${JSON.stringify({
        schemaVersion: 1,
        script: scriptPath,
        input: {},
        expect: { status: 'ok' },
      }, null, 2)}\n`,
    )
    const evidence = await new ReplayVerifier({ runner }).verify(
      makeOperation('unit-harmonization'),
      { plan, bundle: narrowed },
    )

    expect(evidence.status).toBe('fail')
    expect(codesOf(evidence, 'repairableReasons')).toContain('nondeterministic-output')
    const runs = runsOf(evidence)
    expect(runs).toHaveLength(2)
    expect(runs[0]?.outputHash).not.toBe(runs[1]?.outputHash)
  })
})

describe('ReplayVerifier safety boundaries', () => {
  it('rejects a path escape before spawning any process', async () => {
    const plan = planFor('unit-harmonization')
    const spy = new RecordingRunner()
    const bundle = replaceFile(plan.bundle, '../evil.py', 'print("escape")\n')
    const evidence = await new ReplayVerifier({ runner: spy }).verify(
      makeOperation('unit-harmonization'),
      { plan, bundle },
    )

    expect(evidence.status).toBe('fail')
    expect(codesOf(evidence, 'terminalReasons').length).toBeGreaterThan(0)
    expect(areasOf(evidence)).toContain('safety')
    expect(spy.requests).toEqual([])
    expect(runsOf(evidence)).toEqual([])
  })

  it('refuses a network client without attempting a network call', async () => {
    const plan = planFor('unit-harmonization')
    const scriptPath = scriptPathOf(plan)
    const spy = new RecordingRunner()
    const bundle = replaceFile(
      plan.bundle,
      scriptPath,
      'import urllib.request\nprint("{}")\n',
    )
    const evidence = await new ReplayVerifier({ runner: spy }).verify(
      makeOperation('unit-harmonization'),
      { plan, bundle },
    )

    expect(evidence.status).toBe('fail')
    expect(codesOf(evidence, 'terminalReasons')).toContain('network-not-allowed')
    expect(areasOf(evidence)).toContain('safety')
    expect(spy.requests).toEqual([])
    expect(runsOf(evidence)).toEqual([])
  })

  it('rejects benchmark leakage and task-specific constants', async () => {
    const plan = planFor('financial-reconciliation')
    const referencePath = plan.resources.find(
      (row) => row.resource.kind === 'references',
    )?.resource.path
    if (referencePath === undefined) throw new Error('plan has no reference')
    const bundle = replaceFile(
      plan.bundle,
      referencePath,
      `${plan.bundle[referencePath] ?? ''}\nanswer_key: 42\n`,
    )
    const evidence = await new ReplayVerifier({ runner }).verify(
      makeOperation('financial-reconciliation'),
      { plan, bundle },
    )

    expect(evidence.status).toBe('fail')
    expect(codesOf(evidence, 'repairableReasons')).toContain('answer-key')
    expect(areasOf(evidence)).toContain('leakage')
  })

  it('rejects an unresolved bundle reference', async () => {
    const plan = planFor('codebook-parsing')
    const referencePath = plan.resources.find(
      (row) => row.resource.kind === 'references',
    )?.resource.path
    if (referencePath === undefined) throw new Error('plan has no reference')
    const bundle = replaceFile(
      plan.bundle,
      referencePath,
      `${plan.bundle[referencePath] ?? ''}\nSee scripts/missing.py for details.\n`,
    )
    const evidence = await new ReplayVerifier({ runner }).verify(
      makeOperation('codebook-parsing'),
      { plan, bundle },
    )

    expect(evidence.status).toBe('fail')
    expect(codesOf(evidence, 'repairableReasons')).toContain('unresolved-reference')
    expect(areasOf(evidence)).toContain('reference')
  })

  it('fails terminal when no plan or bundle context is supplied', async () => {
    const evidence = await new ReplayVerifier({ runner }).verify(
      makeOperation('unit-harmonization'),
    )
    expect(evidence.status).toBe('fail')
    expect(codesOf(evidence, 'terminalReasons')).toContain('missing-context')
  })
})
