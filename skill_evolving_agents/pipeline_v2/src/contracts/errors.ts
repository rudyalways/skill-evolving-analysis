/** A structured failure that crosses a pipeline boundary. */
export interface StructuredIssue {
  readonly path: string
  readonly code: string
  readonly message: string
}

/** Base class for v2 failures; `code` is stable and `details` is JSON-safe. */
export class PipelineError extends Error {
  readonly code: string
  readonly details: Readonly<Record<string, unknown>>

  constructor(code: string, message: string, details: Readonly<Record<string, unknown>> = {}) {
    super(message)
    this.name = new.target.name
    this.code = code
    this.details = details
  }

  /** Stable JSON representation for worker and report boundaries. */
  toJSON(): { code: string; message: string; details: Readonly<Record<string, unknown>> } {
    return { code: this.code, message: this.message, details: this.details }
  }
}

/** An id constructor received a value that cannot be used as a branded id. */
export class InvalidIdError extends PipelineError {
  constructor(kind: string, value: unknown) {
    super('invalid-id', `invalid ${kind} id`, { kind, value: String(value) })
  }
}

/** An event failed structural validation before it could be appended. */
export class EventValidationError extends PipelineError {
  readonly issues: readonly StructuredIssue[]

  constructor(issues: readonly StructuredIssue[]) {
    super('invalid-event', 'event failed validation', { issues })
    this.issues = issues
  }
}

/** A durable event declared a schema version this build cannot interpret. */
export class UnsupportedEventVersionError extends PipelineError {
  constructor(eventType: unknown, version: unknown) {
    super('unsupported-event-version', `unsupported event version ${String(version)}`, {
      eventType: String(eventType),
      version: String(version),
    })
  }
}

/** An event would move the run or an operation into an illegal state. */
export class InvalidTransitionError extends PipelineError {
  constructor(eventType: string, from: string, reason: string) {
    super('invalid-transition', reason, { eventType, from })
  }
}

/** An event belongs to a different run than the log it is appended to. */
export class RunIdMismatchError extends PipelineError {
  constructor(expected: string, actual: string) {
    super('run-id-mismatch', 'event belongs to a different run', { expected, actual })
  }
}

/** Two resource events reused the same resource id within one run. */
export class DuplicateResourceError extends PipelineError {
  constructor(resourceId: string) {
    super('duplicate-resource', `duplicate resource id ${resourceId}`, { resourceId })
  }
}

/** Two events reused the same append-only event id. */
export class DuplicateEventError extends PipelineError {
  constructor(eventId: string) {
    super('duplicate-event', `duplicate event id ${eventId}`, { eventId })
  }
}

/** A capability already has a provider and replacement was not requested. */
export class DuplicateCapabilityError extends PipelineError {
  constructor(name: string) {
    super('duplicate-capability', `capability ${name} already has a provider`, { name })
  }
}

/** A consumer required a capability that is not mounted. */
export class CapabilityMissingError extends PipelineError {
  constructor(name: string) {
    super('capability-missing', `capability ${name} is not mounted`, { name })
  }
}

/** A legacy comparison report failed schema validation. */
export class InvalidComparisonReportError extends PipelineError {
  readonly issues: readonly StructuredIssue[]

  constructor(issues: readonly StructuredIssue[]) {
    super('invalid-comparison-report', 'comparison report failed validation', { issues })
    this.issues = issues
  }
}

/** A worker request or result violated the versioned JSON protocol. */
export class WorkerProtocolError extends PipelineError {
  readonly issues: readonly StructuredIssue[]

  constructor(issues: readonly StructuredIssue[]) {
    super('invalid-worker-protocol', 'worker protocol payload failed validation', { issues })
    this.issues = issues
  }
}
