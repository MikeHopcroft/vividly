---
description: "Use when creating or modifying Vividly slides, presentation manifests, themes, assets, or other files under the hosted site."
applyTo:
  - "site/**"
---
# Vividly Authoring Instructions

- Run `vividly reference` when local guidance is absent or stale. Read
  `.vividly/reference/authoring.md` and only the detailed references relevant to the
  task.
- Keep slide modules independently authorable. Preserve the documented module-root and
  data-root boundaries.
- Register slide instances and structure in the target presentation manifest. Change
  `site/catalog.yaml` only for root presentations or the project-wide dependency
  selection.
- Use browser-native ES modules; do not introduce a compilation or bundling step.
- Keep fixed steps absolute, deterministic, idempotent, and reversible. Release owned
  resources at the appropriate lifecycle boundary.
- Inspect the effective registry with `vividly dependencies`. Access packages through
  `this.ctx.dependency(key).load()` and follow
  `.vividly/reference/dependencies.md`. Do not embed selected package URLs, read
  dependency globals, declare dependencies in presentation manifests, or replace
  runtime-owned keys.
- Keep presentation-wide author styling under `site/` without using the reserved
  `site/vividly/` subtree.
- Follow the validation and definition-of-done checklists in
  `.vividly/reference/authoring.md`.
