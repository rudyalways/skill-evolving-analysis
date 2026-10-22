---
name: standing-approval
description: After a named action is already approved, carry that approval through the remaining prepared steps and stop only for an irreversible choice that was explicitly reserved. Use when later steps, including an already-finished check, are still inside that approval.
---

## Overview

One approval of a named action covers the remaining prepared steps of that action. Continue those steps until a newly reserved irreversible choice is reached. The original approval, or a later restatement of the same approval, is each enough to keep going. Do not ask for the same go-ahead again.

## When to Use

Use this skill when either of these is already true:

- The user has approved a named action, and later prepared steps of that same action are still ahead.
- The user restates that same approval, and the remaining prepared steps, including a check that was already completed, are still inside it.

Either case is sufficient. A first approval that has not been restated is still in scope once that approval exists. A restatement of the same named action is also in scope on its own.

## Do Not Use

Do not use this skill in any of these situations:

- The named action has not been approved yet. This skill does not obtain the first approval.
- The next step belongs to a different action than the one that was approved.
- The user explicitly reserved a stop that has now been reached, such as entering a secret or approving a paid upgrade.

## Workflow

1. Record the approved action in the user's words, plus every stop the user explicitly reserved. A reserved stop is an irreversible choice the user named in advance, such as entering a secret or approving a paid upgrade.
2. List the remaining prepared steps of that action. Drop any check that is already satisfied and treat it as done.
3. Continue those remaining steps without asking for the same go-ahead again.
4. Before each step, compare it with the recorded action and the reserved stops. Proceed when the step is still inside the approved action and is not a reserved stop.
5. Stop only when a new irreversible choice was explicitly reserved and that choice is now reached. Ask for that reserved choice and wait.
6. If a new irreversible choice appears but was not reserved, do not treat it as a stop and do not widen the approval. Leave it unstarted and say that it was not part of the standing approval.
7. Finish by stating which steps ran under the standing approval and which reserved stop, if any, is still open.

## Constraints

- Do not re-ask for the same go-ahead after the named action is approved.
- Do not invent extra reserved stops. Only stops the user explicitly reserved count.
- Do not widen the approval to a new irreversible choice that was not part of the prepared steps.
- Keep the method free of product-specific paths, commands, prices, and constants. Name the action and the reserved stop in the user's terms.

## Verification

Before the next user turn, check both of these:

- The next step is still one of the prepared steps of the approved action.
- The next step is not an explicitly reserved stop.

A repeated confirmation prompt for the same approved action is a failure. Stopping for an irreversible choice that was never reserved is also a failure. Skipping a reserved secret or paid upgrade is a failure.

## Output Format

Report three items:

- **Standing approval:** the named action that was approved, and the reserved stops recorded with it.
- **Continued:** the prepared steps that ran under that approval, including any already-satisfied check treated as done.
- **Open reserved stop:** the reserved irreversible choice that is still open, or none.

Ask only when a new reserved irreversible choice is reached. The question names that reserved choice and does not repeat the original go-ahead.

## Limitations

This skill does not decide whether the original action should be approved. It does not cover unstated side effects that were never in the prepared steps. It does not convert an unreserved irreversible choice into an approved step.
