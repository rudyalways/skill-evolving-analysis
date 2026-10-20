# Skill label leaves

Built from `data/processed/skill-labels.jsonl`. Every leaf holds at most 100 skills.
Assignments: `data/processed/skill-label-leaves.jsonl`.

Cut order when a node is over 100: semantic child, another domain, the clone, then a name-range block.

| Facet | Leaves | Largest leaf | Skills placed |
|---|---:|---:|---:|
| job | 2744 | 100 | 27823 |
| domain | 3927 | 100 | 59373 |
| form | 2017 | 100 | 19716 |
| artifact | 1694 | 100 | 19716 |
| binding | 1702 | 100 | 21486 |
| audience | 1603 | 100 | 19716 |
| language | 1567 | 100 | 19716 |
| provenance | 828 | 100 | 19716 |

Leaves in total: 16082. Largest leaf anywhere: 100.
