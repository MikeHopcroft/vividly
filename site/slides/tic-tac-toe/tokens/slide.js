import { Slide } from "vividly/runtime/slide.js";
import { HIDDEN_SIZE, INPUT_TOKENS, OUTPUT_TOKENS, VOCABULARY_SIZE } from "./data.js";
import {
  CELL, GUTTER, MATRIX_WIDTH, format, randomSequence, svgElement, size, dots, gap,
} from "../mlp-diagram.js";

export const meta = {
  template: "./slide.html",
  styles: ["./slide.css"],
  steps: 1,
};

const GAP_HEIGHT = 17;
const BLOCK_GAP = 12;

function inputLayout() {
  const rows = [];
  const blocks = [];
  let height = 0;
  INPUT_TOKENS.forEach(({ id }, position) => {
    if (position) height += BLOCK_GAP;
    const top = height;
    for (const row of [
      { index: 0 }, { omitted: id - 1 }, { index: id, active: true },
      { omitted: VOCABULARY_SIZE - id - 2 }, { index: VOCABULARY_SIZE - 1 },
    ]) {
      rows.push({ ...row, y: height, position });
      height += row.omitted === undefined ? CELL : GAP_HEIGHT;
    }
    blocks.push({ top, height: height - top });
  });
  return { rows, blocks, height };
}

function renderInput(root) {
  const { rows, blocks, height } = inputLayout();
  const weights = root.querySelector(".input-weights");
  const input = root.querySelector(".input-vector");
  const slots = root.querySelector(".token-slots");
  slots.style.height = `${height}px`;
  size(weights, GUTTER + MATRIX_WIDTH, height);
  size(input, CELL + 4, height);
  const random = randomSequence(11);
  blocks.forEach((block, position) => {
    if (position) {
      for (const [svg, width] of [[weights, GUTTER + MATRIX_WIDTH], [input, CELL + 4]]) {
        svgElement(svg, "line", {
          x1: 0, x2: width, y1: block.top - BLOCK_GAP / 2,
          y2: block.top - BLOCK_GAP / 2, class: "block-divider",
        });
      }
    }
    const token = INPUT_TOKENS[position];
    const slot = document.createElement("div");
    slot.className = "token-slot";
    slot.dataset.position = position;
    slot.dataset.tokenId = token.id;
    slot.style.top = `${block.top + 6}px`;
    slot.style.height = `${block.height - 6}px`;
    slot.innerHTML = `<div class="slot-meta"><span class="token-position">POS ${position + 1}</span><span class="token-id">#${format(token.id)}</span></div><code class="token-text"></code>`;
    slot.querySelector("code").textContent = JSON.stringify(token.text);
    slots.append(slot);
  });
  for (const row of rows) {
    if (row.omitted !== undefined) {
      gap(weights, row.y, row.omitted, GAP_HEIGHT);
      svgElement(input, "text", { x: CELL / 2 + 2, y: row.y + GAP_HEIGHT / 2 + 5, class: "ellipsis" }, "⋮");
      continue;
    }
    const group = svgElement(weights, "g", {
      class: row.active ? "selected-row" : "weight-row",
      "data-position": row.position, "data-token-id": row.index,
    });
    if (row.active) svgElement(group, "rect", {
      x: GUTTER, y: row.y, width: MATRIX_WIDTH, height: CELL, rx: 3, class: "row-highlight",
    });
    svgElement(group, "text", { x: GUTTER - 6, y: row.y + CELL - 2, class: "row-index" }, format(row.index));
    dots(group, GUTTER, row.y, random, Boolean(row.active));
    svgElement(input, "circle", {
      cx: CELL / 2 + 2, cy: row.y + CELL / 2, r: CELL * .38,
      class: `binary-value${row.active ? " active" : ""}`,
    });
  }
}

function renderHidden(root) {
  const bias = root.querySelector(".hidden-bias");
  size(bias, GUTTER + MATRIX_WIDTH, CELL);
  dots(bias, GUTTER, 0, randomSequence(23));
  const hidden = root.querySelector(".hidden-vector");
  size(hidden, MATRIX_WIDTH + 8, CELL + 8);
  const random = randomSequence(5);
  for (let column = 0; column < HIDDEN_SIZE; column += 1) {
    const value = random() < .4 ? 0 : random();
    svgElement(hidden, "circle", {
      cx: 4 + column * CELL + CELL / 2, cy: 4 + CELL / 2,
      r: value ? Math.max(1.5, value * CELL * .47) : 2,
      class: value ? "positive" : "zero-activation",
    });
  }
}

function renderOutput(root) {
  const weights = root.querySelector(".output-weights");
  const bias = root.querySelector(".output-bias");
  const height = 6 * CELL + 22;
  size(weights, GUTTER + MATRIX_WIDTH, height);
  size(bias, CELL, height);
  const weightRandom = randomSequence(41);
  const biasRandom = randomSequence(42);
  const rows = [0, 1, 2, VOCABULARY_SIZE - 3, VOCABULARY_SIZE - 2, VOCABULARY_SIZE - 1];
  rows.forEach((row, index) => {
    const y = index * CELL + (index >= 3 ? 22 : 0);
    if (index === 3) {
      gap(weights, 3 * CELL, VOCABULARY_SIZE - 6, 22);
      svgElement(bias, "text", { x: CELL / 2, y: 3 * CELL + 16, class: "ellipsis" }, "⋮");
    }
    svgElement(weights, "text", { x: GUTTER - 6, y: y + CELL - 2, class: "row-index" }, format(row));
    dots(weights, GUTTER, y, weightRandom);
    dots(bias, 0, y, biasRandom, true, 1);
  });
  const candidates = root.querySelector(".token-scores");
  OUTPUT_TOKENS.forEach((token, index) => {
    const row = document.createElement("li");
    row.className = `token-score${index === 0 ? " winner" : ""}`;
    row.dataset.tokenId = token.id;
    row.title = `Token #${format(token.id)}${index === 0 ? " · argmax" : ""}`;
    row.innerHTML = `<code></code><div class="score-bar" aria-hidden="true"><span style="width:${token.score * 10}%"></span></div><span class="score-value">${token.score.toFixed(2)}</span>`;
    row.querySelector("code").textContent = JSON.stringify(token.text);
    candidates.append(row);
  });
  const sentence = root.querySelector(".sentence");
  sentence.append(INPUT_TOKENS.map(token => token.text).join(""));
  const winner = document.createElement("mark");
  winner.textContent = OUTPUT_TOKENS[0].text.trimStart();
  sentence.append(" ", winner);
}

export default class TokenCompletionSlide extends Slide {
  mount(root) {
    this.root = root;
    renderInput(root);
    renderHidden(root);
    renderOutput(root);
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(root);
  }

  enter() {
    this.resize();
  }

  resize() {
    const { clientWidth, clientHeight } = this.root;
    if (clientWidth && clientHeight) {
      this.root.style.setProperty("--token-scale", Math.min(clientWidth / 1920, clientHeight / 1080));
    }
  }

  unmount() {
    this.resizeObserver.disconnect();
    this.root.style.removeProperty("--token-scale");
    this.root = null;
  }
}
