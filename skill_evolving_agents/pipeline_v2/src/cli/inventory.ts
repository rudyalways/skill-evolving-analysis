#!/usr/bin/env node
/** Build a router inventory from a directory of skill bundles. */
import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { skillId } from '../contracts/ids.ts'
import type { FailureFamilyDocument, RouterInventory, SkillDocument } from '../router/two-stage-router.ts'

interface Frontmatter {
  readonly name?: string
  readonly description?: string
  readonly family?: string
  readonly keywords?: string
}

function parseFrontmatter(text: string): Frontmatter {
  const match = /^---\n([\s\S]*?)\n---\n/.exec(text)
  if (match === null) return {}
  const fields: Record<string, string> = {}
  for (const line of (match[1] ?? '').split('\n')) {
    const separator = line.indexOf(':')
    if (separator <= 0) continue
    const key = line.slice(0, separator).trim()
    const value = line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, '')
    if (key) fields[key] = value
  }
  return fields
}

/** Read immediate skill directories and produce a deterministic inventory. */
export async function inventoryFromSkills(root: string): Promise<RouterInventory> {
  const base = resolve(root)
  const entries = await readdir(base, { withFileTypes: true })
  const skills: SkillDocument[] = []
  const families = new Map<string, FailureFamilyDocument>()
  for (const entry of entries.filter((row) => row.isDirectory()).sort((a, b) => a.name.localeCompare(b.name))) {
    let text: string
    try {
      text = await readFile(join(base, entry.name, 'SKILL.md'), 'utf8')
    } catch {
      continue
    }
    const meta = parseFrontmatter(text)
    const name = meta.name || entry.name
    const description = meta.description || name
    const family = meta.family || name.toLowerCase().replace(/[^a-z0-9]+/g, '-')
    const keywords = (meta.keywords || name).split(/[,\s]+/).filter(Boolean)
    skills.push({
      skillId: skillId(`inventory-${entry.name}`),
      name,
      description,
      family,
      keywords,
      selectable: true,
    })
    if (!families.has(family)) {
      families.set(family, {
        familyId: family,
        family,
        description,
        keywords,
        selectable: true,
      })
    }
  }
  return { skills, failureFamilies: [...families.values()] }
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  const dirIndex = args.indexOf('--skills-dir')
  const outIndex = args.indexOf('--out')
  if (dirIndex < 0 || !args[dirIndex + 1] || outIndex < 0 || !args[outIndex + 1]) {
    throw new Error('usage: inventory --skills-dir <dir> --out <file>')
  }
  const inventory = await inventoryFromSkills(args[dirIndex + 1]!)
  const out = resolve(args[outIndex + 1]!)
  await mkdir(dirname(out), { recursive: true })
  await writeFile(out, `${JSON.stringify(inventory, null, 2)}\n`)
  process.stdout.write(`${JSON.stringify({ skills: inventory.skills.length, families: inventory.failureFamilies.length })}\n`)
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error: unknown) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`)
    process.exitCode = 1
  })
}
