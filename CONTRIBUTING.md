# Contributing to Vividly

This guide is for developing Vividly itself. To create a presentation instead, use
the [getting-started guide](https://mikehopcroft.github.io/vividly/#/vividly/make-something/choose-your-path)
or the [agentic bootstrap instructions](src/vividly/resources/reference/agentic-bootstrap.md).

Please keep in mind that Vividly doesn't generally accept unsolicited PRs. We encourage you to modify Vividly to try out new ideas and if you find something you feel would improve Vividly, describe it in a GitHub issue and include, if possible, any specs or agent prompts that could be used to implement the functionality.

Choose one of the two setups below. Both assume [git](https://git-scm.com/) and
[uv](https://docs.astral.sh/uv/getting-started/installation/) are available in your
terminal. The commands work in macOS/Linux shells and Windows PowerShell unless
otherwise noted.

## 1. You just want the Vividly CLI

Use this to run Vividly from a checkout without installing development tools or
matching the repository's exact dependency versions.

```console
git clone https://github.com/MikeHopcroft/vividly.git
cd vividly
uv tool install --editable .
uv tool update-shell
```

Complete the setup for your platform below.

<details>
<summary>Windows PowerShell: update your current PATH</summary>

Add uv's tool directory to the current session:

```powershell
$env:PATH = "$(uv tool dir --bin);$env:PATH"
```

**Simply opening a new PowerShell terminal in an already-running VS Code instance
is not sufficient to ensure a refreshed PATH.** It can inherit VS Code's older
PATH; the same applies to a new tab in an already-running Windows Terminal.

On Windows, `uv tool update-shell` updates the saved user PATH for future
processes. As a child process, uv cannot change the environment of the PowerShell
or VS Code process that launched it. It may therefore report "already in PATH"
even though the current terminal cannot find the command.

The PowerShell assignment above updates the current session immediately. It asks
uv for the actual tool directory, including custom configurations, and preserves
the existing PATH. It does not replace the persistent setup done by
`uv tool update-shell`.

</details>

<details>
<summary>macOS/Linux: restart your shell</summary>

On macOS/Linux, restart your shell to load the configuration updated by
`uv tool update-shell`.

</details>

Then, from the repository root:

```console
vividly --help
```

uv installs the CLI and its dependencies in a per-user tool environment, outside
the project's `.venv`, and makes the command available globally for your user.
This installation does not read or rewrite the repository's `uv.lock`.

## 2. You want the full contributor toolchain

This installs the editable project, pytest, Ruff, and Pyright in the project's
`.venv`, plus Chromium for browser tests. Also install
[Node.js 24](https://nodejs.org/) for the JavaScript tests, matching CI.
You do not need the global CLI installation from scenario 1.

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

```console
git clone https://github.com/MikeHopcroft/vividly.git
cd vividly
uv venv --python 3.12
uv export --frozen --all-groups --no-emit-project --output-file .venv/requirements.txt
uv pip sync .venv/requirements.txt
uv pip install --no-deps --editable .
```

Verify the CLI and install the browser used by the tests:

```console
uv run --no-sync vividly --help
uv run --no-sync vividly install-browser
```

Chromium installation requires an organization-approved browser download path
on managed devices. On Linux, Playwright may also require system libraries; see
its [system dependency instructions](https://playwright.dev/python/docs/browsers#install-system-dependencies).

Run focused checks from the repository root, for example:

```console
uv run --no-sync pytest tests/test_cli.py
uv run --no-sync ruff check src tests tools/release.py
uv run --no-sync pyright
node --test tests/billiards.test.mjs
```

Before contributing, review the details below, including line endings and
pre-commit hook setup. Hook activation is separate from installing the toolchain.

## Contributor details

### Dependencies and package sources

The export keeps version pins and hashes but does not emit registry index
settings. `uv pip sync` uses your configured registry to fetch those packages.
The requirements file stays inside the Git-ignored `.venv` directory.
The editable-install command installs Vividly itself without resolving its
dependencies again. If the approved registry lacks a pinned version or matching
artifact, ask your organization's package-service owners; do not remove pins or
hashes to force installation.

Use `uv run --no-sync` with this setup. It runs the installed environment without
reconciling it with the lockfile's public sources, and skips dependency freshness
checks. Repeat the export, sync, and editable-install commands after pulling
dependency updates. `--frozen` does not check that the lockfile matches changed
project metadata; it is not a substitute for updating the lockfile when
intentionally changing dependencies.

If you already hit a lockfile problem:

- If `--locked` fails, do not simply drop it. Use the export workflow for a
  registry mismatch. If project metadata and the lockfile genuinely disagree,
  resolve that dependency change intentionally.
- If a commit is rejected for private URLs in `uv.lock`, inspect
  `git diff -- uv.lock` and `git diff --cached -- uv.lock`. Remove unintended
  local registry changes from the working and staged copies without discarding
  intentional dependency work. Do not bypass the guard or commit the URLs.

Before committing, review your changes, including `uv.lock`. Intentional lockfile
updates must retain public sources and be produced in an approved environment
with public PyPI access.

### Line endings

Vividly verifies runtime resources against hashes of their exact bytes and
requires the runtime manifest to use a canonical byte representation. Converting
LF line endings to CRLF changes those bytes even when the text looks identical,
so automatic conversion can cause runtime validation to fail.

[.gitattributes](.gitattributes) keeps text files in LF format on checkout, including
on Windows. [.editorconfig](.editorconfig) asks compatible editors to save files
with LF line endings and a final newline. Enable EditorConfig support in your
editor so new text files follow these settings before they are added to Git.

Git detects binary files automatically; explicit binary rules also protect the
image formats currently used here. When adding a new binary format, add an
explicit rule if Git might misidentify it as text. Binary contents must remain
unchanged.

The [runtime manifest generator](tools/build_runtime_manifest.py) rejects CRLF in
known text formats under the runtime and reference resource roots. It lists every
offending file and leaves the manifest unchanged. Save those files with LF line
endings and rerun the generator. When adding a new text format, extend its
`TEXT_EXTENSIONS` set; other formats are hashed without line-ending validation.
The generated manifest itself is excluded from input validation so regeneration
can repair its line endings.

The manifest generator and [public reference synchronizer](tools/sync_public_reference.py)
always write LF output. The synchronizer's `--check` compares bytes, so it also
detects CRLF in generated public reference files.

### Activate the pre-commit hook

The tracked [pre-commit hook](.githooks/pre-commit) runs two offline checks:

- a secret scan of the staged changes with [gitleaks](https://github.com/gitleaks/gitleaks),
  when it is installed; and
- a lockfile guard that rejects staged lockfile changes referencing private
  registries or artifact hosts. It uses only the Python standard library, preferring
  `.venv/bin/python` and otherwise using `python3` on `PATH`. The selected interpreter
  must be Python 3.12 or later.

Installing gitleaks is recommended. Without it, the hook prints a warning and skips
the secret scan. On macOS:

```console
brew install gitleaks
```

For other platforms, see the
[gitleaks installation instructions](https://github.com/gitleaks/gitleaks#installing).

Git does not activate cloned hooks automatically. Before enabling this hook,
inspect existing configuration and the default hooks directory:

```console
git config --show-origin --get-all core.hooksPath
git rev-parse --git-path hooks
```

No output from the first command means no hooks path is configured. Inspect the
directory reported by the second command for existing active hooks. Resolve any
existing hook setup before changing the configuration; do not overwrite it
blindly. Then activate this repository's hooks once per clone:

```console
git config --local core.hooksPath .githooks
```

If the secret scan reports a finding, remove the secret from the staged changes and
commit again. Findings are shown with the secret redacted. If the value was ever
real, rotate it. Removing it from a commit does not make it safe again.

The lockfile guard checks the staged version of `uv.lock`, rejects its deletion, and
leaves files and staged content untouched on failure. Correct and stage the intended
public lockfile before retrying. Dependency changes should be made intentionally
in an environment with public PyPI access; the hook never regenerates the lockfile.
Unrelated commits do not run the validator.

To check a snapshot or another file manually without synchronizing dependencies:

macOS/Linux:

```console
.venv/bin/python -I tools/check_uv_lock.py uv.lock
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -I tools\check_uv_lock.py uv.lock
```

You can use `python3` instead if it is Python 3.12+. Hook activation is local to
each clone; it is not enabled by this documentation or by running the tests.
These checks catch accidental commits, but can be bypassed with `--no-verify`.
See the [pre-commit hook specification](docs/specs/precommit.md) for the source policy and limits.

### Secret scanning on GitHub

The repository has GitHub
[secret scanning and push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
enabled. GitHub rejects a push that contains a recognized secret, such as an API
token. If a push is blocked, remove the secret from the unpushed commits, for
example by amending them, rotate the secret, and push again. Do not bypass the block
for a real secret.

## Preview and reference documentation

Start the composed development server and open the reported URL:

```console
uv run --no-sync vividly run
```

The repository's [runtime selection](vividly.yaml) points to the editable browser
runtime. The server composes it with the repository's presentation content and
reloads connected browsers after relevant changes.

Materialize the reference documentation for that selected runtime:

```console
uv run --no-sync vividly reference
```

This writes derived, Git-ignored Markdown under `.vividly/reference/`. The canonical
reference sources live in [src/vividly/resources/reference/](src/vividly/resources/reference/).
See the [CLI reference](src/vividly/resources/reference/cli.md) for command behavior
and the [agent reference index](src/vividly/resources/reference/agentic.md) for
task-specific guidance.

## Validation

Choose the smallest checks that directly cover your change. Documentation-only
changes do not require running the application test suites.

### Python

Run focused tests with pytest, for example:

```console
uv run --no-sync pytest tests/test_cli.py
```

Use Ruff for linting and Pyright for strict type checking. Narrow the paths when
appropriate; the repository-wide commands are:

```console
uv run --no-sync ruff check src tests tools/release.py
uv run --no-sync pyright
```

Some tests require Playwright-managed Chromium. Install it when needed:

```console
uv run --no-sync vividly install-browser
```

### JavaScript

The JavaScript tests use Node.js's built-in test runner. Use Node.js 24 to match
CI; no npm dependencies or installation step are needed.

```console
node --test tests/billiards.test.mjs
```

### Complete suites

The [tests/](tests/) directory contains independent Python and JavaScript suites.
Neither runner executes the other suite. When broader validation is warranted:

```console
uv run --no-sync pytest tests
node --test tests/*.test.mjs
```

The [CI workflow](.github/workflows/ci.yml) defines the supported test matrix and
additional distribution checks. It can be dispatched manually and is also called
by the release workflow.

## Releases

Maintainers publish packages and the matching site through the supervised release
workflow using PyPI Trusted Publishing. Follow the [release guide](docs/releasing.md)
for setup, publication, and recovery.
