# Pre-commit Hook Specification

Status: implemented. Hook activation is an explicit per-clone action.

## Purpose

The committed [uv.lock](../../uv.lock) must resolve every third-party package from
public PyPI. Development environments may route package installation through a
private package index, and a lockfile-generating command in such an environment
can rewrite registry and artifact URLs to private hosts.

The pre-commit hook runs two checks before an ordinary local commit:

- a **secret scan** of the staged changes, using [gitleaks](https://github.com/gitleaks/gitleaks)
  when it is installed; and
- a **lockfile guard** that rejects a staged `uv.lock` resolving packages from anywhere
  but public PyPI.

Both are accidental-commit safeguards, not unbypassable security boundaries. Neither
requires pull requests or network access. On GitHub, the repository's secret scanning
and push protection complement the hook.

## Components

| Component | Role |
| --- | --- |
| [tools/check_uv_lock.py](../../tools/check_uv_lock.py) | Validator. Owns the source policy. |
| [.githooks/pre-commit](../../.githooks/pre-commit) | Tracked Git hook. Runs the secret scan, then selects the lockfile input and invokes the validator. |
| `gitleaks` | Optional secret scanner, installed separately by each developer. |
| [tests/test_check_uv_lock.py](../../tests/test_check_uv_lock.py) | Focused tests for this specification. |
| [Contributing](../../CONTRIBUTING.md) | Documents activation and manual validation. |

## Secret scan

The hook runs first:

```sh
gitleaks git --pre-commit --staged --redact --verbose --no-banner --log-level warn .
```

- It scans only the staged changes, so it adds little time to a commit.
- It uses gitleaks' default rules. The repository adds no gitleaks configuration,
  baseline, or allowlist.
- Findings are reported with secret values redacted.
- If gitleaks reports a finding or fails, the commit is blocked.
- If `gitleaks` is not on `PATH`, the hook prints a warning and continues with the
  lockfile guard. The hook never installs or downloads gitleaks.

## Source policy

The validator parses the lockfile as TOML and inspects dependency-source fields.
It does not search raw text.

Each `[[package]]` entry must have a `source` that is exactly one of:

- `{ registry = "https://pypi.org/simple" }`; or
- `{ editable = "." }`, for the root package `vividly` only.

Each `sdist` and every entry in `wheels` must have a `url` that:

- uses the `https` scheme;
- has the exact network location `files.pythonhosted.org`, with no credentials and
  no explicit port; and
- contains no space or C0 control characters.

Everything else is rejected, including private registries and artifact hosts, HTTP
URLs, Git, direct-URL and path dependencies, and missing or unsupported source
forms. Allowing another host or source form requires changing this specification.

## Validator

`tools/check_uv_lock.py` requires Python 3.12 or later. It uses only the standard
library, imports nothing from the project, and runs offline. It is launched with a
plain interpreter, never through a dependency-synchronizing `uv run`, so it works
when the lockfile itself is invalid.

Invocation:

| Command | Input |
| --- | --- |
| `check_uv_lock.py` | `uv.lock` in the current directory |
| `check_uv_lock.py PATH` | the selected file |
| `check_uv_lock.py --staged` | `uv.lock` from Git's index, via `git show :uv.lock` |

`--staged` cannot be combined with a path.

The validator exits with status 0 when the input satisfies the source policy and 1
otherwise. Invalid TOML, an empty or missing package list, non-UTF-8 input,
unreadable files, and Git failures all fail. Diagnostics name the package and field
where possible, never print URLs or credentials, and state that no files or staged
content were changed.

The validator never modifies the lockfile, the index, the environment, or uv
configuration.

## Pre-commit hook

`.githooks/pre-commit` is committed with executable permissions. After the secret
scan, the lockfile guard runs:

1. If the staged `uv.lock` is unchanged from `HEAD`, the hook exits 0 without running
   the validator. Rename detection is disabled, so renaming the lockfile counts as a
   change.
2. If Git cannot report whether the lockfile changed, the commit is blocked.
3. Otherwise the hook selects `.venv/bin/python` if executable, or `python3` on
   `PATH`. If neither is Python 3.12 or later, the commit is blocked with a setup
   message. The hook never installs or downloads an interpreter.
4. The hook runs the validator with `--staged`. The staged version is checked, not
   the working tree: a public working copy cannot hide a private staged lockfile,
   and unstaged private changes do not block a public staged lockfile.
5. A staged deletion, or renaming the lockfile away, fails because the index no
   longer contains `uv.lock`.

On failure the hook changes nothing. It does not regenerate, restore, or stage any
file.

## Activation

Git does not activate repository-provided hooks on clone. Each clone is activated
once:

```sh
git config --local core.hooksPath .githooks
```

Before activation, the developer checks for an existing `core.hooksPath` or installed
hooks and resolves any conflict. The configuration is local and not committed. Once
active, committed updates to the hook take effect without reinstalling it.

## Dependency changes

Routine development uses locked mode, as described in
[Contributing](../../CONTRIBUTING.md). Dependency additions and upgrades are made
intentionally in an environment with public PyPI access. The guard provides no
regeneration command.

## Limits

The hook protects ordinary commits only in an activated clone. It can be bypassed
with `--no-verify`, disabled through Git configuration, or absent in a fresh clone.
The secret scan runs only where gitleaks is installed, and gitleaks recognizes only
the secret formats its rules describe. Neither check inspects history or runs before
a push.

There is no pre-push hook or CI check. GitHub secret scanning with push protection is
the server-side check for recognized secrets.

## Validation

The focused tests cover:

- public sources, including the repository's lockfile and the root editable source;
- private registries and artifact hosts, HTTP, unsupported source forms, invalid
  TOML, missing source data, and credential-free diagnostics;
- initial commits with public staged input;
- rejection of private staged input when the working copy is public, with `HEAD`,
  the index, and the working file preserved;
- commits of public staged input while private changes remain unstaged;
- rejection of a staged deletion or rename of the lockfile;
- unrelated commits succeeding without invoking the validator;
- the secret scan receiving the staged-scan arguments;
- a secret-scan failure blocking the commit with `HEAD` and the index preserved; and
- a missing gitleaks producing a warning without blocking the commit.

Integration tests make real Git commits in disposable repositories with no remotes,
isolated Git configuration, dummy identities, and a `PATH` containing only `git` and,
where needed, a stand-in `gitleaks` that records its arguments and returns a chosen
status. Fixtures use invented URLs. Tests
do not activate hooks or stage files in the developer's repository.

Missing or old interpreters, simulated Git failures, and exhaustive URL edge cases
are handled by the implementation but not covered by tests.
