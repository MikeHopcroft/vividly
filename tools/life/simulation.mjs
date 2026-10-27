import { key, coordinates } from '../../site/slides/game-of-life/cells.mjs';

const NEIGHBORS = [
  [-1, -1], [0, -1], [1, -1],
  [-1, 0],            [1, 0],
  [-1, 1],  [0, 1],   [1, 1],
];

export function compileLifePresentation(config) {
  if (!config || !Array.isArray(config.passages) || config.passages.length === 0) {
    throw new TypeError('Game of Life props must include at least one passage');
  }

  const frames = [];
  config.passages.forEach((passage, passageIndex) => {
    frames.push(...compilePassage(passage, passageIndex, config.initialCells));
  });

  return frames.map((frame, index) => ({
    ...frame,
    index,
    total: frames.length,
  }));
}

function compilePassage(passage, passageIndex, fallbackCells) {
  const initialCells = passage.initialCells ?? fallbackCells;
  if (!Array.isArray(initialCells) || !Array.isArray(passage.generations)) {
    throw new TypeError(`Passage "${passage.id ?? passageIndex}" needs initialCells and generations`);
  }

  const initialWorld = worldFromCells(initialCells);
  const generationRequests = passage.generations.map((generation, index) => {
    const turn = asNonNegativeInteger(generation.turn, `generation ${index} turn`);
    return {
      generation,
      turn,
      resolvedTurn: generation.mode === 'explain' ? turn + 1 : turn,
    };
  });
  const rangeRequests = collectViewportRanges(passage, generationRequests);
  const neededTurns = new Set([0]);
  let previousTurn = 0;

  generationRequests.forEach(({ generation, turn, resolvedTurn }) => {
    neededTurns.add(turn);
    neededTurns.add(resolvedTurn);
    if (generation.animate) {
      sampleTurns(
        previousTurn,
        turn,
        generation.animate.frames ?? 90,
        generation.animate.turnCurve ?? 1,
      )
        .forEach((sample) => neededTurns.add(sample));
    }
    previousTurn = resolvedTurn;
  });

  const maxTurn = Math.max(
    ...neededTurns,
    ...rangeRequests.map(({ end }) => end),
  );
  const snapshots = new Map();
  let world = initialWorld;

  for (let turn = 0; turn <= maxTurn; turn += 1) {
    if (neededTurns.has(turn)) snapshots.set(turn, new Set(world));
    rangeRequests.forEach((request) => {
      if (turn >= request.start && turn <= request.end) {
        includeWorldInBounds(request.bounds, world);
      }
    });
    if (turn < maxTurn) world = evolve(world);
  }

  const frames = [];
  let inheritedViewport = passage.viewport;
  previousTurn = 0;

  generationRequests.forEach(({ generation, turn, resolvedTurn }, generationIndex) => {
    inheritedViewport = generation.viewport ?? inheritedViewport;
    if (!inheritedViewport) {
      throw new TypeError(`Passage "${passage.id ?? passageIndex}" has no viewport`);
    }
    const viewport = resolveViewportBounds(inheritedViewport, rangeRequests);
    const shared = {
      passageId: passage.id ?? String(passageIndex),
      passageIndex,
      passageLabel: passage.label ?? `Passage ${passageIndex + 1}`,
      title: generation.title ?? passage.title ?? 'Conway’s Game of Life',
      caption: generation.caption ?? '',
      viewport,
      generationIndex,
      overlay: generation.overlayCells === undefined
        ? undefined
        : worldFromCells(generation.overlayCells),
    };

    if (generation.mode === 'explain') {
      const predictionWorld = snapshots.get(turn);
      const previousFrame = frames.at(-1);
      if (previousFrame?.world !== predictionWorld || previousFrame.predictions) {
        frames.push({
          ...shared,
          turn,
          phase: 'current',
          world: predictionWorld,
        });
      }
      frames.push({
        ...shared,
        turn,
        phase: 'prediction',
        world: predictionWorld,
        predictions: classify(predictionWorld),
      });
      frames.push({
        ...shared,
        turn: resolvedTurn,
        phase: 'resolved',
        world: snapshots.get(resolvedTurn),
      });
    } else {
      const frame = {
        ...shared,
        turn,
        phase: 'normal',
        world: snapshots.get(turn),
      };
      if (generation.animate) {
        const turns = sampleTurns(
          previousTurn,
          turn,
          generation.animate.frames ?? 90,
          generation.animate.turnCurve ?? 1,
        );
        frame.animation = {
          duration: positiveNumber(generation.animate.duration, 'animation duration'),
          viewportDuration: generation.animate.viewportDuration === undefined
            ? generation.animate.duration
            : positiveNumber(generation.animate.viewportDuration, 'viewport animation duration'),
          viewportKeyframes: compileViewportKeyframes(generation.animate.viewportKeyframes),
          worlds: turns.map((sample) => snapshots.get(sample)),
        };
      }
      frames.push(frame);
    }
    previousTurn = resolvedTurn;
  });

  return frames;
}

function collectViewportRanges(passage, generationRequests) {
  const viewports = [passage.viewport, ...generationRequests.map(({ generation }) => generation.viewport)];
  const requests = [];
  viewports.forEach((viewport) => {
    const range = viewport?.encompass?.generations;
    if (!range) return;
    if (!Array.isArray(range) || range.length !== 2) {
      throw new TypeError('Viewport encompass.generations must be a two-item array');
    }
    const start = asNonNegativeInteger(range[0], 'viewport range start');
    const end = asNonNegativeInteger(range[1], 'viewport range end');
    if (end < start) throw new RangeError('Viewport generation range must be ascending');
    if (!requests.some((request) => request.viewport === viewport)) {
      requests.push({ viewport, start, end, bounds: emptyBounds() });
    }
  });
  return requests;
}

function resolveViewportBounds(viewport, requests) {
  if (!viewport.encompass) return viewport;
  const request = requests.find((candidate) => candidate.viewport === viewport);
  if (!request || !Number.isFinite(request.bounds.minX)) {
    throw new RangeError('Cannot encompass a generation range with no live cells');
  }
  return {
    bounds: request.bounds,
    padding: viewport.encompass.padding ?? 2,
  };
}

function sampleTurns(start, end, count, curve = 1) {
  const frameCount = Math.max(2, asNonNegativeInteger(count, 'animation frames'));
  const exponent = positiveNumber(curve, 'animation turn curve');
  if (start === end) return [end];
  return [...new Set(Array.from({ length: frameCount }, (_, index) => (
    Math.round(start + (end - start) * ((index / (frameCount - 1)) ** exponent))
  )))];
}

function compileViewportKeyframes(keyframes) {
  if (keyframes === undefined) return [];
  if (!Array.isArray(keyframes)) {
    throw new TypeError('animation viewportKeyframes must be an array');
  }
  let previous = 0;
  return keyframes.map((keyframe, index) => {
    const at = keyframe?.at;
    if (!Number.isFinite(at) || at <= previous || at >= 1) {
      throw new RangeError(`viewport keyframe ${index} must have an ascending at value between 0 and 1`);
    }
    previous = at;
    return {
      at,
      viewport: {
        center: keyframe.center,
        cellsWide: keyframe.cellsWide,
      },
    };
  });
}

function worldFromCells(cells) {
  const world = new Set();
  cells.forEach((cell, index) => {
    if (!Array.isArray(cell) || cell.length !== 2 || !cell.every(Number.isInteger)) {
      throw new TypeError(`Cell ${index} must be an [x, y] integer pair`);
    }
    world.add(key(cell[0], cell[1]));
  });
  return world;
}

function evolve(world) {
  const neighborCounts = countNeighbors(world);
  const next = new Set();
  neighborCounts.forEach((count, cell) => {
    if (count === 3 || (count === 2 && world.has(cell))) next.add(cell);
  });
  return next;
}

function classify(world) {
  const neighborCounts = countNeighbors(world);
  const predictions = [];
  world.forEach((cell) => {
    const count = neighborCounts.get(cell) ?? 0;
    const [x, y] = coordinates(cell);
    predictions.push({ x, y, count, outcome: count === 2 || count === 3 ? 'survives' : 'dies' });
  });
  neighborCounts.forEach((count, cell) => {
    if (count !== 3 || world.has(cell)) return;
    const [x, y] = coordinates(cell);
    predictions.push({ x, y, count, outcome: 'born' });
  });
  return predictions;
}

function countNeighbors(world) {
  const counts = new Map();
  world.forEach((cell) => {
    const [x, y] = coordinates(cell);
    NEIGHBORS.forEach(([dx, dy]) => {
      const neighbor = key(x + dx, y + dy);
      counts.set(neighbor, (counts.get(neighbor) ?? 0) + 1);
    });
  });
  return counts;
}

function includeWorldInBounds(bounds, world) {
  world.forEach((cell) => {
    const [x, y] = coordinates(cell);
    bounds.minX = Math.min(bounds.minX, x);
    bounds.maxX = Math.max(bounds.maxX, x);
    bounds.minY = Math.min(bounds.minY, y);
    bounds.maxY = Math.max(bounds.maxY, y);
  });
}

function emptyBounds() {
  return {
    minX: Infinity,
    maxX: -Infinity,
    minY: Infinity,
    maxY: -Infinity,
  };
}

function asNonNegativeInteger(value, label) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${label} must be a non-negative integer`);
  }
  return value;
}

function positiveNumber(value, label) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new TypeError(`${label} must be a positive number`);
  }
  return value;
}
