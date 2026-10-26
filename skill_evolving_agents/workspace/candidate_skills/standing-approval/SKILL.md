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

1. Record the approved action in the user's words, plus every stop the user explicitly reserved. A reserved stop is an irreversible choice the user named in advance, such as entering a secret or approving a paid upgrade. When the user authorizes non-critical work and asks for confirmation only at critical boundaries, treat that mandate as already granted. A first grant is enough. Do not wait for the user to restate the same mandate.
2. Before acting, enumerate every concrete item in the requested scope into a scope ledger. Split a multi-part request into named, checkable items such as tasks, sub-parts, slices, deliverables, and checks. Include all prepared steps of the approved action, and mark any check that is already satisfied as done. This ledger, not the latest summary, decides what remains.
3. In the same turn, do the next reversible item on the ledger. Continue the remaining non-critical items without asking for the same go-ahead again.
4. After each item, re-read the scope ledger and choose the next unimplemented item. Do not end the turn while an item remains unstarted, reversible, and inside the recorded approval. A list of remaining items in a closing summary is a handoff, not an end state.
5. Before each item, compare it with the recorded action and the reserved stops. Proceed when the item is still inside the approved action, is reversible, and is not a reserved stop.
6. Stop only at the next critical boundary. A critical boundary is a credential, a password the user must remember, or another irreversible confirmation, including a reserved stop that has now been reached. Name that one blocker, ask for it, and wait. Do not stop earlier to restate the standing mandate.
7. If a new irreversible choice appears but was not reserved and is not one of those critical boundaries, do not treat it as a stop and do not widen the approval. Leave it unstarted and say that it was not part of the standing approval.
8. Finish only when every ledger item is implemented, deferred with explicit user agreement, or proven blocked by an external constraint with evidence. Then state which items ran under the standing approval, which items are deferred or blocked with that basis, and which reserved stop or critical blocker, if any, is still open.

## Constraints

- Do not re-ask for the same go-ahead after the named action is approved.
- Do not answer a standing non-critical mandate with only a restatement of the rule or a repeated wait at the same critical wall. Stop once at that wall after the reversible work already in scope is done or explicitly named.
- A closing summary that still lists unstarted sliced work is not a completion state. Continue that work in the same turn instead of handing it back.
- Stop only when every ledger item is implemented, deferred with explicit user agreement, or proven blocked by an external constraint with evidence. An unlabeled remaining item is none of those and requires continuation.
- Do not invent extra reserved stops. Only stops the user explicitly reserved count, plus a credential, a password the user must remember, or another irreversible confirmation that is the next action.
- Do not widen the approval to a new irreversible choice that was not part of the prepared steps.
- Keep the method free of product-specific paths, commands, prices, and constants. Name the action and the reserved stop in the user's terms.

## Verification

Before the next user turn, check both of these:

- The next step is still one of the prepared steps of the approved action.
- The next step is not an explicitly reserved stop.

Before any completion claim, run a final scope check. Walk the scope ledger item by item and label every item implemented, user-deferred with explicit agreement, or blocked by an external constraint with evidence. No item may be left unlabeled.

A repeated confirmation prompt for the same approved action is a failure. Stopping for an irreversible choice that was never reserved is also a failure. Skipping a reserved secret or paid upgrade is a failure. Claiming completion while the scope ledger still contains an unstarted, unlabeled item is a failure, even if the closing summary lists it.

## Output Format

Report three items:

- **Standing approval:** the named action that was approved, and the reserved stops recorded with it.
- **Continued:** the prepared steps that ran under that approval, including any already-satisfied check treated as done.
- **Open reserved stop:** the reserved irreversible choice that is still open, or none.

Ask only when a new reserved irreversible choice is reached. The question names that reserved choice and does not repeat the original go-ahead.

## Limitations

This skill does not decide whether the original action should be approved. It does not cover unstated side effects that were never in the prepared steps. It does not convert an unreserved irreversible choice into an approved step.
