import { createAdvanceButton } from './advance.js';

export class VividlyStepProgress extends HTMLElement {
  static observedAttributes = ['value', 'label', 'advance'];

  connectedCallback() {
    if (!this._track) {
      this._track = document.createElement('div');
      this._track.className = 'v-step-progress-track';
      this._track.setAttribute('role', 'progressbar');
      this._track.setAttribute('aria-valuemin', '0');
      this._track.setAttribute('aria-valuemax', '100');
      this._fill = document.createElement('span');
      this._fill.className = 'v-step-progress-fill';
      this._track.append(this._fill);
      this._button = createAdvanceButton(this);
      this._button.className = 'v-step-progress-advance';
      this._button.textContent = 'Advance →';
      this._error = document.createElement('p');
      this._error.className = 'v-control-error';
      this.replaceChildren(this._track, this._button, this._error);
    }
    this._render();
  }

  attributeChangedCallback(_name, oldValue, newValue) {
    if (this._track && oldValue !== newValue) this._render();
  }

  get value() {
    const source = this.getAttribute('value');
    const value = source === null ? 0 : Number(source);
    if ((source !== null && !source.trim()) || !Number.isFinite(value)) {
      throw new TypeError('Step progress value must be a finite number.');
    }
    return Math.min(1, Math.max(0, value));
  }

  set value(value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw new TypeError('Step progress value must be a finite number.');
    }
    this.setAttribute('value', String(Math.min(1, Math.max(0, value))));
  }

  get label() {
    return this.getAttribute('label') || 'Step readiness';
  }

  set label(value) {
    if (value == null || value === '') this.removeAttribute('label');
    else this.setAttribute('label', value);
  }

  get advance() {
    return this.hasAttribute('advance');
  }

  set advance(value) {
    this.toggleAttribute('advance', Boolean(value));
  }

  _render() {
    let value;
    try {
      value = this.value;
    } catch (error) {
      this._track.hidden = true;
      this._button.disabled = true;
      this._button.style.visibility = 'hidden';
      this._error.hidden = false;
      this._error.textContent = error.message;
      this.dispatchEvent(new CustomEvent('vividly-error', {
        bubbles: true, detail: { error },
      }));
      return;
    }
    const percent = Math.round(value * 100);
    this._error.hidden = true;
    this._track.hidden = false;
    this._track.setAttribute('aria-label', this.label);
    this._track.setAttribute('aria-valuenow', String(percent));
    this._track.setAttribute('aria-valuetext', value === 1 ? 'Ready' : `${percent}%`);
    this._fill.style.transform = `scaleX(${value})`;
    const ready = this.advance && value === 1;
    this._button.disabled = !ready;
    this._button.style.visibility = ready ? 'visible' : 'hidden';
    this.dispatchEvent(new CustomEvent('vividly-rendered', { bubbles: true }));
  }
}
