"""Stage 0 spike for static dependency resolution through a Service Worker."""

import hashlib
import http.server
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, sync_playwright

WASM_CONTENT = bytes.fromhex(
    "0061736d01000000"
    "0105016000017f"
    "03020100"
    "070a0106616e737765720000"
    "0a06010400412a0b"
)
MAIN_MODULE_CONTENT = b"""
const worker = new Worker(new URL("./worker.js", import.meta.url), {
  type: "module",
});
export const message = await new Promise((resolve, reject) => {
  worker.onmessage = (event) => {
    resolve(`resolver loaded: ${event.data}`);
    worker.terminate();
  };
  worker.onerror = reject;
});
"""
WORKER_CONTENT = b"""
import { helper } from "./helper.js";
const dataResponse = await fetch(new URL("./data.json", import.meta.url));
const data = await dataResponse.json();
const wasmResponse = await fetch(new URL("./answer.wasm", import.meta.url));
const { instance } = await WebAssembly.instantiateStreaming(wasmResponse);
self.postMessage(`${helper}/${data.value}/${instance.exports.answer()}`);
"""
HELPER_CONTENT = b"export const helper = 5;\n"
DATA_CONTENT = b'{"value": 6}\n'
OPTIONAL_CONTENT = b"declared but not requested by page code\n"


@dataclass(frozen=True)
class DependencyResource:
    """One exact resource in the Service Worker mapping."""

    name: str
    content: bytes
    content_type: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class RunningServer:
    """One temporary threaded HTTP server."""

    server: http.server.ThreadingHTTPServer
    thread: threading.Thread
    base_url: str


@dataclass
class MutableDeployment:
    """Currently published lifecycle-spike assets."""

    index: bytes
    service_worker: bytes


class FetchResult(TypedDict):
    """Browser result for one fetch."""

    status: int
    text: str


class ResponseDetails(FetchResult):
    """Browser-visible response details for security assertions."""

    content_type: str | None
    service_worker_allowed: str | None
    upstream_header: str | None


class UpstreamObservation(TypedDict):
    """Request metadata observed by the deterministic upstream."""

    path: str
    cookie: str | None
    referer: str | None


RESOURCES = (
    DependencyResource("graph/main.js", MAIN_MODULE_CONTENT, "text/javascript"),
    DependencyResource("graph/worker.js", WORKER_CONTENT, "text/javascript"),
    DependencyResource("graph/helper.js", HELPER_CONTENT, "text/javascript"),
    DependencyResource("graph/data.json", DATA_CONTENT, "application/json"),
    DependencyResource("graph/answer.wasm", WASM_CONTENT, "application/wasm"),
    DependencyResource(
        "graph/optional.dat",
        OPTIONAL_CONTENT,
        "application/octet-stream",
    ),
)


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
    resources: tuple[DependencyResource, ...],
    requests: list[str],
) -> type[http.server.BaseHTTPRequestHandler]:
    content = {
        f"/upstream/{resource.name}": resource
        for resource in resources
    }

    class UpstreamHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            requests.append(path)
            resource = content.get(path)
            if resource is None:
                self.send_error(http.HTTPStatus.NOT_FOUND)
                return
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", resource.content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(resource.content)))
            self.end_headers()
            self.wfile.write(resource.content)

    return UpstreamHandler


def _service_worker_script(
    resources: tuple[DependencyResource, ...],
    upstream_base_url: str,
    cache_name: str,
    *,
    eager_names: tuple[str, ...] | None = None,
) -> bytes:
    mapping = {
        resource.name: {
            "url": f"{upstream_base_url}/upstream/{resource.name}",
            "sha256": resource.sha256,
            "contentType": resource.content_type,
        }
        for resource in resources
    }
    eager = (
        [resource.name for resource in resources]
        if eager_names is None
        else list(eager_names)
    )
    template = r"""
const CACHE_NAME = __CACHE_NAME__;
const RESOURCES = Object.freeze(__RESOURCES__);
const EAGER_RESOURCES = Object.freeze(__EAGER_RESOURCES__);
const dependencyBaseUrl = new URL("./~dependencies/", self.registration.scope);

function virtualUrl(name) {
  return new URL(name, dependencyBaseUrl).href;
}

async function digest(bytes) {
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function verifiedResponse(bytes, resource) {
  return new Response(bytes, {
    status: 200,
    headers: {
      "Content-Type": resource.contentType,
      "Cache-Control": "no-store",
      "X-Vividly-Content-SHA256": resource.sha256,
    },
  });
}

async function acquire(name, resource) {
  const upstream = await fetch(resource.url, {
    mode: "cors",
    credentials: "omit",
    redirect: "error",
    referrerPolicy: "no-referrer",
    cache: "no-store",
  });
  if (!upstream.ok || upstream.type === "opaque") {
    throw new Error(`Cannot acquire dependency ${name}: HTTP ${upstream.status}`);
  }
  const bytes = await upstream.arrayBuffer();
  const actual = await digest(bytes);
  if (actual !== resource.sha256) {
    throw new Error(
      `Integrity mismatch for ${name}: expected ${resource.sha256}, got ${actual}`,
    );
  }
  const response = verifiedResponse(bytes, resource);
  const cache = await caches.open(CACHE_NAME);
  await cache.put(virtualUrl(name), response.clone());
  return response;
}

async function resolve(name, resource) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(virtualUrl(name));
  if (cached) {
    const bytes = await cached.arrayBuffer();
    if (await digest(bytes) === resource.sha256) {
      return verifiedResponse(bytes, resource);
    }
    await cache.delete(virtualUrl(name));
  }
  return acquire(name, resource);
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    await Promise.all(
      EAGER_RESOURCES.map((name) => acquire(name, RESOURCES[name])),
    );
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (!url.pathname.startsWith(dependencyBaseUrl.pathname)) return;

  if (event.request.method !== "GET") {
    event.respondWith(new Response("Method not allowed", { status: 405 }));
    return;
  }

  const name = url.pathname.slice(dependencyBaseUrl.pathname.length);
  const resource = url.search === "" ? RESOURCES[name] : undefined;
  if (!resource) {
    event.respondWith(new Response("Undeclared dependency", { status: 404 }));
    return;
  }
  event.respondWith(
    resolve(name, resource).catch(
      (error) => new Response(`Dependency resolution failed: ${error.message}`, {
        status: 502,
        headers: { "Content-Type": "text/plain" },
      }),
    ),
  );
});
"""
    return (
        template.replace("__CACHE_NAME__", json.dumps(cache_name))
        .replace("__RESOURCES__", json.dumps(mapping, separators=(",", ":")))
        .replace("__EAGER_RESOURCES__", json.dumps(eager))
        .encode()
    )


def _index_html(
    *,
    entrypoint: str | None = "./~dependencies/graph/main.js",
    set_test_cookie: bool = False,
) -> bytes:
    action = (
        f"""
      const dependency = await import({json.dumps(entrypoint)});
      result.textContent = dependency.message;
"""
        if entrypoint is not None
        else '      result.textContent = "resolver ready";\n'
    )
    cookie_script = (
        '<script>document.cookie = "vividly-secret=do-not-forward; Path=/";</script>'
        if set_test_cookie
        else ""
    )
    template = """<!doctype html>
<html>
<body>
  <output id="result">loading</output>
  __COOKIE_SCRIPT__
  <script type="module">
    const result = document.querySelector("#result");
    try {
      await navigator.serviceWorker.register("./service-worker.js", {
        scope: "./",
        updateViaCache: "none",
      });
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise((resolve, reject) => {
          const timeout = setTimeout(
            () => reject(new Error("Service Worker did not take control")),
            5000,
          );
          navigator.serviceWorker.addEventListener("controllerchange", () => {
            clearTimeout(timeout);
            resolve();
          }, { once: true });
        });
      }
__ACTION__
    } catch (error) {
      result.textContent = `error: ${error.message}`;
    }
  </script>
</body>
</html>
"""
    return (
        template.replace("__COOKIE_SCRIPT__", cookie_script)
        .replace("__ACTION__", action)
        .encode()
    )


def _site_handler(
    *,
    base_path: str,
    service_worker: bytes,
    requests: list[str],
    index: bytes | None = None,
) -> type[http.server.BaseHTTPRequestHandler]:
    service_worker_path = f"{base_path}service-worker.js"
    dependency_prefix = f"{base_path}~dependencies/"
    index_content = _index_html() if index is None else index

    class SiteHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            requests.append(path)
            if path == base_path:
                self._send(index_content, "text/html")
                return
            if path == service_worker_path:
                self._send(service_worker, "text/javascript")
                return
            if path.startswith(dependency_prefix):
                self.send_error(http.HTTPStatus.NOT_FOUND)
                return
            self.send_error(http.HTTPStatus.NOT_FOUND)

        def _send(self, content: bytes, content_type: str) -> None:
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return SiteHandler


def _adversarial_upstream_handler(
    observations: list[UpstreamObservation],
) -> type[http.server.BaseHTTPRequestHandler]:
    class AdversarialHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            observations.append(
                {
                    "path": path,
                    "cookie": self.headers.get("Cookie"),
                    "referer": self.headers.get("Referer"),
                }
            )
            if path == "/upstream/security/good.js":
                self._send(
                    b"verified content\n",
                    dangerous_headers=True,
                )
                return
            if path == "/upstream/security/wrong.js":
                self._send(b"unexpected content\n")
                return
            if path == "/upstream/security/redirect.js":
                self.send_response(http.HTTPStatus.FOUND)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Location", "/upstream/security/redirect-target.js")
                self.end_headers()
                return
            if path == "/upstream/security/redirect-target.js":
                self._send(b"redirect target\n")
                return
            if path == "/upstream/security/partial.js":
                content = b"partial content\n"
                self.send_response(http.HTTPStatus.OK)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", "text/javascript")
                self.send_header("Content-Length", str(len(content) + 10))
                self.end_headers()
                self.wfile.write(content)
                self.close_connection = True
                return
            if path == "/upstream/security/cors.js":
                self._send(b"cors content\n", cors=False)
                return
            if path == "/upstream/security/missing.js":
                content = b"missing"
                self.send_response(http.HTTPStatus.NOT_FOUND)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            self.send_error(http.HTTPStatus.NOT_FOUND)

        def _send(
            self,
            content: bytes,
            *,
            cors: bool = True,
            dangerous_headers: bool = False,
        ) -> None:
            self.send_response(http.HTTPStatus.OK)
            if cors:
                self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", str(len(content)))
            if dangerous_headers:
                self.send_header("Service-Worker-Allowed", "/")
                self.send_header("X-Upstream-Secret", "must-not-forward")
                self.send_header("Set-Cookie", "upstream-secret=must-not-store")
            self.end_headers()
            self.wfile.write(content)

    return AdversarialHandler


def _fetch_details(
    page: Page,
    relative_url: str,
    *,
    method: str = "GET",
) -> ResponseDetails:
    return cast(
        ResponseDetails,
        page.evaluate(
            """async ({ url, method }) => {
              const response = await fetch(url, { method });
              return {
                status: response.status,
                text: await response.text(),
                content_type: response.headers.get("Content-Type"),
                service_worker_allowed:
                  response.headers.get("Service-Worker-Allowed"),
                upstream_header: response.headers.get("X-Upstream-Secret"),
              };
            }""",
            {"url": relative_url, "method": method},
        ),
    )


def _put_cache_entry(
    page: Page,
    cache_name: str,
    relative_url: str,
    content: str,
) -> None:
    page.evaluate(
        """async ({ cacheName, relativeUrl, content }) => {
          const cache = await caches.open(cacheName);
          const url = new URL(relativeUrl, location.href).href;
          await cache.put(
            url,
            new Response(content, {
              headers: { "Content-Type": "text/javascript" },
            }),
          );
        }""",
        {
            "cacheName": cache_name,
            "relativeUrl": relative_url,
            "content": content,
        },
    )


def _cache_has(page: Page, cache_name: str, relative_url: str) -> bool:
    return cast(
        bool,
        page.evaluate(
            """async ({ cacheName, relativeUrl }) => {
              const cache = await caches.open(cacheName);
              return Boolean(
                await cache.match(new URL(relativeUrl, location.href).href),
              );
            }""",
            {"cacheName": cache_name, "relativeUrl": relative_url},
        ),
    )


def _versioned_service_worker_script(
    resource: DependencyResource,
    upstream_base_url: str,
    *,
    revision: str,
    cache_prefix: str,
) -> bytes:
    mapping = {
        resource.name: {
            "url": f"{upstream_base_url}/upstream/{resource.name}",
            "sha256": resource.sha256,
            "contentType": resource.content_type,
        }
    }
    template = r"""
const REVISION = __REVISION__;
const CACHE_PREFIX = __CACHE_PREFIX__;
const CACHE_NAME = `${CACHE_PREFIX}${REVISION}`;
const RESOURCES = Object.freeze(__RESOURCES__);
const dependencyBaseUrl = new URL(
  `./~dependencies/${REVISION}/`,
  self.registration.scope,
);

async function deleteObsoleteCaches() {
  const names = await caches.keys();
  await Promise.all(
    names
      .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
      .map((name) => caches.delete(name)),
  );
}

async function digest(bytes) {
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function acquire(name, resource) {
  const upstream = await fetch(resource.url, {
    mode: "cors",
    credentials: "omit",
    redirect: "error",
    referrerPolicy: "no-referrer",
    cache: "no-store",
  });
  if (!upstream.ok || upstream.type === "opaque") {
    throw new Error(`Cannot acquire dependency ${name}: HTTP ${upstream.status}`);
  }
  const bytes = await upstream.arrayBuffer();
  if (await digest(bytes) !== resource.sha256) {
    throw new Error(`Integrity mismatch for ${name}`);
  }
  const response = new Response(bytes, {
    headers: {
      "Content-Type": resource.contentType,
      "Cache-Control": "no-store",
      "X-Vividly-Content-SHA256": resource.sha256,
    },
  });
  const cache = await caches.open(CACHE_NAME);
  await cache.put(new URL(name, dependencyBaseUrl), response.clone());
  return response;
}

async function resolve(name, resource) {
  const cache = await caches.open(CACHE_NAME);
  const virtualUrl = new URL(name, dependencyBaseUrl);
  const cached = await cache.match(virtualUrl);
  if (cached) {
    const bytes = await cached.arrayBuffer();
    if (await digest(bytes) === resource.sha256) {
      return new Response(bytes, {
        headers: {
          "Content-Type": resource.contentType,
          "Cache-Control": "no-store",
          "X-Vividly-Content-SHA256": resource.sha256,
        },
      });
    }
    await cache.delete(virtualUrl);
  }
  return acquire(name, resource);
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    await acquire(__RESOURCE_NAME__, RESOURCES[__RESOURCE_NAME__]);
    if (!self.registration.active) await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    await deleteObsoleteCaches();
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data === "revision") {
    event.ports[0]?.postMessage(REVISION);
    return;
  }
  if (event.data === "ready") {
    event.waitUntil(
      deleteObsoleteCaches().then(
        () => event.ports[0]?.postMessage(REVISION),
      ),
    );
    return;
  }
  if (event.data === "activate") {
    event.waitUntil(self.skipWaiting());
  }
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const reservedBase = new URL("./~dependencies/", self.registration.scope);
  if (!url.pathname.startsWith(reservedBase.pathname)) return;
  if (!url.pathname.startsWith(dependencyBaseUrl.pathname)) {
    event.respondWith(new Response("Mapping revision mismatch", { status: 409 }));
    return;
  }
  const name = url.pathname.slice(dependencyBaseUrl.pathname.length);
  const resource = url.search === "" ? RESOURCES[name] : undefined;
  if (!resource) {
    event.respondWith(new Response("Undeclared dependency", { status: 404 }));
    return;
  }
  event.respondWith(resolve(name, resource));
});
"""
    return (
        template.replace("__REVISION__", json.dumps(revision))
        .replace("__CACHE_PREFIX__", json.dumps(cache_prefix))
        .replace("__RESOURCES__", json.dumps(mapping, separators=(",", ":")))
        .replace("__RESOURCE_NAME__", json.dumps(resource.name))
        .encode()
    )


def _lifecycle_index_html(
    *,
    revision: str,
    resource_name: str,
) -> bytes:
    template = r"""<!doctype html>
<html>
<body>
  <output id="result">loading</output>
  <script type="module">
    const desiredRevision = __REVISION__;
    const resourceName = __RESOURCE_NAME__;
    const result = document.querySelector("#result");

    const workerRevision = (
      worker,
      message = "revision",
    ) => new Promise((resolve, reject) => {
      const channel = new MessageChannel();
      const timeout = setTimeout(
        () => reject(new Error("Worker revision timed out")),
        5000,
      );
      channel.port1.onmessage = (event) => {
        clearTimeout(timeout);
        resolve(event.data);
      };
      worker.postMessage(message, [channel.port2]);
    });

    const waitForInstalled = (worker) => new Promise((resolve, reject) => {
      if (worker.state === "installed") {
        resolve();
        return;
      }
      const timeout = setTimeout(
        () => reject(new Error("Worker installation timed out")),
        5000,
      );
      worker.addEventListener("statechange", () => {
        if (worker.state === "installed") {
          clearTimeout(timeout);
          resolve();
        }
      });
    });

    const waitForControllerChange = () => new Promise((resolve, reject) => {
      const timeout = setTimeout(
        () => reject(new Error("Worker activation timed out")),
        5000,
      );
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        clearTimeout(timeout);
        resolve();
      }, { once: true });
    });

    const load = async () => {
      const dependency = await import(
        `./~dependencies/${desiredRevision}/${resourceName}`
      );
      result.textContent = dependency.message;
    };

    try {
      const registration = await navigator.serviceWorker.register(
        "./service-worker.js",
        { scope: "./", updateViaCache: "none" },
      );
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await waitForControllerChange();
      }
      await registration.update();
      if (registration.installing) {
        await waitForInstalled(registration.installing);
      }
      const activeRevision = await workerRevision(
        navigator.serviceWorker.controller,
      );
      if (activeRevision === desiredRevision) {
        await workerRevision(navigator.serviceWorker.controller, "ready");
        await load();
      } else {
        const waiting = registration.waiting;
        if (!waiting || await workerRevision(waiting) !== desiredRevision) {
          throw new Error("Expected mapping revision is not installed");
        }
        result.textContent = "update waiting";
        globalThis.activateVividlyUpdate = async () => {
          const changed = waitForControllerChange();
          waiting.postMessage("activate");
          await changed;
          await workerRevision(navigator.serviceWorker.controller, "ready");
          await load();
        };
      }
    } catch (error) {
      result.textContent = `error: ${error.message}`;
    }
  </script>
</body>
</html>
"""
    return (
        template.replace("__REVISION__", json.dumps(revision))
        .replace("__RESOURCE_NAME__", json.dumps(resource_name))
        .encode()
    )


def _mutable_site_handler(
    deployment: MutableDeployment,
    requests: list[str],
) -> type[http.server.BaseHTTPRequestHandler]:
    class MutableSiteHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            requests.append(path)
            if path == "/vividly/":
                self._send(deployment.index, "text/html")
                return
            if path == "/vividly/service-worker.js":
                self._send(deployment.service_worker, "text/javascript")
                return
            if path.startswith("/vividly/~dependencies/"):
                self.send_error(http.HTTPStatus.NOT_FOUND)
                return
            self.send_error(http.HTTPStatus.NOT_FOUND)

        def _send(self, content: bytes, content_type: str) -> None:
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return MutableSiteHandler


def _scoped_projects_site_handler(
    deployments: dict[str, MutableDeployment],
    requests: list[str],
) -> type[http.server.BaseHTTPRequestHandler]:
    class ScopedProjectsSiteHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            requests.append(path)
            for project, deployment in deployments.items():
                if path == f"/{project}/":
                    self._send(deployment.index, "text/html")
                    return
                if path == f"/{project}/service-worker.js":
                    self._send(deployment.service_worker, "text/javascript")
                    return
            self.send_error(http.HTTPStatus.NOT_FOUND)

        def _send(self, content: bytes, content_type: str) -> None:
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return ScopedProjectsSiteHandler


@pytest.mark.parametrize("base_path", ["/", "/vividly/"])
def test_service_worker_resolves_relative_worker_graph_from_cold_and_warm_cache(
    chromium: None,
    base_path: str,
) -> None:
    del chromium
    upstream_requests: list[str] = []
    upstream = _start_server(_upstream_handler(RESOURCES, upstream_requests))
    mapping_digest = hashlib.sha256(
        "".join(resource.sha256 for resource in RESOURCES).encode()
    ).hexdigest()
    service_worker = _service_worker_script(
        RESOURCES,
        upstream.base_url,
        f"vividly-spike-{mapping_digest}",
    )
    site_requests: list[str] = []
    site = _start_server(
        _site_handler(
            base_path=base_path,
            service_worker=service_worker,
            requests=site_requests,
        )
    )
    upstream_running = True

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(service_workers="allow")
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            page.goto(f"{site.base_url}{base_path}", wait_until="domcontentloaded")
            page.get_by_text("resolver loaded: 5/6/42", exact=True).wait_for()

            assert page_errors == []
            assert site_requests.count(base_path) == 1
            assert len(upstream_requests) == len(RESOURCES)
            assert set(upstream_requests) == {
                f"/upstream/{resource.name}" for resource in RESOURCES
            }

            cache_entries = cast(
                list[str],
                page.evaluate(
                    """async () => {
                      const names = await caches.keys();
                      const requests = await Promise.all(
                        names.map(async (name) => (await caches.open(name)).keys()),
                      );
                      return requests.flat().map((request) => request.url);
                    }"""
                ),
            )
            assert len(cache_entries) == len(RESOURCES)
            assert any(entry.endswith("/graph/optional.dat") for entry in cache_entries)

            undeclared = cast(
                FetchResult,
                page.evaluate(
                    """async () => {
                      const response = await fetch(
                        "./~dependencies/graph/undeclared.js",
                      );
                      return {
                        status: response.status,
                        text: await response.text(),
                      };
                    }"""
                ),
            )
            assert undeclared == {
                "status": http.HTTPStatus.NOT_FOUND,
                "text": "Undeclared dependency",
            }

            first_upstream_requests = list(upstream_requests)
            _stop_server(upstream)
            upstream_running = False

            page.close()
            warm_page = context.new_page()
            warm_errors: list[str] = []
            warm_page.on("pageerror", lambda error: warm_errors.append(str(error)))
            warm_page.goto(
                f"{site.base_url}{base_path}",
                wait_until="domcontentloaded",
            )
            warm_page.get_by_text("resolver loaded: 5/6/42", exact=True).wait_for()

            assert warm_errors == []
            assert upstream_requests == first_upstream_requests
            assert site_requests.count(base_path) == 2

            browser.close()
    finally:
        if upstream_running:
            _stop_server(upstream)
        _stop_server(site)


def test_service_worker_enforces_exact_verified_security_boundary(
    chromium: None,
) -> None:
    del chromium
    good_content = b"verified content\n"
    security_resources = (
        DependencyResource("security/good.js", good_content, "text/javascript"),
        DependencyResource(
            "security/wrong.js",
            b"expected content\n",
            "text/javascript",
        ),
        DependencyResource(
            "security/redirect.js",
            b"redirect target\n",
            "text/javascript",
        ),
        DependencyResource(
            "security/partial.js",
            b"partial content\n",
            "text/javascript",
        ),
        DependencyResource(
            "security/cors.js",
            b"cors content\n",
            "text/javascript",
        ),
        DependencyResource(
            "security/missing.js",
            b"expected missing content\n",
            "text/javascript",
        ),
    )
    observations: list[UpstreamObservation] = []
    upstream = _start_server(_adversarial_upstream_handler(observations))
    cache_name = "vividly-security-spike"
    service_worker = _service_worker_script(
        security_resources,
        upstream.base_url,
        cache_name,
        eager_names=("security/good.js",),
    )
    site_requests: list[str] = []
    site = _start_server(
        _site_handler(
            base_path="/vividly/",
            service_worker=service_worker,
            requests=site_requests,
            index=_index_html(entrypoint=None, set_test_cookie=True),
        )
    )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(service_workers="allow")
            page.goto(f"{site.base_url}/vividly/", wait_until="domcontentloaded")
            page.get_by_text("resolver ready", exact=True).wait_for()

            assert observations == [
                {
                    "path": "/upstream/security/good.js",
                    "cookie": None,
                    "referer": None,
                }
            ]

            good = _fetch_details(
                page,
                "./~dependencies/security/good.js",
            )
            assert good == {
                "status": http.HTTPStatus.OK,
                "text": good_content.decode(),
                "content_type": "text/javascript",
                "service_worker_allowed": None,
                "upstream_header": None,
            }

            _put_cache_entry(
                page,
                cache_name,
                "./~dependencies/security/good.js",
                "poisoned",
            )
            repaired = _fetch_details(
                page,
                "./~dependencies/security/good.js",
            )
            assert repaired["status"] == http.HTTPStatus.OK
            assert repaired["text"] == good_content.decode()
            assert [
                observation["path"] for observation in observations
            ].count("/upstream/security/good.js") == 2

            failures = {
                "wrong.js": "Integrity mismatch",
                "redirect.js": "Dependency resolution failed:",
                "partial.js": "Dependency resolution failed:",
                "cors.js": "Dependency resolution failed:",
                "missing.js": "HTTP 404",
            }
            _put_cache_entry(
                page,
                cache_name,
                "./~dependencies/security/missing.js",
                "stale content",
            )
            for resource_name, expected_message in failures.items():
                response = _fetch_details(
                    page,
                    f"./~dependencies/security/{resource_name}",
                )
                assert response["status"] == http.HTTPStatus.BAD_GATEWAY
                assert expected_message in response["text"]
                assert not _cache_has(
                    page,
                    cache_name,
                    f"./~dependencies/security/{resource_name}",
                )

            assert not any(
                observation["path"] == "/upstream/security/redirect-target.js"
                for observation in observations
            )

            requests_before_rejections = len(observations)
            rejected_urls = (
                "./~dependencies/security/undeclared.js",
                "./~dependencies/security/good.js?url=https://example.invalid/",
                "./~dependencies/security/%2Fgood.js",
                "./~dependencies/security/%2e%2e/good.js",
            )
            for relative_url in rejected_urls:
                response = _fetch_details(page, relative_url)
                assert response["status"] == http.HTTPStatus.NOT_FOUND
            assert len(observations) == requests_before_rejections

            method_rejection = _fetch_details(
                page,
                "./~dependencies/security/good.js",
                method="POST",
            )
            assert method_rejection["status"] == http.HTTPStatus.METHOD_NOT_ALLOWED
            assert len(observations) == requests_before_rejections

            assert all(
                observation["cookie"] is None
                and observation["referer"] is None
                for observation in observations
            )
            browser.close()
    finally:
        _stop_server(upstream)
        _stop_server(site)


def test_service_worker_coordinates_upgrade_recovery_and_rollback(
    chromium: None,
) -> None:
    del chromium
    version_one = DependencyResource(
        "lifecycle/version-one.js",
        b'export const message = "version one";\n',
        "text/javascript",
    )
    version_two = DependencyResource(
        "lifecycle/version-two.js",
        b'export const message = "version two";\n',
        "text/javascript",
    )
    upstream_requests: list[str] = []
    upstream = _start_server(
        _upstream_handler((version_one, version_two), upstream_requests)
    )
    cache_prefix = "vividly-lifecycle-"

    def published(revision: str, resource: DependencyResource) -> MutableDeployment:
        return MutableDeployment(
            index=_lifecycle_index_html(
                revision=revision,
                resource_name=resource.name,
            ),
            service_worker=_versioned_service_worker_script(
                resource,
                upstream.base_url,
                revision=revision,
                cache_prefix=cache_prefix,
            ),
        )

    deployment = published("revision-one", version_one)
    site_requests: list[str] = []
    site = _start_server(_mutable_site_handler(deployment, site_requests))

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(service_workers="allow")

            old_page = context.new_page()
            old_page.goto(
                f"{site.base_url}/vividly/",
                wait_until="domcontentloaded",
            )
            old_page.get_by_text("version one", exact=True).wait_for()
            assert upstream_requests == [
                "/upstream/lifecycle/version-one.js"
            ]

            deployment.index = published("revision-two", version_two).index
            deployment.service_worker = published(
                "revision-two",
                version_two,
            ).service_worker

            update_page = context.new_page()
            update_page.goto(
                f"{site.base_url}/vividly/",
                wait_until="domcontentloaded",
            )
            update_page.get_by_text("update waiting", exact=True).wait_for()
            assert old_page.get_by_text("version one", exact=True).is_visible()
            old_response = _fetch_details(
                old_page,
                "./~dependencies/revision-one/lifecycle/version-one.js",
            )
            assert old_response["status"] == http.HTTPStatus.OK
            assert upstream_requests == [
                "/upstream/lifecycle/version-one.js",
                "/upstream/lifecycle/version-two.js",
            ]

            old_page.close()
            update_page.evaluate(
                """async () => {
                  await globalThis.activateVividlyUpdate();
                }"""
            )
            update_page.get_by_text("version two", exact=True).wait_for()

            cache_names = cast(
                list[str],
                update_page.evaluate("async () => await caches.keys()"),
            )
            assert f"{cache_prefix}revision-one" not in cache_names
            assert f"{cache_prefix}revision-two" in cache_names

            stale_revision = _fetch_details(
                update_page,
                "./~dependencies/revision-one/lifecycle/version-one.js",
            )
            assert stale_revision["status"] == http.HTTPStatus.CONFLICT
            assert stale_revision["text"] == "Mapping revision mismatch"

            deleted = cast(
                bool,
                update_page.evaluate(
                    """async (cacheName) => await caches.delete(cacheName)""",
                    f"{cache_prefix}revision-two",
                ),
            )
            assert deleted
            recovered = _fetch_details(
                update_page,
                "./~dependencies/revision-two/lifecycle/version-two.js",
            )
            assert recovered["status"] == http.HTTPStatus.OK
            assert recovered["text"] == version_two.content.decode()
            assert upstream_requests.count(
                "/upstream/lifecycle/version-two.js"
            ) == 2

            deployment.index = published("revision-one", version_one).index
            deployment.service_worker = published(
                "revision-one",
                version_one,
            ).service_worker

            rollback_page = context.new_page()
            rollback_page.goto(
                f"{site.base_url}/vividly/",
                wait_until="domcontentloaded",
            )
            rollback_page.get_by_text("update waiting", exact=True).wait_for()
            assert update_page.get_by_text("version two", exact=True).is_visible()

            update_page.close()
            rollback_page.evaluate(
                """async () => {
                  await globalThis.activateVividlyUpdate();
                }"""
            )
            rollback_page.get_by_text("version one", exact=True).wait_for()

            rollback_caches = cast(
                list[str],
                rollback_page.evaluate("async () => await caches.keys()"),
            )
            assert f"{cache_prefix}revision-one" in rollback_caches
            assert f"{cache_prefix}revision-two" not in rollback_caches
            assert upstream_requests.count(
                "/upstream/lifecycle/version-one.js"
            ) == 2

            browser.close()
    finally:
        _stop_server(upstream)
        _stop_server(site)


def test_service_workers_isolate_colliding_projects_and_scope_escape(
    chromium: None,
) -> None:
    del chromium
    resource_name = "shared/entry.js"
    alpha_resource = DependencyResource(
        resource_name,
        b'export const message = "alpha project";\n',
        "text/javascript",
    )
    beta_resource = DependencyResource(
        resource_name,
        b'export const message = "beta project";\n',
        "text/javascript",
    )
    alpha_requests: list[str] = []
    beta_requests: list[str] = []
    alpha_upstream = _start_server(
        _upstream_handler((alpha_resource,), alpha_requests)
    )
    beta_upstream = _start_server(
        _upstream_handler((beta_resource,), beta_requests)
    )
    revision = "shared-revision"
    deployments = {
        "alpha": MutableDeployment(
            index=_lifecycle_index_html(
                revision=revision,
                resource_name=resource_name,
            ),
            service_worker=_versioned_service_worker_script(
                alpha_resource,
                alpha_upstream.base_url,
                revision=revision,
                cache_prefix="vividly-isolation-alpha-",
            ),
        ),
        "beta": MutableDeployment(
            index=_lifecycle_index_html(
                revision=revision,
                resource_name=resource_name,
            ),
            service_worker=_versioned_service_worker_script(
                beta_resource,
                beta_upstream.base_url,
                revision=revision,
                cache_prefix="vividly-isolation-beta-",
            ),
        ),
    }
    site_requests: list[str] = []
    site = _start_server(
        _scoped_projects_site_handler(deployments, site_requests)
    )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(service_workers="allow")
            alpha_page = context.new_page()
            beta_page = context.new_page()

            alpha_page.goto(
                f"{site.base_url}/alpha/",
                wait_until="domcontentloaded",
            )
            alpha_page.get_by_text("alpha project", exact=True).wait_for()
            beta_page.goto(
                f"{site.base_url}/beta/",
                wait_until="domcontentloaded",
            )
            beta_page.get_by_text("beta project", exact=True).wait_for()

            assert alpha_requests == [f"/upstream/{resource_name}"]
            assert beta_requests == [f"/upstream/{resource_name}"]

            alpha_dependency = _fetch_details(
                alpha_page,
                f"./~dependencies/{revision}/{resource_name}",
            )
            beta_dependency = _fetch_details(
                beta_page,
                f"./~dependencies/{revision}/{resource_name}",
            )
            assert alpha_dependency["text"] == alpha_resource.content.decode()
            assert beta_dependency["text"] == beta_resource.content.decode()

            escaped_project = _fetch_details(
                alpha_page,
                f"../beta/~dependencies/{revision}/{resource_name}",
            )
            escaped_scope = _fetch_details(
                alpha_page,
                f"../~dependencies/{revision}/{resource_name}",
            )
            assert escaped_project["status"] == http.HTTPStatus.NOT_FOUND
            assert escaped_scope["status"] == http.HTTPStatus.NOT_FOUND
            assert alpha_requests == [f"/upstream/{resource_name}"]
            assert beta_requests == [f"/upstream/{resource_name}"]

            registrations = cast(
                list[str],
                alpha_page.evaluate(
                    """async () => (await navigator.serviceWorker.getRegistrations())
                      .map((registration) => registration.scope)
                      .sort()"""
                ),
            )
            assert registrations == [
                f"{site.base_url}/alpha/",
                f"{site.base_url}/beta/",
            ]

            cache_names = cast(
                list[str],
                alpha_page.evaluate(
                    "async () => (await caches.keys()).sort()"
                ),
            )
            assert cache_names == [
                f"vividly-isolation-alpha-{revision}",
                f"vividly-isolation-beta-{revision}",
            ]

            browser.close()
    finally:
        _stop_server(alpha_upstream)
        _stop_server(beta_upstream)
        _stop_server(site)
