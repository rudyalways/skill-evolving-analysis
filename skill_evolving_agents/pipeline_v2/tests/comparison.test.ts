import { describe, expect, it } from 'vitest'
import {
  COMPARISON_REPORT_VERSION,
  assertComparisonReport,
  validateComparisonReport,
} from '../src/contracts/comparison.ts'
import { InvalidComparisonReportError } from '../src/contracts/errors.ts'

function report() {
  return {
    schemaVersion: COMPARISON_REPORT_VERSION,
    runId: 'run-1',
    traceId: 'trace-1',
    eventCount: 4,
    eventIds: ['evt-1', 'evt-2', 'evt-3', 'evt-4'],
    projectionStatus: 'completed',
    projection: { status: 'completed', eventCount: 4 },
    selectedSkillId: 'skill-1',
    operationId: 'op-1',
    resources: [{ kind: 'scripts', path: 'scripts/guard.py', status: 'generated' }],
    replay: { available: true, status: 'pass', evidenceHash: 'sha256:abc' },
    usage: { agentCalls: 2, tokens: 1200, costUsd: null },
    output: { equivalence: 'equivalent', notes: 'match' },
    cleanup: { disposed: true, leakedRegistrations: 0 },
  }
}

describe('legacy comparison report schema', () => {
  it('accepts a complete report', () => {
    expect(validateComparisonReport(report())).toEqual([])
    expect(assertComparisonReport(report()).eventCount).toBe(4)
  })

  it('rejects an unsupported version and leaked registrations', () => {
    try {
      assertComparisonReport({
        ...report(),
        schemaVersion: 2,
        cleanup: { disposed: false, leakedRegistrations: 1 },
      })
      throw new Error('expected schema failure')
    } catch (error) {
      expect(error).toBeInstanceOf(InvalidComparisonReportError)
      const issues = (error as InvalidComparisonReportError).issues
      expect(issues.map((item) => item.path)).toContain('$.schemaVersion')
      expect(issues.map((item) => item.path)).toContain('$.cleanup.leakedRegistrations')
    }
  })
})
