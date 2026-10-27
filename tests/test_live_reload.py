"""Browser tests for live reload specified by docs/specs/cli.md section 6."""

import argparse
import contextlib
import http.client
import io
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Route, sync_playwright

from vividly.cli import provision_command
from vividly.runtime import packaged_runtime


@pytest.fixture
def chromium() -> None:
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("run 'vividly install-browser' before live-reload tests")


def _provision(project_root: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=project_root, assume_yes=True))


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _start_server(project_root: Path) -> tuple[subprocess.Popen[str], str]:
    port = _available_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vividly.cli",
            "run",
            str(project_root),
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=project_root,
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate()
            pytest.fail(f"preview server exited before serving a request:\n{output}")
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.2)
            connection.request("HEAD", "/")
            response = connection.getresponse()
            response.read()
            connection.close()
            if response.status == 200:
                return process, f"http://127.0.0.1:{port}"
        except OSError:
            time.sleep(0.05)
    process.terminate()
    process.communicate(timeout=5)
    pytest.fail("preview server did not start within five seconds")


def _stop_server(process: subprocess.Popen[str]) -> str:
    process.terminate()
    output, _ = process.communicate(timeout=5)
    return output


def _select_editable_runtime(project_root: Path, source: str) -> Path:
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
    return runtime_root


def _request(base_url: str, path: str) -> tuple[int, bytes]:
    parsed = urlsplit(base_url)
    assert parsed.hostname is not None
    assert parsed.port is not None
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_author_change_reloads_browser_with_fresh_source(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    _provision(tmp_path)
    process, base_url = _start_server(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            with page.expect_request(
                lambda request: request.url.endswith("/vividly/~dev/events")
            ):
                page.goto(
                    f"{base_url}/?vividly-capture=1#/vividly/welcome",
                    wait_until="load",
                )
            page.wait_for_function(
                "() => document.querySelector('vividly-presentation')"
                "?.hasAttribute('data-render-ready')"
            )
            page.get_by_text("Your presentation starts here").wait_for()

            slide_path = tmp_path / "site/slides/title-card/slide.html"
            source = slide_path.read_text(encoding="utf-8")
            with page.expect_event("load", timeout=10_000):
                slide_path.write_text(
                    source.replace(
                        "Your presentation starts here",
                        "Your edited presentation starts here",
                    ),
                    encoding="utf-8",
                )

            page.wait_for_function(
                "() => document.querySelector('vividly-presentation')"
                "?.hasAttribute('data-render-ready')"
            )
            page.get_by_text("Your edited presentation starts here").wait_for()
            assert page.url.endswith("#/vividly/welcome")
            browser.close()
    finally:
        _stop_server(process)


@pytest.mark.parametrize("source", ["repository", "path"])
def test_editable_runtime_change_refreshes_deployed_urls(
    tmp_path: Path,
    source: str,
) -> None:
    _provision(tmp_path)
    runtime_root = _select_editable_runtime(tmp_path, source)
    process, base_url = _start_server(tmp_path)
    parsed = urlsplit(base_url)
    assert parsed.hostname is not None
    assert parsed.port is not None
    events = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
    try:
        events.request("GET", "/vividly/~dev/events")
        response = events.getresponse()
        assert response.status == 200
        assert response.read(len(b": connected\n\n")) == b": connected\n\n"

        added_path = runtime_root / "vividly" / "editable.js"
        added_content = b"export const editable = true;\n"
        added_path.write_bytes(added_content)

        event = b"event: reload\ndata: reload\n\n"
        assert response.read(len(event)) == event
        assert _request(base_url, "/vividly/editable.js") == (200, added_content)
    finally:
        events.close()
        _stop_server(process)


def test_invalid_runtime_manifest_recovers_without_reloading_invalid_state(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    _provision(tmp_path)
    runtime_root = _select_editable_runtime(tmp_path, "path")
    manifest_path = runtime_root / "vividly-runtime.json"
    manifest = manifest_path.read_text(encoding="utf-8")
    process, base_url = _start_server(tmp_path)
    output = ""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            loads = 0

            def count_load(_: Page) -> None:
                nonlocal loads
                loads += 1

            page.on("load", count_load)
            with page.expect_request(
                lambda request: request.url.endswith("/vividly/~dev/events")
            ):
                page.goto(
                    f"{base_url}/?vividly-capture=1#/vividly/welcome",
                    wait_until="load",
                )
            page.wait_for_function(
                "() => document.querySelector('vividly-presentation')"
                "?.hasAttribute('data-render-ready')"
            )
            assert loads == 1

            manifest_path.write_text("{", encoding="utf-8")
            page.wait_for_timeout(750)
            assert loads == 1

            with page.expect_event("load", timeout=10_000):
                manifest_path.write_text(manifest, encoding="utf-8")
            page.wait_for_function(
                "() => document.querySelector('vividly-presentation')"
                "?.hasAttribute('data-render-ready')"
            )
            assert loads == 2
            browser.close()
    finally:
        output = _stop_server(process)
    assert "vividly run: reload validation failed:" in output
    assert "vividly run: reload validation failed:" in output


def test_reload_client_reconnects_after_event_stream_closes(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    _provision(tmp_path)
    process, base_url = _start_server(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            requests = 0
            loads = 0

            def route_event_stream(route: Route) -> None:
                nonlocal requests
                requests += 1
                if requests == 1:
                    body = "retry: 500\n\n"
                elif requests == 2:
                    body = "event: reload\ndata: reload\n\n"
                else:
                    body = "retry: 10000\n\n"
                route.fulfill(
                    status=200,
                    content_type="text/event-stream",
                    body=body,
                )

            def count_load(_: Page) -> None:
                nonlocal loads
                loads += 1

            page.route("**/vividly/~dev/events", route_event_stream)
            page.on("load", count_load)
            page.goto(
                f"{base_url}/?vividly-capture=1#/vividly/welcome",
                wait_until="load",
            )
            page.wait_for_function(
                "() => document.querySelector('vividly-presentation')"
                "?.hasAttribute('data-render-ready')"
            )
            deadline = time.monotonic() + 5
            while loads < 2 and time.monotonic() < deadline:
                page.wait_for_timeout(50)

            assert requests >= 2
            assert loads >= 2
            browser.close()
    finally:
        _stop_server(process)
