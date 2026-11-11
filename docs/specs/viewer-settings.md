# Viewer Settings

Status: accepted interaction contract, 2026-11-11; implementation pending.

This specification defines a runtime-owned settings control panel for reader
preferences. It complements [Presentation Orchestration](presentation-orchestration.md)
and [Touch Navigation](touch-navigation.md). It does not add presentation-manifest
settings or change authored slide content.

## 1. Panel and access

Settings is a modal overlay, like Help, not a full-page browser route. Opening,
editing, and closing it preserve the current route, step, navigator selection,
presentation thread, and browser history. Opening it does not enter, exit, reset,
or advance a slide. It owns input but does not introduce a new animation-pause
contract.

Provide both entry points:

- A native gear button immediately beside the existing `?` Help button, with the
  accessible name and tooltip **Settings**.
- A **Settings** button inside the Help overlay.

The gear remains reachable in slide, table-of-contents, and catalog views,
independently of the navigation-controls preference. It must not be a child of
the hideable navigation bar. Coordinate it with Help, thread controls, safe areas,
and any navigation footer so their targets do not overlap. Its target is at least
48 by 48 CSS pixels. Hide it during thumbnail capture.

Opening Settings from Help replaces Help rather than stacking two active modals.
Closing Settings returns to Help and focuses its Settings button. Opening from
the gear and closing returns focus to the gear. If the originating view is removed
while the panel is open, close it and restore focus to an appropriate control in
the new view, never to hidden or detached content.

Use an accessible modal dialog named **Settings**, with a visible Close button.
Focus its first setting on entry; Tab and Shift+Tab stay within the dialog.
Escape and Close dismiss it without navigating. Clicking its backdrop also
dismisses it; clicks inside do not. Unlike Help's existing any-key dismissal,
ordinary keys do not close Settings. Native input, Enter, and Space behavior
remain intact. Dismissal input must not reach the presentation underneath.

While Settings owns input, presentation keyboard commands, navigation buttons,
and presentation gestures are unavailable. Cancel any gesture already in progress.
Opening or closing the panel must not replay pending input. The panel scrolls
within the visible viewport on small screens and preserves pinch zoom and visible
keyboard-focus indicators.

## 2. Preference scope and persistence

Changes apply immediately; there is no Save or Cancel transaction. Closing the
panel does not revert them. Store preferences through the existing site-scoped
reader-state mechanism backed by localStorage, keyed by the normalized catalog
URL rather than by individual presentation or slide. They survive reloads and
apply across presentations sharing that catalog in the same browser profile.
They do not synchronize across browsers, devices, origins, or separate catalogs.

Reuse the existing initial-hint preference, including previously saved suppression;
do not reset it or introduce an independent second value. Existing onboarding and
Help preference controls remain synchronized views of that same preference.

If storage is unavailable or a write fails, keep the current page's choice usable
but show an accessible, non-blocking notice that it could not be saved for future
visits. Do not claim persistence succeeded. Missing or invalid navigation-control
values use Auto; invalid stored values must not break presentation startup.

## 3. Navigation controls

Provide a labeled native single-choice control:

**Navigation controls: Auto / Show / Hide**

Auto is the default when no valid preference is saved.

| Value | Behavior while a slide is presented |
| --- | --- |
| Auto | Show on touch-capable devices unless the primary pointer is fine and supports hover. |
| Show | Show regardless of touch capability, including mouse-only computers. |
| Hide | Hide regardless of touch capability. |

Use the existing touch-capability test: `navigator.maxTouchPoints > 0` or
`(any-pointer: coarse)`. For Auto's laptop-like exception, require both
`(pointer: fine)` and `(hover: hover)`. These primary-pointer queries describe
the browser's reported input environment, not proof of an attached keyboard.
Re-evaluate Auto when the relevant media queries change; never overwrite the
saved choice as a result.

Explain Auto beside the control: **Show controls on touch-first devices; hide
them when the primary pointer supports precise pointing and hover.**
Explicit Show and Hide take precedence over detection. Do not infer the choice
from viewport width, user-agent strings, fullscreen state, or the most recent
mouse, pen, touch, or keyboard event.

The setting controls the complete navigation footer, including its buttons and
any swipe grip. Hide removes its reserved footprint; Show restores it. Apply
layout changes without changing presentation state or moving focus out of
Settings. All modes keep the bar absent in catalog and table-of-contents views
and during thumbnail capture.

This is a visibility preference, not an input-mode switch. Touch swipes on eligible
slide surfaces, keyboard navigation, clickers, and native slide interactions
remain available regardless of the choice. Hiding the bar must not disable slide
gesture recognition or require a visible bar to recognize touch input. A hidden
grip has no active gesture surface.

For a laptop-style SurfaceBook presentation, Auto normally hides the footer when
Chrome reports a fine primary pointer with hover. Hide is the explicit, reliable
override when hardware detection does not match the reader's intended setup.

## 4. Initial hint dialog

Provide a checkbox labeled **Show initial hint dialog**, with explanatory text:
**Show navigation tips when starting a presentation.**

The saved preference defaults to enabled and is the inverse of the existing
site-scoped hint-suppression value. Unchecking it suppresses automatic onboarding
under the manifest's `keyboardHints: auto` policy. Checking it permits onboarding
on the next otherwise-eligible presentation activation; it does not open the
dialog immediately or re-arm onboarding already shown in the current page.

Preserve the existing precedence and eligibility rules:

- `keyboardHints: auto` respects the saved checkbox.
- `keyboardHints: always` shows eligible onboarding regardless of the saved
  checkbox. While that presentation is active, show the checkbox checked and
  disabled, with **This presentation always shows initial hints.**
- `keyboardHints: never` suppresses onboarding regardless of the saved checkbox.
  While that presentation is active, show the checkbox unchecked and disabled,
  with **This presentation disables initial hints.**
- An enforced manifest policy must not overwrite the saved site preference.
  In the catalog, with no active presentation policy, the checkbox edits the
  saved site preference.
- `vividly-skip-hints=1` suppresses automatic onboarding for the current page even
  under `always`. Show an explanatory notice when it applies; the checkbox
  continues to represent the preference or manifest policy described above,
  not the temporary query override.
- Deep-link eligibility, once-per-page behavior under Auto, activation timing,
  and dismissal behavior remain as specified in Presentation Orchestration.

Help remains available regardless of the checkbox or manifest policy. Touch
instructions and keyboard instructions remain available on hybrid devices;
hiding navigation controls does not remove either from Help or onboarding.

## 5. Required focused verification

Implementation tests must cover:

- Both entry points, the gear remaining reachable with the footer hidden, and
  access in slides, catalog, and table of contents; no gear in captures.
- Modal focus containment, native control activation, dismissal and focus return,
  Help-to-Settings replacement, and removal of the originating view.
- No route, step, history, thread, or slide-lifecycle changes merely from using
  Settings; no leaked keyboard, pointer, or gesture command.
- Auto on touch-first, fine-pointer/hover hybrid, and non-touch environments;
  primary-pointer media-query changes; Show and Hide overriding detection.
- Footer footprint removal/restoration, unchanged slide swipes with hidden
  controls, and Show on a mouse-only device; no footer in overviews or captures.
- Saved choices across reloads and presentations in one catalog, isolation
  between catalogs, invalid navigation-control values, and visible storage
  failure feedback.
- Existing hint-suppression preferences, synchronized controls, all three
  manifest policies, the query override, deep links, and enabling hints without
  immediately opening or replaying onboarding.

Physical hybrid-device validation should include a SurfaceBook-style laptop
setup and a touch-first setup. Browser emulation verifies policy logic but is
not evidence of how real convertible hardware reports its primary pointer.
