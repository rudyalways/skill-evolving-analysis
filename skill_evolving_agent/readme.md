# Evolver workflow

How a container runs one session is `run-guide.md`.

State machine for `evolver.png`. Data drives each step. Thresholds are tunable. A skill states experience, what not to do, what must be done, and where it applies.

```mermaid
stateDiagram-v2
  [*] --> RawTraces
  RawTraces --> CutTraces
  CutTraces --> LabelA
  LabelA --> LabelB
  LabelB --> Goal
  Goal --> Generate: create
  Goal --> Delete: delete
  Goal --> Select: update / merge / split
  Select --> Update
  Select --> Merge
  Select --> Split
  Update --> Verify
  Merge --> Verify
  Split --> Verify
  Generate --> Verify
  Delete --> Verify
  Verify --> Judge
  Judge --> [*]: pass
  Judge --> CutTraces: back
  Judge --> LabelA: back
  Judge --> LabelB: back
  Judge --> Goal: back
  Judge --> Select: back
  Judge --> Update: back
  Judge --> Generate: back
```

| Step | State | Does | Reads | Writes |
|---|---|---|---|---|
| | RawTraces | New traces, read only | `workspace/traces/target_agent_traces`, optional `workspace/traces/reference_agent_traces_optional` | |
| step1 | CutTraces | Cut traces into related topics. A trace that fits no topic stays unassigned | `workspace/traces/target_agent_traces`, optional `workspace/traces/reference_agent_traces_optional`, `evolver_skills/step1-cut-traces`, `evolver_skills/step1-cut-traces/cut-traces.example.json` | Topic slices in `workspace/traces/derived_traces` |
| step2 | LabelA | Demand side. Analyze the derived traces and the gaps. Label the improvement areas that are needed | `workspace/traces/derived_traces`, `data/skill_capabilites`, `evolver_skills/step2-dignosis/evolve-goal-checker.py`, `evolver_skills/step2-dignosis/diagnosis.example.json` | `workspace/run/diagnosis.json` |
| step3 | LabelB | Label each existing skill until it has at least 3 labels, each with a weight | `evolver_skills/step3-existing_skills_labeler`, `data/skill_capabilites`, `workspace/target/to_be_improved_skills` | `workspace/target/to_be_improved_skills_metadata/metadata.json` |
| step4 | Goal | Choose the action: create, update, delete, merge, or split | Label A, `evolver_skills/step4-goal-generator`, `evolver_skills/step4-goal-generator/evolve-goal.example.json`, `evolver_skills/reference-skill_format/skill_format.json` | `workspace/run/evolve-goal.json` |
| step5.1 | Select | For update, merge, and split only. Match Label A to Label B and pick the targeted skills | `workspace/run/diagnosis.json`, `metadata.json`, `evolver_skills/step5.1-skill-select/skill_type_checker.py` | `improve_skills` on the goal |
| | Update | Copy the skill into `raw_skills` if it is not there, then update the copy under `to_be_improved_skills` | Goal, `workspace/target/raw_skills` | `workspace/target/to_be_improved_skills` |
| | Merge | Merge the matched skills | Goal | `workspace/target/to_be_improved_skills` |
| | Split | Split a matched skill | Goal | `workspace/target/to_be_improved_skills` |
| | Delete | Delete the skill named by the goal. No Label A to Label B match | Goal | `workspace/target/to_be_improved_skills` |
| step5.2.1 | Generate | Create a skill. No Label A to Label B match | Goal, `evolver_skills/step5.2.1-skill-create` | New skill under `workspace/target/` |
| step5.2.2 | Generate | Record an out-of-distribution gap on the same create branch | Goal, `evolver_skills/step5.2.2-ood-data-updater`, diagnosis | `newly_detected_skill_capabilites_missing` stays on the diagnosis |
| step6 | Verify | Checklist and goal alignment. Compare each raw skill with the improved skill. Write status and feedback. Do not choose pass or back | `evolver_skills/step6-verifiter`, `evolver_skills/step6-verifiter/verification.example.json`, `evolver_skills/step6-verifiter/verify_goal.py`, `workspace/run/evolve-goal.json`, `target/raw_skills`, `target/to_be_improved_skills` | overall and per-skill status, feedback, and `ood` in `workspace/run/verification.json` |
| step7 | Judge | Read the verifier output and stop or send the run back | `workspace/run/verification.json`, the goal | `feedback.action` in that same file. `pass` stops. `back` re-enters `action.to` |

`reference-skill_format` is the shared section and directory list. It is not a state. Select, update, merge, and split are one branch. Create and the out-of-distribution record are the other branch, so they are step 5.2.1 and step 5.2.2. Update, merge, split, and delete have no skill folder. `z-new-data-format-generator` is the old Cluster skill and is not on this machine.

Label A, Label B, and Select read the capability tree. Select runs only after the goal action is update, merge, or split.

Each step appends one JSON line to `workspace/logs/execution.jsonl` when it starts and when it finishes. A line is `{"step": "<step1>", "event": "<started|done|failed>", "at": "<iso8601>"}`. That file is the run log. It is not an input to the next step.
