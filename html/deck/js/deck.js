/** Fullscreen deck navigation, progress, evidence + walkthrough modals */
(function () {
  const slides = [...document.querySelectorAll('.slide')];
  if (!slides.length) return;

  const progressFill = document.getElementById('progress-fill');
  const progressLabel = document.getElementById('progress-label');
  const btnPrev = document.getElementById('nav-prev');
  const btnNext = document.getElementById('nav-next');
  const overlay = document.getElementById('evidence-modal');
  const modalPanel = document.getElementById('modal-panel');
  const modalTitle = document.getElementById('modal-title');
  const modalBody = document.getElementById('modal-body');

  let current = 0;

  function idx() {
    const y = window.scrollY;
    let best = 0;
    let bestDist = Infinity;
    slides.forEach((s, i) => {
      const d = Math.abs(s.offsetTop - y);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    return best;
  }

  function goTo(i) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    slides[i].scrollIntoView({ behavior: 'smooth', block: 'start' });
    current = i;
    updateProgress();
  }

  function updateProgress() {
    current = idx();
    window.__deckCurrent = current;
    const pct = ((current + 1) / slides.length) * 100;
    if (progressFill) progressFill.style.width = pct + '%';
    if (progressLabel) progressLabel.textContent = current + 1 + '/' + slides.length;
    window.dispatchEvent(new CustomEvent('deck-slide-change', { detail: { index: current } }));
  }

  function wireDetailButtons(root) {
    root.querySelectorAll('[data-detail-target]').forEach((btn) => {
      if (btn.dataset.detailWired) return;
      btn.dataset.detailWired = '1';
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        openDetailTarget(btn.dataset.detailTarget, btn.dataset.detailKind || '');
      });
    });
  }

  function openModal(title, body, kind) {
    if (!overlay) return;
    modalTitle.textContent = title;
    modalBody.innerHTML = body;
    if (modalPanel) {
      const isScrollModal = kind === 'walkthrough' || kind === 'glossary';
      modalPanel.classList.toggle('modal-wt', isScrollModal);
      modalPanel.classList.toggle('modal-glossary', kind === 'glossary');
    }
    overlay.classList.add('open');
    document.body.classList.add('modal-open');
    wireDetailButtons(modalBody);
    if (kind === 'walkthrough' && window.__renderMermaid) {
      window.__renderMermaidIn(modalBody);
    }
  }

  function closeModal() {
    if (overlay) overlay.classList.remove('open');
    if (modalPanel) {
      modalPanel.classList.remove('modal-wt');
      modalPanel.classList.remove('modal-glossary');
    }
    document.body.classList.remove('modal-open');
  }

  window.closeModal = closeModal;

  function openDetailTarget(targetId, kind) {
    const el = document.getElementById(targetId);
    if (!el) return;
    const title = el.dataset.detailTitle || targetId.replace(/^detail-/, '');
    openModal(title, el.innerHTML, kind);
  }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-detail-target]');
    if (btn && !btn.dataset.detailWired) {
      e.preventDefault();
      e.stopPropagation();
      openDetailTarget(btn.dataset.detailTarget, btn.dataset.detailKind || '');
    }
    if (e.target.closest('summary') || e.target.closest('details') || e.target.closest('button')) {
      e.stopPropagation();
    }
  });

  document.querySelectorAll('[data-evidence]').forEach((el) => {
    el.addEventListener('click', () => {
      const title = el.dataset.evidence || 'Evidence';
      const quote = el.dataset.quote || '';
      const source = el.dataset.source || '';
      const link = el.dataset.link || '';
      let html = '';
      if (quote) {
        html +=
          '<blockquote style="margin:0 0 1rem;font-style:italic;color:#475569">' +
          quote +
          '</blockquote>';
      }
      if (source) html += '<pre class="evo-detail-code">' + source + '</pre>';
      if (link) {
        html +=
          '<p style="margin-top:0.75rem"><a href="' +
          link +
          '" target="_blank" rel="noopener">' +
          link +
          '</a></p>';
      }
      openModal(title, html, '');
    });
  });

  wireDetailButtons(document);

  window.__renderMermaidIn = async (root) => {
    if (!root || !window.mermaidRun) return;
    const nodes = root.querySelectorAll('pre.mermaid:not([data-rendered])');
    if (!nodes.length) return;
    try {
      const mermaid = await import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs');
      mermaid.default.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' });
      await mermaid.default.run({ nodes: [...nodes] });
      nodes.forEach((n) => n.setAttribute('data-rendered', '1'));
    } catch (e) {
      console.warn('mermaid in modal', e);
    }
  };

  if (btnPrev) btnPrev.addEventListener('click', () => goTo(current - 1));
  if (btnNext) btnNext.addEventListener('click', () => goTo(current + 1));

  window.addEventListener('keydown', (e) => {
    if (document.querySelector('.modal-overlay.open')) {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeModal();
      }
      return;
    }
    if (e.target.matches('input, textarea, button')) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === ' ') {
      e.preventDefault();
      goTo(current + 1);
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
      e.preventDefault();
      goTo(current - 1);
    } else if (e.key === 'Home') goTo(0);
    else if (e.key === 'End') goTo(slides.length - 1);
  });

  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModal();
    });
  }

  window.addEventListener('scroll', () => requestAnimationFrame(updateProgress), { passive: true });
  updateProgress();
})();
