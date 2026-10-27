import assert from 'node:assert/strict';
import test from 'node:test';
import { loadWhyVividlyFonts } from '../site/shared/why-vividly-fonts.js';

const setup = (t, load = async () => [{}]) => {
  const links = [];
  const fonts = [];
  const original = Object.getOwnPropertyDescriptor(globalThis, 'document');
  t.after(() => {
    if (original) {
      Object.defineProperty(globalThis, 'document', original);
    } else {
      delete globalThis.document;
    }
  });
  globalThis.document = {
    createElement: () => new EventTarget(),
    head: { appendChild: link => links.push(link) },
    fonts: {
      load: font => {
        fonts.push(font);
        return load(font);
      },
    },
  };
  const ctx = {
    dependency: key => ({ url: () => `https://example.invalid/${key}/font.css` }),
  };
  return { ctx, links, fonts };
};

test('font preload shares stylesheets and waits for both families', async (t) => {
  const { ctx, links, fonts } = setup(t);
  const promise = loadWhyVividlyFonts(ctx);
  assert.equal(loadWhyVividlyFonts(ctx), promise);
  assert.deepEqual(links.map(link => [link.rel, link.href]), [
    ['stylesheet', 'https://example.invalid/archivo/font.css'],
    ['stylesheet', 'https://example.invalid/ibm-plex-mono/font.css'],
  ]);
  links[0].dispatchEvent(new Event('load'));
  await Promise.resolve();
  assert.equal(fonts.length, 0);
  links[1].dispatchEvent(new Event('load'));
  await promise;
  assert.deepEqual(fonts, [
    '400 1em "Archivo Variable"',
    '600 1em "Archivo Variable"',
    '700 1em "Archivo Variable"',
    '720 1em "Archivo Variable"',
    '800 1em "Archivo Variable"',
    '400 1em "IBM Plex Mono"',
  ]);
  assert.equal(loadWhyVividlyFonts(ctx), promise);
  assert.equal(links.length, 2);
});

test('stylesheet failures reject font preload', async (t) => {
  const { ctx, links } = setup(t);
  const promise = loadWhyVividlyFonts(ctx);
  links[0].dispatchEvent(new Event('error'));
  await assert.rejects(promise, /Failed to load presentation font stylesheet/);
});

test('font download failures reject font preload', async (t) => {
  const { ctx, links } = setup(t, async () => {
    throw new Error('Font download failed');
  });
  const promise = loadWhyVividlyFonts(ctx);
  links.forEach(link => link.dispatchEvent(new Event('load')));
  await assert.rejects(promise, /Font download failed/);
});

test('missing font faces reject preload instead of accepting fallback fonts', async (t) => {
  const { ctx, links } = setup(t, async () => []);
  const promise = loadWhyVividlyFonts(ctx);
  links.forEach(link => link.dispatchEvent(new Event('load')));
  await assert.rejects(promise, /Presentation font stylesheet did not provide/);
});
