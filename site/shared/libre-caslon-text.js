const loads = new WeakMap();

const loadStylesheet = (url) => new Promise((resolve, reject) => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = url;
  link.addEventListener('load', resolve, { once: true });
  link.addEventListener('error', () => {
    reject(new Error(`Failed to load Libre Caslon Text stylesheet: ${url}`));
  }, { once: true });
  document.head.appendChild(link);
});

export const loadLibreCaslonText = (ctx) => {
  const existing = loads.get(document);
  if (existing) {
    return existing;
  }

  const dependencyUrl = ctx.dependency('libre-caslon-text').url();
  const promise = Promise.all([
    loadStylesheet(dependencyUrl),
    loadStylesheet(new URL('latin-italic.css', dependencyUrl).href),
  ]).then(() => Promise.all([
    document.fonts.load('400 1em "Libre Caslon Text"'),
    document.fonts.load('italic 400 1em "Libre Caslon Text"'),
    document.fonts.load('700 1em "Libre Caslon Text"'),
  ]));

  loads.set(document, promise);
  return promise;
};
