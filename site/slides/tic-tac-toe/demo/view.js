import { chooseLegalMove, encodeBoard, forward } from "./net.js";

const COLORS = {
  positive: "hsl(2 72% 52%)",
  negative: "hsl(226 66% 52%)",
  ink: "#1c2733",
  data: "hsl(52 88% 82%)",
  dataEdge: "hsl(52 34% 50%)",
  line: "#d9e0e6",
  hit: "hsl(140 52% 42%)",
  hitOverlay: "hsl(140 52% 42% / .68)",
  increase: "hsl(140 52% 42%)",
  decrease: "hsl(47 92% 48%)",
};
const EPSILON = 1e-4;
const SCALE = { w1: 2, b1: 2, hidden: 5, w2: 2.4, b2: 2.4 };
const ELEMENT_NAMES = ["expression", "board", "x", "w1", "b1", "h", "w2", "b2", "logits", "argmax", "output"];
export const EXPRESSION_PARTS = ["hidden", "activation", "output", "decision"];
const EXPRESSION_TONES = new Set(["normal", "active", "muted"]);
const NORMAL_EXPRESSION = Object.fromEntries(EXPRESSION_PARTS.map(name => [name, "normal"]));

function maximumAbsolute(data) {
  let maximum = 0;
  for (const value of data) maximum = Math.max(maximum, Math.abs(value));
  return maximum;
}

function scaleFraction(value, maximum, linear = false) {
  const magnitude = Math.abs(value);
  if (magnitude < EPSILON || maximum < EPSILON) return 0;
  if (linear) return Math.min(1, magnitude / maximum);
  return Math.min(1, Math.log1p(magnitude * 4) / Math.log1p(maximum * 4));
}

function matrixSvg(options) {
  const { data, rows, columns } = options;
  const cell = options.cell ?? 10;
  const width = columns * cell;
  const height = rows * cell;
  const radius = cell / 2 - 0.45;
  const maximum = options.scale ?? maximumAbsolute(data);
  const highlights = options.highlights ? new Set(options.highlights) : null;
  let svg = `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true">`;
  svg += `<rect x=".4" y=".4" width="${width - .8}" height="${height - .8}" fill="${options.background ?? "#fbfcfd"}" stroke="${COLORS.line}" stroke-width=".8"/>`;

  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const index = row * columns + column;
      const value = data[index];
      const x = column * cell + cell / 2;
      const y = row * cell + cell / 2;
      if (options.variant === "binary") {
        svg += value
          ? `<circle cx="${x}" cy="${y}" r="${radius}" fill="${COLORS.ink}"/>`
          : `<circle cx="${x}" cy="${y}" r="${radius}" fill="none" stroke="${COLORS.dataEdge}" stroke-width=".8"/>`;
        if (highlights?.has(index)) svg += `<circle cx="${x}" cy="${y}" r="${radius}" fill="${COLORS.hitOverlay}"/>`;
        continue;
      }
      if (options.guides) svg += `<circle cx="${x}" cy="${y}" r="${radius}" fill="none" stroke="${COLORS.dataEdge}" stroke-width=".8"/>`;
      if (options.variant === "hit") {
        if (value) svg += `<circle cx="${x}" cy="${y}" r="${radius}" fill="${COLORS.hit}"/>`;
        continue;
      }
      const fraction = scaleFraction(value, maximum, options.linear);
      if (!fraction) continue;
      const color = value >= 0
        ? options.positiveColor ?? COLORS.positive
        : options.negativeColor ?? COLORS.negative;
      svg += `<circle cx="${x}" cy="${y}" r="${Math.max(.7, radius * fraction)}" fill="${color}"/>`;
    }
  }
  for (const row of options.mutedRows ?? []) {
    svg += `<rect x="0" y="${row * cell}" width="${width}" height="${cell}" fill="rgba(246,248,251,.82)"/>`;
  }
  for (const column of options.mutedColumns ?? []) {
    svg += `<rect x="${column * cell}" y="0" width="${cell}" height="${height}" fill="rgba(246,248,251,.82)"/>`;
  }
  for (const row of options.spotlightRows ?? []) {
    svg += `<rect x=".8" y="${row * cell + .8}" width="${width - 1.6}" height="${cell - 1.6}" fill="none" stroke="${COLORS.hit}" stroke-width="1.6"/>`;
  }
  for (const column of options.spotlightColumns ?? []) {
    svg += `<rect x="${column * cell + .8}" y=".8" width="${cell - 1.6}" height="${height - 1.6}" fill="none" stroke="${COLORS.hit}" stroke-width="1.6"/>`;
  }
  return `${svg}</svg>`;
}

class MlpMatrix extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>
      :host{display:inline-block;line-height:0}
      .frame{display:grid}
      .rich,.schematic{grid-area:1/1;transition:opacity 180ms ease}
      .schematic{display:flex;flex-direction:column;align-items:center;justify-content:center;box-sizing:border-box;color:#263247;white-space:nowrap;overflow:visible;font-family:ui-sans-serif,system-ui}
      .schematic-symbol{font-size:36px;font-weight:650;line-height:1;letter-spacing:-.04em}
      .schematic-dimensions{margin-top:6px;color:#7a8495;font-size:16px;font-weight:650;line-height:1;letter-spacing:.03em}
      .schematic.inline{flex-direction:row;gap:8px}
      .schematic.inline .schematic-dimensions{margin-top:0}
      :host(:not([representation=schematic])) .schematic{opacity:0;pointer-events:none}
      :host([representation=schematic]) .rich{opacity:0;pointer-events:none}
    </style><div class="frame"><div class="rich"></div><div class="schematic"></div></div>`;
  }

  set(options) {
    this.options = { ...this.options, ...options };
    this.render();
    return this;
  }

  setRepresentation(representation) {
    this.setAttribute("representation", representation);
  }

  getGridShape() {
    return { rows: this.options.rows, columns: this.options.columns };
  }

  render() {
    if (!this.options) return;
    const width = this.options.columns * this.options.cell;
    const height = this.options.rows * this.options.cell;
    this.shadowRoot.querySelector(".rich").innerHTML = matrixSvg(this.options);
    const schematic = this.shadowRoot.querySelector(".schematic");
    schematic.style.width = `${width}px`;
    schematic.style.height = `${height}px`;
    schematic.classList.toggle("inline", Boolean(this.options.schematicInline));
    schematic.replaceChildren();
    const symbol = document.createElement("span");
    symbol.className = "schematic-symbol";
    const schematicSymbol = this.options.schematicSymbol ?? "";
    const schematicDimensions = this.options.schematicDimensions ?? `${this.options.rows} × ${this.options.columns}`;
    symbol.textContent = schematicSymbol;
    const dimensions = document.createElement("span");
    dimensions.className = "schematic-dimensions";
    dimensions.textContent = this.options.schematicInline
      ? `(${schematicDimensions})`
      : schematicDimensions;
    schematic.append(symbol, dimensions);
  }
}

class MlpBoard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>
      :host{display:inline-block;line-height:0}
      table{border-collapse:collapse;background:white}
      td{border:2px solid ${COLORS.ink};padding:0;text-align:center;vertical-align:middle;font:750 18px/1 ui-sans-serif,system-ui;cursor:pointer;user-select:none}
      td.x{color:${COLORS.negative}} td.o{color:${COLORS.positive}}
      td.hit{background:hsl(140 52% 42% / .18);color:${COLORS.hit}}
      table.data td:not(.hit){background:${COLORS.data}}
    </style><div></div>`;
    this.shadowRoot.addEventListener("click", event => {
      const cell = event.target.closest("td");
      if (cell) this.dispatchEvent(new CustomEvent("cell-select", { detail: Number(cell.dataset.index) }));
    });
  }

  set(options) {
    this.options = { ...this.options, ...options };
    const { board } = this.options;
    const cell = this.options.cell ?? 30;
    const highlight = this.options.highlight ?? -1;
    let html = `<table class="${this.options.dataBackground ? "data" : ""}">`;
    for (let row = 0; row < 3; row += 1) {
      html += "<tr>";
      for (let column = 0; column < 3; column += 1) {
        const index = row * 3 + column;
        const value = board[index];
        const classes = [value === 1 ? "x" : value === 2 ? "o" : "", index === highlight ? "hit" : ""].filter(Boolean).join(" ");
        const label = value === 1 ? "X" : value === 2 ? "O" : index === highlight ? "●" : "";
        html += `<td data-index="${index}" class="${classes}" style="width:${cell}px;height:${cell}px;font-size:${Math.round(cell * .62)}px">${label}</td>`;
      }
      html += "</tr>";
    }
    this.shadowRoot.querySelector("div").innerHTML = `${html}</table>`;
    return this;
  }
}

class MlpPanel extends HTMLElement {
  static observedAttributes = ["label"];

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>
      :host{display:inline-block;opacity:1;visibility:visible;transition:opacity 220ms ease,visibility 0s linear 0s}
      :host([hidden-state]){opacity:0;visibility:hidden;pointer-events:none;transition:opacity 220ms ease,visibility 0s linear 220ms}
      .card{display:flex;min-width:var(--panel-min-width,auto);box-sizing:border-box;flex-direction:column;align-items:var(--panel-align,flex-start);padding:7px 8px;border:1px solid ${COLORS.line};border-radius:8px;background:white;box-shadow:3px 4px 6px rgba(0,0,0,.16);transition:background 180ms ease,border-color 180ms ease,box-shadow 180ms ease}
      .label{margin-bottom:4px;color:#6b7885;font:500 11px/1.2 ui-sans-serif,system-ui;white-space:nowrap}
      .label b{color:${COLORS.ink};font-weight:700}
      .art{line-height:0}
      :host([schematic-state]) .label{visibility:hidden}
      :host([schematic-state][center-schematic]) .art{transform:translateY(-8.6px)}
      :host([bare-state]) .card{padding:0;border-color:transparent;background:transparent;box-shadow:none}
      :host([bare-state]) .label{display:none}
    </style><div class="card"><div class="label"></div><div class="art"><slot></slot></div></div>`;
  }

  attributeChangedCallback() {
    this.shadowRoot.querySelector(".label").innerHTML = this.getAttribute("label") ?? "";
  }
}

class MlpExpression extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>
      :host{display:block}
      .expression{display:flex;align-items:baseline;justify-content:center;white-space:nowrap;color:${COLORS.ink};font:650 24px/1.35 ui-sans-serif,system-ui;letter-spacing:-.025em}
      .part{display:inline-block;border-radius:5px;padding:2px 1px;transition:color 180ms ease,background 180ms ease,box-shadow 180ms ease}
      .part[data-tone=muted]{color:#aeb6c4}
      .part[data-tone=active]{position:relative;z-index:1;color:#244fc2;background:#e8eeff;box-shadow:0 0 0 3px #e8eeff}
      sub{font-size:.62em;line-height:0}
    </style><div class="expression" aria-label="move equals legal argmax of ReLU of x W 1 plus b 1, times W 2 plus b 2">
      <span class="part" data-part="decision">move = argmax<sub>legal</sub>(</span><span class="part" data-part="activation">ReLU(</span><span class="part" data-part="hidden">xW<sub>1</sub> + b<sub>1</sub></span><span class="part" data-part="activation">)</span><span class="part" data-part="output">W<sub>2</sub> + b<sub>2</sub></span><span class="part" data-part="decision">)</span>
    </div>`;
    this.setState(NORMAL_EXPRESSION);
  }

  setState(nextState = {}) {
    for (const [name, tone] of Object.entries(nextState)) {
      if (!EXPRESSION_PARTS.includes(name)) throw new RangeError(`unknown expression part: ${name}`);
      if (!EXPRESSION_TONES.has(tone)) throw new RangeError(`unknown expression tone: ${tone}`);
      this.shadowRoot.querySelectorAll(`[data-part="${name}"]`).forEach(part => {
        part.dataset.tone = tone;
      });
    }
    return this;
  }
}

class MlpStage extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;width:max-content}
      .grid{display:grid;grid-template-columns:auto auto auto auto;align-items:start;gap:8px 16px;width:max-content}
      ::slotted([slot=expression]){grid-column:3/5;grid-row:1}
      ::slotted([slot=board]){grid-column:1;grid-row:2;align-self:center}
      ::slotted([slot=x]){grid-column:2;grid-row:2}
      ::slotted([slot=w1]){grid-column:3;grid-row:2}
      ::slotted([slot=b1]){grid-column:3;grid-row:3}
      ::slotted([slot=h]){grid-column:3;grid-row:4}
      ::slotted([slot=w2]){grid-column:3;grid-row:5}
      ::slotted([slot=right]){grid-column:4;grid-row:5;display:flex;align-items:flex-start;gap:12px}
    </style><div class="grid"><slot name="expression"></slot><slot name="board"></slot><slot name="x"></slot><slot name="w1"></slot><slot name="b1"></slot><slot name="h"></slot><slot name="w2"></slot><slot name="right"></slot></div>`;
  }
}

for (const [name, constructor] of [["mlp-matrix", MlpMatrix], ["mlp-board", MlpBoard], ["mlp-panel", MlpPanel], ["mlp-expression", MlpExpression], ["mlp-stage", MlpStage]]) {
  if (!customElements.get(name)) customElements.define(name, constructor);
}

function createPanel(slot, label, element, centered = false) {
  const panel = document.createElement("mlp-panel");
  if (slot) panel.slot = slot;
  panel.setAttribute("label", label);
  if (centered) panel.style.setProperty("--panel-align", "center");
  panel.append(element);
  return panel;
}

function createMatrix(options) {
  return document.createElement("mlp-matrix").set(options);
}

function transposeOutputWeights(params) {
  const result = new Float32Array(params.OUT * params.H);
  for (let output = 0; output < params.OUT; output += 1) {
    for (let hidden = 0; hidden < params.H; hidden += 1) {
      result[output * params.H + hidden] = params.Wb[hidden * params.OUT + output];
    }
  }
  return result;
}

function parameterDifference(current, previous) {
  const result = new Float32Array(current.length);
  for (let index = 0; index < current.length; index += 1) {
    result[index] = current[index] - previous[index];
  }
  return result;
}

function bindBoardHover(board, input) {
  let previous = -1;
  board.addEventListener("mousemove", event => {
    const rect = board.getBoundingClientRect();
    const row = Math.max(0, Math.min(2, Math.floor((event.clientY - rect.top) * 3 / rect.height)));
    const column = Math.max(0, Math.min(2, Math.floor((event.clientX - rect.left) * 3 / rect.width)));
    const cell = row * 3 + column;
    if (cell !== previous) {
      previous = cell;
      input.set({ highlights: [cell * 3, cell * 3 + 1, cell * 3 + 2] });
    }
  });
  board.addEventListener("mouseleave", () => {
    previous = -1;
    input.set({ highlights: null });
  });
}

function bindLogitHover(logits, output, getBoard) {
  logits.addEventListener("mousemove", event => {
    const rect = logits.getBoundingClientRect();
    const row = Math.max(0, Math.min(8, Math.floor((event.clientY - rect.top) * 9 / rect.height)));
    output.set({ board: getBoard(), highlight: row, dataBackground: true });
  });
  logits.addEventListener("mouseleave", () => output.dispatchEvent(new CustomEvent("restore-output")));
}

export function createPipelineStage(host, model, initialBoard = new Array(9).fill(0)) {
  const params = model.params;
  let activeParams = params;
  const cell = Math.max(6, Math.min(12, Math.round(920 / params.H)));
  const stage = document.createElement("mlp-stage");
  const elements = {
    expression: document.createElement("mlp-expression"),
    board: document.createElement("mlp-board"),
    x: createMatrix({ data: new Float32Array(27), rows: 27, columns: 1, cell, variant: "binary", background: COLORS.data }),
    w1: createMatrix({ data: params.Wa, rows: 27, columns: params.H, cell, scale: SCALE.w1, schematicSymbol: "W₁", schematicDimensions: `27 × ${params.H}` }),
    b1: createMatrix({ data: params.ba, rows: 1, columns: params.H, cell, scale: SCALE.b1, schematicSymbol: "b₁", schematicDimensions: `1 × ${params.H}`, schematicInline: true }),
    h: createMatrix({ data: new Float32Array(params.H), rows: 1, columns: params.H, cell, scale: SCALE.hidden, background: COLORS.data }),
    w2: createMatrix({ data: transposeOutputWeights(params), rows: 9, columns: params.H, cell, scale: SCALE.w2, schematicSymbol: "W₂ᵀ", schematicDimensions: `9 × ${params.H}` }),
    b2: createMatrix({ data: params.bb, rows: 9, columns: 1, cell, scale: SCALE.b2, schematicSymbol: "b₂ᵀ", schematicDimensions: "9 × 1" }),
    logits: createMatrix({ data: new Float32Array(9), rows: 9, columns: 1, cell, linear: true, background: COLORS.data, guides: true }),
    argmax: createMatrix({ data: new Float32Array(9), rows: 9, columns: 1, cell, variant: "hit", background: COLORS.data, guides: true }),
    output: document.createElement("mlp-board"),
  };

  const panels = {
    expression: createPanel("expression", "<b>computation</b>", elements.expression, true),
    board: createPanel("board", "<b>input</b>", elements.board),
    x: createPanel("x", "<b>xᵀ</b> (27×1)", elements.x, true),
    w1: createPanel("w1", `<b>W₁</b> (27×${params.H})`, elements.w1),
    b1: createPanel("b1", `<b>b₁</b> (1×${params.H})`, elements.b1),
    h: createPanel("h", `<b>h</b> (1×${params.H}) = ReLU(xW₁+b₁)`, elements.h),
    w2: createPanel("w2", `<b>W₂ᵀ</b> (9×${params.H})`, elements.w2),
    b2: createPanel(null, "<b>b₂ᵀ</b> (9×1)", elements.b2, true),
    logits: createPanel(null, "<b>logitsᵀ</b> (9×1)", elements.logits, true),
    argmax: createPanel(null, "<b>argmax</b>", elements.argmax, true),
    output: createPanel(null, "<b>out</b>", elements.output, true),
  };
  panels.expression.setAttribute("bare-state", "");
  panels.b2.style.setProperty("--panel-min-width", "68px");
  panels.b1.setAttribute("center-schematic", "");
  const right = document.createElement("div");
  right.slot = "right";
  right.append(panels.b2, panels.logits, panels.argmax, panels.output);
  stage.append(panels.expression, panels.board, panels.x, panels.w1, panels.b1, panels.h, panels.w2, right);
  host.replaceChildren(stage);

  let board = [...initialBoard];
  let results = null;
  let state = null;
  let explanationState = null;

  function updateValues() {
    const input = encodeBoard(board);
    results = forward(activeParams, input);
    const move = chooseLegalMove(results.logits, board);
    const emptyH = state?.values.h === "empty";
    const emptyLogits = state?.values.logits === "empty";
    const emptyArgmax = state?.values.argmax === "empty";
    const emptyOutput = state?.values.output === "empty";
    const shownMove = explanationState ? explanationState.move : emptyArgmax ? -1 : move;

    elements.board.set({ board, cell: 30 });
    elements.x.set({ data: input });
    elements.w1.set({
      mutedRows: explanationState?.w1?.mutedRows ?? null,
      mutedColumns: null,
      spotlightRows: null,
      spotlightColumns: explanationState?.w1?.spotlightColumns ?? null,
    });
    elements.w2.set({
      mutedRows: null,
      mutedColumns: explanationState?.w2?.mutedColumns ?? null,
      spotlightRows: explanationState?.w2?.spotlightRows ?? null,
      spotlightColumns: null,
    });
    elements.h.set({ data: explanationState?.hidden ?? (emptyH ? new Float32Array(params.H) : results.hidden) });
    elements.logits.set({ data: explanationState?.logits ?? (emptyLogits ? new Float32Array(9) : results.logits), scale: Math.max(1e-6, maximumAbsolute(results.logits)) });
    const shownArgmax = new Float32Array(9);
    if (shownMove >= 0) shownArgmax[shownMove] = 1;
    elements.argmax.set({ data: shownArgmax });
    const showOutput = explanationState ? explanationState.showOutput : !emptyOutput;
    elements.output.set({ board: showOutput ? board : new Array(9).fill(0), highlight: showOutput ? shownMove : -1, dataBackground: true, cell: 30 });
    return { input, ...results, move };
  }

  function setState(nextState) {
    state = {
      visible: { ...Object.fromEntries(ELEMENT_NAMES.map(name => [name, true])), ...nextState.visible },
      representation: { w1: "rich", b1: "rich", w2: "rich", b2: "rich", ...nextState.representation },
      values: { h: "computed", logits: "computed", argmax: "computed", output: "computed", ...nextState.values },
      expression: { ...NORMAL_EXPRESSION, ...nextState.expression },
    };
    for (const name of ELEMENT_NAMES) panels[name].toggleAttribute("hidden-state", !state.visible[name]);
    for (const name of ["w1", "b1", "w2", "b2"]) {
      const schematic = state.representation[name] === "schematic";
      elements[name].setRepresentation(state.representation[name]);
      panels[name].toggleAttribute("schematic-state", schematic);
    }
    elements.expression.setState(state.expression);
    updateValues();
  }

  function setExpressionState(nextExpressionState) {
    state.expression = { ...state.expression, ...nextExpressionState };
    elements.expression.setState(state.expression);
  }

  function setExplanationState(nextExplanationState) {
    explanationState = nextExplanationState;
    return updateValues();
  }

  function patchExplanationState(patch) {
    if (!explanationState) explanationState = {};
    if (patch.w1) {
      explanationState.w1 = { ...explanationState.w1, ...patch.w1 };
      elements.w1.set(explanationState.w1);
    }
    if (patch.w2) {
      explanationState.w2 = { ...explanationState.w2, ...patch.w2 };
      elements.w2.set(explanationState.w2);
    }
    if (patch.hidden) {
      explanationState.hidden = patch.hidden;
      elements.h.set({ data: patch.hidden });
    }
    if (patch.logits) {
      explanationState.logits = patch.logits;
      elements.logits.set({ data: patch.logits, scale: Math.max(1e-6, maximumAbsolute(results.logits)) });
    }
  }

  function clearExplanationState() {
    explanationState = null;
    return updateValues();
  }

  function setBoard(nextBoard) {
    board = [...nextBoard];
    return updateValues();
  }

  function setParameters(snapshot, { comparison = null } = {}) {
    const expected = {
      Wa: params.IN * params.H,
      ba: params.H,
      Wb: params.H * params.OUT,
      bb: params.OUT,
    };
    if (snapshot.H !== params.H) throw new RangeError(`parameter snapshot H=${snapshot.H} does not match stage H=${params.H}`);
    for (const [name, length] of Object.entries(expected)) {
      if (!snapshot[name] || snapshot[name].length !== length) throw new RangeError(`parameter snapshot ${name} must contain ${length} values`);
      if (comparison && (!comparison[name] || comparison[name].length !== length)) {
        throw new RangeError(`comparison snapshot ${name} must contain ${length} values`);
      }
    }
    activeParams = {
      IN: params.IN,
      H: params.H,
      OUT: params.OUT,
      Wa: Float32Array.from(snapshot.Wa),
      ba: Float32Array.from(snapshot.ba),
      Wb: Float32Array.from(snapshot.Wb),
      bb: Float32Array.from(snapshot.bb),
    };
    explanationState = null;
    const shownParams = comparison ? {
      ...activeParams,
      Wa: parameterDifference(activeParams.Wa, comparison.Wa),
      ba: parameterDifference(activeParams.ba, comparison.ba),
      Wb: parameterDifference(activeParams.Wb, comparison.Wb),
      bb: parameterDifference(activeParams.bb, comparison.bb),
    } : activeParams;
    const matrixOptions = comparison
      ? { scale: null, linear: true, positiveColor: COLORS.increase, negativeColor: COLORS.decrease }
      : { linear: false, positiveColor: COLORS.positive, negativeColor: COLORS.negative };
    elements.w1.set({ data: shownParams.Wa, scale: comparison ? null : SCALE.w1, ...matrixOptions });
    elements.b1.set({ data: shownParams.ba, scale: comparison ? null : SCALE.b1, ...matrixOptions });
    elements.w2.set({ data: transposeOutputWeights(shownParams), scale: comparison ? null : SCALE.w2, ...matrixOptions });
    elements.b2.set({ data: shownParams.bb, scale: comparison ? null : SCALE.b2, ...matrixOptions });
    return updateValues();
  }

  function restoreModelParameters() {
    return setParameters(params);
  }

  function getParameters() {
    return {
      H: activeParams.H,
      Wa: activeParams.Wa.slice(),
      ba: activeParams.ba.slice(),
      Wb: activeParams.Wb.slice(),
      bb: activeParams.bb.slice(),
    };
  }

  let boardSelectionHandler = null;
  elements.board.addEventListener("cell-select", event => {
    if (boardSelectionHandler) {
      boardSelectionHandler(event.detail, [...board]);
      return;
    }
    const next = [...board];
    next[event.detail] = (next[event.detail] + 1) % 3;
    setBoard(next);
    host.dispatchEvent(new CustomEvent("pipeline-board-change", { detail: { board: [...board] } }));
  });
  elements.output.addEventListener("restore-output", updateValues);
  bindBoardHover(elements.board, elements.x);
  bindLogitHover(elements.logits, elements.output, () => board);

  setState({});
  return {
    model,
    root: stage,
    elements,
    panels,
    targets: { ...panels, all: stage },
    setState,
    setExpressionState,
    setExplanationState,
    patchExplanationState,
    clearExplanationState,
    setBoard,
    setParameters,
    restoreModelParameters,
    getParameters,
    setBoardSelectionHandler: handler => { boardSelectionHandler = handler; },
    getBoard: () => [...board],
    getComputation: () => ({ input: encodeBoard(board), ...results, move: chooseLegalMove(results.logits, board) }),
    updateValues,
  };
}

export const STAGE_PRESETS = {
  encoding: {
    visible: { expression: false, board: true, x: true, w1: false, b1: false, h: false, w2: false, b2: false, logits: false, argmax: false, output: false },
    representation: { w1: "schematic", b1: "schematic", w2: "schematic", b2: "schematic" },
    values: { h: "empty", logits: "empty", argmax: "empty", output: "empty" },
    expression: { ...NORMAL_EXPRESSION },
  },
  schematics: {
    visible: { expression: true, board: true, x: true, w1: true, b1: true, h: false, w2: true, b2: true, logits: false, argmax: false, output: false },
    representation: { w1: "schematic", b1: "schematic", w2: "schematic", b2: "schematic" },
    values: { h: "empty", logits: "empty", argmax: "empty", output: "empty" },
    expression: { ...NORMAL_EXPRESSION },
  },
  accumulators: {
    visible: { expression: true, board: true, x: true, w1: true, b1: true, h: true, w2: true, b2: true, logits: true, argmax: true, output: true },
    representation: { w1: "schematic", b1: "schematic", w2: "schematic", b2: "schematic" },
    values: { h: "empty", logits: "empty", argmax: "empty", output: "empty" },
    expression: { ...NORMAL_EXPRESSION },
  },
  rich: {
    visible: { expression: true, board: true, x: true, w1: true, b1: true, h: true, w2: true, b2: true, logits: true, argmax: true, output: true },
    representation: { w1: "rich", b1: "rich", w2: "rich", b2: "rich" },
    values: { h: "empty", logits: "empty", argmax: "empty", output: "empty" },
    expression: { ...NORMAL_EXPRESSION },
  },
  complete: {
    visible: Object.fromEntries(ELEMENT_NAMES.map(name => [name, true])),
    representation: { w1: "rich", b1: "rich", w2: "rich", b2: "rich" },
    values: { h: "computed", logits: "computed", argmax: "computed", output: "computed" },
    expression: { ...NORMAL_EXPRESSION },
  },
};
