import { PipelineError, type StructuredIssue } from '../contracts/errors.ts'
import { skillId, type SkillId } from '../contracts/ids.ts'
import { isFiniteNumber, isNonEmptyString, isRecord, issue } from '../contracts/validation.ts'

/** A task presented to the router. Family and intent are optional rule signals. */
export interface RouterTask {
  readonly taskId: string
  readonly text: string
  readonly family?: string
  readonly intent?: string
  readonly action?: string
}

/** One skill document available to stage-one recall. */
export interface SkillDocument {
  readonly skillId: SkillId
  readonly name: string
  readonly description: string
  readonly family?: string
  readonly intents?: readonly string[]
  readonly actions?: readonly string[]
  readonly keywords?: readonly string[]
  readonly text?: string
  /** When false, stage-one excludes this skill from selection. */
  readonly selectable?: boolean
}

/** One reusable failure family available to stage-one recall. */
export interface FailureFamilyDocument {
  readonly familyId: string
  readonly family: string
  readonly description: string
  readonly intents?: readonly string[]
  readonly actions?: readonly string[]
  readonly keywords?: readonly string[]
  /** When false, stage-one excludes this family from selection. */
  readonly selectable?: boolean
}

/** The current skill and failure-family inventory. */
export interface RouterInventory {
  readonly skills: readonly SkillDocument[]
  readonly failureFamilies: readonly FailureFamilyDocument[]
}

/** Per-component stage-one scores for one candidate. */
export interface CandidateComponentScores {
  readonly lexical: number
  readonly embedding: number
  readonly intentAction: number
  readonly family: number
  readonly combined: number
}

/** One retrieved skill candidate with its component scores. */
export interface SkillCandidate {
  readonly skillId: SkillId
  readonly scores: CandidateComponentScores
}

/** One retrieved failure-family candidate with its component scores. */
export interface FailureFamilyCandidate {
  readonly familyId: string
  readonly scores: CandidateComponentScores
}

/** Complete stage-one retrieval output. */
export interface RouterRetrieval {
  readonly skills: readonly SkillCandidate[]
  readonly failureFamilies: readonly FailureFamilyCandidate[]
  readonly queryTokenCount: number
  readonly embeddingDegraded: boolean
}

/** Stage-two decision actions. */
export type RouterDecisionKind = 'reuse' | 'update' | 'create' | 'merge' | 'delete' | 'abstain'

/** Why the deterministic fallback replaced a provider decision. */
export type FallbackReason =
  | 'provider-unavailable'
  | 'budget-exhausted'
  | 'provider-error'
  | 'invalid-decision'
  | 'unsafe-decision'
  | 'no-candidates'
  | null

/** Final, validated router decision. */
export interface RouterDecision {
  readonly kind: RouterDecisionKind
  readonly skillId: SkillId | null
  readonly failureFamilyId: string | null
  readonly confidence: number
  readonly rationale: string
  readonly source: 'provider' | 'fallback'
  readonly fallbackReason: FallbackReason
}

/** Observable stage-two spend. */
export interface RouterUsage {
  readonly calls: number
  readonly tokens: number
  readonly latencyMs: number
  readonly exhausted: boolean
}

/** One complete route result. */
export interface RouterResult {
  readonly task: RouterTask
  readonly retrieval: RouterRetrieval
  readonly decision: RouterDecision
  readonly usage: RouterUsage
}

/** Explicit stage-two budget. Zero calls, tokens, or latency means exhausted. */
export interface RouterBudget {
  /** Maximum candidates offered per list (skills and failure families). */
  readonly maxCandidates: number
  readonly maxCalls: number
  readonly maxTokens: number
  readonly maxLatencyMs: number
}

/** Component weights; the router normalizes their sum. */
export interface ComponentWeights {
  readonly lexical: number
  readonly embedding: number
  readonly intentAction: number
  readonly family: number
}

/** Activation gates. `combined` and `evidence` use normalized component scores. */
export interface RouterThresholds {
  readonly minimumCombined: number
  readonly minimumEvidence: number
  readonly minimumIntentAction: number
  readonly minimumFamily: number
}

/** Router configuration. */
export interface RouterConfig {
  readonly stage1Limit: number
  readonly stage2Candidates: number
  readonly weights: ComponentWeights
  readonly thresholds: RouterThresholds
}

/** The default conservative configuration. */
export const DEFAULT_ROUTER_CONFIG: RouterConfig = {
  stage1Limit: 20,
  stage2Candidates: 5,
  weights: { lexical: 0.4, embedding: 0.25, intentAction: 0.2, family: 0.15 },
  thresholds: {
    minimumCombined: 0.55,
    minimumEvidence: 0.3,
    minimumIntentAction: 0.5,
    minimumFamily: 0.6,
  },
}

/** A seam for deterministic or external embeddings; no model is called here. */
export interface EmbeddingProvider {
  embed(texts: readonly string[]): readonly (readonly number[])[]
}

/** One bounded piece of evidence offered to a stage-two provider. */
export interface DecisionCandidate {
  readonly skillId: SkillId
  readonly scores: CandidateComponentScores
  readonly summary: string
}

/** One bounded failure-family candidate offered to a stage-two provider. */
export interface DecisionFamilyCandidate {
  readonly familyId: string
  readonly scores: CandidateComponentScores
  readonly summary: string
}

/** Cheap, bounded stage-two input. Full documents are intentionally excluded. */
export interface DecisionProviderRequest {
  readonly task: RouterTask
  readonly skills: readonly DecisionCandidate[]
  readonly failureFamilies: readonly DecisionFamilyCandidate[]
  readonly budget: RouterBudget
}

/** A stage-two provider; later implementations may call DSH/DeepSeek. */
export interface DecisionProvider {
  /** Return an unvalidated response; the router validates it before use. */
  decide(request: DecisionProviderRequest): Promise<unknown>
}

/** Validated spend reported by a stage-two provider. */
export interface ProviderUsage {
  readonly tokens: number
  readonly latencyMs: number
}

/** Validated stage-two provider output. */
export interface ParsedProviderDecision {
  readonly kind: RouterDecisionKind
  readonly skillId: SkillId | null
  readonly failureFamilyId: string | null
  readonly confidence: number
  readonly rationale: string
  readonly usage: ProviderUsage
}

/** Candidate ids a provider may reference. */
export interface DecisionAllowlist {
  readonly skillIds: readonly SkillId[]
  readonly failureFamilyIds: readonly string[]
}

/** Options for one router instance. */
export interface TwoStageRouterOptions {
  readonly inventory: RouterInventory
  readonly config?: Partial<RouterConfig>
  readonly embedding?: EmbeddingProvider
  readonly decisionProvider?: DecisionProvider
  readonly clock?: () => number
}

/** Structured router failure with stable code and validation issues. */
export class RouterError extends PipelineError {
  readonly issues: readonly StructuredIssue[]

  constructor(code: string, message: string, issues: readonly StructuredIssue[] = []) {
    super(code, message, { issues })
    this.issues = issues
  }
}

/** Labels for one routed task. Empty `usefulSkillIds` means abstention is correct. */
export interface LabeledObservation {
  readonly task: RouterTask
  readonly usefulSkillIds: readonly SkillId[]
  readonly baselinePassed: boolean
  readonly treatmentPassed: boolean
  readonly costUsd: number
  readonly latencyMs: number
  /** Optional labeled regression count; otherwise derived from pass changes. */
  readonly regressions?: number
}

/** One routed observation paired with its labels. */
export interface RouterEvaluationRow {
  readonly observation: LabeledObservation
  readonly result: RouterResult
}

/** Router quality, cost, and safety metrics over labeled observations. */
export interface RouterMetrics {
  readonly observations: number
  readonly usefulObservations: number
  readonly noSkillObservations: number
  readonly activations: number
  readonly abstentions: number
  readonly recallK: number
  readonly usefulSkillRecallAtK: number
  readonly activationPrecision: number
  readonly falseAbstentionRate: number
  readonly falseActivationRate: number
  readonly activationRate: number
  readonly passLiftPerActivation: number
  readonly meanCostUsd: number
  readonly meanLatencyMs: number
  readonly costPerActivation: number
  readonly latencyPerActivation: number
  readonly regressions: number
}

/** Optional metric controls. */
export interface RouterMetricsOptions {
  readonly recallK?: number
}

const DECISION_KINDS: readonly RouterDecisionKind[] = [
  'reuse',
  'update',
  'create',
  'merge',
  'delete',
  'abstain',
]

const ACTIVATION_KINDS: ReadonlySet<RouterDecisionKind> = new Set([
  'reuse',
  'update',
  'create',
  'merge',
  'delete',
])

const STOPWORDS = new Set([
  'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'when', 'then', 'than',
  'are', 'was', 'were', 'has', 'have', 'had', 'not', 'but', 'you', 'your', 'our',
  'their', 'its', 'can', 'will', 'would', 'should', 'could', 'about', 'over', 'under',
  'after', 'before', 'while', 'where', 'which', 'who', 'how', 'what', 'why', 'all',
  'any', 'each', 'more', 'most', 'some', 'such', 'only', 'own', 'same', 'too', 'very',
  'just', 'also', 'use', 'using', 'via', 'per', 'onto', 'off', 'out', 'up', 'down',
])

const MAX_SUMMARY_CHARS = 240

function isDecisionKind(value: string): value is RouterDecisionKind {
  return DECISION_KINDS.some(kind => kind === value)
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value))
}

function normalize(value: string | undefined): string {
  return (value ?? '').trim().toLowerCase()
}

function tokenize(text: string): readonly string[] {
  return text.toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter(token => token.length > 2 && !STOPWORDS.has(token))
}

function hashToken(token: string): number {
  let value = 2166136261
  for (const character of token) {
    value ^= character.codePointAt(0) ?? 0
    value = Math.imul(value, 16777619)
  }
  return value >>> 0
}

/**
 * Deterministic in-memory embedding provider. It hashes lexical tokens into a
 * fixed vector and L2-normalizes, so equal text always produces equal vectors.
 */
export class DeterministicEmbeddingProvider implements EmbeddingProvider {
  constructor(private readonly dimensions = 64) {
    if (!Number.isInteger(dimensions) || dimensions < 1) {
      throw new RouterError('invalid-embedding-provider', 'embedding dimensions must be a positive integer')
    }
  }

  embed(texts: readonly string[]): readonly (readonly number[])[] {
    return texts.map(text => {
      const vector = new Array<number>(this.dimensions).fill(0)
      for (const token of tokenize(text)) {
        const index = hashToken(token) % this.dimensions
        vector[index] = (vector[index] ?? 0) + 1
      }
      const norm = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0))
      return norm === 0 ? vector : vector.map(value => value / norm)
    })
  }
}

function cosine(left: readonly number[], right: readonly number[]): number {
  if (left.length === 0 || left.length !== right.length) return 0
  let dot = 0
  let leftNorm = 0
  let rightNorm = 0
  for (let index = 0; index < left.length; index += 1) {
    const leftValue = left[index] ?? 0
    const rightValue = right[index] ?? 0
    dot += leftValue * rightValue
    leftNorm += leftValue * leftValue
    rightNorm += rightValue * rightValue
  }
  if (leftNorm === 0 || rightNorm === 0) return 0
  return clamp01(dot / Math.sqrt(leftNorm * rightNorm))
}

function lexicalScore(query: readonly string[], document: readonly string[]): number {
  const queryTokens = new Set(query)
  const documentTokens = new Set(document)
  if (queryTokens.size === 0 || documentTokens.size === 0) return 0
  let overlap = 0
  for (const token of queryTokens) if (documentTokens.has(token)) overlap += 1
  return (2 * overlap) / (queryTokens.size + documentTokens.size)
}

function familyCompatibility(taskFamily: string | undefined, documentFamily: string | undefined): number {
  const left = normalize(taskFamily)
  const right = normalize(documentFamily)
  if (left.length === 0 && right.length === 0) return 0.5
  if (left.length === 0 || right.length === 0) return 0.25
  return left === right ? 1 : 0
}

/** Unknown family metadata is deliberately below the default activation gate. */

function listCompatibility(taskValues: readonly string[], documentValues: readonly string[]): number {
  const left = new Set(taskValues.map(normalize).filter(value => value.length > 0))
  const right = new Set(documentValues.map(normalize).filter(value => value.length > 0))
  if (left.size === 0 || right.size === 0) return 0.5
  let overlap = 0
  for (const value of left) if (right.has(value)) overlap += 1
  return overlap / left.size
}

function intentActionCompatibility(task: RouterTask, document: {
  readonly intents?: readonly string[]
  readonly actions?: readonly string[]
}): number {
  const intents = document.intents ?? []
  const actions = document.actions ?? []
  const parts: number[] = []
  if (task.intent !== undefined || intents.length > 0) {
    parts.push(listCompatibility(task.intent === undefined ? [] : [task.intent], intents))
  }
  if (task.action !== undefined || actions.length > 0) {
    parts.push(listCompatibility(task.action === undefined ? [] : [task.action], actions))
  }
  if (parts.length === 0) return 0.5
  return parts.reduce((sum, value) => sum + value, 0) / parts.length
}

function combineScores(
  lexical: number,
  embedding: number,
  intentAction: number,
  family: number,
  weights: ComponentWeights,
): CandidateComponentScores {
  const total = weights.lexical + weights.embedding + weights.intentAction + weights.family
  const combined = (
    lexical * weights.lexical
    + embedding * weights.embedding
    + intentAction * weights.intentAction
    + family * weights.family
  ) / total
  return {
    lexical: clamp01(lexical),
    embedding: clamp01(embedding),
    intentAction: clamp01(intentAction),
    family: clamp01(family),
    combined: clamp01(combined),
  }
}

function evidenceScore(scores: CandidateComponentScores, weights: ComponentWeights): number {
  const total = weights.lexical + weights.embedding
  if (total === 0) return 0
  return (scores.lexical * weights.lexical + scores.embedding * weights.embedding) / total
}

function meetsActivationGate(scores: CandidateComponentScores, config: RouterConfig): boolean {
  return scores.combined >= config.thresholds.minimumCombined
    && evidenceScore(scores, config.weights) >= config.thresholds.minimumEvidence
    && scores.intentAction >= config.thresholds.minimumIntentAction
    && scores.family >= config.thresholds.minimumFamily
}

function skillDocumentText(skill: SkillDocument): string {
  return [
    skill.name,
    skill.description,
    ...(skill.keywords ?? []),
    skill.text ?? '',
  ].join(' ')
}

function failureFamilyText(family: FailureFamilyDocument): string {
  return [family.description, ...(family.keywords ?? [])].join(' ')
}

function summarize(text: string): string {
  return text.length <= MAX_SUMMARY_CHARS ? text : `${text.slice(0, MAX_SUMMARY_CHARS - 1)}…`
}

function compareCandidates(
  left: CandidateComponentScores,
  right: CandidateComponentScores,
  leftId: string,
  rightId: string,
): number {
  return right.combined - left.combined
    || right.lexical - left.lexical
    || right.embedding - left.embedding
    || right.family - left.family
    || leftId.localeCompare(rightId)
}

function embedMatrix(
  provider: EmbeddingProvider,
  texts: readonly string[],
): readonly (readonly number[])[] | null {
  try {
    const matrix = provider.embed(texts)
    if (matrix.length !== texts.length) return null
    let dimension = -1
    for (const vector of matrix) {
      if (vector.length === 0) return null
      if (dimension < 0) dimension = vector.length
      else if (vector.length !== dimension) return null
      for (const value of vector) if (!Number.isFinite(value)) return null
    }
    return matrix
  } catch {
    return null
  }
}

function estimateTokens(request: DecisionProviderRequest): number {
  const serialized = JSON.stringify(request)
  return Math.ceil((serialized ?? '').length / 4)
}

function assertBudget(budget: RouterBudget): void {
  const issues: StructuredIssue[] = []
  if (!Number.isInteger(budget.maxCandidates) || budget.maxCandidates < 1) {
    issues.push(issue('budget.maxCandidates', 'invalid-max-candidates', 'maxCandidates must be a positive integer'))
  }
  if (!Number.isInteger(budget.maxCalls) || budget.maxCalls < 0) {
    issues.push(issue('budget.maxCalls', 'invalid-max-calls', 'maxCalls must be a non-negative integer'))
  }
  if (!Number.isInteger(budget.maxTokens) || budget.maxTokens < 0) {
    issues.push(issue('budget.maxTokens', 'invalid-max-tokens', 'maxTokens must be a non-negative integer'))
  }
  if (!isFiniteNumber(budget.maxLatencyMs) || budget.maxLatencyMs < 0) {
    issues.push(issue('budget.maxLatencyMs', 'invalid-max-latency', 'maxLatencyMs must be a non-negative finite number'))
  }
  if (issues.length > 0) throw new RouterError('invalid-budget', 'router budget failed validation', issues)
}

function assertTask(task: RouterTask): void {
  const issues: StructuredIssue[] = []
  if (!isNonEmptyString(task.taskId)) {
    issues.push(issue('task.taskId', 'invalid-task-id', 'taskId must be a non-empty string'))
  }
  if (!isNonEmptyString(task.text)) {
    issues.push(issue('task.text', 'invalid-task-text', 'text must be a non-empty string'))
  }
  for (const [path, value] of [
    ['task.family', task.family],
    ['task.intent', task.intent],
    ['task.action', task.action],
  ] as const) {
    if (value !== undefined && !isNonEmptyString(value)) {
      issues.push(issue(path, 'invalid-task-signal', `${path} must be a non-empty string when provided`))
    }
  }
  if (issues.length > 0) throw new RouterError('invalid-task', 'router task failed validation', issues)
}

function assertInventory(inventory: RouterInventory): void {
  const issues: StructuredIssue[] = []
  const seenSkills = new Set<string>()
  for (const skill of inventory.skills) {
    const id = String(skill.skillId)
    if (!isNonEmptyString(id)) issues.push(issue('inventory.skills.skillId', 'invalid-skill-id', 'skill id must be non-empty'))
    if (seenSkills.has(id)) issues.push(issue('inventory.skills', 'duplicate-skill', `duplicate skill candidate ${id}`))
    seenSkills.add(id)
    if (!isNonEmptyString(skill.name)) issues.push(issue('inventory.skills.name', 'invalid-name', `skill ${id} needs a name`))
    if (!isNonEmptyString(skill.description)) {
      issues.push(issue('inventory.skills.description', 'invalid-description', `skill ${id} needs a description`))
    }
    if (skill.family !== undefined && !isNonEmptyString(skill.family)) {
      issues.push(issue('inventory.skills.family', 'invalid-family', `skill ${id} has an empty family`))
    }
  }
  const seenFamilies = new Set<string>()
  for (const family of inventory.failureFamilies) {
    if (!isNonEmptyString(family.familyId)) {
      issues.push(issue('inventory.failureFamilies.familyId', 'invalid-family-id', 'family id must be non-empty'))
    }
    if (seenFamilies.has(family.familyId)) {
      issues.push(issue('inventory.failureFamilies', 'duplicate-family', `duplicate failure family ${family.familyId}`))
    }
    seenFamilies.add(family.familyId)
    if (!isNonEmptyString(family.family)) {
      issues.push(issue('inventory.failureFamilies.family', 'invalid-family', `family ${family.familyId} needs a family`))
    }
    if (!isNonEmptyString(family.description)) {
      issues.push(issue('inventory.failureFamilies.description', 'invalid-description', `family ${family.familyId} needs a description`))
    }
  }
  if (issues.length > 0) throw new RouterError('invalid-candidates', 'router inventory failed validation', issues)
}

function validateConfig(config: RouterConfig): void {
  const issues: StructuredIssue[] = []
  if (!Number.isInteger(config.stage1Limit) || config.stage1Limit < 1) {
    issues.push(issue('config.stage1Limit', 'invalid-limit', 'stage1Limit must be a positive integer'))
  }
  if (!Number.isInteger(config.stage2Candidates) || config.stage2Candidates < 1) {
    issues.push(issue('config.stage2Candidates', 'invalid-limit', 'stage2Candidates must be a positive integer'))
  }
  if (config.stage2Candidates > config.stage1Limit) {
    issues.push(issue('config.stage2Candidates', 'limit-order', 'stage2Candidates cannot exceed stage1Limit'))
  }
  for (const [path, value] of [
    ['config.weights.lexical', config.weights.lexical],
    ['config.weights.embedding', config.weights.embedding],
    ['config.weights.intentAction', config.weights.intentAction],
    ['config.weights.family', config.weights.family],
  ] as const) {
    if (!isFiniteNumber(value) || value < 0 || value > 1) {
      issues.push(issue(path, 'invalid-weight', `${path} must be between 0 and 1`))
    }
  }
  if (config.weights.lexical + config.weights.embedding === 0) {
    issues.push(issue('config.weights', 'missing-evidence-weight', 'lexical or embedding weight must be positive'))
  }
  for (const [path, value] of [
    ['config.thresholds.minimumCombined', config.thresholds.minimumCombined],
    ['config.thresholds.minimumEvidence', config.thresholds.minimumEvidence],
    ['config.thresholds.minimumIntentAction', config.thresholds.minimumIntentAction],
    ['config.thresholds.minimumFamily', config.thresholds.minimumFamily],
  ] as const) {
    if (!isFiniteNumber(value) || value < 0 || value > 1) {
      issues.push(issue(path, 'invalid-threshold', `${path} must be between 0 and 1`))
    }
  }
  if (issues.length > 0) throw new RouterError('invalid-config', 'router config failed validation', issues)
}

function resolveConfig(overrides: Partial<RouterConfig> | undefined): RouterConfig {
  const config: RouterConfig = {
    stage1Limit: overrides?.stage1Limit ?? DEFAULT_ROUTER_CONFIG.stage1Limit,
    stage2Candidates: overrides?.stage2Candidates ?? DEFAULT_ROUTER_CONFIG.stage2Candidates,
    weights: overrides?.weights ?? DEFAULT_ROUTER_CONFIG.weights,
    thresholds: overrides?.thresholds ?? DEFAULT_ROUTER_CONFIG.thresholds,
  }
  validateConfig(config)
  return config
}

function invalidDecision(code: string, path: string, message: string): never {
  throw new RouterError('invalid-decision', 'decision provider output failed validation', [issue(path, code, message)])
}

function parseDecisionKind(value: unknown): RouterDecisionKind {
  if (typeof value !== 'string' || !isDecisionKind(value)) {
    invalidDecision('invalid-kind', 'decision.kind', 'kind must be a supported decision')
  }
  return value
}

function parseSkillReference(
  value: unknown,
  kind: RouterDecisionKind,
  allowedSkillIds: ReadonlySet<string>,
): SkillId | null {
  if (kind === 'create' || kind === 'abstain') {
    if (value !== undefined && value !== null) {
      invalidDecision('unexpected-skill-id', 'decision.skillId', `${kind} must not reference an existing skill`)
    }
    return null
  }
  if (!isNonEmptyString(value)) {
    invalidDecision('missing-skill-id', 'decision.skillId', `${kind} needs a skillId`)
  }
  if (!allowedSkillIds.has(value)) {
    invalidDecision('unknown-candidate', 'decision.skillId', `skillId ${value} is not an offered candidate`)
  }
  return skillId(value)
}

function parseFamilyReference(value: unknown, allowedFamilyIds: ReadonlySet<string>): string | null {
  if (value === undefined || value === null) return null
  if (!isNonEmptyString(value) || !allowedFamilyIds.has(value)) {
    invalidDecision('unknown-candidate', 'decision.failureFamilyId', 'failureFamilyId is not an offered candidate')
  }
  return value
}

function parseUsage(value: unknown): ProviderUsage {
  if (value === undefined) return { tokens: 0, latencyMs: 0 }
  if (!isRecord(value)) invalidDecision('invalid-usage', 'decision.usage', 'usage must be an object')
  let tokens = 0
  if (value.tokens !== undefined) {
    if (typeof value.tokens !== 'number' || !Number.isFinite(value.tokens)
      || !Number.isInteger(value.tokens) || value.tokens < 0) {
      invalidDecision('invalid-tokens', 'decision.usage.tokens', 'usage.tokens must be a non-negative integer')
    }
    tokens = value.tokens
  }
  let latencyMs = 0
  if (value.latencyMs !== undefined) {
    if (typeof value.latencyMs !== 'number' || !Number.isFinite(value.latencyMs) || value.latencyMs < 0) {
      invalidDecision('invalid-latency', 'decision.usage.latencyMs', 'usage.latencyMs must be a non-negative number')
    }
    latencyMs = value.latencyMs
  }
  return { tokens, latencyMs }
}

/** Validate untrusted provider output and reject references outside the offer. */
export function parseDecisionOutput(
  value: unknown,
  allowlist: DecisionAllowlist,
): ParsedProviderDecision {
  if (!isRecord(value)) invalidDecision('not-object', 'decision', 'decision output must be an object')
  const kind = parseDecisionKind(value.kind)
  const confidence = value.confidence
  if (typeof confidence !== 'number' || !Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    invalidDecision('invalid-confidence', 'decision.confidence', 'confidence must be between 0 and 1')
  }
  const rationale = value.rationale
  if (typeof rationale !== 'string' || rationale.trim().length === 0 || rationale.length > 2000) {
    invalidDecision('invalid-rationale', 'decision.rationale', 'rationale must be a non-empty string up to 2000 characters')
  }
  return {
    kind,
    skillId: parseSkillReference(value.skillId, kind, new Set(allowlist.skillIds.map(String))),
    failureFamilyId: parseFamilyReference(value.failureFamilyId, new Set(allowlist.failureFamilyIds)),
    confidence,
    rationale,
    usage: parseUsage(value.usage),
  }
}

interface DecisionOutcome {
  readonly decision: RouterDecision
  readonly usage: RouterUsage
}

/** Two-stage router: deterministic recall first, bounded decision second. */
export class TwoStageRouter {
  private readonly inventory: RouterInventory
  private readonly config: RouterConfig
  private readonly embedding: EmbeddingProvider
  private readonly decisionProvider: DecisionProvider | null
  private readonly clock: () => number
  private readonly skillById: ReadonlyMap<string, SkillDocument>
  private readonly familyById: ReadonlyMap<string, FailureFamilyDocument>

  constructor(options: TwoStageRouterOptions) {
    this.config = resolveConfig(options.config)
    this.inventory = options.inventory
    assertInventory(this.inventory)
    this.embedding = options.embedding ?? new DeterministicEmbeddingProvider()
    this.decisionProvider = options.decisionProvider ?? null
    this.clock = options.clock ?? (() => Date.now())
    this.skillById = new Map(this.inventory.skills.map(skill => [String(skill.skillId), skill]))
    this.familyById = new Map(
      this.inventory.failureFamilies
        .filter(family => family.selectable !== false)
        .map(family => [family.familyId, family]),
    )
  }

  /** Run stage one only: score and rank every skill and failure-family candidate. */
  async retrieve(task: RouterTask): Promise<RouterRetrieval> {
    assertTask(task)
    const queryTokens = tokenize(task.text)
    const skillTexts = this.inventory.skills.map(skillDocumentText)
    const familyTexts = this.inventory.failureFamilies.map(failureFamilyText)
    const matrix = embedMatrix(this.embedding, [task.text, ...skillTexts, ...familyTexts])
    const queryVector = matrix === null ? undefined : matrix[0]

    const skillCandidates = this.inventory.skills.map((skill, index): SkillCandidate => {
      const documentTokens = tokenize(skillDocumentText(skill))
      const documentVector = matrix === null ? undefined : matrix[index + 1]
      const embedding = queryVector !== undefined && documentVector !== undefined
        ? cosine(queryVector, documentVector)
        : 0
      const scores = combineScores(
        lexicalScore(queryTokens, documentTokens),
        embedding,
        intentActionCompatibility(task, skill),
        familyCompatibility(task.family, skill.family),
        this.config.weights,
      )
      return { skillId: skill.skillId, scores }
    }).sort((left, right) => compareCandidates(left.scores, right.scores, String(left.skillId), String(right.skillId)))
      .slice(0, this.config.stage1Limit)

    const familyCandidates = this.inventory.failureFamilies
      .map((family, index) => ({ family, index }))
      .filter(({ family }) => family.selectable !== false)
      .map(({ family, index }): FailureFamilyCandidate => {
        const documentTokens = tokenize(failureFamilyText(family))
        const documentVector = matrix === null ? undefined : matrix[this.inventory.skills.length + index + 1]
        const embedding = queryVector !== undefined && documentVector !== undefined
          ? cosine(queryVector, documentVector)
          : 0
        const scores = combineScores(
          lexicalScore(queryTokens, documentTokens),
          embedding,
          intentActionCompatibility(task, family),
          familyCompatibility(task.family, family.family),
          this.config.weights,
        )
        return { familyId: family.familyId, scores }
      }).sort((left, right) => compareCandidates(left.scores, right.scores, left.familyId, right.familyId))
      .slice(0, this.config.stage1Limit)

    return {
      skills: skillCandidates,
      failureFamilies: familyCandidates,
      queryTokenCount: new Set(queryTokens).size,
      embeddingDegraded: matrix === null,
    }
  }

  /** Run both stages under an explicit budget and return one validated decision. */
  async route(task: RouterTask, budget: RouterBudget): Promise<RouterResult> {
    assertBudget(budget)
    const retrieval = await this.retrieve(task)
    const startedAt = this.clock()
    const outcome = await this.decide(task, retrieval, budget, startedAt)
    return { task, retrieval, decision: outcome.decision, usage: outcome.usage }
  }

  private async decide(
    task: RouterTask,
    retrieval: RouterRetrieval,
    budget: RouterBudget,
    startedAt: number,
  ): Promise<DecisionOutcome> {
    if (retrieval.skills.length === 0 && retrieval.failureFamilies.length === 0) {
      return this.fallback(retrieval, 'no-candidates', startedAt, 0, 0)
    }
    if (this.decisionProvider === null) {
      return this.fallback(retrieval, 'provider-unavailable', startedAt, 0, 0)
    }
    if (budget.maxCalls < 1) {
      return this.fallback(retrieval, 'budget-exhausted', startedAt, 0, 0)
    }
    if (this.clock() - startedAt >= budget.maxLatencyMs) {
      return this.fallback(retrieval, 'budget-exhausted', startedAt, 0, 0)
    }

    const request = this.buildDecisionRequest(task, retrieval, budget)
    if (request === null) {
      return this.fallback(retrieval, 'budget-exhausted', startedAt, 0, 0)
    }
    const estimatedTokens = estimateTokens(request)
    const provider = this.decisionProvider
    let output: unknown
    try {
      output = await provider.decide(request)
    } catch {
      return this.fallback(retrieval, 'provider-error', startedAt, 1, estimatedTokens)
    }

    const latencyMs = this.clock() - startedAt
    let parsed: ParsedProviderDecision
    try {
      parsed = parseDecisionOutput(output, {
        skillIds: request.skills.map(candidate => candidate.skillId),
        failureFamilyIds: request.failureFamilies.map(candidate => candidate.familyId),
      })
    } catch {
      return this.fallback(retrieval, 'invalid-decision', startedAt, 1, estimatedTokens)
    }

    const tokens = estimatedTokens + parsed.usage.tokens
    if (tokens > budget.maxTokens || latencyMs > budget.maxLatencyMs) {
      return this.fallback(retrieval, 'budget-exhausted', startedAt, 1, tokens)
    }
    if (!this.isSafe(parsed, request)) {
      return this.fallback(retrieval, 'unsafe-decision', startedAt, 1, tokens)
    }
    return {
      decision: {
        kind: parsed.kind,
        skillId: parsed.skillId,
        failureFamilyId: parsed.failureFamilyId,
        confidence: parsed.confidence,
        rationale: parsed.rationale,
        source: 'provider',
        fallbackReason: null,
      },
      usage: { calls: 1, tokens, latencyMs, exhausted: false },
    }
  }

  private buildDecisionRequest(
    task: RouterTask,
    retrieval: RouterRetrieval,
    budget: RouterBudget,
  ): DecisionProviderRequest | null {
    const skillLimit = Math.min(this.config.stage2Candidates, budget.maxCandidates)
    const familyLimit = Math.min(this.config.stage2Candidates, budget.maxCandidates)
    const base: DecisionProviderRequest = {
      task,
      skills: [],
      failureFamilies: [],
      budget,
    }
    if (estimateTokens(base) > budget.maxTokens) return null

    const skills: DecisionCandidate[] = []
    for (const candidate of retrieval.skills.slice(0, skillLimit)) {
      const document = this.skillById.get(String(candidate.skillId))
      const nextCandidate: DecisionCandidate = {
        skillId: candidate.skillId,
        scores: candidate.scores,
        summary: summarize(document?.description ?? ''),
      }
      if (estimateTokens({ ...base, skills: [...skills, nextCandidate] }) > budget.maxTokens) break
      skills.push(nextCandidate)
    }

    const failureFamilies: DecisionFamilyCandidate[] = []
    for (const candidate of retrieval.failureFamilies.slice(0, familyLimit)) {
      const document = this.familyById.get(candidate.familyId)
      const nextCandidate: DecisionFamilyCandidate = {
        familyId: candidate.familyId,
        scores: candidate.scores,
        summary: summarize(document?.description ?? ''),
      }
      if (estimateTokens({ ...base, skills, failureFamilies: [...failureFamilies, nextCandidate] }) > budget.maxTokens) {
        break
      }
      failureFamilies.push(nextCandidate)
    }

    if (skills.length === 0 && failureFamilies.length === 0) return null
    return { task, skills, failureFamilies, budget }
  }

  private isSafe(decision: ParsedProviderDecision, request: DecisionProviderRequest): boolean {
    if (decision.kind === 'abstain') return true
    if (decision.kind === 'create') {
      const family = request.failureFamilies.find(candidate => candidate.familyId === decision.failureFamilyId)
      return family !== undefined && meetsActivationGate(family.scores, this.config)
    }
    const skill = request.skills.find(candidate => candidate.skillId === decision.skillId)
    return skill !== undefined && meetsActivationGate(skill.scores, this.config)
  }

  private fallback(
    retrieval: RouterRetrieval,
    reason: Exclude<FallbackReason, null>,
    startedAt: number,
    calls: number,
    tokens: number,
  ): DecisionOutcome {
    const top = retrieval.skills[0]
    const latencyMs = Math.max(0, this.clock() - startedAt)
    const exhausted = reason === 'budget-exhausted'
    if (top !== undefined && meetsActivationGate(top.scores, this.config)) {
      return {
        decision: {
          kind: 'reuse',
          skillId: top.skillId,
          failureFamilyId: null,
          confidence: top.scores.combined,
          rationale: `deterministic fallback (${reason}): reuse the best gated candidate`,
          source: 'fallback',
          fallbackReason: reason,
        },
        usage: { calls, tokens, latencyMs, exhausted },
      }
    }
    return {
      decision: {
        kind: 'abstain',
        skillId: null,
        failureFamilyId: null,
        confidence: 0,
        rationale: `deterministic fallback (${reason}): evidence is insufficient`,
        source: 'fallback',
        fallbackReason: reason,
      },
      usage: { calls, tokens, latencyMs, exhausted },
    }
  }
}

function activationIsCorrect(row: RouterEvaluationRow): boolean {
  if (row.observation.usefulSkillIds.length === 0) return false
  if (row.result.decision.kind === 'create') return true
  const selected = row.result.decision.skillId
  return selected !== null && row.observation.usefulSkillIds.includes(selected)
}

function observationIssue(path: string, message: string): never {
  throw new RouterError('invalid-observation', 'labeled observation failed validation', [issue(path, 'invalid-observation', message)])
}

/**
 * Compute labeled quality, cost, and safety metrics. Activation count is
 * reported only as a diagnostic; utility requires precision, recall, and lift.
 */
export function computeRouterMetrics(
  rows: readonly RouterEvaluationRow[],
  options: RouterMetricsOptions = {},
): RouterMetrics {
  const recallK = options.recallK ?? 3
  if (!Number.isInteger(recallK) || recallK < 1) {
    throw new RouterError('invalid-metrics', 'recallK must be a positive integer')
  }
  for (const row of rows) {
    if (!isFiniteNumber(row.observation.costUsd) || row.observation.costUsd < 0) {
      observationIssue('observation.costUsd', 'costUsd must be a non-negative finite number')
    }
    if (!isFiniteNumber(row.observation.latencyMs) || row.observation.latencyMs < 0) {
      observationIssue('observation.latencyMs', 'latencyMs must be a non-negative finite number')
    }
    if (row.observation.regressions !== undefined
      && (!Number.isInteger(row.observation.regressions) || row.observation.regressions < 0)) {
      observationIssue('observation.regressions', 'regressions must be a non-negative integer when provided')
    }
  }

  const usefulRows = rows.filter(row => row.observation.usefulSkillIds.length > 0)
  const noSkillRows = rows.filter(row => row.observation.usefulSkillIds.length === 0)
  const activatedRows = rows.filter(row => ACTIVATION_KINDS.has(row.result.decision.kind))
  const recallHits = usefulRows.filter(row => row.result.retrieval.skills
    .slice(0, recallK)
    .some(candidate => row.observation.usefulSkillIds.includes(candidate.skillId)))
  const correctedActivations = activatedRows.filter(activationIsCorrect)
  const falseAbstentions = usefulRows.filter(row => row.result.decision.kind === 'abstain')
  const falseActivations = noSkillRows.filter(row => ACTIVATION_KINDS.has(row.result.decision.kind))
  const passDeltas = activatedRows.map(row =>
    (row.observation.treatmentPassed ? 1 : 0) - (row.observation.baselinePassed ? 1 : 0))
  const regressions = activatedRows.reduce((sum, row) => {
    const derived = row.observation.baselinePassed && !row.observation.treatmentPassed ? 1 : 0
    return sum + (row.observation.regressions ?? derived)
  }, 0)
  const totalCost = rows.reduce((sum, row) => sum + row.observation.costUsd, 0)
  const totalLatency = rows.reduce((sum, row) => sum + row.observation.latencyMs, 0)
  const activationCost = activatedRows.reduce((sum, row) => sum + row.observation.costUsd, 0)
  const activationLatency = activatedRows.reduce((sum, row) => sum + row.observation.latencyMs, 0)
  const total = rows.length

  return {
    observations: total,
    usefulObservations: usefulRows.length,
    noSkillObservations: noSkillRows.length,
    activations: activatedRows.length,
    abstentions: total - activatedRows.length,
    recallK,
    usefulSkillRecallAtK: usefulRows.length === 0 ? 0 : recallHits.length / usefulRows.length,
    activationPrecision: activatedRows.length === 0 ? 0 : correctedActivations.length / activatedRows.length,
    falseAbstentionRate: usefulRows.length === 0 ? 0 : falseAbstentions.length / usefulRows.length,
    falseActivationRate: noSkillRows.length === 0 ? 0 : falseActivations.length / noSkillRows.length,
    activationRate: total === 0 ? 0 : activatedRows.length / total,
    passLiftPerActivation: activatedRows.length === 0
      ? 0
      : passDeltas.reduce((sum, value) => sum + value, 0) / activatedRows.length,
    meanCostUsd: total === 0 ? 0 : totalCost / total,
    meanLatencyMs: total === 0 ? 0 : totalLatency / total,
    costPerActivation: activatedRows.length === 0 ? 0 : activationCost / activatedRows.length,
    latencyPerActivation: activatedRows.length === 0 ? 0 : activationLatency / activatedRows.length,
    regressions,
  }
}
