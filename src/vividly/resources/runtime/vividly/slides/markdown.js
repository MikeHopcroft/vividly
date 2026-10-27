import { Slide } from '../runtime/slide.js';

export const meta = {
  styles: ['./markdown.css'],
};

export default class MarkdownSlide extends Slide {
  async preload() {
    const source = this.ctx.props.src || './document.md';
    this.documentUrl = this.ctx.asset(source);
    this.markdown = await this.ctx.load(source);
  }

  mount(root) {
    this.viewer = document.createElement('vividly-markdown');
    this.viewer.highlight = this.ctx.props.highlight !== false;
    this.viewer.baseUrl = this.documentUrl;
    this.viewer.value = this.markdown;
    root.appendChild(this.viewer);
  }

  unmount() {
    this.viewer = null;
  }
}
