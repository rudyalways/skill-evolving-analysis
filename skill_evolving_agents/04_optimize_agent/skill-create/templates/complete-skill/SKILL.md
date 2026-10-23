---
name: complete-skill
description: Demonstrate the complete supported skill package when an optimizer needs a concrete reference for placing instructions, deterministic helpers, detailed knowledge, reusable output material, interface metadata, and behavioral evaluations.
---

# Complete skill reference

## Overview

Normalize JSON Lines records into a stable report shape. This skill is a
read-only structural reference for Optimize; generated skills must include only
the resources authorized by their own goal.

## When to Use

Use this example when a skill author needs to see how `SKILL.md`, references,
scripts, assets, agents, and evals form one coherent package.

## Do Not Use

Do not install this reference as a user-facing capability. Do not copy every
directory into another skill, and do not use the normalizer on non-JSONL input.

## Workflow

1. Read `references/record-schema.md` before accepting or changing record fields.
2. Run `scripts/normalize_jsonl.py` with an input JSONL path and output path;
   `scripts/fixtures/sample.jsonl` is the representative safe fixture.
3. Compare the result with `assets/report-template.json` for the stable shape.
4. Use `evals/evals.json` to test both intended activation and a near miss.
5. Treat malformed input as a failed run; do not silently omit records.

## Constraints

Preserve input order. Require a non-empty string `id` and `text` in every
record. Emit only `id`, normalized `text`, and `tags`; sort and deduplicate tags.

## Verification

Execute the normalizer on a representative fixture, parse every output line,
and confirm ordering, whitespace normalization, and tag deduplication. A
nonzero exit for malformed records is required behavior.

## Output Format

Write UTF-8 JSON Lines. Each line follows the object shape documented in
`references/record-schema.md` and illustrated by `assets/report-template.json`.

## Limitations

The helper performs deterministic structural normalization only. It does not
infer missing fields, classify meaning, translate text, or process JSON arrays.
