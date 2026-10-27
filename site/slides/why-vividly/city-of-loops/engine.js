import { NODES, EDGES, SKETCH_TIMING, cityTransform, drawSketch } from './sketch.js';

const TAU = Math.PI * 2;

const COLORS = {
  bg: '#05080d',
  road: '#1e2735',
  island: '#0b1119',
  lane: '#3a4658',
  label: '#9ba8bb',
  plan: '#5f6a7b',
  red: '#ff5a52',
  pipeline: '#9be564',
  gear: '#161e2b',
  gearEdge: '#5d6c82',
  foreground: '#e6ebf2',
  light: '#fff1d0',
};

const SCIENTISTS = ['#ffb547', '#4fd1e8', '#ff5fa2', '#9be564', '#a58bff'];
const LABELS = [
  ['Data cleaning', 'Human labels', 'Augmentation', 'Case curation', 'Eval harness', 'Judge evals', 'Case repair', 'Debugging', 'Implement'],
  ['Write cases', 'Run', 'Score', 'Edge cases', 'Inspect failures', 'Calibrate', 'Compare runs', 'Fix harness', 'Report'],
  ['Typos', 'Truncations', 'Dedupe', 'Encoding', 'Unicode', 'Re-label', 'Spot-check', 'Regex', 'Diff'],
];
const ADJACENCY = NODES.map(() => []);
for (const [a, b] of EDGES) {
  ADJACENCY[a].push(b);
  ADJACENCY[b].push(a);
}

const NETWORK_SIZE = NODES.length;
const ZOOM_NODE = 4;
const INNER_SCALE = .7;
const ZOOM_SCALE = NODES[ZOOM_NODE].r * INNER_SCALE;
const ZOOM_X = NODES[ZOOM_NODE].x / (1 - ZOOM_SCALE);
const ZOOM_Y = NODES[ZOOM_NODE].y / (1 - ZOOM_SCALE);
const ZOOM_START_DELAY = 1.2;
const ZOOM_CYCLE_DURATION = 5.5;
const ZOOM_CYCLES = 2;
const WATERFALL_REVEAL_DURATION = 3.5;
// Match the 700ms delay and 600ms caption reveal in slide.css.
const CAPTION_REVEAL_DURATION = 1.3;
const HISTORY_LIMIT = 420;
const BASE_CAR_SPEED = .12;
const CAR_SPEED_FACTOR_MIN = .55;
const CAR_SPEED_FACTOR_RANGE = 1;
const MAIN_CAR_SPEED = .14;
const MAIN_CAR_TURN_DURATION = .8;
const MAIN_CAR_TURN_ARC = .28;
const CLOSURE_QUEUE_LENGTH = 4;
const CLOSURE_QUEUE_PROGRESS = .46;
const CLOSURE_QUEUE_SPACING = .052;
const CLOSURE_QUEUE_ENTRY_MARGIN = .02;
const REVERSAL_TARGET_PROGRESS = .4;
const REVERSAL_DURATION = .5;

export const ENDING_TIMING = {
  maskFade: 2,
  trailStart: 3,
  proofFadeStart: 4.5,
  proofFadeEnd: 5.5,
  titleStart: 5.5,
  titleEnd: 7,
  questionStart: 7,
  questionEnd: 8.5,
  duration: 12,
};

export const SCENES = [
  {
    key: 'problem',
    duration: WATERFALL_REVEAL_DURATION,
    label: 'A case study',
    title: '<mark>Case study:</mark> I needed to explain a new way of working.',
    text: 'The familiar picture <mark>missed the point:</mark> work now is fluid, decentralized, and constantly adapting.',
  },
  {
    key: 'gears',
    duration: CAPTION_REVEAL_DURATION,
    label: 'Motion is not enough',
    title: "Adding motion <mark>didn't fix the metaphor.</mark>",
    text: 'Work is no longer linear—or in lockstep.',
  },
  {
    key: 'first-loop',
    duration: SKETCH_TIMING.duration,
    label: 'The realization',
    title: 'The real idea was <mark>far more exciting.</mark>',
    text: 'What I kept seeing was <mark>loops</mark>.',
    expansion: {
      title: 'Lots of loops—interconnected and constantly changing.',
      text: 'Team members hopping from loop to loop as conditions change and new insights emerge.',
    },
  },
  {
    key: 'drivers',
    duration: CAPTION_REVEAL_DURATION,
    label: 'The essence',
    title: "Today's work is a City of Loops.",
    text: 'Independent decisions. Connected work. Constant learning.',
  },
  {
    key: 'zoom',
    duration: ZOOM_START_DELAY + ZOOM_CYCLE_DURATION * ZOOM_CYCLES,
    label: 'Loops inside loops',
    title: 'And every loop contains more loops.',
    text: 'Projects contain features, experiments, inquiries, debugging, and evaluation.',
  },
  {
    key: 'headlights',
    duration: CAPTION_REVEAL_DURATION,
    label: 'Night driving',
    title: 'No one needs to see the entire map.',
    text: 'Team members decide on the spot, using the best information available at the time.',
  },
  {
    key: 'pull',
    duration: ENDING_TIMING.duration,
    label: 'The idea, made visible',
    title: 'The explanation finally behaves like the idea.',
    text: 'Not just a more compelling picture—a truer one.',
    ending: {
      title: `With <img class="closing-logo" src="${new URL('../../../vividly/assets/logo.svg', import.meta.url).href}" alt="Vividly"><span class="closing-comma">,</span> you direct.`,
      text: 'What would you bring to life?',
    },
  },
];

function geometry(a, b, lane = 0) {
  const start = NODES[a];
  const end = NODES[b];
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const distance = Math.hypot(dx, dy);
  const ux = dx / distance;
  const uy = dy / distance;
  const px = -uy * lane;
  const py = ux * lane;
  const startInset = Math.sqrt(Math.max(0, start.r ** 2 - lane ** 2));
  const endInset = Math.sqrt(Math.max(0, end.r ** 2 - lane ** 2));
  return {
    x0: start.x + ux * startInset + px,
    y0: start.y + uy * startInset + py,
    x1: end.x - ux * endInset + px,
    y1: end.y - uy * endInset + py,
    ux,
    uy,
    length: distance - startInset - endInset,
  };
}

const ROAD_GEOMETRY = {};
const CENTER_GEOMETRY = {};
for (const [a, b] of EDGES) {
  ROAD_GEOMETRY[a * NETWORK_SIZE + b] = geometry(a, b, .016);
  ROAD_GEOMETRY[b * NETWORK_SIZE + a] = geometry(b, a, .016);
  CENTER_GEOMETRY[a * NETWORK_SIZE + b] = geometry(a, b);
}

const mod = (value, modulus) => ((value % modulus) + modulus) % modulus;
const smooth = (start, end, value) => {
  const t = Math.min(1, Math.max(0, (value - start) / (end - start)));
  return t * t * (3 - 2 * t);
};
const CITY_CAR = '#c6cfdc';
const MODEL_TRANSITION_DURATION = .7;

function mixColor(from, to, amount) {
  const channels = color => [
    Number.parseInt(color.slice(1, 3), 16),
    Number.parseInt(color.slice(3, 5), 16),
    Number.parseInt(color.slice(5, 7), 16),
  ];
  const start = channels(from);
  const end = channels(to);
  const mixed = start.map((value, index) => Math.round(value + (end[index] - value) * amount));
  return `rgb(${mixed.join(', ')})`;
}

function seededRandom(seed = 0x6d2b79f5) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ value >>> 15, value | 1);
    value ^= value + Math.imul(value ^ value >>> 7, value | 61);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}

export function createCityRenderer(canvas, {
  reducedMotion = false,
  composition = false,
  getWaterfallHeight = () => canvas.getBoundingClientRect().height,
  onProgress = () => {},
} = {}) {
  const ctx = canvas.getContext('2d');
  const mask = document.createElement('canvas');
  const maskContext = mask.getContext('2d');
  let width = 1;
  let height = 1;
  let dpr = 1;
  let sceneIndex = 0;
  let elapsed = 0;
  let sceneSettled = false;
  let lastTime = 0;
  let frameId = 0;
  let resizeTimer = 0;
  let running = false;
  let closure = null;
  let cars = [];
  let gearAngle = 0;
  let zoomProgress = 0;
  let zoomCycle = 0;
  let sceneTransition = null;
  let pullOrigin = null;
  let pullTrailCount = 0;
  const camera = { x: 0, y: 0, heading: 0 };
  const currentSceneKey = () => SCENES[sceneIndex].key;
  const usesLeadCar = () => currentSceneKey() === 'headlights' || currentSceneKey() === 'pull';
  const transitionFromKey = () => (
    sceneTransition ? SCENES[sceneTransition.fromIndex]?.key : null
  );

  function resize() {
    const rect = canvas.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    mask.width = canvas.width;
    mask.height = canvas.height;
    draw(0);
  }

  const observer = new ResizeObserver(resize);
  observer.observe(canvas);

  function isClosed(a, b) {
    return closure && (
      (closure[0] === a && closure[1] === b)
      || (closure[0] === b && closure[1] === a)
    );
  }

  function clearQueueSlot(car) {
    car.queueFrom = undefined;
    car.queueTo = undefined;
    car.queueSlot = undefined;
    car.queueStop = undefined;
  }

  function queueStop(from, to, slot) {
    const road = ROAD_GEOMETRY[from * NETWORK_SIZE + to];
    return CLOSURE_QUEUE_PROGRESS - slot * CLOSURE_QUEUE_SPACING / road.length;
  }

  function claimQueueSlot(car, from, to) {
    const occupied = new Set(cars
      .filter(other => other !== car && other.queueFrom === from && other.queueTo === to)
      .map(other => other.queueSlot));
    for (let slot = 0; slot < CLOSURE_QUEUE_LENGTH; slot += 1) {
      const stop = queueStop(from, to, slot);
      if (stop < CLOSURE_QUEUE_ENTRY_MARGIN) return false;
      if (occupied.has(slot)) continue;
      car.queueFrom = from;
      car.queueTo = to;
      car.queueSlot = slot;
      car.queueStop = stop;
      return true;
    }
    return false;
  }

  function setExit(car, next, extraLoop = false) {
    const from = NODES[car.node];
    const road = ROAD_GEOMETRY[car.node * NETWORK_SIZE + next];
    car.next = next;
    car.exitAngle = Math.atan2(road.y0 - from.y, road.x0 - from.x);
    let remaining = mod(car.angle - car.exitAngle, TAU);
    if (remaining < .25) remaining += TAU;
    car.remaining = remaining + (extraLoop ? TAU : 0);
  }

  function chooseNext(car) {
    let options = ADJACENCY[car.node].filter(node => node !== car.previous);
    if (!options.length) options = ADJACENCY[car.node];
    if (closure) {
      if (car.scientist === 0) {
        const open = options.filter(node => !isClosed(car.node, node));
        if (open.length) options = open;
      } else {
        const blocked = options.filter(node => isClosed(car.node, node));
        if (blocked.length && car.random() < .65) return blocked[0];
      }
    }
    return options[Math.floor(car.random() * options.length)];
  }

  function planExit(car) {
    setExit(car, chooseNext(car), car.random() < .22);
  }

  function resetCars() {
    const random = seededRandom();
    cars = Array.from({ length: 40 }, (_, id) => {
      const node = Math.floor(random() * NETWORK_SIZE);
      const angle = random() * TAU;
      const randomSpeed = BASE_CAR_SPEED * (
        CAR_SPEED_FACTOR_MIN + random() * CAR_SPEED_FACTOR_RANGE
      );
      const car = {
        id,
        scientist: id % SCIENTISTS.length,
        node,
        mode: 'ring',
        angle,
        previous: -1,
        speed: usesLeadCar() && id === 0 ? MAIN_CAR_SPEED : randomSpeed,
        history: [],
        random,
      };
      planExit(car);
      return car;
    });
    for (let i = 0; i < 300; i += 1) simulate(1 / 60);
  }

  function carPosition(car) {
    if (car.mode === 'ring') {
      const node = NODES[car.node];
      return {
        x: node.x + node.r * Math.cos(car.angle),
        y: node.y + node.r * Math.sin(car.angle),
        heading: car.angle - Math.PI / 2,
      };
    }
    if (car.mode === 'turn') {
      const positionAmount = Math.min(1, car.turnElapsed / MAIN_CAR_TURN_DURATION);
      const headingAmount = smooth(0, MAIN_CAR_TURN_DURATION, car.turnElapsed);
      const inverse = 1 - positionAmount;
      const x = inverse ** 3 * car.turnStart.x
        + 3 * inverse ** 2 * positionAmount * car.turnControl1.x
        + 3 * inverse * positionAmount ** 2 * car.turnControl2.x
        + positionAmount ** 3 * car.turnEnd.x;
      const y = inverse ** 3 * car.turnStart.y
        + 3 * inverse ** 2 * positionAmount * car.turnControl1.y
        + 3 * inverse * positionAmount ** 2 * car.turnControl2.y
        + positionAmount ** 3 * car.turnEnd.y;
      return {
        x,
        y,
        heading: car.turnStartHeading + car.turnHeadingDelta * headingAmount,
      };
    }
    const road = ROAD_GEOMETRY[car.from * NETWORK_SIZE + car.to];
    if (car.reversalPhase === 'turning') {
      const reverseRoad = ROAD_GEOMETRY[car.to * NETWORK_SIZE + car.from];
      const amount = smooth(0, REVERSAL_DURATION, car.reversalElapsed);
      const reverseProgress = 1 - car.progress;
      const x = road.x0 + (road.x1 - road.x0) * car.progress;
      const y = road.y0 + (road.y1 - road.y0) * car.progress;
      const reverseX = reverseRoad.x0 + (reverseRoad.x1 - reverseRoad.x0) * reverseProgress;
      const reverseY = reverseRoad.y0 + (reverseRoad.y1 - reverseRoad.y0) * reverseProgress;
      return {
        x: x + (reverseX - x) * amount,
        y: y + (reverseY - y) * amount,
        heading: Math.atan2(road.uy, road.ux) + Math.PI * amount,
      };
    }
    return {
      x: road.x0 + (road.x1 - road.x0) * car.progress,
      y: road.y0 + (road.y1 - road.y0) * car.progress,
      heading: Math.atan2(road.uy, road.ux),
    };
  }

  function startMainCarTurn(car, {
    start,
    end,
    startHeading,
    endHeading,
    handle,
    targetMode,
    endAngle = 0,
    endProgress = 0,
  }) {
    car.mode = 'turn';
    car.turnElapsed = 0;
    car.turnStart = start;
    car.turnControl1 = {
      x: start.x + Math.cos(startHeading) * handle,
      y: start.y + Math.sin(startHeading) * handle,
    };
    car.turnEnd = end;
    car.turnControl2 = {
      x: end.x - Math.cos(endHeading) * handle,
      y: end.y - Math.sin(endHeading) * handle,
    };
    car.turnStartHeading = startHeading;
    car.turnHeadingDelta = mod(endHeading - startHeading + Math.PI, TAU) - Math.PI;
    car.turnTargetMode = targetMode;
    car.turnEndAngle = endAngle;
    car.turnEndProgress = endProgress;
  }

  function stepCar(car, dt) {
    if (car.mode === 'ring') {
      const delta = car.speed / NODES[car.node].r * dt;
      if (delta < car.remaining) {
        car.angle -= delta;
        car.remaining -= delta;
        return;
      }
      car.angle = car.exitAngle;
      if (isClosed(car.node, car.next) && car.scientist === 0) {
        const alternatives = ADJACENCY[car.node].filter(node => !isClosed(car.node, node));
        setExit(car, alternatives[Math.floor(car.random() * alternatives.length)]);
        return;
      }
      if (
        isClosed(car.node, car.next)
        && car.scientist !== 0
        && !claimQueueSlot(car, car.node, car.next)
      ) {
        setExit(car, car.next);
        return;
      }
      if (usesLeadCar() && car.id === 0 && !reducedMotion) {
        const road = ROAD_GEOMETRY[car.node * NETWORK_SIZE + car.next];
        const handle = NODES[car.node].r * .22;
        const endProgress = Math.min(.12, handle * 1.5 / road.length);
        car.from = car.node;
        car.to = car.next;
        startMainCarTurn(car, {
          start: { x: road.x0, y: road.y0 },
          end: {
            x: road.x0 + (road.x1 - road.x0) * endProgress,
            y: road.y0 + (road.y1 - road.y0) * endProgress,
          },
          startHeading: car.angle - Math.PI / 2,
          endHeading: Math.atan2(road.uy, road.ux),
          handle,
          targetMode: 'road',
          endProgress,
        });
        return;
      }
      car.mode = 'road';
      car.from = car.node;
      car.to = car.next;
      car.progress = 0;
      return;
    }
    if (car.mode === 'turn') {
      car.turnElapsed += dt;
      if (car.turnElapsed < MAIN_CAR_TURN_DURATION) return;
      car.mode = car.turnTargetMode;
      if (car.mode === 'ring') {
        car.node = car.to;
        car.angle = car.turnEndAngle;
        car.previous = car.from;
        car.closureExempt = false;
        planExit(car);
      } else {
        car.progress = car.turnEndProgress;
      }
      return;
    }

    const road = ROAD_GEOMETRY[car.from * NETWORK_SIZE + car.to];
    if (car.reversalPhase === 'approaching') {
      const distance = car.reversalTarget - car.progress;
      if (distance <= .001) {
        car.progress = car.reversalTarget;
        car.reversalPhase = 'turning';
        car.reversalElapsed = 0;
        return;
      }
      const braking = Math.max(.12, Math.min(1, distance / .12));
      car.progress = Math.min(
        car.reversalTarget,
        car.progress + car.speed * braking * dt / road.length,
      );
      return;
    }
    if (car.reversalPhase === 'turning') {
      car.reversalElapsed += dt;
      if (car.reversalElapsed < REVERSAL_DURATION) return;
      const from = car.from;
      car.from = car.to;
      car.to = from;
      car.progress = 1 - car.progress;
      car.reversalPhase = null;
      car.reversalElapsed = 0;
      car.closureExempt = true;
      return;
    }

    const limit = car.queueStop ?? 1;
    car.progress = Math.min(limit, car.progress + car.speed * dt / road.length);
    if (car.progress >= 1) {
      if (usesLeadCar() && car.id === 0 && !reducedMotion) {
        const node = NODES[car.to];
        const startAngle = Math.atan2(road.y1 - node.y, road.x1 - node.x);
        const endAngle = startAngle - MAIN_CAR_TURN_ARC;
        const handle = node.r * .22;
        const endHeading = endAngle - Math.PI / 2;
        startMainCarTurn(car, {
          start: { x: road.x1, y: road.y1 },
          end: {
            x: node.x + node.r * Math.cos(endAngle),
            y: node.y + node.r * Math.sin(endAngle),
          },
          startHeading: Math.atan2(road.uy, road.ux),
          endHeading,
          handle,
          targetMode: 'ring',
          endAngle,
        });
        return;
      }
      car.previous = car.from;
      car.node = car.to;
      car.mode = 'ring';
      car.angle = Math.atan2(road.y1 - NODES[car.to].y, road.x1 - NODES[car.to].x);
      car.closureExempt = false;
      clearQueueSlot(car);
      planExit(car);
    }
  }

  function simulate(dt) {
    for (const car of cars) {
      stepCar(car, dt);
      const position = carPosition(car);
      car.history.push([position.x, position.y]);
      if (car.history.length > HISTORY_LIMIT) car.history.shift();
    }
  }

  function placeEverywhereCars() {
    const exits = ADJACENCY[4];
    cars.filter(car => car.scientist === 0).forEach((car, carIndex) => {
      car.node = 4;
      car.mode = 'ring';
      car.angle = -Math.PI / 2;
      car.previous = -1;
      car.speed = .13 + carIndex * .004;
      car.history = [];
      car.random = seededRandom(0x710000 + car.id);
      setExit(car, exits[carIndex % exits.length], carIndex >= exits.length);
    });
  }

  function placeDetourCars() {
    cars.filter(car => car.scientist === 0).forEach((car, carIndex) => {
      car.node = 4;
      car.mode = 'ring';
      car.previous = -1;
      car.speed = .13 + carIndex * .004;
      car.history = [];
      car.random = seededRandom(0xd37000 + car.id);
      setExit(car, 5);
      car.remaining = .18 + carIndex * .08;
      car.angle = car.exitAngle + car.remaining;
    });
  }

  function prepareClosure() {
    for (const car of cars) {
      car.reversalPhase = null;
      car.reversalElapsed = 0;
      car.closureExempt = false;
      clearQueueSlot(car);
      if (car.mode !== 'road' || !isClosed(car.from, car.to)) continue;
      if (car.scientist === 0 && car.progress < .5) {
        car.reversalPhase = 'approaching';
        car.reversalTarget = Math.max(car.progress, REVERSAL_TARGET_PROGRESS);
      } else if (car.progress >= CLOSURE_QUEUE_PROGRESS) {
        car.closureExempt = true;
      }
    }
    for (const [from, to] of [closure, [...closure].reverse()]) {
      const queued = cars
        .filter(car => (
          car.scientist !== 0
          && car.mode === 'road'
          && car.from === from
          && car.to === to
          && !car.closureExempt
        ))
        .sort((a, b) => b.progress - a.progress || a.id - b.id);
      queued.forEach((car, slot) => {
        if (slot >= CLOSURE_QUEUE_LENGTH) {
          car.closureExempt = true;
          return;
        }
        const stop = queueStop(from, to, slot);
        if (stop < CLOSURE_QUEUE_ENTRY_MARGIN) {
          car.closureExempt = true;
          return;
        }
        car.queueFrom = from;
        car.queueTo = to;
        car.queueSlot = slot;
        car.queueStop = Math.max(car.progress, stop);
      });
    }
  }

  function resetScene(index, { preserveTraffic = false, fromIndex } = {}) {
    const incomingKey = SCENES[index].key;
    const outgoingKey = SCENES[fromIndex]?.key;
    const headlightHandoff = preserveTraffic && outgoingKey === 'headlights' && incomingKey === 'pull';
    const outgoingYellow = preserveTraffic && incomingKey === 'everywhere'
      ? cars.filter(car => car.scientist === 0).map(car => carPosition(car))
      : [];
    sceneIndex = index;
    elapsed = 0;
    sceneSettled = false;
    if (!(preserveTraffic && outgoingKey === 'gears' && incomingKey === 'first-loop')) {
      gearAngle = 0;
    }
    zoomProgress = 0;
    zoomCycle = 0;
    closure = incomingKey === 'detour' ? [4, 5] : null;
    if (!preserveTraffic) resetCars();

    if (incomingKey === 'everywhere') {
      placeEverywhereCars();
    } else if (incomingKey === 'detour') {
      if (preserveTraffic && outgoingKey === 'everywhere') prepareClosure();
      else placeDetourCars();
    }

    pullTrailCount = 0;

    sceneTransition = preserveTraffic
      ? {
        fromIndex,
        toIndex: index,
        duration: MODEL_TRANSITION_DURATION,
        outgoingYellow,
      }
      : null;
    const lead = carPosition(cars[0]);
    if (!headlightHandoff) {
      camera.x = lead.x;
      camera.y = lead.y;
      camera.heading = lead.heading;
    }
    pullOrigin = incomingKey === 'pull' ? { ...camera } : null;
    onProgress(reducedMotion ? 1 : 0, reducedMotion ? SCENES[index].duration : elapsed);
    // Reuse the rendered frame as well as the live simulation at this boundary.
    if (!headlightHandoff) draw(0);
  }

  function baseTransform() {
    return cityTransform(width, height);
  }

  function drawCar(x, y, heading, length, carWidth, color, alpha, glow = 0) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(heading);
    ctx.globalAlpha *= alpha;
    if (glow) {
      ctx.shadowColor = color;
      ctx.shadowBlur = glow;
    }
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(-length / 2, -carWidth / 2, length, carWidth, carWidth * .35);
    ctx.fill();
    ctx.restore();
  }

  function renderNetwork(transform, depth, options) {
    const { ox, oy, scale } = transform;
    if (ox + scale * 1.25 < 0 || ox - scale * 1.25 > width
      || oy + scale * 1.25 < 0 || oy - scale * 1.25 > height) return;

    const x = value => ox + scale * value;
    const y = value => oy + scale * value;
    const roadWidth = Math.max(.8, scale * .05);
    const inheritedAlpha = ctx.globalAlpha;
    const ownAlpha = depth < 0 ? (options.inner ?? 1) : 1;
    ctx.globalAlpha = inheritedAlpha * ownAlpha;
    ctx.lineCap = 'round';
    ctx.strokeStyle = COLORS.road;
    ctx.lineWidth = roadWidth;
    ctx.beginPath();
    for (const [a, b] of EDGES) {
      const road = CENTER_GEOMETRY[a * NETWORK_SIZE + b];
      ctx.moveTo(x(road.x0), y(road.y0));
      ctx.lineTo(x(road.x1), y(road.y1));
    }
    ctx.stroke();
    for (const node of NODES) {
      ctx.beginPath();
      ctx.arc(x(node.x), y(node.y), scale * node.r, 0, TAU);
      ctx.lineWidth = roadWidth * 1.15;
      ctx.stroke();
    }

    if (roadWidth > 7) {
      ctx.save();
      ctx.strokeStyle = COLORS.lane;
      ctx.lineWidth = Math.max(1, scale * .0028);
      ctx.setLineDash([scale * .012, scale * .014]);
      ctx.beginPath();
      for (const [a, b] of EDGES) {
        const road = CENTER_GEOMETRY[a * NETWORK_SIZE + b];
        ctx.moveTo(x(road.x0), y(road.y0));
        ctx.lineTo(x(road.x1), y(road.y1));
      }
      for (const node of NODES) {
        ctx.moveTo(x(node.x) + scale * node.r, y(node.y));
        ctx.arc(x(node.x), y(node.y), scale * node.r, 0, TAU);
      }
      ctx.stroke();
      ctx.restore();
    }

    ctx.fillStyle = COLORS.island;
    for (const node of NODES) {
      ctx.beginPath();
      ctx.arc(x(node.x), y(node.y), Math.max(0, scale * node.r - roadWidth * .62), 0, TAU);
      ctx.fill();
    }

    if (((options.inner ?? 0) > 0 || depth < 0) && depth < 4) {
      NODES.forEach((node, nodeIndex) => {
        const radius = scale * node.r;
        if (radius < 9) return;
        const childAlpha = depth < 0 && nodeIndex === ZOOM_NODE
          ? 1
          : options.inner * smooth(9, 40, radius);
        if (childAlpha <= .01) return;
        ctx.save();
        ctx.beginPath();
        ctx.arc(x(node.x), y(node.y), Math.max(0, radius - roadWidth * .62), 0, TAU);
        ctx.clip();
        ctx.globalAlpha = inheritedAlpha * childAlpha;
        renderNetwork({
          ox: x(node.x),
          oy: y(node.y),
          scale: radius * INNER_SCALE,
        }, depth + 1, options);
        ctx.restore();
      });
      ctx.globalAlpha = inheritedAlpha * ownAlpha;
    }

    if (closure && depth === 0 && options.closure) {
      ctx.save();
      ctx.globalAlpha = inheritedAlpha * ownAlpha * (options.closureAlpha ?? 1);
      const road = CENTER_GEOMETRY[closure[0] * NETWORK_SIZE + closure[1]];
      const middleX = x((road.x0 + road.x1) / 2);
      const middleY = y((road.y0 + road.y1) / 2);
      ctx.save();
      ctx.translate(middleX, middleY);
      ctx.rotate(Math.atan2(road.uy, road.ux) + Math.PI / 2);
      const barrierLength = roadWidth * 1.9;
      const barrierWidth = Math.max(3, roadWidth * .32);
      for (let i = 0; i < 6; i += 1) {
        ctx.fillStyle = i % 2 ? '#f2f2f2' : COLORS.red;
        ctx.fillRect(-barrierLength / 2 + i * barrierLength / 6, -barrierWidth / 2, barrierLength / 6, barrierWidth);
      }
      ctx.restore();
      ctx.font = `500 ${Math.max(10, Math.min(13, scale * .032))}px ui-monospace`;
      ctx.fillStyle = COLORS.red;
      ctx.textAlign = 'center';
      ctx.fillText('ROAD CLOSED', middleX, middleY - roadWidth * 1.6);
      ctx.restore();
    }

    const carLength = scale * .042;
    const carWidth = scale * .022;
    if (carLength >= 1.3 && options.style) {
      for (const car of cars) {
        const style = options.style(car);
        if (!style) continue;
        const position = carPosition(car);
        drawCar(
          x(position.x),
          y(position.y),
          position.heading,
          carLength,
          carWidth,
          style.color,
          style.alpha,
          depth <= 0 ? style.glow : 0,
        );
      }
    }

    if (options.labels) {
      const labels = LABELS[mod(depth + (options.cycle || 0), LABELS.length)];
      NODES.forEach((node, nodeIndex) => {
        const radius = scale * node.r;
        if (radius < 16 || radius > 260) return;
        const alpha = smooth(16, 26, radius) * (1 - smooth(180, 260, radius));
        const fontSize = Math.max(10, Math.min(15, radius * .3));
        ctx.save();
        ctx.globalAlpha = inheritedAlpha * ownAlpha * alpha * (options.labelAlpha ?? 1);
        ctx.font = `500 ${fontSize}px ui-monospace`;
        ctx.textAlign = 'center';
        ctx.fillStyle = COLORS.label;
        ctx.fillText(labels[nodeIndex], x(node.x), y(node.y) + radius + roadWidth * .7 + fontSize + 2);
        ctx.restore();
      });
    }
    ctx.globalAlpha = inheritedAlpha;
  }

  function drawTrails(transform, filter, count, lineWidth, alpha) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    for (const car of cars) {
      if (!filter(car)) continue;
      const history = car.history;
      const length = Math.min(count, history.length);
      if (length < 2) continue;
      const start = history.length - length;
      const chunks = 7;
      const perChunk = Math.ceil(length / chunks);
      ctx.strokeStyle = SCIENTISTS[car.scientist];
      ctx.lineWidth = typeof lineWidth === 'function' ? lineWidth(car) : lineWidth;
      for (let chunk = 0; chunk < chunks; chunk += 1) {
        const from = start + chunk * perChunk;
        const to = Math.min(history.length - 1, from + perChunk);
        if (to <= from) break;
        ctx.globalAlpha = alpha * Math.pow((chunk + 1) / chunks, 1.6);
        ctx.beginPath();
        ctx.moveTo(
          transform.ox + transform.scale * history[from][0],
          transform.oy + transform.scale * history[from][1],
        );
        for (let index = from + 1; index <= to; index += 1) {
          ctx.lineTo(
            transform.ox + transform.scale * history[index][0],
            transform.oy + transform.scale * history[index][1],
          );
        }
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawLegend(items, alpha = 1) {
    const fontSize = Math.max(11, Math.min(15, width * .012));
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.font = `500 ${fontSize}px ui-monospace`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    let y = fontSize * 1.8;
    for (const [color, label] of items) {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(fontSize * 1.6, y, fontSize * .38, 0, TAU);
      ctx.fill();
      ctx.fillStyle = COLORS.label;
      ctx.fillText(label, fontSize * 2.5, y);
      y += fontSize * 1.7;
    }
    ctx.restore();
  }

  function drawPolylineProgress(points, progress, color, lineWidth) {
    if (progress <= 0 || points.length < 2) return;
    const lengths = points.slice(1).map(([x, y], index) => (
      Math.hypot(x - points[index][0], y - points[index][1])
    ));
    const total = lengths.reduce((sum, length) => sum + length, 0);
    let remaining = total * Math.min(1, progress);
    let tip = points[0];

    ctx.beginPath();
    ctx.moveTo(...points[0]);
    for (let index = 0; index < lengths.length && remaining > 0; index += 1) {
      const amount = Math.min(1, remaining / lengths[index]);
      const [fromX, fromY] = points[index];
      const [toX, toY] = points[index + 1];
      tip = [
        fromX + (toX - fromX) * amount,
        fromY + (toY - fromY) * amount,
      ];
      ctx.lineTo(...tip);
      remaining -= lengths[index];
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(...tip, Math.max(5, lineWidth * 1.45), 0, TAU);
    ctx.fill();
  }

  function drawWaterfall({ changing = false } = {}) {
    const stageNames = ['Ideate', 'Prototype', 'Build', 'Test', 'Deploy'];
    const availableHeight = Math.max(1, Math.min(height, getWaterfallHeight()));
    const boxWidth = Math.min(width * .15, 190);
    const boxHeight = Math.min(availableHeight * .14, 92);
    const marginX = width * .09;
    const marginY = availableHeight * .08;
    const stepX = (width - marginX * 2 - boxWidth) / (stageNames.length - 1);
    const stepY = (availableHeight - marginY * 2 - boxHeight) / (stageNames.length - 1);
    const reveal = reducedMotion ? 1 : smooth(0, WATERFALL_REVEAL_DURATION, elapsed);
    const fontSize = Math.max(13, Math.min(19, width * .016));
    ctx.save();
    stageNames.forEach((name, index) => {
      const local = Math.min(1, Math.max(0, reveal * stageNames.length - index));
      if (local <= 0) return;
      const x = marginX + index * stepX;
      const y = marginY + index * stepY;
      ctx.globalAlpha = local;
      ctx.fillStyle = COLORS.gear;
      ctx.strokeStyle = COLORS.gearEdge;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(x, y, boxWidth, boxHeight, 10);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = COLORS.foreground;
      ctx.font = `650 ${fontSize}px system-ui`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(name, x + boxWidth / 2, y + boxHeight / 2);

      if (index === stageNames.length - 1) return;
      const nextX = marginX + (index + 1) * stepX;
      const nextY = marginY + (index + 1) * stepY;
      const lineStartX = x + boxWidth / 2;
      const lineStartY = y + boxHeight;
      const lineEndX = nextX;
      const lineEndY = nextY + boxHeight / 2;
      ctx.strokeStyle = COLORS.plan;
      ctx.beginPath();
      ctx.moveTo(lineStartX, lineStartY);
      ctx.lineTo(lineStartX, lineEndY);
      ctx.lineTo(lineEndX, lineEndY);
      ctx.stroke();
      const arrowSize = 7;
      ctx.beginPath();
      ctx.moveTo(lineEndX - arrowSize, lineEndY - arrowSize * .7);
      ctx.lineTo(lineEndX, lineEndY);
      ctx.lineTo(lineEndX - arrowSize, lineEndY + arrowSize * .7);
      ctx.stroke();
    });

    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.globalCompositeOperation = 'lighter';
    if (changing) {
      const radius = Math.min(boxHeight * .55, 48);
      const orbit = Array.from({ length: 18 }, (_, index) => {
        const angle = -Math.PI / 2 + index / 17 * TAU * 1.7;
        return [
          centers[1][0] + Math.cos(angle) * radius,
          centers[1][1] + Math.sin(angle) * radius,
        ];
      });
      const paths = [
        {
          delay: .4,
          color: SCIENTISTS[0],
          points: [centers[0], centers[1], ...orbit],
        },
        {
          delay: 1.4,
          color: SCIENTISTS[1],
          points: [centers[3], centers[2], centers[1]],
        },
        {
          delay: 2.2,
          color: SCIENTISTS[2],
          points: [centers[0], centers[2], centers[4]],
        },
        {
          delay: 3,
          color: SCIENTISTS[3],
          points: [
            centers[2],
            [centers[2][0], top - boxHeight * 1.15],
            [centers[3][0], top - boxHeight * 1.4],
          ],
        },
        {
          delay: 3.8,
          color: SCIENTISTS[4],
          points: [
            centers[3],
            [centers[3][0] + gap, top + boxHeight * 2.05],
            [centers[4][0] + boxWidth * .55, top + boxHeight * 2.35],
          ],
        },
      ];
      paths.forEach(({ delay, color, points }) => {
        const progress = reducedMotion ? 1 : smooth(delay, delay + 2.8, elapsed);
        ctx.globalAlpha = .82;
        drawPolylineProgress(
          points,
          progress,
          color,
          Math.max(2.5, width * .003),
        );
      });
    }
    ctx.restore();
  }

  function drawPipelineArrow(positions, radius, progress, alpha) {
    if (progress <= 0) return;
    const segmentLength = Math.hypot(
      positions[1][0] - positions[0][0],
      positions[1][1] - positions[0][1],
    );
    const totalLength = segmentLength * (positions.length - 1);
    const endIndex = Math.min(
      positions.length - 2,
      Math.floor(progress * (positions.length - 1)),
    );
    const localProgress = progress >= 1
      ? 1
      : progress * (positions.length - 1) - endIndex;
    const [fromX, fromY] = positions[endIndex];
    const [toX, toY] = positions[endIndex + 1];
    const tipX = fromX + (toX - fromX) * localProgress;
    const tipY = fromY + (toY - fromY) * localProgress;
    const angle = Math.atan2(toY - fromY, toX - fromX);

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = COLORS.pipeline;
    ctx.fillStyle = COLORS.pipeline;
    ctx.lineWidth = Math.max(6, radius * .075);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.shadowColor = 'rgba(155,229,100,.45)';
    ctx.shadowBlur = 12;
    ctx.setLineDash([totalLength * progress, totalLength]);
    ctx.beginPath();
    positions.forEach(([x, y], index) => {
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    const arrowLength = Math.max(14, radius * .22);
    const arrowWidth = arrowLength * .55;
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(
      tipX - Math.cos(angle) * arrowLength + Math.sin(angle) * arrowWidth,
      tipY - Math.sin(angle) * arrowLength - Math.cos(angle) * arrowWidth,
    );
    ctx.lineTo(
      tipX - Math.cos(angle) * arrowLength - Math.sin(angle) * arrowWidth,
      tipY - Math.sin(angle) * arrowLength + Math.cos(angle) * arrowWidth,
    );
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawGears(dt, {
    jammed = false,
    alpha = 1,
    pipelineProgress = 0,
    pipelineAlpha = 1,
  } = {}) {
    const radius = Math.min(width / 7.6, height / 4.9);
    const horizontal = 1.15 * radius;
    const vertical = 1.636 * radius;
    const centerX = width / 2;
    const centerY = height * .43;
    const positions = [
      [centerX - 2 * horizontal, centerY - vertical / 2],
      [centerX - horizontal, centerY + vertical / 2],
      [centerX, centerY - vertical / 2],
      [centerX + horizontal, centerY + vertical / 2],
      [centerX + 2 * horizontal, centerY - vertical / 2],
    ];
    const names = ['Ideate', 'Prototype', 'Build', 'Test', 'Deploy'];
    const toothCount = 14;
    if (!jammed) gearAngle += .55 * dt;
    const angles = [gearAngle];
    for (let index = 0; index < 4; index += 1) {
      const direction = Math.atan2(
        positions[index + 1][1] - positions[index][1],
        positions[index + 1][0] - positions[index][0],
      );
      angles.push(-angles[index] + 2 * direction + Math.PI + Math.PI / toothCount);
    }

    ctx.save();
    ctx.globalAlpha = alpha;
    positions.forEach(([x, y], gearIndex) => {
      const shake = jammed && gearIndex === 3 && elapsed < 5.1
        ? Math.sin(elapsed * 80) * radius * .03
        : 0;
      ctx.save();
      ctx.translate(x + shake, y);
      ctx.beginPath();
      const pitch = TAU / toothCount;
      const outer = radius * 1.1;
      const inner = radius * .88;
      for (let tooth = 0; tooth < toothCount; tooth += 1) {
        const center = angles[gearIndex] + tooth * pitch;
        const points = [
          [inner, center - pitch * .32],
          [outer, center - pitch * .19],
          [outer, center + pitch * .19],
          [inner, center + pitch * .32],
        ];
        points.forEach(([pointRadius, angle], pointIndex) => {
          const pointX = pointRadius * Math.cos(angle);
          const pointY = pointRadius * Math.sin(angle);
          if (tooth === 0 && pointIndex === 0) ctx.moveTo(pointX, pointY);
          else ctx.lineTo(pointX, pointY);
        });
      }
      ctx.closePath();
      ctx.fillStyle = COLORS.gear;
      ctx.fill();
      ctx.lineWidth = Math.max(1.2, radius * .022);
      ctx.strokeStyle = jammed && gearIndex === 3 ? COLORS.red : COLORS.gearEdge;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(0, 0, radius * .62, 0, TAU);
      ctx.strokeStyle = 'rgba(93,108,130,.35)';
      ctx.stroke();

      const numeralSize = Math.max(34, radius * .62);
      ctx.rotate(gearIndex % 2 === 0 ? gearAngle : -gearAngle);
      ctx.font = `800 ${numeralSize}px system-ui`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(255,255,255,.06)';
      ctx.fillText(String(gearIndex + 1), radius * .025, radius * .025);
      ctx.fillStyle = jammed && gearIndex === 3 ? COLORS.red : COLORS.gearEdge;
      ctx.fillText(String(gearIndex + 1), 0, 0);
      ctx.restore();

      ctx.font = `650 ${Math.max(10, radius * .16)}px ui-monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = jammed && gearIndex === 3 ? COLORS.red : COLORS.foreground;
      ctx.fillText(names[gearIndex], x + shake, y + radius * .52);
    });
    drawPipelineArrow(positions, radius, pipelineProgress, pipelineAlpha);
    ctx.restore();
  }

  function followLeadCar() {
    const lead = carPosition(cars[0]);
    const follow = reducedMotion ? 1 : 1 / 20;
    camera.x += (lead.x - camera.x) * follow;
    camera.y += (lead.y - camera.y) * follow;
    camera.heading = lead.heading;
  }

  function drawHeadlights(transform, { view, reveal = 0, trailCount = 0 } = {}) {
    const lead = carPosition(cars[0]);
    const scale = view?.scale ?? transform.baseScale * 2.6;
    const closeTransform = view ?? {
      ox: width / 2 - scale * camera.x,
      oy: height / 2 - scale * camera.y,
      scale,
    };
    renderNetwork(closeTransform, 0, {
      labels: true,
      labelAlpha: 1 - reveal,
      style: car => ({
        color: SCIENTISTS[car.scientist],
        alpha: car.id === 0 ? 1 : .7 + .3 * reveal,
        glow: car.id === 0 ? 14 - 6 * reveal : 0,
      }),
    });

    if (trailCount > 1 && reveal > 0) {
      drawTrails(
        closeTransform,
        () => true,
        trailCount,
        car => Math.max(1, scale * (car.scientist === 0 ? .008 : .005)),
        .55 * reveal,
      );
    }

    const headlightX = closeTransform.ox + scale * lead.x;
    const headlightY = closeTransform.oy + scale * lead.y;
    if (reveal < 1) {
      maskContext.setTransform(dpr, 0, 0, dpr, 0, 0);
      maskContext.globalCompositeOperation = 'source-over';
      maskContext.clearRect(0, 0, width, height);
      maskContext.fillStyle = 'rgba(3,5,9,.93)';
      maskContext.fillRect(0, 0, width, height);
      maskContext.globalCompositeOperation = 'destination-out';
      const reach = scale * .5;
      const beam = maskContext.createRadialGradient(headlightX, headlightY, 0, headlightX, headlightY, reach);
      beam.addColorStop(0, 'rgba(0,0,0,1)');
      beam.addColorStop(.65, 'rgba(0,0,0,.85)');
      beam.addColorStop(1, 'rgba(0,0,0,0)');
      maskContext.fillStyle = beam;
      maskContext.beginPath();
      maskContext.moveTo(headlightX, headlightY);
      maskContext.arc(headlightX, headlightY, reach, lead.heading - .45, lead.heading + .45);
      maskContext.closePath();
      maskContext.fill();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.globalAlpha = 1 - reveal;
      ctx.drawImage(mask, 0, 0);
      ctx.globalAlpha = 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    drawCar(
      headlightX,
      headlightY,
      lead.heading,
      scale * .042,
      scale * .022,
      SCIENTISTS[0],
      1,
      14 - 6 * reveal,
    );

    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    ctx.fillStyle = COLORS.light;
    ctx.shadowColor = COLORS.light;
    ctx.shadowBlur = 8;
    ctx.globalAlpha = .85 * (1 - reveal);
    for (const car of cars) {
      const position = carPosition(car);
      const x = closeTransform.ox + scale * position.x;
      const y = closeTransform.oy + scale * position.y;
      if (x < -20 || x > width + 20 || y < -20 || y > height + 20) continue;

      const forwardX = Math.cos(position.heading);
      const forwardY = Math.sin(position.heading);
      const lateralX = -forwardY;
      const lateralY = forwardX;
      const frontOffset = scale * .02;
      const lateralOffset = scale * .007;
      const lampRadius = Math.max(1, scale * .004);
      for (const side of [-1, 1]) {
        ctx.beginPath();
        ctx.arc(
          x + forwardX * frontOffset + lateralX * lateralOffset * side,
          y + forwardY * frontOffset + lateralY * lateralOffset * side,
          lampRadius,
          0,
          TAU,
        );
        ctx.fill();
      }
    }
    ctx.restore();
  }

  function drawOutgoingYellow(transform, transition, amount) {
    if (!transition?.outgoingYellow.length || amount >= 1) return;
    const length = transform.scale * .042;
    const carWidth = transform.scale * .022;
    for (const position of transition.outgoingYellow) {
      drawCar(
        transform.ox + transform.scale * position.x,
        transform.oy + transform.scale * position.y,
        position.heading,
        length,
        carWidth,
        SCIENTISTS[0],
        1 - amount,
        10 * (1 - amount),
      );
    }
  }

  function draw(dt) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, width, height);
    const scene = SCENES[sceneIndex].key;
    const transform = baseTransform();
    if (composition) {
      ctx.clearRect(0, 0, width, height);
      renderNetwork(transform, 0, {});
      return;
    }
    const transition = sceneTransition;
    const transitionAmount = transition
      ? smooth(0, transition.duration, elapsed)
      : 1;

    if (scene === 'problem') {
      drawWaterfall();
    } else if (scene === 'gears') {
      drawGears(dt);
    } else if (scene === 'pipeline-gears') {
      drawGears(dt, {
        pipelineProgress: reducedMotion ? 1 : smooth(.8, 4.8, elapsed),
      });
    } else if (scene === 'first-loop') {
      const time = reducedMotion ? SKETCH_TIMING.duration : elapsed;
      if (time < SKETCH_TIMING.gearsEnd) {
        drawGears(reducedMotion ? 0 : dt, {
          alpha: 1 - smooth(0, SKETCH_TIMING.gearsEnd, time),
        });
      }
      drawSketch(ctx, transform, time);
    } else if (scene === 'city') {
      renderNetwork(transform, 0, {
        labels: true,
        style: car => ({
          color: transitionFromKey() === 'drivers'
            ? mixColor(SCIENTISTS[car.scientist], CITY_CAR, transitionAmount)
            : CITY_CAR,
          alpha: transitionFromKey() === 'drivers' ? 1 - .15 * transitionAmount : .85,
        }),
      });
    } else if (scene === 'drivers') {
      renderNetwork(transform, 0, {
        labels: true,
        style: car => ({
          color: transitionFromKey() === 'city'
            ? mixColor(CITY_CAR, SCIENTISTS[car.scientist], transitionAmount)
            : SCIENTISTS[car.scientist],
          alpha: transitionFromKey() === 'city' ? .85 + .15 * transitionAmount : 1,
        }),
      });
    } else if (scene === 'everywhere') {
      renderNetwork(transform, 0, {
        labels: true,
        style: car => {
          if (car.scientist === 0) {
            return {
              color: SCIENTISTS[0],
              alpha: transitionFromKey() === 'drivers' ? transitionAmount : 1,
              glow: 12 * (transitionFromKey() === 'drivers' ? transitionAmount : 1),
            };
          }
          return {
            color: transitionFromKey() === 'drivers'
              ? mixColor(SCIENTISTS[car.scientist], COLORS.plan, transitionAmount)
              : COLORS.plan,
            alpha: transitionFromKey() === 'drivers'
              ? 1 - .55 * transitionAmount
              : .45,
          };
        },
      });
      drawOutgoingYellow(transform, transition, transitionAmount);
      drawTrails(
        transform,
        car => car.scientist === 0,
        HISTORY_LIMIT,
        Math.max(1.5, transform.scale * .008),
        .85 * transitionAmount,
      );
      drawLegend([[SCIENTISTS[0], 'one scientist, many loops']], transitionAmount);
    } else if (scene === 'detour') {
      renderNetwork(transform, 0, {
        labels: true,
        closure: true,
        closureAlpha: transitionFromKey() === 'everywhere' ? transitionAmount : 1,
        style: car => {
          if (car.scientist === 0) {
            return {
              color: SCIENTISTS[0],
              alpha: 1,
              glow: 12,
            };
          }
          return {
            color: COLORS.plan,
            alpha: transitionFromKey() === 'everywhere'
              ? .45 + .5 * transitionAmount
              : .95,
          };
        },
      });
      drawOutgoingYellow(transform, transition, transitionAmount);
      drawTrails(
        transform,
        car => car.scientist === 0,
        transitionFromKey() === 'everywhere'
          ? Math.round(HISTORY_LIMIT + (90 - HISTORY_LIMIT) * transitionAmount)
          : 90,
        Math.max(1.2, transform.scale * .006),
        transitionFromKey() === 'everywhere'
          ? .85 + (.6 - .85) * transitionAmount
          : .6,
      );
      drawLegend(
        [[SCIENTISTS[0], 'steering'], [COLORS.plan, 'following the plan']],
        transitionFromKey() === 'everywhere' ? transitionAmount : 1,
      );
    } else if (scene === 'zoom') {
      const inner = reducedMotion ? 1 : smooth(.2, 1.6, elapsed);
      const progress = reducedMotion ? 0 : zoomProgress;
      const factor = Math.pow(ZOOM_SCALE, -progress);
      const scale = transform.baseScale * factor;
      const ox = width / 2 + transform.baseScale * (1 - factor) * ZOOM_X;
      const oy = height / 2 + transform.baseScale * (1 - factor) * ZOOM_Y;
      const parentScale = scale / ZOOM_SCALE;
      renderNetwork({
        ox: ox - parentScale * NODES[ZOOM_NODE].x,
        oy: oy - parentScale * NODES[ZOOM_NODE].y,
        scale: parentScale,
      }, -1, {
        inner,
        labels: true,
        cycle: reducedMotion ? 2 : zoomCycle,
        style: car => ({ color: SCIENTISTS[car.scientist], alpha: 1 }),
      });
    } else if (scene === 'headlights') {
      drawHeadlights(transform);
    } else if (scene === 'pull') {
      const time = reducedMotion ? ENDING_TIMING.duration : elapsed;
      const pullback = smooth(0, ENDING_TIMING.duration, time);
      const startScale = transform.baseScale * 2.6;
      const finalScale = Math.min(width * .095, height * .16);
      const scale = startScale * (finalScale / startScale) ** pullback;
      const pullTransform = {
        ox: width / 2 - scale * pullOrigin.x * (1 - pullback),
        oy: height * (.5 + .22 * pullback) - scale * pullOrigin.y * (1 - pullback),
        scale,
      };
      drawHeadlights(transform, {
        view: pullTransform,
        reveal: smooth(0, ENDING_TIMING.maskFade, time),
        trailCount: time > ENDING_TIMING.trailStart ? pullTrailCount : 0,
      });
    }
  }

  function frame(time) {
    if (!running) return;
    const dt = lastTime ? Math.min(.05, (time - lastTime) / 1000) : 0;
    lastTime = time;
    if (!sceneSettled) elapsed += dt;
    if (!reducedMotion) {
      if (currentSceneKey() !== 'first-loop') simulate(dt);
      if (currentSceneKey() === 'headlights') followLeadCar();
      if (currentSceneKey() === 'pull') {
        pullTrailCount = elapsed > ENDING_TIMING.trailStart
          ? Math.min(HISTORY_LIMIT, pullTrailCount + 1)
          : 0;
        if (sceneSettled && elapsed === 0) {
          followLeadCar();
          pullOrigin = { ...camera };
        }
      }
      if (SCENES[sceneIndex].key === 'zoom' && elapsed > ZOOM_START_DELAY) {
        const zoomElapsed = Math.min(
          elapsed - ZOOM_START_DELAY, ZOOM_CYCLE_DURATION * ZOOM_CYCLES,
        );
        zoomCycle = Math.min(ZOOM_CYCLES, Math.floor(zoomElapsed / ZOOM_CYCLE_DURATION));
        zoomProgress = zoomCycle >= ZOOM_CYCLES
          ? 0 : (zoomElapsed % ZOOM_CYCLE_DURATION) / ZOOM_CYCLE_DURATION;
        if (elapsed >= SCENES[sceneIndex].duration) {
          zoomCycle = ZOOM_CYCLES;
          zoomProgress = 0;
        }
      }
    }
    draw(dt);
    onProgress(
      reducedMotion || sceneSettled ? 1 : elapsed / SCENES[sceneIndex].duration,
      reducedMotion ? SCENES[sceneIndex].duration : elapsed,
    );
    if (currentSceneKey() === 'first-loop'
      && (reducedMotion || sceneSettled || elapsed >= SKETCH_TIMING.duration)) {
      running = false;
      frameId = 0;
      return;
    }
    frameId = requestAnimationFrame(frame);
  }

  resetCars();
  resize();

  return {
    setScene(index) {
      if (!SCENES[index]) throw new RangeError(`Unknown City of Loops scene ${index}`);
      resetScene(index);
    },
    transitionToScene(index, fromIndex) {
      if (!SCENES[index]) throw new RangeError(`Unknown City of Loops scene ${index}`);
      resetScene(index, { preserveTraffic: true, fromIndex });
    },
    finishScene(direction = 1) {
      const duration = SCENES[sceneIndex].duration;
      if (reducedMotion || sceneSettled || elapsed >= duration) return false;
      elapsed = direction < 0 ? 0 : duration;
      sceneSettled = true;
      sceneTransition = null;
      if (currentSceneKey() === 'zoom') {
        zoomCycle = direction < 0 ? 0 : ZOOM_CYCLES;
        zoomProgress = 0;
      }
      draw(0);
      onProgress(1, elapsed);
      return true;
    },
    start() {
      resize();
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(resize, 0);
      if (running) return;
      running = true;
      lastTime = 0;
      frameId = requestAnimationFrame(frame);
    },
    stop() {
      running = false;
      cancelAnimationFrame(frameId);
      window.clearTimeout(resizeTimer);
      frameId = 0;
      resizeTimer = 0;
      lastTime = 0;
    },
    destroy() {
      this.stop();
      observer.disconnect();
    },
  };
}
