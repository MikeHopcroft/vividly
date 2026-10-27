import { Slide } from 'vividly/runtime/slide.js';
import { loadWhyVividlyFonts } from '../../../shared/why-vividly-fonts.js';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 3,
};

const ASSETS = {
  director: './assets/director-chair.jpg',
  crew: './assets/production-crew.png',
  soundstage: './assets/soundstage.jpg',
  neon: './assets/vividly-neon.png',
};

export default class Partnership extends Slide {
  async preload() {
    await loadWhyVividlyFonts(this.ctx);
  }

  mount(root) {
    this.root = root;
    this.step = 0;
    this.mobileLayout = window.matchMedia('(max-width: 900px)');
    this.onLayoutChange = () => this.setStep(this.step);
    this.mobileLayout.addEventListener('change', this.onLayoutChange);
    this.cards = [...root.querySelectorAll('[data-partnership-card]')];
    this.phrases = [...root.querySelectorAll('[data-partnership-phrase]')];
    for (const image of root.querySelectorAll('[data-partnership-asset]')) {
      image.src = new URL(ASSETS[image.dataset.partnershipAsset], import.meta.url).href;
    }
  }

  setStep(step) {
    if (step !== this.step) this.root.scrollTop = 0;
    this.step = step;
    const isVisible = (index) => this.mobileLayout.matches ? index === step : index <= step;
    this.cards.forEach((card, index) => {
      const visible = isVisible(index);
      card.classList.toggle('is-visible', visible);
      card.setAttribute('aria-hidden', String(!visible));
      card.inert = !visible;
    });
    this.phrases.forEach((phrase, index) => {
      const visible = isVisible(index);
      phrase.classList.toggle('is-visible', visible);
      phrase.setAttribute('aria-hidden', String(!visible));
    });
  }

  unmount() {
    this.mobileLayout.removeEventListener('change', this.onLayoutChange);
    this.mobileLayout = null;
    this.onLayoutChange = null;
    this.root = null;
    this.cards = null;
    this.phrases = null;
  }
}
