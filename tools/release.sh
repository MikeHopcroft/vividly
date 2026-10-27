#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv --directory "$root" run --locked python -m tools.maintain release "$@"
