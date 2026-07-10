#!/usr/bin/env node
/** Generate agent-skill-architecture-survey-matrix.zh.md from English source */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = path.join(ROOT, 'notes/synthesis/agent-skill-architecture-survey-matrix.md');
const out = path.join(ROOT, 'notes/synthesis/agent-skill-architecture-survey-matrix.zh.md');
const dimZh = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'config/matrix-dimension-zh.json'), 'utf8')
);
const cellCfg = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'config/matrix-cell-prose-zh.json'), 'utf8')
);

const exactCells = cellCfg.exact || {};
const phraseCells = [...(cellCfg.phrases || [])].sort((a, b) => b[0].length - a[0].length);

/** snake_case, camelCase, dotted paths, file.ext — never translate */
const CODE_TOKEN =
  /\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b|\b[A-Za-z]+\.[A-Za-z0-9]+\b|\b[A-Z][A-Za-z0-9]+\b/g;

function isProsePhrase(phrase) {
  if (!phrase || phrase.includes('`')) return false;
  if (/[_/\\→]/.test(phrase)) return false;
  if (CODE_TOKEN.test(phrase)) return false;
  CODE_TOKEN.lastIndex = 0;
  return true;
}

function mappingIsSafe(en, zh) {
  if (!en || !zh || en === zh) return false;
  if (zh.includes('_') && !en.includes('_')) return false;
  // reject if zh adds CJK immediately after an English identifier
  if (/[A-Za-z][A-Za-z0-9_.-]*[\u4e00-\u9fff]/.test(zh) && !/[\u4e00-\u9fff][A-Za-z]/.test(en)) {
    return false;
  }
  if (/[\u4e00-\u9fff][A-Za-z]/.test(zh) && !/[\u4e00-\u9fff][A-Za-z]/.test(en)) {
    return false;
  }
  return true;
}

/** Protect `code` and identifier tokens while translating prose */
function protectTokens(cell, fn) {
  const slots = [];
  const slot = (m) => {
    slots.push(m);
    return `__PH${slots.length - 1}__`;
  };
  let s = cell.replace(/`[^`]*`/g, slot);
  s = s.replace(CODE_TOKEN, slot);
  s = fn(s);
  return s.replace(/__PH(\d+)__/g, (_, i) => slots[+i] ?? _);
}

function translateCell(cell) {
  const raw = cell.trim();
  if (!raw || raw === '·' || raw === '—') return raw;
  if (/^\*\*[\d./]+\*\*$/.test(raw) || /^\d+\/\d+$/.test(raw) || /^[★◐❌]$/.test(raw)) return raw;

  if (exactCells[raw] !== undefined) {
    const v = exactCells[raw];
    if (mappingIsSafe(raw, v)) return v;
    return raw;
  }

  const out = protectTokens(raw, (s) => {
    let t = s;
    for (const [en, zh] of phraseCells) {
      if (!isProsePhrase(en) || !mappingIsSafe(en, zh)) continue;
      if (t.includes(en)) t = t.split(en).join(zh);
    }
    return t;
  });

  if (!mappingIsSafe(raw, out)) return raw;
  // reject partial phrase translations that leave English terms + Chinese fragments
  if (
    out !== raw &&
    !/[\u4e00-\u9fff]/.test(raw) &&
    /[A-Za-z]/.test(out) &&
    /[\u4e00-\u9fff]/.test(out) &&
    exactCells[raw] === undefined
  ) {
    return raw;
  }
  return out === raw ? raw : out;
}

function translateMatrixTables(text) {
  return text
    .split('\n')
    .map((line) => {
      if (!line.startsWith('|')) return line;
      if (line.includes(':---')) return line;
      const parts = line.split('|');
      if (parts.length < 10) return line;

      const head = parts[1]?.trim() || '';
      const isHeader = /^(Dimension|维度)$/.test(head);
      const isDimRow = /^\*\*[^*]+\*\*( \([^)]+\))?$/.test(head);
      if (isHeader) return line;
      if (!isDimRow) return line;

      for (let i = 2; i < parts.length - 1; i += 1) {
        const cell = parts[i].trim();
        parts[i] = ` ${translateCell(cell)} `;
      }
      return parts.join('|');
    })
    .join('\n');
}

let body = fs.readFileSync(src, 'utf8');
const fmEnd = body.indexOf('---', 3);
body = body.slice(fmEnd + 3).trimStart();

const pairs = [
  ['# Agent Skill Architecture Survey Matrix', '# Agent Skill 架构调研矩阵'],
  ['> **Not a feature checklist**', '> **不是功能清单**'],
  ['a comparative architecture instrument', 'Agent Harness + Skill 系统设计的**横向架构调研工具**'],
  ['**Evidence**:', '**证据**：'],
  ['**Projects**:', '**项目**：'],
  ['## Seven mega-categories', '## 七大类'],
  ['| # | Mega-category | Sections | Dimensions |', '| # | 大类 | 章节 | 维度数 |'],
  ['| I | **Skill Data Model** | §1 | 14 |', '| I | **Skill 数据模型** | §1 | 14 |'],
  ['| II | **Runtime** | §2–§7 Discovery, Exposure, Recommendation, Runtime, Offload, Usage | 68 |', '| II | **运行时** | §2–§7 发现、暴露、推荐、运行时、卸载、使用 | 68 |'],
  ['| III | **Lifecycle** | §8 | 13 |', '| III | **生命周期** | §8 | 13 |'],
  ['| IV | **Evolution & Quality** | §9–§10 | 29 |', '| IV | **进化与质量** | §9–§10 | 29 |'],
  ['| V | **Governance** | §11 | 12 |', '| V | **治理** | §11 | 12 |'],
  ['| VI | **Agent Integration** | §12–§14 Relationship, Multi-Agent, Memory | 28 |', '| VI | **Agent 集成** | §12–§14 关系、多 Agent、记忆 | 28 |'],
  ['| VII | **RL Readiness** | §15 | 11 |', '| VII | **RL 就绪度** | §15 | 11 |'],
  ['| | **Total** | **15 sections** | **165** |', '| | **合计** | **15 节** | **165** |'],
  ['### Cell legend', '### 单元格图例'],
  ['| Symbol | Meaning |', '| 符号 | 含义 |'],
  ['| ★ | Strong / first-class / production path |', '| ★ | 强 / 一等公民 / 生产路径 |'],
  ['| ◐ | Partial / experimental / weak |', '| ◐ | 部分 / 实验 / 弱 |'],
  ['| · | Not present / out of scope |', '| · | 无 / 不在范围 |'],
  ['| ❌ | Known gap or documented risk |', '| ❌ | 已知缺口或文档化风险 |'],
  ['| — | N/A for this framework type |', '| — | 该框架类型不适用 |'],
  ['Short text supplements symbols where architecture differs materially.', '架构差异显著处用短文本补充符号。'],
  ['### Per-repo deliverable format', '### 各仓库交付格式'],
  ['Each framework should eventually produce a **12-section survey report**', '每个框架应产出 **12 节调研报告**'],
  ['Worked examples:', '完整示例：'],
  ['# I. Skill Data Model', '# I. Skill 数据模型'],
  ['## §1 — Skill representation & packaging', '## §1 — Skill 表示与打包'],
  ['| Dimension |', '| 维度 |'],
  ['# II. Runtime', '# II. 运行时'],
  ['## §2 — Skill Discovery', '## §2 — Skill 发现'],
  ['## §3 — Skill Exposure', '## §3 — Skill 暴露'],
  ['## §4 — Skill Recommendation', '## §4 — Skill 推荐'],
  ['## §5 — Skill Runtime', '## §5 — Skill 运行时'],
  ['## §6 — Skill Offload', '## §6 — Skill 卸载'],
  ['## §7 — Skill Usage', '## §7 — Skill 使用'],
  ['# III. Lifecycle', '# III. 生命周期'],
  ['## §8 — Skill lifecycle stages', '## §8 — Skill 生命周期阶段'],
  ['# IV. Evolution & Quality', '# IV. 进化与质量'],
  ['## §9 — Skill Evolution', '## §9 — Skill 进化'],
  ['## §10 — Skill Quality', '## §10 — Skill 质量'],
  ['# V. Governance', '# V. 治理'],
  ['## §11 — Skill Governance', '## §11 — Skill 治理'],
  ['# VI. Agent Integration', '# VI. Agent 集成'],
  ['## §12 — Skill Relationship', '## §12 — Skill 关系'],
  ['## §13 — Multi-Agent Skill', '## §13 — 多 Agent Skill'],
  ['## §14 — Memory Integration', '## §14 — 记忆集成'],
  ['# VII. RL Readiness', '# VII. RL 就绪度'],
  ['## §15 — RL Readiness (SkillRL / Claw-R1)', '## §15 — RL 就绪度（SkillRL / Claw-R1）'],
  ['# Aggregate scores (1–10)', '# 综合评分（1–10）'],
  ['| Framework | Data Model | Runtime | Lifecycle | Evolution | Governance | Agent Integ. | RL Ready | **Overall** |', '| 框架 | 数据模型 | 运行时 | 生命周期 | 进化 | 治理 | Agent 集成 | RL 就绪 | **总分** |'],
  ['*Scores are qualitative rollup from matrix coverage; not benchmark metrics.*', '*评分为矩阵覆盖度的定性汇总，非 benchmark 指标。*'],
  ['# TaiChu synthesis (from matrix)', '# TaiChu 综合结论（来自矩阵）'],
  ['## Borrow (by mega-category)', '## 可借鉴（按大类）'],
  ['| Category | Primary sources |', '| 类别 | 主要来源 |'],
  ['| Data Model |', '| 数据模型 |'],
  ['| Runtime |', '| 运行时 |'],
  ['| Lifecycle |', '| 生命周期 |'],
  ['| Evolution |', '| 进化 |'],
  ['| Governance |', '| 治理 |'],
  ['| Agent Integration |', '| Agent 集成 |'],
  ['| RL Readiness |', '| RL 就绪度 |'],
  ['## Do NOT borrow', '## 不应借鉴'],
  ['## Related documents', '## 相关文档'],
  ['| Doc | Role |', '| 文档 | 作用 |'],
  ['| Prior 9-stage condensed matrix |', '| 9 阶段精简矩阵 |'],
  ['| Per-repo L3 narrative evidence |', '| 各仓库 L3 叙事证据 |'],
  ['| 20-dimension repo cards |', '| 20 维仓库卡片 |'],
  ['## Changelog', '## 变更记录'],
  ['| Date | Change |', '| 日期 | 变更 |'],
  ['| Initial 165-dimension Agent Skill Architecture Survey Matrix |', '| 首版 165 维 Agent Skill 架构调研矩阵 |'],
  ['Codex layout + OpenClaw multi-root + ZeroClaw trust metadata', 'Codex layout + OpenClaw multi-root + ZeroClaw trust metadata'],
  ['Codex progressive disclosure + OpenSquilla RRF + Claude incremental listing + **runs_on keep**', 'Codex progressive disclosure + OpenSquilla RRF + Claude incremental listing + **runs_on keep**'],
  ['OpenSquilla proposals + GenericAgent miner + Hermes review (with read-before-write)', 'OpenSquilla proposals + GenericAgent miner + Hermes review (with read-before-write)'],
  ['ZeroClaw audit + OpenSquilla gates + Codex Guardian', 'ZeroClaw audit + OpenSquilla gates + Codex Guardian'],
  ['Claude subagent bundles + OpenSquilla MetaSkill + OpenClaw skillFilter', 'Claude subagent bundles + OpenSquilla MetaSkill + OpenClaw skillFilter'],
  ['OpenClaw trajectory + Claw-R1 step schema on interaction_log', 'OpenClaw trajectory + Claw-R1 step schema on interaction_log'],
  ['Hermes direct production patch without gate', 'Hermes direct production patch without gate'],
  ['OpenClaw marketplace trust model wholesale', 'OpenClaw marketplace trust model wholesale'],
  ['GenericAgent ungated crystallize', 'GenericAgent ungated crystallize'],
  ['ZeroClaw assumption that CI = security boundary', 'ZeroClaw assumption that CI = security boundary'],
];

for (const [from, to] of pairs) {
  body = body.split(from).join(to);
}

/** First column dimension labels: **中文** (English) */
body = body.replace(/\| \*\*([^*|]+)\*\* \|/g, (match, label) => {
  const en = label.trim();
  const zh = dimZh[en];
  if (!zh) return match;
  if (zh === en) return match;
  return `| **${zh}** (${en}) |`;
});

/** Repo columns: prose-only cell translation; code names stay English */
body = translateMatrixTables(body);

const frontmatter = `---
id: T007-zh
title: Agent Skill 架构调研矩阵
date: 2026-07-08
tags: [survey-matrix, architecture, zh]
status: active
lang: zh
related: [T007]
summary: 7 大类、15 节、165 维 × 8 框架 — Agent Harness + Skill 架构调研
---

`;

fs.writeFileSync(out, frontmatter + body);

const dimApplied = (body.match(/\*\*[^*]+\*\* \(/g) || []).length;

let total = 0;
let translated = 0;
const enBody = fs.readFileSync(src, 'utf8').slice(fmEnd + 3);
for (const line of enBody.split('\n')) {
  if (!line.startsWith('| **')) continue;
  if (line.includes(':---')) continue;
  const parts = line.split('|').map((s) => s.trim()).filter(Boolean);
  if (parts.length < 9) continue;
  for (const cell of parts.slice(1)) {
    total += 1;
    const zhCell = translateCell(cell);
    if (zhCell !== cell) translated += 1;
  }
}

console.log(
  `Wrote ${out} (${dimApplied} row labels; ${translated}/${total} prose cells, ${((100 * translated) / total).toFixed(1)}%)`
);
