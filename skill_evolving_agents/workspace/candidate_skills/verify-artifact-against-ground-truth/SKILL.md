---
name: verify-artifact-against-ground-truth
description: Verify an enumerated artifact such as a CSV, JSON, table, report, or extracted record list by diffing it key-by-key against an independently derived expected set, then repair the producing cause of any missing, extra, or changed record before declaring completion.
---

## Overview

Own record-level verification of a produced artifact against an independently derived expected set. Distinguish structural validity from content equivalence: parsing success, schema conformance, and matching counts prove only that the artifact is well formed, not that its records are correct. Treat any unexplained difference from the expected set as a defect to trace and repair, not as a reporting detail to mention in passing.

## When to Use

Use this skill when any one of these conditions holds:

- The deliverable is an enumerated artifact (CSV, JSON, table, report, or extracted record list) with a known or derivable expected set.
- An objective verifier compares produced records with expected records.
- Structural, schema, or count checks pass but the verifier still reports a content mismatch.
- The task restates the need to check produced records against ground truth before completion.

A request that already passed a structural suite is still in scope; it is a near-miss for this skill, not a reason to skip it.

## Do Not Use

Do not use this skill for prose, design, or other deliverables that have no enumerated expected records. Do not use it as a substitute for the task-specific domain judgment needed to build the expected set. Do not use it to guess verifier values, to hand-edit records toward an assumed expectation, or to bypass an unavailable verifier.

## Workflow

1. Identify the authoritative expected set and the stable record key or keys before producing the artifact. If no expected set is supplied, derive it independently from the source data, not from the produced artifact.
2. Build keyed maps of the expected and actual records. Normalize only differences the contract explicitly permits, such as whitespace or date format, and record the normalization rule.
3. Diff the maps for missing keys, extra keys, and field-level value changes. Select the first concrete mismatch rather than summarizing the whole diff.
4. Trace that mismatch to the producing step or rule and repair the cause, not just the affected artifact row. Add or correct the transformation that generated the wrong value or omitted the record.
5. If the source changed, recompute the expected set; then rebuild the artifact and replay the full diff.
6. Repeat only while a named mismatch remains. Finish with matched, missing, extra, and changed counts.

## Constraints

Never claim completion from parsing success, structural tests, schema checks, or record counts alone, because a clean parse is not content equivalence. When a verifier returns a failing assertion with a diff, treat that diff as the primary signal and let it drive the next repair. Do not rerun an unchanged verification, do not hand-edit records to match a guessed expectation, and do not embed task-specific constants in the method.

## Verification

Completion requires a record-level diff against the independent expected set with zero unexplained missing, extra, or changed fields, or an explicit justification for every accepted residual difference. Record the key set, the diff counts, and the derivation or command used. A passing structural suite alone cannot close verification.

## Output Format

Report the expected-versus-actual comparison as a compact ledger: matched count, missing keys, extra keys, changed fields per key, the repaired cause, and the replay result. Keep the artifact in the requested schema, and do not add verification metadata to required columns unless the contract permits it.

## Limitations

Requires a trustworthy expected set or a deterministic derivation from source data; without either, the method can expose unverifiable assumptions but cannot prove correctness. Record-level diffing cannot detect errors shared by both the expected set and the artifact, and normalization differences must be resolved before comparison.
