import { Slide } from '../../vividly/runtime/slide.js';

export const meta = {
  styles: ['./placeholder.css'],
};

export default class DocumentationPlaceholderSlide extends Slide {
  preload() {
    const { title, promise, planned = [], capabilities = [] } = this.ctx.props;
    if (typeof title !== 'string' || typeof promise !== 'string') {
      throw new Error('Documentation placeholder requires title and promise strings');
    }
    if (
      !Array.isArray(planned) ||
      !Array.isArray(capabilities) ||
      [...planned, ...capabilities].some((item) => typeof item !== 'string')
    ) {
      throw new Error('Documentation placeholder lists must contain strings');
    }
    return { steps: 1 };
  }

  mount(root) {
    const { eyebrow = 'Planned', title, promise, planned = [], capabilities = [] } = this.ctx.props;
    const layout = document.createElement('section');
    layout.className = 'docs-placeholder';

    const header = document.createElement('header');
    const label = document.createElement('p');
    label.className = 'docs-placeholder-eyebrow';
    label.textContent = eyebrow;
    const heading = document.createElement('h1');
    heading.textContent = title;
    const summary = document.createElement('p');
    summary.className = 'docs-placeholder-promise';
    summary.textContent = promise;
    header.append(label, heading, summary);

    const details = document.createElement('div');
    details.className = 'docs-placeholder-details';
    if (planned.length > 0) details.append(this.buildList('This passage will include', planned));
    if (capabilities.length > 0) {
      details.append(this.buildList('Vividly capabilities', capabilities));
    }

    const status = document.createElement('p');
    status.className = 'docs-placeholder-status';
    status.textContent = this.ctx.props.status || 'Skeleton placeholder';

    layout.append(header, details, status);
    root.append(layout);
  }

  buildList(title, items) {
    const section = document.createElement('section');
    const heading = document.createElement('h2');
    heading.textContent = title;
    const list = document.createElement('ul');
    for (const item of items) {
      const entry = document.createElement('li');
      entry.textContent = item;
      list.append(entry);
    }
    section.append(heading, list);
    return section;
  }
}
