import type { OperationId, ResourceId, SkillId } from './ids.ts'

/** Resource directories a skill may own. */
export type ResourceKind = 'scripts' | 'references' | 'assets' | 'agents' | 'evals'

/** A generated or consumed skill resource. */
export interface Resource {
  readonly id: ResourceId
  readonly operationId: OperationId
  readonly skillId: SkillId
  readonly kind: ResourceKind
  readonly path: string
  readonly status: 'generated' | 'used' | 'rejected'
}
