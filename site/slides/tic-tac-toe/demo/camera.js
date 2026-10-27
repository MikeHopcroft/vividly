function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

export class StageCamera {
  #viewport;
  #camera;
  #targets;
  #base = { x: 0, y: 0, scale: 1 };
  #adjustment = { x: 0, y: 0, zoom: 1 };
  #activeNames = [];
  #activePadding = 44;
  #resizeObserver;
  #eventController = new AbortController();
  #onChange;
  #animation = null;
  #animationRollback = null;
  #animationFrame = 0;
  #destroyed = false;

  constructor(viewport, camera, targets, onChange = () => {}) {
    this.#viewport = viewport;
    this.#camera = camera;
    this.#targets = targets;
    this.#onChange = onChange;
    this.#resizeObserver = new ResizeObserver(() => {
      if (!this.#destroyed) this.reframe();
    });
    this.#resizeObserver.observe(viewport);
    this.#bindPointerPan();
    this.#bindWheelZoom();
  }

  setTargets(targets) {
    this.#targets = targets;
  }

  frame(names, { padding = 44, preserveAdjustment = false } = {}) {
    this.#stopAnimation();
    this.#activeNames = [...names];
    this.#activePadding = padding;
    if (!preserveAdjustment) this.#adjustment = { x: 0, y: 0, zoom: 1 };
    const base = this.#calculateBase(names, padding, this.#renderedState());
    if (!base) return;
    this.#base = base;
    this.#apply();
  }

  animateFrame(names, { padding = 44, preserveAdjustment = false, duration = 520 } = {}) {
    const start = this.#renderedState();
    this.#stopAnimation(start);
    const rollback = {
      state: start,
      adjustment: { ...this.#adjustment },
      activeNames: [...this.#activeNames],
      activePadding: this.#activePadding,
    };
    this.#activeNames = [...names];
    this.#activePadding = padding;
    if (!preserveAdjustment) this.#adjustment = { x: 0, y: 0, zoom: 1 };
    const base = this.#calculateBase(names, padding, start);
    if (!base) return null;
    this.#base = base;
    const target = this.#composedState();
    const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion || duration <= 0) {
      this.#apply();
      return null;
    }

    this.#camera.style.transform = this.#transform(start);
    const animation = this.#camera.animate([
      { transform: this.#transform(start) },
      { transform: this.#transform(target) },
    ], {
      duration,
      easing: "cubic-bezier(.22,.72,.18,1)",
      fill: "both",
    });
    this.#animation = animation;
    this.#animationRollback = rollback;

    const reportFrame = () => {
      if (this.#animation !== animation) return;
      this.#notify(this.#renderedState());
      this.#animationFrame = requestAnimationFrame(reportFrame);
    };
    this.#animationFrame = requestAnimationFrame(reportFrame);
    animation.finished.then(() => {
      if (this.#animation !== animation) return;
      this.#camera.style.transform = this.#transform(target);
      animation.cancel();
      this.#animation = null;
      this.#animationRollback = null;
      if (this.#animationFrame) cancelAnimationFrame(this.#animationFrame);
      this.#animationFrame = 0;
      this.#notify(target);
    }).catch(() => {});
    return animation;
  }

  reframe() {
    if (this.#activeNames.length) {
      this.frame(this.#activeNames, { padding: this.#activePadding, preserveAdjustment: true });
    }
  }

  setAdjustment({ x, y, zoom }) {
    this.#finishAnimation();
    if (x !== undefined) this.#adjustment.x = Number(x);
    if (y !== undefined) this.#adjustment.y = Number(y);
    if (zoom !== undefined) this.#adjustment.zoom = clamp(Number(zoom), 0.35, 3);
    this.#apply();
  }

  adjustment() {
    return { ...this.#adjustment };
  }

  resetAdjustment() {
    this.#finishAnimation();
    this.#adjustment = { x: 0, y: 0, zoom: 1 };
    this.#apply();
  }

  finishTransition() {
    return this.#finishAnimation();
  }

  finish() {
    return this.finishTransition();
  }

  cancelTransition() {
    if (!this.#animation) return false;
    const rollback = this.#animationRollback;
    this.#stopAnimation();
    if (!rollback) return true;
    this.#adjustment = rollback.adjustment;
    this.#activeNames = rollback.activeNames;
    this.#activePadding = rollback.activePadding;
    this.#base = {
      scale: rollback.state.scale / rollback.adjustment.zoom,
      x: rollback.state.x - rollback.adjustment.x,
      y: rollback.state.y - rollback.adjustment.y,
    };
    this.#apply();
    return true;
  }

  cancel() {
    return this.cancelTransition();
  }

  destroy() {
    this.#destroyed = true;
    this.#stopAnimation();
    this.#resizeObserver.disconnect();
    this.#eventController.abort();
  }

  #calculateBase(names, padding, rendered) {
    const bounds = this.#measure(names, rendered);
    if (!bounds) return null;
    const width = this.#viewport.clientWidth;
    const height = this.#viewport.clientHeight;
    const scale = clamp(Math.min(
      (width - padding * 2) / Math.max(1, bounds.width),
      (height - padding * 2) / Math.max(1, bounds.height),
    ), 0.15, 5);
    return {
      scale,
      x: width / 2 - (bounds.left + bounds.width / 2) * scale,
      y: height / 2 - (bounds.top + bounds.height / 2) * scale,
    };
  }

  #measure(names, rendered = this.#composedState()) {
    const viewportRect = this.#viewport.getBoundingClientRect();
    const rectangles = names
      .map(name => this.#targets[name])
      .filter(Boolean)
      .map(element => {
        const rect = element.getBoundingClientRect();
        return {
          left: (rect.left - viewportRect.left - rendered.x) / rendered.scale,
          top: (rect.top - viewportRect.top - rendered.y) / rendered.scale,
          right: (rect.right - viewportRect.left - rendered.x) / rendered.scale,
          bottom: (rect.bottom - viewportRect.top - rendered.y) / rendered.scale,
        };
      });
    if (!rectangles.length) return null;
    const left = Math.min(...rectangles.map(rect => rect.left));
    const top = Math.min(...rectangles.map(rect => rect.top));
    const right = Math.max(...rectangles.map(rect => rect.right));
    const bottom = Math.max(...rectangles.map(rect => rect.bottom));
    return { left, top, width: right - left, height: bottom - top };
  }

  #apply() {
    const state = this.#composedState();
    this.#camera.style.transform = this.#transform(state);
    this.#notify(state);
  }

  #composedState() {
    return {
      scale: this.#base.scale * this.#adjustment.zoom,
      x: this.#base.x + this.#adjustment.x,
      y: this.#base.y + this.#adjustment.y,
    };
  }

  #renderedState() {
    const transform = getComputedStyle(this.#camera).transform;
    if (!transform || transform === "none") return this.#composedState();
    const matrix = new DOMMatrixReadOnly(transform);
    return {
      scale: Math.hypot(matrix.a, matrix.b),
      x: matrix.e,
      y: matrix.f,
    };
  }

  #transform({ x, y, scale }) {
    return `translate(${x}px, ${y}px) scale(${scale})`;
  }

  #notify({ scale, x, y }) {
    this.#onChange({ scale, x, y, adjustment: this.adjustment() });
  }

  #stopAnimation(rendered = null) {
    if (!this.#animation) return;
    const state = rendered ?? this.#renderedState();
    this.#animation.cancel();
    this.#animation = null;
    this.#animationRollback = null;
    if (this.#animationFrame) cancelAnimationFrame(this.#animationFrame);
    this.#animationFrame = 0;
    this.#camera.style.transform = this.#transform(state);
  }

  #finishAnimation() {
    if (!this.#animation) return false;
    const target = this.#composedState();
    this.#stopAnimation(target);
    this.#notify(target);
    return true;
  }

  #bindPointerPan() {
    let drag = null;
    const options = { signal: this.#eventController.signal };
    this.#viewport.addEventListener("pointerdown", event => {
      if (event.target.closest("button, input, select, mlp-board")) return;
      drag = {
        pointerId: event.pointerId,
        clientX: event.clientX,
        clientY: event.clientY,
        x: this.#adjustment.x,
        y: this.#adjustment.y,
      };
      this.#viewport.setPointerCapture(event.pointerId);
      this.#viewport.classList.add("dragging");
    }, options);
    this.#viewport.addEventListener("pointermove", event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      this.setAdjustment({
        x: drag.x + event.clientX - drag.clientX,
        y: drag.y + event.clientY - drag.clientY,
      }, options);
    });
    const end = event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      drag = null;
      this.#viewport.classList.remove("dragging");
    };
    this.#viewport.addEventListener("pointerup", end, options);
    this.#viewport.addEventListener("pointercancel", end, options);
  }

  #bindWheelZoom() {
    this.#viewport.addEventListener("wheel", event => {
      if (!event.ctrlKey && Math.abs(event.deltaY) < Math.abs(event.deltaX)) return;
      event.preventDefault();
      this.setAdjustment({ zoom: this.#adjustment.zoom * Math.exp(-event.deltaY * 0.0015) });
    }, { passive: false, signal: this.#eventController.signal });
  }
}
