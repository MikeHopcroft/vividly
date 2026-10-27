"""Tests for the dependency contract in docs/specs/dependency-resolution.md."""

import hashlib
import http.server
import json
import textwrap
import threading
from collections.abc import Generator
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest

from vividly.dependencies import (
    DependencyAcquisitionError,
    DependencyCache,
    DependencyCacheMiss,
    DependencyConfigError,
    DependencyLoader,
    DependencyResource,
    DependencySelection,
    acquire_dependency,
    clear_dependency_cache,
    combine_dependencies,
    inspect_dependency_cache,
    load_catalog_dependencies,
    load_runtime_dependencies,
)


def test_loads_project_dependency_selections(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        """
version: 1
dependencies:
  graphics:
    baseUrl: https://cdn.example.invalid/graphics@1.2.3/
    entry: build/main.js
presentations: []
""",
        encoding="utf-8",
    )

    dependencies = load_catalog_dependencies(catalog)

    assert dependencies == {
        "graphics": DependencySelection(
            key="graphics",
            base_url="https://cdn.example.invalid/graphics@1.2.3/",
            entry=PurePosixPath("build/main.js"),
        )
    }


@pytest.mark.parametrize(
    ("dependencies", "message"),
    [
        ("null", "`dependencies` must be a mapping"),
        ("[]", "`dependencies` must be a mapping"),
        (
            """
Not_Valid:
  baseUrl: https://cdn.example.invalid/package/
  entry: main.js
""",
            "invalid dependency key 'Not_Valid'",
        ),
        (
            """
package:
  baseUrl: http://cdn.example.invalid/package/
  entry: main.js
""",
            "baseUrl` must be a clean absolute HTTPS URL",
        ),
        (
            """
package:
  baseUrl: https://cdn.example.invalid/package/
  entry: ../main.js
""",
            "entry` must be a normalized relative path",
        ),
    ],
)
def test_rejects_invalid_project_dependency_selections(
    tmp_path: Path,
    dependencies: str,
    message: str,
) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        "version: 1\ndependencies:\n"
        f"{textwrap.indent(dependencies.strip(), '  ')}\n"
        "presentations: []\n",
        encoding="utf-8",
    )

    with pytest.raises(DependencyConfigError, match=message):
        load_catalog_dependencies(catalog)


def _write_runtime_dependencies(
    runtime_root: Path,
    dependencies: dict[str, object],
) -> Path:
    table_path = runtime_root / "vividly" / "dependencies.json"
    table_path.parent.mkdir(parents=True)
    table_path.write_text(
        json.dumps(
            {"dependencies": dependencies, "schema": 1},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return table_path


def _runtime_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "baseUrl": "https://cdn.example.invalid/package@1/",
        "entry": "main.js",
        "license": "MIT",
        "loader": {"global": "Package", "type": "script"},
        "projectUrl": "https://example.invalid/package",
        "sha256": "a" * 64,
        "version": "1.0.0",
    }
    record.update(overrides)
    return record


def test_loads_runtime_dependency_selections_with_ownership(tmp_path: Path) -> None:
    _write_runtime_dependencies(tmp_path, {"package": _runtime_record()})

    dependencies = load_runtime_dependencies(
        tmp_path,
        owner_identity="Vividly 1.2.3",
    )

    assert dependencies == {
        "package": DependencySelection(
            key="package",
            base_url="https://cdn.example.invalid/package@1/",
            entry=PurePosixPath("main.js"),
            owner="runtime",
            owner_identity="Vividly 1.2.3",
            version="1.0.0",
            project_url="https://example.invalid/package",
            license="MIT",
            sha256="a" * 64,
            loader=DependencyLoader(type="script", global_name="Package"),
        )
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"version": None}, "version` must be a nonempty string"),
        ({"projectUrl": "http://example.invalid"}, "clean absolute HTTPS URL"),
        ({"sha256": "not-a-digest"}, "lowercase SHA-256 digest"),
        ({"loader": {"type": "script"}}, "loader` is missing `global`"),
        (
            {"loader": {"global": "not.valid", "type": "script"}},
            "global` must be a JavaScript identifier",
        ),
        ({"loader": {"type": "unknown"}}, "must be `module`, `script`, or `stylesheet`"),
    ],
)
def test_rejects_invalid_runtime_dependency_selections(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    _write_runtime_dependencies(tmp_path, {"package": _runtime_record(**overrides)})

    with pytest.raises(DependencyConfigError, match=message):
        load_runtime_dependencies(tmp_path, owner_identity="Vividly 1.2.3")


def test_rejects_runtime_and_catalog_dependency_collisions() -> None:
    runtime = {
        "package": DependencySelection(
            key="package",
            base_url="https://cdn.example.invalid/package@1/",
            entry=PurePosixPath("main.js"),
            owner="runtime",
            owner_identity="Vividly 1.2.3",
        )
    }
    catalog = {
        "package": DependencySelection(
            key="package",
            base_url="https://cdn.example.invalid/package@2/",
            entry=PurePosixPath("main.js"),
        )
    }

    with pytest.raises(
        DependencyConfigError,
        match='catalog dependency "package".*Vividly 1.2.3',
    ):
        combine_dependencies(runtime, catalog)


def test_cache_persists_resources_and_separates_concrete_bases(tmp_path: Path) -> None:
    first = DependencySelection(
        key="package",
        base_url="https://cdn.example.invalid/package@1/",
        entry=PurePosixPath("main.js"),
    )
    second = DependencySelection(
        key="package",
        base_url="https://cdn.example.invalid/package@2/",
        entry=PurePosixPath("main.js"),
    )
    acquired_urls: list[str] = []

    def acquire(url: str) -> DependencyResource:
        acquired_urls.append(url)
        return DependencyResource(
            content=f"content from {url}".encode(),
            content_type="text/javascript",
        )

    cache_root = tmp_path / "cache"
    cache = DependencyCache(cache_root, acquirer=acquire)
    first_resource = cache.get(first, PurePosixPath("main.js"))
    second_resource = cache.get(second, PurePosixPath("main.js"))

    assert first_resource.content != second_resource.content
    assert acquired_urls == [
        "https://cdn.example.invalid/package@1/main.js",
        "https://cdn.example.invalid/package@2/main.js",
    ]

    def fail_acquisition(url: str) -> DependencyResource:
        raise AssertionError(f"unexpected acquisition: {url}")

    reopened = DependencyCache(cache_root, acquirer=fail_acquisition)
    assert reopened.get(first, PurePosixPath("main.js")) == first_resource
    assert reopened.get(second, PurePosixPath("main.js")) == second_resource


def test_cache_reacquires_a_resource_when_stored_bytes_fail_validation(
    tmp_path: Path,
) -> None:
    selection = DependencySelection(
        key="package",
        base_url="https://cdn.example.invalid/package@1/",
        entry=PurePosixPath("main.js"),
    )
    responses = [
        DependencyResource(content=b"first", content_type="text/javascript"),
        DependencyResource(content=b"replacement", content_type="text/javascript"),
    ]

    def acquire(url: str) -> DependencyResource:
        del url
        return responses.pop(0)

    cache_root = tmp_path / "cache"
    cache = DependencyCache(cache_root, acquirer=acquire)
    assert cache.get(selection, selection.entry).content == b"first"
    [content_path] = cache_root.rglob("content")
    content_path.write_bytes(b"corrupt")

    assert cache.get(selection, selection.entry).content == b"replacement"
    assert responses == []


def test_cache_inspection_reports_project_resource_states_without_mutation(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    selected = DependencySelection(
        key="selected",
        base_url="https://cdn.example.invalid/selected@1/",
        entry=PurePosixPath("main.js"),
    )
    missing = DependencySelection(
        key="missing",
        base_url="https://cdn.example.invalid/missing@1/",
        entry=PurePosixPath("main.js"),
    )
    global_only = DependencySelection(
        key="global-only",
        base_url="https://cdn.example.invalid/global@1/",
        entry=PurePosixPath("main.js"),
    )
    resource = DependencyResource(
        content=b"export const value = 1;\n",
        content_type="text/javascript",
    )
    cache = DependencyCache(cache_root, acquirer=lambda _: resource)
    cache.get(selected, selected.entry)
    cache.get(selected, PurePosixPath("helper.js"))
    cache.get(global_only, global_only.entry)
    metadata_mtimes = {
        path: path.stat().st_mtime_ns for path in cache_root.rglob("metadata.json")
    }

    project_records = inspect_dependency_cache(
        cache_root,
        {"missing": missing, "selected": selected},
    )

    assert [
        (
            record.key,
            record.relative_path,
            record.status,
            record.size,
        )
        for record in project_records
    ] == [
        ("missing", PurePosixPath("main.js"), "missing", None),
        ("selected", PurePosixPath("helper.js"), "valid", len(resource.content)),
        ("selected", PurePosixPath("main.js"), "valid", len(resource.content)),
    ]
    assert all(record.cached_at is not None for record in project_records[1:])
    assert {
        path: path.stat().st_mtime_ns for path in cache_root.rglob("metadata.json")
    } == metadata_mtimes

    all_records = inspect_dependency_cache(cache_root)
    assert len(all_records) == 3
    assert {record.source_url for record in all_records} == {
        "https://cdn.example.invalid/global@1/main.js",
        "https://cdn.example.invalid/selected@1/helper.js",
        "https://cdn.example.invalid/selected@1/main.js",
    }
    assert all(record.key is None for record in all_records)


def test_cache_inspection_distinguishes_invalid_incomplete_and_unreadable(
    tmp_path: Path,
) -> None:
    selection = DependencySelection(
        key="package",
        base_url="https://cdn.example.invalid/package@1/",
        entry=PurePosixPath("main.js"),
    )
    cache_root = tmp_path / "cache"
    cache = DependencyCache(
        cache_root,
        acquirer=lambda _: DependencyResource(
            content=b"complete",
            content_type="text/javascript",
        ),
    )
    for relative_path in ("main.js", "invalid.js", "incomplete.js", "unreadable.js"):
        cache.get(selection, PurePosixPath(relative_path))
    resource_roots = {
        json.loads(path.read_text(encoding="utf-8"))["source_url"]: path.parent
        for path in cache_root.rglob("metadata.json")
    }
    resource_roots[
        "https://cdn.example.invalid/package@1/invalid.js"
    ].joinpath("content").write_bytes(b"corrupt")
    resource_roots[
        "https://cdn.example.invalid/package@1/incomplete.js"
    ].joinpath("metadata.json").unlink()
    unreadable_content = resource_roots[
        "https://cdn.example.invalid/package@1/unreadable.js"
    ] / "content"
    original_read_bytes = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path == unreadable_content:
            raise PermissionError("fixture is unreadable")
        return original_read_bytes(path)

    with patch.object(Path, "read_bytes", read_bytes):
        records = inspect_dependency_cache(cache_root, {"package": selection})

    statuses = {record.source_url: record.status for record in records if record.source_url}
    assert statuses["https://cdn.example.invalid/package@1/main.js"] == "valid"
    assert statuses["https://cdn.example.invalid/package@1/invalid.js"] == "invalid"
    assert any(record.status == "incomplete" for record in records)
    assert any(record.status == "unreadable" for record in records)


def test_cache_clear_is_safe_idempotent_and_allows_repopulation(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    sibling = tmp_path / "keep"
    sibling.write_text("keep", encoding="utf-8")
    selection = DependencySelection(
        key="package",
        base_url="https://cdn.example.invalid/package@1/",
        entry=PurePosixPath("main.js"),
    )
    acquisitions: list[str] = []

    def acquire(url: str) -> DependencyResource:
        acquisitions.append(url)
        return DependencyResource(content=b"content", content_type="text/javascript")

    cache = DependencyCache(cache_root, acquirer=acquire)
    cache.get(selection, selection.entry)

    assert clear_dependency_cache(cache_root)
    assert not cache_root.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"
    assert not clear_dependency_cache(cache_root)

    cache.get(selection, selection.entry)
    assert cache_root.is_dir()
    assert acquisitions == [
        "https://cdn.example.invalid/package@1/main.js",
        "https://cdn.example.invalid/package@1/main.js",
    ]

    linked_root = tmp_path / "linked-cache"
    linked_root.symlink_to(cache_root, target_is_directory=True)
    with pytest.raises(DependencyAcquisitionError, match="symbolic link"):
        clear_dependency_cache(linked_root)
    file_root = tmp_path / "cache-file"
    file_root.write_text("not a directory", encoding="utf-8")
    with pytest.raises(DependencyAcquisitionError, match="not a directory"):
        clear_dependency_cache(file_root)


def test_cache_only_mode_never_acquires_a_missing_resource(tmp_path: Path) -> None:
    selection = DependencySelection(
        key="package",
        base_url="https://cdn.example.invalid/package@1/",
        entry=PurePosixPath("main.js"),
    )

    def fail_acquisition(url: str) -> DependencyResource:
        raise AssertionError(f"cache-only mode attempted acquisition: {url}")

    cache = DependencyCache(
        tmp_path / "cache",
        acquirer=fail_acquisition,
        cache_only=True,
    )

    with pytest.raises(DependencyCacheMiss, match="dependency is not cached"):
        cache.get(selection, selection.entry)


def test_runtime_entry_integrity_is_enforced_before_storage(tmp_path: Path) -> None:
    valid_content = b"expected runtime dependency"
    selection = DependencySelection(
        key="package",
        base_url="https://cdn.example.invalid/package@1/",
        entry=PurePosixPath("main.js"),
        owner="runtime",
        sha256=hashlib.sha256(valid_content).hexdigest(),
    )
    responses = [
        DependencyResource(content=b"unexpected", content_type="text/javascript"),
        DependencyResource(content=valid_content, content_type="text/javascript"),
    ]
    cache = DependencyCache(
        tmp_path / "cache",
        acquirer=lambda url: responses.pop(0),
    )

    with pytest.raises(DependencyAcquisitionError, match="failed integrity check"):
        cache.get(selection, selection.entry)

    assert cache.get(selection, selection.entry).content == valid_content
    assert responses == []


def test_cache_only_mode_rejects_cached_runtime_entry_with_wrong_expected_hash(
    tmp_path: Path,
) -> None:
    catalog_selection = DependencySelection(
        key="package",
        base_url="https://cdn.example.invalid/package@1/",
        entry=PurePosixPath("main.js"),
    )
    cache_root = tmp_path / "cache"
    DependencyCache(
        cache_root,
        acquirer=lambda url: DependencyResource(
            content=b"cached content",
            content_type="text/javascript",
        ),
    ).get(catalog_selection, catalog_selection.entry)
    runtime_selection = DependencySelection(
        key="package",
        base_url=catalog_selection.base_url,
        entry=catalog_selection.entry,
        owner="runtime",
        sha256=hashlib.sha256(b"different content").hexdigest(),
    )

    with pytest.raises(DependencyCacheMiss, match="dependency is not cached"):
        DependencyCache(cache_root, cache_only=True).get(
            runtime_selection,
            runtime_selection.entry,
        )


@pytest.fixture
def redirect_server() -> Generator[tuple[str, list[str]], None, None]:
    requests: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            requests.append(self.path)
            if self.path == "/redirect":
                self.send_response(http.HTTPStatus.FOUND)
                self.send_header("Location", "/outside")
                self.end_headers()
                return
            if self.path == "/truncated":
                self.send_response(http.HTTPStatus.OK)
                self.send_header("Content-Type", "text/javascript")
                self.send_header("Content-Length", "10")
                self.end_headers()
                self.wfile.write(b"short")
                return
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", "7")
            self.end_headers()
            self.wfile.write(b"outside")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_acquisition_does_not_follow_redirects(
    redirect_server: tuple[str, list[str]],
) -> None:
    base_url, requests = redirect_server

    with pytest.raises(DependencyAcquisitionError, match="cannot acquire dependency"):
        acquire_dependency(f"{base_url}/redirect")

    assert requests == ["/redirect"]


def test_acquisition_rejects_incomplete_responses(
    redirect_server: tuple[str, list[str]],
) -> None:
    base_url, requests = redirect_server

    with pytest.raises(DependencyAcquisitionError, match="dependency"):
        acquire_dependency(f"{base_url}/truncated")

    assert requests == ["/truncated"]
