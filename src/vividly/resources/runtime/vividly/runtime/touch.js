const MIN_DISTANCE = 48;
const MAX_DURATION = 1000;
const EDGE_INSET = 24;
const OBSERVATION = {
  subtree: true, childList: true, attributes: true,
  attributeFilter: [
    'hidden', 'data-render-ready', 'data-capture', 'data-keyboard-hints', 'open',
    'class', 'style', 'role', 'href', 'contenteditable', 'draggable', 'aria-modal',
    'data-vividly-touch-ignore',
  ],
};
const IGNORED = [
  '[data-vividly-touch-ignore]', 'a[href]', 'button', 'input', 'select', 'textarea',
  'option', 'label', 'summary', 'audio[controls]', 'video[controls]', 'iframe',
  '[draggable="true"]', '[contenteditable]:not([contenteditable="false"])',
  '[role~="button"]', '[role~="link"]', '[role~="checkbox"]', '[role~="radio"]',
  '[role~="switch"]', '[role~="slider"]', '[role~="spinbutton"]', '[role~="textbox"]',
  '[role~="combobox"]', '[role~="listbox"]', '[role~="option"]', '[role~="menuitem"]',
  '[role~="menuitemcheckbox"]', '[role~="menuitemradio"]', '[role~="tab"]',
  '[role~="treeitem"]', '[role~="grid"]', '[role~="scrollbar"]',
].join(',');

function ignored(element) {
  if (element.matches(IGNORED)) return true;
  const style = getComputedStyle(element);
  return /^(auto|scroll)$/.test(style.overflowX) &&
    element.scrollWidth > element.clientWidth;
}

export class TouchNavigation {
  constructor(presentation) {
    this.presentation = presentation;
    this.pointers = new Set();
    this.surfaces = new Set();
    this.pending = new Set();
    this.shadows = new Set();
    this.controller = new AbortController();
    const { signal } = this.controller;
    const capture = { capture: true, signal };
    this.coarsePointer = matchMedia('(any-pointer: coarse)');
    this.capable = navigator.maxTouchPoints > 0 || this.coarsePointer.matches;
    this.coarsePointer.addEventListener('change', () => {
      this.capable = navigator.maxTouchPoints > 0 || this.coarsePointer.matches;
      this.sync();
    }, { signal });

    this.bar = document.createElement('nav');
    this.bar.className = 'v-touch-navigation';
    this.bar.setAttribute('aria-label', 'Presentation navigation');
    this.bar.hidden = true;
    for (const [label, delta] of [['Previous', -1], ['Next', 1]]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.addEventListener('keydown', (event) => {
        if (event.key === ' ' || event.key === 'Enter') event.stopPropagation();
      }, { signal });
      button.addEventListener('click', (event) => {
        event.stopPropagation();
        if (this.available()) this.navigate(delta);
      }, { signal });
      this.bar.append(button);
    }
    presentation.append(this.bar);

    document.addEventListener('pointerdown', (event) => this.down(event), capture);
    document.addEventListener('pointerup', (event) => this.up(event), capture);
    document.addEventListener('pointercancel', (event) => {
      this.pointers.delete(event.pointerId);
      this.cancel();
    }, capture);
    document.addEventListener('lostpointercapture', (event) => {
      if (this.candidate?.id === event.pointerId) this.cancel();
    }, capture);
    document.addEventListener('click', (event) => {
      if (this.clickPointer === event.pointerId && event.pointerType === 'touch') {
        this.clickPointer = null;
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, capture);
    for (const type of ['scroll', 'contextmenu', 'selectionchange']) {
      document.addEventListener(type, () => this.cancel(), capture);
    }
    for (const type of ['blur', 'pagehide', 'visibilitychange']) {
      const target = type === 'visibilitychange' ? document : window;
      target.addEventListener(type, () => {
        this.cancel();
        this.pointers.clear();
      }, { signal });
    }
    window.addEventListener('resize', () => {
      this.cancel();
      this.sync();
    }, { signal });
    for (const type of ['resize', 'scroll']) {
      window.visualViewport?.addEventListener(type, () => this.cancel(), { signal });
    }
    this.resizeObserver = new ResizeObserver(() => this.updateSurfaces());
    this.observer = new MutationObserver(() => this.sync());
    this.observer.observe(presentation, OBSERVATION);
    this.sync();
  }

  visible() {
    const p = this.presentation;
    return this.capable && !p.hasAttribute('data-capture') &&
      p._catalogView.hidden && p._toc.hidden && !!p._current && !p._stage.hidden;
  }

  available() {
    const p = this.presentation;
    return this.visible() && !this.pending.size && p.hasAttribute('data-render-ready') &&
      p._keyboardHints.hidden && p._keyboardHelp.hidden && p._threadMenu.hidden &&
      !p.querySelector('dialog[open], [aria-modal="true"]:not([hidden])');
  }

  sync() {
    if (this.controller.signal.aborted) return;
    const visible = this.visible();
    if (this.bar.hidden !== !visible) this.bar.hidden = !visible;
    this.presentation.toggleAttribute('data-touch-navigation', visible);
    this.presentation.toggleAttribute('data-touch-capable', this.capable);
    const available = this.available();
    for (const button of this.bar.children) button.disabled = !available;
    if (!available) this.cancel();
    this.updateSurfaces();
  }

  blockUntil(promise) {
    this.pending.add(promise);
    this.sync();
    const release = () => {
      this.pending.delete(promise);
      this.sync();
    };
    promise.then(release, release);
  }

  updateSurfaces() {
    const root = this.visible() ? this.presentation._current.root : null;
    if (root !== this.observedRoot) {
      this.observer.disconnect();
      this.observer.observe(this.presentation, OBSERVATION);
      this.shadows.clear();
    }
    const next = new Set();
    const observed = new Set();
    const visit = (element) => {
      observed.add(element);
      if (ignored(element)) return false;
      if (element.shadowRoot && !this.shadows.has(element.shadowRoot)) {
        this.observer.observe(element.shadowRoot, OBSERVATION);
        this.shadows.add(element.shadowRoot);
      }
      const children = [...element.children, ...element.shadowRoot?.children || []];
      let safe = true;
      for (const child of children) {
        if (!visit(child)) safe = false;
      }
      if (safe) {
        for (const child of children) next.delete(child);
        next.add(element);
      }
      return safe;
    };
    if (root) visit(root);
    for (const element of this.surfaces) {
      if (!next.has(element)) element.removeAttribute('data-vividly-touch-surface');
    }
    for (const element of next) {
      if (!this.surfaces.has(element)) element.setAttribute('data-vividly-touch-surface', '');
    }
    this.surfaces = next;
    if (this.observedRoot !== root ||
        observed.size !== this.observed?.size ||
        [...observed].some((element) => !this.observed?.has(element))) {
      this.resizeObserver.disconnect();
      for (const element of observed) this.resizeObserver.observe(element);
      this.observed = observed;
      this.observedRoot = root;
    }
    if (this.candidate && !this.eligible(this.candidate.path)) this.cancel();
  }

  eligible(path) {
    const root = this.presentation._current?.root;
    const boundary = path.indexOf(root);
    if (boundary < 0) return false;
    const elements = path.slice(0, boundary + 1).filter((node) => node instanceof Element);
    return elements.some((element) => this.surfaces.has(element)) &&
      elements.every((element) => !ignored(element));
  }

  zoomed() {
    return (window.visualViewport?.scale ?? 1) > 1;
  }

  down(event) {
    this.clickPointer = null;
    if (event.pointerType !== 'touch') return;
    this.pointers.add(event.pointerId);
    this.cancel();
    if (this.pointers.size !== 1 || !event.isPrimary || !this.available() || this.zoomed()) {
      return;
    }
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft ?? 0;
    const top = viewport?.offsetTop ?? 0;
    const width = viewport?.width ?? innerWidth;
    const height = viewport?.height ?? innerHeight;
    const x = event.clientX - left;
    const y = event.clientY - top;
    if (Math.min(x, y, width - x, height - y) < EDGE_INSET) return;
    const path = event.composedPath();
    if (!this.eligible(path) || !getSelection()?.isCollapsed) return;
    this.candidate = {
      id: event.pointerId, x: event.clientX, y: event.clientY, at: event.timeStamp,
      generation: this.presentation._renderGeneration, hash: location.hash, path,
    };
    this.timer = setTimeout(() => this.cancel(), MAX_DURATION + 1);
  }

  up(event) {
    this.pointers.delete(event.pointerId);
    const candidate = this.candidate;
    this.cancel();
    if (!candidate || candidate.id !== event.pointerId || !this.available() ||
        this.zoomed() || candidate.generation !== this.presentation._renderGeneration ||
        candidate.hash !== location.hash || !this.eligible(candidate.path)) return;
    const dx = event.clientX - candidate.x;
    const dy = event.clientY - candidate.y;
    const duration = event.timeStamp - candidate.at;
    if (duration < 0 || duration > MAX_DURATION ||
        Math.abs(dx) < MIN_DISTANCE || Math.abs(dx) < 2 * Math.abs(dy)) return;
    this.clickPointer = event.pointerId;
    this.navigate(dx < 0 ? 1 : -1);
  }

  navigate(delta) {
    this.cancel();
    this.presentation._advance(delta).then(() => {
      const active = document.activeElement;
      if (active instanceof HTMLElement && active.closest('.v-layer[hidden]')) active.blur();
    }).catch((error) => console.error('[vividly]', error));
  }

  cancel() {
    clearTimeout(this.timer);
    this.candidate = null;
  }

  dispose() {
    this.cancel();
    this.controller.abort();
    this.observer.disconnect();
    this.resizeObserver.disconnect();
    for (const element of this.surfaces) element.removeAttribute('data-vividly-touch-surface');
    this.surfaces.clear();
    this.pointers.clear();
    this.pending.clear();
    this.shadows.clear();
    this.observed?.clear();
    this.observedRoot = null;
    this.clickPointer = null;
    this.bar.remove();
    this.presentation.removeAttribute('data-touch-navigation');
    this.presentation.removeAttribute('data-touch-capable');
  }
}
