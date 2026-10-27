export const FRAME_SCHEMA_VERSION = 1;
const REGENERATE = 'Regenerate Life data with: npm --prefix tools/life run generate';

export function canonicalConfig(config) {
  const normalize = (value) => {
    if (Array.isArray(value)) return value.map(normalize);
    if (value !== null && typeof value === 'object') {
      return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalize(value[key])]));
    }
    if (value === null || typeof value === 'string' || typeof value === 'boolean' ||
        (typeof value === 'number' && Number.isFinite(value))) return value;
    throw new TypeError('Life configuration must contain only JSON-compatible values');
  };
  return JSON.stringify(normalize(config));
}

export async function configHash(config) {
  const bytes = new TextEncoder().encode(canonicalConfig(config));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function encodeFrames(frames) {
  return frames.map((frame) => ({
    ...frame,
    world: [...frame.world],
    ...(frame.overlay ? { overlay: [...frame.overlay] } : {}),
    ...(frame.animation ? {
      animation: {
        ...frame.animation,
        worlds: frame.animation.worlds.map((world) => [...world]),
      },
    } : {}),
  }));
}

export function decodeFrames(asset, hash) {
  const require = (condition, field) => {
    if (!condition) throw new TypeError(`Invalid or stale Life data (${field}). ${REGENERATE}`);
  };
  const finite = (value) => typeof value === 'number' && Number.isFinite(value);
  const nonNegativeInteger = (value) => Number.isInteger(value) && value >= 0;
  const positive = (value) => finite(value) && value > 0;
  const viewport = (value) => {
    require(value && typeof value === 'object', 'viewport');
    if (value.bounds) {
      const { minX, maxX, minY, maxY } = value.bounds;
      require([minX, maxX, minY, maxY].every(finite) && minX <= maxX && minY <= maxY &&
        finite(value.padding) && value.padding >= 0, 'viewport bounds');
    } else {
      require(Array.isArray(value.center) && value.center.length === 2 &&
        value.center.every(finite) && positive(value.cellsWide), 'viewport center/width');
    }
  };
  const world = (value) => {
    require(Array.isArray(value) && value.every(
      (cell) => typeof cell === 'string' && /^-?\d+,-?\d+$/.test(cell)
    ), 'cell coordinates');
    return new Set(value);
  };
  require(asset?.schemaVersion === FRAME_SCHEMA_VERSION, 'schemaVersion');
  require(typeof asset.compilerHash === 'string' && /^[0-9a-f]{64}$/.test(asset.compilerHash),
    'compilerHash');
  require(/^[0-9a-f]{64}$/.test(hash), 'configuration hash');
  const frames = asset.simulations?.[hash]?.frames;
  require(Array.isArray(frames) && frames.length > 0, 'configuration hash or frames');
  return frames.map((frame, index) => {
    require(frame && frame.index === index && frame.total === frames.length &&
      nonNegativeInteger(frame.turn) && nonNegativeInteger(frame.passageIndex) &&
      nonNegativeInteger(frame.generationIndex), 'frame indices');
    require(['current', 'prediction', 'resolved', 'normal'].includes(frame.phase), 'phase');
    require(['passageId', 'passageLabel', 'title', 'caption'].every(
      (key) => typeof frame[key] === 'string'
    ), 'frame text');
    viewport(frame.viewport);
    if (frame.predictions !== undefined) {
      require(Array.isArray(frame.predictions) && frame.predictions.every((prediction) =>
        prediction && Number.isInteger(prediction.x) && Number.isInteger(prediction.y) &&
        nonNegativeInteger(prediction.count) && prediction.count <= 8 &&
        ['survives', 'dies', 'born'].includes(prediction.outcome)
      ), 'predictions');
    }
    let animation;
    if (frame.animation !== undefined) {
      const data = frame.animation;
      require(data && positive(data.duration) && positive(data.viewportDuration) &&
        Array.isArray(data.worlds) && data.worlds.length > 0 &&
        Array.isArray(data.viewportKeyframes), 'animation');
      let previous = 0;
      for (const keyframe of data.viewportKeyframes) {
        require(keyframe && finite(keyframe.at) && keyframe.at > previous &&
          keyframe.at < 1, 'viewport keyframe');
        viewport(keyframe.viewport);
        previous = keyframe.at;
      }
      animation = { ...data, worlds: data.worlds.map(world) };
    }
    return {
      ...frame,
      world: world(frame.world),
      ...(frame.overlay !== undefined ? { overlay: world(frame.overlay) } : {}),
      ...(animation ? { animation } : {}),
    };
  });
}
