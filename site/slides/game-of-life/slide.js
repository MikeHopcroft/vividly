import { Slide } from 'vividly/runtime/slide.js';
import { LifeRenderer } from './engine.js';
import { configHash, decodeFrames } from './frames.mjs';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
};

export default class GameOfLife extends Slide {
  async preload() {
    const url = new URL('./data/frames.json', import.meta.url);
    const [response, hash] = await Promise.all([fetch(url), configHash(this.ctx.props)]);
    if (!response.ok) {
      throw new Error(`Cannot load Life frames (${response.status}) from ${url}. Run npm --prefix tools/life run generate`);
    }
    this.frames = decodeFrames(await response.json(), hash);
    return { steps: this.frames.length };
  }

  mount(root) {
    this.renderer = new LifeRenderer(root);
    this.renderer.show(this.frames[this.step ?? 0]);
  }

  enter() {
    this.renderer.resize();
  }

  setStep(step) {
    const frame = this.frames[step];
    if (!frame) throw new RangeError(`No Game of Life frame configured for step ${step}`);

    const previousStep = this.step;
    const isAdjacentForward = previousStep !== undefined && step === previousStep + 1;
    const isBackward = previousStep !== undefined && step < previousStep;
    const previousFrame = previousStep === undefined ? undefined : this.frames[previousStep];
    const isAdjacent = previousStep !== undefined && Math.abs(step - previousStep) === 1;
    const changesPassage = previousFrame?.passageId !== frame.passageId;
    this.step = step;

    if (!this.renderer) return;
    if (frame.animation && isAdjacentForward) {
      this.renderer.animate(frame);
      return;
    }
    this.renderer.show(frame, {
      animateViewport: isAdjacentForward && !frame.predictions && !changesPassage,
      crossfade: isAdjacent && changesPassage,
      morph: isAdjacentForward || isBackward,
    });
  }

  settleStep() {
    return this.renderer?.settle() ?? false;
  }

  exit() {
    this.renderer?.settle();
  }

  unmount() {
    this.renderer.destroy();
    this.renderer = null;
  }
}
