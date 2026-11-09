import type { FindingId, OperationId, SkillId } from './ids.ts'

/** Supported operation families. */
export type OperationKind = 'create' | 'update' | 'merge' | 'split' | 'delete' | 'no_change'

/** A planned skill mutation. */
export interface Operation {
  readonly id: OperationId
  readonly kind: OperationKind
  readonly skillId: SkillId
  readonly findingId: FindingId
  readonly summary: string
}

/** A receipt for an immutable publication. */
export interface PublicationReceipt {
  readonly operationId: OperationId
  readonly releaseId: string
  readonly channel: 'provisional' | 'canary' | 'accepted'
}
