"""Generate deterministic slide thumbnails with the Vividly browser runtime."""

import hashlib
import io
import json
import re
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypedDict, cast

from PIL import Image
from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from .browser import chromium_launch_error_message
from .composition import CompositionError, compose_project
from .dependencies import DependencyCache, default_dependency_cache_root
from .project import ProjectConfigError
from .runtime import RuntimeManifestError
from .server import serve_composition

CAPTURE_HEIGHT = 1080
CAPTURE_WIDTH = 1920
THUMBNAIL_HEIGHT = 180
THUMBNAIL_WIDTH = 320
RENDER_TIMEOUT_MS = 10_000
THUMBNAIL_INDEX_VERSION = 3
MAX_THUMBNAIL_STEPS = 10_000
REVISION_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

type StepCount = int | Literal["dynamic"]
type ThumbnailProgress = Callable[[int, int, str, str, int, int, int], None]


class ThumbnailError(Exception):
    """A user-correctable thumbnail generation failure."""


class ManifestSlide(TypedDict):
    """A normalized manifest leaf needed for thumbnail generation."""

    address: str
    has_step: bool
    step: object


class ThumbnailIndexStep(TypedDict):
    """One generated step image owned through the thumbnail index."""

    path: str
    step: int
    revision: str


class ThumbnailIndexEntry(TypedDict):
    """One generated thumbnail sequence."""

    canonicalStep: int
    steps: list[ThumbnailIndexStep]


class ThumbnailIndex(TypedDict):
    """The versioned thumbnail lookup and ownership ledger."""

    version: int
    presentations: dict[str, dict[str, ThumbnailIndexEntry]]


class ResizableImage(Protocol):
    """The typed subset of Pillow used by thumbnail encoding."""

    def resize(self, size: tuple[int, int], resample: int | None = None) -> Image.Image: ...


@dataclass(frozen=True)
class ThumbnailResult:
    """The output produced for one slide step."""

    presentation_id: str
    address: str
    path: Path
    step: int
    canonical: bool


@dataclass(frozen=True)
class CapturedThumbnail:
    """One encoded step thumbnail held until every capture succeeds."""

    relative_path: Path
    step: int
    revision: str
    content: bytes


@dataclass(frozen=True)
class CapturedSlide:
    """A complete generated sequence for one slide."""

    presentation_id: str
    address: str
    canonical_step: int
    thumbnails: tuple[CapturedThumbnail, ...]


def select_thumbnail_step(
    steps: StepCount,
    *,
    has_override: bool,
    override: object,
) -> int:
    """Choose and validate the canonical capture step for one slide."""
    if steps == "dynamic":
        if has_override:
            raise ThumbnailError("dynamic slides may not declare thumbnail.step")
        return 0

    if steps < 1:
        raise ThumbnailError(f"slide reported invalid step count {steps}")
    if steps > MAX_THUMBNAIL_STEPS:
        raise ThumbnailError(
            f"slide reported {steps} steps; maximum supported is {MAX_THUMBNAIL_STEPS}"
        )
    if not has_override:
        return steps - 1
    if isinstance(override, bool) or not isinstance(override, int) or override < 0:
        raise ThumbnailError("thumbnail.step must be a non-negative integer")
    if override >= steps:
        raise ThumbnailError(
            f"thumbnail.step {override} is outside the slide's 0..{steps - 1} range"
        )
    return override


def generate_thumbnail(
    project_root: Path,
    presentation_id: str,
    address: str,
) -> ThumbnailResult:
    """Generate the canonical thumbnail for one addressed slide."""
    results = generate_thumbnails(
        project_root,
        presentation_id=presentation_id,
        addresses=[address],
    )
    return next(result for result in results if result.canonical)


def generate_thumbnails(
    project_root: Path,
    *,
    presentation_id: str | None = None,
    addresses: Sequence[str] | None = None,
    missing_only: bool = False,
    on_progress: ThumbnailProgress | None = None,
) -> tuple[ThumbnailResult, ...]:
    """Generate thumbnails for one catalog presentation or the complete project."""
    if addresses is not None and presentation_id is None:
        raise ThumbnailError("--slide requires --presentation ID")

    canonical_project = project_root.expanduser().resolve()
    try:
        with (
            compose_project(canonical_project) as composition,
            serve_composition(
                composition,
                dependency_cache=DependencyCache(default_dependency_cache_root()),
            ) as base_url,
            sync_playwright() as playwright,
        ):
            site_root = composition.author_root
            output_root = site_root / "thumbnails"
            old_index = load_thumbnail_index(output_root)
            try:
                browser = playwright.chromium.launch(headless=True)
            except PlaywrightError as error:
                raise ThumbnailError(chromium_launch_error_message(error)) from error

            try:
                catalog_ids = _discover_catalog(browser, base_url)
                if presentation_id is not None and presentation_id not in catalog_ids:
                    raise ThumbnailError(f"unknown presentation ID: {presentation_id}")
                selected_ids = (presentation_id,) if presentation_id is not None else catalog_ids
                slides_by_presentation = {
                    selected_id: _discover_slides(browser, base_url, selected_id)
                    for selected_id in selected_ids
                }
                selected = tuple(
                    (selected_id, slide)
                    for selected_id in selected_ids
                    for slide in _select_slides(slides_by_presentation[selected_id], addresses)
                    if not missing_only
                    or _thumbnail_sequence_is_missing(
                        output_root,
                        old_index,
                        selected_id,
                        slide["address"],
                    )
                )
                captures: list[CapturedSlide] = []
                total = len(selected)
                for position, (selected_id, slide) in enumerate(selected, start=1):
                    captures.append(
                        _capture_slide(
                            browser,
                            base_url,
                            selected_id,
                            slide,
                            slide_position=position,
                            slide_total=total,
                            on_progress=on_progress,
                        )
                    )
            except PlaywrightError as error:
                raise ThumbnailError(f"could not render presentation: {error}") from error
            finally:
                browser.close()
    except (CompositionError, ProjectConfigError, RuntimeManifestError) as error:
        raise ThumbnailError(str(error)) from error

    return _commit_captures(
        site_root,
        output_root,
        old_index,
        slides_by_presentation,
        captures,
        selected_ids=selected_ids,
        catalog_ids=catalog_ids,
        project_wide=presentation_id is None,
    )


def _discover_catalog(browser: Browser, base_url: str) -> tuple[str, ...]:
    context = _new_browser_context(browser)
    try:
        page = context.new_page()
        page.goto(f"{base_url}/?vividly-capture=1#/", wait_until="domcontentloaded")
        _wait_until_ready(page)
        value = page.locator("vividly-presentation").evaluate(
            "(presentation) => [...presentation._catalog.presentations.keys()]"
        )
        return tuple(cast(list[str], value))
    finally:
        context.close()


def _discover_slides(
    browser: Browser,
    base_url: str,
    presentation_id: str,
) -> tuple[ManifestSlide, ...]:
    context = _new_browser_context(browser)
    try:
        page = context.new_page()
        page.goto(
            f"{base_url}/?vividly-capture=1#/{presentation_id}/",
            wait_until="domcontentloaded",
        )
        _wait_until_ready(page)
        value = page.locator("vividly-presentation").evaluate(
            """(presentation) => presentation._leaves.map((leaf) => {
                const thumbnail = leaf.node.thumbnail;
                return {
                    address: leaf.address,
                    has_step: thumbnail != null && Object.hasOwn(thumbnail, 'step'),
                    step: thumbnail?.step ?? null,
                };
            })"""
        )
        return tuple(cast(list[ManifestSlide], value))
    finally:
        context.close()


def _select_slides(
    slides: Sequence[ManifestSlide],
    addresses: Sequence[str] | None,
) -> tuple[ManifestSlide, ...]:
    if addresses is None:
        return tuple(slides)

    by_address = {slide["address"]: slide for slide in slides}
    selected: list[ManifestSlide] = []
    seen: set[str] = set()
    for address in addresses:
        if address not in by_address:
            raise ThumbnailError(f"unknown slide address: {address}")
        if address not in seen:
            selected.append(by_address[address])
            seen.add(address)
    return tuple(selected)


def _thumbnail_sequence_is_missing(
    output_root: Path,
    index: ThumbnailIndex,
    presentation_id: str,
    address: str,
) -> bool:
    entry = index["presentations"].get(presentation_id, {}).get(address)
    if entry is None:
        return True
    return any(
        not _indexed_output_path(output_root, step_entry["path"]).is_file()
        for step_entry in entry["steps"]
    )


def _new_browser_context(browser: Browser):
    return browser.new_context(
        viewport={"width": CAPTURE_WIDTH, "height": CAPTURE_HEIGHT},
        device_scale_factor=1,
        locale="en-US",
        timezone_id="UTC",
        color_scheme="dark",
        reduced_motion="reduce",
    )


def _capture_slide(
    browser: Browser,
    base_url: str,
    presentation_id: str,
    slide: ManifestSlide,
    *,
    slide_position: int,
    slide_total: int,
    on_progress: ThumbnailProgress | None,
) -> CapturedSlide:
    address = slide["address"]
    context = _new_browser_context(browser)
    try:
        page = context.new_page()
        page.goto(
            f"{base_url}/?vividly-capture=1#/{presentation_id}/{address}",
            wait_until="domcontentloaded",
        )
        _wait_until_slide_ready(page, address, 0)
        steps = cast(
            StepCount,
            page.locator("vividly-presentation").evaluate(
                "(presentation) => typeof presentation._current.steps === 'number' "
                "? presentation._current.steps : 'dynamic'"
            ),
        )
        canonical_step = select_thumbnail_step(
            steps,
            has_override=slide["has_step"],
            override=slide["step"],
        )
        step_count = 1 if steps == "dynamic" else steps
        captures: list[CapturedThumbnail] = []
        for step in range(step_count):
            if on_progress is not None:
                on_progress(
                    slide_position,
                    slide_total,
                    presentation_id,
                    address,
                    step,
                    step + 1,
                    step_count,
                )
            if step != 0:
                _navigate(page, presentation_id, address, step)
            content = _capture_stage(page)
            captures.append(
                CapturedThumbnail(
                    relative_path=thumbnail_relative_path(presentation_id, address, step),
                    step=step,
                    revision=hashlib.sha256(content).hexdigest(),
                    content=content,
                )
            )
        return CapturedSlide(
            presentation_id=presentation_id,
            address=address,
            canonical_step=canonical_step,
            thumbnails=tuple(captures),
        )
    finally:
        context.close()


def _capture_stage(page: Page) -> bytes:
    source = page.locator(".v-stage").screenshot(type="png")
    with Image.open(io.BytesIO(source)) as image:
        resizable = cast(ResizableImage, image)
        resized = resizable.resize(
            (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT),
            Image.Resampling.LANCZOS,
        )
        resized.info.clear()
        encoded = io.BytesIO()
        resized.save(encoded, format="PNG", optimize=False, compress_level=9)
    return encoded.getvalue()


def load_thumbnail_index(output_root: Path) -> ThumbnailIndex:
    if output_root.exists() and not output_root.is_dir():
        raise ThumbnailError(f"thumbnail output path is not a directory: {output_root}")
    index_path = output_root / "index.json"
    if not index_path.exists():
        return {"version": THUMBNAIL_INDEX_VERSION, "presentations": {}}
    if not index_path.is_file():
        raise ThumbnailError(f"thumbnail index is not a file: {index_path}")

    try:
        value = cast(object, json.loads(index_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ThumbnailError(f"cannot read thumbnail index {index_path}: {error}") from error
    if not isinstance(value, dict):
        raise ThumbnailError(f"unsupported thumbnail index at {index_path}")
    index_mapping = cast(dict[str, object], value)
    if index_mapping.get("version") != THUMBNAIL_INDEX_VERSION:
        raise ThumbnailError(f"unsupported thumbnail index at {index_path}")
    raw_presentations = index_mapping.get("presentations")
    if not isinstance(raw_presentations, dict):
        raise ThumbnailError(f"invalid thumbnail index at {index_path}")

    presentations: dict[str, dict[str, ThumbnailIndexEntry]] = {}
    owned_paths: set[str] = set()
    for presentation_id, raw_entries in cast(dict[object, object], raw_presentations).items():
        if not isinstance(presentation_id, str) or not isinstance(raw_entries, dict):
            raise ThumbnailError(f"invalid thumbnail index entry at {index_path}")
        entries: dict[str, ThumbnailIndexEntry] = {}
        for address, raw_entry in cast(dict[object, object], raw_entries).items():
            if not isinstance(address, str) or not isinstance(raw_entry, dict):
                raise ThumbnailError(f"invalid thumbnail index entry at {index_path}")
            entry_mapping = cast(dict[str, object], raw_entry)
            canonical_step = entry_mapping.get("canonicalStep")
            raw_steps = entry_mapping.get("steps")
            if (
                isinstance(canonical_step, bool)
                or not isinstance(canonical_step, int)
                or canonical_step < 0
                or not isinstance(raw_steps, list)
                or not raw_steps
            ):
                raise ThumbnailError(
                    f"invalid thumbnail index entry for {presentation_id}:{address}"
                )
            steps: list[ThumbnailIndexStep] = []
            for expected_step, raw_step_entry in enumerate(cast(list[object], raw_steps)):
                if not isinstance(raw_step_entry, dict):
                    raise ThumbnailError(
                        f"invalid thumbnail index entry for {presentation_id}:{address}"
                    )
                step_mapping = cast(dict[str, object], raw_step_entry)
                step = step_mapping.get("step")
                relative_path = step_mapping.get("path")
                revision = step_mapping.get("revision")
                if (
                    isinstance(step, bool)
                    or not isinstance(step, int)
                    or step != expected_step
                    or not isinstance(relative_path, str)
                    or not isinstance(revision, str)
                    or REVISION_PATTERN.fullmatch(revision) is None
                ):
                    raise ThumbnailError(
                        f"invalid thumbnail index entry for {presentation_id}:{address}"
                    )
                expected_path = thumbnail_relative_path(presentation_id, address, step).as_posix()
                if relative_path != expected_path:
                    raise ThumbnailError(
                        f"invalid thumbnail index path for {presentation_id}:{address}:{step}"
                    )
                _indexed_output_path(output_root, relative_path)
                if relative_path in owned_paths:
                    raise ThumbnailError(f"duplicate thumbnail path in index: {relative_path}")
                owned_paths.add(relative_path)
                steps.append(
                    {
                        "path": relative_path,
                        "step": step,
                        "revision": revision,
                    }
                )
            if canonical_step >= len(steps):
                raise ThumbnailError(
                    f"invalid thumbnail index entry for {presentation_id}:{address}"
                )
            entries[address] = {
                "canonicalStep": canonical_step,
                "steps": steps,
            }
        presentations[presentation_id] = entries
    return {"version": THUMBNAIL_INDEX_VERSION, "presentations": presentations}


def _commit_captures(
    site_root: Path,
    output_root: Path,
    old_index: ThumbnailIndex,
    slides_by_presentation: dict[str, tuple[ManifestSlide, ...]],
    captures: Sequence[CapturedSlide],
    *,
    selected_ids: Sequence[str],
    catalog_ids: Sequence[str],
    project_wide: bool,
) -> tuple[ThumbnailResult, ...]:
    selected_id_set = set(selected_ids)
    catalog_id_set = set(catalog_ids)
    reachable = {
        presentation_id: {slide["address"] for slide in slides}
        for presentation_id, slides in slides_by_presentation.items()
    }
    old_presentations = old_index["presentations"]
    old_owned_paths = {
        step_entry["path"]
        for entries in old_presentations.values()
        for entry in entries.values()
        for step_entry in entry["steps"]
    }
    new_presentations: dict[str, dict[str, ThumbnailIndexEntry]] = {}
    stale_paths: set[str] = set()

    for old_presentation_id, old_entries in old_presentations.items():
        reconcile = old_presentation_id in selected_id_set or (
            project_wide and old_presentation_id not in catalog_id_set
        )
        if not reconcile:
            new_presentations[old_presentation_id] = dict(old_entries)
            continue

        new_entries: dict[str, ThumbnailIndexEntry] = {}
        presentation_reachable = reachable.get(old_presentation_id, set())
        for address, entry in old_entries.items():
            if address in presentation_reachable:
                new_entries[address] = entry
            else:
                stale_paths.update(step_entry["path"] for step_entry in entry["steps"])
        if new_entries:
            new_presentations[old_presentation_id] = new_entries

    new_paths: set[str] = set()
    for captured_slide in captures:
        entries = new_presentations.setdefault(captured_slide.presentation_id, {})
        old_entry = entries.get(captured_slide.address)
        if old_entry is not None:
            stale_paths.update(step_entry["path"] for step_entry in old_entry["steps"])
        index_steps: list[ThumbnailIndexStep] = []
        for capture in captured_slide.thumbnails:
            relative_path = capture.relative_path.as_posix()
            if relative_path in new_paths:
                raise ThumbnailError(f"duplicate generated thumbnail path: {relative_path}")
            new_paths.add(relative_path)
            target = _indexed_output_path(output_root, relative_path)
            if target.exists() and relative_path not in old_owned_paths:
                raise ThumbnailError(f"refusing to overwrite unindexed file: {target}")
            if target.exists() and not target.is_file():
                raise ThumbnailError(f"thumbnail output is not a file: {target}")
            _validate_parent_directories(output_root, target)
            stale_paths.discard(relative_path)
            index_steps.append(
                {
                    "path": relative_path,
                    "step": capture.step,
                    "revision": capture.revision,
                }
            )
        entries[captured_slide.address] = {
            "canonicalStep": captured_slide.canonical_step,
            "steps": index_steps,
        }

    stale_targets = tuple(_indexed_output_path(output_root, path) for path in stale_paths)
    for target in stale_targets:
        if target.exists() and not target.is_file():
            raise ThumbnailError(f"indexed thumbnail is not a file: {target}")

    new_index: ThumbnailIndex = {
        "version": THUMBNAIL_INDEX_VERSION,
        "presentations": {
            presentation_id: dict(sorted(entries.items()))
            for presentation_id, entries in sorted(new_presentations.items())
            if entries
        },
    }
    index_content = (json.dumps(new_index, ensure_ascii=False, indent=2) + "\n").encode()

    with tempfile.TemporaryDirectory(prefix=".vividly-thumbnails-", dir=site_root) as staging:
        staging_root = Path(staging)
        staged_images: list[tuple[CapturedSlide, CapturedThumbnail, Path]] = []
        for captured_slide in captures:
            for capture in captured_slide.thumbnails:
                staged_path = staging_root / capture.relative_path
                staged_path.parent.mkdir(parents=True, exist_ok=True)
                staged_path.write_bytes(capture.content)
                staged_images.append((captured_slide, capture, staged_path))
        staged_index = staging_root / "index.json"
        staged_index.write_bytes(index_content)

        output_root.mkdir(parents=True, exist_ok=True)
        results: list[ThumbnailResult] = []
        for captured_slide, capture, staged_path in staged_images:
            target = output_root / capture.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or target.read_bytes() != capture.content:
                staged_path.replace(target)
            results.append(
                ThumbnailResult(
                    presentation_id=captured_slide.presentation_id,
                    address=captured_slide.address,
                    path=target,
                    step=capture.step,
                    canonical=capture.step == captured_slide.canonical_step,
                )
            )

        for target in stale_targets:
            target.unlink(missing_ok=True)
            _prune_empty_directories(target.parent, output_root)

        index_path = output_root / "index.json"
        if not index_path.is_file() or index_path.read_bytes() != index_content:
            staged_index.replace(index_path)

    return tuple(results)


def thumbnail_relative_path(presentation_id: str, address: str, step: int) -> Path:
    if (
        not presentation_id
        or "/" in presentation_id
        or "\\" in presentation_id
        or presentation_id in {".", ".."}
    ):
        raise ThumbnailError(f"invalid presentation ID: {presentation_id}")
    parts = address.split("/")
    if not address or "\\" in address or any(part in {"", ".", ".."} for part in parts):
        raise ThumbnailError(f"invalid slide address: {address}")
    if isinstance(step, bool) or not 0 <= step < MAX_THUMBNAIL_STEPS:
        raise ThumbnailError(f"invalid thumbnail step: {step}")
    return Path(presentation_id, *parts, f"step-{step:04d}.png")


def _indexed_output_path(output_root: Path, relative_text: str) -> Path:
    relative_path = Path(relative_text)
    if (
        not relative_text
        or relative_path.is_absolute()
        or "\\" in relative_text
        or "?" in relative_text
        or "#" in relative_text
        or relative_path.as_posix() != relative_text
    ):
        raise ThumbnailError(f"invalid thumbnail path in index: {relative_text}")
    target = output_root / relative_path
    if not target.resolve().is_relative_to(output_root.resolve()):
        raise ThumbnailError(f"thumbnail path escapes output directory: {relative_text}")
    return target


def _validate_parent_directories(output_root: Path, target: Path) -> None:
    parent = target.parent
    while parent != output_root:
        if parent.exists() and not parent.is_dir():
            raise ThumbnailError(f"thumbnail parent path is not a directory: {parent}")
        parent = parent.parent


def _prune_empty_directories(directory: Path, output_root: Path) -> None:
    while directory != output_root:
        try:
            directory.rmdir()
        except OSError:
            return
        directory = directory.parent


def _navigate(page: Page, presentation_id: str, address: str, step: int) -> None:
    route = f"{presentation_id}/{address}"
    hash_value = f"#/{route}" if step == 0 else f"#/{route}/{step}"
    page.evaluate("(hashValue) => { location.hash = hashValue; }", hash_value)
    _wait_until_slide_ready(page, address, step)


def _wait_until_slide_ready(page: Page, address: str, step: int) -> None:
    page.wait_for_function(
        """({ address, step }) => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._leaves?.[presentation._index]?.address === address
                && presentation._step === step
                && presentation.hasAttribute('data-render-ready');
        }""",
        arg={"address": address, "step": step},
        timeout=RENDER_TIMEOUT_MS,
    )


def _wait_until_ready(page: Page) -> None:
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')",
        timeout=RENDER_TIMEOUT_MS,
    )
