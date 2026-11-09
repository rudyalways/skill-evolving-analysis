---
name: ada-plan-view-accessibility
description: Use when checking simplified ADA-derived plan-view bathroom accessibility constraints such as turning space, door clear width, toilet centerline, grab bars, and lavatory knee/toe clearance.
---

Use this skill for plan-view accessibility checks. It is not a full legal ADA compliance review; apply only the geometric rules provided by the task.

## Workflow

1. Run the plan-view validation once and read the reported rule names, element ids, and verifier response from `Violation Reporting` below.
2. Classify the failure before any repair:
   - Concrete violation: the verifier names a rule, contract, schema field, or element id with a failing value, for example `door_clear_width_min` on `D1`. Treat that named defect as the only repair target and continue to step 3.
   - Execution-budget abort: the verifier reports a wall-clock timeout or tool-call cap, reward 0, and no named rule, contract, schema field, or element id. This is not evidence of a geometry defect. Do not edit geometry and do not replay the identical full run. Preserve the partial artifacts, checkpoint the last completed rule group, reduce scope to the next unchecked rule group or artifact, and re-run only after that scope change.
3. For a concrete violation, identify the specific failing rule and the geometry or input that drives it before taking another action.
4. Make a traceable edit: change the geometry, dimension, or input file for that named rule and record what changed. Do not repeat the identical validation command with unchanged arguments after a near-identical failing payload.
5. If no valid edit is available, inspect the specific failing geometry until the cause is known, or report the unsatisfied rule and stop.
6. Re-run only under the retry admission rule in `Constraints`, and read the full failing rule set rather than only the first error.

## Environment Preflight

- Treat the DXF file and the task's rules JSON as the authoritative inputs.
  Confirm both are readable before analysis.
- The screenshot is an orientation aid, not a measurement source. If it is
  missing, continue from the DXF; do not spend more than one call looking for
  it and do not treat its absence as a geometry defect.
- Use the task environment's DXF library (`ezdxf` when available). Do not make
  plotting or image-rendering libraries a prerequisite; if `matplotlib` or an
  image preview is unavailable, fall back to numeric entity inspection.
- Write the required JSON outputs and the repaired DXF incrementally as each
  section is established. Preserve partial artifacts when a later step fails so
  the run is resumable.
- A missing optional image, a missing plotting package, or a path typo is an
  environment issue. Do not spend repeated calls installing packages,
  re-rendering previews, or searching unrelated directories; record the
  limitation and continue with the authoritative DXF.

## Plan-View Checks

- Door clear opening: compare the submitted clear width against the minimum in the rules file, commonly 32 inches.
- Door swing: if the rule disallows swing into required fixture clearance, prefer an outward or sliding swing in the repaired layout. Do not leave an inward repaired swing unless you have explicitly modeled and cleared the swing path against fixtures and required clearances.
- Turning space: verify that a 60 inch diameter circle fits inside usable floor area. Diameter alone is not enough. Apply the wall/boundary offset from the rules, subtract protected or blocked fixtures such as tubs, and allow overlap with toilet clear floor space only when the rules say so.
- Lavatory overlap: allow the turning circle to overlap a lavatory only when plan-view knee/toe clearance is explicitly indicated and meets the required width and depth.
- Toilet centerline: measure from the adjacent side wall and keep it inside the rule range, commonly 16 to 18 inches.
- Grab bars: classify rear-wall and side-wall bars by orientation/location and compare their plan-view lengths against the minimums. The side-wall grab bar should align with the same adjacent side wall used for the toilet centerline and overlap the toilet use zone. The rear-wall grab bar should align with the rear wall behind the toilet and cross or closely span the toilet centerline.

## Violation Reporting

Report one violation per failed rule/element pair. Use stable machine-readable rule names from the rules file, for example:

- `door_clear_width_min`
- `turning_circle_diameter_min`
- `turning_circle_fit_usable_floor`
- `toilet_centerline_from_side_wall_range`
- `side_grab_bar_length_min`
- `rear_grab_bar_length_min`
- `side_grab_bar_toilet_side_wall_alignment`
- `rear_grab_bar_toilet_centerline_span`
- `lavatory_knee_clearance_min`

Do not report vertical requirements such as seat height, mounting height, mirror height, signage height, or pipe protection if the task scope excludes them.

Use combined rule names for range checks. For example, if the toilet centerline is outside the allowed range, report `toilet_centerline_from_side_wall_range`; do not invent separate `*_min` or `*_max` violation names unless the rules file explicitly asks for them.

Use the element id that matches the failed requirement's scope:

- For toilet centerline failures, use the toilet id, such as `WC1`.
- For room-level turning-circle fit failures, use the room id, such as `bathroom_1`, because the failure is about whether usable floor area can contain the full circle.
- For grab-bar length failures, report them only after classifying the actual side-wall and rear-wall grab bars. Do not report grab-bar failures when the classified bars meet the minimum lengths.
- For lavatory knee/toe clearance, report a violation only when the lavatory lacks the indicated plan-view knee/toe clearance or the stated width/depth is below the rule minimum. Do not infer a before-repair violation from unrelated fixture graphics when the extracted lavatory metadata satisfies the rule.

## Repair Principles

- Preserve existing walls and fixtures whenever a local move or small expansion solves the problem.
- Prefer changing door swing/opening representation over redesigning the whole room.
- Keep protected fixtures such as tubs in place unless the rules make that impossible.
- If the toilet moves, update or validate the grab-bar segments against the repaired toilet position.
- Make every repair traceable to a violation or to preserving a valid clearance.

## Constraints

- A budget abort is never evidence of a geometry defect. Require a named rule, contract, schema field, or element id violation before any repair edit. An abort with no named rule triggers scope reduction and checkpointing, not a geometry repair and not an identical retry.
- Before any repeat of a validation command, require at least one of: a relevant state change since the last run, materially new evidence or a meaningful search refinement, or a bounded transient failure whose cause is outside your control. State which one applies.
- If none applies, do not re-run. Change the action instead: edit the failing geometry or input, narrow the check, or inspect the failing element. If that is not possible, stop and report the blocking rule.
- A run with unchanged arguments, inputs, and payload is not new evidence. A near-identical failure on the same rule, such as a 90%-similar payload, is a repeat regardless of how it is worded.
- Change only what the failing rule requires; preserve unrelated walls, fixtures, and clearances.
- Missing optional images or plotting libraries never justify a geometry edit or a long environment-repair detour.
- Do not let a passing run erase the failing rules recorded from earlier runs.

## Verification

- Before any repair, confirm the recorded verifier failure names a rule, contract, schema field, or element id with a failing value. If it names none and reports a timeout or tool-call cap with reward 0, classify it as an execution-budget abort instead of a repair.
- After an execution-budget abort, confirm the partial outputs were persisted and that the re-run used a narrower scope such as the next unchecked rule group or artifact. A geometry change or an identical replay in response to an abort is a failure.
- Record the full failing rule set from every validation run, with element ids, before deciding the next action.
- Confirm every re-run follows an intervening geometry or input edit, or genuinely new evidence. A re-run without one is an unjustified retry.
- Confirm `repaired_plan.dxf` and `repaired_layout.json` describe the same geometry before accepting a passing final validation. A pass on only one artifact is not a pass.
- Confirm each repair maps to a violated rule or to preserving a valid clearance.
