import type {
  ConfigurationSearch,
} from '../capabilities/definitions.ts'
import type { KnobValue, SearchCandidate, SearchRequest } from './contracts.ts'

function hash(text: string): string {
  let value = 2166136261
  for (const character of text) {
    value ^= character.charCodeAt(0)
    value = Math.imul(value, 16777619)
  }
  return (value >>> 0).toString(16).padStart(8, '0')
}

function encoded(overrides: Readonly<Record<string, KnobValue>>): string {
  return JSON.stringify(Object.entries(overrides).sort(([left], [right]) => left.localeCompare(right)))
}

function distance(left: SearchCandidate, right: SearchCandidate): number {
  const names = new Set([...Object.keys(left.overrides), ...Object.keys(right.overrides)])
  let differences = 0
  for (const name of names) if (left.overrides[name] !== right.overrides[name]) differences += 1
  return differences / Math.max(names.size, 1)
}

/** Deterministic wide, deep, MCTS-like, and random candidate portfolio. */
export class PortfolioConfigurationSearch implements ConfigurationSearch {
  search(request: SearchRequest): readonly SearchCandidate[] {
    if (!Number.isInteger(request.count) || request.count < 1) throw new Error('count must be positive')
    if (request.count > 256) throw new Error('count exceeds 256 candidate safety limit')
    const names = new Set<string>()
    for (const domain of request.domains) {
      if (names.has(domain.name)) throw new Error(`duplicate knob domain ${domain.name}`)
      names.add(domain.name)
      if (domain.values.length === 0) throw new Error(`empty knob domain ${domain.name}`)
      if (!domain.values.includes(domain.defaultValue)) {
        throw new Error(`default is outside knob domain ${domain.name}`)
      }
    }
    const pool = new Map<string, SearchCandidate>()
    const add = (
      overrides: Readonly<Record<string, KnobValue>>,
      source: SearchCandidate['sources'][number],
    ): void => {
      const key = encoded(overrides)
      const existing = pool.get(key)
      pool.set(key, {
        candidateId: `candidate-${hash(key)}`,
        overrides,
        sources: existing ? [...new Set([...existing.sources, source])] : [source],
      })
    }
    for (const domain of request.domains) {
      for (const value of domain.values) add({ [domain.name]: value }, 'wide')
    }
    const eligibleHistory = request.history.filter(row => row.stage === 'validation' && row.samples >= 12)
    const best = [...eligibleHistory].sort((left, right) => right.validationReward - left.validationReward)[0]
    add(best?.overrides ?? Object.fromEntries(request.domains.map(row => [row.name, row.defaultValue])), 'deep')
    if (best) add(best.overrides, 'mcts')
    let state = request.seed >>> 0
    const random = (): number => {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0
      return state / 4294967296
    }
    for (let index = 0; index < Math.max(request.count * 4, 16); index += 1) {
      const overrides: Record<string, KnobValue> = {}
      for (const domain of request.domains) {
        const choice = domain.values[Math.floor(random() * domain.values.length)]
        if (choice !== undefined) overrides[domain.name] = choice
      }
      add(overrides, index % 2 === 0 ? 'random' : 'mcts')
    }
    const chosen: SearchCandidate[] = []
    const remaining = [...pool.values()]
    while (remaining.length > 0 && chosen.length < request.count) {
      remaining.sort((left, right) => {
        const leftNovelty = Math.min(...chosen.map(row => distance(left, row)), 1)
        const rightNovelty = Math.min(...chosen.map(row => distance(right, row)), 1)
        return rightNovelty - leftNovelty || right.sources.length - left.sources.length
          || left.candidateId.localeCompare(right.candidateId)
      })
      const next = remaining.shift()
      if (next) chosen.push(next)
    }
    return chosen
  }
}
