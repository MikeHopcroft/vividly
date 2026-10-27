const FIT_MODES = new Set(['contain', 'cover', 'fill', 'none', 'scale-down']);

export class VividlyImage extends HTMLElement {
  static observedAttributes = ['src', 'alt', 'fit', 'position'];

  connectedCallback() {
    if (!this._image) {
      this._image = document.createElement('img');
      this._image.addEventListener('load', () => this._handleLoad());
      this._image.addEventListener('error', () => this._handleError());
      this.appendChild(this._image);
    }
    this._sync();
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (!this._image || oldValue === newValue) return;
    if (name === 'src') this._syncSource();
    else this._syncPresentation();
  }

  get src() {
    return this.getAttribute('src') || '';
  }

  set src(value) {
    if (value == null || value === '') this.removeAttribute('src');
    else this.setAttribute('src', value);
  }

  get alt() {
    return this.getAttribute('alt') || '';
  }

  set alt(value) {
    this.setAttribute('alt', value == null ? '' : String(value));
  }

  get fit() {
    const value = this.getAttribute('fit') || 'cover';
    return FIT_MODES.has(value) ? value : 'cover';
  }

  set fit(value) {
    if (value == null || value === '') this.removeAttribute('fit');
    else this.setAttribute('fit', value);
  }

  get position() {
    return this.getAttribute('position') || '50% 50%';
  }

  set position(value) {
    if (value == null || value === '') this.removeAttribute('position');
    else this.setAttribute('position', value);
  }

  _sync() {
    this._syncPresentation();
    this._syncSource();
  }

  _syncPresentation() {
    this._image.alt = this.alt;
    this._image.style.objectFit = this.fit;
    this._image.style.objectPosition = this.position;
  }

  _syncSource() {
    if (this.src) {
      this.setAttribute('aria-busy', 'true');
      this._image.src = this.src;
    } else {
      this.removeAttribute('aria-busy');
      this._image.removeAttribute('src');
    }
  }

  _handleLoad() {
    this.removeAttribute('aria-busy');
    this.dispatchEvent(new CustomEvent('vividly-rendered', { bubbles: true }));
  }

  _handleError() {
    this.removeAttribute('aria-busy');
    const error = new Error(`Cannot load image ${this.src}`);
    this.dispatchEvent(new CustomEvent('vividly-error', { bubbles: true, detail: { error } }));
  }
}