// CCv2 browser-only UI: no component state/trigger emissions or iframe access.
export default function ({ data, parentElement }) {
  // CCv2 may execute new data/theme without first calling its unmount cleanup.
  // The stable shadow root also survives replacement of the injected HTML.
  parentElement.__speedlocalWorkspaceGuideDispose?.();
  const host = parentElement.querySelector('[data-workspace-guide-client]');
  if (!host || data.steps?.length !== 10) return;
  host.lang = data.language;
  const launch = host.querySelector('[data-guide-action="launch"]');
  const labels = data.labels;
  const storageKey = `speedlocal:workspace-guide:${data.version}:${data.region}`;
  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(storageKey)); } catch (_) { /* Storage is optional. */ }
  let index = Number.isInteger(saved?.index) ? Math.max(0, Math.min(9, saved.index)) : 0;
  let paused = ['active', 'paused'].includes(saved?.status);
  let active = false;
  let disposed = false;
  let overlay = null;
  let card = null;
  let highlight = null;
  let target = null;
  let resizeObserver = null;
  let targetObserver = null;
  let targetDeadline = null;
  let frame = null;
  let revealFrame = null;
  let revealVersion = 0;

  function persist(status) {
    try {
      if (status === 'closed') sessionStorage.removeItem(storageKey);
      else sessionStorage.setItem(storageKey, JSON.stringify({ index, status }));
    } catch (_) { /* The guide remains usable without browser storage. */ }
  }
  function updateLaunch() {
    launch.textContent = paused ? labels.resume : labels.launch;
    launch.setAttribute('aria-expanded', String(active));
  }
  // A real app rerun or page reload offers Resume, without reopening an overlay.
  if (paused) persist('paused');
  updateLaunch();

  function stopTargetWait() {
    targetObserver?.disconnect();
    targetObserver = null;
    if (targetDeadline !== null) clearTimeout(targetDeadline);
    targetDeadline = null;
  }
  function stopActiveWork() {
    stopTargetWait();
    resizeObserver?.disconnect();
    resizeObserver = null;
    window.removeEventListener('resize', schedulePosition);
    window.removeEventListener('scroll', schedulePosition, true);
    document.removeEventListener('keydown', onKeyDown);
    document.removeEventListener('transitionend', schedulePosition, true);
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    if (revealFrame !== null) cancelAnimationFrame(revealFrame);
    revealFrame = null;
    revealVersion += 1;
  }
  function hide() {
    stopActiveWork();
    active = false;
    if (overlay) {
      if (typeof overlay.hidePopover === 'function' && overlay.matches(':popover-open')) overlay.hidePopover();
      overlay.hidden = true;
    }
    updateLaunch();
    launch.focus({ preventScroll: true });
  }
  function close() {
    paused = false;
    index = 0;
    persist('closed');
    hide();
  }
  function pause() {
    paused = true;
    persist('paused');
    hide();
  }
  function makeOverlay() {
    if (overlay) return;
    overlay = document.createElement('div');
    overlay.setAttribute('data-guide-overlay', '');
    overlay.setAttribute('popover', 'manual');
    overlay.hidden = true;
    // Static markup only; translated content is assigned with textContent below.
    overlay.innerHTML = `
      <div data-guide-highlight hidden></div>
      <section data-guide-card role="dialog" aria-modal="false" aria-labelledby="workspace-guide-heading" aria-describedby="workspace-guide-body">
        <button type="button" data-guide-action="close">×</button>
        <div data-guide-counter aria-live="polite"></div>
        <h2 id="workspace-guide-heading" data-guide-heading tabindex="-1"></h2>
        <p id="workspace-guide-body" data-guide-body></p><ul data-guide-swatches hidden></ul><p data-guide-missing hidden></p>
        <nav data-guide-navigation>
          <button type="button" data-guide-action="pause"></button>
          <button type="button" data-guide-action="previous"></button>
          <button type="button" data-guide-action="next"></button>
        </nav>
      </section>`;
    host.appendChild(overlay);
    card = overlay.querySelector('[data-guide-card]');
    highlight = overlay.querySelector('[data-guide-highlight]');
    for (const name of ['close', 'pause', 'previous', 'next']) {
      const button = overlay.querySelector(`[data-guide-action="${name}"]`);
      button.setAttribute('aria-label', labels[name]);
      if (name !== 'close') button.textContent = labels[name];
    }
    overlay.querySelector('[data-guide-action="close"]').onclick = close;
    overlay.querySelector('[data-guide-action="pause"]').onclick = pause;
    overlay.querySelector('[data-guide-action="previous"]').onclick = () => go(-1);
    overlay.querySelector('[data-guide-action="next"]').onclick = () => index === 9 ? close() : go(1);
    overlay.querySelector('[data-guide-missing]').textContent = labels.missing;
  }

  function markerForStep() {
    return document.querySelector(`[data-workspace-guide="${CSS.escape(data.steps[index].target)}"]`);
  }
  function reveal(marker) {
    const sidebar = marker.closest('[data-testid="stSidebar"]');
    if (sidebar?.getAttribute('aria-expanded') === 'false') {
      const control = document.querySelector('[data-testid="stExpandSidebarButton"]');
      (control?.matches('button') ? control : control?.querySelector('button'))?.click();
    }
    const ancestors = [];
    for (let node = marker.parentElement; node; node = node.parentElement) {
      if (node.tagName === 'DETAILS') ancestors.push(node);
    }
    // Native expanders retain their content; opening them does not edit inputs.
    for (const details of ancestors.reverse()) {
      if (!details.open || details.querySelector(':scope > [data-testid="stExpanderDetails"][inert]')) {
        details.querySelector(':scope > summary')?.click();
      }
    }
  }
  function resolveTarget(marker) {
    const kind = marker.dataset.workspaceGuideKind || 'self';
    if (kind === 'panel') return marker.closest('details') || marker;
    if (kind === 'block') {
      return marker.closest('[data-testid="stVerticalBlockBorderWrapper"]')
        || marker.closest('[data-testid="stVerticalBlock"]') || marker;
    }
    if (kind === 'map') {
      const following = marker.closest('[data-testid="stElementContainer"]')?.nextElementSibling;
      const mapFrame = following?.matches('iframe') ? following : following?.querySelector('iframe');
      return mapFrame?.closest('[data-testid="stIFrame"]') || mapFrame || null;
    }
    return marker;
  }
  function position() {
    frame = null;
    if (!active || disposed) return;
    const width = window.innerWidth;
    const height = window.innerHeight;
    const rect = target?.isConnected ? target.getBoundingClientRect() : null;
    const visible = rect && rect.width > 1 && rect.height > 1
      && rect.right > 0 && rect.bottom > 0 && rect.left < width && rect.top < height;
    highlight.hidden = !visible;
    overlay.dataset.guideTargetAvailable = String(Boolean(visible));
    overlay.querySelector('[data-guide-missing]').hidden = Boolean(visible);
    const cardWidth = card.offsetWidth;
    const cardHeight = card.offsetHeight;
    let left = Math.max(12, width - cardWidth - 16);
    let top = Math.max(12, height - cardHeight - 16);
    if (visible) {
      const x = Math.max(3, rect.left - 4);
      const y = Math.max(3, rect.top - 4);
      highlight.style.cssText = `left:${x}px;top:${y}px;width:${Math.max(0, Math.min(width - 3, rect.right + 4) - x)}px;height:${Math.max(0, Math.min(height - 3, rect.bottom + 4) - y)}px`;
      if (width > 680) {
        if (rect.right + cardWidth + 28 <= width) left = rect.right + 12;
        else if (rect.left - cardWidth - 12 >= 12) left = rect.left - cardWidth - 12;
        else if (target.matches('iframe, [data-testid="stIFrame"]')) left = 12;
        top = Math.max(12, Math.min(rect.top, height - cardHeight - 12));
        if (target.matches('iframe, [data-testid="stIFrame"]') && left === 12) {
          top = Math.max(12, height - cardHeight - 16);
        }
      }
    }
    card.style.left = `${left}px`;
    card.style.top = `${top}px`;
  }
  function schedulePosition() {
    if (active && frame === null) frame = requestAnimationFrame(position);
  }
  function revealTargetAfterLayout() {
    const version = ++revealVersion;
    const revealedTarget = target;
    if (revealFrame !== null) cancelAnimationFrame(revealFrame);
    const scroll = () => {
      if (!active || disposed || version !== revealVersion || !revealedTarget?.isConnected) return;
      // On a narrow screen, leave the upper part free above the guide card.
      revealedTarget.scrollIntoView({ block: window.innerWidth <= 680 ? 'start' : 'nearest', inline: 'nearest', behavior: 'instant' });
      if (window.innerWidth <= 680) {
        // Streamlit's fixed header otherwise covers a target aligned at y=0.
        const headerBottom = document.querySelector('[data-testid="stHeader"]')?.getBoundingClientRect().bottom || 0;
        const offset = Math.max(0, headerBottom) + 12;
        for (let node = revealedTarget.parentElement; node; node = node.parentElement) {
          if (/auto|scroll/.test(getComputedStyle(node).overflowY) && node.scrollHeight > node.clientHeight) {
            node.scrollBy({ top: -offset, behavior: 'instant' });
            break;
          }
        }
      }
      schedulePosition();
    };
    revealFrame = requestAnimationFrame(() => {
      revealFrame = null;
      scroll();
      // Native expanders may still be animating when their child first mounts.
      // Wait only for current ancestor transitions; never poll or follow inputs.
      const animations = [];
      for (let node = revealedTarget; node; node = node.parentElement) {
        animations.push(...(node.getAnimations?.() || []));
      }
      if (animations.length) Promise.allSettled(animations.map(animation => animation.finished)).then(scroll);
    });
  }
  function acquireTarget() {
    if (!active || disposed) return false;
    const marker = markerForStep();
    if (!marker) return false;
    reveal(marker);
    target = resolveTarget(marker);
    if (!target) return false;
    resizeObserver?.disconnect();
    resizeObserver = new ResizeObserver(schedulePosition);
    resizeObserver.observe(target);
    resizeObserver.observe(card);
    revealTargetAfterLayout();
    schedulePosition();
    return true;
  }
  function renderStep(focusHeading = true) {
    revealVersion += 1;
    stopTargetWait();
    resizeObserver?.disconnect();
    target = null;
    const step = data.steps[index];
    overlay.dataset.guideStep = step.id;
    overlay.dataset.guideIndex = String(index);
    overlay.dataset.guideTarget = step.target;
    highlight.dataset.guideTarget = step.target;
    overlay.querySelector('[data-guide-heading]').textContent = step.title;
    overlay.querySelector('[data-guide-body]').textContent = step.body;
    const swatches = overlay.querySelector('[data-guide-swatches]');
    swatches.replaceChildren();
    const colors = data.swatches?.[step.id] || [];
    swatches.hidden = colors.length === 0;
    for (const item of colors) {
      const row = document.createElement('li');
      const chip = document.createElement('span');
      chip.setAttribute('aria-hidden', 'true');
      chip.style.background = item.color;
      if (item.border) chip.style.border = `3px solid ${item.border}`;
      row.append(chip, document.createTextNode(item.label));
      swatches.appendChild(row);
    }
    overlay.querySelector('[data-guide-counter]').textContent = labels.step
      .replace('{index}', String(index + 1)).replace('{count}', String(data.steps.length));
    overlay.querySelector('[data-guide-action="previous"]').disabled = index === 0;
    const next = overlay.querySelector('[data-guide-action="next"]');
    next.textContent = index === 9 ? labels.done : labels.next;
    next.setAttribute('aria-label', next.textContent);
    persist('active');
    if (!acquireTarget()) {
      // A component may mount before later app output. Wait briefly, never poll.
      targetObserver = new MutationObserver(() => {
        if (active && acquireTarget()) stopTargetWait();
      });
      targetObserver.observe(document.querySelector('[data-testid="stAppViewContainer"]') || document.body,
        { childList: true, subtree: true });
      targetDeadline = setTimeout(stopTargetWait, 3000);
    }
    schedulePosition();
    if (focusHeading) overlay.querySelector('[data-guide-heading]').focus({ preventScroll: true });
  }
  function go(delta) {
    index = Math.max(0, Math.min(9, index + delta));
    renderStep();
  }
  function onKeyDown(event) {
    // Do not intercept arrows, Tab or input shortcuts elsewhere in the app.
    if (active && event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  }
  function start() {
    if (active) return;
    makeOverlay();
    active = true;
    paused = false;
    overlay.hidden = false;
    if (typeof overlay.showPopover === 'function') overlay.showPopover();
    else overlay.removeAttribute('popover');
    window.addEventListener('resize', schedulePosition);
    window.addEventListener('scroll', schedulePosition, true);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('transitionend', schedulePosition, true);
    updateLaunch();
    renderStep();
  }
  launch.addEventListener('click', start);
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    if (active) persist('paused');
    active = false;
    stopActiveWork();
    launch.removeEventListener('click', start);
    overlay?.remove();
    if (parentElement.__speedlocalWorkspaceGuideDispose === cleanup) {
      delete parentElement.__speedlocalWorkspaceGuideDispose;
    }
  };
  parentElement.__speedlocalWorkspaceGuideDispose = cleanup;
  return cleanup;
}
