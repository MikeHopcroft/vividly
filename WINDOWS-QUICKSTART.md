# Windows quickstart

Choose one of the two setups below. Both assume [git](https://git-scm.com/) and
[uv](https://docs.astral.sh/uv/getting-started/installation/) are available in
PowerShell.

## 1. You just want the Vividly CLI

Use this to run Vividly from a checkout without installing development tools or
matching the repository's exact dependency versions.

```powershell
git clone https://github.com/MikeHopcroft/vividly.git
cd vividly
uv tool install --editable .
uv tool update-shell
```

Restart your terminal application. For VS Code's integrated terminal, fully quit
and reopen VS Code. Then, from the repository root:

```powershell
vividly --help
```

uv installs the CLI and its dependencies in a per-user tool environment, outside
the project's `.venv`, and makes the command available globally for your user.
This installation does not read or rewrite the repository's `uv.lock`.

## 2. You want the full contributor toolchain

This installs the editable project, pytest, Ruff, Pyright, and Chromium for browser
tests in the project's `.venv`. Also install [Node.js 24](https://nodejs.org/)
for the JavaScript tests, matching CI. You do not need the global CLI installation
from scenario 1.

Unlike CLI-only installation, contributor setup needs to account for your
organization's supply-chain policy. The shared `uv.lock` records public package
sources. `uv sync --locked` and `uv run --locked` prevent lockfile updates, but
do not remap those sources to your organization's registry. They can fail when
that registry is required. Dropping `--locked` can instead rewrite the lockfile
with private registry URLs.

The workflow below exports the locked versions and installs them through your
configured registry, without rewriting `uv.lock`. Use your organization's approved
registry, authentication, certificate, and proxy settings; confirm that this
workflow is permitted rather than bypassing those settings.

```powershell
git clone https://github.com/MikeHopcroft/vividly.git
cd vividly
uv venv --python 3.12
uv export --frozen --all-groups --no-emit-project --output-file .venv\requirements.txt
uv pip sync .venv\requirements.txt
uv pip install --no-deps --editable .
```

The export keeps version pins and hashes but does not emit registry index
settings. `uv pip sync` uses your configured registry to fetch those packages.
The requirements file stays inside the Git-ignored `.venv` directory.
The last command installs Vividly itself without resolving its dependencies again.
If the approved registry lacks a pinned version or matching artifact, ask your
organization's package-service owners; do not remove pins or hashes to force
installation.

Verify the CLI and install the browser used by the tests:

```powershell
uv run --no-sync vividly --help
uv run --no-sync vividly install-browser
```

Chromium installation requires an organization-approved browser download path
on managed devices.

Run focused checks from the repository root, for example:

```powershell
uv run --no-sync pytest tests/test_cli.py
uv run --no-sync ruff check src tests tools/release.py
uv run --no-sync pyright
node --test tests/billiards.test.mjs
```

Use **`--no-sync` instead of `--locked`** for `uv run` commands in
[CONTRIBUTING.md](CONTRIBUTING.md) with this setup. It runs the installed environment
without reconciling it with the lockfile's public sources.
It also skips dependency freshness checks. Repeat the export, sync, and
editable-install commands after pulling dependency updates. `--frozen` does not
check that the lockfile matches changed project metadata; it is not a substitute
for updating the lockfile when intentionally changing dependencies.

### If you already hit a lockfile problem

- If `--locked` fails, do not simply drop it. Use the export workflow for a
  registry mismatch. If project metadata and the lockfile genuinely disagree,
  resolve that dependency change intentionally.
- If a commit is rejected for private URLs in `uv.lock`, inspect
  `git diff -- uv.lock` and `git diff --cached -- uv.lock`. Remove unintended
  local registry changes from the working and staged copies without discarding
  intentional dependency work. Do not bypass the guard or commit the URLs.

### Before contributing

Review [CONTRIBUTING.md](CONTRIBUTING.md) for line-ending rules, pre-commit hook
setup, and choosing validation checks. Install gitleaks as recommended there.
Hook activation is separate from installing the toolchain.

Before committing, review your changes, including `uv.lock`. Intentional lockfile
updates must retain public sources and be produced in an approved environment
with public PyPI access.
