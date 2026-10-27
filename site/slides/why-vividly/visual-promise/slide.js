import { Slide } from 'vividly/runtime/slide.js';
import { BilliardsTable } from '../../experiments/pool-table-break/billiards.js';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 2,
};

const BREAK_SEED = 80;
const OWL_DRAW_DURATION = 1500;
const OWL_HOLD_DURATION = 150;
const OWL_ALIGN_DURATION = 1200;
const OWL_QUESTION_DURATION = 400;
const OWL_SAMPLE_COUNT = 240;
const OWL_START_YAW = 1.18;
const OWL_START_PITCH = -0.22;
const SVG_NS = 'http://www.w3.org/2000/svg';
let owlResourceSerial = 0;
const OWL_PATH = `
  M 177 20
  C 155 43 180 59 197 78
  C 211 93 190 111 205 130
  C 219 147 239 124 231 104
  C 223 84 194 83 190 105
  C 185 127 216 139 231 116
  C 249 86 276 71 309 59
  C 328 51 337 31 324 38
  C 302 49 302 78 282 91
  C 262 105 259 127 250 145
  C 238 124 251 105 272 96
  C 295 85 316 106 307 128
  C 298 151 272 146 262 127
  C 252 108 265 89 285 87
  C 316 83 326 117 313 150
  C 300 181 314 204 310 235
  C 305 278 278 306 248 324
  C 218 342 196 336 208 352
  C 218 365 240 349 254 357
  C 268 365 264 378 258 371
  C 246 357 223 362 208 356
  C 188 348 188 364 196 374
  C 178 362 195 345 209 339
  C 240 324 270 300 282 266
  C 295 226 281 194 253 178
  C 225 162 211 140 183 142
  C 147 145 113 184 103 220
  C 91 263 112 271 139 242
  C 163 216 194 190 214 174
  C 238 154 250 176 239 205
  C 229 232 190 249 165 267
  C 133 290 104 319 68 342
  C 46 357 39 374 64 364
  C 80 357 92 347 100 338
  C 85 365 78 383 95 380
  C 122 375 142 337 166 321
  C 190 304 211 288 211 260
  C 211 241 226 219 219 244
  C 209 274 184 291 159 309
  C 124 335 93 351 60 363
  C 43 370 50 347 70 332
  C 107 305 130 284 146 254
  C 163 222 152 187 166 153
  C 177 125 176 97 189 76
  C 203 54 238 44 267 51
  C 292 57 303 74 314 90
  C 327 117 313 147 306 172
  C 296 206 316 235 299 267
  C 280 303 250 323 235 341
  C 221 358 244 360 259 366
  C 274 374 266 388 283 393
`;
export default class VisualPromise extends Slide {
  mount(root) {
    this.root = root;
    this.beats = [...root.querySelectorAll('[data-promise-beat]')];
    this.progress = root.querySelector('vividly-step-progress');
    this.billiards = new BilliardsTable(root.querySelector('.billiards-table'), BREAK_SEED, {
      onProgress: (value) => {
        if (this.entered && this.step === 0) this.progress.value = value;
      },
    });
    this.owlSource = root.querySelector('[data-owl-source]');
    this.owlSource.setAttribute('d', OWL_PATH);
    this.owlPaths = [...root.querySelectorAll('.owl-wire')];
    this.owlTips = [...root.querySelectorAll('.owl-tip')];
    this.owlQuestion = root.querySelector('[data-owl-question]');
    this.owlPoints = sampleOwl(this.owlSource);
    this.configureOwlResources();
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.owlAnimation = null;
    this.owlTimer = null;
    this.owlDraw = 0;
    this.owlAlignment = 0;
    this.entered = false;
    this.step = 0;
    this.resetOwl();
  }

  setStep(step) {
    const previousStep = this.step;
    this.step = step;
    this.beats.forEach((beat, index) => {
      const active = index === step;
      beat.classList.toggle('is-active', active);
      beat.setAttribute('aria-hidden', String(!active));
      beat.inert = !active;
    });
    if (previousStep !== step) this.progress.value = 0;
    if (step === 0 && this.entered && previousStep !== 0) this.playBreak();
    if (step === 1 && this.entered && previousStep !== 1) this.playOwl();
    if (step !== 0) this.cancelBreak();
    if (step !== 1) this.cancelOwl();
  }

  enter({ step }) {
    this.entered = true;
    this.step = step;
    if (step === 0) this.playBreak();
    if (step === 1) this.playOwl();
  }

  exit() {
    this.entered = false;
    this.cancelBreak();
    this.cancelOwl();
  }

  settleStep() {
    if (this.step === 0 && this.billiards.running) {
      this.billiards.finish();
      return true;
    }
    if (
      this.step === 1
      && (this.owlTimer || this.owlAnimation)
    ) {
      window.clearTimeout(this.owlTimer);
      this.owlTimer = null;
      this.finishOwl();
      return true;
    }
    return false;
  }

  playBreak() {
    if (this.reducedMotion) {
      this.billiards.reset();
      this.billiards.finish();
      return;
    }
    this.billiards.play();
  }

  cancelBreak() {
    this.billiards.stop();
  }

  configureOwlResources() {
    const id = `visual-promise-owl-${++owlResourceSerial}`;
    const gradient = this.root.querySelector('[data-owl-gradient]');
    const glowFilter = this.root.querySelector('[data-owl-glow-filter]');
    const shadowFilter = this.root.querySelector('[data-owl-shadow-filter]');
    gradient.id = `${id}-light`;
    glowFilter.id = `${id}-glow`;
    shadowFilter.id = `${id}-shadow`;
    this.root.querySelector('.owl-body').style.stroke = `url("#${gradient.id}")`;
    this.root.querySelector('.owl-glow').style.filter = `url("#${glowFilter.id}")`;
    this.root.querySelector('.owl-shadow').style.filter = `url("#${shadowFilter.id}")`;
    this.root.querySelector('.owl-pool').style.filter = `url("#${shadowFilter.id}")`;
  }

  playOwl() {
    this.cancelOwl();
    this.resetOwl();
    this.progress.value = 0;
    if (this.reducedMotion) {
      this.applyOwlFinal();
      return;
    }
    this.owlTimer = window.setTimeout(() => {
      this.owlTimer = null;
      if (this.entered && this.step === 1) this.startOwl();
    }, 0);
  }

  startOwl() {
    const duration = (
      OWL_DRAW_DURATION
      + OWL_HOLD_DURATION
      + OWL_ALIGN_DURATION
      + OWL_QUESTION_DURATION
    );
    const startedAt = performance.now();
    this.owlAnimation = {
      frame: requestAnimationFrame((time) => this.tickOwl(time, startedAt, duration)),
    };
  }

  tickOwl(time, startedAt, duration) {
    const elapsed = Math.min(duration, time - startedAt);
    this.progress.value = elapsed / duration;
    this.owlDraw = Math.min(1, elapsed / OWL_DRAW_DURATION);
    const alignmentElapsed = elapsed - OWL_DRAW_DURATION - OWL_HOLD_DURATION;
    this.owlAlignment = alignmentElapsed <= 0
      ? 0
      : easeInOutCubic(Math.min(1, alignmentElapsed / OWL_ALIGN_DURATION));
    const questionElapsed = alignmentElapsed - OWL_ALIGN_DURATION;
    const questionOpacity = questionElapsed <= 0
      ? 0
      : easeInOutCubic(Math.min(1, questionElapsed / OWL_QUESTION_DURATION));
    this.owlQuestion.style.opacity = String(questionOpacity);
    this.renderOwl();

    if (elapsed < duration) {
      this.owlAnimation.frame = requestAnimationFrame(
        (nextTime) => this.tickOwl(nextTime, startedAt, duration),
      );
      return;
    }
    this.owlAnimation = null;
  }

  finishOwl() {
    if (this.owlAnimation) cancelAnimationFrame(this.owlAnimation.frame);
    this.owlAnimation = null;
    this.applyOwlFinal();
  }

  cancelOwl() {
    window.clearTimeout(this.owlTimer);
    this.owlTimer = null;
    if (this.owlAnimation) cancelAnimationFrame(this.owlAnimation.frame);
    this.owlAnimation = null;
    this.resetOwl();
  }

  resetOwl() {
    this.owlDraw = 0;
    this.owlAlignment = 0;
    this.owlQuestion.style.removeProperty('opacity');
    this.renderOwl();
  }

  applyOwlFinal() {
    this.owlDraw = 1;
    this.owlAlignment = 1;
    this.owlQuestion.style.opacity = '1';
    this.renderOwl();
    this.progress.value = 1;
  }

  renderOwl() {
    const projected = this.owlPoints.map((point) => projectOwl(point, this.owlAlignment));
    const drawing = this.owlDraw > 0 && this.owlDraw < 1;
    // Reverse the middle third so the first two heads converge at their shared join.
    const sections = drawing ? [
      sliceOwl(projected, 0, this.owlDraw / 3),
      sliceOwl(projected, 2 / 3, (2 - this.owlDraw) / 3),
      sliceOwl(projected, 2 / 3, (2 + this.owlDraw) / 3),
    ] : [];
    const visibleSections = this.owlDraw === 1 ? [projected] : sections;
    const pathData = visibleSections
      .map((points) => points
        .map(({ x, y }, index) => `${index === 0 ? 'M' : 'L'} ${round(x)} ${round(y)}`)
        .join(' '))
      .join(' ');
    for (const path of this.owlPaths) {
      path.setAttribute('d', pathData);
    }
    this.owlTips.forEach((tip, index) => {
      if (drawing) {
        const endpoint = sections[index].at(-1);
        tip.setAttribute('cx', round(endpoint.x));
        tip.setAttribute('cy', round(endpoint.y));
      }
      tip.style.opacity = drawing ? '1' : '0';
    });
  }

  unmount() {
    this.cancelBreak();
    this.billiards.dispose();
    this.cancelOwl();
    this.root = null;
    this.beats = null;
    this.progress = null;
    this.billiards = null;
    this.owlSource = null;
    this.owlPaths = null;
    this.owlTips = null;
    this.owlQuestion = null;
    this.owlPoints = null;
  }
}

function sliceOwl(points, start, end) {
  const lengths = [0];
  for (let index = 1; index < points.length; index += 1) {
    lengths.push(lengths[index - 1] + Math.hypot(
      points[index].x - points[index - 1].x,
      points[index].y - points[index - 1].y,
    ));
  }
  const total = lengths.at(-1);
  const from = Math.min(start, end) * total;
  const to = Math.max(start, end) * total;
  const section = [];
  for (let index = 1; index < points.length; index += 1) {
    const lower = Math.max(from, lengths[index - 1]);
    const upper = Math.min(to, lengths[index]);
    if (upper <= lower) continue;
    const interpolate = (length) => {
      const fraction = (length - lengths[index - 1]) / (lengths[index] - lengths[index - 1]);
      return {
        x: points[index - 1].x + (points[index].x - points[index - 1].x) * fraction,
        y: points[index - 1].y + (points[index].y - points[index - 1].y) * fraction,
      };
    };
    if (section.length === 0) section.push(interpolate(lower));
    section.push(interpolate(upper));
  }
  return start > end ? section.reverse() : section;
}

function sampleOwl(source) {
  const sampler = document.createElementNS(SVG_NS, 'path');
  sampler.setAttribute('d', source.getAttribute('d'));
  const length = sampler.getTotalLength();
  const sampled = Array.from({ length: OWL_SAMPLE_COUNT }, (_, index) => {
    const t = index / (OWL_SAMPLE_COUNT - 1);
    const point = sampler.getPointAtLength(length * t);
    return { x: point.x, y: point.y, t };
  });
  const xs = sampled.map(({ x }) => x);
  const ys = sampled.map(({ y }) => y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const scale = 390 / Math.max(maxX - minX, maxY - minY);

  return sampled.map(({ x, y, t }) => ({
    x: (x - centerX) * scale,
    y: (y - centerY) * scale,
    z: owlDepthAt(t),
  }));
}

function owlDepthAt(t) {
  const envelope = Math.sin(Math.PI * t) ** 0.35;
  return envelope * (
    168 * Math.sin(t * Math.PI * 5.2 + 0.35)
    + 82 * Math.sin(t * Math.PI * 12.6 - 0.8)
    + 38 * Math.cos(t * Math.PI * 23.4)
  );
}

function projectOwl(point, alignment) {
  const easedAlignment = easeInOutCubic(alignment);
  const yaw = OWL_START_YAW * (1 - easedAlignment);
  const pitch = OWL_START_PITCH * (1 - easedAlignment);
  const cosYaw = Math.cos(yaw);
  const sinYaw = Math.sin(yaw);
  const cosPitch = Math.cos(pitch);
  const sinPitch = Math.sin(pitch);
  const rotatedX = point.x * cosYaw + point.z * sinYaw;
  const rotatedZ = -point.x * sinYaw + point.z * cosYaw;
  const rotatedY = point.y * cosPitch - rotatedZ * sinPitch;
  const finalZ = point.y * sinPitch + rotatedZ * cosPitch;
  const perspective = 1 / (1 + finalZ * (1 - easedAlignment) / 1450);
  const scale = 1.48 * perspective;

  return {
    x: 600 + rotatedX * scale,
    y: 330 + rotatedY * scale,
  };
}

function easeInOutCubic(value) {
  return value < 0.5
    ? 4 * value ** 3
    : 1 - ((-2 * value + 2) ** 3) / 2;
}

function round(value) {
  return Math.round(value * 10) / 10;
}
