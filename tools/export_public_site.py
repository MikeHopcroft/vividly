"""Export a non-deploying Vividly public-site publication candidate."""

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vividly.composition import CompositionError, compose_project
from vividly.export import ExportError, export_project
from vividly.project import ProjectConfigError
from vividly.runtime import RuntimeManifestError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class PublicSiteExportError(RuntimeError):
    """The repository cannot produce an attributable public-site candidate."""


@dataclass(frozen=True)
class PublicSiteCandidate:
    """A locally exported public site and its source identity."""

    path: Path
    source_revision: str
    framework_version: str


def _git(repository_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise PublicSiteExportError(detail)
    return result.stdout.strip()


def repository_revision(repository_root: Path) -> str:
    """Return HEAD when every tracked and untracked source file is committed."""
    changes = _git(repository_root, "status", "--porcelain=v1", "--untracked-files=all")
    if changes:
        raise PublicSiteExportError(
            "repository has uncommitted changes; commit or stash them before "
            "exporting a publication candidate"
        )
    revision = _git(repository_root, "rev-parse", "--verify", "HEAD")
    if COMMIT_PATTERN.fullmatch(revision) is None:
        raise PublicSiteExportError(f"git returned an invalid source revision: {revision!r}")
    return revision


def check_public_reference(repository_root: Path) -> None:
    """Require committed public reference files to match their canonical source."""
    result = subprocess.run(
        [
            sys.executable,
            str(repository_root / "tools/sync_public_reference.py"),
            "--check",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stdout.strip() or result.stderr.strip() or "reference check failed"
        raise PublicSiteExportError(detail)


def export_public_site(repository_root: Path, destination: Path) -> PublicSiteCandidate:
    """Export one clean, synchronized public-site publication candidate."""
    revision = repository_revision(repository_root)
    check_public_reference(repository_root)
    with compose_project(repository_root, verify_package_contents=True) as composition:
        framework_version = composition.runtime.manifest.version
    exported = export_project(repository_root, destination)
    return PublicSiteCandidate(
        path=exported,
        source_revision=revision,
        framework_version=framework_version,
    )


def create_parser() -> argparse.ArgumentParser:
    """Create the public-site candidate argument parser."""
    parser = argparse.ArgumentParser(
        description="Export the Vividly public site without deploying it.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        metavar="DESTINATION",
        help="absent or empty destination directory outside the repository",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Export and report one attributable public-site candidate."""
    parsed = create_parser().parse_args(arguments)
    try:
        candidate = export_public_site(REPOSITORY_ROOT, parsed.output)
    except (
        OSError,
        CompositionError,
        ExportError,
        ProjectConfigError,
        PublicSiteExportError,
        RuntimeManifestError,
    ) as error:
        print(f"public-site export: {error}", file=sys.stderr)
        return 1
    print(f"Exported public-site candidate to {candidate.path}")
    print(f"Source revision: {candidate.source_revision}")
    print(f"Framework version: {candidate.framework_version}")
    print("No deployment was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
