const TAU = Math.PI * 2;

export const NODES = [
  [-.72, -.55, .13], [-.15, -.72, .11], [.5, -.6, .14],
  [-.8, .1, .1], [-.15, -.05, .17], [.62, .05, .12],
  [-.55, .68, .13], [.1, .62, .1], [.7, .66, .13],
].map(([x, y, r]) => ({ x, y, r }));

export const EDGES = [
  [0, 1], [1, 2], [0, 3], [0, 4], [1, 4], [2, 5], [2, 4], [3, 4],
  [3, 6], [4, 5], [4, 7], [5, 8], [6, 7], [7, 8], [4, 6], [5, 7],
];

export const NODE_NAMES = [
  'upper-left', 'upper-middle', 'upper-right', 'middle-left', 'center',
  'middle-right', 'lower-left', 'lower-middle', 'lower-right',
];

export function cityTransform(width, height) {
  const scale = Math.min(width / 2.15, height / 2);
  return { ox: width / 2, oy: height / 2, scale, baseScale: scale };
}

const strokes = [];
const loopOrder = [4, 1, 2, 0, 5, 3, 7, 6, 8];
const arrowHours = [10.6, 12.5, 13.4, 11.2, 12.1, 10.2, 13.8, 11.7, 12.9];
for (const [order, index] of loopOrder.entries()) {
  const node = NODES[index];
  const turns = index === 4 ? 3 : 1;
  const points = Array.from({ length: turns * 96 + 1 }, (_, sample) => {
    const travel = sample / 96 * TAU;
    const angle = (arrowHours[index] - 3) / 12 * TAU + travel;
    const lapDrift = index === 4
      ? .055 * Math.sin(travel * .63 + .4) + .025 * Math.sin(travel * 1.17)
      : 0;
    const radius = node.r * (
      1.06 + .035 * Math.sin(angle * 3 + index)
      + .025 * Math.sin(angle * 5.3 + index * 2)
      + lapDrift
    );
    return [
      node.x + Math.cos(angle) * radius + .003 * Math.sin(angle * .7)
        + (index === 4 ? .006 * Math.sin(travel * .55) : 0),
      node.y + Math.sin(angle) * radius
        + (index === 4 ? .004 * Math.sin(travel * .72) : 0),
    ];
  });
  const start = order === 0 ? .2 : order < 3 ? 3.6 + (order - 1) * .45 : 5.7 + (order - 3) * .32;
  const duration = order === 0 ? 2.8 : order < 3 ? 1.05 : 1.2 + (order % 3) * .18;
  const id = `loop-${NODE_NAMES[index]}`;
  strokes.push({ id, points, start, duration, alpha: order === 0 ? 1 : .8 });
  const tip = points.at(-1);
  const previous = points.at(-2);
  const angle = Math.atan2(tip[1] - previous[1], tip[0] - previous[0]);
  const size = node.r * (.25 + .045 * Math.sin(index * 1.7 + .3));
  const wing = (spread, length, bend) => Array.from({ length: 9 }, (_, sample) => {
    const t = sample / 8;
    const heading = angle + spread;
    const bow = Math.sin(Math.PI * t) * length * bend;
    return [
      tip[0] - Math.cos(heading) * length * t - Math.sin(heading) * bow,
      tip[1] - Math.sin(heading) * length * t + Math.cos(heading) * bow,
    ];
  });
  const leftWing = wing(
    -(.42 + .12 * Math.sin(index * .9)),
    size * (1 + .17 * Math.cos(index)),
    .14 + .07 * Math.sin(index * 1.4),
  );
  const rightWing = wing(
    .63 + .14 * Math.cos(index * 1.3),
    size * (.82 + .14 * Math.sin(index * 2)),
    -.08 - .09 * Math.cos(index * .8),
  );
  strokes.push({
    id: `${id}-arrow`,
    points: [...leftWing.reverse(), ...rightWing.slice(1)],
    start: start + duration,
    duration: .18,
    alpha: order === 0 ? 1 : .8,
  });
}

for (const [index, [a, b]] of EDGES.entries()) {
  const from = NODES[a];
  const to = NODES[b];
  const distance = Math.hypot(to.x - from.x, to.y - from.y);
  const ux = (to.x - from.x) / distance;
  const uy = (to.y - from.y) / distance;
  const triangleOrder = [[1, 4], [1, 2], [2, 4]].findIndex(
    edge => edge[0] === a && edge[1] === b,
  );
  const points = Array.from({ length: 49 }, (_, sample) => {
    const t = sample / 48;
    const along = from.r + (distance - from.r - to.r) * t;
    const wobble = .009 * Math.sin(t * Math.PI) * Math.sin(t * 9 + index);
    return [from.x + ux * along - uy * wobble, from.y + uy * along + ux * wobble];
  });
  strokes.push({
    id: `road-${NODE_NAMES[a]}-${NODE_NAMES[b]}`,
    points,
    start: triangleOrder >= 0 ? 5.1 + triangleOrder * .28 : 6.4 + index * .13,
    duration: .7 + (index % 4) * .16,
    alpha: .7,
  });
}

export const SKETCH_STROKES = strokes;
export const SKETCH_TIMING = {
  gearsEnd: 3.6,
  cityFade: 1,
  expansion: 3.6,
  duration: Math.max(...strokes.map(stroke => stroke.start + stroke.duration)),
};

export function drawSketch(ctx, transform, elapsed) {
  ctx.save();
  ctx.translate(transform.ox, transform.oy);
  ctx.scale(transform.scale, transform.scale);
  ctx.strokeStyle = '#ff5a52';
  ctx.lineWidth = .009;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  for (const stroke of SKETCH_STROKES) {
    const progress = Math.min(1, Math.max(0, (elapsed - stroke.start) / stroke.duration));
    if (progress === 0) continue;
    const position = progress * (stroke.points.length - 1);
    const last = Math.floor(position);
    ctx.globalAlpha = stroke.alpha;
    ctx.beginPath();
    ctx.moveTo(...stroke.points[0]);
    for (let index = 1; index <= last; index += 1) ctx.lineTo(...stroke.points[index]);
    if (last < stroke.points.length - 1) {
      const a = stroke.points[last];
      const b = stroke.points[last + 1];
      const part = position - last;
      ctx.lineTo(a[0] + (b[0] - a[0]) * part, a[1] + (b[1] - a[1]) * part);
    }
    ctx.stroke();
  }
  ctx.restore();
}
