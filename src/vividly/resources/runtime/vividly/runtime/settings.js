export class ViewerSettings {
  constructor(presentation) {
    this.presentation = presentation;
    this.trigger = document.createElement('button');
    this.trigger.type = 'button';
    this.trigger.className = 'v-settings-trigger';
    this.trigger.title = 'Settings';
    this.trigger.setAttribute('aria-label', 'Settings');
    this.trigger.innerHTML = `
      <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
        <path d="m9 3-.6 2.4-2 .9L4.2 6 2 9.8l1.6 1.8v.8L2 14.2 4.2 18l2.2-.3
          2 .9L9 21h6l.6-2.4 2-.9 2.2.3 2.2-3.8-1.6-1.8v-.8L22 9.8 19.8 6
          l-2.2.3-2-.9L15 3Z"/>
        <circle cx="12" cy="12" r="3"/>
      </svg>`;
    this.trigger.addEventListener('click', (event) => {
      event.stopPropagation();
      this.show();
    });
    this.trigger.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') event.stopPropagation();
    });

    this.dialog = document.createElement('dialog');
    this.dialog.className = 'v-settings';
    this.dialog.setAttribute('aria-labelledby', 'v-settings-title');
    this.dialog.innerHTML = `
      <div class="v-settings-panel">
        <h2 id="v-settings-title">Settings</h2>
        <label for="v-settings-navigation">Navigation controls</label>
        <select id="v-settings-navigation" aria-describedby="v-settings-auto">
          <option value="auto">Auto</option>
          <option value="show">Show</option>
          <option value="hide">Hide</option>
        </select>
        <p id="v-settings-auto">Show controls on touch-first devices; hide them when
          the primary pointer supports precise pointing and hover.</p>
        <label class="v-settings-hints">
          <input type="checkbox" aria-describedby="v-settings-hint-description v-settings-policy">
          Show initial hint dialog
        </label>
        <p id="v-settings-hint-description">Show navigation tips when starting a presentation.</p>
        <p id="v-settings-policy"></p>
        <p class="v-settings-query" hidden>Initial hints are skipped for this page by
          vividly-skip-hints=1. Your saved preference is unchanged.</p>
        <p class="v-settings-storage" role="status" aria-live="polite"></p>
        <button type="button" class="v-settings-close">Close</button>
      </div>`;
    this.navigation = this.dialog.querySelector('select');
    this.hints = this.dialog.querySelector('input');
    this.navigation.addEventListener('change', () => {
      presentation._siteState.scope('~viewerSettings').set('navigation', this.navigation.value);
      presentation._touch.sync();
    });
    this.hints.addEventListener('change', () => {
      presentation._setKeyboardHintsSuppressed(!this.hints.checked);
    });
    this.dialog.querySelector('.v-settings-close').addEventListener('click', () => this.close());
    this.dialog.addEventListener('click', (event) => {
      event.stopPropagation();
      if (event.target === this.dialog) this.close();
    });
    this.dialog.addEventListener('cancel', (event) => {
      event.preventDefault();
      this.close();
    });
    this.dialog.addEventListener('keydown', (event) => {
      event.stopPropagation();
      if (event.key === 'Escape') {
        event.preventDefault();
        this.close();
      } else {
        presentation._handleDialogControlKey(event, this.dialog);
      }
    });
    presentation.append(this.trigger, this.dialog);
    this.sync();
  }

  get navigationMode() {
    const value = this.presentation._siteState.scope('~viewerSettings').get('navigation', 'auto');
    return ['auto', 'show', 'hide'].includes(value) ? value : 'auto';
  }

  sync() {
    const p = this.presentation;
    const policy = p._catalogView.hidden ? p._manifest?.keyboardHints || 'auto' : 'auto';
    const suppressed = p._siteState.scope('~keyboardHints').get('suppressed', false);
    this.navigation.value = this.navigationMode;
    this.hints.disabled = policy !== 'auto';
    this.hints.checked = policy === 'always' || (policy === 'auto' && !suppressed);
    this.dialog.querySelector('#v-settings-policy').textContent =
      policy === 'always' ? 'This presentation always shows initial hints.' :
        policy === 'never' ? 'This presentation disables initial hints.' : '';
    this.dialog.querySelector('.v-settings-query').hidden =
      new URLSearchParams(location.search).get('vividly-skip-hints') !== '1';
    this.dialog.querySelector('.v-settings-storage').textContent = p._viewerStorageError
      ? 'Your preferences could not be saved for future visits. Changes apply only to this page.'
      : '';
  }

  show(fromHelp = false) {
    const p = this.presentation;
    if (p.hasAttribute('data-capture') || this.dialog.open ||
        (!p._keyboardHints.hidden && (!fromHelp || p._keyboardHelp.hidden))) return;
    this.fromHelp = fromHelp;
    this.helpReturnFocus = p._helpReturnFocus;
    clearTimeout(p._keyboardHelpTimer);
    p._keyboardHelp.hidden = true;
    delete p._keyboardHelp.dataset.closing;
    this.sync();
    p._touch.cancel();
    this.dialog.showModal();
    p._touch.sync();
    this.navigation.focus({ preventScroll: true });
  }

  close(restoreHelp = true) {
    if (!this.dialog.open) return;
    const p = this.presentation;
    this.dialog.close();
    if (restoreHelp && this.fromHelp) {
      p._showKeyboardHelp();
      p._helpReturnFocus = this.helpReturnFocus;
      p._keyboardHelp.querySelector('.v-help-settings').focus({ preventScroll: true });
    } else if (this.trigger.isConnected && this.trigger.getClientRects().length) {
      this.trigger.focus({ preventScroll: true });
    }
    p._touch.sync();
  }

  dispose() {
    this.close(false);
    this.dialog.remove();
    this.trigger.remove();
  }
}
