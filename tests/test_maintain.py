"""Repository maintainer commands specified by docs/specs/publishing.md section 18.2."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tools import maintain

SOURCE = "a" * 40
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("wait", [False, True])
def test_dispatch_returns_and_watches_only_its_exact_run(wait: bool) -> None:
    response = json.dumps({"workflow_run_id": 42, "html_url": maintain.RUN_URL + "42"})
    with patch.object(maintain, "run", return_value=response) as run:
        maintain.dispatch("release.yml", {"version": "0.0.3"}, wait=wait)
    assert run.call_count == (2 if wait else 1)
    call = run.call_args_list[0]
    assert call.args[:5] == ("gh", "api", "--hostname", "github.com", "--method")
    assert call.args[5:7] == (
        "POST",
        "repos/MikeHopcroft/vividly/actions/workflows/release.yml/dispatches",
    )
    assert json.loads(call.kwargs["input_text"]) == {
        "ref": "main",
        "inputs": {"version": "0.0.3"},
        "return_run_details": True,
    }
    if wait:
        run.assert_called_with(
            "gh",
            "run",
            "watch",
            "42",
            "--repo",
            "github.com/MikeHopcroft/vividly",
            "--exit-status",
            stream=True,
        )


@pytest.mark.parametrize(
    "response",
    [
        "",
        "not json",
        "[]",
        "{}",
        '{"workflow_run_id":true}',
        json.dumps({"workflow_run_id": 42, "html_url": maintain.RUN_URL + "43"}),
    ],
)
def test_unavailable_run_details_never_retry_dispatch(response: str) -> None:
    with (
        patch.object(maintain, "run", return_value=response) as run,
        pytest.raises(maintain.MaintainerError, match="before retrying"),
    ):
        maintain.dispatch("release.yml", {}, wait=True)
    run.assert_called_once()


def test_release_forwards_explicit_identity() -> None:
    with (
        patch(
            "sys.argv",
            [
                "maintain",
                "release",
                "--source-commit",
                SOURCE,
                "--version",
                "0.0.3",
                "--wait",
            ],
        ),
        patch.object(maintain, "preflight") as preflight,
        patch.object(maintain, "dispatch") as dispatch,
    ):
        assert maintain.main() == 0
    preflight.assert_called_once_with()
    dispatch.assert_called_once_with(
        "release.yml", {"source_commit": SOURCE, "version": "0.0.3"}, wait=True
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--source-commit", "main", "--version", "0.0.3"],
        ["--source-commit", SOURCE, "--version", "0.0.3rc1"],
    ],
)
def test_invalid_release_inputs_stop_before_authentication(arguments: list[str]) -> None:
    with (
        patch("sys.argv", ["maintain", "release", *arguments]),
        patch.object(maintain, "preflight") as preflight,
        patch.object(maintain, "dispatch") as dispatch,
    ):
        assert maintain.main() == 1
    preflight.assert_not_called()
    dispatch.assert_not_called()


def test_watch_failure_propagates_without_success_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = json.dumps({"workflow_run_id": 42, "html_url": maintain.RUN_URL + "42"})
    with (
        patch.object(maintain, "run", side_effect=[response, maintain.MaintainerError("failed")]),
        pytest.raises(maintain.MaintainerError, match="failed"),
    ):
        maintain.dispatch("release.yml", {}, wait=True)
    assert "completed successfully" not in capsys.readouterr().out


@pytest.mark.parametrize("stream", [False, True])
def test_command_runs_from_repository_and_preserves_failure(stream: bool) -> None:
    with patch.object(maintain.subprocess, "run") as execute:
        execute.return_value.stdout = "output\n"
        assert maintain.run("gh", "test", stream=stream) == ("" if stream else "output")
        assert execute.call_args.kwargs["cwd"] == ROOT
        assert execute.call_args.kwargs["stdout"] == (None if stream else subprocess.PIPE)
        execute.side_effect = subprocess.CalledProcessError(3, ["gh", "test"])
        with pytest.raises(maintain.MaintainerError, match="exit 3"):
            maintain.run("gh", "test", stream=stream)


def test_bash_entry_point_preserves_cwd_independence_arguments_and_exit_status(
    tmp_path: Path,
) -> None:
    uv = tmp_path / "uv"
    uv.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$ARGUMENTS"\nexit 7\n')
    uv.chmod(0o755)
    arguments = tmp_path / "arguments"
    result = subprocess.run(
        ["bash", str(ROOT / "tools/release.sh"), "--example", "with spaces"],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "ARGUMENTS": str(arguments)},
        check=False,
    )
    assert result.returncode == 7
    assert arguments.read_text().splitlines() == [
        "--directory",
        str(ROOT),
        "run",
        "--locked",
        "python",
        "-m",
        "tools.maintain",
        "release",
        "--example",
        "with spaces",
    ]


def test_powershell_entry_point_preserves_arguments_and_exit_status(tmp_path: Path) -> None:
    powershell = shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell unavailable; manually reviewed, execution requires Windows/pwsh")
    harness = tmp_path / "harness.ps1"
    output = tmp_path / "arguments.json"
    harness.write_text(
        "function global:uv {\n"
        "  $args | ConvertTo-Json | Set-Content $env:ARGUMENTS\n"
        "  $global:LASTEXITCODE = 7\n"
        "}\n"
        f"& '{ROOT / 'tools/release.ps1'}' --example 'with spaces'\n"
        "exit $LASTEXITCODE\n"
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-File", str(harness)],
        cwd=tmp_path,
        env={**os.environ, "ARGUMENTS": str(output)},
        check=False,
    )
    assert result.returncode == 7
    assert json.loads(output.read_text(encoding="utf-8-sig")) == [
        "--directory",
        str(ROOT),
        "run",
        "--locked",
        "python",
        "-m",
        "tools.maintain",
        "release",
        "--example",
        "with spaces",
    ]
