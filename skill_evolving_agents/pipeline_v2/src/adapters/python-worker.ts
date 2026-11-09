import { WorkerProtocolError, type StructuredIssue } from '../contracts/errors.ts'
import {
  WORKER_PROTOCOL_VERSION,
  parseWorkerRequest,
  parseWorkerResult,
  type WorkerRequest,
  type WorkerResult,
} from '../contracts/protocol.ts'

/** Transport that carries exactly one validated request to a worker process. */
export interface WorkerTransport {
  invoke(request: WorkerRequest): Promise<unknown>
}

/** Validated client for a future Python legacy/worker adapter. */
export class PythonWorkerClient {
  constructor(private readonly transport: WorkerTransport) {}

  async call(value: unknown): Promise<WorkerResult> {
    const request = parseWorkerRequest(value)
    const raw = await this.transport.invoke(request)
    const result = parseWorkerResult(raw)
    if (result.requestId !== request.requestId) {
      const issue: StructuredIssue = {
        path: '$.requestId',
        code: 'mismatch',
        message: `result requestId ${result.requestId} does not match request ${request.requestId}`,
      }
      throw new WorkerProtocolError([issue])
    }
    if (result.protocolVersion !== WORKER_PROTOCOL_VERSION) {
      throw new WorkerProtocolError([{
        path: '$.protocolVersion',
        code: 'unsupported',
        message: 'result protocol version is not supported',
      }])
    }
    return result
  }
}
