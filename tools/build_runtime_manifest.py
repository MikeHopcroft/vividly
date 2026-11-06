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
TEXT_EXTENSIONS = frozenset({".css", ".html", ".js", ".json", ".md", ".svg", ".txt"})


def file_hash(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashed_files(root: Path) -> dict[str, str]:
    """Return a sorted path-to-digest mapping for regular files below root."""
    paths = sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())
    return {path.relative_to(root).as_posix(): file_hash(path) for path in paths}


def validate_line_endings() -> None:
    """Reject CRLF text inputs without interpreting binary resource bytes."""
    invalid = [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for root in (RUNTIME_ROOT, REFERENCE_ROOT)
        for path in sorted(root.rglob("*"))
        if path != MANIFEST_PATH
        and path.is_file()
        and not path.is_symlink()
        and path.suffix.lower() in TEXT_EXTENSIONS
        and b"\r\n" in path.read_bytes()
    ]
    if invalid:
        raise SystemExit(
            "Cannot generate runtime manifest: CRLF line endings found in text files:\n"
            + "\n".join(f"  {relative}" for relative in invalid)
            + "\nSave these files with LF line endings and rerun the generator."
        )


def main() -> None:
    """Write the canonical runtime manifest."""
    validate_line_endings()
    runtime_files = hashed_files(RUNTIME_ROOT)
    runtime_files.pop(MANIFEST_PATH.relative_to(RUNTIME_ROOT).as_posix(), None)
    manifest = {
        "composition_api": COMPOSITION_API,
        "files": runtime_files,
        "reference_files": hashed_files(REFERENCE_ROOT),
        "schema": 1,
        "version": (RUNTIME_ROOT / "vividly" / "version.txt")
        .read_text(encoding="utf-8")
        .strip(),
    }
    content = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    MANIFEST_PATH.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
