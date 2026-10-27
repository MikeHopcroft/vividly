---
name: vividly-presentations
description: "Create and revise Vividly web presentations. Use when adding slides, arranging the presentation manifest, authoring slide steps, or working with presentation assets and themes."
argument-hint: "Describe the presentation or slide change"
---
# Vividly Presentations

## Procedure

1. Run `vividly reference` when `.vividly/reference/` is absent or stale. Always read
   `.vividly/reference/authoring.md`, then read only the task-relevant references:
   - `slides.md` for lifecycle, steps, context, modules, data roots, or manifests;
   - `controls.md` when using or extending controls;
   - `keyboard.md` for navigators, captured keys, or presentation navigation;
   - `dependencies.md` for external packages or offline readiness; and
   - `cli.md` for command behavior, thumbnails, cache administration, rehearsal, or
     export.
2. Inspect `site/catalog.yaml`, identify the target presentation and manifest, and read
   neighboring slides, the active theme, and reusable modules, controls, and data
   patterns.
3. Resolve unclear narrative, interaction, or architectural decisions before editing.
   Do not ask for details established by the target presentation's existing
   conventions.
4. Choose the smallest correct boundary: reused module with new data, built-in control,
   custom element, slide module, slide-local source, or project dependency. Run
   `vividly dependencies` before selecting a browser package.
5. Implement author-owned modules, data, and assets under `site/`. Update the target
   manifest for slide instances or structure. Update `site/catalog.yaml` only for root
   presentations or the project-wide dependency selection.
6. Run `vividly run` and open the exact ID-prefixed route. Perform every applicable
   check from `authoring.md`: direct and reverse step arrival, animation settling,
   re-entry, neighboring boundaries, keyboard behavior, 1920 by 1080 layout,
   accessibility, browser errors, failed requests, dependencies, and assets.
7. Regenerate the affected thumbnail scope when its representative image changed.
   After a dependency or remote-resource change, exercise the intended path while
   connected and repeat it under `vividly rehearse`.
8. Report the affected routes and the steps, interactions, thumbnails, and rehearsal
   paths verified. State unverified paths or limitations explicitly.

## Definition of done

- Preserve the requested narrative and presentation sequence.
- Reuse existing presentation conventions and the smallest correct implementation
  boundary.
- Keep fixed steps deterministic on direct, forward, and backward arrival, and release
  owned lifecycle resources.
- Keep content semantic, accessible, legible, and unclipped.
- Resolve data, assets, and dependencies through their documented boundaries.
- Verify the exact route and every affected behavior without related browser or network
  errors.
- Regenerate affected thumbnails and rehearse offline-sensitive paths when applicable.

Do not create `site/vividly/` for author content, add author presentations to the
reserved `~` namespace, import `/vividly/vendor/**`, read dependency globals, embed
selected package URLs, or replace runtime-owned dependency keys. Runtime changes
require an explicit presentation-system task.
