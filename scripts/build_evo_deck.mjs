#!/usr/bin/env node
/** Build skill-evolution deck: 2 slides/repo, SVG, quotes, expandable code/stack detail */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cfg = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/skill-evolution-slides.json'), 'utf8'));
const cfgEn = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/skill-evolution-slides-en.json'), 'utf8'));
const walkthroughs = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/skill-evolution-walkthroughs.json'), 'utf8'));
const quotesByRepo = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/skill-evolution-quotes.json'), 'utf8'));
const codeByRepo = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/skill-evolution-code-detail.json'), 'utf8'));
const glossary = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/skill-evolution-glossary.json'), 'utf8'));
const userIsolation = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'config/skill-evolution-user-isolation.json'), 'utf8')
);
const svgDir = path.join(ROOT, 'html/deck/svg');
fs.mkdirSync(svgDir, { recursive: true });

const total = 1 + cfg.repos.length;
const detailBlocks = [];

/** turn index → "stackId:start-end" frame slice */
const TURN_STACK_LINKS = {
  opensquilla: ['online-turn:2-6', 'online-turn:6', 'evolve-path:0-2', 'evolve-path:2-5', 'evolve-path:5-6'],
  'hermes-agent': ['main-turn:0-4', 'review-path:0-1', 'review-path:1-4', 'main-turn:2-3'],
  openclaw: ['gateway-run:0-4', 'workshop-path:0-2', 'workshop-path:2-5', 'gateway-run:0-2'],
  'claude-code-rev': ['three-channel:0-3', 'three-channel:3-4', 'three-channel:4-5', 'compact-path:0-3', 'three-channel:0-1'],
  codex: ['authoring:0-2', 'runtime-turn:0-4', 'runtime-turn:3-4', 'runtime-turn:4-5'],
  taichu: ['online-today:0-3', 'online-today:3-4', 'online-today:4-5', 'planned-p0-p2:0-3'],
  zeroclaw: ['install-load:0-2', 'install-load:2-3', 'runtime:0-1', 'runtime:2-3'],
  genericagent: ['task-run:0-3', 'task-run:3-4', 'task-run:4-5', 'task-run:0-2', 'reflect-cron:0-2'],
};

const MODE_LABELS = {
  online: 'Online 在线',
  async: 'Async 异步',
  offline: 'Offline 离线',
  human: 'Human 人工',
  cron: 'Cron 定时',
  none: 'None 无',
};

const ISO_LEVEL = { strong: '★', partial: '◐', none: '·' };

function isoLevelClass(level) {
  if (level === 'strong') return 'iso-strong';
  if (level === 'partial') return 'iso-partial';
  return 'iso-none';
}

function isoCell(level) {
  const sym = ISO_LEVEL[level] || '·';
  return `<span class="evo-iso-level ${isoLevelClass(level)}" title="${esc(level)}">${sym}</span>`;
}

function isoEvidencePointer(item) {
  if (!item?.file) return '';
  const loc = item.lines && item.lines !== '—' ? `${item.file}:${item.lines}` : item.file;
  const note = item.note ? ` — ${item.note}` : '';
  return `<li><code class="evo-iso-ptr">${esc(loc)}</code>${esc(note)}</li>`;
}

function isoEvidenceList(items, { limit = 0 } = {}) {
  if (!items?.length) return '';
  const slice = limit > 0 ? items.slice(0, limit) : items;
  const more = limit > 0 && items.length > limit ? `<li class="evo-iso-more">+${items.length - limit} more</li>` : '';
  return `<ul class="evo-iso-evidence">${slice.map(isoEvidencePointer).join('')}${more}</ul>`;
}

function isoEvidenceTitle(items) {
  if (!items?.length) return '';
  const first = items[0];
  const loc = first.lines && first.lines !== '—' ? `${first.file}:${first.lines}` : first.file;
  return first.note ? `${loc} — ${first.note}` : loc;
}

function userIsolationBadges(repoId) {
  const row = userIsolation.repos?.[repoId];
  if (!row) return '';
  const parts = [];
  if (row.cross_user === 'strong' || row.cross_user === 'partial') {
    parts.push(
      `<span class="evo-iso-badge evo-iso-cross ${isoLevelClass(row.cross_user)}" title="${esc(isoEvidenceTitle(row.cross_user_evidence) || row.cross_user_detail || '')}">${bi('Cross-user evolve', '跨用户进化')} ${ISO_LEVEL[row.cross_user]}</span>`
    );
  }
  if (row.user_isolation === 'strong' || row.user_isolation === 'partial') {
    parts.push(
      `<span class="evo-iso-badge evo-iso-private ${isoLevelClass(row.user_isolation)}" title="${esc(isoEvidenceTitle(row.isolation_evidence) || row.isolation_detail || '')}">${bi('Evolution isolation', '进化隔离')} ${ISO_LEVEL[row.user_isolation]}</span>`
    );
  }
  if (row.user_accounts && row.user_accounts !== 'none') {
    parts.push(
      `<span class="evo-iso-badge evo-iso-account ${isoLevelClass(row.user_accounts === 'yes' ? 'strong' : 'partial')}" title="${esc(row.user_accounts)}">${bi('User accounts', '用户账户')} ${ISO_LEVEL[row.user_accounts === 'yes' ? 'strong' : 'partial']}</span>`
    );
  }
  if (row.edge_evolution === 'strong' || row.edge_evolution === 'partial') {
    parts.push(
      `<span class="evo-iso-badge evo-iso-edge iso-strong" title="${esc(isoEvidenceTitle(row.edge_evidence) || row.edge_detail || '')}">${bi('Edge-only evolve', '端侧进化')} ★</span>`
    );
  }
  if (row.cloud_cross_device === 'none' || !row.cloud_cross_device) {
    parts.push(
      `<span class="evo-iso-badge evo-iso-cloud-none iso-none" title="No cloud cross-device evolution sync / 无端云跨设备进化同步">${bi('No cloud×device', '无端云跨设备')} ·</span>`
    );
  }
  if (!parts.length) return '';
  return `<div class="evo-iso-badges">${parts.join('')}</div>`;
}

function userIsolationPanel(repoId) {
  const row = userIsolation.repos?.[repoId];
  if (!row) return '';
  const acct = row.user_accounts
    ? `<tr><th>${bi('User accounts', '用户账户')}</th><td>${isoCell(row.user_accounts === 'yes' ? 'strong' : row.user_accounts === 'partial' ? 'partial' : 'none')} ${esc(row.user_accounts)} — ${bi('auth / user_id on evolution path', '进化链路 auth / user_id')}</td></tr>`
    : '';
  const crossEv = row.cross_user_evidence?.length
    ? `<tr><th>${bi('Cross-user ptr', '跨用户证据')}</th><td>${isoEvidenceList(row.cross_user_evidence)}</td></tr>`
    : '';
  const isoEv = row.isolation_evidence?.length
    ? `<tr><th>${bi('Isolation ptr', '隔离证据')}</th><td>${isoEvidenceList(row.isolation_evidence)}</td></tr>`
    : '';
  const edgeEv = row.edge_evidence?.length
    ? `<tr><th>${bi('Edge ptr', '端侧证据')}</th><td>${isoEvidenceList(row.edge_evidence)}</td></tr>`
    : '';
  return `<div class="evo-iso-panel">
    <div class="evo-iso-panel-head">${bi('Evolution privacy & deployment (§13)', '进化隐私与部署（§13）')}</div>
    <p class="evo-iso-panel-def">${bi('Isolation = other users’ history NOT used for shared skills. All 8 repos: evolution writes are edge-side — no cloud cross-device evolution sync.', '隔离 = 不用其他用户历史生成共享 skill。8 仓均为端侧进化写入 — 无端云跨设备进化同步。')}</p>
    <table class="dense evo-iso-table">
      <tbody>
        ${acct}
        <tr><th>${bi('Edge evolution', '端侧进化')}</th><td>${isoCell(row.edge_evolution || 'strong')} ${esc(row.edge_detail || '—')}</td></tr>
        <tr><th>${bi('Cloud×device', '端云跨设备')}</th><td>${isoCell(row.cloud_cross_device || 'none')} ${bi('No cloud miner / cross-device skill patch sync', '无云端 miner / 跨设备 skill 补丁同步')}</td></tr>
        <tr><th>${bi('Cross-user evolve', '跨用户进化')}</th><td>${isoCell(row.cross_user)} ${esc(row.cross_user_detail || '—')}</td></tr>
        <tr><th>${bi('Evolution isolation', '进化隔离')}</th><td>${isoCell(row.user_isolation)} ${esc(row.isolation_detail || '—')}</td></tr>
        ${edgeEv}
        ${crossEv}
        ${isoEv}
        <tr><th>${bi('Matrix §13', '矩阵 §13')}</th><td class="mono-fn">${esc(row.matrix_ref || '—')}</td></tr>
      </tbody>
    </table>
  </div>`;
}

function isoMatrixRows({ compact = false } = {}) {
  return cfg.repos
    .map((r) => {
      const row = userIsolation.repos?.[r.id] || {};
      if (compact) {
        return `<tr>
        <td><strong>${esc(r.id)}</strong></td>
        <td class="evo-iso-matrix-cell">${isoCell(row.edge_evolution || 'strong')}</td>
        <td class="evo-iso-matrix-cell">${isoCell(row.cloud_cross_device || 'none')}</td>
        <td class="evo-iso-matrix-cell">${isoCell(row.user_accounts === 'yes' ? 'strong' : row.user_accounts === 'partial' ? 'partial' : 'none')}</td>
        <td class="evo-iso-matrix-cell">${isoCell(row.cross_user || 'none')}</td>
        <td class="evo-iso-matrix-cell">${isoCell(row.user_isolation || 'none')}</td>
        <td class="evo-iso-matrix-summary">${esc(row.edge_detail || '—')}</td>
      </tr>`;
      }
      return `<tr>
        <td><strong>${esc(r.id)}</strong></td>
        <td class="evo-iso-matrix-cell">${isoCell(row.edge_evolution || 'strong')}</td>
        <td class="evo-iso-matrix-cell">${isoCell(row.cloud_cross_device || 'none')}</td>
        <td class="evo-iso-matrix-cell">${isoCell(row.user_accounts === 'yes' ? 'strong' : row.user_accounts === 'partial' ? 'partial' : 'none')}</td>
        <td class="evo-iso-matrix-cell">${isoCell(row.cross_user || 'none')}</td>
        <td class="evo-iso-matrix-cell">${isoCell(row.user_isolation || 'none')}</td>
        <td class="evo-iso-matrix-detail">${esc(row.edge_detail || '—')}${isoEvidenceList(row.edge_evidence)}</td>
        <td class="evo-iso-matrix-detail">${esc(row.cross_user_detail || '—')}${isoEvidenceList(row.cross_user_evidence)}</td>
        <td class="evo-iso-matrix-detail">${esc(row.isolation_detail || '—')}${isoEvidenceList(row.isolation_evidence)}</td>
      </tr>`;
    })
    .join('');
}

function isoMatrixTableHtml({ compact = false, tableClass = 'evo-iso-matrix' } = {}) {
  return `<table class="dense ${tableClass}${compact ? ' evo-iso-matrix-compact' : ''}">
      <thead><tr>
        <th>Repo</th>
        <th>${bi('Edge', '端侧')}</th>
        <th>${bi('Cloud×dev', '端云')}</th>
        <th>${bi('Acct', '账户')}</th>
        <th>${bi('Cross-user', '跨用户')}</th>
        <th>${bi('Isolation', '隔离')}</th>
        <th>${compact ? bi('Edge evolution path', '端侧进化路径') : bi('Edge / cross-user / isolation + evidence', '端侧 / 跨用户 / 隔离 + 证据')}</th>
        ${compact ? '' : `<th>${bi('Cross-user source', '跨用户来源')}</th><th>${bi('Evolution isolation', '进化隔离')}</th>`}
      </tr></thead>
      <tbody>${isoMatrixRows({ compact })}</tbody>
    </table>`;
}

function introEdgeBanner() {
  return `<div class="evo-edge-banner panel accent-survey evo-panel">
    <strong>${bi('8/8 edge-side skill self-evolution', '8/8 端侧 skill 自进化')}</strong>
    <span class="evo-edge-banner-sep">·</span>
    ${bi('All propose / patch / accept writes on local FS (~/. or workspace/)', 'propose / patch / accept 均在本地 FS（~/. 或 workspace/）')}
    <span class="evo-edge-banner-sep">·</span>
    <strong>${bi('No cloud cross-device evolution sync', '无端云跨设备进化同步')}</strong>
    <span class="evo-edge-banner-note">${bi('(TaiChu cloud catalog = consume-only; runs_on = execute delegation, not evolve sync)', '（TaiChu 云目录 = 仅消费；runs_on = 执行委托，非进化同步）')}</span>
  </div>`;
}

function registerIntroIsolationModal() {
  const id = detailId('intro', 'isolation', 'full');
  const body = `<div class="evo-iso-modal-inner">
    ${introEdgeBanner()}
    <p class="evo-iso-legend">${bi('Edge = local device evolution. Cloud×device = auto skill patch synced across devices from cloud — · for all 8.', '端侧 = 本设备进化。端云跨设备 = 云端自动 patch 并跨设备同步 skill — 8 仓均为 ·。')}</p>
    <p class="evo-iso-legend">${bi('Cross-user evolve = pooled interaction history → shared skills. Evolution isolation = other users’ history NOT used for shared skill generation.', '跨用户进化 = 聚合交互历史 → 共享 skill。进化隔离 = 不用其他用户历史生成共享 skill。')}</p>
    ${isoMatrixTableHtml({ compact: false, tableClass: 'evo-iso-matrix evo-iso-matrix-full' })}
  </div>`;
  registerDetail(id, 'Evolution privacy — full evidence', body);
  return id;
}

function introIsolationTeaser(modalId) {
  return `<div class="panel accent-survey evo-panel evo-iso-matrix-panel">
    <div class="evo-iso-matrix-head">
      <h3>${bi('Evolution privacy & deployment (§13)', '进化隐私与部署（§13）')}</h3>
      <button type="button" class="evo-wt-open-btn evo-iso-open-btn" data-detail-target="${modalId}" data-detail-kind="walkthrough">
        <span data-lang-only="en">Full evidence ↗</span><span data-lang-only="zh" hidden>完整证据 ↗</span>
      </button>
    </div>
    ${introEdgeBanner()}
    <p class="evo-iso-legend">${bi('Edge ★ = local evolution · Cloud×device · = none · code pointers in popup', '端侧 ★ = 本地进化 · 端云 · = 无 · 代码指针见弹窗')}</p>
    ${isoMatrixTableHtml({ compact: true })}
  </div>`;
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Inline bilingual: toggled by i18n.js via [data-lang-only] */
function bi(en, zh) {
  if (!en && zh) return `<span data-lang-only="zh">${esc(zh)}</span>`;
  if (!zh && en) return `<span data-lang-only="en">${esc(en)}</span>`;
  if (en === zh) return esc(en);
  return `<span data-lang-only="en">${esc(en)}</span><span data-lang-only="zh" hidden>${esc(zh)}</span>`;
}

function repoEn(id) {
  return cfgEn.repos?.[id] || {};
}

const PANEL_EN = {
  w5: '① 5W',
  meth: '② Methodology',
  comp: '③ Components',
  walk: '⑤ Walkthrough — cross-turn example',
  code: '④ Code & call stacks',
  explain: '⑥ Auto Explain',
};
const PANEL_ZH = {
  w5: '① 5W',
  meth: '② 方法论',
  comp: '③ 组件',
  walk: '⑤ Walkthrough — 跨 Turn 示例',
  code: '④ 代码 & 调用栈',
  explain: '⑥ Auto Explain',
};

function panelLabel(key) {
  return bi(PANEL_EN[key] || key, PANEL_ZH[key] || key);
}

function l3Href(id) {
  return `../site/notes/synthesis/survey-reports/${id}.html`;
}

function detailId(repoId, kind, key) {
  return `detail-${repoId}-${kind}-${key}`;
}

function registerDetail(id, title, html) {
  detailBlocks.push(`<div id="${id}" class="evo-detail-content" data-detail-title="${esc(title)}">${html}</div>`);
}

function snippetDetailBlock(repoId, snip) {
  const id = detailId(repoId, 'snippet', snip.id);
  const body = `<p class="evo-detail-meta"><code>${esc(snip.file)}</code> · L${esc(snip.lines)} · ${esc(snip.summary)}</p>
    <pre class="evo-detail-code lang-${esc(snip.lang)}">${esc(snip.code)}</pre>`;
  registerDetail(id, `${snip.title}`, body);
  return id;
}

function frameDetailBlock(repoId, stackId, frame, idx) {
  const id = detailId(repoId, 'frame', `${stackId}-${idx}`);
  const snip = frame.snippet_id
    ? codeByRepo[repoId]?.snippets?.find((s) => s.id === frame.snippet_id)
    : null;
  let body = `<p class="evo-detail-meta"><code>${esc(frame.file)}</code></p>
    <p>${esc(frame.note)}</p>`;
  if (snip) {
    body += `<p class="evo-detail-related">Related: <button type="button" class="evo-link-btn" data-detail-target="${detailId(repoId, 'snippet', snip.id)}">${esc(snip.title)}</button></p>
      <pre class="evo-detail-code lang-${esc(snip.lang)}">${esc(snip.code)}</pre>`;
  } else {
    body += `<pre class="evo-detail-code">${esc(frame.call)}</pre>`;
  }
  registerDetail(id, frame.call, body);
  return id;
}

function stackDetailBlock(repoId, stack) {
  const id = detailId(repoId, 'stack', stack.id);
  const frames = stack.frames
    .map((f, i) => {
      const fid = frameDetailBlock(repoId, stack.id, f, i);
      const mode = f.mode || 'online';
      return `<li class="evo-stack-frame mode-${esc(mode)}">
        <button type="button" class="evo-stack-frame-btn" data-detail-target="${fid}">
          <span class="evo-frame-n">${i + 1}</span>
          <span class="evo-frame-call">${esc(f.call)}</span>
          <span class="mode-badge mode-${esc(mode)}">${esc((MODE_LABELS[mode] || mode).split(' ')[0])}</span>
        </button>
        <span class="evo-frame-file">${esc(f.file)}</span>
      </li>`;
    })
    .join('');
  registerDetail(
    id,
    stack.title,
    `<ol class="evo-stack-full">${frames}</ol><p class="evo-detail-hint">Click any frame above for code detail.</p>`
  );
  return id;
}

function parseSlice(spec) {
  const [stackId, range] = spec.split(':');
  const [start, end] = range.split('-').map(Number);
  return { stackId, start, end: end ?? start };
}

function stackPreviewHtml(repoId, spec, codeDetail) {
  if (!spec || !codeDetail) return '';
  const { stackId, start, end } = parseSlice(spec);
  const stack = codeDetail.stacks?.find((s) => s.id === stackId);
  if (!stack) return '';
  const slice = stack.frames.slice(start, end + 1);
  const stackFullId = detailId(repoId, 'stack', stackId);
  const items = slice
    .map((f, i) => {
      const globalIdx = start + i;
      const fid = detailId(repoId, 'frame', `${stackId}-${globalIdx}`);
      frameDetailBlock(repoId, stackId, f, globalIdx);
      return `<li class="evo-stack-mini mode-${esc(f.mode || 'online')}">
        <button type="button" class="evo-stack-mini-btn" data-detail-target="${fid}">${esc(f.call)}</button>
      </li>`;
    })
    .join('');
  return `<div class="evo-turn-stack">
    <div class="evo-turn-stack-head">
      <span>Call trace</span>
      <button type="button" class="evo-expand-btn" data-detail-target="${stackFullId}">Full stack ↗</button>
    </div>
    <ol class="evo-stack-mini-list">${items}</ol>
  </div>`;
}

function w5Table(w, wEn) {
  const labels = cfgEn.labels || {};
  const rows = [
    [bi(`${labels.why || 'Why'} 为何`, '为何'), wEn?.why || w.why, w.why],
    [bi(`${labels.what || 'What'} 做什么`, '做什么'), wEn?.what || w.what, w.what],
    [bi(`${labels.who || 'Who'} 谁`, '谁'), wEn?.who || w.who, w.who],
    [bi(`${labels.where || 'Where'} 在哪`, '在哪'), wEn?.where || w.where, w.where],
    [bi(`${labels.when || 'When'} 何时`, '何时'), wEn?.when || w.when, w.when],
    [bi(`${labels.how || 'How'} 如何`, '如何'), wEn?.how || w.how, w.how],
  ];
  return `<table class="dense w5-table"><tbody>${rows
    .map(([k, enVal, zhVal]) => `<tr><th>${k}</th><td>${bi(enVal, zhVal)}</td></tr>`)
    .join('')}</tbody></table>`;
}

function listItems(arr, arrEn) {
  const en = arrEn || arr;
  return `<ul class="compact-list">${arr
    .map((x, i) => `<li>${bi(en[i] || x, x)}</li>`)
    .join('')}</ul>`;
}

/** Collect glossary terms for intro or a repo */
function collectGlossaryItems(repoId) {
  const shared = glossary._shared || {};
  const repoTerms = glossary[repoId] || {};
  const items = [];
  if (repoId === 'intro') {
    if (shared.async_vs_post_turn) items.push({ key: 'async_vs_post_turn', term: shared.async_vs_post_turn, open: true });
    if (shared.decision_log) items.push({ key: 'decision_log', term: shared.decision_log, open: false });
    return items;
  }
  if (repoId === 'opensquilla') {
    if (repoTerms.gates_json) items.push({ key: 'gates_json', term: repoTerms.gates_json, open: true });
    if (shared.decision_log) items.push({ key: 'decision_log', term: shared.decision_log, open: false });
    if (shared.async_vs_post_turn) items.push({ key: 'async_vs_post_turn', term: shared.async_vs_post_turn, open: false });
  } else if (repoId === 'hermes-agent') {
    if (repoTerms.skill_nudge_example) items.push({ key: 'skill_nudge_example', term: repoTerms.skill_nudge_example, open: true });
    if (repoTerms.spawn_background_review) items.push({ key: 'spawn_background_review', term: repoTerms.spawn_background_review, open: false });
    if (repoTerms.skill_manage_races) items.push({ key: 'skill_manage_races', term: repoTerms.skill_manage_races, open: false });
    if (shared.async_vs_post_turn) items.push({ key: 'async_vs_post_turn', term: shared.async_vs_post_turn, open: false });
  } else if (repoId === 'genericagent') {
    if (repoTerms.long_term_update) items.push({ key: 'long_term_update', term: repoTerms.long_term_update, open: true });
  } else if (repoTerms && Object.keys(repoTerms).length) {
    for (const [key, term] of Object.entries(repoTerms)) {
      if (term?.html) items.push({ key, term, open: false });
    }
  }
  return items;
}

/** Auto-explain glossary: shared + per-repo terms as <details> (open = visible by default) */
function glossaryTermDetails(termKey, term, { open = false, repoId = 'shared' } = {}) {
  if (!term?.html) return '';
  const modalId = detailId(repoId, 'glossary-term', termKey);
  registerDetail(modalId, term.title, `<div class="evo-glossary-full">${term.html}</div>`);
  const openAttr = open ? ' open' : '';
  return `<details class="evo-glossary-item"${openAttr}>
    <summary>
      <span class="evo-glossary-title">${esc(term.title)}</span>
      <button type="button" class="evo-expand-btn evo-expand-sm evo-glossary-expand" data-detail-target="${modalId}">Expand ↗</button>
    </summary>
    <div class="evo-glossary-body">${term.html}</div>
  </details>`;
}

function registerGlossaryModal(repoId, title) {
  const items = collectGlossaryItems(repoId);
  if (!items.length) return null;
  const id = detailId(repoId, 'glossary', 'full');
  const body = `<div class="evo-glossary-modal-inner">${items
    .map((it, i) => glossaryTermDetails(it.key, it.term, { open: i === 0 || it.open, repoId }))
    .join('')}</div>`;
  registerDetail(id, title, body);
  return id;
}

function glossaryTeaser(repoId, glossaryModalId, { heading, hint = '' } = {}) {
  const items = collectGlossaryItems(repoId);
  if (!glossaryModalId || !items.length) return '';
  const preview = items
    .map((it) => {
      const t = it.term.title || '';
      const dash = t.indexOf('—');
      return dash > 0 ? t.slice(0, dash).trim() : t.slice(0, 36);
    })
    .slice(0, 3)
    .join(' · ');
  const h = heading || panelLabel('explain');
  return `<div class="panel accent-survey evo-panel evo-glossary-teaser evo-ov-glossary">
    <h3>${h}</h3>
    <p class="evo-wt-teaser-text">${esc(preview)}${items.length > 3 ? ' …' : ''}</p>
    <p class="evo-wt-teaser-sub">${items.length} terms${hint ? ` · ${esc(hint)}` : ''}</p>
    <button type="button" class="evo-wt-open-btn evo-glossary-open-btn" data-detail-target="${glossaryModalId}" data-detail-kind="glossary">
      <span data-i18n="deck.evo.open_explain">打开 Auto Explain ↗</span> <span class="evo-wt-open-hint" data-lang-only="zh">（弹窗内滚动）</span><span class="evo-wt-open-hint" data-lang-only="en" hidden>(scroll in popup)</span>
    </button>
  </div>`;
}

function introGlossaryTeaser(glossaryModalId) {
  return glossaryTeaser('intro', glossaryModalId, {
    heading: bi('Auto Explain — glossary', 'Auto Explain — 术语速查'),
    hint: 'Post-turn / Async · decision_log',
  });
}

function componentsTable(r, wt, repoId, codeDetail) {
  const detail = wt?.components_detail;
  if (!detail?.length) return listItems(r.components);
  return `<table class="dense evo-comp-table"><thead><tr><th>Path</th><th>Role</th><th>Entry</th><th></th></tr></thead><tbody>${detail
    .map((c) => {
      const snip = codeDetail?.snippets?.find((s) => c.path.includes(s.file.split('/').pop()?.split('.')[0] || '___'));
      const snipMatch =
        codeDetail?.snippets?.find((s) => c.path.startsWith(s.file) || s.file.endsWith(c.path.split('/').pop())) ||
        snip;
      let btn = '';
      if (snipMatch) {
        const sid = snippetDetailBlock(repoId, snipMatch);
        btn = `<button type="button" class="evo-expand-btn evo-expand-sm" data-detail-target="${sid}">Code</button>`;
      }
      return `<tr>
        <td class="mono-path">${esc(c.path)}</td>
        <td>${esc(c.role)}</td>
        <td class="mono-fn">${esc(c.fn)}</td>
        <td>${btn}</td>
      </tr>`;
    })
    .join('')}</tbody></table>`;
}

function lifecycleBlock(lc) {
  if (!lc) return '';
  return `<div class="evo-lifecycle">
    <div class="evo-lifecycle-head">
      <span class="evo-lifecycle-title">${bi('Lifecycle', '生命周期')}</span>
      <span class="evo-lifecycle-score">${esc(lc.score || '—')}</span>
    </div>
    ${lc.stages ? `<div class="evo-lifecycle-stages">${esc(lc.stages)}</div>` : ''}
    ${lc.note ? `<div class="evo-lifecycle-note">${esc(lc.note)}</div>` : ''}
  </div>`;
}

function timelineBar(timeline) {
  if (!timeline?.length) return '';
  return `<div class="evo-timeline">
    <span class="evo-timeline-label">${bi('Timeline', '时间线')}</span>
    <div class="evo-timeline-track">${timeline
      .map(
        (t) => `<span class="evo-timeline-node mode-${esc(t.mode)}">
        <span class="evo-timeline-mode">${esc(MODE_LABELS[t.mode] || t.mode)}</span>
        <span class="evo-timeline-phase">${esc(t.phase)}</span>
      </span>`
      )
      .join('<span class="evo-timeline-arrow">→</span>')}</div>
  </div>`;
}

function snippetsAccordion(repoId, codeDetail) {
  if (!codeDetail?.snippets?.length) return '';
  return `<div class="evo-snippets">${codeDetail.snippets
    .map((snip, i) => {
      const sid = snippetDetailBlock(repoId, snip);
      const open = i === 0 ? ' open' : '';
      return `<details class="evo-snippet-details"${open}>
        <summary>
          <span class="evo-snippet-title">${esc(snip.title)}</span>
          <code class="evo-snippet-file">${esc(snip.file)}</code>
          <button type="button" class="evo-expand-btn evo-expand-sm" data-detail-target="${sid}">Expand ↗</button>
        </summary>
        <p class="evo-snippet-summary">${esc(snip.summary)}</p>
        <pre class="mono evo-snippet-preview lang-${esc(snip.lang)}">${esc(snip.code.split('\n').slice(0, 6).join('\n'))}${snip.code.split('\n').length > 6 ? '\n…' : ''}</pre>
      </details>`;
    })
    .join('')}</div>`;
}

function stacksPanel(repoId, codeDetail) {
  if (!codeDetail?.stacks?.length) return '';
  return `<div class="evo-stacks-panel">${codeDetail.stacks
    .map((stack) => {
      const fullId = stackDetailBlock(repoId, stack);
      const preview = stack.frames
        .slice(0, 4)
        .map((f, i) => {
          const fid = detailId(repoId, 'frame', `${stack.id}-${i}`);
          frameDetailBlock(repoId, stack.id, f, i);
          return `<li><button type="button" class="evo-stack-mini-btn" data-detail-target="${fid}">${esc(f.call)}</button></li>`;
        })
        .join('');
      const more =
        stack.frames.length > 4
          ? `<li><button type="button" class="evo-expand-btn" data-detail-target="${fullId}">+${stack.frames.length - 4} more frames ↗</button></li>`
          : '';
      return `<details class="evo-stack-details" open>
        <summary>
          <strong>${esc(stack.title)}</strong>
          <button type="button" class="evo-expand-btn evo-expand-sm" data-detail-target="${fullId}">Full trace ↗</button>
        </summary>
        <ol class="evo-stack-mini-list">${preview}${more}</ol>
      </details>`;
    })
    .join('')}</div>`;
}

function codeDetailPanel(r, codeDetail, repoId) {
  if (!codeDetail) {
    return `<div class="evo-code-row">
      <pre class="mono evo-code">${esc(r.code)}</pre>
      <pre class="mono evo-stack">${esc(r.stack)}</pre>
    </div>`;
  }
  return `<div class="evo-code-detail-grid">
    <div class="evo-code-detail-col">
      <div class="evo-stack-label">Code snippets <span class="evo-hint">(click Expand or ▶)</span></div>
      ${snippetsAccordion(repoId, codeDetail)}
    </div>
    <div class="evo-code-detail-col">
      <div class="evo-stack-label">Call stacks / traces <span class="evo-hint">(click frame → popup)</span></div>
      ${stacksPanel(repoId, codeDetail)}
    </div>
  </div>`;
}

function turnQuote(quote) {
  if (!quote) return '';
  return `<details class="evo-quote-details">
    <summary class="evo-quote-summary">${esc(quote.source || 'Source quote')}</summary>
    <pre class="mono evo-quote-code lang-${esc(quote.lang || 'text')}">${esc(quote.text)}</pre>
  </details>`;
}

function turnCard(t, quote, repoId, turnIdx, codeDetail) {
  const mode = t.mode || 'none';
  const modeLabel = MODE_LABELS[mode] || mode;
  const rows = [
    t.scope && ['Scope', t.scope],
    t.user && t.user !== '—' && ['User', t.user],
    t.system && t.system !== '—' && ['System', t.system],
    t.agent && t.agent !== '—' && ['Agent', t.agent],
    t.tools?.length && ['Tools', t.tools.join(' · ')],
    t.artifacts?.length && ['Artifacts', t.artifacts.join(' · ')],
    t.note && ['Ref', t.note],
  ].filter(Boolean);

  const stackLink = TURN_STACK_LINKS[repoId]?.[turnIdx];
  const stackHtml = stackPreviewHtml(repoId, stackLink, codeDetail);

  return `<div class="evo-turn-card mode-${esc(mode)}">
    <div class="evo-turn-head">
      <span class="evo-turn-label">${esc(t.label)}</span>
      <span class="mode-badge mode-${esc(mode)}">${esc(modeLabel.split(' ')[0])}</span>
    </div>
    <dl class="evo-turn-dl">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    ${turnQuote(quote || t.quote)}
    ${stackHtml}
  </div>`;
}

function tryBuildSvg(repoId, mermaidSrc) {
  const svgFile = path.join(svgDir, `${repoId}.svg`);
  const mmdFile = path.join(svgDir, `${repoId}.mmd`);
  fs.writeFileSync(mmdFile, mermaidSrc);
  if (fs.existsSync(svgFile) && fs.statSync(svgFile).mtimeMs >= fs.statSync(mmdFile).mtimeMs) {
    return `svg/${repoId}.svg`;
  }
  try {
    execSync(`npx --yes @mermaid-js/mermaid-cli@11 -i "${mmdFile}" -o "${svgFile}" -b transparent`, {
      cwd: ROOT,
      stdio: 'pipe',
      timeout: 120000,
    });
    if (fs.existsSync(svgFile)) return `svg/${repoId}.svg`;
  } catch {
    /* client fallback */
  }
  return null;
}

function diagramBlock(repoId, wt) {
  if (!wt?.mermaid) return '';
  const svgRel = tryBuildSvg(repoId, wt.mermaid);
  if (svgRel) {
    return `<div class="evo-diagram-hero evo-svg-hero"><img class="evo-flow-svg" src="${svgRel}" alt="${esc(repoId)} flow" loading="lazy"></div>`;
  }
  return `<div class="evo-diagram-hero evo-mermaid-hero"><pre class="mermaid evo-mermaid-lg">${wt.mermaid}</pre></div>`;
}

function registerWalkthroughModal(repoId, r, wt, codeDetail) {
  const id = detailId(repoId, 'walkthrough', 'full');
  const repoQuotes = quotesByRepo[repoId] || [];
  const turns = wt?.turns?.length
    ? `<div class="evo-turn-grid evo-turn-grid-2col evo-turn-grid-modal">${wt.turns
        .map((t, i) => turnCard(t, t.quote || repoQuotes[i], repoId, i, codeDetail))
        .join('')}</div>`
    : '';
  const body = `<div class="evo-wt-modal-inner">
    ${lifecycleBlock(r.lifecycle)}
    ${timelineBar(r.timeline)}
    ${wt?.cross_session ? `<div class="evo-cross-session"><strong>Cross-turn / session:</strong> ${esc(wt.cross_session)}</div>` : ''}
    ${diagramBlock(repoId, wt)}
    ${turns}
  </div>`;
  registerDetail(id, `${r.headline} — 工作流 Walkthrough`, body);
  return id;
}

function walkthroughTeaser(r, wt, wtModalId) {
  const n = wt?.turns?.length || 0;
  const phases = r.timeline?.slice(0, 4).map((t) => t.phase).join(' → ') || '';
  return `<div class="panel accent-survey evo-panel evo-wt-teaser evo-ov-wt">
    <h3>${panelLabel('walk')}</h3>
    <p class="evo-wt-teaser-text">${esc(phases)}${r.timeline?.length > 4 ? ' …' : ''}</p>
    <p class="evo-wt-teaser-sub">${n} turns · SVG · source quotes · call trace</p>
    <button type="button" class="evo-wt-open-btn" data-detail-target="${wtModalId}" data-detail-kind="walkthrough">
      <span data-i18n="deck.evo.open_wt">打开 Walkthrough ↗</span> <span class="evo-wt-open-hint" data-lang-only="zh">（弹窗内滚动，不影响 → 切页）</span><span class="evo-wt-open-hint" data-lang-only="en" hidden>(popup scroll; → still advances slides)</span>
    </button>
  </div>`;
}
function repoOverviewSlide(r, slideNum, wt, codeDetail, wtModalId, glossaryModalId) {
  const theme = r.theme || 'survey';
  const reportHref = l3Href(r.id);
  const num = String(slideNum).padStart(2, '0');
  const hasGlossary = !!glossaryModalId;
  const glossaryClass = hasGlossary ? ' evo-has-glossary' : '';
  const enR = repoEn(r.id);
  const glossaryHeaderBtn = glossaryModalId
    ? `<button type="button" class="evo-wt-open-btn evo-wt-open-header evo-glossary-header-btn" data-detail-target="${glossaryModalId}" data-detail-kind="glossary"><span data-i18n="deck.evo.explain_header">Explain ↗</span></button>`
    : '';
  return `
    <section class="slide theme-${theme} evo-slide evo-slide-overview${glossaryClass}" id="slide-${slideNum}">
      <div class="slide-inner">
        <header class="slide-header">
          <div>
            <div class="kicker">#${r.rank} · Score ${r.score} · L3</div>
            <h1>${bi(enR.headline || r.headline, r.headline)}</h1>
            <p class="subtitle">${bi(enR.tagline || r.tagline, r.tagline)}</p>
            ${userIsolationBadges(r.id)}
          </div>
          <div class="slide-header-actions">
            <button type="button" class="evo-wt-open-btn evo-wt-open-header" data-detail-target="${wtModalId}" data-detail-kind="walkthrough"><span data-i18n="deck.evo.wt_header">Walkthrough ↗</span></button>
            ${glossaryHeaderBtn}
            <a class="l3-report-btn" href="${reportHref}" target="_blank" rel="noopener"><span data-i18n="deck.evo.l3_report">📎 L3 Report</span></a>
            <span class="slide-num">${num} / ${String(total).padStart(2, '0')}</span>
          </div>
        </header>
        <div class="slide-body evo-grid evo-grid-overview">
          <div class="panel accent-survey evo-panel evo-panel-scroll evo-ov-w5">
            <h3>${panelLabel('w5')}</h3>
            ${w5Table(r.five_w, enR.five_w)}
          </div>
          <div class="panel accent-survey evo-panel evo-panel-scroll evo-ov-meth">
            <h3>${panelLabel('meth')}</h3>
            ${listItems(r.methodologies, enR.methodologies)}
            ${lifecycleBlock(r.lifecycle)}
            ${userIsolationPanel(r.id)}
          </div>
          <div class="panel accent-survey evo-panel evo-panel-scroll evo-ov-comp">
            <h3>${panelLabel('comp')} <span class="evo-hint">· Code → popup</span></h3>
            ${componentsTable(r, wt, r.id, codeDetail)}
          </div>
          ${walkthroughTeaser(r, wt, wtModalId)}
          ${glossaryTeaser(r.id, glossaryModalId)}
          <div class="panel accent-survey evo-panel evo-code-panel evo-ov-code evo-panel-scroll">
            <h3>${panelLabel('code')}</h3>
            ${codeDetailPanel(r, codeDetail, r.id)}
          </div>
        </div>
        <footer class="slide-footer">
          <a class="l3-footer-link" href="${reportHref}" target="_blank" rel="noopener">L3 · ${r.id}</a>
          <span><kbd>→</kbd> <span data-i18n="deck.evo.footer.next">next repo · Walkthrough / Explain popups scroll inside</span></span>
        </footer>
      </div>
    </section>`;
}

let slideNum = 2;
const introGlossaryModalId = registerGlossaryModal('intro', 'Auto Explain — 术语速查');
const introIsolationModalId = registerIntroIsolationModal();
const repoSlides = cfg.repos
  .map((r) => {
    const wt = walkthroughs[r.id] || {};
    const cd = codeByRepo[r.id] || null;
    const wtModalId = registerWalkthroughModal(r.id, r, wt, cd);
    const glossaryModalId = registerGlossaryModal(r.id, `${r.headline} — Auto Explain`);
    const slide = repoOverviewSlide(r, slideNum, wt, cd, wtModalId, glossaryModalId);
    slideNum += 1;
    return slide;
  })
  .join('\n');

const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Skill Self-Evolution — 8 Repos · Skill 自进化 — 八仓对照</title>
  <link rel="stylesheet" href="css/deck.css">
</head>
<body data-i18n-page="deck" data-content-lang="bi">
  <div class="lang-switch-deck" data-lang-switch aria-label="Language"></div>
  <a class="hub-link" href="index.html" data-i18n="deck.hub">← Deck Hub</a>
  <div class="deck">

    <section class="slide theme-survey evo-slide evo-slide-intro" id="slide-1">
      <div class="slide-inner">
        <header class="slide-header">
          <div>
            <div class="kicker">Agent Skill Architecture · L3</div>
            <h1>${bi(cfgEn.title || cfg.title, cfg.title)}</h1>
            <p class="subtitle" data-i18n="deck.evo.intro.subtitle">9 slides · Walkthrough + Auto Explain popups</p>
          </div>
          <div class="slide-header-actions">
            <button type="button" class="evo-wt-open-btn evo-wt-open-header" data-detail-target="${introIsolationModalId}" data-detail-kind="walkthrough"><span data-lang-only="en">Evolution privacy ↗</span><span data-lang-only="zh" hidden>进化隐私 ↗</span></button>
            ${introGlossaryModalId ? `<button type="button" class="evo-wt-open-btn evo-wt-open-header" data-detail-target="${introGlossaryModalId}" data-detail-kind="glossary"><span data-i18n="deck.evo.explain_header">Explain ↗</span></button>` : ''}
            <span class="slide-num">01 / ${String(total).padStart(2, '0')}</span>
          </div>
        </header>
        <div class="slide-body">
          <div class="stat-row">
            <div class="stat purple"><div class="val">8</div><div class="lbl" data-i18n="deck.evo.stat.repos">Repos</div></div>
            <div class="stat green"><div class="val">9</div><div class="lbl" data-i18n="deck.evo.stat.slides">Slides</div></div>
            <div class="stat blue"><div class="val">↗</div><div class="lbl" data-i18n="deck.evo.stat.wt">Walkthrough popup</div></div>
            <div class="stat orange"><div class="val">?</div><div class="lbl" data-i18n="deck.evo.stat.explain">Auto Explain popup</div></div>
          </div>
          <div class="eli5">
            <span data-i18n="deck.evo.intro.nav">Navigate: → / ← switch repos. Walkthrough and Auto Explain scroll inside popups.</span>
          </div>
          ${introIsolationTeaser(introIsolationModalId)}
          ${introGlossaryTeaser(introGlossaryModalId)}
        </div>
        <footer class="slide-footer"><span>code-detail.json + walkthroughs + quotes</span><span><kbd>→</kbd> OpenSquilla</span></footer>
      </div>
    </section>

    ${repoSlides}

  </div>

  <div id="evo-detail-store" hidden aria-hidden="true">${detailBlocks.join('\n')}</div>

  <nav class="deck-nav" aria-label="Slide navigation">
    <button type="button" id="nav-prev" data-i18n="deck.nav.prev">← Prev</button>
    <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
    <span class="progress-label" id="progress-label">1/${total}</span>
    <button type="button" id="nav-next" data-i18n="deck.nav.next">Next →</button>
  </nav>

  <div class="modal-overlay" id="evidence-modal" role="dialog" aria-modal="true">
    <div class="modal modal-lg" id="modal-panel">
      <button type="button" class="close-btn" onclick="closeModal()" aria-label="Close">&times;</button>
      <h2 id="modal-title">Detail</h2>
      <div id="modal-body"></div>
    </div>
  </div>
  <script src="../js/i18n.js"></script>
  <script src="js/deck.js"></script>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
    mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' });
    window.__renderMermaid = async () => {
      const slide = document.querySelectorAll('.slide')[window.__deckCurrent ?? 0];
      if (!slide) return;
      const nodes = slide.querySelectorAll('pre.mermaid:not([data-rendered])');
      if (!nodes.length) return;
      try {
        await mermaid.run({ nodes: [...nodes] });
        nodes.forEach((n) => n.setAttribute('data-rendered', '1'));
      } catch (e) { console.warn('mermaid', e); }
    };
    window.addEventListener('deck-slide-change', () => window.__renderMermaid?.());
    window.__renderMermaid();
  </script>
</body>
</html>`;

fs.writeFileSync(path.join(ROOT, 'html/deck/skill-evolution-repos.html'), html);
const svgCount = fs.readdirSync(svgDir).filter((f) => f.endsWith('.svg')).length;
console.log(`Wrote deck (${total} slides, ${svgCount} SVG, ${detailBlocks.length} detail blocks)`);
