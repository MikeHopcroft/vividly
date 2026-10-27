# Life authoring tools

Precompute the fixed Game of Life scenarios so viewing a presentation never runs
thousands of simulation generations on the browser's main thread.

## Setup (authors only)

Requires Node.js 22 or newer and npm. From the repository root:

```sh
npm --prefix tools/life ci
```

The only package is the `yaml` development dependency, installed locally under
`tools/life/node_modules/` (Git-ignored). Commit `package.json` and `package-lock.json`.
No Node tooling or packages are required to serve, view, export, or publish the
checked-in site. Do not copy this tools directory into a published site.

The lockfile retains exact versions and integrity hashes but omits registry-specific
download URLs, allowing npm to use the author's configured registry. When updating
the dependency intentionally, preserve that portability with
`npm --prefix tools/life install --package-lock-only --omit-lockfile-registry-resolved`.

## Change a scenario

1. Edit the `props` on the `life` slide in
   [the manifest](../../site/presentations/life.yaml). It remains the authoritative
   simulation configuration.
2. Generate the asset:

   ```sh
   npm --prefix tools/life run generate
   ```

3. Verify freshness and run the focused Node tests:

   ```sh
   npm --prefix tools/life run check
   npm --prefix tools/life test
   ```

4. Preview `#/vividly/gallery/life/life` and affected steps using your usual Vividly
   command. Also check responsiveness of the following
   `#/vividly/make-something/choose-your-path` navigator. Life is incorporated into
   Vividly's gallery rather than registered as a standalone catalog presentation.
5. Commit the configuration/compiler change together with
   [frames.json](../../site/slides/game-of-life/data/frames.json).

No automatic build or regeneration runs during preview or publication.

## Files and format

- [simulation.mjs](./simulation.mjs): compiler extracted from the original engine.
- [precompute.mjs](./precompute.mjs): YAML input, generation, and freshness checking.
- [frames.mjs](../../site/slides/game-of-life/frames.mjs): shared configuration
  hashing, encoding, and schema validation/decoding.
- [cells.mjs](../../site/slides/game-of-life/cells.mjs): coordinate helpers shared by
  the author-time simulation and runtime renderer.
- [engine.js](../../site/slides/game-of-life/engine.js): browser renderer only.

The asset includes schema version 1, a compiler/source fingerprint, and a
`simulations` object keyed by SHA-256 of canonical configuration JSON. Object keys
are sorted recursively; array order and JSON values are preserved. Node and browser
use the same implementation, including number/string serialization.

All 25 steps, predictions, overlays, resolved viewports, animation timing, viewport
keyframes, and intermediate sampled worlds are baked. Sets become arrays in JSON
and are restored on load. Cell iteration order is preserved.

The browser hashes the current props and requires a matching entry. Missing,
corrupt, unsupported, or configuration-mismatched data fails explicitly; there is no
viewing-time simulation fallback. Compiler-only changes are detected by `--check`,
not by fetching authoring sources in the browser.

The source fingerprint covers the generator, simulation, codec, and coordinate
helpers. It excludes manifest structure outside the selected props, renderer-only
code, prose, and machine paths. Output is deterministic with no timestamps. A write
uses a same-directory temporary file and atomic replacement; `--check` regenerates
in memory, compares the entire output, and never writes.

## Explicit paths

Defaults resolve relative to the tool, independent of your working directory.
Explicit paths resolve relative to the working directory:

```sh
node tools/life/precompute.mjs \
  --manifest site/presentations/life.yaml \
  --slide life \
  --output site/slides/game-of-life/data/frames.json
```

Append `--check` to verify without writing. The selector supports slides nested in
sections of this manifest; it does not follow incorporated manifests. The current
runtime slide loads its module-local `data/frames.json`, so use that output location
for this presentation.

Change `FRAME_SCHEMA_VERSION` and update the codec/tests when the asset format
changes. After simulation, codec, helper, or generator changes, regenerate even if
the manifest did not change. JSON is uncompressed on disk; HTTP compression is a
server choice, not a requirement.

## Browser verification

Use Playwright separately from the generator; it is not a Node tool dependency.
Check direct arrivals, all steps forward and backward, finite-motion settling,
re-entry, reduced motion, and local JSON loading without console or network errors.
Compare decoded data with compiler output and measure speculative preload cost.
Do not generate thumbnails as part of this work.

These tools and Life assets are shared with the presentations repository. Keep
changes to the compiler, codec, helpers, and baked frames together when synchronizing
the two copies; merge presentation manifests selectively.
