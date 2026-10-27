import { StageCamera } from "./camera.js";
import { createCalloutOverlay } from "./callouts.js";
import { createPresentationDirector } from "./director.js";
import { createExplainController, EXPLAIN_BEATS } from "./explain.js";
import { createInferenceController } from "./inference.js";
import { loadCatalog } from "./model.js";
import { createTrainingController } from "./training.js";
import { createPipelineStage, STAGE_PRESETS } from "./view.js";

export const TIC_TAC_TOE_DEMO_STEPS = 21;
const DEMO_MODES = new Set(["presentation", "inference", "training"]);

export function createTicTacToeDemo() {
  let registry = null;
  let template = null;
  let mountedDemo = null;
  let pendingStep = 0;
  let pendingMode = "presentation";
  let disposed = false;

  function assertActive() {
    if (disposed) throw new Error("Demo has been disposed");
  }

  function unmount() {
    if (!mountedDemo) return;
    pendingStep = mountedDemo.step;
    pendingMode = presentationMode(mountedDemo.mode);
    mountedDemo.unmount();
    mountedDemo = null;
  }

  return Object.freeze({
    async preload() {
      assertActive();
      if (!registry) {
        const [loadedRegistry, response] = await Promise.all([
          loadCatalog(new URL("./models/catalog.json", import.meta.url)),
          fetch(new URL("./template.html", import.meta.url)),
        ]);
        if (!response.ok) {
          throw new Error(`Failed to load demo template: ${response.status} ${response.statusText}`);
        }
        registry = loadedRegistry;
        template = await response.text();
      }
      return { steps: TIC_TAC_TOE_DEMO_STEPS };
    },
    mount(root) {
      assertActive();
      if (!registry) throw new Error("Demo must be preloaded before mounting");
      if (mountedDemo) throw new Error("Demo is already mounted");
      if (!(root instanceof HTMLElement)) throw new TypeError("Demo root must be an HTML element");
      root.innerHTML = template;
      mountedDemo = mountTicTacToeDemo(root, registry);
    },
    enter({ step = pendingStep, mode = pendingMode } = {}) {
      assertActive();
      if (!mountedDemo) throw new Error("Demo must be mounted before entering");
      pendingMode = normalizeMode(mode);
      mountedDemo.enter();
      if (pendingMode === "presentation") {
        pendingStep = normalizeStep(step);
        mountedDemo.setStep(pendingStep, { animate: false });
      } else {
        mountedDemo.setMode(pendingMode);
      }
    },
    setStep(step, options) {
      assertActive();
      pendingMode = "presentation";
      pendingStep = normalizeStep(step);
      return mountedDemo?.setStep(pendingStep, options) ?? false;
    },
    setMode(mode) {
      assertActive();
      pendingMode = normalizeMode(mode);
      return mountedDemo?.setMode(pendingMode) ?? false;
    },
    settleStep() {
      assertActive();
      return mountedDemo?.settleStep() ?? false;
    },
    exit() {
      if (!mountedDemo) return;
      mountedDemo.exit();
    },
    navigate(direction) {
      assertActive();
      return mountedDemo?.navigate(direction) ?? false;
    },
    replayStep() {
      assertActive();
      return mountedDemo?.replayStep() ?? false;
    },
    unmount,
    dispose() {
      if (disposed) return;
      unmount();
      registry = null;
      template = null;
      disposed = true;
    },
    get root() {
      return mountedDemo?.root ?? null;
    },
    get director() {
      return mountedDemo?.director ?? null;
    },
    get explain() {
      return mountedDemo?.explain ?? null;
    },
    get step() {
      return mountedDemo?.step ?? pendingStep;
    },
    get mode() {
      return mountedDemo?.mode ?? pendingMode;
    },
  });
}

function normalizeStep(step) {
  const value = Number(step);
  if (!Number.isInteger(value) || value < 0 || value >= TIC_TAC_TOE_DEMO_STEPS) {
    throw new RangeError(`Demo step must be an integer from 0 to ${TIC_TAC_TOE_DEMO_STEPS - 1}`);
  }
  return value;
}

function normalizeMode(mode) {
  if (!DEMO_MODES.has(mode)) {
    throw new RangeError(`Demo mode must be one of: ${[...DEMO_MODES].join(", ")}`);
  }
  return mode;
}

function presentationMode(mode) {
  return mode === "inference" || mode === "training" ? mode : "presentation";
}

function mountTicTacToeDemo(root, registry) {
if (!(root instanceof HTMLElement)) throw new TypeError("Demo root must be an HTML element");

const INITIAL_BOARD = [1, 0, 2, 0, 1, 0, 2, 0, 0];
const title = root.querySelector("h1");
const status = root.querySelector("#status");
const modelSelector = root.querySelector("#model-selector");
const beatSelector = root.querySelector("#beat-selector");
const stepPicker = root.querySelector(".step-picker");
const stageHost = root.querySelector("#stage-host");
const workspace = root.querySelector(".workspace");
const viewport = root.querySelector("#viewport");
const cameraElement = root.querySelector("#camera");
const beatNumber = root.querySelector("#beat-number");
const caption = root.querySelector("#beat-caption");
const previousButton = root.querySelector("#previous-beat");
const replayButton = root.querySelector("#replay-beat");
const settleButton = root.querySelector("#settle-beat");
const nextButton = root.querySelector("#next-beat");
const summaryButton = root.querySelector("#toggle-summary");
const enterInferenceButton = root.querySelector("#enter-inference");
const technicalControls = root.querySelector(".technical-controls");
const technicalTitle = root.querySelector("#technical-title");
const technicalNumber = root.querySelector("#technical-number");
const technicalCaption = root.querySelector("#technical-caption");
const previousTechnicalButton = root.querySelector("#previous-technical");
const nextTechnicalButton = root.querySelector("#next-technical");
const explainerControls = root.querySelector(".explainer-controls");
const inferenceControls = root.querySelector(".inference-controls");
const inferenceStatus = root.querySelector("#inference-status");
const inferenceMove = root.querySelector("#inference-move");
const inferenceLegal = root.querySelector("#inference-legal");
const inferenceWidth = root.querySelector("#inference-width");
const playSuggestedButton = root.querySelector("#play-suggested");
const runInferenceButton = root.querySelector("#run-inference");
const undoInferenceButton = root.querySelector("#undo-inference");
const clearInferenceButton = root.querySelector("#clear-inference");
const animateInferenceInput = root.querySelector("#animate-inference");
const leaveInferenceButton = root.querySelector("#leave-inference");
const enterTrainingButton = root.querySelector("#enter-training");
const trainingControls = root.querySelector(".training-controls");
const trainingStatus = root.querySelector(".training-status");
const trainingWidthSelector = root.querySelector("#training-width-selector");
const trainingSeed = root.querySelector("#training-seed");
const resetTrainingButton = root.querySelector("#reset-training");
const trainingEpochs = root.querySelector("#training-epochs");
const startTrainingButton = root.querySelector("#start-training");
const stopTrainingButton = root.querySelector("#stop-training");
const trainingWidth = root.querySelector("#training-width");
const trainingEpoch = root.querySelector("#training-epoch");
const trainingLoss = root.querySelector("#training-loss");
const trainingPassing = root.querySelector("#training-passing");
const trainingFailures = root.querySelector("#training-failures");
const trainingElapsed = root.querySelector("#training-elapsed");
const trainingFrames = root.querySelector("#training-frames");
const trainingCurve = root.querySelector("#training-curve");
const trainingCurveLabel = root.querySelector("#training-curve-label");
const trainingFailuresCard = root.querySelector("#training-failures-card");
const trainingFailingLabel = root.querySelector("#training-failing-label");
const trainingFailingBoards = root.querySelector("#training-failing-boards");
const trainingReplay = root.querySelector("#training-replay");
const trainingFramePosition = root.querySelector("#training-frame-position");
const trainingTimeline = root.querySelector("#training-timeline");
const toggleTrainingReplayButton = root.querySelector("#toggle-training-replay");
const finishTrainingReplayButton = root.querySelector("#finish-training-replay");
const trainingReplaySpeed = root.querySelector("#training-replay-speed");
const trainingSlowStart = root.querySelector("#training-slow-start");
const trainingWeightChanges = root.querySelector("#training-weight-changes");
const trainingWeightChangeScale = root.querySelector("#training-weight-change-scale");
const leaveTrainingButton = root.querySelector("#leave-training");
const PIPELINE_TARGETS = ["expression", "board", "x", "w1", "b1", "h", "w2", "b2", "logits", "argmax", "output"];
const TECHNICAL_SCENES = [
  {
    id: "encoding",
    title: "Encode the position",
    caption: "The board becomes 27 input values: one slot each for X, O, and empty in every square.",
    preset: () => STAGE_PRESETS.encoding,
    targets: ["board", "x"],
    padding: 70,
    duration: 700,
  },
  {
    id: "pipeline",
    title: "Reveal the architecture",
    caption: "The camera pulls back. The same board and one-hot input already occupy their places in the complete network.",
    preset: () => STAGE_PRESETS.encoding,
    targets: PIPELINE_TARGETS,
    padding: 44,
    duration: 760,
  },
  {
    id: "schematics",
    title: "Introduce the parameters",
    caption: "Four labeled shapes establish the dimensions of W₁, b₁, W₂, and b₂ before any individual weights appear.",
    preset: () => STAGE_PRESETS.schematics,
    targets: PIPELINE_TARGETS,
    padding: 44,
    duration: 240,
  },
  {
    id: "accumulators",
    title: "Make room for the sums",
    caption: "Empty hidden and logit accumulators show where the two layers will collect their dot products; argmax and out complete the decision path.",
    preset: () => STAGE_PRESETS.accumulators,
    targets: PIPELINE_TARGETS,
    padding: 44,
    duration: 240,
  },
  {
    id: "rich",
    title: "Resolve the trained network",
    caption: "The schematic parameters resolve into the trained weights while every accumulator remains empty and ready for one forward pass.",
    preset: () => STAGE_PRESETS.rich,
    targets: PIPELINE_TARGETS,
    padding: 44,
    duration: 240,
  },
];
const TECHNICAL_SCENE_IDS = new Set(TECHNICAL_SCENES.map(scene => scene.id));
const CORE_PRESENTATION_STEPS = [
  ...TECHNICAL_SCENES.map(scene => ({ kind: "technical", id: scene.id, label: scene.title })),
  ...EXPLAIN_BEATS.slice(1).map((beat, index) => ({ kind: "explanation", id: beat.id, label: beat.id, beat: index + 1 })),
];
const EXPLANATION_STEP_OFFSET = TECHNICAL_SCENES.length - 1;
const EXPLANATION_STATUS = {
  ready: "Resolve the trained network",
  "select-w1": "Select the active W₁ rows",
  "hidden-0": "Compute hidden unit 0",
  "hidden-1": "Compute hidden unit 1",
  "hidden-rest": "Compute the remaining hidden units",
  relu: "Apply ReLU",
  "select-w2": "Select the active W₂ columns",
  "logit-0": "Compute logit 0",
  "logit-1": "Compute logit 1",
  "logits-rest": "Compute the remaining logits",
  argmax: "Choose the legal move",
};

const SUMMARY_CALLOUTS = [
  {
    id: "encoding",
    number: 1,
    text: "The board state becomes a 27-value one-hot input.",
    anchor: { target: "x", point: "top-center" },
    card: { zone: "top", slot: 1 },
  },
  {
    id: "hidden-sum",
    number: 2,
    text: "W₁ combines the selected input features.",
    anchor: { target: "w1", point: "top-center" },
    card: { zone: "top", slot: 2 },
  },
  {
    id: "relu",
    number: 3,
    text: "ReLU clips negative hidden sums to zero.",
    anchor: { target: "h", point: "center-right" },
    card: { zone: "right", vertical: "center" },
  },
  {
    id: "scores",
    number: 4,
    text: "W₂ creates one score for each candidate move.",
    anchor: { target: "w2", point: "center-left" },
    card: { zone: "bottom", slot: 1 },
  },
  {
    id: "decision",
    number: 5,
    text: "Legal argmax selects the highest-scoring empty square.",
    anchor: { target: "argmax", point: "bottom-center" },
    card: { zone: "bottom", horizontal: 2 / 3 },
  },
  {
    id: "move",
    number: 6,
    text: "The selected move returns to the board.",
    anchor: { target: "output", point: "bottom-center" },
    card: { zone: "bottom", slot: 3 },
  },
];
const PRESENTATION_STEPS = [
  ...CORE_PRESENTATION_STEPS,
  ...SUMMARY_CALLOUTS.map((callout, index) => ({
    kind: "callout",
    id: `callout-${callout.id}`,
    label: `callout ${callout.number}`,
    calloutCount: index + 1,
  })),
];
if (PRESENTATION_STEPS.length !== TIC_TAC_TOE_DEMO_STEPS) {
  throw new Error(`Expected ${TIC_TAC_TOE_DEMO_STEPS} presentation steps, found ${PRESENTATION_STEPS.length}`);
}

let pipeline;
let explain;
let inference;
let training;
let inferenceReturnState = null;
let inferenceReturnModel = null;
let inferenceReturnCalloutCount = 0;
let camera;
let callouts;
let director;
let calloutCount = 0;
let calloutTransition = null;
let mode = "explanation";
let technicalTransition = null;
let currentStep = 0;
let entered = false;
const eventController = new AbortController();
const instant = new URLSearchParams(location.search).has("instant");

beatSelector.replaceChildren();
modelSelector.replaceChildren();
trainingWidthSelector.replaceChildren();
status.classList.remove("ready", "error");

for (const [index, step] of PRESENTATION_STEPS.entries()) {
  const option = document.createElement("option");
  option.value = index;
  option.textContent = `${index + 1}. ${step.label}`;
  beatSelector.append(option);
}

function renderController(state) {
  if (state.beat !== EXPLAIN_BEATS.length - 1 && calloutCount) {
    setCalloutCount(0);
  }
  const step = calloutCount
    ? CORE_PRESENTATION_STEPS.length + calloutCount - 1
    : EXPLANATION_STEP_OFFSET + state.beat;
  currentStep = step;
  beatNumber.textContent = `Step ${step + 1} of ${PRESENTATION_STEPS.length}`;
  caption.textContent = state.beatInfo.caption;
  status.textContent = calloutCount
    ? `Summary callout ${calloutCount} of ${SUMMARY_CALLOUTS.length}`
    : EXPLANATION_STATUS[state.beatInfo.id];
  beatSelector.value = step;
  previousButton.disabled = false;
  nextButton.disabled = false;
  previousButton.disabled ||= state.animating;
  nextButton.disabled ||= state.animating;
  replayButton.disabled = state.animating;
  settleButton.disabled = !state.animating;
  beatSelector.disabled = state.animating;
  modelSelector.disabled = state.animating;
  summaryButton.disabled = state.animating || state.beat !== EXPLAIN_BEATS.length - 1;
  enterInferenceButton.disabled = state.animating || state.beat !== EXPLAIN_BEATS.length - 1;
  summaryButton.classList.toggle("active", calloutCount > 0);
  summaryButton.textContent = calloutCount ? "Hide summary callouts" : "Show summary callouts";
  callouts?.update();
}

function formatMove(move) {
  if (move < 0) return "—";
  return `r${Math.floor(move / 3) + 1}c${move % 3 + 1} (${move})`;
}

function renderInference(state) {
  inferenceStatus.textContent = state.status;
  inferenceMove.textContent = formatMove(state.move);
  inferenceLegal.textContent = state.legalCount;
  inferenceWidth.textContent = state.hiddenWidth;
  animateInferenceInput.checked = state.animateChanges;
  undoInferenceButton.disabled = !state.canUndo || state.animating;
  clearInferenceButton.disabled = state.animating;
  playSuggestedButton.disabled = state.move < 0 || state.animating;
  runInferenceButton.disabled = false;
  runInferenceButton.textContent = state.animating ? "Finish flow" : "Run flow";
  modelSelector.disabled = state.animating;
}

function drawTrainingCurve(points) {
  const context = trainingCurve.getContext("2d");
  const width = trainingCurve.width;
  const height = trainingCurve.height;
  const padding = { left: 34, right: 10, top: 10, bottom: 24 };
  context.clearRect(0, 0, width, height);
  context.strokeStyle = "#d8dee8";
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(padding.left, padding.top);
  context.lineTo(padding.left, height - padding.bottom);
  context.lineTo(width - padding.right, height - padding.bottom);
  context.stroke();
  context.fillStyle = "#7b8597";
  context.font = "18px ui-sans-serif, system-ui";
  context.fillText("100", 0, padding.top + 7);
  context.fillText("0", 18, height - padding.bottom + 6);
  context.fillText("epoch", width - 56, height - 3);
  if (!points.length) return;
  const maximumEpoch = Math.max(1, ...points.map(point => point.epoch));
  context.strokeStyle = "#3458d4";
  context.lineWidth = 3;
  context.lineJoin = "round";
  context.beginPath();
  points.forEach((point, index) => {
    const x = padding.left + point.epoch / maximumEpoch * (width - padding.left - padding.right);
    const y = padding.top + (100 - point.passing) / 100 * (height - padding.top - padding.bottom);
    if (index) context.lineTo(x, y);
    else context.moveTo(x, y);
  });
  context.stroke();
}

function renderFailingBoards(examples, failed) {
  trainingFailingBoards.replaceChildren();
  trainingFailingLabel.textContent = failed === null
    ? "No evaluation yet"
    : failed === 0 ? "None — perfect" : `showing ${examples.length} of ${failed}`;
  for (const { board, prediction } of examples) {
    const element = document.createElement("div");
    element.className = "failing-board";
    element.setAttribute("aria-label", `Failed board; model predicts square ${prediction + 1}`);
    board.forEach((value, index) => {
      const cell = document.createElement("span");
      cell.className = `failing-cell ${value === 1 ? "x" : value === 2 ? "o" : ""}`;
      cell.textContent = value === 1 ? "X" : value === 2 ? "O" : "";
      if (index === prediction) {
        const dot = document.createElement("span");
        dot.className = "failing-prediction";
        dot.setAttribute("aria-hidden", "true");
        cell.append(dot);
      }
      element.append(cell);
    });
    trainingFailingBoards.append(element);
  }
}

function renderTraining(state) {
  const labels = {
    initialized: "Ready at epoch 0",
    running: `Training epoch ${state.epoch}`,
    stopping: "Stopping…",
    stopped: `Stopped at epoch ${state.epoch}`,
    complete: `Perfect at epoch ${state.epoch}`,
    limit: `Epoch limit reached at ${state.epoch}`,
    error: "Training worker failed",
  };
  trainingStatus.textContent = state.replayPlaying || (state.replayAvailable && state.replayIndex < state.frameCount - 1)
    ? `Replaying epoch ${state.epoch}`
    : labels[state.phase] ?? state.phase;
  trainingWidth.textContent = state.hiddenWidth;
  trainingEpoch.textContent = state.epoch;
  trainingLoss.textContent = state.loss === null ? "—" : state.loss.toFixed(4);
  trainingPassing.textContent = state.passing === null ? "—" : `${state.passing.toFixed(2)}%`;
  trainingFailures.textContent = state.failed === null ? "—" : state.boardCount === null ? state.failed : `${state.failed} / ${state.boardCount}`;
  trainingElapsed.textContent = `${(state.elapsed / 1000).toFixed(1)} s`;
  trainingFrames.textContent = state.frameCount;
  trainingCurveLabel.textContent = state.curve.length ? `${state.passing.toFixed(2)}% at epoch ${state.epoch}` : "—";
  drawTrainingCurve(state.curve);
  renderFailingBoards(state.failingBoards, state.failed);
  trainingReplay.hidden = !state.replayAvailable;
  trainingTimeline.max = Math.max(0, state.frameCount - 1);
  trainingTimeline.value = Math.max(0, state.replayIndex);
  trainingTimeline.disabled = state.running;
  trainingFramePosition.textContent = state.frameCount
    ? `frame ${state.replayIndex + 1}/${state.frameCount}`
    : "frame 0/0";
  toggleTrainingReplayButton.textContent = state.replayPlaying ? "❚❚ Pause" : "▶ Replay";
  toggleTrainingReplayButton.disabled = state.running || !state.replayAvailable;
  finishTrainingReplayButton.disabled = !state.replayPlaying;
  trainingReplaySpeed.value = String(state.replaySpeed);
  trainingReplaySpeed.disabled = state.running;
  trainingSlowStart.checked = state.replaySlowStart;
  trainingSlowStart.disabled = state.running;
  trainingWeightChanges.checked = state.showWeightChanges;
  trainingWeightChangeScale.hidden = !state.showWeightChanges;
  const w1Scale = state.w1WeightChangeScale;
  const formattedW1Scale = w1Scale === 0
    ? "0"
    : w1Scale < .001 ? w1Scale.toExponential(2) : w1Scale.toFixed(4);
  trainingWeightChangeScale.textContent = `W₁ full dot = ±${formattedW1Scale}`;
  trainingSeed.value = state.seed;
  trainingSeed.disabled = state.running;
  trainingWidthSelector.disabled = state.running;
  trainingEpochs.disabled = state.running;
  resetTrainingButton.disabled = state.running;
  startTrainingButton.disabled = state.running;
  stopTrainingButton.disabled = !state.running;
  leaveTrainingButton.disabled = false;
  modelSelector.disabled = true;
}

function technicalScene(id) {
  const scene = TECHNICAL_SCENES.find(candidate => candidate.id === id);
  if (!scene) throw new RangeError(`Unknown technical scene: ${id}`);
  return scene;
}

function renderTechnicalScene(id) {
  const scene = technicalScene(id);
  const index = TECHNICAL_SCENES.indexOf(scene);
  currentStep = index;
  technicalTitle.textContent = scene.title;
  technicalNumber.textContent = `Step ${index + 1} of ${PRESENTATION_STEPS.length}`;
  technicalCaption.textContent = scene.caption;
  beatSelector.value = index;
  previousTechnicalButton.disabled = index === 0;
  nextTechnicalButton.textContent = "Next →";
  modelSelector.disabled = false;
  status.textContent = scene.title;
}

function applyTechnicalScene(id) {
  const scene = technicalScene(id);
  showMode("technical");
  pipeline.clearExplanationState();
  pipeline.setState(scene.preset());
  renderTechnicalScene(id);
}

function finishTechnicalTransition({ cancel = false } = {}) {
  const transition = technicalTransition;
  if (!transition) return false;
  technicalTransition = null;
  clearTimeout(transition.timer);
  modelSelector.disabled = false;
  beatSelector.disabled = false;
  if (cancel) {
    camera.cancel();
    if (TECHNICAL_SCENE_IDS.has(transition.from)) applyTechnicalScene(transition.from);
    else if (transition.from === "explanation") {
      showMode("explanation");
      explain.enter({ beat: transition.fromBeat });
    }
  } else {
    camera.finish();
  }
  transition.resolve();
  return true;
}

function enterTechnicalScene(id, from) {
  const fromBeat = from === "explanation" ? explain.getState().beat : null;
  applyTechnicalScene(id);
  const scene = technicalScene(id);
  const previous = TECHNICAL_SCENE_IDS.has(from) ? technicalScene(from) : null;
  const cameraChanged = !previous
    || previous.padding !== scene.padding
    || previous.targets.join("|") !== scene.targets.join("|");
  const duration = instant ? 0 : cameraChanged ? scene.duration : 220;
  if (cameraChanged) camera.animateFrame(scene.targets, { padding: scene.padding, duration });
  if (duration === 0) {
    camera.finish();
    return true;
  }
  modelSelector.disabled = true;
  beatSelector.disabled = true;
  return new Promise(resolve => {
    technicalTransition = {
      id,
      from,
      fromBeat,
      resolve,
      timer: setTimeout(() => finishTechnicalTransition(), duration),
    };
  });
}

function showMode(nextMode) {
  mode = nextMode;
  const presenting = mode === "technical" || mode === "explanation";
  title.textContent = mode === "inference"
    ? "Network inference"
    : mode === "training"
      ? "Network training"
      : "Math explainer";
  workspace.classList.toggle("presentation-mode", presenting);
  stepPicker.hidden = !presenting;
  technicalControls.hidden = true;
  explainerControls.hidden = true;
  inferenceControls.hidden = mode !== "inference";
  trainingControls.hidden = mode !== "training";
  trainingFailuresCard.hidden = mode !== "training";
}

function renderCallouts() {
  if (calloutCount) callouts?.show(SUMMARY_CALLOUTS.slice(0, calloutCount));
  else callouts?.hide();
}

function finishCalloutTransition({ cancel = false } = {}) {
  const transition = calloutTransition;
  if (!transition) return false;
  calloutTransition = null;
  clearTimeout(transition.timer);
  if (cancel) {
    camera.cancel();
    calloutCount = transition.previousCount;
    renderCallouts();
  } else {
    camera.finish();
  }
  renderController(explain.getState());
  return true;
}

function setCalloutCount(nextCount, { animateCamera = true } = {}) {
  if (calloutTransition) finishCalloutTransition();
  const previousCount = calloutCount;
  calloutCount = Math.max(0, Math.min(SUMMARY_CALLOUTS.length, Number(nextCount) || 0));
  if (calloutCount === previousCount) return false;
  renderCallouts();
  const framingChanged = (previousCount === 0) !== (calloutCount === 0);
  if (framingChanged) {
    const duration = instant || !animateCamera ? 0 : 520;
    const animation = camera.animateFrame(PIPELINE_TARGETS, {
      padding: calloutCount ? 100 : 44,
      duration,
    });
    if (animation) {
      calloutTransition = {
        previousCount,
        direction: Math.sign(calloutCount - previousCount),
        timer: setTimeout(() => finishCalloutTransition(), duration),
      };
    }
  }
  return true;
}

function attachInference(history = null) {
  inference = createInferenceController({ pipeline, viewport, onChange: renderInference });
  showMode("inference");
  inference.enter({ board: pipeline.getBoard(), history });
  status.textContent = "Interactive inference ready";
}

function enterInference(history = null) {
  explain.settle();
  inferenceReturnCalloutCount = calloutCount;
  if (calloutTransition) finishCalloutTransition();
  calloutCount = 0;
  renderCallouts();
  explain.detach({ preserveState: true });
  attachInference(history);
  camera.frame(PIPELINE_TARGETS, { padding: 44 });
}

function enterTraining() {
  const seed = requestedTrainingSeed();
  if (seed === null) return false;
  inferenceReturnState = inference.getState();
  inferenceReturnModel = pipeline.model;
  inference.detach();
  inference = null;
  training = createTrainingController({ pipeline, onChange: renderTraining });
  trainingWidthSelector.value = pipeline.model.id;
  showMode("training");
  training.enter({ seed });
  status.textContent = "Training initialized";
  return true;
}

function requestedTrainingSeed() {
  const value = trainingSeed.valueAsNumber;
  const valid = Number.isInteger(value) && value >= 0;
  trainingSeed.setCustomValidity(valid ? "" : "Enter a non-negative integer seed.");
  if (!valid) trainingSeed.reportValidity();
  return valid ? value : null;
}

function leaveTraining() {
  const sameGeometry = pipeline.model.id === inferenceReturnModel.id;
  training.detach({ restoreModel: sameGeometry });
  training = null;
  if (!sameGeometry) replacePipeline(inferenceReturnModel, inferenceReturnState.board);
  pipeline.setBoard(inferenceReturnState.board);
  pipeline.setState(STAGE_PRESETS.complete);
  attachInference(inferenceReturnState.history);
  inferenceReturnState = null;
  inferenceReturnModel = null;
}

function leaveInference() {
  const board = inference.getState().board;
  const restoredCalloutCount = inferenceReturnCalloutCount;
  inference.detach();
  inference = null;
  explain = createExplainController({ pipeline, viewport, onChange: renderController });
  showMode("explanation");
  pipeline.setBoard(board);
  explain.enter({ beat: EXPLAIN_BEATS.length - 1 });
  setCalloutCount(restoredCalloutCount, { animateCamera: false });
  renderController(explain.getState());
  inferenceReturnCalloutCount = 0;
}

function updateCameraReadout(cameraState) {
  callouts?.update();
}

function replacePipeline(model, board) {
  pipeline = createPipelineStage(stageHost, model, board);
  camera.setTargets(pipeline.targets);
  callouts.setTargets(pipeline.targets);
  camera.frame(PIPELINE_TARGETS, { padding: 44 });
}

function changeTrainingWidth(modelId) {
  const model = registry.get(modelId);
  if (!model || model.id === pipeline.model.id) return;
  const seed = requestedTrainingSeed();
  if (seed === null) {
    trainingWidthSelector.value = pipeline.model.id;
    return;
  }
  training.detach({ restoreModel: false });
  replacePipeline(model, inferenceReturnState.board);
  training = createTrainingController({ pipeline, onChange: renderTraining });
  training.enter({ seed });
  trainingWidthSelector.value = model.id;
  status.textContent = `Training reconfigured for H=${model.H}`;
}

function createStage(model, board = INITIAL_BOARD, beat = 0, { frame = entered } = {}) {
  if (training) {
    training.detach({ restoreModel: false });
    training = null;
  }
  if (inference) {
    inference.detach();
    inference = null;
  }
  if (explain) explain.detach();
  pipeline = createPipelineStage(stageHost, model, board);
  explain = createExplainController({ pipeline, viewport, onChange: renderController });
  explain.enter({ beat });
  if (camera) camera.setTargets(pipeline.targets);
  else camera = new StageCamera(viewport, cameraElement, pipeline.targets, updateCameraReadout);
  if (callouts) callouts.setTargets(pipeline.targets);
  else callouts = createCalloutOverlay(viewport, pipeline.targets);
  if (frame) camera.frame(PIPELINE_TARGETS, { padding: calloutCount ? 100 : 44 });
  if (calloutCount && beat === EXPLAIN_BEATS.length - 1) renderCallouts();
}

function createDirector() {
  const technicalScenes = TECHNICAL_SCENES.map((scene, index) => ({
    id: scene.id,
    enter: ({ from }) => enterTechnicalScene(scene.id, from),
    next() {
      const next = TECHNICAL_SCENES[index + 1]?.id;
      if (next) director.goTo(next, { direction: 1 });
      else director.goTo("explanation", { beat: 1, animate: true, direction: 1 });
    },
    previous() {
      const previous = TECHNICAL_SCENES[index - 1]?.id;
      if (!previous) return false;
      director.goTo(previous, { direction: -1 });
    },
    finish: () => finishTechnicalTransition(),
    cancel: () => finishTechnicalTransition({ cancel: true }),
    state: () => ({ id: scene.id, index, count: TECHNICAL_SCENES.length, title: scene.title }),
  }));
  return createPresentationDirector({
    initialScene: null,
    scenes: [
      ...technicalScenes,
      {
        id: "explanation",
        enter({ from, beat = 0, animate = false }) {
          if (from === "inference") leaveInference();
          else {
            showMode("explanation");
            explain.enter({ beat: animate ? Math.max(0, beat - 1) : beat });
            if (animate) explain.next();
            if (from !== "rich") camera.frame(PIPELINE_TARGETS, { padding: 44 });
          }
        },
        next() {
          const state = explain.getState();
          if (calloutTransition) {
            finishCalloutTransition({ cancel: calloutTransition.direction < 0 });
          } else if (state.animating) {
            if (state.animationDirection > 0) explain.finish();
            else explain.cancel();
          }
          else if (state.canNext) explain.next();
          else if (calloutCount < SUMMARY_CALLOUTS.length) {
            setCalloutCount(calloutCount + 1);
            renderController(state);
          } else director.goTo("inference", { direction: 1 });
        },
        previous() {
          const state = explain.getState();
          if (calloutTransition) {
            finishCalloutTransition({ cancel: calloutTransition.direction > 0 });
          }
          else if (calloutCount) {
            setCalloutCount(calloutCount - 1);
            renderController(state);
          } else if (state.animating) {
            if (state.animationDirection < 0) explain.finish();
            else explain.cancel();
          }
          else if (state.beat > 1) explain.previous();
          else director.goTo("rich", { direction: -1 });
        },
        finish() {
          finishCalloutTransition();
          camera.finish();
          explain.finish();
        },
        cancel() {
          if (calloutTransition) {
            finishCalloutTransition({ cancel: true });
            return;
          }
          camera.cancel();
          explain.cancel();
          const currentScene = director.state().scene;
          if (TECHNICAL_SCENE_IDS.has(currentScene)) applyTechnicalScene(currentScene);
        },
        state: () => explain.getState(),
      },
      {
        id: "inference",
        enter({ from }) {
          if (from === "explanation") enterInference();
          else if (from === "training") leaveTraining();
          else return false;
        },
        next() {
          const state = inference.getState();
          if (!state.animating) return false;
          inference.finish();
        },
        previous() {
          const state = inference.getState();
          if (state.animating) inference.cancel();
          else director.goTo("explanation", { direction: -1 });
        },
        finish: () => inference.finish(),
        cancel: () => inference.cancel(),
        state: () => inference.getState(),
      },
      {
        id: "training",
        enter({ from }) {
          return from === "inference" ? enterTraining() : false;
        },
        next() {
          const state = training.getState();
          if (!state.replayPlaying) return false;
          training.finish();
        },
        previous() {
          const state = training.getState();
          if (!state.replayPlaying) return false;
          training.cancel();
        },
        finish: () => training.finish(),
        cancel: () => training.cancel(),
        state: () => training.getState(),
      },
    ],
  });
}

function returnToPresentation() {
  if (mode === "training") leaveTraining();
  if (mode === "inference") leaveInference();
}

function setMode(nextMode) {
  const normalized = normalizeMode(nextMode);
  settleStep();
  if (normalized === "presentation") {
    returnToPresentation();
    return setStep(currentStep, { animate: false });
  }
  if (normalized === "inference") {
    if (mode === "training") leaveTraining();
    else if (mode !== "inference") enterInference();
    return true;
  }
  if (mode === "training") return true;
  if (mode !== "inference") enterInference();
  return enterTraining();
}

function setStep(index, { animate = entered } = {}) {
  const normalized = normalizeStep(index);
  const direction = Math.sign(normalized - currentStep);
  const presenting = mode === "technical" || mode === "explanation";
  if (animate && presenting && Math.abs(normalized - currentStep) === 1) {
    const handled = direction > 0 ? director.next() : director.previous();
    if (handled) return true;
  }
  settleStep();
  returnToPresentation();
  const step = PRESENTATION_STEPS[normalized];
  if (step.kind === "technical") {
    calloutCount = 0;
    renderCallouts();
    director.setScene(step.id);
    applyTechnicalScene(step.id);
    if (entered) {
      const scene = technicalScene(step.id);
      camera.frame(scene.targets, { padding: scene.padding });
    }
  } else {
    director.setScene("explanation");
    showMode("explanation");
    const beat = step.kind === "callout" ? EXPLAIN_BEATS.length - 1 : step.beat;
    calloutCount = step.kind === "callout" ? step.calloutCount : 0;
    explain.enter({ beat });
    renderCallouts();
    renderController(explain.getState());
    if (entered) camera.frame(PIPELINE_TARGETS, { padding: calloutCount ? 100 : 44 });
  }
  currentStep = normalized;
  return true;
}

function navigate(direction) {
  const delta = Math.sign(Number(direction) || 0);
  if (!delta) return false;
  return delta > 0 ? director.next() : director.previous();
}

function replayStep() {
  if (mode !== "explanation") return false;
  explain.replay();
  return true;
}

function settleStep() {
  let changed = false;
  changed = finishTechnicalTransition() || changed;
  changed = finishCalloutTransition() || changed;
  changed = camera?.finish() || changed;
  changed = explain?.finish() || changed;
  changed = inference?.finish() || changed;
  changed = training?.finish() || changed;
  return changed;
}

function enter() {
  entered = true;
}

function exit() {
  settleStep();
  if (training?.getState().running) training.stop();
  entered = false;
}

function unmount() {
  exit();
  eventController.abort();
  if (training) {
    training.detach({ restoreModel: false });
    training = null;
  }
  if (inference) {
    inference.detach();
    inference = null;
  }
  if (explain) {
    explain.detach();
    explain = null;
  }
  camera?.destroy();
  camera = null;
  cameraElement.style.transform = "";
  callouts?.destroy();
  callouts = null;
  pipeline = null;
  director = null;
  stageHost.replaceChildren();
}

function listen(target, type, handler, options = {}) {
  target.addEventListener(type, handler, { ...options, signal: eventController.signal });
}

listen(enterInferenceButton, "click", () => director.goTo("inference"));
listen(playSuggestedButton, "click", () => inference.playSuggested());
listen(runInferenceButton, "click", () => {
  if (inference.getState().animating) inference.finish();
  else inference.runFlow();
});
listen(undoInferenceButton, "click", () => inference.undo());
listen(clearInferenceButton, "click", () => inference.clear());
listen(animateInferenceInput, "change", () => inference.setAnimateChanges(animateInferenceInput.checked));
listen(leaveInferenceButton, "click", () => director.goTo("explanation"));
listen(enterTrainingButton, "click", () => director.goTo("training"));
listen(resetTrainingButton, "click", () => {
  const seed = requestedTrainingSeed();
  if (seed !== null) training.reset(seed);
});
listen(startTrainingButton, "click", () => {
  const maximum = trainingEpochs.valueAsNumber;
  if (!Number.isInteger(maximum) || maximum < 1) {
    trainingEpochs.setCustomValidity("Enter a positive integer epoch limit.");
    trainingEpochs.reportValidity();
    return;
  }
  trainingEpochs.setCustomValidity("");
  training.start({ maxEpochs: maximum });
});
listen(stopTrainingButton, "click", () => training.stop());
listen(toggleTrainingReplayButton, "click", () => training.toggleReplay());
listen(finishTrainingReplayButton, "click", () => training.finish());
listen(trainingTimeline, "input", () => training.seekReplay(Number(trainingTimeline.value)));
listen(trainingReplaySpeed, "change", () => training.setReplayOptions({ speed: Number(trainingReplaySpeed.value) }));
listen(trainingSlowStart, "change", () => training.setReplayOptions({ slowStart: trainingSlowStart.checked }));
listen(trainingWeightChanges, "change", () => training.setShowWeightChanges(trainingWeightChanges.checked));
listen(trainingWidthSelector, "change", () => changeTrainingWidth(trainingWidthSelector.value));
listen(leaveTrainingButton, "click", () => director.goTo("inference"));
listen(summaryButton, "click", () => {
  setCalloutCount(calloutCount ? 0 : SUMMARY_CALLOUTS.length);
  renderController(explain.getState());
});
listen(stageHost, "pipeline-board-change", () => {
  if (mode === "explanation") explain.enter({ beat: 0 });
});

for (const model of registry.list()) {
  const option = document.createElement("option");
  option.value = model.id;
  const dimensions = `(H=${model.H})`;
  option.textContent = model.name.includes(dimensions) ? model.name : `${model.name} ${dimensions}`;
  modelSelector.append(option);
  const trainingOption = document.createElement("option");
  trainingOption.value = model.id;
  trainingOption.textContent = `H=${model.H}`;
  trainingWidthSelector.append(trainingOption);
}
modelSelector.value = registry.selected().id;
createStage(registry.selected(), INITIAL_BOARD, 0, { frame: false });
director = createDirector();
applyTechnicalScene("encoding");
director.setScene("encoding");
listen(modelSelector, "change", () => {
  const board = pipeline.getBoard();
  const previousMode = mode;
  const previousScene = director.state().scene;
  const history = inference?.getState().history ?? null;
  const beat = previousMode === "explanation" ? explain.getState().beat : EXPLAIN_BEATS.length - 1;
  createStage(registry.select(modelSelector.value), board, beat);
  if (previousMode === "inference") enterInference(history);
  else if (previousMode === "technical") {
    const scene = technicalScene(previousScene);
    applyTechnicalScene(previousScene);
    if (entered) camera.frame(scene.targets, { padding: scene.padding });
  }
});
status.textContent = technicalScene("encoding").title;
status.classList.add("ready");

return Object.freeze({
  root,
  enter,
  setStep,
  setMode,
  settleStep,
  navigate,
  replayStep,
  exit,
  unmount,
  get director() {
    return director;
  },
  get explain() {
    return explain;
  },
  get step() {
    return currentStep;
  },
  get mode() {
    return mode;
  },
});
}
