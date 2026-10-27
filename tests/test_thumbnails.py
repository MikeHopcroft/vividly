"""Tests for thumbnail generation specified by docs/specs/cli.md §10."""

import argparse
import hashlib
import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright
from runtime_site import install_test_runtime

from vividly.cli import main, provision_command
from vividly.dependencies import (
    DependencyCache,
    DependencyResource,
    DependencySelection,
)
from vividly.thumbnails import (
    MAX_THUMBNAIL_STEPS,
    ThumbnailError,
    generate_thumbnail,
    generate_thumbnails,
    load_thumbnail_index,
    select_thumbnail_step,
    thumbnail_relative_path,
)

REVISION = "0" * 64


@pytest.fixture
def presentation_root(tmp_path: Path) -> Path:
    with redirect_stdout(StringIO()):
        provision_command(argparse.Namespace(project_root=tmp_path, assume_yes=True))
    return tmp_path


@pytest.fixture
def multi_presentation_root(presentation_root: Path) -> Path:
    site_root = presentation_root / "site"
    (site_root / "catalog.yaml").write_text(
        """version: 1
presentations:
  - id: alpha
    title: Alpha
    manifest: ./presentations/alpha.yaml
  - id: beta
    title: Beta
    manifest: ./presentations/beta.yaml
""",
        encoding="utf-8",
    )
    module_root = site_root / "slides/shared-thumbnail"
    module_root.mkdir(parents=True)
    (module_root / "slide.js").write_text(
        """import { Slide } from '../../vividly/runtime/slide.js';

export default class SharedThumbnailSlide extends Slide {
  mount(root) {
    root.textContent = this.ctx.props.label;
    root.style.background = this.ctx.props.background;
    root.style.color = '#ffffff';
    root.style.fontSize = '160px';
  }
}
""",
        encoding="utf-8",
    )
    for presentation_id, label, background in (
        ("alpha", "ALPHA", "#a02c2c"),
        ("beta", "BETA", "#176b52"),
    ):
        (site_root / f"presentations/{presentation_id}.yaml").write_text(
            f"""id: {presentation_id}
title: {label.title()}
theme: ../vividly/themes/dark.css
nodes:
  - type: section
    id: shared
    title: Shared
    children:
      - type: slide
        id: card
        title: Shared Card
        module: ../slides/shared-thumbnail/slide.js
        props:
          label: {label}
          background: '{background}'
""",
            encoding="utf-8",
        )
    return presentation_root


@pytest.fixture
def chromium() -> None:
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("run 'vividly install-browser' before thumbnail tests")


def test_select_thumbnail_step_defaults_to_final_step() -> None:
    assert select_thumbnail_step(4, has_override=False, override=None) == 3


@pytest.mark.parametrize("override", [-1, True, 1.5, "1"])
def test_select_thumbnail_step_rejects_invalid_override(override: object) -> None:
    with pytest.raises(ThumbnailError, match="non-negative integer"):
        select_thumbnail_step(4, has_override=True, override=override)


def test_select_thumbnail_step_rejects_out_of_range_override() -> None:
    with pytest.raises(ThumbnailError, match="outside the slide's 0..3 range"):
        select_thumbnail_step(4, has_override=True, override=4)


def test_select_thumbnail_step_rejects_dynamic_override() -> None:
    with pytest.raises(ThumbnailError, match="dynamic slides"):
        select_thumbnail_step("dynamic", has_override=True, override=0)


def test_select_thumbnail_step_rejects_excessive_step_count() -> None:
    with pytest.raises(ThumbnailError, match="maximum supported"):
        select_thumbnail_step(MAX_THUMBNAIL_STEPS + 1, has_override=False, override=None)


def test_load_index_accepts_valid_version_three_sequence(tmp_path: Path) -> None:
    output_root = tmp_path / "thumbnails"
    output_root.mkdir()
    index = {
        "version": 3,
        "presentations": {
            "demo": {
                "opening/title": {
                    "canonicalStep": 1,
                    "steps": [
                        {
                            "step": 0,
                            "path": "demo/opening/title/step-0000.png",
                            "revision": REVISION,
                        },
                        {
                            "step": 1,
                            "path": "demo/opening/title/step-0001.png",
                            "revision": REVISION,
                        },
                    ],
                }
            }
        },
    }
    (output_root / "index.json").write_text(json.dumps(index), encoding="utf-8")

    assert load_thumbnail_index(output_root) == index


@pytest.mark.parametrize(
    "entry",
    [
        {
            "canonicalStep": 2,
            "steps": [
                {
                    "step": 0,
                    "path": "demo/opening/title/step-0000.png",
                    "revision": REVISION,
                }
            ],
        },
        {
            "canonicalStep": 0,
            "steps": [
                {
                    "step": 1,
                    "path": "demo/opening/title/step-0001.png",
                    "revision": REVISION,
                }
            ],
        },
        {
            "canonicalStep": 0,
            "steps": [
                {
                    "step": 0,
                    "path": "../title.png",
                    "revision": REVISION,
                }
            ],
        },
        {
            "canonicalStep": 0,
            "steps": [
                {
                    "step": 0,
                    "path": "demo/opening/title/step-0000.png",
                    "revision": "not-a-revision",
                }
            ],
        },
    ],
)
def test_load_index_rejects_invalid_version_three_entries(
    tmp_path: Path,
    entry: object,
) -> None:
    output_root = tmp_path / "thumbnails"
    output_root.mkdir()
    (output_root / "index.json").write_text(
        json.dumps(
            {
                "version": 3,
                "presentations": {"demo": {"opening/title": entry}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ThumbnailError, match="invalid thumbnail index"):
        load_thumbnail_index(output_root)


def test_load_index_rejects_version_two(tmp_path: Path) -> None:
    output_root = tmp_path / "thumbnails"
    output_root.mkdir()
    (output_root / "index.json").write_text(
        '{"version": 2, "presentations": {}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ThumbnailError, match="unsupported thumbnail index"):
        load_thumbnail_index(output_root)


def test_thumbnail_relative_path_includes_fixed_width_step() -> None:
    assert thumbnail_relative_path("demo", "opening/title", 7) == Path(
        "demo/opening/title/step-0007.png"
    )


def test_thumbnails_command_captures_complete_sequence(
    chromium: None,
    presentation_root: Path,
) -> None:
    del chromium
    output = StringIO()
    with (
        patch.object(
            sys,
            "argv",
            [
                "vividly",
                "thumbnails",
                str(presentation_root),
                "--presentation",
                "vividly",
                "--slide",
                "welcome",
            ],
        ),
        redirect_stdout(output),
    ):
        main()

    output_root = presentation_root / "site/thumbnails"
    lines = output.getvalue().splitlines()
    assert lines[:3] == [
        "Capturing slide 1/1: vividly:welcome, step 0 (1 of 3)",
        "Capturing slide 1/1: vividly:welcome, step 1 (2 of 3)",
        "Capturing slide 1/1: vividly:welcome, step 2 (3 of 3)",
    ]
    assert lines[-1] == "Generated 3 thumbnails."
    for step in range(3):
        with Image.open(output_root / f"vividly/welcome/step-{step:04d}.png") as image:
            assert image.size == (320, 180)

    output = StringIO()
    with (
        patch.object(
            sys,
            "argv",
            [
                "vividly",
                "thumbnails",
                str(presentation_root),
                "--presentation",
                "vividly",
                "--slide",
                "welcome",
                "--missing",
            ],
        ),
        redirect_stdout(output),
    ):
        main()

    assert output.getvalue().splitlines() == ["Generated 0 thumbnails."]


def test_generate_thumbnail_honors_manifest_step_override(
    chromium: None,
    presentation_root: Path,
) -> None:
    del chromium
    manifest_path = presentation_root / "site/presentations/vividly.yaml"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        manifest.replace(
            "    title: Welcome\n",
            "    title: Welcome\n    thumbnail:\n      step: 1\n",
        ),
        encoding="utf-8",
    )

    result = generate_thumbnail(presentation_root, "vividly", "welcome")

    assert result.step == 1
    assert result.canonical
    assert result.path.name == "step-0001.png"


def test_generate_thumbnail_captures_dynamic_initial_state(
    chromium: None,
    presentation_root: Path,
) -> None:
    del chromium
    module_path = presentation_root / "site/slides/title-card/slide.js"
    module = module_path.read_text(encoding="utf-8")
    module_path.write_text(module.replace("steps: 3", "steps: 'dynamic'"), encoding="utf-8")

    result = generate_thumbnail(presentation_root, "vividly", "welcome")
    index = json.loads(
        (presentation_root / "site/thumbnails/index.json").read_text(encoding="utf-8")
    )

    assert result.step == 0
    assert result.canonical
    assert index["presentations"]["vividly"]["welcome"]["steps"] == [
        {
            "step": 0,
            "path": "vividly/welcome/step-0000.png",
            "revision": hashlib.sha256(result.path.read_bytes()).hexdigest(),
        }
    ]


def test_generate_thumbnail_populates_shared_dependency_cache(
    chromium: None,
    presentation_root: Path,
    tmp_path: Path,
) -> None:
    del chromium
    site_root = presentation_root / "site"
    catalog_path = site_root / "catalog.yaml"
    catalog_path.write_text(
        catalog_path.read_text(encoding="utf-8").replace(
            "presentations:\n",
            """dependencies:
  graphics:
    baseUrl: https://cdn.example.invalid/graphics@1.2.3/
    entry: entry.js
presentations:
""",
        ),
        encoding="utf-8",
    )
    (site_root / "slides/title-card/slide.js").write_text(
        """import { Slide } from '../../vividly/runtime/slide.js';

export default class DependencyThumbnailSlide extends Slide {
  async preload() {
    this.module = await this.ctx.dependency('graphics').import();
  }

  mount(root) {
    root.textContent = this.module.message;
  }
}
""",
        encoding="utf-8",
    )
    requests: list[str] = []
    builtins = install_test_runtime(presentation_root)

    def acquire(source_url: str) -> DependencyResource:
        requests.append(source_url)
        if source_url in builtins:
            content, content_type = builtins[source_url]
            return DependencyResource(
                content=content,
                content_type=content_type,
            )
        return DependencyResource(
            content=b"export const message = 'cached thumbnail dependency';",
            content_type="text/javascript",
        )

    cache_root = tmp_path / "dependency-cache"
    cache = DependencyCache(cache_root, acquirer=acquire)
    with (
        patch(
            "vividly.thumbnails.default_dependency_cache_root",
            return_value=cache_root,
        ),
        patch("vividly.thumbnails.DependencyCache", return_value=cache),
    ):
        result = generate_thumbnail(presentation_root, "vividly", "welcome")

    selection = DependencySelection(
        key="graphics",
        base_url="https://cdn.example.invalid/graphics@1.2.3/",
        entry=PurePosixPath("entry.js"),
    )
    cached = DependencyCache(cache_root, cache_only=True).get(
        selection,
        selection.entry,
    )

    assert result.path.is_file()
    assert set(requests) == {
        *builtins,
        "https://cdn.example.invalid/graphics@1.2.3/entry.js",
    }
    assert b"cached thumbnail dependency" in cached.content


def test_generate_thumbnail_rejects_unknown_address(
    chromium: None,
    presentation_root: Path,
) -> None:
    del chromium
    with pytest.raises(ThumbnailError, match="unknown slide address"):
        generate_thumbnail(presentation_root, "vividly", "missing/slide")


def test_full_generation_is_idempotent_and_reconciles_rename(
    chromium: None,
    presentation_root: Path,
) -> None:
    del chromium
    output_root = presentation_root / "site/thumbnails"
    custom_file = output_root / "notes.txt"
    custom_file.parent.mkdir(parents=True, exist_ok=True)
    custom_file.write_text("author-owned\n", encoding="utf-8")

    results = generate_thumbnails(presentation_root)
    index_path = output_root / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    canonical_addresses = [result.address for result in results if result.canonical]

    assert canonical_addresses == ["welcome"]
    assert list(index["presentations"]["vividly"]) == sorted(canonical_addresses)
    assert index["version"] == 3
    assert all(result.path.is_file() for result in results)
    for entry in index["presentations"]["vividly"].values():
        assert [step["step"] for step in entry["steps"]] == list(range(len(entry["steps"])))
        assert entry["canonicalStep"] < len(entry["steps"])
        for step in entry["steps"]:
            path = output_root / step["path"]
            assert step["revision"] == hashlib.sha256(path.read_bytes()).hexdigest()

    first_snapshot = _thumbnail_snapshot(output_root)
    generate_thumbnails(presentation_root)
    assert _thumbnail_snapshot(output_root) == first_snapshot

    manifest_path = presentation_root / "site/presentations/vividly.yaml"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        manifest.replace("    id: welcome\n", "    id: greeting\n", 1),
        encoding="utf-8",
    )
    generate_thumbnails(
        presentation_root,
        presentation_id="vividly",
        addresses=["greeting"],
    )

    renamed_index = json.loads(index_path.read_text(encoding="utf-8"))["presentations"]["vividly"]
    assert "welcome" not in renamed_index
    assert "greeting" in renamed_index
    assert not (output_root / "vividly/welcome").exists()
    assert (output_root / "vividly/greeting/step-0002.png").is_file()
    assert custom_file.read_text(encoding="utf-8") == "author-owned\n"


def test_failed_capture_leaves_existing_outputs_unchanged(
    chromium: None,
    presentation_root: Path,
) -> None:
    del chromium
    output_root = presentation_root / "site/thumbnails"
    generate_thumbnail(presentation_root, "vividly", "welcome")
    before = _thumbnail_snapshot(output_root)

    manifest_path = presentation_root / "site/presentations/vividly.yaml"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        manifest.replace(
            "    title: Welcome\n",
            "    title: Welcome\n    thumbnail:\n      step: 99\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ThumbnailError, match="outside the slide's 0..2 range"):
        generate_thumbnail(presentation_root, "vividly", "welcome")

    assert _thumbnail_snapshot(output_root) == before


def test_generation_refuses_to_overwrite_an_unindexed_file(
    chromium: None,
    presentation_root: Path,
) -> None:
    del chromium
    output_root = presentation_root / "site/thumbnails"
    thumbnail_path = output_root / "vividly/welcome/step-0000.png"
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.write_bytes(b"author-owned")

    with pytest.raises(ThumbnailError, match="refusing to overwrite unindexed file"):
        generate_thumbnail(presentation_root, "vividly", "welcome")

    assert thumbnail_path.read_bytes() == b"author-owned"
    assert not (output_root / "index.json").exists()


def test_slide_selection_requires_one_presentation(presentation_root: Path) -> None:
    with pytest.raises(ThumbnailError, match="--slide requires --presentation ID"):
        generate_thumbnails(presentation_root, addresses=["welcome"])


def test_project_generation_keys_equal_addresses_by_presentation(
    chromium: None,
    multi_presentation_root: Path,
) -> None:
    del chromium
    output_root = multi_presentation_root / "site/thumbnails"
    assert not output_root.exists()

    results = generate_thumbnails(multi_presentation_root)
    index = json.loads((output_root / "index.json").read_text(encoding="utf-8"))

    assert [(result.presentation_id, result.address) for result in results] == [
        ("alpha", "shared/card"),
        ("beta", "shared/card"),
    ]
    assert index == {
        "version": 3,
        "presentations": {
            "alpha": {
                "shared/card": {
                    "canonicalStep": 0,
                    "steps": [
                        {
                            "step": 0,
                            "path": "alpha/shared/card/step-0000.png",
                            "revision": hashlib.sha256(
                                (output_root / "alpha/shared/card/step-0000.png").read_bytes()
                            ).hexdigest(),
                        }
                    ],
                }
            },
            "beta": {
                "shared/card": {
                    "canonicalStep": 0,
                    "steps": [
                        {
                            "step": 0,
                            "path": "beta/shared/card/step-0000.png",
                            "revision": hashlib.sha256(
                                (output_root / "beta/shared/card/step-0000.png").read_bytes()
                            ).hexdigest(),
                        }
                    ],
                }
            },
        },
    }
    assert (output_root / "alpha/shared/card/step-0000.png").read_bytes() != (
        output_root / "beta/shared/card/step-0000.png"
    ).read_bytes()


def test_selective_generation_preserves_unselected_presentation(
    chromium: None,
    multi_presentation_root: Path,
) -> None:
    del chromium
    generate_thumbnails(multi_presentation_root)
    output_root = multi_presentation_root / "site/thumbnails"
    beta_path = output_root / "beta/shared/card/step-0000.png"
    beta_before = (beta_path.read_bytes(), beta_path.stat().st_ino)

    generate_thumbnails(multi_presentation_root, presentation_id="alpha")

    index = json.loads((output_root / "index.json").read_text(encoding="utf-8"))
    assert "beta" in index["presentations"]
    assert (beta_path.read_bytes(), beta_path.stat().st_ino) == beta_before


def test_missing_generation_skips_complete_slides_and_repairs_incomplete_sequence(
    chromium: None,
    presentation_root: Path,
) -> None:
    del chromium
    initial_results = generate_thumbnails(presentation_root, missing_only=True)
    output_root = presentation_root / "site/thumbnails"

    assert generate_thumbnails(presentation_root, missing_only=True) == ()

    missing_path = output_root / "vividly/welcome/step-0001.png"
    missing_path.unlink()

    repaired_results = generate_thumbnails(presentation_root, missing_only=True)

    assert [result.step for result in repaired_results] == [0, 1, 2]
    assert all(result.path.is_file() for result in repaired_results)
    assert [result.path for result in repaired_results] == [
        result.path for result in initial_results
    ]


def test_missing_generation_intersects_explicit_selection(
    chromium: None,
    multi_presentation_root: Path,
) -> None:
    del chromium
    generate_thumbnails(multi_presentation_root)
    output_root = multi_presentation_root / "site/thumbnails"
    alpha_path = output_root / "alpha/shared/card/step-0000.png"
    beta_path = output_root / "beta/shared/card/step-0000.png"
    alpha_path.unlink()
    beta_path.unlink()

    results = generate_thumbnails(
        multi_presentation_root,
        presentation_id="alpha",
        addresses=["shared/card"],
        missing_only=True,
    )

    assert [(result.presentation_id, result.address) for result in results] == [
        ("alpha", "shared/card")
    ]
    assert alpha_path.is_file()
    assert not beta_path.exists()


def test_regeneration_removes_trailing_steps(
    chromium: None,
    presentation_root: Path,
) -> None:
    del chromium
    output_root = presentation_root / "site/thumbnails"
    generate_thumbnail(presentation_root, "vividly", "welcome")
    removed_path = output_root / "vividly/welcome/step-0002.png"
    assert removed_path.is_file()

    module_path = presentation_root / "site/slides/title-card/slide.js"
    module = module_path.read_text(encoding="utf-8")
    module_path.write_text(module.replace("steps: 3", "steps: 2"), encoding="utf-8")

    generate_thumbnail(presentation_root, "vividly", "welcome")

    index = json.loads((output_root / "index.json").read_text(encoding="utf-8"))
    entry = index["presentations"]["vividly"]["welcome"]
    assert [step["step"] for step in entry["steps"]] == [0, 1]
    assert entry["canonicalStep"] == 1
    assert not removed_path.exists()


def test_unknown_presentation_and_manifest_failure_do_not_mutate_outputs(
    chromium: None,
    multi_presentation_root: Path,
) -> None:
    del chromium
    generate_thumbnails(multi_presentation_root)
    output_root = multi_presentation_root / "site/thumbnails"
    before = _thumbnail_snapshot(output_root)

    with pytest.raises(ThumbnailError, match="unknown presentation ID: missing"):
        generate_thumbnails(multi_presentation_root, presentation_id="missing")
    assert _thumbnail_snapshot(output_root) == before

    beta_manifest = multi_presentation_root / "site/presentations/beta.yaml"
    beta_manifest.write_text("not: [valid", encoding="utf-8")
    with pytest.raises(ThumbnailError, match="could not render presentation"):
        generate_thumbnails(multi_presentation_root)
    assert _thumbnail_snapshot(output_root) == before


def test_project_generation_removes_presentations_deleted_from_catalog(
    chromium: None,
    multi_presentation_root: Path,
) -> None:
    del chromium
    generate_thumbnails(multi_presentation_root)
    site_root = multi_presentation_root / "site"
    catalog_path = site_root / "catalog.yaml"
    catalog = catalog_path.read_text(encoding="utf-8")
    catalog_path.write_text(catalog[: catalog.index("  - id: beta\n")], encoding="utf-8")

    generate_thumbnails(multi_presentation_root)

    output_root = site_root / "thumbnails"
    index = json.loads((output_root / "index.json").read_text(encoding="utf-8"))
    assert list(index["presentations"]) == ["alpha"]
    assert not (output_root / "beta").exists()


def _thumbnail_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_ino)
        for path in root.rglob("*")
        if path.is_file()
    }
