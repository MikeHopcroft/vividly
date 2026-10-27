// Image slide: a grid where the current step highlights one tile. Highlight is
// pure CSS via the kit's .v-at primitive; JS only builds the grid.

import { Slide } from '../../vividly/runtime/slide.js';

export const meta = {
  styles: ['./slide.css'],
};

const IMAGES = [
  { src: 'aurora', label: 'Aurora' },
  { src: 'canyon', label: 'Canyon' },
  { src: 'harbor', label: 'Harbor' },
  { src: 'dunes', label: 'Dunes' },
  { src: 'glacier', label: 'Glacier' },
  { src: 'orchard', label: 'Orchard' },
];

export default class ContactSheet extends Slide {
  async preload() {
    return { steps: IMAGES.length };
  }

  mount(root) {
    root.innerHTML = `
      <h2 class="sheet-heading">Contact Sheet</h2>
      <div class="sheet-grid">
        ${IMAGES.map(
          (img, i) => `
          <figure class="sheet-tile v-at" style="--at: ${i}" data-index="${i}">
            <img src="${this.ctx.asset(`../../vividly/assets/demo/${img.src}.svg`)}" alt="${img.label}">
            <figcaption>${img.label}</figcaption>
          </figure>`
        ).join('')}
      </div>
    `;

    root.addEventListener('click', (e) => {
      const tile = e.target.closest('.sheet-tile');
      if (tile) this.ctx.navigate(this.ctx.address, Number(tile.dataset.index));
    });
  }
}
