# Environment

The sandbox is an in-memory CMS implemented in
`evaluation/skill_benchmark/cms.py`.

- auth token: `test-token` for authorized tasks;
- missing auth: no token, expected refusal;
- published page state is checked after the run;
- publish timeout can be injected;
- slug and title conflicts can be seeded.

No real CMS credentials are stored in this bundle.
