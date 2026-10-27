"""Horizontal touch contract in docs/specs/touch-navigation.md, sections 2-7."""

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, cast

import pytest
from playwright.sync_api import Browser, Page, expect
from test_runtime import (
    browser as browser,
)
from test_runtime import (
    configure_active_step_transitions,
    open_animation_settling_slide,
    route_navigator_manifest,
    route_thread_manifests,
    wait_for_navigation_queue,
)
from test_runtime import (
    runtime_url as runtime_url,
)


# Playwright's CDP annotations omit payload types.
class TouchProtocol(Protocol):
    def send(self, method: str, params: dict[str, object]) -> object: ...

    def detach(self) -> None: ...


@pytest.fixture
def touch_page(browser: Browser, runtime_url: str) -> Iterator[Page]:
    context = browser.new_context(has_touch=True, viewport={"width": 600, "height": 700})
    page = context.new_page()
    manifest = {
        "id": "touch-test",
        "keyboardHints": "never",
        "theme": "../vividly/themes/dark.css",
        "transition": "cut",
        "nodes": [
            {"type": "slide", "id": name, "module": "../slides/touch-test.js"}
            for name in ["first", "second"]
        ],
    }
    page.route(
        "**/presentations/vividly.yaml",
        lambda route: route.fulfill(content_type="application/yaml", body=json.dumps(manifest)),
    )
    page.route(
        "**/slides/touch-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body="""
                import {Slide} from '../vividly/runtime/slide.js';
                export default class extends Slide {
                    preload() { return {steps: 3}; }
                    mount(root) {
                        root.innerHTML = `
                            <div id="surface" style="height:180px">Swipe surface</div>
                            <button id="control">Control</button>
                            <a id="link" href="#anchor">Link</a>
                            <input id="input">
                            <span id="editable" contenteditable>Editable</span>
                            <div id="widget" role="slider" tabindex="0">Slider</div>
                            <div id="camera" data-vividly-touch-ignore="false"
                                style="height:60px;touch-action:none">
                                <span id="camera-child">Camera</span>
                            </div>
                            <div id="horizontal"
                                style="width:200px;height:60px;overflow-x:auto">
                                <div style="width:800px;height:40px">Horizontal scroll</div>
                            </div>
                            <div id="vertical"
                                style="width:200px;height:100px;overflow-y:auto">
                                <div style="height:800px">Vertical scroll</div>
                            </div>`;
                        root.addEventListener('click', () => {
                            root.dataset.clicks = String(Number(root.dataset.clicks || 0) + 1);
                        });
                    }
                }
            """,
        ),
    )
    page.goto(f"{runtime_url}/#/vividly/first")
    ready(page)
    yield page
    context.close()


def ready(page: Page) -> None:
    page.locator("vividly-presentation[data-render-ready]").wait_for()
    page.wait_for_function(
        "() => !document.querySelector('.v-touch-navigation button')?.disabled"
    )


def swipe(
    page: Page,
    dx: float = -80,
    dy: float = 0,
    *,
    selector: str = "#surface",
    x: float = 300,
    y: float = 80,
    duration: float = 100,
) -> None:
    page.locator(".v-layer:not([hidden])").locator(selector).evaluate(
        """(target, {dx,dy,x,y,duration}) => {
            const dispatch = (type, x, y, at) => {
                const event = new PointerEvent(type, {
                    pointerType:'touch', pointerId:7, isPrimary:true,
                    clientX:x, clientY:y, bubbles:true, composed:true, cancelable:true,
                });
                Object.defineProperty(event, 'timeStamp', {value:at});
                target.dispatchEvent(event);
            };
            dispatch('pointerdown', x, y, 10000);
            dispatch('pointerup', x+dx, y+dy, 10000+duration);
        }""",
        {"dx": dx, "dy": dy, "x": x, "y": y, "duration": duration},
    )
    wait_for_navigation_queue(page)


def native_swipe(
    page: Page, selector: str, dx: int, dy: int, *, root: str = ".v-layer:not([hidden])"
) -> None:
    box = page.locator(root).locator(selector).bounding_box()
    assert box is not None
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    session = cast(TouchProtocol, page.context.new_cdp_session(page))
    try:
        session.send(
            "Input.dispatchTouchEvent",
            {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]},
        )
        for index in range(1, 7):
            session.send(
                "Input.dispatchTouchEvent",
                {
                    "type": "touchMove",
                    "touchPoints": [{"x": x + dx * index / 6, "y": y + dy * index / 6}],
                },
            )
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    finally:
        session.detach()
    wait_for_navigation_queue(page)


@pytest.mark.parametrize(
    ("dx", "dy", "duration", "x", "expected"),
    [
        (-48, 24, 1000, 24, 1),
        (-47, 0, 100, 300, 0),
        (-48, 25, 100, 300, 0),
        (-48, 0, 1001, 300, 0),
        (-80, 0, 100, 23, 0),
        (0, -80, 100, 300, 0),
    ],
)
def test_touch_recognition_boundaries(
    touch_page: Page, dx: int, dy: int, duration: int, x: int, expected: int
) -> None:
    swipe(touch_page, dx, dy, duration=duration, x=x)
    assert touch_page.locator("vividly-presentation").evaluate("(p) => p._step") == expected


def test_touch_traverses_steps_boundaries_and_history(touch_page: Page) -> None:
    page = touch_page
    for route in ["first/1", "first/2", "second"]:
        swipe(page)
        expect(page).to_have_url(f"{page.url.split('#')[0]}#/vividly/{route}")
        ready(page)
    swipe(page, 80)
    page.wait_for_url("**/#/vividly/first/2")
    page.go_back()
    page.wait_for_url("**/#/vividly/second")
    ready(page)
    page.go_forward()
    page.wait_for_url("**/#/vividly/first/2")


@pytest.mark.parametrize(
    "selector",
    ["#control", "#link", "#input", "#editable", "#widget", "#camera-child", "#horizontal"],
)
def test_touch_exclusions(touch_page: Page, selector: str) -> None:
    swipe(touch_page, selector=selector)
    touch_page.wait_for_url("**/#/vividly/first")
    assert touch_page.locator(".v-layer:not([hidden]) #horizontal").evaluate(
        """el => {
            for (;el;el=el.parentElement) {
                if (getComputedStyle(el).touchAction === 'pan-y pinch-zoom') return false;
            }
            return true;
        }"""
    )


def test_native_touch_swipes_and_native_scrolling(touch_page: Page) -> None:
    page = touch_page
    native_swipe(page, "#surface", -100, 0)
    page.wait_for_url("**/#/vividly/first/1")
    ready(page)
    native_swipe(page, "#horizontal", -70, 0)
    page.wait_for_function("document.querySelector('#horizontal').scrollLeft > 0")
    page.wait_for_url("**/#/vividly/first/1")
    native_swipe(page, "#vertical", 0, -45)
    page.wait_for_function("document.querySelector('#vertical').scrollTop > 0")
    page.wait_for_url("**/#/vividly/first/1")


def test_touch_bar_layout_activation_and_overviews(touch_page: Page) -> None:
    page = touch_page
    bar = page.get_by_role("navigation", name="Presentation navigation")
    expect(bar).to_be_visible()
    assert bar.evaluate(
        """bar => {
            const stage = document.querySelector('.v-stage').getBoundingClientRect();
            const buttons = [...bar.querySelectorAll('button')];
            return buttons.every(button => {
                const box = button.getBoundingClientRect();
                return box.width >= 48 && box.height >= 48 && box.top >= stage.bottom;
            });
        }"""
    )
    next_button = bar.get_by_role("button", name="Next", exact=True)
    next_button.focus()
    next_button.press("Space")
    ready(page)
    page.wait_for_url("**/#/vividly/first/1")
    next_button.press("Enter")
    ready(page)
    page.wait_for_url("**/#/vividly/first/2")
    bar.get_by_role("button", name="Previous").click()
    ready(page)
    page.wait_for_url("**/#/vividly/first/1")
    page.keyboard.press("Escape")
    expect(bar).to_be_hidden()
    assert page.locator("vividly-presentation").get_attribute("data-touch-navigation") is None


def test_touch_busy_cancellation_and_overlay_priority(touch_page: Page) -> None:
    page = touch_page
    page.locator(".v-layer:not([hidden]) #surface").evaluate(
        """el => el.dispatchEvent(new PointerEvent('pointerdown', {
            pointerType:'touch',pointerId:7,isPrimary:true,clientX:300,clientY:80,bubbles:true,
        }))"""
    )
    page.locator("vividly-presentation").evaluate("(p) => p._beginRender()")
    page.locator(".v-layer:not([hidden]) #surface").evaluate(
        """el => el.dispatchEvent(new PointerEvent('pointerup', {
            pointerType:'touch',pointerId:7,isPrimary:true,clientX:200,clientY:80,bubbles:true,
        }))"""
    )
    swipe(page)
    page.wait_for_url("**/#/vividly/first")
    page.locator("vividly-presentation").evaluate(
        "(p) => p._settleRender(p._renderGeneration, p._current.layer)"
    )
    ready(page)
    page.keyboard.press("?")
    swipe(page)
    page.wait_for_url("**/#/vividly/first")
    expect(page.get_by_role("button", name="Next", exact=True)).to_be_disabled()
    page.keyboard.press("Escape")
    expect(page.locator(".v-keyboard-help")).to_be_hidden()
    ready(page)
    swipe(page)
    page.wait_for_url("**/#/vividly/first/1")


@pytest.mark.parametrize("cancellation", ["pointercancel", "scroll", "contextmenu", "second-touch"])
def test_touch_cancellation(touch_page: Page, cancellation: str) -> None:
    page = touch_page
    page.locator(".v-layer:not([hidden]) #surface").evaluate(
        """(target, cancellation) => {
            const event = (type, id=7) => target.dispatchEvent(new PointerEvent(type, {
                pointerId:id, pointerType:'touch', isPrimary:id===7, bubbles:true,
                clientX:type==='pointerup'?200:300, clientY:80,
            }));
            event('pointerdown');
            if (cancellation==='second-touch') {
                event('pointerdown', 8);
                event('pointerup', 8);
            } else if (cancellation==='pointercancel') event('pointercancel');
            else target.dispatchEvent(new Event(cancellation, {bubbles:true}));
            event('pointerup');
        }""",
        cancellation,
    )
    wait_for_navigation_queue(page)
    page.wait_for_url("**/#/vividly/first")
    swipe(page)
    page.wait_for_url("**/#/vividly/first/1")


@pytest.mark.skipif(
    sys.platform == "linux",
    reason="Linux Chromium does not attribute a tap after a native swipe to the slide",
)
def test_touch_click_attribution_and_next_tap(touch_page: Page) -> None:
    page = touch_page
    swipe(page)
    ready(page)
    result = page.locator(".v-layer:not([hidden]) #surface").evaluate(
        """target => {
            const click = (pointerId, pointerType) => target.dispatchEvent(
                new PointerEvent('click', {
                    pointerId,pointerType,bubbles:true,cancelable:true,
                }));
            return [click(7,'touch'), click(-1,'')];
        }"""
    )
    assert result == [False, True]
    assert page.locator(".v-layer:not([hidden]) .v-slide").get_attribute("data-clicks") == "1"
    native_swipe(page, "#surface", -80, 0)
    ready(page)
    page.locator(".v-layer:not([hidden]) #control").tap()
    expect(page.locator(".v-layer:not([hidden]) .v-slide")).to_have_attribute("data-clicks", "2")


def test_touch_dynamic_exclusions_and_entire_slide_opt_out(touch_page: Page) -> None:
    page = touch_page
    page.locator(".v-layer:not([hidden]) #surface").evaluate(
        """el => {
            el.innerHTML = '<div id="late" style="overflow-x:auto;width:150px">'
                + '<div style="width:600px">Scrollable</div></div>'
                + '<div id="late-surface">Swipe here</div>';
        }"""
    )
    page.wait_for_function(
        "() => document.querySelector('#late-surface').hasAttribute('data-vividly-touch-surface')"
    )
    swipe(page, selector="#late")
    page.wait_for_url("**/#/vividly/first")
    swipe(page, selector="#late-surface")
    page.wait_for_url("**/#/vividly/first/1")
    ready(page)
    page.locator(".v-layer:not([hidden]) .v-slide").evaluate(
        "el => el.setAttribute('data-vividly-touch-ignore', '')"
    )
    swipe(page, selector="#late-surface")
    page.wait_for_url("**/#/vividly/first/1")
    page.get_by_role("button", name="Next", exact=True).click()
    ready(page)
    page.wait_for_url("**/#/vividly/first/2")


def test_touch_open_shadow_widgets_and_mouse_pen_input(touch_page: Page) -> None:
    page = touch_page
    page.locator(".v-layer:not([hidden]) #surface").evaluate(
        """el => {
            const host = document.createElement('div');
            host.id = 'shadow-host';
            host.attachShadow({mode:'open'}).innerHTML =
                '<button id="shadow-control">Shadow control</button>'
                + '<div id="shadow-surface">Shadow surface</div>';
            el.append(host);
        }"""
    )
    page.wait_for_function(
        """() => document.querySelector('#shadow-host').shadowRoot
            .querySelector('#shadow-surface').hasAttribute('data-vividly-touch-surface')"""
    )
    swipe(page, selector="#shadow-control")
    page.wait_for_url("**/#/vividly/first")
    swipe(page, selector="#shadow-surface")
    ready(page)
    page.wait_for_url("**/#/vividly/first/1")
    for pointer_type in ["mouse", "pen"]:
        page.locator(".v-layer:not([hidden]) #surface").evaluate(
            """(el, pointerType) => {
                for (const type of ['pointerdown','pointerup']) {
                    el.dispatchEvent(new PointerEvent(type, {
                        pointerType,pointerId:9,isPrimary:true,bubbles:true,
                        clientX:type==='pointerdown'?300:200,clientY:80,
                    }));
                }
            }""",
            pointer_type,
        )
        wait_for_navigation_queue(page)
        page.wait_for_url("**/#/vividly/first/1")


def test_touch_zoom_rejection_and_boundary_no_ops(touch_page: Page) -> None:
    page = touch_page
    history_length = page.evaluate("history.length")
    swipe(page, 80)
    assert page.evaluate("history.length") == history_length
    session = cast(TouchProtocol, page.context.new_cdp_session(page))
    try:
        session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 2})
        page.wait_for_function("visualViewport.scale > 1")
        swipe(page, x=80)
        page.wait_for_url("**/#/vividly/first")
        session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
        page.wait_for_function("visualViewport.scale === 1")
    finally:
        session.detach()
    swipe(page)
    ready(page)
    page.wait_for_url("**/#/vividly/first/1")
    page.locator("vividly-presentation").evaluate("(p) => p._navigateTo('second', 2)")
    ready(page)
    history_length = page.evaluate("history.length")
    swipe(page)
    page.wait_for_url("**/#/vividly/second/2")
    assert page.evaluate("history.length") == history_length


def test_touch_footer_small_viewports_and_disposal(touch_page: Page) -> None:
    page = touch_page
    for width, height in [(390, 844), (320, 568), (844, 390)]:
        page.set_viewport_size({"width": width, "height": height})
        ready(page)
        assert page.locator(".v-touch-navigation").evaluate(
            """bar => {
                const stage = document.querySelector('.v-stage').getBoundingClientRect();
                const help = document.querySelector('.v-help-trigger').getBoundingClientRect();
                return [...bar.querySelectorAll('button')].every(button => {
                    const box = button.getBoundingClientRect();
                    return box.left >= 24 && box.right <= innerWidth-24
                        && box.top >= stage.bottom && box.bottom <= innerHeight-24
                        && box.width >= 48 && box.height >= 48 && help.bottom <= box.top;
                });
            }"""
        )
    assert page.locator("vividly-presentation").evaluate(
        """p => {
            const touch = p._touch;
            const root = p._current.root;
            p.remove();
            return touch.controller.signal.aborted && !touch.bar.isConnected
                && !root.querySelector('[data-vividly-touch-surface]')
                && !root.hasAttribute('data-vividly-touch-surface')
                && !p.hasAttribute('data-touch-navigation');
        }"""
    )


def test_touch_navigator_uses_structural_not_spatial_traversal(
    browser: Browser, runtime_url: str
) -> None:
    with browser.new_context(has_touch=True) as context:
        page = context.new_page()
        route_navigator_manifest(page)
        page.goto(f"{runtime_url}/#/vividly/book/chapter/overview")
        ready(page)
        page.get_by_role("button", name="Next", exact=True).click()
        ready(page)
        page.wait_for_url("**/#/vividly/book/chapter/topic-a/first")
        page.get_by_role("button", name="Previous", exact=True).click()
        ready(page)
        page.wait_for_url("**/#/vividly/book/chapter/overview")


def test_touch_preserves_animation_settling(browser: Browser, runtime_url: str) -> None:
    with browser.new_context(has_touch=True) as context:
        page = context.new_page()
        open_animation_settling_slide(page, runtime_url, "css")
        ready(page)
        next_button = page.get_by_role("button", name="Next", exact=True)
        next_button.click()
        ready(page)
        configure_active_step_transitions(page, elapsed_ms=700, paused=True)
        next_button.click()
        ready(page)
        page.wait_for_url("**/#/vividly/css/1")
        next_button.click()
        ready(page)
        page.wait_for_url("**/#/vividly/css/2")

def test_touch_dynamic_steps_and_custom_settling(browser: Browser, runtime_url: str) -> None:
    with browser.new_context(has_touch=True) as context:
        page = context.new_page()
        open_animation_settling_slide(page, runtime_url, "dynamic")
        ready(page)
        swipe(page, selector=".v-slide")
        ready(page)
        root = page.locator(".v-layer:not([hidden]) .v-slide")
        expect(root).to_have_attribute("data-dynamic-step", "1")
        swipe(page, 80, selector=".v-slide")
        ready(page)
        expect(root).to_have_attribute("data-dynamic-step", "0")
        open_animation_settling_slide(page, runtime_url, "custom")
        ready(page)
        swipe(page, selector=".v-slide")
        ready(page)
        page.wait_for_url("**/#/vividly/custom/1")
        swipe(page, selector=".v-slide")
        ready(page)
        page.wait_for_url("**/#/vividly/custom/1")
        expect(page.locator(".v-layer:not([hidden]) [data-custom-state]")).to_have_text("settled")
        swipe(page, selector=".v-slide")
        ready(page)
        page.wait_for_url("**/#/vividly/custom/2")


def test_tic_tac_toe_camera_retains_touch_drag(touch_page: Page) -> None:
    page = touch_page
    demo = Path(__file__).resolve().parents[1] / "site/slides/tic-tac-toe/demo"
    source = (demo / "camera.js").read_text(encoding="utf-8")
    template = (demo / "template.html").read_text(encoding="utf-8")
    assert page.evaluate(
        """html => {
            const template = document.createElement('template');
            template.innerHTML = html;
            return template.content.querySelector('#viewport')
                .hasAttribute('data-vividly-touch-ignore');
        }""",
        template,
    )
    page.route(
        "**/camera-test.js",
        lambda route: route.fulfill(content_type="text/javascript", body=source),
    )
    page.locator(".v-layer:not([hidden]) #camera").evaluate(
        """async viewport => {
            const {StageCamera} = await import('/camera-test.js');
            const camera = document.createElement('div');
            camera.textContent = 'Camera content';
            viewport.replaceChildren(camera);
            const controller = new StageCamera(viewport, camera, {});
            viewport.addEventListener('test-dispose', () => controller.destroy(), {once:true});
        }"""
    )
    native_swipe(page, "#camera", -60, 0)
    page.wait_for_function(
        "() => document.querySelector('#camera > div').style.transform.includes('-60px')"
    )
    page.wait_for_url("**/#/vividly/first")
    page.locator(".v-layer:not([hidden]) #camera").evaluate(
        "el => el.dispatchEvent(new Event('test-dispose'))"
    )


@pytest.mark.parametrize(("dx", "dy"), [(-80, 0), (0, -120)])
def test_touch_onboarding_gestures_do_not_dismiss(
    browser: Browser, runtime_url: str, dx: int, dy: int
) -> None:
    with browser.new_context(has_touch=True, viewport={"width": 390, "height": 360}) as context:
        page = context.new_page()
        page.goto(f"{runtime_url}/#/vividly/opening/title-card")
        hints = page.locator(".v-keyboard-hints")
        expect(hints).to_be_visible()
        hints.locator("summary").tap()
        assert hints.get_attribute("data-closing") is None
        panel = hints.locator(".v-keyboard-hints-panel")
        assert panel.evaluate("el => el.scrollHeight > el.clientHeight")
        native_swipe(page, ".v-keyboard-hints-panel", dx, dy, root=".v-keyboard-hints")
        if dy:
            page.wait_for_function(
                "() => document.querySelector('.v-keyboard-hints-panel').scrollTop > 0"
            )
        assert hints.get_attribute("data-closing") is None
        expect(hints).to_be_visible()
        assert page.locator(".v-layer:not([hidden])").count() == 0
        assert page.url.endswith("#/vividly/opening/title-card")


def test_touch_onboarding_help_and_failed_thread_recovery(
    browser: Browser, runtime_url: str
) -> None:
    with browser.new_context(has_touch=True, viewport={"width": 390, "height": 844}) as context:
        page = context.new_page()
        page.goto(f"{runtime_url}/#/vividly/opening/title-card")
        hints = page.locator(".v-keyboard-hints")
        expect(hints).to_be_visible()
        expect(hints.locator("p.v-touch-instructions")).to_be_visible()
        expect(hints.get_by_text("Continue to the next step")).to_be_hidden()
        hints.locator("summary").tap()
        assert hints.get_attribute("data-closing") is None
        expect(hints.get_by_text("Continue to the next step")).to_be_visible()
        hints.get_by_role("button", name="Start presentation").click()
        ready(page)
        page.get_by_role("button", name="Keyboard shortcuts").click()
        expect(page.locator(".v-keyboard-help .v-touch-instructions")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator(".v-keyboard-help")).to_be_hidden()
        ready(page)
        route_thread_manifests(page)
        page.goto(f"{runtime_url}/?thread-touch-check=1#/vividly/opening/title-card/1")
        ready(page)
        result = page.locator("vividly-presentation").evaluate(
            """async p => {
                try {
                    await p.createThread('broken-thread', {route:'broken'});
                    return 'unexpected success';
                } catch (error) { return error.message; }
            }"""
        )
        assert "missing-thread.js" in result
        ready(page)
        assert page.url.endswith("#/vividly/opening/title-card/1")
        page.get_by_role("button", name="Next", exact=True).click()
        wait_for_navigation_queue(page)
        ready(page)
        assert page.url.endswith("#/vividly/opening/title-card/2"), page.locator(
            "vividly-presentation"
        ).evaluate(
            """p => ({hash:location.hash,step:p._step,index:p._index,
                pending:p._touch.pending.size,available:p._touch.available(),
                suppress:p._suppressHistoryWrites})"""
        )


def test_touch_bar_absent_without_touch_and_in_captures(browser: Browser, runtime_url: str) -> None:
    with browser.new_context() as context:
        page = context.new_page()
        page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        expect(page.locator(".v-touch-navigation")).to_be_hidden()
        assert page.locator("vividly-presentation").get_attribute("data-touch-navigation") is None
    with browser.new_context(has_touch=True) as context:
        page = context.new_page()
        page.goto(f"{runtime_url}/?vividly-capture=1#/vividly/opening/title-card/1")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        expect(page.locator(".v-touch-navigation")).to_be_hidden()
