const POSITIVE = "hsl(2 72% 52%)";
const NEGATIVE = "hsl(226 66% 52%)";
const GAUGE_CENTER = 143;
const GAUGE_HEIGHT = 90;
const RETURN_DURATION = 420;
const NEGATIVE_OPENING_SCALE = .9;
const BOARD_ROTATION_DEGREES = -15;

const clamp = (value, limit) => Math.max(-limit, Math.min(limit, value));
const format = value => Math.abs(value) < .0005 ? "0" : value.toFixed(3);

function columnChart(values, limit) {
  const angle = BOARD_ROTATION_DEGREES * Math.PI / 180;
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  const rotate = (x, y) => {
    const dx = x - 232;
    const dy = y - 147.5;
    return [232 + dx * cosine - dy * sine, 147.5 + dx * sine + dy * cosine];
  };
  const project = (row, column) => ({
    x: 228 + (column - 1) * 34 - (row - 1) * 26,
    y: 138 + (column - 1) * 10 + (row - 1) * 17,
  });
  const corners = ({ x, y }, height = 0) => [
    [x, y], [x + 25, y + 8],
    [x + 8, y + 19], [x - 17, y + 11],
  ].map(([px, py]) => {
    const [rx, ry] = rotate(px, py);
    return [rx, ry - height];
  });
  const points = vertices => vertices.map(point => point.join(",")).join(" ");
  const boardPoint = (row, column) => {
    const { x, y } = project(row, column);
    return rotate(x + 4, y + 9.5);
  };
  const boardCorners = [
    boardPoint(-.5, -.5), boardPoint(-.5, 2.5),
    boardPoint(2.5, 2.5), boardPoint(2.5, -.5),
  ];
  let board = `<g class="zero-plane" aria-hidden="true">
    <polygon points="${points(boardCorners)}" fill="#aeb7c2" fill-opacity=".22"
      stroke="#8994a4" stroke-opacity=".65" stroke-width="1"/>`;
  for (const division of [.5, 1.5]) {
    for (const [start, end] of [
      [boardPoint(-.5, division), boardPoint(2.5, division)],
      [boardPoint(division, -.5), boardPoint(division, 2.5)],
    ]) {
      board += `<line x1="${start[0]}" y1="${start[1]}" x2="${end[0]}" y2="${end[1]}"
        stroke="#6b7787" stroke-opacity=".75" stroke-width="1.2"/>`;
    }
  }
  board += "</g>";
  let below = "";
  let above = "";
  values.forEach((value, index) => {
    const position = project(Math.floor(index / 3), index % 3);
    const base = corners(position);
    const top = corners(position, value / limit * 65);
    const faces = [
      [base[1], base[2], top[2], top[1]],
      [base[2], base[3], top[3], top[2]],
    ];
    let bar = `<g class="contribution-bar" data-cell="${index}" data-value="${value}">
      <title>Row ${Math.floor(index / 3) + 1}, column ${index % 3 + 1}: ${format(value)}</title>`;
    if (Math.abs(value) > 1e-8) {
      const shades = value > 0
        ? ["#b82f2a", "#e34f43", "#ff9480"]
        : ["#29499b", "#547ddd", "#a9c5ff"];
      const edge = value > 0 ? "#9e2925" : "#244483";
      faces.forEach((face, faceIndex) => {
        bar += `<polygon points="${points(face)}" fill="${shades[faceIndex]}"
          stroke="${edge}" stroke-width=".8" stroke-linejoin="round"/>`;
      });
      if (value > 0) {
        bar += `<polygon points="${points(top)}" fill="${shades[2]}"
          stroke="${edge}" stroke-width=".8" stroke-linejoin="round"/>`;
      } else {
        const center = [(base[0][0] + base[2][0]) / 2, (base[0][1] + base[2][1]) / 2];
        const opening = base.map(point => point.map((coordinate, axis) =>
          center[axis] + (coordinate - center[axis]) * NEGATIVE_OPENING_SCALE));
        bar += `<polygon class="bar-rim" points="${points(base)}" fill="${shades[2]}"
            stroke="${edge}" stroke-width=".8" stroke-linejoin="round"/>
          <polygon class="bar-opening" points="${points(opening)}" fill="#162d61"
            stroke="#355998" stroke-width=".8" stroke-linejoin="round"/>`;
      }
    }
    bar += "</g>";
    if (value < 0) below += bar;
    else above += bar;
  });
  return `<g class="negative-contributions">${below}</g>${board}<g class="positive-contributions">${above}</g>`;
}

export function createColumnExplorer({ pipeline }) {
  const root = document.createElement("section");
  root.className = "column-explorer";
  root.slot = "explorer";
  root.hidden = true;
  root.setAttribute("aria-label", "Explore output logits and hidden-column contributions");
  root.setAttribute("data-vividly-touch-ignore", "");
  root.innerHTML = `
    <h2>Output contributions</h2>
    <div class="column-explorer-selection">
      <button type="button" class="previous-column" aria-label="Previous column">[</button>
      <strong class="column-label"></strong>
      <button type="button" class="next-column" aria-label="Next column or logits">]</button>
    </div>
    <svg class="column-explorer-chart" viewBox="0 0 360 270">
      <g class="activation-gauge" role="slider" tabindex="0" aria-label="Temporary hidden activation"
        aria-orientation="vertical">
        <title>Drag the handle to change the activation temporarily</title>
        <rect x="34" y="53" width="18" height="180" rx="2" fill="#f3f5f8" stroke="#8c98ab"/>
        <rect class="activation-value" x="35" width="16"/>
        <path d="M28,143 H59" stroke="#172033" stroke-width="1.5"/>
        <text x="20" y="147" text-anchor="end">0</text>
        <path class="unit-tick" stroke="#172033"/>
        <text class="unit-label" x="20" text-anchor="end">1</text>
        <text class="range-top" x="43" y="44" text-anchor="middle"></text>
        <text class="range-bottom" x="43" y="252" text-anchor="middle"></text>
        <circle class="activation-handle" cx="43" r="8" fill="white" stroke="#188451" stroke-width="3"/>
      </g>
      <g class="column-bars" role="img" aria-label="Scaled contributions arranged as a three by three board"></g>
      <text class="chart-caption" x="228" y="253" text-anchor="middle">activation × column weights</text>
    </svg>
    <p class="activation-readout"></p>
    <p class="column-explorer-hint">Drag to preview; release to restore. Click W₁ or use [ and ] for columns, then logits.</p>
    <p class="column-explorer-note">What-if only: the network and logits stay unchanged.</p>`;
  pipeline.root.append(root);
  const svg = root.querySelector("svg");
  const gauge = root.querySelector(".activation-gauge");
  const handle = root.querySelector(".activation-handle");
  const bar = root.querySelector(".activation-value");
  const bars = root.querySelector(".column-bars");
  const previous = root.querySelector(".previous-column");
  const next = root.querySelector(".next-column");
  const events = new AbortController();
  let visible = false;
  let selected = 0;
  let selectedRow = null;
  let original = 0;
  let value = 0;
  let gaugeLimit = 2;
  let chartLimit = 1;
  let weights = [];
  let pointer = null;
  let returnFrame = 0;

  function listen(target, type, listener, options = {}) {
    target.addEventListener(type, listener, { ...options, signal: events.signal });
  }

  function highlight() {
    const columnSelected = visible && selected < pipeline.model.params.H;
    const range = columnSelected ? [selected, selected] : null;
    pipeline.patchExplanationState({
      w1: {
        spotlightCell: columnSelected && selectedRow !== null ? [selectedRow, selected] : null,
        spotlightColumns: columnSelected && selectedRow === null ? [selected] : null,
      },
      w2: { spotlightColumnRange: range },
      h: { spotlightColumnRange: range },
      logitsOptions: { spotlightColumnRange: visible && !columnSelected ? [0, 0] : null },
    });
  }

  function render() {
    const showingLogits = selected === pipeline.model.params.H;
    root.classList.toggle("showing-logits", showingLogits);
    gauge.setAttribute("aria-hidden", showingLogits);
    gauge.setAttribute("tabindex", showingLogits ? "-1" : "0");
    const y = GAUGE_CENTER - value / gaugeLimit * GAUGE_HEIGHT;
    const unitY = GAUGE_CENTER - GAUGE_HEIGHT / gaugeLimit;
    bar.setAttribute("y", Math.min(GAUGE_CENTER, y));
    bar.setAttribute("height", Math.abs(y - GAUGE_CENTER));
    bar.setAttribute("fill", value < 0 ? NEGATIVE : POSITIVE);
    handle.setAttribute("cy", y);
    gauge.setAttribute("aria-valuemin", -gaugeLimit);
    gauge.setAttribute("aria-valuemax", gaugeLimit);
    gauge.setAttribute("aria-valuenow", value);
    gauge.setAttribute("aria-valuetext", `${format(value)}; original activation ${format(original)}`);
    root.querySelector(".unit-tick").setAttribute("d", `M28,${unitY} H59`);
    root.querySelector(".unit-label").setAttribute("y", unitY + 4);
    root.querySelector(".range-top").textContent = `+${gaugeLimit}`;
    root.querySelector(".range-bottom").textContent = `−${gaugeLimit}`;
    root.querySelector(".column-label").textContent = showingLogits ? "logits"
      : selectedRow === null ? `h[${selected}] · column ${selected}`
        : `W₁[${selectedRow}, ${selected}] → h[${selected}]`;
    root.querySelector(".activation-readout").textContent = `Activation ${format(value)} · original ${format(original)}`;
    root.querySelector(".chart-caption").textContent = showingLogits
      ? "logits (all columns + bias)" : "activation × column weights";
    bars.setAttribute("aria-label", showingLogits
      ? "Logits arranged as a three by three board"
      : "Scaled contributions arranged as a three by three board");
    bars.innerHTML = columnChart(showingLogits ? weights : weights.map(weight => weight * value), chartLimit);
    previous.disabled = selected === 0;
    next.disabled = showingLogits;
  }

  function cancelReturn() {
    if (returnFrame) cancelAnimationFrame(returnFrame);
    returnFrame = 0;
  }

  function releasePointer() {
    const activePointer = pointer;
    pointer = null;
    if (activePointer !== null && gauge.hasPointerCapture(activePointer)) {
      gauge.releasePointerCapture(activePointer);
    }
  }

  function select(index) {
    cancelReturn();
    releasePointer();
    const { Wb, OUT, H } = pipeline.model.params;
    selected = Math.max(0, Math.min(H, index));
    const { hidden, logits } = pipeline.getComputation();
    if (selected === H) {
      original = value = 0;
      gauge.blur();
      weights = Array.from(logits);
      chartLimit = Math.max(1e-6, ...weights.map(weight => Math.abs(weight)));
    } else {
      original = hidden[selected];
      value = original;
      gaugeLimit = Math.max(2, Math.ceil(Math.abs(original) * 1.5));
      weights = Array.from({ length: OUT }, (_, output) => Wb[selected * OUT + output]);
      chartLimit = Math.max(1e-6, ...weights.map(weight => Math.abs(weight) * gaugeLimit));
    }
    highlight();
    render();
  }

  function finish() {
    if (!returnFrame) return false;
    cancelReturn();
    value = original;
    render();
    return true;
  }

  function restore() {
    cancelReturn();
    const startValue = value;
    if (startValue === original) return;
    if (!visible || matchMedia("(prefers-reduced-motion: reduce)").matches ||
        new URLSearchParams(location.search).has("instant") || document.hidden) {
      value = original;
      render();
      return;
    }
    const started = performance.now();
    function frame(now) {
      const progress = Math.min(1, (now - started) / RETURN_DURATION);
      value = original + (startValue - original) * (1 - progress) ** 3;
      render();
      returnFrame = progress < 1 ? requestAnimationFrame(frame) : 0;
    }
    returnFrame = requestAnimationFrame(frame);
  }

  function setVisible(nextVisible, { clearHighlights = true } = {}) {
    if (nextVisible === visible) {
      if (visible) highlight();
      return;
    }
    visible = nextVisible;
    root.hidden = !visible;
    if (visible) {
      select(pipeline.model.params.H);
    } else {
      cancelReturn();
      releasePointer();
      gauge.blur();
      value = original;
      selectedRow = null;
      if (clearHighlights) highlight();
    }
  }

  function movePointer(event) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(svg.getScreenCTM().inverse());
    value = clamp((GAUGE_CENTER - local.y) / GAUGE_HEIGHT * gaugeLimit, gaugeLimit);
    render();
  }

  function captureKey(event) {
    if (!visible || event.altKey || event.ctrlKey || event.metaKey || event.isComposing) return false;
    if (event.target instanceof Element && event.target.closest("input, select, textarea, [contenteditable=true]")) return false;
    if (event.key === "\\" && selectedRow !== null) {
      selectedRow = null;
      highlight();
      render();
      return true;
    }
    if (event.key === "[" || event.key === "]") {
      select(selected + (event.key === "[" ? -1 : 1));
      return true;
    }
    if (selected === pipeline.model.params.H ||
        !(event.target instanceof Element) || !gauge.contains(event.target)) return false;
    if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return false;
    cancelReturn();
    value = event.key === "Home" ? -gaugeLimit
      : event.key === "End" ? gaugeLimit
        : clamp(value + (event.key === "ArrowUp" ? 1 : -1) * gaugeLimit / 40, gaugeLimit);
    render();
    return true;
  }

  listen(root, "pointerdown", event => event.stopPropagation());
  listen(root, "wheel", event => event.stopPropagation());
  listen(previous, "click", () => select(selected - 1));
  listen(next, "click", () => select(selected + 1));
  const selectionMatrices = [pipeline.elements.w1, pipeline.elements.w2, pipeline.elements.logits];
  for (const matrix of selectionMatrices) {
    listen(matrix, "pointerdown", event => {
      if (visible) event.stopPropagation();
    });
  }
  listen(document, "click", event => {
    if (!visible) return;
    const path = event.composedPath();
    const matrix = selectionMatrices.find(element => path.includes(element));
    if (matrix) {
      const rect = matrix.getBoundingClientRect();
      if (event.clientX >= rect.left && event.clientX < rect.right &&
          event.clientY >= rect.top && event.clientY < rect.bottom) {
        const { rows, columns } = matrix.getGridShape();
        selectedRow = matrix === pipeline.elements.w1
          ? Math.floor((event.clientY - rect.top) / rect.height * rows) : null;
        select(matrix === pipeline.elements.logits ? pipeline.model.params.H
          : Math.floor((event.clientX - rect.left) / rect.width * columns));
        return;
      }
    }
    if (selectedRow !== null) {
      selectedRow = null;
      highlight();
      render();
    }
  }, { capture: true });
  listen(gauge, "pointerdown", event => {
    if (selected === pipeline.model.params.H || event.button !== 0 || pointer !== null) return;
    event.preventDefault();
    cancelReturn();
    pointer = event.pointerId;
    gauge.focus();
    gauge.setPointerCapture(pointer);
    movePointer(event);
  });
  listen(gauge, "pointermove", event => {
    if (event.pointerId === pointer) movePointer(event);
  });
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) {
    listen(gauge, type, event => {
      if (event.pointerId !== pointer) return;
      releasePointer();
      restore();
    });
  }
  listen(gauge, "keyup", event => {
    if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) restore();
  });
  listen(gauge, "blur", () => {
    if (pointer === null) restore();
  });
  listen(root, "keydown", event => {
    if (!root.closest(".vividly-hosted") && captureKey(event)) {
      event.preventDefault();
      event.stopPropagation();
    }
  });
  listen(document, "visibilitychange", () => {
    if (!visible || !document.hidden) return;
    releasePointer();
    cancelReturn();
    value = original;
    render();
  });

  return {
    setVisible,
    captureKey,
    finish,
    refresh() {
      if (visible) select(selected);
    },
    destroy() {
      setVisible(false);
      events.abort();
      root.remove();
    },
  };
}
