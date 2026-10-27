"""Tests for the distribution contract described in README.md."""

import hashlib
import json
import re
from importlib.resources import as_file, files
from pathlib import Path

from vividly.cli import main


def test_cli_main_is_callable() -> None:
    assert callable(main)


def test_packaged_resources_have_separate_source_roots() -> None:
    starter_project = files("vividly.resources").joinpath("starter-project")
    runtime = files("vividly.resources").joinpath("runtime")
    reference = files("vividly.resources").joinpath("reference")
    documentation = files("vividly.resources").joinpath("documentation-presentation")

    starter_paths = (
        ".gitignore",
        ".github/copilot-instructions.md",
        ".github/instructions/managed-runtime.instructions.md",
        ".github/instructions/vividly.instructions.md",
        ".github/skills/vividly-presentations/SKILL.md",
        "site/catalog.yaml",
        "site/presentations/vividly.yaml",
        "site/slides/title-card/slide.html",
        "site/slides/title-card/slide.css",
        "site/slides/title-card/slide.js",
        "site/slides/title-card/assets/hero.svg",
    )
    with as_file(starter_project) as starter_root:
        actual_starter_paths = {
            path.relative_to(starter_root).as_posix()
            for path in starter_root.rglob("*")
            if path.is_file()
        }
    assert actual_starter_paths == set(starter_paths)

    for relative_path in starter_paths:
        assert starter_project.joinpath(relative_path).is_file(), relative_path

    runtime_paths = (
        "index.html",
        "vividly/css/controls.css",
        "vividly/runtime/controls/annotated-markdown.js",
        "vividly/runtime/controls/code.js",
        "vividly/runtime/controls/image.js",
        "vividly/runtime/controls/markdown.js",
        "vividly/runtime/controls/thumbnail.js",
        "vividly/runtime/config.js",
        "vividly/runtime/dependencies.js",
        "vividly/runtime/presentation.js",
        "vividly/dependencies.json",
        "vividly/assets/logo.svg",
        "vividly/slides/annotated-markdown.js",
        "vividly/slides/image.js",
        "vividly/slides/markdown.js",
        "vividly/slides/markdown.css",
        "vividly/slides/logo-animation.js",
        "vividly/slides/section-overview.js",
        "vividly/slides/section-overview.css",
    )
    for relative_path in runtime_paths:
        assert runtime.joinpath(relative_path).is_file(), relative_path

    for name in (
        "agentic-bootstrap.md",
        "agentic.md",
        "authoring.md",
        "cli.md",
        "controls.md",
        "dependencies.md",
        "keyboard.md",
        "slides.md",
    ):
        assert reference.joinpath(name).is_file(), name

    assert not documentation.is_dir()

    index = runtime.joinpath("index.html").read_text(encoding="utf-8")
    assert 'catalog="./catalog.yaml"' in index
    assert runtime.joinpath("vividly/runtime/config.js").read_text(encoding="utf-8") == (
        'export const PUBLIC_DOCUMENTATION_URL = "https://mikehopcroft.github.io/vividly/";\n'
    )
    starter_slide = starter_project.joinpath(
        "site/slides/title-card/slide.html"
    ).read_text(encoding="utf-8")
    assert 'href="https://mikehopcroft.github.io/vividly/"' in starter_slide
    assert 'target="_blank"' in starter_slide
    assert 'rel="noopener noreferrer"' in starter_slide
    assert not starter_project.joinpath("site/index.html").is_file()
    assert not starter_project.joinpath("site/vividly").is_dir()
    assert not starter_project.joinpath("site/thumbnails").is_dir()
    assert not starter_project.joinpath("site/slides/presentation.yaml").is_file()
    assert not runtime.joinpath("vividly/vendor").is_dir()


def test_runtime_manifest_matches_packaged_resources() -> None:
    resource_root = files("vividly.resources")
    with (
        as_file(resource_root.joinpath("runtime")) as runtime,
        as_file(resource_root.joinpath("reference")) as reference,
    ):
        manifest_resource = runtime / "vividly-runtime.json"
        manifest_bytes = manifest_resource.read_bytes()
        manifest = json.loads(manifest_bytes)

        assert manifest_bytes == (
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode()
        assert manifest["schema"] == 1
        assert manifest["composition_api"] == 1
        assert manifest["version"] == (runtime / "vividly/version.txt").read_text().strip()

        for root, field in ((runtime, "files"), (reference, "reference_files")):
            expected = {
                path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(root.rglob("*"), key=lambda candidate: str(candidate))
                if path.is_file() and path.name != "vividly-runtime.json"
            }
            assert manifest[field] == expected


def test_current_guidance_uses_catalog_project_vocabulary() -> None:
    repository_root = Path(__file__).parents[1]
    relative_paths = (
        "README.md",
        "src/vividly/resources/starter-project/.github/copilot-instructions.md",
        "src/vividly/resources/starter-project/.github/instructions/managed-runtime.instructions.md",
        "src/vividly/resources/starter-project/.github/instructions/vividly.instructions.md",
        "src/vividly/resources/starter-project/.github/skills/vividly-presentations/SKILL.md",
        "src/vividly/resources/reference/agentic.md",
        "src/vividly/resources/reference/authoring.md",
        "src/vividly/resources/reference/cli.md",
        "src/vividly/resources/reference/controls.md",
        "src/vividly/resources/reference/dependencies.md",
        "src/vividly/resources/reference/publishing.md",
        "src/vividly/resources/reference/slides.md",
        "src/vividly/resources/reference/keyboard.md",
    )
    documents = {
        relative: (repository_root / relative).read_text(encoding="utf-8")
        for relative in relative_paths
    }
    combined = "\n".join(documents.values())

    for relative, document in documents.items():
        assert "site/slides/presentation.yaml" not in document, relative
        assert re.search(r"vividly install(?![-a-z])", document) is None, relative
        assert re.search(r"(?m)^\s*#/[^~\s][^/\s]*/(?:\d+)?\s*$", document) is None, relative

    for required in (
        "site/catalog.yaml",
        "site/presentations/",
        "vividly provision",
        "vividly reference",
        ".vividly/reference/",
        "presentation-local",
        "slide instance",
        "--presentation",
    ):
        assert required in combined, required