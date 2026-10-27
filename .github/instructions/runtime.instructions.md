---
description: "Use when editing the canonical Vividly browser runtime."
applyTo:
  - "src/vividly/resources/runtime/**"
---
# Runtime Development

`src/vividly/resources/runtime/` is the Vividly platform's canonical runtime source
tree. `vividly provision` copies this source into the managed runtime of a
Vividly-powered site.

Edit this directory only as part of explicit Vividly platform or runtime development
and maintenance. Never change it to implement a slide, presentation, theme, or
project-specific workaround.

After changing the canonical runtime:

- update the runtime manifest with
  `uv run python tools/build_runtime_manifest.py`; and
- run the narrow tests that cover the changed runtime behavior plus
  `tests/test_package.py::test_runtime_manifest_matches_packaged_resources`.

Do not edit `vividly-runtime.json` by hand.
