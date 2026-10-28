# Keyboard navigation

Vividly treats the keyboard as a presentation-wide navigation device. The orchestrator
owns one document-level keyboard listener and decides whether a key belongs to the
current slide, the presentation, or an overview. Slides normally respond to navigation
through their step lifecycle rather than by listening for keyboard events themselves.

## Touch navigation

On touch-capable devices, including keyboard/touch hybrids, swipe left to continue
or right to go back through presentation states. Swipes include reveals within a
slide; they do not skip directly to another slide. On a navigator, forward swiping
enters the selected section like Space, rather than moving selection like Right
Arrow. Tap a section card to choose a different section.

A persistent **Previous** / **Next** bar below the slide offers the same traversal.
It reserves its own space rather than covering slide content and is absent from
the catalog, table of contents, and thumbnail captures. While navigation is pending
or a dialog/menu owns input, the bar is disabled and swipes are ignored, not queued.
After rendering is ready, swipes and buttons retain the animation-settling behavior
described below.

Use a deliberate horizontal movement of at least 48 CSS pixels within one second,
with horizontal displacement at least twice the vertical displacement. Start at
least 24 CSS pixels from the screen edges. Vertical gestures scroll content; swiping
up does not navigate. Pinch zoom and native browser-edge gestures remain available.
Presentation swipes are disabled while the page is pinch-zoomed.

Controls, links, editable content, and horizontal scrollers keep their own gestures.
The runtime reserves horizontal gestures only on content subtrees without those
exclusions. A mixed container's own background may therefore remain a native
surface; use its eligible content or the visible navigation buttons instead.
Scrolling, text selection, multi-touch, or cancellation by the browser aborts a swipe.

For a diagram, game, camera viewport, or custom control that owns dragging, mark its
interaction root:

```html
<div class="camera-viewport" data-vividly-touch-ignore></div>
```

This presence-only attribute excludes the element and its entire subtree from
presentation gestures without changing its own input handling or CSS. Even a value
of `"false"` excludes the subtree. Custom elements can put the attribute on their
host, and a slide can mark its whole root; the navigation bar remains available.
Pointer capture alone does not opt an interaction out. An interactive region still
declares its own browser gesture policy, such as the `touch-action` required for a
camera drag.

## Keyboard onboarding

Before a normal entry to the first slide, Vividly can show a runtime-owned activation
screen. It introduces movement, navigator selection, keyboard help, and the table of
contents without requiring the presentation's first slide to contain those instructions.
The runtime may preload and mount the first slide behind this screen, but it does not
enter the slide or begin its animations until onboarding is dismissed. The screen does
not appear on deep links, in captures, or when returning to an existing presentation
runtime. Most unmodified keys dismiss onboarding and are consumed; use the next key
to navigate the newly entered slide. Tab cycles between the screen's controls, and
Enter or Space activates the focused control. The activation screen fades for 300 milliseconds
before Vividly enters the slide and starts its animations.

**Keyboard shortcuts** is an expandable section, initially collapsed on compact
layouts (640 CSS pixels wide or less) and expanded on larger layouts. Click or tap
its heading, or focus it and press Enter or Space, to toggle the instructions without
starting the presentation. Your choice is retained while the screen is open, even
if you resize it. Touch instructions remain visible on touch-capable devices. This
layout does not detect whether a keyboard is attached; keyboard navigation works in
either state, and full help remains available with `?`.

Click or tap anywhere on the activation screen to start, or use **Start presentation**.
The dismissal click or tap is consumed rather than activating anything underneath.
Scrolling or swiping to read the hints does not dismiss them. The **Don't show these
tips again** checkbox and its label change only the preference, leaving the screen open.

With the default `keyboardHints: auto` manifest policy, **Don't show again** suppresses
the panel for every presentation provisioned by the same site in that browser. Open the
full keyboard help with `?` and select **Show navigation hints when presentations start**
to restore it. A manifest may instead use `keyboardHints: always` or
`keyboardHints: never`; those policies override the stored reader preference.

## Moving through a presentation

While a slide is visible, these keys move within it:

| Key | Action |
|---|---|
| Right | Next ordinary step, or move navigator selection right |
| Left | Previous ordinary step, or move navigator selection left |
| Down | Move navigator selection down |
| Up | Select a choice above, or ascend to the owning navigator |
| Space | Next state in the structural itinerary |
| Home (Fn + Left) | First step in slide |
| End (Fn + Right) | Last step in slide |
| Enter | Activate the selected navigator item |
| Escape | Open the table of contents |

Steps form one continuous route through the presentation. Advancing past an ordinary
slide's last step opens the next slide at step 0. Going back from step 0 opens the
previous ordinary slide at its last step. On a navigator slide, advancing enters the
highlighted section and returning from that section highlights the next one. Going
back follows those same states in reverse. The browser address changes with every move,
so the current slide and step can be bookmarked or shared.

For an external link that should land on the first reveal instead of a quiet step 0,
add `?vividly-auto-advance=1` before the hash, for example
`https://example.com/?vividly-auto-advance=1#/product-tour/intro/title-card`. On the
initial page load, Vividly advances once when the route is at step 0 and the slide
supports step 1. It removes the parameter and replaces the current history entry with
the resulting route, so Back returns to the previous page. Without the parameter,
presenters retain manual control; links to nonzero steps are not advanced. If keyboard
onboarding appears, the one-step advance happens after the reader dismisses it.

A navigator has one state per choice and an after-completion state; there is no empty
before-first state. Left and Right prefer another item in the same rendered row;
Up and Down prefer one in the same column. When no spatial neighbor exists, Left falls
back to the previous choice and Right or Down to the next choice in manifest order.
Up instead ascends to the enclosing navigator, selecting the choice for the section
being left. At the root top edge, Up does nothing. Selection does not wrap.

Left from the first choice reaches the preceding introductory step or slide.
Right or Down beyond the final choice skips the completion state and continues to the
first concluding step or beyond the navigator's owned sections. Forward entry selects
the first choice when it is step zero; reverse entry selects the final choice unless
the slide has authored concluding steps.

Enter activates the selected choice or a rendered continuation control. At an after
state without a continuation control, use Right, Down, or Space to continue. Space
remains the complete forward structural itinerary: it enters the selected section,
including the final choice, and advances from after. Completing the final section
returns to after with no choice selected; Left or Up brings the final choice into focus.
Outside the navigator interval, Right and Left traverse ordinary slide steps, Down has
no presentation action, and Up returns to the owning navigator when one exists.

Arrow selection and keyboard returns from child sections move actual keyboard focus
to the selected control. Direct links and reloads focus the selected choice when focus
is on the document body, without taking focus from unrelated controls. Browser history
and restored threads synchronize selection without forcing focus.

The opening animation runs within its first selected state on fresh entry, refresh,
and forward arrival; it does not require an extra keypress. Returning from a child or
restoring history does not replay it. Hover only subtly lightens a card's background;
selection retains its accent and keyboard focus its outer ring.

Navigation APIs use presentation-local addresses such as `intro/title-card`; the browser
route prefixes that address with the catalog or system presentation ID, for example
`#/product-tour/intro/title-card/2`. Keyboard navigation never crosses into a different
presentation. Use the catalog to choose a different presentation.

Browser Back and Forward revisit visible states chronologically, including structural
navigator transitions and switches between presentation threads.

Home and End apply to fixed-length slides and have no effect on a dynamic slide. On a
compact Mac keyboard, Fn+Left produces Home and Fn+Right produces End.

Vividly ignores presentation shortcuts when Command, Control, or Option/Alt is held.
This leaves modified browser and operating-system shortcuts available.

## Settling animations

Incremental navigation gives an animated step time to finish without letting rapid
input stack several builds on top of one another. If a step is still moving and the
presenter repeats navigation in the direction that selected it, Vividly completes the
motion. If the repeated input arrives more than 500 milliseconds after the motion
began, Vividly consumes that input:

```text
Right        select step 2 and start its build
Right        finish step 2; remain on step 2
Right        select step 3
```

When the repeated input arrives within 500 milliseconds after tracked CSS motion
began, Vividly finishes the motion and continues to the next state on the same input.
This lets rapid repeated presses traverse the deck. Custom motion completed by
`settleStep()` always consumes the input.

The same rule applies in reverse. If Left selects step 2 and starts a long reverse
transition, another Left finishes at step 2; the following Left continues to step 1.

An input in the opposite direction acts immediately. Left during a forward build
returns toward the preceding step, while Right during reverse motion returns toward
the following step. Vividly does not force motion to finish at a destination the
presenter has just rejected.

Inside a navigator, the runtime still owns all four arrow keys. It first finds the
spatial target, then applies the same directional settling rule. When settling consumes
an arrow, the current choice and keyboard focus do not move. Space is forward
structural traversal and settles before selecting or entering the next structural
state. Enter is explicit activation and acts immediately.

Home, End, Page Up, Page Down, overview selection, direct links, browser history, and
navigation APIs request a destination rather than the next incremental state. They act
immediately and never require an extra settling input.

Once at a destination, including a section entered with Enter or a click, Right or
Space can finish a custom build through the slide's `settleStep()` hook without
advancing. The following input continues. Left remains immediate on destination
arrival. Completed builds and ambient motion do not consume input; destination-started
CSS transitions are not automatically tracked for settling.

Vividly automatically recognizes finite CSS transitions started by a step. Slides with
timer-driven, canvas, keyframe, or library-managed builds implement `settleStep()`; see
[Settling step animations](./slides.md) in the slide
authoring guide. The rapid-input grace is an internal runtime policy, not slide
configuration. Ambient and infinite animation should never block navigation.

## Moving through the presentation tree

Page Up and Page Down skip between slides or whole sections. The current navigation
level controls the size of the jump:

| Key | Action |
|---|---|
| Page Down (Fn Down) | Next slide or section at the selected level |
| Page Up (Fn Up) | Previous slide or section at the selected level |
| `[` | Move the selected level outward |
| `]` | Move the selected level inward |

Navigation starts at slide level, where Page Up and Page Down move between adjacent
slides. Press `[` once to select the containing section; Page Up and Page Down now skip
whole sections. Press `[` again to select the next enclosing level. Press `]` to move
back toward individual slides.

Changing levels does not change the current slide. Vividly briefly displays a breadcrumb
HUD showing the selected level. The HUD also appears after Page Up or Page Down, and a
level key pressed at its boundary still reveals it.

The selected level remains active across structural jumps, making it possible to scan
several sections with repeated Page Up or Page Down presses. When the destination branch
is shallower than the selected level, Vividly narrows the level to the deepest one that
exists there. Opening the table of contents resets navigation to slide level, so choosing
a slide there starts a fresh traversal.

On a compact Mac keyboard, Fn+Up produces Page Up and Fn+Down produces Page Down.

## Keyboard help

Press `?` or select the subtle `?` button in the corner of the presentation to open a
shortcut summary. The button becomes fully visible when hovered or focused. The overlay
softly enters and leaves; any key or mouse click closes it.

## Switching presentations

Use the project catalog to open another presentation. The Threads button, menu, and
associated keyboard controls are temporarily unavailable.

Browser Back and Forward remain chronological: they revisit every visible route,
including routes in other presentations.

## Navigating overviews

The project catalog and presentation table of contents are overview views rather than
slides. The table of contents offers Outline and Grid display modes without changing
its route. In the catalog, use the arrow keys to move among visible destinations. In
Grid, Left and Right move through destinations in manifest order, while Up and Down
move to the nearest horizontally aligned card in the row immediately above or below.
Home and End focus the first and last destination.

Within the table of contents, press `g` for Grid, `o` for Outline, and `s` to expand
or collapse steps. In Outline, expanding or collapsing while thumbnails are hidden
sets **Show thumbnails** and expanded steps to true rather than toggling the retained
expansion state. These shortcuts do not change the URL or browser history. They have no
view or expansion effect in the catalog or while a slide is presented.

Outline uses vertical keys for slides and horizontal keys for their expanded steps.
Up and Down move to the previous or next slide, including when a step currently has
focus. Home and End focus the first and last slide. Right enters a slide's first
visible step and advances through its steps. Left reverses through those steps and
returns from the first step to its owning slide. Left and Right do not cross between
slides. Hidden or collapsed steps never participate in keyboard navigation.

In the catalog, Enter or pointer activation opens the focused presentation's table of
contents. In the table of contents, activating any canonical slide destination opens it at step
0, while activating an expanded step card opens that exact step. Moving focus alone
does not change the active presentation, slide, or step.

Escape from a slide opens its table of contents in the presentation's persisted mode,
focuses the active destination, and scrolls it into view. Escape from the table of
contents returns to the catalog and focuses the presentation just exited. On a cold
catalog load, Vividly focuses the most recently activated presentation when it is still
available, otherwise the first entry. Escape in the catalog has no navigation effect.
An open runtime dialog or menu consumes Escape before the overview hierarchy does.

Outline's icon-only, push-on/push-off **Show thumbnails** button reveals thumbnails and
enables expanded indexed step destinations within each slide. The icon-only
**Expand/collapse steps** control remains enabled while thumbnails are hidden and
sets both thumbnail visibility and expansion to true when activated. Expansion
replaces an indexed slide's canonical thumbnail with its complete step sequence. Slides
without indexed steps retain their canonical placeholder. Grid shows one card per
slide or, with expanded steps enabled, replaces
each card with that slide's complete indexed step sequence. The expansion preference
is shared by both modes. Outline or Grid mode, thumbnail visibility, and expansion are
persisted per presentation. Changing these controls does not change the URL or create
browser history.

## How slides receive navigation

A fixed-length slide declares its number of steps. Vividly owns the current zero-based
step and calls the slide's `setStep(n)` method with an absolute value. It also publishes
the same value through `data-step` and `--step`, allowing many slides to implement
keyboard-driven builds entirely in CSS.

This means a slide should not interpret `setStep()` as a relative keyboard command.
The same step can be reached through forward navigation, backward navigation, an
overview, or a deep link, and it must produce the same visual state each time.

See [Slides](./slides.md) for the fixed and dynamic step models.

## Capturing keys in an interactive slide

Most slides should leave keyboard handling to Vividly. A slide that genuinely needs raw
keyboard input can register a handler with `ctx.captureKeys()`:

```js
mount(root) {
  this.ctx.captureKeys((event) => {
    if (event.key !== 'r') return false;
    this.resetView();
    return true;
  });
}
```

The handler runs before presentation shortcuts while that slide is current. Return
`true` when the slide consumed the event; Vividly then calls `preventDefault()` and
stops processing it. Return `false` for every other key so normal presentation
navigation continues.

Capture only the smallest set of keys the interaction requires. In particular, avoid
capturing Left, Right, Space, Page Up, Page Down, Home, End, `[`, `]`, or Escape unless
replacing their presentation behavior is essential to the slide. Modified key
combinations are ignored before a slide's capture handler runs.

Do not add a separate `document` keyboard listener in a slide or control. Competing
global listeners make navigation dependent on load order and can cause a single key to
affect both the slide and the presentation. A reusable control should expose methods or
events; its slide module decides whether those interactions belong on the presentation
step axis or require captured keys.

## See also

[Authoring slides](./authoring.md) — the complete slide workflow and validation
checklist.

[Slides](./slides.md) — slide steps, lifecycle, and the context API.

[Controls](./controls.md) — the boundary between reusable controls and slide-level
navigation.