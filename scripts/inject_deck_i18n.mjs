#!/usr/bin/env node
/** Inject i18n.js + lang switcher into deck and misc HTML pages missing them. */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DECK = path.join(ROOT, 'html/deck');
const HTML = path.join(ROOT, 'html');

const DECK_FILES = fs.readdirSync(DECK).filter((f) => f.endsWith('.html'));
const MISC = ['structure.html', 'workflow.html', 'viewer.html', 'i18n-coverage.html'];

function inject(html, { scriptSrc, switchClass = 'lang-switch-deck' }) {
  if (html.includes('data-content-lang="bi"')) {
    if (!html.includes('i18n.js')) {
      html = html.replace('</body>', `  <script src="${scriptSrc}"></script>\n</body>`);
    }
    return html;
  }

  let out = html;
  if (!out.includes('data-lang-switch')) {
    const switcher = `<div class="${switchClass}" data-lang-switch aria-label="Language"></div>\n`;
    if (out.includes('<body class="hub-page">')) {
      out = out.replace('<body class="hub-page">', `<body class="hub-page" data-i18n-page="deck">\n  ${switcher}`);
    } else if (out.includes('<body>')) {
      out = out.replace('<body>', `<body data-i18n-page="deck">\n  ${switcher}`);
    }
  }

  if (!out.includes('data-content-lang')) {
    out = out.replace(/<body([^>]*)>/, '<body$1 data-content-lang="en">');
  }

  const script = `  <script src="${scriptSrc}"></script>\n`;
  if (out.includes('</body>')) {
    out = out.replace('</body>', `${script}</body>`);
  }
  return out;
}

function patchDeckNav(html) {
  let out = html;
  out = out.replace(
    /<button type="button" id="nav-prev">← Prev<\/button>/,
    '<button type="button" id="nav-prev" data-i18n="deck.nav.prev">← Prev</button>'
  );
  out = out.replace(
    /<button type="button" id="nav-next">Next →<\/button>/,
    '<button type="button" id="nav-next" data-i18n="deck.nav.next">Next →</button>'
  );
  out = out.replace(
    /<a class="hub-link" href="index\.html">← Deck Hub<\/a>/,
    '<a class="hub-link" href="index.html" data-i18n="deck.hub">← Deck Hub</a>'
  );
  out = out.replace(
    /<a class="hub-link" href="index\.html">← Decks<\/a>/,
    '<a class="hub-link" href="index.html" data-i18n="deck.hubs">← Decks</a>'
  );
  return out;
}

let n = 0;
for (const f of DECK_FILES) {
  const p = path.join(DECK, f);
  let html = fs.readFileSync(p, 'utf8');
  const next = patchDeckNav(inject(html, { scriptSrc: '../js/i18n.js' }));
  if (next !== html) {
    fs.writeFileSync(p, next);
    n++;
  }
}

for (const f of MISC) {
  const p = path.join(HTML, f);
  if (!fs.existsSync(p)) continue;
  let html = fs.readFileSync(p, 'utf8');
  const next = inject(html, { scriptSrc: 'js/i18n.js', switchClass: 'lang-switch-host' });
  if (next !== html) {
    fs.writeFileSync(p, next);
    n++;
  }
}

console.log(`inject_deck_i18n: updated ${n} files`);
