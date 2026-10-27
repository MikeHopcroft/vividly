"""Tests for the publishing configuration in docs/specs/publishing.md section 5."""

from pathlib import Path

import pytest

from vividly.publishing.config import (
    PublishingConfigError,
    load_publishing_config,
    resolve_target,
)


def _write_config(project_root: Path, content: str) -> None:
    (project_root / "vividly.publish.yaml").write_text(content, encoding="utf-8")


def test_loads_github_pages_defaults_and_resolves_sole_target(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """schema: 1
targets:
  pages:
    provider: github-pages
""",
    )

    config = load_publishing_config(tmp_path)
    target = resolve_target(config, None)

    assert config.default is None
    assert target.name == "pages"
    assert target.remote == "origin"
    assert target.branch == "gh-pages"
    assert target.expected_url is None
    assert target.custom_domain is None


def test_normalizes_custom_domain_and_preserves_expected_url(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """schema: 1
default: production
targets:
  preview:
    provider: github-pages
    branch: preview
  production:
    provider: github-pages
    remote: upstream
    branch: public
    expected_url: https://slides.example.com/talk/
    custom_domain: Slides.Example.COM
""",
    )

    config = load_publishing_config(tmp_path)
    target = resolve_target(config, None)

    assert target.name == "production"
    assert target.remote == "upstream"
    assert target.branch == "public"
    assert target.expected_url == "https://slides.example.com/talk/"
    assert target.custom_domain == "slides.example.com"
    assert resolve_target(config, "preview").branch == "preview"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            """schema: 1
schema: 1
targets: {}
""",
            "duplicate key",
        ),
        (
            """schema: 1
targets: {}
""",
            "`targets` must not be empty",
        ),
        (
            """schema: 1
targets:
  first:
    provider: github-pages
  second:
    provider: github-pages
""",
            "`default` is required",
        ),
        (
            """schema: 1
targets:
  pages:
    provider: github-pages
    unknown: true
""",
            "unknown key `unknown`",
        ),
        (
            """schema: 1
targets:
  pages:
    provider: other
""",
            "must equal `github-pages`",
        ),
        (
            """schema: 1
targets:
  pages:
    provider: github-pages
    expected_url: http://example.com/
""",
            "absolute HTTPS URL",
        ),
        (
            """schema: 1
targets:
  pages:
    provider: github-pages
    custom_domain: https://example.com/
""",
            "ASCII DNS name",
        ),
    ],
)
def test_rejects_invalid_configuration(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    _write_config(tmp_path, content)

    with pytest.raises(PublishingConfigError, match=message):
        load_publishing_config(tmp_path)


def test_rejects_unknown_requested_target(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """schema: 1
targets:
  pages:
    provider: github-pages
""",
    )
    config = load_publishing_config(tmp_path)

    with pytest.raises(PublishingConfigError, match="not configured: preview"):
        resolve_target(config, "preview")
