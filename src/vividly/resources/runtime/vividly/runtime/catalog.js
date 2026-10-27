const AUTHOR_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const RESOURCE_PATH = /^[a-zA-Z0-9][a-zA-Z0-9._~!$&'()+,;=@/-]*$/;

export async function loadCatalog(catalogUrl, yaml) {
  const response = await fetch(catalogUrl, { cache: 'no-cache' });
  if (!response.ok) throw new Error(`Cannot load catalog ${catalogUrl}`);

  const raw = yaml.load(await response.text());
  if (!raw || raw.version !== 1 || !Array.isArray(raw.presentations)) {
    throw new Error('Invalid catalog: expected version 1 with a presentations array');
  }

  const siteRoot = new URL('./', catalogUrl);
  const dependencies = normalizeDependencies(raw.dependencies, catalogUrl);
  const presentations = new Map();
  for (const entry of raw.presentations) {
    if (!entry || !AUTHOR_ID.test(entry.id || '')) {
      throw new Error(`Invalid catalog presentation ID "${entry?.id || ''}"`);
    }
    if (presentations.has(entry.id)) {
      throw new Error(`Duplicate catalog presentation ID "${entry.id}"`);
    }
    if (typeof entry.title !== 'string' || !entry.title.trim()) {
      throw new Error(`Catalog presentation "${entry.id}" requires a title`);
    }
    if (typeof entry.manifest !== 'string' || !entry.manifest) {
      throw new Error(`Catalog presentation "${entry.id}" requires a manifest`);
    }

    const isAbsolute = /^[a-z][a-z0-9+.-]*:/i.test(entry.manifest);
    const escapesSite = entry.manifest.split(/[\\/]/).includes('..');
    const manifestUrl = new URL(entry.manifest, catalogUrl);
    if (
      isAbsolute ||
      escapesSite ||
      manifestUrl.origin !== siteRoot.origin ||
      !manifestUrl.pathname.startsWith(siteRoot.pathname) ||
      entry.manifest.startsWith('/') ||
      entry.manifest.startsWith('//')
    ) {
      throw new Error(`Catalog manifest for "${entry.id}" must remain below site/`);
    }
    presentations.set(entry.id, {
      id: entry.id,
      title: entry.title,
      manifestUrl: manifestUrl.href,
    });
  }

  return { version: 1, dependencies, presentations };
}

function normalizeDependencies(raw, catalogUrl) {
  if (raw === undefined) return new Map();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error(`Invalid dependencies in ${catalogUrl}: expected a mapping`);
  }

  const dependencies = new Map();
  for (const [key, value] of Object.entries(raw)) {
    if (!AUTHOR_ID.test(key)) {
      throw new Error(`Invalid dependency key "${key}" in ${catalogUrl}`);
    }
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error(`Invalid dependency "${key}" in ${catalogUrl}: expected a mapping`);
    }
    const fields = Object.keys(value);
    const unknown = fields.find((field) => !['baseUrl', 'entry'].includes(field));
    if (unknown) {
      throw new Error(
        `Invalid dependency "${key}" in ${catalogUrl}: unknown field "${unknown}"`
      );
    }
    if (typeof value.baseUrl !== 'string' || !value.baseUrl.endsWith('/')) {
      throw new Error(
        `Invalid dependency "${key}" in ${catalogUrl}: baseUrl must end with "/"`
      );
    }
    let baseUrl;
    try {
      baseUrl = new URL(value.baseUrl);
    } catch {
      throw new Error(
        `Invalid dependency "${key}" in ${catalogUrl}: baseUrl must be an absolute URL`
      );
    }
    if (
      baseUrl.protocol !== 'https:' ||
      baseUrl.username ||
      baseUrl.password ||
      baseUrl.search ||
      baseUrl.hash
    ) {
      throw new Error(
        `Invalid dependency "${key}" in ${catalogUrl}: baseUrl must be a clean HTTPS URL`
      );
    }
    if (
      typeof value.entry !== 'string' ||
      !RESOURCE_PATH.test(value.entry) ||
      value.entry
        .split('/')
        .some((part) => !part || part === '.' || part === '..')
    ) {
      throw new Error(
        `Invalid dependency "${key}" in ${catalogUrl}: entry must be a normalized relative path`
      );
    }
    dependencies.set(
      key,
      Object.freeze({
        key,
        baseUrl: baseUrl.href,
        entry: value.entry,
      })
    );
  }
  return dependencies;
}
