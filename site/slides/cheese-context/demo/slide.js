import { Slide } from '../../../vividly/runtime/slide.js';

const PASSES = 3;

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 11,
};

export default class CheeseSlide extends Slide {
  mount(root) {
    this.root = root;
    this.previousStep = null;
    this.pile = root.querySelector('.pile');
    this.cheeses = [...root.querySelectorAll('.cheese')];
    this.marks = [...root.querySelectorAll('.marks')];

    for (const image of this.cheeses) {
      image.src = this.ctx.asset(image.dataset.asset);
    }

    for (const use of root.querySelectorAll('.marks use')) {
      use.setAttribute('href', this.ctx.asset(use.dataset.asset));
    }
  }

  setStep(step) {
    if (!this.pile) {
      return;
    }

    const skipTransitions = this.previousStep === null || Math.abs(step - this.previousStep) > 1;
    this.root.classList.toggle('skip-step-transitions', skipTransitions);
    this.pile.classList.toggle('on', step >= 1);

    for (let pass = 1; pass <= PASSES; pass += 1) {
      const flyIn = 2 + (pass - 1) * 3;
      const marksOn = flyIn + 1;
      const flyOut = flyIn + 2;
      const cheese = this.cheeses[pass - 1];

      cheese.dataset.state = step < flyIn ? 'before' : step < flyOut ? 'on' : 'after';
      this.marks[pass - 1].classList.toggle('on', step >= marksOn);
    }

    if (skipTransitions) {
      this.root.getBoundingClientRect();
      this.root.classList.remove('skip-step-transitions');
    }

    this.previousStep = step;
  }

  unmount() {
    this.root = null;
    this.previousStep = null;
    this.pile = null;
    this.cheeses = null;
    this.marks = null;
  }
}
