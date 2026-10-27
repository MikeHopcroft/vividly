import { createTicTacToeDemo } from "./demo.js";

export function createTicTacToeSlide(mode = "presentation") {
  return class TicTacToeDemoSlide {
    constructor(ctx) {
      this.ctx = ctx;
      this.demo = createTicTacToeDemo();
      this.root = null;
    }

    async preload() {
      const [, result] = await Promise.all([
        loadDemoStyles(),
        this.demo.preload(),
      ]);
      return mode === "presentation" ? result : { steps: 1 };
    }

    mount(root) {
      this.root = root;
      adoptDemoStyles();
      root.classList.add("tic-tac-toe-demo", "vividly-hosted");
      this.demo.mount(root);
      this.ctx.captureKeys(event => captureFocusedControlKey(root, event));
    }

    enter({ step = 0 } = {}) {
      this.demo.enter({ step, mode });
    }

    setStep(step) {
      if (mode === "presentation") return this.demo.setStep(step);
      if (Number(step) !== 0) throw new RangeError(`${mode} slide only has step 0`);
      return this.demo.setMode(mode);
    }

    settleStep() {
      return this.demo.settleStep();
    }

    exit() {
      this.demo.exit();
    }

    unmount() {
      this.demo.unmount();
      this.root?.classList.remove("tic-tac-toe-demo", "vividly-hosted");
      this.root = null;
    }

    dispose() {
      this.demo.dispose();
    }
  };
}

export default createTicTacToeSlide();

let stylesheetTextPromise = null;
let stylesheetText = null;
let stylesheet = null;

function loadDemoStyles() {
  if (stylesheetTextPromise) return stylesheetTextPromise;
  const href = new URL("./demo.css", import.meta.url).href;
  stylesheetTextPromise = fetch(href).then(async response => {
    if (!response.ok) {
      throw new Error(`Failed to load demo stylesheet: ${response.status} ${response.statusText}`);
    }
    stylesheetText = await response.text();
  });
  return stylesheetTextPromise;
}

function adoptDemoStyles() {
  if (stylesheetText === null) throw new Error("Demo must be preloaded before mounting");
  if (!stylesheet) {
    stylesheet = new CSSStyleSheet();
    stylesheet.replaceSync(stylesheetText);
  }
  if (!document.adoptedStyleSheets.includes(stylesheet)) {
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, stylesheet];
  }
}

function captureFocusedControlKey(root, event) {
  const control = event.target instanceof Element
    ? event.target.closest("button, input, select")
    : null;
  if (!control || !root.contains(control)) return false;

  if (control instanceof HTMLButtonElement && event.key === " ") {
    control.click();
    return true;
  }

  if (
    control instanceof HTMLInputElement &&
    (control.type === "checkbox" || control.type === "radio") &&
    event.key === " "
  ) {
    control.click();
    return true;
  }

  if (control instanceof HTMLSelectElement) {
    return moveSelect(control, event.key);
  }

  if (control instanceof HTMLInputElement && control.type === "range") {
    return moveRange(control, event.key);
  }

  if (control instanceof HTMLInputElement && control.type === "number") {
    return moveNumber(control, event.key);
  }

  return false;
}

function moveSelect(select, key) {
  let index = select.selectedIndex;
  if (key === "Home") index = 0;
  else if (key === "End") index = select.options.length - 1;
  else if (key === "ArrowUp" || key === "ArrowLeft") index -= 1;
  else if (key === "ArrowDown" || key === "ArrowRight") index += 1;
  else return false;

  index = Math.max(0, Math.min(select.options.length - 1, index));
  while (select.options[index]?.disabled) {
    const next = index + (key === "ArrowUp" || key === "ArrowLeft" ? -1 : 1);
    if (next < 0 || next >= select.options.length) return true;
    index = next;
  }
  if (index !== select.selectedIndex) {
    select.selectedIndex = index;
    dispatchControlChange(select);
  }
  return true;
}

function moveRange(input, key) {
  if (key === "Home") input.value = input.min;
  else if (key === "End") input.value = input.max;
  else if (key === "ArrowLeft" || key === "ArrowDown") input.stepDown();
  else if (key === "ArrowRight" || key === "ArrowUp") input.stepUp();
  else return false;
  dispatchControlChange(input);
  return true;
}

function moveNumber(input, key) {
  if (key === "ArrowDown") input.stepDown();
  else if (key === "ArrowUp") input.stepUp();
  else return false;
  dispatchControlChange(input);
  return true;
}

function dispatchControlChange(control) {
  control.dispatchEvent(new Event("input", { bubbles: true }));
  control.dispatchEvent(new Event("change", { bubbles: true }));
}
