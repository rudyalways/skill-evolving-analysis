import type {
  PreflightCapability,
  ResourcePlannerCapability,
} from '../capabilities/definitions.ts'
import type { PreflightReport, PreflightRequest } from '../preflight/preflight.ts'
import { preflight } from '../preflight/preflight.ts'
import type { SkillPlan, SkillPlanningRequest } from '../resources/planner.ts'
import { planSkillResources } from '../resources/planner.ts'

/** Deterministic resource planner provider. */
export class DeterministicResourcePlanner implements ResourcePlannerCapability {
  plan(request: SkillPlanningRequest): SkillPlan {
    return planSkillResources(request)
  }
}

/** Deterministic executable preflight provider. */
export class DeterministicPreflight implements PreflightCapability {
  run(request: PreflightRequest): Promise<PreflightReport> {
    return preflight(request)
  }
}
