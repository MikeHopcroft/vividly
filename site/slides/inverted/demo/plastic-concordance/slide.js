import { Slide } from '../../../../vividly/runtime/slide.js';
import { loadLibreCaslonText } from '../../../../shared/libre-caslon-text.js';

export const meta = {
  styles: ['./slide.css'],
};

const escapeHtml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

const abbreviateHeadword = (headword) => {
  const clean = headword.replace(/\s*\(.*$/, '');
  return clean.length > 9 ? `${clean.slice(0, 7)}.` : clean;
};

const lineTemplate = (line, word) => `
  <div class="line">
    <span class="headword">${escapeHtml(abbreviateHeadword(line.hw))}</span>
    <span class="context">${escapeHtml(line.left)}<strong>${escapeHtml(word[0])}.</strong>${escapeHtml(line.right.replace(/^\./, ''))}</span>
    <span class="reference">${escapeHtml(line.ref)}</span>
  </div>
`;

const blockTemplate = (block) => {
  const count = block.continuedFromPrevPage
    ? '<small><i>continued</i></small>'
    : `<small>(${block.count})</small>`;
  const continuation = block.continuesOnNextPage
    ? '<div class="continuation">(continued)</div>'
    : '';

  return `
    <section class="block${block.target ? ' target' : ''}" data-word="${escapeHtml(block.word)}">
      <h2>${escapeHtml(block.word)} ${count}</h2>
      ${block.lines.map((line) => lineTemplate(line, block.word)).join('')}
      ${continuation}
    </section>
  `;
};

export default class ConcordancePage extends Slide {
  async preload() {
    [this.page] = await Promise.all([
      this.ctx.load('./data/plastic.json'),
      loadLibreCaslonText(this.ctx),
    ]);
    return { steps: 2 };
  }

  mount(root) {
    root.innerHTML = `
      <div class="page-frame">
        <article class="sheet" aria-label="Concordance page ${this.page.concordancePage}">
          <header>
            <span>${escapeHtml(this.page.guideLeft)}</span>
            <strong>${this.page.concordancePage}</strong>
            <span>${escapeHtml(this.page.guideRight)}</span>
          </header>
          <div class="columns">
            ${this.page.blocks.map(blockTemplate).join('')}
          </div>
        </article>
      </div>
    `;

    this.root = root;
    this.sheet = root.querySelector('.sheet');
    this.pageNumber = root.querySelector('header strong');
    this.fictor = [...root.querySelectorAll('.headword')]
      .find((element) => element.textContent.trim().toLowerCase() === 'fictor');
    this.resizeObserver = new ResizeObserver(() => this.updateFocus());
    this.resizeObserver.observe(root);
    this.updateFocus();
  }

  updateFocus() {
    const transform = getComputedStyle(this.sheet).transform;
    const currentScale = new DOMMatrixReadOnly(transform).a;
    const sheetRect = this.sheet.getBoundingClientRect();
    const numberRect = this.pageNumber.getBoundingClientRect();
    const fictorRect = this.fictor.getBoundingClientRect();
    const numberTop = (numberRect.top - sheetRect.top) / currentScale;
    const fictorBottom = (fictorRect.bottom - sheetRect.top) / currentScale;
    const margin = 8;
    const focusScale = (this.root.clientHeight - (margin * 2))
      / (fictorBottom - numberTop);
    const focusTop = margin - (numberTop * focusScale);

    this.root.style.setProperty('--focus-scale', focusScale);
    this.root.style.setProperty('--focus-top', `${focusTop}px`);
  }

  unmount() {
    this.resizeObserver.disconnect();
  }
}
