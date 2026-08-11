# Skill 自进化

> 来源：`skill自进化.pptx`（共 24 页；有效内容约第 1–11 页，第 12–24 页为占位）  
> Web：[`html/deck/skill-self-evolution-roadmap.html`](../../html/deck/skill-self-evolution-roadmap.html)  
> 对齐路线图 SSOT：TaiChu `docs/architecture/skill-self-evolution-roadmap.md`（v1.5）

---

## 1. 整体 Roadmap

TaiChu 在多端路由（`runs_on` + remote delegation）与 A-system per-turn 列表不 bust prompt cache 上已有差异化；短板在 compaction 保护、SubAgent 技能传递、自进化门禁、PC 默认可用 harness。

本路线图以**完全解耦的 Skill OS 侧车（`skill-os`）**为内核，对用户与主 Agent 的演进接口按三层递进。

### Milestones

| 里程碑 | 主题 | 要点 |
| --- | --- | --- |
| **M1 · Online** | 业界追平：框架适配 / 工具实现 / Benchmark（在线） | 一等 `skill_evo` Tool + `invoked_skills` + compact reinject；仅 turn 内同步路径；写 L1 staging |
| **M2 · Async** | Benchmark / 异步路径 | DecisionLog sidecar、session_end miner、Claude improvement、Hermes bg-review；不阻塞 `prompt()` |
| **M3 · Online 暴露增强** | — | `filter_skills` + staging 格式 + 共现只观察 |
| **M4 · Offline** | 离线挖掘 | cron/Dream、全量 OfflineGate / Survey UI、install-wide 只读挖掘、外部 scout |
| **M5 · 版本管理与晋升** | 进化与门禁 | semver / `skill-versions/` / active version SSOT；staging → L2 |
| **M6 · 上线验证** | 异步 / 离线验证 | gates/tests/smoke 沙箱、SkillsBench 晋升门禁、发布前 A/B |
| **M7 · 多用户进化** | — | per-user/persona 分区；Heavy 多租户；可选共享 catalog（显式 ACL） |
| **M8 · 端云 / 端端共进化** | — | skilldiff + OfflineGate；Cloud↔Device / Device↔Device |
| **M9 · 多 Agent 编排（可选）** | — | Meta-DAG |

**演进与门禁主线：** 版本管理 → 上线验证（异步、离线）→ 引入多 Agent 进行进化 → 端云 / 端端进化 → 多用户进化。

---

## 2. 第一阶段（M1 · 业界对齐）

议题列表（skill自进化-M1-业界对齐）：

1. **TaiChu 接口和平台适配** — metadata、skill 格式/协议、输入适配、调用点、skill 使用跟踪。
2. **进化时机策略** — 同步 / 异步 / 离线；每 N 轮；LLM judge。
3. **工具实现** — create / patch / delete。
4. **Benchmark** — skill bench。
5. **上线验证** — 格式、测试、benchmark。

### M1 硬需求：用户创建 vs 反馈自优化

**结论：** 三者都支持「用户请求创建 Skill」；只有 Hermes 原生支持「根据反馈自动直接改造/创建**已生效** Skill」。OpenClaw 自动化默认=待审提案；Claude Code 官方未见反馈闭环自动改写。

| 场景 | TaiChu M1 | 对标 |
|------|-----------|------|
| 1 · 用户 query 创建 | **必须** `skill_evo` → L1 staging；禁直写 canonical | OpenClaw/Hermes/Claude 均可创建 |
| 2 · 反馈自动优化 | **不在 M1**；M2 仍只写 staging/pending（**OpenClaw 安全边界为默认**） | Hermes 直写生效 = 非默认，须 ≥M5 OfflineGate + flag |

---

## 3. 相关工作与应用要点

### 3.1 MUSE-Autoskill

统一生命周期 Creation / Memory / Management / Evaluation / Refinement；Master Agent（ReAct）编排 Skill Bank / Creator / Executor / Evaluator / Refiner。

**应用：** 第一阶段参考 skill 格式 + tests；长期参考 resources、离线后台优化、与记忆结合；蓝图对齐反复更正/合并/遗忘 → **M6**。

### 3.2 SkillSmith

一次编译边界、反复受控调用；Compile Time 分类 + Runtime Workflow/Dispatcher/Reference。至少覆盖离线阶段。

### 3.3 SkillHone

版本管理、评测/回归、决策历史跟踪。**版本管理应作为 roadmap 第一性原则** → **M5**。

### 3.4 SkillCat

Contrastive Causal Extraction · Assessment-Augmented Evolution · Topology-aware Task Execution。跨会话离线、评测/打分。

### 3.5 SkillClaw

多用户轨迹聚合 → `Evolve-Skill.md` 驱动 → 验证回灌。适合多用户集体进化 → **M7**。

### 3.6 CoEvoSkill 及其他

Generator ↔ Surrogate Verifier 共进化；FederatedSkill / MememtoSkill 等。

---

## 4. 占位页说明

第 12–24 页目前仅有标题碎片，无实质正文，待后续补充。
