#!/usr/bin/env node
/** Rewrite .md / viewer.html links → static html/site/*.html in dashboard HTML */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const HTML = path.join(__dirname, '..', 'html');

function mdToSite(rel) {
  const base = rel.replace(/\.md$/i, '');
  return `site/${base}.html`;
}

function rewriteContent(text, fileDir) {
  let out = text;

  // viewer.html?path=foo/bar.md → site/foo/bar.html
  out = out.replace(/viewer\.html\?path=([^"'&]+)\.md/gi, (_, p) => mdToSite(decodeURIComponent(p)));

  // ../../notes/...md from deck → ../site/notes/...html
  out = out.replace(/\.\.\/\.\.\/notes\/([^"'<>]+\.md)/gi, (_, p) => `../site/notes/${p.replace(/\.md$/i, '.html')}`);

  // ../../topics/...md from deck
  out = out.replace(/\.\.\/\.\.\/topics\/([^"'<>]+\.md)/gi, (_, p) => `../site/topics/${p.replace(/\.md$/i, '.html')}`);

  // ../../INDEX.md etc from deck
  out = out.replace(/\.\.\/\.\.\/(INDEX|README|STORE)\.md/gi, (_, name) => `../site/${name}.html`);

  // ../notes/... from index (dashboard nav)
  out = out.replace(/\.\.\/notes\/([^"'<>]+\.md)/gi, (_, p) => `site/notes/${p.replace(/\.md$/i, '.html')}`);

  // ../topics/... from index
  out = out.replace(/\.\.\/topics\/([^"'<>]+\.md)/gi, (_, p) => `site/topics/${p.replace(/\.md$/i, '.html')}`);

  // ../INDEX.md from index
  out = out.replace(/\.\.\/(INDEX|README|STORE)\.md/gi, (_, name) => `site/${name}.html`);

  return out;
}

function walk(dir) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      if (ent.name === 'site' || ent.name === 'node_modules') continue;
      walk(full);
    } else if (ent.name.endsWith('.html')) {
      const raw = fs.readFileSync(full, 'utf8');
      const next = rewriteContent(raw, path.dirname(full));
      if (next !== raw) {
        fs.writeFileSync(full, next);
        console.log('updated', path.relative(HTML, full));
      }
    }
  }
}

walk(HTML);
console.log('Link rewrite done.');
