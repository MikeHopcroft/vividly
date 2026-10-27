"""Validated project dependencies and persistent read-through storage."""

import hashlib
import http
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import IO, Literal, Never, cast
from urllib.parse import urljoin, urlsplit

import yaml

_AUTHOR_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_RESOURCE_PATH = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._~!$&'()+,;=@/-]*")
_CACHE_SCHEMA = 1
_MAX_RESOURCE_BYTES = 64 * 1024 * 1024
_FETCH_TIMEOUT_SECONDS = 15
RUNTIME_DEPENDENCY_PATH = PurePosixPath("vividly/dependencies.json")


class DependencyConfigError(ValueError):
    """A dependency table or effective mapping is invalid."""


class DependencyAcquisitionError(RuntimeError):
    """A dependency resource could not be acquired or stored."""


class DependencyCacheMiss(DependencyAcquisitionError):
    """A dependency resource is absent while acquisition is disabled."""


@dataclass(frozen=True)
class DependencyLoader:
    """One browser instantiation strategy."""

    type: Literal["module", "script", "stylesheet"]
    global_name: str | None = None


@dataclass(frozen=True)
class DependencySelection:
    """One effective logical dependency selection."""

    key: str
    base_url: str
    entry: PurePosixPath
    owner: Literal["runtime", "catalog"] = "catalog"
    owner_identity: str | None = None
    version: str | None = None
    project_url: str | None = None
    license: str | None = None
    sha256: str | None = None
    loader: DependencyLoader = DependencyLoader(type="module")


@dataclass(frozen=True)
class DependencyResource:
    """One complete dependency response."""

    content: bytes
    content_type: str


type DependencyCacheStatus = Literal[
    "valid",
    "missing",
    "invalid",
    "incomplete",
    "unreadable",
]


@dataclass(frozen=True)
class DependencyCacheRecord:
    """One observed dependency-cache resource."""

    key: str | None
    relative_path: PurePosixPath | None
    source_url: str | None
    status: DependencyCacheStatus
    size: int | None
    cached_at: datetime | None
    cache_path: Path


type DependencyAcquirer = Callable[[str], DependencyResource]


def dependency_relative_path(value: str) -> PurePosixPath | None:
    """Return a validated package-relative path, or None when invalid."""
    if _RESOURCE_PATH.fullmatch(value) is None or any(
        part in {"", ".", ".."} for part in value.split("/")
    ):
        return None
    return PurePosixPath(value)


def _invalid(path: Path, label: str, detail: str) -> Never:
    raise DependencyConfigError(f"invalid {label} {path}: {detail}")


def _mapping(
    value: object,
    path: Path,
    label: str,
    field: str,
) -> dict[object, object]:
    if not isinstance(value, dict):
        _invalid(path, label, f"`{field}` must be a mapping")
    return cast(dict[object, object], value)


def _validate_base_url(
    value: object,
    path: Path,
    label: str,
    field: str,
) -> str:
    if not isinstance(value, str) or not value.endswith("/"):
        _invalid(path, label, f"`{field}` must end with `/`")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        _invalid(path, label, f"`{field}` is invalid: {error}")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        _invalid(path, label, f"`{field}` must be a clean absolute HTTPS URL")
    return value


def _validate_https_url(
    value: object,
    path: Path,
    label: str,
    field: str,
) -> str:
    if not isinstance(value, str):
        _invalid(path, label, f"`{field}` must be a clean absolute HTTPS URL")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        _invalid(path, label, f"`{field}` is invalid: {error}")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        _invalid(path, label, f"`{field}` must be a clean absolute HTTPS URL")
    return value


def _validate_entry(
    value: object,
    path: Path,
    label: str,
    field: str,
) -> PurePosixPath:
    entry = dependency_relative_path(value) if isinstance(value, str) else None
    if entry is None:
        _invalid(path, label, f"`{field}` must be a normalized relative path")
    return entry


def _validate_catalog_selection(
    key: object,
    value: object,
    catalog_path: Path,
) -> DependencySelection:
    label = "dependency catalog"
    if not isinstance(key, str) or _AUTHOR_ID.fullmatch(key) is None:
        _invalid(catalog_path, label, f"invalid dependency key {key!r}")
    selection = _mapping(value, catalog_path, label, f"dependencies.{key}")
    keys = set(selection)
    if not all(isinstance(field, str) for field in keys):
        _invalid(catalog_path, label, f"`dependencies.{key}` keys must be strings")
    missing = {"baseUrl", "entry"} - keys
    if missing:
        _invalid(
            catalog_path,
            label,
            f"`dependencies.{key}` is missing `{sorted(missing)[0]}`",
        )
    unknown = keys - {"baseUrl", "entry"}
    if unknown:
        _invalid(
            catalog_path,
            label,
            f"`dependencies.{key}` contains unknown key `{sorted(cast(set[str], unknown))[0]}`",
        )
    field = f"dependencies.{key}"
    return DependencySelection(
        key=key,
        base_url=_validate_base_url(selection["baseUrl"], catalog_path, label, f"{field}.baseUrl"),
        entry=_validate_entry(selection["entry"], catalog_path, label, f"{field}.entry"),
    )


def load_catalog_dependencies(catalog_path: Path) -> Mapping[str, DependencySelection]:
    """Load the project-wide dependency selections from catalog.yaml."""
    try:
        loaded = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise DependencyConfigError(
            f"cannot read dependency catalog {catalog_path}: {error}"
        ) from error
    document = _mapping(loaded, catalog_path, "dependency catalog", "document")
    if "dependencies" not in document:
        return MappingProxyType({})
    raw_dependencies = document["dependencies"]
    dependencies = _mapping(
        raw_dependencies,
        catalog_path,
        "dependency catalog",
        "dependencies",
    )
    normalized: dict[str, DependencySelection] = {}
    for key, value in dependencies.items():
        selection = _validate_catalog_selection(key, value, catalog_path)
        normalized[selection.key] = selection
    return MappingProxyType(normalized)


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DependencyConfigError(f"found duplicate key {key!r}")
        result[key] = value
    return result


def _required_string(
    value: object,
    path: Path,
    field: str,
) -> str:
    if not isinstance(value, str) or not value:
        _invalid(path, "runtime dependency table", f"`{field}` must be a nonempty string")
    return value


def _validate_loader(
    value: object,
    path: Path,
    field: str,
) -> DependencyLoader:
    label = "runtime dependency table"
    loader = _mapping(value, path, label, field)
    raw_keys = set(loader)
    if not all(isinstance(key, str) for key in raw_keys):
        _invalid(path, label, f"`{field}` keys must be strings")
    keys = cast(set[str], raw_keys)
    loader_type = loader.get("type")
    if loader_type == "module":
        normalized_type: Literal["module", "script", "stylesheet"] = "module"
        expected = {"type"}
        global_name = None
    elif loader_type == "stylesheet":
        normalized_type = "stylesheet"
        expected = {"type"}
        global_name = None
    elif loader_type == "script":
        normalized_type = "script"
        expected = {"type", "global"}
        missing = expected - keys
        if missing:
            _invalid(path, label, f"`{field}` is missing `{sorted(missing)[0]}`")
        global_value = loader.get("global")
        if (
            not isinstance(global_value, str)
            or re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", global_value) is None
        ):
            _invalid(path, label, f"`{field}.global` must be a JavaScript identifier")
        global_name = global_value
    else:
        _invalid(path, label, f"`{field}.type` must be `module`, `script`, or `stylesheet`")
    missing = expected - keys
    if missing:
        _invalid(path, label, f"`{field}` is missing `{sorted(missing)[0]}`")
    unknown = keys - expected
    if unknown:
        _invalid(path, label, f"`{field}` contains unknown key `{sorted(unknown)[0]}`")
    return DependencyLoader(type=normalized_type, global_name=global_name)


def _validate_runtime_selection(
    key: object,
    value: object,
    path: Path,
    owner_identity: str,
) -> DependencySelection:
    label = "runtime dependency table"
    if not isinstance(key, str) or _AUTHOR_ID.fullmatch(key) is None:
        _invalid(path, label, f"invalid dependency key {key!r}")
    record = _mapping(value, path, label, f"dependencies.{key}")
    keys = set(record)
    if not all(isinstance(field, str) for field in keys):
        _invalid(path, label, f"`dependencies.{key}` keys must be strings")
    expected = {
        "version",
        "projectUrl",
        "baseUrl",
        "entry",
        "sha256",
        "license",
        "loader",
    }
    missing = expected - keys
    if missing:
        _invalid(path, label, f"`dependencies.{key}` is missing `{sorted(missing)[0]}`")
    unknown = keys - expected
    if unknown:
        _invalid(
            path,
            label,
            f"`dependencies.{key}` contains unknown key `{sorted(cast(set[str], unknown))[0]}`",
        )
    field = f"dependencies.{key}"
    sha256 = record["sha256"]
    if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        _invalid(path, label, f"`{field}.sha256` must be a lowercase SHA-256 digest")
    return DependencySelection(
        key=key,
        base_url=_validate_base_url(record["baseUrl"], path, label, f"{field}.baseUrl"),
        entry=_validate_entry(record["entry"], path, label, f"{field}.entry"),
        owner="runtime",
        owner_identity=owner_identity,
        version=_required_string(record["version"], path, f"{field}.version"),
        project_url=_validate_https_url(
            record["projectUrl"],
            path,
            label,
            f"{field}.projectUrl",
        ),
        license=_required_string(record["license"], path, f"{field}.license"),
        sha256=sha256,
        loader=_validate_loader(record["loader"], path, f"{field}.loader"),
    )


def load_runtime_dependencies(
    runtime_root: Path,
    *,
    owner_identity: str,
) -> Mapping[str, DependencySelection]:
    """Load the selected runtime's strictly validated built-in dependency table."""
    table_path = runtime_root / RUNTIME_DEPENDENCY_PATH
    if table_path.is_symlink() or not table_path.is_file():
        raise DependencyConfigError(f"runtime dependency table is not a regular file: {table_path}")
    try:
        content = table_path.read_bytes()
        loaded = cast(
            object,
            json.loads(content, object_pairs_hook=_object_pairs),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DependencyConfigError(
            f"cannot read runtime dependency table {table_path}: {error}"
        ) from error
    except DependencyConfigError as error:
        raise DependencyConfigError(
            f"invalid runtime dependency table {table_path}: {error}"
        ) from error
    document = _mapping(loaded, table_path, "runtime dependency table", "document")
    keys = set(document)
    if not all(isinstance(key, str) for key in keys):
        _invalid(table_path, "runtime dependency table", "top-level keys must be strings")
    expected = {"schema", "dependencies"}
    missing = expected - keys
    if missing:
        _invalid(
            table_path,
            "runtime dependency table",
            f"missing `{sorted(missing)[0]}`",
        )
    unknown = keys - expected
    if unknown:
        _invalid(
            table_path,
            "runtime dependency table",
            f"unknown key `{sorted(cast(set[str], unknown))[0]}`",
        )
    if document["schema"] != 1 or isinstance(document["schema"], bool):
        _invalid(table_path, "runtime dependency table", "`schema` must equal 1")
    raw_dependencies = _mapping(
        document["dependencies"],
        table_path,
        "runtime dependency table",
        "dependencies",
    )
    normalized: dict[str, DependencySelection] = {}
    for key, value in raw_dependencies.items():
        selection = _validate_runtime_selection(key, value, table_path, owner_identity)
        normalized[selection.key] = selection
    return MappingProxyType(normalized)


def combine_dependencies(
    runtime: Mapping[str, DependencySelection],
    catalog: Mapping[str, DependencySelection],
) -> Mapping[str, DependencySelection]:
    """Combine non-overlapping runtime and catalog dependency tables."""
    collisions = sorted(set(runtime) & set(catalog))
    if collisions:
        key = collisions[0]
        owner = runtime[key].owner_identity or "the selected runtime"
        raise DependencyConfigError(
            f'catalog dependency "{key}" conflicts with dependency selected by {owner}'
        )
    return MappingProxyType(dict(sorted({**runtime, **catalog}.items())))


def default_dependency_cache_root() -> Path:
    """Return the platform user-cache location for dependency resources."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "vividly" / "dependencies-v1"
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "Vividly" / "Cache" / "dependencies-v1"
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache) if xdg_cache else Path.home() / ".cache"
    return base / "vividly" / "dependencies-v1"


def inspect_dependency_cache(
    root: Path,
    selections: Mapping[str, DependencySelection] | None = None,
) -> tuple[DependencyCacheRecord, ...]:
    """Inspect project-selected or global cache resources without mutation."""
    cache_root = root.expanduser()
    records: list[DependencyCacheRecord]
    if selections is None:
        records = _inspect_all_cache_resources(cache_root)
    else:
        records = []
        for selection in selections.values():
            records.extend(_inspect_selected_cache_resources(cache_root, selection))
    return tuple(sorted(records, key=_cache_record_sort_key))


def clear_dependency_cache(root: Path) -> bool:
    """Remove the complete cache root, returning whether it existed."""
    cache_root = root.expanduser()
    if cache_root.is_symlink():
        raise DependencyAcquisitionError(
            f"dependency cache root is a symbolic link: {cache_root}"
        )
    if not cache_root.exists():
        return False
    if not cache_root.is_dir():
        raise DependencyAcquisitionError(
            f"dependency cache root is not a directory: {cache_root}"
        )
    resolved = cache_root.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise DependencyAcquisitionError(
            f"refusing to clear unsafe dependency cache root: {resolved}"
        )
    shutil.rmtree(resolved)
    return True


def _inspect_all_cache_resources(root: Path) -> list[DependencyCacheRecord]:
    if not root.exists():
        return []
    try:
        base_roots = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError:
        return [_unreadable_cache_record(root)]
    records: list[DependencyCacheRecord] = []
    for base_root in base_roots:
        try:
            resource_roots = (
                sorted(base_root.iterdir(), key=lambda path: path.name)
                if base_root.is_dir()
                else [base_root]
            )
        except OSError:
            records.append(_unreadable_cache_record(base_root))
            continue
        records.extend(_inspect_cache_resource(path, None) for path in resource_roots)
    return records


def _inspect_selected_cache_resources(
    root: Path,
    selection: DependencySelection,
) -> list[DependencyCacheRecord]:
    base_key = hashlib.sha256(selection.base_url.encode()).hexdigest()
    base_root = root / base_key
    records: list[DependencyCacheRecord] = []
    if base_root.exists():
        try:
            resource_roots = (
                sorted(base_root.iterdir(), key=lambda path: path.name)
                if base_root.is_dir()
                else [base_root]
            )
        except OSError:
            records.append(_unreadable_cache_record(base_root, selection.key))
        else:
            records.extend(
                _inspect_cache_resource(resource_root, selection)
                for resource_root in resource_roots
            )
    entry_url = urljoin(selection.base_url, selection.entry.as_posix())
    if not any(
        record.status == "valid" and record.source_url == entry_url
        for record in records
    ):
        records.append(
            DependencyCacheRecord(
                key=selection.key,
                relative_path=selection.entry,
                source_url=entry_url,
                status="missing",
                size=None,
                cached_at=None,
                cache_path=base_root
                / hashlib.sha256(entry_url.encode()).hexdigest(),
            )
        )
    return records


def _inspect_cache_resource(
    resource_root: Path,
    selection: DependencySelection | None,
) -> DependencyCacheRecord:
    key = selection.key if selection is not None else None
    content_path = resource_root / "content"
    metadata_path = resource_root / "metadata.json"
    try:
        content_exists = content_path.is_file()
        metadata_exists = metadata_path.is_file()
    except OSError:
        return _unreadable_cache_record(resource_root, key)
    if not content_exists or not metadata_exists:
        size: int | None = None
        cached_at: datetime | None = None
        source_url: str | None = None
        try:
            if content_exists:
                size = content_path.stat().st_size
            if metadata_exists:
                loaded_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                cached_at = datetime.fromtimestamp(
                    metadata_path.stat().st_mtime,
                    UTC,
                )
                if isinstance(loaded_metadata, dict):
                    source_value = cast(dict[str, object], loaded_metadata).get(
                        "source_url"
                    )
                    if isinstance(source_value, str):
                        source_url = source_value
        except (OSError, UnicodeError):
            return _unreadable_cache_record(resource_root, key)
        except json.JSONDecodeError:
            pass
        relative_path = (
            dependency_relative_path(source_url[len(selection.base_url) :])
            if selection is not None
            and source_url is not None
            and source_url.startswith(selection.base_url)
            else None
        )
        return DependencyCacheRecord(
            key=key,
            relative_path=relative_path,
            source_url=source_url,
            status="incomplete",
            size=size,
            cached_at=cached_at,
            cache_path=resource_root,
        )
    try:
        content = content_path.read_bytes()
        metadata_text = metadata_path.read_text(encoding="utf-8")
        cached_at = datetime.fromtimestamp(metadata_path.stat().st_mtime, UTC)
    except (OSError, UnicodeError):
        return _unreadable_cache_record(resource_root, key)
    try:
        loaded_metadata = json.loads(metadata_text)
    except json.JSONDecodeError:
        return DependencyCacheRecord(
            key=key,
            relative_path=None,
            source_url=None,
            status="invalid",
            size=len(content),
            cached_at=cached_at,
            cache_path=resource_root,
        )
    metadata = cast(dict[str, object], loaded_metadata) if isinstance(loaded_metadata, dict) else {}
    source_value = metadata.get("source_url")
    source_url = source_value if isinstance(source_value, str) else None
    relative_path: PurePosixPath | None = None
    if (
        selection is not None
        and source_url is not None
        and source_url.startswith(selection.base_url)
    ):
        relative_path = dependency_relative_path(source_url[len(selection.base_url) :])
    valid = (
        bool(metadata)
        and metadata.get("schema") == _CACHE_SCHEMA
        and source_url is not None
        and resource_root.name == hashlib.sha256(source_url.encode()).hexdigest()
        and metadata.get("size") == len(content)
        and metadata.get("sha256") == hashlib.sha256(content).hexdigest()
        and isinstance(metadata.get("content_type"), str)
    )
    if selection is not None:
        valid = (
            valid
            and relative_path is not None
            and (
                selection.sha256 is None
                or relative_path != selection.entry
                or hashlib.sha256(content).hexdigest() == selection.sha256
            )
        )
    return DependencyCacheRecord(
        key=key,
        relative_path=relative_path,
        source_url=source_url,
        status="valid" if valid else "invalid",
        size=len(content),
        cached_at=cached_at,
        cache_path=resource_root,
    )


def _unreadable_cache_record(
    cache_path: Path,
    key: str | None = None,
) -> DependencyCacheRecord:
    return DependencyCacheRecord(
        key=key,
        relative_path=None,
        source_url=None,
        status="unreadable",
        size=None,
        cached_at=None,
        cache_path=cache_path,
    )


def _cache_record_sort_key(
    record: DependencyCacheRecord,
) -> tuple[str, str, str, str]:
    return (
        record.key or "",
        record.source_url or "",
        record.status,
        str(record.cache_path),
    )


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        del req, fp, code, msg, headers, newurl
        return None


def acquire_dependency(url: str) -> DependencyResource:
    """Fetch one complete dependency resource without following redirects."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Vividly dependency cache"},
    )
    opener = urllib.request.build_opener(_RejectRedirects)
    try:
        with opener.open(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            if response.status != http.HTTPStatus.OK:
                raise DependencyAcquisitionError(
                    f"dependency acquisition returned HTTP {response.status}: {url}"
                )
            content_length = response.headers.get("Content-Length")
            declared_length: int | None = None
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError as error:
                    raise DependencyAcquisitionError(
                        f"dependency response has an invalid Content-Length: {url}"
                    ) from error
                if declared_length < 0 or declared_length > _MAX_RESOURCE_BYTES:
                    raise DependencyAcquisitionError(f"dependency has an invalid size: {url}")
            content = response.read(_MAX_RESOURCE_BYTES + 1)
            if len(content) > _MAX_RESOURCE_BYTES:
                raise DependencyAcquisitionError(
                    f"dependency exceeds {_MAX_RESOURCE_BYTES} bytes: {url}"
                )
            if declared_length is not None and len(content) != declared_length:
                raise DependencyAcquisitionError(f"dependency response is incomplete: {url}")
            return DependencyResource(
                content=content,
                content_type=response.headers.get_content_type(),
            )
    except DependencyAcquisitionError:
        raise
    except (OSError, http.client.HTTPException, urllib.error.URLError) as error:
        raise DependencyAcquisitionError(f"cannot acquire dependency {url}: {error}") from error


class DependencyCache:
    """Persistent cache for resources below validated dependency bases."""

    def __init__(
        self,
        root: Path,
        *,
        acquirer: DependencyAcquirer = acquire_dependency,
        cache_only: bool = False,
    ) -> None:
        self._root = root
        self._acquirer = acquirer
        self._cache_only = cache_only
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def get(
        self,
        selection: DependencySelection,
        relative_path: PurePosixPath,
    ) -> DependencyResource:
        """Return a cached resource, acquiring and storing it on a miss."""
        source_url = urljoin(selection.base_url, relative_path.as_posix())
        if not source_url.startswith(selection.base_url):
            raise DependencyAcquisitionError(
                f"dependency path escapes its configured base: {relative_path}"
            )
        resource_key = hashlib.sha256(source_url.encode()).hexdigest()
        base_key = hashlib.sha256(selection.base_url.encode()).hexdigest()
        resource_root = self._root / base_key / resource_key
        lock = self._resource_lock(f"{base_key}/{resource_key}")
        with lock:
            cached = self._read(resource_root, source_url)
            if cached is not None and self._has_expected_integrity(
                selection,
                relative_path,
                cached,
            ):
                return cached
            if self._cache_only:
                raise DependencyCacheMiss(f"dependency is not cached: {source_url}")
            acquired = self._acquirer(source_url)
            if not self._has_expected_integrity(selection, relative_path, acquired):
                raise DependencyAcquisitionError(f"dependency failed integrity check: {source_url}")
            self._store(resource_root, source_url, acquired)
            return acquired

    @staticmethod
    def _has_expected_integrity(
        selection: DependencySelection,
        relative_path: PurePosixPath,
        resource: DependencyResource,
    ) -> bool:
        if selection.sha256 is None or relative_path != selection.entry:
            return True
        return hashlib.sha256(resource.content).hexdigest() == selection.sha256

    def _resource_lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())

    def _read(self, root: Path, source_url: str) -> DependencyResource | None:
        content_path = root / "content"
        metadata_path = root / "metadata.json"
        if not content_path.is_file() or not metadata_path.is_file():
            return None
        try:
            content = content_path.read_bytes()
            loaded_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(loaded_metadata, dict):
            return None
        metadata = cast(dict[str, object], loaded_metadata)
        if (
            metadata.get("schema") != _CACHE_SCHEMA
            or metadata.get("source_url") != source_url
            or metadata.get("size") != len(content)
            or metadata.get("sha256") != hashlib.sha256(content).hexdigest()
            or not isinstance(metadata.get("content_type"), str)
        ):
            return None
        return DependencyResource(
            content=content,
            content_type=cast(str, metadata["content_type"]),
        )

    def _store(
        self,
        root: Path,
        source_url: str,
        resource: DependencyResource,
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        metadata = {
            "content_type": resource.content_type,
            "schema": _CACHE_SCHEMA,
            "sha256": hashlib.sha256(resource.content).hexdigest(),
            "size": len(resource.content),
            "source_url": source_url,
        }
        temporary_paths: list[Path] = []
        try:
            content_path = self._write_temporary(root, resource.content)
            temporary_paths.append(content_path)
            metadata_path = self._write_temporary(
                root,
                (
                    json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                    + "\n"
                ).encode(),
            )
            temporary_paths.append(metadata_path)
            os.replace(content_path, root / "content")
            temporary_paths.remove(content_path)
            os.replace(metadata_path, root / "metadata.json")
            temporary_paths.remove(metadata_path)
        except OSError as error:
            raise DependencyAcquisitionError(
                f"cannot store dependency {source_url}: {error}"
            ) from error
        finally:
            for path in temporary_paths:
                path.unlink(missing_ok=True)

    @staticmethod
    def _write_temporary(root: Path, content: bytes) -> Path:
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            return Path(temporary.name)
