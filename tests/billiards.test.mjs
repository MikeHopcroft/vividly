import assert from 'node:assert/strict';
import test from 'node:test';
import { BilliardsSimulation } from '../site/slides/experiments/pool-table-break/billiards.js';

const snapshot = simulation => simulation.balls.map(({ n, x, y, vx, vy, q, state, ft }) => ({
  n, x, y, vx, vy, q: [...q], state, ft,
}));

test('a seed reproduces the rack, shot, final positions and ball orientations', () => {
  const simulation = new BilliardsSimulation(7);
  const rack = snapshot(simulation);
  simulation.finish();
  const final = snapshot(simulation);
  const ticks = simulation.ticks;
  simulation.reset();
  assert.deepEqual(snapshot(simulation), rack);
  for (let i = 0; i < 4000; i++) simulation.step();
  simulation.finish();
  assert.deepEqual(snapshot(simulation), final);
  assert.equal(simulation.ticks, ticks);
});

test('different seeds produce different reproducible breaks', () => {
  const a = new BilliardsSimulation(7);
  const b = new BilliardsSimulation(42);
  assert.notDeepEqual(snapshot(a), snapshot(b));
  a.finish();
  b.finish();
  assert.notDeepEqual(snapshot(a), snapshot(b));
});

test('the cue strikes at 460ms, with no texture rotation before contact', () => {
  const simulation = new BilliardsSimulation(7);
  const rack = snapshot(simulation);
  for (let i = 0; i < 1103; i++) simulation.step();
  assert.equal(simulation.struck, false);
  assert.deepEqual(simulation.balls.map(ball => ball.q), rack.map(ball => ball.q));
  assert.ok(simulation.balls.every(ball => ball.vx === 0 && ball.vy === 0));
  simulation.step();
  assert.equal(simulation.struck, true);
  assert.equal(simulation.ticks/2400, .46);
  for (let i = 0; i < 48; i++) simulation.step();
  assert.notDeepEqual(simulation.cueBall.q, rack[0].q);
  assert.deepEqual(simulation.balls.slice(1).map(ball => ball.q), rack.slice(1).map(ball => ball.q));
});

test('supported seed boundaries settle with frozen positions and textures', () => {
  for (const seed of [0, 7, 42, 0xFFFFFFFF]) {
    const simulation = new BilliardsSimulation(seed);
    simulation.finish();
    assert.equal(simulation.resting, true);
    assert.equal(simulation.balls.length, 16);
    assert.ok(simulation.balls.every(ball => ball.state !== 'falling'));
    for (const ball of simulation.balls) {
      assert.equal(ball.vx, 0);
      assert.equal(ball.vy, 0);
      assert.ok([ball.x, ball.y, ...ball.q].every(Number.isFinite));
      assert.ok(Math.abs(Math.hypot(...ball.q) - 1) < 1e-10);
    }
    const settled = snapshot(simulation);
    for (let i = 0; i < 2400; i++) simulation.step();
    assert.deepEqual(snapshot(simulation), settled);
  }
});

test('the rack follows eight-ball rules on the compact horizontal table', () => {
  for (const seed of [0, 7, 42, 0xFFFFFFFF]) {
    const simulation = new BilliardsSimulation(seed);
    const rack = simulation.balls.slice(1);
    assert.equal(rack[0].n, 1);
    assert.equal(rack[4].n, 8);
    assert.equal(new Set(simulation.balls.map(ball => ball.n)).size, 16);
    assert.notEqual(rack[10].n < 8, rack[14].n < 8);
    assert.ok(simulation.cueBall.x < rack[0].x);
    assert.equal(simulation.walls[1].pos, 1856);
    assert.equal(simulation.walls[3].pos, 1028);
    assert.equal(simulation.pockets.length, 6);
    assert.ok(rack.every(ball => ball.x > 28.575 && ball.x < 1856 - 28.575
      && ball.y > 28.575 && ball.y < 1028 - 28.575));
  }
});

test('each pocket mouth admits a ball and has wood behind it within the wider rails', () => {
  const simulation = new BilliardsSimulation(7);
  const diameter = 57.15;
  const longWall = simulation.walls[2];
  const sideMouth = longWall.ranges[1][0] - longWall.ranges[0][1];
  const cornerMouth = Math.hypot(simulation.walls[0].ranges[0][0], longWall.ranges[0][0]);
  assert.ok(sideMouth > diameter);
  assert.ok(cornerMouth > diameter);
  for (const pocket of simulation.pockets) {
    assert.ok(pocket.r*2 > diameter);
    assert.ok(pocket.x - pocket.r >= -100 + 24 && pocket.x + pocket.r <= 1856 + 100 - 24);
    assert.ok(pocket.y - pocket.r >= -100 + 24 && pocket.y + pocket.r <= 1028 + 100 - 24);
  }
});

test('balls entering any pocket finish falling instead of resting in a pocket mouth', () => {
  const simulation = new BilliardsSimulation(7);
  for (const pocket of simulation.pockets) {
    simulation.reset();
    simulation.struck = true;
    simulation.ticks = 4800;
    simulation.cueBall.x = pocket.x;
    simulation.cueBall.y = pocket.y;
    simulation.step();
    assert.equal(simulation.cueBall.state, 'falling');
    simulation.finish();
    assert.equal(simulation.cueBall.state, 'gone');
  }
});

test('invalid seeds are rejected instead of silently selecting a different break', () => {
  for (const seed of [-1, .5, 2**32, NaN, Infinity, '7', null, undefined]) {
    assert.throws(() => new BilliardsSimulation(seed), /breakSeed must be an integer/);
  }
});

test('fixed-pixel balls fit the rack and pocket mouths at different table widths', () => {
  for (const tableWidth of [248, 512, 720]) {
    const radius = 20.8*2056/(2*tableWidth);
    const simulation = new BilliardsSimulation(7, radius);
    const rack = simulation.balls.slice(1);
    assert.ok(rack.every(ball => ball.x >= radius && ball.x <= 1856 - radius
      && ball.y >= radius && ball.y <= 1028 - radius));
    const longWall = simulation.walls[2];
    assert.ok(longWall.ranges[1][0] - longWall.ranges[0][1] > 2*radius);
    assert.ok(Math.hypot(simulation.walls[0].ranges[0][0], longWall.ranges[0][0]) > 2*radius);
    assert.ok(simulation.pockets.every(pocket => pocket.r > radius));
    simulation.finish();
    assert.equal(simulation.resting, true);
  }
});

test('collisions use the larger visible radius, not the original ball radius', () => {
  const simulation = new BilliardsSimulation(7, 40.21875);
  simulation.struck = true;
  simulation.ticks = 4800;
  const [a, b] = simulation.balls;
  simulation.balls = [a, b];
  Object.assign(a, { x: 500, y: 500, vx: 300, vy: 0 });
  Object.assign(b, { x: 580, y: 500, vx: 0, vy: 0 });
  simulation.step();
  assert.ok(a.vx < 30);
  assert.ok(b.vx > 250);
});

test('resizing reproduces the seeded break at the same time and restores its settled state', () => {
  const resized = new BilliardsSimulation(7);
  const direct = new BilliardsSimulation(7, 40.21875);
  for (let i = 0; i < 4000; i++) {
    resized.step();
    direct.step();
  }
  resized.setRadius(40.21875);
  assert.equal(resized.ticks, direct.ticks);
  assert.deepEqual(snapshot(resized), snapshot(direct));
  resized.finish();
  resized.setRadius(28.575);
  const original = new BilliardsSimulation(7);
  original.finish();
  assert.deepEqual(snapshot(resized), snapshot(original));
});

test('invalid ball radii are rejected', () => {
  for (const radius of [0, -1, NaN, Infinity, '40', null]) {
    assert.throws(() => new BilliardsSimulation(7, radius), /radius must be a positive finite number/);
  }
});
