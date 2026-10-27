"""Tests for static export specified by docs/specs/cli.md section 10."""

import argparse
import contextlib
import io
import sys
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest

from vividly.cli import main, provision_command
from vividly.composition import compose_project
from vividly.export import ExportError, export_project
from vividly.server import RELOAD_CLIENT


def _provision(project_root: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=project_root, assume_yes=True))


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_export_materializes_exact_composition_without_development_state(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    author_file = project_root / "site" / "author.txt"
    author_file.write_text("author\n", encoding="utf-8")

    with compose_project(project_root) as composition:
        expected = {
            url_path.relative_to(PurePosixPath("/")).as_posix(): (composed.source_path.read_bytes())
            for url_path, composed in composition.files.items()
        }

    with patch("vividly.export.compose_project", wraps=compose_project) as compose:
        assert export_project(project_root, destination) == destination
    compose.assert_called_once_with(project_root, verify_package_contents=True)
    assert _snapshot(destination) == expected
    assert RELOAD_CLIENT not in (destination / "index.html").read_bytes()
    assert not (destination / "vividly.yaml").exists()
    assert not (destination / ".github").exists()
    assert not (destination / "vividly/~dev").exists()


def test_export_keeps_dependencies_cdn_backed_and_excludes_cache_artifacts(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    catalog_path = project_root / "site/catalog.yaml"
    catalog_path.write_text(
        catalog_path.read_text(encoding="utf-8").replace(
            "presentations:\n",
            """dependencies:
  graphics:
    baseUrl: https://cdn.example.invalid/graphics@1.2.3/
    entry: entry.js
presentations:
""",
        ),
        encoding="utf-8",
    )

    export_project(project_root, destination)

    index = (destination / "index.html").read_text(encoding="utf-8")
    catalog = (destination / "catalog.yaml").read_text(encoding="utf-8")
    assert "dependency-base=" not in index
    assert "https://cdn.example.invalid/graphics@1.2.3/" in catalog
    assert (destination / "vividly/dependencies.json").is_file()
    assert not (destination / "~dependencies").exists()
    exported_paths = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert not any(path.startswith("vividly/vendor/") for path in exported_paths)
    assert not any(
        Path(path).name.lower().startswith(("license", "copying"))
        for path in exported_paths
    )


def test_export_replaces_an_existing_empty_destination(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    destination.mkdir()

    export_project(project_root, destination)

    assert (destination / "index.html").is_file()
    assert (destination / "catalog.yaml").is_file()


def test_repeated_exports_have_identical_paths_and_bytes(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    first = tmp_path / "first"
    second = tmp_path / "second"
    _provision(project_root)

    export_project(project_root, first)
    export_project(project_root, second)

    assert _snapshot(first) == _snapshot(second)


def test_export_command_reports_materialized_destination(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    output = io.StringIO()

    with (
        patch.object(
            sys,
            "argv",
            [
                "vividly",
                "export",
                str(project_root),
                "--output",
                str(destination),
            ],
        ),
        contextlib.redirect_stdout(output),
    ):
        main()

    assert output.getvalue().strip() == f"Exported static site to {destination}"
    assert (destination / "index.html").is_file()


@pytest.mark.parametrize(
    "destination_name",
    ["project", "project/site", "project/site/output"],
)
def test_export_rejects_source_and_destination_overlap(
    tmp_path: Path,
    destination_name: str,
) -> None:
    project_root = tmp_path / "project"
    _provision(project_root)

    with pytest.raises(ExportError, match="overlaps"):
        export_project(project_root, tmp_path / destination_name)


def test_export_rejects_a_destination_containing_the_project(tmp_path: Path) -> None:
    project_root = tmp_path / "container" / "project"
    project_root.parent.mkdir()
    _provision(project_root)

    with pytest.raises(ExportError, match="overlaps"):
        export_project(project_root, tmp_path / "container")


def test_export_rejects_nonempty_destination_without_changes(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    destination.mkdir()
    existing = destination / "keep.txt"
    existing.write_text("keep\n", encoding="utf-8")

    with pytest.raises(ExportError, match="not empty"):
        export_project(project_root, destination)

    assert existing.read_text(encoding="utf-8") == "keep\n"


def test_export_rejects_symbolic_link_destination(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    target = tmp_path / "target"
    destination = tmp_path / "export"
    _provision(project_root)
    target.mkdir()
    destination.symlink_to(target, target_is_directory=True)

    with pytest.raises(ExportError, match="symbolic link"):
        export_project(project_root, destination)


def test_failed_export_leaves_no_destination_or_staging_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)

    with (
        patch("pathlib.Path.write_bytes", side_effect=OSError("disk full")),
        pytest.raises(ExportError, match="could not materialize export"),
    ):
        export_project(project_root, destination)

    assert not destination.exists()
    assert not tuple(tmp_path.glob(".export-*"))


def test_source_read_failure_preserves_source_and_leaves_no_output(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    author_file = project_root / "site" / "author.txt"
    author_file.write_text("author\n", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def fail_author_read(path: Path) -> bytes:
        if path == author_file:
            raise OSError("source unavailable")
        return original_read_bytes(path)

    with (
        patch("pathlib.Path.read_bytes", fail_author_read),
        pytest.raises(ExportError, match="source unavailable"),
    ):
        export_project(project_root, destination)

    assert author_file.read_text(encoding="utf-8") == "author\n"
    assert not destination.exists()
    assert not tuple(tmp_path.glob(".export-*"))


def test_destination_appearing_during_assembly_is_not_replaced(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    original_write_bytes = Path.write_bytes
    changed = False

    def create_destination(path: Path, content: bytes) -> int:
        nonlocal changed
        written = original_write_bytes(path, content)
        if not changed:
            destination.mkdir()
            changed = True
        return written

    with (
        patch("pathlib.Path.write_bytes", create_destination),
        pytest.raises(ExportError, match="changed during assembly"),
    ):
        export_project(project_root, destination)

    assert destination.is_dir()
    assert not tuple(destination.iterdir())
    assert not tuple(tmp_path.glob(".export-*"))


def test_empty_destination_becoming_nonempty_is_preserved(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    destination.mkdir()
    original_write_bytes = Path.write_bytes
    changed = False

    def add_unknown_file(path: Path, content: bytes) -> int:
        nonlocal changed
        written = original_write_bytes(path, content)
        if not changed:
            (destination / "keep.txt").write_text("keep\n", encoding="utf-8")
            changed = True
        return written

    with (
        patch("pathlib.Path.write_bytes", add_unknown_file),
        pytest.raises(ExportError, match="changed during assembly"),
    ):
        export_project(project_root, destination)

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert not tuple(tmp_path.glob(".export-*"))


def test_empty_destination_becoming_symlink_is_preserved(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    symlink_target = tmp_path / "target"
    _provision(project_root)
    destination.mkdir()
    symlink_target.mkdir()
    original_write_bytes = Path.write_bytes
    changed = False

    def replace_with_symlink(path: Path, content: bytes) -> int:
        nonlocal changed
        written = original_write_bytes(path, content)
        if not changed:
            destination.rmdir()
            destination.symlink_to(symlink_target, target_is_directory=True)
            changed = True
        return written

    with (
        patch("pathlib.Path.write_bytes", replace_with_symlink),
        pytest.raises(ExportError, match="changed during assembly"),
    ):
        export_project(project_root, destination)

    assert destination.is_symlink()
    assert not tuple(tmp_path.glob(".export-*"))


def test_failed_install_restores_existing_empty_destination(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = tmp_path / "export"
    _provision(project_root)
    destination.mkdir()

    with (
        patch("pathlib.Path.rename", side_effect=OSError("rename failed")),
        pytest.raises(ExportError, match="rename failed"),
    ):
        export_project(project_root, destination)

    assert destination.is_dir()
    assert not tuple(destination.iterdir())
    assert not tuple(tmp_path.glob(".export-*"))
