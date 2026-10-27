"""Development/export equivalence tests from docs/specs/runtime-composition.md."""

import argparse
import contextlib
import http.client
import http.server
import io
import shutil
import threading
from collections.abc import Generator
from contextlib import contextmanager
from functools import partial
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright

from vividly.cli import provision_command
from vividly.composition import compose_project
from vividly.export import export_project
from vividly.runtime import packaged_runtime
from vividly.server import RELOAD_CLIENT, ReloadBroker, composition_handler

REPRESENTATIVE_PATHS = (
    "/",
    "/catalog.yaml?cache-bust=1",
    "/presentations/vividly.yaml",
    "/slides/title-card/slide.js",
    "/slides/title-card/slide.html",
    "/vividly/runtime/presentation.js",
    "/vividly/themes/dark.css",
)


@pytest.fixture
def chromium() -> None:
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("run 'vividly install-browser' before export browser tests")


def _provision(project_root: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=project_root, assume_yes=True))


def _select_runtime(project_root: Path, source: str) -> None:
    if source == "package":
        return

    runtime_root = project_root / "runtime"
    reference_root = project_root / "reference"
    with packaged_runtime() as runtime:
        shutil.copytree(runtime.runtime_root, runtime_root)
        shutil.copytree(runtime.reference_root, reference_root)
        framework_version = runtime.manifest.version

    if source == "repository":
        runtime_config = (
            "  source: repository\n"
            "  path: runtime\n"
            f"  version: {framework_version}\n"
            f"  commit: {'a' * 40}\n"
        )
    else:
        runtime_config = (
            "  source: path\n"
            "  path: runtime\n"
            f"  upstream_version: {framework_version}\n"
        )
    (project_root / "vividly.yaml").write_text(
        f"schema: 1\nruntime:\n{runtime_config}",
        encoding="utf-8",
    )


@contextmanager
def _development_server(project_root: Path) -> Generator[str, None, None]:
    with compose_project(project_root) as composition:
        broker = ReloadBroker()
        handler = composition_handler(
            composition,
            log_requests=False,
            reload_broker=broker,
        )
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            broker.close()
            server.shutdown()
            thread.join()
            server.server_close()


@contextmanager
def _static_server(root: Path) -> Generator[str, None, None]:
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
) -> tuple[int, str | None, str | None, bytes]:
    parsed = urlsplit(base_url)
    assert parsed.hostname is not None
    assert parsed.port is not None
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return (
            response.status,
            response.getheader("Content-Type"),
            response.getheader("Cache-Control"),
            response.read(),
        )
    finally:
        connection.close()


@pytest.mark.parametrize("source", ["package", "repository", "path"])
def test_export_matches_composed_url_set_and_source_bytes(
    tmp_path: Path,
    source: str,
) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    _select_runtime(project_root, source)
    if source != "package":
        (project_root / "runtime/vividly/editable.js").write_text(
            "export const editable = true;\n",
            encoding="utf-8",
        )

    with compose_project(project_root) as composition:
        expected = {
            url_path.relative_to(PurePosixPath("/")).as_posix(): (
                composed.source_path.read_bytes()
            )
            for url_path, composed in composition.files.items()
        }
    export_project(project_root, destination)
    actual = {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    }

    assert actual == expected


@pytest.mark.parametrize("source", ["package", "repository", "path"])
def test_development_and_export_http_responses_are_equivalent(
    tmp_path: Path,
    source: str,
) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    _select_runtime(project_root, source)
    export_project(project_root, destination)

    with _development_server(project_root) as development_url, _static_server(
        destination
    ) as export_url:
        for path in REPRESENTATIVE_PATHS:
            development = _request(development_url, path)
            exported = _request(export_url, path)
            assert development[0] == exported[0] == 200
            assert development[1] == exported[1]
            development_body = development[3]
            if path == "/":
                assert RELOAD_CLIENT in development_body
                development_body = development_body.replace(RELOAD_CLIENT, b"")
            assert development_body == exported[3]
            assert development[2] == "no-store"
            assert exported[2] is None

        assert _request(development_url, "/vividly/~dev/events", method="HEAD")[0] == 200
        assert _request(export_url, "/vividly/~dev/events", method="HEAD")[0] == 404
        assert _request(development_url, "/%2e%2e/vividly.yaml")[0] == 404
        assert _request(export_url, "/%2e%2e/vividly.yaml")[0] == 404


@pytest.mark.parametrize("source", ["package", "repository", "path"])
def test_exported_artifact_loads_in_browser(
    chromium: None,
    tmp_path: Path,
    source: str,
) -> None:
    del chromium
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    _select_runtime(project_root, source)
    export_project(project_root, destination)

    with _static_server(destination) as export_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        development_requests: list[str] = []
        page.on(
            "request",
            lambda request: (
                development_requests.append(request.url)
                if "/vividly/~dev/" in request.url
                else None
            ),
        )
        page.goto(
            f"{export_url}/?vividly-capture=1#/vividly/welcome",
            wait_until="domcontentloaded",
        )
        page.wait_for_function(
            "() => document.querySelector('vividly-presentation')"
            "?.hasAttribute('data-render-ready')"
        )

        page.get_by_text("Your presentation starts here").wait_for()
        assert development_requests == []
        browser.close()
