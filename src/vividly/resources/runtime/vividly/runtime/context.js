// A slide's only interface to the world.

const scriptCache = new Map(); // resolved url -> Promise<any>

export class SlideContext {
  constructor({
    moduleUrl,
    dataUrl,
    address,
    props,
    bus,
    state,
    navigate,
    navigator,
    enterSection,
    goUp,
    captureKeys,
    dependencyRegistry,
  }) {
    this.moduleUrl = moduleUrl;
    this.dataUrl = dataUrl;
    this.address = address;
    this.props = props || {};
    this.bus = bus;
    this.state = state;
    this.navigate = navigate;
    this.navigator = navigator;
    this.enterSection = enterSection;
    this.goUp = goUp;
    this.captureKeys = captureKeys;
    this.dependencyRegistry = dependencyRegistry;
  }

  asset(relativePath) {
    return new URL(relativePath, this.dataUrl).href;
  }

  /** Fetch a slide-local data file, parsed by extension. */
  async load(relativePath) {
    const href = this.asset(relativePath);
    const response = await fetch(href);
    if (!response.ok) throw new Error(`Cannot load ${href}`);
    const text = await response.text();
    if (/\.ya?ml$/i.test(href)) {
      const yaml = await this.dependency('js-yaml').load();
      return yaml.load(text);
    }
    if (/\.json$/i.test(href)) return JSON.parse(text);
    return text;
  }

  dependency(key) {
    if (!this.dependencyRegistry.has(key)) {
      throw new Error(
        `Slide "${this.address}" requested unmapped dependency "${key}"`
      );
    }
    return this.dependencyRegistry.dependency(key);
  }

  /** Load a non-ESM dependency; deduped across slides by resolved URL. */
  loadScript(relativePath, { global } = {}) {
    const href = this.asset(relativePath);
    if (!scriptCache.has(href)) {
      scriptCache.set(
        href,
        new Promise((resolve, reject) => {
          const el = document.createElement('script');
          el.src = href;
          el.onload = () => resolve(global ? window[global] : undefined);
          el.onerror = () => reject(new Error(`Cannot load script ${href}`));
          document.head.appendChild(el);
        })
      );
    }
    return scriptCache.get(href);
  }
}
