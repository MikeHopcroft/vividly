import { countAnnotations } from '../runtime/controls/render.js';
import { Slide } from '../runtime/slide.js';

export default class AnnotatedMarkdownSlide extends Slide {
  async preload() {
    const source = this.ctx.props.src || './document.md';
    this.documentUrl = this.ctx.asset(source);
    this.markdown = await this.ctx.load(source);
    return { steps: Math.max(1, countAnnotations(this.markdown)) };
  }

  mount(root) {
    this.viewer = document.createElement('vividly-annotated-markdown');
    this.viewer.highlight = this.ctx.props.highlight !== false;
    this.viewer.baseUrl = this.documentUrl;
    this.viewer.value = this.markdown;
    this.viewer.addEventListener('vividly-annotation-change', (event) => {
      const index = event.detail.index;
      if (index !== this._step) this.ctx.navigate(this.ctx.address, index);
    });
    root.appendChild(this.viewer);
  }

  enter() {
    this._entered = true;
    this._arriving = true;
  }

  setStep(step) {
    this._step = step;
    if (this._entered) {
      this.viewer.revealAnnotation(step, {
        behavior: this._arriving ? 'instant' : 'smooth',
      });
    } else {
      this.viewer.activeAnnotation = step;
    }
    this._arriving = false;
  }

  exit() {
    this._entered = false;
  }

  unmount() {
    this.viewer = null;
  }
}