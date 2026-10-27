"""Generate the packaged Vividly runtime manifest."""

import hashlib
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = REPOSITORY_ROOT / "src" / "vividly" / "resources"
RUNTIME_ROOT = RESOURCE_ROOT / "runtime"
REFERENCE_ROOT = RESOURCE_ROOT / "reference"
MANIFEST_PATH = RUNTIME_ROOT / "vividly-runtime.json"
COMPOSITION_API = 1


def file_hash(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashed_files(root: Path) -> dict[str, str]:
    """Return a sorted path-to-digest mapping for regular files below root."""
    paths = sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())
    return {path.relative_to(root).as_posix(): file_hash(path) for path in paths}


def main() -> None:
    """Write the canonical runtime manifest."""
    manifest = {
        "composition_api": COMPOSITION_API,
        "files": hashed_files(RUNTIME_ROOT),
        "reference_files": hashed_files(REFERENCE_ROOT),
        "schema": 1,
        "version": (RUNTIME_ROOT / "vividly" / "version.txt")
        .read_text(encoding="utf-8")
        .strip(),
    }
    manifest["files"].pop(MANIFEST_PATH.relative_to(RUNTIME_ROOT).as_posix(), None)
    content = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    MANIFEST_PATH.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
