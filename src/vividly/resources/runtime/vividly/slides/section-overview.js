import { Slide } from '../runtime/slide.js';
import {
  animateLogo,
  cancelLogoAnimation,
  prefersStaticLogo,
  showCompletedLogo,
} from './logo-animation.js';

export const meta = {
  styles: ['./section-overview.css'],
};

export default class SectionOverviewSlide extends Slide {
  async preload() {
    if (!this.ctx.navigator) throw new Error('Section overview must be a navigator');
    this.logoSource = await this.ctx.load('../assets/logo.svg');
    return { steps: this.ctx.navigator.afterStep + 1 };
  }

  mount(root) {
    this.root = root;

    const layout = document.createElement('section');
    layout.className = 'section-overview';

    const logoDocument = new DOMParser().parseFromString(this.logoSource, 'image/svg+xml');
    const logo = document.importNode(logoDocument.documentElement, true);
    logo.setAttribute('class', 'section-overview-logo');
    logo.removeAttribute('width');
    logo.removeAttribute('height');
    logo.setAttribute('role', 'button');
    logo.setAttribute('aria-label', 'Replay Vividly logo animation');
    logo.setAttribute('tabindex', '0');
    logo.setAttribute('title', 'Replay logo animation');
    logo.addEventListener('click', () => this.playLogoAnimation());
    logo.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      event.stopPropagation();
      this.playLogoAnimation();
    });
    this.logo = logo;

    const introduction = document.createElement('div');
    introduction.className = 'section-overview-introduction';
    introduction.innerHTML = `
      <p>Vividly is a toolkit for building, previewing, and publishing interactive web presentations.</p>
      <p>Each presentation is a portable web application, giving authors the reach of the web without giving up precise, slide-by-slide storytelling.</p>
    `;

    const heading = document.createElement('h2');
    heading.className = 'section-overview-heading';
    heading.textContent = 'Explore the documentation';

    this.sectionList = document.createElement('div');
    this.sectionList.className = 'section-overview-sections';
    this.sectionButtons = this.ctx.navigator.sections.map((section, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'section-overview-section';
      button.dataset.vividlyNavigatorChoice = index;
      button.innerHTML = `
        <span class="section-overview-ordinal">${String(index + 1).padStart(2, '0')}</span>
        <span class="section-overview-title"></span>
        <span class="section-overview-action">Open section</span>
      `;
      button.querySelector('.section-overview-title').textContent = section.title;
      this.sectionList.append(button);
      return button;
    });

    layout.append(logo, introduction, heading, this.sectionList);
    root.append(layout);
  }

  enter() {
    if (this.hasPlayedLogoAnimation || prefersStaticLogo(this.root)) {
      this.showCompletedLogo();
      return;
    }

    this.hasPlayedLogoAnimation = true;
    this.playLogoAnimation();
  }

  playLogoAnimation() {
    if (prefersStaticLogo(this.root)) {
      this.showCompletedLogo();
      return;
    }

    animateLogo(this.logo);
  }

  exit() {
    this.cancelLogoAnimations();
    this.showCompletedLogo();
  }

  cancelLogoAnimations() {
    cancelLogoAnimation(this.logo);
  }

  showCompletedLogo() {
    showCompletedLogo(this.logo);
  }

  setStep(step) {
    this.sectionButtons.forEach((button, index) => {
      const active = this.ctx.navigator.sections[index].step === step;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-current', active ? 'step' : 'false');
    });
  }

  unmount() {
    this.cancelLogoAnimations();
    this.root = null;
    this.logo = null;
    this.logoSource = null;
    this.sectionList = null;
    this.sectionButtons = null;
  }
}
