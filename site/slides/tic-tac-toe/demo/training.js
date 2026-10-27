import { STAGE_PRESETS } from "./view.js";

function mulberry32(seed) {
  let state = seed | 0;
  return () => {
    state = (state + 0x6D2B79F5) | 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussian(rng) {
  return standardDeviation => {
    let u = 0;
    let v = 0;
    while (u === 0) u = rng();
    while (v === 0) v = rng();
    const magnitude = Math.sqrt(-2 * Math.log(u));
    const angle = 2 * Math.PI * v;
    return magnitude * Math.cos(angle) * standardDeviation;
  };
}

export function createInitialParameters({ IN = 27, H, OUT = 9, seed = 1 }) {
  if (!Number.isInteger(H) || H < 1) throw new RangeError("H must be a positive integer");
  if (!Number.isInteger(seed) || seed < 0) throw new RangeError("seed must be a non-negative integer");
  const randomGaussian = gaussian(mulberry32(seed >>> 0));
  const Wa = new Float32Array(IN * H);
  const Wb = new Float32Array(H * OUT);
  const firstLayerScale = Math.sqrt(2 / IN);
  const secondLayerScale = Math.sqrt(2 / H);
  for (let index = 0; index < Wa.length; index += 1) Wa[index] = randomGaussian(firstLayerScale);
  for (let index = 0; index < Wb.length; index += 1) Wb[index] = randomGaussian(secondLayerScale);
  return { H, Wa, ba: new Float32Array(H), Wb, bb: new Float32Array(OUT) };
}

export function createTrainingController({ pipeline, onChange = () => {} }) {
  let attached = false;
  let seed = 1;
  let generation = 0;
  let worker = null;
  let phase = "detached";
  let epoch = 0;
  let loss = null;
  let passing = null;
  let failed = null;
  let boardCount = null;
  let elapsed = 0;
  let frames = [];
  let initialParameters = null;
  let showWeightChanges = false;
  let w1WeightChangeScale = 0;
  let replayIndex = -1;
  let replayPlaying = false;
  let replaySpeed = 1;
  let replaySlowStart = true;
  let replayFrame = 0;
  let replayLastTime = 0;
  let replayAccumulator = 0;
  let failingBoards = [];
  const instant = new URLSearchParams(location.search).has("instant");

  function state() {
    return {
      attached,
      seed,
      generation,
      hiddenWidth: pipeline.model.params.H,
      phase,
      running: phase === "running" || phase === "stopping",
      epoch,
      loss,
      passing,
      failed,
      boardCount,
      elapsed,
      frameCount: frames.length,
      replayIndex,
      replayPlaying,
      replaySpeed,
      replaySlowStart,
      showWeightChanges,
      w1WeightChangeScale,
      replayAvailable: frames.length > 1,
      curve: frames.slice(0, Math.max(0, replayIndex + 1)).map(frame => ({ epoch: frame.epoch, passing: frame.passing })),
      failingBoards: failingBoards.map(example => ({
        board: [...example.board],
        prediction: example.prediction,
      })),
    };
  }

  function emit() {
    onChange(state());
  }

  function showParameters(snapshot, index = replayIndex) {
    const previous = index > 0 ? frames[index - 1]?.params : initialParameters;
    w1WeightChangeScale = 0;
    if (previous) {
      for (let valueIndex = 0; valueIndex < snapshot.Wa.length; valueIndex += 1) {
        w1WeightChangeScale = Math.max(
          w1WeightChangeScale,
          Math.abs(snapshot.Wa[valueIndex] - previous.Wa[valueIndex]),
        );
      }
    }
    pipeline.setParameters(snapshot, {
      comparison: showWeightChanges ? previous ?? snapshot : null,
    });
  }

  function initialize(nextSeed = seed) {
    pauseReplay();
    stop({ resetPhase: false });
    seed = Number(nextSeed);
    const { IN, H, OUT } = pipeline.model.params;
    const snapshot = createInitialParameters({ IN, H, OUT, seed });
    initialParameters = snapshot;
    generation += 1;
    phase = "initialized";
    epoch = 0;
    loss = null;
    passing = null;
    failed = null;
    boardCount = null;
    elapsed = 0;
    frames = [];
    replayIndex = -1;
    failingBoards = [];
    pipeline.setState(STAGE_PRESETS.rich);
    showParameters(snapshot, -1);
    emit();
    return snapshot;
  }

  function enter({ seed: nextSeed = 1 } = {}) {
    attached = true;
    pipeline.setBoardSelectionHandler(() => {});
    initialize(nextSeed);
  }

  function acceptMessage(message, runGeneration) {
    if (!attached || runGeneration !== generation || message.generation !== runGeneration) return;
    if (message.type === "meta") {
      boardCount = message.boards;
      emit();
      return;
    }
    if (message.type !== "progress" && message.type !== "done") return;
    epoch = message.epoch;
    loss = message.loss;
    failed = message.failed;
    passing = 100 - message.pct;
    elapsed = message.elapsed;
    failingBoards = (message.failingBoards ?? []).map(example => Array.isArray(example)
      ? { board: example, prediction: -1 }
      : example);
    if (message.params) {
      const frame = { epoch, loss, failed, passing, elapsed, params: message.params, failingBoards };
      if (frames.at(-1)?.epoch === epoch) frames[frames.length - 1] = frame;
      else frames.push(frame);
      replayIndex = frames.length - 1;
      showParameters(message.params);
    }
    if (message.type === "done") {
      phase = message.perfect ? "complete" : message.stopped ? "stopped" : "limit";
      worker?.terminate();
      worker = null;
    }
    emit();
  }

  function start({ maxEpochs = 30000, batchSize = 512, chunkMs = 30 } = {}) {
    if (!attached || worker) return;
    if (phase !== "initialized") initialize(seed);
    generation += 1;
    const runGeneration = generation;
    phase = "running";
    worker = new Worker(new URL("./training-worker.js", import.meta.url));
    worker.onmessage = event => acceptMessage(event.data, runGeneration);
    worker.onerror = error => {
      if (runGeneration !== generation) return;
      console.error(error);
      phase = "error";
      worker?.terminate();
      worker = null;
      emit();
    };
    worker.postMessage({ type: "start", config: { H: pipeline.model.params.H, seed, maxEpochs, batchSize, chunkMs, failingLimit: 9, generation: runGeneration } });
    emit();
  }

  function stop({ resetPhase = true } = {}) {
    if (!worker) return;
    generation += 1;
    worker.terminate();
    worker = null;
    if (resetPhase) phase = "stopped";
    emit();
  }

  function showReplayFrame(index, { notify = true } = {}) {
    if (!frames.length) return;
    replayIndex = Math.max(0, Math.min(frames.length - 1, Math.trunc(index)));
    const frame = frames[replayIndex];
    epoch = frame.epoch;
    loss = frame.loss;
    failed = frame.failed;
    passing = frame.passing;
    elapsed = frame.elapsed;
    failingBoards = frame.failingBoards ?? [];
    showParameters(frame.params);
    if (notify) emit();
  }

  function pauseReplay({ notify = true } = {}) {
    replayPlaying = false;
    if (replayFrame) cancelAnimationFrame(replayFrame);
    replayFrame = 0;
    if (notify && attached) emit();
  }

  function playReplay() {
    if (phase === "running" || phase === "stopping" || frames.length < 2) return;
    pauseReplay({ notify: false });
    if (replayIndex >= frames.length - 1 || replayIndex < 0) showReplayFrame(0, { notify: false });
    if (instant || document.hidden) {
      showReplayFrame(frames.length - 1);
      return;
    }
    replayPlaying = true;
    replayLastTime = performance.now();
    replayAccumulator = 0;
    emit();
    function tick(now) {
      if (!replayPlaying) return;
      const frame = frames[replayIndex];
      const localSpeed = replaySpeed * (replaySlowStart && frame.elapsed < 2000 ? .25 : 1);
      replayAccumulator += (now - replayLastTime) * localSpeed;
      replayLastTime = now;
      while (replayAccumulator >= 45 && replayIndex < frames.length - 1) {
        replayAccumulator -= 45;
        showReplayFrame(replayIndex + 1, { notify: false });
      }
      emit();
      if (replayIndex >= frames.length - 1) {
        pauseReplay();
        return;
      }
      replayFrame = requestAnimationFrame(tick);
    }
    replayFrame = requestAnimationFrame(tick);
  }

  function toggleReplay() {
    if (replayPlaying) pauseReplay();
    else playReplay();
  }

  function seekReplay(index) {
    pauseReplay({ notify: false });
    showReplayFrame(index);
  }

  function finishTransition() {
    if (!replayPlaying) return false;
    pauseReplay({ notify: false });
    showReplayFrame(frames.length - 1);
    return true;
  }

  function cancelTransition() {
    if (!replayPlaying) return false;
    pauseReplay();
    return true;
  }

  function setReplayOptions({ speed = replaySpeed, slowStart = replaySlowStart } = {}) {
    replaySpeed = Number(speed);
    replaySlowStart = Boolean(slowStart);
    emit();
  }

  function setShowWeightChanges(nextShowWeightChanges) {
    showWeightChanges = Boolean(nextShowWeightChanges);
    const frame = frames[replayIndex];
    showParameters(frame?.params ?? initialParameters);
    emit();
  }

  function settle() {
    if (attached) emit();
  }

  function detach({ restoreModel = true } = {}) {
    pauseReplay({ notify: false });
    stop({ resetPhase: false });
    generation += 1;
    pipeline.setBoardSelectionHandler(null);
    if (restoreModel) pipeline.restoreModelParameters();
    attached = false;
    phase = "detached";
  }

  return {
    enter,
    initialize,
    reset: initialize,
    start,
    stop,
    toggleReplay,
    playReplay,
    pauseReplay,
    seekReplay,
    finishTransition,
    cancelTransition,
    finish: finishTransition,
    cancel: cancelTransition,
    setReplayOptions,
    setShowWeightChanges,
    settle,
    detach,
    getState: state,
  };
}
