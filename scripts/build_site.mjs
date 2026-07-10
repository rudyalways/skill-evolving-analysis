#!/usr/bin/env node
/**
 * Build static HTML from workspace markdown → html/site/ (+ html/site/zh/)
 * Run: npm install --prefix scripts && node scripts/build_site.mjs
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { marked } from './node_modules/marked/lib/marked.esm.js';
import {
  ROOT,
  detectContentLang,
  hasDedicatedZh,
  hasZhPage,
  auditCoverage,
  zhMdPath,
} from './i18n_detect.mjs';
import {
  isSurveyReport,
  preprocessSurveyReport,
  postprocessSurveyHtml,
} from './survey_report_enhance.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(ROOT, 'html', 'site');

/** @type {{titleKey:string, items:{labelKey?:string, label?:string, md:string}[]}[]} */
const NAV = [
  {
    titleKey: 'nav.compare',
    items: [
      { labelKey: 'nav.matrix165', md: 'notes/synthesis/agent-skill-architecture-survey-matrix.md' },
      { labelKey: 'nav.lifecycle', md: 'notes/synthesis/skill-lifecycle-full-matrix.md' },
      { labelKey: 'nav.web_l3', md: 'notes/synthesis/web-expanded-lifecycle-matrix-merged.md' },
      { labelKey: 'nav.survey20', md: 'notes/synthesis/eight-repo-comprehensive-survey.md' },
      { labelKey: 'nav.per_turn', md: 'notes/synthesis/skill-lifecycle-and-dynamic-loading-survey.md' },
      { labelKey: 'nav.deep_source', md: 'notes/synthesis/eight-repo-deep-source-analysis.md' },
    ],
  },
  {
    titleKey: 'nav.per_repo',
    items: [
      { label: 'OpenSquilla (9.0)', md: 'notes/synthesis/survey-reports/opensquilla.md' },
      { label: 'Hermes (8.1)', md: 'notes/synthesis/survey-reports/hermes-agent.md' },
      { label: 'OpenClaw (8.0)', md: 'notes/synthesis/survey-reports/openclaw.md' },
      { label: 'Claude Rev (7.7)', md: 'notes/synthesis/survey-reports/claude-code-rev.md' },
      { label: 'Codex (7.2)', md: 'notes/synthesis/survey-reports/codex.md' },
      { label: 'TaiChu (5.0)', md: 'notes/synthesis/survey-reports/taichu.md' },
      { label: 'ZeroClaw (5.0)', md: 'notes/synthesis/survey-reports/zeroclaw.md' },
      { label: 'GenericAgent (4.8)', md: 'notes/synthesis/survey-reports/genericagent.md' },
    ],
  },
  {
    titleKey: 'nav.papers',
    items: [
      { label: 'SkillRL', md: 'topics/skill-rl/overview.md' },
      { label: 'Claw-R1', md: 'topics/claw-r1/overview.md' },
      { labelKey: 'nav.comparison', md: 'notes/synthesis/comparison.md' },
      { labelKey: 'nav.pipeline', md: 'notes/synthesis/combined-pipeline.md' },
      { labelKey: 'nav.l3', md: 'notes/synthesis/l3-comprehensive-skill-analysis.md' },
      { labelKey: 'nav.taichu_p0', md: 'notes/synthesis/taichu-p0-skill-compaction-spec.md' },
    ],
  },
];

function collectEnMdFiles() {
  const files = new Set();
  for (const section of NAV) {
    for (const item of section.items) files.add(item.md);
  }
  function walk(dir) {
    const full = path.join(ROOT, dir);
    if (!fs.existsSync(full)) return;
    for (const ent of fs.readdirSync(full, { withFileTypes: true })) {
      const rel = `${dir}/${ent.name}`.replace(/\\/g, '/');
      if (ent.isDirectory()) walk(rel);
      else if (ent.name.endsWith('.md') && !ent.name.endsWith('.zh.md')) files.add(rel);
    }
  }
  walk('notes/synthesis');
  walk('notes/daily');
  walk('topics');
  for (const f of ['INDEX.md', 'README.md', 'STORE.md']) {
    if (fs.existsSync(path.join(ROOT, f))) files.add(f);
  }
  return [...files].sort();
}

function collectZhMdFiles() {
  const files = [];
  function walk(dir) {
    const full = path.join(ROOT, dir);
    if (!fs.existsSync(full)) return;
    for (const ent of fs.readdirSync(full, { withFileTypes: true })) {
      const rel = `${dir}/${ent.name}`.replace(/\\/g, '/');
      if (ent.isDirectory()) walk(rel);
      else if (ent.name.endsWith('.zh.md')) files.push(rel);
    }
  }
  walk('notes/synthesis');
  walk('notes/daily');
  walk('topics');
  return files.sort();
}

function canonicalMd(mdRel) {
  return mdRel.replace(/\.zh\.md$/i, '.md');
}

function mdToHtmlPath(mdRel) {
  return canonicalMd(mdRel).replace(/\.md$/i, '.html');
}

function relSiteUrl(fromCanonical, toCanonical, locale) {
  const toHtml = mdToHtmlPath(toCanonical);
  const fromDir = path.dirname(mdToHtmlPath(fromCanonical));

  if (locale === 'zh' && localHasZhPage(toCanonical)) {
    const rel = path.relative(fromDir, toHtml).replace(/\\/g, '/');
    return rel.startsWith('.') ? rel : `./${rel}`;
  }
  if (locale === 'zh') {
    const depth = fromDir === '.' ? 0 : fromDir.split('/').length;
    const up = '../'.repeat(depth + 1);
    return `${up}${toHtml}`;
  }
  const rel = path.relative(fromDir, toHtml).replace(/\\/g, '/');
  return rel.startsWith('.') ? rel : `./${rel}`;
}

function rewriteLinks(html, fromCanonical, locale) {
  return html.replace(/href="([^"]+\.md)"/g, (_, href) => {
    if (href.startsWith('http') || href.startsWith('#')) return `href="${href}"`;
    const base = path.dirname(fromCanonical);
    const target = path.normalize(path.join(base, href)).replace(/\\/g, '/');
    return `href="${relSiteUrl(fromCanonical, target, locale)}"`;
  });
}

function preprocessI18nBlocks(md) {
  return md.replace(
    /<!--\s*i18n:(en|zh)\s*-->\s*([\s\S]*?)\s*<!--\s*\/i18n:\1\s*-->/g,
    (_, locale, body) => `\n<div class="i18n-content" data-lang="${locale}">\n\n${body.trim()}\n\n</div>\n\n`
  );
}

function mermaidBlocks(html) {
  return html.replace(
    /<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g,
    (_, code) => `<pre class="mermaid">${code.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')}</pre>`
  );
}

function wrapTables(html) {
  return html.replace(/<table>/g, '<div class="table-wrap"><table>').replace(/<\/table>/g, '</table></div>');
}

function buildNav(currentCanonical, locale) {
  let html = '';
  for (const section of NAV) {
    html += `<section class="highlight-section"><h2 data-i18n="${section.titleKey}">${section.titleKey}</h2><ul>`;
    for (const item of section.items) {
      const active = item.md === currentCanonical ? ' class="active"' : '';
      const href = relSiteUrl(currentCanonical, item.md, locale);
      if (item.labelKey) {
        html += `<li><a${active} href="${href}" data-i18n="${item.labelKey}">${item.labelKey}</a></li>`;
      } else {
        html += `<li><a${active} href="${href}">${item.label}</a></li>`;
      }
    }
    html += '</ul></section>';
  }
  html += `<section><h2 data-i18n="nav.more">More</h2><ul>
    <li><a href="/html/docs.html" data-i18n="nav.sitemap">Sitemap</a></li>
    <li><a href="/html/i18n-coverage.html" data-i18n="nav.i18n_coverage">i18n coverage</a></li>
    <li><a href="/html/index.html" data-i18n="nav.dashboard">Dashboard</a></li>
    <li><a href="/html/deck/index.html" data-i18n="nav.decks">Slide decks</a></li>
  </ul></section>`;
  return html;
}

function localHasZhPage(canonical) {
  if (hasDedicatedZh(canonical)) return true;
  if (detectContentLang(canonical) === 'zh') return true;
  if (isSurveyReport(canonical)) return true;
  return false;
}

function alternateLinks(canonical) {
  const enPath = `/html/site/${mdToHtmlPath(canonical)}`;
  const zhPath = `/html/site/zh/${mdToHtmlPath(canonical)}`;
  let links = `<link rel="alternate" hreflang="en" href="${enPath}">`;
  if (localHasZhPage(canonical)) links += `\n  <link rel="alternate" hreflang="zh-Hans" href="${zhPath}">`;
  links += `\n  <link rel="alternate" hreflang="x-default" href="${enPath}">`;
  return links;
}

function pageTemplate({ title, canonical, srcMd, bodyHtml, locale, contentLang, bodyClass = '' }) {
  const nav = buildNav(canonical, locale);
  const depth = canonical.split('/').length - 1;
  const cssPrefix = '../'.repeat(depth + 1 + (locale === 'zh' ? 1 : 0));
  const htmlLang = locale === 'zh' || contentLang === 'zh' ? 'zh-Hans' : 'en';
  const fallback =
    contentLang === 'en'
      ? `<p id="i18n-fallback-notice" class="i18n-notice" hidden data-i18n="content.fallback">content.fallback</p>`
      : locale === 'en' && contentLang === 'zh'
        ? `<p id="i18n-zh-native-notice" class="i18n-notice zh-native" hidden data-i18n="content.zh_native">content.zh_native</p>`
        : '';

  return `<!DOCTYPE html>
<html lang="${htmlLang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)} — Skill-Evolving</title>
  ${alternateLinks(canonical)}
  <link rel="stylesheet" href="${cssPrefix}css/viewer.css">
</head>
<body class="${bodyClass}" data-doc-locale="${locale}" data-content-lang="${contentLang}">
  <div class="viewer-layout">
    <nav>
      <div data-lang-switch class="lang-switch-host"></div>
      <h1 data-i18n="nav.docs">Docs</h1>
      <div class="title" data-i18n="nav.rendered">Rendered HTML</div>
      ${nav}
    </nav>
    <div class="viewer-main">
      <div class="viewer-toolbar">
        <div>
          <h1>${escapeHtml(title)}</h1>
          <div class="path">${escapeHtml(srcMd)}</div>
        </div>
        <a class="btn" href="/html/docs.html" data-i18n="toolbar.sitemap">Sitemap</a>
        <a class="btn primary" href="${relSiteUrl(canonical, 'notes/synthesis/agent-skill-architecture-survey-matrix.md', locale)}" data-i18n="toolbar.matrix">165-dim matrix</a>
      </div>
      ${fallback}
      <article class="md-body">${bodyHtml}</article>
    </div>
  </div>
  <script src="${cssPrefix}js/i18n.js"></script>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
    mermaid.initialize({ startOnLoad: true, theme: 'neutral' });
  </script>
</body>
</html>`;
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function stripFrontmatter(text) {
  if (text.startsWith('---')) {
    const end = text.indexOf('---', 3);
    if (end !== -1) return text.slice(end + 3).trimStart();
  }
  return text;
}

function buildPage(srcMd, locale, contentLangOverride) {
  const src = path.join(ROOT, srcMd);
  if (!fs.existsSync(src)) return null;
  const canonical = canonicalMd(srcMd);
  const raw = fs.readFileSync(src, 'utf8');
  const rawBody = stripFrontmatter(raw);

  let contentLang = contentLangOverride || detectContentLang(srcMd.endsWith('.zh.md') ? canonical : srcMd);
  let content = rawBody;
  let bodyClass = '';

  if (isSurveyReport(canonical)) {
    bodyClass = 'page-compact page-survey-report';
    content = preprocessSurveyReport(rawBody, canonical, locale);
    if (locale === 'zh') contentLang = 'zh';
  }

  content = preprocessI18nBlocks(content);
  let body = marked.parse(content);
  if (isSurveyReport(canonical)) {
    body = postprocessSurveyHtml(body);
  }
  body = rewriteLinks(body, canonical, locale);
  body = mermaidBlocks(body);
  body = wrapTables(body);

  const titleMatch = content.match(/^#\s+(.+)$/m);
  const title = titleMatch ? titleMatch[1].trim() : path.basename(canonical, '.md');

  return pageTemplate({ title, canonical, srcMd, bodyHtml: body, locale, contentLang, bodyClass });
}

function writeHtml(outPath, html) {
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, html);
}

marked.setOptions({ gfm: true, breaks: false });

// Always regenerate matrix zh from EN source + dimension glossary
await import('./generate_matrix_zh.mjs');

let built = 0;
const enFiles = collectEnMdFiles();
const dedicatedZh = new Set(collectZhMdFiles().map(canonicalMd));

for (const mdRel of enFiles) {
  const canonical = mdRel;
  const contentLang = detectContentLang(mdRel);
  const htmlEn = buildPage(mdRel, 'en', contentLang);
  if (!htmlEn) continue;

  writeHtml(path.join(OUT, mdToHtmlPath(mdRel)), htmlEn);
  built++;

  // Survey reports: always emit condensed Chinese page at zh/
  if (isSurveyReport(canonical) && !dedicatedZh.has(canonical)) {
    const htmlZh = buildPage(mdRel, 'zh', 'zh');
    if (htmlZh) {
      writeHtml(path.join(OUT, 'zh', mdToHtmlPath(mdRel)), htmlZh);
      built++;
    }
  } else if (contentLang === 'zh' && !dedicatedZh.has(canonical)) {
    const htmlZh = buildPage(mdRel, 'zh', 'zh');
    writeHtml(path.join(OUT, 'zh', mdToHtmlPath(mdRel)), htmlZh);
    built++;
  }
}

for (const mdRel of collectZhMdFiles()) {
  const html = buildPage(mdRel, 'zh', 'zh');
  if (!html) continue;
  writeHtml(path.join(OUT, 'zh', mdToHtmlPath(mdRel)), html);
  built++;
}

const { enOnly, priorityGaps } = auditCoverage(enFiles);
fs.writeFileSync(
  path.join(ROOT, 'html', 'i18n-coverage.json'),
  JSON.stringify({ generated: new Date().toISOString(), enOnly: enOnly.map((r) => r.canonical), priorityGaps }, null, 2)
);

const coverageRows = enOnly
  .map((r) => `<tr><td><code>${r.canonical}</code></td><td>${r.contentLang}</td><td>${r.status}</td></tr>`)
  .join('\n');
const priorityRows = priorityGaps.map((p) => `<li><code>${p}</code></li>`).join('\n');

fs.writeFileSync(
  path.join(ROOT, 'html', 'i18n-coverage.html'),
  `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>i18n Coverage</title>
<link rel="stylesheet" href="css/style.css"></head>
<body><div class="layout"><main style="max-width:900px">
<h1>中文覆盖审计</h1>
<p>Priority nav gaps (${priorityGaps.length}):</p><ul>${priorityRows || '<li>none</li>'}</ul>
<p>All EN-only pages (${enOnly.length}):</p>
<table><thead><tr><th>Path</th><th>Content</th><th>Status</th></tr></thead><tbody>${coverageRows}</tbody></table>
<p><a href="docs.html">← Sitemap</a></p>
</main></div></body></html>`
);

fs.mkdirSync(OUT, { recursive: true });
writeHtml(
  path.join(OUT, 'index.html'),
  `<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url=/html/docs.html"><title>Redirect</title></head><body><p><a href="/html/docs.html">Docs</a></p></body></html>`
);

console.log(`Built ${built} HTML pages → html/site/ (+ zh/)`);
console.log(`  Priority gaps (no zh): ${priorityGaps.length}`);
priorityGaps.forEach((p) => console.log(`    - ${p}`));
console.log(`  Coverage: /html/i18n-coverage.html`);
