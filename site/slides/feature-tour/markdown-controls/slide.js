import { Slide } from '../../../vividly/runtime/slide.js';

class MarkdownControlsCallout extends HTMLElement {
  connectedCallback() {
    const label = this.getAttribute('label') || 'Note';
    const content = this.textContent.trim();
    this.replaceChildren();

    const heading = document.createElement('strong');
    heading.textContent = label;
    const body = document.createElement('span');
    body.textContent = content;
    this.append(heading, body);
    this.dataset.upgraded = 'true';
  }
}

customElements.define('markdown-controls-callout', MarkdownControlsCallout);

export const meta = {
  styles: ['./slide.css'],
};

export default class MarkdownControlsSlide extends Slide {
  async preload() {
    this.markdown = await this.ctx.load('./document.md');
  }

  mount(root) {
    const viewer = document.createElement('vividly-markdown');
    viewer.highlight = true;
    viewer.value = this.markdown;
    root.appendChild(viewer);
  }
}