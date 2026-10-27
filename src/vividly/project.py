"""Project configuration loading and validation."""

import re
from collections.abc import Callable, Set
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Never, cast

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from .constants import BASELINE_NAME, PROJECT_CONFIG_NAME

_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_COMMIT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_compose_yaml = cast(Callable[[str], Node | None], vars(yaml)["compose"])
_load_yaml = cast(Callable[[str], object], vars(yaml)["safe_load"])


class ProjectConfigError(ValueError):
    """A project configuration cannot be loaded safely."""


def _reject_duplicate_keys(node: Node) -> None:
    """Reject duplicate scalar keys in every YAML mapping."""
    if isinstance(node, MappingNode):
        keys: set[str] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode):
                if key_node.value in keys:
                    raise ProjectConfigError(f"found duplicate key {key_node.value!r}")
                keys.add(key_node.value)
            _reject_duplicate_keys(key_node)
            _reject_duplicate_keys(value_node)
    elif isinstance(node, SequenceNode):
        for item in node.value:
            _reject_duplicate_keys(item)


@dataclass(frozen=True)
class PackageRuntime:
    """An exact runtime supplied by an installed Vividly distribution."""

    source: Literal["package"]
    distribution_version: str
    version: str
    integrity: str


@dataclass(frozen=True)
class RepositoryRuntime:
    """An editable runtime in the Vividly repository."""

    source: Literal["repository"]
    path: PurePosixPath
    version: str
    commit: str


@dataclass(frozen=True)
class PathRuntime:
    """An editable, ejected runtime owned by the project."""

    source: Literal["path"]
    path: PurePosixPath
    upstream_version: str
    upstream_commit: str | None


type RuntimeConfig = PackageRuntime | RepositoryRuntime | PathRuntime


@dataclass(frozen=True)
class ProjectConfig:
    """Validated contents of vividly.yaml."""

    schema: Literal[1]
    runtime: RuntimeConfig


def _invalid(path: Path, detail: str) -> Never:
    raise ProjectConfigError(f"invalid project configuration {path}: {detail}")


def _mapping(value: object, path: Path, field: str) -> dict[object, object]:
    if not isinstance(value, dict):
        _invalid(path, f"`{field}` must be a mapping")
    return cast(dict[object, object], value)


def _validate_keys(
    value: dict[object, object],
    path: Path,
    field: str,
    required: Set[str],
    optional: Set[str] = frozenset(),
) -> None:
    keys = set(value)
    if not all(isinstance(key, str) for key in keys):
        _invalid(path, f"`{field}` keys must be strings")
    missing = required - keys
    if missing:
        _invalid(path, f"`{field}` is missing `{sorted(missing)[0]}`")
    unknown = keys - required - optional
    if unknown:
        _invalid(path, f"`{field}` contains unknown key `{sorted(cast(set[str], unknown))[0]}`")


def _string(value: object, path: Path, field: str) -> str:
    if not isinstance(value, str) or not value:
        _invalid(path, f"`{field}` must be a nonempty string")
    return value


def _relative_path(value: object, path: Path, field: str) -> PurePosixPath:
    text = _string(value, path, field)
    if "\\" in text:
        _invalid(path, f"`{field}` must use `/` separators")
    relative = PurePosixPath(text)
    if relative.is_absolute() or str(relative) != text or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        _invalid(path, f"`{field}` must be a normalized project-relative path")
    return relative


def _commit(value: object, path: Path, field: str) -> str:
    commit = _string(value, path, field)
    if _COMMIT_PATTERN.fullmatch(commit) is None:
        _invalid(path, f"`{field}` must be a full lowercase hexadecimal commit ID")
    return commit


def _runtime_config(value: object, path: Path) -> RuntimeConfig:
    runtime = _mapping(value, path, "runtime")
    source = _string(runtime.get("source"), path, "runtime.source")

    if source == "package":
        _validate_keys(
            runtime,
            path,
            "runtime",
            {"source", "distribution_version", "version", "integrity"},
        )
        integrity = _string(runtime["integrity"], path, "runtime.integrity")
        if _SHA256_PATTERN.fullmatch(integrity) is None:
            _invalid(path, "`runtime.integrity` must be `sha256:` plus 64 lowercase hex digits")
        return PackageRuntime(
            source="package",
            distribution_version=_string(
                runtime["distribution_version"],
                path,
                "runtime.distribution_version",
            ),
            version=_string(runtime["version"], path, "runtime.version"),
            integrity=integrity,
        )

    if source == "repository":
        _validate_keys(runtime, path, "runtime", {"source", "path", "version", "commit"})
        return RepositoryRuntime(
            source="repository",
            path=_relative_path(runtime["path"], path, "runtime.path"),
            version=_string(runtime["version"], path, "runtime.version"),
            commit=_commit(runtime["commit"], path, "runtime.commit"),
        )

    if source == "path":
        _validate_keys(
            runtime,
            path,
            "runtime",
            {"source", "path", "upstream_version"},
            {"upstream_commit"},
        )
        upstream_commit = runtime.get("upstream_commit")
        return PathRuntime(
            source="path",
            path=_relative_path(runtime["path"], path, "runtime.path"),
            upstream_version=_string(
                runtime["upstream_version"],
                path,
                "runtime.upstream_version",
            ),
            upstream_commit=(
                _commit(upstream_commit, path, "runtime.upstream_commit")
                if upstream_commit is not None
                else None
            ),
        )

    _invalid(path, "`runtime.source` must be `package`, `repository`, or `path`")


def load_project_config(project_root: Path) -> ProjectConfig:
    """Load and strictly validate a project's vividly.yaml."""
    config_path = project_root / PROJECT_CONFIG_NAME
    if not config_path.exists():
        baseline_path = project_root / BASELINE_NAME
        if baseline_path.exists() or baseline_path.is_symlink():
            raise ProjectConfigError(
                f"unsupported Vividly project layout at {project_root}: "
                f"{BASELINE_NAME} requires reprovisioning"
            )
        raise ProjectConfigError(f"project configuration not found: {config_path}")
    if config_path.is_symlink() or not config_path.is_file():
        raise ProjectConfigError(f"project configuration is not a regular file: {config_path}")

    try:
        content = config_path.read_text(encoding="utf-8")
        node = _compose_yaml(content)
        if node is not None:
            _reject_duplicate_keys(node)
        loaded = _load_yaml(content)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ProjectConfigError(
            f"cannot read project configuration {config_path}: {error}"
        ) from error

    document = _mapping(loaded, config_path, "document")
    _validate_keys(document, config_path, "document", {"schema", "runtime"})
    if document["schema"] != 1:
        _invalid(config_path, "`schema` must equal 1")
    return ProjectConfig(schema=1, runtime=_runtime_config(document["runtime"], config_path))
