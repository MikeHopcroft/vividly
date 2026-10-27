# Presentation Orchestration Spec

Status: implemented, except for the open questions and unimplemented items in §10.
Covers the slide module contract and the orchestrator that drives it. Thumbnail
generation is covered where it meets the runtime contract; general bundling,
narration, and deployment are out of scope.

Presentation threads, chronological browser history, and navigator-owned structural
traversal are specified in
[`docs/specs/presentation-threads.md`](presentation-threads.md). That contract governs
where this document's general routing rules meet those features.

Touch gestures, interaction-owned regions, and visible touch navigation controls
are specified in [Touch Navigation](touch-navigation.md). That accepted contract
is implementation-pending and reuses this document's navigation and settling rules.

## 1. Principles

Carried over from llm-explainer, and the reason this document exists before any code:

- **No third-party framework.** No React, Vue, or Angular. Vividly uses vanilla JS,
  custom elements, and runtime- or catalog-selected browser dependencies.
- **No required build step.** Vividly composes the author-owned `site/` tree with the
  selected runtime without compiling either source. ES modules are loaded natively by
  the browser. Optional authoring commands may refresh committed static assets such as
  thumbnails; export materializes the same composition as a static site.
- **CSS does the heavy lifting.** JS computes *state*; CSS renders it. A slide's
  animation steps are a CSS problem, not a JS problem (see §4.4).
- **Slides are independently authorable.** A slide is a directory an agent can write
  in isolation, with no edits to any shared file other than the manifest.

## 2. Module system

### 2.1 JavaScript

Slides are **ES modules loaded via dynamic `import()`**. This is the load-bearing
decision:

- Namespacing is free — no globals, no IIFE wrapper, no name collisions between
  independently authored slides.
- `preload()` maps directly onto `import()`; the browser caches and dedupes.
- `import.meta.url` gives every slide a stable base for its own assets, with no
  bundler and no manifest-relative path juggling.

The shell creates the dependency registry specified by
[`dependency-resolution.md`](dependency-resolution.md). Runtime and slide consumers use
one promise-memoized result per logical key. Runtime-owned classic scripts may define a
global as part of their loading model, but consumers receive the value through the
registry and do not read ambient globals.

**Runtime imports.** The runtime's `index.html` declares one import map entry,
`"vividly/": "./vividly/"`, resolved against the page URL. Slides import runtime
modules as `vividly/runtime/slide.js`, so the import is independent of the slide's
directory depth and of the subpath the site is published under. A relative path
(`../../vividly/...`) depends on depth; a root-relative path (`/vividly/...`) breaks
under a subpath such as a GitHub Pages project site. The `vividly/` prefix is
runtime-owned and is the only import map entry; author or package import map entries
remain outside scope ([`dependency-resolution.md`](dependency-resolution.md) §11).
Runtime modules themselves continue to import one another relatively.

### 2.2 Assets and the data root

Every slide instance has a **data root**: the base URL that `ctx.load()` and
`ctx.asset()` resolve against. It defaults to the module's own directory, and a
manifest node may point it elsewhere with `data:` (§3).

```js
const data = await this.ctx.load('./data/stages.yaml');   // data root
const img = new URL('./assets/diagram.png', import.meta.url);   // module's own file
```

The split is what makes a module reusable. Files belonging to the *instance* — the
content this particular slide shows — move with the data root. Files belonging to the
*module* — a source helper, an icon that is part of the code — resolve against
`import.meta.url`, which is plain ESM and needs no runtime API.

A module that never reaches outside its own directory is a slide. A module that takes
its content from the data root is a slide *type*, and the same code can back any
number of manifest nodes. Nothing in the runtime distinguishes the two cases: `module:`
names code, `data:` names a directory, and whether a module is referenced once or ten
times is an authoring decision. Segregating shared modules from instance data by
folder is a useful convention and is not enforced.

`data:` is normalized to a trailing slash before use as a `URL` base. Without it,
`new URL('./photos.yaml', '.../photo-tour')` resolves into the *parent* directory — a
silent and confusing failure.

`ctx.load()` dispatches on extension: `.yaml`/`.yml` → the runtime-selected `js-yaml`
instance, `.md` → text, `.json` → parsed, anything else → text.

**Props are configuration, not content.** A heading, a flag, a theme token, a list of
paths belong in `props`; prose, markdown and code listings belong in files under the
data root. The workable line is that anything containing a newline is a file. The
manifest is the one shared file every slide author edits, so keeping payloads out of
it preserves the independent-authorability property that §1 exists to protect — and
content in files is diffable, reviewable and editable in a tool that understands it.

### 2.3 CSS

Slide styles are **light DOM, scoped by the orchestrator using native `@scope`**.

Shadow DOM is rejected: it breaks the shared markdown/highlight styles, complicates
orchestrator-level transitions, and buys isolation we can get more cheaply.

The orchestrator fetches each stylesheet listed in `meta.styles`, parses it into a
temporary constructed stylesheet, serializes the recovered CSSOM rules, wraps those
rules, and adopts the scoped result when the module is first preloaded:

```js
const source = new CSSStyleSheet();
source.replaceSync(cssText);
const normalized = [...source.cssRules].map((rule) => rule.cssText).join("\n");
const scoped = new CSSStyleSheet();
scoped.replaceSync(`@scope ([data-vividly-module="${moduleId}"]) {\n${normalized}\n}`);
document.adoptedStyleSheets.push(scoped);
```

Authors write ordinary selectors (`.stage-label { ... }`) and get isolation with zero
discipline. Theme custom properties inherit through the scope boundary normally, which
is exactly what we want and what Shadow DOM would have obstructed.

Parsing before wrapping is part of the isolation boundary. Browser error recovery may
discard malformed tokens such as an unmatched closing brace, but serialized CSSOM rules
are balanced and cannot terminate the runtime-owned `@scope` wrapper.

**Scoping is one-way.** `@scope` limits where a slide's rules apply; it does not
isolate the slide from the document. Global stylesheets — theme tokens, typography
defaults, the standard controls — cascade into the slide root normally, because the
slide lives in the light DOM. This is the point: a slide inherits presentation-wide
look and feel by default and overrides only what it names. It is also what makes a
single theme swap restyle every slide at once.

Conflicts resolve in the slide author's favour without specificity wars. All global
stylesheets are wrapped in cascade layers, declared in order by the shell:

```css
@layer vividly.base,      /* resets, typography, step primitives */
       vividly.controls,  /* the standard control library (§4.7) */
       vividly.theme;     /* tokens only */
```

Slide stylesheets are left unlayered, and unlayered author styles beat layered ones
regardless of specificity. A slide can therefore override any control or theme rule
with a plain class selector and never needs `!important` or escalating selectors.

Slides cannot contribute global CSS. Styling that must apply across slides belongs in
the theme or the control library — that separation is what keeps a slide directory
independently authorable.

`moduleId` is derived from the module's directory name plus a hash of its URL, so the
same module used twice in a presentation shares one stylesheet.

**Relative `url()` is rewritten, not delegated.** Constructed stylesheets resolve
`url()` against the document, not the source file, so a slide's
`background-image: url('./assets/hero.svg')` would silently break. The runtime
absolutizes every relative `url()` against the stylesheet's own href before adopting
it. This is deterministic and avoids depending on `new CSSStyleSheet({ baseURL })`,
whose support is uneven. Verified working in the prototype.

**Slide CSS cannot reach the runtime's own boxes.** Unlayered slide rules beat
everything, which means a slide setting `display: grid` on its root would otherwise
defeat the runtime's `[hidden]` rule and leave dead slides on screen. The runtime
therefore owns a wrapper element outside the `@scope` root (§5.5), which slide CSS
provably cannot select.

### 2.4 Directory layout

```
vividly.yaml              # committed runtime selection and exact identity
site/                     # wholly author-owned source
  catalog.yaml            # registry of root presentations
  presentations/
    product-tour.yaml     # conventional location; catalog paths are authoritative
    architecture.yaml
  thumbnails/             # generated, committed overview images and index
  slides/
    token-anatomy/        # one-off slide: code and data together
      slide.js            # default export
      slide.css
      data/stages.yaml
      assets/diagram.png
      lib/chart.js        # slide-local source helper
    photo-tour/           # instance data only; module supplied by the manifest
      photos.yaml
      assets/hero.jpg
```

`site/catalog.yaml` is the one known author-owned entry point. The catalog, manifests,
slides, assets, and thumbnails are author content. `site/index.html` and
`site/vividly/` are invalid because the selected runtime owns deployed `/index.html`
and `/vividly/**`. The composition rules are specified in
[`runtime-composition.md`](runtime-composition.md).

`site/presentations/<presentation-id>.yaml` and `site/slides/<slide-id>/` are starter
conventions, not runtime inferences. Catalog and manifest references are authoritative.

Paths declared by a manifest resolve relative to that manifest, so moving a manifest
requires updating its relative references but sharing a slide requires no special
runtime mechanism. Presentation-specific slides may be grouped under
`site/slides/<presentation-id>/`; the directory name conveys no ownership semantics.

### 2.5 Project catalog

The versioned catalog registers every author-owned root presentation:

```yaml
version: 1
presentations:
  - id: product-tour
    title: Product Tour
    manifest: ./presentations/product-tour.yaml
  - id: architecture
    title: System Architecture
    manifest: ./presentations/architecture.yaml
```

Catalog order is display order. `id` is a stable presentation identity and URL segment;
an author ID consists of lowercase ASCII letters and digits separated by single hyphens,
with no leading or trailing hyphen. IDs are unique. The entire `~` namespace is
reserved for runtime views and possible future system identities; author catalogs
cannot use it. `title` is the label available without fetching the manifest.

`manifest` resolves as a URL relative to `site/catalog.yaml`. After URL normalization,
its URL must have the same origin as the catalog and its pathname must remain below the
catalog's `site/` directory. Absolute URLs, protocol-relative URLs, remote origins, and
paths whose normalized result escapes `site/` are invalid. Validation happens before
the manifest is fetched.

Vividly does not scan for manifests. A manifest omitted from the catalog may be
incorporated into a root presentation (§6), but it cannot itself be routed, opened as a
thread root, or processed independently by project-wide operations. Every independently
runnable presentation therefore has a catalog ID. The initial runtime defines no
framework-owned root presentation; the reserved `~` namespace remains available for
runtime views and future system identities.

### 2.6 Browser dependencies

Project-wide browser dependencies are selected in `site/catalog.yaml` and loaded
through `ctx.dependency(key)`. Runtime-owned keys are available through the same API,
and catalog keys cannot replace them. The handle's `load()` operation supports every
loader type; retained `import()` supports module records only. Complete resolution,
loader, collision, caching, and browser-realm rules are specified in
[`dependency-resolution.md`](dependency-resolution.md).

A slide-local source helper may still use an ordinary relative ESM import. A genuinely
slide-local classic script may use `ctx.loadScript(path, { global })`, which dedupes by
resolved URL. Those files are neither project-registry dependencies nor cache
selections. They run with full page privileges and must not masquerade as
runtime-owned dependencies.

All dependencies and slide code share one browser realm. Physical copies or distinct
logical keys do not by themselves establish runtime compatibility. Slides must not
import `/vividly/vendor/**`, read runtime dependency globals, or embed the selected CDN
URL.

## 3. Manifest

The presentation tree. Interior nodes are sections, leaves are slides or nested
presentations. Discriminated by `type`, following llm-explainer's convention.

```yaml
title: How Tokenizers Work
theme: ./themes/dark.css
transition: dissolve            # default for every slide
nodes:
  - type: section
    id: intro
    title: Introduction
    children:
      - type: slide
        id: title-card
        module: ../slides/title-card/slide.js
        props: { subtitle: A visual tour }
      - type: slide
        id: token-anatomy
        module: ../slides/token-anatomy/slide.js
        transition: fly-left    # per-slide override
        thumbnail:
          step: 2               # zero-based; default is the final fixed step
      - type: slide
        id: photo-tour
        module: ../slides/shared/gallery/slide.js   # module shared with other nodes
        data: ../slides/photo-tour/                 # this instance's data root
  - type: presentation
    id: appendix
    manifest: ./appendix/presentation.yaml
```

`id` must be unique among siblings. The path of ids from the root forms a slide's
**address** (§5.1). `props` is opaque manifest data handed to the slide, and `data:`
sets its data root (§2.2); together they let one module be instantiated several times
with different content.

`theme` applies only when this manifest is the root (§6.1). `transition` is the
default for boundaries whose later slide does not declare one. A slide's transition
belongs to the boundary immediately before it (§5.4).

`keyboardHints` controls the runtime-owned keyboard activation screen. `auto` is the
default and shows the screen before the first normal presentation entry until the
reader suppresses it for the provisioned site. `always` shows it at the start of each
newly activated presentation runtime, and `never` disables automatic display. Deep
links to slides other than the first slide at step zero do not display onboarding. The
runtime may preload and mount the requested first slide behind the activation screen,
but it does not call `enter()` until the reader dismisses onboarding. The first
unmodified key dismisses the activation screen and is consumed; navigation begins with
the next key. Tab instead cycles focus within the activation screen, skipping
disabled controls; Enter and Space retain native activation on its controls.
As an exception, `?` dismisses onboarding and opens full keyboard help.
Dismissal fades the activation screen for 300 milliseconds before the
runtime calls the first slide's `enter()` method. The screen is not a slide or history
entry. The full keyboard-help dialog remains available with `?` after activation under
every policy.

The activation screen keeps keycap visuals and groups slide controls separately from
browsing controls. It explains moving the highlight with arrow keys and opening the
highlighted item with Enter, offers a Start presentation button and an any-key prompt,
and conditionally describes the progress indicator: "If you see a yellow bar, it
shows progress toward being ready to continue."
Below that sentence, a small, partially filled example uses the readiness indicator's
track and yellow fill styling. The example is static and decorative, not a live
progress indicator, and is hidden from assistive technology.

Keyboard instructions, including the Esc and ? shortcuts, are grouped in a native
**Keyboard shortcuts** disclosure. When onboarding is shown, the disclosure defaults
to collapsed at viewport widths of 40rem (640 CSS pixels) or less, and expanded
otherwise. This is a layout choice, not keyboard detection: touch instructions remain
visible on touch-capable devices, and all navigation methods remain enabled. The
reader can toggle the disclosure with a click, tap, Enter, or Space without dismissing
onboarding. Its state is retained while the screen is open, including across resizes.
Full keyboard help continues to expose both input methods on touch-capable devices.

A completed click or tap anywhere on the activation screen also starts the
presentation, including its backdrop and instructional content. The preference
checkbox and its label only change the preference; the disclosure summary only
toggles the keyboard instructions. Neither dismisses the screen.
Scrolling and swiping do not dismiss it. The dismissal event is consumed, and the
screen continues intercepting pointer input during its 300-millisecond fade so the
gesture cannot activate underlying controls or advance the first slide. The screen
prompts "Tap anywhere to start." on touch-capable devices and "Click anywhere or
press a key to start." otherwise. The Start presentation button and keyboard
dismissal remain available.

### 3.1 Thumbnail capture

A thumbnail belongs to a manifest slide node, not to its module. The node is the slide
*instance*: a shared module may appear several times with different `data` and `props`,
and therefore with different rendered content. Keeping thumbnail configuration in the
manifest also lets overview views remain manifest-only; they never import every slide
module merely to discover image metadata.

Vividly generates a thumbnail sequence for each slide and designates one member as its
canonical thumbnail. For a fixed-length slide, generation captures every step from `0`
through `steps - 1`. Its final step is canonical by default. `thumbnail.step` overrides
the canonical selection with a zero-based non-negative integer, matching the route and
`setStep()` model. A value outside the slide's actual range is a generation error.

A dynamic slide has no enumerable step axis. Generation captures only its initial state
as step `0`, which is canonical, and the slide may not declare `thumbnail.step`.
Dynamic-slide checkpoints require a separate author-facing contract and are deferred.

Generated image locations are derived from the slide's complete address and recorded in
the author-owned thumbnail ledger (§9). Each path ends in the fixed-width zero-based
name `step-0000.png`, with the number replaced by the captured step. The index, not this
naming convention, is authoritative. Locations and content revisions are not written
back into presentation manifests. Renaming a slide changes its address and therefore
every thumbnail identity in its sequence, just as it changes deep links and persisted
slide state.

## 4. Slide contract

### 4.1 Shape

```js
import { Slide } from 'vividly/runtime/slide.js';

export const meta = {
  styles: ['./slide.css'],
};

export default class TokenAnatomy extends Slide {
  async preload() {
    this.stages = (await this.ctx.load('./data/stages.yaml')).stages;
    return { steps: this.stages.length };
  }

  mount(root) {
    root.innerHTML = this.stages.map(renderStage).join('');
  }
}
```

`Slide` supplies no-op defaults for every method, so a slide implements only what it
needs. A static slide implements `mount()` and nothing else.

`meta` is optional, and describes only what the module itself owns. It carries no title.
A title names one slide *instance*, so like a thumbnail (§3.1) it belongs to the manifest
node. Overview views depend on this: they read titles straight from the manifest without
loading a single slide module.

### 4.2 Lifecycle

| Method | When | Notes |
|---|---|---|
| `constructor(ctx)` | on `import()` | No I/O, no DOM. |
| `async preload()` | before it can be shown | Fetch data. Returns `{ steps }`. No DOM. |
| `mount(root)` | when it enters the preload window | Root is **hidden**. Must not assume visibility or size. |
| `enter({ direction, step, restoring })` | becoming visible | Before the transition runs; `restoring` identifies history or thread restoration. |
| `setStep(n)` | every step change, including on enter | Must be idempotent and order-independent. |
| `settleStep()` | before repeated same-direction incremental navigation | Complete custom motion synchronously. Return `true` only when motion was completed. |
| `exit({ direction })` | leaving | Before the outbound transition. |
| `unmount()` | leaving the preload window | Release DOM-bound resources. |
| `dispose()` | presentation teardown | Release everything else. |

The split between `mount` and `enter` is what makes preloading and cross-fade
transitions possible: both the outgoing and incoming slide are mounted and laid out
simultaneously.

Selecting the already-current slide from the table of contents performs an
`exit()`/`enter()` cycle. The slide remains mounted, but receives a fresh visible entry
so entry animations and other transient presentation state can restart.

### 4.3 Step model

Every slide declares its step count from `preload()`. The runtime owns the step index
and drives the slide with `setStep(n)`, `0 <= n < steps`. A slide's steps are the
innermost level of the presentation hierarchy, so "step 2 of 4" reads the same way as
"slide 6 of 9 in this section" (§5.7).

`setStep` is **absolute and idempotent**, never relative. This is the property that
makes richly interactive slides work. Consider a data explorer with six guided points
that also allows free exploration: the guided points are a static step count, while
the exploration is state that simply is not on the step axis. `setStep(3)`
re-establishes guided point 3 no matter how far the reader wandered. "Advance by one"
from an explored state has no defined answer; "go to point 3" always does.

Because the runtime knows each slide's length, deep links, status (§5.7), table-of-
contents jumps, and reload-restore all fall out of the one mechanism.

**Escape hatch.** A slide whose length is genuinely unknowable returns
`{ steps: 'dynamic' }` and is driven by `advance(delta) -> boolean`, where `false`
means "I am at my end, move on". It reports length changes with
`vividly:steps-changed`, and must write its own status (§5.7), since the runtime
cannot derive completion from a step count it does not know.

`dynamic` is rarer than it first appears. A complex internal navigation model is not a
reason to use it — a slide with rich interaction usually still has a static number of
authored points. Reserve it for streaming or user-generated content, where the count
genuinely does not exist until runtime.

#### Step animation settling

An **incremental navigation action** asks for the next or previous presentation state
relative to the current one. Ordinary Right, Left, and forward Space traversal are
incremental, as are navigator selection movement, navigator itinerary traversal,
crossing an ordinary slide boundary, and a dynamic slide's `advance(delta)`. Home,
End, PageUp, PageDown, direct routes, `ctx.navigate()`, browser-history restoration,
initial entry, thread rehydration, and thumbnail capture are **destination actions**,
not incremental actions.

An incremental action that changes a fixed step, successfully advances a dynamic
slide, or crosses a slide boundary associates any resulting step motion with its
navigation direction:

```text
+1  forward incremental navigation
-1  backward incremental navigation
```

The direction describes movement through presentation state, not the physical key.
For navigator arrows the runtime resolves the spatial target first, then derives the
direction from the target step relative to the current step (§5.2). Space follows the
forward structural itinerary and therefore has direction `+1`.

When applying the resulting step or dynamic state, the runtime snapshots the slide
root's descendant animations before publishing the state, then discovers newly created
finite `CSSTransition` instances after styles resolve. Those transitions are
**step-owned motion** associated with that incremental direction. Pre-existing
animations and CSS keyframe animations are not tracked automatically: either may be
decorative, ambient, or intended to span multiple steps. Canceled, replaced, and
naturally completed transitions cease to be unsettled. Applying another step, exiting,
or unmounting clears stale tracked motion.

When tracked transitions begin, the runtime records their step motion's start time.
Before another incremental action in the same direction changes state, it compares the
time when that action was received with the recorded start time. The runtime then:

1. finishes all unfinished tracked transitions
2. calls the slide's `settleStep()`
3. consumes the action if it was received more than 500 milliseconds after the tracked
   motion began or `settleStep()` returned `true`
4. otherwise continues the requested navigation within the same queued action

The 500 millisecond **rapid-input grace** is an internal runtime policy, not manifest,
theme, or per-slide configuration. Its boundary is inclusive: an action received at
most 500 milliseconds after tracked motion began finishes that motion and continues.
The action's receipt time controls the decision even if queued rendering work delays
its execution. Transition duration, remaining time, playback rate, and pause state do
not change this classification.

A consumed action does not call `setStep()` or `advance()`, change the address or
current step, write persisted step state, move navigator focus, or emit navigation,
step, or lifecycle events. When the action continues within the completion grace,
finishing the current transitions does not itself emit structural events; the
requested navigation performs its normal state, route, focus, and event updates. This
applies symmetrically at either end of a slide: forward motion at the last step settles
before leaving forward, and backward motion at step zero settles before leaving
backward.

An opposite-direction incremental action acts immediately. It applies the requested
absolute step or dynamic action, replacing the abandoned tracked motion rather than
first forcing that motion to its old target. This lets Left reverse an in-progress
forward build and Right reverse an in-progress backward build without an extra press.
The slide's `setStep()` or `advance()` implementation is responsible for replacing its
own stale custom motion when the direction reverses.

A destination action also acts immediately, clears the incremental direction
association, and replaces stale tracked motion. CSS transitions produced by a
destination action are not tracked for automatic settling. The destination's custom
build is eligible for forward settling: the next Right or Space calls `settleStep()`
and stays at the destination if the hook returns `true`. This includes initial entry,
direct links, navigator activation by Enter or click, Home/End, history restoration,
and navigation APIs. Backward input after destination arrival acts immediately.
If the custom build has already finished, the hook returns `false` and forward
navigation proceeds normally. Destination activation itself never settles the
outgoing build or requires an extra input.

`settleStep()` is the extension point for motion the runtime cannot identify, including
timers, canvas drawing, CSS keyframes, and third-party animation libraries. It is
synchronous: when it returns `true`, the slide must already render the settled form of
the current absolute step or dynamic state. It returns `false` when it changed nothing,
and must never change the step or navigate. The base `Slide` implementation returns
`false`. A `true` result always consumes same-direction incremental navigation; the
completion grace applies only to automatically tracked CSS transitions because the
boolean hook cannot express "completed custom motion but continue." This hook does not
weaken the absolute `setStep()` contract.

### 4.4 Steps in CSS

Before calling `setStep(n)`, the runtime publishes the step four ways: `data-step` and
`data-steps` attributes on the slide root, and `--step` / `--steps` custom properties
on the layer above it. The attributes are for selectors; the custom properties are for
arithmetic. A slide whose steps are purely visual therefore needs **no JS for stepping
at all**:

```css
:scope[data-step='0'] .stage-2 { opacity: 0; }
```

The numeric form is what makes step-driven CSS scale past hand-written per-step rules.
The `vividly.base` layer provides two primitives built on it — they are step
arithmetic rather than controls, which is why they sit in `base`:

```css
/* .v-reveal — visible once the deck reaches --at, and thereafter. */
--shown: clamp(0, calc(var(--step) - var(--at) + 1), 1);

/* .v-at — --on is 1 only on the exact step --at. The difference of two clamps
   stands in for an equality test CSS cannot express directly. */
--on: calc(clamp(0, calc(var(--step) - var(--at) + 1), 1) -
           clamp(0, calc(var(--step) - var(--at)), 1));
```

An author writes `<li class="v-reveal" style="--at: 2">` and gets a build-in; a grid
of tiles with `.v-at` highlights exactly one per step. Both work for any step count
with a single rule. A whole-filmstrip advance is one declaration:
`transform: translateX(calc(var(--step) * -100%))`.

`meta.template: './slide.html'` goes one step further: the runtime fetches and injects
it during `mount()`, so a slide can be pure HTML + CSS with no JS body. Such a module
exports only `meta`, and declares its length as `meta.steps`.

### 4.5 Context

`ctx` is the slide's only interface to the world:

- `ctx.props` — the `props` block from the manifest.
- `ctx.address` — this slide's address path.
- `ctx.load(relativePath)` — data loading, resolved against the data root (§2.2).
- `ctx.asset(relativePath)` — URL resolved against the data root (§2.2).
- `ctx.dependency(key)` — access one runtime or catalog dependency through its shared
  registry handle (§2.6).
- `ctx.bus` — presentation event bus (§7).
- `ctx.state` — persisted state, namespaced to the address (§8).
- `ctx.navigate(address)` — request navigation to any address (§5.6).
- `ctx.navigator` — immutable normalized child-section metadata on a navigator slide
  (§5.6).
- `ctx.enterSection()` — enter the child section mapped to the current navigator choice
  step
  (§5.6).
- `ctx.goUp()` — navigate to the nearest enclosing structural navigator (§5.6).
- `ctx.progress` — status and ordinals for the current address (§5.7).
- `ctx.captureKeys(handler)` — take raw keyboard input for the duration of the visit.
  Escape hatch only; slides normally receive keyboard input as `setStep`.
- `ctx.loadScript(path, { global })` — load a genuinely slide-local non-ESM script
  (§2.6).

### 4.6 Where reusable code lives

Reuse happens at two levels, and conflating them is the easiest way to get the control
boundary wrong.

| Layer | Responsibility | Reused by |
|---|---|---|
| **Custom element** | rendering a region; knows nothing of slides or steps | being written into any slide's markup |
| **Slide module** | the slide contract — steps, lifecycle, `ctx` | being named by any manifest node |
| **Manifest node** | none; it *is* the instance (§2.2, §3) | — |

An element renders. A module adapts a rendering to the slide contract: declaring a
step count, mapping `setStep(n)` onto element properties, reading `ctx.props`. A
manifest node supplies the data root and props that make one instance of it.

The test for which layer something belongs in: **could two of them appear on one
slide, or appear beside other content? Then it is an element. Is it inherently the
whole stage and the whole step axis? Then it is a module.** Markdown, code, images,
charts and diagrams are all elements. Very little is only a module.

It follows that a built-in slide type is a thin module over a standard control rather
than a reimplementation of one:

```js
export default class ImageSlide extends Slide {
  async preload() {
    this.images = this.ctx.props.images ?? [this.ctx.props.src];
    return { steps: this.images.length };
  }

  mount(root) {
    root.innerHTML = '<vividly-image></vividly-image>';
    this.el = root.firstElementChild;
  }

  setStep(n) {
    this.el.src = this.ctx.asset(this.images[n]);
  }
}
```

**The element publishes state as properties; the module owns the step axis.** An
element that knows what a step is cannot be used twice on one slide, and cannot be
used at all outside a stepped context. Keeping the mapping in the module is what lets
a control sit in a split layout beside something else, driven by that slide's own
logic, instead of only ever being a slide in its own right.

This is the proposed answer to the control boundary that §10 lists as least settled.
`annotated-markdown` is the hard case: it feels like a whole slide — nav pane,
content pane, its own sense of position — and the claim here is that it should still
be an element exposing `activeAnnotation`, with a module of a few dozen lines mapping
`setStep(n)` onto it. The prototype exists to falsify that.

### 4.7 Standard controls

The shell registers the standard control library as custom elements at boot, before
any slide mounts. Because slides live in the light DOM, a slide uses a control by
writing its tag — in a template, in `innerHTML`, or via `createElement`:

```html
<vividly-markdown src="./notes.md" highlight></vividly-markdown>
```

Registering at boot means element upgrade timing is never a concern: properties set
during `mount()` always land on an upgraded element.

Initial library, ported from llm-explainer:

| Element | Purpose |
|---|---|
| `<vividly-markdown>` | marked + highlight.js rendering, from `src` or inline content |
| `<vividly-code>` | syntax-highlighted code block with optional line emphasis |
| `<vividly-annotated-markdown>` | markdown with a numbered-annotation nav pane |

Control stylesheets live in the `vividly.controls` layer (§2.3), so slides can restyle
them with plain selectors.

#### Copying code

`<vividly-markdown>` and `<vividly-code>` provide copy buttons by default. The boolean
`no-copy` HTML attribute disables them; the JavaScript `copyable` property defaults to
`true` and reflects the inverse of that attribute. `no-copy="false"` still disables
copying because presence defines a boolean attribute. Annotated Markdown inherits
the same behavior in its document, header, and annotation content.

Markdown adds one button per block-level `pre > code`, whether fenced, indented, or
authored as HTML. Inline code and prompt fences rendered as prose do not receive a
button. The copied text is the code element's plain text after Markdown parsing,
including whitespace and trailing newlines. The code control copies its entire
source value, preserving whitespace, regardless of scrolling or line selection.
Neither path includes syntax-highlighting markup, line numbers, button labels, or
status messages.

Both controls share a quiet, visible icon button, focus styling, and copy/check
feedback. Layout reserves space for the button rather than covering code, and long
code can scroll independently of the button. The native button supports pointer,
Enter, and Space activation without also triggering presentation navigation. A
polite status announces success. Success is shown only after the clipboard write
resolves; while pending, the button cannot issue a duplicate write.

Clipboard access uses `navigator.clipboard.writeText()` from the user activation.
HTTPS or localhost and browser permission are required. An unavailable API or rejected
write displays a manual-copy explanation, logs the error, and dispatches bubbling
`vividly-error` with the original `detail.error` and `detail.operation === 'copy'`.
Failure preserves the code, allows retry, and does not substitute a legacy clipboard
fallback or success state.

Replacing content, changing `no-copy`, and reconnecting controls must not duplicate
buttons or listeners. Obsolete asynchronous completions must not update replacement
content or disconnected controls. Copy feedback requires no lifecycle timers.
The getting-started pages use these built-in buttons instead of decorating Markdown
and managing clipboard writes themselves.

#### Step readiness progress

`<vividly-step-progress>` renders progress through the meaningful build of the
current step, not position within a slide or presentation. It is registered before
slides mount, uses light DOM, and inherits the presentation theme.

- `value` is a finite number normalized to `[0, 1]`, defaulting to zero; finite
  out-of-range values are clamped. The JavaScript setter rejects non-numeric or
  non-finite values with a `TypeError`. Malformed `value` attributes render an error
  state and dispatch a bubbling `vividly-error` with `detail.error`.
- `label` supplies the progressbar's accessible name, defaulting to `Step readiness`.
  Its accessible range is 0–100, with rounded percentage values and `Ready` at one.
- The boolean `advance` attribute/property opts into an `Advance →` button at one.
  Before completion, on reset, and when opted out, the button is hidden from
  assistive technology and keyboard focus and cannot be activated. Revealing it
  neither moves focus nor changes layout.
- Activation uses the same closest-presentation `advance()` path as
  `<vividly-advance>`, including normal settling and structural navigation.
  Enter and Space activate the native button once; Right Arrow retains normal
  presentation behavior. Outside a presentation, activation does nothing.
- The bar renders each supplied value directly, without its own timer, easing,
  CSS transition, automatic advancement, or animation discovery. Reconnection must
  not duplicate DOM or listeners.

The slide owns reporting, reset, completion, and lifecycle cleanup. It may report
every animation frame for smooth motion. JavaScript-chained animations are supported:
their coordinator maps each phase onto an overall progress range and reports one only
after the final meaningful phase. Ambient animation need not stop. Settling or
reduced-motion handling reports completion immediately; stale callbacks from inactive
steps must not overwrite the active step's progress. Unknown-duration work must not
invent percentages.

The default visual is a thin full-width track with a warm-accent fill and a compact
completion button above its right end, inset to clear the shell's keyboard-help
button. `--v-step-progress-color` and
`--v-step-progress-height` customize the fill and track height. Slides own placement;
light-DOM classes allow additional styling.

Automatic progress detection and a presentation-wide placement/reporting mode are
out of scope. The initial public-site integrations replace City of Loops' local
readiness bar and Complex Ideas Should Move's two-segment step-position indicator
with this control. Both opt into Advance and report their actual animation progress.

### 4.8 Slide-defined elements

A slide may define its own custom elements, but they cannot be truly namespaced.
`customElements` is a single global registry, and `define()` is irreversible — a name
cannot be released when a slide unmounts, nor redefined with a different class. Scoped
registries exist, but they attach through `attachShadow({ registry })`, so they only
scope elements inside a shadow root. That door is closed for slides, which live in the
light DOM by design.

Namespacing is therefore by convention: prefix the tag with the slide's directory
name, `<token-anatomy-legend>`. Generated or hashed prefixes are rejected because a
hashed tag name cannot be written into a `slide.html` template, which is the point of
having one.

Two rules:

- **Define at module scope.** The ES module cache evaluates a module once per resolved
  URL, and the runtime normalizes every module path to an absolute href, so a
  top-level `define()` runs exactly once however many times the slide appears in a
  deck. Defining after `mount()` has set `innerHTML` is a bug: those elements upgrade
  asynchronously and properties assigned before upgrade are silently dropped.
- **Do not guard against collisions.** `if (!customElements.get(name))` makes a
  colliding second slide silently adopt the first slide's implementation — a
  wrong-behaviour bug in place of a loud error. Prefix so collisions cannot happen,
  and let a genuine one throw.

Slide-defined elements sit inside the slide root, so `@scope` covers them and their
styles belong in the slide's own stylesheet. This is the exception rather than the
norm: most slides want plain DOM and classes, and anything genuinely reusable belongs
in the control library. A widget that truly needs encapsulation may use Shadow DOM for
itself alone — theme custom properties still inherit through it, so it stays themable.

## 5. Orchestrator

Implemented as `<vividly-presentation>`. It owns routing, presentation input, the preload
window, transitions, and the stage for one selected root presentation. The project
shell owns catalog loading, global route dispatch, and root-presentation handoff.

### 5.1 Address and routing

Hash-based, path-shaped, stable across edits:

```
#/                                      project catalog
#/product-tour/                         presentation table of contents
#/product-tour/intro/token-anatomy/3    presentation id / slide address / step index
```

The first segment selects a catalog presentation. The remaining slide address is the
path of manifest-node IDs within that presentation; a final numeric segment is the step
and is omitted when zero. Presentation IDs and address paths use stable IDs, not
ordinals, so inserting a presentation or slide does not break existing links.

A presentation-local route has no leading slash. The empty string is the presentation
table of contents, `intro/title-card` is a slide at step zero, and
`intro/title-card/2` is that slide at step two. These are the values stored as a
thread's `latestRoute` and accepted by `createThread({ route })`. Manifest node IDs may
not begin with `~`; the namespace remains reserved even though the initial runtime
defines no presentation-local runtime route.

`#/` is the project catalog and lies outside every presentation. An unknown presentation
ID or invalid local address is an invalid route; it is never interpreted as a manifest
path. The shell removes the presentation prefix before handing a route to the selected
orchestrator.

Every slide and every step is addressable and shareable. The URL carries structural
position only. Transient and per-reader state — scroll offset, which annotation is
expanded, whether a tool result was revealed — lives in `ctx.state` (§8) and is
deliberately not encoded in the hash, so a shared link lands the recipient at the same
place in the presentation without importing the sender's reading state. Step addresses
into a `dynamic` slide are best-effort (§4.3).

An external link can opt into advancing one step after its initial route loads by adding
`?vividly-auto-advance=1` before the hash, for example
`https://example.com/?vividly-auto-advance=1#/product-tour/intro/title-card`. When the
route identifies a slide at step 0 that supports step 1, the runtime enters that slide,
then advances it once without crossing to another slide. It removes this parameter while
replacing the current history entry with the step-1 route, preserving other query
parameters. Browser Back therefore returns to the previous page rather than revisiting
the unadvanced landing step. Links without the parameter, links to a nonzero step, and
subsequent in-page navigation retain their ordinary behavior. If keyboard onboarding
appears, the one-step advance happens after the reader dismisses it and enters the slide.

The table of contents' Outline or Grid mode, thumbnail visibility, and step expansion
are also per-reader state rather than routes. Switching those controls does not change
the hash or append browser history. `~sorter` is not a compatibility or input route; it
is invalid under this grammar.

`ctx.address` is the presentation-local slide address, not the ID-prefixed global route.
Likewise, `ctx.navigate(address)` accepts only an address in the currently normalized
presentation tree. Cross-presentation movement selects a catalog ID through the
presentation-thread API. Keeping these APIs local lets a shared slide module and an
incorporated manifest behave unchanged in every root presentation and makes a root
handoff explicit rather than disguising it as ordinary slide navigation.

A known limit: slide-internal state is not addressable. You can link to guided point 3
of a data explorer, but not to "the explorer focused on record 4711". Making that work
would mean letting a slide contribute an opaque trailing segment to the address. It is
unbuilt, but the grammar reserves room for it, so adding it later will not invalidate
existing links.

### 5.2 Keyboard

The orchestrator installs a single `keydown` listener on `document`. Slides never
listen directly; this is what keeps incorporated chapters and runtime views from
fighting over input.

| Key | Action |
|---|---|
| Right | Advance an ordinary step, or move navigator selection right |
| Left | Reverse an ordinary step, or move navigator selection left |
| Down Arrow | Move navigator selection down; no ordinary presentation action |
| Up Arrow | Select a choice spatially above, or move to the enclosing navigator |
| Space | Advance one step through the forward structural itinerary |
| Home / End | First / last step of the current fixed-length slide |
| PageDown / PageUp | Next / previous slide or section at the selected level |
| `[` / `]` | Move the selected level outward / inward |
| Enter | Activate the current navigator choice or rendered after continuation |
| Escape | Table of contents |
| `?` | Keyboard help |

Advancing past the last step of an ordinary slide moves to the next slide; going back
from step zero enters the previous ordinary slide **at its last step**. A navigator
occupies a contiguous interval within a fixed-length slide: one explicit step per
choice and an explicit after-completion step. There is no before-first detent.
Steps outside that interval
retain ordinary fixed-slide behavior.

Inside the interval, arrows move selection without entering a section. Left and Right
prefer a choice in the corresponding rendered row; Up and Down prefer one in the
corresponding column. If no spatial neighbor exists, Left falls back one choice backward
in manifest order and Right or Down one choice forward. Up instead returns to the
nearest enclosing navigator; at the root top edge it does nothing. Selection does not
wrap. Left before the first choice reaches the preceding ordinary step or structural
boundary. Right or Down beyond the final choice skips after and continues to the first
concluding step or forward boundary. Forward arrival selects the first choice when it
is step zero; backward arrival skips after and selects the final choice. Introductory
and concluding steps are preserved. Direct entry, history, and child completion retain
their explicit steps.

From after, Left or Up selects the last
choice while Right or Down reaches the following ordinary step or structural boundary.
Outside the interval, Right and Left retain ordinary step traversal, Down has no
presentation action, and Up moves to the nearest enclosing navigator.

Space preserves the complete forward structural itinerary. It advances ordinary
steps, enters the selected child section (including the final choice), and
advances from after. Enter enters the selected child or activates a rendered after
continuation; it has no presentation action at an after detent without a
control, or on an ordinary navigator-slide step. Completing a child revisits the owning
navigator at the next choice or after step. Crossing backward before a child revisits
its explicit choice step.

At a root navigator's after step, Right Arrow, Down Arrow, or Space continues to the
first root slide after the final owned section or to the first concluding step when one
exists. Enter also continues when the navigator renders an after control. Left Arrow
from the following root slide revisits the root navigator's final choice.

Navigator arrow handling remains runtime-owned during step animation settling. The
runtime first resolves the spatial target using the rules above, then compares the
target step with the current step to obtain the incremental direction. If that
direction matches unsettled motion, settling consumes the arrow before selection or
focus changes. A later arrow moves to the resolved target. If the direction opposes
the unsettled motion, selection changes immediately and the new step replaces the old
motion. An arrow with no target and no boundary action leaves the step unchanged and
does not perform a settling check.

Space remains a forward itinerary action inside a navigator. It settles same-direction
motion before entering the selected child or advancing
from the after step. Enter is explicit activation rather than incremental traversal
and activates its target immediately.

Navigator slides normally render the after step by clearing current treatment from all
choices without adding a prompt or continuation control. Slides must not label an
assumed next destination; structural traversal computes it from the manifest. A
rendered after control is an explicit product exception, not the authoring default.

Navigator choices and any rendered after continuation use runtime-managed roving focus.
A keyboard selection moves actual DOM focus without scrolling. A boundary detent
without a rendered control leaves no navigator control tabbable. Sequential arrivals
and keyboard child returns focus the selected control. Fresh entry and reload focus
it only when focus is on the document body. Browser history and thread rehydration
restore selection and tab stops without forcing focus. Inactive boundary UI may retain layout but is hidden, noninteractive,
untabbable, and absent from the accessibility tree.

Entry animation runs within the selected state, without a separate navigation step or
history write. The documentation opening animates on fresh first-choice entry, refresh,
and forward entry from the preceding slide, but not child returns or restoration.
Hover subtly lightens a choice's background without moving it or adding selection
accents. Selection has a persistent accent border and stripe; keyboard focus adds an
outer ring. Pointer hover never changes selection or focus.

Structural navigation starts at slide level. Each press of `[` selects the next ancestor
toward the presentation root, and `]` selects the next descendant toward the current
slide. PageDown enters the next subtree at its first leaf and first step. PageUp enters
the previous subtree at its last leaf and last step. The level remains selected across
jumps and is clamped to the deepest level available when entering a shallower branch.
Opening the table of contents resets the selected level to slide level.

Changing levels does not navigate. A transient breadcrumb HUD identifies the selected
level after `[` or `]`, including at a boundary, and after PageUp or PageDown. End has no
effect on a dynamic slide because it has no known last step. On compact Mac keyboards,
Fn+Left/Right produce Home/End and Fn+Up/Down produce PageUp/PageDown.

A low-opacity `?` button remains available in a corner and becomes fully opaque on hover
or focus. Selecting it or pressing `?` opens a keyboard shortcut dialog. Any subsequent
key or pointer click softly dismisses the dialog without performing another action. The
trigger and dialog are absent from thumbnail capture mode, and the transition respects
the reader's reduced-motion preference.

#### Touch navigation

[Touch Navigation](touch-navigation.md) defines single-touch left/right traversal,
a dedicated upward-swipe grip, and persistent touch-capable-device controls.
Left/right gestures invoke forward/reverse structural itinerary commands, including
step animation settling; they do not simulate spatial arrow keys or skip reveals.
Up returns directly to the nearest owning navigator, with TOC fallback when there
is no owner. Keyboard behavior above remains unchanged.

The touch contract also governs native and author-declared gesture exclusions,
browser gesture ownership, overlay priority, and rejection of gestures while
navigation is pending render readiness.

### 5.3 Preload window

The orchestrator maintains a window of `{ prev: 1, next: 1 }` around the current
slide, configurable in the manifest. Slides entering the window are imported,
preloaded, and mounted hidden; slides leaving it are unmounted and disposed. Preload
work is scheduled with `requestIdleCallback` so it never competes with an in-flight
transition.

### 5.4 Transitions

Each slide is mounted inside a runtime-owned **layer** (§5.5). On navigation the
runtime marks the incoming layer `.v-enter` and every visible outgoing layer
`.v-leave`, sets `data-transition` and `data-direction` on both, and awaits
`element.getAnimations()`. Transitions are therefore defined entirely in CSS —
`dissolve`, `fly`, `slide`, and `cut` are stylesheet rules, not JS, and adding one
means adding a rule. `slide` moves the incoming and outgoing layers by their full width
without changing opacity.

A transition belongs to the **boundary immediately before a slide**. Moving forward
from A to B uses B's transition; moving backward from B to A uses the same transition
in reverse. For a non-adjacent jump, the later endpoint owns the transition, preserving
the same result in both directions. Initial entry uses the destination slide's
transition in the forward direction.

The selected transition is stamped on both layers. Direction is carried separately in
`data-direction`, so one declaration covers both ways through. Entering an incorporated
chapter needs no special rule: its first slide owns the boundary into that chapter.

Three properties the prototype proved are not optional:

- **Navigation is serialized.** Overlapping `_show` calls corrupt layer state. All
  navigation goes through a promise queue.
- **Cleanup is generation-guarded and state-derived.** Each transition takes a
  generation number; a later navigation cancels and snaps the earlier one, whose
  cleanup then aborts. Final visibility is reconciled from *the current slide*, never
  from the outgoing/incoming pair captured when the transition started. Deriving it
  from the captured pair left stale layers visible under rapid input.
- **Waiting on animations needs a timeout.** CSS animations do not progress in a
  backgrounded tab, so `finished` never resolves and the navigation queue deadlocks
  permanently. The wait is capped, after which animations are force-finished.

### 5.5 Layers

```
.v-stage            runtime
  .v-layer          runtime — visibility, transition classes, --step/--steps
    .v-slide        author  — @scope root, data-step/data-steps, slide content
```

The split exists because slide CSS is unlayered and beats the runtime's own rules.
Anything the runtime must be able to guarantee — that a dead slide is not painted,
that a transition class applies — lives on the layer, which is outside the slide's
scope root and therefore unreachable from slide CSS.

### 5.6 Navigation: spine, navigators, and edges

The manifest tree defines a **spine** — the default in-order traversal of its leaves.
Next/prev follow the spine, and for a linear deck the spine is the whole story.

Everything non-linear is an **edge** layered on top. Ad hoc edges use
`ctx.navigate(address)` to any address in the tree. Because addresses are path-based
and stable, those edges need no registry or declaration in the manifest.

- A **choice** is a slide offering several unrelated navigate targets. No new
  mechanism.
- **Skip** is an edge to the address following a subtree; **drill-in** is an edge into
  one.
- A **navigator** is a slide whose `navigator.sections` manifest field maps its
  explicit choice steps to direct child sections. `navigator.choiceStartStep` defaults
  to zero and is nonnegative; each section receives the next step in manifest
  order, and the step following the final choice is after. `ctx.enterSection()` follows
  the mapping at a choice step. Crossing the child's forward boundary revisits the
  navigator at the following choice or after step; crossing its backward boundary or
  calling `ctx.goUp()` revisits its explicit choice step. Nested navigators apply
  recursively.

  A navigator declares enough fixed steps to contain its complete interval and may
  include ordinary introductory or concluding steps outside it. A dynamic count,
  invalid `choiceStartStep`, or insufficient fixed count is an authoring error.

Navigator ownership and boundary destinations are normalized tree facts. Slides inside
a child section require no markers or lifecycle participation. Direct entry, reload,
and thread rehydration derive the same boundary behavior without a runtime call stack.
The manifest shape, validation, exact APIs, and chronological history rules are
normative in the presentation threads specification.

The spine is a default, not a constraint. A presentation that is entirely
choice-driven simply never uses it.

### 5.7 Progress

Progress exists for one reason: a presenter hopping around the table of contents while
answering audience questions needs to see at a glance what has been covered. That is
served by three states per node, not by a percentage.

Every node is **not-started**, **in-progress**, or **complete**. Interior nodes
aggregate bottom-up — not-started when no child has started, complete when every child
is complete, in-progress otherwise. The same marker appears at every level, which is
what keeps a deep book readable at a glance.

**Leaf status without loading the slide.** A slide never entered is not-started, known
from state alone. Once entered, the runtime derives status from steps seen: complete
when the reader has reached the last step, in-progress otherwise. A slide with richer
semantics — a data explorer that considers itself covered at four of six guided points
— overrides this by writing its own status into `ctx.state` when it changes.

The slide *writes* its status rather than being *asked* for it. Asking would fail for
any slide the preload window has disposed, and would mean loading slide modules to
render a table of contents. Reading status entirely from `ctx.state` is what keeps
composition (§6) cheap: the TOC for a twenty-chapter book loads no slide code at all.

**Ordinals.** Sibling index and count — "slide 6 of 9 in this section", and at the
innermost level "step 2 of 4" — are available for display, being nothing more than
tree facts. They are positional, not cumulative: they report where the reader is, not
how far they have come. A flat "slide 12 of 40" is deliberately not offered, because
once readers can skip or choose, its denominator is the length of a traversal that no
longer exists.

### 5.8 Render readiness

Automation needs a positive signal that a routed step has settled; document load and
network idleness do not prove that slide lifecycle work, fonts, images, and transitions
have completed. The orchestrator removes `data-render-ready` from
`<vividly-presentation>` when navigation starts and restores it only after it has
preloaded and mounted the slide, applied the requested step, completed the transition,
awaited `document.fonts.ready`, decoded descendant `<img>` elements, and crossed two
animation frames. Each frame wait is bounded because browsers may suspend animation
frames in hidden documents; render readiness must not deadlock navigation when that
happens. Thumbnail generation waits for this attribute before capture.

`?vividly-capture=1` enables capture mode. In this mode the runtime disables CSS
animations, transitions, smooth scrolling, and visible carets without changing the
routed slide or step. The parameter is an automation interface, not presenter state,
and is never persisted.

Slides perform asynchronous data acquisition in `preload()`. `mount()`, `enter()`, and
`setStep()` establish their rendered state synchronously; starting untracked asynchronous
render work from those methods violates the lifecycle contract and cannot participate in
render readiness. The two-frame boundary permits synchronous DOM changes to reach
layout and paint without inventing a thumbnail-specific slide hook. When frames are
suspended, the bounded fallback preserves navigation progress without claiming that a
hidden document was painted.

Here, render readiness and step animation settling are separate contracts.
`data-render-ready` waits for orchestrator-owned slide-to-slide transitions, but it
does not wait for tracked step-owned motion to finish. It becomes ready after that
motion has been discovered, so a queued incremental action can settle it
deterministically. Capture mode disables the motion and therefore has nothing to
settle.

## 6. Composition

A presentation incorporates another by reference:

```yaml
- type: presentation
  id: regex
  manifest: ./chapters/regex/presentation.yaml
```

The reference is resolved at **load time**: the child manifest is fetched and its
nodes are spliced into the parent tree. There is one orchestrator, one stage, one
keyboard, one preload window. This is what makes a "book" of "chapter" presentations
work, with chapters drawn from a shared library.

It works because of an asymmetry: **manifests are cheap and slide modules are
expensive.** Resolving a reference costs one small YAML fetch and yields the complete
subtree — ids, titles, structure, declared step counts — without loading a single line
of slide JS or CSS, or any asset. Code loading stays governed by the preload window
(§5.3).

The alternatives look like a three-way choice and are really a two-way one, since in
every viable design the author writes a reference and nothing is copied. What differs
is when the reference resolves:

- **Author-time inlining** — a tool flattens chapters into one manifest. This *is*
  copying: it severs the live link, so fixing a chapter does not fix the books using
  it. It defeats the point of a library.
- **Runtime instantiation** — each chapter becomes a child orchestrator satisfying the
  slide contract. To report its own length it must eagerly preload its entire subtree,
  which is exactly what the preload window exists to avoid, and it brings nested
  stages, transitions inside transitions, and two components wanting the keyboard.

### 6.1 Rules

**Root eligibility.** A chapter manifest may be valid when normalized as a root, but it
is independently runnable only when registered in the catalog. Registration and
incorporation are independent: a cataloged presentation may be incorporated elsewhere,
and an uncataloged manifest may be incorporated but has no root presentation identity.

**Theme.** `theme:` means *what this presentation looks like when it is the root*.
Embedded, it is ignored and the host's theme applies. There is no override flag and no
precedence table, because none is needed: a chapter that must look a particular way
expresses that in its slide stylesheets, which are unlayered and already beat the
theme layer (§2.3). This also avoids an unresolvable ambiguity — with a single field
there is no way to distinguish a chapter's default theme from one it insists on.

**Transition** cascades slide → chapter → book, most specific winning. A chapter's
`transition:` is the default for its own slides and is preserved when embedded.

**Addresses** compose within the selected root: the `regex` presentation can contain
the local address `deep-dive/backtracking`, producing the global route
`#/regex/deep-dive/backtracking/2`. IDs need only be unique within their own manifest,
since the incorporating node's ID scopes everything beneath it.

**Paths** resolve against the manifest that declared them, so a chapter's relative
module and asset paths keep working at any depth.

**Sections.** An incorporating node becomes a section, so a navigator may list it like
any other child section. Completing the chapter then returns to that navigator.

**Self-contained chapters.** A chapter maintained elsewhere and refreshed by replacing
its slide directories should keep those directories self-contained: runtime imports
use the `vividly/` prefix (§2.1), other imports and `ctx.load`/`ctx.asset` paths stay
within the directory, and shared packages come from `ctx.dependency()`. A relative
import that climbs out of the directory ties it to one site layout and breaks when the
directory moves to a different depth.

**Cycles must be detected.** A manifest referencing itself, directly or through a
chain, otherwise recurses until the tab dies. Resolution carries a visited-URL set.

**Fetches are parallel per level.** Resolving references serially makes a
twenty-chapter book twenty round trips deep before first paint.

The one thing this cannot express is a presentation running *inside* a frame on a
slide — picture-in-picture. That is a different feature, and it would be an ordinary
slide that happens to embed a runtime.

### 6.2 Presentation threads

A presentation thread is a page-local bookmark containing an opaque identity, catalog
presentation ID, latest presentation-local route, and recency. It is not composition
and does not retain a mounted presentation session or private navigation stack.
Switching threads resolves the ID through the catalog, disposes the outgoing runtime,
and loads the destination route fresh. Arbitrary manifest URLs are not thread identities
or thread targets.

Browser history is one chronological journal across all threads. Application-authored
visible navigation appends entries; browser Back and Forward restore the selected
entry without being repurposed as structural return or thread switching commands.

The lifecycle, runtime API, history markers, reload behavior, and route-only restoration
contract are normative in the presentation threads specification.

## 7. Eventing

`ctx.bus` provides `emit(type, detail)` and `on(type, handler)`. Subscriptions taken
by a slide are released automatically at `unmount()`.

Reserved event types: `vividly:navigate`, `vividly:step`, `vividly:slide-enter`,
`vividly:slide-exit`, `vividly:steps-changed`, `vividly:preloaded`.

An incremental action consumed solely to settle step-owned motion emits none of these
events because it does not change presentation state.

Slide-authored events use their own prefix. The bus is a plain `EventTarget`; it is
not a state store.

## 8. State and theming

**State.** `ctx.state.get(key)` / `ctx.state.set(key, value)`, namespaced by slide
address, serialized into localStorage under the normalized catalog URL and presentation
ID. The catalog URL distinguishes projects served from different paths on one origin;
the presentation ID distinguishes roots within a project. The store is used for
visited/completion tracking and for slides that deliberately remember where the reader
was. It belongs to the presentation identity, not to a thread. Cold thread rehydration
does not snapshot it, and multiple threads for the same presentation observe the same
durable state. Transient controls expected to reset during thread switching do not write
their state here. State is scoped to the selected root identity: the same manifest
incorporated into another root, or registered separately under another root ID, does not
share state with the original root.

**Theming.** A theme is a plain CSS file defining custom properties on `:root`. The
rule that makes theming work: **slide stylesheets reference tokens, never literal
colors or spacings.** Tokens follow llm-explainer's naming — `--bg-*`, `--text-*`,
`--accent`, `--spacing-*`.

## 9. Overview views

The project catalog and presentation table of contents share a stable top bar above an
independently scrolling content body. The bar contains a Vividly identity and a
breadcrumb navigation trail. The catalog marks its Catalog crumb as current. A
presentation table of contents links its Catalog crumb to `#/` and marks the
presentation-title crumb as current. Presentation-specific display controls appear
only in the table of contents. The top bar is hidden while a slide is presented;
keyboard help and thread controls retain their separately specified behavior.

At ordinary widths, the bar uses two rows. The packaged Vividly logo is at the left of
the first row and the Outline/Grid mode selector is at the right. Breadcrumbs are at
the left of the second row, with icon-only **Show thumbnails** and **Expand/collapse
steps** controls at the right. Their accessible names and tooltips identify their
actions, while their pressed and expanded states remain programmatically available.
The logo uses its artwork's 508:130 aspect ratio so its intrinsic file dimensions do
not inflate the first row. The header crops the logo's built-in SVG whitespace so the
painted left edge of the `V` aligns with the bar while leaving the canonical logo asset
unchanged. The TOC uses 32 pixels of top padding and 24 pixels on its other sides at
ordinary widths. Narrow layouts may add rows and reduce padding to preserve readable
breadcrumbs and reachable controls without horizontal overflow.

Keeping the bar outside the content body leaves its navigation and controls visible
while a long catalog, outline, or grid scrolls. Keyboard selection remains visible
within that body. Home selects the first visible item and scrolls the body to its start;
End selects the last visible item and scrolls the body to its end. Vividly uses the
native scrollbar and may style it subtly, but does not hide it or require pointer hover
to expose scrolling. The scrollbar gutter remains outside item selection and hover
surfaces.

### 9.1 Project catalog

Catalog and TOC destinations, including expanded step cards in Outline and Grid,
use the navigator's hover treatment: subtly lighten the background without adding
selection accents or changing selection or focus. Accent borders remain reserved
for the selected destination and keyboard focus.

The project catalog (`#/`) lists author-owned catalog entries in catalog order without
loading every manifest. Arrow keys move focus among presentations; Home and End move to
the first and last entries. Enter and pointer activation both create a fresh
presentation thread at the selected presentation's table of contents. Merely moving
focus does not activate a presentation or update recency.

Escape from a table of contents returns to the catalog and focuses the presentation
just exited, scrolling it into view. On a cold catalog load, the catalog focuses the
persisted most-recently activated presentation when that ID still exists, otherwise
the first entry. Activation, not focus movement, updates that persisted ID. Escape in
the catalog has no navigation effect. An open runtime dialog or menu consumes Escape
before this view hierarchy does.

### 9.2 Presentation table of contents

The table of contents (`#/<presentation-id>/`) is the presentation's single overview
route. It offers two display modes, **Outline** and **Grid**. Switching mode changes no
route and creates no browser-history entry. Each presentation persists its own selected
mode in the runtime state store; a presentation with no stored preference starts in
Outline. A direct link, reload, new tab, browser-history traversal, or thread
rehydration uses that presentation's current persisted mode. The URL does not
communicate mode or expansion preferences.

When the runtime has displayed a slide, the table of contents visually identifies the
active slide and step. Escape from a presented slide opens the same presentation's
table of contents in its persisted mode, focuses the active destination, and scrolls it
into view. Direct TOC entry, browser-history restoration, and thread restoration
synchronize the visual selection without stealing focus. A fresh runtime that has not
displayed a slide selects the first available item.

In Catalog, arrow keys move focus among visible first-class destinations. In Grid,
Left and Right move to the previous and next visible destination in manifest order,
while Up and Down move to the nearest horizontally aligned destination in the
immediately adjacent rendered row. Grid Home and End move to the first and last
destination.

Within the table of contents, `g` selects Grid, `o` selects Outline, and `s` toggles
the shared expanded-steps preference when the **Expand/collapse steps** control is
enabled. These shortcuts change no route or browser-history entry. Mode shortcuts
focus the selected destination in the newly visible mode. Collapsing from a focused
Outline step returns focus to its owning slide. The same unmodified keys have no
view-switching or expansion behavior in the Catalog or while a slide is presented.

Outline follows its visual structure: Up and Down move to the previous and next slide,
Home and End move to the first and last slide, and expanded step cards never
participate in that vertical sequence. Right moves from a slide to its first visible
step and then through that slide's steps. Left moves to the previous step and returns
from the first step to its owning slide. Left and Right do not cross between slides and
have no effect on a slide without visible expanded steps. Up or Down from a step moves
to the adjacent slide relative to that step's owning slide. Collapsed and otherwise
hidden steps never participate in keyboard navigation.

Enter and pointer activation have identical destination semantics:

- activating any canonical slide destination opens it at step zero
- activating an explicit step opens that exact zero-based step

Moving focus alone never changes or discards the active slide or step. Re-entering the
already-current slide performs the `exit()`/`enter()` cycle defined in §4.2.

### 9.3 Outline mode

Outline mode renders the normalized manifest tree, including incorporated chapters,
and the three-state status marker (§5.7) on every node. It provides a push-on/push-off
**Show thumbnails** button. Thumbnails are hidden by default, and the preference is
persisted per presentation. Toggling thumbnails does not change the table of contents'
outer width or move its top bar.

The presentation has one persisted expanded-steps preference shared by Outline and
Grid, initially false. The **Expand/collapse steps** control remains enabled and visible
in Outline when thumbnails are hidden. Activating it first enables **Show thumbnails**
and sets expansion to true rather than toggling the retained expansion state,
preserving stable top-bar geometry. Once thumbnails are visible, later activations
toggle expansion normally. When thumbnails and expanded steps are both enabled, a
slide with multiple indexed steps replaces its canonical thumbnail with those
destinations while retaining the outline hierarchy and a clear visual grouping.
A slide with one indexed step likewise replaces its canonical thumbnail with that
explicit step card. A slide with no indexed steps retains its canonical title-bearing
placeholder. The responsive layout may place step destinations horizontally or
vertically according to available space. When thumbnails are hidden, step destinations
are hidden as well, but the shared expansion preference is retained.

### 9.4 Grid mode

Grid mode displays one canonical card per slide while the presentation's shared
expanded-steps preference is false. When expansion is enabled, each slide card is
replaced in place by that slide's complete indexed step sequence in ascending step
order. Step cards are first-class keyboard destinations, remain visibly grouped by
their owning slide, and use one-based labels such as `Step 2 of 4`. Expanded sequences
participate directly in one responsive wrapping grid rather than using a structural
wrapper that forces every slide onto its own row. A subtle alternating background
treatment identifies adjacent cards from the same slide even when a sequence wraps,
with thick warm-accent borders marking the left edge of the first card and the right
edge of the last card in every slide sequence. Cards retain a consistent thumbnail
width independent of how many indexed steps their slide contains; a one-step sequence
must not stretch to fill the row. Per-slide expansion controls and expansion maps are
deferred.

The canonical card uses the thumbnail index's canonical step rather than assuming step
zero for its image. Activating any canonical card opens the slide at step zero. An
explicit step card opens its indexed step. The active slide and, when represented,
active step have a non-color-only visual marker.

### 9.5 Thumbnail data and accessibility

Both modes load `/thumbnails/index.json` from the composed site without importing or
mounting slide modules. Images are lazy-loaded. A missing index, slide entry, step
entry, or image produces the existing title-bearing placeholder rather than a broken
image. Dynamic slides use their canonical indexed image when present and otherwise the
same placeholder. This feature adds no catalog thumbnail field.

Mode controls expose their selected state, expansion controls expose their expanded
state, breadcrumbs identify the current page, and hidden mode content is absent from
the accessibility tree. Switching mode leaves focus on the activating mode control and
synchronizes content selection without stealing focus. Collapsing a sequence that
contains focus moves focus to its owning slide card before removing the step cards.
The exact responsive arrangement may vary, but DOM and keyboard order remain manifest
order.

Overview preferences use the existing durable state identity: normalized catalog URL
plus presentation ID. Stronger local-development project disambiguation is deferred.

The generated index has a versioned, timestamp-free shape and sorts presentation IDs
and addresses. Each slide entry records its canonical step and an ascending contiguous
sequence:

```json
{
  "version": 3,
  "presentations": {
    "product-tour": {
      "mechanics/diagram-build": {
        "canonicalStep": 2,
        "steps": [
          {
            "step": 0,
            "path": "product-tour/mechanics/diagram-build/step-0000.png",
            "revision": "628ee627a7b31e7f8c3185a14e408154fc10d484939d60ff5c5927c31f22056f"
          },
          {
            "step": 1,
            "path": "product-tour/mechanics/diagram-build/step-0001.png",
            "revision": "ba800375968690a9b7e4e2454a040eafff9b7c21c1905b9e31dbdb1448817e24"
          },
          {
            "step": 2,
            "path": "product-tour/mechanics/diagram-build/step-0002.png",
            "revision": "a41789b9e0529bc5006a4498c0c51a520401e3f2f9049209dd9d9e2f482e4441"
          }
        ]
      }
    }
  }
}
```

Thumbnail paths are relative to the author-owned `site/thumbnails/` source and deployed
`/thumbnails/` URL. Thumbnail identity includes the presentation ID, complete local
address, and step, so equal addresses, shared modules, and different steps do not
collide. Each revision is the lowercase hexadecimal SHA-256 digest of the encoded PNG.
The runtime appends it as the image URL's `v` query parameter while retaining the
stable physical path.

The runtime fetches the stable index URL with cache revalidation once per activated
presentation and retains the validated branch in memory. The CLI owns the author index
and every image named by it, but not unindexed files in that directory. The complete
local address prevents collisions between incorporated chapters within one root.

## 10. Open questions and unimplemented items

This document was first tested against a small prototype runtime. This section records
what that pass settled, which questions remain open, and what the runtime does not yet
implement.

Open questions, in priority order:

- Which llm-explainer controls belong in the control library and which belong inside
  slides? §4.6 proposes a rule — anything that could appear twice on one slide is an
  element, and a built-in slide type is a thin module wrapping one. Whether that
  survives contact with `annotated-markdown` is the open part.
- Does forcing `annotated-markdown` into the step model improve it or distort it?
- Does three-state status actually serve the presenter mid-question, or does hopping
  around the TOC reveal a need the crude model misses?
- Is `mount`-hidden-then-`enter` sufficient for slides that need measured layout?
  Untested so far — every prototype slide sizes itself from CSS alone. The
  `annotated-markdown` port will hit this first, since it calls `scrollIntoView`,
  which is a no-op on a `display: none` element.
- Is `props` enough for reuse, or do slides need per-instance data files?

Settled by the first runtime pass:

- `@scope` wrapping holds up, and unlayered-beats-layered removes specificity fights
  entirely — but it also lets slide CSS defeat runtime rules, which is why the layer
  split in §5.5 exists.
- Relative `url()` must be rewritten by the runtime (§2.3).
- Numeric `--step` / `--steps` are as important as the attributes; without them,
  step-driven CSS does not scale past hand-written per-step rules.
- Transition waits need a timeout, and navigation needs to be serialized (§5.4).

Still unimplemented in the runtime: cycle detection and parallel fetching in manifest
resolution (§6.1), three-state status aggregation (§5.7), chapter transition cascade,
and the control library itself.

## 11. Deferred

Audio narration and timing, bundling for deployment, presenter view and speaker notes,
printing/export, mobile layout, authoring tooling and slide scaffolds. Dynamic-slide
thumbnail checkpoints and live miniature rendering in overview views are also deferred.
