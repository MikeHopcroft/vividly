import { SourceControl } from './source-control.js';
import { highlightSource } from './render.js';
import { createCodeCopyTools } from './code-copy.js';

export class VividlyCode extends SourceControl {
  static observedAttributes = ['src', 'language', 'highlight-lines', 'active-line', 'no-copy'];

  get language() {
    return this.getAttribute('language') || '';
  }

  set language(value) {
    if (value == null || value === '') this.removeAttribute('language');
    else this.setAttribute('language', value);
  }

  get highlightLines() {
    return this.getAttribute('highlight-lines') ?? '';
  }

  set highlightLines(value) {
    const selection = Array.isArray(value) ? value.join(',') : String(value ?? '');
    if (selection) this.setAttribute('highlight-lines', selection);
    else this.removeAttribute('highlight-lines');
  }

  get activeLine() {
    const value = Number(this.getAttribute('active-line'));
    return Number.isInteger(value) && value > 0 ? value : -1;
  }

  set activeLine(value) {
    const line = Number(value);
    if (Number.isInteger(line) && line > 0) this.setAttribute('active-line', line);
    else this.removeAttribute('active-line');
  }

  controlAttributeChanged(name) {
    if (name === 'language') this._renderCurrent();
    else if (name === 'no-copy') this._syncCopyTools();
    else this._updateLineMarkers();
  }

  renderValue(value) {
    const lineCount = value.split('\n').length;

    this.replaceChildren();
    this._scroll = document.createElement('div');
    this._scroll.className = 'v-code-scroll';

    const frame = document.createElement('div');
    frame.className = 'v-code-frame';

    const gutter = document.createElement('div');
    gutter.className = 'v-code-gutter';
    gutter.setAttribute('aria-hidden', 'true');
    for (let line = 1; line <= lineCount; line += 1) {
      const number = document.createElement('span');
      number.textContent = String(line);
      gutter.appendChild(number);
    }

    const pre = document.createElement('pre');
    this._code = document.createElement('code');
    this._code.className = `hljs${this.language ? ` language-${this.language}` : ''}`;
    this._code.innerHTML = highlightSource(value, this.language);
    pre.appendChild(this._code);

    this._markers = document.createElement('div');
    this._markers.className = 'v-code-markers';
    this._markers.setAttribute('aria-hidden', 'true');

    frame.append(this._markers, gutter, pre);
    this._scroll.appendChild(frame);
    this.appendChild(this._scroll);
    this._lineCount = lineCount;
    this._updateLineMarkers();
    this._syncCopyTools();
  }

  _syncCopyTools() {
    this.querySelector(':scope > .v-code-copy-tools')?.remove();
    if (this._code && this.contains(this._code) && this.copyable) {
      this.prepend(createCodeCopyTools(() => this.value));
    }
  }

  revealLine(line, { block = 'nearest', behavior = 'auto' } = {}) {
    if (!this._scroll || !this._code || !this._validLine(line)) return;
    const lineHeight = this._lineHeight();
    const paddingTop = Number.parseFloat(getComputedStyle(this._code).paddingTop) || 0;
    const top = paddingTop + (line - 1) * lineHeight;
    const bottom = top + lineHeight;
    const viewportTop = this._scroll.scrollTop;
    const viewportBottom = viewportTop + this._scroll.clientHeight;
    let target = top;

    if (block === 'center') target = top - (this._scroll.clientHeight - lineHeight) / 2;
    else if (block === 'end') target = bottom - this._scroll.clientHeight;
    else if (block === 'nearest') {
      if (top >= viewportTop && bottom <= viewportBottom) return;
      target = top < viewportTop ? top : bottom - this._scroll.clientHeight;
    }

    this._scroll.scrollTo({ top: Math.max(0, target), behavior: behavior === 'instant' ? 'auto' : behavior });
  }

  _updateLineMarkers() {
    if (!this._markers) return;
    const highlighted = parseLineSelection(this.highlightLines, this._lineCount);
    const active = this.activeLine;
    if (this._validLine(active)) highlighted.add(active);

    this._markers.replaceChildren();
    for (const line of [...highlighted].sort((left, right) => left - right)) {
      const marker = document.createElement('span');
      marker.className = line === active ? 'v-code-line is-active' : 'v-code-line';
      marker.style.setProperty('--line', line - 1);
      this._markers.appendChild(marker);
    }
  }

  _lineHeight() {
    const style = getComputedStyle(this._code);
    const lineHeight = Number.parseFloat(style.lineHeight);
    return Number.isFinite(lineHeight) ? lineHeight : Number.parseFloat(style.fontSize) * 1.5;
  }

  _validLine(line) {
    return Number.isInteger(line) && line >= 1 && line <= this._lineCount;
  }
}

function parseLineSelection(selection, lineCount) {
  const lines = new Set();
  const parts = Array.isArray(selection) ? selection : String(selection).split(',');

  for (const part of parts) {
    if (Number.isInteger(part)) {
      if (part >= 1 && part <= lineCount) lines.add(part);
      continue;
    }

    const match = String(part).trim().match(/^(\d+)(?:-(\d+))?$/);
    if (!match) continue;
    const start = Number(match[1]);
    const end = Number(match[2] || match[1]);
    if (end < start) continue;
    for (let line = start; line <= Math.min(end, lineCount); line += 1) {
      if (line >= 1) lines.add(line);
    }
  }

  return lines;
}