# Public skill mechanisms to adopt

This ledger records mechanisms reviewed from major public repositories, what
this pipeline adopts, and what remains intentionally external. Source revisions
were inspected on 2026-10-22. Concepts are adapted to
`common/skill_format.json`; upstream orchestration and product packaging are
not copied blindly.

## Sources

| Organization | Source | Inspected revision | Useful mechanism |
| --- | --- | --- | --- |
| Anthropic | [skill-creator](https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/skill-creator) | `dbd4588f9e1033efb41dad4bef2f7947c8993d44` | Paired evals, evidence grading, blind comparison, causal analysis, iterative improvement |
| OpenAI | [skill-creator](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.system/skill-creator) | `49f948faa9258a0c61caceaf225e179651397431` | Concise authoring, degrees of freedom, progressive disclosure, deterministic validation |
| Google Cloud | [EvalBench](https://github.com/GoogleCloudPlatform/evalbench/tree/5e57038708db781418c4969b7ed0c2c17adb2f6c) | `5e57038708db781418c4969b7ed0c2c17adb2f6c` | Sandboxed multi-turn scenarios, simulated users, trajectory scoring, epochs and model matrices |
| Google DeepMind | [workflow skill creator](https://github.com/google-deepmind/science-skills/blob/99f3085bcb40514cdba7833205b3dedbf473b26d/skills/workflow_skill_creator/SKILL.md) | `99f3085bcb40514cdba7833205b3dedbf473b26d` | Distill completed workflows, dependency reuse, error/rate-limit design, instruction-only versus executable skills |
| Google ADK | [agent skills tutorial](https://github.com/google/adk-samples/tree/main/python/agents/agent-skills-tutorial) | repository moved during inspection | L1 metadata, L2 instructions, L3 resources, composition and missing-skill handling |
| Microsoft | [skill creator](https://github.com/microsoft/skills/blob/bd924c165294e72356fdd19260ac81e5a968d889/.github/skills/skill-creator/SKILL.md) | `bd924c165294e72356fdd19260ac81e5a968d889` | Authoritative sources, complete examples, authentication and non-happy-path acceptance checks |
| AWS | [Strands Agent Skills sample](https://github.com/aws-samples/sample-strands-agents-agentskills) | main inspected 2026-10-22 | Path containment, file-size limits, strict loading errors |
| MCP | [experimental Skills extension](https://github.com/modelcontextprotocol/experimental-ext-skills/tree/c1aa87e4c381c82b99aa37471d0eae4ab50f9985) | `c1aa87e4c381c82b99aa37471d0eae4ab50f9985` | Portable catalogs, content digests, directory reads and `skill://` resource identity |

## Adoption status

| Mechanism | Status | Local implementation |
| --- | --- | --- |
| Canonical sections and directories | implemented | `common/skill_format.json` |
| Structural authoring validation | implemented | `common/skill_format_checker.py` |
| Eval fixtures and aggregation | implemented | `common/skill_evaluation.py` |
| Grader, comparator and analyzer contracts | implemented | `04_optimize_agent/skill-create/references/` |
| Trace and operation provenance | implemented | normalized manifests, finding records, lifecycle metadata |
| Secure resource containment and size limits | implemented | `common/skill_format_checker.py` |
| Skill dependencies and source ledger | implemented | skill metadata contract |
| Activation positive/near-miss metrics | implemented | `common/skill_evaluation.py` |
| Evaluated/promoted lifecycle | implemented | publication transition after Judge |
| Replay manifest and measured benchmark gates | implemented | `common/skill_evaluation.py`, Verifiter and Judge |
| Automated multi-turn paired executor | planned | must drive a real backend; `not_run` remains mandatory without execution |
| MCP `skill://` serving | deferred | transport feature, separate from evolution quality |

## Pipeline rules derived from the review

1. Distill successful completed workflows as well as defects. Reuse an existing
   skill or dependency before creating overlapping instructions.
2. Record source URL, revision, retrieval time, and content digest for external
   knowledge. Stale or unpinned knowledge is a limitation, not silent truth.
3. Keep candidate skills provisional until structural checks pass. Mark them
   evaluated only when Judge accepts measured evidence; promote only when
   configured evidence and session thresholds are met.
4. Test skill activation separately from task execution. Measure positive
   recall and near-miss false-positive rate.
5. Treat skill resources as untrusted input: reject traversal, symlink escape,
   oversized files, invalid eval paths, and broken scripts.
6. Behavioral claims require real paired execution. Preserve backend, model,
   prompt sequence, trial count, skill hashes, transcripts, outputs, timings,
   errors, tokens, and tool calls. Otherwise write `not_run`.
7. Score goal completion and tool trajectories in addition to final text.
   Repeat nondeterministic trials and retain variance.
8. Preserve the previously published skill as current best. A failed Judge or
   regressing replay must not publish candidate files or lifecycle promotion.
9. Keep promotion cases hidden from Optimize. Held-out prompts and source trace
   IDs must be disjoint from development fixtures. Promotion uses held-out
   pass rate and activation false-positive limits, never training gain alone.

## Next executable milestone

The remaining large feature is the multi-turn paired executor. It should reuse
operation worker isolation and existing backend launchers, execute identical
conversation plans against baseline and candidate skill sets, and write the
replay manifest and benchmark artifacts already validated by this repository.
It must be optional when no backend is available and must never synthesize
missing measurements.
