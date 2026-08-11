---
id: N2026-08-11-001
title: Harness Evolving Frameworks (OSS) — from Lilian Weng post
date: 2026-08-11
tags: [harness-evolution, self-improving-harness, oss, lilian-weng, synthesis]
status: active
source:
  url: https://lilianweng.github.io/posts/2026-07-04-harness/
  title: "Harness Engineering for Self-Improvement"
  author: Lilian Weng
  published: "2026-07-04"
  accessed: "2026-08-11"
  local_raw: data/raw/web/lilian-weng-2026-07-04-harness.md
related: [T004, N2026-07-08-002, N2026-07-08-003]
summary: Open-source / paper systems that evolve the harness (prompts, tools, workflow, harness code), distilled from Lil’Log 2026-07-04, with GitHub links where available.
---

# Harness Evolving Frameworks (OSS)

> Distilled from [Harness Engineering for Self-Improvement](https://lilianweng.github.io/posts/2026-07-04-harness/) (Lilian Weng, 2026-07-04).
>
> **Scope:** systems that evolve the **harness** (L2 — prompts, tools, middleware, workflow, control flow), not only the skill library (L1).

## Optimization ladder (from the post)

```
instruction prompts → structured context → workflow → harness code → optimizer code
```

Shared loop for most harness evolvers:

```
traces → find harness failures → propose harness edit → eval / regression → accept / reject
```

---

## 1. Direct harness self-improvement

These target the full (or near-full) harness design space.

| System | Paper / cite | What evolves | Open source |
|--------|--------------|--------------|-------------|
| **Meta-Harness** | Lee et al. 2026 · [arXiv:2603.28052](https://arxiv.org/abs/2603.28052) | Code that stores / retrieves / presents context — “harness for optimizing harnesses” | [stanford-iris-lab/meta-harness](https://github.com/stanford-iris-lab/meta-harness) |
| **Self-Harness** | Zhang et al. 2026 · [arXiv:2606.09498](https://arxiv.org/abs/2606.09498) | Own harness via weakness mining → bounded proposal → validation | [qzzqzzb/Self-Harness](https://github.com/qzzqzzb/Self-Harness) |
| **AHE** (Agentic Harness Engineering) | Lin et al. 2026 · [arXiv:2604.25850](https://arxiv.org/abs/2604.25850) | 7 components: system prompt, tool desc, tool impl, middleware, skill, sub-agent, LTM — observability-gated edits | [pieea/agentic-harness-engineering](https://github.com/pieea/agentic-harness-engineering) |
| **Darwin Gödel Machine (DGM)** | Zhang et al. 2025 · [arXiv:2505.22954](https://arxiv.org/abs/2505.22954) | Agent modifies its **own harness codebase**; archive of agents; eval-gated | [jennyzzt/dgm](https://github.com/jennyzzt/dgm) |
| **Hyperagents** | Zhang et al. 2026 · [arXiv:2603.19461](https://arxiv.org/abs/2603.19461) | Meta-agent controls how to modify task agents | Follow-on to DGM |

### Self-Harness loop (detail)

1. **Weakness mining** — cluster verifier-grounded failure patterns from traces  
2. **Harness proposal** — same model proposes bounded edits (editable surfaces + failures + preserve-list + prior attempts)  
3. **Proposal validation** — held-in + held-out regression; accept only if no regression  

### AHE observability pillars

1. **Component** — every editable piece is a file; failures map to one component  
2. **Experience** — agent debugger → per-task reports → benchmark overview  
3. **Decision** — each edit is a falsifiable claim (manifesto: evidence, root cause, fix, predicted impact); runs/tracer/verifier/LLM config stay read-only  

---

## 2. Context & workflow search (stepping stones)

Not always “full harness,” but Lilian treats them as the path toward harness-code search.

| System | Paper | Target | Notes / code |
|--------|-------|--------|--------------|
| **ACE** (Agentic Context Engineering) | Zhang et al. · ICLR 2026 | Evolving context playbook (Generator / Reflector / Curator) | Context layer; update rules still handcrafted |
| **MCE** (Meta Context Engineering) | Ye et al. · [arXiv:2601.21557](https://arxiv.org/abs/2601.21557) | Bi-level: meta skill (how to manage context) + base context | Skills as free-form files in a directory |
| **ADAS** | Hu et al. 2025 | Agent workflow **as code** via meta-agent search | Archive of workflows; meta-agent programs new agents |
| **AFlow** | Zhang et al. · ICLR 2025 | Workflow graph + MCTS | Nodes = LLM actions; edges = logic in code |
| **STOP** (Self-Taught Optimizer) | Zelikman et al. · COLM 2024 | Improves the **improver** (recursive scaffolding) | Needs a strong enough base model |

Workflow automation example (not an evolver): [karpathy/autoresearch](https://github.com/karpathy/autoresearch)

Also cited as expert-designed (not self-evolving) workflows: AI Scientist, ScientistOne, Autodata.

---

## 3. Evolutionary search family

| System | Paper | Role | Open source / status |
|--------|-------|------|----------------------|
| **GEPA** | Agrawal et al. · [arXiv:2507.19457](https://arxiv.org/abs/2507.19457) | Reflective prompt evolution + evolutionary search | Widely used; also via DSPy / Hermes self-evolution |
| **Promptbreeder** | Fernando et al. 2023 · [arXiv:2309.16797](https://arxiv.org/abs/2309.16797) | Task prompts + mutation prompts co-evolve | Research |
| **AlphaEvolve** | Novikov et al. · [arXiv:2506.13131](https://arxiv.org/abs/2506.13131) | Coding-agent evolutionary search over marked code blocks | Google; not a general harness product |
| **ShinkaEvolve** | Lange et al. · [arXiv:2509.19349](https://arxiv.org/abs/2509.19349) | Sample-efficient parent sampling + novelty rejection | Research |
| **ThetaEvolve** | Wang et al. · [arXiv:2511.23473](https://arxiv.org/abs/2511.23473) | Evolutionary search + RL + ICL | Research |
| **DemoEvolve** | Che et al. · [arXiv:2605.24539](https://arxiv.org/abs/2605.24539) | Human demos as reference for harness-level diagnosis/editing | Research |
| **DGM** | see §1 | Explicit **harness-code** evolution (vs solution-only) | [jennyzzt/dgm](https://github.com/jennyzzt/dgm) |

---

## 4. Joint harness + model weights

| System | Paper | Idea | Status |
|--------|-------|------|--------|
| **SIA** | Hebbar et al. · [arXiv:2605.27276](https://arxiv.org/abs/2605.27276) | Feedback-agent chooses harness update vs weight update | Early / provisional evidence (per Lilian) |
| **Continual Harness** | Karten et al. · [arXiv:2605.09998](https://arxiv.org/abs/2605.09998) | Online harness adapt + distill teacher on low-reward trajectories | Research |

---

## 5. Related foundry (not in Lilian post; same track)

| System | Repo | Role |
|--------|------|------|
| **HarnessX** | [Darwin-Agent/HarnessX](https://github.com/Darwin-Agent/HarnessX) | Compose processors → auto-search harness config; optional model RL |

---

## Recommended starters (GitHub)

If the goal is **rewrite harness code under a fixed model**:

1. [jennyzzt/dgm](https://github.com/jennyzzt/dgm) — self-modifying harness archive  
2. [stanford-iris-lab/meta-harness](https://github.com/stanford-iris-lab/meta-harness) — outer-loop harness search  
3. [pieea/agentic-harness-engineering](https://github.com/pieea/agentic-harness-engineering) — observability-driven component edits  
4. [qzzqzzb/Self-Harness](https://github.com/qzzqzzb/Self-Harness) — propose / validate loop  

---

## Contrast with skill self-evolution (this workspace)

| Layer | Evolves | Examples |
|-------|---------|----------|
| **L1 Skill** | `SKILL.md` / SOP / SkillBank | Hermes `skill_manage`, OpenSquilla proposals, SkillRL |
| **L2 Harness** | prompts, tools, middleware, workflow, harness code | Meta-Harness, Self-Harness, AHE, DGM |
| **L3 Weights** | model checkpoint via SFT/RL | OpenClaw-RL, HarnessX model loop, SIA |

Platform products (Cursor / Anthropic / OpenAI) often improve the **default harness** via eval flywheels; that loop is usually **not** open-sourced.

---

## Source

| Field | Value |
|-------|-------|
| **Title** | Harness Engineering for Self-Improvement |
| **Author** | Lilian Weng (Lil'Log) |
| **Published** | 2026-07-04 |
| **URL** | https://lilianweng.github.io/posts/2026-07-04-harness/ |
| **Accessed** | 2026-08-11 |
| **Local raw archive** | [`data/raw/web/lilian-weng-2026-07-04-harness.md`](../../data/raw/web/lilian-weng-2026-07-04-harness.md) |

Cross-ref in this repo: [industry-harness-survey.md](industry-harness-survey.md), [skill-evolution-taxonomy.md](skill-evolution-taxonomy.md), [paper-index.md](paper-index.md)
