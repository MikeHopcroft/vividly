import { createHash, randomUUID } from 'node:crypto';
import { readFile, mkdir, rename, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { parse } from 'yaml';
import { compileLifePresentation } from './simulation.mjs';
import {
  FRAME_SCHEMA_VERSION, configHash, decodeFrames, encodeFrames,
} from '../../site/slides/game-of-life/frames.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
export const defaultManifest = resolve(root, 'site/presentations/life.yaml');
export const defaultOutput = resolve(root, 'site/slides/game-of-life/data/frames.json');

export function findConfig(manifest, slideId) {
  const matches = [];
  const visit = (nodes) => {
    if (!Array.isArray(nodes)) throw new TypeError('Manifest nodes/children must be arrays');
    for (const node of nodes) {
      if (node.type === 'slide' && node.id === slideId) matches.push(node);
      if (node.children !== undefined) visit(node.children);
    }
  };
  visit(manifest?.nodes);
  if (matches.length !== 1) {
    throw new Error(`Expected exactly one slide with id "${slideId}", found ${matches.length}`);
  }
  return matches[0].props;
}

export async function buildAsset(config) {
  const compilerHash = createHash('sha256');
  for (const relative of [
    './simulation.mjs',
    '../../site/slides/game-of-life/cells.mjs',
    '../../site/slides/game-of-life/frames.mjs',
    './precompute.mjs',
  ]) {
    compilerHash.update(relative).update('\0');
    compilerHash.update(await readFile(new URL(relative, import.meta.url))).update('\0');
  }
  const hash = await configHash(config);
  const asset = {
    schemaVersion: FRAME_SCHEMA_VERSION,
    compilerHash: compilerHash.digest('hex'),
    simulations: { [hash]: { frames: encodeFrames(compileLifePresentation(config)) } },
  };
  decodeFrames(asset, hash);
  return `${JSON.stringify(asset)}\n`;
}

export async function precompute({
  manifestPath = defaultManifest, slideId = 'life', outputPath = defaultOutput, check = false,
} = {}) {
  const manifest = parse(await readFile(manifestPath, 'utf8'), { uniqueKeys: true });
  const output = await buildAsset(findConfig(manifest, slideId));
  if (check) {
    let existing;
    try {
      existing = await readFile(outputPath, 'utf8');
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      throw new Error(`Missing Life data: ${outputPath}. Run npm --prefix tools/life run generate`);
    }
    if (existing !== output) {
      throw new Error(`Stale Life data: ${outputPath}. Run npm --prefix tools/life run generate`);
    }
  } else {
    await mkdir(dirname(outputPath), { recursive: true });
    const temporary = `${outputPath}.${randomUUID()}.tmp`;
    try {
      await writeFile(temporary, output, { flag: 'wx' });
      await rename(temporary, outputPath);
    } finally {
      await rm(temporary, { force: true });
    }
  }
  return Buffer.byteLength(output);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const { values } = parseArgs({
      options: {
        manifest: { type: 'string' },
        slide: { type: 'string' },
        output: { type: 'string' },
        check: { type: 'boolean', default: false },
        help: { type: 'boolean', default: false },
      },
    });
    if (values.help) {
      console.log('node tools/life/precompute.mjs [--manifest PATH] [--slide ID] [--output PATH] [--check]');
    } else {
      const bytes = await precompute({
        manifestPath: values.manifest && resolve(values.manifest),
        slideId: values.slide,
        outputPath: values.output && resolve(values.output),
        check: values.check,
      });
      console.log(`${values.check ? 'Verified' : 'Generated'} Life frames (${bytes} bytes)`);
    }
  } catch (error) {
    console.error(`[life precompute] ${error.message}`);
    process.exitCode = 1;
  }
}
