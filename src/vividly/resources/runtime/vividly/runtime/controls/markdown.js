import { SourceControl } from './source-control.js';
import { highlightCodeBlocks, renderMarkdown } from './render.js';
import { addMarkdownCopyButtons } from './code-copy.js';

export class VividlyMarkdown extends SourceControl {
  static observedAttributes = ['src', 'highlight', 'base-url', 'no-copy'];

  get baseUrl() {
    return this.getAttribute('base-url') || '';
  }

  set baseUrl(value) {
    if (value == null || value === '') this.removeAttribute('base-url');
    else this.setAttribute('base-url', value);
  }

  get highlight() {
    return this.hasAttribute('highlight');
  }

  set highlight(value) {
    this.toggleAttribute('highlight', Boolean(value));
  }

  renderValue(value) {
    this.innerHTML = renderMarkdown(value, this.baseUrl || this._sourceUrl);

    if (this.highlight) highlightCodeBlocks(this);
    if (this.copyable) addMarkdownCopyButtons(this);
  }
}