---
name: uv-environment
description: "Use when running uv commands. Covers local package-index permissions and lockfile safety."
---

- Respect configured package indexes and proxies. Do not switch to public PyPI
  or bypass access restrictions.
- Use `uv run --no-sync ...` with the existing `.venv` for routine local commands,
  including tests, version preparation, and release dispatch. Keep `--locked`
  in GitHub Actions.
- Follow [contributor setup](../../CONTRIBUTING.md#contributor-details) to install
  or update dependencies: export the committed pins, sync through the configured
  registry, and install the project editable without resolving dependencies.
  `--no-sync` does not validate dependency freshness; repeat setup after dependency
  changes.
- An index mismatch is not a dependency change. If `--locked` fails for that
  reason, use the contributor workflow; do not retry without a lockfile-preserving
  flag or regenerate `uv.lock`. `--frozen` is not a dependency-validation fix.
- Ask before overwriting pre-existing lockfile edits. Report any existing temporary
  registry rewrites and leave them for review; never stage or commit them. Version
  preparation requires a lockfile satisfying the public-source policy.
- For genuine metadata/lockfile inconsistencies, stop and ask. After using uv,
  check `git status --short -- uv.lock`; never expose private URLs or credentials.