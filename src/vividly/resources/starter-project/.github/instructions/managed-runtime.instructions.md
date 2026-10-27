---
description: "Use when viewing or considering changes to Vividly-managed runtime or reference files."
applyTo:
  - "site/runtime/**"
  - "site/reference/**"
---
# Managed Vividly Files

Files under `site/runtime/` and `site/reference/` are part of the provisioned
Vividly-powered site. `vividly provision` creates and maintains these files, and their
contents are covered by the runtime manifest.

Never edit these directories directly. Direct changes break the managed runtime's
integrity and may be replaced by a later provision operation.

To experiment with or develop changes to the runtime or packaged documentation, run
`vividly eject` and edit the separate source tree it creates. Keep author slides,
presentations, themes, assets, and project dependency selections in their documented
author-owned locations.
