import { Slide } from '../../vividly/runtime/slide.js';

export const meta = {
  styles: ['./slide.css'],
};

const SLIDES = [
  ['B1', 'B2', 'B3'],
  ['C1', 'C2'],
  ['D1', 'D2'],
];

export default class SequenceNavigatorSlide extends Slide {
  preload() {
    if (!this.ctx.navigator) throw new Error('Sequence navigator requires navigator sections');
    if (this.ctx.navigator.sections.length !== SLIDES.length) {
      throw new Error('Sequence navigator requires B, C, and D sections');
    }
    return { steps: this.ctx.navigator.afterStep + 1 };
  }

  mount(root) {
    const layout = document.createElement('section');
    layout.className = 'sequence-navigator';
    layout.innerHTML = `
      <header class="sequence-navigator-header">
        <p>Navigation slide N</p>
        <h2>One key, the whole presentation</h2>
      </header>
      <div class="sequence-navigator-spine" aria-label="Navigation sequences"></div>
      <p class="sequence-navigator-completion">All sections complete <span>Continue to S2</span></p>
    `;

    const spine = layout.querySelector('.sequence-navigator-spine');
    this.rows = this.ctx.navigator.sections.map((section, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'sequence-navigator-row';
      button.dataset.vividlyNavigatorChoice = index;
      button.innerHTML = `
        <span class="sequence-navigator-section"></span>
        <span class="sequence-navigator-slides"></span>
        <span class="sequence-navigator-enter">Next</span>
      `;
      button.querySelector('.sequence-navigator-section').textContent = section.title;
      const slides = button.querySelector('.sequence-navigator-slides');
      for (const label of SLIDES[index]) {
        const item = document.createElement('span');
        item.textContent = label;
        slides.append(item);
      }
      button.addEventListener('click', async () => {
        await this.ctx.navigate(this.ctx.address, index);
        await this.ctx.enterSection();
      });
      spine.append(button);
      return button;
    });

    this.completion = layout.querySelector('.sequence-navigator-completion');
    root.append(layout);
  }

  setStep(step) {
    this.rows.forEach((row, index) => {
      const active = index === step;
      row.classList.toggle('is-active', active);
      row.setAttribute('aria-current', active ? 'step' : 'false');
    });
    this.completion.classList.toggle('is-active', step === this.ctx.navigator.afterStep);
  }

  unmount() {
    this.rows = null;
    this.completion = null;
  }
}