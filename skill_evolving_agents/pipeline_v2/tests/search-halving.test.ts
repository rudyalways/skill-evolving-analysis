import { describe, expect, it } from 'vitest'
import {
  selectSurvivors,
  successiveHalvingSchedule,
} from '../src/search/halving.ts'
import type { SearchCandidate } from '../src/search/contracts.ts'

function candidate(candidateId: string): SearchCandidate {
  return { candidateId, overrides: {}, sources: ['wide'] }
}

describe('successive halving', () => {
  it('builds a deterministic bounded schedule', () => {
    expect(successiveHalvingSchedule(16, { rounds: 3, keepFraction: 0.5, minimumSurvivors: 2 }))
      .toEqual([
        { round: 1, candidates: 16, budgetUnits: 1 },
        { round: 2, candidates: 8, budgetUnits: 2 },
        { round: 3, candidates: 4, budgetUnits: 4 },
      ])
  })

  it('selects by score with a stable id tie-break', () => {
    const rows = [candidate('b'), candidate('a'), candidate('c')]
    expect(selectSurvivors(rows, { a: 1, b: 1, c: 3 }, 0.34).map(row => row.candidateId))
      .toEqual(['c', 'a'])
    expect(selectSurvivors(rows, { a: 1, b: 1, c: 3 }, 0.3).map(row => row.candidateId))
      .toEqual(['c'])
  })

  it('rejects invalid options', () => {
    expect(() => successiveHalvingSchedule(0, { rounds: 1, keepFraction: 0.5, minimumSurvivors: 1 }))
      .toThrow('candidateCount')
    expect(() => selectSurvivors([candidate('a')], {}, 0)).toThrow('keepFraction')
  })
})
