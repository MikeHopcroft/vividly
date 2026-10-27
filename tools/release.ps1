$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
& uv --directory $root run --locked python -m tools.maintain release @args
exit $LASTEXITCODE
