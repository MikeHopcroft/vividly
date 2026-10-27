"""Stage 0 spike for cache-backed and CDN-backed ESM dependency resolution."""

import hashlib
import http.client
import http.server
import json
import struct
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import IO
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright

DEPENDENCY_CONTENT = b'export const message = "dependency loaded";\n'
DEPENDENCY_SHA256 = hashlib.sha256(DEPENDENCY_CONTENT).hexdigest()
WASM_CONTENT = bytes.fromhex(
    "0061736d01000000"
    "0105016000017f"
    "03020100"
    "070a0106616e737765720000"
    "0a06010400412a0b"
)
MULTI_MODULE_CONTENT = b"""
const wasmUrl = new URL("./answer.wasm", import.meta.url);
const response = await fetch(wasmUrl);
const { instance } = await WebAssembly.instantiateStreaming(response);
export const message = `dependency loaded: ${instance.exports.answer()}`;
export const optionalUrl = new URL("./optional.dat", import.meta.url);
"""
OPTIONAL_CONTENT = b"loaded only when an optional code path is exercised\n"
FONT_CSS_CONTENT = b"""
@font-face {
  font-family: "Vividly Spike";
  src: url("./spike.ttf") format("truetype");
}
"""
CLASSIC_V1_CONTENT = b'globalThis.SpikeClassic = Object.freeze({ version: "v1" });\n'
CLASSIC_V2_CONTENT = b'globalThis.SpikeClassic = Object.freeze({ version: "v2" });\n'
WORKER_MODULE_CONTENT = b"""
const workerUrl = new URL("./worker.js", import.meta.url);
export const message = await new Promise((resolve) => {
  try {
    const worker = new Worker(workerUrl, { type: "module" });
    worker.onmessage = (event) => {
      resolve(`worker loaded: ${event.data}`);
      worker.terminate();
    };
    worker.onerror = () => resolve("worker failed: load");
  } catch (error) {
    resolve(`worker failed: ${error.name}`);
  }
});
"""
WORKER_CONTENT = b"self.postMessage(7);\n"


@dataclass(frozen=True)
class DependencyResource:
    """One exact browser-ready resource used by the spike."""

    name: str
    url: str
    sha256: str
    content_type: str


@dataclass(frozen=True)
class RunningServer:
    """One temporary HTTP server and its origin."""

    server: http.server.ThreadingHTTPServer
    thread: threading.Thread
    base_url: str


@dataclass(frozen=True)
class ResourceFailure:
    """One resource that cache preparation could not make available."""

    name: str
    reason: str


class DependencyPreparationError(Exception):
    """All resource failures from one eager preparation attempt."""

    def __init__(self, failures: Sequence[ResourceFailure]) -> None:
        self.failures = tuple(failures)
        details = "\n".join(
            f"- {failure.name}: {failure.reason}" for failure in self.failures
        )
        super().__init__(f"dependency preparation failed:\n{details}")


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent dependency acquisition from changing the declared URL."""

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


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _font_checksum(content: bytes | bytearray) -> int:
    padded = content + bytes(-len(content) % 4)
    words = struct.unpack(f">{len(padded) // 4}I", padded)
    return sum(words) & 0xFFFFFFFF


def _build_test_font() -> bytes:
    family = "Vividly Spike".encode("utf-16-be")
    subfamily = "Regular".encode("utf-16-be")
    name_records = (
        struct.pack(">HHHHHH", 3, 1, 0x0409, 1, len(family), 0)
        + struct.pack(">HHHHHH", 3, 1, 0x0409, 2, len(subfamily), len(family))
    )
    name = struct.pack(">HHH", 0, 2, 30) + name_records + family + subfamily
    cmap_subtable = (
        struct.pack(">HHHHHHH", 4, 32, 0, 4, 4, 1, 0)
        + struct.pack(">HH", 0x0041, 0xFFFF)
        + struct.pack(">H", 0)
        + struct.pack(">HH", 0x0041, 0xFFFF)
        + struct.pack(">hh", -64, 1)
        + struct.pack(">HH", 0, 0)
    )
    cmap = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + cmap_subtable
    head = struct.pack(
        ">IIIIHHQQhhhhHHhhh",
        0x00010000,
        0x00010000,
        0,
        0x5F0F3CF5,
        0,
        1000,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        8,
        2,
        0,
        0,
    )
    hhea = struct.pack(
        ">IhhhHhhhhhhhhhhhH",
        0x00010000,
        800,
        -200,
        0,
        500,
        0,
        500,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        2,
    )
    maxp = struct.pack(
        ">I14H",
        0x00010000,
        2,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    os2 = struct.pack(
        ">HhHHH11h10s4I4sHHHhhhHH",
        0,
        500,
        400,
        5,
        0,
        650,
        600,
        0,
        75,
        650,
        600,
        0,
        350,
        50,
        250,
        0,
        bytes(10),
        1,
        0,
        0,
        0,
        b"VIVD",
        0x0040,
        0x0041,
        0x0041,
        800,
        -200,
        0,
        800,
        200,
    )
    tables = {
        "OS/2": os2,
        "cmap": cmap,
        "glyf": bytes(20),
        "head": head,
        "hhea": hhea,
        "hmtx": struct.pack(">HhHh", 500, 0, 500, 0),
        "loca": struct.pack(">HHH", 0, 5, 10),
        "maxp": maxp,
        "name": name,
        "post": struct.pack(">IIhhIIIII", 0x00030000, 0, 0, 0, 0, 0, 0, 0, 0),
    }
    num_tables = len(tables)
    header = struct.pack(">IHHHH", 0x00010000, num_tables, 128, 3, 32)
    offset = len(header) + 16 * num_tables
    records = bytearray()
    bodies = bytearray()
    table_offsets: dict[str, int] = {}
    for tag, content in sorted(tables.items()):
        table_offsets[tag] = offset
        records.extend(
            struct.pack(
                ">4sIII",
                tag.encode("ascii"),
                _font_checksum(content),
                offset,
                len(content),
            )
        )
        padded = content + bytes(-len(content) % 4)
        bodies.extend(padded)
        offset += len(padded)

    font = bytearray(header + records + bodies)
    adjustment = (0xB1B0AFBA - _font_checksum(font)) & 0xFFFFFFFF
    struct.pack_into(">I", font, table_offsets["head"] + 8, adjustment)
    return bytes(font)


def _cache_path(cache_root: Path, resource: DependencyResource) -> Path:
    return cache_root / resource.sha256 / "resource"


def _prepare_resource(cache_root: Path, resource: DependencyResource) -> Path:
    target = _cache_path(cache_root, resource)
    if target.is_file() and _digest(target.read_bytes()) == resource.sha256:
        return target
    target.unlink(missing_ok=True)

    opener = urllib.request.build_opener(RejectRedirects())
    with opener.open(resource.url, timeout=2) as response:
        expected_length = response.headers.get("Content-Length")
        try:
            content = response.read()
        except http.client.IncompleteRead as error:
            raise ValueError(
                f"partial dependency response: received {len(error.partial)} bytes"
            ) from error
    if expected_length is not None and len(content) != int(expected_length):
        raise ValueError(
            "partial dependency response: "
            f"expected {expected_length} bytes, received {len(content)}"
        )
    actual = _digest(content)
    if actual != resource.sha256:
        raise ValueError(
            f"dependency integrity mismatch: expected {resource.sha256}, got {actual}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as staged_file:
        staged_file.write(content)
        staged = Path(staged_file.name)
    try:
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)
    return target


def _prepare_resources(
    cache_root: Path,
    resources: Sequence[DependencyResource],
) -> dict[str, Path]:
    prepared: dict[str, Path] = {}
    failures: list[ResourceFailure] = []
    for resource in resources:
        try:
            prepared[resource.name] = _prepare_resource(cache_root, resource)
        except (
            http.client.HTTPException,
            OSError,
            urllib.error.URLError,
            ValueError,
        ) as error:
            failures.append(ResourceFailure(resource.name, str(error)))
    if failures:
        raise DependencyPreparationError(failures)
    return prepared


@contextmanager
def _running_server(
    handler: type[http.server.BaseHTTPRequestHandler],
) -> Generator[RunningServer, None, None]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    running = RunningServer(
        server=server,
        thread=thread,
        base_url=f"http://127.0.0.1:{server.server_port}",
    )
    try:
        yield running
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@contextmanager
def _upstream_dependency() -> Generator[tuple[str, list[str]], None, None]:
    content = {
        "/dependency.js": (DEPENDENCY_CONTENT, "text/javascript"),
    }
    with _upstream_resources(content) as (base_url, requests):
        yield f"{base_url}/dependency.js", requests


@contextmanager
def _upstream_resources(
    content: Mapping[str, tuple[bytes, str]],
) -> Generator[tuple[str, list[str]], None, None]:
    requests: list[str] = []

    class UpstreamHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            requests.append(self.path)
            resource = content.get(self.path)
            if resource is None:
                self.send_error(http.HTTPStatus.NOT_FOUND)
                return
            body, content_type = resource
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _running_server(UpstreamHandler) as upstream:
        yield upstream.base_url, requests


@contextmanager
def _failing_upstream() -> Generator[tuple[str, list[str]], None, None]:
    requests: list[str] = []

    class FailingHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            requests.append(self.path)
            if self.path == "/wrong.js":
                self._send(b"wrong content")
                return
            if self.path == "/unavailable.js":
                self.send_error(http.HTTPStatus.SERVICE_UNAVAILABLE)
                return
            if self.path == "/redirect.js":
                self.send_response(http.HTTPStatus.FOUND)
                self.send_header("Location", "/redirect-target.js")
                self.end_headers()
                return
            if self.path == "/redirect-target.js":
                self._send(b"redirect target")
                return
            if self.path == "/partial.js":
                content = b"partial"
                self.send_response(http.HTTPStatus.OK)
                self.send_header("Content-Type", "text/javascript")
                self.send_header("Content-Length", str(len(content) + 10))
                self.end_headers()
                self.wfile.write(content)
                self.close_connection = True
                return
            self.send_error(http.HTTPStatus.NOT_FOUND)

        def _send(self, content: bytes) -> None:
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    with _running_server(FailingHandler) as upstream:
        yield upstream.base_url, requests


def _index_html(
    resource: DependencyResource,
    dependency_base_url: str | None,
) -> bytes:
    environment = _environment_script(dependency_base_url)
    dependency_url = json.dumps(resource.url)
    resource_name = json.dumps(resource.name)
    return f"""<!doctype html>
<html>
<body>
  <output id="result">loading</output>
  {environment}
  <script type="module">
    const environment = globalThis.__VIVIDLY_ENVIRONMENT__;
    const dependencyUrl = environment?.dependencyBaseUrl
      ? new URL(
          {resource_name},
          new URL(environment.dependencyBaseUrl, document.baseURI),
        )
      : new URL({dependency_url});
    const dependency = await import(dependencyUrl);
    document.querySelector("#result").textContent = dependency.message;
  </script>
</body>
</html>
""".encode()


def _environment_script(dependency_base_url: str | None) -> str:
    return (
        "<script>"
        "globalThis.__VIVIDLY_ENVIRONMENT__ = Object.freeze("
        f"{{dependencyBaseUrl:{json.dumps(dependency_base_url)}}}"
        ");"
        "</script>"
        if dependency_base_url is not None
        else ""
    )


def _font_index_html(
    resource: DependencyResource,
    dependency_base_url: str | None,
) -> bytes:
    environment = _environment_script(dependency_base_url)
    dependency_url = json.dumps(resource.url)
    resource_name = json.dumps(resource.name)
    return f"""<!doctype html>
<html>
<body>
  <output id="result">loading</output>
  {environment}
  <script>
    const environment = globalThis.__VIVIDLY_ENVIRONMENT__;
    const stylesheetUrl = environment?.dependencyBaseUrl
      ? new URL(
          {resource_name},
          new URL(environment.dependencyBaseUrl, document.baseURI),
        )
      : new URL({dependency_url});
    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = stylesheetUrl;
    stylesheet.onload = async () => {{
      const faces = await document.fonts.load('24px "Vividly Spike"', "A");
      await document.fonts.ready;
      const loaded =
        faces.length > 0 && document.fonts.check('24px "Vividly Spike"', "A");
      document.querySelector("#result").textContent =
        loaded ? "font loaded" : "font failed";
    }};
    document.head.append(stylesheet);
  </script>
</body>
</html>
""".encode()


def _global_bootstrap_index_html(
    resource: DependencyResource,
    dependency_base_url: str | None,
) -> bytes:
    environment = _environment_script(dependency_base_url)
    dependency_url = json.dumps(resource.url)
    resource_name = json.dumps(resource.name)
    return f"""<!doctype html>
<html>
<head>{environment}</head>
<body>
  <output id="result">loading</output>
  <script>
    const environment = globalThis.__VIVIDLY_ENVIRONMENT__;
    const dependencyUrl = environment?.dependencyBaseUrl
      ? new URL(
          {resource_name},
          new URL(environment.dependencyBaseUrl, document.baseURI),
        )
      : new URL({dependency_url});
    const dependency = document.createElement("script");
    dependency.src = dependencyUrl;
    dependency.onload = () => {{
      document.querySelector("#result").textContent =
        `global loaded: ${{globalThis.SpikeClassic.version}}`;
    }};
    document.head.append(dependency);
  </script>
</body>
</html>
""".encode()


def _element_bootstrap_index_html(
    resource: DependencyResource,
    dependency_base_url: str | None,
) -> bytes:
    attribute = (
        f' dependency-base-url="{dependency_base_url}"'
        if dependency_base_url is not None
        else ""
    )
    dependency_url = json.dumps(resource.url)
    resource_name = json.dumps(resource.name)
    return f"""<!doctype html>
<html>
<body>
  <vividly-spike{attribute}>loading</vividly-spike>
  <script type="module">
    class VividlySpike extends HTMLElement {{
      async connectedCallback() {{
        const dependencyBaseUrl = this.getAttribute("dependency-base-url");
        const dependencyUrl = dependencyBaseUrl
          ? new URL(
              {resource_name},
              new URL(dependencyBaseUrl, document.baseURI),
            )
          : new URL({dependency_url});
        await new Promise((resolve, reject) => {{
          const dependency = document.createElement("script");
          dependency.src = dependencyUrl;
          dependency.onload = resolve;
          dependency.onerror = reject;
          document.head.append(dependency);
        }});
        this.textContent = `element loaded: ${{globalThis.SpikeClassic.version}}`;
      }}
    }}
    customElements.define("vividly-spike", VividlySpike);
  </script>
</body>
</html>
""".encode()


def _switching_index_builder(
    second_resource: DependencyResource,
) -> Callable[[DependencyResource, str | None], bytes]:
    def build(
        first_resource: DependencyResource,
        dependency_base_url: str | None,
    ) -> bytes:
        def resource_url(resource: DependencyResource) -> str:
            if dependency_base_url is None:
                return resource.url
            return f"{dependency_base_url}{resource.name}"

        first_url = json.dumps(resource_url(first_resource))
        second_url = json.dumps(resource_url(second_resource))
        return f"""<!doctype html>
<html>
<body>
  <output id="result">loading</output>
  <script>
    const load = (url) => new Promise((resolve, reject) => {{
      const dependency = document.createElement("script");
      dependency.src = url;
      dependency.onload = resolve;
      dependency.onerror = reject;
      document.head.append(dependency);
    }});
    (async () => {{
      await load({first_url});
      const captured = globalThis.SpikeClassic;
      await load({second_url});
      document.querySelector("#result").textContent =
        `captured: ${{captured.version}}; global: ${{globalThis.SpikeClassic.version}}`;
    }})();
  </script>
</body>
</html>
""".encode()

    return build


def _site_handler(
    resources: Sequence[DependencyResource],
    cached_paths: Mapping[str, Path] | None,
    *,
    base_path: str,
    entrypoint: str,
    index_builder: Callable[[DependencyResource, str | None], bytes] = _index_html,
) -> type[http.server.BaseHTTPRequestHandler]:
    resources_by_name = {resource.name: resource for resource in resources}
    resource = resources_by_name[entrypoint]
    dependency_base_url = (
        f"{base_path}~dependencies/" if cached_paths is not None else None
    )
    index = index_builder(resource, dependency_base_url)
    dependency_prefix = f"{base_path}~dependencies/"

    class SiteHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            if self.path == base_path:
                self._send(index, "text/html")
                return
            if cached_paths is not None and self.path.startswith(dependency_prefix):
                name = self.path.removeprefix(dependency_prefix)
                cached_path = cached_paths.get(name)
                dependency = resources_by_name.get(name)
                if cached_path is not None and dependency is not None:
                    self._send(cached_path.read_bytes(), dependency.content_type)
                    return
            self.send_error(http.HTTPStatus.NOT_FOUND)

        def _send(self, content: bytes, content_type: str) -> None:
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return SiteHandler


def _request(base_url: str, path: str) -> tuple[int, bytes]:
    parsed = urlsplit(base_url)
    assert parsed.hostname is not None
    assert parsed.port is not None
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _assert_dependency_loaded(
    page_url: str,
    *,
    expected_text: str = "dependency loaded",
) -> list[str]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        requests: list[str] = []
        page.on("request", lambda request: requests.append(request.url))
        page.goto(page_url, wait_until="domcontentloaded")
        page.get_by_text(expected_text, exact=True).wait_for()
        browser.close()
        return requests


@pytest.mark.parametrize("base_path", ["/", "/vividly/"])
def test_local_capability_uses_cold_then_warm_cache(
    chromium: None,
    tmp_path: Path,
    base_path: str,
) -> None:
    del chromium
    cache_root = tmp_path / "cache"
    with _upstream_dependency() as (dependency_url, upstream_requests):
        resource = DependencyResource(
            name="esm/module.js",
            url=dependency_url,
            sha256=DEPENDENCY_SHA256,
            content_type="text/javascript",
        )
        cached = _prepare_resources(cache_root, [resource])
        assert upstream_requests == ["/dependency.js"]

        with _running_server(
            _site_handler(
                [resource],
                cached,
                base_path=base_path,
                entrypoint="esm/module.js",
            )
        ) as site:
            requests = _assert_dependency_loaded(f"{site.base_url}{base_path}")
            assert f"{site.base_url}{base_path}~dependencies/esm/module.js" in requests
            assert dependency_url not in requests

    resource = DependencyResource(
        name="esm/module.js",
        url=dependency_url,
        sha256=DEPENDENCY_SHA256,
        content_type="text/javascript",
    )
    cached = _prepare_resources(cache_root, [resource])
    with _running_server(
        _site_handler(
            [resource],
            cached,
            base_path=base_path,
            entrypoint="esm/module.js",
        )
    ) as site:
        requests = _assert_dependency_loaded(f"{site.base_url}{base_path}")
        assert f"{site.base_url}{base_path}~dependencies/esm/module.js" in requests
        assert dependency_url not in requests


def test_static_site_omits_capability_and_imports_declared_url(
    chromium: None,
) -> None:
    del chromium
    with _upstream_dependency() as (dependency_url, upstream_requests):
        resource = DependencyResource(
            name="esm/module.js",
            url=dependency_url,
            sha256=DEPENDENCY_SHA256,
            content_type="text/javascript",
        )
        with _running_server(
            _site_handler(
                [resource],
                None,
                base_path="/vividly/",
                entrypoint="esm/module.js",
            )
        ) as site:
            status, index = _request(site.base_url, "/vividly/")
            assert status == 200
            assert b"__VIVIDLY_ENVIRONMENT__ = " not in index

            requests = _assert_dependency_loaded(f"{site.base_url}/vividly/")
            assert dependency_url in requests
            assert upstream_requests == ["/dependency.js"]


def test_multifile_dependency_preserves_relative_resource_graph(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    upstream_content = {
        "/multi/module.js": (MULTI_MODULE_CONTENT, "text/javascript"),
        "/multi/answer.wasm": (WASM_CONTENT, "application/wasm"),
        "/multi/optional.dat": (OPTIONAL_CONTENT, "application/octet-stream"),
    }
    cache_root = tmp_path / "cache"

    with _upstream_resources(upstream_content) as (upstream_url, upstream_requests):
        resources = [
            DependencyResource(
                name="multi/module.js",
                url=f"{upstream_url}/multi/module.js",
                sha256=_digest(MULTI_MODULE_CONTENT),
                content_type="text/javascript",
            ),
            DependencyResource(
                name="multi/answer.wasm",
                url=f"{upstream_url}/multi/answer.wasm",
                sha256=_digest(WASM_CONTENT),
                content_type="application/wasm",
            ),
            DependencyResource(
                name="multi/optional.dat",
                url=f"{upstream_url}/multi/optional.dat",
                sha256=_digest(OPTIONAL_CONTENT),
                content_type="application/octet-stream",
            ),
        ]
        cached = _prepare_resources(cache_root, resources)
        assert upstream_requests == [
            "/multi/module.js",
            "/multi/answer.wasm",
            "/multi/optional.dat",
        ]
        assert set(cached) == {
            "multi/module.js",
            "multi/answer.wasm",
            "multi/optional.dat",
        }
        assert all(path.is_file() for path in cached.values())

        with _running_server(
            _site_handler(
                resources,
                cached,
                base_path="/vividly/",
                entrypoint="multi/module.js",
            )
        ) as local_site:
            local_requests = _assert_dependency_loaded(
                f"{local_site.base_url}/vividly/",
                expected_text="dependency loaded: 42",
            )
            assert (
                f"{local_site.base_url}/vividly/~dependencies/multi/module.js"
                in local_requests
            )
            assert (
                f"{local_site.base_url}/vividly/~dependencies/multi/answer.wasm"
                in local_requests
            )
            assert not any("optional.dat" in request for request in local_requests)
            status, _ = _request(
                local_site.base_url,
                "/vividly/~dependencies/multi/undeclared.dat",
            )
            assert status == http.HTTPStatus.NOT_FOUND

        with _running_server(
            _site_handler(
                resources,
                None,
                base_path="/vividly/",
                entrypoint="multi/module.js",
            )
        ) as static_site:
            static_requests = _assert_dependency_loaded(
                f"{static_site.base_url}/vividly/",
                expected_text="dependency loaded: 42",
            )
            assert f"{upstream_url}/multi/module.js" in static_requests
            assert f"{upstream_url}/multi/answer.wasm" in static_requests
            assert not any("optional.dat" in request for request in static_requests)

    warm_cached = _prepare_resources(cache_root, resources)
    with _running_server(
        _site_handler(
            resources,
            warm_cached,
            base_path="/vividly/",
            entrypoint="multi/module.js",
        )
    ) as warm_site:
        warm_requests = _assert_dependency_loaded(
            f"{warm_site.base_url}/vividly/",
            expected_text="dependency loaded: 42",
        )
        assert (
            f"{warm_site.base_url}/vividly/~dependencies/multi/answer.wasm"
            in warm_requests
        )


def test_invalid_cache_entry_is_repaired_from_declared_url(tmp_path: Path) -> None:
    with _upstream_dependency() as (dependency_url, upstream_requests):
        resource = DependencyResource(
            name="esm/module.js",
            url=dependency_url,
            sha256=DEPENDENCY_SHA256,
            content_type="text/javascript",
        )
        target = _cache_path(tmp_path, resource)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"corrupt cache entry")

        prepared = _prepare_resources(tmp_path, [resource])

    assert upstream_requests == ["/dependency.js"]
    assert prepared == {"esm/module.js": target}
    assert target.read_bytes() == DEPENDENCY_CONTENT
    assert list(target.parent.iterdir()) == [target]


def test_preparation_aggregates_failures_without_corrupt_cache_entries(
    tmp_path: Path,
) -> None:
    with _failing_upstream() as (upstream_url, upstream_requests):
        resources = [
            DependencyResource(
                name="failures/wrong.js",
                url=f"{upstream_url}/wrong.js",
                sha256=_digest(b"expected content"),
                content_type="text/javascript",
            ),
            DependencyResource(
                name="failures/unavailable.js",
                url=f"{upstream_url}/unavailable.js",
                sha256=_digest(b"unavailable"),
                content_type="text/javascript",
            ),
            DependencyResource(
                name="failures/redirect.js",
                url=f"{upstream_url}/redirect.js",
                sha256=_digest(b"redirect target"),
                content_type="text/javascript",
            ),
            DependencyResource(
                name="failures/partial.js",
                url=f"{upstream_url}/partial.js",
                sha256=_digest(b"partial"),
                content_type="text/javascript",
            ),
        ]
        corrupt_target = _cache_path(tmp_path, resources[0])
        corrupt_target.parent.mkdir(parents=True)
        corrupt_target.write_bytes(b"existing corrupt content")

        with pytest.raises(DependencyPreparationError) as raised:
            _prepare_resources(tmp_path, resources)

    assert [failure.name for failure in raised.value.failures] == [
        "failures/wrong.js",
        "failures/unavailable.js",
        "failures/redirect.js",
        "failures/partial.js",
    ]
    reasons = [failure.reason for failure in raised.value.failures]
    assert "integrity mismatch" in reasons[0]
    assert "503" in reasons[1]
    assert "302" in reasons[2]
    assert "partial dependency response" in reasons[3]
    assert upstream_requests == [
        "/wrong.js",
        "/unavailable.js",
        "/redirect.js",
        "/partial.js",
    ]
    assert "/redirect-target.js" not in upstream_requests
    assert all(not _cache_path(tmp_path, resource).exists() for resource in resources)


def test_css_relative_font_loads_locally_statically_and_from_warm_cache(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    font_content = _build_test_font()
    assert _font_checksum(font_content) == 0xB1B0AFBA
    upstream_content = {
        "/font/style.css": (FONT_CSS_CONTENT, "text/css"),
        "/font/spike.ttf": (font_content, "font/ttf"),
    }
    cache_root = tmp_path / "cache"

    with _upstream_resources(upstream_content) as (upstream_url, upstream_requests):
        resources = [
            DependencyResource(
                name="font/style.css",
                url=f"{upstream_url}/font/style.css",
                sha256=_digest(FONT_CSS_CONTENT),
                content_type="text/css",
            ),
            DependencyResource(
                name="font/spike.ttf",
                url=f"{upstream_url}/font/spike.ttf",
                sha256=_digest(font_content),
                content_type="font/ttf",
            ),
        ]
        cached = _prepare_resources(cache_root, resources)
        assert upstream_requests == ["/font/style.css", "/font/spike.ttf"]

        with _running_server(
            _site_handler(
                resources,
                cached,
                base_path="/vividly/",
                entrypoint="font/style.css",
                index_builder=_font_index_html,
            )
        ) as local_site:
            local_requests = _assert_dependency_loaded(
                f"{local_site.base_url}/vividly/",
                expected_text="font loaded",
            )
            assert (
                f"{local_site.base_url}/vividly/~dependencies/font/style.css"
                in local_requests
            )
            assert (
                f"{local_site.base_url}/vividly/~dependencies/font/spike.ttf"
                in local_requests
            )
            assert not any(
                request.startswith(upstream_url) for request in local_requests
            )

        with _running_server(
            _site_handler(
                resources,
                None,
                base_path="/vividly/",
                entrypoint="font/style.css",
                index_builder=_font_index_html,
            )
        ) as static_site:
            static_requests = _assert_dependency_loaded(
                f"{static_site.base_url}/vividly/",
                expected_text="font loaded",
            )
            assert f"{upstream_url}/font/style.css" in static_requests
            assert f"{upstream_url}/font/spike.ttf" in static_requests

    warm_cached = _prepare_resources(cache_root, resources)
    with _running_server(
        _site_handler(
            resources,
            warm_cached,
            base_path="/vividly/",
            entrypoint="font/style.css",
            index_builder=_font_index_html,
        )
    ) as warm_site:
        warm_requests = _assert_dependency_loaded(
            f"{warm_site.base_url}/vividly/",
            expected_text="font loaded",
        )
        assert (
            f"{warm_site.base_url}/vividly/~dependencies/font/spike.ttf"
            in warm_requests
        )


def test_root_element_configuration_is_sufficient_for_classic_bootstrap(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    upstream_content = {
        "/classic/v1.js": (CLASSIC_V1_CONTENT, "text/javascript"),
    }
    with _upstream_resources(upstream_content) as (upstream_url, upstream_requests):
        resource = DependencyResource(
            name="classic/v1.js",
            url=f"{upstream_url}/classic/v1.js",
            sha256=_digest(CLASSIC_V1_CONTENT),
            content_type="text/javascript",
        )
        cached = _prepare_resources(tmp_path, [resource])
        assert upstream_requests == ["/classic/v1.js"]

        with _running_server(
            _site_handler(
                [resource],
                cached,
                base_path="/vividly/",
                entrypoint="classic/v1.js",
                index_builder=_global_bootstrap_index_html,
            )
        ) as global_site:
            status, global_index = _request(global_site.base_url, "/vividly/")
            assert status == http.HTTPStatus.OK
            assert b"__VIVIDLY_ENVIRONMENT__ = " in global_index
            global_requests = _assert_dependency_loaded(
                f"{global_site.base_url}/vividly/",
                expected_text="global loaded: v1",
            )
            assert (
                f"{global_site.base_url}/vividly/~dependencies/classic/v1.js"
                in global_requests
            )

        with _running_server(
            _site_handler(
                [resource],
                cached,
                base_path="/vividly/",
                entrypoint="classic/v1.js",
                index_builder=_element_bootstrap_index_html,
            )
        ) as element_site:
            status, element_index = _request(element_site.base_url, "/vividly/")
            assert status == http.HTTPStatus.OK
            assert b"__VIVIDLY_ENVIRONMENT__" not in element_index
            assert b'dependency-base-url="/vividly/~dependencies/"' in element_index
            element_requests = _assert_dependency_loaded(
                f"{element_site.base_url}/vividly/",
                expected_text="element loaded: v1",
            )
            assert (
                f"{element_site.base_url}/vividly/~dependencies/classic/v1.js"
                in element_requests
            )

        with _running_server(
            _site_handler(
                [resource],
                None,
                base_path="/vividly/",
                entrypoint="classic/v1.js",
                index_builder=_element_bootstrap_index_html,
            )
        ) as static_site:
            status, static_index = _request(static_site.base_url, "/vividly/")
            assert status == http.HTTPStatus.OK
            assert b"<vividly-spike>loading" in static_index
            assert b"<vividly-spike dependency-base-url=" not in static_index
            static_requests = _assert_dependency_loaded(
                f"{static_site.base_url}/vividly/",
                expected_text="element loaded: v1",
            )
            assert resource.url in static_requests


def test_classic_global_version_switch_requires_a_fresh_document(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    upstream_content = {
        "/classic/v1.js": (CLASSIC_V1_CONTENT, "text/javascript"),
        "/classic/v2.js": (CLASSIC_V2_CONTENT, "text/javascript"),
    }
    with _upstream_resources(upstream_content) as (upstream_url, _):
        first = DependencyResource(
            name="classic/v1.js",
            url=f"{upstream_url}/classic/v1.js",
            sha256=_digest(CLASSIC_V1_CONTENT),
            content_type="text/javascript",
        )
        second = DependencyResource(
            name="classic/v2.js",
            url=f"{upstream_url}/classic/v2.js",
            sha256=_digest(CLASSIC_V2_CONTENT),
            content_type="text/javascript",
        )
        resources = [first, second]
        cached = _prepare_resources(tmp_path, resources)

    with _running_server(
        _site_handler(
            resources,
            cached,
            base_path="/vividly/",
            entrypoint="classic/v1.js",
            index_builder=_switching_index_builder(second),
        )
    ) as switching_site:
        _assert_dependency_loaded(
            f"{switching_site.base_url}/vividly/",
            expected_text="captured: v1; global: v2",
        )

    for resource, expected_version in ((first, "v1"), (second, "v2")):
        with _running_server(
            _site_handler(
                resources,
                cached,
                base_path="/vividly/",
                entrypoint=resource.name,
                index_builder=_global_bootstrap_index_html,
            )
        ) as fresh_site:
            _assert_dependency_loaded(
                f"{fresh_site.base_url}/vividly/",
                expected_text=f"global loaded: {expected_version}",
            )


def test_static_cross_origin_worker_url_is_not_supported(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    upstream_content = {
        "/worker/module.js": (WORKER_MODULE_CONTENT, "text/javascript"),
        "/worker/worker.js": (WORKER_CONTENT, "text/javascript"),
    }
    with _upstream_resources(upstream_content) as (upstream_url, upstream_requests):
        resources = [
            DependencyResource(
                name="worker/module.js",
                url=f"{upstream_url}/worker/module.js",
                sha256=_digest(WORKER_MODULE_CONTENT),
                content_type="text/javascript",
            ),
            DependencyResource(
                name="worker/worker.js",
                url=f"{upstream_url}/worker/worker.js",
                sha256=_digest(WORKER_CONTENT),
                content_type="text/javascript",
            ),
        ]
        cached = _prepare_resources(tmp_path, resources)
        assert upstream_requests == ["/worker/module.js", "/worker/worker.js"]

        with _running_server(
            _site_handler(
                resources,
                cached,
                base_path="/vividly/",
                entrypoint="worker/module.js",
            )
        ) as local_site:
            local_requests = _assert_dependency_loaded(
                f"{local_site.base_url}/vividly/",
                expected_text="worker loaded: 7",
            )
            assert (
                f"{local_site.base_url}/vividly/~dependencies/worker/worker.js"
                in local_requests
            )

        with _running_server(
            _site_handler(
                resources,
                None,
                base_path="/vividly/",
                entrypoint="worker/module.js",
            )
        ) as static_site:
            static_requests = _assert_dependency_loaded(
                f"{static_site.base_url}/vividly/",
                expected_text="worker failed: SecurityError",
            )
            assert f"{upstream_url}/worker/module.js" in static_requests
            assert f"{upstream_url}/worker/worker.js" not in static_requests
