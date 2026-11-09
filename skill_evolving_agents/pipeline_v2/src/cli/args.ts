/**
 * Production command-line parsing for the v2 experiment runner.
 *
 * The parser deliberately does not use a third-party dependency and does not
 * resolve any path against the current working directory.  A parsed option
 * object is therefore a pure function of the argument vector: the same flags
 * in a different order produce the same frozen object.
 *
 * Parsing has three stages:
 *
 * 1. tokenize `--flag`, `--flag=value`, and the `--` terminator;
 * 2. reject unknown, duplicated, malformed, and positional arguments;
 * 3. enforce the cross-option contract (source selection, stage, publish root).
 *
 * All failures are collected into one structured `CliUsageError` so a CLI can
 * print every problem in a single pass instead of failing one flag at a time.
 */

import { PipelineError } from '../contracts/errors.ts'

/** Experimental stages accepted by the command line. */
export const CLI_STAGES = ['train', 'validation'] as const

/** Supported routing modes. */
export const CLI_ROUTERS = ['deterministic', 'dsh', 'hybrid'] as const

/** Supported embedding providers. */
export const CLI_EMBEDDINGS = ['deterministic', 'qwen-http'] as const

/** A train or validation experiment stage. */
export type CliStage = (typeof CLI_STAGES)[number]

/** A router implementation selected on the command line. */
export type CliRouter = (typeof CLI_ROUTERS)[number]

/** An embedding provider selected on the command line. */
export type CliEmbedding = (typeof CLI_EMBEDDINGS)[number]

/**
 * Canonical parsed options.
 *
 * Absent scalar options are `null` rather than silently defaulted to a value
 * the user did not request.  Boolean switches default to `false`, and the two
 * provider modes have explicit, deterministic defaults.
 */
export interface CliOptions {
  readonly traceFile: string | null
  readonly jobDir: string | null
  readonly store: string | null
  readonly stage: CliStage | null
  readonly runId: string | null
  readonly seed: number | null
  readonly sourceInventory: string | null
  readonly publishRoot: string | null
  readonly router: CliRouter
  readonly embedding: CliEmbedding
  readonly embeddingUrl: string | null
  readonly model: string | null
  readonly budgetCalls: number | null
  readonly budgetTokens: number | null
  readonly budgetWallSeconds: number | null
  readonly maxToolCalls: number | null
  readonly dryRun: boolean
  readonly resume: boolean
  readonly jsonOut: string | null
  readonly reportMd: string | null
  readonly abstainThreshold: number | null
  readonly help: boolean
}

/** Stable code for one command-line problem. */
export type CliUsageErrorCode =
  | 'unknown-option'
  | 'duplicate-option'
  | 'missing-value'
  | 'unexpected-value'
  | 'unexpected-argument'
  | 'invalid-value'
  | 'missing-required-option'
  | 'conflicting-options'

/** One structured command-line problem. */
export interface CliUsageIssue {
  readonly code: CliUsageErrorCode
  /** Canonical long flag, when the issue belongs to one option. */
  readonly option: string | null
  readonly message: string
}

/** A command line that violates the supported option contract. */
export class CliUsageError extends PipelineError {
  readonly issues: readonly CliUsageIssue[]

  constructor(issues: readonly CliUsageIssue[]) {
    super('invalid-cli-usage', 'invalid command-line arguments', { issues })
    this.issues = issues
  }
}

/** Help text for the experiment CLI. */
export const HELP_TEXT = `Usage: skill-evolving-run [options]

Run one train or validation experiment over a trace file or legacy job directory.

Source (exactly one is required):
  --trace-file <path>        Trace file to replay.
  --job-dir <path>           Legacy job directory to read.
  --source-inventory <path>  Inventory describing available source material.
  --store <path>             Durable study-store directory.

Experiment:
  --stage <stage>            Required. One of: train, validation.
  --run-id <id>              Stable run identity.
  --seed <integer>           Positive integer seed.
  --publish-root <path>      Publication root. Required unless --dry-run.
  --resume                   Resume an existing run when possible.
  --dry-run                  Validate and report without publishing.
  --abstain-threshold <n>    Router abstention threshold in [0, 1].

Providers:
  --router <mode>            deterministic | dsh | hybrid (default: deterministic).
  --embedding <mode>         deterministic | qwen-http (default: deterministic).
  --embedding-url <url>      Endpoint for the qwen-http embedding provider.
  --model <name>             Model identifier for provider-backed modes.

Budgets (positive integers):
  --budget-calls <n>         Maximum provider calls.
  --budget-tokens <n>        Maximum provider tokens.
  --budget-wall-seconds <n>  Maximum wall-clock seconds.
  --max-tool-calls <n>       Maximum tool calls per task.

Output:
  --json-out <path>          Write the JSON experiment report.
  --report-md <path>         Write the Markdown experiment report.
  --help                     Print this help and exit.

The command never writes outside --publish-root, --store, and the explicit
report paths.  Paths are recorded exactly as supplied; they are not resolved
against the working directory.`

/** Return the CLI help string. */
export function helpText(): string {
  return HELP_TEXT
}

interface OptionSpec {
  readonly flag: `--${string}`
  readonly key: keyof CliOptions
  readonly kind: 'string' | 'boolean' | 'positive-integer' | 'ratio' | 'enum'
  readonly choices?: readonly string[]
}

const OPTION_SPECS: readonly OptionSpec[] = [
  { flag: '--trace-file', key: 'traceFile', kind: 'string' },
  { flag: '--job-dir', key: 'jobDir', kind: 'string' },
  { flag: '--store', key: 'store', kind: 'string' },
  { flag: '--stage', key: 'stage', kind: 'enum', choices: CLI_STAGES },
  { flag: '--run-id', key: 'runId', kind: 'string' },
  { flag: '--seed', key: 'seed', kind: 'positive-integer' },
  { flag: '--source-inventory', key: 'sourceInventory', kind: 'string' },
  { flag: '--publish-root', key: 'publishRoot', kind: 'string' },
  { flag: '--router', key: 'router', kind: 'enum', choices: CLI_ROUTERS },
  { flag: '--embedding', key: 'embedding', kind: 'enum', choices: CLI_EMBEDDINGS },
  { flag: '--embedding-url', key: 'embeddingUrl', kind: 'string' },
  { flag: '--model', key: 'model', kind: 'string' },
  { flag: '--budget-calls', key: 'budgetCalls', kind: 'positive-integer' },
  { flag: '--budget-tokens', key: 'budgetTokens', kind: 'positive-integer' },
  { flag: '--budget-wall-seconds', key: 'budgetWallSeconds', kind: 'positive-integer' },
  { flag: '--max-tool-calls', key: 'maxToolCalls', kind: 'positive-integer' },
  { flag: '--dry-run', key: 'dryRun', kind: 'boolean' },
  { flag: '--resume', key: 'resume', kind: 'boolean' },
  { flag: '--json-out', key: 'jsonOut', kind: 'string' },
  { flag: '--report-md', key: 'reportMd', kind: 'string' },
  { flag: '--abstain-threshold', key: 'abstainThreshold', kind: 'ratio' },
  { flag: '--help', key: 'help', kind: 'boolean' },
]

const OPTION_BY_KEY: ReadonlyMap<keyof CliOptions, OptionSpec> = new Map(
  OPTION_SPECS.map((spec) => [spec.key, spec]),
)

function isOptionKey(value: string | undefined): value is keyof CliOptions {
  return value !== undefined && OPTION_BY_KEY.has(value as keyof CliOptions)
}

function specFlag(key: keyof CliOptions): string {
  const spec = OPTION_BY_KEY.get(key)
  if (spec === undefined) throw new Error(`missing option spec for ${key}`)
  return spec.flag
}

function usageIssue(
  code: CliUsageErrorCode,
  option: string | null,
  message: string,
): CliUsageIssue {
  return { code, option, message }
}

function requireString(
  value: string,
  key: keyof CliOptions,
  issues: CliUsageIssue[],
): string | null {
  if (value.trim().length === 0) {
    issues.push(usageIssue(
      'missing-value',
      specFlag(key),
      `option ${specFlag(key)} requires a non-empty value`,
    ))
    return null
  }
  return value
}

function parsePositiveInteger(
  value: string,
  key: keyof CliOptions,
  issues: CliUsageIssue[],
): number | null {
  if (!/^[1-9][0-9]*$/.test(value)) {
    issues.push(usageIssue(
      'invalid-value',
      specFlag(key),
      `option ${specFlag(key)} requires a positive integer`,
    ))
    return null
  }
  const parsed = Number(value)
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    issues.push(usageIssue(
      'invalid-value',
      specFlag(key),
      `option ${specFlag(key)} requires a positive safe integer`,
    ))
    return null
  }
  return parsed
}

function parseRatio(
  value: string,
  key: keyof CliOptions,
  issues: CliUsageIssue[],
): number | null {
  if (value.trim().length === 0) {
    issues.push(usageIssue(
      'missing-value',
      specFlag(key),
      `option ${specFlag(key)} requires a number`,
    ))
    return null
  }
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
    issues.push(usageIssue(
      'invalid-value',
      specFlag(key),
      `option ${specFlag(key)} requires a number in [0, 1]`,
    ))
    return null
  }
  return parsed
}

function parseChoice<C extends string>(
  value: string,
  key: keyof CliOptions,
  choices: readonly C[],
  issues: CliUsageIssue[],
): C | null {
  if (!(choices as readonly string[]).includes(value)) {
    issues.push(usageIssue(
      'invalid-value',
      specFlag(key),
      `option ${specFlag(key)} must be one of: ${choices.join(', ')} (received "${value}")`,
    ))
    return null
  }
  return value as C
}

/**
 * Build the canonical options object.
 *
 * Every field is written in one fixed order, which makes `Object.keys()`,
 * `JSON.stringify()`, and report snapshots independent of how the caller
 * built the override object.  The result is frozen.
 */
export function canonicalOptions(overrides: Partial<CliOptions> = {}): CliOptions {
  const options: CliOptions = {
    traceFile: overrides.traceFile ?? null,
    jobDir: overrides.jobDir ?? null,
    store: overrides.store ?? null,
    stage: overrides.stage ?? null,
    runId: overrides.runId ?? null,
    seed: overrides.seed ?? null,
    sourceInventory: overrides.sourceInventory ?? null,
    publishRoot: overrides.publishRoot ?? null,
    router: overrides.router ?? 'deterministic',
    embedding: overrides.embedding ?? 'deterministic',
    embeddingUrl: overrides.embeddingUrl ?? null,
    model: overrides.model ?? null,
    budgetCalls: overrides.budgetCalls ?? null,
    budgetTokens: overrides.budgetTokens ?? null,
    budgetWallSeconds: overrides.budgetWallSeconds ?? null,
    maxToolCalls: overrides.maxToolCalls ?? null,
    dryRun: overrides.dryRun ?? false,
    resume: overrides.resume ?? false,
    jsonOut: overrides.jsonOut ?? null,
    reportMd: overrides.reportMd ?? null,
    abstainThreshold: overrides.abstainThreshold ?? null,
    help: overrides.help ?? false,
  }
  return Object.freeze(options)
}

/** All-default options.  `stage` remains null so the caller must choose one. */
export const DEFAULT_CLI_OPTIONS: CliOptions = canonicalOptions()

function parseTokens(
  argv: readonly string[],
): {
  readonly values: ReadonlyMap<keyof CliOptions, string>
  readonly switches: ReadonlySet<keyof CliOptions>
  readonly issues: CliUsageIssue[]
} {
  const specsByFlag = new Map<string, OptionSpec>(
    OPTION_SPECS.map((spec) => [spec.flag, spec]),
  )
  const values = new Map<keyof CliOptions, string>()
  const switches = new Set<keyof CliOptions>()
  const seen = new Set<keyof CliOptions>()
  const issues: CliUsageIssue[] = []
  let index = 0
  let terminated = false

  while (index < argv.length) {
    const token = argv[index]
    if (token === undefined) break
    index += 1

    if (terminated) {
      issues.push(usageIssue(
        'unexpected-argument',
        null,
        `unexpected positional argument after --: ${token}`,
      ))
      continue
    }

    if (token === '--') {
      terminated = true
      continue
    }

    if (!token.startsWith('--') || token === '--') {
      issues.push(usageIssue(
        'unexpected-argument',
        null,
        `unexpected argument: ${token}`,
      ))
      continue
    }

    const equals = token.indexOf('=')
    const flag = equals === -1 ? token : token.slice(0, equals)
    const inline = equals === -1 ? null : token.slice(equals + 1)
    const spec = specsByFlag.get(flag)
    if (spec === undefined) {
      issues.push(usageIssue('unknown-option', flag, `unknown option: ${flag}`))
      continue
    }

    if (seen.has(spec.key)) {
      issues.push(usageIssue(
        'duplicate-option',
        spec.flag,
        `option ${spec.flag} was provided more than once`,
      ))
      // Consume the duplicate's value so it is not reported again as a
      // positional argument.  A following flag is left for the normal loop.
      if (spec.kind !== 'boolean' && inline === null) {
        const next = argv[index]
        if (next !== undefined && next !== '--' && !next.startsWith('--')) index += 1
      }
      continue
    }
    seen.add(spec.key)

    if (spec.kind === 'boolean') {
      if (inline !== null) {
        issues.push(usageIssue(
          'unexpected-value',
          spec.flag,
          `option ${spec.flag} does not take a value`,
        ))
        continue
      }
      switches.add(spec.key)
      continue
    }

    let value = inline
    if (value === null) {
      const next = argv[index]
      if (next === undefined || next === '--' || next.startsWith('--')) {
        issues.push(usageIssue(
          'missing-value',
          spec.flag,
          `option ${spec.flag} requires a value`,
        ))
        continue
      }
      value = next
      index += 1
    }

    if (value.length === 0) {
      issues.push(usageIssue(
        'missing-value',
        spec.flag,
        `option ${spec.flag} requires a non-empty value`,
      ))
      continue
    }
    values.set(spec.key, value)
  }

  return { values, switches, issues }
}

/**
 * Parse one argument vector.
 *
 * The returned object is canonical and frozen.  `--help` short-circuits the
 * cross-option requirements but still rejects unknown, duplicated, or
 * malformed flags.
 */
export function parseArgs(argv: readonly string[]): CliOptions {
  const { values, switches, issues } = parseTokens(argv)

  if (issues.length > 0) throw new CliUsageError(issues)

  const options: {
    -readonly [K in keyof CliOptions]: CliOptions[K]
  } = { ...DEFAULT_CLI_OPTIONS }

  for (const spec of OPTION_SPECS) {
    if (spec.kind === 'boolean') {
      if (switches.has(spec.key)) {
        switch (spec.key) {
          case 'dryRun':
            options.dryRun = true
            break
          case 'resume':
            options.resume = true
            break
          case 'help':
            options.help = true
            break
          default:
            break
        }
      }
      continue
    }

    const value = values.get(spec.key)
    if (value === undefined) continue

    switch (spec.key) {
      case 'traceFile':
        options.traceFile = requireString(value, spec.key, issues)
        break
      case 'jobDir':
        options.jobDir = requireString(value, spec.key, issues)
        break
      case 'store':
        options.store = requireString(value, spec.key, issues)
        break
      case 'stage':
        options.stage = parseChoice(value, spec.key, CLI_STAGES, issues)
        break
      case 'runId':
        options.runId = requireString(value, spec.key, issues)
        break
      case 'seed':
        options.seed = parsePositiveInteger(value, spec.key, issues)
        break
      case 'sourceInventory':
        options.sourceInventory = requireString(value, spec.key, issues)
        break
      case 'publishRoot':
        options.publishRoot = requireString(value, spec.key, issues)
        break
      case 'router':
        options.router = parseChoice(value, spec.key, CLI_ROUTERS, issues) ?? 'deterministic'
        break
      case 'embedding':
        options.embedding = parseChoice(value, spec.key, CLI_EMBEDDINGS, issues) ?? 'deterministic'
        break
      case 'embeddingUrl':
        options.embeddingUrl = requireString(value, spec.key, issues)
        break
      case 'model':
        options.model = requireString(value, spec.key, issues)
        break
      case 'budgetCalls':
        options.budgetCalls = parsePositiveInteger(value, spec.key, issues)
        break
      case 'budgetTokens':
        options.budgetTokens = parsePositiveInteger(value, spec.key, issues)
        break
      case 'budgetWallSeconds':
        options.budgetWallSeconds = parsePositiveInteger(value, spec.key, issues)
        break
      case 'maxToolCalls':
        options.maxToolCalls = parsePositiveInteger(value, spec.key, issues)
        break
      case 'jsonOut':
        options.jsonOut = requireString(value, spec.key, issues)
        break
      case 'reportMd':
        options.reportMd = requireString(value, spec.key, issues)
        break
      case 'abstainThreshold':
        options.abstainThreshold = parseRatio(value, spec.key, issues)
        break
      case 'help':
      case 'dryRun':
      case 'resume':
        break
      default:
        break
    }
  }

  if (issues.length > 0) throw new CliUsageError(issues)

  if (options.help) return canonicalOptions(options)

  if (options.traceFile !== null && options.jobDir !== null) {
    issues.push(usageIssue(
      'conflicting-options',
      '--trace-file',
      'provide exactly one of --trace-file or --job-dir, not both',
    ))
  } else if (options.traceFile === null && options.jobDir === null) {
    issues.push(usageIssue(
      'missing-required-option',
      '--trace-file',
      'provide exactly one of --trace-file or --job-dir',
    ))
  }

  if (options.stage === null) {
    issues.push(usageIssue(
      'missing-required-option',
      '--stage',
      'option --stage is required',
    ))
  }

  if (options.publishRoot === null && !options.dryRun) {
    issues.push(usageIssue(
      'missing-required-option',
      '--publish-root',
      'option --publish-root is required unless --dry-run is set',
    ))
  }

  if (issues.length > 0) throw new CliUsageError(issues)

  return canonicalOptions(options)
}

/** Alias for callers that prefer an explicit CLI name. */
export const parseCliArgs = parseArgs

/** Return true when a value is a canonical option key. */
export function isCliOptionKey(value: string): value is keyof CliOptions {
  return isOptionKey(value)
}
