import { Slide } from 'vividly/runtime/slide.js';
import { createMandelbrotViewer } from './engine.js';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 2,
};

export default class MandelbrotViewer extends Slide {
  mount(root) {
    this.viewer = createMandelbrotViewer(root);
    this.viewer.setStage(this.step ?? 0);
  }

  setStep(step) {
    this.step = step;
    this.viewer?.setStage(step);
  }

  settleStep() {
    return this.viewer?.settleMotion() ?? false;
  }

  enter() {
    void this.viewer.start();
  }

  exit() {
    this.viewer.stop();
  }

  unmount() {
    this.viewer.destroy();
    this.viewer = null;
  }
}
