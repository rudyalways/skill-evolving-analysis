import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { RouterInventory, DecisionProvider } from '../router/two-stage-router.ts'
import { DEFAULT_ROUTER_CONFIG, type RouterConfig } from '../router/two-stage-router.ts'
import { JsonFileTraceSource } from '../adapters/json-trace-source.ts'
import { InMemoryTraceSource } from '../capabilities/providers.ts'
import { runId, skillId, traceId, findingId } from '../contracts/ids.ts'
import { classifyFailureFamily, type FailureFamily } from '../resources/planner.ts'
import { ReplayVerifier } from '../verification/replay-verifier.ts'
import { WorkspacePublisher } from '../publication/publisher.ts'
import { openStudyStore } from '../store/study-store.ts'
import { RunController } from '../core/run-controller.ts'
import { V2Pipeline } from '../core/v2-pipeline.ts'
import { mountLowCostV2Profile, type LowCostV2Profile } from '../profiles/low-cost-v2.ts'
import { parseArgs, helpText, CliUsageError } from './args.ts'
import {
  buildExperimentReport,
  renderMarkdownReport,
  serializeExperimentReport,
  type ExperimentReport,
} from './report.ts'

function issue(option: string | null, message: string): never {
  throw new CliUsageError([{ code: 'invalid-value', option, message }])
}

/** Deterministic bounded stage-two provider used by the CLI slice. */
function createDecisionProvider(family: FailureFamily): DecisionProvider {
  return {
    async decide() {
      return {
        kind: 'create',
        failureFamilyId: family,
        confidence: 0.78,
        rationale: `create a ${family} skill from the supplied train evidence`,
        usage: { tokens: 0, latencyMs: 0 },
      }
    },
  }
}

function seedInventory(family: FailureFamily): RouterInventory {
  return {
    skills: [{
      skillId: skillId(`seed-${family}`),
      name: `${family} skill`,
      description: `Reusable ${family} workflow with scripts, references, and fixtures`,
      family,
      intents: ['evolve-skill'],
      actions: ['update'],
      keywords: family.split('-'),
    }],
    failureFamilies: [{
      familyId: family,
      family,
      description: `${family} failure family`,
      intents: ['evolve-skill'],
      actions: ['update'],
      keywords: family.split('-'),
    }],
  }
}

async function loadInventory(path: string | null, family: FailureFamily): Promise<RouterInventory> {
  if (path === null) return seedInventory(family)
  try {
    const parsed: unknown = JSON.parse(await readFile(path, 'utf8'))
    if (typeof parsed !== 'object' || parsed === null) issue('--source-inventory', 'inventory must be a JSON object')
    const candidate = parsed as RouterInventory
    if (!Array.isArray(candidate.skills) || !Array.isArray(candidate.failureFamilies)) {
      issue('--source-inventory', 'inventory must contain skills and failureFamilies arrays')
    }
    return candidate
  } catch (error) {
    if (error instanceof CliUsageError) throw error
    issue('--source-inventory', error instanceof Error ? error.message : 'cannot read inventory')
  }
}

function familyFor(traceText: string): FailureFamily {
  return classifyFailureFamily({
    id: findingId('cli-routing'),
    traceId: traceId('cli-routing'),
    detector: 'cli-routing',
    confidence: 0.5,
    summary: traceText.slice(0, 1000),
  }) ?? 'spreadsheet-formula-validation'
}

function reportFromResult(
  options: ReturnType<typeof parseArgs>,
  startAt: string,
  result: Awaited<ReturnType<V2Pipeline['execute']>>,
  taskId: string,
): ExperimentReport {
  const receipt = result.publicationReceipt
  return buildExperimentReport({
    runId: options.runId ?? 'cli-run',
    stage: options.stage ?? 'train',
    startedAt: startAt,
    finishedAt: new Date().toISOString(),
    options,
    tasks: [{ taskId, domain: 'unclassified', stage: options.stage ?? 'train' }],
    candidateScores: (result.route?.retrieval.skills ?? []).map(candidate => ({
      taskId,
      skillId: String(candidate.skillId),
      score: candidate.scores.combined,
      reason: `lexical=${candidate.scores.lexical.toFixed(3)} embedding=${candidate.scores.embedding.toFixed(3)} family=${candidate.scores.family.toFixed(3)}`,
    })),
    resources: (result.plan?.resources ?? []).map(resource => ({
      kind: resource.resource.kind,
      path: resource.resource.path,
      status: resource.resource.status,
      operationId: String(resource.resource.operationId),
      skillId: String(resource.resource.skillId),
    })),
    receipts: receipt === undefined ? [] : [{
      operationId: receipt.operationId as never,
      releaseId: receipt.releaseId,
      channel: receipt.channel,
    }],
    preflight: result.preflight ?? null,
    verification: result.projection.status === 'completed' && receipt !== undefined
      ? { status: 'pass', summary: 'replay verification and publication passed' }
      : { status: 'fail', summary: result.reason ?? 'experiment did not publish' },
    holdoutReady: false,
    limitations: [
      'CLI validation run; not a sealed holdout.',
      'Cost is unmeasured unless the benchmark adapter supplies it.',
      'Router is deterministic/hash-embedding in this slice.',
    ],
  })
}

async function writeOutputs(report: ExperimentReport, options: ReturnType<typeof parseArgs>, json: string) {
  if (options.jsonOut) {
    await mkdir(dirname(options.jsonOut), { recursive: true })
    await writeFile(options.jsonOut, json, 'utf8')
  }
  if (options.reportMd) {
    await mkdir(dirname(options.reportMd), { recursive: true })
    await writeFile(options.reportMd, renderMarkdownReport(report), 'utf8')
  }
  if (!options.jsonOut && !options.reportMd) process.stdout.write(`${json}\n`)
}

async function execute(options: ReturnType<typeof parseArgs>): Promise<number> {
  if (options.dryRun) {
    const report = buildExperimentReport({
      runId: options.runId ?? 'dry-run',
      stage: options.stage ?? 'train',
      startedAt: new Date().toISOString(),
      finishedAt: null,
      options,
      tasks: [],
      holdoutReady: false,
      limitations: ['dry run: no pipeline, publication, or benchmark execution'],
    })
    await writeOutputs(report, options, serializeExperimentReport(report))
    return 0
  }

  if (options.store === null) issue('--store', '--store is required for a non-dry run')
  if (options.publishRoot === null) issue('--publish-root', '--publish-root is required for a non-dry run')
  if (options.traceFile === null && options.jobDir === null) issue('--trace-file', 'trace input is required')

  let traceSource
  if (options.traceFile) {
    traceSource = await JsonFileTraceSource.open(options.traceFile)
  } else {
    const promptsPath = resolve(options.jobDir!, 'prompts.json')
    const prompts: unknown = JSON.parse(await readFile(promptsPath, 'utf8'))
    if (!Array.isArray(prompts) || prompts.some(value => typeof value !== 'string')) {
      issue('--job-dir', 'job prompts.json must be an array of strings')
    }
    const id = traceId(`job-${options.jobDir}`)
    traceSource = new InMemoryTraceSource([{ id, source: options.jobDir!, turns: prompts }])
  }
  const traces = await traceSource.list()
  const firstTrace = traces[0]
  if (firstTrace === undefined) issue('--trace-file', 'trace source is empty')
  const trace = await traceSource.read(firstTrace)
  const family = familyFor(trace.turns.join('\n'))
  const inventory = await loadInventory(options.sourceInventory, family)
  const store = await openStudyStore(options.store)
  const ctx = new Context()
  const publishRoot = resolve(options.publishRoot)
  let profile: LowCostV2Profile | undefined
  try {
    profile = await mountLowCostV2Profile(ctx, {
      traceSource,
      inventory,
      verifier: new ReplayVerifier(),
      skillPublisher: new WorkspacePublisher({ inventoryRoot: publishRoot }),
      decisionProvider: createDecisionProvider(family),
      routerConfig: {
        thresholds: {
          ...DEFAULT_ROUTER_CONFIG.thresholds,
          minimumCombined: 0.1,
          minimumEvidence: 0.01,
          minimumIntentAction: 0.1,
          minimumFamily: 0.5,
        },
      } satisfies Partial<RouterConfig>,
    })
    const pipeline = profile.pipeline(
      new RunController(runId(options.runId ?? `cli-${Date.now()}`)),
      store,
    )
    const result = await pipeline.execute({
      traceId: trace.id,
      taskId: options.runId ?? String(trace.id),
      objective: 'v2 CLI experiment',
      profile: 'cli-low-cost-v2',
      at: new Date().toISOString(),
      family,
      routerBudget: {
        maxCandidates: 5,
        maxCalls: options.budgetCalls ?? 1,
        maxTokens: options.budgetTokens ?? 16384,
        maxLatencyMs: (options.budgetWallSeconds ?? 60) * 1000,
      },
      policyVersion: 'cli-policy-v1',
      configVersion: 'cli-config-v1',
    })
    const report = reportFromResult(options, new Date().toISOString(), result, String(trace.id))
    await writeOutputs(report, options, serializeExperimentReport(report))
    const published = result.publicationReceipt !== undefined
    return published ? 0 : 2
  } finally {
    if (profile) await profile.dispose()
    await store.close()
  }
}

/** Run the CLI and return its process exit code. */
export async function runV2Cli(argv: readonly string[]): Promise<number> {
  try {
    const options = parseArgs(argv)
    if (options.help) {
      process.stdout.write(`${helpText()}\n`)
      return 0
    }
    return await execute(options)
  } catch (error) {
    process.stderr.write(`${JSON.stringify({
      code: error instanceof Error && 'code' in error ? String((error as { code: unknown }).code) : 'cli-error',
      message: error instanceof Error ? error.message : String(error),
    })}\n`)
    return 1
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  void runV2Cli(process.argv.slice(2)).then(code => { process.exitCode = code })
}
