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

- Treat `uv.lock` as protected generated output. Do not create, update, normalize, or otherwise modify it unless the user explicitly requests a dependency change or lockfile refresh.
- Run routine Python commands in locked mode, for example `uv run --locked ...` and `uv sync --locked`. Do not run plain `uv run`, `uv sync`, or `uv lock` when dependency changes are not part of the task.
- Local `UV_*` environment variables—especially `UV_DEFAULT_INDEX`—may refer to private or environment-specific package indexes. Never allow those settings to rewrite registry URLs in `uv.lock`.
- If a command reports that `uv.lock` is stale while running with `--locked`, stop and report the issue rather than regenerating the lockfile.
- A corporate `UV_DEFAULT_INDEX` can disagree with the public PyPI registry recorded in `uv.lock`, even when project dependencies have not changed. Plain `uv run` can then rewrite the lockfile with organization-specific registry URLs.
- For the setup, rationale, and policy-approved command-local publishing workaround, see [Publishing with a corporate uv index](../src/vividly/resources/reference/publishing.md#corporate-uv-index-and-a-public-lockfile). Do not disable an enforced index without authorization, unset proxy settings, or expose private index URLs or credentials.
- Before completing work that used `uv`, check `git status --short -- uv.lock`. If the file changed unexpectedly, do not overwrite or revert pre-existing user changes; report the modification and ask how to proceed.
- When a lockfile update is explicitly requested, confirm the intended package index first, remove environment-specific index overrides, and verify that the resulting diff contains no private registry URLs.
