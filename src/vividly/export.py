"""Deterministic materialization of a validated Vividly composition."""

import shutil
import tempfile
from pathlib import Path

from .composition import Composition, compose_project


class ExportError(ValueError):
    """A project cannot be exported safely to the requested destination."""


def _canonical_destination(destination: Path) -> tuple[Path, Path]:
    requested = destination.expanduser().absolute()
    if requested.is_symlink():
        raise ExportError(f"export destination cannot be a symbolic link: {requested}")
    try:
        canonical = requested.resolve(strict=False)
    except OSError as error:
        raise ExportError(f"cannot resolve export destination {requested}: {error}") from error
    return canonical, canonical


def _validate_destination(
    destination: Path,
    canonical_destination: Path,
    composition: Composition,
) -> bool:
    for label, source in (
        ("project root", composition.project_root),
        ("author root", composition.author_root),
        ("runtime root", composition.runtime.runtime_root.resolve()),
    ):
        if (
            canonical_destination == source
            or canonical_destination.is_relative_to(source)
            or source.is_relative_to(canonical_destination)
        ):
            raise ExportError(
                f"export destination overlaps {label}: {canonical_destination} and {source}"
            )

    if not destination.exists():
        parent = destination.parent
        if parent.is_symlink() or not parent.is_dir():
            raise ExportError(f"export parent is not a regular directory: {parent}")
        return False
    if not destination.is_dir():
        raise ExportError(f"export destination is not a directory: {destination}")
    try:
        next(destination.iterdir())
    except StopIteration:
        return True
    except OSError as error:
        raise ExportError(f"cannot inspect export destination {destination}: {error}") from error
    raise ExportError(f"export destination is not empty: {destination}")


def _materialize(composition: Composition, staging: Path) -> None:
    for url_path, composed in sorted(composition.files.items()):
        relative = Path(*url_path.parts[1:])
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(composed.source_path.read_bytes())


def export_composition(composition: Composition, destination: Path) -> Path:
    """Atomically materialize one already validated composition."""
    requested, canonical = _canonical_destination(destination)
    destination_existed = _validate_destination(requested, canonical, composition)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{requested.name}-",
            dir=requested.parent,
        )
    )
    removed_empty_destination = False
    try:
        _materialize(composition, staging)
        still_exists = requested.exists()
        if destination_existed:
            if requested.is_symlink() or not requested.is_dir():
                raise ExportError(
                    f"export destination changed during assembly: {requested}"
                )
            try:
                next(requested.iterdir())
            except StopIteration:
                pass
            else:
                raise ExportError(
                    f"export destination changed during assembly: {requested}"
                )
            requested.rmdir()
            removed_empty_destination = True
        elif still_exists or requested.is_symlink():
            raise ExportError(f"export destination changed during assembly: {requested}")
        staging.rename(requested)
    except OSError as error:
        if removed_empty_destination and not requested.exists():
            requested.mkdir()
        raise ExportError(f"could not materialize export {requested}: {error}") from error
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return requested


def export_project(project_root: Path, destination: Path) -> Path:
    """Validate and atomically materialize one complete static site."""
    with compose_project(project_root, verify_package_contents=True) as composition:
        return export_composition(composition, destination)
