"""Typed, argument-safe Git operations for publication."""

import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_CREDENTIAL_URL = re.compile(r"(https?://)[^/\s@]+@")
_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


class PublicationGitError(RuntimeError):
    """A required Git operation failed safely."""


class PublicationRaceError(PublicationGitError):
    """The remote publication branch changed after preflight."""


@dataclass(frozen=True)
class GitRepository:
    """Validated source-repository identity needed for publication."""

    root: Path
    git_directory: Path
    source_branch: str
    source_commit: str
    author_name: str
    author_email: str


@dataclass(frozen=True)
class GitTreeEntry:
    """One regular file in a Git tree."""

    mode: str
    object_id: str


def _sanitize(text: str) -> str:
    return _CREDENTIAL_URL.sub(r"\1<redacted>@", text)


def _run(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    environment: Mapping[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    process_environment = os.environ.copy()
    process_environment["LC_ALL"] = "C"
    if environment is not None:
        process_environment.update(environment)
    try:
        result = subprocess.run(
            arguments,
            cwd=cwd,
            env=process_environment,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise PublicationGitError(f"could not start Git: {error}") from error
    if check and result.returncode != 0:
        detail = _sanitize(result.stderr.strip() or result.stdout.strip())
        if detail:
            raise PublicationGitError(f"Git command failed: {detail}")
        raise PublicationGitError(f"Git command failed with exit code {result.returncode}")
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


def _required_output(repository: Path, *arguments: str, label: str) -> str:
    value = _git(repository, *arguments, check=False)
    if value.returncode != 0 or not value.stdout.strip():
        raise PublicationGitError(f"{label} is not configured")
    return value.stdout.strip()


def _git_path(repository: Path, name: str) -> Path:
    value = _git(
        repository,
        "rev-parse",
        "--path-format=absolute",
        "--git-path",
        name,
    ).stdout.strip()
    return Path(value)


def _assert_repository_idle(repository: Path) -> None:
    operations = (
        ("MERGE_HEAD", "merge"),
        ("rebase-merge", "rebase"),
        ("rebase-apply", "rebase"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("REVERT_HEAD", "revert"),
    )
    for git_path, operation in operations:
        if _git_path(repository, git_path).exists():
            raise PublicationGitError(f"repository has a {operation} in progress")


def inspect_repository(project_root: Path) -> GitRepository:
    """Validate and describe the containing source repository."""
    try:
        canonical_project = project_root.expanduser().resolve(strict=True)
    except OSError as error:
        raise PublicationGitError(f"cannot resolve project root {project_root}: {error}") from error
    if not canonical_project.is_dir():
        raise PublicationGitError(f"project root is not a directory: {canonical_project}")

    root_result = _git(
        canonical_project,
        "rev-parse",
        "--show-toplevel",
        check=False,
    )
    if root_result.returncode != 0 or not root_result.stdout.strip():
        raise PublicationGitError(
            f"project is not inside a Git working repository: {canonical_project}"
        )
    root = Path(root_result.stdout.strip()).resolve()
    bare = _git(root, "rev-parse", "--is-bare-repository").stdout.strip()
    if bare != "false":
        raise PublicationGitError(f"publication requires a non-bare Git repository: {root}")

    branch_result = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if branch_result.returncode != 0 or not branch_result.stdout.strip():
        raise PublicationGitError("publication requires an attached source branch")
    source_branch = branch_result.stdout.strip()
    source_commit = _git(root, "rev-parse", "--verify", "HEAD^{commit}", check=False)
    if source_commit.returncode != 0 or _OBJECT_ID.fullmatch(source_commit.stdout.strip()) is None:
        raise PublicationGitError("publication requires an existing source commit")

    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if status:
        raise PublicationGitError("repository has staged, unstaged, or untracked changes")
    _assert_repository_idle(root)

    author_name = _required_output(root, "config", "--get", "user.name", label="Git user.name")
    author_email = _required_output(root, "config", "--get", "user.email", label="Git user.email")
    git_directory = Path(
        _git(root, "rev-parse", "--absolute-git-dir").stdout.strip()
    ).resolve()
    return GitRepository(
        root=root,
        git_directory=git_directory,
        source_branch=source_branch,
        source_commit=source_commit.stdout.strip(),
        author_name=author_name,
        author_email=author_email,
    )


def validate_target(repository: GitRepository, remote: str, branch: str) -> None:
    """Validate the configured remote and publication branch."""
    if branch == repository.source_branch:
        raise PublicationGitError(
            f"publication branch must differ from source branch `{repository.source_branch}`"
        )
    branch_result = _git(
        repository.root,
        "check-ref-format",
        "--branch",
        branch,
        check=False,
    )
    if branch_result.returncode != 0:
        raise PublicationGitError(f"invalid publication branch name: {branch}")
    urls = _git(
        repository.root,
        "remote",
        "get-url",
        "--push",
        "--all",
        remote,
        check=False,
    )
    push_urls = [line for line in urls.stdout.splitlines() if line]
    if urls.returncode != 0 or not push_urls:
        raise PublicationGitError(f"Git remote is not configured: {remote}")
    if len(push_urls) != 1:
        raise PublicationGitError(
            f"Git remote `{remote}` has multiple push destinations; exactly one is required"
        )


def _advertised_tip(repository: GitRepository, remote: str, branch: str) -> str | None:
    result = _git(
        repository.root,
        "ls-remote",
        "--exit-code",
        "--heads",
        remote,
        f"refs/heads/{branch}",
        check=False,
    )
    if result.returncode == 2 and not result.stdout:
        return None
    if result.returncode != 0:
        detail = _sanitize(result.stderr.strip() or result.stdout.strip())
        raise PublicationGitError(
            f"could not inspect publication branch `{remote}/{branch}`"
            + (f": {detail}" if detail else "")
        )
    fields = result.stdout.split()
    if len(fields) != 2 or _OBJECT_ID.fullmatch(fields[0]) is None:
        raise PublicationGitError(
            f"Git remote returned an invalid tip for `{remote}/{branch}`"
        )
    return fields[0]


def fetch_remote_tip(repository: GitRepository, remote: str, branch: str) -> str | None:
    """Fetch and return one stable remote branch tip without updating a local ref."""
    for _ in range(3):
        advertised = _advertised_tip(repository, remote, branch)
        if advertised is None:
            return None
        _git(
            repository.root,
            "fetch",
            "--quiet",
            "--no-tags",
            "--no-write-fetch-head",
            remote,
            f"refs/heads/{branch}",
        )
        current = _advertised_tip(repository, remote, branch)
        if current == advertised:
            available = _git(
                repository.root,
                "cat-file",
                "-e",
                f"{advertised}^{{commit}}",
                check=False,
            )
            if available.returncode == 0:
                return advertised
    raise PublicationGitError(
        f"publication branch `{remote}/{branch}` changed repeatedly during preflight"
    )


def commit_parents(repository: GitRepository, commit: str) -> tuple[str, ...]:
    """Return one commit's direct parents."""
    line = _git(repository.root, "rev-list", "--parents", "-n", "1", commit).stdout.split()
    if not line or line[0] != commit:
        raise PublicationGitError(f"cannot inspect publication commit: {commit}")
    return tuple(line[1:])


def commit_message(repository: GitRepository, commit: str) -> str:
    """Return one commit's complete message."""
    return _git(repository.root, "show", "--no-patch", "--format=%B", commit).stdout


def show_file(repository: GitRepository, commit: str, path: str) -> bytes:
    """Return one regular file from a commit."""
    result = _run(
        ["git", "-C", str(repository.root), "show", f"{commit}:{path}"],
        check=False,
    )
    if result.returncode != 0:
        raise PublicationGitError(f"publication commit is missing `{path}`")
    return result.stdout.encode()


def tree_entry(
    repository: GitRepository,
    commit: str,
    path: str,
) -> GitTreeEntry | None:
    """Return one path's tree entry, when present."""
    output = _git(repository.root, "ls-tree", commit, "--", path).stdout
    if not output:
        return None
    metadata, actual_path = output.rstrip("\n").split("\t", 1)
    mode, object_type, object_id = metadata.split()
    if actual_path != path or object_type != "blob":
        return None
    return GitTreeEntry(mode=mode, object_id=object_id)


def commit_tree_id(repository: GitRepository, commit: str) -> str:
    """Return one commit's root tree ID."""
    return _git(repository.root, "rev-parse", f"{commit}^{{tree}}").stdout.strip()


def tree_entries(repository: GitRepository, commit: str) -> dict[str, GitTreeEntry]:
    """Return every regular file in one commit tree."""
    entries: dict[str, GitTreeEntry] = {}
    output = _git(repository.root, "ls-tree", "-r", commit).stdout
    for line in output.splitlines():
        metadata, path = line.split("\t", 1)
        mode, object_type, object_id = metadata.split()
        if object_type != "blob":
            raise PublicationGitError(f"publication tree contains unsupported entry: {path}")
        entries[path] = GitTreeEntry(mode=mode, object_id=object_id)
    return entries


def candidate_entries(repository: GitRepository, candidate: Path) -> dict[str, GitTreeEntry]:
    """Compute candidate Git identities without writing objects."""
    entries: dict[str, GitTreeEntry] = {}
    for path in sorted(candidate.rglob("*")):
        if path.is_symlink():
            raise PublicationGitError(f"publication candidate contains a symbolic link: {path}")
        if path.is_file():
            object_id = _git(
                repository.root,
                "hash-object",
                "--no-filters",
                str(path),
            ).stdout.strip()
            entries[path.relative_to(candidate).as_posix()] = GitTreeEntry(
                mode="100644",
                object_id=object_id,
            )
    return entries


def write_tree(repository: GitRepository, candidate: Path, index: Path) -> str:
    """Write a complete tree from a candidate through an isolated index."""
    environment = {"GIT_INDEX_FILE": str(index)}
    base = [
        "git",
        "--git-dir",
        str(repository.git_directory),
    ]
    _run([*base, "read-tree", "--empty"], environment=environment)
    for path in sorted(candidate.rglob("*")):
        if path.is_symlink():
            raise PublicationGitError(f"publication candidate contains a symbolic link: {path}")
        if not path.is_file():
            continue
        object_id = _run(
            [*base, "hash-object", "-w", "--no-filters", str(path)],
        ).stdout.strip()
        relative = path.relative_to(candidate).as_posix()
        _run(
            [*base, "update-index", "--add", "--cacheinfo", f"100644,{object_id},{relative}"],
            environment=environment,
        )
    return _run([*base, "write-tree"], environment=environment).stdout.strip()


def create_commit(
    repository: GitRepository,
    tree: str,
    message: str,
    parent: str | None,
) -> str:
    """Create one publication commit without updating a ref."""
    arguments = ["commit-tree", tree]
    if parent is not None:
        arguments.extend(["-p", parent])
    return _git(repository.root, *arguments, input_text=message).stdout.strip()


def push_commit(
    repository: GitRepository,
    remote: str,
    branch: str,
    commit: str,
) -> None:
    """Push one publication commit through a normal non-force update."""
    result = _git(
        repository.root,
        "push",
        "--porcelain",
        remote,
        f"{commit}:refs/heads/{branch}",
        check=False,
    )
    if result.returncode == 0:
        return
    detail = _sanitize(
        "\n".join(
            part
            for part in (result.stdout.strip(), result.stderr.strip())
            if part
        )
    )
    lowered = detail.lower()
    if "non-fast-forward" in lowered or "[rejected]" in lowered or "fetch first" in lowered:
        raise PublicationRaceError(
            f"publication branch `{remote}/{branch}` changed; rerun publication"
        )
    raise PublicationGitError(
        f"could not push publication to `{remote}/{branch}`"
        + (f": {detail}" if detail else "")
    )
