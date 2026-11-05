# Contributing to Vividly

This guide is for developing Vividly itself. To create a presentation instead, use
the [getting-started guide](https://mikehopcroft.github.io/vividly/#/vividly/make-something/choose-your-path)
or the [agentic bootstrap instructions](src/vividly/resources/reference/agentic-bootstrap.md).

## Development setup

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

### GitHub Codespaces

The [devcontainer configuration](.devcontainer/devcontainer.json) uses a
Python 3.12 Bookworm image with uv and Node.js LTS, rather than the larger
universal image. Creation synchronizes locked dependencies and installs Chromium
with its Linux system dependencies. Port 8080 is forwarded for the Vividly preview.

For an existing Codespace, run **Codespaces: Rebuild Container** from the VS Code
Command Palette to apply configuration changes.

### Using another package registry

If your environment requires a package mirror or another registry, configure it
in your user-level `uv.toml` for persistent use, rather than this repository.
The recommendation is the same on macOS, Linux, and Windows; only the configuration
location and shell syntax differ:

| Platform | User configuration location |
| --- | --- |
| macOS / Linux | `$XDG_CONFIG_HOME/uv/uv.toml`, or `~/.config/uv/uv.toml` when unset |
| Windows | `%APPDATA%\uv\uv.toml` |

For example:

```toml
[[index]]
url = "https://packages.example.org/simple"
default = true
```

`default = true` replaces PyPI as the default index rather than adding another
index alongside it.

For a temporary override or CI, use `UV_DEFAULT_INDEX` instead. In bash or zsh on
macOS or Linux, set it for one command:

```sh
UV_DEFAULT_INDEX=https://packages.example.org/simple uv sync --locked
```

In PowerShell on Windows, set it for the current session:

```powershell
$env:UV_DEFAULT_INDEX = "https://packages.example.org/simple"
uv sync --locked
```

For a single invocation on any platform, use the command-line option:

```console
uv sync --locked --default-index https://packages.example.org/simple
```

Command-line options take precedence over environment variables, which take
precedence over configuration files. An existing `UV_DEFAULT_INDEX` can therefore
override your user configuration. See
[uv's configuration documentation](https://docs.astral.sh/uv/concepts/configuration-files/)
for details. Keep credentials separate from the registry URL, using your
organization's authentication mechanism or
[named-index credential environment variables](https://docs.astral.sh/uv/concepts/indexes/#providing-credentials-directly).

Changing the configured registry can make `uv sync --locked` report that the
lockfile needs updating even when dependency requirements have not changed.
Check the registry configuration before treating this as a dependency mismatch.
If your required registry is incompatible with the committed lockfile, you may
intentionally run `uv sync` without `--locked` to create a registry-specific local
lockfile. Review the resulting `uv.lock` changes and do not commit registry-specific
rewrites. When restoring the public lockfile, remove only changes introduced by
this workaround, preserving any pre-existing edits. Subsequent locked commands,
including `uv run --locked`, may remain incompatible with your registry
configuration; syncing and then restoring the lockfile does not resolve that
mismatch. Do not put registry credentials in tracked files.

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
