/**
 * Fetch workspace .md files and render with marked (GFM tables).
 * Usage: viewer.html?path=notes/synthesis/skill-lifecycle-full-matrix.md
 */

const SITE = document.documentElement.dataset.siteRoot || '..';

function getPathParam() {
  const q = new URLSearchParams(window.location.search).get('path');
  if (q) return q.replace(/^\/+/, '');
  return 'notes/synthesis/agent-skill-architecture-survey-matrix.md';
}

function mdUrl(relPath) {
  const clean = relPath.replace(/^\/+/, '');
  return `${SITE}/${clean.split('/').map(encodeURIComponent).join('/')}`;
}

function viewerUrl(relPath) {
  return `viewer.html?path=${encodeURIComponent(relPath.replace(/^\/+/, ''))}`;
}

async function loadMarkdown(relPath) {
  const url = mdUrl(relPath);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
  return res.text();
}

function wrapTables(html) {
  return html.replace(/<table>/g, '<div class="table-wrap"><table>').replace(/<\/table>/g, '</table></div>');
}

function renderMarkdown(text) {
  if (typeof marked === 'undefined') {
    return '<p>Markdown renderer failed to load.</p>';
  }
  marked.setOptions({
    gfm: true,
    breaks: false,
    headerIds: true,
    mangle: false,
  });
  return wrapTables(marked.parse(text));
}

function setActiveNav(relPath) {
  document.querySelectorAll('nav a[data-md]').forEach((a) => {
    a.classList.toggle('active', a.dataset.md === relPath);
  });
}

async function main() {
  const relPath = getPathParam();
  const content = document.getElementById('md-content');
  const titleEl = document.getElementById('doc-title');
  const pathEl = document.getElementById('doc-path');
  const rawLink = document.getElementById('raw-link');

  if (pathEl) pathEl.textContent = relPath;
  if (rawLink) rawLink.href = mdUrl(relPath);
  setActiveNav(relPath);

  content.className = 'md-body loading';
  content.textContent = 'Loading…';

  try {
    const text = await loadMarkdown(relPath);
    content.className = 'md-body';
    content.innerHTML = renderMarkdown(text);

    const h1 = content.querySelector('h1');
    if (titleEl && h1) titleEl.textContent = h1.textContent;
    else if (titleEl) titleEl.textContent = relPath.split('/').pop();

    document.title = (titleEl?.textContent || 'Doc') + ' — Skill-Evolving';
  } catch (err) {
    content.className = 'md-body error';
    content.innerHTML = `<p><strong>Failed to load:</strong> ${err.message}</p>
      <p>Ensure the server is running: <code>python3 scripts/serve.py</code></p>
      <p>Path: <code>${relPath}</code></p>`;
  }
}

document.addEventListener('DOMContentLoaded', main);

// Export for docs.html
window.viewerUrl = viewerUrl;
