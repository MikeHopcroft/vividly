export function createAdvanceButton(control) {
  const button = document.createElement('button');
  button.type = 'button';
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    if (!button.disabled) control.closest('vividly-presentation')?.advance();
  });
  button.addEventListener('keydown', (event) => {
    if (event.key === ' ' || event.key === 'Enter') event.stopPropagation();
  });
  return button;
}

export class VividlyAdvance extends HTMLElement {
  static observedAttributes = ['message'];

  connectedCallback() {
    if (!this._button) {
      this._button = createAdvanceButton(this);
    }
    this._render();
  }

  attributeChangedCallback(_name, oldValue, newValue) {
    if (!this._button || oldValue === newValue) return;
    this._render();
  }

  get message() {
    return this.getAttribute('message') || 'continue';
  }

  set message(value) {
    if (value == null || value === '') this.removeAttribute('message');
    else this.setAttribute('message', value);
  }

  _render() {
    const rightArrow = document.createElement('kbd');
    rightArrow.className = 'v-advance-arrow';
    rightArrow.setAttribute('aria-hidden', 'true');
    rightArrow.textContent = '→';

    const space = document.createElement('kbd');
    space.setAttribute('aria-hidden', 'true');
    space.textContent = 'Space';

    this._button.setAttribute(
      'aria-label',
      `Press Right Arrow or Space to ${this.message}`
    );
    this._button.replaceChildren(
      'Press ',
      rightArrow,
      ' or ',
      space,
      ` to ${this.message}`
    );
    this.replaceChildren(this._button);
  }
}
