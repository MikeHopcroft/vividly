import { boardsEqual, gameStatus, legalMoves, playerToMove } from "./game.js";
import { createExplanationFx } from "./explain-fx.js";
import { EXPRESSION_PARTS, STAGE_PRESETS } from "./view.js";

function expressionState(activePart = null) {
  const activeIndex = EXPRESSION_PARTS.indexOf(activePart);
  return Object.fromEntries(EXPRESSION_PARTS.map((part, index) => [
    part,
    activeIndex < 0 || index < activeIndex ? "normal" : index === activeIndex ? "active" : "muted",
  ]));
}

function stageState(preset, activePart = null) {
  return {
    visible: { ...preset.visible },
    representation: { ...preset.representation },
    values: { ...preset.values },
    expression: expressionState(activePart),
  };
}

function maximumAbsolute(values) {
  let maximum = 0;
  for (const value of values) maximum = Math.max(maximum, Math.abs(value));
  return maximum;
}

function deterministicDelay(index, range) {
  return ((index * 47 + 23) % 101) / 100 * range;
}

export function createInferenceController({ pipeline, viewport, onChange = () => {} }) {
  let history = [pipeline.getBoard()];
  let animateChanges = true;
  let animating = false;
  let attached = false;
  let generation = 0;
  let sweepFrame = 0;
  let sweepResolve = null;
  const fx = createExplanationFx(viewport);
  const instant = new URLSearchParams(location.search).has("instant");

  function board() {
    return [...history[history.length - 1]];
  }

  function computationState() {
    const currentBoard = board();
    const computation = pipeline.getComputation();
    const legal = legalMoves(currentBoard);
    return {
      board: currentBoard,
      history: history.map(entry => [...entry]),
      historyLength: history.length,
      canUndo: history.length > 1,
      status: gameStatus(currentBoard),
      legalCount: legal.length,
      move: legal.includes(computation.move) ? computation.move : -1,
      hiddenWidth: pipeline.model.params.H,
      animateChanges,
      animating,
    };
  }

  function emit() {
    onChange(computationState());
  }

  function cancelAnimation() {
    generation += 1;
    fx.cancel();
    if (sweepFrame) cancelAnimationFrame(sweepFrame);
    sweepFrame = 0;
    if (sweepResolve) sweepResolve(false);
    sweepResolve = null;
    animating = false;
    return generation;
  }

  function sweep(milliseconds, activeGeneration, onProgress) {
    return new Promise(resolve => {
      sweepResolve = resolve;
      const started = performance.now();
      function frame(now) {
        if (activeGeneration !== generation) {
          sweepResolve = null;
          resolve(false);
          return;
        }
        const progress = Math.min(1, (now - started) / milliseconds);
        onProgress(progress);
        if (progress < 1) sweepFrame = requestAnimationFrame(frame);
        else {
          sweepFrame = 0;
          sweepResolve = null;
          resolve(true);
        }
      }
      sweepFrame = requestAnimationFrame(frame);
    });
  }

  function renderStatic() {
    pipeline.setBoard(board());
    pipeline.clearExplanationState();
    pipeline.setState(stageState(STAGE_PRESETS.complete));
    animating = false;
    emit();
  }

  function phaseState({ hidden, logits, move = -1, showOutput = false, activePart }) {
    const computation = pipeline.getComputation();
    const inactiveRows = [];
    const inactiveColumns = [];
    for (let index = 0; index < computation.input.length; index += 1) {
      if (!computation.input[index]) inactiveRows.push(index);
    }
    for (let index = 0; index < computation.hidden.length; index += 1) {
      if (computation.hidden[index] <= 0) inactiveColumns.push(index);
    }
    pipeline.setState(stageState(STAGE_PRESETS.rich, activePart));
    pipeline.setExplanationState({
      hidden,
      logits,
      move,
      showOutput,
      w1: { mutedRows: inactiveRows },
      w2: { mutedColumns: inactiveColumns },
    });
  }

  function layerOneParticles(computation, accumulator, activeGeneration) {
    const { Wa, ba, H } = pipeline.model.params;
    const activeRows = [];
    computation.input.forEach((value, index) => { if (value) activeRows.push(index); });
    const scale = Math.max(maximumAbsolute(Wa), maximumAbsolute(ba));
    const radius = fx.cellRadius(pipeline.elements.w1);
    const started = performance.now() + 40;
    const particles = [];
    for (let hidden = 0; hidden < H; hidden += 1) {
      const target = fx.center(pipeline.elements.h, 0, hidden);
      const delay = deterministicDelay(hidden, 90);
      activeRows.forEach((row, order) => {
        const value = Wa[row * H + hidden];
        particles.push({
          source: fx.center(pipeline.elements.w1, row, hidden), target, value, scale, radius,
          start: started + delay + order * 40, duration: 520,
          onLand: () => { if (activeGeneration === generation) accumulator[hidden] += value; },
        });
      });
      const bias = ba[hidden];
      particles.push({
        source: fx.center(pipeline.elements.b1, 0, hidden), target, value: bias, scale, radius,
        start: started + delay + activeRows.length * 40, duration: 520,
        onLand: () => { if (activeGeneration === generation) accumulator[hidden] += bias; },
      });
    }
    return particles;
  }

  function layerTwoParticles(computation, accumulator, activeGeneration) {
    const { Wb, bb, H, OUT } = pipeline.model.params;
    const activeHidden = [];
    computation.hidden.forEach((value, index) => { if (value > 0) activeHidden.push(index); });
    let scale = maximumAbsolute(bb);
    for (let output = 0; output < OUT; output += 1) {
      for (const hidden of activeHidden) scale = Math.max(scale, Math.abs(computation.hidden[hidden] * Wb[hidden * OUT + output]));
    }
    const radius = fx.cellRadius(pipeline.elements.w2);
    const started = performance.now() + 40;
    const particles = [];
    for (let output = 0; output < OUT; output += 1) {
      const target = fx.center(pipeline.elements.logits, output, 0);
      const delay = deterministicDelay(output, 80);
      activeHidden.forEach((hidden, order) => {
        const value = computation.hidden[hidden] * Wb[hidden * OUT + output];
        particles.push({
          source: fx.center(pipeline.elements.w2, output, hidden), target, value, scale, radius,
          start: started + delay + order * 24, duration: 560,
          onLand: () => { if (activeGeneration === generation) accumulator[output] += value; },
        });
      });
      const bias = bb[output];
      particles.push({
        source: fx.center(pipeline.elements.b2, output, 0), target, value: bias, scale, radius,
        start: started + delay + activeHidden.length * 24, duration: 560,
        onLand: () => { if (activeGeneration === generation) accumulator[output] += bias; },
      });
    }
    return particles;
  }

  async function runFlow() {
    if (!attached) return;
    const activeGeneration = cancelAnimation();
    const computation = pipeline.getComputation();
    if (instant || document.hidden) {
      renderStatic();
      return;
    }
    animating = true;
    phaseState({
      hidden: new Float32Array(computation.hidden.length),
      logits: new Float32Array(computation.logits.length),
      activePart: "hidden",
    });
    emit();
    const hiddenAccumulator = new Float32Array(computation.hidden.length);
    const completedLayerOne = await fx.launch(
      layerOneParticles(computation, hiddenAccumulator, activeGeneration),
      () => pipeline.patchExplanationState({ hidden: hiddenAccumulator }),
    );
    if (!completedLayerOne || activeGeneration !== generation) return;
    phaseState({
      hidden: hiddenAccumulator,
      logits: new Float32Array(computation.logits.length),
      activePart: "activation",
    });
    const reluValues = new Float32Array(computation.hidden.length);
    if (!await sweep(600, activeGeneration, progress => {
      const count = Math.min(computation.hidden.length, Math.ceil(progress * computation.hidden.length));
      reluValues.set(computation.hidden.subarray(0, count), 0);
      pipeline.patchExplanationState({ hidden: reluValues });
    })) return;
    phaseState({ hidden: reluValues, logits: new Float32Array(computation.logits.length), activePart: "output" });
    const logitAccumulator = new Float32Array(computation.logits.length);
    const completedLayerTwo = await fx.launch(
      layerTwoParticles(computation, logitAccumulator, activeGeneration),
      () => pipeline.patchExplanationState({ logits: logitAccumulator }),
    );
    if (!completedLayerTwo || activeGeneration !== generation) return;
    phaseState({
      hidden: Float32Array.from(computation.hidden),
      logits: logitAccumulator,
      move: computation.move,
      showOutput: true,
      activePart: "decision",
    });
    if (!await sweep(320, activeGeneration, () => {})) return;
    renderStatic();
  }

  function commit(nextBoard, animate = animateChanges) {
    cancelAnimation();
    history.push([...nextBoard]);
    pipeline.setBoard(nextBoard);
    if (animate) runFlow();
    else renderStatic();
  }

  function selectCell(index) {
    const next = board();
    if (next[index]) {
      next[index] = 0;
      commit(next);
      return;
    }
    if (!legalMoves(next).includes(index)) return;
    next[index] = playerToMove(next);
    commit(next);
  }

  function enter({ board: entryBoard = pipeline.getBoard(), history: entryHistory = null } = {}) {
    cancelAnimation();
    const nextBoard = [...entryBoard];
    history = entryHistory?.length ? entryHistory.map(entry => [...entry]) : [nextBoard];
    if (!boardsEqual(history[history.length - 1], nextBoard)) history.push(nextBoard);
    attached = true;
    pipeline.setBoardSelectionHandler(selectCell);
    emit();
  }

  function undo() {
    if (history.length <= 1) return;
    cancelAnimation();
    history.pop();
    renderStatic();
  }

  function clear() {
    cancelAnimation();
    history = [new Array(9).fill(0)];
    renderStatic();
  }

  function playSuggested() {
    const state = computationState();
    if (state.move < 0) return;
    const next = state.board;
    next[state.move] = playerToMove(next);
    commit(next);
  }

  function setAnimateChanges(enabled) {
    animateChanges = Boolean(enabled);
    emit();
  }

  function settle() {
    cancelAnimation();
    renderStatic();
  }

  function finishTransition() {
    if (!animating) return false;
    settle();
    return true;
  }

  function cancelTransition() {
    if (!animating) return false;
    cancelAnimation();
    renderStatic();
    return true;
  }

  function handleVisibilityChange() {
    if (document.hidden && animating) settle();
  }

  document.addEventListener("visibilitychange", handleVisibilityChange);

  function detach() {
    cancelAnimation();
    pipeline.setBoardSelectionHandler(null);
    pipeline.clearExplanationState();
    attached = false;
    fx.destroy();
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  }

  return {
    enter,
    undo,
    clear,
    playSuggested,
    runFlow,
    setAnimateChanges,
    settle,
    finishTransition,
    cancelTransition,
    finish: finishTransition,
    cancel: cancelTransition,
    detach,
    getState: computationState,
  };
}
