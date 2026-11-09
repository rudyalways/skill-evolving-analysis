import { describe, expect, it } from 'vitest'
import { RunController } from '../src/core/run-controller.ts'
import { runId } from '../src/contracts/ids.ts'

describe('deterministic run controller', () => {
  it('assigns deterministic event ids and projects the run', () => {
    const controller = new RunController(runId('run-1'))
    const first = controller.start('improve', 'default', '2026-11-09T00:00:00.000Z')
    expect(first.id).toBe('run-1:evt:1')
    expect(controller.snapshot().status).toBe('running')
    expect(controller.snapshot().eventCount).toBe(1)
  })
})
