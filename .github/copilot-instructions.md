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

- Use locked execution for routine Python commands, such as
  `uv run --locked ...`. Do not refresh dependencies or regenerate
  `uv.lock` unless requested.
- A locked-command failure does not always mean dependencies changed.
  Environment-specific package-index settings (such as
  `UV_DEFAULT_INDEX`) can conflict with registry URLs in the lockfile.
  Check for this possibility before proposing a lockfile refresh.
- Respect the maintainer's configured indexes and proxies. Do not
  override them or retry unlocked without authorization.
- If an unlocked retry is authorized, preserve pre-existing lockfile
  edits, report resulting changes, and leave temporary registry
  rewrites for the maintainer to review and revert. Never stage or
  commit those temporary changes.
- Before completing work that used uv, check
  `git status --short -- uv.lock`. Never expose private registry
  URLs or credentials.
