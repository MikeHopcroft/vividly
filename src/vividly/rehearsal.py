"""User-driven cache-only rehearsal for a Vividly project."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Page, Response, Route, WebSocketRoute, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from .browser import chromium_launch_error_message
from .composition import compose_project
from .dependencies import DependencyCache, default_dependency_cache_root
from .server import DEPENDENCY_PREFIX, serve_composition

type RehearsalIssueKind = Literal[
    "browser-error",
    "cache-miss",
    "external-request",
    "external-websocket",
]


class RehearsalError(RuntimeError):
    """A rehearsal could not be started or completed."""


@dataclass(frozen=True)
class RehearsalIssue:
    """One failure observed during a rehearsal."""

    kind: RehearsalIssueKind
    route: str
    url: str
    detail: str


@dataclass(frozen=True)
class RehearsalResult:
    """The bounded result of one user-driven rehearsal."""

    issues: tuple[RehearsalIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


type RehearsalInteraction = Callable[[Page], None]


def _route_label(page_url: str) -> str:
    fragment = urlsplit(page_url).fragment
    return fragment.removeprefix("/") or "(catalog)"


def _is_local_url(url: str, local_origin: str) -> bool:
    candidate = urlsplit(url)
    local = urlsplit(local_origin)
    scheme = {"ws": "http", "wss": "https"}.get(candidate.scheme, candidate.scheme)
    return (
        scheme == local.scheme
        and candidate.hostname == local.hostname
        and candidate.port == local.port
    )


def _wait_for_user(page: Page) -> None:
    del page
    try:
        input(
            "Rehearsal browser is ready. Exercise the intended presentation path, "
            "then press Enter here to finish: "
        )
    except EOFError as error:
        raise RehearsalError("input ended before rehearsal was explicitly finished") from error


def rehearse_project(
    project_root: Path,
    *,
    cache_root: Path | None = None,
    headless: bool = False,
    interact: RehearsalInteraction = _wait_for_user,
    browser: Browser | None = None,
) -> RehearsalResult:
    """Run one fresh, cache-only, user-driven browser rehearsal."""
    selected_cache_root = cache_root or default_dependency_cache_root()
    cache = DependencyCache(selected_cache_root, cache_only=True)
    with (
        compose_project(project_root) as composition,
        serve_composition(composition, dependency_cache=cache) as base_url,
    ):
        if browser is not None:
            return _rehearse_in_browser(browser, base_url, interact)
        with sync_playwright() as playwright:
            try:
                launched_browser = playwright.chromium.launch(headless=headless)
            except PlaywrightError as error:
                raise RehearsalError(chromium_launch_error_message(error)) from error
            try:
                return _rehearse_in_browser(launched_browser, base_url, interact)
            finally:
                if launched_browser.is_connected():
                    launched_browser.close()


def _rehearse_in_browser(
    browser: Browser,
    base_url: str,
    interact: RehearsalInteraction,
) -> RehearsalResult:
    issues: list[RehearsalIssue] = []
    seen: set[tuple[RehearsalIssueKind, str, str, str]] = set()

    def record(kind: RehearsalIssueKind, page_url: str, url: str, detail: str) -> None:
        issue_key = (kind, _route_label(page_url), url, detail)
        if issue_key in seen:
            return
        seen.add(issue_key)
        issues.append(
            RehearsalIssue(
                kind=kind,
                route=issue_key[1],
                url=url,
                detail=detail,
            )
        )

    context = browser.new_context(service_workers="block")
    page: Page | None = None
    try:

        def handle_request(route: Route) -> None:
            request_url = route.request.url
            if urlsplit(request_url).scheme not in {"http", "https"}:
                route.continue_()
                return
            current_page_url = page.url if page is not None else route.request.frame.page.url
            if _is_local_url(request_url, base_url):
                route.continue_()
                return
            record(
                "external-request",
                current_page_url,
                request_url,
                "blocked external HTTP(S) request",
            )
            route.abort("blockedbyclient")

        def handle_websocket(websocket: WebSocketRoute) -> None:
            current_page_url = page.url if page is not None else base_url
            if _is_local_url(websocket.url, base_url):
                websocket.connect_to_server()
                return
            record(
                "external-websocket",
                current_page_url,
                websocket.url,
                "blocked external WebSocket connection",
            )

        context.route("**/*", handle_request)
        context.route_web_socket("**/*", handle_websocket)
        page = context.new_page()

        def handle_response(response: Response) -> None:
            response_url = response.url
            response_status = response.status
            parsed = urlsplit(response_url)
            if (
                response_status == 504
                and _is_local_url(response_url, base_url)
                and parsed.path.startswith(DEPENDENCY_PREFIX)
            ):
                record(
                    "cache-miss",
                    page.url,
                    response_url,
                    "dependency was not present in the Vividly cache",
                )

        def observe_page(observed: Page) -> None:
            observed.on(
                "pageerror",
                lambda error: record(
                    "browser-error",
                    page.url,
                    observed.url,
                    str(error),
                ),
            )
            observed.on(
                "crash",
                lambda _: record(
                    "browser-error",
                    page.url,
                    observed.url,
                    "browser page crashed",
                ),
            )

        context.on("page", observe_page)
        observe_page(page)
        context.on("response", handle_response)
        page.goto(base_url, wait_until="domcontentloaded")
        interact(page)
        if page.is_closed():
            record(
                "browser-error",
                base_url,
                base_url,
                "browser was closed before rehearsal finished",
            )
        else:
            page.wait_for_timeout(100)
    except PlaywrightError as error:
        raise RehearsalError(f"browser rehearsal failed: {error}") from error
    finally:
        if browser.is_connected():
            context.close()

    return RehearsalResult(issues=tuple(issues))
