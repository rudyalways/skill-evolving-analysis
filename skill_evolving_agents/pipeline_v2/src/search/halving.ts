import type { SearchCandidate } from './contracts.ts'

/** One successive-halving round with a deterministic evaluation budget. */
export interface HalvingRound {
  readonly round: number
  readonly candidates: number
  readonly budgetUnits: number
}

/** Bounded schedule options for successive halving. */
export interface HalvingOptions {
  readonly rounds: number
  readonly keepFraction: number
  readonly minimumSurvivors: number
}

/** Deterministic round schedule; no evaluation is performed here. */
export function successiveHalvingSchedule(
  candidateCount: number,
  options: HalvingOptions,
): readonly HalvingRound[] {
  if (!Number.isInteger(candidateCount) || candidateCount < 1) {
    throw new Error('candidateCount must be a positive integer')
  }
  if (!Number.isInteger(options.rounds) || options.rounds < 1) {
    throw new Error('rounds must be a positive integer')
  }
  if (!(options.keepFraction > 0 && options.keepFraction < 1)) {
    throw new Error('keepFraction must be between 0 and 1')
  }
  if (!Number.isInteger(options.minimumSurvivors) || options.minimumSurvivors < 1) {
    throw new Error('minimumSurvivors must be a positive integer')
  }
  const rounds: HalvingRound[] = []
  let remaining = candidateCount
  for (let index = 0; index < options.rounds; index += 1) {
    rounds.push({ round: index + 1, candidates: remaining, budgetUnits: 2 ** index })
    remaining = Math.max(
      options.minimumSurvivors,
      Math.ceil(remaining * options.keepFraction),
    )
    if (remaining >= candidateCount) break
  }
  return rounds
}

/** Keep the highest-scoring candidates with a stable id tie-break. */
export function selectSurvivors(
  candidates: readonly SearchCandidate[],
  scores: Readonly<Record<string, number>>,
  keepFraction: number,
): readonly SearchCandidate[] {
  if (!(keepFraction > 0 && keepFraction <= 1)) {
    throw new Error('keepFraction must be in (0, 1]')
  }
  const keep = Math.max(1, Math.ceil(candidates.length * keepFraction))
  return [...candidates]
    .sort((left, right) => {
      const leftScore = scores[left.candidateId] ?? Number.NEGATIVE_INFINITY
      const rightScore = scores[right.candidateId] ?? Number.NEGATIVE_INFINITY
      return rightScore - leftScore || left.candidateId.localeCompare(right.candidateId)
    })
    .slice(0, keep)
}
