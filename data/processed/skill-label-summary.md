# Skill label coverage

Labeled 19716 skills from `public_skills` using `config/skill-label-system.yaml`.
Assignments: `data/processed/skill-labels.jsonl`.

Every skill has one provenance, one form, and at least one domain.
Job labels are optional and a skill may have several.

## Form

| Label | Skills |
|---|---:|
| technique | 11473 |
| pattern | 6910 |
| reference | 1333 |

## Job

Skills with no job label: 6508.

| Labels on one skill | Skills |
|---:|---:|
| 0 | 6508 |
| 1 | 6935 |
| 2 | 4745 |
| 3 | 1242 |
| 4 | 267 |
| 5 | 18 |
| 6 | 1 |

| Job | Skills |
|---|---:|
| skill-authoring | 64 |
| discovery | 1203 |
| audience | 58 |
| output-format | 909 |
| repo-understanding | 2454 |
| verification | 5243 |
| reflection | 3078 |
| methodology | 8306 |

## Domain

Unspecified: 1083 (5.5%).

| Labels on one skill | Skills |
|---:|---:|
| 1 | 4873 |
| 2 | 3857 |
| 3 | 4127 |
| 4 | 3083 |
| 5 | 1841 |
| 6 | 1080 |
| 7 | 583 |
| 8 | 180 |
| 9 | 58 |
| 10 | 31 |
| 11 | 1 |
| 12 | 2 |

| Domain | Skills |
|---|---:|
| life-science | 722 |
| legal | 1847 |
| finance | 1660 |
| commerce | 421 |
| games | 126 |
| education | 319 |
| media | 1348 |
| documents | 597 |
| design | 2671 |
| frontend | 2334 |
| mobile | 529 |
| databases | 1754 |
| data | 4250 |
| security | 4789 |
| testing | 3235 |
| cloud-devops | 2555 |
| git | 1040 |
| marketing | 1447 |
| writing | 2267 |
| research | 1430 |
| ai | 7890 |
| productivity | 1183 |
| business | 1043 |
| backend | 1699 |
| systems | 1157 |
| software | 9977 |
| unspecified | 1083 |

## Unspecified sample

- `00-andruia-consultant` — Arquitecto de Soluciones Principal y Consultor Tecnológico de Andru.ia. Diagnostica y traza la hoja de ruta óptima para proyectos de IA en e
- `10-andruia-skill-smith` — Ingeniero de Sistemas de Andru.ia. Diseña, redacta y despliega nuevas habilidades (skills) dentro del repositorio siguiendo el Estándar de D
- `20-andruia-niche-intelligence` — Estratega de Inteligencia de Dominio de Andru.ia. Analiza el nicho específico de un proyecto para inyectar conocimientos, regulaciones y est
- `aas-review-stack` — Review AAS stack manifests, preview plans and selection evidence in Workbench without applying changes.
- `accint-commitments` — Triage acc's open promises and close them with honest real-world verdicts via acc_act(runtime="outcome").
- `accint-frames` — Drain acc's deliberation queue — open/waiting brain_frames checkpointed by headless runs — via acc_act(runtime="continue").
- `accint-solve` — Route a goal through acc's scored-memory loop via acc_act(runtime="solve"); deliberate any returned brain_frame and submit via continue.
- `algolia-search` — Expert patterns for Algolia search implementation, indexing
- `ask-questions-if-underspecified` — Clarify requirements before implementing. Use when serious doubts arise.
- `cc-skill-continuous-learning` — Turn a completed debugging session or repeated user correction into a small, evidence-backed procedure. Use for explicit requests to capture
- `check-identity-pack` — Run an AFP 100-point or AUSTRAC safe-harbour identity check over a set of documents, and report exactly what's missing. Use when the user as
- `chrome-extension-developer` — Expert in building Chrome Extensions using Manifest V3. Covers background scripts, service workers, content scripts, and cross-context commu
- `competitive-landscape` — Comprehensive frameworks for analyzing competition, identifying differentiation opportunities, and developing winning market positioning str
- `concise-planning` — Use when a user asks for a plan for a coding task, to generate a clear, actionable, and atomic checklist.
- `conductor-manage` — Manage track lifecycle: archive, restore, delete, rename, and cleanup
- `create-issue-gate` — Use when starting a new implementation task and an issue must be created with strict acceptance criteria gating before execution.
- `crossframe` — Use when the user explicitly invokes CrossFrame or 跨尺度结构诊断 for Chinese-canonical structural diagnosis of complex relationships, organization
- `crossframe-casebook` — Use when CrossFrame Suite routes explicit Chinese casebook work: turning materials into reusable cases, anonymized entries, mechanisms, and 
- `crossframe-critical` — Use only when the user explicitly names crossframe-critical for a Chinese structural critique dossier, article plan, or long-form critical e
- `crossframe-essay` — Use when explicit CrossFrame work needs a Chinese critical insight essay, commentary, concept essay, public piece, or structure-to-article d
- `crossframe-org` — Use when CrossFrame Suite routes explicit Chinese analysis of teams, projects, organizations, responsibility chains, feedback write-back, re
- `crossframe-review` — Use when explicit CrossFrame output needs review for reasoning fidelity, evidence boundaries, source anchors, concept drift, article collaps
- `ddd-context-mapping` — Map relationships between bounded contexts and define integration contracts using DDD context mapping patterns.
- `debugging-strategies` — Transform debugging from frustrating guesswork into systematic problem-solving with proven strategies, powerful tools, and methodical approa
- `discord-bot-architect` — Specialized skill for building production-ready Discord bots.
- `distributed-tracing` — Implement distributed tracing with Jaeger and Tempo for request flow visibility across microservices.
- `doc2math` — Convert narrative technical documents into grounded Mathematical Problem Specifications with variables, constraints, objectives, and uncerta
- `draft-my-comments` — Write a LinkedIn comment that adds something the post did not have, not agreement. Use when someone asks what to comment, wants to engage wi
- `elon-musk` — Agente que simula Elon Musk com profundidade psicologica e comunicacional de alta fidelidade. Ativado para: \"fale como Elon\", \"simule Elo
- `emergency-card` — 生成紧急情况下快速访问的医疗信息摘要卡片。当用户需要旅行、就诊准备、紧急情况或询问"紧急信息"、"医疗卡片"、"急救信息"时使用此技能。提取关键信息（过敏、用药、急症、植入物），支持多格式输出（JSON、文本、二维码），用于急救或快速就医。
