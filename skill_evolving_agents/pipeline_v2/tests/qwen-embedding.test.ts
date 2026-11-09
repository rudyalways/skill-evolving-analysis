import { spawn } from 'node:child_process'
import type { ChildProcess } from 'node:child_process'
import { mkdtemp, readdir, rm } from 'node:fs/promises'
import { createServer } from 'node:http'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

import { skillId } from '../src/contracts/ids.ts'
import {
  DeterministicEmbeddingProvider,
  TwoStageRouter,
} from '../src/router/two-stage-router.ts'
import type { EmbeddingProvider, RouterTask, SkillDocument } from '../src/router/two-stage-router.ts'
import {
  FALLBACK_EMBEDDING_MODEL,
  QwenEmbeddingError,
  QwenEmbeddingProvider,
  embeddingCacheKey,
  probeInProcessEmbeddingRuntime,
} from '../src/router/qwen-embedding.ts'
import type { QwenEmbeddingOptions } from '../src/router/qwen-embedding.ts'

interface RecordedRequest {
  readonly method: string
  readonly path: string
  readonly body: string
}

interface TestResponse {
  readonly status?: number
  readonly body: string
  readonly delayMs?: number
}

type TestHandler = (request: RecordedRequest, index: number) => TestResponse | Promise<TestResponse>

interface TestServer {
  readonly url: string
  readonly requests: RecordedRequest[]
  close(): Promise<void>
}

const TEXTS = ['alpha', 'beta', 'gamma', 'delta', 'epsilon'] as const

const VECTORS: Readonly<Record<string, readonly number[]>> = {
  alpha: [3, 4, 0],
  beta: [0, 5, 0],
  gamma: [1, 2, 2],
  delta: [1, 0, 0],
  epsilon: [2, 0, 1],
}

const servers: TestServer[] = []
const children: ChildProcess[] = []
const tempDirectories: string[] = []

function isRecordValue(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readInput(body: string): readonly string[] {
  const parsed: unknown = JSON.parse(body)
  if (!isRecordValue(parsed) || !Array.isArray(parsed.input)) {
    throw new Error('embedding request body must contain an input array')
  }
  const input: string[] = []
  for (const value of parsed.input) {
    if (typeof value !== 'string') throw new Error('embedding request input must be strings')
    input.push(value)
  }
  return input
}

function vectorsFor(input: readonly string[]): readonly (readonly number[])[] {
  return input.map(text => VECTORS[text] ?? [0, 0, 1])
}

function embeddingsResponse(vectors: readonly (readonly number[])[]): string {
  return JSON.stringify({ data: vectors.map((embedding, index) => ({ embedding, index })) })
}

function norm(vector: readonly number[]): number {
  return Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0))
}

async function readBody(request: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = []
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk)))
  }
  return Buffer.concat(chunks).toString('utf8')
}

async function startServer(handler: TestHandler): Promise<TestServer> {
  const requests: RecordedRequest[] = []
  const server = createServer((request: IncomingMessage, response: ServerResponse) => {
    void (async () => {
      const body = await readBody(request)
      const recorded: RecordedRequest = {
        method: request.method ?? 'GET',
        path: request.url ?? '/',
        body,
      }
      requests.push(recorded)
      try {
        const result = await handler(recorded, requests.length - 1)
        if (result.delayMs !== undefined) {
          await new Promise<void>(resolve => setTimeout(resolve, result.delayMs))
        }
        if (response.destroyed || response.writableEnded) return
        response.writeHead(result.status ?? 200, { 'content-type': 'application/json' })
        response.end(result.body)
      } catch (error) {
        try {
          if (response.destroyed || response.writableEnded) return
          response.writeHead(500, { 'content-type': 'application/json' })
          response.end(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }))
        } catch {
          // The client aborted; there is no response left to write.
        }
      }
    })()
  })

  await new Promise<void>((resolve, reject) => {
    const onError = (error: Error): void => reject(error)
    server.once('error', onError)
    server.listen(0, '127.0.0.1', () => {
      server.off('error', onError)
      resolve()
    })
  })

  const address = server.address()
  if (address === null || typeof address === 'string') {
    await new Promise<void>(resolve => server.close(() => resolve()))
    throw new Error('test embedding server did not bind a TCP port')
  }

  const testServer: TestServer = {
    url: `http://127.0.0.1:${address.port}`,
    requests,
    close: async () => {
      server.closeAllConnections()
      await new Promise<void>((resolve, reject) => {
        server.close(error => {
          if (error !== undefined) reject(error)
          else resolve()
        })
      })
    },
  }
  servers.push(testServer)
  return testServer
}

function createProvider(
  server: TestServer,
  overrides: Partial<QwenEmbeddingOptions> = {},
): QwenEmbeddingProvider {
  return new QwenEmbeddingProvider({
    baseUrl: server.url,
    model: 'qwen3-embedding-test',
    revision: 'rev-1',
    timeoutMs: 1_000,
    ...overrides,
  })
}

function childServerUrl(child: ChildProcess): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    let output = ''
    let settled = false
    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      reject(new Error('child embedding server did not report a port'))
    }, 5_000)

    child.stdout?.on('data', (chunk: Buffer) => {
      output += chunk.toString('utf8')
      const line = output.split('\n')[0]
      if (settled || line === undefined || line.trim().length === 0) return
      settled = true
      clearTimeout(timer)
      resolve(`http://127.0.0.1:${line.trim()}`)
    })
    child.once('error', error => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(error)
    })
    child.once('exit', code => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(new Error(`child embedding server exited with code ${String(code)}`))
    })
  })
}

const SYNC_HTTP_SERVER_SOURCE = `
const { createServer } = require('node:http')
const server = createServer((request, response) => {
  let body = ''
  request.on('data', chunk => { body += chunk })
  request.on('end', () => {
    const payload = JSON.parse(body)
    const data = payload.input.map((text, index) => ({
      embedding: [text.length, 1, 0.5],
      index,
    }))
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify({ data }))
  })
})
server.listen(0, '127.0.0.1', () => {
  const address = server.address()
  process.stdout.write(String(address.port) + '\\n')
})
`

function skillText(skill: SkillDocument): string {
  return [skill.name, skill.description, ...(skill.keywords ?? []), skill.text ?? ''].join(' ')
}

class RecordingInProcessProvider implements EmbeddingProvider {
  calls = 0

  embed(texts: readonly string[]): readonly (readonly number[])[] {
    this.calls += 1
    return texts.map(text => [text.length, 2, 1])
  }
}

afterEach(async () => {
  await Promise.all(servers.splice(0).map(server => server.close()))
  for (const child of children.splice(0)) {
    if (child.exitCode === null) child.kill('SIGTERM')
  }
  await Promise.all(tempDirectories.splice(0).map(directory => rm(directory, { recursive: true, force: true })))
})

describe('QwenEmbeddingProvider HTTP transport', () => {
  it('batches inputs, preserves order, and L2-normalizes vectors', async () => {
    const server = await startServer(request => ({
      body: embeddingsResponse(vectorsFor(readInput(request.body))),
    }))
    const provider = createProvider(server, { baseUrl: `${server.url}/v1`, batchSize: 2 })

    const result = await provider.embedAsyncWithReport(TEXTS)

    expect(server.requests).toHaveLength(3)
    expect(server.requests.map(request => readInput(request.body).length)).toEqual([2, 2, 1])
    expect(server.requests[0]?.path).toBe('/v1/embeddings')
    expect(server.requests[0]?.body).toContain('"model":"qwen3-embedding-test"')
    expect(server.requests[0]?.body).toContain('"input"')
    expect(result.report).toMatchObject({
      source: 'qwen',
      model: 'qwen3-embedding-test',
      revision: 'rev-1',
      degraded: false,
      degradationReason: null,
      error: null,
      cacheHits: 0,
      cacheMisses: 5,
      batches: 3,
      dimensions: 3,
    })
    expect(result.report.latencyMs).toBeGreaterThanOrEqual(0)
    expect(result.vectors).toHaveLength(TEXTS.length)

    TEXTS.forEach((text, index) => {
      const expected = VECTORS[text] ?? [0, 0, 1]
      const expectedNorm = norm(expected)
      const actual = result.vectors[index] ?? []
      expect(actual).toHaveLength(expected.length)
      expect(norm(actual)).toBeCloseTo(1, 10)
      expected.forEach((value, position) => {
        expect(actual[position] ?? 0).toBeCloseTo(value / expectedNorm, 10)
      })
    })
  })

  it('serves repeated inputs from the content-addressed cache and records hits', async () => {
    const server = await startServer(request => ({
      body: embeddingsResponse(vectorsFor(readInput(request.body))),
    }))
    const provider = createProvider(server)

    const first = await provider.embedAsyncWithReport(TEXTS)
    const second = await provider.embedAsyncWithReport(TEXTS)

    expect(server.requests).toHaveLength(1)
    expect(first.report).toMatchObject({ cacheHits: 0, cacheMisses: 5, batches: 1 })
    expect(second.report).toMatchObject({ cacheHits: 5, cacheMisses: 0, batches: 0, degraded: false })
    expect(second.vectors).toEqual(first.vectors)
    expect(provider.stats()).toMatchObject({
      calls: 2,
      cacheHits: 5,
      cacheMisses: 5,
      batches: 1,
      degradedCalls: 0,
      failures: 0,
    })
    expect(provider.lastReport()).toEqual(second.report)
  })

  it('persists content-addressed vectors in an optional disk cache', async () => {
    const server = await startServer(request => ({
      body: embeddingsResponse(vectorsFor(readInput(request.body))),
    }))
    const directory = await mkdtemp(join(tmpdir(), 'qwen-embedding-cache-'))
    tempDirectories.push(directory)

    const first = createProvider(server, { cache: { directory } })
    const firstVectors = await first.embedAsync(TEXTS)
    expect(server.requests).toHaveLength(1)
    const files = await readdir(directory, { recursive: true })
    expect(files.filter(file => file.endsWith('.json'))).toHaveLength(TEXTS.length)

    const second = createProvider(server, { cache: { directory } })
    const result = await second.embedAsyncWithReport(TEXTS)
    expect(server.requests).toHaveLength(1)
    expect(result.report).toMatchObject({
      cacheHits: 5,
      diskHits: 5,
      cacheMisses: 0,
      batches: 0,
      degraded: false,
    })
    expect(result.vectors).toEqual(firstVectors)
  })

  it('builds stable cache keys from runtime, model, revision, normalization, and text', () => {
    const key = embeddingCacheKey('http', 'model-a', 'rev-1', true, 'same text')
    expect(key).toMatch(/^[0-9a-f]{64}$/)
    expect(embeddingCacheKey('http', 'model-a', 'rev-1', true, 'same text')).toBe(key)
    expect(embeddingCacheKey('http', 'model-a', 'rev-2', true, 'same text')).not.toBe(key)
    expect(embeddingCacheKey('http', 'model-b', 'rev-1', true, 'same text')).not.toBe(key)
    expect(embeddingCacheKey('http', 'model-a', 'rev-1', false, 'same text')).not.toBe(key)
    expect(embeddingCacheKey('http', 'model-a', 'rev-1', true, 'other text')).not.toBe(key)
    expect(embeddingCacheKey('in-process', 'model-a', 'rev-1', true, 'same text')).not.toBe(key)
  })

  it('falls back with a timeout report when the endpoint is too slow', async () => {
    const server = await startServer(() => ({
      body: embeddingsResponse([[1, 0, 0]]),
      delayMs: 300,
    }))
    const provider = createProvider(server, { timeoutMs: 50 })

    const result = await provider.embedAsyncWithReport(['alpha', 'beta'])
    const expected = new DeterministicEmbeddingProvider().embed(['alpha', 'beta'])

    expect(result.report).toMatchObject({
      source: 'fallback',
      model: FALLBACK_EMBEDDING_MODEL,
      requestedModel: 'qwen3-embedding-test',
      requestedRevision: 'rev-1',
      degraded: true,
      degradationReason: 'http-timeout',
    })
    expect(result.report.error).toContain('50ms')
    expect(result.vectors).toEqual(expected)
    expect(provider.stats()).toMatchObject({ calls: 1, degradedCalls: 1, failures: 1 })
  })

  it.each([
    'not json',
    JSON.stringify({ data: [] }),
    JSON.stringify({ data: [{ embedding: [1, 'nope'], index: 0 }] }),
    JSON.stringify({ data: [{ embedding: [1, 2], index: 0 }, { embedding: [1, 2], index: 0 }] }),
  ])('falls back when the response is malformed: %#', async payload => {
    const server = await startServer(() => ({ body: payload }))
    const provider = createProvider(server)

    const result = await provider.embedAsyncWithReport(['alpha'])

    expect(result.report).toMatchObject({
      source: 'fallback',
      degraded: true,
      degradationReason: 'malformed-response',
      model: FALLBACK_EMBEDDING_MODEL,
    })
    expect(result.vectors).toEqual(new DeterministicEmbeddingProvider().embed(['alpha']))
  })

  it('falls back for the whole call when a later batch is malformed', async () => {
    const server = await startServer((request, index) => ({
      body: index === 0
        ? embeddingsResponse(vectorsFor(readInput(request.body)))
        : JSON.stringify({ data: [{ embedding: ['bad'], index: 0 }] }),
    }))
    const provider = createProvider(server, { batchSize: 1 })

    const result = await provider.embedAsyncWithReport(['alpha', 'beta'])

    expect(result.report).toMatchObject({
      source: 'fallback',
      degraded: true,
      degradationReason: 'malformed-response',
      batches: 2,
      cacheMisses: 2,
    })
    expect(result.vectors).toEqual(new DeterministicEmbeddingProvider().embed(['alpha', 'beta']))
  })

  it('handles empty input without calling the endpoint', async () => {
    const server = await startServer(request => ({
      body: embeddingsResponse(vectorsFor(readInput(request.body))),
    }))
    const provider = createProvider(server, { expectedDimensions: 3 })

    const result = await provider.embedAsyncWithReport([])

    expect(result.vectors).toEqual([])
    expect(result.report).toMatchObject({
      cacheHits: 0,
      cacheMisses: 0,
      batches: 0,
      degraded: false,
      dimensions: 0,
    })
    expect(server.requests).toHaveLength(0)
  })

  it('falls back when batches disagree on vector width', async () => {
    const server = await startServer((_request, index) => ({
      body: embeddingsResponse(index === 0 ? [[1, 0]] : [[1, 0, 0]]),
    }))
    const provider = createProvider(server, { batchSize: 1 })

    const result = await provider.embedAsyncWithReport(['alpha', 'beta'])

    expect(result.report).toMatchObject({
      source: 'fallback',
      degraded: true,
      degradationReason: 'malformed-response',
      batches: 2,
    })
    expect(result.vectors).toEqual(new DeterministicEmbeddingProvider().embed(['alpha', 'beta']))
  })

  it('reports health success and failure without throwing', async () => {
    const healthy = await startServer(request => request.path === '/health'
      ? { body: '{"status":"ok"}' }
      : { status: 404, body: '{}' })
    const healthyProvider = createProvider(healthy)
    const ok = await healthyProvider.health()

    expect(healthy.requests[0]?.method).toBe('GET')
    expect(ok).toMatchObject({
      ok: true,
      model: 'qwen3-embedding-test',
      revision: 'rev-1',
      degraded: false,
      status: 200,
      error: null,
    })
    expect(ok.latencyMs).toBeGreaterThanOrEqual(0)

    const failing = await startServer(() => ({ status: 503, body: '{"error":"unavailable"}' }))
    const failingProvider = createProvider(failing)
    const down = await failingProvider.health()

    expect(down.ok).toBe(false)
    expect(down.degraded).toBe(true)
    expect(down.status).toBe(503)
    expect(down.error).toContain('503')
  })

  it('rejects invalid configuration with structured issues', () => {
    expect(() => new QwenEmbeddingProvider({ batchSize: 0 })).toThrowError(QwenEmbeddingError)

    let thrown: unknown = null
    try {
      new QwenEmbeddingProvider({ baseUrl: 'ftp://embedding.test' })
    } catch (error) {
      thrown = error
    }
    expect(thrown).toBeInstanceOf(QwenEmbeddingError)
    if (thrown instanceof QwenEmbeddingError) {
      expect(thrown.code).toBe('invalid-embedding-config')
      expect(thrown.issues.some(entry => entry.path === 'baseUrl')).toBe(true)
    }
  })
})

describe('QwenEmbeddingProvider in-process mode', () => {
  it('falls back with a clear unsupported report when no adapter is supplied', async () => {
    const provider = new QwenEmbeddingProvider({ runtime: 'in-process' })
    const result = provider.embedWithReport(['alpha'])

    expect(result.report).toMatchObject({
      source: 'fallback',
      degraded: true,
      degradationReason: 'in-process-unavailable',
    })
    expect(result.vectors).toEqual(new DeterministicEmbeddingProvider().embed(['alpha']))
    expect(provider.capabilities()).toMatchObject({
      runtime: 'in-process',
      syncHttp: false,
      asyncHttp: false,
      diskCache: false,
    })
    expect(provider.capabilities().inProcess.checked.length).toBeGreaterThan(0)
    expect(probeInProcessEmbeddingRuntime().reason.length).toBeGreaterThan(0)

    const health = await provider.health()
    expect(health.ok).toBe(false)
    expect(health.degraded).toBe(true)
    expect(health.status).toBeNull()
  })

  it('uses an explicit in-process adapter and normalizes its vectors', () => {
    const adapter = new RecordingInProcessProvider()
    const provider = new QwenEmbeddingProvider({ runtime: 'in-process', inProcess: adapter })

    const result = provider.embedWithReport(['alpha', 'beta'])

    expect(adapter.calls).toBe(1)
    expect(result.report).toMatchObject({
      source: 'in-process',
      degraded: false,
      cacheMisses: 2,
      dimensions: 3,
    })
    expect(result.vectors).toHaveLength(2)
    for (const vector of result.vectors) expect(norm(vector)).toBeCloseTo(1, 10)
  })
})

describe('QwenEmbeddingProvider router integration', () => {
  it('plugs into the existing EmbeddingProvider seam after prewarming', async () => {
    const server = await startServer(request => ({
      body: embeddingsResponse(readInput(request.body).map(text => {
        const lower = text.toLowerCase()
        if (lower.includes('reconcile') || lower.includes('synchronize')) return [1, 0, 0]
        if (lower.includes('paint')) return [0, 1, 0]
        return [0, 0, 1]
      })),
    }))
    const provider = createProvider(server)
    const skills: readonly SkillDocument[] = [
      {
        skillId: skillId('skill:ledger-sync'),
        name: 'Financial record synchronization',
        description: 'Synchronize financial records across the accounting system.',
        family: 'finance',
        intents: ['reconcile'],
        actions: ['synchronize'],
        keywords: ['records', 'accounting'],
      },
      {
        skillId: skillId('skill:wall-paint'),
        name: 'Wall painting',
        description: 'Paint interior walls with a consistent finish.',
        family: 'home',
        intents: ['paint'],
        actions: ['paint'],
        keywords: ['walls'],
      },
    ]
    const task: RouterTask = {
      taskId: 'task:ledger',
      text: 'Reconcile the ledger entries for the month.',
      family: 'finance',
      intent: 'reconcile',
      action: 'synchronize',
    }
    await provider.embedAsync([task.text, ...skills.map(skillText)])
    const requestsBefore = server.requests.length
    const router = new TwoStageRouter({
      inventory: { skills, failureFamilies: [] },
      embedding: provider,
    })

    const retrieval = await router.retrieve(task)

    expect(server.requests).toHaveLength(requestsBefore)
    expect(retrieval.embeddingDegraded).toBe(false)
    expect(retrieval.skills[0]?.skillId).toBe(skills[0]?.skillId)
    expect(retrieval.skills[0]?.scores.embedding).toBeCloseTo(1, 10)
    expect(retrieval.skills[0]?.scores.lexical).toBe(0)
  })
})

describe('QwenEmbeddingProvider synchronous seam', () => {
  it('serves the synchronous EmbeddingProvider seam from cache without blocking', async () => {
    const server = await startServer(request => ({
      body: embeddingsResponse(vectorsFor(readInput(request.body))),
    }))
    const provider = createProvider(server)

    const first = await provider.embedAsync(TEXTS)
    const sync = provider.embedWithReport(TEXTS)

    expect(server.requests).toHaveLength(1)
    expect(sync.vectors).toEqual(first)
    expect(sync.report).toMatchObject({
      source: 'qwen',
      cacheHits: 5,
      cacheMisses: 0,
      batches: 0,
      degraded: false,
    })
  })

  it('does not block and degrades when synchronous transport is disabled', () => {
    const provider = new QwenEmbeddingProvider({
      baseUrl: 'http://127.0.0.1:1',
      syncTransport: 'disabled',
    })

    const result = provider.embedWithReport(['alpha'])

    expect(result.report).toMatchObject({
      source: 'fallback',
      degraded: true,
      degradationReason: 'sync-transport-disabled',
    })
    expect(result.vectors).toEqual(new DeterministicEmbeddingProvider().embed(['alpha']))
    expect(provider.capabilities().syncHttp).toBe(false)
  })

  it('does not apply the Qwen expected width to deterministic fallback vectors', () => {
    const provider = new QwenEmbeddingProvider({
      baseUrl: 'http://127.0.0.1:1',
      expectedDimensions: 3,
      syncTransport: 'disabled',
    })

    const result = provider.embedWithReport(['alpha'])

    expect(result.report).toMatchObject({ source: 'fallback', degraded: true, dimensions: 64 })
    expect(result.vectors).toEqual(new DeterministicEmbeddingProvider().embed(['alpha']))
  })

  it('falls back synchronously when the HTTP transport cannot connect', () => {
    const provider = new QwenEmbeddingProvider({
      baseUrl: 'http://127.0.0.1:1',
      model: 'sync-model',
      revision: 'sync-rev',
      timeoutMs: 250,
    })
    try {
      const result = provider.embedWithReport(['alpha'])

      expect(result.report).toMatchObject({
        source: 'fallback',
        degraded: true,
        degradationReason: 'http-unavailable',
        requestedModel: 'sync-model',
        requestedRevision: 'sync-rev',
      })
      expect(result.vectors).toEqual(new DeterministicEmbeddingProvider().embed(['alpha']))
      expect(provider.stats()).toMatchObject({ degradedCalls: 1, failures: 1 })
    } finally {
      provider.close()
    }
  })

  it('performs a blocking HTTP embedding through the worker bridge', async () => {
    const child = spawn(process.execPath, ['-e', SYNC_HTTP_SERVER_SOURCE], {
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    children.push(child)
    const baseUrl = await childServerUrl(child)
    const provider = new QwenEmbeddingProvider({
      baseUrl,
      model: 'sync-model',
      revision: 'sync-rev',
      timeoutMs: 2_000,
    })
    try {
      const vectors = provider.embed(['alpha', 'beta'])

      expect(vectors).toHaveLength(2)
      for (const vector of vectors) expect(norm(vector)).toBeCloseTo(1, 10)
      expect(provider.lastReport()).toMatchObject({
        source: 'qwen',
        model: 'sync-model',
        revision: 'sync-rev',
        degraded: false,
        cacheMisses: 2,
        batches: 1,
      })
    } finally {
      provider.close()
    }
  }, 15_000)
})
