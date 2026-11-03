import { Slide } from 'vividly/runtime/slide.js';

export const meta = {
  styles: ['./slide.css'],
  steps: 1,
};

const HUES = [
  'Red', 'Orange', 'Yellow', 'Yellow-green', 'Green', 'Teal',
  'Cyan', 'Azure', 'Blue', 'Violet', 'Magenta', 'Rose',
];
const PRIMARY = new Set([0, 60, 240]);
const SECONDARY = new Set([30, 120, 270]);
const BOARD = [1, 0, 2, 0, 1, 0, 2, 0, 0];
const INK = '#1c2733';
const LINE = '#d9e0e6';

// Palette values and the fixed comparison mockup come from color-swatches.html.
const SCHEMES = [
  {
    name: 'Complementary',
    relationship: 'Opposing hues for positive and negative weights',
    note: 'Two opposite hues carry the weight signs; a warm data highlight stays clear of both.',
    palettes: [
      { name: 'Orange / Azure', bg: [210, 16, 95], card: [0, 0, 100], pos: [30, 82, 52], neg: [212, 70, 50], data: [48, 85, 85], select: [150, 52, 42] },
      { name: 'Red / Cyan', bg: [190, 14, 95], card: [0, 0, 100], pos: [4, 74, 52], neg: [188, 66, 43], data: [46, 88, 85], select: [270, 46, 55] },
      { name: 'Magenta / Green', bg: [300, 10, 96], card: [0, 0, 100], pos: [322, 60, 52], neg: [138, 52, 40], data: [45, 85, 85], select: [212, 66, 50] },
    ],
  },
  {
    name: 'Split-complementary',
    relationship: 'A base hue and the two neighbors of its complement',
    note: 'A softer alternative to complementary colors, with the third hue used for the data highlight.',
    palettes: [
      { name: 'Blue / Orange / Chartreuse', bg: [222, 14, 96], card: [0, 0, 100], pos: [30, 82, 52], neg: [226, 66, 52], data: [92, 55, 84], select: [330, 60, 50] },
      { name: 'Red / Teal / Blue', bg: [200, 14, 96], card: [0, 0, 100], pos: [4, 74, 52], neg: [180, 60, 40], data: [232, 60, 86], select: [140, 52, 42] },
    ],
  },
  {
    name: 'Triadic',
    relationship: 'Three hue families, three distinct roles',
    note: 'Positive and negative weights take two colors; the data highlight takes the third.',
    palettes: [
      { name: 'Primaries: Red / Blue / Yellow', bg: [220, 12, 96], card: [0, 0, 100], pos: [2, 72, 52], neg: [226, 66, 52], data: [52, 88, 82], select: [140, 52, 42] },
      { name: 'Secondaries: Orange / Violet / Green', bg: [280, 10, 96], card: [0, 0, 100], pos: [30, 82, 52], neg: [276, 46, 55], data: [130, 45, 84], select: [340, 62, 50] },
    ],
  },
  {
    name: 'Square / Tetradic',
    relationship: 'Four hue families for four visual roles',
    note: 'Positive weights, negative weights, data, and selection each get their own color family.',
    palettes: [
      { name: 'Red / Chartreuse / Cyan / Violet', bg: [210, 12, 96], card: [0, 0, 100], pos: [2, 72, 52], neg: [190, 64, 43], data: [92, 58, 83], select: [280, 48, 56] },
    ],
  },
  {
    name: 'Analogous surfaces',
    relationship: 'Related surfaces with contrasting weight colors',
    note: 'Background, card, and data share a calm color family; opposing dot colors separate the weight signs.',
    palettes: [
      { name: 'Warm paper family', bg: [40, 45, 95], card: [45, 60, 99], pos: [10, 74, 52], neg: [205, 68, 50], data: [42, 85, 83], select: [150, 52, 42] },
      { name: 'Cool slate family', bg: [205, 28, 95], card: [205, 40, 99], pos: [20, 80, 52], neg: [232, 66, 54], data: [190, 55, 84], select: [150, 52, 42] },
    ],
  },
];

function color([hue, saturation, lightness]) {
  return `hsl(${hue} ${saturation}% ${lightness}%)`;
}

function hueName(hue) {
  return HUES[Math.round(hue / 30) % HUES.length];
}

function dots(rows, columns, positive, negative, background, phase = 0) {
  const cell = 20;
  const label = `${rows === 1 ? 'Weights' : 'Weight values'}: ${hueName(positive[0])} positive, ${hueName(negative[0])} negative; dot size shows magnitude`;
  let svg = `<svg viewBox="0 0 ${columns * cell} ${rows * cell}" role="img" aria-label="${label}">
    <rect width="100%" height="100%" fill="${background}" stroke="${LINE}" />`;
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const value = Math.sin(row * 1.7 + column * 0.9 + phase);
      if (Math.abs(value) < 0.14) continue;
      svg += `<circle cx="${column * cell + cell / 2}" cy="${row * cell + cell / 2}"
        r="${Math.max(0.9, (cell / 2 - 0.6) * Math.abs(value))}"
        fill="${color(value >= 0 ? positive : negative)}" />`;
    }
  }
  return `${svg}</svg>`;
}

function board(palette) {
  let table = '<table class="color-board" aria-label="Tic-tac-toe input; selected move in row 2, column 1"><tbody>';
  for (let row = 0; row < 3; row += 1) {
    table += '<tr>';
    for (let column = 0; column < 3; column += 1) {
      const index = row * 3 + column;
      const selected = index === 3;
      const mark = selected ? '&#9679;' : BOARD[index] === 1 ? 'X' : BOARD[index] === 2 ? 'O' : '';
      const background = selected ? color([...palette.select.slice(0, 2), 90]) : color(palette.data);
      const foreground = selected
        ? color([...palette.select.slice(0, 2), 40])
        : BOARD[index] === 1 ? color(palette.neg) : BOARD[index] === 2 ? color(palette.pos) : INK;
      table += `<td style="background:${background};color:${foreground}">${mark}</td>`;
    }
    table += '</tr>';
  }
  return `${table}</tbody></table>`;
}

function swatch(label, value) {
  return `<div class="color-chip">
    <span class="color-chip-paint" style="background:${color(value)}"></span>
    <span class="color-chip-label">${label}</span>
    <code>${value[0]} ${value[1]}% ${value[2]}%</code>
  </div>`;
}

function paletteCard(palette) {
  return `<article class="color-palette">
    <h3>${palette.name}</h3>
    <p class="color-roles">+ ${hueName(palette.pos[0])} / - ${hueName(palette.neg[0])}</p>
    <div class="color-chips">
      ${swatch('Background', palette.bg)}${swatch('Card', palette.card)}
      ${swatch('Positive (+)', palette.pos)}${swatch('Negative (-)', palette.neg)}
      ${swatch('Data', palette.data)}${swatch('Selection', palette.select)}
    </div>
    <div class="color-preview" style="background:${color(palette.bg)}">
      <div class="color-mockup" style="background:${color(palette.card)}">
        <div class="color-preview-column"><span>Input</span>${board(palette)}</div>
        <div class="color-preview-column"><span>Weights</span>${dots(5, 8, palette.pos, palette.neg, '#ffffff')}</div>
        <div class="color-preview-column"><span>Data</span>${dots(5, 1, palette.pos, palette.neg, color(palette.data), 1.1)}</div>
      </div>
    </div>
  </article>`;
}

export default class ColorSchemesSlide extends Slide {
  mount(root) {
    this.events = new AbortController();
    this.schemeIndex ??= 0;
    root.innerHTML = `<section class="color-explorer">
      <header class="color-header">
        <p class="color-eyebrow">Labs / Color</p>
        <h1>Color harmony explorer</h1>
        <p>Keep the mockup fixed. Change the palette. Compare how color separates meaning.</p>
      </header>
      <section class="color-reference" aria-label="Hue family reference">
        <div class="color-reference-heading">
          <h2>Hue families</h2>
          <p>Approximate RYB families: P = primary, S = secondary, T = tertiary. Swatches use HSL.</p>
        </div>
        <div class="color-wheel">${HUES.map((name, index) => {
          const hue = index * 30;
          const tier = PRIMARY.has(hue) ? 'P' : SECONDARY.has(hue) ? 'S' : 'T';
          return `<div class="color-hue">
            <span style="background:${color([hue, 68, 50])}"></span>
            <strong>${name}</strong><small>${hue}&deg; / ${tier}</small>
          </div>`;
        }).join('')}</div>
      </section>
      <div class="color-families" role="group" aria-label="Color harmony families">
        ${SCHEMES.map((scheme, index) => `<button type="button" data-scheme="${index}" aria-pressed="${index === this.schemeIndex}">${scheme.name}</button>`).join('')}
      </div>
      <section class="color-comparison" aria-label="Palette comparison"></section>
      <p class="color-footer">A creative workflow: generate alternatives, compare the same content, then refine.
        Adapted from the Tic-Tac-Toe color-swatches prototype.</p>
    </section>`;
    this.panel = root.querySelector('.color-comparison');
    this.buttons = [...root.querySelectorAll('[data-scheme]')];
    this.renderScheme();
    root.addEventListener('click', (event) => {
      const button = event.target instanceof Element ? event.target.closest('button[data-scheme]') : null;
      if (!button) return;
      this.schemeIndex = Number(button.dataset.scheme);
      this.renderScheme();
    }, { signal: this.events.signal });
  }

  renderScheme() {
    const scheme = SCHEMES[this.schemeIndex];
    for (const [index, button] of this.buttons.entries()) {
      button.setAttribute('aria-pressed', String(index === this.schemeIndex));
    }
    this.panel.innerHTML = `<header class="color-comparison-heading">
      <h2>${scheme.relationship}</h2><p>${scheme.note}</p>
    </header><div class="color-palettes">${scheme.palettes.map(paletteCard).join('')}</div>`;
  }

  unmount() {
    this.events.abort();
  }
}
