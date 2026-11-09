import { describe, expect, it } from 'vitest'
import { PythonWorkerClient, type WorkerTransport } from '../src/adapters/python-worker.ts'
import { WORKER_PROTOCOL_VERSION, type WorkerRequest } from '../src/contracts/protocol.ts'
import { WorkerProtocolError } from '../src/contracts/errors.ts'

const request = {
  protocolVersion: WORKER_PROTOCOL_VERSION,
  requestId: 'req-1',
  operation: 'extract-trace',
  input: { trace: 'trace-1' },
  limits: { wallSeconds: 10, outputBytes: 4096 },
} as const

function transport(result: (request: WorkerRequest) => unknown): WorkerTransport {
  return { invoke: async (value) => result(value) }
}

describe('python worker client', () => {
  it('validates one request/result pair', async () => {
    const client = new PythonWorkerClient(transport((value) => ({
      protocolVersion: WORKER_PROTOCOL_VERSION,
      requestId: value.requestId,
      status: 'ok',
      output: { turns: 2 },
    })))
    const result = await client.call(request)
    expect(result.status).toBe('ok')
  })

  it('rejects a mismatched result request id', async () => {
    const client = new PythonWorkerClient(transport(() => ({
      protocolVersion: WORKER_PROTOCOL_VERSION,
      requestId: 'req-other',
      status: 'ok',
      output: {},
    })))
    await expect(client.call(request)).rejects.toBeInstanceOf(WorkerProtocolError)
  })

  it('passes a structured worker failure through', async () => {
    const client = new PythonWorkerClient(transport((value) => ({
      protocolVersion: WORKER_PROTOCOL_VERSION,
      requestId: value.requestId,
      status: 'error',
      error: { code: 'unknown-trace', message: 'missing' },
    })))
    const result = await client.call(request)
    expect(result.status).toBe('error')
  })
})
