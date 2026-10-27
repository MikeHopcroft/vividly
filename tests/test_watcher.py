"""Tests for source watching specified by docs/specs/cli.md section 6."""

import argparse
import contextlib
import io
import threading
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest
from watchfiles import Change

from vividly.cli import provision_command
from vividly.server import CompositionSession, ReloadBroker
from vividly.watcher import WatcherError, watch_for_reloads


def _provision(project_root: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=project_root, assume_yes=True))


def test_valid_change_refreshes_composition_and_notifies_clients(tmp_path: Path) -> None:
    _provision(tmp_path)
    added_path = tmp_path / "site" / "added.js"
    added_path.write_text("export const added = true;\n", encoding="utf-8")
    changes = [{(Change.added, str(added_path))}]
    errors: list[str] = []
    broker = ReloadBroker()

    with (
        CompositionSession(tmp_path) as compositions,
        patch("vividly.watcher.watch", return_value=iter(changes)),
    ):
        watch_for_reloads(
            compositions,
            broker,
            threading.Event(),
            errors.append,
        )
        with compositions.read() as composition:
            assert PurePosixPath("/added.js") in composition.files

    assert broker.current_version() == 1
    assert errors == []


def test_invalid_change_waits_for_a_valid_refresh_before_notifying(tmp_path: Path) -> None:
    _provision(tmp_path)
    collision = tmp_path / "site" / "index.html"
    added_path = tmp_path / "site" / "added.js"
    errors: list[str] = []
    broker = ReloadBroker()

    def changes():
        collision.write_text("<!doctype html>\n", encoding="utf-8")
        yield {(Change.added, str(collision))}
        collision.unlink()
        added_path.write_text("export const added = true;\n", encoding="utf-8")
        yield {(Change.added, str(added_path))}

    with (
        CompositionSession(tmp_path) as compositions,
        patch("vividly.watcher.watch", return_value=changes()),
    ):
        watch_for_reloads(
            compositions,
            broker,
            threading.Event(),
            errors.append,
        )
        with compositions.read() as composition:
            assert composition.files[PurePosixPath("/index.html")].owner == "runtime"
            assert PurePosixPath("/added.js") in composition.files

    assert broker.current_version() == 1
    assert len(errors) == 1
    assert "author path collides with runtime ownership" in errors[0]


def test_watcher_operating_failure_is_explicit(tmp_path: Path) -> None:
    _provision(tmp_path)
    broker = ReloadBroker()

    with (
        CompositionSession(tmp_path) as compositions,
        patch("vividly.watcher.watch", side_effect=OSError("watch unavailable")),
        pytest.raises(WatcherError, match="watch unavailable"),
    ):
        watch_for_reloads(
            compositions,
            broker,
            threading.Event(),
            lambda _: None,
        )
