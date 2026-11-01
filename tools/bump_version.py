"""Prepare matching package and runtime versions without resolving dependencies."""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import cast

import yaml

from tools.check_uv_lock import LockfileError, validate
from tools.release import VERSION_PATTERN

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("src/vividly/resources/runtime")
TOML_VERSION = r"""(?m)^([ \t]*version[ \t]*=[ \t]*["'])([^"'\r\n]+)(["'])"""
YAML_VERSION = r"(?m)^([ \t]+version:[ \t]*)([^ \t\r\n#]+)"


class VersionError(ValueError):
    """Release preparation could not safely complete."""


def replace_version(content: str, pattern: str, old: str, new: str, label: str) -> str:
    matches = list(re.finditer(pattern, content))
    if len(matches) != 1 or matches[0].group(2) != old:
        raise VersionError(f"{label}: expected exactly one version field matching {old}")
    start, end = matches[0].span(2)
    return content[:start] + new + content[end:]


def bump_version(root: Path, version: str) -> None:
    """Validate all inputs, update version fields, and regenerate the runtime manifest."""
    if VERSION_PATTERN.fullmatch(version) is None:
        raise VersionError("version must be an ordinary 0.x.y release")
    paths = [
        Path("pyproject.toml"),
        Path("vividly.yaml"),
        Path("uv.lock"),
        RUNTIME / "vividly/version.txt",
        RUNTIME / "vividly-runtime.json",
    ]
    for path in paths:
        if (root / path).is_symlink() or not (root / path).is_file():
            raise VersionError(f"{path}: expected a regular, non-symbolic-link file")
    originals = {path: (root / path).read_bytes() for path in paths}
    contents = {path: content.decode("utf-8") for path, content in originals.items()}
    project = tomllib.loads(contents[paths[0]])
    metadata: object = project.get("project")
    if not isinstance(metadata, dict):
        raise VersionError("pyproject.toml: expected a project table")
    old = cast(dict[str, object], metadata).get("version")
    if not isinstance(old, str) or VERSION_PATTERN.fullmatch(old) is None:
        raise VersionError("pyproject.toml: expected an ordinary 0.x.y project version")
    if tuple(map(int, version.split("."))) < tuple(map(int, old.split("."))):
        raise VersionError(f"version must not go backwards from {old}")
    selector: object = yaml.safe_load(contents[paths[1]])
    if not isinstance(selector, dict):
        raise VersionError("vividly.yaml: expected a mapping")
    runtime = cast(dict[str, object], selector).get("runtime")
    manifest: object = json.loads(contents[paths[4]])
    if (
        not isinstance(runtime, dict)
        or cast(dict[str, object], runtime).get("version") != old
        or contents[paths[3]].strip() != old
        or not isinstance(manifest, dict)
        or cast(dict[str, object], manifest).get("version") != old
    ):
        raise VersionError("package, runtime text, manifest, and selector versions must agree")

    validate(contents[paths[2]])
    lock = tomllib.loads(contents[paths[2]])
    packages = [
        package
        for package in lock["package"]
        if package.get("name") == "vividly" and package.get("source") == {"editable": "."}
    ]
    if len(packages) != 1 or packages[0].get("version") != old:
        raise VersionError(
            "uv.lock: expected one root editable vividly package matching the version"
        )
    blocks = re.split(r"(?m)(?=^\[\[package\]\][ \t]*\r?$)", contents[paths[2]])
    for index, block in enumerate(blocks):
        if re.search(r"""(?m)^name[ \t]*=[ \t]*["']vividly["'][ \t]*(?:#.*)?\r?$""", block):
            blocks[index] = replace_version(block, TOML_VERSION, old, version, "uv.lock")
    updated_lock = "".join(blocks)
    expected_lock = tomllib.loads(contents[paths[2]])
    for package in expected_lock["package"]:
        if package.get("name") == "vividly" and package.get("source") == {"editable": "."}:
            package["version"] = version
    if tomllib.loads(updated_lock) != expected_lock:
        raise VersionError("uv.lock: could not isolate the root package version")

    updates = {
        paths[0]: replace_version(contents[paths[0]], TOML_VERSION, old, version, "pyproject.toml"),
        paths[1]: replace_version(contents[paths[1]], YAML_VERSION, old, version, "vividly.yaml"),
        paths[2]: updated_lock,
        paths[3]: contents[paths[3]].replace(old, version, 1),
    }
    try:
        for path, content in updates.items():
            (root / path).write_bytes(content.encode("utf-8"))
        subprocess.run(
            [sys.executable, str(root / "tools/build_runtime_manifest.py")],
            cwd=root,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        for path, content in originals.items():
            (root / path).write_bytes(content)
        raise
    print(f"Prepared version {version} (previously {old}).")
    print("Updated package, runtime selector, root lock entry, runtime text, and manifest.")
    print("No dependencies resolved, commits created, or releases dispatched.")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="target 0.x.y version, for example 0.0.4")
    parsed = parser.parse_args(arguments)
    try:
        bump_version(ROOT, cast(str, parsed.version))
    except (
        VersionError,
        LockfileError,
        OSError,
        UnicodeError,
        tomllib.TOMLDecodeError,
        yaml.YAMLError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as error:
        message = str(error)
        if isinstance(
            error, (UnicodeError, tomllib.TOMLDecodeError, yaml.YAMLError, json.JSONDecodeError)
        ):
            message = f"invalid input encoding or document syntax ({type(error).__name__})"
        print(f"bump-version: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
