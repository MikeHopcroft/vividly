import { Slide } from 'vividly/runtime/slide.js';
import { createBreakCandidates } from './break-candidates.js';

export const meta = {
  styles: ['./break-candidates.css'],
  steps: 1,
};

export default class BreakCandidates extends Slide {
  mount(root) {
    this.comparison = createBreakCandidates(root);
  }

  enter() {
    this.frame = requestAnimationFrame(() => {
      this.frame = null;
      this.comparison.finish();
    });
  }

  exit() {
    cancelAnimationFrame(this.frame);
    this.frame = null;
    this.comparison.stop();
  }

  settleStep() {
    const pending = this.frame != null;
    cancelAnimationFrame(this.frame);
    this.frame = null;
    if (pending) this.comparison.finish();
    return this.comparison.settle() || pending;
  }

  unmount() {
    this.exit();
    this.comparison.dispose();
    this.comparison = null;
  }
}
