import { Slide } from '../../vividly/runtime/slide.js';

export const meta = {
  styles: ['./slide.css'],
};

export default class NavigationSequenceSlide extends Slide {
  mount(root) {
    const { label, section, heading, detail } = this.ctx.props;

    const layout = document.createElement('section');
    layout.className = 'navigation-sequence';
    layout.dataset.section = section || 'boundary';

    const marker = document.createElement('p');
    marker.className = 'navigation-sequence-marker';
    marker.textContent = label;

    const copy = document.createElement('div');
    copy.className = 'navigation-sequence-copy';

    const eyebrow = document.createElement('p');
    eyebrow.className = 'navigation-sequence-eyebrow';
    eyebrow.textContent = section ? `Section ${section}` : 'Presentation spine';

    const title = document.createElement('h2');
    title.textContent = heading;

    const description = document.createElement('p');
    description.className = 'navigation-sequence-detail';
    description.textContent = detail;

    copy.append(eyebrow, title, description);
    layout.append(marker, copy);
    root.append(layout);
  }
}