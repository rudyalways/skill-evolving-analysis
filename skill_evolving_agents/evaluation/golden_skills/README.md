# Golden skill bundles

Each golden skill is a **directory**, not a single JSON record. JSON is only the
machine-readable manifest inside the directory and the catalog index.

## Required layout

```text
golden_skills/<skill-id>/
  SKILL.md                 # canonical human-readable skill
  skill.json               # visible/workflow/verification/source/review
  README.md                # scope, status, limitations
  evals/
    tasks.json             # frozen task cards
  environment/
    README.md              # sandbox, auth, fixtures
  simulator/
    personas.json          # optional user personas
  scripts/                 # optional executable helpers
  references/              # optional source references
  assets/                  # optional images/fixtures
  stage-goldens/           # optional internal-stage labels
```

Scripts are optional. A skill needs them only when its procedure requires
executable helpers. A CMS API skill may need none; a spreadsheet or invoice
skill may need a validator and fixtures.

## Status

- `candidate` — source material selected; no bundle yet.
- `draft` — bundle exists; no independent review.
- `silver` — one reviewer.
- `gold` — two independent reviewers with the required roles, frozen evals,
  and a held-out pass record.

## Gold requirements

A bundle cannot be `gold` unless:

- `SKILL.md` and `skill.json` exist;
- verification is non-empty;
- `evals/tasks.json` exists and is frozen;
- source provenance is recorded;
- two reviewers with `domain_expert` and `user_advocate` roles approved;
- synthetic origin is flagged, not hidden;
- a held-out run passes.

## Catalog

A catalog is an index of candidate bundles:

```json
{
  "skill_id": "report-publishing",
  "bundle_path": "golden_skills/report-publishing",
  "authority": "official_vendor | named_expert",
  "domain": "office",
  "review_status": "draft",
  "bundle_status": "ready | scaffolded | missing"
}
```

The catalog does not replace the directory. A candidate with no bundle is not a
skill.
