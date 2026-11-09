import { describe, expect, it } from 'vitest'
import {
  WORKER_PROTOCOL_VERSION,
  parseWorkerRequest,
  parseWorkerResult,
} from '../src/contracts/protocol.ts'
import { WorkerProtocolError } from '../src/contracts/errors.ts'

const request = {
  protocolVersion: WORKER_PROTOCOL_VERSION,
  requestId: 'req-1',
  operation: 'detect',
  input: { trace: 'trace-1' },
  limits: { wallSeconds: 30, outputBytes: 4096 },
}

describe('versioned worker protocol', () => {
  it('parses a valid request', () => {
    expect(parseWorkerRequest(request)).toEqual(request)
  })

  it('rejects an unsupported protocol version with structured issues', () => {
    try {
      parseWorkerRequest({ ...request, protocolVersion: 2 })
      throw new Error('expected protocol failure')
    } catch (error) {
      expect(error).toBeInstanceOf(WorkerProtocolError)
      expect((error as WorkerProtocolError).issues[0]?.path).toBe(
        '$.protocolVersion',
      )
    }
  })

  it('rejects invalid limits', () => {
    expect(() => parseWorkerRequest({ ...request, limits: { wallSeconds: 0, outputBytes: 1 } }))
      .toThrow(WorkerProtocolError)
  })

  it('parses an ok result and a structured error result', () => {
    expect(parseWorkerResult({
      protocolVersion: WORKER_PROTOCOL_VERSION,
      requestId: 'req-1',
      status: 'ok',
      output: { findings: [] },
    }).status).toBe('ok')
    expect(parseWorkerResult({
      protocolVersion: WORKER_PROTOCOL_VERSION,
      requestId: 'req-1',
      status: 'error',
      error: { code: 'unknown-trace', message: 'missing' },
    }).status).toBe('error')
  })

  it('rejects a result without a status-specific payload', () => {
    expect(() => parseWorkerResult({
      protocolVersion: WORKER_PROTOCOL_VERSION,
      requestId: 'req-1',
      status: 'error',
    })).toThrow(WorkerProtocolError)
  })
})
