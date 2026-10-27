// World dimensions are millimetres; time is seconds.
const R = 28.575;
// Match the intro's fixed 1.3rem balls rather than scaling them with table width.
const BALL_DIAMETER_REM = 1.3;
const LONG = 1856;
const SHORT = 1028;
const RAIL = 100;
const CUSH = 22;
const E_BALL = .95;
const E_RAIL = .75;
const ROLL = 200;
const DRAG = .6;
const H = 1 / 2400;
const CORNER_GAP = 68;
const SIDE_GAP = 48;
const CUE_HOLD = .12;
const CUE_DRAWBACK = .24;
const CONTACT = CUE_DRAWBACK + .1;
const CUE_FADE = .3;
const COSD = Math.cos(.43);
const SIND = Math.sin(.43);
const STRIPE = .52;
const T = 64;
const BALL_RGB = [
  [246, 244, 236], [242, 184, 15], [26, 63, 163],
  [196, 30, 42], [74, 42, 127], [234, 106, 26],
  [19, 122, 72], [124, 29, 35], [22, 22, 22],
];

function rngFrom(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffle(values, random) {
  for (let i = values.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [values[i], values[j]] = [values[j], values[i]];
  }
  return values;
}

function qmul(a, b) {
  return [
    a[0]*b[0] - a[1]*b[1] - a[2]*b[2] - a[3]*b[3],
    a[0]*b[1] + a[1]*b[0] + a[2]*b[3] - a[3]*b[2],
    a[0]*b[2] - a[1]*b[3] + a[2]*b[0] + a[3]*b[1],
    a[0]*b[3] + a[1]*b[2] - a[2]*b[1] + a[3]*b[0],
  ];
}

function randQuat(random) {
  const u1 = random(), u2 = random()*Math.PI*2, u3 = random()*Math.PI*2;
  const a = Math.sqrt(1 - u1), b = Math.sqrt(u1);
  return [a*Math.sin(u2), a*Math.cos(u2), b*Math.sin(u3), b*Math.cos(u3)];
}

function context2d(canvas, options) {
  const context = canvas.getContext('2d', options);
  if (!context) throw new Error('The billiards slide requires a 2D canvas context.');
  return context;
}

export class BilliardsSimulation {
  constructor(seed, radius = R) {
    this.seed = seed;
    this.setRadius(radius);
  }

  setRadius(radius) {
    if (!Number.isFinite(radius) || radius <= 0) {
      throw new RangeError('The billiards ball radius must be a positive finite number.');
    }
    if (this.radius === radius) return;
    const ticks = this.ticks ?? 0;
    const resting = this.resting;
    this.radius = radius;
    const cornerGap = Math.max(CORNER_GAP, radius*1.7);
    const sideGap = Math.max(SIDE_GAP, radius*1.2);
    this.walls = [
      { ax: 0, pos: 0, sgn: 1, len: SHORT },
      { ax: 0, pos: LONG, sgn: -1, len: SHORT },
      { ax: 1, pos: 0, sgn: 1, len: LONG },
      { ax: 1, pos: SHORT, sgn: -1, len: LONG },
    ];
    this.points = [];
    for (const wall of this.walls) {
      wall.ranges = wall.len === LONG
        ? [[cornerGap, LONG/2 - sideGap], [LONG/2 + sideGap, LONG - cornerGap]]
        : [[cornerGap, SHORT - cornerGap]];
      for (const range of wall.ranges) {
        for (const t of range) {
          this.points.push(wall.ax === 0 ? { x: wall.pos, y: t } : { x: t, y: wall.pos });
        }
      }
    }
    const cornerRadius = Math.max(44, radius*1.1);
    const sideRadius = Math.max(42, radius*1.1);
    this.pockets = [
      { x: -10, y: -10, r: cornerRadius }, { x: LONG + 10, y: -10, r: cornerRadius },
      { x: -10, y: SHORT + 10, r: cornerRadius }, { x: LONG + 10, y: SHORT + 10, r: cornerRadius },
      { x: LONG/2, y: -14, r: sideRadius }, { x: LONG/2, y: SHORT + 14, r: sideRadius },
    ];
    this.reset();
    // Reconstruct the same point in the seeded break when responsive sizing changes.
    for (let i = 0; i < ticks && !this.resting; i++) this.step();
    if (resting) this.finish();
  }

  reset(seed = this.seed) {
    if (!Number.isInteger(seed) || seed < 0 || seed > 0xFFFFFFFF) {
      throw new RangeError('breakSeed must be an integer between 0 and 4294967295.');
    }
    this.seed = seed;
    const R = this.radius;
    const random = rngFrom(seed);
    const slots = [];
    const d = R + .08;
    const footX = Math.min(LONG*3/4, LONG - R - 4*Math.sqrt(3)*d - .5);
    for (let row = 0; row < 5; row++) {
      for (let j = 0; j <= row; j++) {
        slots.push({
          x: footX + row*Math.sqrt(3)*d + (random() - .5)*.5,
          y: SHORT/2 + (j - row/2)*2*d + (random() - .5)*.5,
        });
      }
    }
    const solids = shuffle([2, 3, 4, 5, 6, 7], random);
    const stripes = shuffle([9, 10, 11, 12, 13, 14, 15], random);
    const numbers = new Array(15);
    numbers[0] = 1;
    numbers[4] = 8;
    const solid = solids.pop(), stripe = stripes.pop();
    [numbers[10], numbers[14]] = random() < .5 ? [solid, stripe] : [stripe, solid];
    const rest = shuffle(solids.concat(stripes), random);
    let index = 0;
    for (let i = 0; i < 15; i++) {
      if (numbers[i] === undefined) numbers[i] = rest[index++];
    }
    const makeBall = (n, x, y) => ({
      n, x, y, vx: 0, vy: 0, q: randQuat(random), state: 'table', ft: 0,
    });
    const lateral = (random() - .5)*SHORT*.55;
    this.cueBall = makeBall(0, LONG/4, SHORT/2 + lateral);
    this.balls = [this.cueBall, ...slots.map((slot, i) => makeBall(numbers[i], slot.x, slot.y))];
    this.cueStart = { x: this.cueBall.x, y: this.cueBall.y };
    let dx = slots[0].x - this.cueBall.x, dy = slots[0].y - this.cueBall.y;
    const length = Math.hypot(dx, dy);
    dx /= length;
    dy /= length;
    const angle = (random() - .5)*.012;
    this.cueDir = {
      x: dx*Math.cos(angle) - dy*Math.sin(angle),
      y: dx*Math.sin(angle) + dy*Math.cos(angle),
    };
    this.cueSpeed = 9200 + random()*3000;
    this.ticks = 0;
    this.strikeT = -CUE_HOLD;
    this.struck = false;
    this.resting = false;
  }

  step() {
    if (this.resting) return;
    const R = this.radius;
    this.strikeT = ++this.ticks*H - CUE_HOLD;
    if (!this.struck && this.strikeT >= CONTACT) {
      this.struck = true;
      this.cueBall.vx = this.cueDir.x*this.cueSpeed;
      this.cueBall.vy = this.cueDir.y*this.cueSpeed;
    }
    const active = this.balls.filter(ball => ball.state === 'table');
    for (const ball of active) {
      const speed = Math.hypot(ball.vx, ball.vy);
      if (speed === 0) continue;
      ball.x += ball.vx*H;
      ball.y += ball.vy*H;
      const angle = speed*H/R, s = Math.sin(angle/2);
      ball.q = qmul([Math.cos(angle/2), ball.vy/speed*s, -ball.vx/speed*s, 0], ball.q);
    }
    for (let i = 0; i < active.length; i++) {
      const a = active[i];
      for (let j = i + 1; j < active.length; j++) {
        const b = active[j];
        const dx = b.x - a.x, dy = b.y - a.y, distance2 = dx*dx + dy*dy;
        if (distance2 >= 4*R*R || distance2 === 0) continue;
        const distance = Math.sqrt(distance2), nx = dx/distance, ny = dy/distance;
        const overlap = (2*R - distance)/2;
        a.x -= nx*overlap;
        a.y -= ny*overlap;
        b.x += nx*overlap;
        b.y += ny*overlap;
        const relative = (b.vx - a.vx)*nx + (b.vy - a.vy)*ny;
        if (relative < 0) {
          const impulse = -(1 + E_BALL)*relative/2;
          a.vx -= impulse*nx;
          a.vy -= impulse*ny;
          b.vx += impulse*nx;
          b.vy += impulse*ny;
        }
      }
    }
    for (const ball of active) {
      for (const wall of this.walls) {
        const coord = wall.ax === 0 ? ball.x : ball.y;
        const along = wall.ax === 0 ? ball.y : ball.x;
        const distance = (coord - wall.pos)*wall.sgn;
        if (distance >= R || !wall.ranges.some(([a, b]) => along >= a && along <= b)) continue;
        const normalVelocity = (wall.ax === 0 ? ball.vx : ball.vy)*wall.sgn;
        if (wall.ax === 0) {
          ball.x = wall.pos + wall.sgn*R;
          if (normalVelocity < 0) {
            ball.vx = -normalVelocity*E_RAIL*wall.sgn;
            ball.vy *= .96;
          }
        } else {
          ball.y = wall.pos + wall.sgn*R;
          if (normalVelocity < 0) {
            ball.vy = -normalVelocity*E_RAIL*wall.sgn;
            ball.vx *= .96;
          }
        }
      }
      for (const point of this.points) {
        const dx = ball.x - point.x, dy = ball.y - point.y, distance2 = dx*dx + dy*dy;
        if (distance2 >= R*R || distance2 === 0) continue;
        const distance = Math.sqrt(distance2), nx = dx/distance, ny = dy/distance;
        ball.x = point.x + nx*R;
        ball.y = point.y + ny*R;
        const normalVelocity = ball.vx*nx + ball.vy*ny;
        if (normalVelocity < 0) {
          ball.vx -= (1 + E_RAIL)*normalVelocity*nx;
          ball.vy -= (1 + E_RAIL)*normalVelocity*ny;
        }
      }
      const gone = this.walls.some(wall =>
        ((wall.ax === 0 ? ball.x : ball.y) - wall.pos)*wall.sgn < -.35*R)
        || this.pockets.some(pocket => Math.hypot(ball.x - pocket.x, ball.y - pocket.y) < pocket.r - R*.55);
      if (gone) {
        const pocket = this.pockets.reduce((best, candidate) =>
          Math.hypot(ball.x - candidate.x, ball.y - candidate.y)
            < Math.hypot(ball.x - best.x, ball.y - best.y) ? candidate : best);
        Object.assign(ball, {
          state: 'falling', ft: 0, fx: ball.x, fy: ball.y, px: pocket.x, py: pocket.y, vx: 0, vy: 0,
        });
        continue;
      }
      const speed = Math.hypot(ball.vx, ball.vy);
      if (speed > 0) {
        const deceleration = (ROLL + DRAG*speed)*H;
        if (speed <= deceleration || speed < 3) ball.vx = ball.vy = 0;
        else {
          const factor = (speed - deceleration)/speed;
          ball.vx *= factor;
          ball.vy *= factor;
        }
      }
    }
    for (const ball of this.balls) {
      if (ball.state !== 'falling') continue;
      ball.ft += H;
      if (ball.ft >= .3) ball.state = 'gone';
    }
    this.resting = this.struck && this.strikeT > CONTACT + CUE_FADE && !this.balls.some(ball =>
      ball.state === 'falling' || (ball.state === 'table' && (ball.vx !== 0 || ball.vy !== 0)));
  }

  finish() {
    // A safety bound makes lifecycle settlement finite even if the physics regresses.
    for (let i = 0; !this.resting && i < 60/H; i++) this.step();
    if (!this.resting) throw new Error('The billiards break did not come to rest within 60 seconds.');
  }
}

export class BilliardsTable {
  constructor(canvas, seed, { onProgress } = {}) {
    this.canvas = canvas;
    this.ctx = context2d(canvas);
    this.simulation = new BilliardsSimulation(seed);
    this.onProgress = onProgress;
    this.bg = document.createElement('canvas');
    this.bgx = context2d(this.bg);
    this.glyphs = [null];
    const glyphCanvas = document.createElement('canvas');
    glyphCanvas.width = glyphCanvas.height = T;
    const g = context2d(glyphCanvas, { willReadFrequently: true });
    for (let n = 1; n <= 15; n++) {
      g.clearRect(0, 0, T, T);
      g.fillStyle = '#000';
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      g.font = `bold ${n > 9 ? 29 : 37}px Arial, Helvetica, sans-serif`;
      g.fillText(String(n), T/2, T/2 + 2);
      if (n === 6 || n === 9) g.fillRect(T/2 - 9, 50, 18, 3.5);
      const data = g.getImageData(0, 0, T, T).data;
      this.glyphs.push(Uint8Array.from({ length: T*T }, (_, i) => data[i*4 + 3]));
    }
    this.frameId = null;
    this.accumulator = 0;
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas);
  }

  reset() {
    this.stop();
    this.simulation.reset();
    this.accumulator = 0;
    this.render();
  }

  play() {
    this.reset();
    this.resize();
    this.last = null;
    const frame = now => {
      this.frameId = null;
      if (this.last !== null) this.accumulator += Math.min(.05, (now - this.last)/1000);
      this.last = now;
      while (this.accumulator >= H && !this.simulation.resting) {
        this.simulation.step();
        this.accumulator -= H;
      }
      this.render();
      if (!this.simulation.resting) this.frameId = requestAnimationFrame(frame);
    };
    this.frameId = requestAnimationFrame(frame);
  }

  stop() {
    if (this.frameId !== null) cancelAnimationFrame(this.frameId);
    this.frameId = null;
  }

  finish() {
    this.stop();
    this.simulation.finish();
    this.resize();
    this.render();
  }

  get running() {
    return this.frameId !== null;
  }

  dispose() {
    this.stop();
    this.observer.disconnect();
  }

  resize() {
    const { width, height } = this.canvas.getBoundingClientRect();
    if (width <= 0 || height <= 0) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    const pixelWidth = Math.round(width*dpr), pixelHeight = Math.round(height*dpr);
    if (this.canvas.width === pixelWidth && this.canvas.height === pixelHeight && this.scale) return;
    this.canvas.width = pixelWidth;
    this.canvas.height = pixelHeight;
    this.scale = Math.min(pixelWidth/(LONG + 2*RAIL), pixelHeight/(SHORT + 2*RAIL));
    this.ox = (pixelWidth - LONG*this.scale)/2;
    this.oy = (pixelHeight - SHORT*this.scale)/2;
    const ballDiameter = BALL_DIAMETER_REM*parseFloat(getComputedStyle(document.documentElement).fontSize);
    this.simulation.setRadius(ballDiameter*dpr/(2*this.scale));
    if (this.onProgress && this.progressRadius !== this.simulation.radius) {
      // The seeded simulation supplies an exact endpoint, including cue and pocket motion.
      const completed = new BilliardsSimulation(this.simulation.seed, this.simulation.radius);
      completed.finish();
      this.progressTicks = completed.ticks;
      this.progressRadius = this.simulation.radius;
    }
    this.drawBackground();
    this.buildBallCache();
    this.render();
  }

  X(x) { return this.ox + x*this.scale; }
  Y(y) { return this.oy + y*this.scale; }

  drawBackground() {
    this.bg.width = this.canvas.width;
    this.bg.height = this.canvas.height;
    const g = this.bgx;
    g.setTransform(this.scale, 0, 0, this.scale, this.ox, this.oy);
    const roundedRect = (x, y, w, h, r) => {
      g.beginPath();
      g.roundRect(x, y, w, h, r);
    };
    let gradient = g.createLinearGradient(-RAIL, -RAIL, LONG + RAIL, SHORT + RAIL);
    gradient.addColorStop(0, '#5d321b');
    gradient.addColorStop(.5, '#7a4426');
    gradient.addColorStop(1, '#4b2716');
    roundedRect(-RAIL, -RAIL, LONG + 2*RAIL, SHORT + 2*RAIL, 70);
    g.fillStyle = gradient;
    g.fill();
    g.lineWidth = 6;
    g.strokeStyle = 'rgba(255,220,180,.12)';
    roundedRect(-RAIL + 10, -RAIL + 10, LONG + 2*RAIL - 20, SHORT + 2*RAIL - 20, 60);
    g.stroke();
    gradient = g.createRadialGradient(LONG/2, SHORT/2, 0, LONG/2, SHORT/2, LONG*.7);
    gradient.addColorStop(0, '#2f8460');
    gradient.addColorStop(1, '#1b5a40');
    g.fillStyle = gradient;
    g.fillRect(-CUSH, -CUSH, LONG + 2*CUSH, SHORT + 2*CUSH);
    for (const pocket of this.simulation.pockets) {
      gradient = g.createRadialGradient(pocket.x, pocket.y, pocket.r*.2, pocket.x, pocket.y, pocket.r);
      gradient.addColorStop(0, '#000');
      gradient.addColorStop(.85, '#0b0b0b');
      gradient.addColorStop(1, '#2a2a2a');
      g.fillStyle = gradient;
      g.beginPath();
      g.arc(pocket.x, pocket.y, pocket.r, 0, Math.PI*2);
      g.fill();
    }
    for (const wall of this.simulation.walls) {
      for (const [start, end] of wall.ranges) {
        const backStart = start - CUSH*(start === wall.ranges[0][0] ? .95 : .35);
        const backEnd = end + CUSH*(end === wall.ranges.at(-1)[1] ? .95 : .35);
        const back = wall.pos - wall.sgn*CUSH;
        const point = (along, coord) => wall.ax === 0 ? [coord, along] : [along, coord];
        g.beginPath();
        g.moveTo(...point(start, wall.pos));
        g.lineTo(...point(end, wall.pos));
        g.lineTo(...point(backEnd, back));
        g.lineTo(...point(backStart, back));
        g.closePath();
        g.fillStyle = '#17543a';
        g.fill();
        g.beginPath();
        g.moveTo(...point(start, wall.pos));
        g.lineTo(...point(end, wall.pos));
        g.lineWidth = 4;
        g.strokeStyle = 'rgba(160,230,190,.22)';
        g.stroke();
      }
    }
    const inset = CUSH + (RAIL - CUSH)/2;
    const diamond = (x, y) => {
      g.beginPath();
      g.moveTo(x, y - 11);
      g.lineTo(x + 6.6, y);
      g.lineTo(x, y + 11);
      g.lineTo(x - 6.6, y);
      g.closePath();
      g.fillStyle = 'rgba(239,230,210,.65)';
      g.fill();
    };
    for (const fraction of [.25, .75]) {
      diamond(LONG*fraction, -inset);
      diamond(LONG*fraction, SHORT + inset);
    }
    diamond(-inset, SHORT/2);
    diamond(LONG + inset, SHORT/2);
    g.setTransform(1, 0, 0, 1, 0, 0);
  }

  buildBallCache() {
    const radius = this.simulation.radius*this.scale;
    this.size = Math.ceil(radius*2) + 3;
    this.normals = [];
    let lx = -.35, ly = -.45, lz = -.82;
    const lightLength = Math.hypot(lx, ly, lz);
    lx /= lightLength;
    ly /= lightLength;
    lz /= lightLength;
    const halfLength = Math.hypot(lx, ly, lz - 1);
    const hx = lx/halfLength, hy = ly/halfLength, hz = (lz - 1)/halfLength;
    for (let j = 0; j < this.size; j++) {
      for (let i = 0; i < this.size; i++) {
        let dx = (i + .5 - this.size/2)/radius, dy = (j + .5 - this.size/2)/radius;
        const distance = Math.hypot(dx, dy);
        const alpha = Math.max(0, Math.min(1, radius - distance*radius + .5));
        if (distance > .999) {
          dx /= distance/.999;
          dy /= distance/.999;
        }
        const nz = -Math.sqrt(Math.max(0, 1 - dx*dx - dy*dy));
        const diffuse = Math.max(0, dx*lx + dy*ly + nz*lz);
        const highlight = Math.max(0, dx*hx + dy*hy + nz*hz);
        this.normals.push({
          x: dx, y: dy, z: nz, alpha,
          shade: .2 + .92*diffuse,
          specular: .85*Math.pow(highlight, 70) + .1*Math.pow(highlight, 8),
        });
      }
    }
    for (const ball of this.simulation.balls) ball.key = null;
  }

  drawBall(ball, cx, cy, factor, dim) {
    const size = this.size, ctx = this.ctx;
    const key = `${ball.q.join(',')},${dim.toFixed(3)},${size}`;
    if (!ball.canvas || ball.canvas.width !== size) {
      ball.canvas = document.createElement('canvas');
      ball.canvas.width = ball.canvas.height = size;
      ball.context = context2d(ball.canvas);
      ball.image = ball.context.createImageData(size, size);
    }
    if (ball.key !== key) {
      ball.key = key;
      const [w, x, y, z] = ball.q;
      const m00 = 1 - 2*(y*y + z*z), m01 = 2*(x*y - w*z), m02 = 2*(x*z + w*y);
      const m10 = 2*(x*y + w*z), m11 = 1 - 2*(x*x + z*z), m12 = 2*(y*z - w*x);
      const m20 = 2*(x*z - w*y), m21 = 2*(y*z + w*x), m22 = 1 - 2*(x*x + y*y);
      const number = ball.n, base = BALL_RGB[number > 8 ? number - 8 : number];
      const glyph = this.glyphs[number], data = ball.image.data;
      this.normals.forEach((normal, i) => {
        const offset = i*4;
        if (normal.alpha === 0) {
          data[offset + 3] = 0;
          return;
        }
        const lx = m00*normal.x + m10*normal.y + m20*normal.z;
        const ly = m01*normal.x + m11*normal.y + m21*normal.z;
        const lz = m02*normal.x + m12*normal.y + m22*normal.z;
        let r, g, b;
        if (number === 0) {
          [r, g, b] = Math.abs(lx) > .985 || Math.abs(ly) > .985 || Math.abs(lz) > .985
            ? [196, 32, 40] : BALL_RGB[0];
        } else if (Math.abs(lx) > COSD) {
          const u = (lx > 0 ? ly : -ly)/SIND, v = lz/SIND;
          const tx = ((u*.5 + .5)*T) | 0, ty = ((-v*.5 + .5)*T) | 0;
          const alpha = tx >= 0 && tx < T && ty >= 0 && ty < T ? glyph[ty*T + tx]/255 : 0;
          r = 244 - 228*alpha;
          g = 240 - 224*alpha;
          b = 228 - 212*alpha;
        } else if (number > 8 && Math.abs(lz) > STRIPE) [r, g, b] = [244, 240, 228];
        else [r, g, b] = base;
        const shade = normal.shade*dim, specular = normal.specular*255*dim;
        data[offset] = r*shade + specular;
        data[offset + 1] = g*shade + specular;
        data[offset + 2] = b*shade + specular;
        data[offset + 3] = normal.alpha*255;
      });
      ball.context.putImageData(ball.image, 0, 0);
    }
    const width = size*factor;
    ctx.drawImage(ball.canvas, cx - width/2, cy - width/2, width, width);
  }

  drawCue() {
    const R = this.simulation.radius;
    const { strikeT, struck, cueBall, cueDir, cueStart } = this.simulation;
    if (strikeT > CONTACT + CUE_FADE) return;
    let tipX, tipY, alpha = 1;
    if (!struck) {
      let gap;
      if (strikeT < 0) gap = 60;
      else if (strikeT < CUE_DRAWBACK) gap = 60 + 240*(1 - Math.cos(strikeT/CUE_DRAWBACK*Math.PI))/2;
      else {
        const u = Math.min(1, (strikeT - CUE_DRAWBACK)/(CONTACT - CUE_DRAWBACK));
        gap = 300*(1 - u*u);
      }
      tipX = cueBall.x - cueDir.x*(R + gap);
      tipY = cueBall.y - cueDir.y*(R + gap);
    } else {
      const follow = Math.min(80, (strikeT - CONTACT)*3000);
      tipX = cueStart.x - cueDir.x*R + cueDir.x*follow;
      tipY = cueStart.y - cueDir.y*R + cueDir.y*follow;
      alpha = Math.max(0, 1 - (strikeT - CONTACT)/CUE_FADE);
    }
    const ctx = this.ctx, dx = -cueDir.x, dy = -cueDir.y, nx = -dy, ny = dx, length = 1470;
    const quad = (s0, s1, offX, offY) => {
      const w0 = 6.5 + 8*s0/length, w1 = 6.5 + 8*s1/length;
      const ax = tipX + dx*s0 + offX, ay = tipY + dy*s0 + offY;
      const bx = tipX + dx*s1 + offX, by = tipY + dy*s1 + offY;
      ctx.beginPath();
      ctx.moveTo(this.X(ax + nx*w0), this.Y(ay + ny*w0));
      ctx.lineTo(this.X(bx + nx*w1), this.Y(by + ny*w1));
      ctx.lineTo(this.X(bx - nx*w1), this.Y(by - ny*w1));
      ctx.lineTo(this.X(ax - nx*w0), this.Y(ay - ny*w0));
      ctx.closePath();
    };
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = 'rgba(0,0,0,.28)';
    quad(0, length, 14, 20);
    ctx.fill();
    for (const [s0, s1, color] of [
      [0, 10, '#4b78b8'], [10, 34, '#efe8d6'], [34, 820, '#e2c697'],
      [820, 836, '#c9a046'], [836, 1050, '#2b1a10'],
      [1050, 1300, '#141414'], [1300, length, '#2b1a10'],
    ]) {
      ctx.fillStyle = color;
      quad(s0, s1, 0, 0);
      ctx.fill();
    }
    ctx.strokeStyle = 'rgba(255,255,255,.25)';
    ctx.lineWidth = Math.max(1, 1.5*this.scale);
    ctx.beginPath();
    ctx.moveTo(this.X(tipX + nx*2), this.Y(tipY + ny*2));
    ctx.lineTo(this.X(tipX + dx*length + nx*5), this.Y(tipY + dy*length + ny*5));
    ctx.stroke();
    ctx.restore();
  }

  render() {
    if (!this.scale) return;
    const R = this.simulation.radius;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.drawImage(this.bg, 0, 0);
    const visible = this.simulation.balls
      .filter(ball => ball.state === 'table' || ball.state === 'falling')
      .map(ball => {
        const t = ball.state === 'falling' ? Math.min(1, ball.ft/.3) : 0;
        return {
          ball,
          x: t ? ball.fx + (ball.px - ball.fx)*t*t : ball.x,
          y: t ? ball.fy + (ball.py - ball.fy)*t*t : ball.y,
          factor: 1 - .42*t, dim: 1 - .65*t, shadow: 1 - t,
        };
      });
    for (const { x, y, factor, shadow } of visible) {
      const cx = this.X(x + R*.2), cy = this.Y(y + R*.26), radius = R*1.08*this.scale*factor;
      const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
      gradient.addColorStop(0, `rgba(0,0,0,${.45*shadow})`);
      gradient.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI*2);
      ctx.fill();
    }
    for (const { ball, x, y, factor, dim } of visible) {
      this.drawBall(ball, this.X(x), this.Y(y), factor, dim);
    }
    this.drawCue();
    this.onProgress?.(this.simulation.resting ? 1 : this.simulation.ticks / this.progressTicks);
  }
}
