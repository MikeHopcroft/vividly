# Touch Navigation

Status: accepted interaction contract, 2026-10-21. Horizontal navigation and
Previous/Next controls are implemented in chunk 2; hierarchy navigation and its
grip remain pending chunk 3. Physical-device validation remains pending chunk 4.

This specification defines touch input and its visible alternatives. Structural
destinations and browser history remain governed by
[Presentation Threads and Browser History](presentation-threads.md); step motion
and settling remain governed by
[Presentation Orchestration](presentation-orchestration.md#step-animation-settling).
The implementation sequence and device-validation work are tracked in the
[mobile touch navigation plan](../plans/mobile-touch-navigation.md).

## 1. Scope

The runtime owns one presentation-wide touch recognizer. Slides do not install
competing document-level gesture listeners. The recognizer invokes navigation
operations directly, without synthesizing keyboard events or invoking
`ctx.captureKeys()` handlers.

Touch navigation traverses states, including reveals, rather than skipping whole
slides. It does not cross presentation roots or repurpose browser Back as Up.
Mouse dragging, pen input, keyboard navigation, responsive slide authoring, and
mobile fullscreen are outside this feature's scope.

## 2. Commands and destinations

| Input | Command |
| --- | --- |
| Swipe left on an eligible slide surface | Next structural state |
| Swipe right on an eligible slide surface | Previous structural state |
| Swipe up starting on the navigation grip | Up / Contents |
| Previous button | Previous structural state |
| Next button | Next structural state |
| Up / Contents button | Up / Contents |
| Tap a navigator choice | Existing explicit section activation |

Next follows Space's forward itinerary, including entering the selected navigator
section and returning through navigator completion states. Previous follows the
corresponding reverse structural itinerary, not spatial navigator selection.
Neither command changes the selected PageUp/PageDown navigation depth.

Next and Previous are incremental actions. They use existing directional motion
settling, including the 500 millisecond CSS completion grace and custom
`settleStep()` behavior. Receipt time is the accepted release or button activation,
not pointer-down time. One accepted gesture issues at most one command; settling
can consume that command without changing the route.

Up / Contents is a destination action:

1. If the current slide has an owning navigator, navigate to its nearest owner at
   the existing explicit child-return choice.
2. Otherwise open the current presentation's TOC, preserving its display mode,
   selecting the current destination, and resetting structural jump depth as for
   existing TOC entry.

This command applies even when the current slide is itself a navigator. It does
not use Up Arrow's spatial selection or after-step behavior. It never navigates
from TOC to catalog because presentation gestures and this bar are absent there.

Changed visible states create the same history entries as existing navigation.
Rejected gestures, settling-only actions, and boundary no-ops create none.
At an itinerary boundary, stay at the current state without wrapping or switching
presentations.

## 3. Eligible input and surfaces

Only a single primary touch pointer can start recognition. The starting target
must be in the visible active slide, or on the runtime-owned upward-swipe grip.
Hidden/preloaded slides, the TOC, catalog, and other runtime chrome are ineligible.
The grip recognizes only upward movement; horizontal or downward movement there
does not navigate. The bar's buttons accept ordinary activation, not swipes.

Determine eligibility at pointer down using the composed event path and containing
ancestors through the active slide boundary. Exclude gestures starting in:

- native controls and activation targets, including links, buttons, form controls,
  media controls, summaries, and draggable content;
- editable content and accessible interactive widgets, including custom controls
  with interactive ARIA roles;
- horizontal scrolling regions whose overflow permits native horizontal scrolling
  and whose content exceeds their client width, including their descendants;
- any explicitly interaction-owned subtree defined below.

Reserve horizontal browser gestures only on subtrees that contain no exclusions.
An ancestor containing an excluded region keeps its native browser policy: its own
background is not a horizontal-swipe surface, while safe child subtrees remain
eligible. The visible buttons provide navigation when interaction-owned regions
or mixed backgrounds occupy the available surface. This preserves descendant
scrolling without a blanket ancestor policy or changes to authored text markup.

Do not turn a gesture that started in an excluded region into presentation
navigation when its pointer later moves outside that region. Conversely, reaching
an excluded region after an eligible start does not grant that region a new tap.
Nested vertical scrolling remains native. Actual scrolling or text selection
that starts during recognition cancels presentation recognition.

### 3.1 Author-owned interaction regions

`data-vividly-touch-ignore` is a presence-only attribute. On an element, it excludes
that element and its entire subtree from presentation gesture recognition.
Its value is not parsed; `data-vividly-touch-ignore="false"` still excludes.
It does not disable the region's own pointer handlers, scrolling, clicks, or keys.
An inner element cannot re-enable presentation gestures inside an excluded parent.

Authors may place it on a custom-element host, interaction root, or entire slide
root. Closed-shadow interactions must mark their host; runtime recognition must
not depend on access to private shadow internals. Visible runtime navigation
remains available even when the entire slide is excluded.

For example, an interaction can declare:

```html
<div class="camera-viewport" data-vividly-touch-ignore></div>
```

The tic-tac-toe camera viewport must use this exclusion when the feature is
implemented. Its current pointer capture and `touch-action: none` own camera
panning, but do not by themselves prevent a runtime listener from also recognizing
a swipe. Both camera panning and board interactions must remain touch-usable
without changing presentation state.

## 4. Recognition policy

These are the accepted initial runtime constants, not manifest, theme, or
per-slide settings. Device evidence may motivate a later contract revision.
All distances use CSS pixels in the visible viewport's coordinate system.

| Rule | Initial value |
| --- | --- |
| Minimum net displacement on the command axis | 48 CSS pixels, inclusive |
| Direction dominance at release | Command-axis displacement at least twice the absolute perpendicular displacement |
| Maximum duration from down to release | 1,000 milliseconds, inclusive |
| Viewport edge exclusion at start | Less than 24 CSS pixels from any visible viewport edge |
| Zoom | Do not start or complete recognition while the page is pinch-zoomed beyond its unzoomed scale |
| Commit | Once, on release; never on intermediate movement |

For horizontal commands, the command axis is X and the perpendicular axis is Y.
Negative X is Next; positive X is Previous. For the grip, negative Y is Up /
Contents and X is perpendicular. Use net displacement from the starting point,
not accumulated path length. A gesture returning near its start does not qualify.

At exactly 48 pixels on the command axis and 24 perpendicular pixels, the distance
and dominance requirements pass; 47 command-axis pixels or 25 perpendicular
pixels at that same 48-pixel displacement fail. A start exactly 24 pixels from an
edge is eligible if every other rule passes. A release at exactly 1,000 milliseconds
passes the duration rule; a later release fails. No minimum velocity or extra
velocity-based shortcut applies.

Respect browser and OS edge gestures; do not try to capture starts in the excluded
bands. Position the grip's usable surface outside those bands and device safe areas.
Re-evaluate viewport geometry when its dimensions change.

### 4.1 Cancellation and priority

Cancel a candidate without navigation when:

- another touch pointer appears, including one outside the candidate's region;
- the browser sends `pointercancel` or tracked pointer capture is lost;
- the time limit expires, native scrolling, text selection, or a context menu starts;
- the page becomes zoomed, loses focus, becomes hidden, or changes viewport geometry;
- route, step, presentation, thread, view, or runtime ownership changes;
- runtime navigation begins or an input-owning overlay opens;
- the active slide exits or the recognizer is disconnected.

After multi-touch cancellation, require all touch pointers to lift before accepting
a new candidate. Do not resume a canceled candidate or reinterpret its remaining
movement. Release associated listeners, timers, and pointer state at the matching
lifecycle boundary.

Onboarding, help, dialogs, and menus have priority over gestures and the touch bar.
While one owns input, disable presentation touch commands; its normal dismissal or
activation must not also navigate the presentation.

Do not start or complete a gesture while an earlier runtime navigation request is
pending its render-ready work. Ignore those gestures rather than enqueueing or
replaying them. Once rendering is ready, ongoing step animation alone does not
block recognition: subsequent accepted commands still use the ordinary settling
policy. A new gesture must start after the pending request finishes.

### 4.2 Click handling

Ordinary taps retain native click behavior. After a qualifying swipe, consume only
the compatibility click attributable to that same touch sequence, including when
the resulting command only settles motion or reaches a boundary. It must not
activate underlying content or dismiss an overlay opened by the command.

Do not install a page-wide time window that suppresses unrelated clicks. A new
intentional tap, keyboard activation, or assistive-technology activation must remain
usable. Rejected gestures do not manufacture a click or globally cancel native
activation.

## 5. Browser gesture ownership

Declare browser gesture policy before pointer down. Pointer-event exclusions alone
do not restore browser scrolling or zoom if a restrictive ancestor policy already
disabled them.

Eligible horizontal surfaces reserve horizontal movement while allowing native
vertical panning and pinch zoom; `pan-y pinch-zoom` is the starting policy.
The separate grip reserves upward recognition while retaining pinch zoom.
The ordinary slide body never recognizes upward navigation, even at a scroll edge.

Native horizontal scrollers and other excluded interaction regions must retain
their required browser gestures. Do not blanket the presentation or slide with a
policy that those descendants cannot undo. The runtime's surface/policy arrangement
must preserve those regions before a gesture starts, including dynamically mounted
slide content. The author opt-out controls recognition; it does not replace an
interaction's own CSS gesture policy.

Never apply global `touch-action: none`, disable page zoom, or use late changes to
`touch-action` as a gesture-arbitration mechanism. If the browser takes ownership,
honor cancellation rather than attempting to recover the gesture.

## 6. Visible navigation and accessibility

On touch-capable devices, including hybrid devices, show a compact persistent
bottom-center navigation bar while a slide is presented. Detect touch capability,
not phone user-agent strings or screen width; a hybrid's mouse use must not hide
the controls. Show no bar or reserved footprint on devices without touch capability,
in overview views, or during thumbnail capture.

The bar contains native buttons in Previous, Next, Up / Contents order and a
separate upward-swipe grip. Keep the grip beside the buttons in the same compact
footer where space permits. Each button and the grip have at least a 48 by 48 CSS
pixel target. The grip is an optional gesture surface, not a redundant keyboard
tab stop; all of its functionality is available through the hierarchy button.

Use visible Previous and Next labels. The hierarchy button's visible and accessible
label is Up when a navigator owns the slide and Contents otherwise. Give the bar a
navigation landmark label such as Presentation navigation. Explain the grip with
a visible cue and touch-aware help, not an icon with no explanation.

Reserve the footer's footprint outside the authored slide viewport rather than
covering slide controls or captions. Include device safe areas and the 24-pixel
gesture-start edge exclusion in placement. Coordinate existing runtime help and
thread controls with the footer so they do not overlap its targets. Reserve no
space while the bar is absent. Broader slide responsiveness remains separate work.

Buttons support native pointer, Enter, Space, and assistive-technology activation.
Button activation must not also bubble into a presentation keyboard command.
While navigation or an input-owning overlay is pending, make the bar unavailable
without changing its reserved footprint. Disable a boundary command only when no
destination or applicable settling action exists; unknown dynamic-slide bounds
must not disable navigation prematurely.

Do not focus noninteractive slide content merely because of a horizontal swipe.
Retain existing navigator arrival/selection focus behavior. An explicit parent
return focuses its selected navigator control; TOC entry focuses and reveals the
current destination. Never leave focus in hidden or removed slide content.
Controls use visible focus indicators, and contextual labels update with the
active route without moving focus solely because the label changed.

Onboarding and help describe both touch and keyboard input on hybrid devices.
Onboarding keeps touch instructions visible on touch-capable devices and places
keyboard instructions in an expandable **Keyboard shortcuts** section. Its initial
collapsed or expanded state depends on viewport width, not inferred keyboard
availability; the reader can always expand it without dismissing onboarding.
Discovering gestures must not require a hardware keyboard. Keep the existing
onboarding preference policy; add touch instructions rather than a new preference
or manifest flag. Respect reduced motion and preserve pinch zoom.

## 7. Required focused verification

Implementation tests must cover:

- exact distance, dominance, duration, and edge boundaries in section 4;
- left/right traversal within fixed and dynamic slides, across slide boundaries,
  and through navigator choice, child-return, and completion states;
- parent returns from ordinary slides and nested navigators, plus root TOC fallback;
- same/opposite-direction settling, busy-state rejection, and no stale queued swipe;
- native and declarative exclusions, including nested/custom-element content,
  horizontal scrollers, and regions mounted after slide entry;
- tic-tac-toe camera and board interaction without presentation navigation;
- vertical reading, long press/selection, pointer cancellation, multi-touch,
  zoomed-page panning, viewport changes, overlays, and route changes;
- click suppression for the originating swipe without suppressing a later tap;
- correct history writes, boundary no-ops, focus, labels, target sizes, and footer
  layout; no bar in overviews/captures or on devices without touch capability;
- unchanged keyboard behavior, mouse/pen interactions, and navigator-card taps.

Synthetic pointer tests establish recognizer logic, not native browser ownership.
Touch-enabled browser coverage must exercise scrolling and cancellation. Real iOS
Safari and Android Chrome validation must cover zoom, edge/system gestures,
safe-area/browser-chrome changes, and the grip. Record any device limitations
without treating desktop emulation as physical-device evidence.
