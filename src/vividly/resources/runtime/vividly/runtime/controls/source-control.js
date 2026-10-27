export class SourceControl extends HTMLElement {
  connectedCallback() {
    if (!this._initialized) {
      this._initialized = true;
      this._value ??= this.textContent || '';
    }
    this._connected = true;
    if (this.hasAttribute('src')) {
      this._loadSource();
    } else {
      this._renderCurrent();
    }
  }

  disconnectedCallback() {
    this._connected = false;
    this._abortController?.abort();
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (!this._connected || oldValue === newValue) return;
    if (name === 'src') {
      if (newValue) this._loadSource();
      else {
        this._abortController?.abort();
        this._abortController = null;
        this._sourceUrl = null;
        this.removeAttribute('aria-busy');
        this._renderCurrent();
      }
      return;
    }
    this.controlAttributeChanged(name);
  }

  get src() {
    return this.getAttribute('src') || '';
  }

  get copyable() {
    return !this.hasAttribute('no-copy');
  }

  set copyable(value) {
    this.toggleAttribute('no-copy', !value);
  }

  set src(value) {
    if (value == null || value === '') this.removeAttribute('src');
    else this.setAttribute('src', value);
  }

  get value() {
    return this._value || '';
  }

  set value(value) {
    this._sourceUrl = null;
    this._value = value == null ? '' : String(value);
    if (this.hasAttribute('src')) this.removeAttribute('src');
    else if (this._connected) this._renderCurrent();
  }

  controlAttributeChanged() {
    this._renderCurrent();
  }

  async _loadSource() {
    this._abortController?.abort();
    const controller = new AbortController();
    this._abortController = controller;
    this.setAttribute('aria-busy', 'true');

    try {
      const response = await fetch(this.src, { signal: controller.signal });
      if (!response.ok) throw new Error(`Cannot load ${response.url || this.src}`);
      const value = await response.text();
      if (controller !== this._abortController) return;
      this._value = value;
      this._sourceUrl = response.url;
      this._renderCurrent();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      if (controller === this._abortController) this.removeAttribute('aria-busy');
      this._renderError(error);
      this.dispatchEvent(
        new CustomEvent('vividly-error', { bubbles: true, detail: { error } })
      );
    } finally {
      if (controller === this._abortController) this.removeAttribute('aria-busy');
    }
  }

  _renderCurrent() {
    try {
      this.renderValue(this.value);
      this.dispatchEvent(new CustomEvent('vividly-rendered', { bubbles: true }));
    } catch (error) {
      this._renderError(error);
      this.dispatchEvent(
        new CustomEvent('vividly-error', { bubbles: true, detail: { error } })
      );
    }
  }

  _renderError(error) {
    this.replaceChildren();
    const message = document.createElement('p');
    message.className = 'v-control-error';
    message.setAttribute('role', 'alert');
    message.textContent = error instanceof Error ? error.message : String(error);
    this.appendChild(message);
  }
}