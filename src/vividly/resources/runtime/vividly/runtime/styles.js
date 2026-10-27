// Per-module stylesheet loading, scoped with @scope and adopted once per module.

const adopted = new Map(); // moduleId -> Promise<void>

/**
 * Slide stylesheets are deliberately left unlayered so they win over the
 * layered global sheets (base/kit/theme) without specificity escalation.
 */
export function adoptModuleStyles(moduleId, moduleUrl, styles) {
  if (!styles || styles.length === 0) return Promise.resolve();
  if (adopted.has(moduleId)) return adopted.get(moduleId);

  const work = (async () => {
    const sheets = [];
    for (const relative of styles) {
      const href = new URL(relative, moduleUrl).href;
      const response = await fetch(href);
      if (!response.ok) throw new Error(`Cannot load stylesheet ${href}`);
      const text = absolutizeUrls(await response.text(), href);
      sheets.push(scopeStyles(moduleId, text));
    }
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, ...sheets];
  })();

  adopted.set(moduleId, work);
  return work;
}

function scopeStyles(moduleId, text) {
  const source = new CSSStyleSheet();
  source.replaceSync(text);
  const normalized = [...source.cssRules].map((rule) => rule.cssText).join('\n');
  const scoped = new CSSStyleSheet();
  scoped.replaceSync(
    `@scope ([data-vividly-module="${moduleId}"]) {\n${normalized}\n}`
  );
  return scoped;
}

// Constructed stylesheets resolve url() against the document, not the source
// file, so rewrite relative references before adopting.
function absolutizeUrls(css, baseHref) {
  return css.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/g, (match, quote, ref) => {
    if (/^(?:[a-z][a-z0-9+.-]*:|\/\/|#|data:)/i.test(ref)) return match;
    return `url("${new URL(ref, baseHref).href}")`;
  });
}

export function moduleIdFor(moduleUrl) {
  const parts = new URL(moduleUrl).pathname.split('/').filter(Boolean);
  const dir = parts.length > 1 ? parts[parts.length - 2] : 'slide';
  return `${dir}-${hash(moduleUrl)}`;
}

function hash(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(36);
}
