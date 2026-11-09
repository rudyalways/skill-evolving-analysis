import { EVENT_VERSION, type EventOf, type EventPayloadMap, type PipelineEventType } from '../contracts/events.ts'
import type { RunId } from '../contracts/ids.ts'
import { eventId } from '../contracts/ids.ts'
import { EventLog } from './event-log.ts'
import { projectEvents, type RunProjection } from './projections.ts'

/** A small deterministic facade over the append-only log. */
export class RunController {
  private sequence = 0

  constructor(
    readonly runId: RunId,
    readonly log: EventLog = new EventLog(),
  ) {}

  private nextEventId() {
    this.sequence += 1
    return eventId(`${this.runId}:evt:${this.sequence}`)
  }

  /** Append one typed event with a deterministic id. */
  append<T extends PipelineEventType>(
    type: T,
    payload: EventPayloadMap[T],
    at: string,
  ): EventOf<T> {
    const event = {
      id: this.nextEventId(),
      runId: this.runId,
      type,
      version: EVENT_VERSION,
      at,
      payload,
    } as EventOf<T>
    this.log.append(event)
    return event
  }

  /** Start the run at a caller-supplied timestamp. */
  start(objective: string, profile: string, at: string): EventOf<'run/started'> {
    return this.append('run/started', { objective, profile }, at)
  }

  /** Project the current event sequence. */
  snapshot(): RunProjection {
    return projectEvents(this.log.events)
  }
}
