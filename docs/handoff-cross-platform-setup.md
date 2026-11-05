# Handoff: cross-platform contributor setup

Status: analysis complete; no fixes implemented. Prepared on a Windows clone for an
agent continuing in a Codespace or on macOS.

## Goal

Make first-time contributor setup automatic and low-friction on macOS, Linux, and
Windows: clone, set up the toolchain, and run tests and Vividly commands. Handle
problems in the repository where that's appropriate. Document anything that is the
user's responsibility instead of automating it.

Two problems were observed:

1. Windows line endings break the runtime-manifest hashes.
2. Corporate users who must use a secure supply-chain registry end up with
   organization-specific URLs in `uv.lock`, or locked commands fail.

## Problem 1: line endings and runtime integrity hashes

### How the hashes work

- [tools/build_runtime_manifest.py](../tools/build_runtime_manifest.py) writes
  `src/vividly/resources/runtime/vividly-runtime.json`. The manifest contains a raw-byte
  SHA-256 digest for every file under `resources/runtime/` and `resources/reference/`.
- The runtime identity is `sha256:` of the canonical manifest bytes (sorted keys, no
  extra whitespace, one trailing LF). User projects record it in `vividly.yaml` as
  `integrity`. See [runtime-composition.md](specs/runtime-composition.md) section 5.
- `src/vividly/runtime.py` (`_verify_files`) checks per-file contents when
  `verify_runtime_contents` or `verify_reference_contents` is set. Callers that enable
  it are in `src/vividly/cli.py`: `provision`, `provision --upgrade`, and `reference`.
  Export and publish also verify contents, per the spec.
- `tests/test_package.py::test_runtime_manifest_matches_packaged_resources` compares the
  manifest with the working tree byte for byte.

### Findings

- The repository has no `.gitattributes` or `.editorconfig`.
- Git for Windows sets `core.autocrlf=true` system-wide by default.
- The Git index is clean: 338 text files are stored with LF (`i/lf`), 40 are binary
  (`.png`, `.jpg`, `.webp`), and 1 shows `i/none`. Only Windows checkouts get CRLF.
- In a fresh clone on Windows, 56 runtime/reference files had CRLF and all 55 manifest
  digests failed. That breaks the manifest test and any content-verifying command
  (`provision`, `reference`, export, publish) run from a development install.
- An existing Windows clone can have mixed line endings, depending on how and when
  files were checked out. If its runtime and reference files happen to be LF, the
  problem stays hidden locally.
- `build_runtime_manifest.py` uses `Path.write_text`, which writes CRLF on Windows. Run
  there, it produces a manifest that fails the canonical-bytes test and has a different
  runtime identity. `tools/sync_public_reference.py` uses the same pattern.
- CI and releases run on `ubuntu-latest`, so published wheels are correct and end users
  are not affected. This is a source-checkout problem only.
- macOS and Linux are only affected if a user sets `core.autocrlf=true`.

### Decision: keep the hashes

They are the runtime identity that projects pin, and they guard export and publish
artifacts. They should keep describing exact bytes.

Rejected alternatives:

- Hashing with line endings normalized: the identity would no longer describe the
  bytes that are actually served or exported.
- Skipping verification for development installs: this adds a special mode and hides
  real drift.

### Recommended fix

1. Add `.gitattributes`:

   ```gitattributes
   * text=auto eol=lf
   *.png binary
   *.jpg binary
   *.jpeg binary
   *.webp binary
   ```

   Check for other binary types first, such as fonts or icons; none were found at the
   time of analysis. Since the index is already LF, `git add --renormalize .` is expected
   to change no file contents and just add the new files. Expected, not yet verified.
2. Add `.editorconfig` with `end_of_line = lf` and `insert_final_newline = true` (plus
   any existing style settings), so new files created on Windows start as LF. On its own,
   `.gitattributes` only acts at commit and checkout time, so an uncommitted new CRLF file
   could still be hashed by the manifest tool.
3. Harden the tools:
   - Write generated text with `newline="\n"` in `build_runtime_manifest.py` and
     `sync_public_reference.py`. Check other writers of canonical bytes (for example
     `publishing/publication.py`, which writes `CNAME`).
   - Make `build_runtime_manifest.py` refuse files containing CRLF and list them,
     instead of quietly recording CRLF digests.
   - Optionally, when a content check fails, say whether the file has CRLF and point to
     the documented fix.
4. Document a one-time refresh for existing clones in CONTRIBUTING, run after committing
   or stashing work:

   ```console
   git rm --cached -r -q .
   git reset --hard
   ```

5. Optional: also run the manifest test, or a simple line-ending check, on
   `windows-latest` in CI. That is a CI change and needs the maintainer's explicit
   approval under the repository instructions.

### Verification (must happen on Windows)

Use a fresh clone, not an existing one.

1. `git ls-files --eol` shows `w/lf` for every text file.
2. `uv run --locked pytest tests/test_package.py` passes.
3. After `uv run --locked python tools/build_runtime_manifest.py`, `git status` shows no
   changes.
4. Creating a temporary CRLF file under `resources/reference/` makes the manifest tool
   fail with a clear message. Remove the file afterwards.

## Problem 2: corporate package registries and `uv.lock`

### Findings

uv 0.13.7 was used for testing.

- The committed `uv.lock` uses `https://pypi.org/simple` for all 22 registry packages.
- uv writes the resolving registry URL into every lockfile entry. It cannot use a
  mirror while keeping PyPI URLs in the lockfile. Upstream requests: astral-sh/uv#6349
  (open), astral-sh/uv#9056, and astral-sh/uv#9053.
- With a user-level `uv.toml` that sets an `[[index]]` with `default = true` (the setup
  CONTRIBUTING currently recommends), `uv lock --check` reports the committed lockfile as
  outdated. With `--no-config`, the same lockfile passes. So the documented advice leads
  directly to lockfile rewrites.
- `--frozen` does not help. It downloads from the PyPI artifact URLs recorded in the
  lockfile, which a restricted network may block.
- The repository already has a pre-commit guard, `tools/check_uv_lock.py` in
  `.githooks/pre-commit`, that rejects staged lockfiles with private registry or artifact
  hosts. It requires `git config --local core.hooksPath .githooks` once per clone.

### Tested workaround

These commands were tested in a temporary directory with the committed `pyproject.toml`
and `uv.lock` and a user-level `uv.toml` that sets a non-PyPI default index:

```console
uv export --frozen --no-emit-project -o req.txt
uv venv
uv pip install --require-hashes -r req.txt
```

Results:

- The export contained 250 `--hash=sha256:` pins and no registry URLs.
- The install went through the user's configured registry, and hash checking ensured
  the exact locked artifacts were installed.
- `uv.lock` was byte-for-byte unchanged.

Not yet tested end to end:

- `uv pip sync --require-hashes` instead of `install`
- `uv pip install --no-deps -e .` for the project itself
- `uv run --no-sync ...` for later commands (`--no-sync` implies `--frozen`, so it
  doesn't re-resolve)
- `playwright install`

### Recommendation

1. Provide a small, cross-platform, standard-library-only helper, for example
   `tools/dev_env.py sync`. It should run the export, create the venv, run the
   hash-pinned install, then install the project with `--no-deps -e .`. It must never
   write `uv.lock` and should keep the temporary requirements file out of the work tree,
   or ignore it.
2. In CONTRIBUTING, document two paths:
   - Public PyPI reachable: `uv sync --locked` and `uv run --locked ...` (unchanged).
   - Required corporate registry: the helper, then `uv run --no-sync ...`. Warn that
     plain `uv run` or `uv sync` would re-resolve and rewrite `uv.lock`.
3. Keep an unlocked `uv sync` followed by restoring the lockfile only as a last resort.
   CONTRIBUTING currently documents it with caveats.
4. Recommend enabling the pre-commit hook as the safety net.
5. Changing dependencies still requires an environment with public PyPI access. A
   Codespace is the natural place to do it.

### User's responsibility (document, don't automate)

- The registry URL and credentials: user-level `uv.toml` or environment variables,
  keyring or netrc, or named-index credential variables. Never put them in tracked files.
- Corporate TLS and proxies: `UV_NATIVE_TLS=1` or `SSL_CERT_FILE`, and `HTTPS_PROXY`.
  If the network only proxies traffic but still allows PyPI, the standard locked path
  works and no registry configuration is needed.
- Mirrors for Python downloads (`UV_PYTHON_INSTALL_MIRROR`) and for Playwright browsers
  (`PLAYWRIGHT_DOWNLOAD_HOST`).
- User-level uv config locations: `~/.config/uv/uv.toml` (or `$XDG_CONFIG_HOME`) on
  macOS and Linux, and `%APPDATA%\uv\uv.toml` on Windows. Precedence: command line, then
  environment, then project config, then user config, then system config.

## Repository state at handoff

- CONTRIBUTING.md has edits under "Using another package registry" (platform paths,
  temporary `UV_DEFAULT_INDEX` and `--default-index` overrides, precedence, credentials,
  and the caveated unlocked-sync workaround). It's undecided whether to keep them.
  They'll need revising to recommend the export-based path above, because the
  `UV_DEFAULT_INDEX` and `--default-index` examples combined with `--locked` fail
  against the committed PyPI lockfile.

## Suggested order of work

1. Line-ending fix (items 1–4 of problem 1) in one focused change. Verify on Windows.
2. Registry helper and CONTRIBUTING update in a separate change. Verify with a
   user-level `default = true` index (in a scratch environment) that `uv.lock` stays
   unchanged and that `uv run --no-sync vividly --help` and the tests work.
