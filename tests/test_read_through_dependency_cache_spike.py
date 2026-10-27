"""Stage 0 spike for a constrained local read-through dependency cache."""

import http.server
import json
import mimetypes
import os
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import IO, TypedDict, cast
from urllib.parse import unquote, urlsplit

import pytest
from playwright.sync_api import Route, sync_playwright

WASM_CONTENT = bytes.fromhex(
    "0061736d01000000"
    "0105016000017f"
    "03020100"
    "070a0106616e737765720000"
    "0a06010400412a0b"
)
MAIN_CONTENT = b"""
import { helper } from "./helper.js";
const dataUrl = new URL("./data.json", import.meta.url);
const wasmUrl = new URL("./answer.wasm", import.meta.url);
const data = await (await fetch(dataUrl)).json();
const wasm = await WebAssembly.instantiateStreaming(fetch(wasmUrl));
export const message = `${helper}/${data.value}/${wasm.instance.exports.answer()}`;
"""
HELPER_CONTENT = b'export const helper = "relative";\n'
DYNAMIC_CONTENT = b'export const message = "dynamic loaded";\n'
DATA_CONTENT = b'{"value": 7}\n'
STYLE_CONTENT = b"""
@font-face {
  font-family: "Read Through Spike";
  src: url("../fonts/spike.woff2") format("woff2");
}
#font-probe {
  font-family: "Read Through Spike", sans-serif;
}
"""
FONT_CONTENT = b"deterministic font request fixture"


@dataclass(frozen=True)
class Resource:
    """One deterministic upstream resource."""

    path: str
    content: bytes
    content_type: str


@dataclass(frozen=True)
class RunningServer:
    """One temporary threaded HTTP server."""

    server: http.server.ThreadingHTTPServer
    thread: threading.Thread
    base_url: str


@dataclass
class CacheMode:
    """Mutable acquisition policy for the local spike server."""

    cache_only: bool = False


class FetchResult(TypedDict):
    """One direct HTTP result."""

    status: int
    body: str


RESOURCES = (
    Resource("main.js", MAIN_CONTENT, "text/javascript"),
    Resource("helper.js", HELPER_CONTENT, "text/javascript"),
    Resource("dynamic.js", DYNAMIC_CONTENT, "text/javascript"),
    Resource("data.json", DATA_CONTENT, "application/json"),
    Resource("answer.wasm", WASM_CONTENT, "application/wasm"),
    Resource("styles/theme.css", STYLE_CONTENT, "text/css"),
    Resource("fonts/spike.woff2", FONT_CONTENT, "font/woff2"),
)


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent cache acquisition from leaving the derived upstream URL."""

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


@pytest.fixture
def chromium() -> None:
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("run 'vividly install-browser' before dependency spike tests")


def _start_server(
    handler: type[http.server.BaseHTTPRequestHandler],
) -> RunningServer:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return RunningServer(
        server=server,
        thread=thread,
        base_url=f"http://127.0.0.1:{server.server_port}",
    )


def _stop_server(running: RunningServer) -> None:
    running.server.shutdown()
    running.thread.join()
    running.server.server_close()


def _upstream_handler(
    requests: list[str],
) -> type[http.server.BaseHTTPRequestHandler]:
    resources = {
        f"/upstream/package/{resource.path}": resource for resource in RESOURCES
    }

    class UpstreamHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            requests.append(path)
            if path == "/upstream/package/redirect.js":
                self.send_response(http.HTTPStatus.FOUND)
                self.send_header("Location", "/outside.js")
                self.end_headers()
                return
            if path == "/outside.js":
                self._send(b"external response\n", "text/javascript")
                return
            resource = resources.get(path)
            if resource is None:
                self.send_error(http.HTTPStatus.NOT_FOUND)
                return
            self._send(resource.content, resource.content_type)

        def _send(self, content: bytes, content_type: str) -> None:
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return UpstreamHandler


def _index_html(external_url: str) -> bytes:
    template = """<!doctype html>
<html>
<head>
  <link rel="stylesheet" href="./~dependencies/package/styles/theme.css">
</head>
<body>
  <output id="result">loading</output>
  <div id="font-probe">font probe</div>
  <button id="dynamic">Load dynamic resource</button>
  <button id="external">Load external resource</button>
  <script type="module">
    import { message } from "./~dependencies/package/main.js";
    const result = document.querySelector("#result");
    result.textContent = message;
    document.querySelector("#dynamic").addEventListener("click", async () => {
      const dependency = await import(
        "./~dependencies/package/dynamic.js"
      );
      result.textContent = dependency.message;
    });
    document.querySelector("#external").addEventListener("click", async () => {
      try {
        await fetch(__EXTERNAL_URL__);
        result.textContent = "external loaded";
      } catch {
        result.textContent = "external blocked";
      }
    });
  </script>
</body>
</html>
"""
    return template.replace("__EXTERNAL_URL__", json.dumps(external_url)).encode()


def _valid_relative_path(raw_path: str) -> str | None:
    if "%" in raw_path or "\\" in raw_path or "//" in raw_path:
        return None
    decoded = unquote(raw_path)
    parts = decoded.split("/")
    if not decoded or any(part in {"", ".", ".."} for part in parts):
        return None
    return decoded


def _content_type(path: str) -> str:
    known = {
        ".js": "text/javascript",
        ".wasm": "application/wasm",
        ".woff2": "font/woff2",
    }
    suffix = Path(path).suffix
    return known.get(suffix) or mimetypes.guess_type(path)[0] or "application/octet-stream"


def _read_through_site_handler(
    *,
    upstream_base_url: str,
    cache_root: Path,
    mode: CacheMode,
    site_requests: list[str],
    upstream_attempts: list[str],
) -> type[http.server.BaseHTTPRequestHandler]:
    prefix = "/~dependencies/package/"
    opener = urllib.request.build_opener(RejectRedirects)

    class ReadThroughSiteHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            site_requests.append(self.path)
            if parsed.path == "/":
                self._send(
                    _index_html(f"{upstream_base_url}/outside.js"),
                    "text/html",
                )
                return
            if not parsed.path.startswith(prefix):
                self.send_error(http.HTTPStatus.NOT_FOUND)
                return
            if parsed.query:
                self.send_error(http.HTTPStatus.BAD_REQUEST, "Query not allowed")
                return
            relative_path = _valid_relative_path(parsed.path.removeprefix(prefix))
            if relative_path is None:
                self.send_error(http.HTTPStatus.BAD_REQUEST, "Invalid dependency path")
                return
            cache_path = cache_root.joinpath(*relative_path.split("/"))
            if not cache_path.is_file():
                if mode.cache_only:
                    self.send_error(
                        http.HTTPStatus.GATEWAY_TIMEOUT,
                        "Dependency is not cached",
                    )
                    return
                upstream_path = f"/upstream/package/{relative_path}"
                upstream_attempts.append(upstream_path)
                request = urllib.request.Request(
                    f"{upstream_base_url}{upstream_path}",
                    headers={"User-Agent": "Vividly read-through spike"},
                )
                try:
                    with opener.open(request, timeout=5) as response:
                        content = response.read(1024 * 1024 + 1)
                except (urllib.error.HTTPError, urllib.error.URLError) as error:
                    self.send_error(
                        http.HTTPStatus.BAD_GATEWAY,
                        f"Dependency acquisition failed: {error}",
                    )
                    return
                if len(content) > 1024 * 1024:
                    self.send_error(
                        http.HTTPStatus.BAD_GATEWAY,
                        "Dependency exceeds size limit",
                    )
                    return
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary_path: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=cache_path.parent,
                        delete=False,
                    ) as temporary:
                        temporary.write(content)
                        temporary_path = Path(temporary.name)
                    os.replace(temporary_path, cache_path)
                except OSError as error:
                    if temporary_path is not None:
                        temporary_path.unlink(missing_ok=True)
                    self.send_error(
                        http.HTTPStatus.INTERNAL_SERVER_ERROR,
                        f"Cannot install dependency: {error}",
                    )
                    return
            self._send(cache_path.read_bytes(), _content_type(relative_path))

        def _send(self, content: bytes, content_type: str) -> None:
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return ReadThroughSiteHandler


def _fetch(url: str) -> FetchResult:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return {
                "status": response.status,
                "body": response.read().decode(errors="replace"),
            }
    except urllib.error.HTTPError as error:
        return {
            "status": error.code,
            "body": error.read().decode(errors="replace"),
        }


def test_read_through_cache_preserves_relative_graph_and_rehearses_offline(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    upstream_requests: list[str] = []
    upstream = _start_server(_upstream_handler(upstream_requests))
    site_requests: list[str] = []
    upstream_attempts: list[str] = []
    mode = CacheMode()
    site = _start_server(
        _read_through_site_handler(
            upstream_base_url=upstream.base_url,
            cache_root=tmp_path / "cache",
            mode=mode,
            site_requests=site_requests,
            upstream_attempts=upstream_attempts,
        )
    )
    upstream_running = True

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            connected = browser.new_context(service_workers="block")
            page = connected.new_page()
            page.goto(site.base_url, wait_until="domcontentloaded")
            page.get_by_text("relative/7/42", exact=True).wait_for()
            page.get_by_role("button", name="Load dynamic resource").click()
            page.get_by_text("dynamic loaded", exact=True).wait_for()
            page.wait_for_function(
                """() => performance.getEntriesByType("resource")
                  .some((entry) => entry.name.endsWith("/fonts/spike.woff2"))"""
            )
            connected.close()

            expected_relative_requests = {
                f"/upstream/package/{resource.path}" for resource in RESOURCES
            }
            assert set(upstream_requests) == expected_relative_requests
            assert set(upstream_attempts) == expected_relative_requests
            connected_attempts = list(upstream_attempts)

            _stop_server(upstream)
            upstream_running = False
            mode.cache_only = True

            blocked_external: list[str] = []
            rehearsal = browser.new_context(service_workers="block")

            def enforce_local_only(route: Route) -> None:
                if route.request.url.startswith(f"{site.base_url}/"):
                    route.continue_()
                    return
                blocked_external.append(route.request.url)
                route.abort("internetdisconnected")

            rehearsal.route("**/*", enforce_local_only)
            rehearsal_page = rehearsal.new_page()
            rehearsal_page.goto(site.base_url, wait_until="domcontentloaded")
            rehearsal_page.get_by_text("relative/7/42", exact=True).wait_for()
            rehearsal_page.get_by_role(
                "button",
                name="Load dynamic resource",
            ).click()
            rehearsal_page.get_by_text("dynamic loaded", exact=True).wait_for()
            rehearsal_page.get_by_role(
                "button",
                name="Load external resource",
            ).click()
            rehearsal_page.get_by_text("external blocked", exact=True).wait_for()

            missing = cast(
                FetchResult,
                rehearsal_page.evaluate(
                    """async () => {
                      const response = await fetch(
                        "./~dependencies/package/conditional-miss.js",
                      );
                      return {
                        status: response.status,
                        body: await response.text(),
                      };
                    }"""
                ),
            )
            assert blocked_external == [f"{upstream.base_url}/outside.js"]
            assert upstream_attempts == connected_attempts
            assert missing["status"] == http.HTTPStatus.GATEWAY_TIMEOUT
            assert "Dependency is not cached" in missing["body"]
            assert "/upstream/package/conditional-miss.js" not in upstream_attempts

            rehearsal.close()
            browser.close()
    finally:
        if upstream_running:
            _stop_server(upstream)
        _stop_server(site)


def test_read_through_cache_rejects_proxy_and_path_escape(
    tmp_path: Path,
) -> None:
    upstream_requests: list[str] = []
    upstream = _start_server(_upstream_handler(upstream_requests))
    site_requests: list[str] = []
    upstream_attempts: list[str] = []
    site = _start_server(
        _read_through_site_handler(
            upstream_base_url=upstream.base_url,
            cache_root=tmp_path / "cache",
            mode=CacheMode(),
            site_requests=site_requests,
            upstream_attempts=upstream_attempts,
        )
    )

    try:
        injected = _fetch(
            f"{site.base_url}/~dependencies/package/main.js"
            "?url=https://example.invalid/escape.js"
        )
        encoded_traversal = _fetch(
            f"{site.base_url}/~dependencies/package/%2e%2e/outside.js"
        )
        redirect = _fetch(
            f"{site.base_url}/~dependencies/package/redirect.js"
        )

        assert injected["status"] == http.HTTPStatus.BAD_REQUEST
        assert encoded_traversal["status"] == http.HTTPStatus.BAD_REQUEST
        assert redirect["status"] == http.HTTPStatus.BAD_GATEWAY
        assert upstream_attempts == ["/upstream/package/redirect.js"]
        assert upstream_requests == ["/upstream/package/redirect.js"]
        assert "/outside.js" not in upstream_requests
    finally:
        _stop_server(upstream)
        _stop_server(site)
