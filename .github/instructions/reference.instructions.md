---
description: "Use when editing canonical packaged Vividly reference Markdown or its generated public copies."
applyTo:
  - "src/vividly/resources/reference/*.md"
  - "site/reference/*.md"
---
# Packaged Reference Maintenance

`src/vividly/resources/reference/*.md` is the canonical packaged reference.
`site/reference/*.md` is generated public-site output; do not edit it directly.

After editing canonical reference Markdown, run these commands in order:

```console
uv run python tools/sync_public_reference.py
uv run python tools/build_runtime_manifest.py
```

The first command synchronizes the public copies. The second updates the selected
runtime's `reference_files` names and hashes. Review and commit the generated
`site/reference/` and `src/vividly/resources/runtime/vividly-runtime.json` changes with
the canonical edit.

Run the focused validation:

```console
uv run python tools/sync_public_reference.py --check
uv run pytest \
  tests/test_package.py::test_runtime_manifest_matches_packaged_resources \
  tests/test_public_site.py::test_public_reference_matches_canonical_package_source
```

When adding or removing a reference document, also:

- register or remove its slide in `site/presentations/vividly.yaml` when the page should
  appear in the public documentation presentation; and
- update tests that intentionally enumerate the complete packaged reference set.
