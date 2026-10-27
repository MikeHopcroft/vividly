"""Validate public dependency sources as specified in docs/specs/precommit.md."""

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit


class LockfileError(ValueError):
    """The lockfile could not be read or violates the public-source policy."""


def table(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LockfileError(f"{field}: expected a table")
    return cast(dict[str, object], value)


def artifact(value: object, field: str) -> None:
    entry = table(value, field)
    url = entry.get("url")
    if not isinstance(url, str) or any(ord(character) <= 32 for character in url):
        raise LockfileError(f"{field}.url: expected a public artifact URL")
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise LockfileError(f"{field}.url: invalid artifact URL") from None
    if parsed.scheme != "https" or parsed.netloc != "files.pythonhosted.org":
        raise LockfileError(
            f"{field}.url: expected HTTPS on files.pythonhosted.org without credentials or ports"
        )


def validate(content: str) -> None:
    try:
        document = cast(dict[str, object], tomllib.loads(content))
    except tomllib.TOMLDecodeError:
        raise LockfileError("uv.lock: invalid TOML") from None
    packages = document.get("package")
    if not isinstance(packages, list) or not packages:
        raise LockfileError("uv.lock: expected a nonempty package list")
    for number, value in enumerate(cast(list[object], packages)):
        package = table(value, f"package[{number}]")
        name = package.get("name")
        if not isinstance(name, str) or not name:
            raise LockfileError(f"package[{number}].name: expected a package name")
        field = f"package {name!r}"
        source = table(package.get("source"), f"{field}.source")
        if source != {"registry": "https://pypi.org/simple"} and not (
            name == "vividly" and source == {"editable": "."}
        ):
            raise LockfileError(
                f"{field}.source: expected public PyPI or the root editable package"
            )
        if "sdist" in package:
            artifact(package["sdist"], f"{field}.sdist")
        wheels = package.get("wheels", [])
        if not isinstance(wheels, list):
            raise LockfileError(f"{field}.wheels: expected a list")
        for wheel_number, wheel in enumerate(cast(list[object], wheels)):
            artifact(wheel, f"{field}.wheels[{wheel_number}]")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="read uv.lock from Git's index")
    parser.add_argument("path", nargs="?", type=Path, help="lockfile to check (default: uv.lock)")
    arguments = parser.parse_args()
    if arguments.staged and arguments.path is not None:
        parser.error("--staged cannot be combined with a file path")
    try:
        if arguments.staged:
            result = subprocess.run(
                ["git", "show", ":uv.lock"],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                raise LockfileError(
                    "Cannot read staged uv.lock; it must remain present in the index "
                    f"(git exit {result.returncode})."
                )
            content = result.stdout.decode("utf-8")
        else:
            path = cast(Path | None, arguments.path) or Path("uv.lock")
            content = path.read_text(encoding="utf-8")
        validate(content)
    except (LockfileError, OSError, UnicodeError) as error:
        if isinstance(error, LockfileError):
            message = str(error)
        elif isinstance(error, UnicodeError):
            message = "uv.lock must be UTF-8 text"
        else:
            message = f"Cannot read lockfile input or run Git ({type(error).__name__})"
        print(f"Lockfile check failed: {message}", file=sys.stderr)
        print(
            "Correct the selected lockfile; no files or staged content were changed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
