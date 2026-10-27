# Thumbnail Control Specification

Status: specified; step-thumbnail sequence implementation pending

## Purpose

`<vividly-thumbnail>` renders a generated thumbnail for a slide in the active
presentation. It provides one presentation-aware rendering contract for slide modules,
Markdown documents, and the table of contents' Outline and Grid modes.

Every finite slide has one generated image per step and designates one of those images
as its canonical thumbnail. A dynamic slide has one generated initial-state image,
which is canonical. The control renders the canonical image by default and accepts an
explicit step when an author needs one state from the sequence.

The control renders an image or a stable fallback. It does not navigate, activate a
navigator choice, own selection state, or capture a live slide.

## Thumbnail identity

A generated thumbnail belongs to one manifest slide node and step. Its identity is:

```text
presentation ID + presentation-local slide address + zero-based step
```

The generated thumbnail index is the source of image paths, revisions, sequence order,
and canonical-step selection. The control does not infer a file name or import a slide
module.

The `address` input accepts either:

- a presentation-local slide address, which resolves to that slide; or
- a presentation-local section address, which resolves to the section's first
  structural slide.

Section resolution lets a navigator render a thumbnail directly from an entry in
`ctx.navigator.sections`. It is structural resolution, not prefix matching. An unknown
address does not resolve.

Addresses do not include a presentation ID, route hash, step, query, or fragment. The
optional `step` input selects a thumbnail within the resolved slide's sequence.
Omitting `step` selects the canonical thumbnail.

The control resolves only against the active presentation. Cross-presentation lookup
requires a separate contract and is not encoded into `address`.

## Element API

Canonical thumbnail:

```html
<vividly-thumbnail
  address="gallery/layered-build"
  label="Layered build demonstration"
  fallback="Layered Build"
  loading="lazy">
</vividly-thumbnail>
```

Exact-step thumbnail:

```html
<vividly-thumbnail
  address="gallery/layered-build"
  step="2"
  label="Layered build after annotations appear">
</vividly-thumbnail>
```

| Attribute / property | Type | Default | Meaning |
|---|---|---|---|
| `address` | string | `""` | Presentation-local slide or section address |
| `step` | nonnegative integer or `null` | `null` | Exact zero-based step; `null` selects the canonical thumbnail |
| `label` | string | `""` | Optional accessible name and fallback text |
| `fallback` | string | `""` | Visual fallback text without accessibility semantics |
| `loading` | `"lazy"` or `"eager"` | `"lazy"` | Native image loading policy |

The corresponding JavaScript properties are `address`, `step`, `label`, `fallback`,
and `loading`. Removing the `step` attribute or assigning `null` restores canonical
selection. An invalid `step` does not fall back to the canonical image; it produces the
same stable unavailable state as an unindexed step. Unsupported `loading` values
behave as `lazy`.

Changing an observed input rerenders the control against the current active
presentation runtime.

## Runtime resolution

The containing `<vividly-presentation>` exposes synchronous canonical, exact-step, and
sequence resolvers:

```js
presentation.thumbnailFor(address)
presentation.thumbnailFor(address, step)
presentation.thumbnailsFor(address)
```

`thumbnailFor(address)` returns the canonical descriptor.
`thumbnailFor(address, step)` returns the descriptor for that exact indexed step.
`thumbnailsFor(address)` returns every indexed descriptor in ascending step order.

A descriptor has this shape:

```js
{
  address: "gallery/layered-build/demo",
  title: "Layered Build Demonstration",
  src: "https://example.test/thumbnails/product-tour/gallery/.../step-0002.png?v=a41789b9...",
  capturedStep: 2,
}
```

Each descriptor and the array returned by `thumbnailsFor()` are immutable. `address`
is the resolved slide address, including when the caller supplied a section address.
`title` is the resolved slide title. `src` is an absolute URL containing the indexed
content revision as its `v` query parameter. `capturedStep` is the descriptor's
zero-based step.

`thumbnailFor()` returns `null` when:

- the address is empty or unknown;
- a section contains no slide;
- the active presentation has no valid index entry for the resolved slide;
- an explicit step is invalid or absent from the indexed sequence; or
- the selected descriptor does not contain a usable path and revision.

`thumbnailsFor()` returns an empty immutable array for the corresponding missing or
invalid states. It never substitutes the canonical descriptor for an invalid explicit
step.

The runtime loads and validates the version-3 thumbnail index once per active
presentation. It fetches the stable `index.json` URL with
`fetch(url, { cache: "no-cache" })` so the browser revalidates cached metadata.
Controls do not fetch or parse the index independently. Presentation thumbnails resolve
from the composed site's `/thumbnails/` URL, backed by the author-owned
`site/thumbnails/` source. Authors may commit or ignore generated thumbnails; this
repository ignores them and generates them in CI, while `vividly thumbnails` runs
locally for preview.

For each valid descriptor, the runtime appends the indexed lowercase hexadecimal
SHA-256 revision to the image URL as `?v=<revision>`. An unchanged PNG therefore keeps
the same URL, while changed bytes receive a new cache key without changing the physical
path. A missing, malformed, or unsupported index produces unavailable results rather
than inferred paths.

The table of contents' Outline and Grid modes use `<vividly-thumbnail>` and the same
resolvers. They do not retain a separate path-resolution implementation or import slide
modules to discover thumbnail metadata.

## Rendering

The control uses light DOM and renders:

- an `<img>` when the requested `thumbnailFor()` call returns a descriptor; and
- a fallback layer in every state, behind the image.

The image:

- uses the descriptor `src`;
- uses native `loading` from the control;
- fills the control with `object-fit: cover`; and
- has empty alternative text because the host owns accessibility semantics.

The fallback remains mounted while the image loads, when no descriptor exists, and
after an image load error. Its text is:

1. `label`, when nonempty;
2. `fallback`, when nonempty;
3. the resolved slide title, when available; or
4. `Thumbnail unavailable`.

The control has a default `16 / 9` aspect ratio and stable dimensions independent of
image availability. Slide CSS may override its width, height, aspect ratio, border,
radius, background, and descendant image fitting because the control uses light DOM.

The control dispatches a bubbling `vividly-rendered` event after it renders a fallback
or after its image loads. A missing index entry, invalid step, unavailable step, and
failed image request are expected fallback states and do not dispatch `vividly-error`.

## Accessibility

The thumbnail is decorative by default:

- without `label`, the host has `aria-hidden="true"`;
- the internal image always has `alt=""`; and
- the fallback layer is always hidden from the accessibility tree.

When `label` is nonempty, the host has `role="img"` and `aria-label` equal to `label`.
The internal image remains decorative so assistive technology announces one name.

Navigator cards normally omit `label` because the containing registered choice control
already names the destination. A standalone thumbnail may provide `label`.

## Navigation boundary

`<vividly-thumbnail>` has no `href`, click behavior, keyboard behavior, navigator
marker, active state, or focus state. The containing card, link, or button owns
navigation and interaction.

This separation allows the same thumbnail to appear in navigator choices, passive
recaps, presenter guides, and overview surfaces without nested interactive controls.

## Failure and lifecycle behavior

The control renders its fallback when it is disconnected from a presentation, when no
runtime is active, when its address cannot be resolved, when its requested step is
invalid or unavailable, or when its image fails.

On reconnection or input change, it resolves again. An image load or error from an
older render must not replace the current render.

Presentation runtime replacement reconstructs slide and overview DOM, so controls
resolve against the newly active runtime when they connect. An already active runtime
retains its in-memory index; regeneration becomes visible after the presentation is
reloaded or reactivated.

## Validation

Focused validation covers:

- canonical and exact-step slide-address resolution;
- complete ordered sequence resolution;
- section-address resolution to the first structural slide;
- invalid and unavailable steps without canonical substitution;
- immutable descriptors and sequence arrays;
- version-3 index and revision validation;
- index cache revalidation and revision-bearing image URLs;
- author thumbnail-root resolution through the composed site;
- lazy and eager loading;
- decorative and labeled accessibility;
- missing-index and broken-image fallbacks;
- input changes and stale image events;
- canonical and step-level TOC use of the shared control in Outline and Grid modes;
- no slide-module loading merely to render an overview thumbnail; and
- stable layout when an image is unavailable.
