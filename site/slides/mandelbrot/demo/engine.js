"use strict";

export function createMandelbrotViewer(root) {
const query = (selector) => {
  const element = root.querySelector(selector);
  if (!element) throw new Error(`Missing Mandelbrot viewer element: ${selector}`);
  return element;
};
const authoringTools = new URLSearchParams(window.location.search).get("authoring") === "1";
const abortController = new AbortController();
const { signal } = abortController;
let active = false;
let initialized = false;
let ready = false;
let authoredStage = 0;
let lifecycle = 0;
let resizeTimer;
let animationFrame;
let workerUrl;

/* =========================================================================
   Per-pixel kernel (perturbation with rebasing). Shared by workers and
   the main-thread fallback, so it must be self-contained.
   ========================================================================= */
function kernel(y0, y1, step, W, H, scale, maxIter, Zr, Zi, len, c0r, c0i, useBulb, out) {
  let k = 0;
  const hw = W / 2, hh = H / 2;
  for (let y = y0; y < y1; y += step) {
    const dci = (hh - y) * scale;
    for (let x = 0; x < W; x += step) {
      const dcr = (x - hw) * scale;
      if (useBulb) {
        // Skip main cardioid and period-2 bulb (only meaningful at shallow zoom)
        const cr = c0r + dcr, ci = c0i + dci;
        const xq = cr - 0.25, q = xq * xq + ci * ci;
        if (q * (q + xq) <= 0.25 * ci * ci || (cr + 1) * (cr + 1) + ci * ci <= 0.0625) { out[k++] = -1; continue; }
      }
      let dr = 0, di = 0, ref = 0, n = 0, res = -1;
      while (n < maxIter) {
        const zr = Zr[ref] + dr, zi = Zi[ref] + di;
        const m = zr * zr + zi * zi;
        if (m > 1e6) {
          res = n + 1 - Math.log2(0.5 * Math.log(m));
          if (res < 0) res = 0;
          break;
        }
        // Rebase: jump back to the start of the reference orbit when the
        // pixel's orbit is closer to 0 than to the reference, or the reference ran out.
        if (m < dr * dr + di * di || ref === len - 1) { dr = zr; di = zi; ref = 0; }
        const Rr = Zr[ref], Ri = Zi[ref];
        const nr = 2 * (Rr * dr - Ri * di) + dr * dr - di * di + dcr;
        const ni = 2 * (Rr * di + Ri * dr) + 2 * dr * di + dci;
        dr = nr; di = ni; ref++; n++;
      }
      out[k++] = res;
    }
  }
}

/* =========================================================================
   Fixed-point BigInt helpers: value = x / 2^P
   ========================================================================= */
const P2 = (e) => Math.pow(2, e);

function toDouble(x, P) {
  if (P <= 1000) return Number(x) * P2(-P);
  return Number(x >> BigInt(P - 1000)) * P2(-1000);
}

function fromDouble(v, P) {
  if (v === 0 || !isFinite(v)) return 0n;
  const e = Math.floor(Math.log2(Math.abs(v)));
  const m = v * P2(-e);                         // 1 <= |m| < 2
  const M = BigInt(Math.round(m * P2(52)));
  const sh = P + e - 52;
  return sh >= 0 ? (M << BigInt(sh)) : (M >> BigInt(-sh));
}

function parseFixed(s, P) {
  s = s.trim();
  const neg = s[0] === "-";
  if (neg || s[0] === "+") s = s.slice(1);
  const [ip, fp = ""] = s.split(".");
  const num = BigInt((ip || "0") + fp);
  const r = (num << BigInt(P)) / (10n ** BigInt(fp.length));
  return neg ? -r : r;
}

function referenceOrbit(cr, ci, P, maxIter) {
  const Zr = new Float64Array(maxIter + 2), Zi = new Float64Array(maxIter + 2);
  const PB = BigInt(P), PB1 = BigInt(P - 1);
  const four = 4n << PB;
  let zr = 0n, zi = 0n, n = 0;
  Zr[0] = 0; Zi[0] = 0;
  for (n = 1; n <= maxIter; n++) {
    const zr2 = zr * zr, zi2 = zi * zi;
    const nzi = ((zr * zi) >> PB1) + ci;
    zr = ((zr2 - zi2) >> PB) + cr;
    zi = nzi;
    Zr[n] = toDouble(zr, P);
    Zi[n] = toDouble(zi, P);
    if (zr * zr + zi * zi > (four << PB)) break;
  }
  const len = Math.min(n, maxIter) + 1;
  return { Zr: Zr.slice(0, len), Zi: Zi.slice(0, len), len };
}

/* =========================================================================
   View state
   ========================================================================= */
const HOME = { re: "-0.75", im: "0", radius: 1.35 };
const TOUR = { re: "-0.743643887037158704752191506114774", im: "0.131825904205311970493132056385139" };
const STAGE_TWO = {
  cr: -44662760949448567685120n,
  ci: -12296818335630523105280n,
  P: 75,
  radius: 0.135,
};
const MAX_MAG = 1e280;

let view;           // { cr, ci, P, radius }
const history = [];

function precisionFor(radius) {
  return Math.max(64, Math.ceil(-Math.log2(radius)) + 72);
}
function homeView() {
  const P = precisionFor(HOME.radius);
  return { cr: parseFixed(HOME.re, P), ci: parseFixed(HOME.im, P), P, radius: HOME.radius };
}
function stageView(stage) {
  if (stage === 0) return homeView();
  return { ...STAGE_TWO };
}
function withPrecision(v, P) {
  if (P === v.P) return { ...v };
  const d = BigInt(P - v.P);
  return P > v.P ? { ...v, cr: v.cr << d, ci: v.ci << d, P }
                 : { ...v, cr: v.cr >> -d, ci: v.ci >> -d, P };
}
const magnification = () => HOME.radius / view.radius;

/* =========================================================================
   Canvas, buffers
   ========================================================================= */
const canvas = query("#view");
const ctx = canvas.getContext("2d", { alpha: false });
let W = 0, H = 0, DPR = 1, iter, img, pix;

function sizeCanvas() {
  DPR = Math.min(window.devicePixelRatio || 1, 2);
  W = Math.max(1, Math.floor(root.clientWidth * DPR));
  H = Math.max(1, Math.floor(root.clientHeight * DPR));
  canvas.width = W; canvas.height = H;
  iter = new Float32Array(W * H);
  img = ctx.createImageData(W, H);
  pix = new Uint32Array(img.data.buffer);
}
const pixelScale = () => (2 * view.radius) / Math.min(W, H);

/* =========================================================================
   Colour
   ========================================================================= */
const PALETTES = [
  [[0, [0, 7, 100]], [0.16, [32, 107, 203]], [0.42, [237, 255, 255]], [0.6425, [255, 170, 0]], [0.8575, [0, 2, 0]], [1, [0, 7, 100]]],
  [[0, [8, 0, 0]], [0.22, [120, 10, 20]], [0.45, [240, 90, 20]], [0.62, [255, 215, 120]], [0.75, [255, 250, 235]], [1, [8, 0, 0]]],
  [[0, [4, 12, 34]], [0.25, [20, 110, 130]], [0.45, [210, 245, 240]], [0.65, [120, 80, 170]], [0.85, [30, 20, 60]], [1, [4, 12, 34]]],
  [[0, [10, 10, 10]], [0.5, [245, 245, 245]], [1, [10, 10, 10]]],
];
let paletteIndex = 0, cycles = 3, colorOffset = 0;
const LUT_N = 2048;
let lut = new Uint32Array(LUT_N);

function buildLut() {
  const stops = PALETTES[paletteIndex];
  for (let i = 0; i < LUT_N; i++) {
    const t = i / LUT_N;
    let j = 0;
    while (j < stops.length - 2 && t > stops[j + 1][0]) j++;
    const [t0, a] = stops[j], [t1, b] = stops[j + 1];
    let f = (t - t0) / (t1 - t0);
    f = f * f * (3 - 2 * f);
    const r = Math.round(a[0] + (b[0] - a[0]) * f);
    const g = Math.round(a[1] + (b[1] - a[1]) * f);
    const bl = Math.round(a[2] + (b[2] - a[2]) * f);
    lut[i] = (255 << 24) | (bl << 16) | (g << 8) | r;
  }
}
buildLut();

let quant = new Float32Array(0);    // sorted sample of escape values -> histogram colouring

function buildQuantiles(stepSample) {
  const vals = [];
  for (let y = 0; y < H; y += stepSample) {
    const row = y * W;
    for (let x = 0; x < W; x += stepSample) { const v = iter[row + x]; if (v >= 0) vals.push(v); }
  }
  const stride = Math.max(1, Math.floor(vals.length / 4096));
  const s = [];
  for (let i = 0; i < vals.length; i += stride) s.push(vals[i]);
  quant = Float32Array.from(s).sort();
}

const BLACK = 0xff000000;
function colorRows(y0, y1) {
  const q = quant, nq = q.length, lastQ = nq - 1;
  for (let y = y0; y < y1; y++) {
    const row = y * W;
    for (let x = 0; x < W; x++) {
      const i = row + x, v = iter[i];
      if (v < 0) { pix[i] = BLACK; continue; }
      let t = 0;
      if (nq > 1) {
        let lo = 0, hi = lastQ;
        if (v <= q[0]) t = 0;
        else if (v >= q[lastQ]) t = 1;
        else {
          while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (q[mid] <= v) lo = mid; else hi = mid; }
          const span = q[hi] - q[lo];
          t = (lo + (span > 0 ? (v - q[lo]) / span : 0)) / lastQ;
        }
      }
      let u = t * cycles + colorOffset;
      u -= Math.floor(u);
      pix[i] = lut[(u * LUT_N) | 0];
    }
  }
}
function paint(y0, y1) {
  colorRows(y0, y1);
  ctx.putImageData(img, 0, 0, 0, y0, W, y1 - y0);
}

/* =========================================================================
   Workers (with main-thread fallback if the page blocks them)
   ========================================================================= */
const workerSource = `"use strict";
${kernel.toString()}
let ref = null;
onmessage = (e) => {
  const d = e.data;
  if (d.type === "ping") { postMessage({ type: "pong" }); return; }
  if (d.type === "ref") { ref = d; return; }
  if (d.type === "job") {
    if (!ref || ref.gen !== d.gen) { postMessage({ type: "skip" }); return; }
    const cols = Math.ceil(d.W / d.step), rows = Math.ceil((d.y1 - d.y0) / d.step);
    const out = new Float32Array(cols * rows);
    kernel(d.y0, d.y1, d.step, d.W, d.H, d.scale, d.maxIter, ref.Zr, ref.Zi, ref.len, d.c0r, d.c0i, d.useBulb, out);
    postMessage({ type: "done", gen: d.gen, y0: d.y0, y1: d.y1, step: d.step, out }, [out.buffer]);
  }
};`;

let workers = [];
let useWorkers = false;

function initWorkers() {
  return new Promise((resolve) => {
    if (workerUrl) URL.revokeObjectURL(workerUrl);
    try { workerUrl = URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" })); }
    catch (e) { resolve(false); return; }
    const n = Math.max(1, Math.min(16, (navigator.hardwareConcurrency || 4)));
    let ready = 0, settled = false;
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      if (!ok) {
        workers.forEach((worker) => worker.terminate());
        workers = [];
      }
      resolve(ok && active);
    };
    try {
      for (let i = 0; i < n; i++) {
        const w = new Worker(workerUrl);
        w.busy = false;
        w.onerror = () => finish(false);
        w.onmessage = (e) => {
          if (e.data.type === "pong") { if (++ready === n) finish(true); return; }
          onWorkerMessage(w, e.data);
        };
        w.postMessage({ type: "ping" });
        workers.push(w);
      }
    } catch (e) { finish(false); return; }
    setTimeout(() => finish(ready === n), 1500);
  });
}

/* =========================================================================
   Render scheduler
   ========================================================================= */
let gen = 0, job = null, animating = false, finishAnimation = null;
const progressEl = query("#progress");

function autoIter() {
  const l = Math.max(0, Math.log10(magnification()));
  return Math.round(Math.min(600000, (2000 + 1000 * l) * iterMul * boost));
}
let iterMul = 1, boost = 1;

function render(keepBoost, transition = null) {
  if (!active || !ready) return;
  if (!keepBoost) boost = 1;
  gen++;
  const g = gen;
  const maxIter = autoIter();
  const t0 = performance.now();
  const ref = referenceOrbit(view.cr, view.ci, view.P, maxIter);
  const scale = pixelScale();
  const mag = magnification();
  const c0r = toDouble(view.cr, view.P), c0i = toDouble(view.ci, view.P);
  const common = { gen: g, W, H, scale, maxIter, c0r, c0i, useBulb: mag < 1e6 };

  // Row chunks, ordered from the centre outwards so the middle resolves first.
  const queue = [];
  const passes = [{ step: 4, rows: 32 }, { step: 1, rows: 8 }];
  const counts = [];
  passes.forEach((p, pi) => {
    const chunks = [];
    for (let y = 0; y < H; y += p.rows) chunks.push({ ...common, type: "job", pass: pi, step: p.step, y0: y, y1: Math.min(H, y + p.rows) });
    chunks.sort((a, b) => Math.abs(a.y0 - H / 2) - Math.abs(b.y0 - H / 2));
    counts.push(chunks.length);
    queue.push(...chunks);
  });
  job = {
    gen: g,
    queue,
    counts,
    done: [0, 0],
    total: queue.length,
    finished: 0,
    previewReady: false,
    maxIter,
    t0,
    pendingPaint: [],
    transition,
  };

  if (useWorkers) {
    for (const w of workers) w.postMessage({ type: "ref", gen: g, Zr: ref.Zr, Zi: ref.Zi, len: ref.len });
    pumpWorkers();
  } else {
    job.ref = ref;
    setTimeout(() => pumpMain(g), 0);
  }
  updatePanel(maxIter);
  setProgress(0);
}

function pumpWorkers() {
  if (!active || !job) return;
  for (const w of workers) {
    if (w.busy || !job.queue.length) continue;
    const j = job.queue.shift();
    w.busy = true;
    w.postMessage(j);
  }
}

function onWorkerMessage(w, d) {
  if (!active) return;
  w.busy = false;
  if (d.type === "done" && job && d.gen === job.gen) accept(d.y0, d.y1, d.step, d.out, d.step === 4 ? 0 : 1);
  pumpWorkers();
}

function pumpMain(g) {
  if (!active || !job || job.gen !== g) return;
  const tEnd = performance.now() + 24;
  while (job.queue.length && performance.now() < tEnd) {
    const j = job.queue.shift();
    const cols = Math.ceil(W / j.step), rows = Math.ceil((j.y1 - j.y0) / j.step);
    const out = new Float32Array(cols * rows);
    kernel(j.y0, j.y1, j.step, j.W, j.H, j.scale, j.maxIter, job.ref.Zr, job.ref.Zi, job.ref.len, j.c0r, j.c0i, j.useBulb, out);
    accept(j.y0, j.y1, j.step, out, j.pass);
    if (!job || job.gen !== g) return;
  }
  if (job.queue.length) setTimeout(() => pumpMain(g), 0);
}

function accept(y0, y1, step, out, pass) {
  if (!active || !job) return;
  const cols = Math.ceil(W / step);
  let k = 0;
  for (let y = y0; y < y1; y += step) {
    for (let cx = 0; cx < cols; cx++) {
      const v = out[k++];
      const x = cx * step;
      if (step === 1) { iter[y * W + x] = v; continue; }
      const yEnd = Math.min(y + step, y1), xEnd = Math.min(x + step, W);
      for (let yy = y; yy < yEnd; yy++) { const row = yy * W; for (let xx = x; xx < xEnd; xx++) iter[row + xx] = v; }
    }
  }
  job.done[pass]++;
  job.finished++;
  setProgress(job.finished / job.total);

  if (pass === 0 && job.done[0] === job.counts[0]) {
    // If many points never escaped but the escaped ones got close to the limit,
    // the limit is too low for this depth: raise it and redraw.
    let inside = 0, total = 0, late = 0;
    const half = job.maxIter / 2;
    for (let yy = 0; yy < H; yy += 4) for (let xx = 0; xx < W; xx += 4) {
      const v = iter[yy * W + xx]; total++;
      if (v < 0) inside++; else if (v > half) late++;
    }
    if (inside / total > 0.01 && late > 0.1 * inside && boost < 32) {
      const transition = job.transition;
      boost *= 2;
      render(true, transition);
      return;
    }
    buildQuantiles(4);
    job.previewReady = true;
    if (job.transition) {
      paint(0, H);
      const target = snapshotCanvas();
      const transition = job.transition;
      job.transition = null;
      animateStageTransition(transition.source, target, transition.from, transition.to);
    } else if (!animating) {
      paint(0, H);
    }
  } else if (pass === 1 && job.previewReady) {
    if (animating) job.pendingPaint.push([y0, y1]);
    else paint(y0, y1);
  }
  if (job.finished === job.total) {
    const secs = ((performance.now() - job.t0) / 1000).toFixed(1);
    updatePanel(job.maxIter, secs);
  }
}

function setProgress(f) {
  progressEl.style.width = (f * 100).toFixed(1) + "%";
  progressEl.style.opacity = f >= 1 ? "0" : "1";
}

/* =========================================================================
   Zoom actions
   ========================================================================= */
let zoomFactor = 10;
const FACTORS = [2, 4, 10, 100, 1000];

function zoomAt(px, py, factor, exact) {
  // px, py: canvas pixel position of new centre (or exact {cr, ci} BigInts)
  const newRadius = view.radius / factor;
  if (HOME.radius / newRadius > MAX_MAG) { toast("This viewer's precision limit is about 10²⁸⁰× — go back or start over."); return; }
  history.push(view);
  const scale = pixelScale();
  const P = precisionFor(newRadius);
  let v = withPrecision(view, P);
  if (exact) { v.cr = exact.cr; v.ci = exact.ci; }
  else {
    v.cr += fromDouble((px - W / 2) * scale, P);
    v.ci += fromDouble((H / 2 - py) * scale, P);
  }
  v.radius = newRadius;
  animateZoom(px, py, factor);
  view = v;
  render();
}

function goBack() {
  if (!history.length) { toast("Already at the starting view."); return; }
  view = history.pop();
  render();
}

function reset() {
  history.length = 0;
  view = homeView();
  render();
}

function tourStep() {
  const P = Math.max(view.P, precisionFor(view.radius / zoomFactor));
  const tr = parseFixed(TOUR.re, P), ti = parseFixed(TOUR.im, P);
  const v = withPrecision(view, P);
  const scale = pixelScale();
  const px = W / 2 + toDouble(tr - v.cr, P) / scale;
  const py = H / 2 - toDouble(ti - v.ci, P) / scale;
  if (px < 0 || px >= W || py < 0 || py >= H) { toast("The dive point is off-screen. Press R to start over, then dive."); return; }
  if (magnification() * zoomFactor > 1e32) toast("The preset point's coordinates run out around 10³²× — beyond this you're exploring on your own.");
  const newP = precisionFor(view.radius / zoomFactor);
  zoomAt(px, py, zoomFactor, { cr: parseFixed(TOUR.re, newP), ci: parseFixed(TOUR.im, newP) });
}

/* Zoom animation: the chosen rectangle grows to fill the screen while the new view computes. */
const snap = document.createElement("canvas");
function snapshotCanvas() {
  const snapshot = document.createElement("canvas");
  snapshot.width = W;
  snapshot.height = H;
  snapshot.getContext("2d").drawImage(canvas, 0, 0);
  return snapshot;
}

function settleMotion() {
  if (!finishAnimation) return false;
  finishAnimation();
  return true;
}

function animateZoom(px, py, factor) {
  settleMotion();
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  snap.width = W; snap.height = H;
  snap.getContext("2d").drawImage(canvas, 0, 0);
  const tw = W / factor, th = H / factor;
  const tx = px - tw / 2, ty = py - th / 2;
  const dur = reduce ? 0 : 650;
  const start = performance.now();
  animating = true;
  const finish = () => {
    cancelAnimationFrame(animationFrame);
    animating = false;
    finishAnimation = null;
    if (job && job.previewReady) paint(0, H);
  };
  finishAnimation = finish;
  const frame = (now) => {
    if (!active) return;
    const f = dur ? Math.min(1, (now - start) / dur) : 1;
    // Interpolate in log space so the zoom feels uniform
    const e = f < 0.5 ? 4 * f * f * f : 1 - Math.pow(-2 * f + 2, 3) / 2;
    const s = Math.pow(factor, e);
    const w = W / s, h = H / s;
    const x = tx * (W - w) / (W - tw || 1), y = ty * (H - h) / (H - th || 1);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(snap, x, y, w, h, 0, 0, W, H);
    if (f < 1) animationFrame = requestAnimationFrame(frame);
    else finish();
  };
  animationFrame = requestAnimationFrame(frame);
}

function animateStageTransition(source, target, from, to) {
  settleMotion();
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const duration = reduce ? 0 : 900;
  const start = performance.now();
  const fromCenter = [toDouble(from.cr, from.P), toDouble(from.ci, from.P)];
  const toCenter = [toDouble(to.cr, to.P), toDouble(to.ci, to.P)];
  animating = true;

  const drawMapped = (image, imageView, center, radius, alpha) => {
    const scale = (2 * radius) / Math.min(W, H);
    const imageCenter = [
      toDouble(imageView.cr, imageView.P),
      toDouble(imageView.ci, imageView.P),
    ];
    const size = imageView.radius / radius;
    const width = W * size;
    const height = H * size;
    const x = W / 2 + (imageCenter[0] - center[0]) / scale - width / 2;
    const y = H / 2 - (imageCenter[1] - center[1]) / scale - height / 2;
    ctx.globalAlpha = alpha;
    ctx.drawImage(image, x, y, width, height);
  };

  const finish = () => {
    cancelAnimationFrame(animationFrame);
    animating = false;
    finishAnimation = null;
    ctx.globalAlpha = 1;
    if (job && job.previewReady) paint(0, H);
  };
  finishAnimation = finish;

  const frame = (now) => {
    if (!active) return;
    const fraction = duration ? Math.min(1, (now - start) / duration) : 1;
    const eased = fraction < 0.5
      ? 4 * fraction * fraction * fraction
      : 1 - Math.pow(-2 * fraction + 2, 3) / 2;
    const center = [
      fromCenter[0] + (toCenter[0] - fromCenter[0]) * eased,
      fromCenter[1] + (toCenter[1] - fromCenter[1]) * eased,
    ];
    const radius = from.radius * Math.pow(to.radius / from.radius, eased);

    ctx.globalAlpha = 1;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);
    drawMapped(target, to, center, radius, eased);
    drawMapped(source, from, center, radius, 1 - eased);
    ctx.globalAlpha = 1;

    if (fraction < 1) animationFrame = requestAnimationFrame(frame);
    else finish();
  };
  animationFrame = requestAnimationFrame(frame);
}

/* =========================================================================
   Panel text
   ========================================================================= */
const SUP = { "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "-": "⁻" };
const sup = (n) => String(n).split("").map(c => SUP[c] || c).join("");

function fmtMag(m) {
  if (m < 1e6) return Math.round(m).toLocaleString("en-US") + "×";
  const e = Math.floor(Math.log10(m));
  const mant = m / Math.pow(10, e);
  return (mant >= 1.05 ? mant.toFixed(1) + " × " : "") + "10<sup>" + e + "</sup>×";
}

const THINGS = [
  [0.08, "the palm of a hand"], [0.024, "a coin"], [0.004, "a lentil"],
  [0.001, "a grain of sand"], [7e-5, "a human hair"], [8e-6, "a red blood cell"], [2e-6, "a bacterium"],
  [1e-7, "a virus"], [2e-9, "a strand of DNA"], [1e-10, "an atom"], [1.5e-14, "an atomic nucleus"], [1.7e-15, "a proton"],
];

function describeWidth(w) {
  let best = null, bestD = Infinity;
  for (const [s, name] of THINGS) { const d = Math.abs(Math.log10(w / s)); if (d < bestD) { bestD = d; best = [s, name]; } }
  if (bestD <= 0.6) return "about the width of " + best[1];
  const smaller = THINGS.filter(t => t[0] > w).pop();
  if (!smaller) return null;
  const k = Math.round(Math.log10(smaller[0] / w));
  return (k >= 3 ? "10" + sup(k) + " times" : Math.round(smaller[0] / w) + " times") + " smaller than " + smaller[1];
}

function compareText(m) {
  if (m < 8) return "Click anywhere near the edge of the black shape to zoom in.";
  const PLANCK = 1.6e-35, UNIVERSE = 8.8e26;
  const w1 = 1 / m;
  if (w1 >= PLANCK) return "If the first view were 1 metre wide, this one would be " + describeWidth(w1) + ".";
  const w2 = UNIVERSE / m;
  if (w2 >= PLANCK) {
    const d = describeWidth(w2) || ("10" + sup(Math.round(Math.log10(1.7e-15 / w2))) + " times smaller than a proton");
    return "If the first view were as wide as the observable universe, this one would be " + d + ".";
  }
  return "Even if the first view were the entire observable universe, this one would be smaller than the smallest meaningful length in physics.";
}

function updatePanel(maxIter, secs) {
  const m = magnification();
  query("#mag").innerHTML = fmtMag(m) + " magnification";
  query("#compare").textContent = compareText(m);
  let t = "The same one-line rule, repeated up to " + maxIter.toLocaleString("en-US") + " times per point, with " + view.P + "-bit arithmetic.";
  if (secs) t += " Drawn in " + secs + " s.";
  query("#tech").textContent = t;
}

let toastTimer;
function toast(msg) {
  const el = query("#toast");
  el.textContent = msg; el.style.opacity = "1";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.style.opacity = "0"), 3200);
}

/* =========================================================================
   Input
   ========================================================================= */
const lens = query("#lens");
const lensLabel = lens.querySelector("span");
let lastPointer = null;
let drag = null;
let suppressClick = false;
const DRAG_THRESHOLD = 6;

function drawLens(clientX, clientY) {
  const bounds = root.getBoundingClientRect();
  const x = clientX - bounds.left;
  const y = clientY - bounds.top;
  const w = root.clientWidth / zoomFactor;
  const h = root.clientHeight / zoomFactor;
  lens.style.display = "block";
  lens.style.width = w + "px"; lens.style.height = h + "px";
  lens.style.left = (x - w / 2) + "px"; lens.style.top = (y - h / 2) + "px";
  lensLabel.textContent = zoomFactor + "×";
}

canvas.addEventListener("pointermove", (e) => {
  lastPointer = [e.clientX, e.clientY];
  if (drag && e.pointerId === drag.pointerId) {
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    if (!drag.moved && Math.hypot(dx, dy) >= DRAG_THRESHOLD) {
      drag.moved = true;
      root.classList.add("panning");
      lens.style.display = "none";
    }
    if (drag.moved) {
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, W, H);
      ctx.drawImage(drag.snapshot, dx * DPR, dy * DPR);
      return;
    }
  }
  if (e.pointerType === "mouse") drawLens(e.clientX, e.clientY);
}, { signal });
canvas.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || !active || !ready) return;
  settleMotion();
  canvas.focus({ preventScroll: true });
  gen++;
  job = null;
  setProgress(1);
  drag = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    view: { ...view },
    snapshot: snapshotCanvas(),
    moved: false,
  };
  canvas.setPointerCapture(event.pointerId);
}, { signal });
canvas.addEventListener("pointerleave", () => { lens.style.display = "none"; }, { signal });
canvas.addEventListener("click", (e) => {
  if (suppressClick) {
    suppressClick = false;
    return;
  }
  const bounds = canvas.getBoundingClientRect();
  zoomAt((e.clientX - bounds.left) * DPR, (e.clientY - bounds.top) * DPR, zoomFactor);
}, { signal });
canvas.addEventListener("contextmenu", (e) => { e.preventDefault(); goBack(); }, { signal });
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  let i = FACTORS.indexOf(zoomFactor);
  i = Math.max(0, Math.min(FACTORS.length - 1, i + (e.deltaY < 0 ? 1 : -1)));
  zoomFactor = FACTORS[i];
  if (lastPointer) drawLens(lastPointer[0], lastPointer[1]);
}, { passive: false, signal });

const finishDrag = (event, cancelled = false) => {
  if (!drag || event.pointerId !== drag.pointerId) return;
  const currentDrag = drag;
  drag = null;
  root.classList.remove("panning");
  if (canvas.hasPointerCapture(event.pointerId)) {
    canvas.releasePointerCapture(event.pointerId);
  }

  if (cancelled || !currentDrag.moved) {
    ctx.drawImage(currentDrag.snapshot, 0, 0);
    return;
  }

  const dx = (event.clientX - currentDrag.startX) * DPR;
  const dy = (event.clientY - currentDrag.startY) * DPR;
  const scale = (2 * currentDrag.view.radius) / Math.min(W, H);
  history.push(currentDrag.view);
  view = {
    ...currentDrag.view,
    cr: currentDrag.view.cr - fromDouble(dx * scale, currentDrag.view.P),
    ci: currentDrag.view.ci + fromDouble(dy * scale, currentDrag.view.P),
  };
  suppressClick = true;
  render();
};

canvas.addEventListener("pointerup", (event) => finishDrag(event), { signal });
canvas.addEventListener("pointercancel", (event) => finishDrag(event, true), { signal });
canvas.addEventListener("lostpointercapture", (event) => {
  if (drag && event.pointerId === drag.pointerId) finishDrag(event, true);
}, { signal });

function toggleFull() {
  if (document.fullscreenElement) document.exitFullscreen?.();
  else root.requestFullscreen?.().catch(() => toast("Full screen isn't available here. Try your browser's own full-screen key (F11)."));
}
function nextColors() { paletteIndex = (paletteIndex + 1) % PALETTES.length; buildLut(); if (job && job.previewReady) paint(0, H); }

function viewportParameters() {
  return {
    cr: view.cr.toString(),
    ci: view.ci.toString(),
    P: view.P,
    radius: view.radius,
    approximateRe: toDouble(view.cr, view.P),
    approximateIm: toDouble(view.ci, view.P),
    magnification: magnification(),
  };
}

async function copyView() {
  const text = JSON.stringify(viewportParameters(), null, 2);
  try {
    if (!navigator.clipboard?.writeText) {
      throw new Error("The Clipboard API is unavailable in this browser context.");
    }
    await navigator.clipboard.writeText(text);
    toast("Viewport parameters copied.");
  } catch (error) {
    console.error("[mandelbrot] Unable to copy viewport parameters.", error);
    window.prompt("Copy viewport parameters:", text);
    toast("Clipboard unavailable; viewport parameters opened for manual copy.");
  }
}

const copyButton = query("#bCopy");
copyButton.hidden = !authoringTools;
const controls = [
  [query("#bBack"), goBack],
  [query("#bTour"), tourStep],
  [query("#bColor"), nextColors],
  [query("#bReset"), reset],
  [copyButton, () => void copyView()],
  [query("#bFull"), toggleFull],
];
controls.forEach(([button, action]) => {
  button.addEventListener("pointerdown", (event) => event.preventDefault(), { signal });
  button.addEventListener("click", action, { signal });
});

const resizeObserver = new ResizeObserver(() => {
  if (!active || !ready) return;
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { sizeCanvas(); render(); }, 200);
});
resizeObserver.observe(root);

/* =========================================================================
   Lifecycle
   ========================================================================= */
async function start() {
  if (active) return;
  active = true;
  const currentLifecycle = ++lifecycle;
  await new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
  if (!active || currentLifecycle !== lifecycle) return;
  sizeCanvas();
  if (!initialized) {
    view = stageView(authoredStage);
    initialized = true;
  }
  useWorkers = await initWorkers();
  if (!active || currentLifecycle !== lifecycle) return;
  ready = true;
  render();
}

function stop() {
  if (!active) return;
  settleMotion();
  active = false;
  ready = false;
  lifecycle++;
  gen++;
  job = null;
  animating = false;
  clearTimeout(resizeTimer);
  clearTimeout(toastTimer);
  cancelAnimationFrame(animationFrame);
  workers.forEach((worker) => worker.terminate());
  workers = [];
  useWorkers = false;
}

function setStage(stage) {
  const nextStage = stage === 1 ? 1 : 0;
  const shouldAnimate = ready && initialized && nextStage !== authoredStage;
  settleMotion();
  const from = initialized ? { ...view } : null;
  const source = shouldAnimate ? snapshotCanvas() : null;
  authoredStage = nextStage;
  history.length = 0;
  if (!initialized) return;
  view = stageView(authoredStage);
  render(false, shouldAnimate ? { source, from, to: { ...view } } : null);
}

function destroy() {
  stop();
  resizeObserver.disconnect();
  abortController.abort();
  if (workerUrl) URL.revokeObjectURL(workerUrl);
}

return { start, stop, destroy, setStage, settleMotion };
}
