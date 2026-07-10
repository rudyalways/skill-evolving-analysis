# Paper & System Index — Skill Evolution Landscape

> Quick lookup for all systems referenced in this research workspace.  
> Last updated: 2026-07-08

## By evolution route

### Route 1: Trajectory → Skill

| System | Org | arXiv | GitHub |
|--------|-----|-------|--------|
| Voyager | NVIDIA | — | [MineDojo/Voyager](https://github.com/MineDojo/Voyager) |
| SkillRL | aiming-lab | [2602.08234](https://arxiv.org/abs/2602.08234) | [aiming-lab/SkillRL](https://github.com/aiming-lab/SkillRL) |
| Trace2Skill | Qwen/Alibaba | [2603.25158](https://arxiv.org/abs/2603.25158) | [Qwen-Applications/Trace2Skill](https://github.com/Qwen-Applications/Trace2Skill) |
| Memento-Skills | — | [2603.18743](https://arxiv.org/abs/2603.18743) | [skills.memento.run](https://skills.memento.run/) |
| SkillHone | Tencent | [2606.08671](https://arxiv.org/abs/2606.08671) | [Tencent/SkillHone](https://github.com/Tencent/SkillHone) |
| ExpeL | THU | [2308.10144](https://arxiv.org/abs/2308.10144) | [LeapLabTHU/ExpeL](https://github.com/LeapLabTHU/ExpeL) |

### Route 2: Failure → Skill / Harness

| System | arXiv | Notes |
|--------|-------|-------|
| SkillRL | 2602.08234 | Failure lessons in SkillBank |
| HarnessFix | [2606.06324](https://arxiv.org/abs/2606.06324) | HTIR → ETCLOVG layer repair |
| SkillHone | 2606.08671 | Practice probe failure → revision |

### Route 3: Skill Revision (Versioned)

| System | arXiv | Key mechanism |
|--------|-------|---------------|
| SkillHone | 2606.08671 | Persistent decision history |
| SkillOpt | — | Validation-gated text edits → best_skill.md |
| Trace2Skill | 2603.25158 | Parallel patch → conflict-free merge |

### Route 4: Skill Graph

| System | arXiv | Scale |
|--------|-------|-------|
| Graph of Skills | [2604.05333](https://arxiv.org/abs/2604.05333) | Dependency-aware subgraph |
| SkillRouter | [2603.22455](https://arxiv.org/abs/2603.22455) | ~80K skills |
| GraSP | [2604.17870](https://arxiv.org/abs/2604.17870) | Graph-structured compositions |
| SkillGraph | [2604.17503](https://arxiv.org/abs/2604.17503) | Multi-agent + graph topology |

### Route 5: Program Skill

| System | Notes |
|--------|-------|
| Voyager | Executable JS skills in Minecraft |
| Inducing Programmatic Skills | — |

### Route 6: Workflow Skill

| System | arXiv | Domain |
|--------|-------|--------|
| ComfyClaw | [2607.01709](https://arxiv.org/abs/2607.01709) | ComfyUI image generation workflows |
| SkillFlow (executor) | — | YAML DAG pipeline engine |

## By production method

| Method | Systems |
|--------|---------|
| Distillation | SkillRL, Trace2Skill, AutoSkill |
| Reflection | Memento-Skills, Reflexion, ExpeL |
| RL | SkillRL (GRPO + SkillBank) |
| Search/Validate | SkillOpt, EvoSkills, HarnessFix |

## Infrastructure layer

| System | arXiv | Role |
|--------|-------|------|
| Claw-R1 | [2606.09138](https://arxiv.org/abs/2606.09138) | Step-level data middleware |
| OpenClaw-RL | [2603.10165](https://arxiv.org/abs/2603.10165) | Online RL from next-state (weight layer) |
| AgentEvolver | [2511.10395](https://arxiv.org/abs/2511.10395) | Self-questioning + navigating + attributing |
| HarnessX | — | Harness foundry + RL bridge |

## Harness co-evolution

| System | arXiv | Mechanism |
|--------|-------|-----------|
| Self-Harness | [2606.09498](https://arxiv.org/abs/2606.09498) | Weakness mining → proposal → validation |
| AHE | [2604.25850](https://arxiv.org/abs/2604.25850) | Observability-driven harness edit |
| Meta-Harness | [2603.28052](https://arxiv.org/abs/2603.28052) | Outer-loop harness code search |
| HarnessFix | 2606.06324 | Trace-guided harness flaw repair |

## Industry (manual / semi-auto)

| Product | Skill format | Evolution |
|---------|-------------|-----------|
| Anthropic Agent Skills | agentskills.io SKILL.md | Human + roadmap for auto |
| OpenAI Codex | Skills + Record & Replay | Demo → skill |
| Cursor | .cursor/skills/ | Human + Tab RL signal |
| OpenHands | Persistent skill install | Cross-session manage |

## Curated lists

- [DataArcTech/Awesome-Agent-Skill-Papers](https://github.com/DataArcTech/Awesome-Agent-Skill-Papers)
- [agentskills.io](https://agentskills.io) — open standard
