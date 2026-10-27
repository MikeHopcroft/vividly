"""Integration tests for dependency-resolution.md sections 6 through 8."""

import argparse
import contextlib
import http.client
import http.server
import io
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import cast
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, sync_playwright
from runtime_site import install_test_runtime

from vividly.cli import provision_command
from vividly.composition import compose_project
from vividly.dependencies import (
    DependencyAcquisitionError,
    DependencyCache,
    DependencyResource,
    DependencySelection,
)
from vividly.rehearsal import rehearse_project
from vividly.server import CompositionSession, composition_handler

WASM_CONTENT = bytes.fromhex(
    "0061736d010000000105016000017f03020100070a0106616e7377657200000a06010400412a0b"
)


@pytest.fixture(scope="module")
def browser() -> Generator[Browser, None, None]:
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("run 'vividly install-browser' before browser tests")
        instance = playwright.chromium.launch(headless=True)
        try:
            yield instance
        finally:
            instance.close()


@contextmanager
def serve_project(
    project_root: Path,
    cache: DependencyCache,
) -> Generator[str, None, None]:
    with CompositionSession(project_root) as compositions:
        handler = composition_handler(
            compositions,
            dependency_cache=cache,
            log_requests=False,
        )
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


def provision_dependency_project(project_root: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=project_root, assume_yes=True))
    site = project_root / "site"
    (site / "catalog.yaml").write_text(
        """
version: 1
dependencies:
  graph:
    baseUrl: https://cdn.example.invalid/graph@1/
    entry: main.js
presentations:
  - id: vividly
    title: Dependency Cache
    manifest: ./presentations/cache.yaml
""",
        encoding="utf-8",
    )
    (site / "presentations" / "cache.yaml").write_text(
        """
id: dependency-cache
title: Dependency Cache
keyboardHints: never
nodes:
  - type: slide
    id: entry
    module: ../slides/dependency-cache.js
""",
        encoding="utf-8",
    )
    (site / "slides" / "dependency-cache.js").write_text(
        """
import { Slide } from '../vividly/runtime/slide.js';

export default class DependencyCacheSlide extends Slide {
  async preload() {
    this.graph = await this.ctx.dependency('graph').import();
  }

  mount(root) {
    root.innerHTML = `
      <output id="dependency-result">${this.graph.message}</output>
      <button id="dynamic">Load dynamic dependency</button>
      <button id="external">Request external resource</button>
      <button id="websocket">Open external WebSocket</button>
      <button id="browser-error">Raise browser error</button>
    `;
    root.querySelector('#dynamic').addEventListener('click', async () => {
      try {
        const dynamic = await this.graph.loadDynamic();
        root.querySelector('#dependency-result').textContent = dynamic.message;
      } catch {
        root.querySelector('#dependency-result').textContent = 'dynamic unavailable';
      }
    });
    root.querySelector('#external').addEventListener('click', () => {
      fetch('https://external.example.invalid/resource').catch(() => {});
    });
    root.querySelector('#websocket').addEventListener('click', () => {
      new WebSocket('wss://external.example.invalid/socket');
    });
    root.querySelector('#browser-error').addEventListener('click', () => {
      setTimeout(() => {
        throw new Error('rehearsal browser error');
      });
    });
  }
}
""",
        encoding="utf-8",
    )


def dependency_resources(project_root: Path) -> dict[str, DependencyResource]:
    runtime_resources = install_test_runtime(project_root)
    resources = {
        "https://cdn.example.invalid/graph@1/main.js": DependencyResource(
            content=b"""
import { helper } from './helper.js';
const data = await (await fetch(new URL('./data.json', import.meta.url))).json();
const wasm = await WebAssembly.instantiateStreaming(
  fetch(new URL('./answer.wasm', import.meta.url))
);
export const message = `${helper}/${data.value}/${wasm.instance.exports.answer()}`;
export const loadDynamic = () => import('./dynamic.js');
""",
            content_type="text/javascript",
        ),
        "https://cdn.example.invalid/graph@1/helper.js": DependencyResource(
            content=b"export const helper = 'relative';\n",
            content_type="text/javascript",
        ),
        "https://cdn.example.invalid/graph@1/data.json": DependencyResource(
            content=b'{"value": 7}\n',
            content_type="application/json",
        ),
        "https://cdn.example.invalid/graph@1/answer.wasm": DependencyResource(
            content=WASM_CONTENT,
            content_type="application/wasm",
        ),
        "https://cdn.example.invalid/graph@1/dynamic.js": DependencyResource(
            content=b"export const message = 'dynamic loaded';\n",
            content_type="text/javascript",
        ),
        "https://cdn.example.invalid/graph@1/styles/theme.css": DependencyResource(
            content=b"body { color: rebeccapurple; }\n",
            content_type="text/css",
        ),
        "https://cdn.example.invalid/graph@1/fonts/demo.woff2": DependencyResource(
            content=b"font fixture",
            content_type="font/woff2",
        ),
    }
    for source_url, (content, content_type) in runtime_resources.items():
        resources[source_url] = DependencyResource(
            content=content,
            content_type=content_type,
        )
    return resources


def request(base_url: str, target: str) -> tuple[int, str | None, bytes]:
    parsed = urlsplit(base_url)
    assert parsed.hostname is not None
    assert parsed.port is not None
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
    try:
        connection.request("GET", target)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    finally:
        connection.close()


def test_relative_graph_and_media_types_survive_server_restart(
    tmp_path: Path,
    browser: Browser,
) -> None:
    provision_dependency_project(tmp_path)
    resources = dependency_resources(tmp_path)
    acquisitions: list[str] = []

    def acquire(url: str) -> DependencyResource:
        acquisitions.append(url)
        return resources[url]

    cache_root = tmp_path / "persistent-cache"
    with serve_project(tmp_path, DependencyCache(cache_root, acquirer=acquire)) as base_url:
        page = browser.new_page()
        page.goto(f"{base_url}/#/vividly/entry")
        page.locator("#dependency-result").wait_for()
        assert page.locator("#dependency-result").text_content() == "relative/7/42"
        page.get_by_role("button", name="Load dynamic dependency").click()
        page.get_by_text("dynamic loaded", exact=True).wait_for()
        page.close()

        css = request(base_url, "/~dependencies/graph/styles/theme.css")
        font = request(base_url, "/~dependencies/graph/fonts/demo.woff2")
        assert css == (200, "text/css", b"body { color: rebeccapurple; }\n")
        assert font == (200, "font/woff2", b"font fixture")

    assert set(acquisitions) == set(resources)

    def fail_acquisition(url: str) -> DependencyResource:
        raise AssertionError(f"unexpected acquisition after restart: {url}")

    with serve_project(
        tmp_path,
        DependencyCache(cache_root, acquirer=fail_acquisition),
    ) as base_url:
        page = browser.new_page()
        page.goto(f"{base_url}/#/vividly/entry")
        page.locator("#dependency-result").wait_for()
        assert page.locator("#dependency-result").text_content() == "relative/7/42"
        page.get_by_role("button", name="Load dynamic dependency").click()
        page.get_by_text("dynamic loaded", exact=True).wait_for()
        page.close()
        assert request(base_url, "/~dependencies/graph/styles/theme.css")[0] == 200
        assert request(base_url, "/~dependencies/graph/fonts/demo.woff2")[0] == 200


def test_dependency_route_rejects_unmapped_and_malformed_requests(tmp_path: Path) -> None:
    provision_dependency_project(tmp_path)
    acquisitions: list[str] = []

    def reject_acquisition(url: str) -> DependencyResource:
        acquisitions.append(url)
        raise DependencyAcquisitionError("upstream rejected")

    with serve_project(
        tmp_path,
        DependencyCache(tmp_path / "cache", acquirer=reject_acquisition),
    ) as base_url:
        assert request(base_url, "/~dependencies/unknown/main.js")[0] == 404
        assert request(base_url, "/~dependencies/graph/../outside.js")[0] == 400
        assert request(base_url, "/~dependencies/graph/%2e%2e/outside.js")[0] == 400
        assert request(base_url, "/~dependencies/graph/main.js?upstream=https://evil")[0] == 400
        assert request(base_url, "/~dependencies/graph/https:evil")[0] == 400
        assert request(base_url, "/~dependencies/graph/missing.js")[0] == 502

    assert acquisitions == ["https://cdn.example.invalid/graph@1/missing.js"]


def test_catalog_refresh_changes_the_fixed_upstream_mapping(tmp_path: Path) -> None:
    provision_dependency_project(tmp_path)
    acquisitions: list[str] = []

    def acquire(url: str) -> DependencyResource:
        acquisitions.append(url)
        return DependencyResource(content=url.encode(), content_type="text/javascript")

    cache = DependencyCache(tmp_path / "cache", acquirer=acquire)
    with CompositionSession(tmp_path) as compositions:
        handler = composition_handler(
            compositions,
            dependency_cache=cache,
            log_requests=False,
        )
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            first = request(base_url, "/~dependencies/graph/main.js")
            catalog = tmp_path / "site" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace("graph@1", "graph@2"),
                encoding="utf-8",
            )
            compositions.refresh()
            second = request(base_url, "/~dependencies/graph/main.js")
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    assert first[2] == b"https://cdn.example.invalid/graph@1/main.js"
    assert second[2] == b"https://cdn.example.invalid/graph@2/main.js"
    assert acquisitions == [
        "https://cdn.example.invalid/graph@1/main.js",
        "https://cdn.example.invalid/graph@2/main.js",
    ]


def test_runtime_dependency_uses_the_same_persistent_route_and_cache(
    tmp_path: Path,
) -> None:
    provision_dependency_project(tmp_path)
    source_url = "https://cdn.jsdelivr.net/npm/marked@12.0.2/lib/marked.umd.js"
    marked_content, marked_content_type = install_test_runtime(tmp_path)[source_url]
    acquisitions: list[str] = []

    def acquire(url: str) -> DependencyResource:
        acquisitions.append(url)
        assert url == source_url
        return DependencyResource(
            content=marked_content,
            content_type=marked_content_type,
        )

    cache_root = tmp_path / "persistent-cache"
    with serve_project(tmp_path, DependencyCache(cache_root, acquirer=acquire)) as base_url:
        response = request(base_url, "/~dependencies/marked/marked.umd.js")
        assert response == (200, "text/javascript", marked_content)

    with serve_project(tmp_path, DependencyCache(cache_root, cache_only=True)) as base_url:
        response = request(base_url, "/~dependencies/marked/marked.umd.js")
        assert response == (200, "text/javascript", marked_content)

    assert acquisitions == [source_url]


def populate_rehearsal_cache(
    project_root: Path,
    cache_root: Path,
    *,
    include_dynamic: bool,
    omit_runtime_key: str | None = None,
) -> None:
    resources = dependency_resources(project_root)
    cache = DependencyCache(cache_root, acquirer=resources.__getitem__)
    selection = DependencySelection(
        key="graph",
        base_url="https://cdn.example.invalid/graph@1/",
        entry=PurePosixPath("main.js"),
    )
    paths = ["main.js", "helper.js", "data.json", "answer.wasm"]
    if include_dynamic:
        paths.append("dynamic.js")
    for path in paths:
        cache.get(selection, PurePosixPath(path))
    with compose_project(project_root) as composition:
        for runtime_selection in composition.dependencies.values():
            if (
                runtime_selection.owner == "runtime"
                and runtime_selection.key != omit_runtime_key
            ):
                cache.get(runtime_selection, runtime_selection.entry)


def test_rehearsal_passes_for_the_exercised_cached_path(
    tmp_path: Path,
    browser: Browser,
) -> None:
    provision_dependency_project(tmp_path)
    cache_root = tmp_path / "cache"
    populate_rehearsal_cache(tmp_path, cache_root, include_dynamic=True)
    service_worker_counts: list[int] = []

    def interact(page: Page) -> None:
        page.goto(f"{page.url}#/vividly/entry")
        page.get_by_text("relative/7/42", exact=True).wait_for()
        page.get_by_role("button", name="Load dynamic dependency").click()
        page.get_by_text("dynamic loaded", exact=True).wait_for()
        cast(
            object,
            page.evaluate(
                """() => navigator.serviceWorker
                  .register('/rehearsal-service-worker.js')
                  .catch(() => null)"""
            ),
        )
        service_worker_counts.append(len(page.context.service_workers))

    result = rehearse_project(
        tmp_path,
        cache_root=cache_root,
        headless=True,
        interact=interact,
        browser=browser,
    )

    assert result.passed
    assert service_worker_counts == [0]


def test_rehearsal_reports_missing_js_yaml_without_acquisition(
    tmp_path: Path,
    browser: Browser,
) -> None:
    provision_dependency_project(tmp_path)
    cache_root = tmp_path / "cache"
    populate_rehearsal_cache(
        tmp_path,
        cache_root,
        include_dynamic=True,
        omit_runtime_key="js-yaml",
    )
    acquisitions: list[str] = []

    def fail_acquisition(url: str) -> DependencyResource:
        acquisitions.append(url)
        raise AssertionError(f"unexpected rehearsal acquisition: {url}")

    def cache_only(root: Path, *, cache_only: bool) -> DependencyCache:
        return DependencyCache(
            root,
            cache_only=cache_only,
            acquirer=fail_acquisition,
        )

    with patch("vividly.rehearsal.DependencyCache", side_effect=cache_only):
        result = rehearse_project(
            tmp_path,
            cache_root=cache_root,
            headless=True,
            interact=lambda page: page.wait_for_timeout(100),
            browser=browser,
        )

    assert acquisitions == []
    assert any(
        issue.kind == "cache-miss"
        and issue.url.endswith("/~dependencies/js-yaml/js-yaml.min.js")
        for issue in result.issues
    )


def test_rehearsal_reports_cache_miss_external_network_and_browser_error(
    tmp_path: Path,
    browser: Browser,
) -> None:
    provision_dependency_project(tmp_path)
    cache_root = tmp_path / "cache"
    populate_rehearsal_cache(tmp_path, cache_root, include_dynamic=False)

    def interact(page: Page) -> None:
        page.goto(f"{page.url}#/vividly/entry")
        page.get_by_text("relative/7/42", exact=True).wait_for()
        page.get_by_role("button", name="Load dynamic dependency").click()
        page.get_by_text("dynamic unavailable", exact=True).wait_for()
        page.get_by_role("button", name="Request external resource").click()
        page.get_by_role("button", name="Open external WebSocket").click()
        page.get_by_role("button", name="Raise browser error").click()
        page.wait_for_timeout(200)

    result = rehearse_project(
        tmp_path,
        cache_root=cache_root,
        headless=True,
        interact=interact,
        browser=browser,
    )

    assert any(
        issue.kind == "cache-miss"
        and issue.route == "vividly/entry"
        and issue.url.endswith("/~dependencies/graph/dynamic.js")
        for issue in result.issues
    )
    assert any(
        issue.kind == "external-request"
        and issue.route == "vividly/entry"
        and issue.url == "https://external.example.invalid/resource"
        for issue in result.issues
    )
    assert any(
        issue.kind == "external-websocket"
        and issue.route == "vividly/entry"
        and issue.url == "wss://external.example.invalid/socket"
        for issue in result.issues
    )
    assert any(
        issue.kind == "browser-error"
        and issue.route == "vividly/entry"
        and "rehearsal browser error" in issue.detail
        for issue in result.issues
    )
