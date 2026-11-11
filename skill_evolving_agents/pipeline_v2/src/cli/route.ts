#!/usr/bin/env node
/** Inspect router retrieval for a task against a skill inventory, without running it. */
import { writeFile, mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { TwoStageRouter, DEFAULT_ROUTER_CONFIG } from '../router/two-stage-router.ts'
import { inventoryFromSkills } from './inventory.ts'

interface RouteOptions {
  readonly skillsDir: string
  readonly task: string
  readonly family?: string
  readonly out?: string
}

function parse(argv: readonly string[]): RouteOptions {
  const get = (flag: string): string | undefined => {
    const index = argv.indexOf(flag)
    return index >= 0 ? argv[index + 1] : undefined
  }
  const skillsDir = get('--skills-dir')
  const task = get('--task')
  if (!skillsDir || !task) throw new Error('usage: route --skills-dir <dir> --task <text> [--family <id>] [--out <file>]')
  const family = get('--family')
  const out = get('--out')
  return {
    skillsDir,
    task,
    ...(family === undefined ? {} : { family }),
    ...(out === undefined ? {} : { out }),
  }
}

async function main(): Promise<void> {
  const options = parse(process.argv.slice(2))
  const inventory = await inventoryFromSkills(options.skillsDir)
  const router = new TwoStageRouter({
    inventory,
    config: {
      thresholds: {
        ...DEFAULT_ROUTER_CONFIG.thresholds,
        minimumCombined: 0.1,
        minimumEvidence: 0.01,
        minimumIntentAction: 0.1,
        minimumFamily: 0.5,
      },
    },
  })
  const retrieval = await router.retrieve({
    taskId: 'route-inspection',
    text: options.task,
    ...(options.family === undefined ? {} : { family: options.family }),
    intent: 'evolve-skill',
    action: 'update',
  })
  const payload = {
    skills: retrieval.skills.map((row) => ({ skillId: String(row.skillId), scores: row.scores })),
    failureFamilies: retrieval.failureFamilies.map((row) => ({ familyId: row.familyId, scores: row.scores })),
    embeddingDegraded: retrieval.embeddingDegraded,
    queryTokenCount: retrieval.queryTokenCount,
  }
  const text = `${JSON.stringify(payload, null, 2)}\n`
  if (options.out) {
    const out = resolve(options.out)
    await mkdir(dirname(out), { recursive: true })
    await writeFile(out, text)
  } else {
    process.stdout.write(text)
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error: unknown) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`)
    process.exitCode = 1
  })
}
