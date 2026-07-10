#!/usr/bin/env node
/** Add bilingual headers + zh slide bodies to survey/paper deck HTML. */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DECK = path.join(ROOT, 'html/deck');
const zhCfg = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/deck-survey-zh.json'), 'utf8'));

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function biText(en, zh) {
  if (!zh) return en;
  if (en === zh) return en;
  return `<span data-lang-only="en">${en}</span><span data-lang-only="zh" hidden>${zh}</span>`;
}

function biHtml(en, zh) {
  if (!zh) return en;
  return `<span data-lang-only="en">${en}</span><span data-lang-only="zh" hidden>${zh}</span>`;
}

function buildCompareZh(body) {
  if (!body?.strengths) return '';
  const stats = (body.stats || [])
    .map(
      ([val, lbl]) =>
        `<div class="stat${lbl.includes('runs_on') ? ' green' : ''}"><div class="val">${val}</div><div class="lbl">${lbl}</div></div>`
    )
    .join('');
  const strengths = body.strengths.map((li) => `<li>${li}</li>`).join('');
  const gaps = body.gaps.map((li) => `<li>${li}</li>`).join('');
  const footer = body.footer
    ? `<footer class="slide-footer">${body.footer.map((s) => `<span>${esc(s)}</span>`).join('')}</footer>`
    : '';
  return `<div data-lang-only="zh" hidden>
          <div class="stat-row">${stats}</div>
          <div class="compare">
            <div class="panel before accent-taichu">
              <h3 data-i18n="deck.strengths">优势（保留）</h3>
              <ul>${strengths}</ul>
            </div>
            <div class="compare-mid">→</div>
            <div class="panel after accent-warn">
              <h3 data-i18n="deck.gaps">缺口（P0–P3）</h3>
              <ul>${gaps}</ul>
            </div>
          </div>
          <div class="mono" style="margin-top:0.35rem;color:var(--muted)">${body.flow || ''}</div>
        </div>${footer ? '' : ''}`;
}

function processFile(filename) {
  const slidesZh = zhCfg[filename];
  if (!slidesZh?.length) return false;
  const p = path.join(DECK, filename);
  let html = fs.readFileSync(p, 'utf8');
  if (html.includes('data-content-lang="bi"')) return false;

  html = html.replace(/<html lang="[^"]*">/, '<html lang="en">');
  html = html.replace(/<body([^>]*)>/, '<body$1 data-i18n-page="deck" data-content-lang="bi">');
  if (!html.includes('data-lang-switch')) {
    html = html.replace(
      /<body[^>]*>/,
      (m) => `${m}\n  <div class="lang-switch-deck" data-lang-switch aria-label="Language"></div>`
    );
  }
  if (!html.includes('i18n.js')) {
    html = html.replace('</body>', '  <script src="../js/i18n.js"></script>\n</body>');
  }

  const sections = [...html.matchAll(/<section class="slide[^"]*"[^>]*>[\s\S]*?<\/section>/g)];
  if (sections.length !== slidesZh.length) {
    console.warn(`${filename}: slide count ${sections.length} vs zh config ${slidesZh.length}`);
  }

  let idx = 0;
  html = html.replace(/<section class="slide[^"]*"[^>]*>[\s\S]*?<\/section>/g, (section) => {
    const meta = slidesZh[idx] || {};
    idx += 1;
    let out = section;

    out = out.replace(/<h1>([\s\S]*?)<\/h1>/, (_, en) => `<h1>${biHtml(en.trim(), meta.h1)}</h1>`);
    out = out.replace(
      /<p class="subtitle">([\s\S]*?)<\/p>/,
      (_, en) => `<p class="subtitle">${biHtml(en.trim(), meta.subtitle)}</p>`
    );

    out = out.replace(/<h3>Strengths \(keep\)<\/h3>/, '<h3 data-i18n="deck.strengths">Strengths (keep)</h3>');
    out = out.replace(/<h3>Gaps \(P0–P3\)<\/h3>/, '<h3 data-i18n="deck.gaps">Gaps (P0–P3)</h3>');
    out = out.replace(/Overall score/g, '<span data-i18n="deck.stat.overall">Overall score</span>');
    out = out.replace(/(<div class="lbl">)Lifecycle(<\/div>)/g, '$1<span data-i18n="deck.stat.lifecycle">Lifecycle</span>$2');
    out = out.replace(/(<div class="lbl">)Evolution(<\/div>)/g, '$1<span data-i18n="deck.stat.evolution">Evolution</span>$2');

    if (meta.body?.strengths && out.includes('class="slide-body"')) {
      out = out.replace(
        /(<div class="slide-body">)([\s\S]*?)(<\/div>\s*\n\s*<footer)/,
        (m, open, body, foot) => {
          const enWrap = `<div data-lang-only="en">${body.trim()}</div>`;
          const zhWrap = buildCompareZh(meta.body);
          return `${open}${enWrap}${zhWrap}${foot}`;
        }
      );
    } else if (out.includes('class="slide-body"') && !out.includes('data-lang-only="en"')) {
      out = out.replace(
        /(<div class="slide-body">)([\s\S]*?)(<\/div>\s*\n\s*<footer)/,
        (m, open, body, foot) => `${open}<div data-lang-only="en">${body.trim()}</div><div data-lang-only="zh" hidden class="deck-zh-fallback"><p class="eli5">${esc(meta.intro || meta.subtitle || '完整中文版见站点 L3 报告。')}</p></div>${foot}`
      );
    }

    return out;
  });

  html = html.replace(
    /<button type="button" id="nav-prev">← Prev<\/button>/,
    '<button type="button" id="nav-prev" data-i18n="deck.nav.prev">← Prev</button>'
  );
  html = html.replace(
    /<button type="button" id="nav-next">Next →<\/button>/,
    '<button type="button" id="nav-next" data-i18n="deck.nav.next">Next →</button>'
  );
  html = html.replace(
    /<a class="hub-link" href="index\.html">← Decks<\/a>/,
    '<a class="hub-link" href="index.html" data-i18n="deck.hubs">← Decks</a>'
  );
  html = html.replace(
    /<a class="hub-link" href="index\.html">← Deck Hub<\/a>/,
    '<a class="hub-link" href="index.html" data-i18n="deck.hub">← Deck Hub</a>'
  );

  fs.writeFileSync(p, html);
  return true;
}

const files = Object.keys(zhCfg);
let n = 0;
for (const f of files) {
  if (processFile(f)) n += 1;
}
console.log(`build_survey_deck_i18n: updated ${n} deck files`);
