$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
& uv --directory $root run --no-sync python -m tools.maintain release @args
exit $LASTEXITCODE
