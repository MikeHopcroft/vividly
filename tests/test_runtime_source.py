"""Tests for runtime resolution in docs/specs/runtime-composition.md."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vividly.runtime import RuntimeManifestError, load_runtime_manifest, packaged_runtime


def _write_bundle(root: Path) -> tuple[Path, Path]:
    runtime = root / "runtime"
    reference = root / "reference"
    (runtime / "vividly").mkdir(parents=True)
    reference.mkdir()
    (runtime / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (runtime / "vividly" / "version.txt").write_text("1.2.3\n", encoding="utf-8")
    (reference / "cli.md").write_text("# CLI\n", encoding="utf-8")

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "composition_api": 1,
        "files": {
            "index.html": digest(runtime / "index.html"),
            "vividly/version.txt": digest(runtime / "vividly" / "version.txt"),
        },
        "reference_files": {"cli.md": digest(reference / "cli.md")},
        "schema": 1,
        "version": "1.2.3",
    }
    (runtime / "vividly-runtime.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return runtime, reference


def test_loads_canonical_manifest_and_computes_identity(tmp_path: Path) -> None:
    runtime, _ = _write_bundle(tmp_path)
    manifest_path = runtime / "vividly-runtime.json"

    manifest = load_runtime_manifest(runtime)

    assert manifest.version == "1.2.3"
    assert manifest.composition_api == 1
    assert manifest.integrity == f"sha256:{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}"


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            b'{"schema":1,"schema":1,"version":"1","composition_api":1,'
            b'"files":{"index.html":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
            b'"reference_files":{}}\n',
            "duplicate key",
        ),
        (
            b'{"schema":1, "version":"1","composition_api":1,'
            b'"files":{"index.html":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
            b'"reference_files":{}}\n',
            "not canonical",
        ),
        (
            b'{"composition_api":2,"files":'
            b'{"index.html":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
            b'"reference_files":{},"schema":1,"version":"1"}\n',
            "unsupported composition API",
        ),
        (
            b'{"composition_api":1,"files":'
            b'{"../index.html":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
            b'"reference_files":{},"schema":1,"version":"1"}\n',
            "normalized relative paths",
        ),
        (
            b'{"composition_api":1,"files":'
            b'{"index.html":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            b'"vividly/~dev/events":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
            b'"reference_files":{},"schema":1,"version":"1"}\n',
            "reserved development namespace",
        ),
    ],
)
def test_rejects_invalid_runtime_manifests(
    tmp_path: Path,
    replacement: bytes,
    message: str,
) -> None:
    runtime, _ = _write_bundle(tmp_path)
    (runtime / "vividly-runtime.json").write_bytes(replacement)

    with pytest.raises(RuntimeManifestError, match=message):
        load_runtime_manifest(runtime)


def test_packaged_runtime_verifies_file_sets_and_content(tmp_path: Path) -> None:
    runtime, _ = _write_bundle(tmp_path)
    package_root = runtime.parent

    with (
        patch("vividly.runtime.resources.files", return_value=package_root),
        patch("vividly.runtime.version", return_value="9.8.7"),
        packaged_runtime(
            verify_runtime_contents=True,
            verify_reference_contents=True,
        ) as selected,
    ):
        assert selected.distribution_version == "9.8.7"
        assert selected.manifest.version == "1.2.3"

    (runtime / "index.html").write_text("changed\n", encoding="utf-8")
    with (
        patch("vividly.runtime.resources.files", return_value=package_root),
        pytest.raises(RuntimeManifestError, match="failed integrity check: index.html"),
        packaged_runtime(verify_runtime_contents=True),
    ):
        pass


def test_packaged_runtime_rejects_an_additional_deployed_file(tmp_path: Path) -> None:
    runtime, _ = _write_bundle(tmp_path)
    (runtime / "vividly" / "extra.js").write_text("export {};\n", encoding="utf-8")

    with (
        patch("vividly.runtime.resources.files", return_value=runtime.parent),
        pytest.raises(RuntimeManifestError, match="unexpected runtime file: vividly/extra.js"),
        packaged_runtime(),
    ):
        pass
