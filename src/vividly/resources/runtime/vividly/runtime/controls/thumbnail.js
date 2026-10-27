const LOADING_MODES = new Set(['lazy', 'eager']);
const STEP_PATTERN = /^\d+$/;

export class VividlyThumbnail extends HTMLElement {
  static observedAttributes = ['address', 'step', 'label', 'fallback', 'loading'];

  connectedCallback() {
    this.classList.add('v-thumbnail');
    this._render();
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (!this.isConnected || oldValue === newValue) return;
    this._render();
  }

  get address() {
    return this.getAttribute('address') || '';
  }

  set address(value) {
    if (value == null || value === '') this.removeAttribute('address');
    else this.setAttribute('address', value);
  }

  get step() {
    const requested = this._requestedStep();
    return requested.valid ? requested.value : null;
  }

  set step(value) {
    if (value == null) this.removeAttribute('step');
    else this.setAttribute('step', value);
  }

  get label() {
    return this.getAttribute('label') || '';
  }

  set label(value) {
    if (value == null || value === '') this.removeAttribute('label');
    else this.setAttribute('label', value);
  }

  get fallback() {
    return this.getAttribute('fallback') || '';
  }

  set fallback(value) {
    if (value == null || value === '') this.removeAttribute('fallback');
    else this.setAttribute('fallback', value);
  }

  get loading() {
    const value = this.getAttribute('loading') || 'lazy';
    return LOADING_MODES.has(value) ? value : 'lazy';
  }

  set loading(value) {
    if (value == null || value === '') this.removeAttribute('loading');
    else this.setAttribute('loading', value);
  }

  _render() {
    const renderToken = {};
    this._renderToken = renderToken;
    const presentation = this.closest('vividly-presentation');
    const requested = this._requestedStep();
    const descriptor =
      requested.valid && presentation?.thumbnailFor
        ? presentation.thumbnailFor(this.address, requested.value ?? undefined)
        : null;
    const resolved = descriptor || presentation?.thumbnailFor?.(this.address) || null;
    const fallback = document.createElement('span');
    fallback.className = 'v-thumbnail-placeholder';
    fallback.textContent =
      this.label || this.fallback || resolved?.title || 'Thumbnail unavailable';
    fallback.setAttribute('aria-hidden', 'true');

    this._syncAccessibility();
    this.removeAttribute('aria-busy');
    this.replaceChildren(fallback);

    if (!descriptor) {
      this.dataset.thumbnailStatus = 'missing';
      queueMicrotask(() => {
        if (this._renderToken === renderToken && this.isConnected) {
          this.dispatchEvent(new CustomEvent('vividly-rendered', { bubbles: true }));
        }
      });
      return;
    }

    this.dataset.thumbnailStatus = 'loading';
    this.setAttribute('aria-busy', 'true');
    const image = document.createElement('img');
    image.alt = '';
    image.loading = this.loading;
    image.dataset.vividlyOptionalImage = '';
    image.addEventListener('load', () => {
      if (this._renderToken !== renderToken || image !== this.firstElementChild) return;
      this.removeAttribute('aria-busy');
      this.dataset.thumbnailStatus = 'ready';
      this.dispatchEvent(new CustomEvent('vividly-rendered', { bubbles: true }));
    });
    image.addEventListener('error', () => {
      if (this._renderToken !== renderToken || image !== this.firstElementChild) return;
      image.remove();
      this.removeAttribute('aria-busy');
      this.dataset.thumbnailStatus = 'missing';
      this.dispatchEvent(new CustomEvent('vividly-rendered', { bubbles: true }));
    });
    image.src = descriptor.src;
    this.prepend(image);
  }

  _requestedStep() {
    const value = this.getAttribute('step');
    if (value === null) return { valid: true, value: null };
    if (!STEP_PATTERN.test(value)) return { valid: false, value: null };
    const step = Number(value);
    return Number.isSafeInteger(step)
      ? { valid: true, value: step }
      : { valid: false, value: null };
  }

  _syncAccessibility() {
    if (this.label) {
      this.removeAttribute('aria-hidden');
      this.setAttribute('role', 'img');
      this.setAttribute('aria-label', this.label);
      return;
    }
    this.setAttribute('aria-hidden', 'true');
    this.removeAttribute('role');
    this.removeAttribute('aria-label');
  }
}
