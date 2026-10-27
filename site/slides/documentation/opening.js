import { Slide } from '../../vividly/runtime/slide.js';
import {
  animateLogo,
  cancelLogoAnimation,
  prefersStaticLogo,
  showCompletedLogo,
} from '../../vividly/slides/logo-animation.js';

export const meta = {
  styles: ['./opening.css'],
};

export default class DocumentationOpeningSlide extends Slide {
  async preload() {
    this.logoSource = await this.ctx.load('../../vividly/assets/logo.svg');
    if (!this.ctx.navigator) throw new Error('Documentation opening requires navigator sections');
    const descriptions = this.ctx.props.descriptions || [];
    if (!Array.isArray(descriptions)) {
      throw new Error('Documentation opening descriptions must be an array');
    }
    if (descriptions.length !== this.ctx.navigator.sections.length) {
      throw new Error('Documentation opening descriptions must match navigator sections');
    }
    if (descriptions.some((description) => typeof description !== 'string')) {
      throw new Error('Documentation opening descriptions must be strings');
    }
    this.descriptions = descriptions;
    return { steps: this.ctx.navigator.afterStep + 1 };
  }

  mount(root) {
    this.root = root;
    const layout = document.createElement('section');
    layout.className = 'docs-opening';

    const logoDocument = new DOMParser().parseFromString(this.logoSource, 'image/svg+xml');
    this.logo = document.importNode(logoDocument.documentElement, true);
    this.logo.classList.add('docs-opening-logo');
    this.logo.removeAttribute('width');
    this.logo.removeAttribute('height');
    this.logo.setAttribute('aria-label', 'Vividly');

    const message = document.createElement('header');
    message.className = 'docs-opening-message';
    const subtitle = document.createElement('h1');
    subtitle.textContent = this.ctx.props.subtitle || 'Making complex ideas move.';
    const tagline = document.createElement('p');
    tagline.className = 'docs-opening-tagline';
    tagline.textContent =
      this.ctx.props.description ||
      'Human-authored. Agent-implemented. Presentations built as code.';
    message.append(subtitle, tagline);
    this.message = message;

    const choices = document.createElement('div');
    choices.className = 'docs-opening-choices';
    const mobileDescriptions = [
      'See what makes this different.',
      'Explore interactive examples.',
      'Make your first presentation.',
    ];
    this.cards = this.ctx.navigator.sections.map((section, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'docs-opening-choice';
      button.dataset.vividlyNavigatorChoice = index;

      const ordinal = document.createElement('span');
      ordinal.className = 'docs-opening-choice-ordinal';
      ordinal.textContent = String(index + 1).padStart(2, '0');
      const title = document.createElement('span');
      title.className = 'docs-opening-choice-title';
      title.textContent = section.title;
      const description = document.createElement('span');
      description.className = 'docs-opening-choice-description docs-opening-desktop';
      description.textContent = this.descriptions[index];
      const mobileDescription = document.createElement('span');
      mobileDescription.className = 'docs-opening-choice-description docs-opening-mobile';
      mobileDescription.textContent = mobileDescriptions[index] ?? this.descriptions[index];
      const action = document.createElement('span');
      action.className = 'docs-opening-choice-action';
      const desktopAction = document.createElement('span');
      desktopAction.className = 'docs-opening-desktop';
      desktopAction.textContent = 'Open';
      const mobileAction = document.createElement('span');
      mobileAction.className = 'docs-opening-mobile';
      mobileAction.textContent = '→';
      mobileAction.setAttribute('aria-hidden', 'true');
      action.append(desktopAction, mobileAction);

      button.append(ordinal, action, title, description, mobileDescription);
      choices.append(button);
      return button;
    });

    const resources = document.createElement('p');
    resources.className = 'docs-opening-resources';
    resources.append('Looking for a specific answer? ');
    const documentation = document.createElement('a');
    documentation.href = '#/vividly/documentation/overview';
    documentation.textContent = 'Documentation →';
    resources.append(documentation);

    layout.append(this.logo, message, choices, resources);
    root.append(layout);
    this.layout = layout;
    this.mobileLayout = window.matchMedia('(max-width: 900px)');
    this.onLayoutChange = () => {
      if (!this.mobileLayout.matches) return;
      this.layout.classList.remove('is-animated');
      cancelLogoAnimation(this.logo);
      showCompletedLogo(this.logo);
    };
    this.mobileLayout.addEventListener('change', this.onLayoutChange);
  }

  enter({ direction, step, restoring }) {
    cancelLogoAnimation(this.logo);
    this.layout.classList.remove('is-animated');
    this.layout.classList.add('is-complete');

    if (
      step !== this.ctx.navigator.choiceStartStep ||
      direction !== 'forward' ||
      restoring ||
      this.mobileLayout.matches ||
      prefersStaticLogo(this.root)
    ) {
      showCompletedLogo(this.logo);
      return;
    }

    void this.layout.offsetWidth;
    animateLogo(this.logo);
    this.layout.classList.add('is-animated');
  }

  setStep(step) {
    if (step !== this.ctx.navigator.choiceStartStep) {
      this.layout?.classList.remove('is-animated');
      cancelLogoAnimation(this.logo);
      showCompletedLogo(this.logo);
    }
    this.cards?.forEach((card, index) => {
      const active = this.ctx.navigator.sections[index].step === step;
      card.classList.toggle('is-active', active);
      card.setAttribute('aria-current', active ? 'step' : 'false');
    });
  }

  exit() {
    cancelLogoAnimation(this.logo);
    showCompletedLogo(this.logo);
    this.layout.classList.remove('is-animated', 'is-complete');
  }

  unmount() {
    this.mobileLayout.removeEventListener('change', this.onLayoutChange);
    cancelLogoAnimation(this.logo);
    this.mobileLayout = null;
    this.onLayoutChange = null;
    this.root = null;
    this.logo = null;
    this.logoSource = null;
    this.layout = null;
    this.message = null;
    this.cards = null;
    this.descriptions = null;
  }
}
