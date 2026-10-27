"""Tests for browser diagnostics specified by docs/specs/cli.md section 7."""

from unittest.mock import patch

from vividly.browser import chromium_launch_error_message


def test_missing_chromium_diagnostic_names_playwright_version_and_remedy() -> None:
    error = RuntimeError("BrowserType.launch: Executable doesn't exist at /browser")

    with patch("vividly.browser.version", return_value="1.63.0"):
        message = chromium_launch_error_message(error)

    assert message == (
        "compatible Chromium is not installed for Playwright 1.63.0; "
        "this can happen after Vividly or Playwright is installed or upgraded; "
        "run 'vividly install-browser'"
    )


def test_other_chromium_launch_failure_preserves_playwright_detail() -> None:
    error = RuntimeError("browser process exited unexpectedly")

    assert chromium_launch_error_message(error) == (
        "could not launch Chromium: browser process exited unexpectedly"
    )
