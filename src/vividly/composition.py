"""Validated virtual-site composition independent of HTTP."""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal

from .constants import DEFAULT_SITE_ROOT
from .dependencies import (
    DependencyConfigError,
    DependencySelection,
    combine_dependencies,
    load_catalog_dependencies,
    load_runtime_dependencies,
)
from .project import load_project_config
from .runtime import RUNTIME_MANIFEST_NAME, SelectedRuntime, selected_runtime

type FileOwner = Literal["author", "runtime"]


class CompositionError(ValueError):
    """Author and runtime sources cannot form a safe virtual site."""


@dataclass(frozen=True)
class ComposedFile:
    """One deployed URL and its owning physical source file."""

    url_path: PurePosixPath
    source_path: Path
    owner: FileOwner


@dataclass(frozen=True)
class Composition:
    """An immutable mapping for one validated logical static site."""

    project_root: Path
    author_root: Path
    runtime: SelectedRuntime
    dependencies: Mapping[str, DependencySelection]
    files: Mapping[PurePosixPath, ComposedFile]


def _validate_author_root(project_root: Path) -> Path:
    author_root = project_root / DEFAULT_SITE_ROOT
    if author_root.is_symlink() or not author_root.is_dir():
        raise CompositionError(f"author root is not a regular directory: {author_root}")
    catalog_path = author_root / "catalog.yaml"
    if catalog_path.is_symlink() or not catalog_path.is_file():
        raise CompositionError(f"project catalog is not a regular file: {catalog_path}")
    for reserved in (author_root / "index.html", author_root / "vividly"):
        if reserved.exists() or reserved.is_symlink():
            relative = reserved.relative_to(author_root).as_posix()
            raise CompositionError(f"author path collides with runtime ownership: /{relative}")
    return author_root.resolve()


def _regular_files(root: Path, *, omit: frozenset[str] = frozenset()) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise CompositionError(f"source tree contains a symbolic link: {path}")
        if path.is_file() and relative not in omit:
            if "\\" in relative:
                raise CompositionError(f"source path is not a normalized URL path: {path}")
            files[relative] = path
    return files


def _runtime_files(runtime: SelectedRuntime) -> dict[str, Path]:
    if runtime.source == "package":
        return {
            relative: runtime.runtime_root / relative
            for relative in runtime.manifest.files
        }

    files = _regular_files(
        runtime.runtime_root,
        omit=frozenset({RUNTIME_MANIFEST_NAME}),
    )
    for relative in files:
        if relative != "index.html" and not relative.startswith("vividly/"):
            raise CompositionError(
                f"editable runtime file has no deployed runtime URL: {relative}"
            )
        if relative == "vividly/~dev" or relative.startswith("vividly/~dev/"):
            raise CompositionError(
                f"editable runtime occupies the reserved development namespace: {relative}"
            )
    if "index.html" not in files:
        raise CompositionError(
            f"editable runtime is missing required shell: {runtime.runtime_root / 'index.html'}"
        )
    return files


def _validate_disjoint_roots(author_root: Path, runtime_root: Path) -> None:
    canonical_runtime = runtime_root.resolve()
    if (
        canonical_runtime == author_root
        or canonical_runtime.is_relative_to(author_root)
        or author_root.is_relative_to(canonical_runtime)
    ):
        raise CompositionError(
            f"author and runtime roots overlap: {author_root} and {canonical_runtime}"
        )


def _add_file(
    files: dict[PurePosixPath, ComposedFile],
    relative: str,
    source_path: Path,
    owner: FileOwner,
) -> None:
    url_path = PurePosixPath("/") / relative
    if url_path in files:
        existing = files[url_path]
        raise CompositionError(
            f"deployed URL collision at {url_path}: "
            f"{existing.source_path} and {source_path}"
        )
    files[url_path] = ComposedFile(
        url_path=url_path,
        source_path=source_path,
        owner=owner,
    )


@contextmanager
def compose_project(
    project_root: Path,
    *,
    verify_package_contents: bool = False,
) -> Generator[Composition, None, None]:
    """Validate and compose one project's author and selected runtime trees."""
    canonical_project = project_root.expanduser().resolve()
    config = load_project_config(canonical_project)
    author_root = _validate_author_root(canonical_project)
    try:
        catalog_dependencies = load_catalog_dependencies(author_root / "catalog.yaml")
    except DependencyConfigError as error:
        raise CompositionError(str(error)) from error

    with selected_runtime(
        canonical_project,
        config,
        verify_runtime_contents=verify_package_contents,
    ) as runtime:
        _validate_disjoint_roots(author_root, runtime.runtime_root)
        try:
            runtime_dependencies = load_runtime_dependencies(
                runtime.runtime_root,
                owner_identity=f"Vividly {runtime.manifest.version}",
            )
            dependencies = combine_dependencies(
                runtime_dependencies,
                catalog_dependencies,
            )
        except DependencyConfigError as error:
            raise CompositionError(str(error)) from error
        author_files = _regular_files(author_root)
        runtime_files = _runtime_files(runtime)
        files: dict[PurePosixPath, ComposedFile] = {}
        for relative, source_path in runtime_files.items():
            _add_file(files, relative, source_path, "runtime")
        for relative, source_path in author_files.items():
            _add_file(files, relative, source_path, "author")
        yield Composition(
            project_root=canonical_project,
            author_root=author_root,
            runtime=runtime,
            dependencies=dependencies,
            files=MappingProxyType(files),
        )
