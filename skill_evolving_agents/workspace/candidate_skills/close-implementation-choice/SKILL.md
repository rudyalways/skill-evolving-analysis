---
name: close-implementation-choice
description: When a follow-up offers concrete implementation options, end the turn with a visible choice or a short impossibility note. Use when the user asks which named option to take, such as a local script versus an entrypoint.
---

# Close implementation choice

## Overview

Own the closing shape of an answer that offers concrete implementation options. The turn ends on one chosen path, with the reason it meets the stated constraint, or on a one- or two-sentence note that the requested path is impossible and what remains possible. This skill does not design the implementation.

## When to Use

Use this skill when the user asks which concrete option to take and the turn must close with that decision. A request that names the options, such as a local script versus an entrypoint for a non-periodic news update, is enough on its own. A later restatement of the same choice is also enough on its own. Either case triggers the skill.

## Do Not Use

Do not use this skill for open-ended exploration that has not yet named options. Do not use it when an infrastructure failure already explains an empty turn. Listing approaches without a request to pick one is outside this skill.

## Workflow

1. Name the concrete options the follow-up offered.
2. If one option meets the stated constraint, pick it and state the reason in the assistant text.
3. If none is possible, state in one or two sentences why, and name what remains possible, such as an entrypoint when a local script cannot run.
4. Stop. Do not continue into implementation design, and do not send another message that drops the decision.

## Constraints

The choice or the impossibility note must be visible in the assistant text before the turn is closed. Do not end on an empty message after options were requested. Do not leave the user with a list of options and no selection.

## Verification

Confirm the final assistant text either selects one named option or contains a short impossibility note that states what remains possible. An empty body fails. A list of options with no choice fails.

## Output Format

End with a short decision block:

- Chosen option, and why it meets the stated constraint.
- Or: impossible, plus the remaining alternative, such as an entrypoint.

## Limitations

This skill does not design the implementation. It only requires the turn to close on a choice or an impossibility note. Promotion needs two held-out passes at rate 0.8.
