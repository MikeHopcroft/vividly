// Image slide: data-driven step count, filmstrip advanced entirely by CSS
// reading --step. No setStep implementation is needed.

import { Slide } from '../../../vividly/runtime/slide.js';

export const meta = {
  styles: ['./slide.css'],
};

export default class PhotoTour extends Slide {
  async preload() {
    const data = await this.ctx.load('./data/photos.yaml');
    this.heading = this.ctx.props.heading || data.heading;
    this.photos = data.photos;
    return { steps: this.photos.length };
  }

  mount(root) {
    root.innerHTML = `
      <h2 class="tour-heading">${esc(this.heading)}</h2>
      <div class="tour-viewport">
        <div class="tour-strip">
          ${this.photos.map((p) => this._frame(p)).join('')}
        </div>
      </div>
      <div class="tour-progress"><span class="tour-progress-thumb"></span></div>
    `;
  }

  _frame(photo) {
    return `
      <figure class="tour-frame v-figure">
        <img src="${esc(this.ctx.asset(photo.src))}" alt="${esc(photo.alt)}">
        <figcaption>
          <strong>${esc(photo.title)}</strong>
          <span class="v-caption">${esc(photo.caption)}</span>
        </figcaption>
      </figure>`;
  }
}

function esc(value) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
  );
}
