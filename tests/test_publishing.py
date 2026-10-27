"""Tests for core publication specified by docs/specs/publishing.md."""

import argparse
import contextlib
import functools
import http.server
import io
import json
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from vividly.cli import main, provision_command
from vividly.publishing import PublicationError, publish_project
from vividly.publishing import publication as publication_module

REPOSITORY_ROOT = Path(__file__).parents[1]


@dataclass(frozen=True)
class PublishingFixture:
    project: Path
    remote: Path
    source_commit: str


def _run(arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _git(
    repository: Path,
    *arguments: str,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): git -C {repository} {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _bare_git(
    repository: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run(["git", "--git-dir", str(repository), *arguments], check=check)


def _commit(repository: Path, message: str) -> str:
    _git(repository, "add", ".")
    _git(repository, "commit", "--quiet", "-m", message)
    return _git(repository, "rev-parse", "HEAD").stdout.strip()


def _fixture(tmp_path: Path, *, custom_domain: bool = False) -> PublishingFixture:
    project = tmp_path / "project"
    remote = tmp_path / "remote.git"
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=project, assume_yes=True))
    domain = "    custom_domain: Slides.Example.COM\n" if custom_domain else ""
    (project / "vividly.publish.yaml").write_text(
        """schema: 1
targets:
  pages:
    provider: github-pages
    expected_url: https://example.invalid/presentation/
"""
        + domain,
        encoding="utf-8",
    )
    _run(["git", "init", "--bare", "--quiet", str(remote)])
    _run(["git", "init", "--quiet", "--initial-branch=main", str(project)])
    _git(project, "config", "user.name", "Vividly Tests")
    _git(project, "config", "user.email", "tests@example.invalid")
    _git(project, "remote", "add", "origin", str(remote))
    source_commit = _commit(project, "Create presentation")
    _git(project, "push", "--quiet", "--set-upstream", "origin", "main")
    return PublishingFixture(project=project, remote=remote, source_commit=source_commit)


def _checkout_snapshot(project: Path) -> tuple[str, str, str, str, str]:
    return (
        _git(project, "symbolic-ref", "--short", "HEAD").stdout.strip(),
        _git(project, "rev-parse", "HEAD").stdout.strip(),
        _git(project, "write-tree").stdout.strip(),
        _git(project, "status", "--porcelain=v1", "--untracked-files=all").stdout,
        _git(project, "worktree", "list", "--porcelain").stdout,
    )


def _publication_tip(fixture: PublishingFixture) -> str:
    return _bare_git(fixture.remote, "rev-parse", "refs/heads/gh-pages").stdout.strip()


def _extract_publication(remote: Path, destination: Path) -> None:
    result = subprocess.run(
        [
            "git",
            "--git-dir",
            str(remote),
            "archive",
            "--format=tar",
            "refs/heads/gh-pages",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        archive.extractall(destination, filter="data")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


def test_dry_run_materializes_initial_candidate_without_writing_git_objects_or_refs(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    before = _git(fixture.project, "count-objects", "-v").stdout

    result = publish_project(fixture.project, dry_run=True)

    assert result.operation == "dry-run-initial"
    assert result.publication_commit is None
    assert result.plan.expected_url == "https://example.invalid/presentation/"
    assert result.identity.runtime_integrity.startswith("sha256:")
    assert _git(fixture.project, "count-objects", "-v").stdout == before
    assert _bare_git(
        fixture.remote,
        "show-ref",
        "--verify",
        "--quiet",
        "refs/heads/gh-pages",
        check=False,
    ).returncode == 1


def test_cli_runs_publication_dry_run_and_reports_observation_boundary(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    output = io.StringIO()

    with (
        patch.object(
            sys,
            "argv",
            ["vividly", "publish", str(fixture.project), "--dry-run"],
        ),
        contextlib.redirect_stdout(output),
    ):
        main()

    report = output.getvalue()
    assert f"Project: {fixture.project}" in report
    assert f"Source revision: {fixture.source_commit}" in report
    assert "Publication branch: origin/gh-pages" in report
    assert "configure the repository to deploy `gh-pages` from `/` (root)" in report
    assert "Dry run: initial publication would be created" in report
    assert "no candidate Git objects or refs were written" in report


def test_publishes_root_then_linear_replacement_and_no_op(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, custom_domain=True)
    assert not (fixture.project / "pyproject.toml").exists()
    assert not (fixture.project / "src").exists()
    before = _checkout_snapshot(fixture.project)

    first = publish_project(fixture.project)

    assert first.operation == "published"
    assert first.publication_commit is not None
    assert _publication_tip(fixture) == first.publication_commit
    assert _bare_git(
        fixture.remote,
        "rev-list",
        "--parents",
        "-n",
        "1",
        first.publication_commit,
    ).stdout.split() == [first.publication_commit]
    assert _bare_git(
        fixture.remote,
        "show",
        f"{first.publication_commit}:.nojekyll",
    ).stdout == ""
    assert _bare_git(
        fixture.remote,
        "show",
        f"{first.publication_commit}:CNAME",
    ).stdout == "slides.example.com\n"
    metadata_text = _bare_git(
        fixture.remote,
        "show",
        f"{first.publication_commit}:vividly-publication.json",
    ).stdout
    metadata = json.loads(metadata_text)
    assert metadata["schema"] == 1
    assert metadata["runtime"]["integrity"] == first.identity.runtime_integrity
    assert metadata_text == json.dumps(
        metadata,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"
    message = _bare_git(
        fixture.remote,
        "show",
        "--no-patch",
        "--format=%B",
        first.publication_commit,
    ).stdout
    assert "Vividly-Publication: 1\n" in message
    assert f"Source-Revision: {fixture.source_commit}\n" in message
    assert f"Runtime-Integrity: {first.identity.runtime_integrity}\n" in message
    assert _checkout_snapshot(fixture.project) == before
    assert _git(
        fixture.project,
        "show-ref",
        "--verify",
        "--quiet",
        "refs/heads/gh-pages",
        check=False,
    ).returncode == 1

    slide = fixture.project / "site/slides/published.txt"
    slide.write_text("published content\n", encoding="utf-8")
    second_source = _commit(fixture.project, "Add published content")
    before_second = _checkout_snapshot(fixture.project)

    second = publish_project(fixture.project)

    assert second.operation == "published"
    assert second.publication_commit is not None
    assert _bare_git(
        fixture.remote,
        "rev-list",
        "--parents",
        "-n",
        "1",
        second.publication_commit,
    ).stdout.split() == [second.publication_commit, first.publication_commit]
    assert _bare_git(
        fixture.remote,
        "show",
        f"{second.publication_commit}:slides/published.txt",
    ).stdout == "published content\n"
    second_message = _bare_git(
        fixture.remote,
        "show",
        "--no-patch",
        "--format=%B",
        second.publication_commit,
    ).stdout
    assert f"Source-Revision: {second_source}\n" in second_message
    assert _checkout_snapshot(fixture.project) == before_second

    slide.unlink()
    _commit(fixture.project, "Remove published content")
    third = publish_project(fixture.project)

    assert third.operation == "published"
    assert third.publication_commit is not None
    assert _bare_git(
        fixture.remote,
        "cat-file",
        "-e",
        f"{third.publication_commit}:slides/published.txt",
        check=False,
    ).returncode != 0

    (fixture.project / "source-notes.txt").write_text(
        "source-only change\n",
        encoding="utf-8",
    )
    _commit(fixture.project, "Add source-only notes")
    no_change = publish_project(fixture.project)

    assert no_change.operation == "unchanged"
    assert no_change.publication_commit == third.publication_commit
    assert _publication_tip(fixture) == third.publication_commit


def test_dry_run_reports_changed_and_unchanged_existing_publication(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    published = publish_project(fixture.project)

    unchanged = publish_project(fixture.project, dry_run=True)

    assert unchanged.operation == "dry-run-unchanged"
    assert unchanged.publication_commit == published.publication_commit

    (fixture.project / "site/changed.txt").write_text("changed\n", encoding="utf-8")
    _commit(fixture.project, "Change site")

    changed = publish_project(fixture.project, dry_run=True)

    assert changed.operation == "dry-run-changed"
    assert changed.publication_commit is None
    assert _publication_tip(fixture) == published.publication_commit


def test_rejects_dirty_source_publication_owned_collision_and_unrecognized_history(
    tmp_path: Path,
) -> None:
    dirty = _fixture(tmp_path / "dirty")
    (dirty.project / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(PublicationError, match="untracked changes"):
        publish_project(dirty.project)

    collision = _fixture(tmp_path / "collision")
    (collision.project / "site/.nojekyll").write_text("author\n", encoding="utf-8")
    _commit(collision.project, "Occupy publication path")
    with pytest.raises(PublicationError, match="publication-owned path: /.nojekyll"):
        publish_project(collision.project)

    unrelated = _fixture(tmp_path / "unrelated")
    tree = _git(unrelated.project, "write-tree").stdout.strip()
    commit = _git(
        unrelated.project,
        "commit-tree",
        tree,
        input_text="Unrelated Pages history\n",
    ).stdout.strip()
    _git(
        unrelated.project,
        "push",
        "--quiet",
        "origin",
        f"{commit}:refs/heads/gh-pages",
    )
    with pytest.raises(PublicationError, match="not recognized as Vividly history"):
        publish_project(unrelated.project)


@pytest.mark.parametrize(
    "reserved",
    [".nojekyll", "CNAME", "vividly-publication.json"],
)
def test_rejects_every_publication_owned_author_path(
    tmp_path: Path,
    reserved: str,
) -> None:
    fixture = _fixture(tmp_path)
    (fixture.project / "site" / reserved).write_text("author\n", encoding="utf-8")
    _commit(fixture.project, f"Occupy {reserved}")

    with pytest.raises(PublicationError, match="publication-owned path"):
        publish_project(fixture.project)


def test_published_tree_serves_from_github_pages_project_subpath(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    publish_project(fixture.project)
    hosting_root = tmp_path / "hosting"
    publication_root = hosting_root / "presentation"
    _extract_publication(fixture.remote, publication_root)
    handler = functools.partial(_QuietHandler, directory=str(hosting_root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/presentation"
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            index = response.read().decode()
        assert 'href="vividly/css/base.css"' in index
        assert 'src="vividly/runtime/presentation.js"' in index
        assert 'catalog="./catalog.yaml"' in index
        for relative in (
            "catalog.yaml",
            "vividly/css/base.css",
            "vividly/runtime/presentation.js",
            "vividly-publication.json",
        ):
            with urllib.request.urlopen(f"{base}/{relative}", timeout=5) as response:
                assert response.status == 200
                assert response.read()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_vividly_source_repository_layout_publishes_with_repository_runtime(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "vividly"
    remote = tmp_path / "remote.git"
    shutil.copytree(REPOSITORY_ROOT / "site", repository / "site")
    shutil.copytree(
        REPOSITORY_ROOT / "src/vividly/resources/runtime",
        repository / "src/vividly/resources/runtime",
    )
    shutil.copytree(
        REPOSITORY_ROOT / "src/vividly/resources/reference",
        repository / "src/vividly/resources/reference",
    )
    shutil.copy2(REPOSITORY_ROOT / "vividly.yaml", repository / "vividly.yaml")
    shutil.copy2(
        REPOSITORY_ROOT / "vividly.publish.yaml",
        repository / "vividly.publish.yaml",
    )
    _run(["git", "init", "--bare", "--quiet", str(remote)])
    _run(["git", "init", "--quiet", "--initial-branch=main", str(repository)])
    _git(repository, "config", "user.name", "Vividly Tests")
    _git(repository, "config", "user.email", "tests@example.invalid")
    _git(repository, "remote", "add", "origin", str(remote))
    _commit(repository, "Create Vividly source fixture")
    _git(repository, "push", "--quiet", "--set-upstream", "origin", "main")

    result = publish_project(repository)

    assert result.operation == "published"
    assert result.publication_commit is not None
    paths = _bare_git(
        remote,
        "ls-tree",
        "-r",
        "--name-only",
        result.publication_commit,
    ).stdout.splitlines()
    assert "index.html" in paths
    assert "catalog.yaml" in paths
    assert "slides/home/slide.js" in paths
    assert "vividly/runtime/presentation.js" in paths
    assert ".nojekyll" in paths
    assert "vividly-publication.json" in paths
    assert not any(path.startswith("src/") for path in paths)


def test_reports_concurrent_initial_publication_as_a_race(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    push_commit = publication_module.push_commit

    def race(
        repository: publication_module.GitRepository,
        remote: str,
        branch: str,
        commit: str,
    ) -> None:
        tree = _git(fixture.project, "rev-parse", f"{commit}^{{tree}}").stdout.strip()
        competing = _git(
            fixture.project,
            "commit-tree",
            tree,
            input_text="Competing publication\n",
        ).stdout.strip()
        push_commit(repository, remote, branch, competing)
        push_commit(repository, remote, branch, commit)

    monkeypatch.setattr(publication_module, "push_commit", race)

    with pytest.raises(PublicationError, match="changed; rerun publication"):
        publish_project(fixture.project)
