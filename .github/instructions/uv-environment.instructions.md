---
name: uv-environment
description: "Use when running uv commands. Covers local package-index permissions and lockfile safety."
---

- Respect my configured package index and proxy settings.
  Do not switch to public PyPI or bypass access restrictions.
- If locked execution fails solely because the configured index
  differs from the lockfile's registry, and dependency declarations
  are unchanged, I authorize retrying routine local commands
  without --locked.
- Temporary registry rewrites in uv.lock are acceptable locally.
  Report them and leave them for me to review and revert.
  Never stage or commit them.
- Ask before allowing commands to overwrite pre-existing lockfile
  edits. For other lockfile inconsistencies, stop and ask.