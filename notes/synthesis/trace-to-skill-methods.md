# Trace → skill methods

> Distilled 2026-09-29 from local cards in
> [`skill-evolving-papers/papers/`](../../../skill-evolving-papers/papers/README.md)
> and the route map in
> [`skill-evolution-taxonomy.md`](skill-evolution-taxonomy.md).
> Scores are the numbers those cards record. A blank score means the card states a
> gain and does not give a figure.
> RRSI is not in that catalog. It is recorded below from the project page and
> [arXiv:2609.24972](https://arxiv.org/abs/2609.24972).

The shared loop is:

```
rollout → trajectory → teacher model → skill document → library
```

The trajectory is discarded. What stays is a procedure: when to use it, the steps, and the pitfalls.

Three families use that loop. They differ in when the distillation runs, whether an edit must pass a check, and whether weights are trained.

## Offline distillers

Batch job on logs. Not on the request path.

| Method | What it does with the trace | Benchmark and reported score |
|---|---|---|
| **Trace2Skill** ([2603.25158](https://arxiv.org/abs/2603.25158), [Hert4/trace2skill](https://github.com/Hert4/trace2skill)) | Parallel analysts read clusters of trajectories, extract a workflow, and merge patches into one skill directory with no conflicts. No online reflection. Can deepen a human skill or start from a weak draft. Card: [`trace2skill-2026.md`](../../../skill-evolving-papers/papers/training-free/trace2skill-2026.md). | Office workflows, math, vision QA. Skills from Qwen3.5-35B traces raise Qwen3.5-122B by up to **+57.65 points** on WikiTableQuestions. Beats sequential editing and ReasoningBank-style memory. Transfers across model size, model family, and out-of-distribution tasks. |
| **ClawTrace / CostCraft** ([2604.23853](https://arxiv.org/abs/2604.23853)) | Same distillation, plus per-step cost. Each session becomes a TraceCard. Patches are typed: preserve, prune, or repair. | On 30 held-out SpreadsheetBench tasks, dropping prune patches roughly **triples quality regressions** without lowering median cost. On the full 84-task SkillsBench transfer it **saves no aggregate cost**. Quality wins come from prune; regressions come from preserve. |
| **SkillCAT** ([2606.13317](https://arxiv.org/abs/2606.13317)) | Several traces per task. Keeps a patch only if replaying it on a clone of the source task does not get worse. At inference, loads only the sub-skill on the path, not the whole library. | SpreadsheetBench, WikiTableQuestions, DocVQA. Up to **+40.40%** average over baselines. |
| **SkillX** ([2604.04804](https://arxiv.org/abs/2604.04804)) | Splits one trace into three layers: plan, functional skill, atomic skill. Then revises from execution feedback. | Built with GLM-4.6, plugged into weaker agents on AppWorld, BFCL-v3, and τ²-Bench. Success and efficiency go up. No number in the card. |
| **SkillGen** ([2605.10999](https://arxiv.org/abs/2605.10999)) | Contrastive induction over success and failure traces, then checks the skill as an intervention: same instances with the skill on and off. | Beats other skill generators on held-out tasks. No number in the card. |
| **SkillAudit** ([2606.14239](https://arxiv.org/abs/2606.14239)) | Paired runs with and without the skill. No hidden tests. Refine strips noise; Repair replaces passages that conflict with the task. | 89 containerized tasks, 8 domains: **73.9%** reward, vs **40.9%** with no skill and **56.7%** with a static expert skill. |
| **ExpeL** ([2308.10144](https://arxiv.org/abs/2308.10144)) | Distills traces into flat natural-language rules, not a skill package. | No numeric score in the card. |
| **Voyager** ([2305.16291](https://arxiv.org/abs/2305.16291)) | Successful programs are summarized into executable JavaScript and retrieved later. | Minecraft: **3.3×** unique items, **2.3×** distance, tech-tree milestones up to **15.3×** faster than prior SOTA. |
| **SkillWeaver** ([2504.07079](https://arxiv.org/abs/2504.07079)) | Web exploration traces become tested Python APIs. | Relative success **+31.8%** on WebArena, **+39.8%** on real sites. Strong-agent APIs help a weaker agent by up to **+54.3%** on WebArena. |

## Online revisers

Still start from a trace. Edit an existing skill after a run, and keep the edit only if a check passes.

| Method | Gate | Benchmark and reported score |
|---|---|---|
| **SkillOpt** ([2605.23904](https://arxiv.org/abs/2605.23904)) | Bounded add/delete/replace on one skill file. Accepted only if a held-out score strictly rises. Explicitly compared with Trace2Skill. | Best or tied on all **52** cells across 6 benchmarks, 7 models, and 3 harnesses (chat, Codex, Claude Code), against human, one-shot, Trace2Skill, TextGrad, GEPA, and EvoSkill. On GPT-5.5, no-skill accuracy rises **+23.5** in chat, **+24.8** in Codex, **+19.1** in Claude Code. |
| **EvoSkill** ([2603.02766](https://arxiv.org/abs/2603.02766)) | Failure analysis writes or edits a skill folder. Pareto selection on held-out validation. Frozen model. | OfficeQA exact match **60.6% → 67.9%** (+7.3). SealQA **26.6% → 38.7%** (+12.1). SealQA skills transfer to BrowseComp at **+5.3** with no further edit. |
| **MetaSkill-Evolve** ([2607.05297](https://arxiv.org/abs/2607.05297)) | Fast loop rewrites the task skill from traces. Slow loop rewrites the procedure that does the rewriting. | Held-out gain over the raw model: OfficeQA **+23.54**, SealQA **+16.09**, ALFWorld **+1.92**. |
| **SkillHone** ([2606.08671](https://arxiv.org/abs/2606.08671)) | Keeps the diagnosis, the rejected revisions, and the evidence, not only the latest skill. | **+15.8** on GAIA and **+3.2** on WebWalkerQA-EN versus a commercial deep-research agent. **+18.8** average across seven internal tool settings. |
| **MUSE-Autoskill** ([2605.27366](https://arxiv.org/abs/2605.27366)) | Create, store, retrieve, attach per-skill memory, evaluate, refine. | On SkillsBench, self-made skills beat human-authored skills on the covered subset: **85.24% vs 81.17%**. Transferred onto Hermes: **51.90%**. Beats Hermes, Codex, and Claude Code on the reported SkillsBench and SkillLearnBench settings. |
| **CoEvoSkills** ([2604.01687](https://arxiv.org/abs/2604.01687)) | A generator and a surrogate verifier co-evolve. The verifier never sees the hidden tests. | Highest pass rate of five baselines on SkillsBench, on both Claude Code and Codex. Absolute pass rate is not in the card. |
| **SkillComposer** ([2606.06079](https://arxiv.org/abs/2606.06079)) | Three learned operations: create, improve, merge. A 4B composer is trained by rejection sampling. | A 4B composer lifts a 27B executor by up to **+4.5** on τ²-Bench / AppWorld and **+3.4** on LiveCodeBench v6. |
| **SkillSmith** ([2606.01314](https://arxiv.org/abs/2606.01314)) | Trace-estimated interaction graph decides which skills complement or conflict. Skills and tools are edited together. Anti-patterns are stored. | WildClawBench and two other benches, five Qwen3.5 sizes. Gains grow as more skills fire together. No absolute number in the card. |
| **AutoSkill** ([2603.01145](https://arxiv.org/abs/2603.01145)), **SkillClaw** ([2604.08377](https://arxiv.org/abs/2604.08377)), **Memento-Skills** ([2603.18743](https://arxiv.org/abs/2603.18743)) | Experience or multi-user traces become SKILL.md. SkillClaw syncs a shared repo. Memento writes skill + tool + tests. | Cards describe the loop and do not record a score. |

## Training-based

The skill is still distilled from traces. Then the policy, or a skill manager, is trained.

| Method | Loop | Benchmark and reported score |
|---|---|---|
| **SkillRL** ([2602.08234](https://arxiv.org/abs/2602.08234)) | Teacher distills success and failure into a hierarchical SkillBank. The bank co-evolves with the policy under GRPO. | ALFWorld, WebShop, and seven search tasks. More than **+15.3%** over strong baselines. |
| **D2Skill** ([2603.28716](https://arxiv.org/abs/2603.28716)) | Task-level and step-level skills. Utility is the gap between a paired rollout with and without the skill. | ALFWorld, WebShop, search QA. Substantial over skill-free baselines. No number in the card. |
| **SkillMaster** ([2605.08693](https://arxiv.org/abs/2605.08693)) | Skill edits are trained on their counterfactual effect on probe tasks. | **+8.8%** success on ALFWorld and **+9.3%** on WebShop over prior SOTA. |
| **CODESKILL** ([2605.25430](https://arxiv.org/abs/2605.25430)) | A learned manager extracts and prunes coding skills from trajectories. Reward mixes a rubric with execution. | EnvBench, SWE-bench Verified, Terminal-Bench 2. Average pass rate **+9.69** over no skill, **+4.01** over the best prompt or memory baseline. |
| **ARISE** ([2603.16060](https://arxiv.org/abs/2603.16060)) | After a correct math trace, a manager summarizes it into a tiered library and retrieves it before the next problem. | Seven math benchmarks. Beats GRPO-family and memory baselines, especially out of distribution. No number in the card. |
| **Skill1** ([2605.06130](https://arxiv.org/abs/2605.06130)) | One RL objective covers select, use, and distill. | ALFWorld and WebShop. Beats prior skill and RL baselines. No number in the card. |

## What the numbers say

Trace2Skill is the batch miner: many logs in, one portable skill directory out. The +57.65 WikiTableQuestions transfer is its headline.

SkillOpt is the method that then beat Trace2Skill on every cell they both entered, by refusing any edit that does not raise a held-out score.

ClawTrace is the warning on the same pipeline. Keeping every step that appeared in a successful trace lowers quality. The useful patch is the one that deletes the expensive step.

## RRSI — regularized harness search

Not a trace-to-skill distiller. Google Cloud AI Research, with UNC, Stanford, and Washington University in St. Louis. Announced around 22 Sep 2026. No `research.google` or `blog.google` post. Official surfaces:

- Project page: [regularized-rsi.com](https://regularized-rsi.com/)
- Paper: [arXiv:2609.24972](https://arxiv.org/abs/2609.24972)
- Code: [github.com/google-research/rrsi](https://github.com/google-research/rrsi)

The model stays frozen. What evolves is the harness: prompts, control flow, tools, skills, memory, and subagents. Unregularized harness search memorizes the suite it is scored on. RRSI leaves every component editable and regularizes the search.

- **Proposal.** An annealed edit budget shrinks how many changes one candidate can bundle. The proposer also reads the history of rejected and accepted edits, so it does not retest a mechanism that already failed.
- **Selection.** A critic rejects diffs that name the evolve-set tasks, entities, or answers before they are scored. A noise floor, measured by re-running the starting harness, blocks candidates that only win by evaluation noise. A cost gate drops edits that are too small, too expensive, or no longer useful. The cost gate is ridge-style shrinkage on policy tokens.

The policy is Claude Opus 4.8. The harness is evolved on one suite per domain, then run unchanged everywhere else. Baselines are Meta-Harness, AHE, TTHE, and HarnessX, all from the same starting harness.

| Split | What they report |
|---|---|
| Evolve set | Up to **+14.1** overall. Per suite: Terminal-Bench 2.1 **+6.0**, EngDesign **+4.9**, Harvey LAB **+1.1**. RRSI’s evolve-set gain is the smallest of the evolved harnesses. |
| Held out | Improves every held-out split. SWE-bench Verified **+1.8**. Harvey LAB in-distribution holdout **+2.3**. JobBench, GDPval, and APEX-Agents **+3.5 to +4.7** (7.2% to 13.1%). Frontier-Eng **+4.3** medal points (24.3% relative). Out-of-distribution average **43.6 vs 39.7** for the starting harness. |
| Cost | About **30% fewer policy tokens** than unregularized evolution. |

Meta-Harness wins the evolve split and adds only 0.9 out of distribution. AHE and TTHE finish below the harness they started from.
