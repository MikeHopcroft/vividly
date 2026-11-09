import { Slide } from "vividly/runtime/slide.js";
import { StageCamera } from "../demo/camera.js";
import { renderMovieDiagram } from "./view.js";

export const meta = {
  template: "./slide.html",
  styles: ["./slide.css"],
  steps: 4,
};

const SCENES = [
  {
    targets: ["liked", "encoding"], active: ["x"],
    caption: "Four liked movies become four ones in a 9,500-value multi-hot input.",
  },
  {
    targets: ["encoding", "network"], active: ["x", "w1", "b1", "relu", "w2"],
    caption: "Add the four selected W₁ rows, add bias, apply ReLU, then score every movie.",
  },
  {
    targets: ["winner"], active: ["argmax"],
    caption: "Mask already-liked movies—even those with higher scores—then choose Cold Case, Warm Room (8.54).",
  },
  {
    targets: ["recommendations"], active: [],
    caption: "One logit per movie: 46 distinct examples from a catalog of 9,500.",
  },
];

export default class MovieRecommendationsSlide extends Slide {
  mount(root) {
    this.root = root;
    this.active = false;
    this.step = null;
    renderMovieDiagram(root);
    this.revealElements = [...root.querySelectorAll(".network, .score-arrow, .recommendations")];
    this.revealAnimations = [];
    for (const element of this.revealElements) {
      element.style.opacity = "0";
      element.inert = true;
    }
    this.camera = new StageCamera(
      root.querySelector(".movie-viewport"),
      root.querySelector(".movie-camera"),
      {
        liked: root.querySelector(".liked-card"),
        encoding: root.querySelector(".input-vector-card"),
        network: root.querySelector(".network"),
        winner: root.querySelector(".winner-focus"),
        recommendations: root.querySelector(".recommendations"),
      },
      undefined,
      { minimumScale: 0.01 },
    );
    this.events = new AbortController();
    const reset = root.querySelector(".reset-view");
    reset.addEventListener("click", () => {
      this.camera.frame(SCENES[this.step].targets, { padding: 36 });
    }, { signal: this.events.signal });
    this.ctx.captureKeys(event => {
      if (event.target !== reset || event.key !== " ") return false;
      reset.click();
      return true;
    });
  }

  enter({ step = 0 } = {}) {
    this.active = true;
    this.applyStep(step, false);
  }

  setStep(step) {
    this.applyStep(step, this.active && step !== this.step);
  }

  applyStep(step, animate) {
    if (!Number.isInteger(step) || step < 0 || step >= SCENES.length) {
      throw new RangeError(`Movie explainer step must be between 0 and ${SCENES.length - 1}`);
    }
    const duration = this.step === 1 && step === 2 ? 1800 : 900;
    this.step = step;
    const scene = SCENES[step];
    this.root.querySelector(".scene-caption").textContent = scene.caption;
    this.root.querySelector(".step-readout").textContent = `${step + 1} / ${SCENES.length}`;
    for (const part of this.root.querySelectorAll("[data-formula]")) {
      const on = scene.active.includes(part.dataset.formula);
      part.classList.toggle("on", on);
      part.classList.toggle("dim", scene.active.length > 0 && !on);
    }
    const motion = this.active && animate
      && !new URLSearchParams(location.search).has("instant")
      && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    const opacities = this.revealElements.map(element => getComputedStyle(element).opacity);
    this.finishReveal();
    this.revealElements.forEach((element, index) => {
      const opacity = step === 0 ? "0" : "1";
      element.style.opacity = opacity;
      element.inert = step === 0;
      if (motion && opacities[index] !== opacity) {
        this.revealAnimations.push(element.animate([
          { opacity: opacities[index] },
          { opacity },
        ], { duration, easing: "ease-in-out" }));
      }
    });
    if (!this.active) return;
    if (motion) {
      this.camera.animateFrame(scene.targets, { padding: 36, duration });
    } else {
      this.camera.frame(scene.targets, { padding: 36 });
    }
  }

  settleStep() {
    const revealed = this.finishReveal();
    return this.camera.finish() || revealed;
  }

  finishReveal() {
    const unfinished = this.revealAnimations.some(animation =>
      animation.playState === "running" || animation.pending);
    for (const animation of this.revealAnimations) animation.cancel();
    this.revealAnimations = [];
    return unfinished;
  }

  exit() {
    this.active = false;
    this.finishReveal();
    this.camera.finish();
  }

  unmount() {
    this.finishReveal();
    this.camera.destroy();
    this.events.abort();
    this.root = null;
  }
}
