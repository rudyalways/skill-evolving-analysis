---
name: derived-aggregate-audit
description: Repair failing derived aggregate cells such as averages, shares, growth rates, and totals by restating the metric definition, pinning the source range and contributing population, recomputing independently, and replaying the full objective verifier until it passes.
---

# Derived aggregate audit

## Overview

Treat every derived aggregate as a definition plus a population, not as arithmetic over whatever cells happen to be nearby. A passing row-sum or cross-sheet consistency check only proves the workbook is internally consistent; it does not prove an average, share, growth rate, or total used the intended records or denominator. This skill localizes the failing derived cell, repairs its source range and population, and drives the objective verifier to a full pass.

## When to Use

Use this skill when any of these conditions holds:

- A workbook contains computed cells (averages, shares, growth rates, totals) whose input range or population is implicit.
- A row-sum or cross-sheet consistency check passes, but a scalar aggregate assertion still fails.
- A verifier reports a failing derived cell after most other checks pass.
- A reported aggregate looks plausible but disagrees with an independently recomputed value.

## Do Not Use

Do not use this skill for transcription-only tasks with no derived cells, for failures already localized to a formula syntax error, or as a substitute for the task's own definition of each metric. Do not use it to relax, reinterpret, or bypass the verifier contract.

## Workflow

1. Run the objective verifier once and record every failing assertion with its cell, expected value, and message. Do not fix cells that were not named.
2. Classify each failure. An assertion that names a cell and a value is a concrete contract defect and is in scope. A budget or timeout abort with no named assertion is a scope or performance problem, not a numeric one; report it as such instead of guessing at a cell.
3. For each named cell, restate the metric definition in words: the numerator, the denominator, the unit, and the filter that defines the population.
4. Identify the exact source range and the count of contributing records. Verify that the range covers the intended population and does not silently include header rows, blank rows, stale rows, or records outside the filter.
5. Confirm the denominator is the intended population, not all rows, a stale range, or a count that includes excluded records. A row-sum check cannot validate this choice.
6. Independently recompute the value outside the deliverable, from the source data, using the restated definition. Record the computed value and the record count before touching the workbook.
7. Compare the independent value with the expected value. If they differ, re-examine the definition and population rather than forcing agreement.
8. Write the recomputed value or corrected formula into the named cell, leaving unrelated cells unchanged.
9. Replay the complete objective verifier, not a focused subset. Repeat localization and recomputation for any remaining assertion until the run exits clean or a concrete external block is documented.
10. Treat row-sum and cross-sheet checks as consistency evidence only, never as proof that a derived aggregate used the right population.

## Constraints

- Preserve the task's stated metric definition; do not change it to match an observed expected value.
- Do not modify unrelated cells to force agreement.
- Recompute from source data; never copy the expected value into the cell as a substitute for computation.
- Keep every edit traceable to the named cell, its definition, and its source range.
- Do not claim completion from a partially passing suite or from consistency checks alone.
- Do not reinterpret or weaken the verifier contract to make an assertion pass.

## Verification

Completion requires the full objective verifier to exit with zero failures, including the specific assertion that failed before the edit. Report the independently recomputed value, its source range, and its contributing record count, followed by the exact verifier result. If an assertion still fails, report it explicitly with its cell, expected value, and observed value instead of reporting success.

## Output Format

Report, in this order:

1. The failing assertion, its cell, and its expected value.
2. The metric definition: numerator, denominator, unit, and population filter.
3. The pinned source range and contributing record count.
4. The independently recomputed value.
5. The value or formula written to the cell.
6. The final verifier summary counts (passed, failed, and exit status).

## Limitations

This method depends on the metric definition being recoverable from the task, neighboring sheets, or the verifier message. When the population is genuinely ambiguous, record the ambiguity and the chosen interpretation rather than silently guessing a denominator. It cannot repair missing source data or formula syntax errors, and it does not replace the task's authoritative definition of a metric.
