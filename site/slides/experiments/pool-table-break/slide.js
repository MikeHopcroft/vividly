import { Slide } from 'vividly/runtime/slide.js';
import { BilliardsTable } from './billiards.js';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 2,
};

// Audition with ?breakSeed=123#/pool-table-break-lab/opening, then pin the chosen seed here.
// Manifest props.breakSeed overrides this default; the URL override takes precedence.
const BREAK_SEED = 7;
const POSSIBILITIES_DURATION = 3200;

export default class VisualPromise extends Slide {
  mount(root) {
    this.root = root;
    this.beats = [...root.querySelectorAll('[data-promise-beat]')];
    this.markers = [...root.querySelectorAll('[data-promise-marker]')];
    const seedParameter = new URLSearchParams(window.location.search).get('breakSeed');
    if (seedParameter !== null && !/^\d+$/.test(seedParameter)) {
      throw new RangeError('breakSeed must be an integer between 0 and 4294967295.');
    }
    const seed = seedParameter === null ? (this.ctx.props.breakSeed ?? BREAK_SEED) : Number(seedParameter);
    this.billiards = new BilliardsTable(root.querySelector('.billiards-table'), seed);
    this.possibilityPaths = [...root.querySelectorAll('.possibility-paths path')];
    this.possibilityPoints = [...root.querySelectorAll('.possibility-points circle')];
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.possibilityAnimations = [];
    this.entered = false;
    this.step = 0;
    this.resetPossibilities();
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
    this.markers.forEach((marker, index) => {
      marker.classList.toggle('is-active', index === step);
    });
    if (step === 0 && this.entered && previousStep !== 0) this.playBreak();
    if (step === 1 && this.entered && previousStep !== 1) this.playPossibilities();
    if (step !== 0) this.cancelBreak();
    if (step !== 1) this.cancelPossibilities();
  }

  enter({ step }) {
    this.entered = true;
    this.step = step;
    if (step === 0) this.playBreak();
    if (step === 1) this.playPossibilities();
  }

  exit() {
    this.entered = false;
    this.cancelBreak();
    this.cancelPossibilities();
  }

  settleStep() {
    if (this.step === 0 && this.billiards.running) {
      this.billiards.finish();
      return true;
    }
    if (
      this.step === 1
      && (this.possibilitiesTimer || this.possibilityAnimations.length > 0)
    ) {
      window.clearTimeout(this.possibilitiesTimer);
      this.possibilitiesTimer = null;
      this.finishPossibilities();
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

  playPossibilities() {
    this.cancelPossibilities();
    this.resetPossibilities();
    if (this.reducedMotion) {
      this.applyPossibilitiesFinal();
      return;
    }
    this.possibilitiesTimer = window.setTimeout(() => {
      this.possibilitiesTimer = null;
      if (this.entered && this.step === 1) this.startPossibilities();
    }, 0);
  }

  startPossibilities() {
    this.possibilityAnimations = [
      ...this.possibilityPaths.map((path, index) => path.animate(
        [
          { strokeDashoffset: 1, opacity: .18 },
          { strokeDashoffset: 0, opacity: index < 2 ? .32 : .9 },
        ],
        {
          delay: index * 130,
          duration: POSSIBILITIES_DURATION - index * 90,
          easing: 'cubic-bezier(.2,.72,.2,1)',
          fill: 'forwards',
        },
      )),
      ...this.possibilityPoints.map((point, index) => point.animate(
        [
          { opacity: 0, transform: 'scale(.2)' },
          { opacity: 1, transform: 'scale(1)' },
        ],
        {
          delay: 1350 + index * 150,
          duration: 520,
          easing: 'cubic-bezier(.2,.8,.2,1)',
          fill: 'forwards',
        },
      )),
    ];

    const animations = this.possibilityAnimations;
    Promise.allSettled(animations.map((animation) => animation.finished)).then(() => {
      if (this.possibilityAnimations === animations) this.applyPossibilitiesFinal();
    });
  }

  finishPossibilities() {
    if (this.possibilityAnimations.length > 0) {
      for (const animation of this.possibilityAnimations) animation.finish();
    }
    this.applyPossibilitiesFinal();
  }

  cancelPossibilities() {
    window.clearTimeout(this.possibilitiesTimer);
    this.possibilitiesTimer = null;
    for (const animation of this.possibilityAnimations) animation.cancel();
    this.possibilityAnimations = [];
    this.resetPossibilities();
  }

  resetPossibilities() {
    for (const element of [...this.possibilityPaths, ...this.possibilityPoints]) {
      element.getAnimations().forEach((animation) => animation.cancel());
      element.style.removeProperty('opacity');
      element.style.removeProperty('stroke-dashoffset');
      element.style.removeProperty('transform');
    }
  }

  applyPossibilitiesFinal() {
    for (const path of this.possibilityPaths) {
      path.style.opacity = '1';
      path.style.strokeDashoffset = '0';
    }
    for (const point of this.possibilityPoints) {
      point.style.opacity = '1';
      point.style.transform = 'scale(1)';
    }
    this.possibilityAnimations = [];
  }

  unmount() {
    this.cancelBreak();
    this.billiards.dispose();
    this.cancelPossibilities();
    this.root = null;
    this.beats = null;
    this.markers = null;
    this.billiards = null;
    this.possibilityPaths = null;
    this.possibilityPoints = null;
  }
}
