Source tree organization:

- vividly
  - docs
    - specs - the folder where we will place the specs
  - src - source code for the vividly project
  - site - source for the github pages site

## Scope and validation
- Make only the changes requested by the user.
- Use the narrowest validation that directly verifies those changes.
- Do not perform release builds, package publication checks, dependency refreshes, broad test runs, or CI changes unless explicitly requested or necessary for the requested behavior.
- Treat potentially useful adjacent work as a recommendation, not an action.
- Stop after the requested behavior and focused validation pass.
- Never add or modify CI, publishing workflows, or release configuration unless explicitly requested.

## Python dependency and lockfile safety

- Use `uv run --no-sync ...` for routine local Python commands, including
  tests, version preparation, and release dispatch. Use the existing `.venv`;
  follow [contributor setup](../CONTRIBUTING.md#contributor-details) if dependencies
  need installing or updating. Do not refresh dependencies or regenerate
  `uv.lock` unless requested.
- Keep `--locked` in GitHub Actions. Local execution uses `--no-sync` because
  the committed lockfile records public PyPI sources while configured local
  indexes may differ. `--no-sync` skips dependency freshness checks; repeat
  contributor setup after dependency changes rather than assuming it validates
  the installed environment.
- A locked-command failure does not always mean dependencies changed.
  Environment-specific package-index settings (such as
  `UV_DEFAULT_INDEX`) can conflict with registry URLs in the lockfile.
  Check for this possibility before proposing a lockfile refresh. For a registry
  mismatch, use the contributor workflow, not an unlocked retry or `--frozen`
  as a substitute for dependency validation.
- Respect the maintainer's configured indexes and proxies. Do not
  override them or retry unlocked without authorization.
- Preserve pre-existing lockfile edits. Never stage or commit temporary registry
  rewrites; version preparation requires a lockfile satisfying the public-source
  policy. Stop and ask about genuine metadata/lockfile inconsistencies.
- Before completing work that used uv, check
  `git status --short -- uv.lock`. Never expose private registry
  URLs or credentials.
