"""Repository-only entry points specified in docs/specs/publishing.md section 18.2."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

from tools.release import ReleaseError, validate_inputs

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "MikeHopcroft/vividly"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/"


class MaintainerError(RuntimeError):
    """A maintainer operation could not safely complete."""


def run(*arguments: str, input_text: str | None = None, stream: bool = False) -> str:
    """Run a required command with visible stderr and repository-relative paths."""
    try:
        result = subprocess.run(
            arguments,
            cwd=ROOT,
            input=input_text,
            stdout=None if stream else subprocess.PIPE,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise MaintainerError(
            f"{arguments[0]} {arguments[1]} failed (exit {error.returncode})"
        ) from error
    return "" if stream else result.stdout.strip()


def preflight() -> None:
    """Check prerequisites before requesting a release."""
    if shutil.which("gh") is None:
        raise MaintainerError("required command not found: gh")
    run("gh", "auth", "status", "--hostname", "github.com")


def dispatch(workflow: str, inputs: dict[str, str], *, wait: bool) -> None:
    """Request one exact run, without guessing the newest run or retrying dispatch."""
    print(f"Requesting {workflow} on {REPOSITORY}@main...", flush=True)
    response = run(
        "gh",
        "api",
        "--hostname",
        "github.com",
        "--method",
        "POST",
        f"repos/{REPOSITORY}/actions/workflows/{workflow}/dispatches",
        "--input",
        "-",
        input_text=json.dumps({"ref": "main", "inputs": inputs, "return_run_details": True}),
    )
    details: object
    try:
        details = json.loads(response)
    except json.JSONDecodeError as error:
        raise MaintainerError(
            "Dispatch was accepted but run details were unavailable. Inspect "
            f"https://github.com/{REPOSITORY}/actions before retrying."
        ) from error
    record = cast(dict[str, object], details) if isinstance(details, dict) else {}
    run_id = record.get("workflow_run_id")
    url = record.get("html_url")
    if type(run_id) is not int or run_id <= 0 or url != f"{RUN_URL}{run_id}":
        raise MaintainerError(
            "Dispatch was accepted but run details were invalid. Inspect "
            f"https://github.com/{REPOSITORY}/actions before retrying."
        )
    print(f"Workflow requested: {url}", flush=True)
    if wait:
        print("Waiting for completion; environment approvals may still be required.", flush=True)
        run(
            "gh",
            "run",
            "watch",
            str(run_id),
            "--repo",
            f"github.com/{REPOSITORY}",
            "--exit-status",
            stream=True,
        )
        print("Workflow completed successfully.", flush=True)
    else:
        print("Completion has not been observed; use --wait to wait for the workflow.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    release = commands.add_parser("release", help="request the PyPI and Pages release workflow")
    release.add_argument("--source-commit", required=True, help="full committed source SHA on main")
    release.add_argument("--version", required=True, help="committed 0.x.y version")
    release.add_argument("--wait", action="store_true", help="wait and propagate workflow failure")
    parsed = parser.parse_args()
    try:
        source = cast(str, parsed.source_commit)
        version = cast(str, parsed.version)
        validate_inputs(source, version)
        preflight()
        dispatch(
            "release.yml",
            {"source_commit": source, "version": version},
            wait=cast(bool, parsed.wait),
        )
    except (MaintainerError, ReleaseError, OSError) as error:
        print(f"maintain: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
