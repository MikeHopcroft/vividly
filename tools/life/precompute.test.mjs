import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { parse } from 'yaml';
import { compileLifePresentation } from './simulation.mjs';
import {
  canonicalConfig, configHash, decodeFrames, encodeFrames,
} from '../../site/slides/game-of-life/frames.mjs';
import {
  buildAsset, defaultManifest, defaultOutput, findConfig, precompute,
} from './precompute.mjs';

const config = {
  passages: [{
    id: 'blinker',
    initialCells: [[-1, 0], [0, 0], [1, 0]],
    viewport: { center: [0, 0], cellsWide: 8 },
    generations: [{ turn: 0, mode: 'explain' }, { turn: 2, mode: 'normal' }],
  }],
};

test('configuration hashes ignore object key order but preserve scenario changes', async () => {
  assert.equal(await configHash({ b: 2, a: [1, 2] }), await configHash({ a: [1, 2], b: 2 }));
  assert.notEqual(await configHash({ a: [1, 2] }), await configHash({ a: [2, 1] }));
  assert.throws(() => canonicalConfig({ turn: Infinity }), /JSON-compatible/);
});

test('extracted compiler preserves blinker predictions and deterministic worlds', () => {
  const frames = compileLifePresentation(config);
  assert.equal(frames.length, 4);
  assert.deepEqual(frames[2].world, new Set(['0,-1', '0,0', '0,1']));
  assert.deepEqual(frames[3].world, new Set(['-1,0', '0,0', '1,0']));
  assert.equal(frames[1].predictions.filter((cell) => cell.outcome === 'born').length, 2);
});

test('serialization round-trips every field and rejects malformed/stale data', async () => {
  const asset = JSON.parse(await buildAsset(config));
  const hash = await configHash(config);
  const frames = decodeFrames(asset, hash);
  assert.deepEqual(encodeFrames(frames), asset.simulations[hash].frames);
  assert.throws(() => decodeFrames(asset, '0'.repeat(64)), /stale Life data/);
  for (const alter of [
    (data) => { data.schemaVersion = 2; },
    (data) => { data.simulations[hash].frames[0].world = ['invalid']; },
    (data) => { data.simulations[hash].frames[0].viewport.center = []; },
    (data) => { data.simulations[hash].frames[1].predictions[0].count = 9; },
    (data) => { data.simulations[hash].frames[0].total = 999; },
  ]) {
    const changed = structuredClone(asset);
    alter(changed);
    assert.throws(() => decodeFrames(changed, hash), /Regenerate Life data/);
  }
});

test('manifest selection rejects missing/duplicate slides and supports sections', () => {
  assert.deepEqual(findConfig({ nodes: [{ type: 'section', children: [
    { type: 'slide', id: 'life', props: config },
  ] }] }, 'life'), config);
  assert.throws(() => findConfig({ nodes: [] }, 'life'), /found 0/);
  assert.throws(() => findConfig({ nodes: [
    { type: 'slide', id: 'life' }, { type: 'slide', id: 'life' },
  ] }, 'life'), /found 2/);
});

test('generation is deterministic; check detects changed inputs/output without writing', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'life-precompute-'));
  try {
    const manifestPath = join(directory, 'life.yaml');
    const outputPath = join(directory, 'frames.json');
    const manifest = { nodes: [{ type: 'slide', id: 'life', props: config }] };
    await writeFile(manifestPath, JSON.stringify(manifest));
    const options = { manifestPath, outputPath };
    await assert.rejects(precompute({ ...options, check: true }), /Missing Life data/);
    await precompute(options);
    const original = await readFile(outputPath, 'utf8');
    await precompute(options);
    assert.equal(await readFile(outputPath, 'utf8'), original);
    await precompute({ ...options, check: true });
    manifest.nodes[0].props = { ...config, passages: [{
      ...config.passages[0], title: 'Changed scenario',
    }] };
    await writeFile(manifestPath, JSON.stringify(manifest));
    await assert.rejects(precompute({ ...options, check: true }), /Stale Life data/);
    assert.equal(await readFile(outputPath, 'utf8'), original);
    await writeFile(outputPath, 'corrupt output\n');
    await assert.rejects(precompute({ ...options, check: true }), /Stale Life data/);
    assert.equal(await readFile(outputPath, 'utf8'), 'corrupt output\n');
  } finally {
    await rm(directory, { recursive: true });
  }
});

test('checked-in full presentation matches fresh compilation and final Acorn world', async () => {
  const manifest = parse(await readFile(defaultManifest, 'utf8'));
  const fullConfig = findConfig(manifest, 'life');
  const generated = await buildAsset(fullConfig);
  assert.equal(await readFile(defaultOutput, 'utf8'), generated);
  const frames = decodeFrames(JSON.parse(generated), await configHash(fullConfig));
  assert.equal(frames.length, 25);
  assert.equal(frames.at(-1).turn, 5206);
  assert.equal(frames.at(-1).world.size, 633);
  assert.equal(frames.at(-1).overlay.size, 7);
  assert(frames.filter((frame) => frame.animation).length > 0);
  const invalid = JSON.parse(generated);
  const hash = await configHash(fullConfig);
  invalid.simulations[hash].frames.find((frame) => frame.animation).animation.worlds = [[] , ['bad']];
  assert.throws(() => decodeFrames(invalid, hash), /cell coordinates/);
});
