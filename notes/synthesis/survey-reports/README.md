# Survey Reports — Per-Repo 12-Section Deliverables

Template: [templates/survey-matrix-repo-report.md](../../templates/survey-matrix-repo-report.md)  
Matrix: [agent-skill-architecture-survey-matrix.md](../agent-skill-architecture-survey-matrix.md) (165 dimensions)

| Repo | Report | Status | Overall | RL | Evolution |
|------|--------|--------|:-------:|:--:|:---------:|
| **OpenSquilla** | [opensquilla.md](opensquilla.md) | ★ complete L3 | 9.0 | 6 | 9 |
| **Hermes** | [hermes-agent.md](hermes-agent.md) | ★ complete L3 | 8.1 | 8 | 9 |
| **OpenClaw** | [openclaw.md](openclaw.md) | ★ complete L3 | 8.0 | 7 | 7 |
| **Claude Rev** | [claude-code-rev.md](claude-code-rev.md) | ★ complete L3 | 7.7 | 4 | 7 |
| **Codex** | [codex.md](codex.md) | ★ complete L3 | 7.2 | 4 | 3 |
| **TaiChu** | [taichu.md](taichu.md) | ★ complete L3 | 5.0 | 3 | 1 |
| **ZeroClaw** | [zeroclaw.md](zeroclaw.md) | ★ complete L3 | 5.0 | 2 | 2 |
| **GenericAgent** | [genericagent.md](genericagent.md) | ★ complete L3 | 4.8 | 2 | 6 |
| **OpenClaw-RL** | [openclaw-rl.md](openclaw-rl.md) | ★ complete L0 (RL layer) | 8.0* | 8 | — |

\* OpenClaw-RL scored on RL Readiness only — not a skill lifecycle runtime.

Each report includes:
- 12 sections (Architecture → Score)
- Source quotes with file:line
- Public URLs (docs, issues, papers)
- Evidence index table

## Combined borrow stack for TaiChu

```text
Codex          → SKILL.md standard + metadata budget + hooks
OpenClaw       → multi-source scope + trajectory JSONL
Claude Rev     → invoked_skills compact + subagent preload  [P0]
OpenSquilla    → proposals + gates + RRF                    [P1]
Hermes         → review + skill_manage (candidate) + RL env   [P1-P2]
ZeroClaw       → audit + trust_tier metadata                  [P1]
GenericAgent   → Skill Miner philosophy                     [P2]
TaiChu native  → runs_on + per-turn user prefix              [keep]
```
