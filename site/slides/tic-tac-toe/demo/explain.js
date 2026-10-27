import { EXPRESSION_PARTS, STAGE_PRESETS } from "./view.js";
import { createExplanationFx } from "./explain-fx.js";

export const EXPLAIN_BEATS = [
  {
    id: "ready",
    caption: "The trained network is ready for one forward pass. The hidden values, logits, argmax, and output begin empty.",
  },
  {
    id: "select-w1",
    caption: "x is one-hot: its nine active entries select nine rows of W₁. The other eighteen rows do not contribute.",
  },
  {
    id: "hidden-0",
    caption: "Hidden unit 0 adds its nine selected weights and bias into the first accumulator.",
  },
  {
    id: "hidden-1",
    caption: "Hidden unit 1 repeats the same selected-weight sum in the next accumulator.",
  },
  {
    id: "hidden-rest",
    caption: "The remaining hidden units compute the same kind of sum in parallel.",
  },
  {
    id: "relu",
    caption: "ReLU clips every negative hidden sum to zero and leaves positive sums unchanged.",
  },
  {
    id: "select-w2",
    caption: "Hidden values clipped to zero contribute nothing through W₂; only active hidden units remain.",
  },
  {
    id: "logit-0",
    caption: "Output 0 takes a dot product of the hidden values and its weights, then adds its bias.",
  },
  {
    id: "logit-1",
    caption: "Output 1 repeats the dot product to produce the next candidate-move score.",
  },
  {
    id: "logits-rest",
    caption: "The remaining outputs produce one logit for each board position.",
  },
  {
    id: "argmax",
    caption: "Legal argmax selects the highest-scoring empty square and returns that move to the board.",
  },
];

const EXPRESSION_ORDER = ["hidden", "activation", "output", "decision"];

function clonePreset(preset) {
  return {
    visible: { ...preset.visible },
    representation: { ...preset.representation },
    values: { ...preset.values },
    expression: { ...preset.expression },
  };
}

function prefix(values, count) {
  const result = new Float32Array(values.length);
  result.set(values.subarray(0, count));
  return result;
}

function expressionState(activePart) {
  if (!activePart) return Object.fromEntries(EXPRESSION_PARTS.map(part => [part, "normal"]));
  const activeIndex = EXPRESSION_ORDER.indexOf(activePart);
  return Object.fromEntries(EXPRESSION_ORDER.map((part, index) => [
    part,
    index < activeIndex ? "normal" : index === activeIndex ? "active" : "muted",
  ]));
}

function activeExpressionPart(beat) {
  if (beat >= 1 && beat <= 4) return "hidden";
  if (beat === 5) return "activation";
  if (beat >= 6 && beat <= 9) return "output";
  if (beat === 10) return "decision";
  return null;
}

export function createExplainController({ pipeline, viewport, onChange = () => {} }) {
  let currentBeat = 0;
  let settledBeat = 0;
  let attached = true;
  let animating = false;
  let animationDirection = 0;
  let animationGeneration = 0;
  let sweepFrame = 0;
  let sweepResolve = null;
  const fx = createExplanationFx(viewport);
  const instant = new URLSearchParams(location.search).has("instant");

  function duration(milliseconds) {
    return instant ? 1 : milliseconds;
  }

  function buildBeatState(beat) {
    const computation = pipeline.getComputation();
    const { input, preactivation, hidden, logits, move } = computation;
    const inactiveInputRows = [];
    const inactiveHiddenColumns = [];
    for (let index = 0; index < input.length; index += 1) {
      if (!input[index]) inactiveInputRows.push(index);
    }
    for (let index = 0; index < hidden.length; index += 1) {
      if (hidden[index] <= 0) inactiveHiddenColumns.push(index);
    }

    const presentation = {
      hidden: new Float32Array(hidden.length),
      logits: new Float32Array(logits.length),
      move: -1,
      showOutput: false,
      w1: {},
      w2: {},
    };

    if (beat >= 1) presentation.w1.mutedRows = inactiveInputRows;
    if (beat === 2) {
      presentation.hidden = prefix(preactivation, 1);
      presentation.w1.spotlightColumns = [0];
    } else if (beat === 3) {
      presentation.hidden = prefix(preactivation, 2);
      presentation.w1.spotlightColumns = [1];
    } else if (beat === 4) {
      presentation.hidden = Float32Array.from(preactivation);
    } else if (beat >= 5) {
      presentation.hidden = Float32Array.from(hidden);
    }

    if (beat >= 6) presentation.w2.mutedColumns = inactiveHiddenColumns;
    if (beat === 7) {
      presentation.logits = prefix(logits, 1);
      presentation.w2.spotlightRows = [0];
    } else if (beat === 8) {
      presentation.logits = prefix(logits, 2);
      presentation.w2.spotlightRows = [1];
    } else if (beat >= 9) {
      presentation.logits = Float32Array.from(logits);
    }

    if (beat >= 10) {
      presentation.move = move;
      presentation.showOutput = true;
    }
    return presentation;
  }

  function setStage(beat, presentation = buildBeatState(beat)) {
    if (!attached) return;
    currentBeat = Math.max(0, Math.min(EXPLAIN_BEATS.length - 1, Number(beat) || 0));
    const stageState = clonePreset(STAGE_PRESETS.rich);
    stageState.expression = expressionState(activeExpressionPart(currentBeat));
    pipeline.setState(stageState);
    pipeline.setExplanationState(presentation);
  }

  function applyBeat(beat) {
    if (!attached) return;
    setStage(beat);
    settledBeat = currentBeat;
    animating = false;
    animationDirection = 0;
    onChange(getState());
  }

  function finishTransition() {
    if (!animating) return false;
    const targetBeat = currentBeat;
    cancelAnimation();
    applyBeat(targetBeat);
    return true;
  }

  function cancelTransition() {
    if (!animating) return false;
    cancelAnimation();
    applyBeat(settledBeat);
    return true;
  }

  function cancelAnimation() {
    animationGeneration += 1;
    fx.cancel();
    if (sweepFrame) cancelAnimationFrame(sweepFrame);
    sweepFrame = 0;
    if (sweepResolve) sweepResolve(false);
    sweepResolve = null;
    animating = false;
    animationDirection = 0;
    return animationGeneration;
  }

  function sweep(milliseconds, update, generation) {
    return new Promise(resolve => {
      sweepResolve = resolve;
      const started = performance.now();
      function frame(now) {
        if (generation !== animationGeneration) {
          sweepResolve = null;
          resolve(false);
          return;
        }
        const progress = Math.min(1, (now - started) / duration(milliseconds));
        update(progress);
        if (progress < 1) {
          sweepFrame = requestAnimationFrame(frame);
        } else {
          sweepFrame = 0;
          sweepResolve = null;
          resolve(true);
        }
      }
      sweepFrame = requestAnimationFrame(frame);
    });
  }

  function unitParticles(units, accumulator) {
    const { input } = pipeline.getComputation();
    const { H, Wa, ba } = pipeline.model.params;
    const activeRows = [];
    for (let row = 0; row < input.length; row += 1) if (input[row]) activeRows.push(row);
    const particles = [];
    const base = performance.now();
    const single = units.length === 1;
    const startDelay = single ? 120 : 40;
    const stagger = single ? 70 : 52;
    const flight = duration(single ? 620 : 560);
    const radius = fx.cellRadius(pipeline.elements.w1);

    for (const unit of units) {
      const unitDelay = single ? 0 : (unit * 37) % 91;
      const target = fx.center(pipeline.elements.h, 0, unit);
      activeRows.forEach((row, index) => {
        const value = Wa[row * H + unit];
        particles.push({
          source: fx.center(pipeline.elements.w1, row, unit),
          target,
          value,
          scale: 2,
          radius,
          start: base + duration(startDelay + unitDelay + index * stagger),
          duration: flight,
          onLand: () => { accumulator[unit] += value; },
        });
      });
      const bias = ba[unit];
      particles.push({
        source: fx.center(pipeline.elements.b1, 0, unit),
        target,
        value: bias,
        scale: 2,
        radius,
        start: base + duration(startDelay + unitDelay + activeRows.length * stagger),
        duration: flight,
        onLand: () => { accumulator[unit] += bias; },
      });
    }
    return particles;
  }

  function outputParticles(outputs, accumulator) {
    const { hidden } = pipeline.getComputation();
    const { H, OUT, Wb, bb } = pipeline.model.params;
    const activeUnits = [];
    let productScale = 1e-6;
    for (let unit = 0; unit < H; unit += 1) {
      if (Math.abs(hidden[unit]) < 1e-4) continue;
      activeUnits.push(unit);
      for (let output = 0; output < OUT; output += 1) {
        productScale = Math.max(productScale, Math.abs(hidden[unit] * Wb[unit * OUT + output]));
      }
    }

    const particles = [];
    const base = performance.now();
    const single = outputs.length === 1;
    const startDelay = single ? 120 : 40;
    const stagger = single ? 45 : 28;
    const flight = duration(single ? 640 : 600);
    const radius = fx.cellRadius(pipeline.elements.w2);

    for (const output of outputs) {
      const outputDelay = single ? 0 : (output * 43) % 81;
      const target = fx.center(pipeline.elements.logits, output, 0);
      activeUnits.forEach((unit, index) => {
        const value = hidden[unit] * Wb[unit * OUT + output];
        particles.push({
          source: fx.center(pipeline.elements.w2, output, unit),
          target,
          value,
          scale: productScale,
          linear: true,
          radius,
          start: base + duration(startDelay + outputDelay + index * stagger),
          duration: flight,
          onLand: () => { accumulator[output] += value; },
        });
      });
      const bias = bb[output];
      particles.push({
        source: fx.center(pipeline.elements.b2, output, 0),
        target,
        value: bias,
        scale: productScale,
        linear: true,
        radius,
        start: base + duration(startDelay + outputDelay + activeUnits.length * stagger),
        duration: flight,
        onLand: () => { accumulator[output] += bias; },
      });
    }
    return particles;
  }

  async function animateMaskW1(generation) {
    const target = buildBeatState(1);
    const deadRows = target.w1.mutedRows;
    target.w1.mutedRows = [];
    setStage(1, target);
    animating = true;
    onChange(getState());
    let shown = 0;
    const completed = await sweep(650 * 27 / pipeline.model.params.H, progress => {
      const scannedRows = Math.min(27, Math.floor(progress * 27) + 1);
      while (shown < deadRows.length && deadRows[shown] < scannedRows) shown += 1;
      pipeline.patchExplanationState({ w1: { mutedRows: deadRows.slice(0, shown) } });
    }, generation);
    if (completed && generation === animationGeneration) applyBeat(1);
  }

  async function animateHiddenUnits(beat, units, generation) {
    const target = buildBeatState(beat);
    const previous = buildBeatState(beat - 1);
    const accumulator = Float32Array.from(previous.hidden);
    target.hidden = accumulator;
    setStage(beat, target);
    animating = true;
    onChange(getState());
    const completed = await fx.launch(unitParticles(units, accumulator), () => {
      if (generation === animationGeneration) {
        pipeline.patchExplanationState({ hidden: Float32Array.from(accumulator) });
      }
    });
    if (completed && generation === animationGeneration) applyBeat(beat);
  }

  async function animateRelu(generation) {
    const { H } = pipeline.model.params;
    const { preactivation, hidden } = pipeline.getComputation();
    const presentation = buildBeatState(5);
    const displayed = Float32Array.from(preactivation);
    presentation.hidden = displayed;
    setStage(5, presentation);
    animating = true;
    onChange(getState());
    let changed = 0;
    const completed = await sweep(650, progress => {
      const target = Math.min(H, Math.floor(progress * H) + 1);
      while (changed < target) {
        displayed[changed] = hidden[changed];
        changed += 1;
      }
      pipeline.patchExplanationState({ hidden: Float32Array.from(displayed) });
    }, generation);
    if (completed && generation === animationGeneration) applyBeat(5);
  }

  async function animateMaskW2(generation) {
    const { H } = pipeline.model.params;
    const target = buildBeatState(6);
    const deadColumns = target.w2.mutedColumns;
    target.w2.mutedColumns = [];
    setStage(6, target);
    animating = true;
    onChange(getState());
    let shown = 0;
    const completed = await sweep(650, progress => {
      const scannedColumns = Math.min(H, Math.floor(progress * H) + 1);
      while (shown < deadColumns.length && deadColumns[shown] < scannedColumns) shown += 1;
      pipeline.patchExplanationState({ w2: { mutedColumns: deadColumns.slice(0, shown) } });
    }, generation);
    if (completed && generation === animationGeneration) applyBeat(6);
  }

  async function animateOutputs(beat, outputs, generation) {
    const target = buildBeatState(beat);
    const previous = buildBeatState(beat - 1);
    const accumulator = Float32Array.from(previous.logits);
    target.logits = accumulator;
    setStage(beat, target);
    animating = true;
    onChange(getState());
    const completed = await fx.launch(outputParticles(outputs, accumulator), () => {
      if (generation === animationGeneration) {
        pipeline.patchExplanationState({ logits: Float32Array.from(accumulator) });
      }
    });
    if (completed && generation === animationGeneration) applyBeat(beat);
  }

  function playBeat(beat) {
    if (!attached || animating) return;
    const target = Math.max(0, Math.min(EXPLAIN_BEATS.length - 1, beat));
    if (document.hidden || target < 1 || target > 9) {
      applyBeat(target);
      return;
    }
    const generation = cancelAnimation();
    animationDirection = 1;
    if (target === 1) animateMaskW1(generation);
    else if (target === 2) animateHiddenUnits(2, [0], generation);
    else if (target === 3) animateHiddenUnits(3, [1], generation);
    else if (target === 4) {
      const units = Array.from({ length: pipeline.model.params.H - 2 }, (_, index) => index + 2);
      animateHiddenUnits(4, units, generation);
    } else if (target === 5) animateRelu(generation);
    else if (target === 6) animateMaskW2(generation);
    else if (target === 7) animateOutputs(7, [0], generation);
    else if (target === 8) animateOutputs(8, [1], generation);
    else {
      const outputs = Array.from({ length: pipeline.model.params.OUT - 2 }, (_, index) => index + 2);
      animateOutputs(9, outputs, generation);
    }
  }

  async function reverseMaskW1(generation) {
    const deadRows = buildBeatState(1).w1.mutedRows;
    currentBeat = 0;
    animating = true;
    onChange(getState());
    const completed = await sweep(650 * 27 / pipeline.model.params.H, progress => {
      const cutoff = Math.floor((1 - progress) * 27);
      pipeline.patchExplanationState({ w1: { mutedRows: deadRows.filter(row => row < cutoff) } });
    }, generation);
    if (completed && generation === animationGeneration) applyBeat(0);
  }

  async function reverseRelu(generation) {
    const { H } = pipeline.model.params;
    const { preactivation, hidden } = pipeline.getComputation();
    const displayed = Float32Array.from(hidden);
    currentBeat = 4;
    animating = true;
    onChange(getState());
    let changed = 0;
    const completed = await sweep(650, progress => {
      const target = Math.min(H, Math.floor(progress * H) + 1);
      while (changed < target) {
        const unit = H - 1 - changed;
        displayed[unit] = preactivation[unit];
        changed += 1;
      }
      pipeline.patchExplanationState({ hidden: Float32Array.from(displayed) });
    }, generation);
    if (completed && generation === animationGeneration) applyBeat(4);
  }

  async function reverseMaskW2(generation) {
    const { H } = pipeline.model.params;
    const deadColumns = buildBeatState(6).w2.mutedColumns;
    currentBeat = 5;
    animating = true;
    onChange(getState());
    const completed = await sweep(650, progress => {
      const cutoff = Math.floor((1 - progress) * H);
      pipeline.patchExplanationState({ w2: { mutedColumns: deadColumns.filter(column => column < cutoff) } });
    }, generation);
    if (completed && generation === animationGeneration) applyBeat(5);
  }

  function handleVisibilityChange() {
    if (document.hidden && animating) {
      cancelAnimation();
      applyBeat(currentBeat);
    }
  }

  document.addEventListener("visibilitychange", handleVisibilityChange);

  function getState() {
    return {
      beat: currentBeat,
      beatCount: EXPLAIN_BEATS.length,
      beatInfo: EXPLAIN_BEATS[currentBeat],
      canPrevious: currentBeat > 0,
      canNext: currentBeat < EXPLAIN_BEATS.length - 1,
      animating,
      animationDirection,
    };
  }

  return {
    load({ board } = {}) {
      cancelAnimation();
      if (board) pipeline.setBoard(board);
      applyBeat(currentBeat);
    },
    enter({ beat = 0 } = {}) {
      attached = true;
      cancelAnimation();
      applyBeat(beat);
    },
    next() {
      if (!animating && currentBeat < EXPLAIN_BEATS.length - 1) playBeat(currentBeat + 1);
    },
    previous() {
      if (animating || currentBeat <= 0) return;
      if (document.hidden) {
        applyBeat(currentBeat - 1);
        return;
      }
      const generation = cancelAnimation();
      animationDirection = -1;
      if (currentBeat === 1) reverseMaskW1(generation);
      else if (currentBeat === 5) reverseRelu(generation);
      else if (currentBeat === 6) reverseMaskW2(generation);
      else applyBeat(currentBeat - 1);
    },
    replay() {
      if (!animating) currentBeat === 0 ? applyBeat(0) : playBeat(currentBeat);
    },
    settle() {
      if (animating) return finishTransition();
      applyBeat(currentBeat);
      return false;
    },
    finishTransition,
    cancelTransition,
    finish: finishTransition,
    cancel: cancelTransition,
    detach({ preserveState = false } = {}) {
      cancelAnimation();
      if (!preserveState) pipeline.clearExplanationState();
      fx.destroy();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      attached = false;
    },
    getState,
  };
}
