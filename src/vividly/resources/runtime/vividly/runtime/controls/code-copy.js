const CONTROL_SELECTOR = 'vividly-markdown, vividly-annotated-markdown, vividly-code';

export function createCodeCopyTools(getText, label = 'Copy code') {
  const tools = document.createElement('span');
  tools.className = 'v-code-copy-tools';

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'v-code-copy';
  button.title = label;
  button.setAttribute('aria-label', label);
  button.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
      <g class="v-code-copy-symbol">
        <rect x="9" y="9" width="12" height="12" rx="2"></rect>
        <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"></path>
      </g>
      <path class="v-code-copy-check" d="m5 12 4 4 10-10"></path>
    </svg>`;

  const status = document.createElement('span');
  status.className = 'v-code-copy-status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  tools.append(button, status);

  button.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') event.stopPropagation();
  });
  button.addEventListener('click', async event => {
    event.stopPropagation();
    const owner = tools.closest(CONTROL_SELECTOR);
    if (button.disabled || !owner?.copyable) return;
    button.disabled = true;
    delete button.dataset.copied;
    button.title = label;
    status.textContent = '';
    status.classList.remove('is-error');
    const current = () => tools.isConnected && owner.contains(tools) && owner.copyable;
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error('Clipboard access requires HTTPS or localhost and browser permission.');
      }
      await navigator.clipboard.writeText(getText());
      if (!current()) return;
      button.dataset.copied = 'true';
      button.title = 'Copied';
      status.textContent = 'Copied to clipboard.';
    } catch (error) {
      if (!current()) return;
      console.error('[vividly] Could not copy code', error);
      button.title = 'Copy failed';
      status.classList.add('is-error');
      status.textContent = 'Could not access the clipboard. Select the code and copy it manually.';
      owner.dispatchEvent(new CustomEvent('vividly-error', {
        bubbles: true, detail: { error, operation: 'copy' },
      }));
    } finally {
      button.disabled = false;
    }
  });
  return tools;
}

export function addMarkdownCopyButtons(root) {
  const owner = root.closest(CONTROL_SELECTOR);
  let number = 0;
  for (const code of root.querySelectorAll('pre > code')) {
    if (code.closest(CONTROL_SELECTOR) !== owner) continue;
    const pre = code.parentElement;
    pre.querySelector(':scope > .v-code-copy-tools')?.remove();
    pre.classList.add('v-code-copy-block');
    const text = code.textContent;
    pre.append(createCodeCopyTools(() => text, `Copy code block ${++number}`));
  }
}
