import { VividlyMarkdown } from './markdown.js';
import { addMarkdownCopyButtons } from './code-copy.js';

export class VividlyAnnotatedMarkdown extends VividlyMarkdown {
  get annotationCount() {
    return this._annotations?.length || 0;
  }

  get activeAnnotation() {
    return this._activeAnnotation ?? -1;
  }

  set activeAnnotation(value) {
    this._cancelPendingScroll();
    this._selectAnnotation(normalizeIndex(value), { emit: false });
  }

  renderValue(value) {
    const selected = this.activeAnnotation;
    this.replaceChildren();
    this._annotations = [];

    const header = document.createElement('header');
    header.className = 'v-annotated-header';
    header.hidden = true;

    const body = document.createElement('div');
    body.className = 'v-annotated-body';

    this._nav = document.createElement('nav');
    this._nav.className = 'v-annotated-nav';
    this._nav.setAttribute('aria-label', 'Annotations');

    const navHeading = document.createElement('h2');
    navHeading.textContent = 'Annotations';
    this._nav.appendChild(navHeading);

    this._content = document.createElement('main');
    this._content.className = 'v-annotated-content';

    const markdown = document.createElement('vividly-markdown');
    markdown.copyable = this.copyable;
    markdown.highlight = this.highlight;
    markdown.baseUrl = this.baseUrl || this._sourceUrl;
    markdown.value = value;
    markdown.addEventListener('vividly-rendered', (event) => event.stopPropagation());
    markdown.addEventListener('vividly-error', (event) => {
      if (event.detail.operation !== 'copy') event.stopPropagation();
    });
    this._content.appendChild(markdown);

    body.append(this._nav, this._content);
    this.append(header, body);

    this._discoverHeader(markdown, header);
    this._discoverAnnotations(markdown);
    this._selectAnnotation(selected, { emit: false });
  }

  revealAnnotation(index, { block = 'center', behavior = 'smooth' } = {}) {
    const normalized = normalizeIndex(index);
    if (!this._selectAnnotation(normalized, { emit: false })) return;

    this._cancelPendingScroll();
    this._scrollTimer = setTimeout(() => {
      this._scrollTimer = null;
      const annotation = this._annotations[normalized];
      if (!annotation) return;
      scrollWithin(this._nav, annotation.navEntry, 'nearest', behavior);
      scrollWithin(this._content, annotation.anchor, block, behavior);
    }, 0);
  }

  disconnectedCallback() {
    this._cancelPendingScroll();
    super.disconnectedCallback();
  }

  _discoverHeader(markdown, header) {
    const metadata = markdown.querySelector('vividly-document-header');
    if (!metadata) return;

    const title = metadata.getAttribute('title');
    if (title) {
      const heading = document.createElement('h1');
      heading.textContent = title;
      header.appendChild(heading);
    }

    if (metadata.innerHTML.trim()) {
      const description = document.createElement('div');
      description.className = 'v-annotated-description';
      description.innerHTML = metadata.innerHTML;
      header.appendChild(description);
      if (this.copyable) addMarkdownCopyButtons(description);
    }
    header.hidden = false;
  }

  _discoverAnnotations(markdown) {
    markdown.querySelectorAll('vividly-annotation').forEach((metadata, index) => {
      const anchor = document.createElement('span');
      anchor.className = 'v-annotation-anchor';

      const marker = document.createElement('button');
      marker.className = 'v-annotation-marker';
      marker.type = 'button';
      marker.textContent = String(index + 1);
      marker.setAttribute('aria-label', `Show annotation ${index + 1}`);
      anchor.appendChild(marker);
      metadata.before(anchor);

      const navEntry = document.createElement('section');
      navEntry.className = 'v-annotation-entry';

      const navButton = document.createElement('button');
      navButton.className = 'v-annotation-title';
      navButton.type = 'button';
      navButton.textContent = metadata.getAttribute('title') || `Annotation ${index + 1}`;

      const navContent = document.createElement('div');
      navContent.className = 'v-annotation-content';
      navContent.innerHTML = metadata.innerHTML;

      navEntry.append(navButton, navContent);
      this._nav.appendChild(navEntry);
      if (this.copyable) addMarkdownCopyButtons(navContent);
      this._annotations.push({ anchor, marker, navEntry, navButton });

      marker.addEventListener('click', () => {
        this._selectFromPointer(index);
        this._cancelPendingScroll();
        this._scrollTimer = setTimeout(() => {
          this._scrollTimer = null;
          scrollWithin(this._nav, navEntry, 'nearest', 'smooth');
        }, 0);
      });
      navButton.addEventListener('click', () => {
        this._selectFromPointer(index);
        this.revealAnnotation(index);
      });
    });
  }

  _selectFromPointer(index) {
    this._selectAnnotation(index, { emit: true });
  }

  _selectAnnotation(index, { emit }) {
    if (!this._annotations) {
      this._activeAnnotation = index;
      return false;
    }
    if (index < -1 || index >= this._annotations.length) return false;

    for (const [annotationIndex, annotation] of this._annotations.entries()) {
      const selected = annotationIndex === index;
      annotation.navEntry.classList.toggle('selected', selected);
      annotation.marker.classList.toggle('selected', selected);
      annotation.navButton.setAttribute('aria-expanded', String(selected));
    }
    this._activeAnnotation = index;

    if (emit) {
      this.dispatchEvent(
        new CustomEvent('vividly-annotation-change', {
          bubbles: true,
          detail: { index },
        })
      );
    }
    return index >= 0;
  }

  _cancelPendingScroll() {
    if (this._scrollTimer != null) clearTimeout(this._scrollTimer);
    this._scrollTimer = null;
  }
}

function normalizeIndex(value) {
  const index = Number(value);
  return Number.isInteger(index) ? index : -1;
}

function scrollWithin(container, target, block, behavior) {
  if (!container || !target || container.clientHeight === 0) return;
  const containerRect = container.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const top = container.scrollTop + targetRect.top - containerRect.top;
  const bottom = top + targetRect.height;
  let destination = top;

  if (targetRect.height > container.clientHeight) destination = top;
  else if (block === 'center') destination = top - (container.clientHeight - targetRect.height) / 2;
  else if (block === 'end') destination = bottom - container.clientHeight;
  else if (block === 'nearest') {
    if (top >= container.scrollTop && bottom <= container.scrollTop + container.clientHeight) return;
    destination = top < container.scrollTop ? top : bottom - container.clientHeight;
  }

  container.scrollTo({
    top: Math.max(0, destination),
    behavior: behavior === 'instant' ? 'auto' : behavior,
  });
}