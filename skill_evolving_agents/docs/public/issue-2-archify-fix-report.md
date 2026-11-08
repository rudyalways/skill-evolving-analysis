# Issue #2 fix report: Archify-inspired Goal validation

Date: 2026-11-06 (Asia/Hong_Kong)

## Scope

This change addresses the three failures reported in public issue #2:

1. Goal can emit invalid JSON.
2. The model can choose a worker-data cwd where the relative validator path is
   absent, so self-validation never starts.
3. A contract-failed run can be summarized as a legitimate `no_change` run,
   while the invalid candidate disappears with the worker.

The strict Goal schema is unchanged. The fix does not force skill creation and
does not retry semantic decisions indefinitely.

## Archify mechanisms reviewed

The relevant Archify sources were:

- `archify/SKILL.md`
- `archify/references/delivery-contract.md`
- `archify/bin/finalize.mjs`
- `archify/bin/recover-output.mjs`
- `archify/scripts/update-contract.mjs`

The useful general mechanisms were:

- validate outside the authoring model;
- bind validation evidence to exact candidate bytes using SHA-256 and byte
  count;
- emit a compact machine-readable receipt for every gate;
- fail closed on non-zero or invalid output;
- permit only a bounded, evidence-directed repair;
- keep failed provenance before temporary state is removed;
- separate artifact/change disposition from execution status;
- make completed recovery idempotent and avoid treating an environmental
  failure as successful validation.

## What was borrowed

### Host-owned validation

The Goal model no longer receives or runs a relative validator command. It
writes the candidate and stops. The host then validates:

- the full Goal contract; and
- the one-action invariant that prevents one skill from appearing in multiple
  operations.

This removes model-selected cwd from the trust boundary. There is no validator
path for the model to resolve incorrectly.

### Candidate-bound validation receipts

Every Goal validation attempt writes:

```text
run/validation/goal/<scope>/attempt-<n>.json
```

The receipt records:

- validator identity;
- status;
- attempt number;
- timestamp;
- candidate path, presence, SHA-256, and byte count;
- a compact contract diagnostic on failure.

The receipt therefore proves which candidate bytes were checked, following the
same candidate/provenance separation used by Archify's finalizer.

The receipt is governed by a strict JSON Schema at
`common/schemas/goal-validation-receipt.schema.json`. The host validates the
schema at process startup and validates every receipt before writing it. The
schema rejects unknown fields, malformed candidate digests, missing failure
diagnostics, and inconsistent passed/failed payloads. This makes the receipt a
versioned interface rather than an informal JSON convention.

### One bounded repair

`phases.goal.contract_repair_attempts` is configurable with the domain `[0, 1, 2]`
and defaults to `1` in all bundled profiles.

On the first contract failure, the host may start exactly one focused Goal
repair session. That session receives:

- the exact Goal file to rewrite;
- the compact host diagnostic;
- the rejected candidate SHA-256 and byte count; and
- an instruction not to run, locate, or inspect a validator.

The host validates the rewritten bytes again. A second invalid candidate fails
closed. The repair remains subject to the global agent-call cap.

This is a format-contract repair, not an unrestricted semantic retry.

### Preserved failure evidence

Before the worker can be deleted, each invalid candidate writes a bounded
failure record at:

```text
run/failures/goal/<scope>/attempt-<n>.json
```

It contains the validation receipt and, when the candidate is at most 64 KiB,
a deterministic DLP-redacted candidate snapshot plus its redaction count.
Larger candidates retain only identity and an omission reason. It does not
retain hidden reasoning or raw traces.

### Honest run disposition

Phase metrics now expose execution and change state separately:

```json
{
  "execution": {
    "status": "failed",
    "failed_phases": ["goal"],
    "change_disposition": "no_change"
  },
  "funnel": {
    "execution_status": "failed",
    "run_disposition": "failed"
  }
}
```

A legitimate completed no-change run still reports `no_change`. A converged
idempotent replay still reports `converged`. A failed Goal run now reports
`failed`, even if no operation artifact exists.

## What was deliberately not borrowed

Archify's directory mutex, symlink/hard-link defenses, paired artifact commit,
browser evidence, and publication recovery protocol solve concurrent delivery
of durable HTML artifacts. They would add substantial complexity without
addressing this Goal-contract failure. The skill pipeline already isolates Goal
workers and has its own atomic JSON/status writes.

The implementation therefore borrows the smaller contract pattern—not the
entire Archify delivery subsystem.

## Verification

Focused regression coverage verifies:

- malformed Goal JSON triggers host validation failure;
- the repair prompt contains the contract error and no validator path;
- one repair can produce a valid Goal;
- the original candidate and error are preserved;
- an ineffective repair is attempted only once and then fails closed;
- failed Goal status produces `run_disposition=failed`;
- the formal receipt schema accepts valid receipts and rejects missing errors,
  malformed digests, and unknown fields;
- ordinary concurrent Goal fan-out still publishes valid outputs.

Results:

```text
Focused issue #2 tests: 5/5 passed
Repository unit tests: 267/267 passed
Deterministic funnel benchmark: 23/23 passed
  calibration: 12/12
  held-out: 11/11
```

## Live DSH trace validation

Three independent traces were run through the real low-cost pipeline with the
signed-in DSH DeepSeek Flash backend after the deterministic tests:

- A 23-turn Codex trace reached Goal, produced one invalid create candidate,
  wrote a failed receipt, completed one bounded repair, wrote a passed receipt
  for different candidate bytes, and completed the pipeline. The proposed
  create was later rejected by the publication policy gate, independently of
  Goal contract validity.
- A 36-turn Codex trace completed normally with no evolution units remaining
  after deterministic selection and infrastructure filtering. It correctly
  produced no Goal receipt because Goal was never entered.
- An OfficeVal Claude trace reached Goal, produced one invalid update
  candidate, completed one bounded repair, passed the second validation, and
  completed with an accepted update to `openpyxl-chart-rendering`.

The live runs exposed two prompt-contract ambiguities: create records did not
state the required `skill` identity prominently enough, and label and removal
record shapes were underspecified. The Goal instructions now explicitly
require `skill`, `{type, weight}` label records, and string-valued `remove`
entries. Repair instructions also require one complete contract audit after
fixing the reported defect, so the single repair budget is not consumed by a
second defect that was visible from the same candidate.

## Remaining validation

The deterministic reproduction is fixed. A real hosted-model replay of the
OfficeVal trace is still needed to measure whether the bounded repair succeeds
for the originally observed malformed output and to measure its frequency and
incremental cost. Such a replay should use the intended backend, retain the new
receipts, and must not claim behavioral skill improvement without a separate
task evaluation.
