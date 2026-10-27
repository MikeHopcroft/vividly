"""Test-only assembly of the frozen runtime shakedown."""

import hashlib
import json
import shutil
import tempfile
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

import yaml
from playwright.sync_api import Page, Route

from vividly.constants import (
    RUNTIME_RESOURCE_NAME,
    SITE_INDEX_NAME,
    STARTER_PROJECT_PACKAGE,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures/runtime-shakedown"
DEPENDENCY_FIXTURES = {
    "highlight-github-dark": (
        "github-dark.min.css",
        "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css",
        "text/css",
    ),
    "highlight-js": (
        "highlight.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js",
        "text/javascript",
    ),
    "js-yaml": (
        "js-yaml.min.js",
        "https://cdn.jsdelivr.net/npm/js-yaml@4.1.0/dist/js-yaml.min.js",
        "text/javascript",
    ),
    "marked": (
        "marked.umd.js",
        "https://cdn.jsdelivr.net/npm/marked@12.0.2/lib/marked.umd.js",
        "text/javascript",
    ),
}
STATIC_DEPENDENCY_URLS = frozenset(
    source_url for _entry, source_url, _content_type in DEPENDENCY_FIXTURES.values()
)

MARKED_FIXTURE = b"""
globalThis.marked = {
  parse(source) {
    const escapeHtml = (value) => value
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;');
    const inline = (value) => escapeHtml(value)
      .replace(/!\\[([^\\]]*)\\]\\(([^)]+)\\)/g, '<img alt="$1" src="$2">')
      .replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="$2">$1</a>')
      .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code>$1</code>');
    const output = [];
    let paragraph = [];
    let code = null;
    let language = '';
    const flush = () => {
      if (!paragraph.length) return;
      output.push(`<p>${inline(paragraph.join(' '))}</p>`);
      paragraph = [];
    };
    for (const line of source.split(/\\r?\\n/)) {
      const fence = line.match(/^```(.*)$/);
      if (fence) {
        if (code === null) {
          flush();
          code = [];
          language = fence[1].trim();
        } else {
          const className = language ? ` class="language-${language}"` : '';
          output.push(`<pre><code${className}>${escapeHtml(code.join('\\n'))}</code></pre>`);
          code = null;
          language = '';
        }
        continue;
      }
      if (code !== null) {
        code.push(line);
        continue;
      }
      const heading = line.match(/^(#{1,6})\\s+(.+)$/);
      if (heading) {
        flush();
        const level = heading[1].length;
        output.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      } else if (!line.trim()) {
        flush();
      } else if (line.trimStart().startsWith('<')) {
        flush();
        output.push(line);
      } else {
        paragraph.push(line.trim());
      }
    }
    flush();
    return output.join('\\n');
  },
  lexer(source) {
    return [{ type: 'html', raw: source }];
  },
  walkTokens(tokens, visitor) {
    tokens.forEach(visitor);
  },
};
"""
HIGHLIGHT_FIXTURE = b"""
globalThis.hljs = {
  highlight(source) {
    const escaped = source
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;');
    return { value: escaped.replace(/\\b(const|class|export|function|return)\\b/g,
      '<span class="hljs-keyword">$1</span>') };
  },
  highlightAuto(source) {
    return this.highlight(source);
  },
  highlightElement(element) {
    element.classList.add('hljs');
    element.innerHTML = this.highlight(element.textContent).value;
  },
};
"""
HIGHLIGHT_THEME_FIXTURE = b".hljs{color:#c9d1d9;background:#0d1117}\n"


def dependency_fixture_resources(
    site_root: Path,
    additional_yaml: Iterable[str] = (),
) -> dict[str, tuple[bytes, str]]:
    """Return deterministic test implementations for the runtime dependencies."""
    yaml_documents: dict[str, object] = {}
    for path in sorted(site_root.rglob("*.yaml")):
        source = path.read_text(encoding="utf-8")
        yaml_documents[source] = yaml.safe_load(source)
    for source in additional_yaml:
        yaml_documents[source] = yaml.safe_load(source)
    serialized = json.dumps(yaml_documents, ensure_ascii=False, separators=(",", ":"))
    yaml_fixture = (
        "const documents = "
        + serialized
        + ";\n"
        + """globalThis.jsyaml = {
  load(source) {
            if (Object.prototype.hasOwnProperty.call(documents, source)) {
              return structuredClone(documents[source]);
    }
            try {
              return JSON.parse(source);
            } catch {
              throw new Error('Unexpected YAML document in test dependency fixture');
            }
          },
        };
"""
    ).encode()
    return {
        DEPENDENCY_FIXTURES["js-yaml"][1]: (yaml_fixture, "text/javascript"),
        DEPENDENCY_FIXTURES["marked"][1]: (MARKED_FIXTURE, "text/javascript"),
        DEPENDENCY_FIXTURES["highlight-js"][1]: (
            HIGHLIGHT_FIXTURE,
            "text/javascript",
        ),
        DEPENDENCY_FIXTURES["highlight-github-dark"][1]: (
            HIGHLIGHT_THEME_FIXTURE,
            "text/css",
        ),
    }


def install_test_runtime(project_root: Path) -> dict[str, tuple[bytes, str]]:
    """Install an editable runtime whose built-in integrity matches test fixtures."""
    package = resources.files(STARTER_PROJECT_PACKAGE)
    runtime_root = project_root / "test-runtime"
    with resources.as_file(package.joinpath(RUNTIME_RESOURCE_NAME)) as runtime:
        shutil.copytree(runtime, runtime_root)
    with resources.as_file(package.joinpath("reference")) as reference:
        shutil.copytree(reference, project_root / "reference")
    fixtures = dependency_fixture_resources(project_root / "site")
    dependency_path = runtime_root / "vividly" / "dependencies.json"
    dependency_table = json.loads(dependency_path.read_text(encoding="utf-8"))
    for key, (_entry, source_url, _content_type) in DEPENDENCY_FIXTURES.items():
        dependency_table["dependencies"][key]["sha256"] = hashlib.sha256(
            fixtures[source_url][0]
        ).hexdigest()
    dependency_bytes = (
        json.dumps(dependency_table, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
    dependency_path.write_bytes(dependency_bytes)
    manifest_path = runtime_root / "vividly-runtime.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["vividly/dependencies.json"] = hashlib.sha256(
        dependency_bytes
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    version = (runtime_root / "vividly" / "version.txt").read_text(encoding="utf-8").strip()
    (project_root / "vividly.yaml").write_text(
        "schema: 1\n"
        "runtime:\n"
        "  source: path\n"
        "  path: test-runtime\n"
        f"  upstream_version: {version}\n",
        encoding="utf-8",
    )
    return fixtures


@contextmanager
def assembled_runtime_site() -> Generator[Path, None, None]:
    """Yield a physical site containing the runtime and frozen test content."""
    package = resources.files(STARTER_PROJECT_PACKAGE)
    with (
        resources.as_file(package.joinpath(RUNTIME_RESOURCE_NAME)) as runtime,
        tempfile.TemporaryDirectory(prefix="vividly-runtime-test-") as temporary,
    ):
        site_root = Path(temporary) / "site"
        shutil.copytree(FIXTURE_ROOT, site_root)
        shutil.copy2(runtime / SITE_INDEX_NAME, site_root / SITE_INDEX_NAME)
        shutil.copytree(runtime / "vividly", site_root / "vividly")
        index_path = site_root / SITE_INDEX_NAME
        index_path.write_text(
            index_path.read_text(encoding="utf-8").replace(
                "<vividly-presentation ",
                '<vividly-presentation dependency-base="./~dependencies/" ',
                1,
            ),
            encoding="utf-8",
        )
        fixtures = dependency_fixture_resources(site_root)
        for key, (entry, source_url, _content_type) in DEPENDENCY_FIXTURES.items():
            destination = site_root / "~dependencies" / key / entry
            destination.parent.mkdir(parents=True)
            destination.write_bytes(fixtures[source_url][0])
        yield site_root


def route_static_dependencies(
    page: Page,
    site_root: Path,
    additional_yaml: Iterable[str] = (),
) -> None:
    """Fulfill pinned runtime dependency URLs with deterministic test implementations."""
    for source_url, (content, content_type) in dependency_fixture_resources(
        site_root,
        additional_yaml,
    ).items():

        def fulfill(
            route: Route, *, content_type: str = content_type, content: bytes = content
        ) -> None:
            route.fulfill(
                body=content,
                content_type=content_type,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        page.route(
            source_url,
            fulfill,
        )


def route_local_dependencies(page: Page, base_url: str, site_root: Path) -> None:
    """Fulfill local dependency-route URLs with deterministic test implementations."""
    fixtures = dependency_fixture_resources(site_root)
    for key, (entry, source_url, _content_type) in DEPENDENCY_FIXTURES.items():
        local_url = f"{base_url}/~dependencies/{key}/{entry}"
        content, content_type = fixtures[source_url]

        def fulfill(
            route: Route, *, content_type: str = content_type, content: bytes = content
        ) -> None:
            route.fulfill(
                body=content,
                content_type=content_type,
            )

        page.route(
            local_url,
            fulfill,
        )
