import { Slide } from '../runtime/slide.js';

export default class ImageSlide extends Slide {
  preload() {
    const { images, src, alt, fit, position } = this.ctx.props;
    if (images !== undefined && src !== undefined) {
      throw new Error('Image slide props may specify either images or src, not both');
    }

    this.images = images ?? (src ? [{ src, alt, fit, position }] : []);
    if (!Array.isArray(this.images) || this.images.length === 0) {
      throw new Error('Image slide props must specify src or a non-empty images array');
    }
    this.defaults = { alt, fit, position };
    return { steps: this.images.length };
  }

  mount(root) {
    this.image = document.createElement('vividly-image');
    root.appendChild(this.image);
  }

  setStep(step) {
    const entry = typeof this.images[step] === 'string' ? { src: this.images[step] } : this.images[step];
    if (!entry?.src) throw new Error(`Image slide entry ${step} must specify src`);

    this.image.alt = entry.alt ?? this.defaults.alt ?? '';
    this.image.fit = entry.fit ?? this.defaults.fit ?? 'cover';
    this.image.position = entry.position ?? this.defaults.position ?? '50% 50%';
    this.image.src = this.ctx.asset(entry.src);
  }

  unmount() {
    this.image = null;
  }
}