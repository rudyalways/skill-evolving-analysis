#!/usr/bin/env node
/** Audit zh coverage; used by build_site.mjs */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '..');

export function parseFrontmatter(raw) {
  if (!raw.startsWith('---')) return { meta: {}, body: raw };
  const end = raw.indexOf('---', 3);
  if (end === -1) return { meta: {}, body: raw };
  const block = raw.slice(3, end).trim();
  const meta = {};
  for (const line of block.split('\n')) {
    const m = line.match(/^([\w-]+):\s*(.+)$/);
    if (m) meta[m[1]] = m[2].trim();
  }
  return { meta, body: raw.slice(end + 3).trimStart() };
}

export function cjkRatio(text) {
  const cjk = (text.match(/[\u4e00-\u9fff]/g) || []).length;
  const chars = text.replace(/\s/g, '').length;
  return chars ? cjk / chars : 0;
}

/** @returns {'en'|'zh'} */
export function detectContentLang(mdRel) {
  const src = path.join(ROOT, mdRel);
  if (!fs.existsSync(src)) return 'en';
  const raw = fs.readFileSync(src, 'utf8');
  const { meta, body } = parseFrontmatter(raw);
  if (meta.lang === 'zh') return 'zh';
  if (meta.lang === 'en') return 'en';

  const cjkCount = (body.match(/[\u4e00-\u9fff]/g) || []).length;
  const ratio = cjkRatio(body);
  const h1 = body.match(/^#\s+(.+)$/m)?.[1] || '';
  const titleHasCjk = /[\u4e00-\u9fff]/.test(h1) || /[\u4e00-\u9fff]/.test(meta.title || '');

  // Table-heavy zh docs: Chinese title or high absolute CJK count
  if (titleHasCjk) return 'zh';
  if (cjkCount >= 120 && ratio >= 0.035) return 'zh';
  if (ratio >= 0.12) return 'zh';
  return 'en';
}

export function zhMdPath(canonical) {
  return canonical.replace(/\.md$/i, '.zh.md');
}

export function hasDedicatedZh(canonical) {
  return fs.existsSync(path.join(ROOT, zhMdPath(canonical)));
}

export function hasZhPage(canonical) {
  return hasDedicatedZh(canonical) || detectContentLang(canonical) === 'zh';
}

export const PRIORITY_NAV = [
  'notes/synthesis/agent-skill-architecture-survey-matrix.md',
  'notes/synthesis/skill-lifecycle-full-matrix.md',
  'notes/synthesis/web-expanded-lifecycle-matrix-merged.md',
  'notes/synthesis/eight-repo-comprehensive-survey.md',
  'notes/synthesis/skill-lifecycle-and-dynamic-loading-survey.md',
  'notes/synthesis/eight-repo-deep-source-analysis.md',
  'notes/synthesis/comparison.md',
  'notes/synthesis/combined-pipeline.md',
  'notes/synthesis/l3-comprehensive-skill-analysis.md',
  'notes/synthesis/taichu-p0-skill-compaction-spec.md',
  'notes/synthesis/web-deep-taichu-borrowing-guide.md',
  'topics/skill-rl/overview.md',
  'topics/claw-r1/overview.md',
];

export function auditCoverage(allCanonical) {
  const rows = allCanonical.map((canonical) => {
    const dedicated = hasDedicatedZh(canonical);
    const contentLang = detectContentLang(canonical);
    const zhAvailable = hasZhPage(canonical);
    let status = 'en-only';
    if (dedicated) status = 'dedicated-zh';
    else if (contentLang === 'zh') status = 'zh-native';
    return { canonical, contentLang, dedicated, zhAvailable, status };
  });
  const enOnly = rows.filter((r) => !r.zhAvailable);
  const priorityGaps = PRIORITY_NAV.filter((p) => !hasZhPage(p));
  return { rows, enOnly, priorityGaps };
}
