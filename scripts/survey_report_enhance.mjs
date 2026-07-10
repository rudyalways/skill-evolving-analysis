/**
 * Survey report: Chinese injection, compact layout, collapsible evidence.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

let zhMeta = null;

function loadZhMeta() {
  if (!zhMeta) {
    zhMeta = JSON.parse(
      fs.readFileSync(path.join(ROOT, 'config/survey-reports-zh.json'), 'utf8')
    );
  }
  return zhMeta;
}

export function surveyRepoFromPath(mdRel) {
  const m = mdRel.match(/survey-reports\/([^/]+)\.md$/);
  if (!m || m[1] === 'README') return null;
  return m[1];
}

export function isSurveyReport(mdRel) {
  return !!surveyRepoFromPath(mdRel);
}

/** Tighter markdown before parse */
export function compactMarkdown(md) {
  return md
    .replace(/\n---\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/^>\s*\*\*Local\*\*:[^\n]+\n>\s*\*\*Upstream\*\*:[^\n]+\n>\s*\*\*Matrix\*\*:[^\n]+\n>\s*\*\*Detail card\*\*:[^\n]+\n/gm, (block) => {
      const oneLine = block.replace(/\n>/g, ' · ').replace(/^>\s?/gm, '').replace(/\*\*/g, '');
      return `> ${oneLine.trim()}\n`;
    })
    .trim();
}

/** Inject Chinese lead + bilingual h2 on EN pages */
export function injectChineseLeads(md, repo) {
  const meta = loadZhMeta()[repo];
  if (!meta) return md;

  let out = md;
  const header = `# ${meta.title_zh}（${meta.score}）\n\n> **${meta.tagline}**  \n> ${meta.intro_zh}\n\n`;
  out = out.replace(/^#\s+.+\n/, header);

  out = out.replace(/^## (\d+)\.\s+(.+)$/gm, (_, num, title) => {
    const zh = meta.sections[num];
    const lead = zh
      ? `\n\n<p class="zh-lead"><strong>中文</strong> ${zh}</p>\n`
      : '';
    return `## ${num}. ${title}\n${lead}`;
  });

  return out;
}

/** Build condensed Chinese-only markdown for zh/ URL */
export function buildCondensedZhMarkdown(mdRel, enMd) {
  const repo = surveyRepoFromPath(mdRel);
  const meta = loadZhMeta()[repo];
  if (!meta) return enMd;

  const scoreMatch = enMd.match(/\*\*Overall\*\*\s*\|\s*\*\*([\d.]+)\*\*/);
  const score = scoreMatch?.[1] || meta.score;

  const sectionTitles = [
    ['1', '架构', 'Architecture'],
    ['2', 'Skill 运行时', 'Skill Runtime'],
    ['3', 'Skill 生命周期', 'Skill Lifecycle'],
    ['4', 'Skill 进化', 'Skill Evolution'],
    ['5', '多 Agent Skill', 'Multi-Agent Skill'],
    ['6', 'Skill 治理', 'Skill Governance'],
    ['7', 'Harness 集成', 'Harness Integration'],
    ['8', 'RL 就绪度', 'RL Readiness'],
    ['9', 'TaiChu 可借鉴', 'Borrow for TaiChu'],
    ['10', 'TaiChu 落地', 'Implement in TaiChu'],
    ['11', '不应借鉴', 'Do NOT Borrow'],
    ['12', '评分', 'Score'],
  ];

  let body = `# ${meta.title_zh}（${score}）\n\n`;
  body += `> **${meta.tagline}**\n>\n> ${meta.intro_zh}\n\n`;

  for (const [num, zhTitle, enTitle] of sectionTitles) {
    const text = meta.sections[num];
    if (!text) continue;
    body += `## ${num}. ${zhTitle}\n\n${text}\n\n`;
    // Pull first table from EN section if score section
    if (num === '12') {
      const secRe = new RegExp(
        `## 12\\. Score[\\s\\S]*?(\\| Category \\|[\\s\\S]*?\\| \\*\\*Overall\\*\\*[\\s\\S]*?\\n)`,
        'i'
      );
      const m = enMd.match(secRe);
      if (m) body += m[1].trim() + '\n\n';
    }
  }

  body += `---\n\n*完整英文版含 L3 路径与引用 → \`survey-reports/${repo}.md\`*\n`;
  return body;
}

/** Collapse verbose blocks in HTML */
export function postprocessSurveyHtml(html) {
  // Evidence tables → collapsible
  html = html.replace(
    /<p><strong>Evidence<\/strong><\/p>\s*(<div class="table-wrap">[\s\S]*?<\/div>)/gi,
    '<details class="evidence-block"><summary>📎 证据 / Evidence</summary>$1</details>'
  );
  html = html.replace(
    /<p><strong>Quote[^<]*<\/strong><\/p>\s*(<pre>[\s\S]*?<\/pre>)/gi,
    '<details class="evidence-block"><summary>💬 引用 / Quote</summary>$1</details>'
  );
  html = html.replace(
    /<h2>Evidence index<\/h2>\s*(<div class="table-wrap">[\s\S]*?<\/div>)/i,
    '<details class="evidence-block"><summary><h2 style="display:inline;font-size:inherit">📎 证据索引 / Evidence index</h2></summary>$1</details>'
  );
  // Shorten blockquote meta to one line style already in md
  return html;
}

export function preprocessSurveyReport(md, mdRel, locale) {
  const repo = surveyRepoFromPath(mdRel);
  if (!repo) return md;

  let content = compactMarkdown(md);
  if (locale === 'zh') {
    content = buildCondensedZhMarkdown(mdRel, md);
    content = compactMarkdown(content);
  } else {
    content = injectChineseLeads(content, repo);
  }
  return content;
}
