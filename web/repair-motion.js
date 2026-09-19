/* Scroll direction is the timeline. Native scrolling and replay controls retain ownership. */
(function () {
  'use strict';
  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const hero = document.querySelector('.hero');
  const stage = document.getElementById('replay');
  const chapters = [...document.querySelectorAll('.story-chapter')];
  const mode = document.querySelector('.scroll-replay-mode');
  const progress = document.getElementById('reading-progress-fill');
  const replay = window.ProposalReplay;
  const settled = new WeakSet();
  const panels = [
    { node: document.querySelector('.bench-section .section-heading'), y: 35, scale: 1, rotate: 0 },
    { node: document.querySelector('.bench-frame'), y: 60, scale: .972, rotate: 0 },
    { node: document.querySelector('.run-copy'), y: 36, scale: 1, rotate: 0 },
    { node: document.querySelector('.tutorial-panel'), y: 75, scale: .965, rotate: 1.3 },
    { node: document.querySelector('.evidence-copy'), y: 32, scale: 1, rotate: 0 },
    { node: document.querySelector('.aws-proof'), y: 52, scale: .97, rotate: -1.2 }
  ];
  const run = document.querySelector('.run-section');
  const proofLinks = [...document.querySelectorAll('.proof-strip > a')];
  let frame = 0, pin = false, stageHeight = 0, wide = false, suspended = false;
  const clamp = value => Math.max(0, Math.min(1, value));
  const ease = value => 1 - Math.pow(1 - clamp(value), 3);
  const layoutTop = node => { let top = 0; for (let item = node; item; item = item.offsetParent) top += item.offsetTop; return top; };

  for (const chapter of chapters) {
    const target = chapter.querySelector('.chapter-outcomes');
    for (const result of replay.chapterCounts(Number(chapter.dataset.chapter))) {
      const item = document.createElement('span');
      const title = document.createElement('small'); title.textContent = result.title;
      const counts = document.createElement('strong'); counts.textContent = 'A ' + result.a + ' · B ' + result.b;
      item.append(title, counts); target.append(item);
    }
  }

  function clearPanel(node) { node.style.removeProperty('transform'); node.style.removeProperty('opacity'); }
  function requestFrame() {
    if (!frame && !suspended && !document.hidden) frame = requestAnimationFrame(paint);
  }
  function paint() {
    frame = 0;
    if (suspended || document.hidden) return;
    const vh = innerHeight;
    const heroBox = hero.getBoundingClientRect();
    const stageBox = stage.getBoundingClientRect();
    const chapterBoxes = chapters.map(node => node.getBoundingClientRect());
    const panelTops = panels.map(({ node }) => layoutTop(node) - scrollY);
    const runBox = run.getBoundingClientRect();
    const proofBox = document.querySelector('.proof-strip').getBoundingClientRect();
    const scrollRange = Math.max(1, document.documentElement.scrollHeight - vh);
    progress.style.transform = 'scaleX(' + clamp(scrollY / scrollRange) + ')';
    if (reduced.matches) return;
    let selected = 0;
    const readingLine = wide ? vh * .58 : Math.min(vh - 90, stageBox.bottom + 24);
    chapterBoxes.forEach((box, index) => { if (box.top <= readingLine) selected = index + 1; });
    const started = chapterBoxes[0].top < vh - 40;
    if (pin) replay.setScrollStep(started ? selected : 4);
    else replay.setScrollStep(4);

    chapters.forEach((chapter, index) => {
      const amount = ease((vh - 20 - chapterBoxes[index].top) / Math.max(1, vh * .47));
      chapter.dataset.active = String(selected === index + 1);
      chapter.style.setProperty('--chapter-reveal', amount.toFixed(4));
      chapter.style.setProperty('--chapter-shift', ((1 - amount) * (wide ? 32 : 16)).toFixed(2) + 'px');
    });
    hero.style.setProperty('--story-progress', clamp((readingLine - chapterBoxes[0].top) / Math.max(1, chapterBoxes[3].top - chapterBoxes[0].top)).toFixed(4));
    const scene = started && heroBox.bottom > stageHeight ? selected / 4 : 1;
    stage.style.setProperty('--paper-spread', ((1 - scene) * 3).toFixed(2) + 'px');

    panels.forEach((panel, index) => {
      if (settled.has(panel.node)) return;
      const baseTop = panelTops[index];
      const amount = ease((vh - baseTop) / Math.max(1, vh * .58));
      const rest = 1 - amount, y = panel.y * rest;
      panel.node.dataset.motionY = String(y);
      panel.node.style.transform = 'translateY(' + y.toFixed(2) + 'px) scale(' + (1 - (1 - panel.scale) * rest).toFixed(4) + ') rotate(' + (panel.rotate * rest).toFixed(3) + 'deg)';
      panel.node.style.opacity = String(.5 + amount * .5);
    });
    const runAmount = ease((vh - runBox.top) / Math.max(1, vh * .72));
    run.style.setProperty('--run-inset', ((1 - runAmount) * 24).toFixed(2) + 'px');
    run.style.setProperty('--run-radius', ((1 - runAmount) * 30).toFixed(2) + 'px');
    proofLinks.forEach((link, index) => {
      if (settled.has(link)) return;
      const amount = ease((vh - proofBox.top - index * 45) / Math.max(1, vh * .38));
      link.style.transform = 'translateY(' + ((1 - amount) * 30).toFixed(2) + 'px)';
      link.style.opacity = String(.5 + amount * .5);
    });
  }

  function measure() {
    root.classList.toggle('scroll-story-ready', !reduced.matches);
    wide = innerWidth >= 960;
    // Measure with the mode control present so hiding it cannot make pinning oscillate.
    mode.hidden = false;
    stageHeight = stage.offsetHeight;
    pin = !reduced.matches && stageHeight < innerHeight - (wide ? 48 : 185);
    root.classList.toggle('scroll-story-on', pin);
    hero.style.setProperty('--stage-height', stageHeight + 'px');
    if (!pin && mode.contains(document.activeElement)) document.getElementById('replay-toggle').focus({ preventScroll: true });
    mode.hidden = !pin;
    if (reduced.matches) {
      for (const { node } of panels) clearPanel(node);
      for (const link of proofLinks) clearPanel(link);
      for (const chapter of chapters) {
        chapter.style.removeProperty('--chapter-reveal'); chapter.style.removeProperty('--chapter-shift');
      }
      run.style.removeProperty('--run-inset'); run.style.removeProperty('--run-radius');
      stage.style.removeProperty('--paper-spread'); replay.setScrollStep(4);
    }
    requestFrame();
  }
  function focusStable(target) {
    if (!(target instanceof Element)) return;
    const section = target.closest('section');
    for (const { node } of panels) if (node.contains(target) || section && section.contains(node)) {
      settled.add(node); node.dataset.motionY = '0'; clearPanel(node);
    }
    for (const node of proofLinks) if (node.contains(target)) { settled.add(node); clearPanel(node); }
  }
  const resize = new ResizeObserver(() => measure());
  resize.observe(stage); resize.observe(document.querySelector('.bench-frame'));
  addEventListener('scroll', requestFrame, { passive: true });
  addEventListener('resize', measure, { passive: true });
  document.addEventListener('replayguard:scroll-owner', requestFrame);
  document.addEventListener('focusin', event => focusStable(event.target));
  addEventListener('hashchange', () => {
    try { focusStable(document.getElementById(decodeURIComponent(location.hash.slice(1)))); } catch {}
    requestFrame();
  });
  reduced.addEventListener('change', measure);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { cancelAnimationFrame(frame); frame = 0; }
    else measure();
  });
  addEventListener('pagehide', () => { suspended = true; cancelAnimationFrame(frame); frame = 0; resize.disconnect(); });
  addEventListener('pageshow', event => {
    if (event.persisted) { suspended = false; resize.observe(stage); resize.observe(document.querySelector('.bench-frame')); measure(); }
  });
  measure();
})();
