const INPUT_SIZE = 27;
const OUTPUT_SIZE = 9;

function requireString(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value;
}

function requireVector(value, length, field) {
  if (!Array.isArray(value) || value.length !== length) {
    throw new Error(`${field} must contain ${length} values`);
  }
  if (!value.every(number => typeof number === "number" && Number.isFinite(number))) {
    throw new Error(`${field} must contain finite numbers`);
  }
  const result = Float32Array.from(value);
  return result;
}

function requireMatrix(value, rows, columns, field) {
  if (!Array.isArray(value) || value.length !== rows) {
    throw new Error(`${field} must contain ${rows} rows`);
  }
  const result = new Float32Array(rows * columns);
  for (let row = 0; row < rows; row += 1) {
    if (!Array.isArray(value[row]) || value[row].length !== columns) {
      throw new Error(`${field}[${row}] must contain ${columns} values`);
    }
    for (let column = 0; column < columns; column += 1) {
      const number = value[row][column];
      if (typeof number !== "number" || !Number.isFinite(number)) {
        throw new Error(`${field}[${row}][${column}] must be a finite number`);
      }
      result[row * columns + column] = number;
    }
  }
  return result;
}

export function modelFromArtifact(artifact, sourceUrl = null) {
  if (!artifact || typeof artifact !== "object" || Array.isArray(artifact)) {
    throw new Error("model artifact must be an object");
  }
  if (artifact.formatVersion !== 1) throw new Error("model formatVersion must be 1");
  if (!Number.isInteger(artifact.H) || artifact.H < 1) {
    throw new Error("model H must be a positive integer");
  }

  const id = requireString(artifact.id, "model id");
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)) {
    throw new Error("model id must be lowercase kebab-case");
  }
  const parameters = artifact.parameters;
  if (!parameters || typeof parameters !== "object") {
    throw new Error("model parameters must be an object");
  }

  return Object.freeze({
    formatVersion: 1,
    id,
    name: requireString(artifact.name, "model name"),
    description: requireString(artifact.description, "model description"),
    H: artifact.H,
    sourceUrl,
    training: artifact.training ? Object.freeze({ ...artifact.training }) : null,
    params: Object.freeze({
      IN: INPUT_SIZE,
      H: artifact.H,
      OUT: OUTPUT_SIZE,
      Wa: requireMatrix(parameters.Wa, INPUT_SIZE, artifact.H, "parameters.Wa"),
      ba: requireVector(parameters.ba, artifact.H, "parameters.ba"),
      Wb: requireMatrix(parameters.Wb, artifact.H, OUTPUT_SIZE, "parameters.Wb"),
      bb: requireVector(parameters.bb, OUTPUT_SIZE, "parameters.bb"),
    }),
  });
}

export async function fetchModel(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`could not load model (${response.status} ${response.statusText})`);
  return modelFromArtifact(await response.json(), response.url);
}

export class ModelRegistry {
  #models = new Map();
  #selectedId = null;

  register(model, { replace = false } = {}) {
    if (this.#models.has(model.id) && !replace) {
      throw new Error(`model ${model.id} is already registered`);
    }
    this.#models.set(model.id, model);
    return model;
  }

  get(id) {
    return this.#models.get(id) ?? null;
  }

  list() {
    return [...this.#models.values()];
  }

  select(id) {
    if (!this.#models.has(id)) throw new Error(`model ${id} is not registered`);
    this.#selectedId = id;
    return this.selected();
  }

  selected() {
    return this.#selectedId === null ? null : this.#models.get(this.#selectedId);
  }
}

export async function loadCatalog(catalogUrl, registry = new ModelRegistry()) {
  const response = await fetch(catalogUrl);
  if (!response.ok) throw new Error(`could not load model catalog (${response.status})`);
  const catalog = await response.json();
  if (catalog.formatVersion !== 1 || !Array.isArray(catalog.models)) {
    throw new Error("unsupported model catalog");
  }

  const models = await Promise.all(
    catalog.models.map(path => fetchModel(new URL(path, response.url))),
  );
  models.forEach(model => registry.register(model));
  registry.select(catalog.defaultModelId);
  return registry;
}
