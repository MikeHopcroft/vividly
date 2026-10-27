let marked = null;
let highlight = null;

export function configureRenderDependencies(registry) {
  marked = registry.value('marked');
  highlight = registry.value('highlight-js');
}

export function renderMarkdown(markdown, baseUrl) {
  requireMarked();
  const template = document.createElement('template');
  template.innerHTML = marked.parse(markdown);
  renderPromptBlocks(template.content);

  if (baseUrl) {
    const documentUrl = new URL(baseUrl, document.baseURI);
    for (const element of template.content.querySelectorAll('img[src], a[href]')) {
      const attribute = element.tagName === 'IMG' ? 'src' : 'href';
      const reference = element.getAttribute(attribute).trim();
      if (!reference || /^(?:[/#]|[a-z][a-z\d+.-]*:)/i.test(reference)) continue;
      element.setAttribute(attribute, new URL(reference, documentUrl).href);
    }
  }

  return template.innerHTML;
}

export function countAnnotations(markdown) {
  requireMarked();
  let count = 0;
  marked.walkTokens(marked.lexer(markdown), (token) => {
    if (token.type !== 'html') return;
    count += token.raw.match(/<vividly-annotation(?:\s|>)/gi)?.length || 0;
  });
  return count;
}

export function highlightCodeBlocks(root) {
  requireHighlightJs('Vividly Markdown highlighting');
  root.querySelectorAll('pre code').forEach((code) => {
    if (code.closest('.v-prompt')) return;
    highlight.highlightElement(code);
  });
}

export function highlightSource(source, language) {
  requireHighlightJs('Vividly Code');
  return language
    ? highlight.highlight(source, { language, ignoreIllegals: true }).value
    : highlight.highlightAuto(source).value;
}

function renderPromptBlocks(root) {
  for (const code of root.querySelectorAll('pre > code.language-prompt')) {
    const figure = document.createElement('figure');
    figure.className = 'v-prompt';

    const caption = document.createElement('figcaption');
    caption.textContent = 'Agent prompt';

    const content = document.createElement('div');
    content.className = 'v-prompt-content';
    content.innerHTML = marked.parse(code.textContent);

    figure.append(caption, content);
    code.parentElement.replaceWith(figure);
  }
}

function requireHighlightJs(feature) {
  if (!highlight) throw new Error(`${feature} requires highlight.js`);
}

function requireMarked() {
  if (!marked) throw new Error('Vividly Markdown requires marked');
}