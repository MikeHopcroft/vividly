import { Slide } from 'vividly/runtime/slide.js';
import { createCityRenderer, ENDING_TIMING, SCENES } from './engine.js';
import { SKETCH_TIMING } from './sketch.js';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: SCENES.length,
};

const TRANSITION_DURATION = 450;
const CONTINUITY_TRANSITIONS = new Set([
  'gears:first-loop',
  'city:drivers',
  'drivers:city',
  'drivers:zoom',
  'zoom:drivers',
  'drivers:everywhere',
  'everywhere:detour',
  'headlights:pull',
  'pull:headlights',
]);

export default class CityOfLoops extends Slide {
  mount(root) {
    this.root = root;
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.entered = false;
    this.hasEntered = false;
    this.stepDirection = 1;
    this.title = root.querySelector('#scene-title');
    this.copy = root.querySelector('#scene-copy');
    this.captionCurrent = root.querySelector('.caption-current');
    this.captionOutgoing = root.querySelector('.caption-outgoing');
    this.captionExpansion = root.querySelector('.caption-expansion');
    this.expansionTitle = root.querySelector('#expansion-title');
    this.expansionCopy = root.querySelector('#expansion-copy');
    this.stage = root.querySelector('.stage');
    this.closing = root.querySelector('.closing');
    this.closingTitle = root.querySelector('#closing-title');
    this.closingCopy = root.querySelector('#closing-copy');
    this.timing = root.querySelector('.timing');

    this.canvasRecords = [...root.querySelectorAll('.scene-canvas')].map(canvas => {
      const record = { canvas };
      record.renderer = createCityRenderer(canvas, {
        reducedMotion: this.reducedMotion,
        getWaterfallHeight: () => (
          this.captionCurrent.getBoundingClientRect().top
          - canvas.getBoundingClientRect().top
          - 24
        ),
        onProgress: (progress, elapsed) => {
          if (record === this.activeRecord) {
            this.setProgress(progress);
            this.updateEndingTime(elapsed);
            this.updateSketchTime(elapsed);
          }
        },
      });
      return record;
    });
    this.activeRecord = this.canvasRecords[0];
    this.activeRecord.canvas.classList.add('is-active');
    this.step ??= 0;
    this.applyScene(this.step, false);
  }

  setStep(step) {
    if (!SCENES[step]) {
      throw new RangeError(`No City of Loops scene configured for step ${step}`);
    }
    const previousStep = this.step;
    if (previousStep !== undefined && previousStep !== step) {
      this.stepDirection = Math.sign(step - previousStep);
    }
    this.step = step;
    const transition = this.entered
      && !this.reducedMotion
      && previousStep !== undefined
      && previousStep !== step;
    this.applyScene(step, transition, previousStep);
  }

  applyScene(step, transition, previousStep) {
    if (!this.activeRecord) return;
    const scene = SCENES[step];
    if (transition) this.beginChromeTransition(previousStep);
    this.updateSceneContent(scene);
    if (transition) {
      const previousScene = SCENES[previousStep];
      if (CONTINUITY_TRANSITIONS.has(`${previousScene.key}:${scene.key}`)) {
        this.finishCanvasTransition();
        this.activeRecord.renderer.transitionToScene(step, previousStep);
      } else {
        const duration = previousScene.key === 'first-loop' && scene.key === 'drivers'
          ? SKETCH_TIMING.cityFade * 1000
          : TRANSITION_DURATION;
        this.beginCanvasTransition(step, duration);
      }
    } else {
      this.finishTransition();
      this.setProgress(0);
      this.activeRecord.renderer.setScene(step);
    }
    if (this.entered) this.activeRecord.renderer.start();
  }

  updateSceneContent(scene) {
    this.root.querySelector('.city-slide').classList.toggle('is-sketch', Boolean(scene.expansion));
    this.captionExpansion.hidden = !scene.expansion;
    this.expansionTitle.innerHTML = scene.expansion?.title ?? '';
    this.expansionCopy.textContent = scene.expansion?.text ?? '';
    this.title.innerHTML = scene.title;
    this.copy.innerHTML = scene.text;
    this.copy.classList.remove('is-revealing', 'is-at-start');
    this.copy.removeAttribute('aria-hidden');
    this.copy.style.removeProperty('opacity');
    this.copy.style.removeProperty('visibility');
    this.setCaptionVisibility(this.captionCurrent, 1);
    this.closing.hidden = !scene.ending;
    this.closingTitle.innerHTML = scene.ending?.title ?? '';
    this.closingCopy.textContent = scene.ending?.text ?? '';
    this.stage.setAttribute('aria-labelledby', 'scene-title');
    this.stage.setAttribute('aria-describedby', 'scene-copy');
    void this.copy.offsetWidth;
    if (!this.reducedMotion && !scene.ending && !scene.expansion) {
      this.copy.classList.add('is-revealing');
    }
  }

  updateSketchTime(elapsed) {
    if (!SCENES[this.step]?.expansion) return;
    const amount = this.reducedMotion ? 1 : Math.min(1, Math.max(
      0, (elapsed - SKETCH_TIMING.expansion) / .6,
    ));
    this.setCaptionVisibility(this.captionExpansion, amount);
    this.setCaptionVisibility(this.captionCurrent, 1 - amount * .3);
    this.stage.setAttribute('aria-labelledby', amount > 0
      ? 'scene-title expansion-title' : 'scene-title');
    this.stage.setAttribute('aria-describedby', amount > 0
      ? 'scene-copy expansion-copy' : 'scene-copy');
  }

  setCaptionVisibility(element, opacity) {
    element.style.opacity = String(opacity);
    element.style.visibility = opacity > 0 ? 'visible' : 'hidden';
    const hidden = String(opacity === 0);
    if (element.getAttribute('aria-hidden') !== hidden) {
      element.setAttribute('aria-hidden', hidden);
    }
  }

  updateEndingTime(elapsed) {
    if (!SCENES[this.step]?.ending) return;
    const fade = (start, end) => {
      const amount = Math.min(1, Math.max(0, (elapsed - start) / (end - start)));
      return amount * amount * (3 - 2 * amount);
    };
    const proof = 1 - fade(ENDING_TIMING.proofFadeStart, ENDING_TIMING.proofFadeEnd);
    this.setCaptionVisibility(this.captionCurrent, proof);
    this.setCaptionVisibility(this.copy, fade(.7, 1.3));
    this.setCaptionVisibility(
      this.closingTitle, fade(ENDING_TIMING.titleStart, ENDING_TIMING.titleEnd),
    );
    this.setCaptionVisibility(
      this.closingCopy, fade(ENDING_TIMING.questionStart, ENDING_TIMING.questionEnd),
    );
    this.stage.setAttribute('aria-labelledby', proof > 0 ? 'scene-title' : 'closing-title');
    this.stage.setAttribute('aria-describedby', proof > 0 ? 'scene-copy' : 'closing-copy');
  }

  beginCanvasTransition(step, duration = TRANSITION_DURATION) {
    this.finishCanvasTransition();
    const outgoing = this.activeRecord;
    const incoming = this.canvasRecords.find(record => record !== outgoing);
    this.activeRecord = incoming;
    incoming.renderer.setScene(step);
    if (this.entered) incoming.renderer.start();
    incoming.canvas.className = 'scene-canvas is-active';
    outgoing.canvas.className = 'scene-canvas is-active';
    outgoing.canvas.style.setProperty('--canvas-transition-duration', `${duration}ms`);
    void outgoing.canvas.offsetWidth;
    outgoing.canvas.className = 'scene-canvas is-outgoing';
    this.outgoingRecord = outgoing;
    this.canvasTransitionTimer = window.setTimeout(
      () => this.finishCanvasTransition(),
      duration,
    );
  }

  beginChromeTransition(previousStep) {
    this.finishChromeTransition();

    this.captionOutgoing.querySelector('h2').innerHTML = this.title.innerHTML;
    this.captionOutgoing.classList.toggle(
      'is-sketch-outgoing',
      Boolean(SCENES[previousStep]?.expansion || SCENES[this.step]?.expansion),
    );
    this.captionOutgoing.style.visibility = this.captionCurrent.style.visibility;
    const outgoingCopy = this.captionOutgoing.querySelector('.scene-copy');
    outgoingCopy.innerHTML = this.copy.innerHTML;
    outgoingCopy.classList.toggle('is-at-start', this.copy.classList.contains('is-at-start'));
    this.captionOutgoing.classList.add('is-visible');
    void this.captionOutgoing.offsetWidth;
    this.captionOutgoing.classList.add('is-outgoing');

    this.chromeTransitionTimer = window.setTimeout(
      () => this.finishChromeTransition(),
      TRANSITION_DURATION,
    );
  }

  finishCanvasTransition() {
    if (!this.outgoingRecord) return false;
    window.clearTimeout(this.canvasTransitionTimer);
    this.outgoingRecord.renderer.stop();
    this.outgoingRecord.canvas.className = 'scene-canvas';
    this.activeRecord.canvas.className = 'scene-canvas is-active';
    this.outgoingRecord = null;
    this.canvasTransitionTimer = null;
    return true;
  }

  finishChromeTransition() {
    const transitioning = this.captionOutgoing.classList.contains('is-visible');
    window.clearTimeout(this.chromeTransitionTimer);
    this.captionOutgoing.classList.remove('is-visible', 'is-outgoing');
    this.captionOutgoing.querySelector('h2').textContent = '';
    this.captionOutgoing.querySelector('.scene-copy').textContent = '';
    this.chromeTransitionTimer = null;
    return transitioning;
  }

  finishTransition() {
    const canvasChanged = this.finishCanvasTransition();
    const chromeChanged = this.finishChromeTransition();
    return canvasChanged || chromeChanged;
  }

  setProgress(progress) {
    this.timing.value = progress;
  }

  enter({ step, direction } = {}) {
    this.stepDirection = direction === 'backward' ? -1 : 1;
    if (!this.hasEntered && Number.isInteger(step) && step !== this.step) {
      this.step = step;
      this.applyScene(step, false);
    }
    this.hasEntered = true;
    this.entered = true;
    this.activeRecord?.renderer.start();
  }

  exit() {
    this.entered = false;
    this.finishTransition();
    for (const record of this.canvasRecords ?? []) record.renderer.stop();
  }

  settleStep() {
    const transitionChanged = this.finishTransition();
    const copyAnimations = this.copy?.getAnimations() ?? [];
    const copyChanged = copyAnimations.some(animation => animation.playState !== 'finished');
    for (const animation of copyAnimations) animation.finish();
    const sceneChanged = this.activeRecord?.renderer.finishScene(this.stepDirection) ?? false;
    const changed = transitionChanged || copyChanged || sceneChanged;
    if (changed && this.stepDirection < 0) {
      this.copy.classList.remove('is-revealing');
      this.copy.classList.add('is-at-start');
      this.copy.setAttribute('aria-hidden', 'true');
    }
    return changed;
  }

  unmount() {
    this.finishTransition();
    for (const record of this.canvasRecords ?? []) record.renderer.destroy();
    this.canvasRecords = null;
    this.activeRecord = null;
    this.root = null;
  }
}
