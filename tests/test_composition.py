"""Tests for the virtual-site model in docs/specs/runtime-composition.md."""

import argparse
import contextlib
import hashlib
import io
import json
import tempfile
from collections.abc import Generator, MutableMapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest

from vividly.cli import provision_command
from vividly.composition import CompositionError, compose_project
from vividly.runtime import RuntimeManifest, SelectedRuntime, packaged_runtime
from vividly.server import CompositionSession


def _write_author_tree(project_root: Path) -> Path:
    author = project_root / "site"
    (author / "slides").mkdir(parents=True)
    (author / "catalog.yaml").write_text(
        "version: 1\npresentations: []\n",
        encoding="utf-8",
    )
    (author / "slides" / "author.js").write_text("export {};\n", encoding="utf-8")
    return author


def _write_editable_runtime(project_root: Path, source: str = "repository") -> Path:
    runtime = project_root / "runtime"
    reference = project_root / "reference"
    (runtime / "vividly").mkdir(parents=True)
    reference.mkdir()
    (runtime / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (runtime / "vividly" / "app.js").write_text("export {};\n", encoding="utf-8")
    dependency_table = '{"dependencies":{},"schema":1}\n'
    (runtime / "vividly" / "dependencies.json").write_text(
        dependency_table,
        encoding="utf-8",
    )
    digest = "a" * 64
    manifest = {
        "composition_api": 1,
        "files": {
            "index.html": digest,
            "vividly/app.js": digest,
            "vividly/dependencies.json": hashlib.sha256(dependency_table.encode()).hexdigest(),
        },
        "reference_files": {},
        "schema": 1,
        "version": "1.2.3",
    }
    (runtime / "vividly-runtime.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if source == "repository":
        runtime_config = (
            "  source: repository\n"
            "  path: runtime\n"
            "  version: 1.2.3\n"
            f"  commit: {'a' * 40}\n"
        )
    else:
        runtime_config = (
            "  source: path\n"
            "  path: runtime\n"
            "  upstream_version: 1.2.3\n"
        )
    (project_root / "vividly.yaml").write_text(
        f"schema: 1\nruntime:\n{runtime_config}",
        encoding="utf-8",
    )
    return runtime


def test_composes_package_runtime_and_author_files(tmp_path: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))

    with compose_project(tmp_path) as composition:
        assert composition.files[PurePosixPath("/index.html")].owner == "runtime"
        assert composition.files[PurePosixPath("/vividly/runtime/presentation.js")].owner == (
            "runtime"
        )
        assert composition.files[PurePosixPath("/catalog.yaml")].owner == "author"
        assert composition.files[PurePosixPath("/slides/title-card/slide.js")].owner == "author"
        assert not isinstance(composition.files, MutableMapping)


@pytest.mark.parametrize("source", ["repository", "path"])
def test_composes_editable_runtime_files(tmp_path: Path, source: str) -> None:
    _write_author_tree(tmp_path)
    _write_editable_runtime(tmp_path, source)

    with compose_project(tmp_path) as composition:
        assert composition.runtime.source == source
        assert set(composition.files) == {
            PurePosixPath("/index.html"),
            PurePosixPath("/vividly/app.js"),
            PurePosixPath("/vividly/dependencies.json"),
            PurePosixPath("/catalog.yaml"),
            PurePosixPath("/slides/author.js"),
        }


@pytest.mark.parametrize("source", ["repository", "path"])
def test_composition_session_watches_editable_runtime(
    tmp_path: Path,
    source: str,
) -> None:
    author_root = _write_author_tree(tmp_path)
    runtime_root = _write_editable_runtime(tmp_path, source)

    with CompositionSession(tmp_path) as compositions:
        assert compositions.watch_roots() == (
            author_root.resolve(),
            runtime_root.resolve(),
        )


def test_composition_holds_selected_runtime_context_open(tmp_path: Path) -> None:
    _write_author_tree(tmp_path)
    _write_editable_runtime(tmp_path)
    manifest = RuntimeManifest(
        schema=1,
        version="1.2.3",
        composition_api=1,
        files={"index.html": "a" * 64},
        reference_files={},
        integrity=f"sha256:{'b' * 64}",
    )
    extracted_paths: list[Path] = []

    @contextmanager
    def temporary_runtime(
        project_root: Path,
        selected_config: object,
        *,
        verify_runtime_contents: bool = False,
    ) -> Generator[SelectedRuntime, None, None]:
        del project_root, selected_config, verify_runtime_contents
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary)
            (runtime_root / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
            (runtime_root / "vividly").mkdir()
            (runtime_root / "vividly" / "dependencies.json").write_text(
                '{"dependencies":{},"schema":1}\n',
                encoding="utf-8",
            )
            reference_root = runtime_root.parent / "reference"
            extracted_paths.append(runtime_root / "index.html")
            yield SelectedRuntime(
                source="package",
                runtime_root=runtime_root,
                reference_root=reference_root,
                manifest=manifest,
                distribution_version="1.0",
            )

    with (
        patch("vividly.composition.selected_runtime", temporary_runtime),
        compose_project(tmp_path) as composition,
    ):
        assert composition.files[PurePosixPath("/index.html")].source_path.is_file()

    assert len(extracted_paths) == 1
    assert not extracted_paths[0].exists()


def test_requires_author_catalog(tmp_path: Path) -> None:
    (tmp_path / "site").mkdir()
    _write_editable_runtime(tmp_path)

    with (
        pytest.raises(CompositionError, match="project catalog is not a regular file"),
        compose_project(tmp_path),
    ):
        pass


def test_rejects_invalid_catalog_dependency_mapping(tmp_path: Path) -> None:
    author = _write_author_tree(tmp_path)
    _write_editable_runtime(tmp_path)
    (author / "catalog.yaml").write_text(
        """
version: 1
dependencies:
  package:
    baseUrl: http://cdn.example.invalid/package/
    entry: main.js
presentations: []
""",
        encoding="utf-8",
    )

    with (
        pytest.raises(
            CompositionError,
            match="baseUrl` must be a clean absolute HTTPS URL",
        ),
        compose_project(tmp_path),
    ):
        pass


def test_rejects_catalog_dependency_that_conflicts_with_runtime(tmp_path: Path) -> None:
    with packaged_runtime() as runtime:
        expected_version = runtime.manifest.version
    with contextlib.redirect_stdout(io.StringIO()):
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))
    catalog = tmp_path / "site" / "catalog.yaml"
    catalog.write_text(
        """
version: 1
dependencies:
  marked:
    baseUrl: https://cdn.example.invalid/marked@99/
    entry: main.js
presentations: []
""",
        encoding="utf-8",
    )

    with (
        pytest.raises(CompositionError) as error,
        compose_project(tmp_path),
    ):
        pass

    assert str(error.value) == (
        'catalog dependency "marked" conflicts with dependency selected by '
        f"Vividly {expected_version}"
    )


def test_refresh_carries_runtime_dependency_changes_and_preserves_previous_on_error(
    tmp_path: Path,
) -> None:
    _write_author_tree(tmp_path)
    runtime = _write_editable_runtime(tmp_path)
    table_path = runtime / "vividly" / "dependencies.json"

    def write_table(base_url: str) -> None:
        record = {
            "baseUrl": base_url,
            "entry": "main.js",
            "license": "MIT",
            "loader": {"type": "module"},
            "projectUrl": "https://example.invalid/runtime-package",
            "sha256": "a" * 64,
            "version": "1.0.0",
        }
        table_path.write_text(
            json.dumps(
                {"dependencies": {"runtime-package": record}, "schema": 1},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    write_table("https://cdn.example.invalid/runtime-package@1/")
    with CompositionSession(tmp_path) as compositions:
        with compositions.read() as composition:
            assert (
                composition.dependencies["runtime-package"].base_url
                == "https://cdn.example.invalid/runtime-package@1/"
            )

        write_table("https://cdn.example.invalid/runtime-package@2/")
        compositions.refresh()
        with compositions.read() as composition:
            assert (
                composition.dependencies["runtime-package"].base_url
                == "https://cdn.example.invalid/runtime-package@2/"
            )

        table_path.write_text("not json\n", encoding="utf-8")
        with pytest.raises(CompositionError, match="runtime dependency table"):
            compositions.refresh()
        with compositions.read() as composition:
            assert (
                composition.dependencies["runtime-package"].base_url
                == "https://cdn.example.invalid/runtime-package@2/"
            )


@pytest.mark.parametrize("reserved", [Path("index.html"), Path("vividly")])
def test_rejects_author_runtime_namespace_collisions(
    tmp_path: Path,
    reserved: Path,
) -> None:
    author = _write_author_tree(tmp_path)
    _write_editable_runtime(tmp_path)
    occupied = author / reserved
    if reserved.suffix:
        occupied.write_text("author collision\n", encoding="utf-8")
    else:
        occupied.mkdir()

    with (
        pytest.raises(CompositionError, match="collides with runtime ownership"),
        compose_project(tmp_path),
    ):
        pass


def test_rejects_symbolic_links_in_author_tree(tmp_path: Path) -> None:
    author = _write_author_tree(tmp_path)
    _write_editable_runtime(tmp_path)
    outside = tmp_path / "outside.js"
    outside.write_text("outside\n", encoding="utf-8")
    (author / "slides" / "linked.js").symlink_to(outside)

    with pytest.raises(CompositionError, match="symbolic link"), compose_project(tmp_path):
        pass


def test_rejects_symbolic_links_in_editable_runtime(tmp_path: Path) -> None:
    _write_author_tree(tmp_path)
    runtime = _write_editable_runtime(tmp_path)
    outside = tmp_path / "outside.js"
    outside.write_text("outside\n", encoding="utf-8")
    (runtime / "vividly" / "linked.js").symlink_to(outside)

    with pytest.raises(CompositionError, match="symbolic link"), compose_project(tmp_path):
        pass


def test_rejects_undeployable_editable_runtime_files(tmp_path: Path) -> None:
    _write_author_tree(tmp_path)
    runtime = _write_editable_runtime(tmp_path)
    (runtime / "notes.txt").write_text("not deployed\n", encoding="utf-8")

    with (
        pytest.raises(CompositionError, match="has no deployed runtime URL"),
        compose_project(tmp_path),
    ):
        pass


def test_rejects_editable_runtime_development_namespace(tmp_path: Path) -> None:
    _write_author_tree(tmp_path)
    runtime = _write_editable_runtime(tmp_path)
    reserved = runtime / "vividly" / "~dev"
    reserved.mkdir()
    (reserved / "events").write_text("reserved\n", encoding="utf-8")

    with (
        pytest.raises(CompositionError, match="reserved development namespace"),
        compose_project(tmp_path),
    ):
        pass


def test_rejects_overlapping_author_and_runtime_roots(tmp_path: Path) -> None:
    author = _write_author_tree(tmp_path)
    runtime = author / "runtime"
    reference = author / "reference"
    (runtime / "vividly").mkdir(parents=True)
    reference.mkdir()
    (runtime / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    manifest = {
        "composition_api": 1,
        "files": {"index.html": "a" * 64},
        "reference_files": {},
        "schema": 1,
        "version": "1.2.3",
    }
    (runtime / "vividly-runtime.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "vividly.yaml").write_text(
        "schema: 1\n"
        "runtime:\n"
        "  source: path\n"
        "  path: site/runtime\n"
        "  upstream_version: 1.2.3\n",
        encoding="utf-8",
    )

    with pytest.raises(CompositionError, match="roots overlap"), compose_project(tmp_path):
        pass
