// <vividly-presentation> — routing, keyboard, preload window, transitions, stage.

import './controls/index.js';
import { Bus } from './bus.js';
import { StateStore } from './state.js';
import { adoptModuleStyles, moduleIdFor } from './styles.js';
import { SlideContext } from './context.js';
import { Slide, DYNAMIC } from './slide.js';
import { TouchNavigation } from './touch.js';
import { loadManifest } from './manifest.js';
import { loadCatalog } from './catalog.js';
import {
  DependencyRegistry,
  DependencyTable,
  loadRuntimeDependencyTable,
} from './dependencies.js';
import { configureRenderDependencies } from './controls/render.js';

// Animations do not progress in a backgrounded tab; without a cap a stalled
// transition would deadlock the navigation queue permanently.
const TRANSITION_TIMEOUT_MS = 2000;
const RENDER_FRAME_TIMEOUT_MS = 100;
const STEP_SETTLING_GRACE_MS = 500;
const STEP_SETTLING_NONE = 'none';
const STEP_SETTLING_CONTINUE = 'continue';
const STEP_SETTLING_CONSUME = 'consume';
const NAVIGATION_HUD_DURATION_MS = 1600;
const KEYBOARD_HELP_TRANSITION_MS = 160;
const KEYBOARD_HINT_FADE_MS = 300;
const THUMBNAIL_REVISION_PATTERN = /^[0-9a-f]{64}$/;
const EMPTY_THUMBNAIL_SEQUENCE = Object.freeze([]);

class VividlyPresentation extends HTMLElement {
  async connectedCallback() {
    if (this._booted) return;
    this._booted = true;

    this._bus = new Bus();
    this._index = 0;
    this._step = 0;
    this._generation = 0;
    this._renderGeneration = 0;
    this._navigationDepth = null;
    this._navigatorArrivalFocus = null;
    this._navigationHudTimer = null;
    this._keyboardHelpTimer = null;
    this._keyboardHintTimer = null;
    this._keyboardHintResolve = null;
    this._keyboardHintRuntimes = new Set();
    this._keyboardHintShownThisPage = false;
    this._focusTocSelectionOnShow = false;
    this._queue = Promise.resolve();
    this._threadSwitchQueue = Promise.resolve();
    this._pageId = crypto.randomUUID();
    this._threadId = crypto.randomUUID();
    this._threads = new Map();
    this._threadLabels = new Map();
    this._lastActivatedAt = 0;
    this._ignoredHashChange = null;
    this._lastHash = location.hash;
    this.toggleAttribute(
      'data-capture',
      new URLSearchParams(location.search).get('vividly-capture') === '1'
    );

    this.innerHTML = '';
    this._stage = document.createElement('div');
    this._stage.className = 'v-stage';
    this._catalogView = document.createElement('nav');
    this._catalogView.className = 'v-catalog';
    this._catalogView.hidden = true;
    this._catalogView.setAttribute('aria-label', 'Project catalog');
    this._toc = document.createElement('nav');
    this._toc.className = 'v-toc';
    this._toc.hidden = true;
    this._toc.setAttribute('aria-label', 'Presentation outline');
    this._navigationHud = document.createElement('div');
    this._navigationHud.className = 'v-navigation-hud';
    this._navigationHud.hidden = true;
    this._navigationHud.setAttribute('role', 'status');
    this._navigationHud.setAttribute('aria-live', 'polite');
    this._navigationHud.setAttribute('aria-atomic', 'true');
    this._helpTrigger = document.createElement('button');
    this._helpTrigger.type = 'button';
    this._helpTrigger.className = 'v-help-trigger';
    this._helpTrigger.textContent = '?';
    this._helpTrigger.title = 'Keyboard shortcuts';
    this._helpTrigger.setAttribute('aria-label', 'Keyboard shortcuts');
    this._helpTrigger.addEventListener('click', (event) => {
      event.stopPropagation();
      if (this._keyboardHelp.hidden) this._showKeyboardHelp();
      else this._hideKeyboardHelp(false);
    });
    this._keyboardHelp = this._buildKeyboardHelp();
    this._keyboardHints = this._buildKeyboardHints();
    this.append(
      this._catalogView,
      this._stage,
      this._toc,
      this._navigationHud,
      this._helpTrigger,
      this._keyboardHints,
      this._keyboardHelp
    );
    this._touch = new TouchNavigation(this);

    this._catalogUrl = new URL(
      this.getAttribute('catalog') || './catalog.yaml',
      document.baseURI
    ).href;
    this._dependencyBaseUrl = this._readDependencyBaseUrl();
    const dependencyTableUrl = new URL('../dependencies.json', import.meta.url).href;
    const runtimeDependencies = await loadRuntimeDependencyTable(dependencyTableUrl);
    this._dependencyRegistry = new DependencyRegistry({
      localBaseUrl: this._dependencyBaseUrl,
    });
    this._dependencyRegistry.push(runtimeDependencies);
    this._yaml = await this._dependencyRegistry.load('js-yaml');
    this._siteState = new StateStore(this._catalogUrl, '~runtime');
    this._catalog = await loadCatalog(this._catalogUrl, this._yaml);
    this._dependencyRegistry.push(
      DependencyTable.fromCatalog(this._catalog.dependencies, this._catalogUrl)
    );
    await Promise.all(
      [...runtimeDependencies.records.keys()]
        .filter((key) => key !== 'js-yaml')
        .map((key) => this._dependencyRegistry.load(key))
    );
    configureRenderDependencies(this._dependencyRegistry);
    this._buildCatalog();
    const requestedPresentationId = this._presentationIdFromHash();
    const entry = this._hasPresentation(requestedPresentationId)
      ? this._resolvePresentation(requestedPresentationId)
      : null;
    if (entry) {
      this._presentationId = entry.id;
      const manifestUrl = entry.manifestUrl;
      this._manifest = await loadManifest(manifestUrl, this._yaml);
      this._manifestUrl = manifestUrl;
      this._leaves = this._manifest.leaves;
      this._runtimeToken = Symbol('presentation runtime');
      this._leaves.forEach((leaf) => {
        leaf.runtimeToken = this._runtimeToken;
      });
      this._state = new StateStore(this._catalogUrl, this._presentationId);
      document.title = this._manifest.title;
      this._applyTheme();
      this._thumbnailIndex = await this._loadThumbnailIndex();
      this._buildToc();
      this._threads.set(
        this._threadId,
        this._createThreadDescriptor(this._threadId, this._presentationId, this._currentRoute())
      );
      this._rootThreadId = this._threadId;
    } else {
      this._stage.remove();
      this._toc.remove();
      this._clearRuntimeFields();
      this._threadId = null;
      this._rootThreadId = null;
    }

    history.replaceState(this._historyState(), '', location.href);

    this._onHashChange = () => {
      this._finishKeyboardHints(false);
      if (this._ignoredHashChange === location.hash) {
        this._ignoredHashChange = null;
        this._lastHash = location.hash;
        return;
      }
      this._lastHash = location.hash;
      history.replaceState(this._historyState(), '', location.href);
      this._route();
    };
    this._onPopState = (event) => {
      this._finishKeyboardHints(false);
      this._ignoredHashChange = location.hash === this._lastHash ? null : location.hash;
      this._lastHash = location.hash;
      const route = location.hash;
      this._restoreHistoryEntry(event.state, route).catch((error) => {
        console.error('[vividly]', error);
      });
    };
    this._onKeyDown = (e) => this._handleKey(e);
    this._onDocumentClick = () => {
      if (!this._keyboardHelp.hidden) this._hideKeyboardHelp(false);
    };
    window.addEventListener('hashchange', this._onHashChange);
    window.addEventListener('popstate', this._onPopState);
    document.addEventListener('keydown', this._onKeyDown);
    document.addEventListener('click', this._onDocumentClick);

    await this._route();
    await this._autoAdvanceInitialRoute();
    if (this._presentationId) this._recordCatalogActivation(this._presentationId);
    if (this._threadId) this._recordThreadLabel(this._threadId);
  }

  get threads() {
    const currentRoute = this._currentRoute();
    return Object.freeze(
      [...this._threads.values()]
        .map((thread) =>
          Object.freeze({
            ...thread,
            latestRoute: thread.id === this._threadId ? currentRoute : thread.latestRoute,
            ...(thread.id === this._threadId
              ? this._threadLabel(this._manifest, currentRoute)
              : this._threadLabels.get(thread.id)),
          })
        )
        .sort((left, right) => right.lastActivatedAt - left.lastActivatedAt)
    );
  }

  thumbnailFor(address, step) {
    const leaf = this._thumbnailLeaf(address);
    if (!leaf) return null;
    const entry = this._thumbnailIndex?.[leaf.address];
    if (!entry) return null;
    const selectedStep =
      step === undefined
        ? entry.steps[entry.canonicalStep]
        : Number.isInteger(step) && step >= 0
          ? entry.steps[step]
          : null;
    return selectedStep ? this._thumbnailDescriptor(leaf, selectedStep) : null;
  }

  thumbnailsFor(address) {
    const leaf = this._thumbnailLeaf(address);
    if (!leaf) return EMPTY_THUMBNAIL_SEQUENCE;
    const entry = this._thumbnailIndex?.[leaf.address];
    if (!entry) return EMPTY_THUMBNAIL_SEQUENCE;
    return Object.freeze(
      entry.steps.map((step) => this._thumbnailDescriptor(leaf, step))
    );
  }

  advance() {
    return this._advance(1);
  }

  _thumbnailLeaf(address) {
    if (typeof address !== 'string' || !address) return null;
    return (
      this._manifest?.leavesByAddress.get(address) ||
      (() => {
        const section = this._manifest?.sections.get(address);
        return section?.firstLeafIndex == null ? null : this._leaves[section.firstLeafIndex];
      })()
    );
  }

  _thumbnailDescriptor(leaf, step) {
    const src = new URL(`${this._thumbnailRoot()}${step.path}`, document.baseURI);
    src.searchParams.set('v', step.revision);
    return Object.freeze({
      address: leaf.address,
      title: leaf.title,
      src: src.href,
      capturedStep: step.step,
    });
  }

  createThread(presentationId, { route = '' } = {}) {
    this._resolvePresentation(presentationId);
    const threadId = crypto.randomUUID();
    const descriptor = this._createThreadDescriptor(threadId, presentationId, route);
    return this._serializeThreadSwitch(async () => {
      await this._switchThread(descriptor);
      this._threads.set(threadId, descriptor);
      return threadId;
    });
  }

  selectThread(threadId) {
    return this._serializeThreadSwitch(async () => {
      const descriptor = this._threads.get(threadId);
      if (!descriptor) throw new Error(`Unknown presentation thread "${threadId}"`);
      if (threadId === this._threadId) return;
      await this._switchThread(descriptor);
    });
  }

  _readDependencyBaseUrl() {
    if (!this.hasAttribute('dependency-base')) return null;
    const configured = this.getAttribute('dependency-base');
    if (!configured) throw new Error('dependency-base must be a nonempty URL');
    const normalized = configured.endsWith('/') ? configured : `${configured}/`;
    const baseUrl = new URL(normalized, document.baseURI);
    if (baseUrl.origin !== document.location.origin) {
      throw new Error('dependency-base must be same-origin');
    }
    return baseUrl.href;
  }

  disconnectedCallback() {
    this._touch?.dispose();
    window.removeEventListener('hashchange', this._onHashChange);
    window.removeEventListener('popstate', this._onPopState);
    document.removeEventListener('keydown', this._onKeyDown);
    document.removeEventListener('click', this._onDocumentClick);
    clearTimeout(this._navigationHudTimer);
    clearTimeout(this._keyboardHelpTimer);
    clearTimeout(this._keyboardHintTimer);
    this._finishKeyboardHints(false);
    for (const leaf of this._leaves || []) this._dispose(leaf);
    this._themeLink?.remove();
  }

  _applyTheme() {
    if (!this._manifest.theme) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = this._manifest.theme;
    document.head.appendChild(link);
    this._themeLink = link;
  }

  // --- routing ------------------------------------------------------------

  _historyState() {
    return {
      vividly: {
        pageId: this._pageId,
        threadId: this._threadId,
      },
    };
  }

  _createThreadDescriptor(id, presentationId, latestRoute) {
    return {
      id,
      presentationId,
      latestRoute,
      lastActivatedAt: this._nextActivationTime(),
    };
  }

  _resolvePresentation(presentationId) {
    const entry = this._catalog.presentations.get(presentationId);
    if (!entry) throw new Error(`Unknown presentation ID "${presentationId}"`);
    return entry;
  }

  _hasPresentation(presentationId) {
    return this._catalog.presentations.has(presentationId);
  }

  _currentRoute() {
    if (!this._toc?.hidden) return '';
    const address = this._leaves?.[this._index]?.address;
    if (!address) return '';
    return this._step > 0 ? `${address}/${this._step}` : address;
  }

  _clearRuntimeFields() {
    this._manifest = null;
    this._manifestUrl = null;
    this._presentationId = null;
    this._leaves = [];
    this._runtimeToken = null;
    this._state = null;
    this._thumbnailIndex = {};
    this._themeLink = null;
    this._current = null;
    this._index = 0;
    this._step = 0;
    this._navigationDepth = null;
  }

  _serializeThreadSwitch(operation) {
    const result = this._threadSwitchQueue.then(operation);
    this._touch?.blockUntil(result);
    this._threadSwitchQueue = result.catch(() => {});
    return result;
  }

  async _switchThread(descriptor, { route: requestedRoute, writeHistory = true } = {}) {
    this._touch?.cancel();
    await this._queue;
    const entry = this._resolvePresentation(descriptor.presentationId);
    const manifest = await loadManifest(entry.manifestUrl, this._yaml);
    const routeText = requestedRoute ?? descriptor.latestRoute;
    const parsed = routeText.startsWith('#')
      ? this._parseGlobalRoute(routeText)
      : this._parseRoute(routeText);
    if (
      parsed.view === 'catalog' ||
      parsed.view === 'invalid' ||
      (parsed.presentationId && parsed.presentationId !== descriptor.presentationId)
    ) {
      throw new Error(`Unknown route "${routeText}"`);
    }
    const { presentationId: _presentationId, ...route } = parsed;
    if (
      route.view === 'slide' &&
      !manifest.leaves.some((leaf) => leaf.address === route.address)
    ) {
      throw new Error(`Unknown route "${routeText}"`);
    }

    const source = this._manifest ? this._captureRuntime() : null;
    const destination = this._createRuntime(
      manifest,
      entry.manifestUrl,
      descriptor.presentationId
    );
    delete this.dataset.renderReady;
    this._installRuntime(destination);
    if (!source) this._catalogView.after(this._stage, this._toc);
    this._thumbnailIndex = await this._loadThumbnailIndex();
    this._buildToc();
    this._themeLink && document.head.appendChild(this._themeLink);
    this._suppressHistoryWrites = true;
    try {
      await this._route(route, false, true);
    } catch (error) {
      this._disposeRuntime(destination);
      if (source) this._installRuntime(source);
      else {
        this._clearRuntimeFields();
        this._showCatalog();
      }
      this.dataset.renderReady = '';
      throw error;
    } finally {
      this._suppressHistoryWrites = false;
    }

    if (source) {
      source.stage.replaceWith(this._stage);
      source.toc.replaceWith(this._toc);
      source.themeLink?.remove();
      this._disposeRuntime(source);
    }

    const outgoing = this._threads.get(this._threadId);
    if (outgoing && source) {
      outgoing.latestRoute = this._routeFromRuntime(source);
      this._recordThreadLabel(outgoing.id, source);
    }
    this._threadId = descriptor.id;
    descriptor.latestRoute = this._currentRoute();
    descriptor.lastActivatedAt = this._nextActivationTime();
    this._recordCatalogActivation(descriptor.presentationId);
    this._recordThreadLabel(descriptor.id);
    document.title = this._manifest.title;
    if (writeHistory) {
      history.pushState(this._historyState(), '', this._hashForRoute(descriptor.latestRoute));
    }
    this._lastHash = location.hash;
  }

  _restoreHistoryEntry(state, route) {
    return this._serializeThreadSwitch(async () => {
      if (this._parseGlobalRoute(route).view === 'catalog') {
        await this._enterCatalog();
        history.replaceState(this._historyState(), '', location.href);
        return;
      }
      const marker = state?.vividly;
      if (marker?.pageId === this._pageId && !marker.threadId) {
        await this._enterCatalog();
        return;
      }
      const descriptor =
        marker?.pageId === this._pageId ? this._threads.get(marker.threadId) : null;
      if (descriptor) {
        if (descriptor.id === this._threadId) {
          await this._restoreRoute(route);
          descriptor.latestRoute = this._currentRoute();
          descriptor.lastActivatedAt = this._nextActivationTime();
          this._recordThreadLabel(descriptor.id);
          return;
        }
        await this._switchThread(descriptor, { route, writeHistory: false });
        return;
      }

      const root = this._threads.get(this._rootThreadId);
      if (!root) {
        await this._enterCatalog();
        history.replaceState(this._historyState(), '', location.href);
        return;
      }
      if (root.id === this._threadId) {
        await this._restoreRoute(route);
        root.latestRoute = this._currentRoute();
        root.lastActivatedAt = this._nextActivationTime();
        this._recordThreadLabel(root.id);
      } else {
        await this._switchThread(root, { route, writeHistory: false });
      }
      history.replaceState(this._historyState(), '', location.href);
    });
  }

  async _restoreRoute(route) {
    this._suppressHistoryWrites = true;
    try {
      await this._route(this._parseGlobalRoute(route), true, true);
    } finally {
      this._suppressHistoryWrites = false;
    }
  }

  _captureRuntime() {
    return {
      manifest: this._manifest,
      manifestUrl: this._manifestUrl,
      presentationId: this._presentationId,
      leaves: this._leaves,
      runtimeToken: this._runtimeToken,
      bus: this._bus,
      state: this._state,
      stage: this._stage,
      toc: this._toc,
      thumbnailIndex: this._thumbnailIndex,
      themeLink: this._themeLink,
      current: this._current,
      index: this._index,
      step: this._step,
      navigationDepth: this._navigationDepth,
    };
  }

  _createRuntime(manifest, manifestUrl, presentationId) {
    const runtimeToken = Symbol('presentation runtime');
    manifest.leaves.forEach((leaf) => {
      leaf.runtimeToken = runtimeToken;
    });
    const stage = document.createElement('div');
    stage.className = 'v-stage';
    const toc = document.createElement('nav');
    toc.className = 'v-toc';
    toc.hidden = true;
    toc.setAttribute('aria-label', 'Presentation outline');
    const themeLink = manifest.theme ? document.createElement('link') : null;
    if (themeLink) {
      themeLink.rel = 'stylesheet';
      themeLink.href = manifest.theme;
    }
    return {
      manifest,
      manifestUrl,
      presentationId,
      leaves: manifest.leaves,
      runtimeToken,
      bus: new Bus(),
      state: new StateStore(this._catalogUrl, presentationId),
      stage,
      toc,
      thumbnailIndex: {},
      themeLink,
      current: null,
      index: 0,
      step: 0,
      navigationDepth: null,
    };
  }

  _installRuntime(runtime) {
    for (const [key, value] of Object.entries(runtime)) this[`_${key}`] = value;
  }

  _disposeRuntime(runtime) {
    for (const leaf of runtime.leaves) this._dispose(leaf);
    runtime.themeLink?.remove();
    runtime.stage.remove();
    runtime.toc.remove();
  }

  _routeFromRuntime(runtime) {
    if (!runtime.toc.hidden) return '';
    const address = runtime.leaves[runtime.index]?.address;
    if (!address) return '';
    return runtime.step > 0 ? `${address}/${runtime.step}` : address;
  }

  _nextActivationTime() {
    this._lastActivatedAt = Math.max(Date.now(), this._lastActivatedAt + 1);
    return this._lastActivatedAt;
  }

  _recordThreadLabel(threadId, runtime = null) {
    const manifest = runtime?.manifest || this._manifest;
    const route = runtime ? this._routeFromRuntime(runtime) : this._currentRoute();
    this._threadLabels.set(threadId, this._threadLabel(manifest, route));
  }

  _threadLabel(manifest, route) {
    const parsed = this._parseRoute(route);
    let routeTitle = 'Table of contents';
    if (parsed.view === 'slide') {
      routeTitle = manifest.leavesByAddress.get(parsed.address)?.title || parsed.address;
    }
    return {
      presentationTitle: manifest.title,
      routeTitle,
    };
  }

  _hashForRoute(route) {
    const prefix = `#/${this._presentationId}`;
    return route ? `${prefix}/${route}` : `${prefix}/`;
  }

  async _autoAdvanceInitialRoute() {
    const url = new URL(location.href);
    if (url.searchParams.get('vividly-auto-advance') !== '1') return;

    const route = this._parseHash();
    if (route.view !== 'slide' || route.step !== 0) return;
    const index = this._leaves.findIndex((leaf) => leaf.address === route.address);
    const rec = this._current;
    if (
      index < 0 ||
      index !== this._index ||
      !rec ||
      (rec.steps !== DYNAMIC && rec.steps <= 1)
    ) {
      return;
    }

    this._suppressHistoryWrites = true;
    try {
      await this._show(index, 1, 'forward', false, 1);
    } finally {
      this._suppressHistoryWrites = false;
    }
    if (this._index !== index || this._step !== 1) return;

    url.searchParams.delete('vividly-auto-advance');
    url.hash = this._hashForRoute(`${this._leaves[index].address}/1`);
    history.replaceState(this._historyState(), '', url);
    this._lastHash = url.hash;
  }

  _parseRoute(route) {
    const raw = route.replace(/^#\/?/, '');
    if (!raw) return { view: 'toc' };
    const parts = raw.split('/').filter(Boolean);
    const last = parts[parts.length - 1];
    let step = 0;
    if (/^\d+$/.test(last)) {
      step = Number(last);
      parts.pop();
    }
    return { view: 'slide', address: parts.join('/'), step };
  }

  _parseHash() {
    return this._parseGlobalRoute(location.hash);
  }

  _parseGlobalRoute(hash) {
    const raw = hash.replace(/^#\/?/, '');
    if (!raw) return { view: 'catalog' };
    const [presentationId, ...localParts] = raw.split('/').filter(Boolean);
    if (!this._hasPresentation(presentationId)) return { view: 'invalid' };
    return { ...this._parseRoute(localParts.join('/')), presentationId };
  }

  _presentationIdFromHash() {
    const [presentationId] = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
    return presentationId || null;
  }

  async _route(route = this._parseHash(), enqueueSlide = true, restoring = false) {
    const routeGeneration = this._beginRender();
    if (route.view === 'catalog') {
      await this._enterCatalog();
      return;
    }
    if (route.view === 'invalid') {
      await this._enterCatalog();
      return;
    }
    if (route.presentationId && route.presentationId !== this._presentationId) {
      const localRoute = this._routeText(route);
      const threadId = crypto.randomUUID();
      const descriptor = this._createThreadDescriptor(
        threadId,
        route.presentationId,
        localRoute
      );
      await this._switchThread(descriptor, { route: localRoute, writeHistory: false });
      this._threads.set(threadId, descriptor);
      if (!this._rootThreadId) this._rootThreadId = threadId;
      history.replaceState(this._historyState(), '', location.href);
      return;
    }
    if (route.view === 'toc') {
      const generation = this._beginRender();
      const focusSelection = this._focusTocSelectionOnShow;
      this._focusTocSelectionOnShow = false;
      this._showToc({ focusSelection });
      await this._settleRender(generation, this._toc);
      return;
    }
    const index = this._leaves.findIndex((l) => l.address === route.address);
    if (index < 0) {
      const generation = this._beginRender();
      this._showToc();
      await this._settleRender(generation, this._toc);
      return;
    }
    try {
      await this._preload(this._leaves[index]);
    } catch (error) {
      if (!enqueueSlide) throw error;
      console.error('[vividly]', error);
      if (this._current) await this._settleRender(routeGeneration, this._current.layer);
      return;
    }
    if (!(await this._runKeyboardHintGate(index, route.step))) return;
    const reenter = !this._toc.hidden;
    this._catalogView.hidden = true;
    this._toc.hidden = true;
    this._stage.hidden = false;
    if (enqueueSlide) {
      await this._show(index, route.step, 'forward', reenter, null, restoring);
      return;
    }
    const generation = this._beginRender();
    await this._showNow(index, route.step, 'forward', reenter, null, restoring);
    await this._settleRender(generation, this._current.layer);
  }

  _writeHash(address, step) {
    if (this._suppressHistoryWrites) return;
    const route = step > 0 ? `${address}/${step}` : address;
    const hash = this._hashForRoute(route);
    if (location.hash === hash) return;
    history.pushState(this._historyState(), '', hash);
    this._lastHash = hash;
  }

  _navigateHash(hash) {
    const raw = hash.replace(/^#\/?/, '');
    const [first] = raw.split('/');
    if (raw && !this._hasPresentation(first)) hash = this._hashForRoute(raw);
    if (location.hash === hash) return Promise.resolve();
    history.pushState(this._historyState(), '', hash);
    this._lastHash = hash;
    return this._route();
  }

  _routeText(route) {
    if (route.view === 'toc') return '';
    return route.step > 0 ? `${route.address}/${route.step}` : route.address;
  }

  async _enterCatalog() {
    const generation = this._beginRender();
    if (this._manifest) {
      this._recordCatalogActivation(this._presentationId);
      const source = this._captureRuntime();
      const outgoing = this._threads.get(this._threadId);
      if (outgoing) {
        outgoing.latestRoute = this._routeFromRuntime(source);
        this._recordThreadLabel(outgoing.id, source);
      }
      this._disposeRuntime(source);
      this._clearRuntimeFields();
    }
    this._threadId = null;
    this._showCatalog();
    history.replaceState(this._historyState(), '', location.href);
    await this._settleRender(generation, this._catalogView);
  }

  // --- slide lifecycle ----------------------------------------------------

  _record(leaf) {
    return (leaf.rec ||= { status: 'idle' });
  }

  async _preload(leaf) {
    if (leaf.runtimeToken !== this._runtimeToken) return;
    const runtimeToken = this._runtimeToken;
    const manifest = this._manifest;
    const bus = this._bus;
    const state = this._state;
    const stage = this._stage;
    const rec = this._record(leaf);
    if (rec.ready) return rec.ready;

    rec.ready = (async () => {
      rec.status = 'loading';
      const moduleUrl = leaf.node.moduleUrl;
      const mod = await import(moduleUrl);
      const meta = mod.meta || {};
      const moduleId = moduleIdFor(moduleUrl);
      await adoptModuleStyles(moduleId, moduleUrl, meta.styles);
      if (runtimeToken !== this._runtimeToken) return;

      const scopedBus = bus.scoped();
      const navigator = manifest.navigators.get(leaf.address);
      const navigatorContext = navigator
        ? Object.freeze({
            choiceStartStep: navigator.choiceStartStep,
            afterStep: navigator.afterStep,
            sections: Object.freeze(
              navigator.sections.map((section) => Object.freeze({ ...section }))
            ),
          })
        : null;
      const ctx = new SlideContext({
        moduleUrl,
        dataUrl: leaf.node.dataUrl,
        address: leaf.address,
        props: leaf.node.props,
        bus: scopedBus,
        state: state.scope(leaf.address),
        navigate: (address, step = 0) => this._navigateTo(address, step),
        navigator: navigatorContext,
        enterSection: () => this._enterSection(leaf),
        goUp: () => this._goUp(leaf),
        captureKeys: (handler) => {
          rec.keyHandler = handler;
        },
        dependencyRegistry: this._dependencyRegistry,
      });

      const Ctor = mod.default || Slide;
      const instance = new Ctor(ctx);
      const declared = (await instance.preload()) || {};
      const steps = declared.steps ?? meta.steps ?? 1;
      if (
        navigator &&
        (steps === DYNAMIC || !Number.isInteger(steps) || steps <= navigator.afterStep)
      ) {
        throw new Error(
          `Navigator "${leaf.address}" must declare at least ${navigator.afterStep + 1} fixed steps`
        );
      }

      // The layer is runtime-owned and sits outside the slide's @scope root,
      // so slide CSS cannot override visibility or transition state.
      const layer = document.createElement('div');
      layer.className = 'v-layer';
      layer.hidden = true;
      layer.style.setProperty('--steps', steps === DYNAMIC ? 1 : steps);
      layer.style.setProperty('--step', 0);

      const root = document.createElement('div');
      root.className = 'v-slide';
      root.dataset.vividlyModule = moduleId;
      root.dataset.vividlySlide = leaf.address;
      root.dataset.steps = steps;
      root.dataset.step = 0;
      if (meta.template) {
        root.innerHTML = await (await fetch(new URL(meta.template, moduleUrl))).text();
      }
      if (runtimeToken !== this._runtimeToken) {
        scopedBus.releaseAll();
        instance.dispose();
        return;
      }
      layer.appendChild(root);
      stage.appendChild(layer);
      instance.mount(root);
      let navigatorControls = null;
      try {
        if (navigator) {
          navigatorControls = this._registerNavigatorControls(leaf, navigator, root);
        }
      } catch (error) {
        instance.unmount();
        scopedBus.releaseAll();
        instance.dispose();
        layer.remove();
        throw error;
      }

      Object.assign(rec, {
        status: 'mounted',
        mod,
        meta,
        instance,
        steps,
        layer,
        root,
        scopedBus,
        ctx,
        navigatorControls,
        stepMotion: null,
      });
      bus.emit('vividly:preloaded', { address: leaf.address });
    })();

    return rec.ready;
  }

  _dispose(leaf) {
    const rec = leaf.rec;
    if (!rec || rec.status !== 'mounted') return;
    this._clearStepMotion(rec);
    rec.navigatorControls?.dispose();
    rec.instance.unmount();
    rec.scopedBus.releaseAll();
    rec.instance.dispose();
    rec.layer.remove();
    leaf.rec = { status: 'idle' };
  }

  _updatePreloadWindow() {
    const { prev, next } = this._manifest.preloadWindow;
    const lo = this._index - prev;
    const hi = this._index + next;
    this._leaves.forEach((leaf, i) => {
      if (i < lo || i > hi) this._dispose(leaf);
    });
    const schedule = window.requestIdleCallback || ((fn) => setTimeout(fn, 0));
    for (let i = Math.max(0, lo); i <= Math.min(this._leaves.length - 1, hi); i++) {
      const leaf = this._leaves[i];
      if (i !== this._index) schedule(() => this._preload(leaf));
    }
  }

  // --- navigation ---------------------------------------------------------

  /** Navigation is serialized; overlapping transitions corrupt layer state. */
  _enqueue(fn) {
    this._queue = this._queue.then(fn).catch((err) => console.error('[vividly]', err));
    return this._queue;
  }

  _show(index, step, direction, reenter = false, motionDirection = null, restoring = false) {
    const generation = this._beginRender();
    return this._enqueue(async () => {
      await this._showNow(index, step, direction, reenter, motionDirection, restoring);
      await this._settleRender(generation, this._current.layer);
    });
  }

  async _showNow(
    index, step, direction, reenter = false, motionDirection = null, restoring = false
  ) {
    const leaf = this._leaves[index];
    await this._preload(leaf);
    const rec = leaf.rec;
    const target = rec.steps === DYNAMIC ? step : clamp(step, 0, rec.steps - 1);
    const deepestNavigationLevel = leaf.trail.length - 1;
    this._navigationDepth =
      this._navigationDepth === null
        ? deepestNavigationLevel
        : Math.min(this._navigationDepth, deepestNavigationLevel);

    const outgoing = this._current && this._current !== rec ? this._current : null;
    const changingSlide = outgoing !== null || !this._current;
    const enteringSlide = changingSlide || reenter;
    const boundaryIndex = outgoing ? Math.max(this._index, index) : index;

    if (outgoing) {
      this._clearStepMotion(outgoing);
      outgoing.instance.exit({ direction });
    } else if (reenter) {
      rec.instance.exit({ direction });
    }

    if (enteringSlide) {
      rec.instance.enter({ direction, step: target, restoring });
      rec.ctx.state.set('visited', true);
    }
    this._applyStep(rec, target, motionDirection);

    this._index = index;
    this._step = target;
    this._current = rec;
    this._writeHash(leaf.address, target);
    rec.ctx.state.set('step', target);

    const focusArrival =
      this._navigatorArrivalFocus === leaf.address ||
      (enteringSlide && !restoring && document.activeElement === document.body);
    this._navigatorArrivalFocus = null;
    if (changingSlide) {
      const boundary = this._leaves[boundaryIndex];
      const transition = boundary.node.transition || this._manifest.transition;
      await this._transition(rec.layer, transition, direction);
    }
    if (focusArrival && this._current === rec) this._focusNavigatorControl(rec, target);
    if (enteringSlide) {
      this._bus.emit('vividly:slide-enter', { address: leaf.address });
    }
    this._bus.emit('vividly:step', { address: leaf.address, step: target });
    this._updatePreloadWindow();
  }

  _applyStep(rec, n, motionDirection = null) {
    const baseline =
      motionDirection === null ? null : new Set(rec.root.getAnimations({ subtree: true }));
    this._beginStepMotion(rec, motionDirection, baseline);
    rec.root.dataset.step = n;
    // Numeric mirror of data-step, so CSS can do arithmetic on it.
    rec.layer.style.setProperty('--step', n);
    rec.instance.setStep(n);
    this._syncNavigatorControls(rec, n);
  }

  _beginStepMotion(rec, direction, baseline = null) {
    this._clearStepMotion(rec);
    direction ??= 1;
    if (Math.sign(direction) === 0) return;
    rec.stepMotion = {
      direction: Math.sign(direction),
      startedAt: performance.now(),
      baseline,
      transitions: new Set(),
    };
  }

  _clearStepMotion(rec) {
    rec.stepMotion = null;
  }

  _discoverStepTransitions(rec) {
    const motion = rec.stepMotion;
    if (!motion?.baseline) return;
    motion.transitions = new Set(
      rec.root.getAnimations({ subtree: true }).filter((animation) => {
        if (!(animation instanceof CSSTransition) || motion.baseline.has(animation)) {
          return false;
        }
        const endTime = animation.effect?.getComputedTiming().endTime;
        return (
          Number.isFinite(endTime) &&
          animation.playState !== 'finished' &&
          animation.playState !== 'idle'
        );
      })
    );
    motion.baseline = null;
  }

  _settleStepMotion(rec, direction, requestedAt) {
    const motion = rec.stepMotion;
    if (!motion || motion.direction !== Math.sign(direction)) return STEP_SETTLING_NONE;

    let settledTransitions = false;
    for (const animation of motion.transitions) {
      if (animation.playState === 'finished' || animation.playState === 'idle') continue;
      if (animation.playbackRate <= 0) animation.playbackRate = 1;
      animation.finish();
      settledTransitions = true;
    }
    motion.transitions.clear();
    const settledCustomMotion = rec.instance.settleStep?.() === true;
    if (!settledTransitions && !settledCustomMotion) return STEP_SETTLING_NONE;

    this._clearStepMotion(rec);
    return settledCustomMotion || requestedAt - motion.startedAt > STEP_SETTLING_GRACE_MS
      ? STEP_SETTLING_CONSUME
      : STEP_SETTLING_CONTINUE;
  }

  _registerNavigatorControls(leaf, navigator, root) {
    const choices = Array(navigator.sections.length).fill(null);
    const markedChoices = [...root.querySelectorAll('[data-vividly-navigator-choice]')];
    for (const control of markedChoices) {
      if (!(control instanceof HTMLElement)) {
        throw new Error(`Navigator "${leaf.address}" choice markers must be HTML elements`);
      }
      const rawIndex = control.getAttribute('data-vividly-navigator-choice');
      if (!/^(0|[1-9]\d*)$/.test(rawIndex || '')) {
        throw new Error(
          `Navigator "${leaf.address}" has invalid choice marker "${rawIndex || ''}"`
        );
      }
      const index = Number(rawIndex);
      if (index >= choices.length) {
        throw new Error(
          `Navigator "${leaf.address}" choice marker ${index} is out of range`
        );
      }
      if (choices[index]) {
        throw new Error(
          `Navigator "${leaf.address}" has duplicate choice marker ${index}`
        );
      }
      choices[index] = control;
    }

    const missing = choices.findIndex((control) => control === null);
    if (missing >= 0) {
      throw new Error(`Navigator "${leaf.address}" is missing choice marker ${missing}`);
    }

    const afterControls = [...root.querySelectorAll('[data-vividly-navigator-after]')];
    if (afterControls.length > 1) {
      throw new Error(
        `Navigator "${leaf.address}" must render at most one after control`
      );
    }
    const after = afterControls[0] || null;
    if (after && !(after instanceof HTMLElement)) {
      throw new Error(`Navigator "${leaf.address}" after control must be an HTML element`);
    }
    if (
      after &&
      !after.textContent.trim() &&
      !after.getAttribute('aria-label')?.trim() &&
      !after.getAttribute('aria-labelledby')?.trim()
    ) {
      throw new Error(`Navigator "${leaf.address}" after control needs an accessible name`);
    }

    const listeners = [];

    choices.forEach((control, index) => {
      const section = navigator.sections[index];
      const handler = () => {
        this._activateNavigatorChoice(leaf, section).catch((error) => {
          console.error('[vividly]', error);
        });
      };
      control.addEventListener('click', handler);
      listeners.push([control, handler]);
    });

    if (after) {
      const afterHandler = () => {
        this._activateNavigatorAfter(leaf, navigator).catch((error) => {
          console.error('[vividly]', error);
        });
      };
      after.addEventListener('click', afterHandler);
      listeners.push([after, afterHandler]);
    }

    return {
      choices,
      after,
      sections: navigator.sections,
      afterStep: navigator.afterStep,
      dispose() {
        for (const [control, handler] of listeners) {
          control.removeEventListener('click', handler);
        }
      },
    };
  }

  async _activateNavigatorChoice(leaf, section) {
    if (this._leaves[this._index] !== leaf || this._step !== section.step) {
      await this._navigateTo(leaf.address, section.step);
    }
    await this._enterSection(leaf);
  }

  async _activateNavigatorAfter(leaf, navigator) {
    if (this._leaves[this._index] !== leaf || this._step !== navigator.afterStep) {
      await this._navigateTo(leaf.address, navigator.afterStep);
    }
    await this._advance(1, false);
  }

  _syncNavigatorControls(rec, step) {
    const controls = rec.navigatorControls;
    if (!controls) return;

    controls.choices.forEach((control, index) => {
      const active = controls.sections[index].step === step;
      control.tabIndex = active ? 0 : -1;
      control.setAttribute('aria-current', active ? 'step' : 'false');
    });

    const afterActive = step === controls.afterStep;
    if (controls.after) {
      controls.after.inert = !afterActive;
      controls.after.tabIndex = afterActive ? 0 : -1;
      controls.after.setAttribute('aria-hidden', String(!afterActive));
      controls.after.setAttribute('aria-current', afterActive ? 'step' : 'false');
    }
  }

  _focusNavigatorControl(rec, step) {
    const controls = rec?.navigatorControls;
    if (!controls) return;
    const sectionIndex = controls.sections.findIndex((section) => section.step === step);
    const target =
      sectionIndex >= 0
        ? controls.choices[sectionIndex]
        : step === controls.afterStep
          ? controls.after
          : null;
    if (target) {
      target.focus({ preventScroll: true });
    } else if (
      document.activeElement instanceof HTMLElement &&
      rec.root.contains(document.activeElement)
    ) {
      document.activeElement.blur();
    }
  }

  async _navigateTo(address, step = 0) {
    const index = this._leaves.findIndex((l) => l.address === address);
    if (index < 0) return;
    this._beginRender();
    const direction = index < this._index ? 'backward' : 'forward';
    const reenter = !this._toc.hidden;
    this._toc.hidden = true;
    this._stage.hidden = false;
    if (!(await this._runKeyboardHintGate(index, step))) return;
    return this._show(index, step, direction, reenter);
  }

  _navigateRoute(route) {
    return this._navigateTo(route.address, route.step);
  }

  async _navigateRouteNow(route, motionDirection = null) {
    const index = this._leaves.findIndex((leaf) => leaf.address === route.address);
    if (index < 0) return;
    if (this._manifest.navigators.has(route.address)) {
      this._navigatorArrivalFocus = route.address;
    }
    const direction = index < this._index ? 'backward' : 'forward';
    await this._showNow(index, route.step, direction, false, motionDirection);
  }

  _assertCurrentLeaf(leaf) {
    if (this._leaves[this._index] !== leaf) {
      throw new Error(`Slide "${leaf.address}" does not own the active presentation`);
    }
  }

  _enterSection(leaf) {
    this._assertCurrentLeaf(leaf);
    const navigator = this._manifest.navigators.get(leaf.address);
    if (!navigator) throw new Error(`Slide "${leaf.address}" is not a navigator`);
    const section = this._navigatorSectionAtStep(navigator, this._step);
    if (!section) return Promise.resolve(false);
    const owner = this._manifest.sectionOwners.get(section.address);
    const step = this._navigatorArrivalStep(owner.entryAddress, 0, 1);
    return this._navigateTo(owner.entryAddress, step).then(() => true);
  }

  _navigatorSectionAtStep(navigator, step) {
    return navigator.sections.find((section) => section.step === step) || null;
  }

  _isNavigatorInterval(navigator, step = this._step) {
    return step >= navigator.choiceStartStep && step <= navigator.afterStep;
  }

  // Reverse sequential arrival skips completion; explicit child returns preserve it.
  _navigatorArrivalStep(address, step, direction) {
    const navigator = this._manifest.navigators.get(address);
    if (!navigator) return step;
    let arrival = step;
    if (direction < 0 && step === navigator.afterStep) {
      arrival = navigator.sections.at(-1).step;
    }
    if (arrival >= navigator.choiceStartStep && arrival <= navigator.afterStep) {
      this._navigatorArrivalFocus = address;
    }
    return arrival;
  }

  _nearestSectionOwner(sectionAddress) {
    let address = sectionAddress;
    while (address) {
      const owner = this._manifest.sectionOwners.get(address);
      if (owner) return owner;
      address = this._manifest.sections.get(address)?.parentAddress;
    }
    return null;
  }

  _goUp(leaf) {
    this._assertCurrentLeaf(leaf);
    const owner = this._nearestSectionOwner(leaf.sectionAddress);
    if (!owner) return Promise.resolve(false);
    this._navigatorArrivalFocus = owner.navigatorAddress;
    return this._navigateRoute(owner.backwardRoute).then(() => true);
  }

  _moveNavigatorSelection(direction) {
    const generation = this._beginRender();
    const requestedAt = performance.now();
    return this._enqueue(async () => {
      const leaf = this._leaves[this._index];
      const navigator = this._manifest.navigators.get(leaf.address);
      if (!navigator) return;

      const forward = direction === 'right' || direction === 'down';
      if (this._step === navigator.afterStep) {
        if (forward) {
          await this._advanceNow(1, true, requestedAt);
        } else {
          await this._moveNavigatorStepNow(navigator.sections.at(-1).step, requestedAt);
        }
      } else {
        const controls = this._current.navigatorControls;
        const currentIndex = navigator.sections.findIndex(
          (section) => section.step === this._step
        );
        const spatialIndex = this._navigatorSpatialNeighborIndex(
          controls.choices,
          currentIndex,
          direction
        );
        if (direction === 'up' && spatialIndex === null) {
          const owner = this._nearestSectionOwner(leaf.sectionAddress);
          if (owner) await this._navigateRouteNow(owner.backwardRoute);
        } else {
          const targetIndex = spatialIndex ?? currentIndex + (forward ? 1 : -1);
          if (targetIndex < 0) {
            await this._advanceNow(-1, true, requestedAt);
          } else if (targetIndex >= navigator.sections.length) {
            const settlement = this._settleStepMotion(this._current, 1, requestedAt);
            if (settlement !== STEP_SETTLING_CONSUME) {
              if (navigator.afterStep < this._current.steps - 1) {
                await this._showNow(this._index, navigator.afterStep + 1, 'forward', false, 1);
              } else {
                await this._exitNavigatorForwardNow(navigator, 1);
              }
            }
          } else {
            await this._moveNavigatorStepNow(navigator.sections[targetIndex].step, requestedAt);
          }
        }
      }
      this._focusNavigatorControl(this._current, this._step);
      await this._settleRender(generation, this._current.layer);
    });
  }

  async _moveNavigatorStepNow(targetStep, requestedAt = performance.now()) {
    const direction = Math.sign(targetStep - this._step);
    if (direction === 0) return;
    const settlement = this._settleStepMotion(this._current, direction, requestedAt);
    if (settlement === STEP_SETTLING_CONSUME) return;
    await this._showNow(
      this._index,
      targetStep,
      direction > 0 ? 'forward' : 'backward',
      false,
      direction
    );
  }

  _navigatorSpatialNeighborIndex(choices, currentIndex, direction) {
    const current = choices[currentIndex]?.getBoundingClientRect();
    if (!current) return null;
    const horizontal = direction === 'left' || direction === 'right';
    const positive = direction === 'right' || direction === 'down';
    const currentPrimary = horizontal
      ? (current.left + current.right) / 2
      : (current.top + current.bottom) / 2;
    const currentCross = horizontal
      ? (current.top + current.bottom) / 2
      : (current.left + current.right) / 2;

    const candidates = [];
    choices.forEach((choice, index) => {
      if (index === currentIndex) return;
      const rect = choice.getBoundingClientRect();
      const primary = horizontal
        ? (rect.left + rect.right) / 2
        : (rect.top + rect.bottom) / 2;
      if (positive ? primary <= currentPrimary : primary >= currentPrimary) return;
      const overlaps = horizontal
        ? Math.min(current.bottom, rect.bottom) > Math.max(current.top, rect.top)
        : Math.min(current.right, rect.right) > Math.max(current.left, rect.left);
      if (!overlaps) return;
      const cross = horizontal
        ? (rect.top + rect.bottom) / 2
        : (rect.left + rect.right) / 2;
      candidates.push({
        index,
        primaryDistance: Math.abs(primary - currentPrimary),
        crossDistance: Math.abs(cross - currentCross),
      });
    });

    candidates.sort(
      (left, right) =>
        left.primaryDistance - right.primaryDistance ||
        left.crossDistance - right.crossDistance ||
        left.index - right.index
    );
    return candidates[0]?.index ?? null;
  }

  _structuralBoundary(index, delta) {
    let sectionAddress = this._leaves[index].sectionAddress;
    while (sectionAddress) {
      const section = this._manifest.sections.get(sectionAddress);
      const owner = this._manifest.sectionOwners.get(sectionAddress);
      if (owner) {
        if (delta > 0 && index === section.lastLeafIndex) return owner.forwardRoute;
        if (delta < 0 && index === section.firstLeafIndex) return owner.backwardRoute;
      }
      sectionAddress = section.parentAddress;
    }
    return null;
  }

  _sectionCompletionRoute(section) {
    for (const navigator of this._manifest.navigators.values()) {
      if (navigator.sectionAddress !== section.address) continue;
      const finalSection = this._manifest.sections.get(navigator.sections.at(-1).address);
      if (finalSection.lastLeafIndex === section.lastLeafIndex) {
        return { address: navigator.address, step: navigator.afterStep };
      }
    }
    return null;
  }

  async _navigateToSectionEndNow(section, motionDirection = null) {
    const completionRoute = this._sectionCompletionRoute(section);
    if (completionRoute) {
      await this._navigateToNavigatorEndNow(completionRoute, motionDirection);
      return;
    }

    const leaf = this._leaves[section.lastLeafIndex];
    await this._preload(leaf);
    await this._showNow(
      section.lastLeafIndex,
      Math.max(0, stepCount(leaf.rec) - 1),
      'backward',
      false,
      motionDirection
    );
  }

  async _navigateToNavigatorEndNow(route, motionDirection = null) {
    const index = this._leaves.findIndex((leaf) => leaf.address === route.address);
    if (index < 0) return;
    const leaf = this._leaves[index];
    await this._preload(leaf);
    const navigator = this._manifest.navigators.get(route.address);
    const step =
      navigator && route.step === navigator.afterStep
        ? Math.max(route.step, stepCount(leaf.rec) - 1)
        : route.step;
    await this._showNow(
      index,
      this._navigatorArrivalStep(route.address, step, -1),
      'backward',
      false,
      motionDirection
    );
  }

  _precedingNavigatorCompletion(index) {
    if (index === 0) return null;
    let sectionAddress = this._leaves[index - 1].sectionAddress;
    let completionRoute = null;
    while (sectionAddress) {
      const section = this._manifest.sections.get(sectionAddress);
      if (section.lastLeafIndex !== index - 1) break;
      completionRoute =
        this._manifest.sectionOwners.get(sectionAddress)?.forwardRoute ||
        this._sectionCompletionRoute(section) ||
        completionRoute;
      sectionAddress = section.parentAddress;
    }
    return completionRoute;
  }

  _advance(delta, incremental = true) {
    const generation = this._beginRender();
    const requestedAt = performance.now();
    return this._enqueue(async () => {
      await this._advanceNow(delta, incremental, requestedAt);
      await this._settleRender(generation, this._current.layer);
    });
  }

  async _advanceNow(delta, incremental = true, requestedAt = performance.now()) {
    const rec = this._current;
    if (!rec) return;
    const motionDirection = incremental ? Math.sign(delta) : null;
    const settlement = incremental
      ? this._settleStepMotion(rec, motionDirection, requestedAt)
      : STEP_SETTLING_NONE;
    if (settlement === STEP_SETTLING_CONSUME) return;
    if (!incremental) this._clearStepMotion(rec);

    const leaf = this._leaves[this._index];
    const navigator = this._manifest.navigators.get(leaf.address);
    if (navigator && this._isNavigatorInterval(navigator)) {
      const section = this._navigatorSectionAtStep(navigator, this._step);
      if (delta > 0 && section) {
        const owner = this._manifest.sectionOwners.get(section.address);
        await this._navigateRouteNow(
          {
            address: owner.entryAddress,
            step: this._navigatorArrivalStep(owner.entryAddress, 0, 1),
          },
          motionDirection
        );
        return;
      }

      if (delta < 0 && this._step > navigator.choiceStartStep) {
        const previous = this._navigatorSectionAtStep(navigator, this._step - 1);
        const previousSection = this._manifest.sections.get(previous.address);
        await this._navigateToSectionEndNow(previousSection, motionDirection);
        return;
      }

      if (
        delta > 0 &&
        this._step === navigator.afterStep &&
        navigator.afterStep === rec.steps - 1
      ) {
        await this._exitNavigatorForwardNow(navigator, motionDirection);
        return;
      }
    }

    if (
      navigator &&
      delta > 0 &&
      this._step > navigator.afterStep &&
      this._step === rec.steps - 1
    ) {
      await this._exitNavigatorForwardNow(navigator, motionDirection);
      return;
    }

    if (rec.steps === DYNAMIC) {
      const baseline =
        motionDirection === null ? null : new Set(rec.root.getAnimations({ subtree: true }));
      if (rec.instance.advance(delta)) {
        this._beginStepMotion(rec, motionDirection, baseline);
        return;
      }
    } else {
      const next = this._step + delta;
      if (next >= 0 && next < rec.steps) {
        this._step = next;
        this._applyStep(rec, next, motionDirection);
        this._writeHash(this._leaves[this._index].address, next);
        rec.ctx.state.set('step', next);
        this._bus.emit('vividly:step', { address: this._leaves[this._index].address, step: next });
        return;
      }
    }

    const structuralRoute = this._structuralBoundary(this._index, delta);
    if (structuralRoute) {
      await this._navigateRouteNow(structuralRoute, motionDirection);
      return;
    }

    if (delta < 0) {
      const completionRoute = this._precedingNavigatorCompletion(this._index);
      if (completionRoute) {
        await this._navigateToNavigatorEndNow(completionRoute, motionDirection);
        return;
      }
    }

    const index = this._index + Math.sign(delta);
    if (index < 0 || index >= this._leaves.length) return;
    // Entering backwards lands on the previous slide's last step.
    const destination = this._leaves[index];
    await this._preload(destination);
    const step = this._navigatorArrivalStep(
      destination.address,
      delta < 0 ? Math.max(0, stepCount(destination.rec) - 1) : 0,
      delta
    );
    await this._showNow(
      index,
      step,
      delta > 0 ? 'forward' : 'backward',
      false,
      motionDirection
    );
  }

  async _exitNavigatorForwardNow(navigator, motionDirection = null) {
    const sectionAddress = this._leaves[this._index].sectionAddress;
    if (!sectionAddress) {
      const finalSection = this._manifest.sections.get(navigator.sections.at(-1).address);
      const target = finalSection.lastLeafIndex + 1;
      if (target < this._leaves.length) {
        const step = this._navigatorArrivalStep(this._leaves[target].address, 0, 1);
        await this._showNow(target, step, 'forward', false, motionDirection);
      }
      return;
    }

    const section = this._manifest.sections.get(sectionAddress);
    const owner = this._nearestSectionOwner(section.address);
    if (owner) {
      await this._navigateRouteNow(owner.forwardRoute, motionDirection);
      return;
    }

    const target = section.lastLeafIndex + 1;
    if (target < this._leaves.length) {
      const step = this._navigatorArrivalStep(this._leaves[target].address, 0, 1);
      await this._showNow(target, step, 'forward', false, motionDirection);
    }
  }

  _goToSlideEdge(edge) {
    if (!this._current || this._current.steps === DYNAMIC) return;
    const step = edge === 'end' ? Math.max(0, stepCount(this._current) - 1) : 0;
    this._show(this._index, step, edge === 'end' ? 'forward' : 'backward');
  }

  _changeNavigationDepth(delta) {
    const trail = this._leaves[this._index]?.trail;
    if (!trail) return;
    const current = this._navigationDepth ?? trail.length - 1;
    this._navigationDepth = clamp(current + delta, 0, trail.length - 1);
    this._showNavigationHud();
  }

  _navigationGroupKey(leaf) {
    const depth = Math.min(this._navigationDepth ?? leaf.trail.length - 1, leaf.trail.length - 1);
    return JSON.stringify(leaf.trail.slice(0, depth + 1).map((node) => node.id));
  }

  _jumpSubtree(delta) {
    const currentKey = this._navigationGroupKey(this._leaves[this._index]);
    let target = this._index;
    if (delta > 0) {
      do target += 1;
      while (
        target < this._leaves.length &&
        this._navigationGroupKey(this._leaves[target]) === currentKey
      );
    } else {
      while (
        target > 0 &&
        this._navigationGroupKey(this._leaves[target - 1]) === currentKey
      ) {
        target -= 1;
      }
      target -= 1;
    }

    const generation = this._beginRender();
    this._enqueue(async () => {
      const structuralRoute = this._structuralBoundary(this._index, delta);
      if (structuralRoute) {
        await this._navigateRouteNow(structuralRoute);
        this._showNavigationHud();
        await this._settleRender(generation, this._current.layer);
        return;
      }
      if (target < 0 || target >= this._leaves.length) {
        this._showNavigationHud();
        await this._settleRender(generation, this._current.layer);
        return;
      }
      const leaf = this._leaves[target];
      await this._preload(leaf);
      const step = delta < 0 && leaf.rec.steps !== DYNAMIC ? stepCount(leaf.rec) - 1 : 0;
      await this._showNow(target, step, delta > 0 ? 'forward' : 'backward');
      this._showNavigationHud();
      await this._settleRender(generation, this._current.layer);
    });
  }

  _showNavigationHud() {
    const trail = this._leaves[this._index]?.trail;
    if (!trail) return;
    clearTimeout(this._navigationHudTimer);
    this._navigationHud.replaceChildren();

    const root = document.createElement('span');
    root.className = 'v-navigation-hud-root';
    root.textContent = this._manifest.title;
    this._navigationHud.append(root);
    trail.forEach((node, depth) => {
      const separator = document.createElement('span');
      separator.className = 'v-navigation-hud-separator';
      separator.textContent = '›';
      const item = document.createElement('span');
      item.className = 'v-navigation-hud-item';
      item.textContent = node.title || node.id;
      if (depth === this._navigationDepth) item.dataset.active = '';
      this._navigationHud.append(separator, item);
    });
    this._navigationHud.hidden = false;
    this._navigationHudTimer = setTimeout(() => {
      this._navigationHud.hidden = true;
    }, NAVIGATION_HUD_DURATION_MS);
  }

  _hideNavigationHud() {
    clearTimeout(this._navigationHudTimer);
    this._navigationHud.hidden = true;
  }

  _buildKeyboardHelp() {
    const overlay = document.createElement('div');
    overlay.className = 'v-keyboard-help';
    overlay.hidden = true;
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'v-keyboard-help-title');
    overlay.tabIndex = -1;
    overlay.innerHTML = `
      <div class="v-keyboard-help-panel">
        <h2 id="v-keyboard-help-title">Keyboard shortcuts</h2>
        <p class="v-touch-instructions">Swipe left to continue, or right to go back.
          You can also use Previous and Next below the slide. Tap a section to open it.</p>
        <div class="v-keyboard-help-groups">
          <section>
            <h3>Steps</h3>
            <dl>
              <div><dt><kbd>Space</kbd></dt><dd>Next structural state</dd></div>
              <div><dt><kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Right Arrow">→</kbd></dt><dd>Move right or advance an ordinary step</dd></div>
              <div><dt><kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Left Arrow">←</kbd></dt><dd>Move left or reverse an ordinary step</dd></div>
              <div><dt><kbd>Home</kbd><small>(<kbd>Fn</kbd> + <kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Left Arrow">←</kbd>)</small></dt><dd>First step in slide</dd></div>
              <div><dt><kbd>End</kbd><small>(<kbd>Fn</kbd> + <kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Right Arrow">→</kbd>)</small></dt><dd>Last step in slide</dd></div>
            </dl>
          </section>
          <section>
            <h3>Slides and sections</h3>
            <dl>
              <div><dt><kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Left Arrow">←</kbd><kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Up Arrow">↑</kbd><kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Down Arrow">↓</kbd><kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Right Arrow">→</kbd></dt><dd>Move navigator selection</dd></div>
              <div><dt><kbd>Enter</kbd></dt><dd>Open navigator selection</dd></div>
              <div><dt><kbd>PgDn</kbd><small>(<kbd>Fn</kbd> + <kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Down Arrow">↓</kbd>)</small></dt><dd>Next at selected level</dd></div>
              <div><dt><kbd>PgUp</kbd><small>(<kbd>Fn</kbd> + <kbd class="v-keyboard-help-symbol v-keyboard-help-arrow" aria-label="Up Arrow">↑</kbd>)</small></dt><dd>Previous at selected level</dd></div>
              <div><dt><kbd>[</kbd></dt><dd>Move level outward</dd></div>
              <div><dt><kbd>]</kbd></dt><dd>Move level inward</dd></div>
            </dl>
          </section>
          <section>
            <h3>Views</h3>
            <dl>
              <div><dt><kbd>Esc</kbd></dt><dd>Table of contents</dd></div>
              <div><dt><kbd>G</kbd></dt><dd>TOC Grid mode</dd></div>
              <div><dt><kbd>O</kbd></dt><dd>TOC Outline mode</dd></div>
              <div><dt><kbd>S</kbd></dt><dd>TOC expand or collapse steps</dd></div>
              <div><dt><kbd class="v-keyboard-help-symbol">?</kbd></dt><dd>Keyboard help</dd></div>
            </dl>
          </section>
        </div>
        <label class="v-keyboard-help-hints">
          <input type="checkbox">
          Show navigation hints when presentations start
        </label>
        <p>Press any key or click anywhere to close.</p>
      </div>`;
    overlay.querySelector('.v-keyboard-help-hints input').addEventListener('change', (event) => {
      this._setKeyboardHintsSuppressed(!event.target.checked);
    });
    return overlay;
  }

  _showKeyboardHelp() {
    if (this.hasAttribute('data-capture')) return;
    this._finishKeyboardHints(true);
    clearTimeout(this._keyboardHelpTimer);
    delete this._keyboardHelp.dataset.closing;
    this._syncKeyboardHintPreference();
    this._helpReturnFocus = document.activeElement;
    this._keyboardHelp.hidden = false;
    this._keyboardHelp.focus({ preventScroll: true });
  }

  _hideKeyboardHelp(restoreFocus = true) {
    if (this._keyboardHelp.hidden || this._keyboardHelp.dataset.closing !== undefined) return;
    this._keyboardHelp.dataset.closing = '';
    this._keyboardHelpTimer = setTimeout(() => {
      this._keyboardHelp.hidden = true;
      delete this._keyboardHelp.dataset.closing;
    }, KEYBOARD_HELP_TRANSITION_MS);
    if (restoreFocus && this._helpReturnFocus instanceof HTMLElement) {
      this._helpReturnFocus.focus({ preventScroll: true });
    }
    this._helpReturnFocus = null;
  }

  _buildKeyboardHints() {
    const hints = document.createElement('div');
    hints.className = 'v-keyboard-hints';
    hints.hidden = true;
    hints.setAttribute('role', 'dialog');
    hints.setAttribute('aria-modal', 'true');
    hints.setAttribute('aria-label', 'Keyboard navigation');
    hints.tabIndex = -1;
    hints.innerHTML = `
      <div class="v-keyboard-hints-panel">
        <strong>Getting started</strong>
        <p class="v-touch-instructions">Swipe left to continue, or right to go back.
          Use Previous and Next below the slide, or tap a section to open it.
          Scroll normally to read; interactive controls keep their own gestures.</p>
        <details class="v-keyboard-hints-keyboard">
          <summary>Keyboard shortcuts</summary>
          <div class="v-keyboard-hints-groups">
            <section>
              <h2>Moving through the presentation</h2>
              <dl>
                <div><dt><kbd>Space</kbd></dt><dd>Continue to the next step</dd></div>
                <div><dt><kbd class="v-keyboard-help-arrow" aria-label="Left Arrow">←</kbd><kbd class="v-keyboard-help-arrow" aria-label="Right Arrow">→</kbd></dt><dd>Go back / forward one step</dd></div>
                <div><dt><kbd class="v-keyboard-help-arrow" aria-label="Up Arrow">↑</kbd></dt><dd>Go up to the section containing this slide</dd></div>
              </dl>
            </section>
            <section>
              <h2>Choosing a slide or section</h2>
              <dl>
                <div><dt><kbd class="v-keyboard-help-arrow" aria-label="Left Arrow">←</kbd><kbd class="v-keyboard-help-arrow" aria-label="Up Arrow">↑</kbd><kbd class="v-keyboard-help-arrow" aria-label="Down Arrow">↓</kbd><kbd class="v-keyboard-help-arrow" aria-label="Right Arrow">→</kbd></dt><dd>Highlight a slide or section</dd></div>
                <div><dt><kbd>Enter</kbd></dt><dd>Open the highlighted slide or section</dd></div>
              </dl>
            </section>
          </div>
          <div class="v-keyboard-hints-shortcuts">
            <span><kbd>Esc</kbd> Open the table of contents</span>
            <span><kbd>?</kbd> Show keyboard help</span>
          </div>
        </details>
        <p class="v-keyboard-hints-progress">
          A yellow bar shows an animation in progress. Press <b>Space</b> or <b>→</b> to finish it immediately.
          <span class="v-keyboard-hints-progress-example" aria-hidden="true">
            <span class="v-step-progress-track">
              <span class="v-step-progress-fill"></span>
            </span>
          </span>
        </p>
        <div class="v-keyboard-hints-actions">
          <label><input type="checkbox"> Don't show these tips again</label>
          <div class="v-keyboard-hints-start">
            <button type="button">Start presentation</button>
            <small class="v-keyboard-hints-pointer-prompt">Click anywhere or press a key to start.</small>
            <small class="v-touch-instructions">Tap anywhere to start.</small>
          </div>
        </div>
        <small class="v-keyboard-hints-branding">
          <a href="https://mikehopcroft.github.io/vividly/?vividly-skip-hints=1#/vividly/opening"
             target="_blank" rel="noopener noreferrer">Powered by
            <img src="${new URL('../assets/logo-cropped.svg', import.meta.url).href}"
                 alt="Vividly">
          </a>
        </small>
      </div>`;
    hints.querySelector('input').addEventListener('change', (event) => {
      this._setKeyboardHintsSuppressed(event.target.checked);
    });
    hints.addEventListener('click', (event) => {
      event.stopPropagation();
      if (event.target.closest('label, input, summary, a[href]')) return;
      event.preventDefault();
      this._finishKeyboardHints(true);
    });
    return hints;
  }

  _runKeyboardHintGate(index, step) {
    if (this._keyboardHintRuntimes.has(this._runtimeToken)) return Promise.resolve(true);
    this._keyboardHintRuntimes.add(this._runtimeToken);
    if (
      index !== 0 || step !== 0 || this.hasAttribute('data-capture') ||
      new URLSearchParams(location.search).get('vividly-skip-hints') === '1'
    ) {
      return Promise.resolve(true);
    }

    const policy = this._manifest.keyboardHints;
    const suppressed = this._siteState.scope('~keyboardHints').get('suppressed', false);
    if (
      policy === 'never' ||
      (policy === 'auto' && (suppressed || this._keyboardHintShownThisPage))
    ) {
      return Promise.resolve(true);
    }

    this._keyboardHintShownThisPage = true;
    const suppressToggle = this._keyboardHints.querySelector('input');
    suppressToggle.disabled = policy !== 'auto';
    suppressToggle.checked = policy === 'auto' && suppressed;
    this._keyboardHints.querySelector('details').open =
      !window.matchMedia('(max-width: 40rem)').matches;
    this._keyboardHints.hidden = false;
    delete this._keyboardHints.dataset.closing;
    this.setAttribute('data-keyboard-hints', '');
    this._keyboardHints.querySelector('button').focus({ preventScroll: true });
    return new Promise((resolve) => {
      this._keyboardHintResolve = resolve;
    });
  }

  _finishKeyboardHints(activate) {
    if (!this._keyboardHintResolve && this._keyboardHints.hidden) return false;
    if (this._keyboardHints.dataset.closing !== undefined) {
      if (activate) return true;
      clearTimeout(this._keyboardHintTimer);
      this._keyboardHintTimer = null;
    } else if (activate) {
      this._keyboardHints.dataset.closing = '';
      this._keyboardHintTimer = setTimeout(() => {
        this._keyboardHintTimer = null;
        this._completeKeyboardHints(true);
      }, KEYBOARD_HINT_FADE_MS);
      return true;
    }
    this._completeKeyboardHints(activate);
    return true;
  }

  _completeKeyboardHints(activate) {
    this._keyboardHints.hidden = true;
    delete this._keyboardHints.dataset.closing;
    this.removeAttribute('data-keyboard-hints');
    const resolve = this._keyboardHintResolve;
    this._keyboardHintResolve = null;
    resolve?.(activate);
  }

  _setKeyboardHintsSuppressed(suppressed) {
    this._siteState.scope('~keyboardHints').set('suppressed', suppressed);
    this._keyboardHints.querySelector('input').checked = suppressed;
    this._syncKeyboardHintPreference();
  }

  _syncKeyboardHintPreference() {
    const toggle = this._keyboardHelp.querySelector('.v-keyboard-help-hints input');
    const policy = this._manifest?.keyboardHints || 'auto';
    const suppressed = this._siteState.scope('~keyboardHints').get('suppressed', false);
    toggle.disabled = policy !== 'auto';
    toggle.checked = policy === 'always' || (policy === 'auto' && !suppressed);
  }

  // --- transitions --------------------------------------------------------

  async _transition(incoming, name, direction) {
    const generation = ++this._generation;
    const layers = [...this._stage.children];

    // A navigation during a transition cancels it and snaps.
    for (const layer of layers) {
      layer.getAnimations().forEach((a) => a.finish());
      layer.classList.remove('v-enter', 'v-leave');
    }

    const outgoing = layers.filter((l) => l !== incoming && !l.hidden);
    for (const el of [incoming, ...outgoing]) {
      el.dataset.transition = name;
      el.dataset.direction = direction;
    }
    incoming.hidden = false;
    incoming.classList.add('v-enter');
    outgoing.forEach((el) => el.classList.add('v-leave'));
    void incoming.offsetWidth;

    const animations = [incoming, ...outgoing].flatMap((el) => el.getAnimations());
    const settled = Promise.all(animations.map((a) => a.finished.catch(() => {})));
    await Promise.race([settled, delay(TRANSITION_TIMEOUT_MS)]);
    if (generation !== this._generation) return;

    animations.forEach((a) => a.finish());
    this._reconcileLayers();
  }

  /** Visibility is derived from the current slide, never from a captured pair. */
  _reconcileLayers() {
    for (const layer of this._stage.children) {
      layer.classList.remove('v-enter', 'v-leave');
      layer.hidden = layer !== this._current?.layer;
    }
  }

  // --- render readiness --------------------------------------------------

  _beginRender() {
    this._touch?.cancel();
    const generation = ++this._renderGeneration;
    delete this.dataset.renderReady;
    return generation;
  }

  async _settleRender(generation, root) {
    this._touch?.sync();
    await document.fonts.ready;
    const images = [...root.querySelectorAll('img')].filter(
      (image) =>
        image.dataset.vividlyOptionalImage === undefined && image.getClientRects().length
    );
    await Promise.all(images.map((image) => image.decode()));
    await nextFrame();
    await nextFrame();
    if (root === this._current?.layer) this._discoverStepTransitions(this._current);
    if (generation === this._renderGeneration) this.dataset.renderReady = '';
  }

  // --- keyboard -----------------------------------------------------------

  _handleKey(e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (!this._keyboardHints.hidden) {
      if (e.key === 'Shift') return;
      if (e.key === 'Tab') {
        const controls = [...this._keyboardHints.querySelectorAll(
          'summary, input:not(:disabled), button:not(:disabled), a[href]'
        )];
        const index = controls.indexOf(document.activeElement);
        const next = e.shiftKey
          ? (index > 0 ? index - 1 : controls.length - 1)
          : (index + 1) % controls.length;
        e.preventDefault();
        controls[next].focus();
        return;
      }
      if (
        (e.key === 'Enter' || e.key === ' ') &&
        e.target.closest('summary, input, button, a[href]')
      ) return;
      e.preventDefault();
      if (e.key === '?') this._showKeyboardHelp();
      else this._finishKeyboardHints(true);
      return;
    }
    if (!this._keyboardHelp.hidden) {
      e.preventDefault();
      this._hideKeyboardHelp();
      return;
    }
    if (e.key === '?') {
      e.preventDefault();
      this._showKeyboardHelp();
      return;
    }
    if (!this._catalogView.hidden) {
      this._handleOverviewKey(e);
      return;
    }
    if (!this._toc.hidden) {
      this._handleOverviewKey(e);
      return;
    }
    if (this._current?.keyHandler?.(e)) {
      e.preventDefault();
      return;
    }
    switch (e.key) {
      case 'ArrowRight':
        {
          const navigator = this._manifest.navigators.get(this._leaves[this._index].address);
          e.preventDefault();
          if (navigator && this._isNavigatorInterval(navigator)) {
            this._moveNavigatorSelection('right');
          } else {
            this._advance(1);
          }
        }
        break;
      case 'ArrowLeft':
        {
          const navigator = this._manifest.navigators.get(this._leaves[this._index].address);
          e.preventDefault();
          if (navigator && this._isNavigatorInterval(navigator)) {
            this._moveNavigatorSelection('left');
          } else {
            this._advance(-1);
          }
        }
        break;
      case ' ':
        e.preventDefault();
        this._advance(1);
        break;
      case 'ArrowDown':
        {
          const navigator = this._manifest.navigators.get(this._leaves[this._index].address);
          if (!navigator || !this._isNavigatorInterval(navigator)) break;
          e.preventDefault();
          this._moveNavigatorSelection('down');
        }
        break;
      case 'ArrowUp':
        e.preventDefault();
        {
          const navigator = this._manifest.navigators.get(this._leaves[this._index].address);
          if (navigator && this._isNavigatorInterval(navigator)) {
            this._moveNavigatorSelection('up');
          } else {
            this._goUp(this._leaves[this._index]);
          }
        }
        break;
      case 'Enter':
        {
          const navigator = this._manifest.navigators.get(this._leaves[this._index].address);
          if (!navigator || !this._isNavigatorInterval(navigator)) break;
          if (
            this._step === navigator.afterStep &&
            !this._current.navigatorControls?.after
          ) {
            e.preventDefault();
            break;
          }
          e.preventDefault();
          this._advance(1, false);
        }
        break;
      case 'PageDown':
        e.preventDefault();
        this._jumpSubtree(1);
        break;
      case 'PageUp':
        e.preventDefault();
        this._jumpSubtree(-1);
        break;
      case '[':
        e.preventDefault();
        this._changeNavigationDepth(-1);
        break;
      case ']':
        e.preventDefault();
        this._changeNavigationDepth(1);
        break;
      case 'Home':
        e.preventDefault();
        this._goToSlideEdge('start');
        break;
      case 'End':
        e.preventDefault();
        this._goToSlideEdge('end');
        break;
      case 'Escape':
        e.preventDefault();
        this._focusTocSelectionOnShow = true;
        this._navigateHash(this._hashForRoute(''));
        break;
    }
  }

  _handleOverviewKey(e) {
    if (e.key === 'Escape') {
      if (!this._toc.hidden) {
        e.preventDefault();
        this._navigateHash('#/');
        return;
      }
    }
    if (!this._toc.hidden && (e.key === 'g' || e.key === 'o')) {
      e.preventDefault();
      this._setTocMode(e.key === 'g' ? 'grid' : 'outline');
      this._syncTocSelection(true);
      return;
    }
    if (!this._toc.hidden && e.key === 's') {
      e.preventDefault();
      const control = this._toc.querySelector('.v-steps-expand');
      if (!control.disabled) {
        this._setStepsExpanded(
          control.getAttribute('aria-expanded') !== 'true'
        );
      }
      return;
    }
    if (
      !this._toc.hidden &&
      this._toc.dataset.mode === 'outline' &&
      this._handleOutlineOverviewKey(e)
    ) {
      return;
    }
    if (
      !this._toc.hidden &&
      this._toc.dataset.mode === 'grid' &&
      this._handleGridOverviewKey(e)
    ) {
      return;
    }
    const view = this._catalogView.hidden ? this._toc : this._catalogView;
    const items = [
      ...view.querySelectorAll(
        '.v-overview-body:not([hidden]) .v-overview-item'
      ),
    ].filter((item) => !item.closest('[hidden]'));
    if (items.length === 0) return;
    const current = items.findIndex((el) => el.classList.contains('focused'));
    const forward = e.key === 'ArrowDown' || e.key === 'ArrowRight';
    const backward = e.key === 'ArrowUp' || e.key === 'ArrowLeft';
    if (forward || backward || e.key === 'Home' || e.key === 'End') {
      e.preventDefault();
      let next = current;
      if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = items.length - 1;
      else next = clamp(current + (forward ? 1 : -1), 0, items.length - 1);
      this._focusOverviewItem(view, items[next], e.key);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = items[Math.max(0, current)];
      this._activateOverviewItem(item);
    }
  }

  _handleOutlineOverviewKey(e) {
    const navigationKeys = new Set([
      'ArrowUp',
      'ArrowDown',
      'ArrowLeft',
      'ArrowRight',
      'Home',
      'End',
    ]);
    if (!navigationKeys.has(e.key)) return false;

    const outline = this._toc.querySelector('.v-toc-outline:not([hidden])');
    if (!outline) return false;
    const slides = [...outline.querySelectorAll('.v-toc-item')];
    if (slides.length === 0) return false;

    e.preventDefault();
    const focused = outline.querySelector('.v-overview-item.focused');
    const focusedStep = focused?.classList.contains('v-outline-step')
      ? focused
      : null;
    const owner = focusedStep
      ? focusedStep.closest('.v-toc-item')
      : focused?.classList.contains('v-toc-item')
        ? focused
        : slides[0];
    const ownerIndex = Math.max(0, slides.indexOf(owner));
    let target = null;

    if (e.key === 'Home') target = slides[0];
    else if (e.key === 'End') target = slides[slides.length - 1];
    else if (e.key === 'ArrowUp') target = slides[Math.max(0, ownerIndex - 1)];
    else if (e.key === 'ArrowDown') {
      target = slides[Math.min(slides.length - 1, ownerIndex + 1)];
    } else if (e.key === 'ArrowRight') {
      target = focusedStep
        ? focusedStep.nextElementSibling
        : owner.querySelector(
            ':scope > .v-outline-steps:not([hidden]) > .v-outline-step'
          );
    } else if (focusedStep) {
      target = focusedStep.previousElementSibling || owner;
    }

    if (target?.classList.contains('v-overview-item')) {
      this._focusOverviewItem(this._toc, target, e.key);
    }
    return true;
  }

  _handleGridOverviewKey(e) {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return false;

    const grid = this._toc.querySelector('.v-toc-grid:not([hidden])');
    if (!grid) return false;
    const items = [...grid.querySelectorAll('.v-grid-item')].filter(
      (item) => !item.closest('[hidden]')
    );
    if (items.length === 0) return false;

    e.preventDefault();
    const current =
      items.find((item) => item.classList.contains('focused')) || items[0];
    const currentBox = current.getBoundingClientRect();
    const rowsInDirection = items
      .filter((item) => item !== current)
      .map((item) => ({ item, box: item.getBoundingClientRect() }))
      .filter(({ box }) =>
        e.key === 'ArrowDown'
          ? box.top > currentBox.top + 1
          : box.top < currentBox.top - 1
      );
    if (rowsInDirection.length === 0) return true;

    const adjacentRowTop =
      e.key === 'ArrowDown'
        ? Math.min(...rowsInDirection.map(({ box }) => box.top))
        : Math.max(...rowsInDirection.map(({ box }) => box.top));
    const currentCenter = (currentBox.left + currentBox.right) / 2;
    const target = rowsInDirection
      .filter(({ box }) => Math.abs(box.top - adjacentRowTop) < 1)
      .sort(
        ({ box: left }, { box: right }) =>
          Math.abs((left.left + left.right) / 2 - currentCenter) -
          Math.abs((right.left + right.right) / 2 - currentCenter)
      )[0].item;
    this._focusOverviewItem(this._toc, target, e.key);
    return true;
  }

  _focusOverviewItem(view, target, key) {
    for (const item of view.querySelectorAll('.v-overview-item.focused')) {
      item.classList.remove('focused');
    }
    target.classList.add('focused');
    target.focus({ preventScroll: true });
    const body = target.closest('.v-overview-body');
    if (key === 'Home') body?.scrollTo({ top: 0 });
    else if (key === 'End') body?.scrollTo({ top: body.scrollHeight });
    else target.scrollIntoView({ block: 'nearest' });
  }

  // --- table of contents --------------------------------------------------

  _showCatalog() {
    this._hideNavigationHud();
    this._stage.hidden = true;
    this._toc.hidden = true;
    this._catalogView.hidden = false;
    this._syncCatalogSelection(true);
  }

  _recordCatalogActivation(presentationId) {
    if (!presentationId || !this._hasPresentation(presentationId)) return;
    this._siteState.scope('~catalog').set('recentPresentationId', presentationId);
  }

  _syncCatalogSelection(focusSelection) {
    const items = [...this._catalogView.querySelectorAll('.v-catalog-item')];
    if (items.length === 0) return;
    const recentPresentationId = this._siteState
      .scope('~catalog')
      .get('recentPresentationId');
    const target =
      items.find((item) => item.dataset.presentationId === recentPresentationId) ||
      items[0];
    items.forEach((item) => item.classList.toggle('focused', item === target));
    target.scrollIntoView({ block: 'nearest' });
    if (focusSelection) target.focus({ preventScroll: true });
  }

  _activateOverviewItem(item) {
    const presentationId = item.dataset.presentationId;
    if (presentationId) {
      return this._navigateHash(`#/${presentationId}/`);
    }
    const address = item.dataset.address;
    if (!address) return Promise.resolve();
    const step = item.dataset.step === undefined ? 0 : Number(item.dataset.step);
    return this._navigateTo(address, step);
  }

  _createOverviewHeader(currentPage, controls = null) {
    const header = document.createElement('header');
    header.className = 'v-overview-header';

    const identity = document.createElement('div');
    identity.className = 'v-overview-identity';
    const identityImage = document.createElement('img');
    identityImage.className = 'v-overview-identity-image';
    identityImage.src = new URL('../assets/logo.svg', import.meta.url).href;
    identityImage.alt = 'Vividly';
    identity.append(identityImage);

    const breadcrumbs = document.createElement('nav');
    breadcrumbs.className = 'v-breadcrumbs';
    breadcrumbs.setAttribute('aria-label', 'Breadcrumb');
    const trail = document.createElement('ol');
    const catalogCrumb = document.createElement('li');
    if (currentPage === null) {
      const catalogTitle = document.createElement('h1');
      catalogTitle.textContent = 'Catalog';
      catalogTitle.setAttribute('aria-current', 'page');
      catalogCrumb.append(catalogTitle);
    } else {
      const catalogLink = document.createElement('a');
      catalogLink.href = '#/';
      catalogLink.textContent = 'Catalog';
      catalogLink.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') event.stopPropagation();
      });
      catalogLink.addEventListener('click', (event) => {
        event.preventDefault();
        this._navigateHash(catalogLink.getAttribute('href'));
      });
      catalogCrumb.append(catalogLink);
      const currentCrumb = document.createElement('li');
      const currentTitle = document.createElement('h1');
      currentTitle.textContent = currentPage;
      currentTitle.setAttribute('aria-current', 'page');
      currentCrumb.append(currentTitle);
      trail.append(catalogCrumb, currentCrumb);
    }
    if (currentPage === null) trail.append(catalogCrumb);
    breadcrumbs.append(trail);
    header.append(identity, breadcrumbs);
    if (controls) header.append(controls);
    return header;
  }

  _buildCatalog() {
    const header = this._createOverviewHeader(null);

    const list = document.createElement('ol');
    list.className = 'v-overview-body';
    for (const entry of this._catalog.presentations.values()) {
      const item = document.createElement('li');
      item.className = 'v-catalog-item v-overview-item';
      item.dataset.presentationId = entry.id;
      item.tabIndex = -1;
      const link = document.createElement('a');
      link.href = `#/${entry.id}/`;
      link.textContent = entry.title;
      link.addEventListener('click', (event) => {
        event.preventDefault();
        this._activateOverviewItem(item);
      });
      item.append(link);
      list.append(item);
    }
    this._catalogView.append(header, list);
    this._syncCatalogSelection(false);
  }

  _showToc({ focusSelection = false } = {}) {
    this._hideNavigationHud();
    this._navigationDepth = null;
    this._stage.hidden = true;
    this._catalogView.hidden = true;
    this._toc.hidden = false;
    this._refreshTocStatus();
    this._syncTocSelection(focusSelection);
  }

  _buildToc() {
    const actions = document.createElement('div');
    actions.className = 'v-overview-actions';
    const displayOptions = document.createElement('div');
    displayOptions.className = 'v-overview-options';
    const thumbnailToggle = document.createElement('button');
    thumbnailToggle.type = 'button';
    thumbnailToggle.className = 'v-thumbnail-toggle';
    thumbnailToggle.setAttribute('aria-label', 'Show thumbnails');
    thumbnailToggle.title = 'Show thumbnails';
    thumbnailToggle.innerHTML = `
      <svg class="v-overview-icon" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2"></rect>
        <circle cx="8.5" cy="9" r="1.5"></circle>
        <path d="m5 17 4.5-4.5 3 3 2-2 4.5 4.5"></path>
      </svg>
    `;
    thumbnailToggle.setAttribute(
      'aria-pressed',
      String(this._state.scope('~overview').get('showThumbnails', false))
    );
    thumbnailToggle.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') event.stopPropagation();
    });
    thumbnailToggle.addEventListener('click', () => {
      this._setTocThumbnails(
        thumbnailToggle.getAttribute('aria-pressed') !== 'true'
      );
    });
    const stepsExpansion = document.createElement('button');
    stepsExpansion.type = 'button';
    stepsExpansion.className = 'v-steps-expand';
    stepsExpansion.setAttribute('aria-label', 'Expand/collapse steps');
    stepsExpansion.title = 'Expand/collapse steps';
    stepsExpansion.innerHTML = `
      <svg class="v-overview-icon v-overview-icon-expand" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5"></path>
      </svg>
      <svg class="v-overview-icon v-overview-icon-collapse" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M9 9H4V4M15 9h5V4M9 15H4v5M15 15h5v5"></path>
      </svg>
    `;
    stepsExpansion.setAttribute(
      'aria-controls',
      `v-toc-outline-${this._presentationId} v-toc-grid-${this._presentationId}`
    );
    stepsExpansion.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') event.stopPropagation();
    });
    stepsExpansion.addEventListener('click', () => {
      this._setStepsExpanded(stepsExpansion.getAttribute('aria-expanded') !== 'true');
    });
    displayOptions.append(thumbnailToggle, stepsExpansion);
    actions.append(displayOptions, this._createOverviewModeSelector());
    const header = this._createOverviewHeader(this._manifest.title, actions);
    const outline = this._renderNodes(this._manifest.nodes, []);
    outline.classList.add('v-toc-outline', 'v-overview-body');
    outline.id = `v-toc-outline-${this._presentationId}`;
    const grid = document.createElement('div');
    grid.className = 'v-toc-grid v-overview-body';
    grid.id = `v-toc-grid-${this._presentationId}`;
    grid.hidden = true;
    this._toc.append(header, outline, grid);
    const first = this._toc.querySelector('.v-toc-item');
    if (first) first.classList.add('focused');
    const stepsExpanded = this._state.scope('~overview').get('stepsExpanded', false);
    this._setStepsExpanded(stepsExpanded, false);
    this._setTocThumbnails(
      thumbnailToggle.getAttribute('aria-pressed') === 'true',
      false
    );
    const savedMode = this._state.scope('~overview').get('tocMode', 'outline');
    this._setTocMode(savedMode === 'grid' ? 'grid' : 'outline', false);
  }

  _renderNodes(nodes, prefix) {
    const list = document.createElement('ol');
    for (const node of nodes) {
      const path = [...prefix, node.id];
      const li = document.createElement('li');
      if (node.type === 'section') {
        const label = document.createElement('span');
        label.className = 'v-toc-section';
        label.textContent = node.title || node.id;
        li.append(label, this._renderNodes(node.children, path));
      } else {
        const address = path.join('/');
        const title = node.title || node.id;
        li.className = 'v-toc-item v-overview-item';
        li.dataset.address = address;
        li.tabIndex = -1;
        const label = document.createElement('span');
        label.className = 'v-toc-label';
        label.textContent = title;
        li.append(label, this._createThumbnail(address, title));
        const steps = this._createOutlineSteps(address, title);
        if (steps) {
          li.dataset.indexedSteps = '';
          li.append(steps);
        }
        li.addEventListener('click', () => {
          this._activateOverviewItem(li);
        });
      }
      list.appendChild(li);
    }
    return list;
  }

  _refreshTocStatus() {
    for (const el of this._toc.querySelectorAll('.v-toc-item')) {
      const saved = this._state.scope(el.dataset.address);
      el.dataset.status = saved.get('visited') ? 'visited' : 'new';
    }
  }

  _syncTocSelection(focusSelection) {
    const items = [...this._toc.querySelectorAll('.v-toc-item')];
    if (items.length === 0) return;
    const currentAddress = this._current ? this._leaves[this._index]?.address : null;
    const currentStep = String(this._step);
    const target =
      items.find((item) => item.dataset.address === currentAddress) ||
      items.find((item) => item.classList.contains('focused')) ||
      items[0];
    const outlineSteps = [...this._toc.querySelectorAll('.v-outline-step')];
    const exactStep = outlineSteps.find(
      (item) =>
        item.dataset.address === currentAddress && item.dataset.step === currentStep
    );
    const stepIsVisible =
      this._toc.hasAttribute('data-thumbnails') &&
      exactStep &&
      !exactStep.closest('.v-outline-steps').hidden;
    const outlineTarget =
      this._toc.dataset.mode === 'outline' && stepIsVisible ? exactStep : target;
    for (const item of [...items, ...outlineSteps]) {
      item.classList.toggle('focused', item === outlineTarget);
    }
    items.forEach((item) => {
      item.toggleAttribute('data-current-slide', item.dataset.address === currentAddress);
    });
    for (const item of this._toc.querySelectorAll('.v-outline-step')) {
      const current =
        item.dataset.address === currentAddress && item.dataset.step === currentStep;
      item.toggleAttribute('data-current-step', current);
      if (current) item.setAttribute('aria-current', 'step');
      else item.removeAttribute('aria-current');
    }
    if (this._toc.dataset.mode === 'outline') {
      outlineTarget.scrollIntoView({ block: 'nearest' });
      if (focusSelection) outlineTarget.focus({ preventScroll: true });
    }
    this._syncGridSelection(focusSelection);
  }

  _setTocThumbnails(show, persist = true) {
    this._toc.toggleAttribute('data-thumbnails', show);
    this._toc
      .querySelector('.v-thumbnail-toggle')
      .setAttribute('aria-pressed', String(show));
    this._syncTocControls();
    this._syncTocSelection(false);
    if (persist) this._state.scope('~overview').set('showThumbnails', show);
  }

  _setStepsExpanded(expanded, persist = true) {
    if (
      persist &&
      this._toc.dataset.mode === 'outline' &&
      !this._toc.hasAttribute('data-thumbnails')
    ) {
      this._setTocThumbnails(true);
      expanded = true;
    }
    const activeStep =
      document.activeElement instanceof HTMLElement
        ? document.activeElement.closest('.v-toc-grid .v-grid-item[data-step]')
        : null;
    const focusAddress = !expanded ? activeStep?.dataset.address : null;
    const activeOutlineStep =
      document.activeElement instanceof HTMLElement
        ? document.activeElement.closest('.v-outline-step')
        : null;
    const outlineFocusOwner = !expanded
      ? activeOutlineStep?.closest('.v-toc-item')
      : null;
    const control = this._toc.querySelector('.v-steps-expand');
    control.setAttribute('aria-expanded', String(expanded));
    this._toc.toggleAttribute('data-steps-expanded', expanded);
    for (const steps of this._toc.querySelectorAll('.v-outline-steps')) {
      steps.hidden = !expanded;
    }
    const grid = this._toc.querySelector('.v-toc-grid');
    if (grid.childElementCount > 0) this._renderTocGrid();
    if (focusAddress) {
      const replacement = [...grid.querySelectorAll('.v-grid-item')].find(
        (item) => item.dataset.address === focusAddress && item.dataset.step === undefined
      );
      if (replacement) {
        for (const item of grid.querySelectorAll('.v-grid-item.focused')) {
          item.classList.remove('focused');
        }
        replacement.classList.add('focused');
        replacement.focus({ preventScroll: true });
      }
    }
    this._syncTocSelection(false);
    if (outlineFocusOwner && this._toc.dataset.mode === 'outline') {
      this._focusOverviewItem(this._toc, outlineFocusOwner, '');
    }
    if (persist) this._state.scope('~overview').set('stepsExpanded', expanded);
  }

  _syncTocControls() {
    const outlineMode = this._toc.dataset.mode === 'outline';
    const thumbnailToggle = this._toc.querySelector('.v-thumbnail-toggle');
    thumbnailToggle.hidden = !outlineMode;
  }

  _setTocMode(mode, persist = true) {
    this._toc.dataset.mode = mode;
    for (const button of this._toc.querySelectorAll('[data-overview-mode]')) {
      button.setAttribute('aria-pressed', String(button.dataset.overviewMode === mode));
    }
    const outline = this._toc.querySelector('.v-toc-outline');
    const grid = this._toc.querySelector('.v-toc-grid');
    outline.hidden = mode !== 'outline';
    grid.hidden = mode !== 'grid';
    if (mode === 'grid' && grid.childElementCount === 0) this._renderTocGrid();
    this._syncTocControls();
    this._syncTocSelection(false);
    if (persist) this._state.scope('~overview').set('tocMode', mode);
  }

  _renderTocGrid() {
    const grid = this._toc.querySelector('.v-toc-grid');
    if (!grid) return;
    grid.replaceChildren();
    const expanded =
      this._toc.querySelector('.v-steps-expand').getAttribute('aria-expanded') === 'true';
    grid.toggleAttribute('data-expanded', expanded);
    for (const [sequenceIndex, leaf] of this._leaves.entries()) {
      const title = leaf.node.title || leaf.node.id;
      const thumbnails = expanded ? this.thumbnailsFor(leaf.address) : [];
      const items =
        thumbnails.length > 0
          ? thumbnails.map((thumbnail) =>
              this._createGridItem(
                leaf,
                title,
                thumbnail.capturedStep,
                thumbnails.length
              )
            )
          : [this._createGridItem(leaf, title)];
      if (expanded) {
        items.forEach((item, itemIndex) => {
          item.dataset.sequenceTone = String(sequenceIndex % 2);
          item.toggleAttribute('data-sequence-start', itemIndex === 0);
          item.toggleAttribute('data-sequence-end', itemIndex === items.length - 1);
        });
      }
      grid.append(...items);
    }
    this._syncGridSelection(false);
  }

  _createOutlineSteps(address, title) {
    const thumbnails = this.thumbnailsFor(address);
    if (thumbnails.length === 0) return null;
    const steps = document.createElement('div');
    steps.className = 'v-outline-steps';
    steps.setAttribute('role', 'group');
    steps.setAttribute('aria-label', `${title} steps`);
    for (const thumbnail of thumbnails) {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'v-outline-step v-overview-item';
      item.dataset.address = address;
      item.dataset.step = String(thumbnail.capturedStep);
      item.tabIndex = -1;
      item.append(
        this._createThumbnail(address, title, thumbnail.capturedStep),
        this._createStepLabel(thumbnail.capturedStep, thumbnails.length)
      );
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        this._activateOverviewItem(item);
      });
      steps.append(item);
    }
    return steps;
  }

  _createStepLabel(step, totalSteps) {
    const label = document.createElement('span');
    label.className = 'v-outline-step-label';
    label.textContent = `Step ${step + 1} of ${totalSteps}`;
    return label;
  }

  _createGridItem(leaf, title, step = null, totalSteps = null) {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'v-grid-item v-overview-item';
    item.dataset.address = leaf.address;
    if (step !== null) item.dataset.step = String(step);
    item.tabIndex = -1;
    item.append(this._createThumbnail(leaf.address, title, step));
    const label = document.createElement('span');
    label.className = 'v-grid-label';
    const slideTitle = document.createElement('span');
    slideTitle.className = 'v-grid-title';
    slideTitle.textContent = title;
    label.append(slideTitle);
    if (step !== null && totalSteps !== null) {
      const stepLabel = document.createElement('span');
      stepLabel.className = 'v-grid-step';
      stepLabel.textContent = `Step ${step + 1} of ${totalSteps}`;
      label.append(stepLabel);
    }
    item.append(label);
    item.addEventListener('click', () => {
      this._activateOverviewItem(item);
    });
    return item;
  }

  _createOverviewModeSelector() {
    const modes = document.createElement('div');
    modes.className = 'v-overview-modes';
    modes.setAttribute('role', 'group');
    modes.setAttribute('aria-label', 'Overview mode');
    for (const [mode, label] of [
      ['outline', 'Outline'],
      ['grid', 'Grid'],
    ]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.overviewMode = mode;
      button.textContent = label;
      button.setAttribute('aria-pressed', String(mode === 'outline'));
      button.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') event.stopPropagation();
      });
      button.addEventListener('click', () => {
        this._setTocMode(mode);
      });
      modes.append(button);
    }
    return modes;
  }

  _syncGridSelection(focusSelection) {
    const items = [...this._toc.querySelectorAll('.v-toc-grid .v-grid-item')];
    if (items.length === 0) return;
    const currentAddress = this._current ? this._leaves[this._index]?.address : null;
    const currentStep = String(this._step);
    const exact = items.find(
      (item) =>
        item.dataset.address === currentAddress && item.dataset.step === currentStep
    );
    const target =
      exact ||
      items.find((item) => item.dataset.address === currentAddress) ||
      items.find((item) => item.classList.contains('focused')) ||
      items[0];
    items.forEach((item) => item.classList.toggle('focused', item === target));
    let markedCurrentSlide = false;
    for (const item of items) {
      const currentSlide = item.dataset.address === currentAddress;
      const currentSlideMarker = currentSlide && !markedCurrentSlide;
      item.toggleAttribute('data-current-slide', currentSlideMarker);
      if (currentSlideMarker) markedCurrentSlide = true;
      const currentStepItem =
        currentSlide &&
        item.dataset.step !== undefined &&
        item.dataset.step === currentStep;
      item.toggleAttribute('data-current-step', currentStepItem);
      if (currentStepItem) item.setAttribute('aria-current', 'step');
      else if (currentSlide && item.dataset.step === undefined) {
        item.setAttribute('aria-current', 'true');
      } else {
        item.removeAttribute('aria-current');
      }
    }
    if (this._toc.dataset.mode === 'grid') {
      target.scrollIntoView({ block: 'nearest' });
      if (focusSelection) target.focus({ preventScroll: true });
    }
  }

  _createThumbnail(address, title, step = null) {
    const frame = document.createElement('vividly-thumbnail');
    frame.className = 'v-thumbnail';
    frame.address = address;
    if (step !== null) frame.step = step;
    frame.fallback = title;
    return frame;
  }

  async _loadThumbnailIndex() {
    try {
      const response = await fetch(
        new URL(`${this._thumbnailRoot()}index.json`, document.baseURI),
        { cache: 'no-cache' }
      );
      if (!response.ok) return {};
      const index = await response.json();
      if (
        index?.version !== 3 ||
        !index.presentations ||
        typeof index.presentations !== 'object'
      ) {
        return {};
      }
      const entries = index.presentations[this._presentationId];
      if (!entries || typeof entries !== 'object') return {};
      return normalizeThumbnailEntries(this._presentationId, entries);
    } catch {
      return {};
    }
  }

  _thumbnailRoot() {
    return './thumbnails/';
  }
}

function normalizeThumbnailEntries(presentationId, entries) {
  return Object.freeze(
    Object.fromEntries(
      Object.entries(entries).flatMap(([address, entry]) => {
        const normalized = normalizeThumbnailEntry(presentationId, address, entry);
        return normalized ? [[address, normalized]] : [];
      })
    )
  );
}

function normalizeThumbnailEntry(presentationId, address, entry) {
  if (
    !entry ||
    Array.isArray(entry) ||
    !Number.isInteger(entry.canonicalStep) ||
    entry.canonicalStep < 0 ||
    !Array.isArray(entry.steps) ||
    entry.steps.length === 0 ||
    entry.canonicalStep >= entry.steps.length
  ) {
    return null;
  }
  const steps = entry.steps.map((step, index) => {
    const expectedPath =
      `${presentationId}/${address}/step-${String(index).padStart(4, '0')}.png`;
    if (
      !step ||
      Array.isArray(step) ||
      step.step !== index ||
      step.path !== expectedPath ||
      typeof step.revision !== 'string' ||
      !THUMBNAIL_REVISION_PATTERN.test(step.revision)
    ) {
      return null;
    }
    return Object.freeze({
      step: index,
      path: step.path,
      revision: step.revision,
    });
  });
  if (steps.some((step) => step === null)) return null;
  return Object.freeze({
    canonicalStep: entry.canonicalStep,
    steps: Object.freeze(steps),
  });
}

function stepCount(rec) {
  return rec.steps === DYNAMIC ? 1 : rec.steps;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nextFrame() {
  return Promise.race([
    new Promise((resolve) => requestAnimationFrame(resolve)),
    delay(RENDER_FRAME_TIMEOUT_MS),
  ]);
}

function clamp(n, lo, hi) {
  return Math.min(hi, Math.max(lo, n));
}

customElements.define('vividly-presentation', VividlyPresentation);
