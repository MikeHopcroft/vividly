"""Release workflow gates specified by docs/specs/publishing.md section 18.1."""

import json
import subprocess
import urllib.error
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tools import release

SOURCE = "a" * 40
VERSION = "0.0.2"
REPOSITORY_ROOT = Path(__file__).parents[1]


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@dataclass(frozen=True)
class SourceRepository:
    root: Path
    source: str
    stable: str


@pytest.fixture
def source_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SourceRepository:
    root = tmp_path / "source"
    remote = tmp_path / "remote.git"
    root.mkdir()
    git(root, "init", "--quiet", "--initial-branch=main")
    git(root, "config", "user.name", "Release Tests")
    git(root, "config", "user.email", "tests@example.invalid")
    (root / "pyproject.toml").write_text('[project]\nversion = "0.0.1"\n')
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Initial release")
    stable = git(root, "rev-parse", "HEAD")
    git(root, "branch", "stable")
    runtime = root / "src/vividly/resources/runtime"
    (runtime / "vividly").mkdir(parents=True)
    (runtime / "vividly/version.txt").write_text(VERSION + "\n")
    (runtime / "vividly-runtime.json").write_text(json.dumps({"version": VERSION}))
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{VERSION}"\n')
    (root / "vividly.yaml").write_text(f"runtime:\n  version: {VERSION}\n")
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/release.yml").write_text("name: Release\n")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Prepare release")
    source = git(root, "rev-parse", "HEAD")
    git(root, "init", "--bare", "--quiet", str(remote))
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "--quiet", "origin", "main", "stable")
    monkeypatch.setattr(release, "ROOT", root)
    return SourceRepository(root, source, stable)


@pytest.mark.parametrize(
    ("source", "version"),
    [
        ("main", VERSION),
        ("a" * 39, VERSION),
        ("A" * 40, VERSION),
        (SOURCE, "0.0.2rc1"),
        (SOURCE, "0.0.02"),
        (SOURCE, "1.0.0"),
        (SOURCE, "0.0.2\n"),
    ],
)
def test_release_requires_exact_sha_and_ordinary_initial_version(source: str, version: str) -> None:
    with pytest.raises(release.ReleaseError):
        release.validate_inputs(source, version)


def test_clean_release_descending_from_stable_is_eligible(
    source_repository: SourceRepository,
) -> None:
    release.check_source(source_repository.source, VERSION, resume=False)


def test_dirty_source_is_rejected(source_repository: SourceRepository) -> None:
    (source_repository.root / "untracked.txt").write_text("not committed")
    with pytest.raises(release.ReleaseError, match="clean"):
        release.check_source(source_repository.source, VERSION, resume=False)


def test_checkout_must_match_selected_commit(source_repository: SourceRepository) -> None:
    with pytest.raises(release.ReleaseError, match="checkout"):
        release.check_source(SOURCE, VERSION, resume=False)


@pytest.mark.parametrize(
    "name",
    [
        "pyproject.toml",
        "vividly.yaml",
        "src/vividly/resources/runtime/vividly-runtime.json",
        "src/vividly/resources/runtime/vividly/version.txt",
    ],
)
def test_all_committed_versions_must_agree(
    source_repository: SourceRepository, name: str
) -> None:
    root = source_repository.root
    path = root / name
    path.write_text(path.read_text().replace(VERSION, "0.0.3"))
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Mismatched version")
    source = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", source)
    with pytest.raises(release.ReleaseError, match="versions must agree"):
        release.check_source(source, VERSION, resume=False)


@pytest.mark.parametrize("tag_kind", ["expected", "lightweight", "wrong-source", "wrong-message"])
def test_existing_tag_is_accepted_only_for_a_matching_rerun(
    source_repository: SourceRepository, tag_kind: str
) -> None:
    root = source_repository.root
    if tag_kind == "lightweight":
        git(root, "tag", f"v{VERSION}")
    else:
        target = (
            source_repository.stable if tag_kind == "wrong-source" else source_repository.source
        )
        message = "Wrong annotation" if tag_kind == "wrong-message" else f"Release v{VERSION}"
        git(root, "tag", "-a", f"v{VERSION}", target, "-m", message)
    git(root, "push", "--quiet", "origin", f"v{VERSION}")
    with pytest.raises(release.ReleaseError, match="already exists"):
        release.check_source(source_repository.source, VERSION, resume=False)
    if tag_kind == "expected":
        release.check_source(source_repository.source, VERSION, resume=True)
        git(root, "push", "--quiet", "origin", f"{source_repository.source}:refs/heads/stable")
        git(root, "fetch", "--quiet", "origin", "+refs/heads/stable:refs/remotes/origin/stable")
        release.check_source(source_repository.source, VERSION, resume=True)
    else:
        with pytest.raises(release.ReleaseError, match="annotated"):
            release.check_source(source_repository.source, VERSION, resume=True)


def test_same_version_from_a_different_source_cannot_follow_stable(
    source_repository: SourceRepository,
) -> None:
    root = source_repository.root
    git(root, "update-ref", "refs/remotes/origin/stable", source_repository.source)
    (root / "later.txt").write_text("later source")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Later source")
    later = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", later)
    with pytest.raises(release.ReleaseError, match="advance stable"):
        release.check_source(later, VERSION, resume=True)


def test_older_source_cannot_rewind_stable(source_repository: SourceRepository) -> None:
    root = source_repository.root
    (root / "later.txt").write_text("later source")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Later source")
    later = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/stable", later)
    git(root, "checkout", "--quiet", source_repository.source)
    with pytest.raises(release.ReleaseError, match="merge-base"):
        release.check_source(source_repository.source, VERSION, resume=True)


def test_descendant_source_cannot_release_a_lower_version(
    source_repository: SourceRepository,
) -> None:
    root = source_repository.root
    git(root, "checkout", "--quiet", "stable")
    (root / "pyproject.toml").write_text('[project]\nversion = "0.0.3"\n')
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Newer stable release")
    git(root, "update-ref", "refs/remotes/origin/stable", git(root, "rev-parse", "HEAD"))
    git(root, "checkout", "--quiet", "main")
    git(root, "merge", "--quiet", "--strategy=ours", "--no-edit", "stable")
    source = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", source)
    with pytest.raises(release.ReleaseError, match="advance stable"):
        release.check_source(source, VERSION, resume=False)


@pytest.mark.parametrize("code", [403, 404, 429, 500])
def test_only_pypi_404_means_unpublished(code: int) -> None:
    error = urllib.error.HTTPError("https://pypi.org/", code, "failure", Message(), None)
    with patch.object(release.urllib.request, "urlopen", side_effect=error):
        if code == 404:
            assert not release.pypi_published(VERSION)
            assert release.main(["pypi", "--source", SOURCE, "--version", VERSION]) == 0
        else:
            with pytest.raises(release.ReleaseError, match=f"HTTP {code}"):
                release.pypi_published(VERSION)


def test_new_run_rejects_a_version_already_on_pypi() -> None:
    with patch.object(release.urllib.request, "urlopen", return_value=MagicMock()):
        assert release.pypi_published(VERSION)
        assert release.main(["pypi", "--source", SOURCE, "--version", VERSION]) == 1


@pytest.mark.parametrize("name", ["ci.yml", "deploy-pages.yml", "release.yml"])
def test_workflow_bash_steps_have_valid_syntax(name: str) -> None:
    workflow = yaml.safe_load((REPOSITORY_ROOT / ".github/workflows" / name).read_text())
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if "run" not in step:
                continue
            result = subprocess.run(
                ["bash", "-n"],
                input=step["run"],
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, f"{step.get('name', step['run'])}: {result.stderr}"
