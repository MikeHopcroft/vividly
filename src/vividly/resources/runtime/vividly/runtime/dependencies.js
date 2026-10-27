const DEPENDENCY_KEY = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const RESOURCE_PATH = /^[a-zA-Z0-9][a-zA-Z0-9._~!$&'()+,;=@/-]*$/;
const SHA256 = /^[0-9a-f]{64}$/;
const GLOBAL_NAME = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

export class DependencyTable {
  constructor(owner, records) {
    if (typeof owner !== 'string' || !owner) {
      throw new Error('Dependency table owner must be a nonempty string');
    }
    if (!(records instanceof Map)) {
      throw new Error(`Dependency table "${owner}" must contain a Map`);
    }
    this.owner = owner;
    this.records = new Map();
    for (const [key, record] of records) {
      if (key !== record.key) {
        throw new Error(`Dependency table "${owner}" has mismatched key "${key}"`);
      }
      this.records.set(key, Object.freeze({ ...record, owner }));
    }
  }

  static fromRuntime(document, sourceUrl) {
    const value = requireObject(document, `runtime dependency table ${sourceUrl}`);
    requireFields(value, ['schema', 'dependencies'], `runtime dependency table ${sourceUrl}`);
    if (value.schema !== 1) {
      throw new Error(`Invalid runtime dependency table ${sourceUrl}: schema must equal 1`);
    }
    const rawDependencies = requireObject(
      value.dependencies,
      `runtime dependency table ${sourceUrl} dependencies`
    );
    const records = new Map();
    for (const [key, rawRecord] of Object.entries(rawDependencies)) {
      records.set(key, normalizeRuntimeRecord(key, rawRecord, sourceUrl));
    }
    return new DependencyTable('runtime', records);
  }

  static fromCatalog(records, sourceUrl) {
    if (!(records instanceof Map)) {
      throw new Error(`Invalid catalog dependencies in ${sourceUrl}: expected a Map`);
    }
    const normalized = new Map();
    for (const [key, record] of records) {
      normalized.set(
        key,
        Object.freeze({
          ...record,
          key,
          loader: Object.freeze({ type: 'module' }),
        })
      );
    }
    return new DependencyTable('catalog', normalized);
  }
}

export class DependencyRegistry {
  constructor({ localBaseUrl = null } = {}) {
    this.localBaseUrl = localBaseUrl;
    this.tables = [];
    this.promises = new Map();
    this.values = new Map();
  }

  push(table) {
    if (!(table instanceof DependencyTable)) {
      throw new Error('Dependency registry accepts DependencyTable instances');
    }
    for (const key of table.records.keys()) {
      const existing = this._find(key);
      if (existing) {
        throw new Error(
          `Dependency "${key}" from ${table.owner} conflicts with dependency selected by ${existing.owner}`
        );
      }
    }
    this.tables.push(table);
  }

  has(key) {
    return this._find(key) !== null;
  }

  keys() {
    return this.tables.flatMap((table) => [...table.records.keys()]);
  }

  dependency(key) {
    if (!this.has(key)) throw new Error(`Unknown dependency "${key}"`);
    return new DependencyHandle(this, key);
  }

  url(key) {
    const record = this._require(key);
    if (this.localBaseUrl) {
      return new URL(`${record.key}/${record.entry}`, this.localBaseUrl).href;
    }
    return new URL(record.entry, record.baseUrl).href;
  }

  load(key) {
    if (this.promises.has(key)) return this.promises.get(key);
    const record = this._require(key);
    const promise = this._instantiate(record);
    this.promises.set(key, promise);
    return promise;
  }

  import(key) {
    const record = this._require(key);
    if (record.loader.type !== 'module') {
      throw new Error(
        `Dependency "${key}" uses the ${record.loader.type} loader; use load() instead`
      );
    }
    return this.load(key);
  }

  value(key) {
    this._require(key);
    if (!this.values.has(key)) {
      throw new Error(`Dependency "${key}" has not finished loading`);
    }
    return this.values.get(key);
  }

  _find(key) {
    for (let index = this.tables.length - 1; index >= 0; index -= 1) {
      const table = this.tables[index];
      const record = table.records.get(key);
      if (record) return record;
    }
    return null;
  }

  _require(key) {
    const record = this._find(key);
    if (!record) throw new Error(`Unknown dependency "${key}"`);
    return record;
  }

  async _instantiate(record) {
    const url = this.url(record.key);
    let value;
    if (record.loader.type === 'module') {
      value = await import(url);
    } else if (record.loader.type === 'script') {
      value = await loadScript(url, record.loader.global);
    } else {
      value = await loadStylesheet(url);
    }
    this.values.set(record.key, value);
    return value;
  }
}

class DependencyHandle {
  constructor(registry, key) {
    this.registry = registry;
    this.key = key;
  }

  url() {
    return this.registry.url(this.key);
  }

  load() {
    return this.registry.load(this.key);
  }

  import() {
    return this.registry.import(this.key);
  }
}

export async function loadRuntimeDependencyTable(sourceUrl) {
  const response = await fetch(sourceUrl, { cache: 'no-cache' });
  if (!response.ok) throw new Error(`Cannot load runtime dependency table ${sourceUrl}`);
  let document;
  try {
    document = JSON.parse(await response.text());
  } catch (error) {
    throw new Error(`Invalid runtime dependency table ${sourceUrl}: ${error.message}`);
  }
  return DependencyTable.fromRuntime(document, sourceUrl);
}

function normalizeRuntimeRecord(key, rawRecord, sourceUrl) {
  const label = `runtime dependency "${key}" in ${sourceUrl}`;
  if (!DEPENDENCY_KEY.test(key)) {
    throw new Error(`Invalid dependency key "${key}" in ${sourceUrl}`);
  }
  const record = requireObject(rawRecord, label);
  requireFields(
    record,
    ['version', 'projectUrl', 'baseUrl', 'entry', 'sha256', 'license', 'loader'],
    label
  );
  const version = requireString(record.version, `${label} version`);
  const projectUrl = cleanHttpsUrl(record.projectUrl, `${label} projectUrl`, false);
  const baseUrl = cleanHttpsUrl(record.baseUrl, `${label} baseUrl`, true);
  const entry = normalizedResourcePath(record.entry, `${label} entry`);
  if (typeof record.sha256 !== 'string' || !SHA256.test(record.sha256)) {
    throw new Error(`Invalid ${label}: sha256 must be a lowercase SHA-256 digest`);
  }
  const license = requireString(record.license, `${label} license`);
  const loader = normalizeLoader(record.loader, label);
  return Object.freeze({
    key,
    version,
    projectUrl,
    baseUrl,
    entry,
    sha256: record.sha256,
    license,
    loader,
  });
}

function normalizeLoader(rawLoader, label) {
  const loader = requireObject(rawLoader, `${label} loader`);
  if (loader.type === 'module' || loader.type === 'stylesheet') {
    requireFields(loader, ['type'], `${label} loader`);
    return Object.freeze({ type: loader.type });
  }
  if (loader.type === 'script') {
    requireFields(loader, ['type', 'global'], `${label} loader`);
    if (typeof loader.global !== 'string' || !GLOBAL_NAME.test(loader.global)) {
      throw new Error(`Invalid ${label} loader: global must be a JavaScript identifier`);
    }
    return Object.freeze({ type: 'script', global: loader.global });
  }
  throw new Error(
    `Invalid ${label} loader: type must be "module", "script", or "stylesheet"`
  );
}

function requireObject(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`Invalid ${label}: expected an object`);
  }
  return value;
}

function requireFields(value, expected, label) {
  const fields = Object.keys(value);
  const missing = expected.find((field) => !fields.includes(field));
  if (missing) throw new Error(`Invalid ${label}: missing field "${missing}"`);
  const unknown = fields.find((field) => !expected.includes(field));
  if (unknown) throw new Error(`Invalid ${label}: unknown field "${unknown}"`);
}

function requireString(value, label) {
  if (typeof value !== 'string' || !value) {
    throw new Error(`Invalid ${label}: expected a nonempty string`);
  }
  return value;
}

function cleanHttpsUrl(value, label, requireTrailingSlash) {
  if (typeof value !== 'string' || (requireTrailingSlash && !value.endsWith('/'))) {
    throw new Error(
      `Invalid ${label}: expected a clean absolute HTTPS URL${requireTrailingSlash ? ' ending with "/"' : ''}`
    );
  }
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`Invalid ${label}: expected a clean absolute HTTPS URL`);
  }
  if (
    url.protocol !== 'https:' ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error(`Invalid ${label}: expected a clean absolute HTTPS URL`);
  }
  return url.href;
}

function normalizedResourcePath(value, label) {
  if (
    typeof value !== 'string' ||
    !RESOURCE_PATH.test(value) ||
    value.split('/').some((part) => !part || part === '.' || part === '..')
  ) {
    throw new Error(`Invalid ${label}: expected a normalized relative path`);
  }
  return value;
}

function loadScript(url, globalName) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = url;
    script.onload = () => {
      const value = globalThis[globalName];
      if (value === undefined) {
        reject(new Error(`Dependency script ${url} did not define "${globalName}"`));
        return;
      }
      resolve(value);
    };
    script.onerror = () => reject(new Error(`Cannot load dependency script ${url}`));
    document.head.appendChild(script);
  });
}

function loadStylesheet(url) {
  return new Promise((resolve, reject) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = url;
    link.onload = () => resolve(link);
    link.onerror = () => reject(new Error(`Cannot load dependency stylesheet ${url}`));
    document.head.appendChild(link);
  });
}
