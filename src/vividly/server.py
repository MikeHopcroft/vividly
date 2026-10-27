"""HTTP serving for a validated Vividly composition."""

import http.server
import mimetypes
import re
import threading
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote_to_bytes, urlsplit

from .composition import Composition, compose_project
from .dependencies import (
    DependencyAcquisitionError,
    DependencyCache,
    DependencyCacheMiss,
    dependency_relative_path,
)

RELOAD_EVENTS_PATH = PurePosixPath("/vividly/~dev/events")
DEPENDENCY_PREFIX = "/~dependencies/"
_DEPENDENCY_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
DEPENDENCY_BASE_ATTRIBUTE = b'dependency-base="./~dependencies/" '
RELOAD_CLIENT = b"""<script>
(() => {
  const events = new EventSource("/vividly/~dev/events");
  events.addEventListener("reload", () => window.location.reload());
})();
</script>
"""
_RELOAD_HEARTBEAT_SECONDS = 15.0


@dataclass(frozen=True)
class _CompositionLease:
    stack: ExitStack
    composition: Composition


class CompositionSession:
    """Own the current validated composition and its resource lifetime."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._lock = threading.RLock()
        self._lease = self._open_composition()
        self._closed = False

    def __enter__(self) -> "CompositionSession":
        return self

    def __exit__(self, *args: object) -> None:
        del args
        self.close()

    @contextmanager
    def read(self) -> Generator[Composition, None, None]:
        """Hold the selected runtime resources while one request reads them."""
        with self._lock:
            if self._closed:
                raise RuntimeError("composition session is closed")
            yield self._lease.composition

    def watch_roots(self) -> tuple[Path, ...]:
        """Return the author root and any selected editable runtime root."""
        with self.read() as composition:
            roots = [composition.author_root]
            if composition.runtime.source != "package":
                roots.append(composition.runtime.runtime_root)
            return tuple(roots)

    def refresh(self) -> None:
        """Replace the current composition after complete validation."""
        candidate = self._open_composition()
        with self._lock:
            if self._closed:
                candidate.stack.close()
                raise RuntimeError("composition session is closed")
            previous = self._lease
            self._lease = candidate
            previous.stack.close()

    def close(self) -> None:
        """Release the current selected runtime resources."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._lease.stack.close()

    def _open_composition(self) -> _CompositionLease:
        stack = ExitStack()
        composition = stack.enter_context(compose_project(self._project_root))
        return _CompositionLease(stack=stack, composition=composition)


class ReloadBroker:
    """Coordinate reload notifications across development-server clients."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._version = 0
        self._closed = False

    def current_version(self) -> int:
        """Return the latest reload sequence number."""
        with self._condition:
            return self._version

    def notify_reload(self) -> None:
        """Notify every connected client that the composition changed."""
        with self._condition:
            if self._closed:
                return
            self._version += 1
            self._condition.notify_all()

    def wait(self, version: int) -> tuple[int, bool]:
        """Wait for a reload, shutdown, or the next heartbeat interval."""
        with self._condition:
            self._condition.wait_for(
                lambda: self._version != version or self._closed,
                timeout=_RELOAD_HEARTBEAT_SECONDS,
            )
            return self._version, self._closed

    def close(self) -> None:
        """Release connected clients during server shutdown."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()


def _request_path(target: str) -> PurePosixPath | None:
    raw_path = urlsplit(target).path
    try:
        decoded = unquote_to_bytes(raw_path).decode("utf-8")
    except UnicodeDecodeError:
        return None
    if decoded == "/":
        return PurePosixPath("/index.html")
    path = PurePosixPath(decoded)
    if (
        not path.is_absolute()
        or str(path) != decoded
        or "\\" in decoded
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    return path


def _inject_reload_client(content: bytes) -> bytes:
    marker = b"</body>"
    position = content.rfind(marker)
    if position == -1:
        return content + b"\n" + RELOAD_CLIENT
    return content[:position] + RELOAD_CLIENT + content[position:]


def _inject_dependency_base(content: bytes) -> bytes:
    marker = b"<vividly-presentation "
    if DEPENDENCY_BASE_ATTRIBUTE.rstrip() in content:
        raise ValueError("runtime index already declares dependency-base")
    if marker not in content:
        raise ValueError("runtime index is missing the vividly-presentation root")
    return content.replace(
        marker,
        b"<vividly-presentation " + DEPENDENCY_BASE_ATTRIBUTE,
        1,
    )


def _dependency_request_path(target: str) -> tuple[str, PurePosixPath] | None:
    parsed = urlsplit(target)
    if (
        parsed.query
        or "%" in parsed.path
        or "\\" in parsed.path
        or not parsed.path.startswith(DEPENDENCY_PREFIX)
    ):
        return None
    relative = parsed.path.removeprefix(DEPENDENCY_PREFIX)
    parts = relative.split("/")
    if len(parts) < 2 or _DEPENDENCY_KEY.fullmatch(parts[0]) is None:
        return None
    path = dependency_relative_path("/".join(parts[1:]))
    if path is None:
        return None
    return parts[0], path


@contextmanager
def _read_composition(
    source: Composition | CompositionSession,
) -> Generator[Composition, None, None]:
    if isinstance(source, CompositionSession):
        with source.read() as composition:
            yield composition
        return
    yield source


def composition_handler(
    composition: Composition | CompositionSession,
    *,
    log_requests: bool = True,
    reload_broker: ReloadBroker | None = None,
    dependency_cache: DependencyCache | None = None,
) -> type[http.server.BaseHTTPRequestHandler]:
    """Create an HTTP handler bound to one immutable composition."""

    class CompositionRequestHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            if log_requests:
                super().log_message(format, *args)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self) -> None:
            self._serve(include_body=True)

        def do_HEAD(self) -> None:
            self._serve(include_body=False)

        def _serve(self, *, include_body: bool) -> None:
            parsed_target = urlsplit(self.path)
            if parsed_target.path.startswith(DEPENDENCY_PREFIX):
                dependency_request = _dependency_request_path(self.path)
                if dependency_request is None:
                    self.send_error(http.HTTPStatus.BAD_REQUEST, "Invalid dependency path")
                    return
                key, relative_path = dependency_request
                if dependency_cache is None:
                    self._send_not_found()
                    return
                with _read_composition(composition) as current:
                    selection = current.dependencies.get(key)
                if selection is None:
                    self._send_not_found()
                    return
                try:
                    resource = dependency_cache.get(selection, relative_path)
                except DependencyCacheMiss as error:
                    self.send_error(http.HTTPStatus.GATEWAY_TIMEOUT, str(error))
                    return
                except DependencyAcquisitionError as error:
                    self.send_error(http.HTTPStatus.BAD_GATEWAY, str(error))
                    return
                self._send_content(
                    resource.content,
                    resource.content_type,
                    include_body=include_body,
                )
                return

            request_path = _request_path(self.path)
            if request_path == RELOAD_EVENTS_PATH and reload_broker is not None:
                self._serve_reload_events(include_body=include_body)
                return
            with _read_composition(composition) as current:
                composed = (
                    current.files.get(request_path)
                    if request_path is not None
                    else None
                )
                if composed is None:
                    self._send_not_found()
                    return
                try:
                    content = composed.source_path.read_bytes()
                except OSError:
                    self._send_not_found()
                    return

            if request_path == PurePosixPath("/index.html"):
                if dependency_cache is not None:
                    try:
                        content = _inject_dependency_base(content)
                    except ValueError as error:
                        self.send_error(http.HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                        return
                if reload_broker is not None:
                    content = _inject_reload_client(content)
            content_type, _ = mimetypes.guess_type(composed.source_path.name)
            self._send_content(
                content,
                content_type or "application/octet-stream",
                include_body=include_body,
            )

        def _send_content(
            self,
            content: bytes,
            content_type: str,
            *,
            include_body: bool,
        ) -> None:
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if include_body:
                self.wfile.write(content)

        def _serve_reload_events(self, *, include_body: bool) -> None:
            assert reload_broker is not None
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            if not include_body:
                self.send_header("Content-Length", "0")
            self.end_headers()
            if not include_body:
                return

            version = reload_broker.current_version()
            if not self._write_event(b": connected\n\n"):
                return
            while True:
                next_version, closed = reload_broker.wait(version)
                if closed:
                    return
                if next_version == version:
                    event = b": keepalive\n\n"
                else:
                    version = next_version
                    event = b"event: reload\ndata: reload\n\n"
                if not self._write_event(event):
                    return

        def _write_event(self, content: bytes) -> bool:
            try:
                self.wfile.write(content)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return False
            return True

        def _send_not_found(self) -> None:
            self.send_response(http.HTTPStatus.NOT_FOUND)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return CompositionRequestHandler


@contextmanager
def serve_composition(
    composition: Composition,
    *,
    log_requests: bool = False,
    dependency_cache: DependencyCache | None = None,
) -> Generator[str, None, None]:
    """Serve a composition on an available loopback port for one operation."""
    handler = composition_handler(
        composition,
        log_requests=log_requests,
        dependency_cache=dependency_cache,
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
