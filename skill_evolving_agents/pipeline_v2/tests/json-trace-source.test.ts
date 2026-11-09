import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { JsonFileTraceSource, InvalidTraceFileError, readJsonTraceFile } from '../src/adapters/json-trace-source.ts'
import { traceId } from '../src/contracts/ids.ts'

describe('json trace source', () => {
  it('reads a validated trace file', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'trace-json-'))
    const path = join(dir, 'trace.json')
    await writeFile(path, JSON.stringify({ id: 'trace-1', source: 'fixture', turns: ['failed', 'retry'] }))
    const trace = await readJsonTraceFile(path)
    expect(trace.id).toBe(traceId('trace-1'))
    const source = await JsonFileTraceSource.open(path)
    expect(await source.list()).toEqual([trace.id])
    expect((await source.read(trace.id)).turns).toEqual(['failed', 'retry'])
    await expect(source.read(traceId('other'))).rejects.toBeInstanceOf(InvalidTraceFileError)
    await rm(dir, { recursive: true, force: true })
  })

  it('rejects malformed traces', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'trace-json-bad-'))
    const path = join(dir, 'trace.json')
    await writeFile(path, JSON.stringify({ id: 'trace-1', source: 'fixture', turns: [1] }))
    await expect(readJsonTraceFile(path)).rejects.toBeInstanceOf(InvalidTraceFileError)
    await rm(dir, { recursive: true, force: true })
  })
})
