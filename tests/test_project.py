"""Tests for the project configuration contract in docs/specs/runtime-composition.md."""

import re
from pathlib import Path

import pytest

from vividly.project import (
    PackageRuntime,
    PathRuntime,
    ProjectConfigError,
    RepositoryRuntime,
    load_project_config,
)
from vividly.runtime import reference_files, selected_runtime


def _write_config(project_root: Path, content: str) -> None:
    (project_root / "vividly.yaml").write_text(content, encoding="utf-8")


def test_loads_package_runtime(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
schema: 1
runtime:
  source: package
  distribution_version: 0.0.r1
  version: 0.0.r2
  integrity: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
""".lstrip(),
    )

    config = load_project_config(tmp_path)

    assert isinstance(config.runtime, PackageRuntime)
    assert config.runtime.distribution_version == "0.0.r1"
    assert config.runtime.version == "0.0.r2"


def test_loads_repository_runtime(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
schema: 1
runtime:
  source: repository
  path: src/vividly/resources/runtime
  version: 0.0.r1
  commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
""".lstrip(),
    )

    config = load_project_config(tmp_path)

    assert isinstance(config.runtime, RepositoryRuntime)
    assert config.runtime.path.as_posix() == "src/vividly/resources/runtime"


def test_loads_path_runtime_without_commit(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
schema: 1
runtime:
  source: path
  path: runtime
  upstream_version: 0.0.r1
""".lstrip(),
    )

    config = load_project_config(tmp_path)

    assert isinstance(config.runtime, PathRuntime)
    assert config.runtime.upstream_commit is None


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "schema: 1\nschema: 1\nruntime: {}\n",
            "found duplicate key 'schema'",
        ),
        (
            "schema: 2\nruntime: {}\n",
            "`schema` must equal 1",
        ),
        (
            "schema: 1\nruntime:\n  source: package\n  version: 1\n",
            "`runtime` is missing `distribution_version`",
        ),
        (
            """
schema: 1
runtime:
  source: package
  distribution_version: 1.0.0
  version: 1.0.0
  integrity: SHA256:nope
""".lstrip(),
            "`runtime.integrity` must be `sha256:` plus 64 lowercase hex digits",
        ),
        (
            """
schema: 1
runtime:
  source: path
  path: ../runtime
  upstream_version: 1.0.0
""".lstrip(),
            "`runtime.path` must be a normalized project-relative path",
        ),
        (
            """
schema: 1
runtime:
  source: repository
  path: runtime
  version: 1.0.0
  commit: short
""".lstrip(),
            "`runtime.commit` must be a full lowercase hexadecimal commit ID",
        ),
        (
            """
schema: 1
runtime:
  source: package
  distribution_version: 1.0.0
  version: 1.0.0
  integrity: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  typo: true
""".lstrip(),
            "`runtime` contains unknown key `typo`",
        ),
    ],
)
def test_rejects_malformed_configuration(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    _write_config(tmp_path, content)

    with pytest.raises(ProjectConfigError, match=re.escape(message)):
        load_project_config(tmp_path)


def test_reports_legacy_marker_without_parsing_it(tmp_path: Path) -> None:
    (tmp_path / "vividly-baseline.json").write_text("not json", encoding="utf-8")

    with pytest.raises(ProjectConfigError, match="requires reprovisioning"):
        load_project_config(tmp_path)


def test_valid_config_takes_precedence_over_legacy_marker(tmp_path: Path) -> None:
    (tmp_path / "vividly-baseline.json").write_text("legacy", encoding="utf-8")
    _write_config(
        tmp_path,
        """
schema: 1
runtime:
  source: path
  path: runtime
  upstream_version: 1.0.0
""".lstrip(),
    )

    config = load_project_config(tmp_path)

    assert isinstance(config.runtime, PathRuntime)


def test_repository_configuration_resolves_checkout_runtime() -> None:
    repository_root = Path(__file__).parents[1]

    config = load_project_config(repository_root)

    assert isinstance(config.runtime, RepositoryRuntime)
    assert config.runtime.path.as_posix() == "src/vividly/resources/runtime"
    with selected_runtime(repository_root, config) as runtime:
        assert runtime.source == "repository"
        assert runtime.manifest.version == config.runtime.version
        assert runtime.reference_root == (
            repository_root / "src" / "vividly" / "resources" / "reference"
        )
        expected_root = repository_root / "src" / "vividly" / "resources" / "reference"
        assert set(reference_files(runtime.reference_root)) == {
            path.relative_to(expected_root).as_posix()
            for path in expected_root.rglob("*")
            if path.is_file()
        }
