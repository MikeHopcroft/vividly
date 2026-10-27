"""Tests for the repository-owned public site."""

import http.client
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

import pytest
import yaml
from playwright.sync_api import Page, expect, sync_playwright
from runtime_site import (
    STATIC_DEPENDENCY_URLS,
    route_local_dependencies,
    route_static_dependencies,
)

from vividly.composition import compose_project
from vividly.export import export_project

REPOSITORY_ROOT = Path(__file__).parents[1]
FRAMEWORK_VERSION = (
    (REPOSITORY_ROOT / "src/vividly/resources/runtime/vividly/version.txt")
    .read_text(encoding="utf-8")
    .strip()
)


@pytest.fixture
def chromium() -> None:
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("run 'vividly install-browser' before public-site tests")


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _wait_for_server(process: subprocess.Popen[str], port: int) -> str:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate()
            pytest.fail(f"public-site server exited before serving a request:\n{output}")
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.2)
            connection.request("HEAD", "/")
            response = connection.getresponse()
            response.read()
            connection.close()
            if response.status == 200:
                return f"http://127.0.0.1:{port}"
        except OSError:
            time.sleep(0.05)
    pytest.fail("public-site server did not start within five seconds")


def _wait_for_public_route(
    page: Page,
    presentation_id: str,
    address: str,
) -> None:
    page.wait_for_function(
        """([presentationId, address]) => {
          const presentation = document.querySelector('vividly-presentation');
          return presentation?._presentationId === presentationId
            && presentation._leaves?.[presentation._index]?.address === address
            && presentation.hasAttribute('data-render-ready');
        }""",
        arg=[presentation_id, address],
    )


def test_repository_composes_public_site_with_editable_runtime() -> None:
    with compose_project(REPOSITORY_ROOT) as composition:
        assert composition.author_root == REPOSITORY_ROOT / "site"
        assert composition.runtime.source == "repository"
        assert composition.files[PurePosixPath("/catalog.yaml")].owner == "author"
        assert composition.files[PurePosixPath("/presentations/vividly.yaml")].owner == "author"
        manifest = PurePosixPath("/presentations/feature-tour.yaml")
        assert composition.files[manifest].owner == "author"
        assert composition.files[PurePosixPath("/slides/home/slide.js")].owner == "author"
        assert (
            composition.files[PurePosixPath("/slides/feature-tour/title-card/slide.js")].owner
            == "author"
        )
        assert (
            composition.files[PurePosixPath("/slides/documentation/opening.js")].owner == "author"
        )
        assert composition.files[PurePosixPath("/reference/authoring.md")].owner == "author"
        assert composition.files[PurePosixPath("/reference/cli.md")].owner == "author"
        assert composition.files[PurePosixPath("/reference/dependencies.md")].owner == "author"
        assert composition.files[PurePosixPath("/reference/publishing.md")].owner == "author"
        assert composition.files[PurePosixPath("/index.html")].owner == "runtime"


def test_public_reference_matches_canonical_package_source() -> None:
    result = subprocess.run(
        [sys.executable, "tools/sync_public_reference.py", "--check"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_public_site_candidate_exports_clean_revision_and_rejects_dirty_source(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(REPOSITORY_ROOT / "site", repository / "site")
    shutil.copytree(
        REPOSITORY_ROOT / "src/vividly/resources/runtime",
        repository / "src/vividly/resources/runtime",
    )
    shutil.copytree(
        REPOSITORY_ROOT / "src/vividly/resources/reference",
        repository / "src/vividly/resources/reference",
    )
    shutil.copytree(REPOSITORY_ROOT / "tools", repository / "tools")
    shutil.copy2(REPOSITORY_ROOT / "vividly.yaml", repository / "vividly.yaml")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "Vividly Tests"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "tests@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-q", "-m", "fixture"],
        check=True,
    )
    expected = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    destination = tmp_path / "vividly"

    result = subprocess.run(
        [
            sys.executable,
            str(repository / "tools/export_public_site.py"),
            "--output",
            str(destination),
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Source revision: {expected}" in result.stdout
    assert f"Framework version: {FRAMEWORK_VERSION}" in result.stdout
    assert "No deployment was performed." in result.stdout
    assert (destination / "index.html").is_file()
    assert (destination / "catalog.yaml").is_file()
    assert (destination / "vividly/version.txt").read_text(encoding="utf-8").strip() == (
        FRAMEWORK_VERSION
    )

    catalog = repository / "site/catalog.yaml"
    catalog.write_text(catalog.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    dirty_destination = tmp_path / "dirty"
    dirty = subprocess.run(
        [
            sys.executable,
            str(repository / "tools/export_public_site.py"),
            "--output",
            str(dirty_destination),
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert dirty.returncode == 1
    assert "repository has uncommitted changes" in dirty.stderr
    assert not dirty_destination.exists()


def test_repository_public_site_exports_to_sibling_artifact(tmp_path: Path) -> None:
    destination = tmp_path / "vividly-public-site"

    export_project(REPOSITORY_ROOT, destination)

    assert (destination / "index.html").is_file()
    assert (destination / "catalog.yaml").read_text(encoding="utf-8") == (
        REPOSITORY_ROOT / "site/catalog.yaml"
    ).read_text(encoding="utf-8")
    assert (destination / "slides/home/slide.js").is_file()
    assert (destination / "slides/documentation/opening.js").is_file()
    assert (destination / "presentations/feature-tour.yaml").is_file()
    assert (destination / "slides/feature-tour/title-card/slide.js").is_file()
    assert (destination / "reference/cli.md").is_file()
    assert (destination / "reference/publishing.md").is_file()


def test_exported_public_site_runs_under_pages_project_path(
    chromium: None,
    tmp_path: Path,
) -> None:
    del chromium
    destination = tmp_path / "vividly"
    export_project(REPOSITORY_ROOT, destination)
    port = _available_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(port),
            "--bind",
            "127.0.0.1",
            "--directory",
            str(tmp_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base_url = _wait_for_server(process, port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            route_static_dependencies(page, destination)
            requested_urls: list[str] = []
            page.on("request", lambda request: requested_urls.append(request.url))
            page.goto(
                f"{base_url}/vividly/?vividly-capture=1#/vividly/home",
                wait_until="domcontentloaded",
            )
            page.wait_for_function(
                "() => document.querySelector('vividly-presentation')"
                "?.hasAttribute('data-render-ready')"
            )

            page.get_by_text("Make complex ideas move.", exact=True).wait_for()
            page.get_by_text(f"Vividly framework {FRAMEWORK_VERSION}", exact=True).wait_for()
            assert requested_urls
            assert all(
                url.startswith(f"{base_url}/vividly/") or url in STATIC_DEPENDENCY_URLS
                for url in requested_urls
            )
            assert STATIC_DEPENDENCY_URLS.issubset(requested_urls)
            assert page.evaluate(
                """async () => {
                    const { Slide } = await import('vividly/runtime/slide.js');
                    return typeof Slide;
                }"""
            ) == "function"
            assert f"{base_url}/vividly/vividly/runtime/slide.js" in requested_urls
            page.goto(
                f"{base_url}/vividly/?vividly-capture=1&case=photo"
                "#/feature-tour/images/photo-tour/2",
                wait_until="domcontentloaded",
            )
            _wait_for_public_route(page, "feature-tour", "images/photo-tour")
            page.get_by_role("heading", name="A Guided Photo Tour").wait_for()
            assert page.locator(".tour-frame img").count() == 4
            first_photo = page.locator(".tour-frame img").first.get_attribute("src")
            assert first_photo is not None
            assert first_photo.startswith(f"{base_url}/vividly/vividly/assets/demo/")

            page.goto(
                f"{base_url}/vividly/?vividly-capture=1&case=markdown"
                "#/feature-tour/mechanics/markdown-controls",
                wait_until="domcontentloaded",
            )
            _wait_for_public_route(page, "feature-tour", "mechanics/markdown-controls")
            page.get_by_role("heading", name="Markdown composition").wait_for()
            assert page.locator("vividly-markdown pre code.hljs").count() == 1
            assert page.locator("markdown-controls-callout[data-upgraded='true']").count() == 1
            assert all(
                url.startswith(f"{base_url}/vividly/")
                or url in STATIC_DEPENDENCY_URLS
                for url in requested_urls
            )
            browser.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)


def test_guided_introduction_step_navigation(chromium: None) -> None:
    del chromium
    port = _available_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vividly.cli",
            "run",
            "--port",
            str(port),
            "--no-watch",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    try:
        base_url = _wait_for_server(process, port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            route_local_dependencies(page, base_url, REPOSITORY_ROOT / "site")
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            steps = (
                "overview",
                "install",
                "provision",
                "prompt",
                "preview",
                "refine",
                "present",
                "publish",
            )
            shell = page.locator(".v-layer:not([hidden]) .guide-shell")
            sidebar = shell.get_by_role("navigation", name="Guided introduction steps")
            for index, step in enumerate(steps):
                address = f"make-something/get-started/{step}"
                page.goto(f"{base_url}/#/vividly/{address}")
                _wait_for_public_route(page, "vividly", address)
                expect(sidebar).to_be_visible()
                expect(sidebar.locator("a")).to_have_count(8)
                expect(sidebar.locator('a[aria-current="page"]')).to_have_count(1)
                expect(sidebar.locator("a").nth(index)).to_have_attribute("aria-current", "page")
                expect(shell.locator(".guide-progress")).to_be_hidden()
                assert shell.locator(".guide-main").evaluate(
                    "element => element.clientWidth === 1120"
                )
                assert shell.evaluate("element => element.scrollWidth <= element.clientWidth")
                if step in ("overview", "preview", "refine"):
                    assert shell.locator(".guide-with-demo").evaluate(
                        "element => element.clientWidth >= 1024"
                    )
                    expect(shell.locator(".guide-demo")).to_be_visible()

            sidebar_top = sidebar.evaluate("element => element.getBoundingClientRect().top")
            shell.locator(".guide-scroll").evaluate(
                "element => element.scrollTop = element.scrollHeight"
            )
            assert sidebar.evaluate("element => element.getBoundingClientRect().top") == sidebar_top
            sidebar.locator("a").nth(2).focus()
            page.keyboard.press("Tab")
            expect(sidebar.locator("a").nth(3)).to_be_focused()
            assert (
                sidebar.locator("a")
                .nth(3)
                .evaluate("element => getComputedStyle(element).outlineStyle")
                == "solid"
            )
            page.keyboard.press("Enter")
            _wait_for_public_route(page, "vividly", "make-something/get-started/prompt")
            page.go_back()
            _wait_for_public_route(page, "vividly", "make-something/get-started/publish")
            page.go_forward()
            _wait_for_public_route(page, "vividly", "make-something/get-started/prompt")
            shell.locator(".guide-next").click()
            _wait_for_public_route(page, "vividly", "make-something/get-started/preview")
            shell.locator(".guide-footer a").first.click()
            _wait_for_public_route(page, "vividly", "make-something/get-started/prompt")

            for width in (1400, 1399, 1280, 1188, 1024, 1023, 900, 480):
                page.set_viewport_size({"width": width, "height": 900})
                if width >= 1024:
                    expect(sidebar).to_be_visible()
                    expect(shell.locator(".guide-progress")).to_be_hidden()
                    if width >= 1400:
                        assert shell.locator(".guide-main").evaluate(
                            "element => element.clientWidth === 1120"
                        )
                    assert shell.locator(".guide-main").evaluate(
                        "element => element.scrollWidth <= element.clientWidth"
                    )
                    continue
                expect(sidebar).to_be_hidden()
                summary = shell.locator(".guide-progress summary")
                expect(summary).to_be_visible()
                if shell.locator(".guide-progress").get_attribute("open") is not None:
                    summary.click()
                expect(shell.locator(".guide-progress nav a").first).to_be_hidden()
                summary.click()
                shell.locator(".guide-progress nav a").nth(6).click()
                _wait_for_public_route(page, "vividly", "make-something/get-started/present")
                expect(shell.locator(".guide-progress summary")).to_have_text("7 of 8 · Present")
                assert shell.evaluate("element => element.scrollWidth <= element.clientWidth")

            for width in (1280, 1188, 1024):
                page.set_viewport_size({"width": width, "height": 900})
                for step in ("overview", "preview", "refine"):
                    address = f"make-something/get-started/{step}"
                    page.goto(f"{base_url}/#/vividly/{address}")
                    _wait_for_public_route(page, "vividly", address)
                    expect(sidebar).to_be_visible()
                    assert shell.locator(".guide-scroll").evaluate(
                        "element => element.scrollWidth <= element.clientWidth"
                    )
                    columns = shell.locator(".guide-with-demo").evaluate(
                        "element => getComputedStyle(element).gridTemplateColumns.split(' ').length"
                    )
                    assert columns == (2 if width >= 1200 else 1)

            page.set_viewport_size({"width": 1920, "height": 1080})
            for address in ("make-something/agentic/bootstrap", "documentation/overview"):
                page.goto(f"{base_url}/#/vividly/{address}")
                _wait_for_public_route(page, "vividly", address)
                expect(shell.locator(".guide-sidebar")).to_have_count(0)
                expect(shell.locator(".guide-progress")).to_have_count(0)
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)


def test_repository_root_runs_public_site(
    chromium: None,
) -> None:
    del chromium
    catalog = yaml.safe_load(
        (REPOSITORY_ROOT / "site" / "catalog.yaml").read_text(encoding="utf-8")
    )
    expected_presentations = [entry["id"] for entry in catalog["presentations"]]
    assert "vividly" in expected_presentations
    manifest = yaml.safe_load(
        (REPOSITORY_ROOT / "site" / "presentations" / "vividly.yaml").read_text(encoding="utf-8")
    )
    gallery = next(section for section in manifest["nodes"] if section["id"] == "gallery")
    gallery_overview = next(slide for slide in gallery["children"] if slide["id"] == "overview")
    expected_gallery_cards = len(gallery_overview["navigator"]["sections"])
    port = _available_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vividly.cli",
            "run",
            "--port",
            str(port),
            "--no-watch",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    try:
        base_url = _wait_for_server(process, port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            route_local_dependencies(page, base_url, REPOSITORY_ROOT / "site")
            page.goto(
                f"{base_url}/?vividly-capture=1#/vividly/home",
                wait_until="domcontentloaded",
            )
            page.wait_for_function(
                "() => document.querySelector('vividly-presentation')"
                "?.hasAttribute('data-render-ready')"
            )

            page.get_by_text("Make complex ideas move.", exact=True).wait_for()
            page.get_by_text(f"Vividly framework {FRAMEWORK_VERSION}", exact=True).wait_for()
            assert page.locator(".public-home-principles article").count() == 3
            assert page.locator("vividly-presentation").evaluate(
                "presentation => [...presentation._catalog.presentations.keys()]"
            ) == expected_presentations

            page.goto(
                f"{base_url}/?vividly-capture=1#/vividly/opening",
                wait_until="domcontentloaded",
            )
            page.wait_for_function(
                "() => document.querySelector('vividly-presentation')"
                "?.hasAttribute('data-render-ready')"
            )

            page.get_by_text("Making complex ideas move.", exact=True).wait_for()
            assert page.url.endswith("#/vividly/opening")
            assert page.locator(".docs-opening-choice").count() == 3

            reference_routes = {
                "documentation/cli": "Command line",
                "documentation/slides": "Slide model",
                "documentation/controls": "Built-in controls",
                "documentation/keyboard": "Present and navigate",
            }
            for route, heading in reference_routes.items():
                page.goto(
                    f"{base_url}/?vividly-capture=1#/vividly/{route}",
                    wait_until="domcontentloaded",
                )
                page.wait_for_function(
                    "() => document.querySelector('vividly-presentation')"
                    "?.hasAttribute('data-render-ready')"
                )
                page.get_by_role("heading", name=heading, exact=True).wait_for()
                control_errors = page.locator(".v-control-error:visible")
                assert control_errors.count() == 0, control_errors.all_text_contents()
                if route == "documentation/slides":
                    active_layer = page.locator(".v-layer:not([hidden])")
                    assert active_layer.locator(".guide-main > h1").count() == 1
                    assert active_layer.locator("vividly-markdown h1").count() == 0
                    highlighted = active_layer.locator("vividly-markdown pre code.hljs").first
                    highlighted.wait_for()
                    assert (
                        active_layer.locator(
                            "vividly-markdown pre code.hljs .hljs-keyword"
                        ).count()
                        > 0
                    )
                    assert highlighted.evaluate(
                        "element => getComputedStyle(element).color"
                    ) == "rgb(201, 209, 217)"
                    assert highlighted.evaluate(
                        "element => getComputedStyle(element).backgroundColor"
                    ) == "rgb(13, 17, 23)"
                    assert page.locator("vividly-presentation").evaluate(
                        """presentation =>
                          presentation._catalog.presentations.has('vividly')
                          && typeof presentation._yaml.load === 'function'"""
                    )

            page.set_viewport_size({"width": 1200, "height": 900})
            page.goto(
                f"{base_url}/?vividly-capture=1#/vividly/gallery/overview",
                wait_until="domcontentloaded",
            )
            page.wait_for_function(
                "() => document.querySelector('vividly-presentation')"
                "?.hasAttribute('data-render-ready')"
            )
            cards = page.locator(".v-layer:not([hidden]) .card-navigator-card")
            cards.first.wait_for()
            assert cards.count() == expected_gallery_cards
            demo_card = page.get_by_role("button", name="Tic-Tac-Toe")
            demo_card.click()
            _wait_for_public_route(page, "vividly", "gallery/tic-tac-toe/introduction")
            page.get_by_role("heading", name="Tic-Tac-Toe", exact=True).wait_for()
            page.go_back()
            _wait_for_public_route(page, "vividly", "gallery/overview")
            cards.first.wait_for()

            def column_count() -> int:
                return cards.evaluate_all(
                    """elements => {
                        const firstTop = elements[0].getBoundingClientRect().top;
                        return elements.filter(
                            (element) => {
                                const box = element.getBoundingClientRect();
                                return Math.abs(box.top - firstTop) < box.height / 2;
                            }
                        ).length;
                    }"""
                )

            wide_columns = column_count()
            assert 1 < wide_columns <= expected_gallery_cards
            page.set_viewport_size({"width": 850, "height": 900})
            assert 1 < column_count() <= wide_columns
            page.set_viewport_size({"width": 500, "height": 900})
            assert column_count() == 1

            page.goto(
                f"{base_url}/?vividly-capture=1&case=photo"
                "#/feature-tour/images/photo-tour/3",
                wait_until="domcontentloaded",
            )
            _wait_for_public_route(page, "feature-tour", "images/photo-tour")
            page.get_by_role("heading", name="A Guided Photo Tour").wait_for()
            assert page.locator(".tour-frame img").count() == 4
            first_photo = page.locator(".tour-frame img").first.get_attribute("src")
            assert first_photo is not None
            assert first_photo.startswith(f"{base_url}/vividly/assets/demo/")

            page.goto(
                f"{base_url}/?vividly-capture=1&case=markdown"
                "#/feature-tour/mechanics/markdown-controls",
                wait_until="domcontentloaded",
            )
            _wait_for_public_route(page, "feature-tour", "mechanics/markdown-controls")
            page.get_by_role("heading", name="Markdown composition").wait_for()
            assert page.locator("vividly-markdown pre code.hljs .hljs-keyword").count() > 0
            assert page.locator("markdown-controls-callout[data-upgraded='true']").count() == 1

            page.goto(
                f"{base_url}/?vividly-capture=1&case=diagram"
                "#/feature-tour/mechanics/diagram-build/3",
                wait_until="domcontentloaded",
            )
            _wait_for_public_route(page, "feature-tour", "mechanics/diagram-build")
            stages = page.locator(".pipeline .stage")
            assert stages.count() == 4
            assert all(
                opacity == "1"
                for opacity in stages.evaluate_all(
                    "elements => elements.map((element) => getComputedStyle(element).opacity)"
                )
            )

            page.goto(
                f"{base_url}/?vividly-capture=1&case=annotated"
                "#/feature-tour/mechanics/annotated-markdown/2",
                wait_until="domcontentloaded",
            )
            _wait_for_public_route(page, "feature-tour", "mechanics/annotated-markdown")
            assert page.locator(".v-annotation-entry").count() == 4
            assert page.locator(".v-annotation-entry.selected").count() == 1

            page.goto(
                f"{base_url}/?vividly-capture=1&case=navigator"
                "#/feature-tour/navigation-sequence/navigator",
                wait_until="domcontentloaded",
            )
            _wait_for_public_route(page, "feature-tour", "navigation-sequence/navigator")
            assert page.locator(".sequence-navigator-row").count() == 3
            browser.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)


@pytest.mark.parametrize("capture", [False, True])
def test_demo_gallery_embeds_demos_and_preserves_standalone_routes(
    chromium: None,
    capture: bool,
    tmp_path: Path,
) -> None:
    """Validate the embedded demo gallery, its posters, and standalone demo routes."""
    del chromium
    port = _available_port()
    # This test makes enough requests to fill an undrained pipe and stall the server.
    server_log = (tmp_path / "server.log").open("w")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vividly.cli",
            "run",
            "--port",
            str(port),
            "--no-watch",
        ],
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    try:
        base_url = _wait_for_server(process, port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            route_local_dependencies(page, base_url, REPOSITORY_ROOT / "site")
            page.route(
                "https://cdn.jsdelivr.net/npm/@fontsource/libre-caslon-text@5.3.0/*",
                lambda route: route.fulfill(content_type="text/css", body=""),
            )
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            query = "?vividly-capture=1" if capture else "?gallery-test=1"
            gallery_url = f"{base_url}/{query}#/vividly/gallery/overview"
            cards = page.locator(".v-layer:not([hidden]) .card-navigator-card")
            for index, (demo_id, title, first_slide, last_slide) in enumerate(
                (
                    ("tic-tac-toe", "Tic-Tac-Toe", "demo", "training"),
                    ("inverted", "Inverted", "clarke-quote", "aglet-definition"),
                )
            ):
                choice_step = index
                choice_suffix = f"/{choice_step}" if choice_step else ""
                page.goto(
                    f"{base_url}/{query}&demo={demo_id}#/vividly/gallery/overview",
                    wait_until="domcontentloaded",
                )
                _wait_for_public_route(page, "vividly", "gallery/overview")
                assert cards.count() == 4
                expect(page.get_by_role("dialog", name="Keyboard navigation")).to_be_hidden()
                assert cards.evaluate_all(
                    """cards => cards.every(card => {
                        const image = card.querySelector('img');
                        return image?.complete && image.naturalWidth > 0;
                    })"""
                )
                expect(cards.first).to_have_attribute("aria-current", "step")
                expect(cards.first).to_be_focused()
                baseline = cards.nth(1).evaluate(
                    """card => {
                        const s = getComputedStyle(card);
                        return {background: s.backgroundColor, border: s.borderColor,
                            transform: s.transform};
                    }"""
                )
                cards.nth(1).hover()
                page.wait_for_function(
                    """background => getComputedStyle(document.querySelectorAll(
                        '.v-layer:not([hidden]) .card-navigator-card')[1]
                    ).backgroundColor !== background""",
                    arg=baseline["background"],
                )
                assert cards.nth(1).evaluate(
                    "card => getComputedStyle(card).borderColor"
                ) == baseline["border"]
                assert cards.nth(1).evaluate(
                    "card => getComputedStyle(card).transform"
                ) == baseline["transform"]
                expect(cards.first).to_be_focused()
                expect(cards.nth(1)).to_have_attribute("aria-current", "false")
                page.mouse.move(0, 0)
                page.keyboard.press("ArrowRight")
                page.wait_for_function("() => location.hash === '#/vividly/gallery/overview/1'")
                expect(cards.nth(1)).to_have_attribute("aria-current", "step")
                expect(cards.nth(1)).to_be_focused()
                page.keyboard.press("ArrowLeft")
                page.wait_for_function("() => location.hash === '#/vividly/gallery/overview'")
                expect(cards.first).to_be_focused()
                page.go_back()
                page.wait_for_function("() => location.hash === '#/vividly/gallery/overview/1'")
                expect(cards.nth(1)).to_have_attribute("aria-current", "step")

                page.goto(
                    f"{base_url}/{query}&tab={demo_id}"
                    f"#/vividly/gallery/overview{choice_suffix}",
                    wait_until="domcontentloaded",
                )
                _wait_for_public_route(page, "vividly", "gallery/overview")
                demo_card = page.get_by_role("button", name=title)
                expect(demo_card).to_be_focused()
                page.keyboard.press("Enter")
                introduction = f"gallery/{demo_id}/introduction"
                _wait_for_public_route(page, "vividly", introduction)
                page.get_by_role("heading", name=title, exact=True).wait_for()
                image = page.locator(
                    ".v-layer:not([hidden]) vividly-markdown img[src$='/gallery-card.png']"
                ).first
                assert image.get_attribute("src") == (
                    f"{base_url}/slides/{demo_id}/introduction/assets/gallery-card.png"
                )
                assert image.evaluate("image => image.complete && image.naturalWidth > 0")
                assert page.get_by_role("link", name="Back to See It Work").count() == 0
                page.keyboard.press("ArrowRight")
                _wait_for_public_route(page, "vividly", f"gallery/{demo_id}/{first_slide}")
                page.keyboard.press("ArrowUp")
                page.wait_for_function(
                    "hash => location.hash === hash",
                    arg=f"#/vividly/gallery/overview{choice_suffix}",
                )
                expect(cards.nth(index)).to_have_attribute("aria-current", "step")
                expect(cards.nth(index)).to_be_focused()
                page.keyboard.press("ArrowUp")
                page.wait_for_function("() => location.hash === '#/vividly/opening/1'")
                expect(page.locator(
                    ".v-layer:not([hidden]) [data-vividly-navigator-choice='1']"
                )).to_be_focused()

                page.goto(
                    f"{base_url}/?vividly-capture=1&finish={demo_id}"
                    f"#/vividly/gallery/{demo_id}/{last_slide}",
                    wait_until="domcontentloaded",
                )
                _wait_for_public_route(page, "vividly", f"gallery/{demo_id}/{last_slide}")
                overview_hash = "#/vividly/gallery/overview"
                for _ in range(4):
                    if page.evaluate("() => location.hash").startswith(overview_hash):
                        break
                    page.keyboard.press("ArrowRight")
                    page.wait_for_timeout(300)
                page.wait_for_function(
                    "hash => location.hash === hash",
                    arg=f"#/vividly/gallery/overview/{choice_step + 1}",
                )

            for presentation_id, addresses in (
                ("tic-tac-toe", ("demo/14", "inference", "training")),
                (
                    "inverted",
                    (
                        "clarke-quote",
                        "aglet",
                        "plastic-concordance/1",
                        "concordance-merge/4",
                        "aglet-definition/2",
                    ),
                ),
            ):
                for address in addresses:
                    page.goto(
                        f"{base_url}/?vividly-capture=1&case={presentation_id}-{address}"
                        f"#/{presentation_id}/{address}",
                        wait_until="domcontentloaded",
                    )
                    _wait_for_public_route(page, presentation_id, address.split("/")[0])
                    assert page.locator(".v-control-error").count() == 0

            page.goto(gallery_url, wait_until="domcontentloaded")
            _wait_for_public_route(page, "vividly", "gallery/overview")
            page.set_viewport_size({"width": 500, "height": 900})
            assert page.locator(".v-layer:not([hidden]) .card-navigator-card").evaluate_all(
                """cards => {
                    const [first, second] = cards.map(card => card.getBoundingClientRect());
                    return Math.abs(first.left - second.left) < 1 && second.top > first.bottom;
                }"""
            )
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)
        server_log.close()


def test_pool_break_candidates_navigation_controls_and_standalone_page(
    chromium: None,
    tmp_path: Path,
) -> None:
    """Validate the shared comparison against the slides.md lifecycle contract."""
    del chromium
    port = _available_port()
    server_log = (tmp_path / "pool-candidates-server.log").open("w")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "vividly.cli", "run",
            "--port", str(port), "--no-watch",
        ],
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    try:
        base_url = _wait_for_server(process, port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            route_local_dependencies(page, base_url, REPOSITORY_ROOT / "site")
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("requestfailed", lambda request: errors.append(request.url))
            page.goto(f"{base_url}/#/pool-table-break-lab/candidates")
            page.get_by_label("Don't show these tips again", exact=True).check()
            page.get_by_role("button", name="Start presentation").click()
            _wait_for_public_route(page, "pool-table-break-lab", "candidates")
            root = page.locator(".v-layer:not([hidden]) .break-comparison")
            seeds = (80, 235, 190, 214, 19, 117, 7)
            expect(root.locator("canvas")).to_have_count(len(seeds))
            assert root.evaluate("element => element.scrollWidth <= element.clientWidth")
            for seed in seeds:
                link = root.get_by_role("link", name=f"Open seed {seed} in the slide")
                expect(link).to_have_attribute(
                    "href", f"{base_url}/?breakSeed={seed}#/pool-table-break-lab/opening"
                )
            comparison = page.evaluate_handle(
                "document.querySelector('vividly-presentation')._current.instance.comparison"
            )
            page.get_by_role("button", name="Replay seed 80", exact=True).click()
            assert comparison.evaluate("comparison => comparison.settle()")
            assert not comparison.evaluate("comparison => comparison.settle()")
            page.get_by_role("button", name="Replay all", exact=True).click()
            assert comparison.evaluate("comparison => comparison.settle()")
            page.get_by_label("Table width").select_option("737.203125")
            page.wait_for_function(
                """() => document.querySelector(
                    '.v-layer:not([hidden]) .break-comparison canvas'
                ).getBoundingClientRect().width > 700"""
            )
            page.get_by_role("button", name="Settle all", exact=True).click()
            assert not comparison.evaluate("comparison => comparison.settle()")
            page.get_by_role("button", name="Replay all", exact=True).click()
            page.get_by_role("heading", name="Billiards break candidates", exact=True).click()
            page.keyboard.press("ArrowRight")
            _wait_for_public_route(page, "pool-table-break-lab", "candidates")
            assert not comparison.evaluate("comparison => comparison.settle()")
            page.keyboard.press("ArrowRight")
            _wait_for_public_route(page, "pool-table-break-lab", "opening")
            assert not comparison.evaluate("comparison => comparison.settle()")
            page.keyboard.press("ArrowLeft")
            _wait_for_public_route(page, "pool-table-break-lab", "candidates")
            expect(root.locator("canvas")).to_have_count(len(seeds))
            assert root.locator("canvas").evaluate_all(
                "canvases => canvases.every(canvas => canvas.width > 0 && canvas.height > 0)"
            )
            assert page.locator("[id]").evaluate_all(
                "elements => new Set(elements.map(element => element.id)).size === elements.length"
            )
            page.goto(
                f"{base_url}/slides/experiments/pool-table-break/break-candidates.html"
            )
            expect(page.locator(".break-comparison canvas")).to_have_count(len(seeds))
            page.get_by_role("button", name="Replay seed 235", exact=True).click()
            page.get_by_role("button", name="Settle all", exact=True).click()
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)
        server_log.close()


@pytest.mark.skipif(
    sys.platform == "linux",
    reason="small-viewport layout margins assume macOS system fonts; Linux fallbacks overflow",
)
@pytest.mark.parametrize("reduced_motion", [False, True])
def test_why_vividly_step_progress_integration(
    chromium: None,
    tmp_path: Path,
    reduced_motion: bool,
) -> None:
    """Validate the two public integrations in the step readiness progress specification."""
    del chromium
    port = _available_port()
    server_log = (tmp_path / "progress-server.log").open("w")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "vividly.cli", "run",
            "--port", str(port), "--no-watch",
        ],
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    try:
        base_url = _wait_for_server(process, port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1920, "height": 1080},
                reduced_motion="reduce" if reduced_motion else "no-preference",
            )
            route_local_dependencies(page, base_url, REPOSITORY_ROOT / "site")
            page.route(
                "https://cdn.jsdelivr.net/npm/@fontsource/libre-caslon-text@5.3.0/*",
                lambda route: route.fulfill(content_type="text/css", body=""),
            )
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("requestfailed", lambda request: errors.append(request.url))
            address = "why-vividly/complex-ideas-should-move"
            page.goto(f"{base_url}/#/vividly/{address}")
            _wait_for_public_route(page, "vividly", address)
            active = page.locator(".v-layer:not([hidden])")
            progress = active.locator("vividly-step-progress")
            button = progress.get_by_role("button", name="Advance →")
            assert active.locator("[data-promise-marker]").count() == 0
            if not reduced_motion:
                page.wait_for_function(
                    """() => {
                        const p = document.querySelector('vividly-presentation');
                        const s = p._current.instance;
                        return s.progress.value > 0 && s.progress.value < 1;
                    }"""
                )
                page.locator("vividly-presentation").evaluate(
                    """p => {
                        const s = p._current.instance;
                        const simulation = s.billiards.simulation;
                        if (s.progress.value !== simulation.ticks / s.billiards.progressTicks) {
                            throw new Error('Billiards progress must follow simulation time');
                        }
                    }"""
                )
                expect(button).to_be_hidden()
            expect(progress.get_by_role("progressbar")).to_have_attribute(
                "aria-valuetext", "Ready", timeout=15000,
            )
            assert page.url.endswith(address)
            assert button.evaluate(
                """button => {
                    const r = button.getBoundingClientRect();
                    const help = document.querySelector('.v-help-trigger').getBoundingClientRect();
                    return r.left >= 0 && r.top >= 0
                        && r.right < help.left && r.bottom <= innerHeight;
                }"""
            )
            button.click()
            page.wait_for_url(f"**/{address}/1")
            if not reduced_motion:
                page.wait_for_function(
                    """() => {
                        const s = document.querySelector('vividly-presentation')._current.instance;
                        return s.step === 1 && s.progress.value > 0 && s.progress.value < 1;
                    }"""
                )
            expect(progress.get_by_role("progressbar")).to_have_attribute(
                "aria-valuetext", "Ready", timeout=8000,
            )
            assert page.url.endswith(f"{address}/1")
            button.press("Space")
            introduction = "why-vividly/introducing-vividly"
            _wait_for_public_route(page, "vividly", introduction)
            if not reduced_motion:
                page.wait_for_function(
                    """() => {
                        const progress = document.querySelector(
                            '.introduction-progress'
                        );
                        return progress.value > 0 && progress.value < 1;
                    }"""
                )
                expect(button).to_be_hidden()
            expect(active.get_by_role("heading", name="Introducing Vividly")).to_be_visible()
            logo = active.get_by_role("img", name="Vividly", exact=True)
            expect(logo).to_be_visible()
            assert logo.evaluate("image => image.complete && image.naturalWidth > 0")
            points = active.locator(".introduction-points li")
            expect(points).to_have_count(3)
            proof = active.locator(".introduction-proof")
            expect(proof).to_have_text("This presentation? Built with Vividly.")
            expect(proof.locator("strong mark")).to_have_text("Built with Vividly.")
            expect(active.locator("mark strong em")).to_have_text([
                "agent-oriented toolkit", "the vision", "the story telling",
                "bring your vision to life", "anything that runs in the browser",
            ])
            expect(points.nth(0)).to_have_text(
                "An agent-oriented toolkit for creating visually stunning, "
                "interactive web presentations."
            )
            expect(points.nth(1)).to_contain_text("Focus all your creative energy on")
            expect(points.nth(2)).to_have_text(
                "Vividly presentations are just web apps so anything that runs in the "
                "browser can be incorporated into your presentation."
            )
            assert points.first.evaluate(
                "element => getComputedStyle(element).fontSize"
            ) == "48px"
            assert active.locator("mark").evaluate_all(
                """marks => marks.every(mark =>
                    getComputedStyle(mark).color === 'rgb(255, 181, 71)')"""
            )
            if reduced_motion:
                assert active.locator(".introduction").evaluate(
                    "element => element.getAnimations({subtree: true}).length"
                ) == 0
            else:
                timings = points.evaluate_all(
                    """points => points.flatMap(point => point.getAnimations().map(
                        animation => animation.effect.getComputedTiming().endTime
                    ))"""
                )
                assert timings == [320, 540, 760]
                assert proof.evaluate(
                    """element => element.getAnimations().map(animation => {
                        const timing = animation.effect.getTiming();
                        return {delay: timing.delay, duration: timing.duration};
                    })"""
                ) == [{"delay": 1300, "duration": 240}]
                assert active.locator("h1").evaluate(
                    """heading => heading.getAnimations().map(animation => ({
                        name: animation.animationName,
                        duration: animation.effect.getTiming().duration,
                        from: animation.effect.getKeyframes()[0].clipPath,
                    }))"""
                ) == [{
                    "name": "introduction-title-wipe",
                    "duration": 420,
                    "from": "inset(0px 100% 0px 0px)",
                }]
            page.wait_for_function(
                """() => document.querySelector('.introduction')
                    .getAnimations({subtree: true}).every(a => a.playState === 'finished')"""
            )
            expect(progress.get_by_role("progressbar")).to_have_attribute(
                "aria-valuetext", "Ready",
            )
            expect(button).to_be_visible()
            expect(proof).to_have_css("opacity", "1")
            expect(proof).to_be_in_viewport()
            assert points.evaluate_all(
                """points => points.every(point => {
                    const box = point.getBoundingClientRect();
                    return box.left >= 0 && box.top >= 0
                        && box.right <= innerWidth && box.bottom <= innerHeight
                        && getComputedStyle(point).opacity === '1';
                })"""
            )
            for width, height in ((320, 568), (375, 667), (390, 844), (430, 932), (844, 390)):
                page.set_viewport_size({"width": width, "height": height})
                assert button.evaluate(
                    """button => {
                        const box = button.getBoundingClientRect();
                        const help = document.querySelector('.v-help-trigger')
                            .getBoundingClientRect();
                        return box.left >= 0 && box.top >= 0
                            && box.right < help.left && box.bottom <= innerHeight;
                    }"""
                )
                assert active.locator(".introduction").evaluate(
                    """element => [...element.querySelectorAll(
                        'h1, img, li, .introduction-proof'
                    )].every(node => {
                        const box = node.getBoundingClientRect();
                        return box.left >= 0 && box.right <= innerWidth;
                    })"""
                )
                if width <= 600:
                    assert active.locator("h1").evaluate(
                        "heading => heading.getBoundingClientRect().top >= 64"
                    )
                    assert logo.evaluate(
                        """image => {
                            const heading = image.closest('h1').getBoundingClientRect();
                            const logo = image.getBoundingClientRect();
                            return logo.top < heading.top + heading.height / 2;
                        }"""
                    )
                    assert points.last.evaluate(
                        "point => point.getBoundingClientRect().bottom <= innerHeight - 48"
                    )
                    assert proof.evaluate(
                        """element => element.getBoundingClientRect().bottom
                            <= document.querySelector('.introduction-progress button')
                                .getBoundingClientRect().top"""
                    )
                else:
                    proof.scroll_into_view_if_needed()
                    expect(proof).to_be_in_viewport()
                    assert proof.evaluate(
                        """point => point.getBoundingClientRect().bottom
                            <= document.querySelector('.introduction-progress button')
                                .getBoundingClientRect().top"""
                    )
            page.set_viewport_size({"width": 1920, "height": 1080})
            button.click()
            city = "why-vividly/micro-demonstration"
            _wait_for_public_route(page, "vividly", city)
            if not reduced_motion:
                page.wait_for_function(
                    """() => {
                        const s = document.querySelector('vividly-presentation')._current.instance;
                        return s.timing.value > 0 && s.timing.value < 1;
                    }"""
                )
                expect(button).to_be_hidden()
                page.locator("vividly-presentation").evaluate(
                    "async p => { await p._queue; p._current.instance.settleStep(); }"
                )
            expect(progress.get_by_role("progressbar", name="Scene readiness")).to_have_attribute(
                "aria-valuetext", "Ready",
            )
            assert button.evaluate(
                """button => {
                    const b = button.getBoundingClientRect();
                    const c = document.querySelector('.caption-current').getBoundingClientRect();
                    return b.top >= c.bottom;
                }"""
            )
            button.press("Enter")
            page.wait_for_url(f"**/{city}/1")
            page.keyboard.press("ArrowLeft")
            page.wait_for_url(f"**/{city}")
            page.locator("vividly-presentation").evaluate(
                "async p => { await p._queue; p._current.instance.settleStep(); }"
            )
            page.keyboard.press("ArrowLeft")
            _wait_for_public_route(page, "vividly", introduction)
            expect(points).to_have_count(3)
            expect(proof).to_have_css("opacity", "1")
            expect(progress.get_by_role("progressbar")).to_have_attribute(
                "aria-valuetext", "Ready",
            )
            assert active.locator(".introduction").evaluate(
                "element => element.getAnimations({subtree: true}).length"
            ) == 0
            page.keyboard.press("ArrowLeft")
            _wait_for_public_route(page, "vividly", address)
            assert page.url.endswith(f"{address}/1")
            page.keyboard.press("Home")
            page.wait_for_url(f"**/{address}")
            page.keyboard.press("End")
            page.wait_for_url(f"**/{address}/1")
            if not reduced_motion:
                page.locator("vividly-presentation").evaluate(
                    "async p => { await p._queue; p._current.instance.settleStep(); }"
                )
            expect(progress.get_by_role("progressbar")).to_have_attribute("aria-valuetext", "Ready")
            button.click()
            _wait_for_public_route(page, "vividly", introduction)
            page.locator("vividly-presentation").evaluate(
                "async p => { await p._queue; p._current.instance.settleStep(); }"
            )
            expect(progress.get_by_role("progressbar")).to_have_attribute(
                "aria-valuetext", "Ready",
            )
            page.keyboard.press("ArrowRight")
            _wait_for_public_route(page, "vividly", city)
            assert active.locator("vividly-step-progress").count() == 1
            page.keyboard.press("End")
            if not reduced_motion:
                page.locator("vividly-presentation").evaluate(
                    "async p => { await p._queue; p._current.instance.settleStep(); }"
                )
            expect(progress.get_by_role("progressbar")).to_have_attribute("aria-valuetext", "Ready")
            button.click()
            _wait_for_public_route(page, "vividly", "why-vividly/the-partnership")
            for target, steps in ((address, 2), (city, 7)):
                for step in reversed(range(steps)):
                    page.goto(f"{base_url}/#/vividly/{target}/{step}")
                    _wait_for_public_route(page, "vividly", target)
                    page.locator("vividly-presentation").evaluate(
                        "async p => { await p._queue; p._current.instance.settleStep(); }"
                    )
                    expect(progress.get_by_role("progressbar")).to_have_attribute(
                        "aria-valuetext", "Ready",
                    )
                    assert active.locator("vividly-step-progress button").count() == 1
            page.goto(f"{base_url}/#/vividly/{address}/1")
            _wait_for_public_route(page, "vividly", address)
            page.locator("vividly-presentation").evaluate(
                "async p => { await p._queue; p._current.instance.settleStep(); }"
            )
            for width, height in (
                (320, 568), (375, 667), (390, 844), (430, 932), (768, 1024),
                (568, 320), (667, 375), (844, 390), (1920, 1080),
            ):
                page.set_viewport_size({"width": width, "height": height})
                assert active.locator(".promise-beat-owl").evaluate(
                    """beat => {
                        const owl = beat.querySelector('.owl-body').getBoundingClientRect();
                        const copy = beat.querySelector('.promise-copy').getBoundingClientRect();
                        const button = document.querySelector(
                            '.promise-progress button'
                        ).getBoundingClientRect();
                        const separate = owl.left >= copy.right || owl.top >= copy.bottom;
                        return owl.width >= 70 && owl.height >= 100
                            && owl.left >= 0 && owl.right <= innerWidth
                            && owl.top >= 0 && owl.bottom <= button.top
                            && separate;
                    }"""
                ), f"owl is clipped, too small, or overlaps copy at {width}x{height}"
                expect(progress.get_by_role("progressbar")).to_have_attribute(
                    "aria-valuetext", "Ready",
                )
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)
        server_log.close()


@pytest.mark.parametrize("arrival", ["direct", "enter", "click", "home", "end"])
def test_why_vividly_arrival_builds_settle_with_keyboard(
    chromium: None,
    tmp_path: Path,
    arrival: str,
) -> None:
    """Validate destination-arrival custom settling in presentation-orchestration.md."""
    del chromium
    port = _available_port()
    server_log = (tmp_path / "settling-server.log").open("w")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "vividly.cli", "run",
            "--port", str(port), "--no-watch",
        ],
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    try:
        base_url = _wait_for_server(process, port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            route_local_dependencies(page, base_url, REPOSITORY_ROOT / "site")
            page.route(
                "https://cdn.jsdelivr.net/npm/@fontsource/libre-caslon-text@5.3.0/*",
                lambda route: route.fulfill(content_type="text/css", body=""),
            )
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("requestfailed", lambda request: errors.append(request.url))
            address = "why-vividly/complex-ideas-should-move"
            if arrival in ("enter", "click"):
                page.goto(f"{base_url}/#/vividly/opening")
                page.get_by_role("button", name="Start presentation", exact=True).click()
                _wait_for_public_route(page, "vividly", "opening")
                if arrival == "enter":
                    page.keyboard.press("Enter")
                else:
                    page.locator("[data-vividly-navigator-choice='0']").click()
            else:
                suffix = "/1" if arrival == "home" else ""
                page.goto(f"{base_url}/#/vividly/{address}{suffix}")
                _wait_for_public_route(page, "vividly", address)
                if arrival in ("home", "end"):
                    page.keyboard.press(arrival.title())
            _wait_for_public_route(page, "vividly", address)
            active = page.locator(".v-layer:not([hidden])")
            progress = active.get_by_role("progressbar", name="Step readiness")
            first_step = 1 if arrival == "end" else 0
            for step in range(first_step, 2):
                expected_url = f"{base_url}/#/vividly/{address}" + ("/1" if step else "")
                page.wait_for_url(expected_url)
                page.wait_for_function(
                    """() => {
                        const s = document.querySelector('vividly-presentation')._current.instance;
                        return s.progress.value > 0 && s.progress.value < 1;
                    }"""
                )
                page.keyboard.press("ArrowRight")
                expect(progress).to_have_attribute("aria-valuetext", "Ready")
                assert page.url == expected_url
                page.locator("vividly-presentation").evaluate("async p => { await p._queue; }")
                assert page.url == expected_url
                assert page.locator("vividly-presentation").evaluate(
                    """p => {
                        const s = p._current.instance;
                        return s.step === 0
                            ? s.billiards.simulation.resting && !s.billiards.running
                            : s.owlDraw === 1 && s.owlAlignment === 1 && !s.owlAnimation;
                    }"""
                )
                page.keyboard.press("Space")
            _wait_for_public_route(page, "vividly", "why-vividly/introducing-vividly")
            page.locator("vividly-presentation").evaluate(
                "async p => { await p._queue; p._current.instance.settleStep(); }"
            )
            page.keyboard.press("ArrowRight")
            city = "why-vividly/micro-demonstration"
            _wait_for_public_route(page, "vividly", city)
            page.goto(f"{base_url}/#/vividly/{city}/1")
            _wait_for_public_route(page, "vividly", city)
            page.keyboard.press("ArrowRight")
            expect(active.get_by_role("progressbar", name="Scene readiness")).to_have_attribute(
                "aria-valuetext", "Ready",
            )
            page.locator("vividly-presentation").evaluate("async p => { await p._queue; }")
            assert page.url.endswith(f"{city}/1")
            page.keyboard.press("ArrowRight")
            page.wait_for_url(f"**/{city}/2")
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)
        server_log.close()


@pytest.mark.parametrize("direction", [-1, 1])
def test_city_of_loops_settles_toward_navigation_direction(
    chromium: None,
    tmp_path: Path,
    direction: int,
) -> None:
    """Exercise directional settling from presentation-orchestration.md on the city sketch."""
    del chromium
    port = _available_port()
    server_log = (tmp_path / "city-server.log").open("w")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "vividly.cli", "run",
            "--port", str(port), "--no-watch",
        ],
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    try:
        base_url = _wait_for_server(process, port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            route_local_dependencies(page, base_url, REPOSITORY_ROOT / "site")
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            address = "why-vividly/micro-demonstration"
            page.goto(f"{base_url}/#/vividly/{address}")
            _wait_for_public_route(page, "vividly", address)
            heading = page.get_by_role(
                "heading",
                name="Case study: I needed to explain a new way of working.",
                exact=True,
            )
            expect(heading.locator("mark")).to_have_text("Case study:")
            assert heading.locator("mark").evaluate(
                "element => getComputedStyle(element).color"
            ) == "rgb(255, 181, 71)"
            assert heading.locator("mark").evaluate(
                "element => getComputedStyle(element).backgroundColor"
            ) == "rgba(0, 0, 0, 0)"
            scene_keys = page.evaluate(
                """async () => {
                    const { SCENES } = await import(
                        '/slides/why-vividly/city-of-loops/engine.js'
                    );
                    return SCENES.map(scene => scene.key);
                }"""
            )
            step = scene_keys.index("first-loop")
            source = scene_keys.index("drivers" if direction < 0 else "gears")
            target = scene_keys.index("gears" if direction < 0 else "drivers")
            page.goto(f"{base_url}/#/vividly/{address}/{source}")
            _wait_for_public_route(page, "vividly", address)
            key = "ArrowLeft" if direction < 0 else "ArrowRight"
            progress = page.get_by_role("progressbar", name="Scene readiness")
            if direction > 0:
                page.keyboard.press(key)
                expect(progress).to_have_attribute("aria-valuenow", "100")
                page.locator("vividly-presentation").evaluate("async p => { await p._queue; }")
                assert page.url.endswith(f"/micro-demonstration/{source}")
            page.keyboard.press(key)
            page.wait_for_function(
                "step => location.hash.endsWith('/micro-demonstration/' + step)",
                arg=step,
            )
            red_pixels = """() => {
                const canvas = document.querySelector('canvas.is-active');
                const pixels = canvas.getContext('2d')
                    .getImageData(0, 0, canvas.width, canvas.height).data;
                let count = 0;
                for (let i = 0; i < pixels.length; i += 4) {
                    if (pixels[i] > 50 && pixels[i] > pixels[i + 1] * 1.5
                        && pixels[i] > pixels[i + 2] * 1.5) count++;
                }
                return count;
            }"""
            page.wait_for_function(f"() => ({red_pixels})() > 100")
            readiness = progress.get_attribute("aria-valuenow")
            assert readiness is not None
            assert 0 < float(readiness) < 100
            copy = page.locator("#scene-copy")
            copy_box = copy.evaluate("element => element.getBoundingClientRect().toJSON()")
            page.keyboard.press(key)
            expect(page.get_by_role("progressbar", name="Scene readiness")).to_have_attribute(
                "aria-valuenow", "100"
            )
            assert page.url.endswith(f"/micro-demonstration/{step}")
            title = page.locator("#scene-title")
            expect(title).to_be_visible()
            expect(title).to_have_text("The real idea was far more exciting.")
            if direction < 0:
                expect(copy).to_be_hidden()
                expect(copy).to_have_attribute("aria-hidden", "true")
                expect(page.locator(".caption-expansion")).to_be_hidden()
            else:
                expect(copy).to_be_visible()
            assert copy.evaluate("element => element.getBoundingClientRect().toJSON()") == copy_box

            if direction < 0:
                assert page.evaluate(red_pixels) == 0
                expect(copy).to_be_hidden()
            else:
                assert page.evaluate(red_pixels) > 100
            page.wait_for_timeout(500)
            expect(page.get_by_role("progressbar", name="Scene readiness")).to_have_attribute(
                "aria-valuenow", "100"
            )
            if direction < 0:
                assert page.evaluate(red_pixels) == 0
            assert page.locator("canvas.is-outgoing").count() == 0

            page.keyboard.press(key)
            page.wait_for_function(
                "step => location.hash.endsWith('/micro-demonstration/' + step)",
                arg=target,
            )
            expect(copy).not_to_have_attribute("aria-hidden", "true")
            for width in (1920, 1280, 1024, 800, 390):
                page.set_viewport_size({"width": width, "height": 1080})
                assert page.locator(".caption-current").evaluate(
                    """panel => [...panel.children].every(element => {
                        const style = getComputedStyle(element);
                        return Math.abs(parseFloat(style.minHeight)
                            - 2 * parseFloat(style.lineHeight)) < 1;
                    })"""
                )
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)
        server_log.close()


def test_opening_navigator_animation_focus_boundaries_and_hover(
    chromium: None,
    tmp_path: Path,
) -> None:
    """Validate navigator entry and return rules in presentation-threads.md section 3.1."""
    del chromium
    port = _available_port()
    server_log = (tmp_path / "navigator-server.log").open("w")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "vividly.cli", "run",
            "--port", str(port), "--no-watch",
        ],
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    try:
        base_url = _wait_for_server(process, port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            route_local_dependencies(page, base_url, REPOSITORY_ROOT / "site")
            page.route(
                "https://cdn.jsdelivr.net/npm/@fontsource/libre-caslon-text@5.3.0/*",
                lambda route: route.fulfill(content_type="text/css", body=""),
            )
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("requestfailed", lambda request: errors.append(request.url))
            choices = page.locator(".v-layer:not([hidden]) .docs-opening-choice")
            layout = page.locator(".v-layer:not([hidden]) .docs-opening")

            page.goto(f"{base_url}/#/vividly/opening")
            page.get_by_label("Don't show these tips again", exact=True).check()
            page.get_by_role("button", name="Start presentation").click()
            page.reload()
            _wait_for_public_route(page, "vividly", "opening")
            expect(choices.first).to_have_attribute("aria-current", "step")
            expect(choices.first).to_be_focused()
            expect(layout).to_have_class("docs-opening is-complete is-animated")
            history_length = page.evaluate("history.length")
            page.wait_for_function(
                """() => document.querySelector('.docs-opening')
                    .getAnimations({subtree:true}).every(a => a.playState !== 'running')"""
            )
            assert page.url.endswith("#/vividly/opening")
            assert page.evaluate("history.length") == history_length
            assert layout.evaluate(
                """element => {
                    const rect = element.getBoundingClientRect();
                    return rect.left >= 0 && rect.top >= 0
                        && rect.right <= innerWidth && rect.bottom <= innerHeight;
                }"""
            )

            style = """element => {
                const s = getComputedStyle(element);
                return {background: s.backgroundColor, border: s.borderColor,
                    transform: s.transform};
            }"""
            baseline = choices.nth(1).evaluate(style)
            choices.nth(1).hover()
            page.wait_for_function(
                """background => getComputedStyle(document.querySelectorAll(
                    '.v-layer:not([hidden]) .docs-opening-choice')[1]
                ).backgroundColor !== background""",
                arg=baseline["background"],
            )
            hovered = choices.nth(1).evaluate(style)
            assert hovered["border"] == baseline["border"]
            assert hovered["transform"] == baseline["transform"]
            expect(choices.first).to_be_focused()
            expect(choices.first).to_have_attribute("aria-current", "step")
            expect(choices.nth(1)).to_have_attribute("aria-current", "false")
            page.mouse.move(0, 0)

            page.keyboard.press("ArrowLeft")
            _wait_for_public_route(page, "vividly", "opening")
            expect(choices.first).to_be_focused()
            expect(layout).to_have_class("docs-opening is-complete is-animated")
            page.keyboard.press("ArrowRight")
            page.wait_for_function("() => location.hash === '#/vividly/opening/1'")
            expect(choices.nth(1)).to_be_focused()
            expect(layout).to_have_class("docs-opening is-complete")
            page.keyboard.press("ArrowLeft")
            page.wait_for_function("() => location.hash === '#/vividly/opening'")
            page.reload()
            _wait_for_public_route(page, "vividly", "opening")
            expect(layout).to_have_class("docs-opening is-complete is-animated")
            expect(choices.first).to_be_focused()

            page.keyboard.press("Enter")
            _wait_for_public_route(page, "vividly", "why-vividly/complex-ideas-should-move")
            page.keyboard.press("ArrowUp")
            _wait_for_public_route(page, "vividly", "opening")
            expect(choices.first).to_be_focused()
            expect(layout).to_have_class("docs-opening is-complete")
            page.go_back()
            _wait_for_public_route(page, "vividly", "why-vividly/complex-ideas-should-move")
            page.go_forward()
            _wait_for_public_route(page, "vividly", "opening")
            expect(layout).to_have_class("docs-opening is-complete")

            for key in ("ArrowRight", "Space"):
                page.goto(
                    f"{base_url}/?complete={key}"
                    "#/vividly/why-vividly/artifact-versus-medium/3"
                )
                _wait_for_public_route(page, "vividly", "why-vividly/artifact-versus-medium")
                page.keyboard.press(key)
                _wait_for_public_route(page, "vividly", "opening")
                assert page.url.endswith("#/vividly/opening/1"), page.url
                expect(choices.nth(1)).to_be_focused()

            page.goto(f"{base_url}/?return=last#/vividly/make-something/get-started/overview")
            _wait_for_public_route(page, "vividly", "make-something/get-started/overview")
            page.keyboard.press("ArrowUp")
            page.wait_for_url("**#/vividly/make-something/choose-your-path/1")
            expect(page.get_by_role("button", name="Guided Introduction")).to_be_focused()
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => location.hash === '#/vividly/opening/2'")
            expect(choices.nth(2)).to_be_focused()
            page.keyboard.press("ArrowRight")
            _wait_for_public_route(page, "vividly", "documentation/overview")
            page.keyboard.press("ArrowLeft")
            page.wait_for_function("() => location.hash === '#/vividly/opening/2'")
            expect(choices.nth(2)).to_be_focused()
            page.keyboard.press("Space")
            _wait_for_public_route(page, "vividly", "make-something/choose-your-path")
            expect(page.get_by_role("button", name="Fully Agentic")).to_be_focused()

            for key in ("ArrowRight", "Space"):
                page.goto(
                    f"{base_url}/?complete={key}#/vividly/make-something/get-started/publish"
                )
                _wait_for_public_route(page, "vividly", "make-something/get-started/publish")
                page.keyboard.press(key)
                page.wait_for_url("**#/vividly/make-something/choose-your-path/2")
                nested_choices = page.locator(
                    ".v-layer:not([hidden]) [data-vividly-navigator-choice]"
                )
                assert nested_choices.count() == 2
                assert nested_choices.evaluate_all(
                    "cards => cards.every(card => card.tabIndex === -1"
                    " && card.getAttribute('aria-current') === 'false'"
                    " && card !== document.activeElement)"
                )
                page.keyboard.press(key)
                page.wait_for_function("() => location.hash === '#/vividly/opening/3'")
                assert choices.evaluate_all(
                    "cards => cards.every(card => card.tabIndex === -1"
                    " && card.getAttribute('aria-current') === 'false'"
                    " && card !== document.activeElement)"
                )
                page.keyboard.press("ArrowLeft")
                page.wait_for_function("() => location.hash === '#/vividly/opening/2'")
                expect(choices.nth(2)).to_be_focused()
                page.locator("vividly-presentation").evaluate(
                    "presentation => presentation._navigateTo('opening', 3)"
                )
                page.keyboard.press(key)
                _wait_for_public_route(page, "vividly", "documentation/overview")

            page.emulate_media(reduced_motion="reduce")
            page.goto(f"{base_url}/?motion=reduce#/vividly/opening")
            _wait_for_public_route(page, "vividly", "opening")
            expect(layout).to_have_class("docs-opening is-complete")
            expect(choices.first).to_be_focused()
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.communicate(timeout=5)
        server_log.close()
