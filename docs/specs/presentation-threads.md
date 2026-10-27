# Presentation Threads and Browser History

Status: proposed

## 1. Purpose

Vividly supports two independent kinds of movement:

- **structural navigation** traverses one presentation's document tree
- **thread switching** suspends one train of thought and continues another

The primary product case is moving between independent presentations without losing
the route where each train of thought stopped. A presenter can open another catalog
presentation as a new thread, traverse its hierarchy, and later select the original
thread at the route where it was left. Arbitrary manifest URLs cannot become thread
roots.

Neither operation repurposes browser Back as an application-level return command.
Browser history remains a chronological record of visible navigation. Threads remember
where independent trains of thought most recently stopped.

This model replaces retained presentation streams and callable-section continuations.
It does not define a general-purpose overlay, dialog, or dismissible sidebar mechanism.
Those temporary UI surfaces may use their own history integration without becoming
presentation threads.

## 2. Principles

The runtime follows these invariants:

1. Every successful application navigation that changes the visible presentation state
   appends one browser-history entry.
2. Browser Back and Forward only traverse existing entries. Vividly never implements an
   application command by consuming one or more unknown browser-history entries.
3. A browser-history entry identifies the presentation thread and route that were
   visible at that point in time.
4. A thread records only enough information to reload its latest route. It does not
   retain mounted slides, component state, pending continuations, or a private history
   stack.
5. At most one presentation runtime is active after a thread switch settles.
6. Structural hierarchy, chronological history, and thread identity remain separate
   concepts.
7. Every thread root is identified by a catalog presentation ID, never by a manifest
  URL.

These rules make every application operation undoable as visible navigation with
browser Back and redoable with browser Forward. Revisited slides are reconstructed;
application side effects are not transactionally undone.

## 3. Structural Navigation

A presentation is a tree of sections whose leaves are slides. Structural navigation
operates within the active thread's presentation:

- next or previous step moves along the step axis; crossing a slide boundary enters the
  adjacent slide unless a navigator-owned section boundary applies
- next or previous at the selected structural level moves between sibling subtrees
- entering a focused section navigates from its owning navigator to that section's
  structural entry point
- moving forward beyond that section revisits the owning navigator at the next choice
  step or its after step
- moving backward before that section revisits the owning navigator at the step that
  entered it
- moving up explicitly navigates to the nearest enclosing structural navigator
- selecting a table-of-contents destination navigates directly to that destination

Application direction and browser-history direction are distinct. Previous-step,
previous-subtree, and up operations move backward through document structure but still
append browser-history entries because they are new user actions.

### 3.1 Navigator ownership

A **navigator** is a slide that presents an ordered set of child sections belonging to
its containing section. A navigator occupies one contiguous interval within an
otherwise ordinary fixed-step slide. A slide declares the role, the first choice step,
and its sections with `navigator`:

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

Each reference resolves relative to the navigator slide's containing section and must
identify a nonempty direct child section. Entries must be unique. A direct child section
may belong to at most one navigator in its parent. Child sections omitted from every
navigator use ordinary adjacent-slide traversal.

`choiceStartStep` is a nonnegative integer and defaults to zero.
For `n` sections, the navigator interval is:

```text
choiceStep(i) = choiceStartStep + i
afterStep = choiceStartStep + n
```

`afterStep` is the addressable completion state immediately after the final choice.
There is no empty before-first state. Steps below `choiceStartStep`
and above `afterStep` are ordinary introductory and concluding slide steps. The slide
must declare a fixed step count greater than `afterStep`; `dynamic`, a noninteger
`choiceStartStep`, a negative value, and a fixed count that does not contain the
complete interval are authoring errors.

Manifest array position defines logical choice order, not slide step. Each normalized
section entry carries its explicit choice step. For a mapping from navigator route `N`
at choice step `s` to child section `C`:

1. Space or Enter at `N/s` navigates to the first structural state of `C`.
2. Sequential forward navigation within `C` follows its slides and nested navigator
   mappings.
3. Forward navigation beyond the final leaf of `C` navigates to the next choice step,
   or to `afterStep` when `C` is the final choice.
4. Backward navigation before the first leaf of `C` navigates to `N/s`.
5. `ctx.goUp()` from anywhere in `C` navigates to `N/s`.

Left from the first choice reaches the preceding introductory step or crosses the
slide's backward structural boundary. Right or Down past the final choice skips the
completion state and reaches the first concluding step or crosses the forward boundary.
Completing the final child returns to `afterStep`, with no choice selected. Left or Up
from after selects the final choice; Right, Down, or Space continues forward.

Forward arrival selects the first choice when it is step zero. Backward sequential
arrival that would land on after selects the final choice instead. Authored introductory
and concluding steps are preserved. Direct entry, reload, browser history, the table of
contents, thread rehydration, and child completion keep their explicit steps.

An entry animation is transient motion within the selected state, not a separate
navigation step. The documentation opening animates on fresh entry, refresh of its
first choice, and forward arrival from the preceding slide. Returning from a child or
restoring browser history or a thread does not replay it. Completion of animation
does not change the route or append history; reduced motion preserves the same selection.

Crossing the after state from a navigator whose containing section is itself
navigator-owned revisits the parent navigator at the choice after that section, or at
the parent's after state when it was the final choice. Otherwise it continues after the
containing section in ordinary document order. Nested navigators apply the same rules
recursively.

For a navigator at the presentation root, forward movement from after continues to the
first root slide after its final owned section. Backward movement from that slide
revisits the root navigator at its final choice, or at its final concluding step when
one exists. If no slide follows the final owned
section, forward movement has no effect.

The runtime exposes resolved addresses, section titles, and explicit choice steps
through a narrow navigator-specific slide context. The managed overview uses that data
as its source of destination order and labels; authors do not duplicate structural
mapping or step arithmetic in component-local props.

For a navigator slide, `SlideContext` exposes immutable normalized metadata and a
structural entry operation:

```js
ctx.navigator // {
              //   choiceStartStep,
              //   afterStep,
              //   sections: [{ address, title, step }],
              // }
await ctx.enterSection()
```

`enterSection()` enters the section mapped to the navigator's current step and resolves
to `true` after navigation settles. It resolves to `false` from the after
state, or an ordinary step outside the navigator interval. It is an authoring error to
call it from a slide without `navigator.sections`.

Every slide context also exposes:

```js
await ctx.goUp()
```

`goUp()` finds the nearest enclosing section with an owning navigator mapping,
navigates to that navigator's explicit choice step, and resolves to `true` after
navigation settles. It resolves to `false` when no enclosing owner exists. Neither
operation accepts or returns a temporal caller identity.

Navigator ownership is static presentation structure, not a record of a temporal
invocation. The mapping is sufficient to compute boundary destinations after direct
entry, reload, or thread rehydration; the runtime does not need to remember which
earlier browser entry initiated traversal. A section without an owning navigator uses
ordinary adjacent-slide boundary behavior.

The navigator mapping lives in normalized manifest data and is never inferred from
component-local state.

#### Navigator controls and focus

A navigator slide renders exactly one choice control for each normalized section and
marks it with its zero-based logical choice index:

```html
<button data-vividly-navigator-choice="0">Visuals</button>
<button data-vividly-navigator-choice="1">Runtime</button>
```

Missing, duplicate, noninteger, or out-of-range choice markers are authoring errors.
Slides may mark optional interactive completion UI with
`data-vividly-navigator-after`. At most one may be rendered.
A rendered after control must have an accessible name and
represents forward continuation from `afterStep`.

An ordinary after detent renders no prompt or control. It removes the current treatment
from every choice, and Right, Down, or Space performs structural continuation. Authors
must not duplicate the expected next route or title in slide copy because the runtime
derives that destination from presentation structure and the copy can become stale.
Use an after control only when the product explicitly requires a pointer-accessible
continuation action; omission is the default.

The runtime owns roving focus among the choice controls and any rendered after control.
The control for the active choice or rendered after state has `tabindex="0"` and all
other navigator controls have `tabindex="-1"`. At a boundary without a rendered control,
all registered navigator controls have `tabindex="-1"`.
Keyboard selection, sequential arrival, child completion, backward child-boundary
crossing, and Up returns move DOM focus to the selected control without scrolling.
Fresh entry and reload focus the selected choice when focus is on the document body;
they do not steal focus from unrelated controls. Browser Back or Forward and thread
rehydration restore logical selection and tab stops without forcing focus.

Inactive after UI may remain in layout but must not be visible, pointer
interactive, tabbable, or present in the accessibility tree. Active boundary UI
restores its accessibility state and visible focus treatment. Hover, DOM focus, and
the active structural step must remain distinguishable. Hover only subtly lightens
the background; it does not add the selection accent or move the card. Selection uses
a persistent accent border and inset stripe; keyboard focus adds a clear outer ring.
Hover does not change selection or focus, and its treatment composes with both.

#### Navigator input

Inside the navigator interval, all four arrow keys move selection without entering a
child section. Left and Right prefer a rendered choice in the corresponding row; Up and
Down prefer a rendered choice in the corresponding column. The runtime derives rows
and columns from current element geometry so responsive layout needs no manifest
topology. Row candidates have overlapping vertical spans; column candidates have
overlapping horizontal spans. Among candidates, the runtime minimizes primary-axis
distance, then cross-axis distance, then logical order. If no spatial neighbor exists,
Left falls back one choice backward and Right or Down one choice forward in manifest
order. Up instead ascends to the nearest enclosing navigator, with no sideways fallback.
At a root navigator's top edge, Up has no effect. Selection does not wrap.
From after, Left or Up selects the final choice; Right or Down continues forward.

Enter activates the selected choice or a rendered after continuation. It has no
presentation action at an after detent without a control or on an ordinary
navigator-slide step. Space is the forward structural itinerary: it advances ordinary
steps, enters every selected child including the final choice, and advances
from after. Arrow selection does not wrap.

Outside the navigator interval, ordinary slide input applies: Right advances, Left
reverses, Up invokes `ctx.goUp()`, and Down has no presentation action. Home and End
select the first and last step of the complete fixed-length slide, including ordinary
steps outside the interval. Page Up, Page Down, and structural-level selection retain
their ordinary presentation-wide meanings.

### 3.2 History behavior

Structural entry, automatic boundary revisit, and explicit Up are application
navigations. Each appends a browser-history entry. For example:

```text
TOC/1 -> section-a/slide-1 -> section-a/slide-2 -> TOC/2
```

Browser Back then revisits the second slide, the first slide, and `TOC/1` in order.
Structural navigation does not create promises, pin navigator slides, preserve their
component-local state, or maintain a runtime call stack. Revisited navigators are
rendered from their route and step.

### 3.3 Structural examples

Completing two sibling sections produces:

```text
overview/0
  -> visuals/dunes
  -> overview/1
  -> runtime/build
  -> overview/2
```

Here steps zero and one are choices, and step two is after. With
`runtime/build` currently visible, Previous before the section boundary or Up navigates
to `overview/1`. Browser Back from that new entry revisits `runtime/build`.

Nested ownership composes without temporal state:

```text
book-overview/0
  -> chapter/overview/0
  -> chapter/topic-a
  -> chapter/overview/1
  -> chapter/topic-b
  -> chapter/overview/2
  -> book-overview/1
```

Directly loading `chapter/topic-b` does not synthesize the preceding routes. Its static
owner is nevertheless `chapter/overview/1`, so Up or Previous at its backward boundary
navigates there, while Next at its forward boundary navigates to
`chapter/overview/2`, the nested navigator's after state. A second Up from a top-row
choice returns directly to `book-overview/0`.

## 4. Presentation Threads

A **presentation thread** is an anonymous, lightweight bookmark for one train of
thought. A thread descriptor contains:

```js
{
  id,
  presentationId,
  latestRoute,
  lastActivatedAt,
}
```

`presentationId` is a stable ID registered by the project catalog. `latestRoute` is
presentation-local and identifies a TOC or slide address and step; the ID-prefixed URL
is derived from the two fields. It does not include table-of-contents display mode,
thumbnail or expansion preferences, transient slide state, or structural navigation
depth. Rehydration resolves the ID to its manifest, restores the route, reads the
presentation's current durable overview preferences, and applies the normal default
navigation depth for that location. Static navigator ownership remains available after
rehydration because it is part of the presentation manifest rather than thread state.

Every author-owned root presentation must be registered in `site/catalog.yaml`.
A manifest without a catalog ID may be incorporated into another manifest, but it
cannot be a thread root. Moving a registered manifest therefore does not change thread
or durable-state identity.

Several threads may refer to the same presentation and route. Thread identity expresses
independent continuity of thought, not content identity.

A thread has no private navigation stack and no retained presentation session. The
browser's history is the only chronological navigation stack.

### 4.1 Create and select

Creating a thread:

1. records the active thread's current route as its latest route
2. allocates an opaque page-local thread ID and descriptor
3. resolves the target presentation ID and loads its manifest and requested route as a
  fresh presentation runtime
4. appends a browser-history entry for the new thread and visible route
5. makes the new thread most recently active

Selecting an existing thread follows the same navigation rule: it records the current
thread's route, loads the selected thread's latest route, appends a browser-history
entry, and updates recency.

The active descriptor's `latestRoute` is captured whenever its presentation is left:
creating or selecting another thread, or opening the project catalog. Ordinary
navigation is already represented by the visible URL; implementations may mirror it
into the active descriptor eagerly, but switching behavior cannot depend on that
optimization.

Thread selection is not return. Selecting an earlier thread does not consume history or
close the thread being left.

### 4.2 Suspension and rehydration

Switching away from a thread tears down its presentation resources. Mounted slide DOM,
component instances, listeners, timers, observers, media state, and other runtime-owned
resources are disposed through the ordinary presentation lifecycle.

Switching back rehydrates the thread as if its manifest and route had been loaded
fresh. The route and step are restored. Transient state resets, including form values,
focus, media position, animation progress, pan and zoom, and component-local data not
represented by the route.

Rehydrating a navigator route restores its choice, after, or ordinary slide
step exactly. The runtime synchronizes active-choice styling, boundary visibility, and
roving tab stops from that step, but does not restore or force the prior DOM focus.

The existing `ctx.state` store is presentation-wide durable state, not a thread
snapshot. Rehydrating a thread reads the same persisted state that a fresh load of that
presentation would read. Two threads for the same presentation therefore do not receive
independent `ctx.state` namespaces. Authors must not put transient controls such as pan,
zoom, focus, or media position in `ctx.state` when those controls are expected to reset
on rehydration.

The runtime may load the destination offscreen and keep the source visible until the
destination is render-ready. After a successful handoff, it disposes the source. This
brief overlap is an implementation detail and does not make either thread a retained
live session.

Route-only thread restoration is the baseline authoring contract. Slides require no
thread suspension or state-serialization lifecycle. A future facility may add
thread-local durable state, but no such facility or compatibility guarantee is
specified here.

### 4.3 Lifetime and presentation

Thread descriptors remain available for the lifetime of the loaded page. The runtime
does not infer descriptor reachability by inspecting browser history, because the
History API provides no reliable enumeration of the complete stack.

The initial model has no close or delete operation. Page unload discards all thread
descriptors. A later close operation must define deterministic behavior for historical
entries before it is added.

A switcher presents threads in most-recently-used order. Threads need no authored names;
the UI may derive labels from presentation, section, and slide titles. The switcher may
show only the most recent entries without deleting hidden descriptors.

### 4.4 Runtime API

The orchestrator exposes:

```js
const threadId = await presentation.createThread(presentationId, { route })
await presentation.selectThread(threadId)
presentation.threads
```

`createThread(presentationId, { route })` resolves `presentationId` through the project
catalog, creates a descriptor, and resolves to its opaque ID after its initial route is
render-ready. Omitting `route` opens the target presentation's TOC. Presentation-local
routes have no leading slash: `''` is the TOC, `intro/title-card` is step zero, and
`intro/title-card/2` is step two. `~sorter` is not a compatibility route. An unknown ID,
manifest load failure, or invalid route rejects and leaves the source thread active
without creating a successful history entry. The API does not accept manifest URLs.

`selectThread()` selects a known descriptor and resolves after its latest route is
render-ready. An unknown ID rejects. Selecting the already active thread without a
visible route change is a no-op and creates no history entry.

`threads` is a read-only snapshot ordered by descending `lastActivatedAt`. Each item
contains `id`, `presentationId`, `latestRoute`, `lastActivatedAt`, and derived presentation
and route titles when available. Mutating the returned array or its items cannot mutate
the registry.

For example, a presenter can leave a product tour for an architecture presentation and
later continue the original train of thought:

```js
const originalThreadId = presentation.threads[0].id
await presentation.createThread('architecture', {
  route: 'runtime/composition',
})
// Navigate through the architecture presentation.
await presentation.selectThread(originalThreadId)
```

Selecting the original thread appends its latest route. Browser Back revisits the
architecture route that immediately preceded the selection; Forward revisits the
original route again.

### 4.5 Project catalog

The project catalog at `#/` is outside every presentation thread. Navigating there
records the active thread's latest route, tears down its runtime, and appends a history
entry with no `threadId`. Existing descriptors remain available. Selecting a catalog
entry creates a fresh thread for that presentation at its TOC; selecting an existing
thread remains a separate thread-switcher operation.

The catalog lists author-owned entries in catalog order.

## 5. Browser History

Each history entry contains opaque coordination metadata:

```js
{
  vividly: {
    pageId,
    threadId,
  },
}
```

The URL hash contains the visible presentation ID and structural route, including its
step. The page-local thread registry maps `threadId` to its presentation ID and latest
presentation-local route. History metadata does not serialize manifest URLs, component
state, or a thread collection. A project-catalog history entry has this page's `pageId`
and a null `threadId`.

### 5.1 Application navigation

Every successful application-authored visible navigation uses `history.pushState`,
including:

- next or previous step or slide
- next or previous at a selected structural level
- enter section, automatic navigator revisit, or move up
- TOC or direct runtime destination selection
- create a thread
- select a thread
- enter the project catalog
- select a catalog presentation

Repeated navigation to the same route may be a no-op when it produces no visible state
change. Internal writes that only stamp missing metadata or settle the URL after loading
may use `replaceState`; they must not collapse a user-visible navigation operation.

A new application navigation after Browser Back naturally truncates the browser's
forward history according to standard browser behavior.

### 5.2 Browser traversal

On `popstate`, the runtime reads the destination entry before deciding what to display:

- if it identifies the active thread, route that thread to the entry's URL
- if it identifies another known thread, tear down the active runtime and rehydrate the
  identified thread at the entry's URL
- if it identifies this page's project-catalog entry, tear down the active runtime and
  render the catalog without selecting a thread
- if it has no valid marker for this page instance, resolve the ID-prefixed URL as a
  fresh page load (§5.3)

History traversal never appends or consumes another history entry. It restores the
entry selected by the browser.

For example, given:

```text
T1:A -> T1:B -> T2:X -> T2:Y -> T1:C
```

Back visits `T2:Y`, `T2:X`, `T1:B`, and `T1:A` in order, switching threads whenever the
destination entry's identity changes. Forward reverses the same visible sequence.

A thread selected through historical traversal becomes the active and most-recently-used
thread. Its restored route becomes its latest route.

### 5.3 Reload and sharing

Thread identities are page-local and are not shareable. On reload, the runtime ignores
stale page and thread markers. `#/` starts at the project catalog with no active thread.
An ID-prefixed route resolves through the catalog and starts one
fresh root thread for that presentation at the visible local route. Unknown presentation
IDs and invalid local routes follow the ordinary invalid-route error behavior. Other
thread descriptors do not survive reload.

A copied ID-prefixed URL therefore shares presentation location, not thread identity or
transient state. Copying `#/` shares the project catalog.

## 6. UI and Input Semantics

The presentation UI keeps structural and temporal commands visibly distinct:

- outside a navigator interval, Right and Left advance and reverse ordinary slide
  steps; inside one, all four arrows move spatial navigator selection
- Space advances the complete forward structural itinerary, including navigator
  waypoints and child sections
- Page Up and Page Down navigate at the selected structural level
- Enter activates an active navigator choice or rendered after continuation
- Up Arrow calls `ctx.goUp()` only outside a navigator interval
- a thread command creates or selects another thread

Browser Back and Forward remain browser commands and are not documented as structural
up, thread return, or aside dismissal.

A thread switcher lists the active thread and a bounded number of recent threads in
most-recently-used order. Hiding older threads from this list does not destroy them or
make their history entries unrestorable.

## 7. Relationship to Earlier Models

This contract supersedes two earlier runtime abstractions:

- A retained **presentation stream** kept mounted sessions and compressed all auxiliary
  navigation into one browser-history entry so Back acted as return.
- A **section call** retained a live Promise continuation, pinned its caller, bounded
  navigation, and also used Back as return.

Those behaviors model temporary modal excursions rather than chronological presentation
navigation. They are not part of presentation threads or structural navigation.

The following implementation concepts remain independently useful:

- normalized section metadata and subordinate-section resolution for structural entry
- static navigator ownership and boundary mapping derived from the document tree
- one orchestrator owning the stage, keyboard, transitions, and history integration
- opaque page-local identity in `history.state`
- deterministic disposal and render-readiness during root-presentation handoff

Call-frame registries, caller pins, completion promises, call-boundary confinement,
retained session layers, exact component-state resume, and history-consuming return are
not required by this contract.

## 8. Required Behavior

The implementation must cover at least these cases:

| Action | Required result |
|---|---|
| Navigate through several slides | Each visible route is a separate chronological history entry. |
| Navigate structurally backward | Append a new entry for the structurally earlier destination. |
| Enter a child section | Append its structural entry route without creating a continuation. |
| Advance beyond a navigator-owned child section | Append the owning navigator route at the next choice step or its after step. |
| Reverse before a navigator-owned child section | Append the owning navigator route at that child's explicit choice step. |
| Move up | Append the owning navigator route at that child's explicit choice step. |
| Enter a nested navigator | Apply the same ownership and boundary rules recursively. |
| Enter a child route directly or after rehydration | Derive later boundary destinations from static navigator ownership. |
| Restore a navigator route | Restore its exact ordinary, choice, or after step without forcing DOM focus. |
| Open the project catalog | Record the active latest route, dispose its runtime, and append a threadless catalog entry. |
| Select a catalog presentation | Create a fresh thread at that presentation's TOC. |
| Create a thread by presentation ID | Resolve its registered target and append an entry carrying its new identity. |
| Create a thread for an unknown ID or manifest URL | Reject without changing the active thread or history. |
| Select an existing thread | Rehydrate its latest route and append a new entry. |
| Back across a thread boundary | Rehydrate the thread and route named by the destination entry. |
| Forward across a thread boundary | Rehydrate the destination entry without creating a new thread. |
| Switch away and back | Restore route and step; reset transient component state. |
| Reload `#/` | Show the catalog with no active thread and discard stale identities. |
| Reload an ID-prefixed route | Start one fresh thread for that registered presentation and discard stale identities. |
| Copy a URL | Share the presentation ID and structural route, never the thread collection. |

## 9. Implementation Baseline

The new runtime should begin before retained stream sessions and section-call frames were
implemented. Existing commits may be recovered selectively when their behavior remains
compatible:

- documentation content and standalone documentation presentation
- normalized section indexing and validation that support structural entry
- managed overview UI after replacing call/return behavior with structural navigation

Retained-session lifecycle, stream-stack history policy, call continuations, caller
pinning, and call-marker reconciliation should not be carried forward merely to preserve
implementation history. They encode contracts superseded by this specification.
