import { key, coordinates } from './cells.mjs';

const COLORS = {
  board: '#11151a',
  grid: '#252b33',
};

const VISUALS = {
  live: visual('#f7f8fa'),
  survives: visual('#e8f7ec', { text: '#17643a' }),
  dies: visual('#f05b62', { text: '#ffffff' }),
  seed: visual('#45ff84'),
  born: visual('rgba(70, 168, 255, 0.08)', {
    border: '#46a8ff',
    borderWidth: 1,
    text: '#9bd3ff',
  }),
};

export class LifeRenderer {
  constructor(root) {
    this.root = root;
    this.canvas = root.querySelector('#board');
    this.context = this.canvas.getContext('2d');
    if (!this.context) throw new Error('Game of Life requires a 2D canvas context');

    this.boardShell = root.querySelector('.board-shell');
    this.title = root.querySelector('#title');
    this.caption = root.querySelector('#caption');
    this.passage = root.querySelector('#passage');
    this.phase = root.querySelector('#phase');
    this.stage = root.querySelector('#stage');
    this.description = root.querySelector('#board-description');
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.resize = this.resize.bind(this);
    window.addEventListener('resize', this.resize);
    this.resizeObserver = new ResizeObserver(this.resize);
    this.resizeObserver.observe(this.boardShell);
    this.resize();
  }

  show(frame, { animateViewport = false, crossfade = false, morph = false } = {}) {
    const previousFrame = this.currentFrame;
    this.cancel();
    this.updateNarrative(frame);
    const targetCamera = this.cameraFor(frame.viewport);
    if (crossfade && previousFrame && !this.reducedMotion) {
      this.startCrossfade(frame, targetCamera);
      return;
    }
    if (animateViewport && this.camera && !sameCamera(this.camera, targetCamera) && !this.reducedMotion) {
      const duration = frame.overlay ? 1600 : 1200;
      const viewportDuration = frame.overlay ? 1100 : duration;
      this.startMotion(frame, [frame.world], targetCamera, duration, viewportDuration);
      return;
    }

    this.camera = targetCamera;
    this.currentFrame = frame;
    const canMorph = morph
      && previousFrame
      && previousFrame.passageId === frame.passageId
      && (previousFrame.predictions || frame.predictions)
      && !this.reducedMotion;
    if (canMorph) {
      this.startMorph(previousFrame, frame, 300);
      return;
    }
    this.draw(frame.world, frame.predictions, frame.overlay);
  }

  animate(frame) {
    this.cancel();
    this.updateNarrative(frame);
    const targetCamera = this.cameraFor(frame.viewport);
    if (this.reducedMotion) {
      this.camera = targetCamera;
      this.currentFrame = frame;
      this.draw(frame.world);
      return;
    }
    this.startMotion(
      frame,
      frame.animation.worlds,
      targetCamera,
      frame.animation.duration,
      frame.animation.viewportDuration,
      frame.animation.viewportKeyframes,
    );
  }

  startMotion(
    frame,
    worlds,
    targetCamera,
    duration,
    viewportDuration = duration,
    viewportKeyframes = [],
  ) {
    const startCamera = this.camera ?? targetCamera;
    const cameraTimeline = [
      { at: 0, camera: startCamera },
      ...viewportKeyframes.map(({ at, viewport }) => ({
        at,
        camera: this.cameraFor(viewport),
      })),
      { at: 1, camera: targetCamera },
    ];
    const startedAt = performance.now();
    this.motion = {
      frame,
      worlds,
      startCamera,
      targetCamera,
      duration,
      startedAt,
      requestId: 0,
    };

    const tick = (now) => {
      if (!this.motion) return;
      const progress = Math.max(0, Math.min(1, (now - startedAt) / duration));
      const viewportProgress = Math.max(0, Math.min(1, (now - startedAt) / viewportDuration));
      const index = Math.min(worlds.length - 1, Math.floor(progress * worlds.length));
      this.camera = cameraAt(cameraTimeline, viewportProgress);
      const overlayAlpha = frame.overlay
        ? Math.max(0, Math.min(1, (progress - 0.7) / 0.3))
        : 1;
      this.draw(worlds[index], undefined, frame.overlay, overlayAlpha);
      if (progress < 1) {
        this.motion.requestId = requestAnimationFrame(tick);
      } else {
        this.finishMotion();
      }
    };
    this.motion.requestId = requestAnimationFrame(tick);
  }

  settle() {
    let changed = false;
    if (this.motion) {
      this.finishMotion();
      changed = true;
    }
    if (this.morph) {
      this.finishMorph();
      changed = true;
    }
    if (this.crossfade) {
      this.finishCrossfade();
      changed = true;
    }
    return changed;
  }

  finishMotion() {
    if (!this.motion) return;
    cancelAnimationFrame(this.motion.requestId);
    const { frame, targetCamera } = this.motion;
    this.motion = null;
    this.camera = targetCamera;
    this.currentFrame = frame;
    this.draw(frame.world, frame.predictions, frame.overlay);
  }

  cancel() {
    if (this.motion) {
      cancelAnimationFrame(this.motion.requestId);
      this.motion = null;
    }
    if (this.morph) {
      cancelAnimationFrame(this.morph.requestId);
      this.morph = null;
    }
    if (this.crossfade) {
      this.crossfade.animation.onfinish = null;
      this.crossfade.animation.cancel();
      this.crossfade.overlay.remove();
      this.crossfade = null;
    }
  }

  startCrossfade(frame, targetCamera) {
    const overlay = document.createElement('canvas');
    overlay.width = this.canvas.width;
    overlay.height = this.canvas.height;
    overlay.setAttribute('aria-hidden', 'true');
    Object.assign(overlay.style, {
      position: 'absolute',
      inset: '0',
      width: '100%',
      height: '100%',
      pointerEvents: 'none',
    });
    const overlayContext = overlay.getContext('2d');
    if (!overlayContext) throw new Error('Game of Life crossfade requires a 2D canvas context');
    overlayContext.drawImage(this.canvas, 0, 0);

    this.camera = targetCamera;
    this.currentFrame = frame;
    this.draw(frame.world, frame.predictions, frame.overlay);
    this.canvas.after(overlay);
    const animation = overlay.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration: 360, easing: 'ease-in-out' },
    );
    this.crossfade = { animation, overlay };
    animation.onfinish = () => {
      if (this.crossfade?.animation === animation) this.finishCrossfade();
    };
  }

  finishCrossfade() {
    if (!this.crossfade) return;
    this.crossfade.animation.onfinish = null;
    this.crossfade.overlay.remove();
    this.crossfade = null;
  }

  startMorph(fromFrame, toFrame, duration) {
    const fromVisuals = frameVisuals(fromFrame);
    const toVisuals = frameVisuals(toFrame);
    const startedAt = performance.now();
    this.morph = {
      requestId: 0,
      toFrame,
    };

    const tick = (now) => {
      if (!this.morph) return;
      const progress = Math.max(0, Math.min(1, (now - startedAt) / duration));
      this.drawMorph(fromVisuals, toVisuals, easeInOutCubic(progress));
      if (progress < 1) {
        this.morph.requestId = requestAnimationFrame(tick);
      } else {
        this.finishMorph();
      }
    };
    this.morph.requestId = requestAnimationFrame(tick);
  }

  finishMorph() {
    if (!this.morph) return;
    cancelAnimationFrame(this.morph.requestId);
    const { toFrame } = this.morph;
    this.morph = null;
    this.draw(toFrame.world, toFrame.predictions, toFrame.overlay);
  }

  resize() {
    const width = this.boardShell.clientWidth;
    const height = this.boardShell.clientHeight;
    if (width === 0 || height === 0) return;
    const scale = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(width * scale);
    this.canvas.height = Math.round(height * scale);
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    this.context.setTransform(scale, 0, 0, scale, 0, 0);
    this.width = width;
    this.height = height;
    if (this.currentFrame) {
      this.draw(this.currentFrame.world, this.currentFrame.predictions, this.currentFrame.overlay);
    }
  }

  updateNarrative(frame) {
    this.currentFrame = frame;
    this.root.classList.toggle('explaining', frame.phase === 'prediction');
    this.passage.textContent = frame.passageLabel;
    this.title.textContent = frame.title;
    this.caption.textContent = frame.caption;
    const phase = frame.phase === 'prediction' ? 'prediction' : `generation ${frame.turn.toLocaleString()}`;
    this.phase.textContent = phase;
    this.stage.textContent = `stage ${frame.index + 1} of ${frame.total}`;
    this.description.textContent = `${frame.title}. ${frame.caption} ${frame.world.size} live cells at generation ${frame.turn}.`;
  }

  cameraFor(viewport) {
    const aspect = (this.width || 1920) / (this.height || 900);
    if (viewport.bounds) {
      const padding = viewport.padding ?? 2;
      const width = viewport.bounds.maxX - viewport.bounds.minX + 1 + padding * 2;
      const height = viewport.bounds.maxY - viewport.bounds.minY + 1 + padding * 2;
      return {
        x: (viewport.bounds.minX + viewport.bounds.maxX) / 2,
        y: (viewport.bounds.minY + viewport.bounds.maxY) / 2,
        cellsWide: Math.max(width, height * aspect),
      };
    }
    if (!Array.isArray(viewport.center) || !Number.isFinite(viewport.cellsWide)) {
      throw new TypeError('Literal viewport needs center and cellsWide');
    }
    return { x: viewport.center[0], y: viewport.center[1], cellsWide: viewport.cellsWide };
  }

  draw(world, predictions, overlay, overlayAlpha = 1) {
    const geometry = this.prepareBoard();
    if (!geometry) return;
    const { left, top, cellSize } = geometry;

    if (predictions) {
      predictions.forEach(({ x, y, count, outcome }) => {
        this.drawCell(x, y, left, top, cellSize, VISUALS[outcome], count);
      });
      return;
    }

    world.forEach((cell) => {
      const [x, y] = coordinates(cell);
      this.drawCell(x, y, left, top, cellSize, VISUALS.live);
    });
    if (overlay && overlayAlpha > 0) {
      overlay.forEach((cell) => {
        const [x, y] = coordinates(cell);
        this.drawCell(
          x,
          y,
          left,
          top,
          cellSize,
          visualWithAlpha(VISUALS.seed, overlayAlpha),
        );
      });
    }
  }

  drawMorph(fromVisuals, toVisuals, progress) {
    const geometry = this.prepareBoard();
    if (!geometry) return;
    const { left, top, cellSize } = geometry;
    const cells = new Set([...fromVisuals.keys(), ...toVisuals.keys()]);
    cells.forEach((cell) => {
      const from = fromVisuals.get(cell);
      const to = toVisuals.get(cell);
      const [x, y] = coordinates(cell);
      this.drawCell(
        x,
        y,
        left,
        top,
        cellSize,
        interpolateVisual(from, to, progress),
        to?.count ?? from?.count,
      );
    });
  }

  prepareBoard() {
    if (!this.width || !this.height || !this.camera) return null;
    const cellSize = this.width / this.camera.cellsWide;
    const cellsHigh = this.height / cellSize;
    const left = this.camera.x - this.camera.cellsWide / 2;
    const top = this.camera.y - cellsHigh / 2;
    this.context.fillStyle = COLORS.board;
    this.context.fillRect(0, 0, this.width, this.height);
    if (cellSize >= 5) this.drawGrid(left, top, cellSize);
    return { left, top, cellSize };
  }

  drawGrid(left, top, cellSize) {
    const ctx = this.context;
    const startX = (Math.ceil(left - 0.5) + 0.5 - left) * cellSize;
    const startY = (Math.ceil(top - 0.5) + 0.5 - top) * cellSize;
    ctx.beginPath();
    for (let x = startX; x <= this.width; x += cellSize) {
      ctx.moveTo(Math.round(x) + 0.5, 0);
      ctx.lineTo(Math.round(x) + 0.5, this.height);
    }
    for (let y = startY; y <= this.height; y += cellSize) {
      ctx.moveTo(0, Math.round(y) + 0.5);
      ctx.lineTo(this.width, Math.round(y) + 0.5);
    }
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  drawCell(x, y, left, top, cellSize, visualState, count) {
    const px = (x - 0.5 - left) * cellSize;
    const py = (y - 0.5 - top) * cellSize;
    const inset = cellSize >= 7 ? 1 : 0;
    const size = Math.max(1, cellSize - inset * 2);
    this.context.fillStyle = colorString(visualState.fill);
    this.context.fillRect(px + inset, py + inset, size, size);
    if (visualState.borderWidth > 0 && visualState.border[3] > 0) {
      const border = Math.max(3, Math.min(7, cellSize * 0.07)) * visualState.borderWidth;
      this.context.strokeStyle = colorString(visualState.border);
      this.context.lineWidth = border;
      this.context.strokeRect(
        px + inset + border / 2,
        py + inset + border / 2,
        Math.max(1, size - border),
        Math.max(1, size - border),
      );
    }
    if (count === undefined || cellSize < 24 || visualState.text[3] === 0) return;

    this.context.fillStyle = colorString(visualState.text);
    this.context.font = `700 ${Math.round(Math.min(40, cellSize * 0.46))}px ui-monospace, monospace`;
    this.context.textAlign = 'center';
    this.context.textBaseline = 'middle';
    this.context.fillText(String(count), px + cellSize / 2, py + cellSize / 2);
  }

  destroy() {
    this.cancel();
    this.resizeObserver.disconnect();
    window.removeEventListener('resize', this.resize);
  }
}

function frameVisuals(frame) {
  const visuals = new Map();
  if (frame.predictions) {
    frame.predictions.forEach(({ x, y, count, outcome }) => {
      visuals.set(key(x, y), { ...VISUALS[outcome], count });
    });
    return visuals;
  }
  frame.world.forEach((cell) => visuals.set(cell, VISUALS.live));
  return visuals;
}

function visual(fill, { border = 'rgba(0, 0, 0, 0)', borderWidth = 0, text = 'rgba(0, 0, 0, 0)' } = {}) {
  return {
    fill: parseColor(fill),
    border: parseColor(border),
    borderWidth,
    text: parseColor(text),
  };
}

function interpolateVisual(from, to, progress) {
  const source = from ?? transparentVisual(to);
  const target = to ?? transparentVisual(from);
  return {
    fill: interpolateColor(source.fill, target.fill, progress),
    border: interpolateColor(source.border, target.border, progress),
    borderWidth: source.borderWidth + (target.borderWidth - source.borderWidth) * progress,
    text: interpolateColor(source.text, target.text, progress),
  };
}

function visualWithAlpha(source, alpha) {
  return {
    fill: [...source.fill.slice(0, 3), source.fill[3] * alpha],
    border: [...source.border.slice(0, 3), source.border[3] * alpha],
    borderWidth: source.borderWidth,
    text: [...source.text.slice(0, 3), source.text[3] * alpha],
  };
}

function transparentVisual(source) {
  return {
    fill: [...source.fill.slice(0, 3), 0],
    border: [...source.border.slice(0, 3), 0],
    borderWidth: source.borderWidth,
    text: [...source.text.slice(0, 3), 0],
  };
}

function interpolateColor(from, to, progress) {
  return from.map((value, index) => value + (to[index] - value) * progress);
}

function parseColor(color) {
  if (color.startsWith('#')) {
    return [
      Number.parseInt(color.slice(1, 3), 16),
      Number.parseInt(color.slice(3, 5), 16),
      Number.parseInt(color.slice(5, 7), 16),
      1,
    ];
  }
  const match = color.match(/^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$/);
  if (!match) throw new TypeError(`Unsupported color format: ${color}`);
  return [Number(match[1]), Number(match[2]), Number(match[3]), Number(match[4])];
}

function colorString([red, green, blue, alpha]) {
  return `rgba(${Math.round(red)}, ${Math.round(green)}, ${Math.round(blue)}, ${alpha})`;
}

function interpolateCamera(from, to, progress) {
  return {
    x: from.x + (to.x - from.x) * progress,
    y: from.y + (to.y - from.y) * progress,
    cellsWide: from.cellsWide + (to.cellsWide - from.cellsWide) * progress,
  };
}

function cameraAt(timeline, progress) {
  const endIndex = timeline.findIndex(({ at }) => at >= progress);
  if (endIndex <= 0) return timeline[0].camera;
  const start = timeline[endIndex - 1];
  const end = timeline[endIndex];
  const localProgress = (progress - start.at) / (end.at - start.at);
  return interpolateCamera(start.camera, end.camera, easeInOutCubic(localProgress));
}

function sameCamera(first, second) {
  return first.x === second.x
    && first.y === second.y
    && first.cellsWide === second.cellsWide;
}

function easeInOutCubic(value) {
  return value < 0.5
    ? 4 * value * value * value
    : 1 - ((-2 * value + 2) ** 3) / 2;
}
