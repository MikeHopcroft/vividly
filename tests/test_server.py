"""Tests for the development server specified by docs/specs/cli.md section 6."""

import argparse
import contextlib
import http.client
import http.server
import io
import threading
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from vividly.cli import provision_command
from vividly.composition import compose_project
from vividly.server import (
    CompositionSession,
    ReloadBroker,
    composition_handler,
    serve_composition,
)


def test_reload_broker_notifies_connected_event_stream(tmp_path: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))

    broker = ReloadBroker()
    with compose_project(tmp_path) as composition:
        handler = composition_handler(
            composition,
            log_requests=False,
            reload_broker=broker,
        )
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_port,
            timeout=2,
        )
        try:
            connection.request("GET", "/vividly/~dev/events")
            response = connection.getresponse()
            assert response.status == 200
            assert response.getheader("Content-Type") == "text/event-stream"
            assert response.read(len(b": connected\n\n")) == b": connected\n\n"

            broker.notify_reload()

            event = b"event: reload\ndata: reload\n\n"
            assert response.read(len(event)) == event
        finally:
            broker.close()
            connection.close()
            server.shutdown()
            thread.join()
            server.server_close()


def test_operation_server_omits_development_reload_support(tmp_path: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))

    with compose_project(tmp_path) as composition:
        expected_index = composition.files[
            PurePosixPath("/index.html")
        ].source_path.read_bytes()
        with serve_composition(composition) as base_url:
            parsed = urlsplit(base_url)
            assert parsed.hostname is not None
            assert parsed.port is not None
            connection = http.client.HTTPConnection(
                parsed.hostname,
                parsed.port,
                timeout=2,
            )
            try:
                connection.request("GET", "/")
                response = connection.getresponse()
                assert response.status == 200
                assert response.read() == expected_index

                connection.request("GET", "/vividly/~dev/events")
                response = connection.getresponse()
                assert response.status == 404
                assert response.read() == b""
            finally:
                connection.close()


def test_composition_session_refreshes_the_deployed_path_map(tmp_path: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))

    added_path = tmp_path / "site" / "added.js"
    with CompositionSession(tmp_path) as compositions:
        assert compositions.watch_roots() == ((tmp_path / "site").resolve(),)

        added_path.write_text("export const added = true;\n", encoding="utf-8")
        compositions.refresh()

        with compositions.read() as composition:
            assert composition.files[
                PurePosixPath("/added.js")
            ].source_path == added_path
