import { Slide } from 'vividly/runtime/slide.js';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 1,
};

export default class IntroducingVividly extends Slide {
  mount(root) {
    this.root = root;
    this.layout = root.querySelector('.introduction');
    this.progress = root.querySelector('vividly-step-progress');
    this.progress.value = 1;
    this.progressFrame = null;
    root.querySelector('.introduction-logo').src =
      new URL('../../../vividly/assets/logo.svg', import.meta.url).href;
  }

  enter({ direction, restoring }) {
    this.stopProgress();
    this.progress.value = 1;
    this.layout.classList.remove('is-revealing');
    if (
      direction === 'forward'
      && !restoring
      && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
      && !this.root.closest('vividly-presentation')?.hasAttribute('data-capture')
    ) {
      void this.layout.offsetWidth;
      this.layout.classList.add('is-revealing');
      this.progress.value = 0;
      this.progressFrame = requestAnimationFrame(() => this.updateProgress());
    }
  }

  updateProgress() {
    let duration = 0;
    let remaining = 0;
    for (const animation of this.layout.getAnimations({ subtree: true })) {
      const end = animation.effect.getComputedTiming().endTime;
      duration = Math.max(duration, end);
      remaining = Math.max(remaining, end - Number(animation.currentTime ?? 0));
    }
    this.progress.value = duration === 0 ? 1 : 1 - remaining / duration;
    this.progressFrame = this.progress.value < 1
      ? requestAnimationFrame(() => this.updateProgress())
      : null;
  }

  stopProgress() {
    if (this.progressFrame !== null) cancelAnimationFrame(this.progressFrame);
    this.progressFrame = null;
  }

  settleStep() {
    const animations = this.layout.getAnimations({ subtree: true }).filter(
      animation => animation.playState !== 'finished' && animation.playState !== 'idle',
    );
    for (const animation of animations) animation.finish();
    this.stopProgress();
    this.progress.value = 1;
    return animations.length > 0;
  }

  exit() {
    this.stopProgress();
    this.layout.classList.remove('is-revealing');
  }

  unmount() {
    this.exit();
    this.progress = null;
    this.layout = null;
    this.root = null;
  }
}
