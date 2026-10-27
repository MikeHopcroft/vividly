// Base class for slide modules. Every method has a no-op default, so a slide
// implements only what it needs — a static slide implements nothing at all.

export const DYNAMIC = 'dynamic';

export class Slide {
  constructor(ctx) {
    this.ctx = ctx;
  }

  /** Fetch data. No DOM. Return { steps } — an integer >= 1, or DYNAMIC.
   *  Omitting steps defers to meta.steps, then to 1. */
  async preload() {
    return {};
  }

  /** Root is in the document but hidden; do not assume visibility or size. */
  mount(_root) {}

  enter(_info) {}

  /** Must be idempotent and order-independent. */
  setStep(_n) {}

  /** Complete custom motion for the current state. Return true when motion was completed. */
  settleStep() {
    return false;
  }

  /** Dynamic slides only. Return false to hand navigation back to the deck. */
  advance(_delta) {
    return false;
  }

  exit(_info) {}

  unmount() {}

  dispose() {}
}
