const POSITIVE = "hsl(2 72% 52%)";
const NEGATIVE = "hsl(226 66% 52%)";
const EPSILON = 1e-4;

const easeOut = value => 1 - (1 - value) ** 3;
const lerp = (start, end, amount) => start + (end - start) * amount;

function scaleFraction(value, maximum, linear = false) {
  const magnitude = Math.abs(value);
  if (magnitude < EPSILON || maximum < EPSILON) return 0;
  if (linear) return Math.min(1, magnitude / maximum);
  return Math.min(1, Math.log1p(magnitude * 4) / Math.log1p(maximum * 4));
}

export function createExplanationFx(viewport) {
  const canvas = document.createElement("canvas");
  canvas.className = "explanation-fx";
  canvas.setAttribute("aria-hidden", "true");
  viewport.append(canvas);
  const context = canvas.getContext("2d");
  let particles = [];
  let frameRequest = 0;
  let generation = 0;
  let pendingResolve = null;

  function sizeCanvas() {
    const ratio = window.devicePixelRatio || 1;
    const width = viewport.clientWidth;
    const height = viewport.clientHeight;
    if (canvas.width !== Math.floor(width * ratio) || canvas.height !== Math.floor(height * ratio)) {
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(height * ratio);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
    }
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function center(element, row, column) {
    const { rows, columns } = element.getGridShape();
    if (!Number.isInteger(row) || row < 0 || row >= rows || !Number.isInteger(column) || column < 0 || column >= columns) {
      throw new RangeError(`cell (${row}, ${column}) is outside ${rows} × ${columns}`);
    }
    const elementRect = element.getBoundingClientRect();
    const viewportRect = viewport.getBoundingClientRect();
    return {
      x: elementRect.left - viewportRect.left + (column + 0.5) * elementRect.width / columns,
      y: elementRect.top - viewportRect.top + (row + 0.5) * elementRect.height / rows,
    };
  }

  function cellRadius(element) {
    const { rows, columns } = element.getGridShape();
    const rect = element.getBoundingClientRect();
    return Math.max(1.4, Math.min(rect.width / columns, rect.height / rows) / 2 - 0.3);
  }

  function clearFrame() {
    sizeCanvas();
    context.clearRect(0, 0, viewport.clientWidth, viewport.clientHeight);
  }

  function cancel() {
    generation += 1;
    particles = [];
    if (frameRequest) cancelAnimationFrame(frameRequest);
    frameRequest = 0;
    if (pendingResolve) pendingResolve(false);
    pendingResolve = null;
    clearFrame();
  }

  function launch(nextParticles, onProgress) {
    cancel();
    const launchGeneration = generation;
    particles = nextParticles.map(particle => ({ ...particle, landed: false }));
    if (!particles.length) return Promise.resolve(true);

    return new Promise(resolve => {
      pendingResolve = resolve;
      function draw(now) {
        if (launchGeneration !== generation) {
          pendingResolve = null;
          resolve(false);
          return;
        }
        clearFrame();
        let pending = 0;
        let changed = false;
        for (const particle of particles) {
          const progress = (now - particle.start) / particle.duration;
          if (progress >= 1) {
            if (!particle.landed) {
              particle.landed = true;
              particle.onLand?.(particle);
              changed = true;
            }
            continue;
          }
          pending += 1;
          const amount = progress <= 0 ? 0 : easeOut(progress);
          const fraction = scaleFraction(particle.value, particle.scale, particle.linear);
          if (!fraction) continue;
          const radius = Math.max(1.4, particle.radius * fraction);
          context.beginPath();
          context.arc(lerp(particle.source.x, particle.target.x, amount), lerp(particle.source.y, particle.target.y, amount), radius, 0, Math.PI * 2);
          context.fillStyle = particle.value >= 0 ? POSITIVE : NEGATIVE;
          context.fill();
        }
        if (changed) onProgress?.();
        if (pending) {
          frameRequest = requestAnimationFrame(draw);
        } else {
          frameRequest = 0;
          particles = [];
          clearFrame();
          pendingResolve = null;
          resolve(true);
        }
      }
      frameRequest = requestAnimationFrame(draw);
    });
  }

  function destroy() {
    cancel();
    canvas.remove();
  }

  sizeCanvas();
  return { center, cellRadius, launch, cancel, destroy };
}
