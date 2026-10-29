# Prior art, not candidate skills

These 166 bundles are **existing third-party skills**. They are not candidate
inputs and not golden labels.

## Why this correction exists

The first selection pass scanned authoritative skill repositories and applied
domain quotas. That was wrong. An existing skill is an implementation, not
evidence of a real user need. Using it as candidate input creates a circular
benchmark: the benchmark would test skills against skills.

## Correct sourcing chain

```text
raw request / real trace / ticket / interview
  -> candidate need and task
  + authority niche
  -> authored golden skill
  -> verification, evals, sandbox
  -> independent review
```

## Allowed use of these bundles

- prior art;
- recall comparison;
- style/structure reference;
- duplicate/merge detection;
- source of "what already exists".

## Forbidden use

- candidate input;
- diagnosis label;
- goal label;
- golden skill;
- verification target by itself.

## Counts

```text
prior-art reference bundles: 166
candidate skills: 0
golden skills: 0
```

A future candidate must name its raw request/trace or authority procedure before
any skill is authored.
