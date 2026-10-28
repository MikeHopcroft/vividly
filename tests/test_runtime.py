"""Browser tests for the runtime contract in docs/specs/presentation-orchestration.md."""

import functools
import http.server
import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest
import yaml
from playwright.sync_api import Browser, Error, Page, Position, expect, sync_playwright
from runtime_site import (
    FIXTURE_ROOT,
    assembled_runtime_site,
    route_static_dependencies,
)

THUMBNAIL_REVISION = "a" * 64


class QuietRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve the fixture presentation without writing request logs."""

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture(scope="module")
def runtime_url() -> Iterator[str]:
    with assembled_runtime_site() as site_root:
        handler = functools.partial(QuietRequestHandler, directory=str(site_root))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as error:
            if "Executable doesn't exist" in str(error):
                pytest.skip("run 'vividly install-browser' before browser runtime tests")
            raise
        yield browser
        browser.close()


def wait_for_navigation_queue(page: Page) -> None:
    page.locator("vividly-presentation").evaluate(
        "async (presentation) => { await presentation._queue; }"
    )


def finish_active_step_transitions(page: Page) -> None:
    page.locator(".v-layer:not([hidden])").evaluate(
        """(layer) => layer.getAnimations({subtree: true})
            .filter((animation) => animation instanceof CSSTransition)
            .forEach((animation) => animation.finish())"""
    )


def configure_active_step_transitions(
    page: Page,
    elapsed_ms: float,
    *,
    remaining_ms: float | list[float] = 1000,
    playback_rate: float = 1,
    paused: bool = False,
    advance_delta: int | None = None,
) -> None:
    page.locator("vividly-presentation").evaluate(
        """async (presentation, options) => {
            await presentation._queue;
            const transitions = [...presentation._current.stepMotion.transitions];
            const remaining = Array.isArray(options.remainingMs)
                ? options.remainingMs
                : transitions.map(() => options.remainingMs);
            if (!transitions.length || transitions.length !== remaining.length) {
                throw new Error(
                    `expected ${remaining.length} tracked transitions, got ${transitions.length}`
                );
            }
            const motion = presentation._current.stepMotion;
            motion.startedAt = performance.now() - options.elapsedMs;
            await Promise.all(transitions.map(async (animation, index) => {
                const effect = animation.effect;
                animation.currentTime =
                    Number(effect.getComputedTiming().endTime)
                    - remaining[index] * Math.abs(options.playbackRate || 1);
                animation.playbackRate = options.playbackRate;
                if (options.paused) {
                    animation.pause();
                    await animation.ready;
                }
            }));
            if (options.advanceDelta !== null) {
                await presentation._advanceNow(
                    options.advanceDelta,
                    true,
                    motion.startedAt + options.elapsedMs
                );
                await presentation._settleRender(
                    presentation._renderGeneration,
                    presentation._current.layer
                );
            }
        }""",
        {
            "elapsedMs": elapsed_ms,
            "remainingMs": remaining_ms,
            "playbackRate": playback_rate,
            "paused": paused,
            "advanceDelta": advance_delta,
        },
    )


def route_navigator_manifest(
    page: Page,
    *,
    root_choice_start_step: int | None = None,
) -> None:
    def slide(slide_id: str, **extra: object) -> dict[str, Any]:
        return {
            "type": "slide",
            "id": slide_id,
            "module": "../slides/navigator-test.js",
            **extra,
        }

    root_navigator: dict[str, Any] = {"sections": ["./chapter"]}
    if root_choice_start_step is not None:
        root_navigator["choiceStartStep"] = root_choice_start_step

    manifest: dict[str, Any] = {
        "id": "navigator-test",
        "title": "Navigator Test",
        "keyboardHints": "never",
        "nodes": [
            {
                "type": "section",
                "id": "book",
                "children": [
                    slide("overview", navigator=root_navigator),
                    {
                        "type": "section",
                        "id": "chapter",
                        "children": [
                            slide(
                                "overview",
                                navigator={"sections": ["./topic-a", "./topic-b"]},
                            ),
                            {
                                "type": "section",
                                "id": "topic-a",
                                "children": [slide("first"), slide("second")],
                            },
                            {
                                "type": "section",
                                "id": "topic-b",
                                "children": [slide("only")],
                            },
                        ],
                    },
                ],
            },
            slide("outro"),
        ],
    }
    page.route(
        "**/presentations/vividly.yaml",
        lambda route: route.fulfill(content_type="application/yaml", body=json.dumps(manifest)),
    )
    page.route(
        "**/slides/navigator-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=(
                "import { Slide } from '../vividly/runtime/slide.js';"
                "export default class NavigatorTestSlide extends Slide {"
                "preload(){return {steps:this.ctx.navigator"
                "?this.ctx.navigator.afterStep+1:1};}"
                "mount(root){"
                "if(!this.ctx.navigator){root.textContent=this.ctx.address;return;}"
                "this.ctx.navigator.sections.forEach((section,index)=>{"
                "const button=document.createElement('button');"
                "button.dataset.vividlyNavigatorChoice=index;"
                "button.textContent=section.title;"
                "root.append(button);"
                "});"
                "const after=document.createElement('button');"
                "after.dataset.vividlyNavigatorAfter='';"
                "after.textContent='Continue';"
                "root.append(after);"
                "}"
                "}"
            ),
        ),
    )


def route_spatial_navigator_manifest(page: Page) -> None:
    sections = ["alpha", "beta", "gamma", "delta", "epsilon"]
    manifest: dict[str, Any] = {
        "id": "spatial-navigator-test",
        "title": "Spatial Navigator Test",
        "keyboardHints": "never",
        "nodes": [
            {
                "type": "slide",
                "id": "navigator",
                "module": "../slides/spatial-navigator-test.js",
                "navigator": {
                    "sections": [f"./{section_id}" for section_id in sections],
                },
            },
            *[
                {
                    "type": "section",
                    "id": section_id,
                    "children": [
                        {
                            "type": "slide",
                            "id": "only",
                            "module": "../slides/spatial-navigator-test.js",
                        }
                    ],
                }
                for section_id in sections
            ],
            {
                "type": "slide",
                "id": "outro",
                "module": "../slides/spatial-navigator-test.js",
            },
        ],
    }
    page.route(
        "**/presentations/vividly.yaml",
        lambda route: route.fulfill(content_type="application/yaml", body=json.dumps(manifest)),
    )
    page.route(
        "**/slides/spatial-navigator-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=(
                "import { Slide } from '../vividly/runtime/slide.js';"
                "export default class SpatialNavigatorTestSlide extends Slide {"
                "preload(){return {steps:this.ctx.navigator"
                "?this.ctx.navigator.afterStep+1:1};}"
                "mount(root){"
                "if(!this.ctx.navigator){root.textContent=this.ctx.address;return;}"
                "const grid=document.createElement('div');"
                "grid.dataset.spatialGrid='';"
                "grid.style.display='grid';"
                "grid.style.gridTemplateColumns='repeat(auto-fit,minmax(180px,1fr))';"
                "grid.style.gap='10px';"
                "grid.style.width='calc(100vw - 40px)';"
                "this.ctx.navigator.sections.forEach((section,index)=>{"
                "const button=document.createElement('button');"
                "button.dataset.vividlyNavigatorChoice=index;"
                "button.textContent=section.title;"
                "button.style.height='60px';"
                "grid.append(button);"
                "});"
                "const after=document.createElement('button');"
                "after.dataset.vividlyNavigatorAfter='';"
                "after.textContent='Continue';"
                "root.append(grid,after);"
                "}"
                "}"
            ),
        ),
    )


def route_animation_settling_manifest(page: Page) -> None:
    def slide(
        slide_id: str,
        mode: str,
        *,
        steps: int | None = None,
        **extra: object,
    ) -> dict[str, Any]:
        props: dict[str, object] = {"mode": mode}
        if steps is not None:
            props["steps"] = steps
        return {
            "type": "slide",
            "id": slide_id,
            "module": "../slides/animation-settling-test.js",
            "props": props,
            **extra,
        }

    manifest: dict[str, Any] = {
        "id": "animation-settling-test",
        "title": "Animation Settling Test",
        "keyboardHints": "never",
        "nodes": [
            slide("intro", "static", steps=1),
            slide("css", "css", steps=4),
            slide("custom", "custom", steps=3),
            slide("ambient", "ambient", steps=2),
            slide("dynamic", "dynamic"),
            slide(
                "navigator",
                "navigator",
                navigator={"sections": ["./alpha", "./beta"]},
            ),
            {
                "type": "section",
                "id": "alpha",
                "children": [slide("only", "static", steps=1)],
            },
            {
                "type": "section",
                "id": "beta",
                "children": [slide("only", "static", steps=1)],
            },
            slide("outro", "static", steps=1),
        ],
    }
    page.route(
        "**/presentations/vividly.yaml",
        lambda route: route.fulfill(content_type="application/yaml", body=json.dumps(manifest)),
    )
    page.route(
        "**/slides/animation-settling-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=(
                "import { DYNAMIC, Slide } from '../vividly/runtime/slide.js';"
                "export const meta={styles:['./animation-settling-test.css']};"
                "export default class AnimationSettlingTestSlide extends Slide {"
                "preload(){"
                "if(this.ctx.navigator)return {steps:this.ctx.navigator.afterStep+1};"
                "return {steps:this.ctx.props.mode==='dynamic'"
                "?DYNAMIC:this.ctx.props.steps};"
                "}"
                "mount(root){"
                "this.root=root;"
                "this.dynamicStep=0;"
                "root.dataset.mode=this.ctx.props.mode;"
                "root.dataset.setStepCalls='0';"
                "root.dataset.settleCalls='0';"
                "root.dataset.stepEvents='0';"
                "root.dataset.slideEnterEvents='0';"
                "const motion=document.createElement('div');"
                "motion.dataset.stepMotion='';"
                "const secondaryMotion=document.createElement('div');"
                "secondaryMotion.dataset.stepMotionSecondary='';"
                "root.append(motion,secondaryMotion);"
                "if(this.ctx.props.mode==='custom'){"
                "const state=document.createElement('output');"
                "state.dataset.customState='';"
                "root.append(state);"
                "}"
                "if(this.ctx.props.mode==='ambient'){"
                "const ambient=document.createElement('div');"
                "ambient.dataset.ambient='';"
                "const keyframe=document.createElement('div');"
                "keyframe.dataset.keyframe='';"
                "root.append(ambient,keyframe);"
                "}"
                "if(this.ctx.props.mode==='dynamic'){"
                "root.dataset.dynamicStep='0';"
                "}"
                "if(this.ctx.navigator){"
                "this.ctx.navigator.sections.forEach((section,index)=>{"
                "const button=document.createElement('button');"
                "button.dataset.vividlyNavigatorChoice=index;"
                "button.textContent=section.title;"
                "root.append(button);"
                "});"
                "}"
                "this.ctx.bus.on('vividly:step',()=>{"
                "root.dataset.stepEvents=String(Number(root.dataset.stepEvents)+1);"
                "});"
                "this.ctx.bus.on('vividly:slide-enter',()=>{"
                "root.dataset.slideEnterEvents="
                "String(Number(root.dataset.slideEnterEvents)+1);"
                "});"
                "}"
                "setStep(step){"
                "this.root.dataset.setStepCalls="
                "String(Number(this.root.dataset.setStepCalls)+1);"
                "if(this.ctx.props.mode!=='custom')return;"
                "clearTimeout(this.timer);"
                "this.timer=null;"
                "const state=this.root.querySelector('[data-custom-state]');"
                "if(step===1){"
                "state.value='running';"
                "this.timer=setTimeout(()=>{"
                "this.timer=null;"
                "state.value='settled';"
                "},30000);"
                "}else{state.value='idle';}"
                "}"
                "advance(delta){"
                "if(this.ctx.props.mode!=='dynamic')return false;"
                "const next=this.dynamicStep+delta;"
                "if(next<0||next>2)return false;"
                "this.dynamicStep=next;"
                "this.root.dataset.dynamicStep=String(next);"
                "this.root.style.setProperty('--dynamic-step',next);"
                "return true;"
                "}"
                "settleStep(){"
                "this.root.dataset.settleCalls="
                "String(Number(this.root.dataset.settleCalls)+1);"
                "if(!this.timer)return false;"
                "clearTimeout(this.timer);"
                "this.timer=null;"
                "this.root.querySelector('[data-custom-state]').value='settled';"
                "return true;"
                "}"
                "unmount(){clearTimeout(this.timer);}"
                "}"
            ),
        ),
    )
    page.route(
        "**/slides/animation-settling-test.css",
        lambda route: route.fulfill(
            content_type="text/css",
            body=(
                ":scope[data-mode='css'] [data-step-motion],"
                ":scope[data-mode='css'] [data-step-motion-secondary],"
                ":scope[data-mode='navigator'] [data-step-motion],"
                ":scope[data-mode='navigator'] [data-step-motion-secondary]{"
                "transform:translateX(calc(var(--step) * 20px));"
                "transition:transform 5s linear;"
                "}"
                ":scope[data-mode='dynamic'] [data-step-motion],"
                ":scope[data-mode='dynamic'] [data-step-motion-secondary]{"
                "transform:translateX(calc(var(--dynamic-step, 0) * 20px));"
                "transition:transform 5s linear;"
                "}"
                ":scope[data-mode='ambient'] [data-ambient]{"
                "animation:settling-ambient 30s linear infinite;"
                "}"
                ":scope[data-mode='ambient'][data-step='1'] [data-keyframe]{"
                "animation:settling-keyframe 30s linear;"
                "}"
                "@keyframes settling-ambient{from{opacity:.9}to{opacity:1}}"
                "@keyframes settling-keyframe{from{transform:none}"
                "to{transform:translateX(20px)}}"
            ),
        ),
    )


def open_animation_settling_slide(page: Page, runtime_url: str, route: str) -> None:
    route_animation_settling_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/{route}")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )




def route_thread_manifests(page: Page) -> None:
    def manifest(manifest_id: str, title: str) -> str:
        return json.dumps(
            {
                "id": manifest_id,
                "title": title,
                "theme": f"./{manifest_id}.css",
                "keyboardHints": "never",
                "nodes": [
                    {
                        "type": "slide",
                        "id": "first",
                        "module": "./thread-test.js",
                    },
                    {
                        "type": "slide",
                        "id": "second",
                        "module": "./thread-test.js",
                    },
                ],
            }
        )

    page.route(
        "**/catalog.yaml",
        lambda route: route.fulfill(
            content_type="application/yaml",
            body=json.dumps(
                {
                    "version": 1,
                    "presentations": [
                        {
                            "id": "vividly",
                            "title": "Vividly Runtime Shakedown",
                            "manifest": "./presentations/vividly.yaml",
                        },
                        {
                            "id": "thread-a",
                            "title": "Thread A",
                            "manifest": "./slides/thread-a.yaml",
                        },
                        {
                            "id": "thread-b",
                            "title": "Thread B",
                            "manifest": "./slides/thread-b.yaml",
                        },
                        {
                            "id": "broken-thread",
                            "title": "Broken Thread",
                            "manifest": "./slides/broken-thread.yaml",
                        },
                    ],
                }
            ),
        ),
    )
    page.route(
        "**/slides/thread-a.yaml",
        lambda route: route.fulfill(
            content_type="application/yaml",
            body=manifest("thread-a", "Thread A"),
        ),
    )
    page.route(
        "**/slides/thread-b.yaml",
        lambda route: route.fulfill(
            content_type="application/yaml",
            body=manifest("thread-b", "Thread B"),
        ),
    )
    page.route(
        "**/slides/thread-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=(
                "import { Slide } from '../vividly/runtime/slide.js';"
                "export default class ThreadTestSlide extends Slide {"
                "mount(root){root.innerHTML='<input>';window.threadMounts="
                "(window.threadMounts||0)+1;}"
                "unmount(){window.threadUnmounts=(window.threadUnmounts||0)+1;}"
                "dispose(){window.threadDisposals=(window.threadDisposals||0)+1;}"
                "}"
            ),
        ),
    )
    page.route(
        "**/slides/thread-*.css",
        lambda route: route.fulfill(
            content_type="text/css",
            body=(
                "@import url('../vividly/themes/dark.css');"
                ":root { --thread-test-theme: loaded; }"
            ),
        ),
    )
    page.route(
        "**/slides/broken-thread.yaml",
        lambda route: route.fulfill(
            content_type="application/yaml",
            body=json.dumps(
                {
                    "id": "broken-thread",
                    "title": "Broken Thread",
                    "nodes": [
                        {
                            "type": "slide",
                            "id": "broken",
                            "module": "./missing-thread.js",
                        }
                    ],
                }
            ),
        ),
    )


def start_presentation(page: Page) -> None:
    page.locator(".v-keyboard-hints").get_by_role(
        "button", name="Start presentation"
    ).click()


def route_multi_presentation_project(page: Page) -> None:
    page.route(
        "**/catalog.yaml",
        lambda route: route.fulfill(
            content_type="application/yaml",
            body=json.dumps(
                {
                    "version": 1,
                    "presentations": [
                        {
                            "id": "alpha",
                            "title": "Alpha Presentation",
                            "manifest": "./presentations/alpha.yaml",
                        },
                        {
                            "id": "beta",
                            "title": "Beta Presentation",
                            "manifest": "./presentations/beta.yaml",
                        },
                        {
                            "id": "gamma",
                            "title": "Gamma Presentation",
                            "manifest": "./presentations/gamma.yaml",
                        },
                    ],
                }
            ),
        ),
    )

    def manifest(presentation_id: str, label: str) -> str:
        return json.dumps(
            {
                "id": presentation_id,
                "title": f"{label} Presentation",
                "keyboardHints": "never",
                "nodes": [
                    {
                        "type": "slide",
                        "id": "shared",
                        "module": "../slides/multi-presentation-test.js",
                        "props": {"label": f"{label} shared"},
                    },
                    {
                        "type": "slide",
                        "id": "end",
                        "module": "../slides/multi-presentation-test.js",
                        "props": {"label": f"{label} end"},
                    },
                ],
            }
        )

    page.route(
        "**/presentations/alpha.yaml",
        lambda route: route.fulfill(
            content_type="application/yaml",
            body=manifest("alpha", "Alpha"),
        ),
    )
    page.route(
        "**/presentations/beta.yaml",
        lambda route: route.fulfill(
            content_type="application/yaml",
            body=manifest("beta", "Beta"),
        ),
    )
    page.route(
        "**/presentations/gamma.yaml",
        lambda route: route.fulfill(
            content_type="application/yaml",
            body=manifest("gamma", "Gamma"),
        ),
    )
    page.route(
        "**/slides/multi-presentation-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=(
                "import { Slide } from '../vividly/runtime/slide.js';"
                "export default class MultiPresentationTestSlide extends Slide {"
                "mount(root){"
                "root.dataset.instance=this.ctx.props.label;"
                "const label=document.createElement('p');"
                "label.textContent=this.ctx.props.label;"
                "const count=document.createElement('output');"
                "count.textContent=this.ctx.state.get('count',0);"
                "const button=document.createElement('button');"
                "button.textContent='Increment';"
                "button.addEventListener('click',()=>{"
                "const next=Number(count.textContent)+1;"
                "count.textContent=next;"
                "this.ctx.state.set('count',next);"
                "});"
                "root.append(label,count,button);"
                "}"
                "}"
            ),
        ),
    )


@pytest.mark.parametrize("tag", ["vividly-markdown", "vividly-annotated-markdown"])
def test_markdown_rebases_relative_assets_and_links(
    browser: Browser, runtime_url: str, tag: str
) -> None:
    """Validate the Markdown URL contract in the packaged controls reference."""
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/mechanics/markdown-controls")
    page.wait_for_selector("vividly-markdown h1")
    result = page.evaluate(
        """({tag, base}) => {
            const viewer = document.createElement(tag);
            viewer.baseUrl = `${base}/content/intro/notes.md`;
            viewer.value = [
                '<img id="relative" src="./assets/network.png">',
                '<a id="parent" href="../guide.md?mode=demo#details">Guide</a>',
                '<a id="query" href="?mode=demo">Query</a>',
                '<a id="fragment" href="#/tic-tac-toe/demo">Demo</a>',
                '<a id="root" href="/vividly/guide">Root</a>',
                '<a id="protocol" href="//example.com/guide">Protocol</a>',
                '<a id="absolute" href="https://example.com/guide">Absolute</a>',
                '<a id="mail" href="mailto:demo@example.com">Mail</a>',
                '<img id="data" src="data:image/png;base64,AA==">',
                '<a id="empty" href="">Empty</a>',
                '<release-status id="custom" source="./release.json"></release-status>',
            ].join('\\n');
            document.body.append(viewer);
            const attributes = () => Object.fromEntries(
                [...viewer.querySelectorAll('[id]')].map((element) => [
                    element.id,
                    element.getAttribute(element.tagName === 'IMG' ? 'src'
                        : element.tagName === 'A' ? 'href' : 'source')
                ])
            );
            const initial = attributes();
            viewer.setAttribute('base-url', `${base}/other/notes.md`);
            const changed = attributes().relative;
            viewer.removeAttribute('base-url');
            const removed = attributes().relative;
            viewer.remove();
            return {initial, changed, removed};
        }""",
        {"tag": tag, "base": runtime_url},
    )
    assert result["initial"] == {
        "relative": f"{runtime_url}/content/intro/assets/network.png",
        "parent": f"{runtime_url}/content/guide.md?mode=demo#details",
        "query": f"{runtime_url}/content/intro/notes.md?mode=demo",
        "fragment": "#/tic-tac-toe/demo",
        "root": "/vividly/guide",
        "protocol": "//example.com/guide",
        "absolute": "https://example.com/guide",
        "mail": "mailto:demo@example.com",
        "data": "data:image/png;base64,AA==",
        "empty": "",
        "custom": "./release.json",
    }
    assert result["changed"] == f"{runtime_url}/other/assets/network.png"
    assert result["removed"] == "./assets/network.png"
    page.close()


@pytest.mark.parametrize("tag", ["vividly-markdown", "vividly-annotated-markdown"])
def test_markdown_source_url_follows_redirects_and_clears_for_inline_value(
    browser: Browser, runtime_url: str, tag: str
) -> None:
    page = browser.new_page()
    page.route(
        "**/source/notes.md",
        lambda route: route.fulfill(
            status=302,
            headers={"Location": "/slides/markdown-controls/assets/rebasing.md"},
        ),
    )
    page.goto(f"{runtime_url}/#/vividly/mechanics/markdown-controls")
    page.wait_for_selector("vividly-markdown h1")
    result = page.evaluate(
        """async ({tag, base}) => {
            const viewer = document.createElement(tag);
            viewer.id = 'source-test';
            viewer.src = `${base}/source/notes.md`;
            const rendered = new Promise((resolve, reject) => {
                viewer.addEventListener('vividly-rendered', resolve, {once: true});
                viewer.addEventListener('vividly-error',
                    (event) => reject(event.detail.error), {once: true});
            });
            document.body.append(viewer);
            await rendered;
            const source = viewer.querySelector('img').getAttribute('src');
            const link = viewer.querySelector('a').getAttribute('href');
            viewer.baseUrl = `${base}/override/notes.md`;
            const override = viewer.querySelector('img').getAttribute('src');
            viewer.baseUrl = null;
            const restored = viewer.querySelector('img').getAttribute('src');
            viewer.value = '<img src="./inline.png">';
            const inline = viewer.querySelector('img').getAttribute('src');
            return {source, link, override, restored, inline, src: viewer.src};
        }""",
        {"tag": tag, "base": runtime_url},
    )
    assert result == {
        "source": f"{runtime_url}/slides/markdown-controls/assets/network.png",
        "link": f"{runtime_url}/slides/markdown-controls/assets/guide.md",
        "override": f"{runtime_url}/override/network.png",
        "restored": f"{runtime_url}/slides/markdown-controls/assets/network.png",
        "inline": "./inline.png",
        "src": "",
    }
    page.close()


@pytest.mark.parametrize("module", ["markdown", "annotated-markdown"])
def test_markdown_slide_rebases_assets_against_document_in_data_root(
    browser: Browser, runtime_url: str, module: str
) -> None:
    page = browser.new_page()
    page.route(
        "**/slides/introduction/docs/notes.md",
        lambda route: route.fulfill(
            content_type="text/markdown",
            body='<img src="../assets/network.png">\n<a href="./guide.md">Guide</a>',
        ),
    )
    page.goto(f"{runtime_url}/#/vividly/mechanics/markdown-controls")
    page.wait_for_selector("vividly-markdown h1")
    result = page.evaluate(
        """async ({module, base}) => {
            const {default: Slide} = await import(`/vividly/slides/${module}.js`);
            const {SlideContext} = await import('/vividly/runtime/context.js');
            const slide = new Slide(new SlideContext({
                moduleUrl: `${base}/vividly/slides/${module}.js`,
                dataUrl: `${base}/slides/introduction/`,
                props: {src: './docs/notes.md'},
            }));
            await slide.preload();
            const root = document.createElement('div');
            document.body.append(root);
            slide.mount(root);
            const result = {
                image: root.querySelector('img').getAttribute('src'),
                link: root.querySelector('a').getAttribute('href'),
            };
            slide.unmount();
            root.remove();
            return result;
        }""",
        {"module": module, "base": runtime_url},
    )
    assert result == {
        "image": f"{runtime_url}/slides/introduction/assets/network.png",
        "link": f"{runtime_url}/slides/introduction/docs/guide.md",
    }
    page.close()


def test_project_catalog_lists_registered_presentations(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    assert page.get_by_role("navigation", name="Project catalog").is_visible()
    assert page.get_by_role("link", name="Vividly Runtime Shakedown").get_attribute("href") == (
        "#/vividly/"
    )
    assert page.evaluate("document.querySelector('vividly-presentation').threads.length") == 0
    assert page.evaluate("history.state.vividly.threadId") is None


def test_malformed_module_css_cannot_escape_its_scope(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.route(
        "**/slides/style-isolation/slide.css",
        lambda route: route.fulfill(
            content_type="text/css",
            body=(
                ":scope { color: rgb(1, 2, 3); }\n"
                "}\n"
                '.leak-target::after { content: "scoped"; }\n'
            ),
        ),
    )
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")

    result = page.evaluate(
        """async () => {
            const moduleId = 'malformed-style-test';
            const root = document.createElement('div');
            root.dataset.vividlyModule = moduleId;
            const inside = document.createElement('div');
            inside.className = 'leak-target';
            root.append(inside);
            const outside = document.createElement('div');
            outside.className = 'leak-target';
            document.body.append(root, outside);

            const { adoptModuleStyles } =
                await import('/vividly/runtime/styles.js');
            await adoptModuleStyles(
                moduleId,
                `${location.origin}/slides/style-isolation/slide.js`,
                ['./slide.css'],
            );

            const result = {
                rootColor: getComputedStyle(root).color,
                insideContent: getComputedStyle(inside, '::after').content,
                outsideContent: getComputedStyle(outside, '::after').content,
            };
            root.remove();
            outside.remove();
            return result;
        }"""
    )

    assert result == {
        "rootColor": "rgb(1, 2, 3)",
        "insideContent": "none",
        "outsideContent": "none",
    }


def test_project_catalog_lists_multiple_presentations(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/")
    page.get_by_role("navigation", name="Project catalog").wait_for(state="visible")

    assert page.get_by_role("link", name="Alpha Presentation").get_attribute("href") == (
        "#/alpha/"
    )
    assert page.get_by_role("link", name="Beta Presentation").get_attribute("href") == "#/beta/"


def test_cold_routes_keep_navigation_within_selected_presentation(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/?root=alpha#/alpha/shared")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    assert page.locator('[data-instance="Alpha shared"]').is_visible()
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**#/alpha/end")
    assert page.locator('[data-instance="Alpha end"]').is_visible()
    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**#/alpha/shared")

    page.goto(f"{runtime_url}/?root=beta#/beta/shared")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._presentationId === 'beta'
                && presentation.hasAttribute('data-render-ready');
        }"""
    )
    assert page.locator('[data-instance="Beta shared"]').is_visible()
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**#/beta/end")
    assert page.locator('[data-instance="Beta end"]').is_visible()


def test_suspended_animation_frames_do_not_block_cross_presentation_routes(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.add_init_script("window.requestAnimationFrame = () => 1;")
    page.goto(f"{runtime_url}/#/alpha/shared")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._presentationId === 'alpha'
                && presentation.hasAttribute('data-render-ready');
        }""",
        polling=50,
    )

    page.evaluate("location.hash = '#/beta/shared'")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._presentationId === 'beta'
                && presentation.hasAttribute('data-render-ready');
        }""",
        polling=50,
    )

    assert page.locator('[data-instance="Beta shared"]').is_visible()
    assert page.title() == "Beta Presentation"


@pytest.mark.parametrize("destination_slide_count", [1, 2])
def test_deferred_preload_stays_with_its_original_runtime(
    browser: Browser,
    runtime_url: str,
    destination_slide_count: int,
) -> None:
    """Validate disposal isolation during handoff in presentation-threads.md."""
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.route(
        "**/presentations/beta.yaml",
        lambda route: route.fulfill(
            content_type="application/yaml",
            body=json.dumps(
                {
                    "id": "beta",
                    "title": "Beta Presentation",
                    "keyboardHints": "never",
                    "nodes": [
                        {
                            "type": "slide",
                            "id": address,
                            "module": "../slides/multi-presentation-test.js",
                            "props": {"label": f"Beta {address}"},
                        }
                        for address in ("shared", "end")[:destination_slide_count]
                    ],
                }
            ),
        ),
    )
    page.add_init_script(
        """window.pendingPreloads = [];
        window.requestIdleCallback = callback => window.pendingPreloads.push(callback);"""
    )
    try:
        page.goto(f"{runtime_url}/#/alpha/shared")
        page.wait_for_function(
            """() => {
                const p = document.querySelector('vividly-presentation');
                return p?._presentationId === 'alpha'
                    && p.hasAttribute('data-render-ready')
                    && window.pendingPreloads.length === 1;
            }"""
        )
        page.evaluate(
            """() => {
                window.sourcePreloads = window.pendingPreloads.splice(0);
                location.hash = '#/beta/shared';
            }"""
        )
        page.wait_for_function(
            """() => {
                const p = document.querySelector('vividly-presentation');
                return p?._presentationId === 'beta'
                    && p.hasAttribute('data-render-ready');
            }"""
        )
        calls = page.evaluate(
            """async () => {
                const p = document.querySelector('vividly-presentation');
                const preload = p._preload;
                const calls = [];
                p._preload = function(leaf) {
                    calls.push({
                        address: leaf?.address,
                        currentRuntime: leaf?.runtimeToken === this._runtimeToken,
                    });
                    return preload.call(this, leaf);
                };
                try {
                    await Promise.all(window.sourcePreloads.map(callback => callback()));
                } finally {
                    p._preload = preload;
                }
                return calls;
            }"""
        )
        assert calls == [{"address": "end", "currentRuntime": False}]
        assert page.locator('[data-instance="Beta shared"]').is_visible()
        assert page.locator('[data-instance="Beta end"]').count() == 0
    finally:
        page.close()


def test_shared_slide_state_is_scoped_to_presentation(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/?root=alpha#/alpha/shared")
    alpha = page.locator('[data-instance="Alpha shared"]')
    alpha.wait_for(state="visible")
    alpha.get_by_role("button", name="Increment").click()
    assert alpha.locator("output").text_content() == "1"

    page.goto(f"{runtime_url}/?root=beta#/beta/shared")
    beta = page.locator('[data-instance="Beta shared"]')
    beta.wait_for(state="visible")
    assert beta.locator("output").text_content() == "0"
    beta.get_by_role("button", name="Increment").click()
    beta.get_by_role("button", name="Increment").click()
    assert beta.locator("output").text_content() == "2"

    page.goto(f"{runtime_url}/?root=alpha-again#/alpha/shared")
    alpha.wait_for(state="visible")
    assert alpha.locator("output").text_content() == "1"


def test_create_thread_switches_by_registered_presentation_id(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/alpha/shared")
    page.locator('[data-instance="Alpha shared"]').wait_for(state="visible")

    result = page.evaluate(
        """async () => {
            const presentation = document.querySelector('vividly-presentation');
            const threadId = await presentation.createThread('beta', {route: 'shared'});
            let rejected = false;
            try {
                await presentation.createThread('./presentations/beta.yaml');
            } catch {
                rejected = true;
            }
            return {threadId, rejected, threads: presentation.threads};
        }"""
    )

    assert page.locator('[data-instance="Beta shared"]').is_visible()
    assert page.url.endswith("#/beta/shared")
    assert result["rejected"] is True
    assert result["threads"][0]["id"] == result["threadId"]
    assert result["threads"][0]["presentationId"] == "beta"
    assert "manifestUrl" not in result["threads"][0]


def test_history_traverses_catalog_presentations(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/alpha/shared")
    page.locator('[data-instance="Alpha shared"]').wait_for(state="visible")
    alpha_thread_id = page.evaluate(
        "document.querySelector('vividly-presentation').threads[0].id"
    )

    page.evaluate(
        """async () => {
            const presentation = document.querySelector('vividly-presentation');
            await presentation.createThread('beta', {route: 'shared'});
        }"""
    )
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**#/beta/end")
    page.evaluate(
        """presentation => presentation.createThread('gamma', {
            route: 'shared',
        })""",
        page.locator("vividly-presentation").element_handle(),
    )
    page.wait_for_url("**#/gamma/shared")
    page.evaluate(
        "(threadId) => document.querySelector('vividly-presentation').selectThread(threadId)",
        alpha_thread_id,
    )
    page.wait_for_url("**#/alpha/shared")

    for expected_hash, expected_id in [
        ("#/gamma/shared", "gamma"),
        ("#/beta/end", "beta"),
    ]:
        page.go_back()
        page.wait_for_function(
            """expected => {
                const presentation = document.querySelector('vividly-presentation');
                return location.hash === expected.hash
                    && presentation?._presentationId === expected.presentationId
                    && presentation.hasAttribute('data-render-ready');
            }""",
            arg={"hash": expected_hash, "presentationId": expected_id},
        )
        if expected_id == "gamma":
            assert page.locator('[data-instance="Gamma shared"]').is_visible()
        else:
            assert page.locator('[data-instance="Beta end"]').is_visible()

    for expected_hash, expected_id in [
        ("#/gamma/shared", "gamma"),
        ("#/alpha/shared", "alpha"),
    ]:
        page.go_forward()
        page.wait_for_function(
            """expected => {
                const presentation = document.querySelector('vividly-presentation');
                return location.hash === expected.hash
                    && presentation?._presentationId === expected.presentationId
                    && presentation.hasAttribute('data-render-ready');
            }""",
            arg={"hash": expected_hash, "presentationId": expected_id},
        )
        if expected_id == "gamma":
            assert page.locator('[data-instance="Gamma shared"]').is_visible()
        else:
            assert page.locator('[data-instance="Alpha shared"]').is_visible()


def test_reload_catalog_presentation_starts_one_fresh_thread(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/beta/shared")
    page.locator('[data-instance="Beta shared"]').wait_for(state="visible")
    stale_thread_id = page.evaluate(
        "document.querySelector('vividly-presentation').threads[0].id"
    )

    page.reload()
    page.locator('[data-instance="Beta shared"]').wait_for(state="visible")
    threads = page.evaluate("document.querySelector('vividly-presentation').threads")

    assert len(threads) == 1
    assert threads[0]["id"] != stale_thread_id
    assert threads[0]["presentationId"] == "beta"
    assert threads[0]["latestRoute"] == "shared"


@pytest.mark.parametrize("touch", [False, True])
@pytest.mark.parametrize(
    "route",
    [
        "/#/",
        "/#/vividly/",
        "/?vividly-skip-hints=1#/vividly/opening/title-card",
        "/?vividly-capture=1#/vividly/opening/title-card",
    ],
)
def test_thread_controls_are_not_rendered(
    browser: Browser, runtime_url: str, touch: bool, route: str
) -> None:
    page = browser.new_page(has_touch=touch)
    page.goto(f"{runtime_url}{route}")
    page.locator("vividly-presentation[data-render-ready]").wait_for()
    expect(page.locator(".v-thread-switcher, .v-thread-trigger, .v-thread-menu")).to_have_count(0)
    expect(page.get_by_role("button", name="Threads", include_hidden=True)).to_have_count(0)
    expect(
        page.get_by_role("menu", name="Presentation threads", include_hidden=True)
    ).to_have_count(0)
    page.close()


def test_catalog_is_threadless_and_selection_creates_fresh_thread(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/alpha/shared")
    page.locator('[data-instance="Alpha shared"]').wait_for(state="visible")
    alpha_thread_id = page.evaluate(
        "document.querySelector('vividly-presentation').threads[0].id"
    )

    page.evaluate("location.hash = '#/'")
    page.get_by_role("navigation", name="Project catalog").wait_for(state="visible")
    catalog_state = page.evaluate(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return {
                activeThreadId: presentation._threadId,
                hasRuntime: Boolean(presentation._manifest),
                historyThreadId: history.state.vividly.threadId,
                threads: presentation.threads,
            };
        }"""
    )

    assert catalog_state["activeThreadId"] is None
    assert catalog_state["hasRuntime"] is False
    assert catalog_state["historyThreadId"] is None
    assert len(catalog_state["threads"]) == 1
    assert catalog_state["threads"][0]["id"] == alpha_thread_id
    assert catalog_state["threads"][0]["latestRoute"] == "shared"

    page.get_by_role("link", name="Beta Presentation").click()
    page.locator(".v-toc").wait_for(state="visible")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation.threads.some(thread =>
                thread.id === presentation._threadId && thread.presentationId === 'beta');
        }"""
    )
    threads = page.evaluate("document.querySelector('vividly-presentation').threads")

    assert page.url.endswith("#/beta/")
    assert len(threads) == 2
    assert threads[0]["presentationId"] == "beta"
    assert threads[0]["id"] != alpha_thread_id


def test_enter_opens_focused_catalog_presentation_toc(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/")
    page.get_by_role("navigation", name="Project catalog").wait_for(state="visible")

    page.keyboard.press("ArrowDown")
    assert page.locator(".v-catalog-item.focused").get_attribute("data-presentation-id") == "beta"

    page.keyboard.press("Enter")
    page.wait_for_url("**/#/beta/")

    page.get_by_role("navigation", name="Presentation outline").wait_for(state="visible")
    page.close()


def test_catalog_restores_activated_presentation_focus_without_tracking_focus_moves(
    browser: Browser,
    runtime_url: str,
) -> None:
    context = browser.new_context()
    page = context.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/")
    page.get_by_role("navigation", name="Project catalog").wait_for(state="visible")

    alpha = page.locator('.v-catalog-item[data-presentation-id="alpha"]')
    beta = page.locator('.v-catalog-item[data-presentation-id="beta"]')
    assert alpha.evaluate("(element) => element === document.activeElement")

    page.keyboard.press("ArrowDown")
    assert beta.evaluate("(element) => element === document.activeElement")

    cold_page = context.new_page()
    route_multi_presentation_project(cold_page)
    cold_page.goto(f"{runtime_url}/#/")
    cold_page.get_by_role("navigation", name="Project catalog").wait_for(state="visible")
    assert cold_page.locator(
        '.v-catalog-item[data-presentation-id="alpha"]'
    ).evaluate("(element) => element === document.activeElement")
    cold_page.close()

    page.keyboard.press("Enter")
    page.wait_for_url("**/#/beta/")
    page.get_by_role("navigation", name="Presentation outline").wait_for(state="visible")
    page.keyboard.press("Escape")
    page.wait_for_url("**/#/")
    assert beta.evaluate("(element) => element === document.activeElement")

    restored_page = context.new_page()
    route_multi_presentation_project(restored_page)
    restored_page.goto(f"{runtime_url}/#/")
    restored_page.get_by_role("navigation", name="Project catalog").wait_for(
        state="visible"
    )
    assert restored_page.locator(
        '.v-catalog-item[data-presentation-id="beta"]'
    ).evaluate("(element) => element === document.activeElement")
    context.close()


def test_id_prefixed_route_loads_catalog_presentation(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._step === 2 && presentation.hasAttribute('data-render-ready');
        }"""
    )

    assert page.locator(".v-slide").filter(has_text="Vividly").is_visible()
    assert page.url.endswith("#/vividly/opening/title-card/2")
    assert page.evaluate(
        "document.querySelector('vividly-presentation')._state._key"
    ) == f"vividly:{runtime_url}/catalog.yaml:vividly"


def test_auto_advance_link_replaces_initial_history_entry(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/")
    page.get_by_role("navigation", name="Project catalog").wait_for(state="visible")
    previous_history_length = page.evaluate("history.length")

    page.evaluate(
        "(url) => { location.href = url; }",
        f"{runtime_url}/?source=readme&vividly-auto-advance=1"
        "#/vividly/opening/title-card",
    )
    page.locator(".v-keyboard-hints").wait_for(state="visible")
    start_presentation(page)
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return location.hash === '#/vividly/opening/title-card/1'
                && presentation?._step === 1
                && presentation.hasAttribute('data-render-ready');
        }"""
    )

    assert page.url == (
        f"{runtime_url}/?source=readme#/vividly/opening/title-card/1"
    )
    assert page.evaluate("history.length") == previous_history_length + 1

    page.reload()
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._step === 1 && presentation.hasAttribute('data-render-ready');
        }"""
    )
    assert page.url == (
        f"{runtime_url}/?source=readme#/vividly/opening/title-card/1"
    )

    page.go_back()
    page.get_by_role("navigation", name="Project catalog").wait_for(state="visible")
    assert page.url == f"{runtime_url}/#/"
    page.close()


def test_auto_advance_link_does_not_advance_nonzero_route(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(
        f"{runtime_url}/?vividly-auto-advance=1#/vividly/opening/title-card/2"
    )
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._step === 2 && presentation.hasAttribute('data-render-ready');
        }"""
    )

    assert page.url == (
        f"{runtime_url}/?vividly-auto-advance=1#/vividly/opening/title-card/2"
    )
    page.close()


def test_toc_modes_share_one_route_without_adding_history(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.locator(".v-toc").wait_for(state="visible")
    initial_length = page.evaluate("history.length")

    outline = page.get_by_role("button", name="Outline", exact=True)
    grid = page.get_by_role("button", name="Grid", exact=True)
    assert outline.count() == 1
    assert grid.count() == 1
    assert outline.get_attribute("aria-pressed") == "true"

    grid.click()
    assert page.url.endswith("#/vividly/")
    assert page.evaluate("history.length") == initial_length
    assert grid.get_attribute("aria-pressed") == "true"
    assert grid.evaluate("(element) => element === document.activeElement")
    assert page.locator(".v-toc-outline").get_attribute("hidden") == ""
    assert page.locator(".v-toc-grid").get_attribute("hidden") is None
    assert page.locator(".v-toc-outline").is_hidden()
    assert page.locator(".v-toc-grid").is_visible()

    outline.click()
    assert page.url.endswith("#/vividly/")
    assert page.evaluate("history.length") == initial_length
    assert outline.get_attribute("aria-pressed") == "true"
    assert outline.evaluate("(element) => element === document.activeElement")
    assert page.locator(".v-toc-outline").get_attribute("hidden") is None
    assert page.locator(".v-toc-grid").get_attribute("hidden") == ""
    assert page.locator(".v-toc-outline").is_visible()
    assert page.locator(".v-toc-grid").is_hidden()
    page.close()


def test_sorter_route_is_not_a_thread_route(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/alpha/")
    page.locator(".v-toc").wait_for(state="visible")
    original_url = page.url
    original_threads = page.locator("vividly-presentation").evaluate(
        "(presentation) => presentation.threads"
    )

    error = page.locator("vividly-presentation").evaluate(
        """async (presentation) => {
            try {
                await presentation.createThread('beta', {route: '~sorter'});
                return null;
            } catch (caught) {
                return String(caught);
            }
        }"""
    )

    assert error is not None
    assert page.url == original_url
    assert page.locator("vividly-presentation").evaluate(
        "(presentation) => presentation.threads"
    ) == original_threads
    page.close()


def test_toc_mode_persists_per_presentation_across_navigation(
    browser: Browser,
    runtime_url: str,
) -> None:
    context = browser.new_context()
    page = context.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/alpha/")
    page.locator(".v-toc").wait_for(state="visible")

    grid = page.get_by_role("button", name="Grid", exact=True)
    assert grid.count() == 1
    grid.click()
    page.locator(
        '.v-overview-body:not([hidden]) .v-overview-item[data-address="shared"]'
    ).click()
    page.wait_for_url("**/#/alpha/shared")
    page.keyboard.press("Escape")
    page.wait_for_url("**/#/alpha/")
    assert page.get_by_role("button", name="Grid", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"

    page.keyboard.press("Escape")
    page.wait_for_url("**/#/")
    page.get_by_role("link", name="Beta Presentation").click()
    page.wait_for_url("**/#/beta/")
    assert page.get_by_role("button", name="Outline", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"

    page.keyboard.press("Escape")
    page.get_by_role("link", name="Alpha Presentation").click()
    page.wait_for_url("**/#/alpha/")
    assert page.get_by_role("button", name="Grid", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"

    page.reload()
    page.locator(".v-toc").wait_for(state="visible")
    assert page.get_by_role("button", name="Grid", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"

    second_page = context.new_page()
    route_multi_presentation_project(second_page)
    second_page.goto(f"{runtime_url}/#/alpha/")
    second_page.locator(".v-toc").wait_for(state="visible")
    assert second_page.get_by_role("button", name="Grid", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"
    context.close()


def test_thread_rehydration_uses_current_presentation_toc_mode(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/alpha/")
    page.locator(".v-toc").wait_for(state="visible")
    grid = page.get_by_role("button", name="Grid", exact=True)
    assert grid.count() == 1
    grid.click()
    presentation = page.locator("vividly-presentation")
    alpha_thread_id = presentation.evaluate("(element) => element.threads[0].id")

    beta_thread_id = presentation.evaluate(
        "async (element) => await element.createThread('beta', {route: ''})"
    )
    page.wait_for_url("**/#/beta/")
    assert page.get_by_role("button", name="Outline", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"

    presentation.evaluate(
        "(element, threadId) => element.selectThread(threadId)",
        alpha_thread_id,
    )
    page.wait_for_url("**/#/alpha/")
    assert page.get_by_role("button", name="Grid", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"

    presentation.evaluate(
        "(element, threadId) => element.selectThread(threadId)",
        beta_thread_id,
    )
    page.wait_for_url("**/#/beta/")
    assert page.get_by_role("button", name="Outline", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"
    page.close()


def test_toc_preferences_are_per_presentation_and_expansion_is_shared(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/alpha/")
    page.locator(".v-toc").wait_for(state="visible")

    show_thumbnails = page.get_by_role("button", name="Show thumbnails", exact=True)
    assert show_thumbnails.count() == 1
    assert show_thumbnails.get_attribute("aria-pressed") == "false"
    expand_steps = page.get_by_role("button", name="Expand/collapse steps", exact=True)
    assert expand_steps.count() == 1
    assert expand_steps.is_enabled()
    assert expand_steps.locator(".v-overview-icon-expand").is_visible()
    assert expand_steps.locator(".v-overview-icon-collapse").is_hidden()
    thumbnail_position = show_thumbnails.bounding_box()
    assert thumbnail_position is not None

    expand_steps.click()
    assert show_thumbnails.bounding_box() == thumbnail_position
    assert show_thumbnails.get_attribute("aria-pressed") == "true"
    assert expand_steps.get_attribute("aria-expanded") == "true"
    assert expand_steps.locator(".v-overview-icon-expand").is_hidden()
    assert expand_steps.locator(".v-overview-icon-collapse").is_visible()

    page.get_by_role("button", name="Grid", exact=True).click()
    assert expand_steps.is_enabled()
    assert expand_steps.get_attribute("aria-expanded") == "true"

    page.get_by_role("button", name="Outline", exact=True).click()
    assert page.get_by_role(
        "button", name="Show thumbnails", exact=True
    ).get_attribute("aria-pressed") == "true"
    assert page.get_by_role("button", name="Expand/collapse steps", exact=True).get_attribute(
        "aria-expanded"
    ) == "true"

    page.reload()
    page.locator(".v-toc").wait_for(state="visible")
    assert page.get_by_role(
        "button", name="Show thumbnails", exact=True
    ).get_attribute("aria-pressed") == "true"
    assert page.get_by_role("button", name="Expand/collapse steps", exact=True).get_attribute(
        "aria-expanded"
    ) == "true"
    page.get_by_role("button", name="Grid", exact=True).click()
    assert page.get_by_role("button", name="Expand/collapse steps", exact=True).get_attribute(
        "aria-expanded"
    ) == "true"
    page.get_by_role("button", name="Outline", exact=True).click()

    page.keyboard.press("Escape")
    page.get_by_role("link", name="Beta Presentation").click()
    page.wait_for_url("**/#/beta/")
    assert page.get_by_role("button", name="Outline", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"
    assert page.get_by_role(
        "button", name="Show thumbnails", exact=True
    ).get_attribute("aria-pressed") == "false"
    beta_expand_steps = page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    )
    assert beta_expand_steps.get_attribute("aria-expanded") == "false"
    assert beta_expand_steps.is_enabled()
    page.close()


def test_toc_view_shortcuts_do_not_restore_sorter_navigation(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?._step === 2"
    )
    url = page.url

    page.keyboard.press("s")
    assert page.url == url
    assert page.locator(".v-slide").filter(has_text="Vividly").is_visible()

    page.keyboard.press("Escape")
    page.wait_for_url("**/#/vividly/")
    toc_url = page.url
    history_length = page.evaluate("history.length")

    page.keyboard.press("s")
    assert page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    ).get_attribute("aria-expanded") == "true"
    assert page.get_by_role(
        "button", name="Show thumbnails", exact=True
    ).get_attribute("aria-pressed") == "true"

    page.keyboard.press("g")
    assert page.url == toc_url
    assert page.evaluate("history.length") == history_length
    assert page.get_by_role("button", name="Grid", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"
    assert page.locator(".v-toc-grid .v-grid-item.focused").evaluate(
        "(element) => element === document.activeElement"
    )

    page.keyboard.press("s")
    assert page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    ).get_attribute("aria-expanded") == "false"

    page.keyboard.press("o")
    assert page.get_by_role("button", name="Outline", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"
    assert page.locator(".v-toc-outline .v-overview-item.focused").evaluate(
        "(element) => element === document.activeElement"
    )
    page.keyboard.press("s")
    assert page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    ).get_attribute("aria-expanded") == "true"

    page.get_by_role("button", name="Show thumbnails", exact=True).click()
    page.keyboard.press("s")
    assert page.get_by_role(
        "button", name="Show thumbnails", exact=True
    ).get_attribute("aria-pressed") == "true"
    assert page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    ).get_attribute("aria-expanded") == "true"
    page.keyboard.press("s")
    assert page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    ).get_attribute("aria-expanded") == "false"
    page.close()


def test_id_prefixed_route_survives_reload(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?._step === 2"
    )

    page.reload()
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._step === 2 && presentation.hasAttribute('data-render-ready');
        }"""
    )

    assert page.url.endswith("#/vividly/opening/title-card/2")


@pytest.mark.parametrize("presentation_id", ["unknown", "Not-Valid"])
def test_invalid_presentation_id_routes_show_catalog(
    browser: Browser,
    runtime_url: str,
    presentation_id: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/{presentation_id}/opening/title-card")
    page.get_by_role("navigation", name="Project catalog").wait_for(state="visible")

    assert page.get_by_role("link", name="Vividly Runtime Shakedown").is_visible()


@pytest.mark.parametrize(
    ("catalog", "message"),
    [
        (
            {
                "version": 1,
                "presentations": [
                    {"id": "Not-Valid", "title": "Invalid", "manifest": "./invalid.yaml"}
                ],
            },
            'Invalid catalog presentation ID "Not-Valid"',
        ),
        (
            {
                "version": 1,
                "presentations": [
                    {"id": "duplicate", "title": "One", "manifest": "./one.yaml"},
                    {"id": "duplicate", "title": "Two", "manifest": "./two.yaml"},
                ],
            },
            'Duplicate catalog presentation ID "duplicate"',
        ),
        (
            {
                "version": 1,
                "presentations": [
                    {"id": "escaped", "title": "Escaped", "manifest": "../outside.yaml"}
                ],
            },
            'Catalog manifest for "escaped" must remain below site/',
        ),
    ],
)
def test_catalog_validation_rejects_invalid_entries(
    browser: Browser,
    runtime_url: str,
    catalog: dict[str, object],
    message: str,
) -> None:
    page = browser.new_page()
    page.goto(runtime_url)
    page.wait_for_function("() => Boolean(document.querySelector('vividly-presentation')?._yaml)")
    page.route(
        "**/invalid-catalog.yaml",
        lambda route: route.fulfill(content_type="application/yaml", body=json.dumps(catalog)),
    )

    actual = page.evaluate(
        """async (catalogUrl) => {
            const { loadCatalog } = await import('./vividly/runtime/catalog.js');
            const yaml = document.querySelector('vividly-presentation')._yaml;
            try {
                await loadCatalog(catalogUrl, yaml);
            } catch (error) {
                return error.message;
            }
            return null;
        }""",
        f"{runtime_url}/invalid-catalog.yaml",
    )

    assert actual == message


def test_render_readiness_tracks_step_navigation(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.evaluate(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            window.readinessChanges = [];
            new MutationObserver(() => {
                window.readinessChanges.push(presentation.hasAttribute('data-render-ready'));
            }).observe(presentation, { attributes: true, attributeFilter: ['data-render-ready'] });
        }"""
    )
    page.keyboard.press("ArrowLeft")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._step === 1 && presentation.hasAttribute('data-render-ready');
        }"""
    )

    assert page.evaluate("window.readinessChanges") == [False, True]
    page.close()


def test_slide_modules_import_runtime_through_import_map(
    browser: Browser, runtime_url: str
) -> None:
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    manifest = {
        "id": "import-map-test",
        "title": "Import Map Test",
        "nodes": [
            {
                "type": "slide",
                "id": "nested",
                "module": "../slides/library/demo/nested/slide.js",
            },
        ],
    }
    page.route(
        "**/presentations/vividly.yaml",
        lambda route: route.fulfill(content_type="application/yaml", body=json.dumps(manifest)),
    )
    page.route(
        "**/slides/library/demo/nested/slide.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=(
                "import { Slide, DYNAMIC } from 'vividly/runtime/slide.js';"
                "export default class NestedSlide extends Slide {"
                "mount(root){root.textContent=`${DYNAMIC} ${this.ctx.address}`;}"
                "}"
            ),
        ),
    )
    page.goto(f"{runtime_url}/?vividly-capture=1#/vividly/nested")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    assert page.locator(".v-layer:not([hidden])").inner_text() == "dynamic nested"
    assert errors == []
    page.close()


def test_threads_are_cold_route_bookmarks(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    route_thread_manifests(page)
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    initial_history_length = page.evaluate("history.length")

    result = page.evaluate(
        """async () => {
            const presentation = document.querySelector('vividly-presentation');
            const originalId = presentation.threads[0].id;
            const firstId = await presentation.createThread('thread-a', {
                route: 'first',
            });
            document.querySelector('.v-slide input').value = 'transient';
            await presentation._navigateTo('second', 0);
            const secondId = await presentation.createThread('thread-a', {
                route: 'first',
            });
            await presentation.selectThread(firstId);
            await presentation.selectThread(firstId);
            return {
                originalId,
                firstId,
                secondId,
                threads: presentation.threads,
                inputValue: document.querySelector('.v-slide input').value,
                mounts: window.threadMounts,
                unmounts: window.threadUnmounts,
                disposals: window.threadDisposals,
                stageCount: presentation.querySelectorAll(':scope > .v-stage').length,
            };
        }"""
    )

    assert result["firstId"] != result["secondId"]
    assert result["threads"][0]["id"] == result["firstId"]
    assert result["threads"][0]["latestRoute"] == "second"
    assert result["threads"][1]["id"] == result["secondId"]
    assert result["threads"][1]["latestRoute"] == "first"
    assert result["threads"][2]["id"] == result["originalId"]
    assert result["inputValue"] == ""
    assert result["mounts"] >= 3
    assert result["unmounts"] >= 2
    assert result["disposals"] >= 2
    assert result["stageCount"] == 1
    assert page.evaluate("history.length") == initial_history_length + 4
    assert page.url.endswith("#/thread-a/second")
    assert page.title() == "Thread A"

    immutable = page.evaluate(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            const snapshot = presentation.threads;
            try { snapshot.pop(); } catch {}
            try { snapshot[0].latestRoute = 'changed'; } catch {}
            return presentation.threads[0].latestRoute;
        }"""
    )
    assert immutable == "second"
    page.close()


def test_thread_switch_failure_keeps_source_active(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    route_thread_manifests(page)
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    initial_history_length = page.evaluate("history.length")
    initial_thread_id = page.evaluate(
        "document.querySelector('vividly-presentation').threads[0].id"
    )

    errors = page.evaluate(
        """async () => {
            const presentation = document.querySelector('vividly-presentation');
            const errors = [];
            for (const operation of [
                () => presentation.createThread('missing'),
                () => presentation.createThread('thread-b', {route: 'missing'}),
                () => presentation.createThread('broken-thread', {route: 'broken'}),
                () => presentation.selectThread('missing-thread'),
            ]) {
                try { await operation(); } catch (error) { errors.push(error.message); }
            }
            return errors;
        }"""
    )

    assert len(errors) == 4
    assert page.url.endswith("#/vividly/opening/title-card/1")
    assert page.evaluate("history.length") == initial_history_length
    assert page.evaluate(
        "document.querySelector('vividly-presentation').threads.length"
    ) == 1
    assert page.evaluate(
        "document.querySelector('vividly-presentation').threads[0].id"
    ) == initial_thread_id
    assert page.evaluate(
        "document.querySelector('vividly-presentation').hasAttribute('data-render-ready')"
    )
    page.close()


def test_browser_history_restores_threads_chronologically(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_thread_manifests(page)
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    root_thread_id = page.evaluate(
        "document.querySelector('vividly-presentation').threads[0].id"
    )
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/opening/title-card/2")

    thread_id = page.evaluate(
        """async () => {
            const presentation = document.querySelector('vividly-presentation');
            const threadId = await presentation.createThread('thread-a', {
                route: 'first',
            });
            await presentation._navigateTo('second', 0);
            document.querySelector('.v-slide input').value = 'transient';
            await presentation.selectThread(presentation.threads.at(-1).id);
            return threadId;
        }"""
    )
    history_length = page.evaluate("history.length")

    def wait_for_state(expected_thread_id: str, route: str, title: str) -> None:
        page.wait_for_function(
            """expected => {
                const presentation = document.querySelector('vividly-presentation');
                return presentation?._threadId === expected.threadId
                    && location.hash === expected.hash
                    && document.title === expected.title
                    && presentation.hasAttribute('data-render-ready');
            }""",
            arg={
                "threadId": expected_thread_id,
                "hash": f"#/{'thread-a' if title == 'Thread A' else 'vividly'}/{route}",
                "title": title,
            },
        )
        assert page.evaluate("history.length") == history_length
        assert page.evaluate("history.state.vividly.threadId") == expected_thread_id
        theme_count = page.evaluate(
            "document.querySelectorAll('link[href$=\"thread-a.css\"]').length"
        )
        assert theme_count == (1 if title == "Thread A" else 0)
        if expected_thread_id == thread_id and route == "second":
            assert page.evaluate("document.querySelector('.v-slide input').value") == ""

    backward_states = [
        (thread_id, "second", "Thread A"),
        (thread_id, "first", "Thread A"),
        (root_thread_id, "opening/title-card/2", "Vividly Runtime Shakedown"),
        (root_thread_id, "opening/title-card/1", "Vividly Runtime Shakedown"),
    ]
    for expected_thread_id, route, title in backward_states:
        page.go_back()
        wait_for_state(expected_thread_id, route, title)

    forward_states = list(reversed(backward_states[:-1])) + [
        (root_thread_id, "opening/title-card/2", "Vividly Runtime Shakedown")
    ]
    for expected_thread_id, route, title in forward_states:
        page.go_forward()
        wait_for_state(expected_thread_id, route, title)

    page.go_back()
    wait_for_state(thread_id, "second", "Thread A")
    page.evaluate(
        "document.querySelector('vividly-presentation')._navigateTo('first', 0)"
    )
    page.wait_for_url("**/#/thread-a/first")
    assert page.go_forward() is None
    assert page.url.endswith("#/thread-a/first")
    assert page.evaluate("history.state.vividly.threadId") == thread_id
    page.close()


def test_reload_discards_page_local_thread_identity(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    route_thread_manifests(page)
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    stale_identity = page.evaluate(
        """async () => {
            const presentation = document.querySelector('vividly-presentation');
            await presentation.createThread('thread-a', {route: 'second'});
            return {...history.state.vividly};
        }"""
    )

    page.reload()
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?.hasAttribute('data-render-ready')
                && presentation._presentationId === 'thread-a';
        }"""
    )
    fresh_identity = page.evaluate("history.state.vividly")

    assert page.url.endswith("#/thread-a/second")
    assert page.title() == "Thread A"
    assert fresh_identity["pageId"] != stale_identity["pageId"]
    assert fresh_identity["threadId"] != stale_identity["threadId"]
    assert page.evaluate(
        "document.querySelector('vividly-presentation').threads.length"
    ) == 1
    assert page.evaluate(
        "document.querySelector('vividly-presentation').threads[0].latestRoute"
    ) == "second"
    page.close()


def test_foreign_history_entry_uses_root_presentation(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    route_thread_manifests(page)
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    root_identity = page.evaluate("({...history.state.vividly})")
    page.evaluate(
        """async () => {
            const presentation = document.querySelector('vividly-presentation');
            await presentation.createThread('thread-a', {route: 'first'});
            history.replaceState({foreign: true}, '', '#/vividly/opening/title-card/1');
            await presentation._navigateTo('second', 0);
        }"""
    )
    history_length = page.evaluate("history.length")

    page.go_back()
    page.wait_for_function(
        """root => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._threadId === root.threadId
                && location.hash === '#/vividly/opening/title-card/1'
                && document.title === 'Vividly Runtime Shakedown'
                && presentation.hasAttribute('data-render-ready');
        }""",
        arg=root_identity,
    )

    assert page.evaluate("history.length") == history_length
    assert page.evaluate("history.state.vividly") == root_identity
    assert page.evaluate(
        "document.querySelector('vividly-presentation').threads.length"
    ) == 2
    page.close()




def test_catalog_presentation_runs_as_a_thread(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/alpha/shared")
    page.locator('[data-instance="Alpha shared"]').wait_for(state="visible")
    presentation = page.locator("vividly-presentation")
    original_thread_id = presentation.evaluate("element => element.threads[0].id")

    beta_thread_id = presentation.evaluate(
        "element => element.createThread('beta', {route: 'shared'})"
    )
    assert page.title() == "Beta Presentation"
    assert page.locator('[data-instance="Beta shared"]').is_visible()
    assert page.url.endswith("#/beta/shared")

    presentation.evaluate("element => element._navigateTo('end')")
    page.wait_for_url("**/#/beta/end")
    page.go_back()
    page.wait_for_url("**/#/beta/shared")
    page.go_forward()
    page.wait_for_url("**/#/beta/end")

    presentation.evaluate(
        "(element, threadId) => element.selectThread(threadId)",
        original_thread_id,
    )
    assert page.title() == "Alpha Presentation"
    assert page.url.endswith("#/alpha/shared")
    presentation.evaluate("(element, threadId) => element.selectThread(threadId)", beta_thread_id)
    assert page.title() == "Beta Presentation"
    assert page.url.endswith("#/beta/end")
    page.close()






def test_runtime_keyboard_hints_can_be_suppressed_and_restored(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    page.locator(".v-keyboard-hints").wait_for(state="visible")

    hints = page.locator(".v-keyboard-hints")
    assert not page.locator("vividly-presentation").get_attribute("data-render-ready")
    assert page.locator(".v-layer:not([hidden])").count() == 0
    assert hints.get_by_text("Getting started", exact=True).is_visible()
    assert hints.get_by_text("Moving through the presentation", exact=True).is_visible()
    assert hints.get_by_text("Go back / forward one step", exact=True).is_visible()
    assert hints.get_by_text("Go up to the section containing this slide", exact=True).is_visible()
    assert hints.get_by_text("Choosing a slide or section", exact=True).is_visible()
    assert hints.get_by_text("Highlight a slide or section", exact=True).is_visible()
    assert hints.get_by_text("Open the highlighted slide or section", exact=True).is_visible()
    expect(hints.locator(".v-keyboard-hints-shortcuts span")).to_have_text(
        ["Esc Open the table of contents", "? Show keyboard help"]
    )
    assert hints.get_by_text(
        "A yellow bar shows an animation in progress. Press Space or → to finish it immediately."
    ).is_visible()
    assert hints.get_by_text("Click anywhere or press a key to start.", exact=True).is_visible()
    assert hints.locator("kbd").all_text_contents() == [
        "Space",
        "←",
        "→",
        "↑",
        "←",
        "↑",
        "↓",
        "→",
        "Enter",
        "Esc",
        "?",
    ]
    assert hints.locator("kbd").first.evaluate(
        "element => getComputedStyle(element).borderBottomWidth"
    ) == "3px"
    assert hints.evaluate("element => getComputedStyle(element).position") == "fixed"
    assert hints.evaluate(
        """element => {
            const box = element.getBoundingClientRect();
            return box.left === 0 && box.top === 0
                && box.right === innerWidth && box.bottom === innerHeight;
        }"""
    )

    hints.get_by_label("Don't show these tips again").check()
    assert hints.get_attribute("data-closing") is None
    hints.get_by_role("button", name="Start presentation").click()
    assert hints.get_attribute("data-closing") == ""
    assert page.locator(".v-layer:not([hidden])").count() == 0
    assert hints.evaluate(
        """element => element.getAnimations().some(
            animation => animation.effect.getTiming().duration === 300
        )"""
    )
    hints.wait_for(state="hidden")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.reload()
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.wait_for_timeout(1200)
    assert hints.is_hidden()

    page.locator(".v-help-trigger").click()
    help_overlay = page.locator(".v-keyboard-help")
    help_overlay.wait_for(state="visible")
    restore = help_overlay.get_by_label("Show navigation hints when presentations start")
    assert not restore.is_checked()
    restore.check()

    page.reload()
    hints.wait_for(state="visible")
    assert not page.locator("vividly-presentation").get_attribute("data-render-ready")
    page.keyboard.press("ArrowRight")
    assert hints.get_attribute("data-closing") == ""
    hints.wait_for(state="hidden")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    assert page.url.endswith("#/vividly/opening/title-card")
    page.close()


@pytest.mark.parametrize("touch", [False, True])
@pytest.mark.parametrize(
    "target",
    [
        "backdrop",
        ".v-keyboard-hints-panel > strong",
        ".v-keyboard-hints-groups kbd",
        ".v-keyboard-hints-start button",
    ],
)
def test_runtime_keyboard_hints_pointer_dismissal_is_consumed(
    browser: Browser, runtime_url: str, touch: bool, target: str
) -> None:
    page = browser.new_page(has_touch=touch, viewport={"width": 390, "height": 844})
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    hints = page.locator(".v-keyboard-hints")
    expect(hints).to_be_visible()
    prompt = "Tap anywhere to start." if touch else "Click anywhere or press a key to start."
    expect(hints.get_by_text(prompt, exact=True)).to_be_visible()
    if target == ".v-keyboard-hints-groups kbd":
        if touch:
            hints.locator("summary").tap()
        else:
            hints.locator("summary").click()
    page.evaluate(
        """() => {
            document.documentElement.dataset.hintClicks = '0';
            document.addEventListener('click', () => {
                document.documentElement.dataset.hintClicks =
                    String(Number(document.documentElement.dataset.hintClicks) + 1);
            });
        }"""
    )
    control = hints if target == "backdrop" else hints.locator(target).first
    position: Position | None = {"x": 4, "y": 4} if target == "backdrop" else None
    if touch:
        control.tap(position=position)
    else:
        control.click(position=position)
    assert hints.get_attribute("data-closing") == ""
    assert hints.evaluate("el => getComputedStyle(el).pointerEvents") == "auto"
    hints.wait_for(state="hidden")
    page.locator("vividly-presentation[data-render-ready]").wait_for()
    assert page.url.endswith("#/vividly/opening/title-card")
    assert page.locator("vividly-presentation").evaluate("p => p._step") == 0
    assert page.locator("html").get_attribute("data-hint-clicks") == "0"
    page.close()


@pytest.mark.parametrize("touch", [False, True])
def test_runtime_keyboard_hints_preference_clicks_do_not_dismiss(
    browser: Browser, runtime_url: str, touch: bool
) -> None:
    page = browser.new_page(has_touch=touch)
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    hints = page.locator(".v-keyboard-hints")
    expect(hints).to_be_visible()
    label = hints.locator("label")
    checkbox = hints.get_by_label("Don't show these tips again")
    if touch:
        label.tap()
    else:
        label.click()
    expect(checkbox).to_be_checked()
    assert hints.get_attribute("data-closing") is None
    if touch:
        checkbox.tap()
    else:
        checkbox.click()
    expect(checkbox).not_to_be_checked()
    assert hints.get_attribute("data-closing") is None
    expect(hints).to_be_visible()
    page.close()


@pytest.mark.parametrize("touch", [False, True])
@pytest.mark.parametrize("width", [390, 640, 641, 1280])
def test_runtime_keyboard_hints_disclosure_defaults_and_toggles(
    browser: Browser, runtime_url: str, touch: bool, width: int
) -> None:
    page = browser.new_page(has_touch=touch, viewport={"width": width, "height": 800})
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    hints = page.locator(".v-keyboard-hints")
    expect(hints).to_be_visible()
    details = hints.locator("details")
    summary = details.locator("summary")
    expanded = width > 640
    expect(details).to_have_js_property("open", expanded)
    expect(summary).to_have_text("Keyboard shortcuts")
    expect(hints.locator("p.v-touch-instructions")).to_have_count(1)
    if touch:
        expect(hints.locator("p.v-touch-instructions")).to_be_visible()
    else:
        expect(hints.locator("p.v-touch-instructions")).to_be_hidden()
    expect(hints.locator(".v-keyboard-hints-progress")).to_be_visible()
    expect(hints.locator(".v-keyboard-hints-progress-example")).to_be_visible()
    if touch:
        summary.tap()
    else:
        summary.click()
    expect(details).to_have_js_property("open", not expanded)
    if expanded:
        expect(details.locator("kbd").first).to_be_hidden()
    else:
        expect(details.locator("kbd").first).to_be_visible()
    assert hints.get_attribute("data-closing") is None
    page.set_viewport_size({"width": 390 if expanded else 1280, "height": 800})
    expect(details).to_have_js_property("open", not expanded)
    if touch:
        summary.tap()
    else:
        summary.click()
    expect(details).to_have_js_property("open", expanded)
    expect(hints).to_be_visible()
    assert hints.get_attribute("data-closing") is None
    assert page.locator(".v-layer:not([hidden])").count() == 0
    assert page.url.endswith("#/vividly/opening/title-card")
    page.close()


def test_runtime_keyboard_hints_controls_support_keyboard_without_dismissal(
    browser: Browser, runtime_url: str
) -> None:
    page = browser.new_page(has_touch=True, viewport={"width": 390, "height": 844})
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    hints = page.locator(".v-keyboard-hints")
    expect(hints).to_be_visible()
    details = hints.locator("details")
    summary = details.locator("summary")
    start = hints.get_by_role("button", name="Start presentation")
    expect(start).to_be_focused()
    page.keyboard.press("Tab")
    branding = hints.get_by_role("link", name="Powered by Vividly")
    expect(branding).to_be_focused()
    page.keyboard.press("Tab")
    expect(summary).to_be_focused()
    page.keyboard.press("Enter")
    expect(details).to_have_js_property("open", True)
    page.keyboard.press("Space")
    expect(details).to_have_js_property("open", False)
    page.keyboard.press("Tab")
    checkbox = hints.get_by_label("Don't show these tips again")
    expect(checkbox).to_be_focused()
    page.keyboard.press("Space")
    expect(checkbox).to_be_checked()
    assert hints.get_attribute("data-closing") is None
    page.keyboard.press("Shift+Tab")
    expect(summary).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(branding).to_be_focused()
    page.keyboard.press("Tab")
    expect(summary).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(branding).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(start).to_be_focused()
    page.keyboard.press("Enter")
    hints.wait_for(state="hidden")
    page.locator("vividly-presentation[data-render-ready]").wait_for()
    assert page.url.endswith("#/vividly/opening/title-card")
    page.close()


@pytest.mark.parametrize("touch", [False, True])
@pytest.mark.parametrize(
    "viewport", [{"width": 1280, "height": 800}, {"width": 390, "height": 664}]
)
def test_runtime_keyboard_hints_layout_and_help(
    browser: Browser,
    runtime_url: str,
    viewport: dict[str, int],
    touch: bool,
) -> None:
    page = browser.new_page(
        has_touch=touch, viewport={"width": viewport["width"], "height": viewport["height"]}
    )
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    hints = page.locator(".v-keyboard-hints")
    hints.wait_for(state="visible")
    assert hints.locator(".v-keyboard-hints-panel").evaluate(
        """element => {
            const box = element.getBoundingClientRect();
            return box.left >= 0 && box.top >= 0
                && box.right <= innerWidth && box.bottom <= innerHeight
                && element.scrollWidth <= element.clientWidth;
        }"""
    )
    example = hints.locator(".v-keyboard-hints-progress-example")
    expect(example).to_be_visible()
    expect(example).to_have_attribute("aria-hidden", "true")
    assert example.get_attribute("role") is None
    assert example.locator("button").count() == 0
    assert example.evaluate(
        """element => {
            const track = element.getBoundingClientRect();
            const fill = element.querySelector('.v-step-progress-fill').getBoundingClientRect();
            return track.width > 0 && track.width <= element.parentElement.clientWidth
                && getComputedStyle(element).height === '3px' && fill.height === track.height
                && Math.abs(fill.width / track.width - 0.6) < 0.01
                && element.getAnimations({subtree: true}).length === 0;
        }"""
    )
    page.keyboard.press("?")
    page.locator(".v-keyboard-help").wait_for(state="visible")
    hints.wait_for(state="hidden")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.keyboard.press("?")
    page.locator(".v-keyboard-help").wait_for(state="hidden")
    assert page.url.endswith("#/vividly/opening/title-card")
    page.close()


def test_runtime_keyboard_hints_do_not_show_on_deep_links(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/mechanics/diagram-build")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.wait_for_timeout(1200)
    assert page.locator(".v-keyboard-hints").is_hidden()
    page.close()


@pytest.mark.parametrize("activation", ["click", "touch", "keyboard"])
@pytest.mark.parametrize(
    "surface", ["hints", "help-branding", "help-documentation", "catalog", "toc"]
)
def test_public_site_links_open_new_tabs_without_changing_current_view(
    browser: Browser, runtime_url: str, activation: str, surface: str
) -> None:
    context = browser.new_context(
        has_touch=activation == "touch",
        viewport={"width": 390, "height": 844}
        if activation == "touch" else {"width": 1280, "height": 800},
    )
    address = "documentation/overview" if surface == "help-documentation" else "opening"
    overview_url = (
        "https://mikehopcroft.github.io/vividly/"
        f"?vividly-skip-hints=1#/vividly/{address}"
    )
    context.route(
        "https://mikehopcroft.github.io/vividly/**",
        lambda route: route.fulfill(content_type="text/html", body="<p>Vividly overview</p>"),
    )
    page = context.new_page()
    if surface == "hints":
        page.goto(f"{runtime_url}/#/vividly/opening/title-card")
        container = page.locator(".v-keyboard-hints")
    elif surface.startswith("help-"):
        page.goto(f"{runtime_url}/?vividly-skip-hints=1#/vividly/opening/title-card")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        page.keyboard.press("?")
        container = page.locator(".v-keyboard-help")
    else:
        route = "#/" if surface == "catalog" else "#/vividly/"
        page.goto(f"{runtime_url}/{route}")
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        container = page.locator(".v-catalog" if surface == "catalog" else ".v-toc")
    name = (
        "Documentation" if surface == "help-documentation"
        else "Vividly" if surface in {"catalog", "toc"}
        else "Powered by Vividly"
    )
    link = container.get_by_role("link", name=name, exact=True)
    target = link
    if surface != "help-documentation":
        logo = link.get_by_role("img", name="Vividly")
        expect(logo).to_be_visible()
        asset = "logo.svg" if surface in {"catalog", "toc"} else "logo-cropped.svg"
        expect(logo).to_have_attribute("src", f"{runtime_url}/vividly/assets/{asset}")
        expect(logo).to_have_js_property("complete", True)
        assert logo.evaluate("img => img.naturalWidth > 0 && img.naturalHeight > 0")
        target = logo
    expect(link).to_have_attribute("href", overview_url)
    expect(link).to_have_attribute("target", "_blank")
    expect(link).to_have_attribute("rel", "noopener noreferrer")
    source_url = page.url
    if activation == "keyboard":
        for _ in range(12):
            if link.evaluate("element => element === document.activeElement"):
                break
            page.keyboard.press("Tab")
        expect(link).to_be_focused()
    with page.expect_popup() as popup_info:
        if activation == "keyboard":
            page.keyboard.press("Enter")
        elif activation == "touch":
            target.tap()
        else:
            target.click()
    popup = popup_info.value
    popup.wait_for_load_state()
    assert popup.url == overview_url
    assert popup.evaluate("window.opener === null")
    expect(container).to_be_visible()
    assert container.get_attribute("data-closing") is None
    if surface == "hints":
        assert page.locator(".v-layer:not([hidden])").count() == 0
    assert page.url == source_url
    context.close()


@pytest.mark.parametrize("policy", ["auto", "always"])
@pytest.mark.parametrize("skip_value", ["1", "0"])
def test_runtime_keyboard_hints_url_override_does_not_change_preference(
    browser: Browser, runtime_url: str, policy: str, skip_value: str
) -> None:
    page = browser.new_page()
    manifest = yaml.safe_load(
        (FIXTURE_ROOT / "presentations/vividly.yaml").read_text(encoding="utf-8")
    )
    manifest["keyboardHints"] = policy
    page.route(
        "**/presentations/vividly.yaml",
        lambda route: route.fulfill(content_type="application/yaml", body=json.dumps(manifest)),
    )
    page.goto(
        f"{runtime_url}/?vividly-skip-hints={skip_value}#/vividly/opening/title-card"
    )
    hints = page.locator(".v-keyboard-hints")
    if skip_value == "1":
        page.locator("vividly-presentation[data-render-ready]").wait_for()
        expect(hints).to_be_hidden()
        page.keyboard.press("?")
        help_overlay = page.locator(".v-keyboard-help")
        expect(help_overlay).to_be_visible()
        expect(
            help_overlay.get_by_label("Show navigation hints when presentations start")
        ).to_be_checked()
        page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    expect(hints).to_be_visible()
    expect(hints.get_by_label("Don't show these tips again")).not_to_be_checked()
    page.close()


@pytest.mark.parametrize(
    ("policy", "should_show"),
    [
        ("always", True),
        ("never", False),
    ],
)
def test_runtime_keyboard_hint_manifest_policy_overrides_reader_preference(
    browser: Browser,
    runtime_url: str,
    policy: str,
    should_show: bool,
) -> None:
    page = browser.new_page()
    manifest = yaml.safe_load(
        (FIXTURE_ROOT / "presentations/vividly.yaml").read_text(encoding="utf-8")
    )
    manifest["keyboardHints"] = policy

    def apply_policy(route: Any) -> None:
        route.fulfill(
            content_type="application/yaml",
            body=json.dumps(manifest),
        )
    page.route("**/presentations/vividly.yaml", apply_policy)
    storage_key = f"vividly:{runtime_url}/catalog.yaml:~runtime"
    page.add_init_script(
        f"""localStorage.setItem(
            {json.dumps(storage_key)},
            JSON.stringify({{"~keyboardHints": {{suppressed: true}}}})
        )"""
    )
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    page.wait_for_function(
        """policy => document.querySelector(
            'vividly-presentation'
        )?._manifest?.keyboardHints === policy""",
        arg=policy,
    )
    hints = page.locator(".v-keyboard-hints")
    if should_show:
        hints.wait_for(state="visible")
        assert not page.locator("vividly-presentation").get_attribute("data-render-ready")
        assert hints.get_by_label("Don't show these tips again").is_disabled()
    else:
        page.wait_for_function(
            "() => document.querySelector("
            "'vividly-presentation'"
            ")?.hasAttribute('data-render-ready')"
        )
        assert hints.is_hidden()
    page.close()










def test_sample_navigator_traverses_every_sequence_with_arrow_keys(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/navigation-sequence-start")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    forward_routes = [
        "navigation-sequence/navigator",
        "navigation-sequence/section-b/b1",
        "navigation-sequence/section-b/b2",
        "navigation-sequence/section-b/b3",
        "navigation-sequence/navigator/1",
        "navigation-sequence/section-c/c1",
        "navigation-sequence/section-c/c2",
        "navigation-sequence/navigator/2",
        "navigation-sequence/section-d/d1",
        "navigation-sequence/section-d/d2",
        "navigation-sequence/navigator/3",
        "navigation-sequence-end",
    ]
    for index, route in enumerate(forward_routes):
        page.keyboard.press("Space")
        page.wait_for_url(f"**/#/vividly/{route}")
        if index == 0:
            assert page.locator(".sequence-navigator-section").all_text_contents() == [
                "Section B",
                "Section C",
                "Section D",
            ]
            assert page.locator(".sequence-navigator-slides span").all_text_contents() == [
                "B1",
                "B2",
                "B3",
                "C1",
                "C2",
                "D1",
                "D2",
            ]
        if route == "navigation-sequence/navigator/3":
            assert page.locator(".sequence-navigator-row.is-active").count() == 0
            assert page.locator("[data-vividly-navigator-after]").count() == 0

    backward_routes = list(reversed(["navigation-sequence-start", *forward_routes[:-1]]))
    for route in backward_routes:
        page.go_back()
        page.wait_for_url(f"**/#/vividly/{route}")

    page.close()


def test_programmatic_thread_selection_does_not_restore_thread_controls(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_thread_manifests(page)
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    thread_ids = page.evaluate(
        """async () => {
            const presentation = document.querySelector('vividly-presentation');
            const first = await presentation.createThread('thread-a', {
                route: 'first',
            });
            const second = await presentation.createThread('thread-b', {
                route: 'second',
            });
            const third = await presentation.createThread('thread-a', {
                route: 'second',
            });
            return [first, second, third];
        }"""
    )
    expect(page.locator(".v-thread-switcher")).to_have_count(0)
    page.locator("vividly-presentation").evaluate(
        "(presentation, threadId) => presentation.selectThread(threadId)", thread_ids[1]
    )
    page.wait_for_function(
        """threadId => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._threadId === threadId
                && presentation.hasAttribute('data-render-ready');
        }""",
        arg=thread_ids[1],
    )
    assert page.evaluate(
        "document.querySelector('vividly-presentation').threads[0].id"
    ) == thread_ids[1]
    page.keyboard.press("Tab")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert page.locator("vividly-presentation").evaluate(
        "presentation => presentation._threadId"
    ) == thread_ids[1]
    expect(page.locator(".v-thread-switcher, .v-thread-menu")).to_have_count(0)
    page.close()


def test_thread_history_is_preserved_without_switcher(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_thread_manifests(page)
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    identities = page.evaluate(
        """async () => {
            const presentation = document.querySelector('vividly-presentation');
            const root = presentation.threads[0].id;
            const created = [];
            for (let index = 0; index < 6; index += 1) {
                created.push(await presentation.createThread('thread-a', {
                    route: index % 2 ? 'second' : 'first',
                }));
            }
            return {root, created};
        }"""
    )
    history_length = page.evaluate("history.length")

    expect(page.locator(".v-thread-switcher")).to_have_count(0)

    for expected_thread_id in reversed(identities["created"][:-1]):
        page.go_back()
        page.wait_for_function(
            "threadId => document.querySelector('vividly-presentation')?._threadId === threadId",
            arg=expected_thread_id,
        )
    page.go_back()
    page.wait_for_function(
        "threadId => document.querySelector('vividly-presentation')?._threadId === threadId",
        arg=identities["root"],
    )
    assert page.evaluate("history.length") == history_length
    assert page.evaluate(
        "document.querySelector('vividly-presentation').threads.length"
    ) == 7
    page.close()


def test_thread_creation_does_not_render_controls_in_capture_mode(
    browser: Browser, runtime_url: str
) -> None:
    page = browser.new_page()
    route_thread_manifests(page)
    page.goto(f"{runtime_url}/?vividly-capture=1#/vividly/opening/title-card/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.evaluate(
        """presentation => presentation.createThread('thread-a', {
            route: 'first',
        })""",
        page.locator("vividly-presentation").element_handle(),
    )

    expect(page.get_by_role("button", name="Threads", include_hidden=True)).to_have_count(0)
    expect(page.locator(".v-thread-switcher")).to_have_count(0)
    page.close()


def test_browser_history_revisits_chronological_navigation(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    initial_length = page.evaluate("history.length")
    initial_marker = page.evaluate("history.state.vividly")

    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/opening/title-card/1")
    page.keyboard.press("PageDown")
    page.wait_for_url("**/#/vividly/images/full-bleed-image")

    assert page.evaluate("history.length") == initial_length + 2
    assert page.evaluate("history.state.vividly") == initial_marker

    page.go_back()
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return location.hash === '#/vividly/opening/title-card/1'
                && presentation?._step === 1
                && presentation.hasAttribute('data-render-ready');
        }"""
    )
    page.go_back()
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return location.hash === '#/vividly/opening/title-card/2'
                && presentation?._step === 2
                && presentation.hasAttribute('data-render-ready');
        }"""
    )
    page.go_forward()
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return location.hash === '#/vividly/opening/title-card/1'
                && presentation?._step === 1
                && presentation.hasAttribute('data-render-ready');
        }"""
    )

    assert page.evaluate("history.length") == initial_length + 2
    assert page.evaluate("history.state.vividly") == initial_marker
    page.close()


def test_browser_history_restores_routes_with_current_toc_preferences(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.locator(".v-toc").wait_for(state="visible")
    initial_length = page.evaluate("history.length")
    initial_marker = page.evaluate("history.state.vividly")

    grid = page.get_by_role("button", name="Grid", exact=True)
    assert grid.count() == 1
    grid.click()
    assert page.evaluate("history.length") == initial_length

    page.keyboard.press("Home")
    page.keyboard.press("Enter")
    start_presentation(page)
    page.wait_for_url("**/#/vividly/opening/title-card")
    assert page.evaluate("history.length") == initial_length + 1
    assert page.evaluate("history.state.vividly") == initial_marker

    page.go_back()
    page.locator(".v-toc").wait_for(state="visible")
    assert page.get_by_role("button", name="Grid", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"

    page.go_forward()
    page.locator(".v-slide:visible").wait_for(state="visible")
    page.go_back()
    page.locator(".v-toc").wait_for(state="visible")
    assert page.get_by_role("button", name="Grid", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"
    assert page.evaluate("history.length") == initial_length + 1
    assert page.evaluate("history.state.vividly") == initial_marker
    page.close()


def test_manual_hash_navigation_is_owned_and_restorable(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    start_presentation(page)
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    initial_marker = page.evaluate("history.state.vividly")

    page.evaluate("location.hash = '#/vividly/images/full-bleed-image'")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._leaves[presentation._index].address
                === 'images/full-bleed-image'
                && presentation.hasAttribute('data-render-ready');
        }"""
    )
    assert page.evaluate("history.state.vividly") == initial_marker

    page.go_back()
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._leaves[presentation._index].address === 'opening/title-card'
                && presentation.hasAttribute('data-render-ready');
        }"""
    )
    assert page.evaluate("history.state.vividly") == initial_marker
    page.close()


def test_navigation_after_back_truncates_browser_forward_history(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    initial_length = page.evaluate("history.length")

    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/opening/title-card/1")
    page.keyboard.press("PageDown")
    page.wait_for_url("**/#/vividly/images/full-bleed-image")
    page.go_back()
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._step === 1
                && presentation.hasAttribute('data-render-ready');
        }"""
    )

    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/opening/title-card")
    assert page.evaluate("history.length") == initial_length + 2

    page.go_forward()
    assert page.url.endswith("#/vividly/opening/title-card")
    page.close()


def test_multi_entry_history_traversal_restores_one_settled_state(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    marker = page.evaluate("history.state.vividly")

    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/opening/title-card/1")
    page.keyboard.press("PageDown")
    page.wait_for_url("**/#/vividly/images/full-bleed-image")

    page.evaluate("history.go(-2)")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return location.hash === '#/vividly/opening/title-card/2'
                && presentation?._leaves[presentation._index].address === 'opening/title-card'
                && presentation._step === 2
                && presentation.hasAttribute('data-render-ready');
        }"""
    )
    assert page.evaluate("history.state.vividly") == marker

    page.evaluate("history.go(2)")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return location.hash === '#/vividly/images/full-bleed-image'
                && presentation?._leaves[presentation._index].address
                    === 'images/full-bleed-image'
                && presentation._step === 0
                && presentation.hasAttribute('data-render-ready');
        }"""
    )
    assert page.evaluate("history.state.vividly") == marker
    page.close()


def test_manifest_indexes_navigator_owned_sections(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/")

    result = page.evaluate(
        """async () => {
            const { indexPresentation } = await import('./vividly/runtime/manifest.js');
            const slide = (id, navigator = null) => ({
                type: 'slide',
                id,
                ...(navigator ? { navigator } : {}),
            });
            const section = (id, children) => ({ type: 'section', id, children });
            const index = indexPresentation([
                section('book', [
                    slide('overview', {
                        choiceStartStep: 2,
                        sections: ['./chapter', './appendix'],
                    }),
                    section('chapter', [
                        slide('overview', { sections: ['./topic'] }),
                        section('topic', [slide('details')]),
                    ]),
                    section('appendix', [slide('notes')]),
                    section('linear', [slide('extra')]),
                ]),
            ]);
            const summarizeOwner = (address) => {
                const owner = index.sectionOwners.get(address);
                return owner ? {
                    navigatorAddress: owner.navigatorAddress,
                    choiceStep: owner.choiceStep,
                    entryAddress: owner.entryAddress,
                    forwardRoute: owner.forwardRoute,
                    backwardRoute: owner.backwardRoute,
                } : null;
            };
            const reject = (nodes) => {
                try {
                    indexPresentation(nodes);
                    return null;
                } catch (error) {
                    return error.message;
                }
            };
            return {
                leaves: index.leaves.map((leaf) => ({
                    address: leaf.address,
                    sectionAddress: leaf.sectionAddress,
                })),
                chapter: summarizeOwner('book/chapter'),
                topic: summarizeOwner('book/chapter/topic'),
                appendix: summarizeOwner('book/appendix'),
                linear: summarizeOwner('book/linear'),
                bookNavigator: index.navigators.get('book/overview'),
                rejected: {
                    unknown: reject([
                        section('book', [
                            slide('overview', { sections: ['./missing'] }),
                        ]),
                    ]),
                    slide: reject([
                        section('book', [
                            slide('overview', { sections: ['./details'] }),
                            slide('details'),
                        ]),
                    ]),
                    nonChild: reject([
                        section('book', [
                            slide('overview', { sections: ['./chapter/topic'] }),
                            section('chapter', [section('topic', [slide('details')])]),
                        ]),
                    ]),
                    empty: reject([
                        section('book', [
                            slide('overview', { sections: ['./empty'] }),
                            section('empty', []),
                        ]),
                    ]),
                    duplicate: reject([
                        section('book', [
                            slide('overview', { sections: ['./chapter', './chapter'] }),
                            section('chapter', [slide('details')]),
                        ]),
                    ]),
                    ambiguous: reject([
                        section('book', [
                            slide('first', { sections: ['./chapter'] }),
                            slide('second', { sections: ['./chapter'] }),
                            section('chapter', [slide('details')]),
                        ]),
                    ]),
                    choiceStartSteps: [-1, 1.5, '1'].map((choiceStartStep) =>
                        reject([
                            section('book', [
                                slide('overview', {
                                    choiceStartStep,
                                    sections: ['./chapter'],
                                }),
                                section('chapter', [slide('details')]),
                            ]),
                        ])
                    ),
                },
            };
        }"""
    )

    assert result["leaves"] == [
        {"address": "book/overview", "sectionAddress": "book"},
        {"address": "book/chapter/overview", "sectionAddress": "book/chapter"},
        {"address": "book/chapter/topic/details", "sectionAddress": "book/chapter/topic"},
        {"address": "book/appendix/notes", "sectionAddress": "book/appendix"},
        {"address": "book/linear/extra", "sectionAddress": "book/linear"},
    ]
    assert result["chapter"] == {
        "navigatorAddress": "book/overview",
        "choiceStep": 2,
        "entryAddress": "book/chapter/overview",
        "forwardRoute": {"address": "book/overview", "step": 3},
        "backwardRoute": {"address": "book/overview", "step": 2},
    }
    assert result["topic"] == {
        "navigatorAddress": "book/chapter/overview",
        "choiceStep": 0,
        "entryAddress": "book/chapter/topic/details",
        "forwardRoute": {"address": "book/chapter/overview", "step": 1},
        "backwardRoute": {"address": "book/chapter/overview", "step": 0},
    }
    assert result["appendix"]["forwardRoute"] == {"address": "book/overview", "step": 4}
    assert result["linear"] is None
    assert result["bookNavigator"] == {
        "address": "book/overview",
        "sectionAddress": "book",
        "choiceStartStep": 2,
        "afterStep": 4,
        "sections": [
            {"address": "book/chapter", "title": "chapter", "step": 2},
            {"address": "book/appendix", "title": "appendix", "step": 3},
        ],
    }
    assert "Unknown navigator section" in result["rejected"]["unknown"]
    assert "targets slide" in result["rejected"]["slide"]
    assert "not a direct child" in result["rejected"]["nonChild"]
    assert "has no slides" in result["rejected"]["empty"]
    assert "Duplicate navigator section" in result["rejected"]["duplicate"]
    assert "already owned" in result["rejected"]["ambiguous"]
    assert all(
        "choiceStartStep must be a nonnegative integer" in error
        for error in result["rejected"]["choiceStartSteps"]
    )
    page.close()


def test_nested_navigator_traversal_revisits_owning_steps(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/book/overview")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    initial_history_length = page.evaluate("history.length")

    expected_routes = [
        "book/chapter/overview",
        "book/chapter/topic-a/first",
        "book/chapter/topic-a/second",
        "book/chapter/overview/1",
        "book/chapter/topic-b/only",
        "book/chapter/overview/2",
        "book/overview/1",
        "outro",
    ]
    keys = ["Space"] * len(expected_routes)
    for key, route in zip(keys, expected_routes, strict=True):
        page.keyboard.press(key)
        page.wait_for_url(f"**/#/vividly/{route}")

    for route in reversed(["book/overview", *expected_routes[:-1]]):
        page.go_back()
        page.wait_for_url(f"**/#/vividly/{route}")

    assert page.evaluate("history.length") == initial_history_length + len(expected_routes)
    page.go_forward()
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return location.hash === '#/vividly/book/chapter/overview'
                && presentation?._step === 0
                && presentation.hasAttribute('data-render-ready');
        }"""
    )
    page.go_back()
    page.wait_for_url("**/#/vividly/book/overview")
    page.close()


def test_sequential_arrival_selects_nearest_navigator_choice(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/outro")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/book/overview")
    choice = page.locator(".v-layer:not([hidden]) [data-vividly-navigator-choice='0']")
    expect(choice).to_be_focused()
    assert choice.get_attribute("aria-current") == "step"
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/outro")
    page.close()


def test_navigator_interval_supports_introductory_steps(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page, root_choice_start_step=2)
    page.goto(f"{runtime_url}/#/vividly/book/overview")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.keyboard.press("ArrowDown")
    assert page.url.endswith("#/vividly/book/overview")
    page.keyboard.press("ArrowUp")
    assert page.url.endswith("#/vividly/book/overview")
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/book/overview/1")
    page.keyboard.press("Enter")
    assert page.url.endswith("#/vividly/book/overview/1")
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/book/overview/2")
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/book/chapter/overview")
    page.keyboard.press("ArrowUp")
    page.wait_for_url("**/#/vividly/book/overview/2")
    page.close()


def test_navigator_allows_concluding_steps(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.route(
        "**/slides/navigator-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=(
                "import { Slide } from '../vividly/runtime/slide.js';"
                "export default class NavigatorWithConclusion extends Slide {"
                "preload(){return {steps:this.ctx.navigator"
                "?this.ctx.navigator.afterStep+3:1};}"
                "mount(root){"
                "if(!this.ctx.navigator){root.textContent=this.ctx.address;return;}"
                "this.ctx.navigator.sections.forEach((section,index)=>{"
                "const button=document.createElement('button');"
                "button.dataset.vividlyNavigatorChoice=index;"
                "button.textContent=section.title;"
                "root.append(button);"
                "});"
                "const after=document.createElement('button');"
                "after.dataset.vividlyNavigatorAfter='';"
                "after.textContent='Continue';"
                "root.append(after);"
                "}"
                "}"
            ),
        ),
    )
    page.goto(f"{runtime_url}/#/vividly/book/overview/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    context = page.locator("vividly-presentation").evaluate(
        """(element) => {
            const navigator = element._current.ctx.navigator;
            return {
                choiceStartStep: navigator.choiceStartStep,
                afterStep: navigator.afterStep,
                sections: navigator.sections,
                frozen: Object.isFrozen(navigator)
                    && Object.isFrozen(navigator.sections)
                    && navigator.sections.every(Object.isFrozen),
            };
        }"""
    )
    assert context == {
        "choiceStartStep": 0,
        "afterStep": 1,
        "sections": [{"address": "book/chapter", "title": "chapter", "step": 0}],
        "frozen": True,
    }

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/book/overview/2")
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/book/overview/3")
    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/book/overview/2")
    page.keyboard.press("Home")
    page.wait_for_url("**/#/vividly/book/overview")
    page.keyboard.press("End")
    page.wait_for_url("**/#/vividly/book/overview/3")
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/outro")
    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/book/overview/3")
    page.locator("vividly-presentation").evaluate(
        "(element) => element._navigateTo('book/overview', 1)"
    )
    page.wait_for_url("**/#/vividly/book/overview/1")
    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/book/overview")
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/book/overview/2")
    page.close()


@pytest.mark.parametrize(
    ("mount_source", "expected_error"),
    [
        (
            (
                "const after=document.createElement('button');"
                "after.dataset.vividlyNavigatorAfter='';"
                "after.textContent='Continue';"
                "root.append(after);"
            ),
            'Navigator "book/overview" is missing choice marker 0',
        ),
        (
            (
                "for(let index=0;index<2;index++){"
                "const button=document.createElement('button');"
                "button.dataset.vividlyNavigatorChoice=0;"
                "button.textContent='Chapter';"
                "root.append(button);"
                "}"
                "const after=document.createElement('button');"
                "after.dataset.vividlyNavigatorAfter='';"
                "after.textContent='Continue';"
                "root.append(after);"
            ),
            'Navigator "book/overview" has duplicate choice marker 0',
        ),
        (
            (
                "const button=document.createElement('button');"
                "button.dataset.vividlyNavigatorChoice=0;"
                "button.textContent='Chapter';"
                "root.append(button);"
                "for(let index=0;index<2;index++){"
                "const after=document.createElement('button');"
                "after.dataset.vividlyNavigatorAfter='';"
                "after.textContent='Continue';"
                "root.append(after);"
                "}"
            ),
            'Navigator "book/overview" must render at most one after control',
        ),
    ],
)
def test_navigator_validates_registered_controls(
    browser: Browser,
    runtime_url: str,
    mount_source: str,
    expected_error: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.route(
        "**/slides/navigator-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=(
                "import { Slide } from '../vividly/runtime/slide.js';"
                "export default class InvalidNavigatorControls extends Slide {"
                "preload(){return {steps:this.ctx.navigator"
                "?this.ctx.navigator.afterStep+1:1};}"
                f"mount(root){{if(!this.ctx.navigator)return;{mount_source}}}"
                "}"
            ),
        ),
    )
    errors: list[str] = []
    page.on(
        "console",
        lambda message: errors.append(message.text) if message.type == "error" else None,
    )
    page.goto(f"{runtime_url}/#/vividly/book/overview")
    page.wait_for_timeout(100)

    assert not page.locator("vividly-presentation").get_attribute("data-render-ready")
    assert any(expected_error in error for error in errors)
    page.close()


def test_navigator_controls_use_roving_focus_and_accessible_boundaries(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/book/overview")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    choice = page.locator(
        ".v-layer:not([hidden]) [data-vividly-navigator-choice='0']"
    )
    after = page.locator(".v-layer:not([hidden]) [data-vividly-navigator-after]")
    assert choice.get_attribute("tabindex") == "0"
    assert choice.get_attribute("aria-current") == "step"
    expect(choice).to_be_focused()
    assert after.get_attribute("tabindex") == "-1"
    assert after.get_attribute("aria-hidden") == "true"
    assert after.evaluate("(element) => element.inert")
    assert page.get_by_role("button", name="Continue").count() == 0

    initial_history_length = page.evaluate("history.length")
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/book/chapter/overview")
    assert page.evaluate("history.length") == initial_history_length + 1
    entered_choice = page.get_by_role("button", name="topic-a")
    expect(entered_choice).to_be_focused()
    assert entered_choice.get_attribute("aria-current") == "step"

    page.keyboard.press("ArrowDown")
    page.wait_for_url("**/#/vividly/book/chapter/overview/1")
    page.keyboard.press("Space")
    page.wait_for_url("**/#/vividly/book/chapter/topic-b/only")
    page.keyboard.press("Space")
    page.wait_for_url("**/#/vividly/book/chapter/overview/2")

    after = page.locator(".v-layer:not([hidden]) [data-vividly-navigator-after]")
    assert after.get_attribute("tabindex") == "0"
    assert after.get_attribute("aria-hidden") == "false"
    assert not after.evaluate("(element) => element.inert")
    expect(after).to_be_focused()
    assert page.get_by_role("button", name="Continue").count() == 1

    page.keyboard.press("ArrowUp")
    page.wait_for_url("**/#/vividly/book/chapter/overview/1")
    second_choice = page.locator(
        ".v-layer:not([hidden]) [data-vividly-navigator-choice='1']"
    )
    assert second_choice.evaluate("(element) => element === document.activeElement")
    page.keyboard.press("ArrowUp")
    page.wait_for_url("**/#/vividly/book/overview")
    expect(page.get_by_role("button", name="chapter", exact=True)).to_be_focused()
    page.close()


def test_navigator_route_restoration_does_not_steal_focus(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/book/overview")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    choice = page.locator(
        ".v-layer:not([hidden]) [data-vividly-navigator-choice='0']"
    )
    assert choice.get_attribute("tabindex") == "0"
    expect(choice).to_be_focused()

    help_trigger = page.locator(".v-help-trigger")
    help_trigger.focus()
    page.locator("vividly-presentation").evaluate(
        "(element) => element._navigateTo('book/overview', 1)"
    )
    page.wait_for_url("**/#/vividly/book/overview/1")
    assert help_trigger.evaluate("(element) => element === document.activeElement")
    page.go_back()
    page.wait_for_url("**/#/vividly/book/overview")
    assert help_trigger.evaluate("(element) => element === document.activeElement")
    page.close()


def test_navigator_pointer_controls_activate_explicit_steps(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/book/chapter/overview")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.locator(
        ".v-layer:not([hidden]) [data-vividly-navigator-choice='0']"
    ).click()
    page.wait_for_url("**/#/vividly/book/chapter/topic-a/first")
    page.locator("vividly-presentation").evaluate(
        "(element) => element._navigateTo('book/chapter/overview', 0)"
    )
    page.wait_for_url("**/#/vividly/book/chapter/overview")
    page.locator(
        ".v-layer:not([hidden]) [data-vividly-navigator-choice='1']"
    ).click()
    page.wait_for_url("**/#/vividly/book/chapter/topic-b/only")

    page.locator("vividly-presentation").evaluate(
        "(element) => element._navigateTo('book/chapter/overview', 2)"
    )
    page.wait_for_url("**/#/vividly/book/chapter/overview/2")
    page.locator(".v-layer:not([hidden]) [data-vividly-navigator-after]").click()
    page.wait_for_url("**/#/vividly/book/overview/1")
    page.close()


def test_navigator_spatial_arrows_follow_responsive_grid(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.set_viewport_size({"width": 620, "height": 700})
    route_spatial_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/navigator")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    presentation = page.locator("vividly-presentation")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/navigator/1")
    page.keyboard.press("ArrowDown")
    page.wait_for_url("**/#/vividly/navigator/4")

    presentation.evaluate("(element) => element._navigateTo('navigator', 2)")
    page.wait_for_url("**/#/vividly/navigator/2")
    page.keyboard.press("ArrowDown")
    page.wait_for_url("**/#/vividly/navigator/3")

    page.set_viewport_size({"width": 430, "height": 700})
    presentation.evaluate("(element) => element._navigateTo('navigator', 0)")
    page.wait_for_url("**/#/vividly/navigator")
    page.keyboard.press("ArrowDown")
    page.wait_for_url("**/#/vividly/navigator/2")
    presentation.evaluate("(element) => element._navigateTo('navigator', 1)")
    page.wait_for_url("**/#/vividly/navigator/1")
    page.keyboard.press("ArrowDown")
    page.wait_for_url("**/#/vividly/navigator/3")

    page.set_viewport_size({"width": 220, "height": 700})
    presentation.evaluate("(element) => element._navigateTo('navigator', 0)")
    page.wait_for_url("**/#/vividly/navigator")
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/navigator/1")
    page.keyboard.press("ArrowUp")
    page.wait_for_url("**/#/vividly/navigator")
    page.close()


def test_navigator_spatial_ties_use_logical_order(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_spatial_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/navigator")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.evaluate(
        """() => {
            const grid = document.querySelector(
                '.v-layer:not([hidden]) [data-spatial-grid]'
            );
            grid.style.position = 'relative';
            grid.style.display = 'block';
            const choices = grid.querySelectorAll('[data-vividly-navigator-choice]');
            const positions = [
                [0, 0],
                [200, 0],
                [200, 0],
                [0, 160],
                [200, 160],
            ];
            choices.forEach((choice, index) => {
                choice.style.position = 'absolute';
                choice.style.left = `${positions[index][0]}px`;
                choice.style.top = `${positions[index][1]}px`;
                choice.style.width = '160px';
            });
        }"""
    )

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/navigator/1")
    page.close()


def test_navigator_arrow_boundaries_do_not_wrap(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.set_viewport_size({"width": 620, "height": 700})
    route_spatial_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/navigator")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    presentation = page.locator("vividly-presentation")

    cases = [
        (0, "ArrowRight", 1),
        (0, "ArrowDown", 3),
        (0, "ArrowLeft", 0),
        (0, "ArrowUp", 0),
        (1, "ArrowLeft", 0),
        (1, "ArrowUp", 1),
        (5, "ArrowLeft", 4),
        (5, "ArrowUp", 4),
        (4, "ArrowUp", 1),
    ]
    for start, key, expected in cases:
        presentation.evaluate(
            "(element, step) => element._navigateTo('navigator', step)",
            start,
        )
        expected_start = "navigator" if start == 0 else f"navigator/{start}"
        page.wait_for_url(f"**/#/vividly/{expected_start}")
        page.keyboard.press(key)
        if expected == start:
            page.wait_for_timeout(50)
        else:
            expected_route = "navigator" if expected == 0 else f"navigator/{expected}"
            page.wait_for_url(f"**/#/vividly/{expected_route}")
        assert presentation.evaluate("(element) => element._step") == expected

    for step in (4, 5):
        for key in ("ArrowRight", "ArrowDown"):
            presentation.evaluate(
                "(element, step) => element._navigateTo('navigator', step)", step
            )
            page.wait_for_url(f"**/#/vividly/navigator/{step}")
            page.keyboard.press(key)
            page.wait_for_url("**/#/vividly/outro")
    page.close()


def test_navigator_arrow_selection_and_enter_activation(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/book/overview")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/book/chapter/overview")
    page.keyboard.press("ArrowDown")
    page.wait_for_url("**/#/vividly/book/chapter/overview/1")
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/book/chapter/topic-b/only")
    page.keyboard.press("ArrowUp")
    page.wait_for_url("**/#/vividly/book/chapter/overview/1")
    expect(page.get_by_role("button", name="topic-b", exact=True)).to_be_focused()
    page.keyboard.press("ArrowUp")
    page.wait_for_url("**/#/vividly/book/overview")
    expect(page.get_by_role("button", name="chapter", exact=True)).to_be_focused()
    page.close()


def test_direct_entry_uses_static_navigator_boundaries(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/book/chapter/topic-b/only")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/book/chapter/overview/1")
    expect(page.get_by_role("button", name="topic-b", exact=True)).to_be_focused()
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/book/chapter/topic-b/only")
    page.keyboard.press("ArrowUp")
    page.wait_for_url("**/#/vividly/book/chapter/overview/1")
    page.close()


def test_page_navigation_obeys_navigator_boundaries(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.goto(f"{runtime_url}/#/vividly/book/chapter/topic-a/second")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.keyboard.press("PageDown")
    page.wait_for_url("**/#/vividly/book/chapter/overview/1")
    expect(page.get_by_role("button", name="topic-b", exact=True)).to_be_focused()
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/book/chapter/topic-b/only")
    page.keyboard.press("PageUp")
    page.wait_for_url("**/#/vividly/book/chapter/overview/1")
    page.close()


@pytest.mark.parametrize("declared_steps", ["1", "'dynamic'"])
def test_navigator_rejects_conflicting_step_count(
    browser: Browser,
    runtime_url: str,
    declared_steps: str,
) -> None:
    page = browser.new_page()
    route_navigator_manifest(page)
    page.route(
        "**/slides/navigator-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=(
                "import { Slide } from '../vividly/runtime/slide.js';"
                "export default class InvalidNavigator extends Slide {"
                f"preload(){{return {{steps:{declared_steps}}};}}"
                "}"
            ),
        ),
    )
    errors: list[str] = []
    page.on(
        "console",
        lambda message: errors.append(message.text) if message.type == "error" else None,
    )
    page.goto(f"{runtime_url}/#/vividly/book/overview")
    page.wait_for_timeout(100)

    assert not page.locator("vividly-presentation").get_attribute("data-render-ready")
    assert any(
        'Navigator "book/overview" must declare at least 2 fixed steps' in error
        for error in errors
    )
    page.close()


def test_keyboard_navigates_steps_and_tree_levels(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    presentation = page.locator("vividly-presentation")

    page.keyboard.press("Home")
    page.wait_for_url("**/#/vividly/opening/title-card")
    page.keyboard.press("End")
    page.wait_for_url("**/#/vividly/opening/title-card/2")

    page.keyboard.press("ArrowDown")
    assert presentation.evaluate("(element) => element._step") == 2

    page.keyboard.press("PageDown")
    page.wait_for_url("**/#/vividly/images/full-bleed-image")
    page.keyboard.press("PageUp")
    page.wait_for_url("**/#/vividly/opening/title-card/2")

    page.keyboard.press("[")
    assert page.locator(".v-navigation-hud-item[data-active]").text_content() == "Opening"
    page.keyboard.press("PageDown")
    page.wait_for_url("**/#/vividly/images/full-bleed-image")
    page.wait_for_function(
        "() => document.querySelector('.v-navigation-hud-item[data-active]')?.textContent"
        " === 'Working With Images'"
    )
    assert (
        page.locator(".v-navigation-hud-item[data-active]").text_content()
        == "Working With Images"
    )

    page.keyboard.press("PageDown")
    page.wait_for_url("**/#/vividly/mechanics/markdown-controls")
    page.keyboard.press("PageUp")
    page.wait_for_url("**/#/vividly/images/contact-sheet/*")
    assert presentation.evaluate(
        "(element) => element._step === element._current.steps - 1"
    )

    page.keyboard.press("]")
    assert page.locator(".v-navigation-hud-item[data-active]").text_content() == "Contact Sheet"
    page.close()


def test_toc_resets_page_navigation_to_slide_level(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    start_presentation(page)
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.keyboard.press("[")
    page.keyboard.press("Escape")
    page.wait_for_url("**/#/vividly/")
    page.locator(".v-toc").wait_for(state="visible")
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/opening/title-card")

    forward = [
        "images/full-bleed-image",
        "images/image-fit-modes",
        "images/photo-tour",
        "images/contact-sheet",
        "mechanics/markdown-controls",
        "mechanics/diagram-build",
        "mechanics/annotated-markdown",
    ]
    for address in forward:
        page.keyboard.press("PageDown")
        page.wait_for_url(f"**/#/vividly/{address}")

    backward = [
        "mechanics/diagram-build",
        "mechanics/markdown-controls",
        "images/contact-sheet",
        "images/photo-tour",
        "images/image-fit-modes",
        "images/full-bleed-image",
        "opening/title-card",
    ]
    for address in backward:
        page.keyboard.press("PageUp")
        page.wait_for_function(
            """(address) => {
                const route = `#/vividly/${address}`;
                return location.hash === route || location.hash.startsWith(`${route}/`);
            }
            """,
            arg=address,
        )

    page.close()


def test_escape_from_toc_opens_catalog(browser: Browser, runtime_url: str) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.locator(".v-toc").wait_for(state="visible")

    page.keyboard.press("Escape")
    page.wait_for_url("**/#/")

    assert page.get_by_role("navigation", name="Project catalog").is_visible()
    page.close()


def test_catalog_and_toc_share_accessible_top_bar(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/")
    catalog = page.get_by_role("navigation", name="Project catalog")
    catalog.wait_for(state="visible")

    catalog_header = catalog.locator(".v-overview-header")
    catalog_logo = catalog_header.get_by_role("img", name="Vividly")
    catalog_logo_src = catalog_logo.get_attribute("src")
    assert catalog_logo_src is not None
    assert catalog_logo_src.endswith("/vividly/assets/logo.svg")
    assert catalog_logo.evaluate(
        """element => {
            const width = element.getBoundingClientRect().width;
            return width >= 150 && width <= 154;
        }"""
    )
    assert catalog_logo.evaluate(
        "(element) => element.getBoundingClientRect().height <= 40"
    )
    catalog_identity_bounds = catalog_header.locator(
        ".v-overview-identity"
    ).bounding_box()
    catalog_logo_bounds = catalog_logo.bounding_box()
    catalog_header_bounds = catalog_header.bounding_box()
    assert catalog_identity_bounds is not None
    assert catalog_logo_bounds is not None
    assert catalog_header_bounds is not None
    assert abs(catalog_identity_bounds["x"] - catalog_header_bounds["x"]) < 1
    assert catalog_logo_bounds["x"] < catalog_identity_bounds["x"]
    assert catalog_identity_bounds["width"] < catalog_logo_bounds["width"]
    catalog_breadcrumbs = catalog_header.get_by_role("navigation", name="Breadcrumb")
    assert catalog_breadcrumbs.locator('[aria-current="page"]').text_content() == "Catalog"
    assert catalog_header.locator(".v-overview-actions").count() == 0

    page.get_by_role("link", name="Vividly Runtime Shakedown").click()
    page.wait_for_url("**/#/vividly/")
    toc = page.get_by_role("navigation", name="Presentation outline")
    toc.wait_for(state="visible")
    toc_header = toc.locator(".v-overview-header")
    assert toc_header.get_by_role("img", name="Vividly").count() == 1
    toc_breadcrumbs = toc_header.get_by_role("navigation", name="Breadcrumb")
    catalog_link = toc_breadcrumbs.get_by_role("link", name="Catalog")
    assert catalog_link.get_attribute("href") == "#/"
    assert (
        toc_breadcrumbs.locator('[aria-current="page"]').text_content()
        == "Vividly Runtime Shakedown"
    )
    assert toc_header.locator(".v-overview-actions").count() == 1
    assert toc_header.locator('input[type="checkbox"]').count() == 0
    assert toc.evaluate(
        "(element) => Number.parseFloat(getComputedStyle(element).paddingTop)"
    ) == 32
    show_thumbnails = toc_header.get_by_role(
        "button", name="Show thumbnails", exact=True
    )
    expand_steps = toc_header.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    )
    assert show_thumbnails.get_attribute("aria-pressed") == "false"
    assert show_thumbnails.get_attribute("title") == "Show thumbnails"
    assert show_thumbnails.locator(".v-overview-icon").count() == 1
    assert show_thumbnails.evaluate("(button) => button.innerText === ''")
    assert expand_steps.get_attribute("title") == "Expand/collapse steps"
    assert expand_steps.locator(".v-overview-icon").count() == 2
    assert expand_steps.locator(".v-overview-icon-expand").is_visible()
    assert expand_steps.locator(".v-overview-icon-collapse").is_hidden()
    assert expand_steps.evaluate("(button) => button.innerText === ''")
    layout = toc_header.evaluate(
        """header => {
            const box = (selector) =>
                header.querySelector(selector).getBoundingClientRect();
            return {
                identity: box('.v-overview-identity'),
                modes: box('.v-overview-modes'),
                breadcrumbs: box('.v-breadcrumbs'),
                options: box('.v-overview-options'),
            };
        }"""
    )
    assert abs(
        (layout["identity"]["top"] + layout["identity"]["bottom"]) / 2
        - (layout["modes"]["top"] + layout["modes"]["bottom"]) / 2
    ) < 2
    assert abs(
        (layout["breadcrumbs"]["top"] + layout["breadcrumbs"]["bottom"]) / 2
        - (layout["options"]["top"] + layout["options"]["bottom"]) / 2
    ) < 2
    assert layout["identity"]["bottom"] <= layout["breadcrumbs"]["top"]
    modes_box = toc_header.locator(".v-overview-modes").bounding_box()
    header_box = toc_header.bounding_box()
    assert modes_box is not None
    assert header_box is not None
    assert abs(
        modes_box["x"] + modes_box["width"] - header_box["x"] - header_box["width"]
    ) < 1

    page.set_viewport_size({"width": 360, "height": 640})
    responsive_layout = toc_header.evaluate(
        """header => {
            const box = (selector) =>
                header.querySelector(selector).getBoundingClientRect();
            return {
                fits: header.scrollWidth <= header.clientWidth,
                identity: box('.v-overview-identity'),
                modes: box('.v-overview-modes'),
                breadcrumbs: box('.v-breadcrumbs'),
                options: box('.v-overview-options'),
            };
        }"""
    )
    assert responsive_layout["fits"]
    assert (
        responsive_layout["breadcrumbs"]["top"]
        >= responsive_layout["identity"]["bottom"]
    )
    assert (
        responsive_layout["options"]["top"]
        >= responsive_layout["breadcrumbs"]["bottom"]
    )
    responsive_modes_box = toc_header.locator(".v-overview-modes").bounding_box()
    responsive_header_box = toc_header.bounding_box()
    assert responsive_modes_box is not None
    assert responsive_header_box is not None
    assert (
        responsive_modes_box["y"]
        >= responsive_layout["breadcrumbs"]["bottom"]
    )
    assert abs(
        responsive_modes_box["x"] + responsive_modes_box["width"]
        - responsive_header_box["x"] - responsive_header_box["width"]
    ) < 1

    slide_page = browser.new_page()
    slide_page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    assert not slide_page.locator(".v-overview-header").is_visible()
    slide_page.close()

    catalog_link.click()
    page.wait_for_url("**/#/")
    assert catalog.is_visible()
    page.close()


def test_toc_selects_the_current_slide_without_stealing_restored_focus(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page(viewport={"width": 800, "height": 500})
    page.goto(f"{runtime_url}/#/vividly/mechanics/markdown-controls")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.keyboard.press("Escape")
    page.wait_for_url("**/#/vividly/")
    current = page.locator(
        ".v-toc-item.focused[data-address='mechanics/markdown-controls']"
    )
    assert current.evaluate("(element) => element === document.activeElement")
    assert current.evaluate(
        """element => {
            const box = element.getBoundingClientRect();
            return box.top >= 0 && box.bottom <= innerHeight;
        }"""
    )

    page.locator(".v-toc-item[data-address='images/full-bleed-image']").click()
    page.wait_for_url("**/#/vividly/images/full-bleed-image")
    page.keyboard.press("Escape")
    page.wait_for_url("**/#/vividly/")
    assert (
        page.locator(".v-toc-item.focused").get_attribute("data-address")
        == "images/full-bleed-image"
    )

    page.locator(".v-toc-item[data-address='mechanics/diagram-build']").click()
    page.wait_for_url("**/#/vividly/mechanics/diagram-build")
    page.locator(".v-help-trigger").focus()
    page.evaluate("location.hash = '#/vividly/'")
    page.wait_for_url("**/#/vividly/")
    assert (
        page.locator(".v-toc-item.focused").get_attribute("data-address")
        == "mechanics/diagram-build"
    )
    assert page.locator(".v-help-trigger").evaluate(
        "(element) => element === document.activeElement"
    )

    page.reload()
    page.locator(".v-toc").wait_for(state="visible")
    assert (
        page.locator(".v-toc-item.focused").get_attribute("data-address")
        == "opening/title-card"
    )
    assert not page.locator(".v-toc-item.focused").evaluate(
        "(element) => element === document.activeElement"
    )
    page.close()


@pytest.mark.parametrize(
    "view",
    ["catalog", "outline", "outline-steps", "grid", "grid-expanded-0", "grid-expanded-1"],
)
def test_overview_hover_lightens_without_selection_accents(
    browser: Browser,
    runtime_url: str,
    view: str,
) -> None:
    page = browser.new_page()
    page.route(
        "**/thumbnails/index.json",
        lambda route: route.fulfill(
            json={
                "version": 3,
                "presentations": {
                    "vividly": {
                        "opening/title-card": {
                            "canonicalStep": 2,
                            "steps": [
                                {
                                    "step": step,
                                    "path": f"vividly/opening/title-card/step-{step:04d}.png",
                                    "revision": THUMBNAIL_REVISION,
                                }
                                for step in range(3)
                            ],
                        },
                    },
                },
            }
        ),
    )
    if view == "catalog":
        route_multi_presentation_project(page)
        page.goto(f"{runtime_url}/#/")
        container = page.locator(".v-catalog")
        items = container.locator(".v-catalog-item:not(.focused)")
    else:
        page.goto(f"{runtime_url}/#/vividly/")
        container = page.locator(".v-toc")
        container.wait_for(state="visible")
        if view.startswith("grid"):
            page.get_by_role("button", name="Grid", exact=True).click()
            items = container.locator(".v-grid-item:not(.focused)")
        else:
            items = container.locator(".v-toc-item:not(.focused)")
        if view == "outline-steps" or view.startswith("grid-expanded"):
            page.get_by_role("button", name="Expand/collapse steps", exact=True).click()
        if view == "outline-steps":
            items = container.locator(".v-outline-step:not(.focused)")
        elif view.startswith("grid-expanded"):
            items = container.locator(
                f".v-grid-item[data-sequence-tone='{view[-1]}']:not(.focused)"
            )

    container.wait_for(state="visible")
    page.mouse.move(0, 0)
    hovered = items.first
    hovered.wait_for(state="visible")
    selected = container.locator(".v-overview-item.focused:visible")
    selected_element = selected.element_handle()
    focus = page.evaluate_handle("document.activeElement")
    read_style = """element => {
        const style = getComputedStyle(element);
        return {
            background: style.backgroundColor,
            borders: [style.borderTopColor, style.borderRightColor,
                style.borderBottomColor, style.borderLeftColor],
        };
    }"""
    before = hovered.evaluate(read_style)
    selected_before = selected.evaluate(read_style)
    hovered.hover()
    after = hovered.evaluate(read_style)
    assert after["background"] != before["background"]
    assert after["borders"] == before["borders"]
    assert selected.evaluate(read_style)["borders"] == selected_before["borders"]
    assert selected.evaluate("(element, previous) => element === previous", selected_element)
    assert page.evaluate("(previous) => document.activeElement === previous", focus)
    page.close()


def test_toc_focus_is_passive_and_canonical_activation_uses_first_step(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?._step === 2"
    )

    page.keyboard.press("Escape")
    page.wait_for_url("**/#/vividly/")
    current = page.locator(
        '.v-toc .v-overview-item.focused[data-address="opening/title-card"]'
    )
    assert current.evaluate("(element) => element === document.activeElement")

    grid = page.get_by_role("button", name="Grid", exact=True)
    grid.click()
    assert page.locator(
        '.v-toc-grid .v-overview-item.focused[data-address="opening/title-card"]'
    ).count() == 1
    assert grid.evaluate("(element) => element === document.activeElement")

    expected_down_address = page.locator(".v-toc-grid .v-grid-item").evaluate_all(
        """items => {
            const current = items.find((item) => item.classList.contains('focused'));
            const currentBox = current.getBoundingClientRect();
            const below = items
                .map((item) => ({ item, box: item.getBoundingClientRect() }))
                .filter(({ box }) => box.top > currentBox.top + 1);
            const nextRowTop = Math.min(...below.map(({ box }) => box.top));
            return below
                .filter(({ box }) => Math.abs(box.top - nextRowTop) < 1)
                .sort(({ box: left }, { box: right }) =>
                    Math.abs((left.left + left.right) / 2
                        - (currentBox.left + currentBox.right) / 2)
                    - Math.abs((right.left + right.right) / 2
                        - (currentBox.left + currentBox.right) / 2)
                )[0].item.dataset.address;
        }"""
    )
    page.keyboard.press("ArrowDown")
    assert page.locator(
        ".v-toc .v-overview-body:not([hidden]) .v-overview-item.focused"
    ).get_attribute("data-address") == expected_down_address
    presentation = page.locator("vividly-presentation")
    assert presentation.evaluate("(element) => element._index") == 0
    assert presentation.evaluate("(element) => element._step") == 2

    page.keyboard.press("ArrowUp")
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/opening/title-card")
    assert presentation.evaluate("(element) => element._step") == 0

    page.keyboard.press("Escape")
    page.wait_for_url("**/#/vividly/")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/images/full-bleed-image")
    assert presentation.evaluate("(element) => element._step") == 0
    page.close()


def test_overview_header_stays_visible_while_keyboard_selection_scrolls(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page(viewport={"width": 800, "height": 500})
    page.goto(f"{runtime_url}/#/vividly/")
    page.locator(".v-toc").wait_for(state="visible")
    page.get_by_role("button", name="Show thumbnails", exact=True).click()

    header = page.locator(".v-toc > .v-overview-header")
    body = page.locator(".v-toc > .v-overview-body:not([hidden])")
    assert body.evaluate("(element) => element.scrollHeight > element.clientHeight")
    assert body.evaluate("(element) => getComputedStyle(element).overflowY") == "auto"
    assert body.evaluate("(element) => getComputedStyle(element).scrollbarGutter") == "stable"
    assert body.evaluate(
        """element => {
            const body = element.getBoundingClientRect();
            const item = element.querySelector('.v-toc-item').getBoundingClientRect();
            const inset = Number.parseFloat(getComputedStyle(element).paddingInlineEnd);
            return inset > 0 && item.right <= body.right - inset;
        }"""
    )

    page.keyboard.press("End")
    assert body.evaluate("(element) => element.scrollTop > 0")
    assert header.evaluate(
        """element => {
            const box = element.getBoundingClientRect();
            return box.top >= 0 && box.bottom <= innerHeight;
        }"""
    )

    page.keyboard.press("Home")
    assert body.evaluate("(element) => element.scrollTop") == 0
    assert page.locator(".v-toc-item").first.evaluate(
        """element => {
            const item = element.getBoundingClientRect();
            const body = element.closest('.v-overview-body').getBoundingClientRect();
            return item.top >= body.top && item.top < body.bottom;
        }"""
    )
    assert header.evaluate(
        """element => {
            const box = element.getBoundingClientRect();
            return box.top >= 0 && box.bottom <= innerHeight;
        }"""
    )
    page.close()


def test_toc_outline_and_grid_expand_indexed_steps_without_loading_slides(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.route(
        "**/thumbnails/index.json",
        lambda route: route.fulfill(
            json={
                "version": 3,
                "presentations": {
                    "vividly": {
                        "opening/title-card": {
                            "canonicalStep": 2,
                            "steps": [
                                {
                                    "step": step,
                                    "path": (
                                        "vividly/opening/title-card/"
                                        f"step-{step:04d}.png"
                                    ),
                                    "revision": THUMBNAIL_REVISION,
                                }
                                for step in range(3)
                            ],
                        }
                    }
                },
            }
        ),
    )
    page.goto(f"{runtime_url}/#/vividly/")
    page.locator(".v-toc").wait_for(state="visible")
    presentation = page.locator("vividly-presentation")
    assert presentation.evaluate("(element) => element._leaves.every((leaf) => !leaf.rec)")

    show_thumbnails = page.get_by_role("button", name="Show thumbnails", exact=True)
    assert show_thumbnails.count() == 1
    show_thumbnails.click()
    outline_expansion = page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    )
    assert outline_expansion.count() == 1
    outline_expansion.click()
    assert page.locator(".v-toc .v-overview-item:visible[data-step]").count() > 0
    assert presentation.evaluate("(element) => element._leaves.every((leaf) => !leaf.rec)")

    page.get_by_role("button", name="Grid", exact=True).click()
    grid_expansion = page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    )
    assert grid_expansion.get_attribute("aria-expanded") == "true"
    assert page.locator(".v-toc .v-overview-item:visible[data-step]").count() > 0

    grid_expansion.click()
    collapsed_items = page.locator(".v-toc .v-overview-item:visible")
    assert collapsed_items.count() == presentation.evaluate(
        "(element) => element._leaves.length"
    )
    assert collapsed_items.locator("[data-step]").count() == 0

    assert grid_expansion.get_attribute("aria-expanded") == "false"
    grid_expansion.click()
    assert page.locator(".v-toc .v-overview-item:visible[data-step]").count() > 0
    assert page.locator(".v-toc .v-thumbnail img:visible").evaluate_all(
        "images => images.every((image) => image.loading === 'lazy')"
    )
    assert presentation.evaluate("(element) => element._leaves.every((leaf) => !leaf.rec)")

    page.locator(
        '.v-toc .v-overview-item:visible[data-address="opening/title-card"][data-step="1"]'
    ).click()
    page.wait_for_url("**/#/vividly/opening/title-card/1")
    page.close()


def test_outline_steps_follow_persisted_thumbnail_and_expansion_preferences(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page(viewport={"width": 720, "height": 600})
    page.route(
        "**/thumbnails/index.json",
        lambda route: route.fulfill(
            json={
                "version": 3,
                "presentations": {
                    "vividly": {
                        "opening/title-card": {
                            "canonicalStep": 2,
                            "steps": [
                                {
                                    "step": step,
                                    "path": (
                                        "vividly/opening/title-card/"
                                        f"step-{step:04d}.png"
                                    ),
                                    "revision": THUMBNAIL_REVISION,
                                }
                                for step in range(3)
                            ],
                        },
                        "mechanics/diagram-build": {
                            "canonicalStep": 3,
                            "steps": [
                                {
                                    "step": step,
                                    "path": (
                                        "vividly/mechanics/diagram-build/"
                                        f"step-{step:04d}.png"
                                    ),
                                    "revision": THUMBNAIL_REVISION,
                                }
                                for step in range(8)
                            ],
                        },
                    }
                },
            }
        ),
    )
    page.route(
        "**/thumbnails/vividly/opening/title-card/step-*.png*",
        lambda route: route.fulfill(
            content_type="image/svg+xml",
            body='<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"/>',
        ),
    )
    page.route(
        "**/thumbnails/vividly/mechanics/diagram-build/step-*.png*",
        lambda route: route.fulfill(status=404, body="missing"),
    )
    page.goto(f"{runtime_url}/#/vividly/")
    page.locator(".v-toc").wait_for(state="visible")
    presentation = page.locator("vividly-presentation")
    show_thumbnails = page.get_by_role("button", name="Show thumbnails", exact=True)

    assert show_thumbnails.get_attribute("aria-pressed") == "false"
    expand_steps = page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    )
    assert expand_steps.is_enabled()
    assert expand_steps.get_attribute("aria-expanded") == "false"
    expand_steps.click()
    assert show_thumbnails.get_attribute("aria-pressed") == "true"
    step_items = page.locator(".v-toc-outline .v-outline-step:visible")
    assert step_items.count() > 0
    assert step_items.evaluate_all(
        """items => items.every((item) => {
            const owner = item.closest('.v-toc-item');
            return owner?.dataset.address === item.dataset.address;
        })"""
    )
    assert page.locator(".v-outline-steps:visible").evaluate_all(
        """groups => groups.every((group) => {
            const style = getComputedStyle(group);
            return style.overflowX === 'visible'
                && group.scrollWidth <= group.clientWidth;
        })"""
    )
    assert page.locator(
        '.v-outline-step[data-address="opening/title-card"] img'
    ).evaluate_all("images => images.every((image) => image.loading === 'lazy')")
    assert page.locator(
        '.v-outline-step[data-address="mechanics/diagram-build"] '
        ".v-thumbnail-placeholder"
    ).first.text_content() == "CSS-Driven Build"
    assert presentation.evaluate("(element) => element._leaves.every((leaf) => !leaf.rec)")

    page.get_by_role("button", name="Grid", exact=True).click()
    assert page.get_by_role("button", name="Expand/collapse steps", exact=True).get_attribute(
        "aria-expanded"
    ) == "true"
    page.get_by_role("button", name="Outline", exact=True).click()
    assert page.get_by_role("button", name="Expand/collapse steps", exact=True).get_attribute(
        "aria-expanded"
    ) == "true"

    page.keyboard.press("Home")
    first_slide = page.locator(".v-toc-outline .v-toc-item").first
    first_address = first_slide.get_attribute("data-address")
    second_slide = page.locator(".v-toc-outline .v-toc-item").nth(1)
    second_address = second_slide.get_attribute("data-address")
    page.keyboard.press("ArrowDown")
    assert second_slide.evaluate("(element) => element.classList.contains('focused')")
    page.keyboard.press("ArrowUp")
    assert first_slide.evaluate("(element) => element.classList.contains('focused')")

    page.keyboard.press("ArrowRight")
    first_step = page.locator(".v-toc-outline .v-outline-step.focused")
    assert first_step.get_attribute("data-address") == first_address
    assert first_step.get_attribute("data-step") == "0"
    page.keyboard.press("ArrowRight")
    assert page.locator(".v-toc-outline .v-outline-step.focused").get_attribute(
        "data-step"
    ) == "1"
    page.keyboard.press("ArrowLeft")
    assert page.locator(".v-toc-outline .v-outline-step.focused").get_attribute(
        "data-step"
    ) == "0"
    page.keyboard.press("ArrowLeft")
    assert first_slide.evaluate("(element) => element.classList.contains('focused')")

    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowDown")
    assert second_slide.evaluate("(element) => element.classList.contains('focused')")
    page.keyboard.press("ArrowUp")
    assert first_slide.evaluate("(element) => element.classList.contains('focused')")

    page.keyboard.press("End")
    last_slide = page.locator(".v-toc-outline .v-toc-item").last
    assert last_slide.evaluate("(element) => element.classList.contains('focused')")
    assert page.locator(".v-toc-outline .v-outline-step.focused").count() == 0
    page.keyboard.press("Home")
    assert first_slide.evaluate("(element) => element.classList.contains('focused')")

    first_step = page.locator(
        '.v-outline-step[data-address="opening/title-card"][data-step="0"]'
    )
    first_step.focus()
    page.keyboard.press("s")
    assert expand_steps.get_attribute("aria-expanded") == "false"
    assert first_slide.evaluate("(element) => element === document.activeElement")
    page.keyboard.press("s")
    assert expand_steps.get_attribute("aria-expanded") == "true"

    show_thumbnails.click()
    assert expand_steps.count() == 1
    assert expand_steps.is_enabled()
    assert page.locator(".v-toc-outline .v-outline-step:visible").count() == 0
    page.keyboard.press("ArrowDown")
    assert second_slide.get_attribute("data-address") == second_address
    assert second_slide.evaluate("(element) => element.classList.contains('focused')")
    assert page.locator(".v-toc-outline .v-outline-step.focused").count() == 0
    page.keyboard.press("s")
    assert show_thumbnails.get_attribute("aria-pressed") == "true"
    assert expand_steps.get_attribute("aria-expanded") == "true"
    page.keyboard.press("s")
    assert expand_steps.get_attribute("aria-expanded") == "false"
    page.keyboard.press("s")
    assert expand_steps.get_attribute("aria-expanded") == "true"
    assert page.locator(".v-toc-outline .v-outline-step:visible").count() > 0

    page.locator(
        '.v-toc-outline .v-outline-step[data-address="opening/title-card"][data-step="1"]'
    ).click()
    page.wait_for_url("**/#/vividly/opening/title-card/1")
    page.keyboard.press("Escape")
    page.wait_for_url("**/#/vividly/")
    assert page.get_by_role("button", name="Expand/collapse steps", exact=True).get_attribute(
        "aria-expanded"
    ) == "true"
    assert page.locator(
        '.v-toc-outline .v-outline-step[data-address="opening/title-card"]'
        '[data-step="1"]'
    ).get_attribute("aria-current") == "step"
    assert page.locator(
        '.v-toc-outline .v-outline-step[data-address="opening/title-card"]'
        '[data-step="1"]'
    ).evaluate("(element) => element === document.activeElement")
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    assert page.locator(
        '.v-toc-outline .v-toc-item[data-address="opening/title-card"]'
    ).evaluate("(element) => element === document.activeElement")
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/vividly/opening/title-card")
    assert presentation.evaluate("(element) => element._step") == 0
    page.keyboard.press("Escape")
    page.wait_for_url("**/#/vividly/")

    page.reload()
    page.locator(".v-toc").wait_for(state="visible")
    assert page.get_by_role(
        "button", name="Show thumbnails", exact=True
    ).get_attribute("aria-pressed") == "true"
    assert page.get_by_role("button", name="Expand/collapse steps", exact=True).get_attribute(
        "aria-expanded"
    ) == "true"
    assert page.locator(".v-toc-outline .v-outline-step:visible").count() > 0
    assert presentation.evaluate("(element) => element._leaves.every((leaf) => !leaf.rec)")
    page.close()


@pytest.mark.parametrize("policy", ["auto", "always"])
def test_keyboard_help_controls_support_keyboard_without_dismissal(
    browser: Browser, runtime_url: str, policy: str
) -> None:
    page = browser.new_page()
    manifest = yaml.safe_load(
        (FIXTURE_ROOT / "presentations/vividly.yaml").read_text(encoding="utf-8")
    )
    manifest["keyboardHints"] = policy
    page.route(
        "**/presentations/vividly.yaml",
        lambda route: route.fulfill(content_type="application/yaml", body=json.dumps(manifest)),
    )
    page.goto(f"{runtime_url}/?vividly-skip-hints=1#/vividly/opening/title-card")
    page.locator("vividly-presentation[data-render-ready]").wait_for()
    trigger = page.get_by_role("button", name="Keyboard shortcuts")
    trigger.click()
    help_overlay = page.locator(".v-keyboard-help")
    expect(help_overlay).to_be_focused()
    checkbox = help_overlay.get_by_label("Show navigation hints when presentations start")
    documentation = help_overlay.get_by_role("link", name="Documentation")
    branding = help_overlay.get_by_role("link", name="Powered by Vividly")
    page.keyboard.press("Tab")
    if policy == "auto":
        expect(checkbox).to_be_focused()
        page.keyboard.press("Space")
        expect(checkbox).not_to_be_checked()
        expect(help_overlay).to_be_visible()
        checkbox.click()
        expect(checkbox).to_be_checked()
        assert help_overlay.get_attribute("data-closing") is None
        page.keyboard.press("Tab")
    else:
        expect(checkbox).to_be_disabled()
    expect(documentation).to_be_focused()
    page.keyboard.press("Tab")
    expect(branding).to_be_focused()
    page.keyboard.press("Tab")
    expect(checkbox if policy == "auto" else documentation).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(branding).to_be_focused()
    page.keyboard.press("Escape")
    expect(help_overlay).to_be_hidden()
    expect(trigger).to_be_focused()
    assert page.url.endswith("#/vividly/opening/title-card")
    page.close()


def test_keyboard_help_opens_and_dismisses_without_navigating(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    start_presentation(page)
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    help_overlay = page.locator(".v-keyboard-help")
    help_trigger = page.get_by_role("button", name="Keyboard shortcuts")

    assert help_trigger.is_visible()
    assert help_trigger.evaluate("(element) => getComputedStyle(element).opacity") == "0.35"
    help_trigger.hover()
    page.wait_for_timeout(150)
    assert help_trigger.evaluate("(element) => getComputedStyle(element).opacity") == "1"
    page.keyboard.press("?")
    assert help_overlay.is_visible()
    assert help_overlay.get_attribute("role") == "dialog"
    assert help_overlay.locator("kbd").count() == 27
    assert not help_overlay.get_by_text("Slide sorter", exact=True).is_visible()
    assert help_overlay.locator("kbd").all_text_contents()[:3] == ["Space", "→", "←"]
    assert help_overlay.get_by_text("Move navigator selection", exact=True).is_visible()
    assert help_overlay.get_by_text("Next structural state", exact=True).is_visible()
    assert help_overlay.get_by_text("Open navigator selection", exact=True).is_visible()
    assert help_overlay.get_by_text("TOC Grid mode", exact=True).is_visible()
    assert help_overlay.get_by_text("TOC Outline mode", exact=True).is_visible()
    assert help_overlay.get_by_text(
        "TOC expand or collapse steps", exact=True
    ).is_visible()
    assert (
        help_overlay.locator(".v-keyboard-help-arrow").first.evaluate(
            "(element) => getComputedStyle(element).fontSize"
        )
        == "18px"
    )

    page.keyboard.press("Escape")
    help_overlay.wait_for(state="hidden")
    assert page.url.endswith("#/vividly/opening/title-card")

    help_trigger.click()
    assert help_overlay.is_visible()
    page.locator(".v-keyboard-help-panel").click()
    help_overlay.wait_for(state="hidden")

    page.goto(f"{runtime_url}/?vividly-capture=1#/vividly/opening/title-card")
    assert not help_trigger.is_visible()
    page.keyboard.press("?")
    assert not help_overlay.is_visible()
    page.close()


def test_same_direction_navigation_after_grace_settles_without_changing_state(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "css")
    root = page.locator(".v-layer:not([hidden]) [data-mode='css']")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/css/1")
    page.wait_for_function(
        """() => document.querySelector(
            ".v-layer:not([hidden]) [data-step-motion]"
        ).getAnimations().some(
            (animation) => animation instanceof CSSTransition
                && animation.playState === "running"
        )"""
    )
    before = root.evaluate(
        """(element) => ({
            setStepCalls: element.dataset.setStepCalls,
            stepEvents: element.dataset.stepEvents,
            slideEnterEvents: element.dataset.slideEnterEvents,
            historyLength: history.length,
        })"""
    )

    configure_active_step_transitions(page, 750)
    page.keyboard.press("ArrowRight")
    wait_for_navigation_queue(page)

    assert page.url.endswith("#/vividly/css/1")
    assert root.evaluate(
        """(element) => ({
            setStepCalls: element.dataset.setStepCalls,
            stepEvents: element.dataset.stepEvents,
            slideEnterEvents: element.dataset.slideEnterEvents,
            historyLength: history.length,
            persistedStep: document.querySelector('vividly-presentation')
                ._current.ctx.state.get('step'),
            runningTransitions: element.querySelector('[data-step-motion]')
                .getAnimations()
                .filter((animation) => animation instanceof CSSTransition
                    && animation.playState === 'running')
                .length,
        })"""
    ) == {
        **before,
        "persistedStep": 1,
        "runningTransitions": 0,
    }

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/css/2")
    page.close()


@pytest.mark.parametrize(
    ("elapsed_ms", "expected_route"),
    [
        (499, "css/2"),
        (500, "css/2"),
        (501, "css/1"),
        (750, "css/1"),
    ],
)
def test_transition_completion_grace_uses_elapsed_wall_clock_time(
    browser: Browser,
    runtime_url: str,
    elapsed_ms: float,
    expected_route: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "css")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/css/1")
    configure_active_step_transitions(
        page,
        elapsed_ms,
        advance_delta=1,
    )

    assert page.url.endswith(f"#/vividly/{expected_route}")
    page.close()


def test_transition_completion_grace_does_not_depend_on_remaining_time(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "css")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/css/1")
    configure_active_step_transitions(
        page,
        50,
        remaining_ms=[50, 150],
        advance_delta=1,
    )
    assert page.url.endswith("#/vividly/css/2")

    configure_active_step_transitions(
        page,
        750,
        remaining_ms=[50, 100],
        advance_delta=1,
    )
    assert page.url.endswith("#/vividly/css/2")
    page.close()


@pytest.mark.parametrize(
    ("playback_rate", "paused", "elapsed_ms", "expected_route"),
    [
        (0, False, 50, "css/2"),
        (1, True, 50, "css/2"),
        (0, False, 750, "css/1"),
        (1, True, 750, "css/1"),
    ],
)
def test_paused_and_zero_rate_transitions_use_elapsed_grace(
    browser: Browser,
    runtime_url: str,
    playback_rate: float,
    paused: bool,
    elapsed_ms: float,
    expected_route: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "css")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/css/1")
    configure_active_step_transitions(
        page,
        elapsed_ms,
        playback_rate=playback_rate,
        paused=paused,
    )
    page.keyboard.press("ArrowRight")
    wait_for_navigation_queue(page)

    assert page.url.endswith(f"#/vividly/{expected_route}")
    page.close()


def test_rapid_forward_navigation_settles_in_queue_order(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "css")

    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    wait_for_navigation_queue(page)

    assert page.url.endswith("#/vividly/css/3")
    assert page.locator("vividly-presentation").evaluate("(element) => element._step") == 3
    page.close()


def test_backward_navigation_settles_and_opposite_direction_reverses(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "css/1")

    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/css")
    page.wait_for_function(
        """() => document.querySelector(
            ".v-layer:not([hidden]) [data-step-motion]"
        ).getAnimations().some(
            (animation) => animation instanceof CSSTransition
                && animation.playState === "running"
        )"""
    )
    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/intro")

    page.goto(f"{runtime_url}/#/vividly/css/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/css")
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/css/1")
    page.close()


def test_step_motion_settles_before_crossing_slide_boundaries(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "css/2")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/css/3")
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/custom")

    page.goto(f"{runtime_url}/#/vividly/css/1")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/css")
    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/intro")
    page.close()


def test_completed_and_destination_motion_do_not_consume_navigation(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "css")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/css/1")
    finish_active_step_transitions(page)
    page.keyboard.press("ArrowRight")
    wait_for_navigation_queue(page)
    assert page.url.endswith("#/vividly/css/2")

    page.goto(f"{runtime_url}/#/vividly/css")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/css/1")
    page.keyboard.press("End")
    page.wait_for_url("**/#/vividly/css/3")
    page.keyboard.press("ArrowLeft")
    page.wait_for_url("**/#/vividly/css/2")
    page.close()


@pytest.mark.parametrize(
    ("action", "expected_route"),
    [
        ("forward", "css/2"),
        ("reverse", "intro"),
        ("boundary", "custom"),
        ("navigator", "outro"),
        ("space", "beta/only"),
    ],
)
def test_completion_grace_is_consistent_across_navigation_actions(
    browser: Browser,
    runtime_url: str,
    action: str,
    expected_route: str,
) -> None:
    page = browser.new_page()
    route = {
        "forward": "css",
        "reverse": "css/1",
        "boundary": "css/2",
        "navigator": "navigator",
        "space": "navigator",
    }[action]
    open_animation_settling_slide(page, runtime_url, route)

    key = "ArrowLeft" if action == "reverse" else "ArrowRight"
    page.keyboard.press(key)
    wait_for_navigation_queue(page)
    configure_active_step_transitions(page, 50)
    page.keyboard.press("Space" if action == "space" else key)
    wait_for_navigation_queue(page)

    assert page.url.endswith(f"#/vividly/{expected_route}")
    page.close()


def test_custom_settler_consumes_navigation_until_custom_motion_finishes(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "custom")
    root = page.locator(".v-layer:not([hidden]) [data-mode='custom']")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/custom/1")
    assert root.locator("[data-custom-state]").evaluate("(element) => element.value") == "running"

    page.keyboard.press("ArrowRight")
    wait_for_navigation_queue(page)
    assert page.url.endswith("#/vividly/custom/1")
    assert root.locator("[data-custom-state]").evaluate("(element) => element.value") == "settled"
    assert root.get_attribute("data-settle-calls") == "2"

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/custom/2")
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/ambient")
    page.close()


def test_custom_settler_consumes_within_css_completion_grace(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "custom")
    root = page.locator(".v-layer:not([hidden]) [data-mode='custom']")
    root.locator("[data-step-motion], [data-step-motion-secondary]").evaluate_all(
        """(elements) => elements.forEach((element) => {
            element.style.transform = 'translateX(calc(var(--step) * 20px))';
            element.style.transition = 'transform 5s linear';
        })"""
    )

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/custom/1")
    configure_active_step_transitions(page, 50)
    page.keyboard.press("ArrowRight")
    wait_for_navigation_queue(page)

    assert page.url.endswith("#/vividly/custom/1")
    assert root.locator("[data-custom-state]").evaluate("(element) => element.value") == "settled"
    assert root.get_attribute("data-settle-calls") == "2"
    page.close()


@pytest.mark.parametrize("arrival", ["direct", "api", "history"])
@pytest.mark.parametrize("key", ["ArrowRight", "Space", "ArrowLeft"])
def test_destination_custom_build_settles_only_on_forward_input(
    browser: Browser,
    runtime_url: str,
    arrival: str,
    key: str,
) -> None:
    """Validate destination-arrival settling in presentation-orchestration.md."""
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "custom/1")
    if arrival == "api":
        page.locator("vividly-presentation").evaluate("p => p._navigateTo('custom', 0)")
        page.locator("vividly-presentation").evaluate("p => p._navigateTo('custom', 1)")
    elif arrival == "history":
        page.locator("vividly-presentation").evaluate("p => p._navigateTo('custom', 0)")
        page.go_back()
        page.wait_for_url("**/#/vividly/custom/1")
        wait_for_navigation_queue(page)
    root = page.locator(".v-layer:not([hidden]) [data-mode='custom']")
    assert root.locator("[data-custom-state]").evaluate("e => e.value") == "running"
    before = root.evaluate(
        """element => ({
            setStepCalls: element.dataset.setStepCalls,
            stepEvents: element.dataset.stepEvents,
            slideEnterEvents: element.dataset.slideEnterEvents,
            historyLength: history.length,
        })"""
    )
    page.keyboard.press(key)
    wait_for_navigation_queue(page)
    if key == "ArrowLeft":
        assert page.url.endswith("#/vividly/custom")
        assert root.locator("[data-custom-state]").evaluate("e => e.value") == "idle"
        assert root.get_attribute("data-settle-calls") == "0"
    else:
        assert page.url.endswith("#/vividly/custom/1")
        assert root.locator("[data-custom-state]").evaluate("e => e.value") == "settled"
        assert root.get_attribute("data-settle-calls") == "1"
        assert root.evaluate(
            """element => ({
                setStepCalls: element.dataset.setStepCalls,
                stepEvents: element.dataset.stepEvents,
                slideEnterEvents: element.dataset.slideEnterEvents,
                historyLength: history.length,
            })"""
        ) == before
        page.keyboard.press(key)
        page.wait_for_url("**/#/vividly/custom/2")
    page.close()


def test_ambient_and_keyframe_animations_do_not_block_navigation(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "ambient")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/ambient/1")
    animations = page.locator(".v-layer:not([hidden]) [data-mode='ambient']").evaluate(
        """(element) => element.getAnimations({subtree: true}).map(
            (animation) => ({
                constructor: animation.constructor.name,
                iterations: animation.effect.getTiming().iterations,
                playState: animation.playState,
            })
        )"""
    )
    assert any(animation["iterations"] == float("inf") for animation in animations)
    assert any(animation["constructor"] == "CSSAnimation" for animation in animations)

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/dynamic")
    page.close()


def test_dynamic_slide_motion_uses_directional_settling(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "dynamic")
    root = page.locator(".v-layer:not([hidden]) [data-mode='dynamic']")

    page.keyboard.press("ArrowRight")
    assert root.get_attribute("data-dynamic-step") == "1"
    page.wait_for_function(
        """() => document.querySelector(
            ".v-layer:not([hidden]) [data-step-motion]"
        ).getAnimations().some(
            (animation) => animation instanceof CSSTransition
                && animation.playState === "running"
        )"""
    )
    page.keyboard.press("ArrowRight")
    wait_for_navigation_queue(page)
    assert root.get_attribute("data-dynamic-step") == "2"
    page.keyboard.press("ArrowLeft")
    wait_for_navigation_queue(page)
    assert root.get_attribute("data-dynamic-step") == "1"
    page.close()


def test_navigator_arrows_and_space_use_completion_grace(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    open_animation_settling_slide(page, runtime_url, "navigator")
    root = page.locator(".v-layer:not([hidden]) [data-mode='navigator']")
    second_choice = root.locator("[data-vividly-navigator-choice='1']")

    page.keyboard.press("ArrowRight")
    page.wait_for_url("**/#/vividly/navigator/1")
    expect(second_choice).to_be_focused()
    page.keyboard.press("ArrowRight")
    wait_for_navigation_queue(page)
    assert page.url.endswith("#/vividly/outro")

    page.goto(f"{runtime_url}/#/vividly/navigator")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.keyboard.press("ArrowDown")
    page.wait_for_url("**/#/vividly/navigator/1")
    page.keyboard.press("Space")
    wait_for_navigation_queue(page)
    assert page.url.endswith("#/vividly/beta/only")
    page.close()


def test_transitions_belong_to_navigation_boundaries(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card")
    start_presentation(page)
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    transitions = page.locator("vividly-presentation").evaluate(
        """async (presentation) => {
            const navigate = async (address) => {
                await presentation._navigateTo(address);
                const layer = presentation._current.layer;
                return {
                    name: layer.dataset.transition,
                    direction: layer.dataset.direction,
                };
            };
            return [
                await navigate('images/photo-tour'),
                await navigate('opening/title-card'),
                await navigate('images/contact-sheet'),
                await navigate('opening/title-card'),
            ];
        }"""
    )

    assert transitions == [
        {"name": "fly", "direction": "forward"},
        {"name": "fly", "direction": "backward"},
        {"name": "slide", "direction": "forward"},
        {"name": "slide", "direction": "backward"},
    ]
    page.close()


def test_slide_transition_translates_without_crossfade(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    animations = page.evaluate(
        """() => {
            const create = (className, direction) => {
                const layer = document.createElement('div');
                layer.className = className;
                layer.dataset.transition = 'slide';
                layer.dataset.direction = direction;
                document.body.appendChild(layer);
                return layer;
            };
            const inspect = (layer) => {
                const style = getComputedStyle(layer);
                const keyframes = layer.getAnimations()[0].effect.getKeyframes();
                return {
                    name: style.animationName,
                    keyframes: keyframes.map((frame) => ({
                        transform: frame.transform,
                        hasOpacity: Object.hasOwn(frame, 'opacity'),
                    })),
                };
            };
            const layers = {
                forwardEnter: create('v-enter', 'forward'),
                forwardLeave: create('v-leave', 'forward'),
                backwardEnter: create('v-enter', 'backward'),
                backwardLeave: create('v-leave', 'backward'),
            };
            const result = Object.fromEntries(
                Object.entries(layers).map(([name, layer]) => [name, inspect(layer)])
            );
            Object.values(layers).forEach((layer) => layer.remove());
            return result;
        }"""
    )

    assert animations == {
        "forwardEnter": {
            "name": "v-slide-in",
            "keyframes": [
                {"transform": "translateX(100%)", "hasOpacity": False},
                {"transform": "none", "hasOpacity": False},
            ],
        },
        "forwardLeave": {
            "name": "v-slide-out",
            "keyframes": [
                {"transform": "none", "hasOpacity": False},
                {"transform": "translateX(-100%)", "hasOpacity": False},
            ],
        },
        "backwardEnter": {
            "name": "v-slide-in",
            "keyframes": [
                {"transform": "translateX(-100%)", "hasOpacity": False},
                {"transform": "none", "hasOpacity": False},
            ],
        },
        "backwardLeave": {
            "name": "v-slide-out",
            "keyframes": [
                {"transform": "none", "hasOpacity": False},
                {"transform": "translateX(100%)", "hasOpacity": False},
            ],
        },
    }
    page.close()


def test_capture_mode_settles_images_and_visual_effects(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/?vividly-capture=1#/vividly/images/photo-tour/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    state = page.locator("vividly-presentation").evaluate(
        """(presentation) => {
            const layer = presentation._current.layer;
            const style = getComputedStyle(layer);
            return {
                capture: presentation.hasAttribute('data-capture'),
                step: presentation._step,
                imagesDecoded: [...layer.querySelectorAll('img')]
                    .every((image) => image.complete && image.naturalWidth > 0),
                animations: document.getAnimations().length,
                animationName: style.animationName,
                transitionDuration: style.transitionDuration,
            };
        }"""
    )

    assert state == {
        "capture": True,
        "step": 2,
        "imagesDecoded": True,
        "animations": 0,
        "animationName": "none",
        "transitionDuration": "0s",
    }
    page.close()


def test_toc_modes_use_thumbnail_index_without_loading_slides(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.route(
        "**/thumbnails/index.json",
        lambda route: route.fulfill(
            json={
                "version": 3,
                "presentations": {
                    "vividly": {
                        "opening/title-card": {
                            "canonicalStep": 2,
                            "steps": [
                                {
                                    "step": step,
                                    "path": (
                                        "vividly/opening/title-card/"
                                        f"step-{step:04d}.png"
                                    ),
                                    "revision": THUMBNAIL_REVISION,
                                }
                                for step in range(3)
                            ],
                        },
                        "images/full-bleed-image": {
                            "canonicalStep": 0,
                            "steps": [
                                {
                                    "step": 0,
                                    "path": (
                                        "vividly/images/full-bleed-image/step-0000.png"
                                    ),
                                    "revision": THUMBNAIL_REVISION,
                                }
                            ],
                        },
                    }
                },
            }
        ),
    )
    page.route(
        "**/thumbnails/vividly/opening/title-card/step-*.png*",
        lambda route: route.fulfill(
            content_type="image/svg+xml",
            body='<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"/>',
        ),
    )
    page.route(
        "**/thumbnails/vividly/images/full-bleed-image/step-0000.png*",
        lambda route: route.fulfill(status=404, body="missing"),
    )
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    presentation = page.locator("vividly-presentation")
    toc = page.locator(".v-toc")
    outline = page.get_by_role("button", name="Outline", exact=True)
    grid = page.get_by_role("button", name="Grid", exact=True)
    show_thumbnails = page.get_by_role("button", name="Show thumbnails", exact=True)
    assert outline.count() == 1
    assert grid.count() == 1
    assert show_thumbnails.count() == 1
    assert outline.get_attribute("aria-pressed") == "true"
    assert show_thumbnails.get_attribute("aria-pressed") == "false"
    assert presentation.evaluate("(element) => element._leaves.every((leaf) => !leaf.rec)")

    width_without_thumbnails = toc.evaluate(
        "(element) => element.getBoundingClientRect().width"
    )
    show_thumbnails.click()
    assert toc.evaluate("(element) => element.getBoundingClientRect().width") == (
        width_without_thumbnails
    )
    title_thumbnail = page.locator(
        '.v-toc-outline .v-toc-item[data-address="opening/title-card"] '
        "> .v-thumbnail img"
    )
    title_thumbnail_src = title_thumbnail.get_attribute("src")
    assert title_thumbnail_src is not None
    assert title_thumbnail_src.endswith(
        f"/thumbnails/vividly/opening/title-card/step-0002.png?v={THUMBNAIL_REVISION}"
    )
    full_bleed_slide = page.locator(
        '.v-toc-outline .v-toc-item[data-address="images/full-bleed-image"]'
    )
    canonical_full_bleed_thumbnail = full_bleed_slide.locator("> .v-thumbnail")
    full_bleed_step = full_bleed_slide.locator(".v-outline-step[data-step='0']")
    assert canonical_full_bleed_thumbnail.is_visible()
    assert full_bleed_step.count() == 1
    assert full_bleed_step.is_hidden()

    outline_expand_steps = page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    )
    outline_expand_steps.click()
    assert canonical_full_bleed_thumbnail.is_hidden()
    assert full_bleed_step.is_visible()
    assert full_bleed_step.evaluate(
        "(step) => step.getBoundingClientRect().width <= 256"
    )
    outline_expand_steps.click()
    assert canonical_full_bleed_thumbnail.is_visible()
    assert full_bleed_step.is_hidden()
    assert presentation.evaluate("(element) => element._leaves.every((leaf) => !leaf.rec)")

    grid.click()
    assert page.url.endswith("#/vividly/")
    assert grid.evaluate("(button) => button === document.activeElement")
    grid_items = page.locator(".v-toc .v-overview-item:visible")
    assert grid_items.count() == presentation.evaluate(
        "(element) => element._leaves.length"
    )
    assert page.locator(".v-toc .v-overview-item:visible[data-step]").count() == 0
    assert page.locator(
        '.v-toc .v-overview-item:visible[data-address="images/full-bleed-image"] '
        ".v-thumbnail-placeholder"
    ).text_content() == "Full-Bleed Image"
    assert page.locator(".v-toc .v-overview-item:visible img").evaluate_all(
        "images => images.every((image) => image.loading === 'lazy')"
    )
    assert presentation.evaluate("(element) => element._leaves.every((leaf) => !leaf.rec)")

    expand_steps = page.get_by_role(
        "button", name="Expand/collapse steps", exact=True
    )
    assert expand_steps.get_attribute("aria-expanded") == "false"
    expand_steps.click()
    step_items = page.locator(".v-toc .v-overview-item:visible[data-step]")
    assert grid_items.count() == 20
    assert step_items.count() == 4
    assert step_items.evaluate_all(
        """items => items.slice(0, 4).map((item) => ({
            address: item.dataset.address,
            step: item.dataset.step,
        }))"""
    ) == [
        {"address": "opening/title-card", "step": str(step)} for step in range(3)
    ] + [{"address": "images/full-bleed-image", "step": "0"}]
    assert step_items.evaluate_all(
        """items => items.every((item) =>
            item.dataset.sequenceTone !== undefined
            && (item.hasAttribute('data-sequence-start')
                || item.hasAttribute('data-sequence-end')
                || items.some((candidate) =>
                    candidate !== item
                    && candidate.dataset.address === item.dataset.address
                ))
        )"""
    )
    grid_body = page.locator(".v-toc-grid")
    assert grid_body.get_by_text("Step 1 of 3", exact=True).is_visible()
    assert grid_body.get_by_text("Step 2 of 3", exact=True).is_visible()
    assert grid_body.get_by_text("Step 3 of 3", exact=True).is_visible()
    assert grid_body.get_by_text("Step 1 of 1", exact=True).is_visible()
    layout = grid_body.evaluate(
        """grid => {
            const cards = [...grid.querySelectorAll('.v-grid-item')];
            const rows = Map.groupBy(
                cards,
                (card) => Math.round(card.getBoundingClientRect().top)
            );
            const accentProbe = document.createElement('span');
            accentProbe.style.color = 'var(--accent-warm)';
            grid.append(accentProbe);
            const accentWarm = getComputedStyle(accentProbe).color;
            accentProbe.remove();
            return {
                display: getComputedStyle(grid).display,
                columns: getComputedStyle(grid).gridTemplateColumns,
                cardWidths: cards.map((card) => card.getBoundingClientRect().width),
                mixedSlideRow: [...rows.values()].some((row) =>
                    new Set(row.map((card) => card.dataset.address)).size > 1
                ),
                singleStepWidth: grid
                    .querySelector(
                        '.v-grid-item[data-address="images/full-bleed-image"]'
                    )
                    .getBoundingClientRect().width,
                gridWidth: grid.getBoundingClientRect().width,
                titleTone: cards.find(
                    (card) => card.dataset.address === 'opening/title-card'
                ).dataset.sequenceTone,
                imageTone: cards.find(
                    (card) => card.dataset.address === 'images/full-bleed-image'
                ).dataset.sequenceTone,
                sequenceStartBorderColor: getComputedStyle(
                    cards.find((card) => card.hasAttribute('data-sequence-start'))
                ).borderLeftColor,
                sequenceStartBorderWidth: getComputedStyle(
                    cards.find((card) => card.hasAttribute('data-sequence-start'))
                ).borderLeftWidth,
                sequenceEndBorderColor: getComputedStyle(
                    cards.find((card) => card.hasAttribute('data-sequence-end'))
                ).borderRightColor,
                sequenceEndBorderWidth: getComputedStyle(
                    cards.find((card) => card.hasAttribute('data-sequence-end'))
                ).borderRightWidth,
                regularBorderWidth: getComputedStyle(
                    cards.find((card) => !card.hasAttribute('data-sequence-start'))
                ).borderLeftWidth,
                accentWarm,
            };
        }"""
    )
    assert layout["display"] == "grid"
    assert len(layout["columns"].split()) > 1
    assert max(layout["cardWidths"]) - min(layout["cardWidths"]) < 1
    assert layout["singleStepWidth"] < layout["gridWidth"] / 2
    assert layout["mixedSlideRow"]
    assert layout["titleTone"] != layout["imageTone"]
    assert layout["sequenceStartBorderColor"] == layout["accentWarm"]
    assert layout["sequenceEndBorderColor"] == layout["accentWarm"]
    assert float(layout["sequenceStartBorderWidth"].removesuffix("px")) > float(
        layout["regularBorderWidth"].removesuffix("px")
    )
    assert layout["sequenceEndBorderWidth"] == layout["sequenceStartBorderWidth"]
    assert presentation.evaluate("(element) => element._leaves.every((leaf) => !leaf.rec)")

    page.locator(
        '.v-toc .v-overview-item:visible[data-address="opening/title-card"][data-step="1"]'
    ).click()
    page.wait_for_url("**/#/vividly/opening/title-card/1")
    page.keyboard.press("Escape")
    page.wait_for_url("**/#/vividly/")
    assert page.get_by_role("button", name="Grid", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"
    assert page.get_by_role("button", name="Expand/collapse steps", exact=True).get_attribute(
        "aria-expanded"
    ) == "true"
    current_slide = page.locator(
        '.v-toc-grid .v-grid-item[data-current-slide]'
        '[data-address="opening/title-card"]'
    )
    current_step = page.locator(
        '.v-toc-grid .v-grid-item[data-current-step][data-step="1"]'
    )
    assert current_slide.evaluate(
        "(element) => getComputedStyle(element, '::before').content"
    ) == '"Current slide"'
    assert current_step.get_attribute("aria-current") == "step"
    assert current_step.evaluate(
        "(element) => getComputedStyle(element, '::after').content"
    ) == '"Current step"'
    assert current_step.evaluate("(element) => element === document.activeElement")

    current_step.focus()
    presentation.evaluate("(element) => element._setStepsExpanded(false)")
    replacement = page.locator(
        '.v-toc-grid .v-grid-item[data-address="opening/title-card"]'
        ":not([data-step])"
    )
    assert replacement.evaluate("(element) => element === document.activeElement")
    assert replacement.get_attribute("aria-current") == "true"
    assert page.get_by_role("button", name="Expand/collapse steps", exact=True).get_attribute(
        "aria-expanded"
    ) == "false"

    page.get_by_role("button", name="Outline", exact=True).click()
    assert page.get_by_role(
        "button", name="Show thumbnails", exact=True
    ).get_attribute("aria-pressed") == "true"
    page.reload()
    page.locator(".v-toc").wait_for(state="visible")
    assert page.get_by_role("button", name="Outline", exact=True).get_attribute(
        "aria-pressed"
    ) == "true"
    assert page.get_by_role(
        "button", name="Show thumbnails", exact=True
    ).get_attribute("aria-pressed") == "true"
    reloaded_thumbnail_src = page.locator(
        '.v-toc-outline .v-toc-item[data-address="opening/title-card"] '
        "> .v-thumbnail img"
    ).get_attribute("src")
    assert reloaded_thumbnail_src is not None
    assert reloaded_thumbnail_src.endswith(
        f"/thumbnails/vividly/opening/title-card/step-0002.png?v={THUMBNAIL_REVISION}"
    )
    page.close()


def test_thumbnail_control_resolves_slides_sections_and_fallbacks(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.route(
        "**/thumbnails/index.json",
        lambda route: route.fulfill(
            json={
                "version": 3,
                "presentations": {
                    "vividly": {
                        "opening/title-card": {
                            "canonicalStep": 2,
                            "steps": [
                                {
                                    "step": step,
                                    "path": (
                                        "vividly/opening/title-card/"
                                        f"step-{step:04d}.png"
                                    ),
                                    "revision": str(step + 1) * 64,
                                }
                                for step in range(3)
                            ],
                        },
                        "mechanics/diagram-build": {
                            "canonicalStep": 1,
                            "steps": [
                                {
                                    "step": step,
                                    "path": (
                                        "vividly/mechanics/diagram-build/"
                                        f"step-{step:04d}.png"
                                    ),
                                    "revision": THUMBNAIL_REVISION,
                                }
                                for step in range(2)
                            ],
                        },
                    }
                },
            }
        ),
    )
    page.route(
        "**/thumbnails/vividly/opening/title-card/step-*.png*",
        lambda route: route.fulfill(
            content_type="image/svg+xml",
            body='<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"/>',
        ),
    )
    page.route(
        "**/thumbnails/vividly/mechanics/diagram-build/step-0001.png*",
        lambda route: route.fulfill(status=404, body="missing"),
    )
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    page.locator("vividly-presentation").evaluate(
        """presentation => {
            const fixtures = document.createElement('div');
            fixtures.id = 'thumbnail-fixtures';
            for (const attributes of [
                { id: 'section-thumbnail', address: 'opening' },
                {
                    id: 'labeled-thumbnail',
                    address: 'opening/title-card',
                    label: 'Opening preview',
                    loading: 'eager',
                },
                {
                    id: 'step-thumbnail',
                    address: 'opening/title-card',
                    step: 1,
                    fallback: 'Step unavailable',
                },
                {
                    id: 'missing-thumbnail',
                    address: 'unknown',
                    label: 'Missing preview',
                },
                {
                    id: 'broken-thumbnail',
                    address: 'mechanics/diagram-build',
                    label: 'Broken preview',
                },
            ]) {
                const thumbnail = document.createElement('vividly-thumbnail');
                Object.assign(thumbnail, attributes);
                fixtures.append(thumbnail);
            }
            presentation.append(fixtures);
        }"""
    )
    page.wait_for_function(
        """() => [...document.querySelectorAll('#thumbnail-fixtures vividly-thumbnail')]
            .every(element => element.dataset.thumbnailStatus !== 'loading')"""
    )

    descriptor = page.locator("vividly-presentation").evaluate(
        """presentation => {
            const canonical = presentation.thumbnailFor('opening');
            const exact = [0, 1, 2].map((step) =>
                presentation.thumbnailFor('opening/title-card', step)
            );
            const sequence = presentation.thumbnailsFor('opening');
            const unknownSequence = presentation.thumbnailsFor('unknown');
            const entry = presentation._thumbnailIndex['opening/title-card'];
            return {
                canonical,
                exact,
                sequence,
                canonicalFrozen: Object.isFrozen(canonical),
                exactFrozen: exact.every(Object.isFrozen),
                sequenceFrozen: Object.isFrozen(sequence),
                sequenceItemsFrozen: sequence.every(Object.isFrozen),
                entryFrozen: Object.isFrozen(entry),
                entryStepsFrozen: Object.isFrozen(entry.steps),
                sameCanonicalUrl:
                    presentation.thumbnailFor('opening/title-card').src === canonical.src,
                unknown: presentation.thumbnailFor('unknown'),
                invalidNegative: presentation.thumbnailFor('opening/title-card', -1),
                invalidFractional: presentation.thumbnailFor('opening/title-card', 1.5),
                unavailable: presentation.thumbnailFor('opening/title-card', 3),
                unknownSequence,
                unknownSequenceFrozen: Object.isFrozen(unknownSequence),
                modulesUnloaded: presentation._leaves.every((leaf) => !leaf.rec),
            };
        }"""
    )
    assert descriptor["canonical"]["address"] == "opening/title-card"
    assert descriptor["canonical"]["capturedStep"] == 2
    assert descriptor["canonical"]["src"].endswith(
        f"/thumbnails/vividly/opening/title-card/step-0002.png?v={'3' * 64}"
    )
    assert [item["capturedStep"] for item in descriptor["exact"]] == [0, 1, 2]
    assert [item["capturedStep"] for item in descriptor["sequence"]] == [0, 1, 2]
    assert descriptor["exact"][0]["src"].endswith(
        f"/thumbnails/vividly/opening/title-card/step-0000.png?v={'1' * 64}"
    )
    assert descriptor["exact"][1]["src"].endswith(
        f"/thumbnails/vividly/opening/title-card/step-0001.png?v={'2' * 64}"
    )
    assert descriptor["canonicalFrozen"]
    assert descriptor["exactFrozen"]
    assert descriptor["sequenceFrozen"]
    assert descriptor["sequenceItemsFrozen"]
    assert descriptor["entryFrozen"]
    assert descriptor["entryStepsFrozen"]
    assert descriptor["sameCanonicalUrl"]
    assert descriptor["modulesUnloaded"]
    assert descriptor["unknown"] is None
    assert descriptor["invalidNegative"] is None
    assert descriptor["invalidFractional"] is None
    assert descriptor["unavailable"] is None
    assert descriptor["unknownSequence"] == []
    assert descriptor["unknownSequenceFrozen"]

    section_thumbnail = page.locator("#section-thumbnail")
    assert section_thumbnail.get_attribute("aria-hidden") == "true"
    assert section_thumbnail.locator("img").get_attribute("alt") == ""
    assert section_thumbnail.locator("img").get_attribute("loading") == "lazy"
    assert section_thumbnail.get_attribute("data-thumbnail-status") == "ready"

    labeled_thumbnail = page.locator("#labeled-thumbnail")
    assert labeled_thumbnail.get_attribute("role") == "img"
    assert labeled_thumbnail.get_attribute("aria-label") == "Opening preview"
    assert labeled_thumbnail.locator("img").get_attribute("loading") == "eager"

    step_thumbnail = page.locator("#step-thumbnail")
    assert step_thumbnail.evaluate("(element) => element.step") == 1
    step_thumbnail_src = step_thumbnail.locator("img").get_attribute("src")
    assert step_thumbnail_src is not None
    assert step_thumbnail_src.endswith(
        f"/thumbnails/vividly/opening/title-card/step-0001.png?v={'2' * 64}"
    )
    stale_result = step_thumbnail.evaluate(
        """element => {
            const staleImage = element.querySelector('img');
            element.step = 0;
            const currentImage = element.querySelector('img');
            staleImage.dispatchEvent(new Event('error'));
            return {
                currentImageRetained: element.firstElementChild === currentImage,
                status: element.dataset.thumbnailStatus,
                step: element.step,
            };
        }"""
    )
    assert stale_result == {
        "currentImageRetained": True,
        "status": "loading",
        "step": 0,
    }
    page.wait_for_function(
        "() => document.querySelector('#step-thumbnail').dataset.thumbnailStatus === 'ready'"
    )
    step_thumbnail_src = step_thumbnail.locator("img").get_attribute("src")
    assert step_thumbnail_src is not None
    assert step_thumbnail_src.endswith(
        f"/thumbnails/vividly/opening/title-card/step-0000.png?v={'1' * 64}"
    )

    step_thumbnail.evaluate("(element) => element.setAttribute('step', '2')")
    page.wait_for_function(
        "() => document.querySelector('#step-thumbnail').dataset.thumbnailStatus === 'ready'"
    )
    step_thumbnail_src = step_thumbnail.locator("img").get_attribute("src")
    assert step_thumbnail_src is not None
    assert step_thumbnail_src.endswith(
        f"/thumbnails/vividly/opening/title-card/step-0002.png?v={'3' * 64}"
    )

    step_thumbnail.evaluate("(element) => { element.step = null; }")
    assert step_thumbnail.get_attribute("step") is None
    assert step_thumbnail.evaluate("(element) => element.step") is None
    page.wait_for_function(
        "() => document.querySelector('#step-thumbnail').dataset.thumbnailStatus === 'ready'"
    )
    step_thumbnail_src = step_thumbnail.locator("img").get_attribute("src")
    assert step_thumbnail_src is not None
    assert step_thumbnail_src.endswith(
        f"/thumbnails/vividly/opening/title-card/step-0002.png?v={'3' * 64}"
    )

    invalid_steps = step_thumbnail.evaluate(
        """element => ['', ' ', 'unknown', '-1', '1.5'].map(step => {
            element.setAttribute('step', step);
            return {
                step,
                property: element.step,
                status: element.dataset.thumbnailStatus,
                imageCount: element.querySelectorAll('img').length,
                fallback: element.querySelector('.v-thumbnail-placeholder').textContent,
            };
        })"""
    )
    assert invalid_steps == [
        {
            "step": step,
            "property": None,
            "status": "missing",
            "imageCount": 0,
            "fallback": "Step unavailable",
        }
        for step in ("", " ", "unknown", "-1", "1.5")
    ]

    step_thumbnail.evaluate("(element) => { element.step = 3; }")
    assert step_thumbnail.get_attribute("step") == "3"
    assert step_thumbnail.evaluate("(element) => element.step") == 3
    assert step_thumbnail.locator("img").count() == 0
    assert step_thumbnail.get_attribute("data-thumbnail-status") == "missing"
    assert (
        step_thumbnail.locator(".v-thumbnail-placeholder").text_content()
        == "Step unavailable"
    )

    missing_thumbnail = page.locator("#missing-thumbnail")
    assert missing_thumbnail.locator("img").count() == 0
    assert missing_thumbnail.get_attribute("data-thumbnail-status") == "missing"
    assert (
        missing_thumbnail.locator(".v-thumbnail-placeholder").text_content()
        == "Missing preview"
    )

    broken_thumbnail = page.locator("#broken-thumbnail")
    assert broken_thumbnail.locator("img").count() == 0
    assert broken_thumbnail.get_attribute("data-thumbnail-status") == "missing"
    assert broken_thumbnail.locator(".v-thumbnail-placeholder").text_content() == (
        "Broken preview"
    )
    assert section_thumbnail.evaluate(
        """element => {
            const box = element.getBoundingClientRect();
            return Math.abs(box.width / box.height - 16 / 9) < 0.01;
        }"""
    )

    labeled_thumbnail.evaluate(
        """element => {
            element.address = 'unknown';
            element.label = '';
            element.fallback = 'Changed preview';
            element.loading = 'unsupported';
        }"""
    )
    assert labeled_thumbnail.get_attribute("aria-hidden") == "true"
    assert labeled_thumbnail.locator("img").count() == 0
    assert labeled_thumbnail.locator(".v-thumbnail-placeholder").text_content() == (
        "Changed preview"
    )
    assert labeled_thumbnail.evaluate("(element) => element.loading") == "lazy"
    page.close()


def test_advance_control_renders_message_and_requests_next_state(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    result = page.locator("vividly-presentation").evaluate(
        """async presentation => {
            const advances = [];
            presentation.advance = () => advances.push(1);
            const fixture = document.createElement('div');
            fixture.innerHTML =
                '<vividly-advance message="start the demo"></vividly-advance>';
            presentation.append(fixture);
            const control = fixture.firstElementChild;
            const button = control.querySelector('button');
            button.click();
            button.focus();
            button.dispatchEvent(new KeyboardEvent('keydown', {
                key: ' ',
                bubbles: true,
            }));
            button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            return {
                message: control.message,
                text: button.textContent,
                label: button.getAttribute('aria-label'),
                advances,
                display: getComputedStyle(control).display,
                background: getComputedStyle(button).backgroundColor,
                borderStyle: getComputedStyle(button).borderStyle,
            };
        }"""
    )

    assert result == {
        "message": "start the demo",
        "text": "Press → or Space to start the demo",
        "label": "Press Right Arrow or Space to start the demo",
        "advances": [1, 1],
        "display": "block",
        "background": "rgb(30, 34, 40)",
        "borderStyle": "solid",
    }
    page.close()


@pytest.mark.parametrize("tag", ["vividly-markdown", "vividly-code", "vividly-annotated-markdown"])
def test_code_copy_defaults_text_keyboard_and_lifecycle(
    browser: Browser,
    runtime_url: str,
    tag: str,
) -> None:
    """Validate copying code in presentation-orchestration.md section 4.7."""
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.locator("vividly-presentation").evaluate(
        """(presentation, tag) => {
            globalThis.copyWrites = [];
            Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
                writeText: async text => { globalThis.copyWrites.push(text); },
            }});
            const control = document.createElement(tag);
            control.id = 'copy-fixture';
            control.style.cssText = 'width:500px;height:300px';
            const source = 'const x = "<&>";\\n\\tconsole.log(x);\\n';
            control.value = tag === 'vividly-code'
                ? source : '```javascript\\n' + source + '```\\n\\nInline `value`.';
            presentation.append(control);
        }""",
        tag,
    )
    control = page.locator("#copy-fixture")
    button = control.locator(".v-code-copy")
    assert control.evaluate("e => e.copyable")
    assert button.count() == 1
    expected = (
        'const x = "<&>";\n\tconsole.log(x);\n'
        if tag == "vividly-code"
        else control.locator("pre > code").text_content()
    )
    assert expected is not None
    url = page.url
    button.click()
    expect(button).to_have_attribute("data-copied", "true")
    button.press("Enter")
    expect(button).to_be_enabled()
    button.press("Space")
    expect(button).to_be_enabled()
    assert page.url == url
    assert page.evaluate("globalThis.copyWrites") == [expected] * 3
    assert control.locator("[role=status]").text_content() == "Copied to clipboard."
    control.evaluate("e => { e.copyable = false; }")
    assert control.get_attribute("no-copy") == ""
    assert button.count() == 0
    control.evaluate("e => { e.copyable = true; }")
    assert button.count() == 1
    control.evaluate(
        """e => {
            const parent = e.parentElement;
            e.remove();
            parent.append(e);
        }"""
    )
    assert button.count() == 1
    button.click()
    expect(button).to_have_attribute("data-copied", "true")
    assert len(page.evaluate("globalThis.copyWrites")) == 4
    page.close()


@pytest.mark.parametrize("tag", ["vividly-markdown", "vividly-code", "vividly-annotated-markdown"])
def test_code_copy_failure_and_obsolete_completion(
    browser: Browser,
    runtime_url: str,
    tag: str,
) -> None:
    """Validate explicit copy failures and stale-result handling in the copy specification."""
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.locator("vividly-presentation").evaluate(
        """(presentation, tag) => {
            globalThis.copyErrors = [];
            Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
                writeText: async () => { throw new Error('Clipboard denied'); },
            }});
            const control = document.createElement(tag);
            control.id = 'copy-fixture';
            control.style.cssText = 'width:500px;height:300px';
            control.value = tag === 'vividly-code' ? 'source' : '```\\nsource\\n```';
            control.addEventListener('vividly-error', event => {
                globalThis.copyErrors.push([event.detail.operation, event.detail.error.message]);
            });
            presentation.append(control);
        }""",
        tag,
    )
    control = page.locator("#copy-fixture")
    button = control.locator(".v-code-copy")
    button.click()
    expect(control.locator("[role=status]")).to_have_class("v-code-copy-status is-error")
    expect(control.locator("[role=status]")).to_contain_text("copy it manually")
    expect(button).not_to_have_attribute("data-copied")
    expect(button).to_be_enabled()
    assert page.evaluate("globalThis.copyErrors") == [["copy", "Clipboard denied"]]
    page.evaluate(
        """() => {
            navigator.clipboard.writeText = () => new Promise(resolve => {
                globalThis.finishCopy = resolve;
            });
        }"""
    )
    button.click()
    expect(button).to_be_disabled()
    control.evaluate(
        """e => {
            e.value = e.localName === 'vividly-code' ? 'new source' : '```\\nnew source\\n```';
            globalThis.finishCopy();
        }"""
    )
    expect(button).to_be_enabled()
    expect(button).not_to_have_attribute("data-copied")
    assert control.locator("[role=status]").text_content() == ""
    page.close()


def test_annotated_markdown_cloned_code_buttons_and_opt_out(
    browser: Browser,
    runtime_url: str,
) -> None:
    """Validate copy controls in cloned annotation/header content from the copy specification."""
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.locator("vividly-presentation").evaluate(
        """presentation => {
            globalThis.copyWrites = [];
            Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
                writeText: async text => { globalThis.copyWrites.push(text); },
            }});
            const control = document.createElement('vividly-annotated-markdown');
            control.id = 'copy-fixture';
            control.style.cssText = 'width:900px;height:500px';
            control.value = [
                '<vividly-document-header title="Notes">',
                '<pre><code>header &lt;&amp;</code></pre>',
                '</vividly-document-header>', '',
                '<vividly-annotation title="Example">',
                '<pre><code>annotation &lt;&amp;</code></pre>',
                '</vividly-annotation>',
            ].join('\\n');
            presentation.append(control);
            control.activeAnnotation = 0;
        }"""
    )
    control = page.locator("#copy-fixture")
    for region in (".v-annotated-description", ".v-annotation-content"):
        button = control.locator(region).get_by_role("button")
        assert button.count() == 1
        button.click()
        expect(button).to_have_attribute("data-copied", "true")
    assert page.evaluate("globalThis.copyWrites") == ["header <&", "annotation <&"]
    control.evaluate("e => e.setAttribute('no-copy', 'false')")
    assert control.locator(".v-code-copy").count() == 0
    control.evaluate("e => e.removeAttribute('no-copy')")
    for region in (".v-annotated-description", ".v-annotation-content"):
        assert control.locator(region).get_by_role("button").count() == 1
    page.close()


def test_step_progress_values_accessibility_errors_and_reconnection(
    browser: Browser,
    runtime_url: str,
) -> None:
    """Validate the step readiness progress contract in presentation-orchestration.md."""
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function("() => customElements.get('vividly-step-progress')")
    result = page.evaluate(
        """() => {
            const control = document.createElement('vividly-step-progress');
            document.body.append(control);
            const track = control.querySelector('[role=progressbar]');
            const button = control.querySelector('button');
            const snapshot = () => ({
                value: control.value,
                label: track.getAttribute('aria-label'),
                now: track.getAttribute('aria-valuenow'),
                text: track.getAttribute('aria-valuetext'),
                disabled: button.disabled,
                visibility: getComputedStyle(button).visibility,
            });
            const initial = snapshot();
            control.advance = true;
            control.label = 'Scene readiness';
            control.value = .375;
            const partial = snapshot();
            const transform = control.querySelector('span').style.transform;
            const transition = getComputedStyle(control.querySelector('span')).transitionDuration;
            const before = control.getBoundingClientRect().toJSON();
            const focusBefore = document.activeElement;
            control.value = 2;
            const complete = snapshot();
            const stableLayout = JSON.stringify(before)
                === JSON.stringify(control.getBoundingClientRect().toJSON());
            const stableFocus = document.activeElement === focusBefore;
            control.remove();
            document.body.append(control);
            const buttons = control.querySelectorAll('button').length;
            control.advance = false;
            const optedOut = snapshot();
            control.advance = true;
            control.value = -1;
            const reset = snapshot();
            const rejected = [NaN, Infinity, '0.5', null].map(value => {
                try { control.value = value; return false; }
                catch (error) { return error instanceof TypeError; }
            });
            const errors = [];
            control.addEventListener('vividly-error', event => {
                errors.push(event.detail.error.message);
            });
            control.setAttribute('value', 'invalid');
            const invalid = {
                hidden: track.hidden,
                disabled: button.disabled,
                message: control.querySelector('.v-control-error').textContent,
            };
            control.value = .999;
            const recovered = snapshot();
            control.value = 1;
            button.click();
            return {initial, partial, transform, transition, complete, stableLayout,
                stableFocus, buttons, optedOut, reset, rejected, errors, invalid, recovered};
        }"""
    )
    assert result["initial"] == {
        "value": 0, "label": "Step readiness", "now": "0", "text": "0%",
        "disabled": True, "visibility": "hidden",
    }
    assert result["partial"] == {
        "value": 0.375, "label": "Scene readiness", "now": "38", "text": "38%",
        "disabled": True, "visibility": "hidden",
    }
    assert result["transform"] == "scaleX(0.375)"
    assert result["transition"] == "0s"
    assert result["complete"] == {
        "value": 1, "label": "Scene readiness", "now": "100", "text": "Ready",
        "disabled": False, "visibility": "visible",
    }
    assert result["stableLayout"] and result["stableFocus"]
    assert result["buttons"] == 1
    assert result["optedOut"]["disabled"]
    assert result["optedOut"]["visibility"] == "hidden"
    assert result["reset"]["value"] == 0
    assert result["reset"]["disabled"]
    assert all(result["rejected"])
    assert result["errors"] == ["Step progress value must be a finite number."]
    assert result["invalid"] == {
        "hidden": True, "disabled": True,
        "message": "Step progress value must be a finite number.",
    }
    assert result["recovered"]["text"] == "100%"
    assert result["recovered"]["disabled"]
    page.close()


def test_step_progress_button_uses_native_keyboard_activation_once(
    browser: Browser,
    runtime_url: str,
) -> None:
    """Validate completion-button navigation from the step readiness specification."""
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    page.locator("vividly-presentation").evaluate(
        """presentation => {
            presentation.progressAdvances = 0;
            presentation.advance = () => presentation.progressAdvances++;
            const control = document.createElement('vividly-step-progress');
            control.id = 'test-progress';
            control.advance = true;
            control.value = 1;
            presentation.append(control);
            control.remove();
            presentation.append(control);
        }"""
    )
    button = page.locator("#test-progress button")
    button.click()
    button.press("Enter")
    button.press("Space")
    assert page.locator("vividly-presentation").evaluate("p => p.progressAdvances") == 3
    page.locator("#test-progress").evaluate("control => { control.value = 0; }")
    expect(button).to_be_hidden()
    expect(button).to_be_disabled()
    assert page.get_by_role("button", name="Advance →").count() == 0
    page.locator("#test-progress").evaluate("control => control.querySelector('button').click()")
    assert page.locator("vividly-presentation").evaluate("p => p.progressAdvances") == 3
    page.close()


def test_thumbnail_index_rejects_unsupported_and_malformed_entries(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    payload: list[dict[str, Any]] = [{"version": 2, "presentations": {}}]
    page.route(
        "**/thumbnails/index.json",
        lambda route: route.fulfill(json=payload[0]),
    )
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    presentation = page.locator("vividly-presentation")
    assert presentation.evaluate(
        "(element) => element.thumbnailFor('opening/title-card')"
    ) is None

    payload[0] = {
        "version": 3,
        "presentations": {
            "vividly": {
                "opening/title-card": {
                    "canonicalStep": 0,
                    "steps": [
                        {
                            "step": 0,
                            "path": "vividly/opening/title-card/step-0000.png",
                            "revision": "invalid",
                        }
                    ],
                },
                "mechanics/diagram-build": {
                    "canonicalStep": 0,
                    "steps": [
                        {
                            "step": 1,
                            "path": "vividly/mechanics/diagram-build/step-0001.png",
                            "revision": THUMBNAIL_REVISION,
                        }
                    ],
                },
            }
        },
    }
    page.reload()
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    assert presentation.evaluate(
        """element => ({
            malformedRevision: element.thumbnailFor('opening/title-card'),
            malformedSequence: element.thumbnailFor('mechanics/diagram-build'),
            sequence: element.thumbnailsFor('opening/title-card'),
        })"""
    ) == {
        "malformedRevision": None,
        "malformedSequence": None,
        "sequence": [],
    }
    page.close()


def test_thumbnail_index_fetch_requests_cache_revalidation(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.add_init_script(
        """const originalFetch = window.fetch.bind(window);
        window.thumbnailFetchCacheModes = [];
        window.fetch = (input, init = {}) => {
            const url =
                typeof input === 'string'
                    ? input
                    : input instanceof Request
                      ? input.url
                      : String(input);
            if (url.includes('/thumbnails/index.json')) {
                window.thumbnailFetchCacheModes.push(init.cache ?? null);
            }
            return originalFetch(input, init);
        };"""
    )
    page.goto(f"{runtime_url}/#/vividly/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    assert page.evaluate("window.thumbnailFetchCacheModes") == ["no-cache"]
    page.close()


def test_secondary_presentation_grid_uses_managed_thumbnail_index(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.route(
        "**/thumbnails/index.json",
        lambda route: route.fulfill(
            json={
                "version": 3,
                "presentations": {
                    "beta": {
                        "shared": {
                            "canonicalStep": 0,
                            "steps": [
                                {
                                    "step": 0,
                                    "path": "beta/shared/step-0000.png",
                                    "revision": THUMBNAIL_REVISION,
                                }
                            ],
                        }
                    }
                },
            }
        ),
    )
    page.route(
        "**/thumbnails/beta/shared/step-0000.png*",
        lambda route: route.fulfill(
            content_type="image/svg+xml",
            body='<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"/>',
        ),
    )

    route_multi_presentation_project(page)
    page.goto(f"{runtime_url}/#/beta/")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )
    grid = page.get_by_role("button", name="Grid", exact=True)
    assert grid.count() == 1
    grid.click()
    assert page.url.endswith("#/beta/")

    presentation = page.locator("vividly-presentation")
    grid_items = page.locator(".v-toc .v-overview-item:visible")
    assert grid_items.count() == presentation.evaluate(
        "(element) => element._leaves.length"
    )
    assert page.locator(".v-toc vividly-thumbnail:visible").count() == presentation.evaluate(
        "(element) => element._leaves.length"
    )
    assert page.locator(".v-toc .v-overview-item:visible img").count() == 1
    shared_image = page.locator(
        '.v-toc .v-overview-item:visible[data-address="shared"] img'
    )
    shared_image_src = shared_image.get_attribute("src")
    assert shared_image_src is not None
    assert shared_image_src.endswith(
        f"/thumbnails/beta/shared/step-0000.png?v={THUMBNAIL_REVISION}"
    )
    page.close()


DEPENDENCY_SLIDE = """
import { Slide } from '../vividly/runtime/slide.js';

export default class DependencySlide extends Slide {
  async preload() {
    const dependency = this.ctx.dependency('graphics');
    this.dependencyUrl = dependency.url();
    this.dependencyModule = await dependency.import();
  }

  mount(root) {
    root.innerHTML = `<p id="dependency-result">${this.dependencyModule.message}</p>`;
    root.querySelector('#dependency-result').dataset.url = this.dependencyUrl;
  }
}
"""


def test_runtime_and_slide_consumers_share_registry_instances(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(f"{runtime_url}/#/vividly/opening/title-card/2")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    result = page.locator("vividly-presentation").evaluate(
        """async (presentation) => {
            const registry = presentation._dependencyRegistry;
            const handle = presentation._current.ctx.dependency('marked');
            const first = registry.load('marked');
            const second = handle.load();
            let importError = null;
            try {
              handle.import();
            } catch (error) {
              importError = error.message;
            }
            const code = document.createElement('code');
            code.className = 'hljs';
            code.textContent = 'const answer = 42;';
            document.body.appendChild(code);
            const style = getComputedStyle(code);
            return {
              samePromise: first === second,
              sameValue: registry.value('marked') === await second,
              parsed: (await second).parse('**shared**'),
              importError,
              stylesheetCount: [...document.querySelectorAll('link[rel="stylesheet"]')]
                .filter((link) => link.href.includes('highlight-github-dark')).length,
              foreground: style.color,
              background: style.backgroundColor,
            };
        }"""
    )

    assert result["samePromise"] is True
    assert result["sameValue"] is True
    assert result["parsed"].strip() == "<p><strong>shared</strong></p>"
    assert result["importError"] == (
        'Dependency "marked" uses the script loader; use load() instead'
    )
    assert result["stylesheetCount"] == 1
    assert result["foreground"] == "rgb(201, 209, 217)"
    assert result["background"] == "rgb(13, 17, 23)"
    page.close()


def test_dependency_table_push_rejects_collisions_atomically(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.goto(runtime_url)
    page.wait_for_function(
        "() => Boolean(document.querySelector('vividly-presentation')?._dependencyRegistry)"
    )

    result = page.locator("vividly-presentation").evaluate(
        """async (presentation) => {
            const { DependencyTable } = await import(
              './vividly/runtime/dependencies.js'
            );
            const candidate = DependencyTable.fromCatalog(
              new Map([
                ['new-package', {
                  key: 'new-package',
                  baseUrl: 'https://cdn.example.invalid/new-package/',
                  entry: 'index.js',
                }],
                ['marked', {
                  key: 'marked',
                  baseUrl: 'https://cdn.example.invalid/marked/',
                  entry: 'index.js',
                }],
              ]),
              'catalog.yaml'
            );
            let message = null;
            try {
              presentation._dependencyRegistry.push(candidate);
            } catch (error) {
              message = error.message;
            }
            return {
              message,
              addedNewPackage: presentation._dependencyRegistry.has('new-package'),
              markedStillLoads: Boolean(await presentation._dependencyRegistry.load('marked')),
            };
        }"""
    )

    assert result == {
        "message": (
            'Dependency "marked" from catalog conflicts with dependency selected by runtime'
        ),
        "addedNewPackage": False,
        "markedStillLoads": True,
    }
    page.close()


DEPENDENCY_CATALOG = json.dumps(
    {
        "version": 1,
        "dependencies": {
            "graphics": {
                "baseUrl": "https://cdn.example.invalid/graphics@1.2.3/",
                "entry": "entry.js",
            }
        },
        "presentations": [
            {
                "id": "vividly",
                "title": "Primary",
                "manifest": "./presentations/vividly.yaml",
            },
            {
                "id": "alternate",
                "title": "Alternate",
                "manifest": "./presentations/alternate.yaml",
            },
        ],
    }
)
DEPENDENCY_MANIFEST = json.dumps(
    {
        "id": "dependency-test",
        "keyboardHints": "never",
        "nodes": [
            {
                "type": "slide",
                "id": "entry",
                "module": "../slides/dependency-test.js",
            }
        ],
    }
)


def route_dependency_presentation(page: Page) -> None:
    page.route(
        "**/catalog.yaml",
        lambda route: route.fulfill(
            content_type="text/yaml",
            body=DEPENDENCY_CATALOG,
        ),
    )
    page.route(
        "**/presentations/*.yaml",
        lambda route: route.fulfill(
            content_type="text/yaml",
            body=DEPENDENCY_MANIFEST,
        ),
    )
    page.route(
        "**/slides/dependency-test.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body=DEPENDENCY_SLIDE,
        ),
    )


def test_dependency_handle_resolves_and_imports_static_cdn_entry(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_dependency_presentation(page)
    route_static_dependencies(
        page,
        FIXTURE_ROOT,
        (DEPENDENCY_CATALOG, DEPENDENCY_MANIFEST),
    )

    def remove_dependency_base(route: Any) -> None:
        response = route.fetch()
        route.fulfill(
            response=response,
            body=response.text().replace(' dependency-base="./~dependencies/"', ""),
        )

    page.route(f"{runtime_url}/", remove_dependency_base)
    cdn_requests: list[str] = []

    def serve_cdn_entry(route: Any) -> None:
        cdn_requests.append(route.request.url)
        route.fulfill(
            content_type="text/javascript",
            headers={"Access-Control-Allow-Origin": "*"},
            body="export const message = 'static dependency';",
        )

    page.route("https://cdn.example.invalid/graphics@1.2.3/entry.js", serve_cdn_entry)
    page.goto(f"{runtime_url}/#/vividly/entry")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    result = page.locator("#dependency-result")
    assert result.text_content() == "static dependency"
    assert (
        result.get_attribute("data-url")
        == "https://cdn.example.invalid/graphics@1.2.3/entry.js"
    )
    assert cdn_requests
    assert set(cdn_requests) == {"https://cdn.example.invalid/graphics@1.2.3/entry.js"}
    error = page.locator("vividly-presentation").evaluate(
        """element => {
            try {
              element._current.ctx.dependency('missing');
              return null;
            } catch (error) {
              return error.message;
            }
        }"""
    )
    assert error == 'Slide "entry" requested unmapped dependency "missing"'

    page.goto(f"{runtime_url}/#/alternate/entry")
    page.wait_for_function(
        """() => {
            const presentation = document.querySelector('vividly-presentation');
            return presentation?._presentationId === 'alternate'
                && presentation.hasAttribute('data-render-ready');
        }"""
    )
    assert result.get_attribute("data-url") == (
        "https://cdn.example.invalid/graphics@1.2.3/entry.js"
    )
    page.close()


def test_dependency_handle_resolves_and_imports_local_mirrored_entry(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    route_dependency_presentation(page)
    local_url = f"{runtime_url}/~dependencies/graphics/entry.js"
    local_requests: list[str] = []

    def serve_local_entry(route: Any) -> None:
        local_requests.append(route.request.url)
        route.fulfill(
            content_type="text/javascript",
            body="export const message = 'local dependency';",
        )

    page.route(local_url, serve_local_entry)
    page.goto(f"{runtime_url}/#/vividly/entry")
    page.wait_for_function(
        "() => document.querySelector('vividly-presentation')?.hasAttribute('data-render-ready')"
    )

    result = page.locator("#dependency-result")
    assert result.text_content() == "local dependency"
    assert result.get_attribute("data-url") == local_url
    assert local_requests == [local_url]
    page.close()


def test_catalog_rejects_invalid_dependency_mappings(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    catalogs = {
        "invalid-key.yaml": json.dumps(
            {
                "version": 1,
                "dependencies": {
                    "Not_Valid": {
                        "baseUrl": "https://cdn.example.invalid/package@1/",
                        "entry": "entry.js",
                    }
                },
                "presentations": [],
            }
        ),
        "invalid-base.yaml": json.dumps(
            {
                "version": 1,
                "dependencies": {
                    "package": {
                        "baseUrl": "http://cdn.example.invalid/package@1/",
                        "entry": "entry.js",
                    }
                },
                "presentations": [],
            }
        ),
        "invalid-entry.yaml": json.dumps(
            {
                "version": 1,
                "dependencies": {
                    "package": {
                        "baseUrl": "https://cdn.example.invalid/package@1/",
                        "entry": "../entry.js",
                    }
                },
                "presentations": [],
            }
        ),
    }

    def serve_catalog(route: Any) -> None:
        name = route.request.url.rsplit("/", maxsplit=1)[-1]
        route.fulfill(content_type="text/yaml", body=catalogs[name])

    page.route("**/dependency-validation/*.yaml", serve_catalog)
    page.goto(runtime_url)
    page.wait_for_function("() => Boolean(document.querySelector('vividly-presentation')?._yaml)")
    errors = page.evaluate(
        """async ({ moduleUrl, catalogBase }) => {
          const { loadCatalog } = await import(moduleUrl);
          const yaml = document.querySelector('vividly-presentation')._yaml;
          const names = [
            'invalid-key.yaml',
            'invalid-base.yaml',
            'invalid-entry.yaml',
          ];
          const errors = {};
          for (const name of names) {
            try {
              await loadCatalog(`${catalogBase}/${name}`, yaml);
              errors[name] = null;
            } catch (error) {
              errors[name] = error.message;
            }
          }
          return errors;
        }""",
        {
            "moduleUrl": f"{runtime_url}/vividly/runtime/catalog.js",
            "catalogBase": f"{runtime_url}/dependency-validation",
        },
    )

    assert 'Invalid dependency key "Not_Valid"' in errors["invalid-key.yaml"]
    assert "baseUrl must be a clean HTTPS URL" in errors["invalid-base.yaml"]
    assert "entry must be a normalized relative path" in errors["invalid-entry.yaml"]
    page.close()


def test_presentation_manifest_rejects_dependency_selections(
    browser: Browser,
    runtime_url: str,
) -> None:
    page = browser.new_page()
    page.route(
        "**/presentation-with-dependencies.yaml",
        lambda route: route.fulfill(
            content_type="text/yaml",
            body=json.dumps(
                {
                    "dependencies": {
                        "package": {
                            "baseUrl": "https://cdn.example.invalid/package@1/",
                            "entry": "entry.js",
                        }
                    },
                    "nodes": [],
                }
            ),
        ),
    )
    page.goto(runtime_url)
    page.wait_for_function("() => Boolean(document.querySelector('vividly-presentation')?._yaml)")
    error = page.evaluate(
        """async (manifestUrl) => {
          const { loadManifest } = await import('./vividly/runtime/manifest.js');
          const yaml = document.querySelector('vividly-presentation')._yaml;
          try {
            await loadManifest(manifestUrl, yaml);
            return null;
          } catch (error) {
            return error.message;
          }
        }""",
        f"{runtime_url}/presentation-with-dependencies.yaml",
    )

    assert "cannot declare dependencies; declare them in catalog.yaml" in error
    page.close()