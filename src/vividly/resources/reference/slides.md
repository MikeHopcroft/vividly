# Slides

A slide is a directory: its code, styles, data, images, and any libraries only it needs
all live inside it, and putting it in a presentation touches nothing but the manifest.
Vividly supplies the shared parts — theme tokens, the standard controls, the runtime —
so the directory holds what is *particular* to one slide, not everything it draws on.

That is the whole authoring model. It exists so you, or a coding agent working on your
behalf, can build one slide without reading or touching any other.

The directory is a unit of *authorship*, not a rule about where files must live. A slide
that contributes no code of its own can borrow a module from elsewhere and keep only its
data — see [Reusing a module](#reusing-a-module-with-different-data).

For the end-to-end procedure and definition of done, start with
[Authoring slides](./authoring.md).

## Anatomy

```text
site/
├── catalog.yaml
├── presentations/
│   └── product-tour.yaml
└── slides/
  └── photo-tour/
    ├── slide.js          the module — unless the manifest borrows one
    ├── slide.css         styles, scoped to this slide
    ├── slide.html        optional template
    ├── data/photos.yaml  data the slide loads at runtime
    ├── assets/hero.png   images referenced by the slide or its data
    ├── assets/detail.png
    └── lib/chart.js      slide-local source module
```

  Keep presentation assets local when practical so the published site remains portable
  and works offline.

Name the directory in kebab-case. It is conventionally the same as the slide `id` in the
manifest, and it also prefixes any custom elements the slide defines, so a short
distinctive name pays off: `token-anatomy`, not `slide2`.

`slide.js` is an ES module, loaded natively by the browser. There is no build step and no
bundler — what you write is what runs.

## JavaScript file extensions

Use `.js` for ordinary browser-only slide modules and helpers. Use `.mjs` when a
module is deliberately shared between browser code and Node.js authoring tools and
needs an explicit ES-module identity outside a Node package's scope. This is a
targeted exception, not a convention to apply to every new slide.

| Code | Default |
| --- | --- |
| Browser-only slide modules and helpers | `.js` |
| Authoring tools | Follow the tool's package configuration; `.mjs` explicitly denotes an ES module |
| Modules shared by browser code and Node.js tools | `.mjs` when explicit module recognition is needed |

In Node.js, `.mjs` explicitly selects ES modules. A tool-local `package.json` with
`"type": "module"` also permits `.js` ES modules within that package's scope, but
does not govern shared files elsewhere in `site/`. Do not add a root package
manifest or a build step merely to author browser modules.

Browsers load modules through `import` or `<script type="module">`, not through the
filename extension or `package.json`. Both `.js` and `.mjs` must be served with a
JavaScript MIME type such as `text/javascript`. Some static web hosts may require
explicit MIME-type configuration for `.mjs` files. GitHub Pages supports `.mjs`
without project-specific MIME configuration; see
[MDN's module-extension guidance](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules#aside_%E2%80%94_.mjs_versus_.js).
For any publication target, verify the deployed module URL returns HTTP success
and a JavaScript content type, and exercise its imports in a browser. An HTML 404
response is a path or publication problem, not evidence that `.mjs` is unsupported.

Keep Node-only tools and their dependencies outside `site/`. A shared module must
be browser-safe: no Node built-ins, package-manager dependencies, or tool-only
side effects in its browser import graph. Authoring dependencies must not become
requirements for viewing the checked-in presentation.

## Browser dependencies

Declare browser-ready shared dependencies once in `site/catalog.yaml`, pinned to an
immutable HTTPS base:

```yaml
dependencies:
  three:
    baseUrl: https://cdn.jsdelivr.net/npm/three@0.180.0/
    entry: build/three.module.js
```

Every presentation in the catalog uses that same selection. If imported slides expect
different versions, reconcile them before presenting rather than assigning different
meanings to one key.

Slide code uses the logical key:

```js
const dependency = this.ctx.dependency('three');
const three = await dependency.load();
const entryUrl = dependency.url();
```

`load()` returns the shared registry instance for every loader type. `import()` remains
available for catalog ESM dependencies and returns the same module namespace, but fails
for classic-script and stylesheet dependencies.

The selected runtime also provides `js-yaml`, `marked`, `highlight-js`, and
`highlight-github-dark`. Run `vividly dependencies` to inspect the complete effective
registry. Catalog keys cannot replace runtime-owned keys.

`vividly run` and `vividly thumbnails` fill Vividly's persistent user cache as
dependency resources are requested. Before presenting without network access, run
`vividly rehearse` and manually exercise the slides and interactions that matter. A
successful rehearsal covers only that exercised path.

Relative ESM imports, dynamic imports, data, WebAssembly, CSS, fonts, images, and local
workers can follow the selected package's relative resource graph. Absolute URLs,
root-relative URLs, bare module specifiers, and unexercised resources are not discovered
or cached automatically. Conventional relative workers from a cross-origin CDN entry do
not work in static publication; use a browser-ready package or supported package
configuration instead.

All code shares one browser realm, so distinct keys do not make incompatible singleton
or global packages safe together. Do not import `/vividly/vendor/**`, depend on
`window.marked`, `window.hljs`, or `window.jsyaml`, or embed a selected CDN URL in slide
code. See [Browser dependencies](./dependencies.md) for package evaluation, addition,
upgrades, conflict resolution, cache preparation, and removal.

## The smallest slide

A slide with no behavior needs no JavaScript body at all. Export `meta`, point at a
template, and declare how many steps it has:

```js
export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 4,
};
```

The runtime fetches the template and injects it for you. The slide advances through its
four steps, and the stepping is handled entirely in CSS — see [Steps](#steps).

## A slide with behavior

When a slide loads data or builds its own DOM, export a class extending `Slide`:

```js
import { Slide } from 'vividly/runtime/slide.js';

export const meta = {
  styles: ['./slide.css'],
};

export default class PhotoTour extends Slide {
  async preload() {
    const data = await this.ctx.load('./data/photos.yaml');
    this.heading = this.ctx.props.heading || data.heading;
    this.photos = data.photos;
    return { steps: this.photos.length };
  }

  mount(root) {
    root.innerHTML = `<h2>${esc(this.heading)}</h2>` + this.photos.map(frame).join('');
  }
}
```

`Slide` supplies a no-op default for every lifecycle method, so implement only what you
need. Note that this slide takes its step count from its *data* — add a photo to the YAML
and the slide gets a step longer, with no code change.

Import runtime modules through the `vividly/` prefix, as above. The runtime's
`index.html` declares an import map that resolves `vividly/` to the site's runtime
directory, so the same import works at any directory depth and when the site is
published under a subpath such as GitHub Pages' `/<repository>/`. A relative path such
as `../../vividly/runtime/slide.js` breaks when the slide moves to a different depth,
and a root-relative path such as `/vividly/runtime/slide.js` breaks under a subpath.

### Lifecycle

| Method | When | Notes |
|---|---|---|
| `constructor(ctx)` | at import | No I/O, no DOM. |
| `async preload()` | before the slide can be shown | Fetch data. Return `{ steps }`. No DOM yet. |
| `mount(root)` | when the slide nears the viewer | The root is **hidden**. Do not measure layout here. |
| `enter({ direction, step, restoring })` | becoming visible | Runs before the transition; `restoring` is true for history or thread restoration. |
| `setStep(n)` | on every step change, including arrival | Must be idempotent. |
| `settleStep()` | before repeated same-direction navigation | Finish custom motion synchronously. Return `true` only when motion was completed. |
| `exit({ direction })` | leaving | Runs before the outbound transition. |
| `unmount()` | moving out of the preload window | Release DOM-bound resources. |
| `dispose()` | teardown | Release everything else. |

`mount` and `enter` are separate because Vividly mounts slides *before* they are visible.
That is what makes preloading and cross-fade transitions possible — during a transition
both slides are mounted at once — and it is why `mount` must not assume it is visible.
Perform visibility-dependent work in `enter()`.

## Steps

A slide declares its step count and the runtime owns the index, calling `setStep(n)` with
an absolute value. Never treat a step change as "advance by one": `setStep` must put the
slide in the same state for a given `n` no matter how the viewer got there, since they
may have arrived from a deep link, from an expanded table-of-contents step card, or by
stepping backwards into your last step.

Most slides never implement `setStep` at all, because Vividly publishes the step to CSS
before calling it:

- `data-step` and `data-steps` attributes on the slide root, for selectors
- `--step` and `--steps` custom properties, for arithmetic

So a build is a stylesheet rule:

```css
:scope[data-step='0'] .stage-2 { opacity: 0; }
```

and advancing a whole filmstrip is one declaration:

```css
.strip { transform: translateX(calc(var(--step) * -100%)); }
```

Two built-in helpers cover the common cases. `.v-reveal` shows an element once the deck
reaches `--at` and keeps it visible; `.v-at` highlights an element on exactly that step:

```html
<li class="v-reveal" style="--at: 2">Appears on step 2</li>
```

Both work for any step count from a single rule, which is why Vividly pushes stepping
into CSS rather than JavaScript.

If your slide's length genuinely cannot be known ahead of time — streaming or
user-generated content — return `{ steps: 'dynamic' }` and implement
`advance(delta) -> boolean`, returning `false` to mean "I'm at my end, move on". This is
rarer than it looks: a richly interactive slide usually still has a fixed number of
authored points, and should say so.

### Settling step animations

Vividly treats finite CSS transitions caused by an incremental step change as part of
that step's build. If the presenter repeats navigation in the same direction while
those transitions are running, Vividly finishes them. When the repeated input arrives
within 500 milliseconds after the motion began, Vividly also continues navigation on
that input so rapid presses move through the deck. A later repeated input finishes the
motion but is consumed, allowing the presenter to reveal a long build's completed
state without advancing.

CSS-only slides get this behavior automatically. The built-in `.v-reveal` helper and a
filmstrip whose `transform` depends on `--step` need no JavaScript. Vividly tracks only
new finite `CSSTransition` instances produced by applying the step; it does not block
on pre-existing motion, CSS keyframe animations, or ambient and infinite animation.
The 500 millisecond rapid-input grace is an internal runtime policy rather than slide
configuration.

An opposite-direction input acts immediately, allowing the current transition to
reverse toward the newly selected absolute step. Destination navigation such as Home,
End, Page Up, Page Down, a direct link, or `ctx.navigate()` also acts immediately.
These operations still depend on `setStep()` being absolute: they may apply any step
without passing through the intervening sequence.

Implement `settleStep()` when the build uses a timer, canvas, CSS keyframes, or an
animation library the runtime cannot inspect. The method must synchronously render the
settled form of the current step and return `true` only when it changed unfinished
motion. Return `false` after that motion finishes naturally. A `true` result always
consumes the navigation input because the hook cannot report how much custom motion
remained.

After initial entry or destination navigation (including direct links, navigator
activation, Home/End, and history restoration), the next Right or Space also calls
`settleStep()`. Returning `true` finishes the arrival build without advancing; the
following input advances. Backward input remains immediate. Destination navigation
itself is never delayed, and destination-started CSS transitions are not automatically
tracked. Return `false` for completed builds and ambient motion.

This timer-driven reveal keeps `setStep()` absolute, cancels obsolete work when another
step is applied, and lets Vividly consume one repeated navigation input to finish the
current reveal:

```js
export default class TimedReveal extends Slide {
  mount(root) {
    this.output = root.querySelector('output');
    this.message = 'The complete explanation';
  }

  setStep(step) {
    this._stopTimer();
    if (step === 0) {
      this.output.textContent = '';
      return;
    }

    let length = 0;
    this.output.textContent = '';
    this.timer = setInterval(() => {
      length += 1;
      this.output.textContent = this.message.slice(0, length);
      if (length === this.message.length) this._stopTimer();
    }, 40);
  }

  settleStep() {
    if (this.timer === undefined) return false;
    this._stopTimer();
    this.output.textContent = this.message;
    return true;
  }

  unmount() {
    this._stopTimer();
  }

  _stopTimer() {
    if (this.timer !== undefined) clearInterval(this.timer);
    this.timer = undefined;
  }
}
```

Do not capture Right, Left, or Space merely to skip an animation. The orchestrator owns
the directional settling policy; the slide owns only how its custom motion reaches the
current step's end state.

## Context

`this.ctx` is your slide's only interface to the outside world.

| Member | Purpose |
|---|---|
| `ctx.props` | The `props` block from this slide's manifest entry |
| `ctx.load(path)` | Fetch and parse data from the data root — `.yaml`, `.json`, `.md`, or text |
| `ctx.asset(path)` | Resolve a path against the data root to a URL |
| `ctx.bus` | Presentation event bus: `emit(type, detail)` and `on(type, handler)` |
| `ctx.state` | `get(key)` / `set(key, value)`, persisted and namespaced to this slide |
| `ctx.address` | This slide instance's presentation-local address |
| `ctx.navigate(address)` | Jump to a presentation-local address in the current presentation |
| `ctx.navigator` | Resolved child sections when this slide is a structural navigator |
| `ctx.enterSection()` | Enter the child section selected by the current navigator step |
| `ctx.goUp()` | Move to the nearest owning structural navigator |
| `ctx.captureKeys(handler)` | Take raw keyboard input while visible — escape hatch only |
| `ctx.loadScript(path, { global })` | Load a non-ESM library |

Paths passed to `ctx.load` and `ctx.asset` resolve against your slide's **data root**,
which defaults to your own directory — so `./data/photos.yaml` means what you expect
regardless of where the presentation lives or whether it has been incorporated into a
larger deck. A manifest entry can point the data root elsewhere, which is how one module
serves several slides; see [Reusing a module](#reusing-a-module-with-different-data).

Subscriptions taken through `ctx.bus` are released for you at `unmount()`.

Keyboard input normally reaches your slide as `setStep`, not as key events. The
orchestrator owns a single listener so that nested chapters and overview views never
fight over input. Reach for `ctx.captureKeys` only when a slide genuinely needs raw
keys.

## Authoring a navigator

A navigator maps an interval of a fixed-step slide to direct child sections. Declare
the first choice step and the ordered child references in the manifest:

```yaml
- type: slide
  id: overview
  module: ../vividly/slides/section-overview.js
  navigator:
    choiceStartStep: 2
    sections:
      - ./visuals
      - ./runtime
```

`choiceStartStep` defaults to `0` and must be a nonnegative integer.
For `n` choices, the navigator interval is:

```text
choiceStep(i) = choiceStartStep + i
afterStep = choiceStartStep + n
```

The slide must declare enough fixed steps to include `afterStep`. It may use steps below
`choiceStartStep` for an introduction and steps above `afterStep` for a conclusion. Dynamic
slides cannot be navigators.

The runtime exposes the normalized interval through `ctx.navigator`:

```js
{
  choiceStartStep,
  afterStep,
  sections: [
    { address, title, step },
  ],
}
```

Use each section's explicit `step` when rendering active state; do not derive slide
steps from array indexes. `ctx.enterSection()` enters the child selected by the current
choice step and returns a promise resolving to `true` when navigation occurs.

Render one control per section with its zero-based logical index:

```html
<button data-vividly-navigator-choice="0">Visuals</button>
<button data-vividly-navigator-choice="1">Runtime</button>
```

Optional interactive completion UI uses `data-vividly-navigator-after`.
A rendered after control must have an accessible name.
Missing, duplicate, invalid, or out-of-range choice markers and duplicate after
markers are authoring errors.

For an ordinary trailing detent, render no prompt or control. Let `setStep()` remove the
active treatment from every choice, and let Right, Down, or Space continue structurally.
Do not write a presumed next slide or section title into navigator UI: Vividly derives
that destination from the manifest, so duplicated labels can become incorrect. Add an
after control only when the product explicitly requires pointer-accessible continuation.

Vividly owns pointer activation and roving focus for registered choice controls and any
rendered after control. It updates `tabindex`, `aria-current`, `aria-hidden`, and
`inert`, and moves focus for arrow selection, sequential arrivals, and child returns.
Fresh entry and reload focus the selected choice when focus is on the document body;
history and thread restoration do not force focus. A completion state without a
control leaves every navigator control untabbable. Hover should only subtly lighten
the background; use an accent border and stripe for selection and an outer ring for
keyboard focus. Hover does not change selection or focus. After UI may retain its layout
while inactive, but it must be visually hidden and noninteractive; the runtime removes
it from the tab order and accessibility tree.

There is no before-first detent. Left from the first choice reaches the preceding
introductory step or slide. Right or Down past the final choice skips after and continues
forward. Up selects a choice spatially above, or ascends to the enclosing navigator
when none exists; at the root top edge it does nothing. Completing the final child
returns to after; Left or Up selects the final choice from there.

Entry animation is motion within a selected state. Do not add a separate unselected
step or navigate automatically when it finishes. Use `enter()`'s direction and
`restoring` flag to distinguish forward entry from child returns and restoration.

Inside the interval, arrows select or cross the appropriate boundary without activating. Enter activates the
selected choice or a rendered after continuation. Space follows the complete forward
structural itinerary, including entering each selected child in turn. See
[Keyboard navigation](./keyboard.md) for the complete key
behavior.

## Styling

List your stylesheets in `meta.styles`. Vividly scopes them to your slide with native
`@scope`, so you write ordinary selectors and get isolation for free:

```css
.stage-label { color: var(--text-muted); }
```

That isolation applies to CSS selectors, not DOM identifiers. Slides use light DOM, and
IDs remain document-global. During transitions, repeated and neighboring slide
instances may coexist, so fixed IDs in a reusable template can collide. Fragment
references such as `url(#gradient)`, `<use href="#symbol">`, `aria-labelledby`, and
`for` may then silently resolve to an element owned by another slide.

Prefer classes or data attributes for internal lookup, and always query through the
slide root rather than `document`. When an SVG paint server or accessibility
relationship requires an ID, allocate it per mounted instance and update every
reference:

```js
let instanceSerial = 0;

mount(root) {
  const prefix = `network-map-${++instanceSerial}`;
  const gradient = root.querySelector('[data-gradient]');
  const line = root.querySelector('[data-line]');

  gradient.id = `${prefix}-gradient`;
  line.style.stroke = `url("#${gradient.id}")`;
}
```

Use the same pattern for SVG filters, masks, clip paths, markers, patterns, and
`<use>` targets, as well as `aria-labelledby`, `aria-describedby`, and label `for`
relationships. Include a module-specific name in the prefix so counters in unrelated
modules cannot collide.

Three rules worth knowing:

**Use theme tokens, not literal values.** Reference `--bg-*`, `--text-*`, `--accent`, and
`--spacing-*` rather than hard-coded colors and sizes. This is what lets a single theme
swap restyle every slide at once.

**Your rules win.** Global stylesheets — base, controls, theme — are wrapped in cascade
layers, and your slide's styles are not, so a plain class selector beats them. You never
need `!important` or specificity escalation to restyle a standard control.

**Slides cannot contribute global CSS.** Styling meant to apply across slides belongs in
the theme or the control library. That restriction is what keeps a slide directory
independently authorable.

Relative `url()` references resolve against your stylesheet, so
`background-image: url('./assets/hero.svg')` works.

## Using Vividly controls

Vividly registers its standard controls as custom elements before any slide mounts, so
you use one by writing its tag — in a template, in `innerHTML`, or via `createElement`:

```html
<vividly-markdown src="./notes.md" highlight></vividly-markdown>
```

| Element | Purpose |
|---|---|
| `<vividly-markdown>` | Markdown rendering with syntax highlighting |
| `<vividly-code>` | Code block with optional line emphasis |
| `<vividly-annotated-markdown>` | Markdown with a numbered-annotation nav pane |

See [Controls](./controls.md) — standard elements for Markdown, code, images, and
annotated documents.

Their styles live in a cascade layer, so you can restyle them from your slide's
stylesheet with plain selectors.

### Defining your own elements

A slide may define custom elements, but the registry is global and definitions cannot be
undone. Prefix the tag with your slide's directory name — `<token-anatomy-legend>` — and
call `customElements.define()` at module scope, never inside `mount()`. Do not guard with
`if (!customElements.get(name))`: that turns a name collision into a silently wrong
slide, where a loud error is what you want.

Most slides want plain DOM and classes. Anything genuinely reusable belongs in the
control library.

### Element or module?

Two things in Vividly are reusable, and they are reused in different ways:

- A **custom element** renders a region. You reuse it by writing its tag in any slide's
  markup, and several can appear on one slide.
- A **slide module** implements the slide contract — steps, lifecycle, `ctx`. You reuse
  it by naming it from several manifest entries.

When you want to make something reusable, ask whether two of them could appear on one
slide, or appear beside other content. If so, build an element. If it is inherently the
whole stage and owns the step axis, build a module — and usually a thin one wrapping an
element:

```js
mount(root) {
  root.innerHTML = '<vividly-image></vividly-image>';
  this.el = root.firstElementChild;
}

setStep(n) {
  this.el.src = this.ctx.asset(this.images[n]);
}
```

Keep steps out of your elements. An element that knows what a step is cannot be used
twice on a slide, or anywhere that is not a slide. Let it expose its state as properties
and let the module map the step axis onto them.

## Data, assets, and libraries

Keep data in `data/` and load it at runtime with `ctx.load`. Keeping content out of code
is what lets a slide's step count follow its data.

Keep images and media in `assets/` and resolve them with `ctx.asset`.

`data/` and `assets/` sit under the **data root**, so they travel with the slide's
content. `meta.styles` and `meta.template` resolve against the *module* instead. For a
self-contained slide the two are the same directory and the distinction never comes
up.

Use the project registry described in [Browser dependencies](#browser-dependencies) for
shared packages. Slide-local source files can still use ordinary relative imports, and
`ctx.loadScript()` remains available for genuinely slide-local classic scripts, but
those files are not project-registry dependencies or cache selections.

## Adding the slide to your presentation

A slide module is not a slide instance until a presentation manifest references it. The
manifest is conventionally kept under `site/presentations/`, and the presentation itself
must be registered in `site/catalog.yaml`:

```yaml
# site/presentations/product-tour.yaml
title: Product Tour
nodes:
  - type: section
    id: images
    title: Working With Images
    children:
      - type: slide
        id: photo-tour
        module: ./photo-tour/slide.js
        title: Photo Tour
        transition: fly
        props:
          heading: A Guided Photo Tour
```

`id` must be unique among its siblings, and the path of ids forms the slide's address:
`images/photo-tour`. That address is presentation-local: `ctx.address` and
`ctx.navigate()` use it without a presentation prefix. The browser route includes the
catalog presentation ID and step, for example `#/product-tour/images/photo-tour/3`.
Because addresses are built from ids rather than positions, inserting a slide never
breaks an existing link.

`props` is opaque data handed to your slide as `ctx.props` — configuration such as a
heading or a display mode.

`title` names this slide in both table-of-contents modes and the browser title bar. Like
`thumbnail`, it belongs to the manifest node rather than to the module: one shared
module can back many slides, and overview views read titles straight from the manifest
without loading any slide code. A node that omits `title` falls back to its `id`. Slide
modules declare no title.

`transition` names the animation for the boundary immediately before this slide and
overrides the presentation-wide default. Moving forward into the slide plays the
transition forward; moving backward out of it plays the same transition in reverse.
For a jump across multiple slides, the later endpoint supplies the transition.

The built-in transitions are `dissolve`, `fly`, `slide`, and `cut`. `slide` pushes the
outgoing slide offscreen as the incoming slide moves in, with no crossfade.

### Incorporating another presentation

A manifest can include another manifest by reference:

```yaml
- type: section
  id: gallery
  title: Gallery
  children:
    - type: slide
      id: overview
      module: ../slides/gallery/slide.js
      navigator:
        sections:
          - ./photo-tour
    - type: presentation
      id: photo-tour
      manifest: ./photo-tour.yaml
```

The included presentation's nodes become a section named by the incorporating `id`, so
its slides have addresses such as `gallery/photo-tour/intro`. A navigator can list it like
any child section; Up and finishing the section return to the navigator. Paths inside
the included manifest still resolve against that manifest. Its `theme` applies only when
it is opened on its own, so a look the slides depend on belongs in their stylesheets. A
presentation can be both incorporated and registered in the catalog, which keeps its
standalone route.

### Portable slide directories

Some slides are maintained in another repository and refreshed by replacing their
directories wholesale. Keep such a directory self-contained so it works at any depth in
any site:

- Import runtime modules through the `vividly/` prefix, for example
  `import { Slide } from 'vividly/runtime/slide.js'`.
- Import other modules only from inside the directory. Do not climb out with `../` to
  reach shared code; move code the slides need into the directory.
- Load shared packages, fonts, and stylesheets through `ctx.dependency()`, declared in
  the catalog, and resolve files with `ctx.load` and `ctx.asset`.
- Put styling the slides require in their own stylesheets rather than a presentation
  theme.
- Keep site-specific material, such as the manifest, introductions, and gallery images,
  outside the directory so a refresh does not overwrite it.
- Keep module filenames stable; the manifest refers to them by path.

## Thumbnails

The table of contents can show a still image for each slide in Outline and Grid modes.
Three different things get called "the thumbnail", and keeping them apart makes the
rest of this section much easier to follow:

- **The captured frame.** Your slide, mounted and advanced to one particular step,
  rendered exactly as a viewer would see it. This is the live DOM that Vividly
  photographs.
- **The image file.** A PNG written under `site/thumbnails/`, named from the slide's
  address. It is generated by `vividly thumbnails` and committed alongside your
  presentation, so a published site needs no build step to show overviews.
- **The `thumbnail:` manifest key.** Configuration that chooses *which step* gets
  captured. It holds no image, no path, and no dimensions.

A thumbnail belongs to a **manifest slide node**, not to a slide module. That is all
"ownership" means here: the node decides what the picture is of. The reason is shared
modules. One gallery module can back six slides with different `data` and `props`, and
therefore six genuinely different pictures — if the module owned the thumbnail, all six
would show the same image. Node ownership also keeps overview views manifest-only: they
read a generated index instead of importing every slide module just to discover image
metadata.

Slide modules therefore declare nothing about thumbnails. There is no `meta.thumbnail`.

By default Vividly captures a fixed-length slide at its **final step**, on the assumption
that the completed build is its most recognizable frame. Override that with a zero-based
step, using the same indexing as routes and `setStep()`:

```yaml
- type: slide
  id: token-anatomy
  module: ./token-anatomy/slide.js
  thumbnail:
    step: 2
```

A step outside the slide's range is a generation error. A dynamic slide is always captured
in its initial state and may not declare `thumbnail.step`, because it has no stable
indexed step axis. Vividly generates one image per slide, not one per step: overviews
represent slides, not their internal sequences.

Running `vividly thumbnails` renders each slide in a headless browser and records what it
wrote in `site/thumbnails/index.json`:

```json
{
  "version": 2,
  "presentations": {
    "product-tour": {
      "mechanics/diagram-build": {
        "path": "product-tour/mechanics/diagram-build.png",
        "step": 2
      }
    }
  }
}
```

Generated paths are never written back into a presentation manifest. Entries are first
grouped by presentation ID and then keyed by presentation-local address. Reusing an
address in another presentation therefore creates a separate thumbnail identity, just
as it creates separate persisted slide state and history. Capturing requires a headless
browser; see [Command Line](./cli.md) for `vividly install-browser`.

## Reusing a module with different data

When a module keeps no data of its own — a gallery, a markdown reader, an image slide —
the same module can serve any number of slides, each with its own content.

Every slide has a **data root**: the directory `ctx.load()` and `ctx.asset()` resolve
against. By default it is the module's own directory, which is why a self-contained slide
needs no extra configuration. A manifest entry can point it somewhere else with `data`:

```yaml
- type: slide
  id: photo-tour
  module: ./shared/gallery/slide.js    # borrowed code
  data: ./photo-tour/                  # this slide's data root
  props:
    heading: A Guided Photo Tour
```

```text
shared/gallery/
├── slide.js          serves any number of slides
└── slide.css
photo-tour/
├── photos.yaml       this slide's content — note there is no slide.js
└── assets/*.jpg
```

`ctx.load('./photos.yaml')` inside `gallery/slide.js` now reads from `photo-tour/`. The
module never learns which slide it is serving, which is the point.

Nothing in the runtime distinguishes a "generic" module from a one-off one. `module`
names code, `data` names a directory, and whether one module is named by a single entry
or by ten is your business. Keeping shared modules and slide data in separate folders is
a convention worth adopting, not a rule Vividly enforces.

Sharing also works across presentations. Each manifest reference creates a distinct
slide instance with its own presentation-local address, props, data root, persisted
state, history, and thumbnail, even when every instance imports the same module URL.

Files the *module* owns — its own icon, a vendored library — are not slide data and do
not move with the data root. Resolve those against the module itself:

```js
const icon = new URL('./icon.svg', import.meta.url);
```

### Props are configuration, not content

A heading, a flag, a theme token, a list of image paths — props. Prose, markdown, code
listings — files, loaded with `ctx.load`. The rule of thumb: **if it contains a newline,
it belongs in a file.**

Content in files gets syntax highlighting, preview, diffing and review; YAML block
scalars get none of those. And the presentation manifest is the one structural file
every slide author has to touch, so keeping payloads out of it is what stops two authors
colliding there.

## The slide interface

For reference, the shape of what a slide module exports:

```ts
interface SlideModule {
  meta?: SlideMeta;              // omitted when the module owns no styles or template
  default?: SlideClass;          // omitted for template-only slides
}

// The default export is a constructor, not an instance: the runtime calls
// `new Ctor(ctx)`, falling back to the base `Slide` class when it is absent.
interface SlideClass {
  new (ctx: SlideContext): Slide;
}

interface SlideMeta {
  styles?: string[];             // stylesheets, scoped to this slide
  template?: string;             // HTML injected at mount
  steps?: number;                // template-only slides declare length here
}

interface Slide {
  preload?(): Promise<{ steps: number | 'dynamic' } | void>;
  mount?(root: HTMLElement): void;
  enter?(info: { direction: 'forward' | 'backward'; step: number; restoring: boolean }): void;
  setStep?(step: number): void;
  settleStep?(): boolean;                // complete custom motion synchronously
  advance?(delta: number): boolean;      // 'dynamic' slides only
  exit?(info: { direction: 'forward' | 'back' }): void;
  unmount?(): void;
  dispose?(): void;
}

interface SlideContext {
  readonly address: string;      // this slide's address in the presentation
  readonly props: object;        // the `props` block from the manifest entry
  readonly moduleUrl: string;    // resolve code-owned files against this
  readonly dataUrl: string;      // the data root; `load` and `asset` resolve here

  asset(path: string): string;
  load(path: string): Promise<unknown>;
  loadScript(path: string, options?: { global?: string }): Promise<unknown>;

  navigate(address: string, step?: number): void;

  readonly bus: {
    emit(type: string, detail?: unknown): void;
    on(type: string, handler: (event: CustomEvent) => void): () => void;  // returns unsubscribe
  };

  readonly state: {
    get(key: string, fallback?: unknown): unknown;
    set(key: string, value: unknown): void;
  };

  // Non-null only when the manifest gives this slide a `navigator` block.
  readonly navigator: {
    choiceStartStep: number;
    afterStep: number;
    sections: ReadonlyArray<{ address: string; title: string; step: number }>;
  } | null;
  enterSection(): Promise<boolean>;
  goUp(): Promise<boolean>;

  captureKeys(handler: (event: KeyboardEvent) => boolean): void;
}
```

## Not yet settled

Two questions this document cannot answer yet:

- **Configuration schemas.** A slide has no way to describe the shape of its `props`, so
  Vividly cannot validate a manifest before running it, and cannot offer form-based
  editing of slide configuration. `meta.propsSchema` is the obvious place for this.
- **Slide-internal addressing.** You can link to step 3 of a slide, but not to "the
  explorer focused on record 4711". The address grammar reserves room for a slide to
  contribute a trailing segment, but it is unbuilt.

## See also

[Authoring slides](./authoring.md) — the task-oriented workflow, author
responsibilities, validation, and definition of done.

[Controls](./controls.md) — standard elements for Markdown, code, images, and
annotated documents.

[Browser dependencies](./dependencies.md) — package selection, maintenance, cache
preparation, and offline verification.

[Keyboard navigation](./keyboard.md) — how steps, navigators, and threads
respond to keys.

[Command Line](./cli.md) — provisioning the framework, running the dev server,
and generating thumbnails.
