import { Slide } from '../../vividly/runtime/slide.js';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 3,
};

export default class PublicHomeSlide extends Slide {
  async preload() {
    const version = await this.ctx.load('../../vividly/version.txt');
    if (typeof version !== 'string' || version.trim() === '') {
      throw new Error('Vividly framework version must be a non-empty string');
    }
    this.version = version.trim();
  }

  mount(root) {
    const label = root.querySelector('[data-public-home-version]');
    if (!label) throw new Error('Public home version label is missing');
    label.textContent = `Vividly framework ${this.version}`;
  }
}
