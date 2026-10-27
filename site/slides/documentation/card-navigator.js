import { Slide } from '../../vividly/runtime/slide.js';

export const meta = {
  styles: ['./card-navigator.css'],
};

export default class CardNavigatorSlide extends Slide {
  preload() {
    const sections = this.ctx.navigator?.sections || [];
    const descriptions = this.ctx.props.descriptions || [];
    if (!Array.isArray(descriptions)) {
      throw new Error('Card navigator descriptions must be an array');
    }
    if (descriptions.length > 0 && descriptions.length !== sections.length) {
      throw new Error('Card navigator descriptions must match navigator sections');
    }
    if (descriptions.some((description) => typeof description !== 'string')) {
      throw new Error('Card navigator descriptions must be strings');
    }
    const images = this.ctx.props.images || [];
    if (!Array.isArray(images)) {
      throw new Error('Card navigator images must be an array');
    }
    if (images.length > 0 && images.length !== sections.length) {
      throw new Error('Card navigator images must match navigator sections');
    }
    const externalCards = this.ctx.props.externalCards || [];
    if (!Array.isArray(externalCards)) {
      throw new Error('Card navigator externalCards must be an array');
    }
    if (
      externalCards.some(
        (card) =>
          !card ||
          typeof card.title !== 'string' ||
          typeof card.description !== 'string' ||
          typeof card.href !== 'string'
      )
    ) {
      throw new Error('Card navigator externalCards require title, description, and href');
    }
    const invalidImage = (image) => typeof image !== 'string' || !image.trim();
    if (images.some(invalidImage) ||
        externalCards.some((card) => card.image !== undefined && invalidImage(card.image))) {
      throw new Error('Card navigator images must be nonempty paths');
    }
    if (sections.length === 0 && externalCards.length === 0) {
      throw new Error('Card navigator requires sections or external cards');
    }
    this.sections = sections;
    this.descriptions = descriptions;
    this.images = images;
    this.externalCards = externalCards;
    return {
      steps: this.ctx.navigator ? this.ctx.navigator.afterStep + 1 : externalCards.length,
    };
  }

  mount(root) {
    const layout = document.createElement('section');
    layout.className = 'card-navigator';

    const header = document.createElement('header');
    header.className = 'card-navigator-header';
    const eyebrow = document.createElement('p');
    eyebrow.className = 'card-navigator-eyebrow';
    eyebrow.textContent = this.ctx.props.eyebrow || 'Explore';
    const heading = document.createElement('h1');
    heading.textContent = this.ctx.props.heading || 'Where would you like to go?';
    header.append(eyebrow, heading);
    if (this.ctx.props.introduction) {
      const introduction = document.createElement('p');
      introduction.className = 'card-navigator-introduction';
      introduction.textContent = this.ctx.props.introduction;
      header.append(introduction);
    }

    const grid = document.createElement('div');
    grid.className = 'card-navigator-grid';
    this.cards = this.sections.map((section, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'card-navigator-card';
      button.dataset.vividlyNavigatorChoice = index;
      this.appendImage(button, this.images[index]);

      const ordinal = document.createElement('span');
      ordinal.className = 'card-navigator-ordinal';
      ordinal.textContent = String(index + 1).padStart(2, '0');
      const title = document.createElement('span');
      title.className = 'card-navigator-title';
      title.textContent = section.title;
      const description = document.createElement('span');
      description.className = 'card-navigator-description';
      description.textContent = this.descriptions[index] || 'Open this section.';
      const action = document.createElement('span');
      action.className = 'card-navigator-action';
      action.textContent = 'Open';

      button.append(ordinal, title, description, action);
      grid.append(button);
      return button;
    });
    this.externalLinks = this.externalCards.map((card, externalIndex) => {
      const link = document.createElement('a');
      link.className = 'card-navigator-card card-navigator-card-external';
      link.href = card.href;
      this.appendImage(link, card.image);

      const ordinal = document.createElement('span');
      ordinal.className = 'card-navigator-ordinal';
      ordinal.textContent = String(this.cards.length + externalIndex + 1).padStart(2, '0');
      const title = document.createElement('span');
      title.className = 'card-navigator-title';
      title.textContent = card.title;
      const description = document.createElement('span');
      description.className = 'card-navigator-description';
      description.textContent = card.description;
      const action = document.createElement('span');
      action.className = 'card-navigator-action';
      action.textContent = 'Open presentation';

      link.append(ordinal, title, description, action);
      if (!this.ctx.navigator) {
        link.addEventListener('focus', () => this.selectExternalCard(externalIndex));
      }
      grid.append(link);
      return link;
    });

    layout.append(header, grid);
    root.append(layout);
    if (!this.ctx.navigator) {
      this.ctx.captureKeys((event) => this.captureExternalCardKey(event));
    }
  }

  appendImage(card, path) {
    if (!path) return;
    card.classList.add('card-navigator-card-with-image');
    const image = document.createElement('img');
    image.className = 'card-navigator-image';
    image.src = this.ctx.asset(path);
    image.alt = '';
    card.append(image);
  }

  setStep(step) {
    this.step = step;
    this.cards.forEach((card, index) => {
      const active = this.sections[index].step === step;
      card.classList.toggle('is-active', active);
      card.setAttribute('aria-current', active ? 'step' : 'false');
    });
    if (!this.ctx.navigator) {
      this.externalLinks.forEach((card, index) => {
        const active = index === step;
        card.classList.toggle('is-active', active);
        card.setAttribute('aria-current', active ? 'step' : 'false');
      });
      if (this.externalLinks.includes(document.activeElement)) {
        this.externalLinks[step].focus();
      }
    }
  }

  selectExternalCard(index, focus = false) {
    const link = this.externalLinks[index];
    if (index === this.step) {
      if (focus) link.focus();
      return;
    }
    this.ctx.navigate(this.ctx.address, index).then(() => {
      if (focus && link.isConnected) link.focus();
    }).catch((error) => {
      console.error('[vividly]', error);
    });
  }

  captureExternalCardKey(event) {
    const focusedIndex = this.externalLinks.indexOf(document.activeElement);
    if (focusedIndex < 0 && event.target instanceof Element &&
        event.target.closest('a, button, input, select, textarea, [contenteditable]')) {
      return false;
    }
    const index = focusedIndex >= 0 ? focusedIndex : this.step;
    if (event.key === 'Enter') {
      this.externalLinks[index].click();
      return true;
    }
    const direction = {
      ArrowRight: 1,
      ArrowDown: 1,
      ArrowLeft: -1,
      ArrowUp: -1,
    }[event.key];
    if (!direction) return false;
    const next = index + direction;
    if (next < 0 || next >= this.externalLinks.length) return false;
    this.selectExternalCard(next, true);
    return true;
  }

  unmount() {
    this.cards = null;
    this.sections = null;
    this.descriptions = null;
    this.images = null;
    this.externalCards = null;
    this.externalLinks = null;
  }
}
