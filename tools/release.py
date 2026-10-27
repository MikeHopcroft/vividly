"""Repository release gates specified in docs/specs/publishing.md, section 18."""

import argparse
import json
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATTERN = re.compile(r"[0-9a-f]{40}")
VERSION_PATTERN = re.compile(r"0\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


class ReleaseError(RuntimeError):
    """A release identity or safety gate failed."""


def git(*arguments: str) -> str:
    """Run a required Git operation without shell interpolation."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ReleaseError(f"git {' '.join(arguments)}: {result.stderr.strip()}")
    return result.stdout.strip()


def validate_inputs(source: str, version: str) -> None:
    """Accept only an exact source SHA and an ordinary initial-series release."""
    if SOURCE_PATTERN.fullmatch(source) is None:
        raise ReleaseError("source must be a full lowercase 40-character commit SHA")
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ReleaseError("version must be an ordinary 0.x.y release")


def require_ancestor(ancestor: str, descendant: str) -> None:
    """Reject divergent or out-of-order releases."""
    git("merge-base", "--is-ancestor", ancestor, descendant)


def check_source(source: str, version: str, *, resume: bool) -> None:
    """Check committed versions and current release-ref eligibility.

    With ``resume``, a re-run job accepts an existing matching annotated tag.
    """
    validate_inputs(source, version)
    if git("rev-parse", "HEAD") != source:
        raise ReleaseError("checkout does not match the selected source commit")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        raise ReleaseError("release source checkout must be clean")
    require_ancestor(source, "refs/remotes/origin/main")
    require_ancestor("refs/remotes/origin/stable", source)
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)
    manifest = read_object(ROOT / "src/vividly/resources/runtime/vividly-runtime.json")
    selector_value = cast(object, yaml.safe_load((ROOT / "vividly.yaml").read_text()))
    if not isinstance(selector_value, dict):
        raise ReleaseError("vividly.yaml must be an object")
    selector = cast(dict[str, object], selector_value)
    runtime_value = selector.get("runtime")
    if not isinstance(runtime_value, dict):
        raise ReleaseError("vividly.yaml is missing its runtime selector")
    runtime = cast(dict[str, object], runtime_value)
    runtime_version = (
        (ROOT / "src/vividly/resources/runtime/vividly/version.txt").read_text().strip()
    )
    if (
        project["project"]["version"] != version
        or manifest.get("version") != version
        or runtime_version != version
        or runtime.get("version") != version
    ):
        raise ReleaseError(
            "package, runtime manifest, runtime text, and selector versions must agree"
        )
    stable_source = git("rev-parse", "refs/remotes/origin/stable")
    stable_version = tomllib.loads(git("show", f"{stable_source}:pyproject.toml"))["project"][
        "version"
    ]
    if not isinstance(stable_version, str) or VERSION_PATTERN.fullmatch(stable_version) is None:
        raise ReleaseError("stable does not identify an ordinary 0.x.y release")
    selected_number = tuple(int(part) for part in version.split("."))
    stable_number = tuple(int(part) for part in stable_version.split("."))
    if selected_number < stable_number or (
        selected_number == stable_number and source != stable_source
    ):
        raise ReleaseError("release version must advance stable, or resume its exact source")
    if not (ROOT / ".github/workflows/release.yml").is_file():
        raise ReleaseError("selected source predates the release workflow")
    tag = f"refs/tags/v{version}"
    advertised = git("ls-remote", "--tags", "origin", tag)
    if advertised:
        if not resume:
            raise ReleaseError(f"release tag v{version} already exists")
        git("fetch", "--no-tags", "origin", tag)
        if (
            git("cat-file", "-t", "FETCH_HEAD") != "tag"
            or git("rev-parse", "FETCH_HEAD^{commit}") != source
            or git("cat-file", "tag", "FETCH_HEAD").split("\n\n", 1)[-1] != f"Release v{version}"
        ):
            raise ReleaseError("existing release tag is not the expected annotated source tag")


def read_object(path: Path) -> dict[str, object]:
    """Read a JSON mapping, rejecting non-object documents."""
    value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        raise ReleaseError(f"expected a JSON object: {path}")
    return cast(dict[str, object], value)


def pypi_published(version: str) -> bool:
    """Read public PyPI, treating only HTTP 404 as an unpublished version."""
    url = f"https://pypi.org/pypi/vividly/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30):
            return True
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise ReleaseError(f"PyPI lookup failed: HTTP {error.code}") from error


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one explicit release gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("source", "pypi"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--resume", action="store_true")
    parsed = parser.parse_args(arguments)
    try:
        validate_inputs(parsed.source, parsed.version)
        if parsed.command == "source":
            check_source(parsed.source, parsed.version, resume=parsed.resume)
        elif pypi_published(parsed.version):
            raise ReleaseError(f"PyPI version {parsed.version} is already in use")
    except (
        ReleaseError,
        OSError,
        ValueError,
        urllib.error.URLError,
        yaml.YAMLError,
    ) as error:
        print(f"release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
