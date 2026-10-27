const loads = new WeakMap();

const loadStylesheet = (url) => new Promise((resolve, reject) => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = url;
  link.addEventListener('load', resolve, { once: true });
  link.addEventListener('error', () => {
    reject(new Error(`Failed to load presentation font stylesheet: ${url}`));
  }, { once: true });
  document.head.appendChild(link);
});

export const loadWhyVividlyFonts = (ctx) => {
  const existing = loads.get(document);
  if (existing) {
    return existing;
  }

  // Catalog load() imports JavaScript; font CSS uses the resolved entry URL instead.
  const promise = Promise.all([
    loadStylesheet(ctx.dependency('archivo').url()),
    loadStylesheet(ctx.dependency('ibm-plex-mono').url()),
  ]).then(() => Promise.all([
    '400 1em "Archivo Variable"',
    '600 1em "Archivo Variable"',
    '700 1em "Archivo Variable"',
    '720 1em "Archivo Variable"',
    '800 1em "Archivo Variable"',
    '400 1em "IBM Plex Mono"',
  ].map(async (font) => {
    const faces = await document.fonts.load(font);
    if (!faces.length) {
      throw new Error(`Presentation font stylesheet did not provide ${font}`);
    }
  })));

  loads.set(document, promise);
  return promise;
};
