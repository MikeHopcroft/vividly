"""Viewer settings contract in docs/specs/viewer-settings.md."""

import json

import pytest
from playwright.sync_api import Browser, Page, expect
from test_runtime import (
    browser as browser,
)
from test_runtime import route_thread_manifests, wait_for_navigation_queue
from test_runtime import (
    runtime_url as runtime_url,
)
from test_touch_navigation import swipe
from test_touch_navigation import (
    touch_page as touch_page,
)


def open_settings(page: Page) -> None:
    page.get_by_role("button", name="Settings", exact=True).click()
    expect(page.get_by_role("dialog", name="Settings", exact=True)).to_be_visible()


def test_settings_modal_preserves_state_and_returns_to_help(touch_page: Page) -> None:
    page = touch_page
    before = page.locator("vividly-presentation").evaluate(
        """p => [location.href, history.length, p._step, p._threadId, p._generation,
            p._renderGeneration]"""
    )
    trigger = page.get_by_role("button", name="Settings", exact=True)
    trigger.focus()
    page.keyboard.press("Space")
    dialog = page.get_by_role("dialog", name="Settings", exact=True)
    navigation = dialog.get_by_label("Navigation controls")
    expect(navigation).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(dialog.get_by_role("button", name="Close")).to_be_focused()
    page.keyboard.press("Tab")
    expect(navigation).to_be_focused()
    page.keyboard.press("a")
    page.keyboard.press("ArrowRight")
    expect(dialog).to_be_visible()
    expect(page.locator(".v-touch-navigation button").first).to_be_disabled()
    swipe(page)
    page.keyboard.press("Escape")
    expect(trigger).to_be_focused()
    assert page.locator("vividly-presentation").evaluate(
        """p => [location.href, history.length, p._step, p._threadId, p._generation,
            p._renderGeneration]"""
    ) == before

    page.keyboard.press("?")
    help_overlay = page.locator(".v-keyboard-help")
    help_overlay.get_by_role("button", name="Settings").click()
    expect(help_overlay).to_be_hidden()
    dialog.get_by_role("button", name="Close").click()
    expect(help_overlay).to_be_visible()
    expect(help_overlay.get_by_role("button", name="Settings")).to_be_focused()
    page.keyboard.press("Escape")
    expect(help_overlay).to_be_hidden()
    expect(trigger).to_be_focused()


def test_hidden_footer_preserves_swipes_and_reclaims_space(touch_page: Page) -> None:
    page = touch_page
    stage = page.locator(".v-stage")
    initial_height = stage.evaluate("el => el.clientHeight")
    open_settings(page)
    dialog = page.get_by_role("dialog", name="Settings", exact=True)
    dialog.get_by_label("Navigation controls").select_option("hide")
    expect(dialog.get_by_label("Navigation controls")).to_be_focused()
    dialog.get_by_role("button", name="Close").click()
    expect(page.locator(".v-touch-navigation")).to_be_hidden()
    assert stage.evaluate("el => el.clientHeight") > initial_height
    swipe(page)
    page.wait_for_url("**/#/vividly/first/1")
    open_settings(page)
    dialog.get_by_label("Navigation controls").select_option("show")
    dialog.get_by_role("button", name="Close").click()
    expect(page.locator(".v-touch-navigation")).to_be_visible()
    assert stage.evaluate("el => el.clientHeight") == initial_height
    page.reload()
    page.locator("vividly-presentation[data-render-ready]").wait_for()
    open_settings(page)
    expect(dialog.get_by_label("Navigation controls")).to_have_value("show")


def test_settings_cancels_an_in_progress_swipe(touch_page: Page) -> None:
    page = touch_page
    surface = page.locator(".v-layer:not([hidden]) #surface")
    surface.evaluate(
        """el => el.dispatchEvent(new PointerEvent('pointerdown', {
            pointerType:'touch', pointerId:7, isPrimary:true, bubbles:true,
            clientX:300, clientY:80,
        }))"""
    )
    assert page.locator("vividly-presentation").evaluate("p => !!p._touch.candidate")
    open_settings(page)
    page.keyboard.press("Escape")
    surface.evaluate(
        """el => el.dispatchEvent(new PointerEvent('pointerup', {
            pointerType:'touch', pointerId:7, isPrimary:true, bubbles:true,
            clientX:200, clientY:80,
        }))"""
    )
    wait_for_navigation_queue(page)
    assert page.url.endswith("#/vividly/first")


@pytest.mark.parametrize("viewport", [{"width": 320, "height": 480},
                                    {"width": 1280, "height": 800}])
def test_settings_layout_and_targets(
    touch_page: Page, viewport: dict[str, int]
) -> None:
    page = touch_page
    page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})
    assert page.locator(".v-settings-trigger").evaluate(
        """el => {
            const box = el.getBoundingClientRect();
            const helpTrigger = document.querySelector('.v-help-trigger');
            const help = helpTrigger.getBoundingClientRect();
            const circle = getComputedStyle(el, '::before');
            const helpCircle = getComputedStyle(helpTrigger, '::before');
            return box.width >= 48 && box.height >= 48 && box.left >= 0
                && box.right <= help.left && box.bottom <= innerHeight
                && box.width === help.width && box.height === help.height
                && box.top === help.top && circle.width === helpCircle.width
                && circle.height === helpCircle.height;
        }"""
    )
    open_settings(page)
    dialog = page.get_by_role("dialog", name="Settings", exact=True)
    assert dialog.evaluate(
        """el => {
            const box = el.getBoundingClientRect();
            return box.left >= 0 && box.top >= 0 && box.right <= innerWidth
                && box.bottom <= innerHeight && el.scrollWidth <= el.clientWidth;
        }"""
    )
    dialog.get_by_role("button", name="Close").click()
    expect(dialog).to_be_hidden()


def test_help_settings_link_treatment_and_themed_scrollbars(touch_page: Page) -> None:
    page = touch_page
    page.set_viewport_size({"width": 320, "height": 480})
    page.keyboard.press("?")
    help_overlay = page.locator(".v-keyboard-help")
    settings = help_overlay.get_by_role("button", name="Settings")
    assert settings.evaluate(
        """el => {
            const style = getComputedStyle(el);
            const link = getComputedStyle(el.parentElement.querySelector('a'));
            return style.backgroundColor === 'rgba(0, 0, 0, 0)'
                && style.borderTopWidth === '0px'
                && style.font === link.font && style.color === link.color
                && style.textDecorationLine.includes('underline');
        }"""
    )
    panel = help_overlay.locator(".v-keyboard-help-panel")
    assert panel.evaluate(
        """el => el.scrollHeight > el.clientHeight &&
            getComputedStyle(el).scrollbarColor !== 'auto' &&
            getComputedStyle(el).scrollbarColor.endsWith('rgba(0, 0, 0, 0)')"""
    )
    settings.click()
    dialog = page.get_by_role("dialog", name="Settings", exact=True)
    expect(dialog).to_be_visible()
    assert dialog.evaluate("el => getComputedStyle(el).scrollbarColor !== 'auto'")


@pytest.mark.parametrize(
    ("touch", "fine", "hover", "visible"),
    [(True, False, False, True), (True, True, True, False),
     (True, True, False, True), (False, True, True, False)],
)
def test_navigation_auto_and_explicit_overrides(
    browser: Browser, runtime_url: str, touch: bool, fine: bool, hover: bool, visible: bool
) -> None:
    with browser.new_context(has_touch=touch) as context:
        page = context.new_page()
        page.add_init_script(
            "(() => { const state = " + json.dumps(
                {"(pointer: fine)": fine, "(hover: hover)": hover}
            ) + """;
                const original = window.matchMedia.bind(window);
                const queries = [];
                window.matchMedia = query => {
                    if (!(query in state)) return original(query);
                    const media = new EventTarget();
                    Object.defineProperty(media, 'matches', {get: () => state[query]});
                    queries.push(media);
                    return media;
                };
                window.changePrimaryPointer = () => {
                    state['(pointer: fine)'] = !state['(pointer: fine)'];
                    state['(hover: hover)'] = !state['(hover: hover)'];
                    queries.forEach(query => query.dispatchEvent(new Event('change')));
                };
            })();"""
        )
        page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        bar = page.locator(".v-touch-navigation")
        assert bar.is_visible() is visible
        if touch and fine and hover:
            page.evaluate("window.changePrimaryPointer()")
            expect(bar).to_be_visible()
        open_settings(page)
        dialog = page.get_by_role("dialog", name="Settings", exact=True)
        for value in ["show", "hide", "auto"]:
            dialog.get_by_label("Navigation controls").select_option(value)
            if value != "auto":
                assert bar.is_visible() is (value == "show")
        dialog.get_by_label("Navigation controls").select_option("show")
        dialog.get_by_role("button", name="Close").click()
        page.locator(".v-touch-navigation").get_by_role("button", name="Previous").click()
        wait_for_navigation_queue(page)
        page.wait_for_url("**/#/vividly/opening/title-card")


@pytest.mark.parametrize("route", ["#/", "#/vividly/", "#/vividly/opening/title-card/1"])
def test_settings_access_and_route_change(
    browser: Browser, runtime_url: str, route: str
) -> None:
    with browser.new_page() as page:
        page.goto(f"{runtime_url}/{route}")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        open_settings(page)
        dialog = page.get_by_role("dialog", name="Settings", exact=True)
        page.mouse.click(1, 1)
        expect(dialog).to_be_hidden()
        open_settings(page)
        destination = "#/vividly/" if route == "#/" else "#/"
        page.evaluate("(hash) => { location.hash = hash; }", destination)
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        expect(dialog).to_be_hidden()
        assert page.evaluate(
            """() => document.activeElement.isConnected &&
                !!document.activeElement.getClientRects().length"""
        )


@pytest.mark.parametrize(
    ("policy", "checked", "disabled"),
    [("auto", False, False), ("always", True, True), ("never", False, True)],
)
def test_hint_setting_reuses_saved_preference_and_preserves_overrides(
    browser: Browser, runtime_url: str, policy: str, checked: bool, disabled: bool
) -> None:
    with browser.new_page() as page:
        route_thread_manifests(page)
        page.route(
            "**/presentations/vividly.yaml",
            lambda route: route.fulfill(
                content_type="application/yaml",
                body=json.dumps({
                    "id": "settings",
                    "keyboardHints": policy,
                    "nodes": [{"type": "slide", "id": "first",
                               "module": "../slides/thread-test.js"}],
                }),
            ),
        )
        key = f"vividly:{runtime_url}/catalog.yaml:~runtime"
        page.add_init_script(
            f"""localStorage.setItem({json.dumps(key)}, JSON.stringify({{
                '~keyboardHints': {{suppressed: true}}
            }}));"""
        )
        page.goto(f"{runtime_url}/?vividly-skip-hints=1#/vividly/first")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        open_settings(page)
        dialog = page.get_by_role("dialog", name="Settings", exact=True)
        hints = dialog.get_by_label("Show initial hint dialog")
        assert hints.is_checked() is checked
        assert hints.is_disabled() is disabled
        expect(dialog.locator(".v-settings-query")).to_be_visible()
        if policy == "auto":
            hints.check()
            dialog.get_by_role("button", name="Close").click()
            expect(page.locator(".v-keyboard-hints")).to_be_hidden()
            page.keyboard.press("?")
            expect(
                page.get_by_label("Show navigation hints when presentations start")
            ).to_be_checked()
        else:
            assert page.evaluate(
                "(key) => JSON.parse(localStorage.getItem(key))['~keyboardHints'].suppressed",
                key,
            )
            dialog.get_by_role("button", name="Close").click()
            page.evaluate("location.hash = '#/'")
            page.locator(".v-catalog").wait_for(state="visible")
            open_settings(page)
            expect(hints).to_be_enabled()
            expect(hints).not_to_be_checked()


def test_enabling_initial_hints_waits_for_next_eligible_activation(
    browser: Browser, runtime_url: str
) -> None:
    with browser.new_page() as page:
        page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        open_settings(page)
        dialog = page.get_by_role("dialog", name="Settings", exact=True)
        dialog.get_by_label("Show initial hint dialog").uncheck()
        page.keyboard.press("Escape")
        page.goto(f"{runtime_url}/#/vividly/opening/title-card")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        expect(page.locator(".v-keyboard-hints")).to_be_hidden()
        open_settings(page)
        dialog.get_by_label("Show initial hint dialog").check()
        page.keyboard.press("Escape")
        expect(page.locator(".v-keyboard-hints")).to_be_hidden()
        page.reload()
        hints = page.locator(".v-keyboard-hints")
        expect(hints).to_be_visible()
        hints.get_by_label("Don't show these tips again").check()
        page.keyboard.press("?")
        page.locator(".v-keyboard-help").get_by_role("button", name="Settings").click()
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        expect(dialog.get_by_label("Show initial hint dialog")).not_to_be_checked()


@pytest.mark.parametrize("failure", ["read", "write"])
def test_settings_storage_failure_is_visible_and_choice_still_applies(
    browser: Browser, runtime_url: str, failure: str
) -> None:
    with browser.new_page() as page:
        method = "getItem" if failure == "read" else "setItem"
        page.add_init_script(
            f"""Storage.prototype.{method} = () => {{ throw new Error('Storage unavailable'); }};"""
        )
        page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        open_settings(page)
        dialog = page.get_by_role("dialog", name="Settings", exact=True)
        dialog.get_by_label("Navigation controls").select_option("show")
        expect(dialog.get_by_role("status")).to_contain_text("could not be saved")
        dialog.get_by_role("button", name="Close").click()
        expect(page.locator(".v-touch-navigation")).to_be_visible()


def test_settings_preferences_span_presentations_but_not_catalogs(
    browser: Browser, runtime_url: str
) -> None:
    with browser.new_page() as page:
        route_thread_manifests(page)
        page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        open_settings(page)
        dialog = page.get_by_role("dialog", name="Settings", exact=True)
        dialog.get_by_label("Navigation controls").select_option("show")
        dialog.get_by_label("Show initial hint dialog").uncheck()
        dialog.get_by_role("button", name="Close").click()
        page.locator("vividly-presentation").evaluate(
            "p => p.createThread('thread-a', {route: 'first'})"
        )
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        expect(page.locator(".v-touch-navigation")).to_be_visible()
        page.goto(f"{runtime_url}/#/vividly/opening/title-card")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        expect(page.locator(".v-keyboard-hints")).to_be_hidden()
        open_settings(page)
        expect(dialog.get_by_label("Navigation controls")).to_have_value("show")
        expect(dialog.get_by_label("Show initial hint dialog")).not_to_be_checked()
        index = page.request.get(f"{runtime_url}/").text()
        page.route(
            "**/isolated.html",
            lambda route: route.fulfill(
                content_type="text/html",
                body=index.replace('catalog="./catalog.yaml"', 'catalog="./other-catalog.yaml"'),
            ),
        )
        page.route(
            "**/other-catalog.yaml",
            lambda route: route.fulfill(
                content_type="application/yaml",
                body=json.dumps({"version": 1, "presentations": [{
                    "id": "vividly", "title": "Isolated",
                    "manifest": "./presentations/vividly.yaml",
                }]}),
            ),
        )
        page.goto(f"{runtime_url}/isolated.html#/vividly/opening/title-card/1")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        open_settings(page)
        expect(dialog.get_by_label("Navigation controls")).to_have_value("auto")
        expect(dialog.get_by_label("Show initial hint dialog")).to_be_checked()


def test_invalid_navigation_preference_and_capture(
    browser: Browser, runtime_url: str
) -> None:
    with browser.new_page() as page:
        key = f"vividly:{runtime_url}/catalog.yaml:~runtime"
        page.add_init_script(
            f"""localStorage.setItem({json.dumps(key)}, JSON.stringify({{
                '~viewerSettings': {{navigation: 'invalid'}}
            }}));"""
        )
        page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        open_settings(page)
        expect(page.get_by_label("Navigation controls")).to_have_value("auto")
        page.goto(f"{runtime_url}/?vividly-capture=1#/vividly/opening/title-card/1")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        expect(page.locator(".v-settings-trigger")).to_be_hidden()
        page.locator("vividly-presentation").evaluate("p => p._settings.show()")
        expect(page.locator(".v-settings")).to_be_hidden()
