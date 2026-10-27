"""Integration proofs for the Git mechanics in the publishing specification."""

import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepositoryFixture:
    source: Path
    remote: Path
    source_commit: str


@dataclass(frozen=True)
class CheckoutSnapshot:
    branch: str
    commit: str
    index_tree: str
    status: str
    local_branches: str
    worktrees: str
    source_bytes: bytes


def _run(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    environment: Mapping[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    process_environment = os.environ.copy()
    if environment is not None:
        process_environment.update(environment)
    result = subprocess.run(
        arguments,
        cwd=cwd,
        env=process_environment,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _git(
    repository: Path,
    *arguments: str,
    environment: Mapping[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run(
        ["git", "-C", str(repository), *arguments],
        environment=environment,
        input_text=input_text,
        check=check,
    )


def _bare_git(
    repository: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run(["git", "--git-dir", str(repository), *arguments], check=check)


def _create_repositories(root: Path) -> RepositoryFixture:
    remote = root / "remote.git"
    source = root / "presentation"
    _run(["git", "init", "--bare", "--quiet", str(remote)])
    _run(["git", "init", "--quiet", "--initial-branch=main", str(source)])
    _git(source, "config", "user.name", "Vividly Tests")
    _git(source, "config", "user.email", "tests@example.invalid")
    (source / "source.txt").write_text("committed presentation source\n", encoding="utf-8")
    _git(source, "add", "source.txt")
    _git(source, "commit", "--quiet", "-m", "Create presentation")
    _git(source, "remote", "add", "origin", str(remote))
    _git(source, "push", "--quiet", "--set-upstream", "origin", "main")
    source_commit = _git(source, "rev-parse", "HEAD").stdout.strip()
    return RepositoryFixture(source=source, remote=remote, source_commit=source_commit)


def _write_candidate(root: Path, files: Mapping[str, bytes]) -> Path:
    root.mkdir()
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return root


def _isolated_environment(index: Path) -> dict[str, str]:
    return {"GIT_INDEX_FILE": str(index)}


def _write_tree(source: Path, candidate: Path, index: Path) -> str:
    environment = _isolated_environment(index)
    git_directory = source / ".git"
    base = ["git", "--git-dir", str(git_directory), "--work-tree", str(candidate)]
    _run([*base, "read-tree", "--empty"], environment=environment)
    _run([*base, "add", "--all", "--", "."], environment=environment)
    return _run([*base, "write-tree"], environment=environment).stdout.strip()


def _commit_tree(source: Path, tree: str, message: str, parent: str | None = None) -> str:
    arguments = ["commit-tree", tree]
    if parent is not None:
        arguments.extend(["-p", parent])
    return _git(source, *arguments, input_text=message).stdout.strip()


def _publication_message(source_commit: str, runtime_integrity: str) -> str:
    return (
        f"Publish site from source revision {source_commit[:12]}\n\n"
        "Vividly-Publication: 1\n"
        f"Source-Revision: {source_commit}\n"
        "Vividly-Distribution: 0.0.test\n"
        "Framework-Version: 0.0.test\n"
        f"Runtime-Integrity: {runtime_integrity}\n"
        "Target: pages\n"
        "Provider: github-pages\n"
    )


def _snapshot(repository: Path) -> CheckoutSnapshot:
    return CheckoutSnapshot(
        branch=_git(repository, "symbolic-ref", "--short", "HEAD").stdout.strip(),
        commit=_git(repository, "rev-parse", "HEAD").stdout.strip(),
        index_tree=_git(repository, "write-tree").stdout.strip(),
        status=_git(
            repository,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).stdout,
        local_branches=_git(
            repository,
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/heads",
        ).stdout,
        worktrees=_git(repository, "worktree", "list", "--porcelain").stdout,
        source_bytes=(repository / "source.txt").read_bytes(),
    )


def _tree_entries(repository: Path, revision: str) -> dict[str, tuple[str, str]]:
    output = _bare_git(repository, "ls-tree", "-r", revision).stdout
    entries: dict[str, tuple[str, str]] = {}
    for line in output.splitlines():
        metadata, path = line.split("\t", 1)
        mode, object_type, object_id = metadata.split()
        assert object_type == "blob"
        entries[path] = (mode, object_id)
    return entries


def _expected_entries(source: Path, candidate: Path) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    for path in sorted(candidate.rglob("*")):
        if path.is_file():
            object_id = _git(source, "hash-object", str(path)).stdout.strip()
            entries[path.relative_to(candidate).as_posix()] = ("100644", object_id)
    return entries


def _push_publication(source: Path, commit: str) -> subprocess.CompletedProcess[str]:
    return _git(
        source,
        "push",
        "--quiet",
        "origin",
        f"{commit}:refs/heads/gh-pages",
        check=False,
    )


def test_isolated_index_creates_root_then_linear_complete_publications(
    tmp_path: Path,
) -> None:
    repositories = _create_repositories(tmp_path)
    before = _snapshot(repositories.source)
    publication_metadata = (
        json.dumps(
            {
                "runtime": {
                    "framework_version": "0.0.test",
                    "integrity": f"sha256:{'1' * 64}",
                },
                "schema": 1,
                "vividly": {"distribution_version": "0.0.test"},
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()
    first_candidate = _write_candidate(
        tmp_path / "candidate-1",
        {
            ".nojekyll": b"",
            "index.html": b"<main>first</main>\n",
            "slides/old.js": b"export const old = true;\n",
            "vividly-publication.json": publication_metadata,
            "vividly/runtime.js": b"export const runtime = 1;\n",
        },
    )
    first_index = tmp_path / "publication-1.idx"
    first_tree = _write_tree(repositories.source, first_candidate, first_index)
    first_commit = _commit_tree(
        repositories.source,
        first_tree,
        _publication_message(repositories.source_commit, f"sha256:{'1' * 64}"),
    )

    first_push = _push_publication(repositories.source, first_commit)
    assert first_push.returncode == 0, first_push.stdout + first_push.stderr
    assert _bare_git(
        repositories.remote,
        "rev-list",
        "--parents",
        "-n",
        "1",
        "refs/heads/gh-pages",
    ).stdout.split() == [first_commit]
    raw_first_commit = _bare_git(repositories.remote, "cat-file", "-p", first_commit).stdout
    assert "\nparent " not in f"\n{raw_first_commit}"
    published_tree = _bare_git(
        repositories.remote,
        "rev-parse",
        f"{first_commit}^{{tree}}",
    ).stdout.strip()
    assert published_tree == first_tree
    assert _tree_entries(repositories.remote, first_commit) == _expected_entries(
        repositories.source,
        first_candidate,
    )
    ancestry = _run(
        [
            "git",
            "--git-dir",
            str(repositories.remote),
            "merge-base",
            "--is-ancestor",
            "refs/heads/main",
            "refs/heads/gh-pages",
        ],
        check=False,
    )
    assert ancestry.returncode == 1

    second_candidate = _write_candidate(
        tmp_path / "candidate-2",
        {
            ".nojekyll": b"",
            "index.html": b"<main>second</main>\n",
            "slides/current.js": b"export const current = true;\n",
            "vividly-publication.json": publication_metadata,
            "vividly/runtime.js": b"export const runtime = 1;\n",
        },
    )
    second_index = tmp_path / "publication-2.idx"
    second_tree = _write_tree(repositories.source, second_candidate, second_index)
    second_commit = _commit_tree(
        repositories.source,
        second_tree,
        _publication_message(repositories.source_commit, f"sha256:{'1' * 64}"),
        parent=first_commit,
    )

    second_push = _push_publication(repositories.source, second_commit)
    assert second_push.returncode == 0, second_push.stdout + second_push.stderr
    assert _bare_git(
        repositories.remote,
        "rev-list",
        "--parents",
        "-n",
        "1",
        "refs/heads/gh-pages",
    ).stdout.split() == [second_commit, first_commit]
    second_entries = _tree_entries(repositories.remote, second_commit)
    assert second_entries == _expected_entries(repositories.source, second_candidate)
    assert "slides/old.js" not in second_entries
    assert "slides/old.js" in _tree_entries(repositories.remote, first_commit)
    assert second_entries["vividly/runtime.js"] == _tree_entries(
        repositories.remote,
        first_commit,
    )["vividly/runtime.js"]

    no_change_index = tmp_path / "publication-no-change.idx"
    no_change_tree = _write_tree(repositories.source, second_candidate, no_change_index)
    assert no_change_tree == second_tree

    for index in (first_index, second_index, no_change_index):
        index.unlink()
        assert not index.exists()
        assert not index.with_name(f"{index.name}.lock").exists()

    assert _snapshot(repositories.source) == before
    assert _git(
        repositories.source,
        "show-ref",
        "--verify",
        "--quiet",
        "refs/heads/gh-pages",
        check=False,
    ).returncode == 1


def test_non_force_push_rejects_initial_and_later_publication_races(tmp_path: Path) -> None:
    repositories = _create_repositories(tmp_path)
    first_candidate = _write_candidate(tmp_path / "candidate-a", {"index.html": b"a\n"})
    competing_candidate = _write_candidate(tmp_path / "candidate-b", {"index.html": b"b\n"})
    first_tree = _write_tree(repositories.source, first_candidate, tmp_path / "a.idx")
    competing_tree = _write_tree(
        repositories.source,
        competing_candidate,
        tmp_path / "b.idx",
    )
    first = _commit_tree(repositories.source, first_tree, "first publication\n")
    competing_initial = _commit_tree(
        repositories.source,
        competing_tree,
        "competing initial publication\n",
    )

    assert _push_publication(repositories.source, first).returncode == 0
    rejected_initial = _push_publication(repositories.source, competing_initial)
    assert rejected_initial.returncode != 0
    assert _bare_git(
        repositories.remote,
        "rev-parse",
        "refs/heads/gh-pages",
    ).stdout.strip() == first

    second = _commit_tree(
        repositories.source,
        competing_tree,
        "second publication\n",
        parent=first,
    )
    competing_second_tree = _write_tree(
        repositories.source,
        _write_candidate(tmp_path / "candidate-c", {"index.html": b"c\n"}),
        tmp_path / "c.idx",
    )
    competing_second = _commit_tree(
        repositories.source,
        competing_second_tree,
        "competing second publication\n",
        parent=first,
    )
    assert _push_publication(repositories.source, second).returncode == 0
    rejected_later = _push_publication(repositories.source, competing_second)
    assert rejected_later.returncode != 0
    assert _bare_git(
        repositories.remote,
        "rev-parse",
        "refs/heads/gh-pages",
    ).stdout.strip() == second


def test_publication_markers_distinguish_vividly_and_unrelated_branch_tips(
    tmp_path: Path,
) -> None:
    repositories = _create_repositories(tmp_path)
    metadata = (
        json.dumps(
            {
                "runtime": {
                    "framework_version": "0.0.test",
                    "integrity": f"sha256:{'2' * 64}",
                },
                "schema": 1,
                "vividly": {"distribution_version": "0.0.test"},
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()
    candidate = _write_candidate(
        tmp_path / "recognized",
        {
            "index.html": b"recognized\n",
            "vividly-publication.json": metadata,
        },
    )
    tree = _write_tree(repositories.source, candidate, tmp_path / "recognized.idx")
    recognized = _commit_tree(
        repositories.source,
        tree,
        _publication_message(repositories.source_commit, f"sha256:{'2' * 64}"),
    )
    recognized_message = _git(
        repositories.source,
        "show",
        "--no-patch",
        "--format=%B",
        recognized,
    ).stdout
    recognized_metadata = _git(
        repositories.source,
        "show",
        f"{recognized}:vividly-publication.json",
    ).stdout
    assert "Vividly-Publication: 1\n" in recognized_message
    assert "Target: pages\n" in recognized_message
    assert json.loads(recognized_metadata)["schema"] == 1

    unrelated_candidate = _write_candidate(
        tmp_path / "unrelated",
        {"index.html": b"unrelated\n"},
    )
    unrelated_tree = _write_tree(
        repositories.source,
        unrelated_candidate,
        tmp_path / "unrelated.idx",
    )
    unrelated = _commit_tree(repositories.source, unrelated_tree, "Unrelated site\n")
    unrelated_message = _git(
        repositories.source,
        "show",
        "--no-patch",
        "--format=%B",
        unrelated,
    ).stdout
    missing_metadata = _git(
        repositories.source,
        "cat-file",
        "-e",
        f"{unrelated}:vividly-publication.json",
        check=False,
    )
    assert "Vividly-Publication:" not in unrelated_message
    assert missing_metadata.returncode != 0


def test_failed_isolated_index_operation_leaves_checkout_and_git_locks_unchanged(
    tmp_path: Path,
) -> None:
    repositories = _create_repositories(tmp_path)
    before = _snapshot(repositories.source)
    candidate = _write_candidate(tmp_path / "candidate", {"index.html": b"candidate\n"})
    index = tmp_path / "publication.idx"
    environment = _isolated_environment(index)
    git_directory = repositories.source / ".git"
    base = ["git", "--git-dir", str(git_directory), "--work-tree", str(candidate)]

    _run([*base, "read-tree", "--empty"], environment=environment)
    failed = _run(
        [*base, "add", "--", "missing-path"],
        environment=environment,
        check=False,
    )
    assert failed.returncode != 0
    assert not index.with_name(f"{index.name}.lock").exists()
    index.unlink()

    assert _snapshot(repositories.source) == before
    assert not tuple(git_directory.rglob("*.lock"))
    assert _bare_git(
        repositories.remote,
        "show-ref",
        "--verify",
        "--quiet",
        "refs/heads/gh-pages",
        check=False,
    ).returncode == 1
