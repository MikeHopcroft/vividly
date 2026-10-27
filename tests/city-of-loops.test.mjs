import assert from 'node:assert/strict';
import test from 'node:test';
import { ENDING_TIMING, SCENES, createCityRenderer } from '../site/slides/why-vividly/city-of-loops/engine.js';
import {
  NODES, EDGES, SKETCH_STROKES, SKETCH_TIMING, cityTransform, drawSketch,
} from '../site/slides/why-vividly/city-of-loops/sketch.js';

test('one combined sketch step retains both narrative beats and the later scenes', () => {
  assert.deepEqual(SCENES.map(scene => scene.key), [
    'problem', 'gears', 'first-loop', 'drivers', 'zoom', 'headlights', 'pull',
  ]);
  assert.equal(SCENES[2].duration, SKETCH_TIMING.duration);
  assert.match(SCENES[2].expansion.title, /interconnected/);
});

test('the closing title incorporates the Vividly SVG with an accessible name', () => {
  assert.match(SCENES.at(-1).ending.title, /^With <img /);
  assert.match(SCENES.at(-1).ending.title, /\/vividly\/assets\/logo\.svg"/);
  assert.match(SCENES.at(-1).ending.title,
    /alt="Vividly"><span class="closing-comma">,<\/span> you direct\.$/);
});

test('all loops, roads and arrowheads have stable unique IDs and finish within the sequence', () => {
  assert.equal(SKETCH_STROKES.length, NODES.length * 2 + EDGES.length);
  assert.equal(new Set(SKETCH_STROKES.map(stroke => stroke.id)).size, SKETCH_STROKES.length);
  for (const stroke of SKETCH_STROKES) {
    assert.ok(stroke.duration > 0);
    assert.ok(stroke.start + stroke.duration <= SKETCH_TIMING.duration, stroke.id);
    assert.ok(stroke.points.flat().every(Number.isFinite));
  }
  const center = SKETCH_STROKES.find(stroke => stroke.id === 'loop-center');
  assert.equal(center.points.length, 289);
  assert.notDeepEqual(center.points[0], center.points[96]);
  const arrow = SKETCH_STROKES.find(stroke => stroke.id === 'loop-center-arrow');
  assert.equal(arrow.start, center.start + center.duration);
  const neighbors = SKETCH_STROKES.filter(stroke => (
    ['loop-upper-middle', 'loop-upper-right'].includes(stroke.id)
  ));
  const triangle = SKETCH_STROKES.filter(stroke => (
    ['road-upper-middle-center', 'road-upper-middle-upper-right', 'road-upper-right-center']
      .includes(stroke.id)
  ));
  assert.equal(triangle.length, 3);
  assert.ok(triangle.every(road => neighbors.every(
    loop => loop.start + loop.duration <= road.start,
  )));
  assert.ok(SKETCH_STROKES.filter(stroke => stroke.id.startsWith('road-'))
    .some((stroke, index, roads) => roads.some(
      (other, otherIndex) => index !== otherIndex
        && other.start > stroke.start && other.start < stroke.start + stroke.duration,
    )));
});

test('readiness ends at the last transient without shortening animation pacing', () => {
  const sketchEnd = Math.max(...SKETCH_STROKES.map(stroke => stroke.start + stroke.duration));
  assert.equal(SKETCH_TIMING.duration, sketchEnd);
  assert.ok(SKETCH_TIMING.duration >= SKETCH_TIMING.gearsEnd);
  assert.ok(SKETCH_TIMING.duration >= SKETCH_TIMING.expansion + .6);
  assert.deepEqual(SCENES.map(scene => Number(scene.duration.toFixed(2))), [
    3.5, 1.3, 9.53, 1.3, 12.2, 1.3, 12,
  ]);
  assert.equal(SCENES.at(-1).duration, ENDING_TIMING.duration);
  assert.ok(SCENES.at(-1).duration > ENDING_TIMING.questionEnd);
});

test('the lab and presentation share exact 1920 by 1080 registration', () => {
  assert.deepEqual(cityTransform(1920, 1080), { ox: 960, oy: 540, scale: 540, baseScale: 540 });
  assert.deepEqual(cityTransform(960, 540), { ox: 480, oy: 270, scale: 270, baseScale: 270 });
});

test('arrowheads vary in clock position and have curved, asymmetric wings', () => {
  const hours = [];
  const shapes = [];
  for (const [index, name] of [
    'upper-left', 'upper-middle', 'upper-right', 'middle-left', 'center',
    'middle-right', 'lower-left', 'lower-middle', 'lower-right',
  ].entries()) {
    const loop = SKETCH_STROKES.find(stroke => stroke.id === `loop-${name}`);
    const arrow = SKETCH_STROKES.find(stroke => stroke.id === `loop-${name}-arrow`);
    const tip = loop.points.at(-1);
    assert.deepEqual(arrow.points[8], tip);
    const node = NODES[index];
    const angle = Math.atan2(tip[1] - node.y, tip[0] - node.x);
    const hour = ((angle / (Math.PI * 2) * 12 + 3) % 12 + 12) % 12;
    const topHour = hour < 3 ? hour + 12 : hour;
    assert.ok(topHour >= 10 && topHour <= 14, `${name}: ${topHour}`);
    hours.push(topHour);
    const left = arrow.points[0];
    const right = arrow.points.at(-1);
    const leftLength = Math.hypot(left[0] - tip[0], left[1] - tip[1]);
    const rightLength = Math.hypot(right[0] - tip[0], right[1] - tip[1]);
    assert.ok(Math.abs(leftLength - rightLength) > node.r * .005, name);
    const middle = arrow.points[4];
    const bow = Math.abs(
      (middle[0] - tip[0]) * (left[1] - tip[1])
      - (middle[1] - tip[1]) * (left[0] - tip[0]),
    ) / leftLength;
    assert.ok(bow > node.r * .01, name);
    shapes.push((leftLength / rightLength).toFixed(3));
  }
  assert.ok(Math.max(...hours) - Math.min(...hours) > 3);
  assert.equal(new Set(shapes).size, 9);
});

test('central passes visibly drift apart without changing the three-turn timing', () => {
  const center = SKETCH_STROKES.find(stroke => stroke.id === 'loop-center');
  assert.equal(center.duration, 2.8);
  for (let lap = 0; lap < 2; lap += 1) {
    const separations = Array.from({ length: 96 }, (_, sample) => {
      const a = center.points[lap * 96 + sample];
      const b = center.points[(lap + 1) * 96 + sample];
      return Math.hypot(a[0] - b[0], a[1] - b[1]) * 540;
    });
    assert.ok(Math.max(...separations) > 7);
    assert.ok(separations.reduce((sum, value) => sum + value, 0) / 96 > 3);
  }
  assert.equal(SKETCH_TIMING.gearsEnd, 3.6);
  assert.equal(SKETCH_TIMING.cityFade, 1);
});

test('partial drawing interpolates stroke tips and deterministic redraws match', () => {
  const calls = [];
  const ctx = new Proxy({}, {
    get: (_, name) => (...args) => calls.push([name, ...args]),
    set: () => true,
  });
  const render = time => {
    calls.length = 0;
    drawSketch(ctx, cityTransform(1920, 1080), time);
    return structuredClone(calls);
  };
  assert.equal(render(0).filter(call => call[0] === 'stroke').length, 0);
  const partial = render(1);
  assert.equal(partial.filter(call => call[0] === 'stroke').length, 1);
  assert.deepEqual(render(1), partial);
  assert.equal(render(SKETCH_TIMING.duration).filter(call => call[0] === 'stroke').length,
    SKETCH_STROKES.length);
});

test('scene readiness, settling and ambient motion preserve lifecycle behavior', t => {
  let callback;
  let time = 1000;
  const rotations = [];
  let gearLabels = 0;
  const ctx = new Proxy({}, {
    get: (_, name) => {
      if (name === 'rotate') return angle => rotations.push(angle);
      if (name === 'fillText') return text => { if (text === 'Ideate') gearLabels += 1; };
      if (name === 'measureText') return () => ({ width: 100 });
      if (name === 'createRadialGradient') return () => ({ addColorStop() {} });
      return () => {};
    },
    set: () => true,
  });
  const canvas = {
    getContext: () => ctx,
    getBoundingClientRect: () => ({ width: 1920, height: 1080 }),
  };
  t.mock.method(globalThis, 'setTimeout', () => 1);
  t.mock.method(globalThis, 'clearTimeout', () => {});
  const globals = {
    window: { devicePixelRatio: 1, setTimeout: () => 1, clearTimeout: () => {} },
    document: { createElement: () => canvas },
    ResizeObserver: class { observe() {} disconnect() {} },
    requestAnimationFrame: next => { callback = next; return 1; },
    cancelAnimationFrame: () => { callback = null; },
  };
  for (const [key, value] of Object.entries(globals)) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, key);
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
    t.after(() => {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    });
  }
  const progress = [];
  const renderer = createCityRenderer(canvas, {
    onProgress: (value, elapsed) => progress.push([value, elapsed]),
  });
  const tick = () => {
    const next = callback;
    callback = null;
    time += 1000 / 60;
    next(time);
  };
  renderer.setScene(1);
  renderer.start();
  for (let index = 0; index < 60; index += 1) tick();
  const gearPhase = rotations.at(-1);
  renderer.transitionToScene(2, 1);
  assert.equal(rotations.at(-1), gearPhase);
  tick();
  assert.ok(rotations.at(-1) > gearPhase);
  for (let index = 0; index < 90; index += 1) tick();
  const labelsDuringFade = gearLabels;
  for (let index = 0; index < 90; index += 1) tick();
  assert.ok(gearLabels > labelsDuringFade);
  while (progress.at(-1)[1] < SKETCH_TIMING.gearsEnd + .05) tick();
  const countAfterFade = gearLabels;
  for (let index = 0; index < 600 && callback; index += 1) tick();
  assert.equal(gearLabels, countAfterFade);
  assert.equal(callback, null);
  assert.ok(progress.at(-1)[0] >= 1);
  renderer.setScene(2);
  assert.equal(progress.at(-1)[1], 0);
  assert.equal(renderer.finishScene(), true);
  assert.equal(progress.at(-1)[1], SKETCH_TIMING.duration);
  assert.equal(renderer.finishScene(), false);
  renderer.setScene(2);
  assert.equal(renderer.finishScene(-1), true);
  assert.equal(progress.at(-1)[1], 0);
  renderer.destroy();
  assert.equal(callback, null);

  const readiness = createCityRenderer(canvas, {
    onProgress: (value, elapsed) => progress.push([value, elapsed]),
  });
  for (const [index, scene] of SCENES.entries()) {
    readiness.setScene(index);
    readiness.start();
    tick();
    assert.deepEqual(progress.at(-1), [0, 0]);
    while (progress.at(-1)[1] < scene.duration - .02) tick();
    assert.ok(progress.at(-1)[0] < 1, scene.key);
    while (progress.at(-1)[1] < scene.duration) tick();
    assert.ok(progress.at(-1)[0] >= 1, scene.key);
    assert.equal(readiness.finishScene(), false, scene.key);
    assert.equal(Boolean(callback), scene.key !== 'first-loop', scene.key);
    readiness.stop();
    readiness.setScene(index);
    assert.equal(readiness.finishScene(), true, scene.key);
    assert.deepEqual(progress.at(-1), [1, scene.duration]);
    assert.equal(readiness.finishScene(), false, scene.key);
    readiness.setScene(index);
    assert.equal(readiness.finishScene(-1), true, scene.key);
    assert.deepEqual(progress.at(-1), [1, 0]);
  }
  readiness.destroy();

  const reduced = createCityRenderer(canvas, {
    reducedMotion: true,
    onProgress: (value, elapsed) => progress.push([value, elapsed]),
  });
  const labelsBeforeReduced = gearLabels;
  reduced.setScene(2);
  assert.equal(gearLabels, labelsBeforeReduced);
  assert.deepEqual(progress.at(-1), [1, SKETCH_TIMING.duration]);
  reduced.start();
  tick();
  assert.equal(callback, null);
  for (const [index, scene] of SCENES.entries()) {
    reduced.setScene(index);
    assert.deepEqual(progress.at(-1), [1, scene.duration]);
    assert.equal(reduced.finishScene(), false, scene.key);
  }
  reduced.destroy();

  const labelsBeforeLab = gearLabels;
  const lab = createCityRenderer(canvas, { composition: true, reducedMotion: true });
  lab.start();
  lab.stop();
  assert.equal(gearLabels, labelsBeforeLab);
  assert.equal(callback, null);
  lab.destroy();
});
