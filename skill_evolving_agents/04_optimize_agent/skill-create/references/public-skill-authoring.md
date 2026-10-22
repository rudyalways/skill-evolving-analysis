# Public skill-authoring sources

This pipeline borrows general authoring principles from two public
Apache-2.0 skill creators while retaining its own contracts.

## Sources reviewed

- Anthropic, `anthropics/skills`, `skills/skill-creator`, revision
  `dbd4588f9e1033efb41dad4bef2f7947c8993d44`
  - https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/skill-creator
- OpenAI, `openai/skills`, `skills/.system/skill-creator`, revision
  `49f948faa9258a0c61caceaf225e179651397431`
  - https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.system/skill-creator

Each source distributes its skill-creator package under Apache License 2.0.
This file records provenance for the adapted concepts; no upstream file is
copied verbatim.

## Principles adopted

- Extract concrete examples, triggers, edge cases, and expected output before
  drafting.
- Keep instructions concise; assume the underlying model already knows common
  facts.
- Match instruction specificity to workflow fragility.
- Use progressive disclosure through scripts, references, assets, and evals.
- Keep references shallow and avoid duplicated content.
- Validate names, descriptions, resources, scripts, and behavioral examples.
- Improve skills iteratively from execution evidence.
- Grade each expectation against concrete transcript or output evidence.
- Compare candidate and baseline outputs blindly before revealing their source.
- Analyze why the winner won and turn causal differences into targeted edits.
- Benchmark repeated with-skill and without-skill runs, preserving variance,
  errors, time, tokens, and tool-call cost.
- Critique weak evaluations that pass superficial or incorrect output.

## Mapping to this pipeline

| Public concept | Canonical section or directory |
| --- | --- |
| Purpose and scope | `overview` |
| Trigger scenarios | `when_to_use` |
| Negative trigger examples | `do_not_use` |
| Ordered creation method | `workflow` |
| Safety and authoring rules | `constraints` |
| Validation and evaluation | `verification` |
| Required generated files | `output_format` |
| Unsupported execution modes | `limitations` |
| Detailed documentation | `references` |
| Deterministic utilities | `scripts` |
| Delegated prompts | `agents` |
| Reusable output material | `assets` |
| Behavioral cases | `evals` |

## Implemented machinery

| Upstream mechanism | Pipeline implementation |
| --- | --- |
| Quick validation | `common/skill_format_checker.py` |
| Eval schema validation | `common/skill_evaluation.py validate` |
| Benchmark aggregation | `common/skill_evaluation.py aggregate` |
| Grader/comparator/analyzer contracts | `references/evaluation-artifacts.md` |
| Paired improvement loop | `references/evaluation-loop.md` plus Verifiter/Judge |
| Version provenance | skill metadata lifecycle and operation archives |

The pipeline reuses its existing agent runner, operation isolation, Verifiter,
Judge, metrics, and trace logs rather than copying Anthropic's Claude-specific
runner. Structural validation is executable now. Behavioral comparison runs
only when an operation has a runnable replay harness and must otherwise be
reported as `not_run`.

## Deliberately not copied

- Claude-specific subagent protocol, browser viewer, and packaging format.
- OpenAI-specific `agents/openai.yaml` generation.
- Upstream heading vocabularies that conflict with
  `common/skill_format.json`.
- Generic interview steps when the trace already contains the requirements.

The existing Optimize, Verifiter, and Judge stages own generation, validation,
pass/fail acceptance, and publication. Any future baseline-versus-skill evaluator should feed
those stages rather than introduce a second orchestration system.
