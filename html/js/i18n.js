/**
 * Bilingual UI (EN / 中文) + inline content blocks (.i18n-content[data-lang]).
 * Persists preference in localStorage; honors ?lang=zh|en.
 */
(function () {
  const STORAGE_KEY = 'skill-evolving-lang';
  const DEFAULT = 'en';
  const LOCALES = ['en', 'zh'];

  let strings = {};
  let lang = DEFAULT;

  function detectLang() {
    const q = new URLSearchParams(location.search).get('lang');
    if (q && LOCALES.includes(q)) return q;
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && LOCALES.includes(saved)) return saved;
    const nav = (navigator.language || '').toLowerCase();
    if (nav.startsWith('zh')) return 'zh';
    return DEFAULT;
  }

  function i18nBase() {
    const p = location.pathname;
    if (p.includes('/html/site/')) {
      const depth = p.split('/html/site/')[1].split('/').length - 1;
      return '../'.repeat(depth + 1) + 'i18n/';
    }
    if (p.includes('/html/deck/')) return '../i18n/';
    if (p.includes('/html/')) return 'i18n/';
    return '/html/i18n/';
  }

  async function loadStrings(locale) {
    const base = i18nBase();
    const res = await fetch(`${base}${locale}.json`);
    if (!res.ok) throw new Error(`i18n load failed: ${locale}`);
    return res.json();
  }

  function t(key) {
    return strings[key] ?? key;
  }

  function contentLang() {
    return document.body.dataset.contentLang || document.body.dataset.docLocale || 'en';
  }

  function applyDom() {
    document.documentElement.lang = lang === 'zh' ? 'zh-Hans' : 'en';

    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.dataset.i18n;
      const val = t(key);
      if (val === key) return;
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') el.placeholder = val;
      else el.textContent = val;
    });

    document.querySelectorAll('[data-i18n-html]').forEach((el) => {
      const key = el.dataset.i18nHtml;
      const val = t(key);
      if (val !== key) el.innerHTML = val;
    });

    document.querySelectorAll('[data-i18n-title]').forEach((el) => {
      const key = el.dataset.i18nTitle;
      const val = t(key);
      if (val !== key) el.title = val;
    });

    document.querySelectorAll('.i18n-content').forEach((el) => {
      el.hidden = el.dataset.lang !== lang;
    });

    document.querySelectorAll('[data-lang-only]').forEach((el) => {
      el.hidden = el.dataset.langOnly !== lang;
    });

    document.documentElement.classList.toggle('lang-en', lang === 'en');
    document.documentElement.classList.toggle('lang-zh', lang === 'zh');

    document.querySelectorAll('.lang-switch [data-set-lang]').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.setLang === lang);
      btn.setAttribute('aria-pressed', btn.dataset.setLang === lang ? 'true' : 'false');
    });

    const notice = document.getElementById('i18n-fallback-notice');
    if (notice) {
      notice.hidden = !(lang === 'zh' && contentLang() === 'en');
    }

    const zhNative = document.getElementById('i18n-zh-native-notice');
    if (zhNative) {
      zhNative.hidden = !(lang === 'en' && contentLang() === 'zh');
    }

    document.dispatchEvent(new CustomEvent('langchange', { detail: { lang } }));
  }

  function alternateHref(targetLang) {
    const alt = document.querySelector(`link[rel="alternate"][hreflang="${targetLang}"]`);
    if (alt && alt.href) return alt.href;
    const path = location.pathname;
    if (targetLang === 'zh' && path.includes('/html/site/') && !path.includes('/html/site/zh/')) {
      return path.replace('/html/site/', '/html/site/zh/');
    }
    if (targetLang === 'en' && path.includes('/html/site/zh/')) {
      return path.replace('/html/site/zh/', '/html/site/');
    }
    return null;
  }

  async function setLang(next, opts = {}) {
    if (!LOCALES.includes(next)) return;
    lang = next;
    localStorage.setItem(STORAGE_KEY, lang);

    if (!opts.skipNavigate && !opts.skipAlternateCheck) {
      const alt = alternateHref(next);
      if (alt && alt !== location.pathname) {
        const needNav =
          (next === 'zh' && contentLang() === 'en') ||
          (next === 'en' && location.pathname.includes('/html/site/zh/'));
        if (needNav) {
          try {
            const head = await fetch(alt, { method: 'HEAD' });
            if (head.ok) {
              location.href = alt;
              return;
            }
          } catch (_) { /* stay on page, UI-only */ }
        }
      }
    }

    strings = await loadStrings(lang);
    applyDom();
  }

  function injectSwitcher(container) {
    if (!container || container.querySelector('.lang-switch')) return;
    const wrap = document.createElement('div');
    wrap.className = 'lang-switch';
    wrap.setAttribute('role', 'group');
    wrap.setAttribute('aria-label', 'Language');
    wrap.innerHTML = `
      <button type="button" data-set-lang="en" aria-pressed="false">${t('lang.en')}</button>
      <button type="button" data-set-lang="zh" aria-pressed="false">${t('lang.zh')}</button>`;
    wrap.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-set-lang]');
      if (btn) setLang(btn.dataset.setLang);
    });
    container.prepend(wrap);
  }

  async function init() {
    lang = detectLang();
    strings = await loadStrings(lang);

    if (lang === 'zh' && contentLang() === 'en') {
      const alt = alternateHref('zh');
      if (alt && alt !== location.pathname) {
        try {
          const head = await fetch(alt, { method: 'HEAD' });
          if (head.ok) {
            location.replace(alt);
            return;
          }
        } catch (_) { /* UI-only fallback */ }
      }
    }

    document.querySelectorAll('[data-lang-switch]').forEach(injectSwitcher);

    applyDom();

    document.querySelectorAll('.lang-switch').forEach((wrap) => {
      if (wrap.dataset.bound) return;
      wrap.dataset.bound = '1';
      wrap.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-set-lang]');
        if (btn) setLang(btn.dataset.setLang);
      });
    });
  }

  window.i18n = { t, setLang, getLang: () => lang, init };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
