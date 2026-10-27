"""Strict publishing configuration loading and target resolution."""

import re
from collections.abc import Callable, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Never, cast
from urllib.parse import urlsplit

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

PUBLISH_CONFIG_NAME = "vividly.publish.yaml"
_TARGET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_compose_yaml = cast(Callable[[str], Node | None], vars(yaml)["compose"])
_load_yaml = cast(Callable[[str], object], vars(yaml)["safe_load"])


class PublishingConfigError(ValueError):
    """Publishing configuration is absent or invalid."""


@dataclass(frozen=True)
class GitHubPagesTarget:
    """One branch-root GitHub Pages publication target."""

    name: str
    provider: Literal["github-pages"]
    remote: str
    branch: str
    expected_url: str | None
    custom_domain: str | None


@dataclass(frozen=True)
class PublishingConfig:
    """Validated contents of vividly.publish.yaml."""

    schema: Literal[1]
    default: str | None
    targets: dict[str, GitHubPagesTarget]


def _invalid(path: Path, detail: str) -> Never:
    raise PublishingConfigError(f"invalid publishing configuration {path}: {detail}")


def _reject_duplicate_keys(node: Node) -> None:
    if isinstance(node, MappingNode):
        keys: set[str] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode):
                if key_node.value in keys:
                    raise PublishingConfigError(f"found duplicate key {key_node.value!r}")
                keys.add(key_node.value)
            _reject_duplicate_keys(key_node)
            _reject_duplicate_keys(value_node)
    elif isinstance(node, SequenceNode):
        for item in node.value:
            _reject_duplicate_keys(item)


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
    if "\n" in value or "\r" in value:
        _invalid(path, f"`{field}` cannot contain a line ending")
    return value


def _target_name(value: object, path: Path, field: str) -> str:
    name = _string(value, path, field)
    if _TARGET_NAME.fullmatch(name) is None:
        _invalid(
            path,
            f"`{field}` must begin with an ASCII letter or digit and contain only "
            "ASCII letters, digits, `.`, `_`, or `-`",
        )
    return name


def _expected_url(value: object, path: Path, field: str) -> str:
    text = _string(value, path, field)
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as error:
        _invalid(path, f"`{field}` is not a valid URL: {error}")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        _invalid(
            path,
            f"`{field}` must be an absolute HTTPS URL without user information, "
            "query, or fragment",
        )
    del port
    return text


def _custom_domain(value: object, path: Path, field: str) -> str:
    domain = _string(value, path, field).lower()
    if len(domain) > 253 or domain.endswith(".") or "*" in domain:
        _invalid(path, f"`{field}` must be an ASCII DNS name without a trailing dot")
    try:
        domain.encode("ascii")
    except UnicodeEncodeError:
        _invalid(path, f"`{field}` must be an ASCII DNS name")
    labels = domain.split(".")
    if len(labels) < 2 or any(_DNS_LABEL.fullmatch(label) is None for label in labels):
        _invalid(path, f"`{field}` must be an ASCII DNS name without a scheme, path, or port")
    return domain


def _target(value: object, path: Path, name: str) -> GitHubPagesTarget:
    field = f"targets.{name}"
    target = _mapping(value, path, field)
    _validate_keys(
        target,
        path,
        field,
        {"provider"},
        {"remote", "branch", "expected_url", "custom_domain"},
    )
    provider = _string(target["provider"], path, f"{field}.provider")
    if provider != "github-pages":
        _invalid(path, f"`{field}.provider` must equal `github-pages`")
    expected = target.get("expected_url")
    domain = target.get("custom_domain")
    return GitHubPagesTarget(
        name=name,
        provider="github-pages",
        remote=_string(target.get("remote", "origin"), path, f"{field}.remote"),
        branch=_string(target.get("branch", "gh-pages"), path, f"{field}.branch"),
        expected_url=(
            _expected_url(expected, path, f"{field}.expected_url")
            if expected is not None
            else None
        ),
        custom_domain=(
            _custom_domain(domain, path, f"{field}.custom_domain")
            if domain is not None
            else None
        ),
    )


def load_publishing_config(project_root: Path) -> PublishingConfig:
    """Load and strictly validate one project's publishing configuration."""
    path = project_root / PUBLISH_CONFIG_NAME
    if path.is_symlink() or not path.is_file():
        raise PublishingConfigError(f"publishing configuration is not a regular file: {path}")
    try:
        content = path.read_text(encoding="utf-8")
        node = _compose_yaml(content)
        if node is not None:
            _reject_duplicate_keys(node)
        loaded = _load_yaml(content)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise PublishingConfigError(
            f"cannot read publishing configuration {path}: {error}"
        ) from error
    except PublishingConfigError as error:
        raise PublishingConfigError(f"invalid publishing configuration {path}: {error}") from error

    document = _mapping(loaded, path, "document")
    _validate_keys(document, path, "document", {"schema", "targets"}, {"default"})
    schema = document["schema"]
    if not isinstance(schema, int) or isinstance(schema, bool) or schema != 1:
        _invalid(path, "`schema` must equal 1")
    raw_targets = _mapping(document["targets"], path, "targets")
    if not raw_targets:
        _invalid(path, "`targets` must not be empty")
    targets: dict[str, GitHubPagesTarget] = {}
    for raw_name, raw_target in raw_targets.items():
        name = _target_name(raw_name, path, "targets key")
        targets[name] = _target(raw_target, path, name)

    raw_default = document.get("default")
    default = (
        _target_name(raw_default, path, "default")
        if raw_default is not None
        else None
    )
    if default is not None and default not in targets:
        _invalid(path, f"`default` names unknown target `{default}`")
    if default is None and len(targets) > 1:
        _invalid(path, "`default` is required when multiple targets are configured")
    return PublishingConfig(schema=1, default=default, targets=targets)


def resolve_target(config: PublishingConfig, requested: str | None) -> GitHubPagesTarget:
    """Resolve an explicit, default, or sole publication target."""
    name = requested if requested is not None else config.default
    if name is None:
        name = next(iter(config.targets))
    target = config.targets.get(name)
    if target is None:
        raise PublishingConfigError(f"publishing target is not configured: {name}")
    return target
