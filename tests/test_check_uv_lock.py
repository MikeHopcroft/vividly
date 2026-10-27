"""Public-source and staged-commit behavior specified by docs/specs/precommit.md."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.check_uv_lock import LockfileError, validate

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = """\
version = 1
[[package]]
name = "example"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/example.tar.gz" }
wheels = [{ url = "https://files.pythonhosted.org/packages/example.whl" }]
[[package]]
name = "vividly"
source = { editable = "." }
"""
PRIVATE = PUBLIC.replace("https://pypi.org/simple", "https://packages.example.invalid/simple")


@pytest.mark.parametrize(
    "content",
    [
        PUBLIC,
        (ROOT / "uv.lock").read_text(encoding="utf-8"),
    ],
    ids=["synthetic", "current-lockfile"],
)
def test_public_sources_pass(content: str) -> None:
    validate(content)


@pytest.mark.parametrize(
    "content",
    [
        PRIVATE,
        PUBLIC.replace("files.pythonhosted.org", "packages.example.invalid"),
        PUBLIC.replace("https://files.pythonhosted.org", "http://files.pythonhosted.org"),
        PUBLIC.replace('registry = "https://pypi.org/simple"', 'git = "https://example.invalid/repo"'),
        PUBLIC.replace('editable = "."', 'editable = "../other"'),
        PUBLIC.replace('source = { registry = "https://pypi.org/simple" }', ""),
        "[[package",
        "",
    ],
)
def test_invalid_sources_fail(content: str) -> None:
    with pytest.raises(LockfileError):
        validate(content)


def test_diagnostics_do_not_expose_credentials() -> None:
    content = PUBLIC.replace("files.pythonhosted.org", "user:invented-secret@example.invalid")
    with pytest.raises(LockfileError) as failure:
        validate(content)
    assert "invented-secret" not in str(failure.value)
    assert "example.invalid" not in str(failure.value)


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    tools = tmp_path / "bin"
    tools.mkdir()
    git_executable = shutil.which("git")
    assert git_executable is not None
    (tools / "git").symlink_to(git_executable)
    monkeypatch.setenv("PATH", str(tools))
    template = tmp_path / "template"
    template.mkdir()
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "--quiet", "--initial-branch=main", f"--template={template}")
    git(root, "config", "user.name", "Lockfile Tests")
    git(root, "config", "user.email", "tests@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "core.hooksPath", ".githooks")
    for relative in (".githooks/pre-commit", "tools/check_uv_lock.py"):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    interpreter = root / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    assert git(root, "remote").stdout == ""
    return root


def git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=check,
    )


def stage(root: Path, content: str) -> None:
    (root / "uv.lock").write_text(content, encoding="utf-8")
    git(root, "add", "uv.lock")


def commit(root: Path) -> subprocess.CompletedProcess[str]:
    return git(root, "commit", "--quiet", "-m", "Test lockfile", check=False)


def test_public_initial_commit(repository: Path) -> None:
    stage(repository, PUBLIC)
    assert commit(repository).returncode == 0
    assert git(repository, "show", "HEAD:uv.lock").stdout == PUBLIC


def test_private_staged_version_fails_without_mutation(repository: Path) -> None:
    stage(repository, PUBLIC)
    assert commit(repository).returncode == 0
    head = git(repository, "rev-parse", "HEAD").stdout
    stage(repository, PRIVATE)
    (repository / "uv.lock").write_text(PUBLIC, encoding="utf-8")
    index = git(repository, "write-tree").stdout
    result = commit(repository)
    assert result.returncode != 0
    assert "expected public PyPI" in result.stderr
    assert git(repository, "rev-parse", "HEAD").stdout == head
    assert git(repository, "write-tree").stdout == index
    assert git(repository, "show", ":uv.lock").stdout == PRIVATE
    assert (repository / "uv.lock").read_text(encoding="utf-8") == PUBLIC


def test_public_staged_version_ignores_private_working_copy(repository: Path) -> None:
    stage(repository, PUBLIC)
    (repository / "uv.lock").write_text(PRIVATE, encoding="utf-8")
    assert commit(repository).returncode == 0
    assert git(repository, "show", "HEAD:uv.lock").stdout == PUBLIC
    assert (repository / "uv.lock").read_text(encoding="utf-8") == PRIVATE
    assert git(repository, "diff", "--cached", "--exit-code").returncode == 0


@pytest.mark.parametrize("rename", [False, True], ids=["delete", "rename"])
def test_lockfile_removal_fails(repository: Path, rename: bool) -> None:
    stage(repository, PUBLIC)
    assert commit(repository).returncode == 0
    head = git(repository, "rev-parse", "HEAD").stdout
    if rename:
        git(repository, "mv", "uv.lock", "other.lock")
    else:
        git(repository, "rm", "uv.lock")
    index = git(repository, "write-tree").stdout
    assert commit(repository).returncode != 0
    assert git(repository, "rev-parse", "HEAD").stdout == head
    assert git(repository, "write-tree").stdout == index


def test_unrelated_commit_does_not_invoke_validator(repository: Path) -> None:
    stage(repository, PUBLIC)
    assert commit(repository).returncode == 0
    (repository / "tools/check_uv_lock.py").write_text("raise RuntimeError('must not run')\n")
    (repository / "note.txt").write_text("Unrelated change\n")
    git(repository, "add", "note.txt")
    assert commit(repository).returncode == 0


def install_gitleaks(repository: Path, exit_status: int) -> Path:
    arguments = repository.parent / "gitleaks-arguments"
    gitleaks = repository.parent / "bin/gitleaks"
    gitleaks.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{arguments}"\nexit {exit_status}\n')
    gitleaks.chmod(0o755)
    return arguments


def test_secret_scan_checks_staged_changes(repository: Path) -> None:
    arguments = install_gitleaks(repository, 0)
    (repository / "note.txt").write_text("Unrelated change\n")
    git(repository, "add", "note.txt")
    result = commit(repository)
    assert result.returncode == 0
    assert "Secret scan skipped" not in result.stderr
    recorded = arguments.read_text().splitlines()
    assert recorded[:3] == ["git", "--pre-commit", "--staged"]
    assert "--redact" in recorded


def test_secret_scan_failure_blocks_commit_without_mutation(repository: Path) -> None:
    stage(repository, PUBLIC)
    assert commit(repository).returncode == 0
    head = git(repository, "rev-parse", "HEAD").stdout
    install_gitleaks(repository, 1)
    (repository / "note.txt").write_text("Possible secret\n")
    git(repository, "add", "note.txt")
    index = git(repository, "write-tree").stdout
    result = commit(repository)
    assert result.returncode != 0
    assert "Secret scan failed" in result.stderr
    assert git(repository, "rev-parse", "HEAD").stdout == head
    assert git(repository, "write-tree").stdout == index


def test_missing_gitleaks_warns_and_commits(repository: Path) -> None:
    (repository / "note.txt").write_text("Unrelated change\n")
    git(repository, "add", "note.txt")
    result = commit(repository)
    assert result.returncode == 0
    assert "Secret scan skipped: gitleaks is not installed" in result.stderr
