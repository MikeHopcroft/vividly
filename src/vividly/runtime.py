"""Runtime manifest loading and installed-package resolution."""

import hashlib
import json
import re
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from importlib import resources
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Literal, Never, cast

from .constants import (
    REFERENCE_RESOURCE_NAME,
    RUNTIME_RESOURCE_NAME,
    STARTER_PROJECT_PACKAGE,
)
from .project import (
    PackageRuntime,
    ProjectConfig,
    RepositoryRuntime,
)

RUNTIME_MANIFEST_NAME = "vividly-runtime.json"
SUPPORTED_COMPOSITION_APIS = frozenset({1})
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class RuntimeManifestError(ValueError):
    """A runtime manifest or its selected resources are invalid."""


@dataclass(frozen=True)
class RuntimeManifest:
    """A validated runtime manifest and its canonical identity."""

    schema: Literal[1]
    version: str
    composition_api: int
    files: dict[str, str]
    reference_files: dict[str, str]
    integrity: str


@dataclass(frozen=True)
class PackagedRuntime:
    """A verified runtime supplied by the installed Vividly distribution."""

    runtime_root: Path
    reference_root: Path
    distribution_version: str
    manifest: RuntimeManifest


@dataclass(frozen=True)
class SelectedRuntime:
    """A validated project-selected runtime held for one command."""

    source: Literal["package", "repository", "path"]
    runtime_root: Path
    reference_root: Path
    manifest: RuntimeManifest
    distribution_version: str | None = None
    commit: str | None = None


def _invalid(path: Path, detail: str) -> Never:
    raise RuntimeManifestError(f"invalid runtime manifest {path}: {detail}")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeManifestError(f"found duplicate key {key!r}")
        result[key] = value
    return result


def _mapping(value: object, path: Path, field: str) -> dict[object, object]:
    if not isinstance(value, dict):
        _invalid(path, f"`{field}` must be an object")
    return cast(dict[object, object], value)


def _string(value: object, path: Path, field: str) -> str:
    if not isinstance(value, str) or not value:
        _invalid(path, f"`{field}` must be a nonempty string")
    return value


def _file_map(
    value: object,
    path: Path,
    field: str,
    *,
    deployed: bool,
) -> dict[str, str]:
    mapping = _mapping(value, path, field)
    files: dict[str, str] = {}
    for raw_relative, raw_digest in mapping.items():
        if not isinstance(raw_relative, str):
            _invalid(path, f"`{field}` keys must be strings")
        relative = PurePosixPath(raw_relative)
        if (
            not raw_relative
            or "\\" in raw_relative
            or relative.is_absolute()
            or str(relative) != raw_relative
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            _invalid(path, f"`{field}` keys must be normalized relative paths")
        if deployed and raw_relative != "index.html" and not raw_relative.startswith("vividly/"):
            _invalid(path, f"`{field}` key {raw_relative!r} is not a deployed runtime path")
        if deployed and (
            raw_relative == "vividly/~dev" or raw_relative.startswith("vividly/~dev/")
        ):
            _invalid(path, f"`{field}` cannot declare the reserved development namespace")
        if deployed and raw_relative == RUNTIME_MANIFEST_NAME:
            _invalid(path, f"`{field}` cannot contain {RUNTIME_MANIFEST_NAME!r}")
        if not isinstance(raw_digest, str) or _SHA256_PATTERN.fullmatch(raw_digest) is None:
            _invalid(path, f"`{field}[{raw_relative!r}]` must be a lowercase SHA-256 digest")
        files[raw_relative] = raw_digest
    if deployed and "index.html" not in files:
        _invalid(path, "`files` must contain `index.html`")
    return dict(sorted(files.items()))


def load_runtime_manifest(runtime_root: Path) -> RuntimeManifest:
    """Load and strictly validate one canonical runtime manifest."""
    manifest_path = runtime_root / RUNTIME_MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RuntimeManifestError(f"runtime manifest is not a regular file: {manifest_path}")
    try:
        content = manifest_path.read_bytes()
        loaded = cast(
            object,
            json.loads(content, object_pairs_hook=_object_pairs),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeManifestError(
            f"cannot read runtime manifest {manifest_path}: {error}"
        ) from error
    except RuntimeManifestError as error:
        raise RuntimeManifestError(f"invalid runtime manifest {manifest_path}: {error}") from error

    document = _mapping(loaded, manifest_path, "document")
    expected_keys = {"schema", "version", "composition_api", "files", "reference_files"}
    keys = set(document)
    if not all(isinstance(key, str) for key in keys):
        _invalid(manifest_path, "top-level keys must be strings")
    missing = expected_keys - keys
    if missing:
        _invalid(manifest_path, f"missing `{sorted(missing)[0]}`")
    unknown = keys - expected_keys
    if unknown:
        _invalid(manifest_path, f"unknown key `{sorted(cast(set[str], unknown))[0]}`")

    schema = document["schema"]
    if not isinstance(schema, int) or isinstance(schema, bool) or schema != 1:
        _invalid(manifest_path, "`schema` must equal 1")
    composition_api = document["composition_api"]
    if not isinstance(composition_api, int) or isinstance(composition_api, bool):
        _invalid(manifest_path, "`composition_api` must be an integer")
    if composition_api not in SUPPORTED_COMPOSITION_APIS:
        supported = ", ".join(str(item) for item in sorted(SUPPORTED_COMPOSITION_APIS))
        _invalid(
            manifest_path,
            f"unsupported composition API {composition_api}; supported: {supported}",
        )

    canonical = (
        json.dumps(loaded, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()
    if content != canonical:
        _invalid(manifest_path, "manifest bytes are not canonical")

    return RuntimeManifest(
        schema=1,
        version=_string(document["version"], manifest_path, "version"),
        composition_api=composition_api,
        files=_file_map(document["files"], manifest_path, "files", deployed=True),
        reference_files=_file_map(
            document["reference_files"],
            manifest_path,
            "reference_files",
            deployed=False,
        ),
        integrity=f"sha256:{hashlib.sha256(content).hexdigest()}",
    )


def _regular_files(root: Path, *, omit: frozenset[str] = frozenset()) -> dict[str, Path]:
    if root.is_symlink() or not root.is_dir():
        raise RuntimeManifestError(f"runtime resource root is not a regular directory: {root}")
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise RuntimeManifestError(f"runtime resource is a symbolic link: {path}")
        if path.is_file() and relative not in omit:
            files[relative] = path
    return files


def _verify_files(
    root: Path,
    expected: dict[str, str],
    *,
    label: str,
    verify_contents: bool,
    omit: frozenset[str] = frozenset(),
) -> None:
    actual = _regular_files(root, omit=omit)
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise RuntimeManifestError(f"missing {label} file: {missing[0]}")
    additional = sorted(set(actual) - set(expected))
    if additional:
        raise RuntimeManifestError(f"unexpected {label} file: {additional[0]}")
    if verify_contents:
        for relative, digest in expected.items():
            actual_digest = hashlib.sha256(actual[relative].read_bytes()).hexdigest()
            if actual_digest != digest:
                raise RuntimeManifestError(f"{label} file failed integrity check: {relative}")


@contextmanager
def packaged_runtime(
    *,
    verify_runtime_contents: bool = False,
    verify_reference_contents: bool = False,
) -> Generator[PackagedRuntime, None, None]:
    """Resolve and verify the runtime carried by the installed distribution."""
    package = resources.files(STARTER_PROJECT_PACKAGE)
    with (
        resources.as_file(package.joinpath(RUNTIME_RESOURCE_NAME)) as runtime_root,
        resources.as_file(package.joinpath(REFERENCE_RESOURCE_NAME)) as reference_root,
    ):
        manifest = load_runtime_manifest(runtime_root)
        _verify_files(
            runtime_root,
            manifest.files,
            label="runtime",
            verify_contents=verify_runtime_contents,
            omit=frozenset({RUNTIME_MANIFEST_NAME}),
        )
        _verify_files(
            reference_root,
            manifest.reference_files,
            label="reference",
            verify_contents=verify_reference_contents,
        )
        yield PackagedRuntime(
            runtime_root=runtime_root,
            reference_root=reference_root,
            distribution_version=version("vividly"),
            manifest=manifest,
        )


def reference_files(
    reference_root: Path,
    *,
    exclude_generated_metadata: bool = False,
) -> dict[str, Path]:
    """Return safe regular reference files keyed by normalized relative path."""
    files = _regular_files(reference_root)
    if exclude_generated_metadata:
        files.pop("runtime.json", None)
        return files
    if "runtime.json" in files:
        raise RuntimeManifestError(
            f"reference source contains reserved generated path: {reference_root / 'runtime.json'}"
        )
    return files


def _package_mismatch(
    configured: PackageRuntime,
    *,
    available_distribution: str,
    available_framework: str | None,
    detail: str,
) -> RuntimeManifestError:
    framework = available_framework if available_framework is not None else "unavailable"
    return RuntimeManifestError(
        f"selected package runtime is unavailable: {detail}\n"
        f"  required distribution: {configured.distribution_version}\n"
        f"  available distribution: {available_distribution}\n"
        f"  required framework: {configured.version}\n"
        f"  available framework: {framework}\n"
        f"Install it separately with: "
        f"python -m pip install 'vividly=={configured.distribution_version}'\n"
        "Installation requires package access; an offline environment must provide "
        "the exact distribution separately."
    )


def _editable_runtime_root(project_root: Path, relative: PurePosixPath) -> Path:
    canonical_project = project_root.resolve()
    current = canonical_project
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeManifestError(f"runtime path contains a symbolic link: {current}")
    try:
        resolved = current.resolve(strict=True)
    except OSError as error:
        raise RuntimeManifestError(f"cannot resolve runtime root {current}: {error}") from error
    if not resolved.is_dir() or not resolved.is_relative_to(canonical_project):
        raise RuntimeManifestError(
            f"runtime root is not a project-contained directory: {resolved}"
        )
    return resolved


@contextmanager
def selected_runtime(
    project_root: Path,
    config: ProjectConfig,
    *,
    verify_runtime_contents: bool = False,
    verify_reference_contents: bool = False,
) -> Generator[SelectedRuntime, None, None]:
    """Resolve and validate the runtime selected by project configuration."""
    configured = config.runtime
    if isinstance(configured, PackageRuntime):
        available_distribution = version("vividly")
        with ExitStack() as stack:
            try:
                packaged = stack.enter_context(
                    packaged_runtime(
                        verify_runtime_contents=verify_runtime_contents,
                        verify_reference_contents=verify_reference_contents,
                    )
                )
            except RuntimeManifestError as error:
                raise _package_mismatch(
                    configured,
                    available_distribution=available_distribution,
                    available_framework=None,
                    detail=str(error),
                ) from error
            manifest = packaged.manifest
            if configured.distribution_version != available_distribution:
                raise _package_mismatch(
                    configured,
                    available_distribution=available_distribution,
                    available_framework=manifest.version,
                    detail="distribution version does not match",
                )
            if configured.version != manifest.version:
                raise _package_mismatch(
                    configured,
                    available_distribution=available_distribution,
                    available_framework=manifest.version,
                    detail="framework version does not match",
                )
            if configured.integrity != manifest.integrity:
                raise _package_mismatch(
                    configured,
                    available_distribution=available_distribution,
                    available_framework=manifest.version,
                    detail="runtime manifest identity does not match",
                )
            yield SelectedRuntime(
                source="package",
                runtime_root=packaged.runtime_root,
                reference_root=packaged.reference_root,
                manifest=manifest,
                distribution_version=packaged.distribution_version,
            )
        return

    runtime_root = _editable_runtime_root(project_root, configured.path)
    reference_root = runtime_root.parent / REFERENCE_RESOURCE_NAME
    if reference_root.is_symlink() or not reference_root.is_dir():
        raise RuntimeManifestError(
            f"editable reference root is not a regular directory: {reference_root}"
        )
    if not reference_root.resolve().is_relative_to(project_root.resolve()):
        raise RuntimeManifestError(
            f"editable reference root escapes the project: {reference_root}"
        )
    manifest = load_runtime_manifest(runtime_root)
    if isinstance(configured, RepositoryRuntime):
        if configured.version != manifest.version:
            raise RuntimeManifestError(
                f"repository runtime version mismatch: configured {configured.version}, "
                f"manifest {manifest.version}"
            )
        yield SelectedRuntime(
            source="repository",
            runtime_root=runtime_root,
            reference_root=reference_root,
            manifest=manifest,
            commit=configured.commit,
        )
        return

    if configured.upstream_version != manifest.version:
        raise RuntimeManifestError(
            f"path runtime version mismatch: configured {configured.upstream_version}, "
            f"manifest {manifest.version}"
        )
    yield SelectedRuntime(
        source="path",
        runtime_root=runtime_root,
        reference_root=reference_root,
        manifest=manifest,
        commit=configured.upstream_commit,
    )
