import { describe, expect, it } from 'vitest'

import {
  CLI_EMBEDDINGS,
  CLI_ROUTERS,
  CLI_STAGES,
  CliUsageError,
  DEFAULT_CLI_OPTIONS,
  HELP_TEXT,
  canonicalOptions,
  helpText,
  isCliOptionKey,
  parseArgs,
  parseCliArgs,
} from '../src/cli/args.ts'

const REQUIRED = [
  '--trace-file',
  'trace.jsonl',
  '--stage',
  'train',
  '--publish-root',
  'publish',
] as const

function usageIssues(argv: readonly string[]): CliUsageError {
  try {
    parseArgs(argv)
  } catch (error) {
    if (error instanceof CliUsageError) return error
    throw error
  }
  throw new Error('expected CliUsageError')
}

describe('CLI argument parsing', () => {
  it('parses every supported option into canonical names', () => {
    const options = parseArgs([
      '--trace-file', 'trace.jsonl',
      '--store', 'store',
      '--stage', 'validation',
      '--run-id', 'run-1',
      '--seed', '42',
      '--source-inventory', 'inventory.json',
      '--publish-root', 'publish',
      '--router', 'hybrid',
      '--embedding', 'qwen-http',
      '--embedding-url', 'http://127.0.0.1:9000/embed',
      '--model', 'deepseek-v4',
      '--budget-calls', '10',
      '--budget-tokens', '2000',
      '--budget-wall-seconds', '30',
      '--max-tool-calls', '7',
      '--dry-run',
      '--resume',
      '--json-out', 'report.json',
      '--report-md', 'report.md',
      '--abstain-threshold', '0.35',
    ])

    expect(options).toMatchObject({
      traceFile: 'trace.jsonl',
      jobDir: null,
      store: 'store',
      stage: 'validation',
      runId: 'run-1',
      seed: 42,
      sourceInventory: 'inventory.json',
      publishRoot: 'publish',
      router: 'hybrid',
      embedding: 'qwen-http',
      embeddingUrl: 'http://127.0.0.1:9000/embed',
      model: 'deepseek-v4',
      budgetCalls: 10,
      budgetTokens: 2000,
      budgetWallSeconds: 30,
      maxToolCalls: 7,
      dryRun: true,
      resume: true,
      jsonOut: 'report.json',
      reportMd: 'report.md',
      abstainThreshold: 0.35,
      help: false,
    })
  })

  it('produces the same canonical object for different flag orders', () => {
    const first = parseArgs([
      '--trace-file', 'trace.jsonl',
      '--stage', 'train',
      '--publish-root', 'publish',
      '--seed', '7',
      '--router=hybrid',
      '--resume',
    ])
    const second = parseArgs([
      '--router=hybrid',
      '--resume',
      '--seed=7',
      '--publish-root', 'publish',
      '--stage', 'train',
      '--trace-file', 'trace.jsonl',
    ])

    expect(first).toEqual(second)
    expect(Object.isFrozen(first)).toBe(true)
    expect(Object.keys(first)).toEqual([
      'traceFile',
      'jobDir',
      'store',
      'stage',
      'runId',
      'seed',
      'sourceInventory',
      'publishRoot',
      'router',
      'embedding',
      'embeddingUrl',
      'model',
      'budgetCalls',
      'budgetTokens',
      'budgetWallSeconds',
      'maxToolCalls',
      'dryRun',
      'resume',
      'jsonOut',
      'reportMd',
      'abstainThreshold',
      'help',
    ])
  })

  it('keeps absent optional values null instead of inventing defaults', () => {
    const options = parseArgs([...REQUIRED])
    expect(options.seed).toBeNull()
    expect(options.runId).toBeNull()
    expect(options.store).toBeNull()
    expect(options.budgetCalls).toBeNull()
    expect(options.abstainThreshold).toBeNull()
    expect(options.router).toBe('deterministic')
    expect(options.embedding).toBe('deterministic')
    expect(options.dryRun).toBe(false)
    expect(options.resume).toBe(false)
  })

  it('accepts --job-dir as the alternative source', () => {
    const options = parseArgs([
      '--job-dir', 'legacy-job',
      '--stage', 'train',
      '--publish-root', 'publish',
    ])
    expect(options.jobDir).toBe('legacy-job')
    expect(options.traceFile).toBeNull()
  })

  it('accepts --flag=value syntax', () => {
    const options = parseArgs([
      '--trace-file=trace.jsonl',
      '--stage=validation',
      '--publish-root=publish',
      '--seed=3',
      '--json-out=out.json',
    ])
    expect(options.traceFile).toBe('trace.jsonl')
    expect(options.stage).toBe('validation')
    expect(options.seed).toBe(3)
    expect(options.jsonOut).toBe('out.json')
  })

  it('prints help without demanding source, stage, or publish root', () => {
    const options = parseArgs(['--help'])
    expect(options.help).toBe(true)
    expect(options.stage).toBeNull()
    expect(helpText()).toBe(HELP_TEXT)
    for (const flag of [
      '--trace-file',
      '--job-dir',
      '--store',
      '--stage',
      '--run-id',
      '--seed',
      '--source-inventory',
      '--publish-root',
      '--router',
      '--embedding',
      '--embedding-url',
      '--model',
      '--budget-calls',
      '--budget-tokens',
      '--budget-wall-seconds',
      '--max-tool-calls',
      '--dry-run',
      '--resume',
      '--json-out',
      '--report-md',
      '--abstain-threshold',
      '--help',
    ]) {
      expect(HELP_TEXT).toContain(flag)
    }
  })

  it('allows a dry run without a publish root', () => {
    const options = parseArgs([
      '--job-dir', 'legacy-job',
      '--stage', 'train',
      '--dry-run',
    ])
    expect(options.publishRoot).toBeNull()
    expect(options.dryRun).toBe(true)
  })

  it('rejects unknown flags and positionals with structured issues', () => {
    expect(usageIssues([...REQUIRED, '--unknown']).issues[0]?.code).toBe('unknown-option')
    expect(usageIssues([...REQUIRED, 'stray']).issues[0]?.code).toBe('unexpected-argument')
    expect(usageIssues([...REQUIRED, '-x']).issues[0]?.code).toBe('unexpected-argument')
  })

  it('rejects duplicate flags once, without treating their value as positional', () => {
    const error = usageIssues([...REQUIRED, '--seed', '3', '--seed', '4'])
    expect(error.issues.map((item) => item.code)).toEqual(['duplicate-option'])
    expect(error.issues[0]?.option).toBe('--seed')
  })

  it('rejects boolean switches with an attached value', () => {
    expect(usageIssues([...REQUIRED, '--dry-run=true']).issues[0]?.code)
      .toBe('unexpected-value')
  })

  it('rejects missing values and empty values', () => {
    expect(usageIssues([...REQUIRED, '--seed']).issues[0]?.code).toBe('missing-value')
    expect(usageIssues([...REQUIRED, '--run-id=']).issues[0]?.code).toBe('missing-value')
    expect(usageIssues([...REQUIRED, '--seed', '--dry-run']).issues[0]?.code)
      .toBe('missing-value')
  })

  it('requires exactly one source', () => {
    const neither = usageIssues([
      '--stage', 'train',
      '--publish-root', 'publish',
    ])
    expect(neither.issues.map((item) => item.code)).toEqual(['missing-required-option'])

    const both = usageIssues([
      '--trace-file', 'trace.jsonl',
      '--job-dir', 'legacy-job',
      '--stage', 'train',
      '--publish-root', 'publish',
    ])
    expect(both.issues.map((item) => item.code)).toEqual(['conflicting-options'])
  })

  it('requires an explicit train or validation stage', () => {
    const error = usageIssues([
      '--trace-file', 'trace.jsonl',
      '--publish-root', 'publish',
    ])
    expect(error.issues.map((item) => item.option)).toContain('--stage')
    expect(usageIssues([
      '--trace-file', 'trace.jsonl',
      '--stage', 'holdout',
      '--publish-root', 'publish',
    ]).issues[0]?.code).toBe('invalid-value')
  })

  it('requires a publish root outside a dry run', () => {
    const error = usageIssues([
      '--trace-file', 'trace.jsonl',
      '--stage', 'validation',
    ])
    expect(error.issues.map((item) => item.option)).toContain('--publish-root')
    expect(error.issues[0]?.code).toBe('missing-required-option')
  })

  it('requires positive safe integers for seeds and budgets', () => {
    for (const flag of [
      '--seed',
      '--budget-calls',
      '--budget-tokens',
      '--budget-wall-seconds',
      '--max-tool-calls',
    ]) {
      for (const value of ['0', '-1', '1.5', '01', '999999999999999999999']) {
        const error = usageIssues([...REQUIRED, flag, value])
        expect(error.issues[0]?.code).toBe('invalid-value')
        expect(error.issues[0]?.option).toBe(flag)
      }
    }
  })

  it('accepts boundary abstention thresholds and rejects out-of-range values', () => {
    expect(parseArgs([...REQUIRED, '--abstain-threshold', '0']).abstainThreshold).toBe(0)
    expect(parseArgs([...REQUIRED, '--abstain-threshold', '1']).abstainThreshold).toBe(1)
    for (const value of ['-0.1', '1.1', 'NaN', 'nope']) {
      expect(usageIssues([...REQUIRED, '--abstain-threshold', value]).issues[0]?.code)
        .toBe('invalid-value')
    }
  })

  it('rejects unsupported enum values', () => {
    for (const [flag, value] of [
      ['--router', 'magic'],
      ['--embedding', 'openai'],
    ] as const) {
      const error = usageIssues([...REQUIRED, flag, value])
      expect(error.issues[0]?.code).toBe('invalid-value')
      expect(error.issues[0]?.message).toContain(value)
    }
  })

  it('exposes the supported enum sets', () => {
    expect(CLI_STAGES).toEqual(['train', 'validation'])
    expect(CLI_ROUTERS).toEqual(['deterministic', 'dsh', 'hybrid'])
    expect(CLI_EMBEDDINGS).toEqual(['deterministic', 'qwen-http'])
  })

  it('supports the parseCliArgs alias and canonical builders', () => {
    expect(parseCliArgs([...REQUIRED])).toEqual(parseArgs([...REQUIRED]))
    expect(DEFAULT_CLI_OPTIONS.stage).toBeNull()
    const options = canonicalOptions({ stage: 'validation', seed: 9 })
    expect(options.stage).toBe('validation')
    expect(options.seed).toBe(9)
    expect(options.publishRoot).toBeNull()
    expect(Object.isFrozen(options)).toBe(true)
    expect(isCliOptionKey('traceFile')).toBe(true)
    expect(isCliOptionKey('--trace-file')).toBe(false)
  })
})
