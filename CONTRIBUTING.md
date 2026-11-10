# Contributing to Vividly

This guide is for developing Vividly itself. To create a presentation instead, use
the [getting-started guide](https://mikehopcroft.github.io/vividly/#/vividly/make-something/choose-your-path)
or the [agentic bootstrap instructions](src/vividly/resources/reference/agentic-bootstrap.md).

## Development setup

On Windows, start with the [Windows quickstart](WINDOWS-QUICKSTART.md). It separates
CLI-only installation from the full contributor toolchain and explains how to
use an organization-required package registry without rewriting the shared lockfile.
If you used its export-based setup, keep using `uv run --no-sync` in place of
`uv run --locked` throughout this guide. The locked setup below assumes the
lockfile's public package sources are permitted in your environment.

Use Python 3.12 or later and [uv](https://docs.astral.sh/uv/) for environment and
dependency management. Clone the repository and synchronize its locked dependencies:

```console
git clone https://github.com/MikeHopcroft/vividly.git
cd vividly
uv sync --locked
```

Run commands from the repository root:

```console
uv run --locked vividly --help
```

Use locked mode for routine development. If uv reports that the lockfile is stale,
resolve the dependency mismatch explicitly rather than regenerating it as part of
an unrelated change.

### Line endings

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

```console
.venv/bin/python -I tools/check_uv_lock.py uv.lock
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
uv run --locked vividly run
```

The repository's [runtime selection](vividly.yaml) points to the editable browser
runtime. The server composes it with the repository's presentation content and
reloads connected browsers after relevant changes.

Materialize the reference documentation for that selected runtime:

```console
uv run --locked vividly reference
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
uv run --locked pytest tests/test_cli.py
```

Use Ruff for linting and Pyright for strict type checking. Narrow the paths when
appropriate; the repository-wide commands are:

```console
uv run --locked ruff check src tests tools/release.py
uv run --locked pyright
```

Some tests require Playwright-managed Chromium. Install it when needed:

```console
uv run --locked vividly install-browser
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
uv run --locked pytest tests
node --test tests/*.test.mjs
```

The [CI workflow](.github/workflows/ci.yml) defines the supported test matrix and
additional distribution checks. It can be dispatched manually and is also called
by the release workflow.

## Releases

Maintainers publish packages and the matching site through the supervised release
workflow using PyPI Trusted Publishing. Follow the [release guide](docs/releasing.md)
for setup, publication, and recovery.
