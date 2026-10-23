# SkillsBench methodology evaluation

Use held-out tasks that were not used to mine or author the evaluated skill.
For each task, run at least three trials in both matched conditions:

```bash
bench eval run --tasks-dir tasks/<task-id> --agent <agent> --model <model> \
  --skill-mode no-skill

bench eval run --tasks-dir tasks/<task-id> --agent <agent> --model <model> \
  --skill-mode with-skill --skills-dir <evolved-skills>
```

Convert run results into one JSONL row per task, trial, and condition. Required
fields are `task_id`, `trial`, `condition`, and `passed`. Optional fields are
`tokens`, `tool_calls`, `repeated_errors`, `skill_context_tokens`,
`candidate_count`, `candidate_correct`, `false_positive_creations`, and
`candidate_novelty`.

Set `ablation` to `full` for the complete miner. Repeat the same paired cells
with one strategy disabled at a time and name that removal, for example
`without_failure_recovery`. Summarize all matched cells with:

```bash
python evaluation/skillsbench_methodology_eval.py results.jsonl \
  --out methodology-report.json
```

The report uses task-macro pass rate, paired efficiency deltas, mining
precision, false-positive creations, novelty, context size, and pass-rate loss
for each ablation. Unpaired cells are reported but excluded from comparisons.

# Configuration research

`optimize_config.py` provides the bounded offline optimization control plane.
It validates the knob and metric registries, generates reproducible constrained
grids, and evaluates recorded results using hard safety constraints before
Pareto-style cost and quality objectives.

It does not promote production configuration. An eligible offline candidate is
authorized only to enter shadow evaluation.

Available search algorithms are bounded grid, seeded random, wide-and-deep,
and persistent UCB/MCTS. Reviewed trial outcomes update a Beta success
posterior and reward exponential moving average for each knob/value choice in
`workspace/optimization.sqlite`.
