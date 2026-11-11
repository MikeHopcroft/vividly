// Reader state, namespaced by slide address, in one localStorage entry.

export class StateStore {
  constructor(catalogUrl, presentationId, onError) {
    this._onError = onError;
    this._key = `vividly:${new URL(catalogUrl).href}:${presentationId}`;
    try {
      this._data = JSON.parse(localStorage.getItem(this._key) || '{}');
    } catch (error) {
      this._data = {};
      this._onError?.(error);
    }
  }

  scope(address) {
    const bucket = (this._data[address] ||= {});
    return {
      get: (key, fallback = undefined) => (key in bucket ? bucket[key] : fallback),
      set: (key, value) => {
        bucket[key] = value;
        this._flush();
      },
      all: () => ({ ...bucket }),
    };
  }

  clear() {
    this._data = {};
    this._flush();
  }

  _flush() {
    try {
      localStorage.setItem(this._key, JSON.stringify(this._data));
    } catch (error) {
      this._onError?.(error);
      // Storage unavailable or full; reader state is best-effort.
    }
  }
}
