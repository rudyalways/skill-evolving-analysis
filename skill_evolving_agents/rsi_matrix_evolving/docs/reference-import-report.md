# Reference import report

Extraction time: 2026-10-27T00:00:00+08:00. The timestamp records this repository bootstrap; hashes make the snapshot independently checkable.

## Successfully read inputs

| Input | SHA-256 |
|---|---|
| `evolvent/scenarios-matrix.md` | `231ec358d40776bca25f997e594d2dcb5d2292a8c7f67b1676882f92466ce05b` |
| `evolvent/benchmark-assessment-matrix.md` | `e063a732661dcd8a282486cc02d7114fe48cbb2d345b376f3a54c792418da0b2` |
| `evolvent/benchmark-capability-audit.md` | `2e0c9ae90b0b00ced82ba2cfe2d1aab1f21b1198accdfcabe1dc92ad64ba4db4` |
| `evolvent/data/benchmarks.json` | `8be0a4157349bd859311d5f1e7107e451f73876c8ffa444b0b5d837c0d63ff09` |
| `evolvent/data/harness_matrix.md` | `ac82b5efa0bbcb436aad625cce550c407d481c90e49ca4b23eb731a64c848c1c` |
| `evolvent/research/arch/CONCEPTS.md` | `30bc632c807455f26d115c3eae35171a44d9f049a51cbd2eb1f85c99d2feeef3` |
| `evolvent/research/arch/concepts-coverage.json` | `cba8b0a06206adb6b346675c3e9fb8d032e3fd46cacc6eaa81ee9fca8c44b39a` |
| `evolvent/tools/build_assessment_matrix.py` | `dc3f954d95b4a08057c4d9973aa731163d64c7020252b8ba37b50f9ba15e7fdc` |
| `evolvent/tools/build_benchmark_portfolio.py` | `d43f4a798fc08bd11ee54f819247eabe0cadf0850c36e17b513e93fcc5411207` |
| `skill-evolving-analysis/common/trace_schema.json` | `b5e288b5dffbd5c1460b0d87edd5b0c19c3c8b7e78e115fc2b0821f6ddfa2a93` |
| `skill-evolving-analysis/trace_mining/source_adapters.py` | `89522dd92cb8e81fc8b781b7e4f2a11c76ed6fe995003ec38f3de617deeb2bca` |
| `skill-evolving-analysis/trace_mining/README.md` | `591168f5b6a6ea7a7b0b9fcc4b38aeb173c7a117de6f6f6f517dad449a5b705d` |
| `skill-evolving-analysis/core/adapters.py` | `51b207e2686919caf995a727aae46b6a793c50bec24279c505c7b52a1b2e4aca` |
| `skill-evolving-analysis/config/service-tiers.json` | `be2e2e386364d066c3249364dbc608b7d65cf3ee480d3b151afc7900d9b34725` |
| `skill-evolving-analysis/config/metric-spec.json` | `9d5a6302e0df01920fb1592645bee4bbfe9979997c38625956332b5a0317a1c0` |
| `skill-evolving-analysis/evaluation/README.md` | `9fbca50f4bff33033eb82741bd6b47c7266cb36fc019dac965c89a7c7977f5bf` |
| `skill-evolving-analysis/tests/fixtures/resource-script-reference-trace.jsonl` | `812772f55cccae6752392ccbe1bb91f87ebde864b87dc91886adfb6d08146377` |

The generated all-in-one HTML was visually identified as the human review surface. Generated HTML is a review surface; JSON, Markdown, and validated schemas are the implementation inputs.

## Concept decisions

Adopted: sparse capability/scenario coverage, deterministic-first verification, canonical observable trace events, immutable evidence plus derived labels, adapter envelopes, exact/MinHash-style deduplication, cost tiers, reproducible seeded generation, and explicit provenance. Renamed: benchmark “archetypes” become scenario families; “methodology signals” become trace features; “phase envelopes” become canonical events; benchmark “sources” become provenance records. Rejected: treating benchmark claims as labels, retaining hidden reasoning, using one global ID/OOD flag, and allowing a judge to override deterministic failures.

The two sources duplicate concepts around canonical events, reproducibility, cost control, evidence, and deterministic evaluation. They differ usefully: evolvent is a content prior while skill-evolving-analysis is a data-plane prior. Where benchmark taxonomy is broad but trace schemas are operational, this repository keeps both layers separate rather than collapsing them.

## Inherited uncovered cells

Initial gaps carried forward are: durable long-horizon waiting and its cost; proactive timing/when-to-assist; cross-session active memory with provenance; real-time/streaming and duplex interaction; multimodal audio-video composition; accessibility and persona shifts; safe consequential multi-service actions; failure localization by trajectory invariant; contamination detection; and benchmark rows whose grading method or capability dimensions were explicitly not found (including OmniBench). These are proposals, not ground-truth labels, and begin as `unknown` or `ood_candidate` until supported by target-relative evidence.

