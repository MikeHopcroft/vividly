"""Version preparation for the matching-version contract in publishing.md section 18.1."""

import hashlib
import json
import shutil
import subprocess
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tools import bump_version
from tools.check_uv_lock import LockfileError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "vividly"\nversion = "0.0.3" # keep comment\n'
        'description = "Unreleased edits"\n',
        encoding="utf-8",
    )
    (tmp_path / "vividly.yaml").write_text(
        "schema: 1\nruntime:\n  source: repository\n  version: 0.0.3 # keep comment\n"
        "  commit: unchanged\n",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        'version = 1\nrevision = 5\n\n[[package]]\nname = "example"\nversion = "0.0.3"\n'
        'source = { registry = "https://pypi.org/simple" }\n\n'
        '[[package]]\nname = "vividly"\nversion = "0.0.3"\nsource = { editable = "." }\n'
        "[package.metadata]\nrequires-dist = []\n",
        encoding="utf-8",
    )
    runtime = tmp_path / bump_version.RUNTIME
    (runtime / "vividly").mkdir(parents=True)
    (runtime / "vividly/version.txt").write_text("0.0.3\n", encoding="utf-8")
    (runtime / "vividly-runtime.json").write_text('{"version":"0.0.3"}\n', encoding="utf-8")
    reference = runtime.parent / "reference"
    reference.mkdir()
    (reference / "example.md").write_text("Unreleased reference edits\n", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    shutil.copy2(ROOT / "tools/build_runtime_manifest.py", tmp_path / "tools")
    return tmp_path


def snapshot(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_updates_all_versions_and_regenerates_hashes_without_resolving(repository: Path) -> None:
    before = snapshot(repository)
    bump_version.bump_version(repository, "0.0.4")
    project = (repository / "pyproject.toml").read_text()
    assert project == before[Path("pyproject.toml")].decode().replace(
        'version = "0.0.3"', 'version = "0.0.4"'
    )
    selector = (repository / "vividly.yaml").read_text()
    assert selector == before[Path("vividly.yaml")].decode().replace(
        "version: 0.0.3", "version: 0.0.4"
    )
    assert yaml.safe_load(selector)["runtime"]["version"] == "0.0.4"
    lock = (repository / "uv.lock").read_text()
    assert lock == before[Path("uv.lock")].decode().replace(
        'name = "vividly"\nversion = "0.0.3"', 'name = "vividly"\nversion = "0.0.4"'
    )
    assert tomllib.loads(lock)["package"][0]["version"] == "0.0.3"
    runtime = repository / bump_version.RUNTIME
    assert (runtime / "vividly/version.txt").read_bytes() == b"0.0.4\n"
    manifest = json.loads((runtime / "vividly-runtime.json").read_text())
    assert manifest["version"] == "0.0.4"
    assert manifest["files"]["vividly/version.txt"] == hashlib.sha256(b"0.0.4\n").hexdigest()
    reference = b"Unreleased reference edits\n"
    assert manifest["reference_files"]["example.md"] == hashlib.sha256(reference).hexdigest()
    assert "vividly-runtime.json" not in manifest["files"]
    after = snapshot(repository)
    bump_version.bump_version(repository, "0.0.4")
    assert snapshot(repository) == after


@pytest.mark.parametrize("version", ["0.0.2", "1.0.0", "0.0.04", "0.0.4rc1", "0.0.4\n"])
def test_invalid_or_decreasing_version_does_not_write(repository: Path, version: str) -> None:
    before = snapshot(repository)
    with pytest.raises(bump_version.VersionError):
        bump_version.bump_version(repository, version)
    assert snapshot(repository) == before


@pytest.mark.parametrize(
    "relative",
    [
        "vividly.yaml",
        "src/vividly/resources/runtime/vividly/version.txt",
        "src/vividly/resources/runtime/vividly-runtime.json",
        "uv.lock",
    ],
)
def test_mismatched_versions_do_not_write(repository: Path, relative: str) -> None:
    path = repository / relative
    path.write_text(path.read_text().replace("0.0.3", "0.0.2"))
    before = snapshot(repository)
    with pytest.raises(bump_version.VersionError):
        bump_version.bump_version(repository, "0.0.4")
    assert snapshot(repository) == before


def test_private_lockfile_does_not_write_or_report_private_urls(repository: Path) -> None:
    path = repository / "uv.lock"
    path.write_text(path.read_text().replace("pypi.org", "private.example.invalid"))
    before = snapshot(repository)
    with pytest.raises(LockfileError) as error:
        bump_version.bump_version(repository, "0.0.4")
    assert "private.example.invalid" not in str(error.value)
    assert snapshot(repository) == before


@pytest.mark.parametrize(
    ("relative", "content"),
    [
        ("pyproject.toml", 'project = "not a table"\n'),
        ("vividly.yaml", "[]\n"),
        ("uv.lock", "[[invalid\n"),
        ("src/vividly/resources/runtime/vividly-runtime.json", "{invalid\n"),
    ],
)
def test_cli_rejects_malformed_documents_without_writes(
    repository: Path, monkeypatch: pytest.MonkeyPatch, relative: str, content: str
) -> None:
    (repository / relative).write_text(content)
    before = snapshot(repository)
    monkeypatch.setattr(bump_version, "ROOT", repository)
    assert bump_version.main(["0.0.4"]) == 1
    assert snapshot(repository) == before


def test_manifest_failure_restores_preexisting_file_contents(repository: Path) -> None:
    before = snapshot(repository)
    with (
        patch.object(
            bump_version.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, ["manifest-generator"]),
        ),
        pytest.raises(subprocess.CalledProcessError),
    ):
        bump_version.bump_version(repository, "0.0.4")
    assert snapshot(repository) == before


def test_cli_reports_errors(
    repository: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(bump_version, "ROOT", repository)
    assert bump_version.main(["invalid"]) == 1
    assert "ordinary 0.x.y" in capsys.readouterr().err
    assert bump_version.main(["0.0.4"]) == 0
    assert "Prepared version 0.0.4" in capsys.readouterr().out
