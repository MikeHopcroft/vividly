"""Tests for reference materialization specified in docs/specs/cli.md."""

import argparse
import contextlib
import hashlib
import io
import json
from importlib.metadata import version as distribution_version
from importlib.resources import as_file, files
from pathlib import Path
from unittest.mock import patch

import pytest

from vividly.cli import create_parser, provision_command, reference_command
from vividly.constants import REFERENCE_RESOURCE_NAME


def _provision(project_root: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=project_root, assume_yes=True))


def _write_editable_runtime(project_root: Path) -> tuple[Path, Path]:
    runtime = project_root / "runtime"
    reference = project_root / "reference"
    (runtime / "vividly").mkdir(parents=True)
    reference.mkdir()
    (runtime / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (runtime / "vividly" / "version.txt").write_text("1.2.3\n", encoding="utf-8")
    (reference / "guide.md").write_text("# Edited guide\n", encoding="utf-8")
    digest = "a" * 64
    manifest = {
        "composition_api": 1,
        "files": {
            "index.html": digest,
            "vividly/version.txt": digest,
        },
        "reference_files": {"old.md": digest},
        "schema": 1,
        "version": "1.2.3",
    }
    (runtime / "vividly-runtime.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return runtime, reference


def test_reference_defaults_to_current_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    arguments = create_parser().parse_args(["reference"])

    assert arguments.project_root == tmp_path


def test_materializes_verified_package_reference_and_metadata(tmp_path: Path) -> None:
    _provision(tmp_path)

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        reference_command(argparse.Namespace(project_root=tmp_path))

    destination = tmp_path / ".vividly" / "reference"
    package_reference = files("vividly.resources").joinpath(REFERENCE_RESOURCE_NAME)
    with as_file(package_reference) as expected_root:
        expected = {
            path.relative_to(expected_root).as_posix(): path.read_bytes()
            for path in expected_root.rglob("*")
            if path.is_file()
        }
    actual = {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file() and path.name != "runtime.json"
    }
    metadata = json.loads((destination / "runtime.json").read_text(encoding="utf-8"))

    assert actual == expected
    assert metadata["source"] == "package"
    assert metadata["distribution_version"]
    assert metadata["framework_version"]
    assert metadata["manifest_integrity"].startswith("sha256:")
    assert metadata["content_digest"].startswith("sha256:")
    assert f"Materialized {len(expected)} reference files" in output.getvalue()


def test_current_reference_is_not_rewritten(tmp_path: Path) -> None:
    _provision(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        reference_command(argparse.Namespace(project_root=tmp_path))

    output = io.StringIO()
    with (
        patch(
            "vividly.reference.tempfile.TemporaryDirectory",
            side_effect=AssertionError("fresh output should not be staged"),
        ),
        contextlib.redirect_stdout(output),
    ):
        reference_command(argparse.Namespace(project_root=tmp_path))

    assert "already current" in output.getvalue()


def test_reference_replaces_modified_generated_output(tmp_path: Path) -> None:
    _provision(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        reference_command(argparse.Namespace(project_root=tmp_path))
    generated = tmp_path / ".vividly" / "reference" / "cli.md"
    generated.write_text("user edit\n", encoding="utf-8")

    with contextlib.redirect_stdout(io.StringIO()):
        reference_command(argparse.Namespace(project_root=tmp_path))

    assert generated.read_text(encoding="utf-8") != "user edit\n"


def test_reference_copies_editable_sibling_tree_without_enforcing_hashes(
    tmp_path: Path,
) -> None:
    _write_editable_runtime(tmp_path)
    commit = "a" * 40
    (tmp_path / "vividly.yaml").write_text(
        "schema: 1\n"
        "runtime:\n"
        "  source: repository\n"
        "  path: runtime\n"
        "  version: 1.2.3\n"
        f"  commit: {commit}\n",
        encoding="utf-8",
    )

    with contextlib.redirect_stdout(io.StringIO()):
        reference_command(argparse.Namespace(project_root=tmp_path))

    destination = tmp_path / ".vividly" / "reference"
    assert (destination / "guide.md").read_text(encoding="utf-8") == "# Edited guide\n"
    metadata = json.loads((destination / "runtime.json").read_text(encoding="utf-8"))
    assert metadata["source"] == "repository"
    assert metadata["commit"] == commit


def test_reference_reports_exact_package_requirement(tmp_path: Path) -> None:
    _provision(tmp_path)
    config_path = tmp_path / "vividly.yaml"
    content = config_path.read_text(encoding="utf-8")
    configured_version = "99.0"
    config_path.write_text(
        content.replace(
            f'distribution_version: "{distribution_version("vividly")}"',
            f'distribution_version: "{configured_version}"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as failure:
        reference_command(argparse.Namespace(project_root=tmp_path))

    message = str(failure.value)
    assert f"required distribution: {configured_version}" in message
    assert "available framework:" in message
    assert f"python -m pip install 'vividly=={configured_version}'" in message
    assert "offline environment" in message
    assert not (tmp_path / ".vividly").exists()
def test_reference_rejects_legacy_project_without_parsing_baseline(tmp_path: Path) -> None:
    (tmp_path / "vividly-baseline.json").write_text("not json", encoding="utf-8")

    with pytest.raises(SystemExit, match="requires reprovisioning"):
        reference_command(argparse.Namespace(project_root=tmp_path))

    assert not (tmp_path / ".vividly").exists()


def test_reference_rejects_symbolic_links_in_editable_reference(
    tmp_path: Path,
) -> None:
    _write_editable_runtime(tmp_path)
    (tmp_path / "outside.md").write_text("outside\n", encoding="utf-8")
    (tmp_path / "reference" / "linked.md").symlink_to(tmp_path / "outside.md")
    (tmp_path / "vividly.yaml").write_text(
        "schema: 1\n"
        "runtime:\n"
        "  source: path\n"
        "  path: runtime\n"
        "  upstream_version: 1.2.3\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="symbolic link"):
        reference_command(argparse.Namespace(project_root=tmp_path))

    assert not (tmp_path / ".vividly").exists()


def test_reference_rejects_symbolic_links_in_generated_output(tmp_path: Path) -> None:
    _provision(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        reference_command(argparse.Namespace(project_root=tmp_path))
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    generated = tmp_path / ".vividly" / "reference" / "cli.md"
    generated.unlink()
    generated.symlink_to(outside)

    with pytest.raises(SystemExit, match="symbolic link"):
        reference_command(argparse.Namespace(project_root=tmp_path))

    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_reference_keeps_previous_output_when_staging_fails(tmp_path: Path) -> None:
    _write_editable_runtime(tmp_path)
    (tmp_path / "vividly.yaml").write_text(
        "schema: 1\n"
        "runtime:\n"
        "  source: path\n"
        "  path: runtime\n"
        "  upstream_version: 1.2.3\n",
        encoding="utf-8",
    )
    with contextlib.redirect_stdout(io.StringIO()):
        reference_command(argparse.Namespace(project_root=tmp_path))
    generated = tmp_path / ".vividly" / "reference" / "guide.md"
    previous = generated.read_bytes()
    (tmp_path / "reference" / "guide.md").write_text("# Changed\n", encoding="utf-8")

    with (
        patch("vividly.reference.shutil.copyfile", side_effect=OSError("copy failed")),
        pytest.raises(SystemExit, match="copy failed"),
    ):
        reference_command(argparse.Namespace(project_root=tmp_path))

    assert generated.read_bytes() == previous


def test_reference_digest_changes_with_paths_and_bytes(tmp_path: Path) -> None:
    _provision(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        reference_command(argparse.Namespace(project_root=tmp_path))
    metadata_path = tmp_path / ".vividly" / "reference" / "runtime.json"
    original_digest = json.loads(metadata_path.read_text(encoding="utf-8"))["content_digest"]

    generated = tmp_path / ".vividly" / "reference" / "cli.md"
    generated.write_text(hashlib.sha256(generated.read_bytes()).hexdigest(), encoding="utf-8")

    with contextlib.redirect_stdout(io.StringIO()):
        reference_command(argparse.Namespace(project_root=tmp_path))

    refreshed_digest = json.loads(metadata_path.read_text(encoding="utf-8"))["content_digest"]
    assert refreshed_digest == original_digest
