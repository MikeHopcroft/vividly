// Presentation-wide event bus. Plain EventTarget; not a state store.

export class Bus {
  constructor() {
    this._target = new EventTarget();
  }

  emit(type, detail) {
    this._target.dispatchEvent(new CustomEvent(type, { detail }));
  }

  on(type, handler) {
    this._target.addEventListener(type, handler);
    return () => this._target.removeEventListener(type, handler);
  }

  /** A view whose subscriptions can all be dropped at once, on slide unmount. */
  scoped() {
    const offs = [];
    const self = this;
    return {
      emit: (type, detail) => self.emit(type, detail),
      on(type, handler) {
        const off = self.on(type, handler);
        offs.push(off);
        return off;
      },
      releaseAll() {
        while (offs.length) offs.pop()();
      },
    };
  }
}
