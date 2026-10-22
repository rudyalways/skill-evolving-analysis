# Behavioral eval fixture

Use this schema only when a create goal names the canonical `evals` directory.
Keep cases grounded in the finding evidence.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "A realistic request that needs the skill",
      "expected_output": "A concise description of the successful result",
      "expectations": [
        "An observable requirement",
        "A required completion check"
      ],
      "kind": "should_apply",
      "files": [],
      "source_trace_ids": ["source:session:turn"]
    },
    {
      "id": 2,
      "kind": "should_not_apply",
      "prompt": "A similar request outside the skill boundary",
      "expected_output": "The skill is not selected",
      "expectations": [
        "The skill is not selected or its prohibited workflow is not used"
      ],
      "files": [],
      "source_trace_ids": []
    }
  ]
}
```

## Requirements

- `skill_name` matches SKILL.md frontmatter.
- IDs are unique.
- Every eval has `prompt` and `expected_output`; `files` and `expectations` are
  optional.
- Include at least one `should_apply` and one `should_not_apply` near-miss.
- Positive cases cite normalized trace IDs when derived from observed evidence.
- Expectations are observable statements, not style preferences.
- Do not copy secrets, credentials, or large raw trace content into fixtures.

This compact schema adapts the public Anthropic eval-fixture pattern to the
pipeline's evidence model. Verifiter and Judge remain authoritative; a fixture
does not by itself prove behavioral improvement.
