import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { inventoryFromSkills } from '../src/cli/inventory.ts'
import { TwoStageRouter, DEFAULT_ROUTER_CONFIG } from '../src/router/two-stage-router.ts'

const roots: string[] = []
afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

describe('routing inspection', () => {
  it('ranks a lexically matching skill first', async () => {
    const root = await mkdtemp(join(tmpdir(), 'route-'))
    roots.push(root)
    for (const [name, description] of [
      ['alpha', 'Recover missing spreadsheet values with formulas'],
      ['beta', 'Build a dialogue graph from a script'],
    ] as const) {
      await mkdir(join(root, name))
      await writeFile(join(root, name, 'SKILL.md'), `---\nname: ${name}\ndescription: ${description}\n---\n\n# ${name}\n`)
    }
    const inventory = await inventoryFromSkills(root)
    const router = new TwoStageRouter({
      inventory,
      config: { thresholds: { ...DEFAULT_ROUTER_CONFIG.thresholds, minimumCombined: 0.1 } },
    })
    const result = await router.retrieve({ taskId: 't', text: 'recover missing spreadsheet values' })
    expect(String(result.skills[0]?.skillId)).toContain('alpha')
  })
})
