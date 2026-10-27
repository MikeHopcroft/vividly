# Vividly Presentation Project

This repository contains a Vividly project. Author-owned presentation source lives in
`site/`; Vividly combines it with the runtime selected by `vividly.yaml`.

- Use the `vividly-presentations` skill for slide-authoring procedure. Materialize
  version-matched guidance with `vividly reference` when `.vividly/reference/` is
  absent or stale.
- `site/catalog.yaml` registers independently routable root presentations and owns the
  project-wide browser dependency selection.
- Presentation manifests conventionally live under `site/presentations/`. Each catalog
  presentation ID is its stable route and storage identity.
- Independently authorable slide modules conventionally live under `site/slides/` with
  their slide-specific scripts, styles, data, and assets.
- A module may serve several slide instances or presentations. Each manifest node keeps
  its own address, props, data root, state, and thumbnail identity.
- Keep author-owned presentation-wide assets, fonts, and themes under `site/` without
  using the reserved `site/vividly/` subtree.
- `site/runtime/` and `site/reference/` are manifest-managed outputs created and
  maintained by `vividly provision`; never edit them directly. Use `vividly eject` to
  create an editable source tree for runtime or documentation experiments.
- Use browser-native ES modules and preserve the no-build-step deployment model.
- Slide code accesses browser packages by logical key through
  `this.ctx.dependency(key).load()`. It does not embed selected package URLs, import
  `/vividly/vendor/**`, read dependency globals, or replace runtime-owned keys.
- Do not add author presentations to the reserved `~` namespace.
- Do not create or modify runtime-owned files as part of an author presentation task.
