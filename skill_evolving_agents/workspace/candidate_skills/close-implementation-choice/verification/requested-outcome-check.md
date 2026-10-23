# Requested-outcome completion check

Use this check for a partial delivery before any completion claim.

1. Restate the user's requested end state in one sentence.
2. Restate the delivered state: what code, configuration, or artifact is actually present.
3. Compare them. A match is required before the work is complete.
4. Leave the task open when any of the following is true:
   - A required gate is unrun (browser check, role page, live render, or other named acceptance step).
   - The outcome is still a no-go.
   - Implementation is finished but console, owner, or provider setup remains.
5. When implementation is finished and only user-owned activation or setup remains, do not call the task complete. Record the two lists in the first status: completed work, and actions the user still has to perform.
