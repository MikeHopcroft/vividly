# Windows quickstart (temporary)

Goal: clone Vividly, install an editable command, and preview the repository.
This is the initial setup checkpoint, not the testing-toolchain guide.

## Prerequisites

- Git and [uv](https://docs.astral.sh/uv/getting-started/installation/) available
  in PowerShell.
- Python 3.12 or later available to uv. If absent, uv normally downloads it;
  on managed devices, follow your employer's approved Python setup.
- Keep your employer's package-index, authentication, and proxy settings.
  Do not disable them or override them with public PyPI.

## Clone, install, run

Run each command separately in PowerShell. Stop if a command fails.
Start in the parent folder where you want the new `vividly2` folder:

```powershell
git clone --branch mhop/feature https://github.com/MikeHopcroft/vividly.git vividly2
cd vividly2
uv tool install --editable .
```

The branch name is `mhop/feature` (singular). It contains the Windows line-ending
fix; omit `--branch mhop/feature` after that fix is merged into `main`.
If you already have this branch checked out, skip cloning and use that checkout.

Make uv's tool commands available in this PowerShell window:

```powershell
$toolBin = uv tool dir --bin
$env:PATH = "$toolBin;$env:PATH"
vividly --help
vividly run
```

Open the local URL printed by the server in your browser. The repository's
presentation should load. Leave PowerShell running; press Ctrl+C to stop.
No virtual-environment activation or Playwright browser installation is needed
for this preview.

For future terminals, run once:

```powershell
uv tool update-shell
```

Restart your terminal application afterward. If using VS Code's integrated
terminal, fully quit and reopen VS Code. The command can say the directory is
already in PATH even when the running terminal still has an older PATH; the
`$env:PATH` command above handles the current window.

## After editing or updating the checkout

Source edits take effect without reinstalling. The tool points at this checkout:
keep it in place, and remember that switching branches also changes the tool.

After adding dependencies, changing dependency constraints, or changing command
entry points, refresh from the repository root:

```powershell
uv tool install --editable . --force
```

Add `--upgrade` to request newer dependency versions within the declared
constraints.

## What this setup does not do

The editable tool has its own environment, uses your configured registry, and
does not rewrite `uv.lock`. It resolves dependencies from `pyproject.toml`, not
from `uv.lock`; a lockfile-only update does not update this tool environment.
It does not install pytest, Ruff, or Pyright. Testing setup will be a separate
checkpoint before these instructions are folded into [CONTRIBUTING.md](CONTRIBUTING.md).

If startup reports `manifest bytes are not canonical`, stop and check that your
checkout includes the Windows line-ending fix. Reinstalling packages does not
repair converted resource files.
