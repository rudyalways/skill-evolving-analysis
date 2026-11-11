import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { inventoryFromSkills } from '../src/cli/inventory.ts'

const roots: string[] = []
afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

describe('inventory builder', () => {
  it('reads immediate skill bundles and deduplicates families', async () => {
    const root = await mkdtemp(join(tmpdir(), 'inventory-'))
    roots.push(root)
    for (const [name, body] of [
      ['alpha', '---\nname: Alpha\ndescription: Alpha workflow\nfamily: shared\nkeywords: alpha, data\n---\n\n# Alpha\n'],
      ['beta', '---\nname: Beta\ndescription: Beta workflow\nfamily: shared\nkeywords: beta, data\n---\n\n# Beta\n'],
    ] as const) {
      await mkdir(join(root, name))
      await writeFile(join(root, name, 'SKILL.md'), body)
    }
    await mkdir(join(root, 'openpyxl-chart'))
    await writeFile(join(root, 'openpyxl-chart', 'SKILL.md'), '---\nname: openpyxl-chart\ndescription: Style Excel workbook charts\n---\n\n# Chart\n')
    await mkdir(join(root, 'ignored'))
    const inventory = await inventoryFromSkills(root)
    expect(inventory.skills.map((row) => row.name)).toEqual(['Alpha', 'Beta', 'openpyxl-chart'])
    expect(inventory.failureFamilies.map((row) => row.familyId)).toContain('shared')
    expect(inventory.skills.find((row) => row.name === 'openpyxl-chart')?.family)
      .toBe('spreadsheet-formula-validation')
  })
})
