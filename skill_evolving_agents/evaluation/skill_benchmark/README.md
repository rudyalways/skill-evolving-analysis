# Golden-skill benchmark: report-publishing slice

This is the first executable vertical slice of the golden-skill benchmark.

```
golden skill
  -> visible task contract
  -> generated task cards
  -> user simulator
  -> multi-turn tool trace
  -> verification section as oracle
  -> pass/fail with feedback
```

## What is implemented

- `golden.py` — loads `skill.json`, validates the bundle, evaluates the
  verification section.
- `tasks.py` — generates 10 related tasks from the golden skill, including
  long-title, missing-auth, publish-timeout, slug-conflict, and duplicate-title
  variants.
- `cms.py` — in-memory CMS with auth, slug conflicts, media, and injectable
  publish timeouts.
- `agent.py` — deterministic reference agent and an incomplete agent used to
  exercise user feedback.
- `simulator.py` — multi-turn user simulator; checks verification as a private
  oracle and returns observable feedback, not rubric IDs.
- `runner.py` — runs tasks, aggregates pass rate, refusals, repairs, and tool
  calls.
- `__main__.py` — CLI.

## Golden skill bundle

`evaluation/golden_skills/report-publishing/` is a directory bundle, not a
single JSON record:

- `SKILL.md` — human-readable skill.
- `skill.json` — visible/workflow/verification sections, source provenance,
  review state.
- `evals/tasks.json` — frozen task cards.
- `environment/` — sandbox description.
- `simulator/personas.json` — user persona.
- `scripts/` — optional helpers; none required here.
- `references/` — source references.
- Status: **draft / synthetic / pending review**. It is not gold.

Validate the directory contract:

```bash
python3 -m evaluation.skill_benchmark.bundle \
  evaluation/golden_skills/report-publishing
```

Use `--require-gold` to reject draft or synthetic bundles.

## Run

```bash
python3 -m evaluation.skill_benchmark \
  --skill evaluation/golden_skills/report-publishing \
  --count 10 \
  --out /tmp/report-publishing-benchmark.json
```

Feedback-recovery demo:

```bash
python3 -m evaluation.skill_benchmark \
  --skill evaluation/golden_skills/report-publishing \
  --agent incomplete \
  --count 10
```

## Task variants

| Variant | What it tests |
|---|---|
| Normal | Full publish and verification |
| Long title | Title truncation and verification |
| Missing auth | Stop and escalate; no page created |
| Publish timeout | Retry once and recover |
| Slug conflict | Choose a unique slug |
| Duplicate title | Choose a distinct title |

## Verification

The simulator checks:

- page is published;
- title is present and at most 60 characters;
- slug is lowercase and hyphenated;
- meta description is 50–160 characters;
- Summary, Method, Findings, and Sources exist;
- at least one `https://` source exists;
- a cover image exists;
- no duplicate title;
- every task-required point appears.

## Current result

- Reference agent: **10/10** tasks pass.
- Incomplete agent (skips the cover image): **10/10** after user feedback and
  repair; 9 tasks exercised recovery.
- Auth case: refused with **0** tool calls and no page.
- Normal trace: 3 user/assistant messages, 6 tool calls.

## Limitations

- The CMS is in-memory, not a real CMS deployment.
- The reference agent is deterministic, not an LLM.
- The golden skill is synthetic and has no raw request attached.
- No domain expert or user advocate has reviewed it.
- No internal-stage goldens yet.
- No live dashboard yet.

## Next

1. Replace the in-memory CMS with a sandbox CMS adapter.
2. Add a real LLM worker as an optional agent.
3. Add `source.json` with a raw request/trace or a reviewed synthetic statement.
4. Add internal-stage goldens from the same trace.
5. Add reviewer approval and a dashboard.
