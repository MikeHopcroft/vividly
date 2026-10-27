import { Slide } from 'vividly/runtime/slide.js';
import { loadWhyVividlyFonts } from '../../../shared/why-vividly-fonts.js';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 4,
};

const ASSETS = {
  table: './assets/printmakers-table.jpg',
  woodblock: './assets/woodblock-artifact.jpg',
  type: './assets/movable-type-medium.jpg',
};

export default class ArtifactVersusMedium extends Slide {
  async preload() {
    await loadWhyVividlyFonts(this.ctx);
  }

  mount(root) {
    this.images = [...root.querySelectorAll('[data-woodblock-image]')];
    this.copy = [...root.querySelectorAll('[data-copy-step]')];

    for (const image of this.images) {
      image.src = new URL(ASSETS[image.dataset.woodblockImage], import.meta.url).href;
    }
  }

  setStep(step) {
    this.images.forEach((image) => {
      const imageStep = Number(image.dataset.imageStep);
      const visible = imageStep === step || (imageStep === 2 && step === 3);
      image.setAttribute('aria-hidden', String(!visible));
    });

    this.copy.forEach((element) => {
      element.setAttribute(
        'aria-hidden',
        String(step !== Number(element.dataset.copyStep)),
      );
    });
  }

  unmount() {
    this.images = null;
    this.copy = null;
  }
}
