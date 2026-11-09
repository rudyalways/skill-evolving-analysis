import { describe, expect, it } from 'vitest'
import { EventLog, validateEvent } from '../src/core/event-log.ts'
import {
  DuplicateEventError,
  EventValidationError,
  InvalidIdError,
  InvalidTransitionError,
  RunIdMismatchError,
  DuplicateResourceError,
  UnsupportedEventVersionError,
} from '../src/contracts/errors.ts'
import { runId } from '../src/contracts/ids.ts'

const AT = '2026-11-09T00:00:00.000Z'

function started(overrides: Record<string, unknown> = {}) {
  return {
    id: 'evt-1',
    runId: 'run-1',
    type: 'run/started',
    version: 1,
    at: AT,
    payload: { objective: 'improve a skill', profile: 'default' },
    ...overrides,
  }
}

function trace(id = 'evt-2') {
  return {
    id,
    runId: 'run-1',
    type: 'trace/ingested',
    version: 1,
    at: AT,
    payload: { traceId: 'trace-1', source: 'fixture', turns: 1 },
  }
}

function operationPlanned(id = 'evt-2') {
  return {
    id,
    runId: 'run-1',
    type: 'operation/planned',
    version: 1,
    at: AT,
    payload: {
      operation: {
        id: 'op-1',
        kind: 'update',
        skillId: 'skill-1',
        findingId: 'finding-1',
        summary: 'tighten the workflow',
      },
    },
  }
}

function verification(id = 'evt-3') {
  return {
    id,
    runId: 'run-1',
    type: 'verification/completed',
    version: 1,
    at: AT,
    payload: { operationId: 'op-1', status: 'pass', summary: 'checker passed' },
  }
}

function accepted(id = 'evt-4') {
  return {
    id,
    runId: 'run-1',
    type: 'operation/accepted',
    version: 1,
    at: AT,
    payload: { operationId: 'op-1', reason: 'verified' },
  }
}

function verificationWith(status: 'pass' | 'fail' | 'efficiency_failure', id: string) {
  return {
    id,
    runId: 'run-1',
    type: 'verification/completed',
    version: 1,
    at: AT,
    payload: { operationId: 'op-1', status, summary: 'checker result' },
  }
}

function rejected(id = 'evt-4') {
  return {
    id,
    runId: 'run-1',
    type: 'operation/rejected',
    version: 1,
    at: AT,
    payload: { operationId: 'op-1', reason: 'failed verification' },
  }
}

function published(id = 'evt-5') {
  return {
    id,
    runId: 'run-1',
    type: 'publication/completed',
    version: 1,
    at: AT,
    payload: { operationId: 'op-1', releaseId: 'release-1', channel: 'provisional' },
  }
}

function resource(id = 'res-1', event = 'evt-4') {
  return {
    id: event,
    runId: 'run-1',
    type: 'resource/generated',
    version: 1,
    at: AT,
    payload: {
      resource: {
        id,
        operationId: 'op-1',
        skillId: 'skill-1',
        kind: 'scripts',
        path: 'scripts/guard.py',
        status: 'generated',
      },
    },
  }
}

describe('branded ids', () => {
  it('rejects empty ids with a structured error', () => {
    expect(() => runId('')).toThrow(InvalidIdError)
  })
})

describe('event validation', () => {
  it('accepts a valid run/started event', () => {
    const log = new EventLog()
    expect(log.append(started()).type).toBe('run/started')
    expect(validateEvent(started())).toEqual([])
    expect(Object.isFrozen(log.events[0])).toBe(true)
  })

  it('rejects an unsupported event version before payload validation', () => {
    const log = new EventLog()
    expect(() => log.append({ ...started(), version: 2 })).toThrow(
      UnsupportedEventVersionError,
    )
  })

  it('rejects a missing payload field with a structured issue path', () => {
    const log = new EventLog()
    try {
      log.append(started({ payload: { profile: 'default' } }))
      throw new Error('expected validation failure')
    } catch (error) {
      expect(error).toBeInstanceOf(EventValidationError)
      expect((error as EventValidationError).issues[0]?.path).toBe('$.payload.objective')
    }
  })

  it('rejects a duplicate event id', () => {
    const log = new EventLog()
    log.append(started())
    expect(() => log.append(trace('evt-1'))).toThrow(DuplicateEventError)
  })

  it('rejects an event before run/started', () => {
    const log = new EventLog()
    expect(() => log.append(trace())).toThrow(InvalidTransitionError)
  })

  it('rejects acceptance before verification and before planning', () => {
    const log = new EventLog()
    log.append(started())
    expect(() => log.append(accepted())).toThrow(InvalidTransitionError)
    log.append(operationPlanned())
    expect(() => log.append(accepted())).toThrow(InvalidTransitionError)
    log.append(verification())
    expect(log.append(accepted()).type).toBe('operation/accepted')
  })

  it('rejects events after a terminal run', () => {
    const log = new EventLog()
    log.append(started())
    log.append({
      id: 'evt-2',
      runId: 'run-1',
      type: 'run/completed',
      version: 1,
      at: AT,
      payload: { summary: 'done' },
    })
    expect(() => log.append(trace('evt-3'))).toThrow(InvalidTransitionError)
  })

  it('rejects events from a different run', () => {
    const log = new EventLog()
    log.append(started())
    expect(() => log.append({ ...trace(), runId: 'run-2' })).toThrow(
      RunIdMismatchError,
    )
  })

  it('does not reopen a verified operation after acceptance', () => {
    const log = new EventLog()
    log.append(started())
    log.append(operationPlanned())
    log.append(verification())
    log.append(accepted())
    expect(() => log.append(verification('evt-5'))).toThrow(
      InvalidTransitionError,
    )
  })

  it('rejects duplicate resource ids instead of overwriting', () => {
    const log = new EventLog()
    log.append(started())
    log.append(operationPlanned())
    log.append(resource('res-1', 'evt-3'))
    expect(() => log.append(resource('res-1', 'evt-4'))).toThrow(
      DuplicateResourceError,
    )
    expect(log.length).toBe(3)
  })

  it('does not reopen an operation after rejection', () => {
    const log = new EventLog()
    log.append(started())
    log.append(operationPlanned())
    log.append(verificationWith('fail', 'evt-3'))
    log.append(rejected())
    expect(() => log.append(verificationWith('pass', 'evt-5'))).toThrow(
      InvalidTransitionError,
    )
  })

  it('does not reopen an operation after publication', () => {
    const log = new EventLog()
    log.append(started())
    log.append(operationPlanned())
    log.append(verificationWith('pass', 'evt-3'))
    log.append(accepted())
    log.append(published())
    expect(() => log.append(verificationWith('pass', 'evt-6'))).toThrow(
      InvalidTransitionError,
    )
  })

  it('rolls back appendAll when a later event is invalid', () => {
    const log = new EventLog()
    expect(() => log.appendAll([started(), trace('evt-2'), { ...trace('evt-3'), version: 9 }]))
      .toThrow(UnsupportedEventVersionError)
    expect(log.length).toBe(0)
  })
})
