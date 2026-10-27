"""Tests for the CLI behavior specified in docs/specs/cli.md."""

import argparse
import contextlib
import errno
import http.client
import io
import json
import socket
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Self
from unittest.mock import patch

import pytest
from rich.console import Console as RichConsole

from vividly.cli import (
    cache_clear_command,
    cache_status_command,
    create_parser,
    dependencies_command,
    install_browser_command,
    main,
    port_number,
    provision_command,
    rehearse_command,
    run_command,
    tool_version,
)
from vividly.constants import BASELINE_NAME, DEFAULT_PORT
from vividly.dependencies import DependencyCache, DependencyResource, DependencySelection
from vividly.project import PackageRuntime, load_project_config
from vividly.rehearsal import RehearsalIssue, RehearsalResult
from vividly.runtime import packaged_runtime
from vividly.server import DEPENDENCY_BASE_ATTRIBUTE, RELOAD_CLIENT
from vividly.watcher import WatcherError


def _provision(project_root: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=project_root, assume_yes=True))


def test_parser_registers_available_commands() -> None:
    parser = create_parser()

    for command in (
        "provision",
        "run",
        "install-browser",
        "reference",
        "dependencies",
        "cache",
        "thumbnails",
        "rehearse",
        "export",
        "publish",
    ):
        command_arguments = [command]
        if command == "thumbnails":
            command_arguments.extend(("--slide", "opening/title-card"))
        if command == "export":
            command_arguments.extend(("--output", "dist"))
        if command == "cache":
            command_arguments.append("status")
        arguments = parser.parse_args(command_arguments)
        assert arguments.command == command

    with pytest.raises(SystemExit):
        parser.parse_args(["install"])


def test_provision_no_longer_accepts_conflict_resolution() -> None:
    with pytest.raises(SystemExit):
        create_parser().parse_args(["provision", "--accept-conflict", "site/index.html"])


def test_thumbnails_accepts_missing_and_repeated_slide_selection() -> None:
    parser = create_parser()

    all_arguments = parser.parse_args(["thumbnails"])
    selected_arguments = parser.parse_args(
        [
            "thumbnails",
            "--missing",
            "--slide",
            "opening/title-card",
            "--slide",
            "images/photo-tour",
        ]
    )

    assert all_arguments.slides is None
    assert all_arguments.missing_only is False
    assert selected_arguments.slides == ["opening/title-card", "images/photo-tour"]
    assert selected_arguments.missing_only is True


def test_dependencies_defaults_to_current_directory_and_accepts_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    arguments = create_parser().parse_args(["dependencies", "--json"])

    assert arguments.project_root == tmp_path
    assert arguments.json_output is True


def test_dependencies_reports_effective_registry_in_deterministic_json(
    tmp_path: Path,
) -> None:
    with packaged_runtime() as runtime:
        expected_version = runtime.manifest.version
    _provision(tmp_path)
    catalog = tmp_path / "site" / "catalog.yaml"
    catalog.write_text(
        """
version: 1
dependencies:
  graphics:
    baseUrl: https://cdn.example.invalid/graphics@1.2.3/
    entry: build/main.js
presentations: []
""",
        encoding="utf-8",
    )
    output = io.StringIO()

    with (
        patch(
            "vividly.cli.default_dependency_cache_root",
            side_effect=AssertionError("dependencies inspected the cache"),
        ),
        contextlib.redirect_stdout(output),
    ):
        dependencies_command(argparse.Namespace(project_root=tmp_path, json_output=True))

    report = json.loads(output.getvalue())
    assert report["schema"] == 1
    assert report["runtime"] == {"source": "package", "version": expected_version}
    records = report["dependencies"]
    assert [record["key"] for record in records] == [
        "graphics",
        "highlight-github-dark",
        "highlight-js",
        "js-yaml",
        "marked",
    ]
    graphics = records[0]
    assert graphics == {
        "baseUrl": "https://cdn.example.invalid/graphics@1.2.3/",
        "entry": "build/main.js",
        "key": "graphics",
        "license": None,
        "loader": {"type": "module"},
        "owner": "catalog",
        "ownerIdentity": None,
        "projectUrl": None,
        "sha256": None,
        "url": "https://cdn.example.invalid/graphics@1.2.3/build/main.js",
        "version": None,
    }
    marked = records[-1]
    assert marked["owner"] == "runtime"
    assert marked["ownerIdentity"] == f"Vividly {expected_version}"
    assert marked["version"] == "12.0.2"
    assert marked["license"] == "MIT"
    assert marked["loader"] == {"global": "marked", "type": "script"}
    assert marked["url"] == "https://cdn.jsdelivr.net/npm/marked@12.0.2/lib/marked.umd.js"


def test_dependencies_human_output_names_owners_versions_and_loaders(
    tmp_path: Path,
) -> None:
    with packaged_runtime() as runtime:
        expected_version = runtime.manifest.version
    _provision(tmp_path)
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        dependencies_command(argparse.Namespace(project_root=tmp_path, json_output=False))

    rendered = output.getvalue()
    assert all(heading in rendered for heading in ("KEY", "OWNER", "VERSION", "LOADER", "URL"))
    assert "marked" in rendered
    assert f"Vividly {expected_version}" in rendered
    assert "12.0.2" in rendered
    assert "script" in rendered
    assert "\x1b[" not in rendered


def test_cache_parser_supports_project_global_json_and_clear() -> None:
    parser = create_parser()

    project = parser.parse_args(["cache", "status", "project", "--json"])
    global_status = parser.parse_args(["cache", "status", "--all"])
    clear = parser.parse_args(["cache", "clear", "--yes"])

    assert project.project_root == Path("project")
    assert project.json_output is True
    assert project.all_cache is False
    assert global_status.project_root is None
    assert global_status.all_cache is True
    assert clear.assume_yes is True


def test_cache_status_reports_project_resources_in_unstyled_json(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _provision(project_root)
    catalog = project_root / "site/catalog.yaml"
    catalog.write_text(
        """
version: 1
dependencies:
  graphics:
    baseUrl: https://cdn.example.invalid/graphics@1/
    entry: main.js
presentations: []
""",
        encoding="utf-8",
    )
    cache_root = tmp_path / "cache"
    selection = DependencySelection(
        key="graphics",
        base_url="https://cdn.example.invalid/graphics@1/",
        entry=PurePosixPath("main.js"),
    )
    DependencyCache(
        cache_root,
        acquirer=lambda _: DependencyResource(
            content=b"export {};\n",
            content_type="text/javascript",
        ),
    ).get(selection, selection.entry)
    output = io.StringIO()

    with (
        patch("vividly.cli.default_dependency_cache_root", return_value=cache_root),
        contextlib.redirect_stdout(output),
    ):
        cache_status_command(
            argparse.Namespace(
                project_root=project_root,
                all_cache=False,
                json_output=True,
            )
        )

    rendered = output.getvalue()
    report = json.loads(rendered)
    assert report["schema"] == 1
    assert report["scope"] == "project"
    assert report["cacheRoot"] == str(cache_root.resolve())
    graphics = [
        resource for resource in report["resources"] if resource["key"] == "graphics"
    ]
    assert graphics == [
        {
            "cachedAt": graphics[0]["cachedAt"],
            "key": "graphics",
            "relativePath": "main.js",
            "size": 11,
            "sourceUrl": "https://cdn.example.invalid/graphics@1/main.js",
            "status": "valid",
        }
    ]
    assert graphics[0]["cachedAt"].endswith("Z")
    assert "\x1b[" not in rendered

    redirected = io.StringIO()
    with (
        patch("vividly.cli.default_dependency_cache_root", return_value=cache_root),
        contextlib.redirect_stdout(redirected),
    ):
        cache_status_command(
            argparse.Namespace(
                project_root=project_root,
                all_cache=False,
                json_output=False,
            )
        )
    assert "missing" in redirected.getvalue()
    assert "\x1b[" not in redirected.getvalue()

    colored = io.StringIO()
    with (
        patch("vividly.cli.default_dependency_cache_root", return_value=cache_root),
        patch(
            "vividly.cli.Console",
            return_value=RichConsole(
                file=colored,
                force_terminal=True,
                color_system="standard",
                width=240,
            ),
        ),
    ):
        cache_status_command(
            argparse.Namespace(
                project_root=project_root,
                all_cache=False,
                json_output=False,
            )
        )
    assert "missing" in colored.getvalue()
    assert "\x1b[" in colored.getvalue()


def test_cache_status_all_uses_rich_color_without_loading_project(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    selection = DependencySelection(
        key="old",
        base_url="https://cdn.example.invalid/old@1/",
        entry=PurePosixPath("main.js"),
    )
    DependencyCache(
        cache_root,
        acquirer=lambda _: DependencyResource(
            content=b"old",
            content_type="text/javascript",
        ),
    ).get(selection, selection.entry)
    output = io.StringIO()

    with (
        patch("vividly.cli.default_dependency_cache_root", return_value=cache_root),
        patch(
            "vividly.cli.compose_project",
            side_effect=AssertionError("--all loaded a project"),
        ),
        patch(
            "vividly.cli.Console",
            return_value=RichConsole(
                file=output,
                force_terminal=True,
                color_system="standard",
                width=200,
            ),
        ),
    ):
        cache_status_command(
            argparse.Namespace(
                project_root=None,
                all_cache=True,
                json_output=False,
            )
        )

    assert "valid" in output.getvalue()
    assert "\x1b[" in output.getvalue()


def test_cache_clear_confirmation_yes_absent_and_symlink_safety(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    (cache_root / "resource").write_text("cached", encoding="utf-8")
    sibling = tmp_path / "sibling"
    sibling.write_text("keep", encoding="utf-8")
    output = io.StringIO()

    with (
        patch("vividly.cli.default_dependency_cache_root", return_value=cache_root),
        patch("builtins.input", return_value="no"),
        contextlib.redirect_stdout(output),
    ):
        cache_clear_command(argparse.Namespace(assume_yes=False))
    assert cache_root.is_dir()
    assert "was not cleared" in output.getvalue()

    with (
        patch("vividly.cli.default_dependency_cache_root", return_value=cache_root),
        patch("builtins.input", return_value="yes"),
    ):
        cache_clear_command(argparse.Namespace(assume_yes=False))
    assert not cache_root.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"

    output = io.StringIO()
    with (
        patch("vividly.cli.default_dependency_cache_root", return_value=cache_root),
        contextlib.redirect_stdout(output),
    ):
        cache_clear_command(argparse.Namespace(assume_yes=True))
    assert "already empty" in output.getvalue()

    target = tmp_path / "target"
    target.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(target, target_is_directory=True)
    with (
        patch("vividly.cli.default_dependency_cache_root", return_value=linked_root),
        pytest.raises(SystemExit, match="symbolic link"),
    ):
        cache_clear_command(argparse.Namespace(assume_yes=True))


def test_rehearse_reports_the_bounded_success_claim(tmp_path: Path) -> None:
    output = io.StringIO()
    with (
        patch(
            "vividly.rehearsal.rehearse_project",
            return_value=RehearsalResult(issues=()),
        ) as rehearse,
        contextlib.redirect_stdout(output),
    ):
        rehearse_command(argparse.Namespace(project_root=tmp_path))

    rehearse.assert_called_once_with(tmp_path)
    assert output.getvalue().strip() == (
        "Rehearsal passed: the presentation worked without external dependency access "
        "for the slides and interactions exercised during this rehearsal."
    )


def test_rehearse_reports_observed_failures(tmp_path: Path) -> None:
    result = RehearsalResult(
        issues=(
            RehearsalIssue(
                kind="cache-miss",
                route="vividly/entry",
                url="http://127.0.0.1:8000/~dependencies/graph/dynamic.js",
                detail="dependency was not present in the Vividly cache",
            ),
        )
    )
    errors = io.StringIO()
    with (
        patch("vividly.rehearsal.rehearse_project", return_value=result),
        contextlib.redirect_stderr(errors),
        pytest.raises(SystemExit) as failure,
    ):
        rehearse_command(argparse.Namespace(project_root=tmp_path))

    assert failure.value.code == 1
    assert errors.getvalue().splitlines() == [
        "Rehearsal failed:",
        "- cache-miss at vividly/entry: "
        "http://127.0.0.1:8000/~dependencies/graph/dynamic.js "
        "(dependency was not present in the Vividly cache)",
    ]


def test_export_requires_and_parses_output_destination() -> None:
    parser = create_parser()

    arguments = parser.parse_args(["export", "project", "--output", "artifact"])

    assert arguments.project_root == Path("project")
    assert arguments.output == Path("artifact")
    with pytest.raises(SystemExit):
        parser.parse_args(["export", "project"])


def test_install_browser_uses_playwright_from_active_environment() -> None:
    output = io.StringIO()
    with (
        patch.object(sys, "argv", ["vividly", "install-browser"]),
        patch("vividly.cli.subprocess.run") as run,
        patch("vividly.cli.version", return_value="1.62.0"),
        contextlib.redirect_stdout(output),
    ):
        main()

    run.assert_called_once_with(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )
    assert output.getvalue().strip() == "Chromium is installed for Playwright 1.62.0."


def test_install_browser_reports_installer_failure() -> None:
    failure = subprocess.CalledProcessError(7, ["playwright", "install", "chromium"])
    with (
        patch("vividly.cli.subprocess.run", side_effect=failure),
        pytest.raises(SystemExit) as raised,
    ):
        install_browser_command(argparse.Namespace())

    assert str(raised.value) == (
        "vividly install-browser: Playwright installer failed with exit code 7"
    )


def test_install_browser_reports_start_failure() -> None:
    with (
        patch("vividly.cli.subprocess.run", side_effect=OSError("not executable")),
        pytest.raises(SystemExit) as raised,
    ):
        install_browser_command(argparse.Namespace())

    assert str(raised.value) == (
        "vividly install-browser: could not start Playwright installer: not executable"
    )


def test_running_without_a_command_shows_help() -> None:
    output = io.StringIO()
    with patch.object(sys, "argv", ["vividly"]), contextlib.redirect_stdout(output):
        main()

    help_text = output.getvalue()
    assert "usage: vividly" in help_text
    assert "provision" in help_text
    assert "publish" in help_text


def test_version_flag_names_runtime_identities() -> None:
    with packaged_runtime() as runtime:
        framework = runtime.manifest.version
        composition_api = runtime.manifest.composition_api

    output = io.StringIO()
    with (
        patch.object(sys, "argv", ["vividly", "--version"]),
        contextlib.redirect_stdout(output),
        pytest.raises(SystemExit) as exit_info,
    ):
        main()

    assert exit_info.value.code == 0
    assert output.getvalue().strip() == (
        f"vividly {tool_version()} "
        f"(framework {framework}; composition API {composition_api})"
    )


def test_provision_defaults_to_current_directory_and_prompts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    arguments = create_parser().parse_args(["provision"])

    assert arguments.project_root == tmp_path
    assert arguments.assume_yes is False
    assert arguments.upgrade is False


def test_provision_parses_upgrade_flag(tmp_path: Path) -> None:
    arguments = create_parser().parse_args(["provision", str(tmp_path), "--upgrade", "--yes"])

    assert arguments.project_root == tmp_path
    assert arguments.upgrade is True
    assert arguments.assume_yes is True


def test_publish_parses_target_path_and_dry_run(tmp_path: Path) -> None:
    arguments = create_parser().parse_args(
        ["publish", str(tmp_path), "--target", "pages", "--dry-run"]
    )

    assert arguments.project_root == tmp_path
    assert arguments.target_name == "pages"
    assert arguments.dry_run is True


def test_publish_help_describes_defaults_safety_and_exit_behavior(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        create_parser().parse_args(["publish", "--help"])

    assert exit_info.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    for expected in (
        "default: current directory",
        "default: configured default or sole target",
        "entire containing Git repository must be clean",
        "isolated temporary index",
        "does not switch branches",
        "create a worktree or local publication branch",
        "ordinary non-force push",
        "unchanged results exit 0",
        "failures exit nonzero",
    ):
        assert expected in help_text


def test_provision_creates_author_seeds_and_exact_package_selection(tmp_path: Path) -> None:
    project_root = tmp_path / "my-project"
    arguments = argparse.Namespace(project_root=project_root, assume_yes=False)

    output = io.StringIO()
    with patch("vividly.cli.input", return_value="y"), contextlib.redirect_stdout(output):
        provision_command(arguments)

    config = load_project_config(project_root)
    assert isinstance(config.runtime, PackageRuntime)
    with packaged_runtime() as runtime:
        assert config.runtime.distribution_version == runtime.distribution_version
        assert config.runtime.version == runtime.manifest.version
        assert config.runtime.integrity == runtime.manifest.integrity

    assert (project_root / ".gitignore").read_text(encoding="utf-8") == ".vividly/\n"
    assert (project_root / "site" / "catalog.yaml").is_file()
    assert (project_root / "site" / "presentations" / "vividly.yaml").is_file()
    assert (project_root / "site" / "slides" / "title-card" / "slide.html").is_file()
    assert (project_root / ".github" / "copilot-instructions.md").is_file()
    assert not (project_root / "site" / "index.html").exists()
    assert not (project_root / "site" / "vividly").exists()
    assert not (project_root / ".vividly").exists()
    assert not (project_root / BASELINE_NAME).exists()
    assert "Runtime integrity: sha256:" in output.getvalue()


def test_provision_preserves_unrelated_content_and_existing_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "outline.md").write_text("draft\n", encoding="utf-8")
    arguments = argparse.Namespace(project_root=tmp_path, assume_yes=True)

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        provision_command(arguments)

    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "build/\n"
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "hello\n"
    assert (tmp_path / "drafts" / "outline.md").read_text(encoding="utf-8") == "draft\n"
    assert "existing Git repository" not in output.getvalue()
    assert "Add this recommended rule if it is not already present: .vividly/" in output.getvalue()


def test_provision_summarizes_top_level_content_and_git_repository(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "objects").mkdir()
    for index in range(15):
        (tmp_path / f"file-{index:02d}.txt").write_text("x", encoding="utf-8")
    arguments = argparse.Namespace(project_root=tmp_path, assume_yes=False)

    output = io.StringIO()
    with patch("vividly.cli.input", return_value="n"), contextlib.redirect_stdout(output):
        provision_command(arguments)

    message = output.getvalue()
    assert "existing Git repository" in message
    assert "...and 6 more" in message
    assert ".git/objects" not in message
    assert not (tmp_path / "vividly.yaml").exists()


def test_provision_refuses_an_existing_configuration_without_parsing_it(tmp_path: Path) -> None:
    config_path = tmp_path / "vividly.yaml"
    config_path.write_text("not valid yaml: [", encoding="utf-8")

    with pytest.raises(SystemExit, match="already provisioned") as failure:
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))

    assert "was not changed" in str(failure.value)
    assert config_path.read_text(encoding="utf-8") == "not valid yaml: ["
    assert not (tmp_path / "site").exists()


def test_provision_upgrade_repins_only_package_runtime_configuration(tmp_path: Path) -> None:
    _provision(tmp_path)
    config_path = tmp_path / "vividly.yaml"
    catalog_path = tmp_path / "site" / "catalog.yaml"
    original_catalog = catalog_path.read_bytes()
    config = config_path.read_text(encoding="utf-8")
    with packaged_runtime() as runtime:
        current_integrity = runtime.manifest.integrity
    stale_integrity = f"sha256:{'0' * 64}"
    config_path.write_text(
        config.replace(current_integrity, stale_integrity),
        encoding="utf-8",
    )

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        provision_command(
            argparse.Namespace(project_root=tmp_path, assume_yes=True, upgrade=True)
        )

    selected = load_project_config(tmp_path).runtime
    assert isinstance(selected, PackageRuntime)
    with packaged_runtime() as runtime:
        assert selected.distribution_version == runtime.distribution_version
        assert selected.version == runtime.manifest.version
        assert selected.integrity == runtime.manifest.integrity
    assert catalog_path.read_bytes() == original_catalog
    assert "Only vividly.yaml will change." in output.getvalue()
    assert "Updated package runtime selection" in output.getvalue()


def test_provision_upgrade_preserves_configuration_when_declined(tmp_path: Path) -> None:
    _provision(tmp_path)
    config_path = tmp_path / "vividly.yaml"
    original = config_path.read_text(encoding="utf-8")
    with packaged_runtime() as runtime:
        current_integrity = runtime.manifest.integrity
    config_path.write_text(
        original.replace(current_integrity, f"sha256:{'0' * 64}"),
        encoding="utf-8",
    )
    stale = config_path.read_text(encoding="utf-8")

    output = io.StringIO()
    with (
        patch("vividly.cli.input", return_value="n"),
        contextlib.redirect_stdout(output),
    ):
        provision_command(
            argparse.Namespace(project_root=tmp_path, assume_yes=False, upgrade=True)
        )

    assert config_path.read_text(encoding="utf-8") == stale
    assert "cancelled. Nothing was written." in output.getvalue()


def test_provision_upgrade_is_a_noop_when_selection_is_current(tmp_path: Path) -> None:
    _provision(tmp_path)
    config_path = tmp_path / "vividly.yaml"
    original = config_path.read_bytes()
    output = io.StringIO()

    with (
        patch("vividly.cli.input") as prompt,
        contextlib.redirect_stdout(output),
    ):
        provision_command(
            argparse.Namespace(project_root=tmp_path, assume_yes=False, upgrade=True)
        )

    prompt.assert_not_called()
    assert config_path.read_bytes() == original
    assert "already selects the installed package runtime" in output.getvalue()


def test_provision_upgrade_rejects_nonpackage_runtime(tmp_path: Path) -> None:
    config_path = tmp_path / "vividly.yaml"
    config_path.write_text(
        """
schema: 1
runtime:
  source: path
  path: runtime
  upstream_version: 0.0.1
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="supports only projects") as failure:
        provision_command(
            argparse.Namespace(project_root=tmp_path, assume_yes=True, upgrade=True)
        )

    assert "not `path`" in str(failure.value)
    assert config_path.read_text(encoding="utf-8").startswith("schema: 1")


def test_provision_upgrade_requires_existing_configuration(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="requires an existing vividly.yaml"):
        provision_command(
            argparse.Namespace(project_root=tmp_path, assume_yes=True, upgrade=True)
        )


def test_provision_upgrade_rejects_invalid_configuration_without_writing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "vividly.yaml"
    config_path.write_text("not valid yaml: [", encoding="utf-8")

    with pytest.raises(SystemExit, match="cannot upgrade invalid vividly.yaml") as failure:
        provision_command(
            argparse.Namespace(project_root=tmp_path, assume_yes=True, upgrade=True)
        )

    assert "Nothing was written." in str(failure.value)
    assert config_path.read_text(encoding="utf-8") == "not valid yaml: ["


def test_provision_refuses_a_legacy_project_without_parsing_baseline(tmp_path: Path) -> None:
    baseline_path = tmp_path / BASELINE_NAME
    baseline_path.write_text("not json", encoding="utf-8")

    with pytest.raises(SystemExit, match="must be reprovisioned") as failure:
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))

    assert "Automatic migration is unavailable" in str(failure.value)
    assert "nothing was written" in str(failure.value)
    assert baseline_path.read_text(encoding="utf-8") == "not json"
    assert not (tmp_path / "vividly.yaml").exists()


@pytest.mark.parametrize(
    "occupied",
    [
        Path("site/catalog.yaml"),
        Path(".github/copilot-instructions.md"),
    ],
)
def test_provision_rejects_seed_collisions_without_writing(
    tmp_path: Path,
    occupied: Path,
) -> None:
    destination = tmp_path / occupied
    destination.parent.mkdir(parents=True)
    destination.write_text("author content", encoding="utf-8")

    with pytest.raises(SystemExit, match="would overwrite existing paths") as failure:
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))

    assert occupied.as_posix() in str(failure.value)
    assert destination.read_text(encoding="utf-8") == "author content"
    assert not (tmp_path / "vividly.yaml").exists()


def test_provision_rejects_a_nonregular_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").mkdir()

    with pytest.raises(SystemExit, match=r"\.gitignore"):
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))

    assert not (tmp_path / "vividly.yaml").exists()


def test_provision_rejects_a_path_that_is_a_file(tmp_path: Path) -> None:
    destination = tmp_path / "project"
    destination.write_text("not a directory", encoding="utf-8")

    with pytest.raises(SystemExit, match="is not a directory"):
        provision_command(argparse.Namespace(project_root=destination, assume_yes=True))


def test_provision_writes_nothing_when_the_user_declines(tmp_path: Path) -> None:
    output = io.StringIO()
    with (
        patch("vividly.cli.input", return_value="n"),
        contextlib.redirect_stdout(output),
    ):
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=False))

    assert list(tmp_path.iterdir()) == []
    assert "cancelled" in output.getvalue()


def test_provision_does_not_write_configuration_when_seed_copy_fails(tmp_path: Path) -> None:
    with (
        patch("vividly.cli.shutil.copytree", side_effect=OSError("copy failed")),
        pytest.raises(OSError, match="copy failed"),
    ):
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))

    assert not (tmp_path / "vividly.yaml").exists()


def test_run_defaults_to_current_directory_and_default_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    arguments = create_parser().parse_args(["run"])

    assert arguments.project_root == tmp_path
    assert arguments.port == DEFAULT_PORT
    assert arguments.no_watch is False

    no_watch_arguments = create_parser().parse_args(["run", "--no-watch"])
    assert no_watch_arguments.no_watch is True


@pytest.mark.parametrize("value", ["1", "8080", "65535"])
def test_port_number_accepts_valid_ports(value: str) -> None:
    assert port_number(value) == int(value)


@pytest.mark.parametrize("value", ["0", "65536", "-1"])
def test_port_number_rejects_out_of_range_ports(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="between 1 and 65535"):
        port_number(value)


def test_run_rejects_a_project_root_without_configuration(tmp_path: Path) -> None:
    arguments = argparse.Namespace(
        port=DEFAULT_PORT,
        project_root=tmp_path,
        no_watch=False,
    )

    with pytest.raises(SystemExit) as failure:
        run_command(arguments)

    assert str(failure.value) == (
        f"vividly run: project configuration not found: {tmp_path / 'vividly.yaml'}"
    )


def test_run_rejects_legacy_project_without_parsing_baseline(tmp_path: Path) -> None:
    (tmp_path / BASELINE_NAME).write_text("not json", encoding="utf-8")
    arguments = argparse.Namespace(
        port=DEFAULT_PORT,
        project_root=tmp_path,
        no_watch=False,
    )

    with (
        patch("vividly.cli.http.server.ThreadingHTTPServer") as server,
        pytest.raises(SystemExit, match="requires reprovisioning"),
    ):
        run_command(arguments)

    server.assert_not_called()


def test_run_rejects_a_site_without_a_catalog(tmp_path: Path) -> None:
    _provision(tmp_path)
    catalog_path = tmp_path / "site" / "catalog.yaml"
    catalog_path.unlink()
    arguments = argparse.Namespace(
        port=DEFAULT_PORT,
        project_root=tmp_path,
        no_watch=False,
    )

    with (
        patch("vividly.cli.http.server.ThreadingHTTPServer") as server,
        pytest.raises(SystemExit) as failure,
    ):
        run_command(arguments)
    assert str(failure.value) == (
        f"vividly run: project catalog is not a regular file: {catalog_path}"
    )
    server.assert_not_called()


def test_run_help_describes_a_project_root(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        create_parser().parse_args(["run", "--help"])

    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "project root containing site/" in help_text
    assert "presentation root" not in help_text


def test_run_reports_when_port_is_already_in_use(tmp_path: Path) -> None:
    _provision(tmp_path)
    arguments = argparse.Namespace(
        port=DEFAULT_PORT,
        project_root=tmp_path,
        no_watch=False,
    )

    with (
        patch(
            "vividly.cli.http.server.ThreadingHTTPServer",
            side_effect=OSError(errno.EADDRINUSE, "Address already in use"),
        ),
        pytest.raises(SystemExit) as failure,
    ):
        run_command(arguments)

    assert str(failure.value) == (
        f"vividly run: port {DEFAULT_PORT} is already in use\n"
        "Choose another port with --port PORT."
    )


def test_run_stops_cleanly_after_keyboard_interrupt(tmp_path: Path) -> None:
    _provision(tmp_path)
    arguments = argparse.Namespace(
        port=DEFAULT_PORT,
        project_root=tmp_path,
        no_watch=True,
    )

    class InterruptingServer:
        server_port = DEFAULT_PORT

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            del args
            return None

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

    output = io.StringIO()
    with (
        patch("vividly.cli.http.server.ThreadingHTTPServer", return_value=InterruptingServer()),
        contextlib.redirect_stdout(output),
    ):
        run_command(arguments)

    assert "Server stopped." in output.getvalue()


def test_run_surfaces_watcher_failure(tmp_path: Path) -> None:
    _provision(tmp_path)
    arguments = argparse.Namespace(port=0, project_root=tmp_path, no_watch=False)

    with (
        patch(
            "vividly.watcher.watch_for_reloads",
            side_effect=WatcherError("watcher failed: watch unavailable"),
        ),
        pytest.raises(SystemExit) as failure,
    ):
        run_command(arguments)

    assert str(failure.value) == "vividly run: watcher failed: watch unavailable"


def test_run_serves_the_composed_project(tmp_path: Path) -> None:
    _provision(tmp_path)
    with packaged_runtime() as runtime:
        expected_index = (runtime.runtime_root / "index.html").read_bytes()
    expected_catalog = (tmp_path / "site" / "catalog.yaml").read_bytes()
    author_script = tmp_path / "site" / "author.js"
    author_script.write_text("export const author = true;\n", encoding="utf-8")
    port = _available_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vividly.cli",
            "run",
            str(tmp_path),
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=tmp_path,
    )

    try:
        status, content_type, cache_control, response_body = _request_when_ready(
            process,
            port,
            "/",
        )
        assert status == 200
        assert response_body != expected_index
        assert RELOAD_CLIENT in response_body
        assert DEPENDENCY_BASE_ATTRIBUTE in response_body
        assert (
            response_body.replace(RELOAD_CLIENT, b"").replace(DEPENDENCY_BASE_ATTRIBUTE, b"")
            == expected_index
        )
        assert content_type == "text/html"
        assert cache_control == "no-store"

        status, _, cache_control, response_body = _request_when_ready(
            process,
            port,
            "/catalog.yaml?cache-bust=1",
        )
        assert status == 200
        assert response_body == expected_catalog
        assert cache_control == "no-store"

        status, content_type, _, response_body = _request_when_ready(
            process,
            port,
            "/author.js",
            method="HEAD",
        )
        assert status == 200
        assert content_type in {"text/javascript", "application/javascript"}
        assert response_body == b""

        status, _, cache_control, _ = _request_when_ready(
            process,
            port,
            "/%2e%2e/vividly.yaml",
            expected_status=404,
        )
        assert status == 404
        assert cache_control == "no-store"

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        connection.request("GET", "/vividly/~dev/events")
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/event-stream"
        assert response.getheader("Cache-Control") == "no-store"
        assert response.read(len(b": connected\n\n")) == b": connected\n\n"

        added_script = tmp_path / "site" / "added.js"
        added_content = b"export const added = true;\n"
        added_script.write_bytes(added_content)
        event = b"event: reload\ndata: reload\n\n"
        assert response.read(len(event)) == event

        status, _, _, response_body = _request_when_ready(
            process,
            port,
            "/added.js",
        )
        assert status == 200
        assert response_body == added_content
        connection.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)


def test_run_no_watch_omits_reload_support(tmp_path: Path) -> None:
    _provision(tmp_path)
    with packaged_runtime() as runtime:
        expected_index = (runtime.runtime_root / "index.html").read_bytes()
    port = _available_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vividly.cli",
            "run",
            str(tmp_path),
            "--port",
            str(port),
            "--no-watch",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=tmp_path,
    )

    try:
        status, _, cache_control, response_body = _request_when_ready(
            process,
            port,
            "/",
        )
        assert status == 200
        assert DEPENDENCY_BASE_ATTRIBUTE in response_body
        assert response_body.replace(DEPENDENCY_BASE_ATTRIBUTE, b"") == expected_index
        assert cache_control == "no-store"

        status, _, cache_control, response_body = _request_when_ready(
            process,
            port,
            "/vividly/~dev/events",
            expected_status=404,
        )
        assert status == 404
        assert response_body == b""
        assert cache_control == "no-store"
    finally:
        process.terminate()
        process.communicate(timeout=5)


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _request_when_ready(
    process: subprocess.Popen[str],
    port: int,
    path: str,
    *,
    method: str = "GET",
    expected_status: int = 200,
) -> tuple[int, str | None, str | None, bytes]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate()
            pytest.fail(f"preview server exited before serving a request:\n{output}")

        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.2)
            connection.request(method, path)
            response = connection.getresponse()
            body = response.read()
            content_type = response.getheader("Content-Type")
            cache_control = response.getheader("Cache-Control")
            connection.close()
            assert response.status == expected_status
            return response.status, content_type, cache_control, body
        except OSError:
            time.sleep(0.05)

    pytest.fail("preview server did not start within five seconds")
