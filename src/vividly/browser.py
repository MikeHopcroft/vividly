"""Playwright browser installation and launch diagnostics."""

from importlib.metadata import version


def chromium_launch_error_message(error: Exception) -> str:
    """Describe a Chromium launch failure with an actionable installation remedy."""
    if "Executable doesn't exist" not in str(error):
        return f"could not launch Chromium: {error}"
    playwright_version = version("playwright")
    return (
        f"compatible Chromium is not installed for Playwright {playwright_version}; "
        "this can happen after Vividly or Playwright is installed or upgraded; "
        "run 'vividly install-browser'"
    )
