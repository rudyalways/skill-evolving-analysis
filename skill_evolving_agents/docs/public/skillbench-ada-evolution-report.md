# SkillsBench ADA evolution experiment

Date: 2026-11-06

## Experiment

The same `ada-bathroom-plan-repair` SkillsBench task was run twice with the
DeepAgents harness and `deepseek/deepseek-chat`: first with `no-skill`, then
with `with-skill`. Both runs used Docker as root, DeepSeek's OpenAI-compatible
`/v1` endpoint, the same task digest, and the same verifier.

The valid no-skill trajectory was then ingested by the evolving pipeline using
the `low-cost` profile, DSH, and DeepSeek Flash. The pipeline started with the
three task skills as its inventory.

## Results

| Metric | No skill | Evolved skill set | Change |
|---|---:|---:|---:|
| SkillsBench score | 0/1 | 0/1 | 0 |
| Passed verifier tests | 0/6 | 0/6 | 0 |
| Required outputs present | 0/6 | 6/6 | +6 |
| Tool calls | 140 | 504 | +364 (+260%) |
| Trajectory steps | 144 | 525 | +381 |
| Agent execution | 390.0 s | 1740.2 s | +1350.2 s |
| Total run time | 641.3 s | 1955.4 s | +1314.1 s |
| Reported total tokens | 5,963,537 | 41,945,397 | +35,981,860 |

The token totals are provider telemetry that include cache reads. They are not
an invoice: BenchFlow had no price source and reported cost as unavailable.

## Evolution result

The pipeline normalized one ACP trajectory, selected one retry-oscillation
finding, diagnosed one methodology gap, recalled all three skills, proposed one
update, and accepted one update. End-to-end pipeline time was 153.782 seconds
with five agent calls.

The accepted operation updated `geometric-layout-repair` with:

- progress-aware retry rules in workflow, constraints, and verification;
- `evals/evals.json`;
- `evals/retry-no-progress.md`;
- deterministic `agents/openai.yaml` metadata.

The structural verifier passed and publication was accepted. No behavioral
replay was available inside the evolution run, which its metrics correctly
reported as a warning.

## What improved

The no-skill agent performed substantial analysis but produced none of the six
required files at `/root/output`. The with-skill agent found and read the three
deployed skills and produced all six required files in the correct output
directory. This is real progress before the binary scorer, even though the
final score stayed zero.

## What regressed

The evolved prose guard did not prevent retry oscillation. The with-skill run
made 504 tool calls and repeatedly executed identical geometry checks. Its
runtime was 4.46 times the baseline agent-execution time.

The generated artifacts then failed on correctness:

- fixture bounding boxes used two corners where the schema required a
  four-point polygon;
- the extracted room polygon had IoU 0.742 against the reference, below 0.85;
- downstream turning-space and repair checks failed or could not evaluate the
  malformed geometry.

## Pipeline defect found and fixed

Post-run audit found that ACP tool results are nested inside `content.content`.
The first adapter version recorded those result previews as empty strings. That
made the retry detector overconfident: it could see repeated tool names, but not
the actual changing geometry results. The adapter now recursively extracts ACP
text content, and a regression test covers user, tool, and final-agent events.

This fix was made after the evolution experiment, so the published skill update
must not be treated as a clean validation of the corrected miner. A corrected
rerun should occur only after adding reward/verifier ingestion and a behavioral
publication gate; otherwise it would repeat an expensive experiment with known
evaluation gaps.

## Conclusion

This experiment does not demonstrate score lift. It demonstrates that the
trace-to-skill loop can ingest a real external benchmark trace and publish an
evidence-linked skill update, but structural acceptance is not a proxy for
behavioral improvement.

The next iteration should make three changes before another paid rerun:

1. Feed verifier output and final reward into trace normalization so mining
   prioritizes the terminal failure, not only tool-pattern signals.
2. Require a behavioral replay or benchmark shadow run before publication.
3. Enforce retry budgets in the harness using action/result fingerprints;
   prose in `SKILL.md` is not a reliable loop-control mechanism.

## Artifacts

- Baseline: `workspace/skillbench/ada-baseline-valid-20261106/2026-11-06__11-32-56`
- Evolution: `workspace/runs/skillbench-ada-evolution@2026-11-06T11:48`
- With-skill rerun: `workspace/skillbench/ada-evolved-20261106/2026-11-06__11-51-14`
- Accepted release: `workspace/runs/skillbench-ada-evolution@2026-11-06T11:48/run/releases/b77eac30cb75eba0393c23f57e725e34360a62852ea1eb67c7b85249df5a193f`

Infrastructure note: BenchFlow 0.6.2 required a local verifier-output download
workaround on Docker Desktop for macOS. The task's oracle was run after that
workaround and passed 1/1, validating the scorer before this experiment.

## Follow-up: objective feedback and harness validity

The follow-up attached the benchmark reward, result, and bounded verifier
output to the ACP trace as an objective terminal event. The normalizer now
reserves one event slot for that signal, so long traces cannot discard the
verifier at the event cap. The pipeline selected the objective failure and
accepted an update to `geometric-layout-repair` containing a deterministic
geometry-contract validator and fixtures.

The first replay after that update passed 4/6 verifier tests in 510.1 seconds
and 184 tool calls, compared with 1,740.2 seconds and 504 calls in the original
with-skill run. It still scored zero. Audit then showed that this was not a
valid treatment cell: BenchFlow mounted `/skills`, but its DeepAgents adapter
did not advertise skills, the evolved skill was never read, and its validator
was never invoked. `evaluation/skillsbench_skill_usage.py` now rejects such
silent no-activation cells.

After adding explicit skill discovery, a replay read all three skills but
exposed a second adapter defect: filesystem tools virtualized `/root/work` as
`/root/root/work`, while shell execution used real `/root/work`. It produced no
deliverables. Aligning both tool families to the real sandbox namespace fixed
that inconsistency.

The namespace-aligned replay demonstrated genuine activation and resource
discovery. It produced all six required artifacts, made 150 tool calls, and
timed out at the configured 900-second agent limit. The objective verifier
found malformed two-corner fixture bboxes, a wrong original turning-circle Y
coordinate, and missing `REPAIR-WC` polygon geometry. The validator was read
but never executed before timeout.

Feeding this replay back through the pipeline produced a new provisional
`repair-budget-checkpoint` skill. The pipeline correctly treated the duplicate
retry signal as `no_change` because `geometric-layout-repair` already covered
it. Verification scored the new skill 0.955556 and identified one concrete
defect: the requested checkpoint-overrun near-miss eval was absent. The
candidate inventory now includes that missing regression case and passes the
deterministic eval-schema validator.

These runs still do not establish benchmark score lift. They establish three
previously missing validity controls: objective terminal evidence retention,
observed skill activation, and consistent harness filesystem semantics. The
next paid replay should use the budget-checkpoint skill together with a
schema-aware artifact validator; a generic point-array checker alone cannot
enforce task-provided JSON Schema constraints.

## Final schema-aware replay

The geometry skill now includes `scripts/validate_output_bundle.py`. It
discovers every `<name>_schema.json`, requires the matching `<name>.json`,
applies Draft 2020-12 validation, then runs generic geometry and DXF checks.
Against the prior failed artifacts it immediately identified the first defect
as `repaired_layout.json:$.fixtures[0].bbox` having fewer than four points.

The final treatment bundle contained four readable skills:
`ada-plan-view-accessibility`, `architectural-dxf-extraction`,
`geometric-layout-repair`, and `repair-budget-checkpoint`. The run used the
non-root sandbox user; trajectory audit found no access to `/oracle`,
`/solution`, verifier code, tests, or other locked benchmark internals. All
four `SKILL.md` files were observed as read, and the bundle validator was
discovered and executed.

The validator first rejected missing output, then rejected the malformed
two-corner fixture bbox, and finally passed the complete bundle after repair.
The objective verifier passed all six tests. Final metrics were:

- score and reward: 1/1, 1.0;
- verifier: 6 passed, 0 failed;
- agent execution: 390.0 seconds;
- tool calls: 112;
- reported tokens: 4,850,780, including provider-reported cache reads;
- agent timeout: none;
- required artifacts: 6/6, plus the optional preview image.

Total wall time was 1,016.1 seconds because non-root DeepAgents provisioning
and installation dominated startup; this is infrastructure overhead, not
agent execution. Compared with the previous valid activated timeout run, agent
execution fell from 900.1 to 390.0 seconds, tool calls from 150 to 112, and
reported tokens from 7,573,118 to 4,850,780 while reward improved from 0 to 1.

Artifact: `workspace/skillbench/ada-schema-budget-final-20261106/2026-11-06__14-24-34`.
