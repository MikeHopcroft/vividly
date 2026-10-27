"""Materialize runtime-matched reference documents for local agents."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from .runtime import SelectedRuntime, reference_files

REFERENCE_STATE_ROOT = ".vividly"
REFERENCE_OUTPUT_NAME = "reference"
REFERENCE_METADATA_NAME = "runtime.json"


class ReferenceMaterializationError(ValueError):
    """Reference output cannot be safely inspected or replaced."""


def _digest(files: dict[str, Path]) -> str:
    digests = {
        relative: hashlib.sha256(path.read_bytes()).hexdigest()
        for relative, path in sorted(files.items())
    }
    content = json.dumps(digests, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"


def _metadata(runtime: SelectedRuntime, content_digest: str) -> bytes:
    metadata: dict[str, object] = {
        "content_digest": content_digest,
        "framework_version": runtime.manifest.version,
        "manifest_integrity": runtime.manifest.integrity,
        "schema": 1,
        "source": runtime.source,
    }
    if runtime.distribution_version is not None:
        metadata["distribution_version"] = runtime.distribution_version
    if runtime.commit is not None:
        key = "commit" if runtime.source == "repository" else "upstream_commit"
        metadata[key] = runtime.commit
    return (
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()


def _is_current(destination: Path, source_digest: str, metadata: bytes) -> bool:
    if destination.is_symlink():
        raise ReferenceMaterializationError(
            f"reference output is not a regular directory: {destination}"
        )
    if not destination.exists():
        return False
    if not destination.is_dir():
        raise ReferenceMaterializationError(
            f"reference output is not a regular directory: {destination}"
        )
    generated = reference_files(destination, exclude_generated_metadata=True)
    metadata_path = destination / REFERENCE_METADATA_NAME
    if not metadata_path.is_file():
        return False
    return metadata_path.read_bytes() == metadata and _digest(generated) == source_digest


def materialize_reference(project_root: Path, runtime: SelectedRuntime) -> tuple[int, bool]:
    """Materialize selected reference files and report count and whether output changed."""
    source_files = reference_files(runtime.reference_root)
    source_digest = _digest(source_files)
    expected_metadata = _metadata(runtime, source_digest)
    state_root = project_root / REFERENCE_STATE_ROOT
    destination = state_root / REFERENCE_OUTPUT_NAME

    if state_root.is_symlink() or (state_root.exists() and not state_root.is_dir()):
        raise ReferenceMaterializationError(
            f"derived-state root is not a regular directory: {state_root}"
        )
    if _is_current(destination, source_digest, expected_metadata):
        return len(source_files), False

    state_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reference-", dir=state_root) as temporary:
        temporary_root = Path(temporary)
        staged = temporary_root / REFERENCE_OUTPUT_NAME
        staged.mkdir()
        for relative, source in source_files.items():
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        staged_digest = _digest(reference_files(staged))
        (staged / REFERENCE_METADATA_NAME).write_bytes(_metadata(runtime, staged_digest))

        previous = temporary_root / "previous"
        had_previous = destination.exists()
        if had_previous:
            destination.replace(previous)
        try:
            staged.replace(destination)
        except BaseException:
            if had_previous and previous.exists():
                previous.replace(destination)
            raise

    return len(source_files), True
