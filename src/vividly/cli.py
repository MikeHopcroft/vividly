"""Command-line interface for Vividly."""

import argparse
import errno
import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from datetime import UTC
from importlib import resources
from importlib.metadata import version
from pathlib import Path
from typing import cast
from urllib.parse import urljoin

from rich.console import Console
from rich.table import Table

from .composition import CompositionError, compose_project
from .constants import (
    BASELINE_NAME,
    DEFAULT_PORT,
    EXISTING_FILE_LIST_LIMIT,
    IGNORED_NAMES,
    IGNORED_SUFFIXES,
    PROJECT_CONFIG_NAME,
    STARTER_PROJECT_NAME,
    STARTER_PROJECT_PACKAGE,
)
from .dependencies import (
    DependencyAcquisitionError,
    DependencyCache,
    DependencyCacheRecord,
    DependencySelection,
    clear_dependency_cache,
    default_dependency_cache_root,
    inspect_dependency_cache,
)
from .export import ExportError, export_project
from .project import PackageRuntime, ProjectConfigError, load_project_config
from .publishing import PublicationError, PublicationPlan, publish_project
from .reference import ReferenceMaterializationError, materialize_reference
from .runtime import RuntimeManifestError, packaged_runtime, selected_runtime
from .server import CompositionSession, ReloadBroker, composition_handler

type CommandHandler = Callable[[argparse.Namespace], None]


def unimplemented_command(arguments: argparse.Namespace) -> None:
    """Report that a command is not implemented."""
    command = cast(str, arguments.command)
    print(f"vividly {command} is not implemented.")


def install_browser_command(arguments: argparse.Namespace) -> None:
    """Install the Chromium revision required by the active Playwright package."""
    del arguments
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )
    except OSError as error:
        raise SystemExit(
            f"vividly install-browser: could not start Playwright installer: {error}"
        ) from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            "vividly install-browser: Playwright installer failed "
            f"with exit code {error.returncode}"
        ) from error
    print(f"Chromium is installed for Playwright {version('playwright')}.")


def tool_version() -> str:
    """Return the version of the installed vividly package."""
    return version("vividly")


def version_banner() -> str:
    """Describe the tool and the packaged runtime it carries."""
    with packaged_runtime() as runtime:
        manifest = runtime.manifest
        return (
            f"vividly {runtime.distribution_version} "
            f"(framework {manifest.version}; composition API {manifest.composition_api})"
        )


def is_ignored_path(path: Path) -> bool:
    """Return whether any path component is provisioning debris."""
    return any(
        part in IGNORED_NAMES or part.endswith(IGNORED_SUFFIXES)
        for part in path.parts
    )


def ignored_copy_entries(directory: str, names: list[str]) -> set[str]:
    """Return payload entries copytree must omit under the shared debris predicate."""
    del directory
    return {name for name in names if is_ignored_path(Path(name))}


def confirm(prompt: str) -> bool:
    """Ask the user to approve an action."""
    try:
        answer = input(f"{prompt} [y/N]: ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def existing_entries(root: Path) -> list[Path]:
    """List the top-level entries already in a directory."""
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir() if not is_ignored_path(Path(path.name))),
        key=lambda path: path.name,
    )


def path_is_occupied(path: Path) -> bool:
    """Return whether a path has an entry, including a broken symbolic link."""
    return path.exists() or path.is_symlink()


def payload_collisions(payload_root: Path, project_root: Path) -> list[str]:
    """List destination paths that prevent copying the payload without overwriting."""
    collisions: list[str] = []
    for source in sorted(payload_root.rglob("*"), key=lambda path: path.as_posix()):
        relative = source.relative_to(payload_root)
        if is_ignored_path(relative):
            continue
        destination = project_root / relative
        if source.is_dir():
            if path_is_occupied(destination) and (
                destination.is_symlink() or not destination.is_dir()
            ):
                collisions.append(relative.as_posix())
        elif path_is_occupied(destination):
            if (
                relative == Path(".gitignore")
                and destination.is_file()
                and not destination.is_symlink()
            ):
                continue
            collisions.append(relative.as_posix())
    return collisions


def report_existing_entries(entries: list[Path]) -> None:
    """Warn that a new project is being added to a non-empty directory."""
    print("This directory already contains:")
    shown = entries[:EXISTING_FILE_LIST_LIMIT]
    for entry in shown:
        if entry.name == ".git" and entry.is_dir() and not entry.is_symlink():
            label = "existing Git repository"
        else:
            suffix = "/" if entry.is_dir() and not entry.is_symlink() else ""
            label = f"{entry.name}{suffix}"
        print(f"  {label}")
    remainder = len(entries) - len(shown)
    if remainder:
        print(f"  ...and {remainder} more")
    print("Existing content will remain unchanged.")


def write_project_config(project_root: Path, content: str) -> Path:
    """Atomically publish project configuration after all seeds exist."""
    config_path = project_root / PROJECT_CONFIG_NAME
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=project_root,
            prefix=f".{PROJECT_CONFIG_NAME}.",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(config_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return config_path


def package_runtime_config(
    distribution_version: str,
    framework_version: str,
    integrity: str,
) -> str:
    """Render canonical package-runtime project configuration."""
    return (
        "schema: 1\n"
        "runtime:\n"
        "  source: package\n"
        f"  distribution_version: {json.dumps(distribution_version)}\n"
        f"  version: {json.dumps(framework_version)}\n"
        f"  integrity: {json.dumps(integrity)}\n"
    )


def upgrade_package_runtime(
    project_root: Path,
    *,
    assume_yes: bool,
) -> None:
    """Repin an existing project to the installed package runtime."""
    config_path = project_root / PROJECT_CONFIG_NAME
    if not path_is_occupied(config_path):
        raise SystemExit(
            f"vividly provision: --upgrade requires an existing {PROJECT_CONFIG_NAME} "
            f"at {project_root}"
        )
    try:
        configured = load_project_config(project_root).runtime
    except ProjectConfigError as error:
        raise SystemExit(
            f"vividly provision: cannot upgrade invalid {PROJECT_CONFIG_NAME}: {error}\n"
            "Nothing was written."
        ) from error
    if not isinstance(configured, PackageRuntime):
        raise SystemExit(
            "vividly provision: --upgrade supports only projects whose runtime source "
            f"is `package`, not `{configured.source}`\n"
            f"{PROJECT_CONFIG_NAME} was not changed."
        )

    try:
        with packaged_runtime(
            verify_runtime_contents=True,
            verify_reference_contents=True,
        ) as runtime:
            distribution_version = runtime.distribution_version
            manifest = runtime.manifest
    except RuntimeManifestError as error:
        raise SystemExit(f"vividly provision: {error}\nNothing was written.") from error

    if (
        configured.distribution_version == distribution_version
        and configured.version == manifest.version
        and configured.integrity == manifest.integrity
    ):
        print(
            f"vividly provision: {project_root} already selects the installed "
            "package runtime."
        )
        return

    print(f"Vividly will update the package runtime selected by {config_path}")
    print(f"  distribution: {configured.distribution_version} -> {distribution_version}")
    print(f"  framework: {configured.version} -> {manifest.version}")
    print(f"  integrity: {configured.integrity} -> {manifest.integrity}")
    print(f"Only {PROJECT_CONFIG_NAME} will change.")
    if not assume_yes and not confirm("Update runtime selection?"):
        print("vividly provision: cancelled. Nothing was written.")
        return

    write_project_config(
        project_root,
        package_runtime_config(
            distribution_version,
            manifest.version,
            manifest.integrity,
        ),
    )
    print(f"Updated package runtime selection in {config_path}")


def provision_command(arguments: argparse.Namespace) -> None:
    """Create a project and select the installed package runtime."""
    project_root = cast(Path, arguments.project_root).expanduser().resolve()
    assume_yes = cast(bool, arguments.assume_yes)
    upgrade = bool(getattr(arguments, "upgrade", False))

    if project_root.exists() and not project_root.is_dir():
        raise SystemExit(f"vividly provision: {project_root} is not a directory")

    config_path = project_root / PROJECT_CONFIG_NAME
    baseline_path = project_root / BASELINE_NAME
    if upgrade:
        upgrade_package_runtime(project_root, assume_yes=assume_yes)
        return
    if path_is_occupied(config_path):
        raise SystemExit(
            f"vividly provision: project is already provisioned at {project_root}\n"
            f"{PROJECT_CONFIG_NAME} was not changed."
        )
    if path_is_occupied(baseline_path):
        raise SystemExit(
            f"vividly provision: unsupported Vividly project layout at {project_root}\n"
            f"{BASELINE_NAME} belongs to the pre-composition layout. Automatic migration "
            "is unavailable, nothing was written, and this project must be reprovisioned."
        )

    package = resources.files(STARTER_PROJECT_PACKAGE)
    with resources.as_file(package.joinpath(STARTER_PROJECT_NAME)) as starter:
        collisions = payload_collisions(starter, project_root)
        if collisions:
            shown = collisions[:EXISTING_FILE_LIST_LIMIT]
            listing = "\n".join(f"  {name}" for name in shown)
            remainder = len(collisions) - len(shown)
            if remainder:
                listing += f"\n  ...and {remainder} more"
            raise SystemExit(
                f"vividly provision: provisioning would overwrite existing paths:\n{listing}\n"
                "Move or remove these paths before provisioning. Nothing was written."
            )

        try:
            with packaged_runtime(
                verify_runtime_contents=True,
                verify_reference_contents=True,
            ) as runtime:
                distribution_version = runtime.distribution_version
                manifest = runtime.manifest
        except RuntimeManifestError as error:
            raise SystemExit(f"vividly provision: {error}\nNothing was written.") from error

        existing = existing_entries(project_root)
        existing_gitignore = (project_root / ".gitignore").is_file()
        print(f"Vividly will create a new project in {project_root}")
        if existing:
            report_existing_entries(existing)
        print("It will add:")
        additions = [".github/", "site/", PROJECT_CONFIG_NAME]
        if not existing_gitignore:
            additions.insert(0, ".gitignore")
        for addition in additions:
            print(f"  {addition}")
        print(f"Installed distribution: {distribution_version}")
        print(f"Framework runtime: {manifest.version}")
        print(f"Runtime integrity: {manifest.integrity}")
        if existing_gitignore:
            print("The existing .gitignore will not be changed.")
            print("Add this recommended rule if it is not already present: .vividly/")

        if not assume_yes and not confirm("Proceed?"):
            print("vividly provision: cancelled. Nothing was written.")
            return

        config_content = package_runtime_config(
            distribution_version,
            manifest.version,
            manifest.integrity,
        )
        with tempfile.TemporaryDirectory(prefix="vividly-provision-") as temporary:
            staged = Path(temporary) / "starter"
            shutil.copytree(starter, staged, ignore=ignored_copy_entries)
            if existing_gitignore:
                (staged / ".gitignore").unlink()
            shutil.copytree(
                staged,
                project_root,
                dirs_exist_ok=True,
                ignore=ignored_copy_entries,
            )

    config_path = write_project_config(project_root, config_content)
    print(f"Created project in {project_root}")
    print(f"Selected framework {manifest.version} in {config_path}")
    print('\nUse "vividly run" to edit your project.')


def reference_command(arguments: argparse.Namespace) -> None:
    """Materialize reference documents for the selected runtime."""
    project_root = cast(Path, arguments.project_root).expanduser().resolve()
    try:
        config = load_project_config(project_root)
        with selected_runtime(
            project_root,
            config,
            verify_reference_contents=True,
        ) as runtime:
            count, changed = materialize_reference(project_root, runtime)
    except (
        OSError,
        ProjectConfigError,
        RuntimeManifestError,
        ReferenceMaterializationError,
    ) as error:
        raise SystemExit(f"vividly reference: {error}") from error

    if changed:
        print(f"Materialized {count} reference files in {project_root / '.vividly/reference'}")
    else:
        print(f"Reference material is already current in {project_root / '.vividly/reference'}")


def run_command(arguments: argparse.Namespace) -> None:
    """Serve a Vividly project locally."""
    # watchfiles loads only for the command that needs its native watcher.
    from .watcher import WatcherError, watch_for_reloads

    port = cast(int, arguments.port)
    no_watch = cast(bool, arguments.no_watch)
    project_root = cast(Path, arguments.project_root).expanduser().resolve()
    try:
        with CompositionSession(project_root) as compositions:
            reload_broker = None if no_watch else ReloadBroker()
            try:
                handler = composition_handler(
                    compositions,
                    reload_broker=reload_broker,
                    dependency_cache=DependencyCache(default_dependency_cache_root()),
                )
                try:
                    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
                except OSError as error:
                    if error.errno != errno.EADDRINUSE:
                        raise
                    raise SystemExit(
                        f"vividly run: port {port} is already in use\n"
                        "Choose another port with --port PORT."
                    ) from error

                with server:
                    print(
                        f"Serving composed project {project_root} "
                        f"at http://localhost:{server.server_port}"
                    )
                    if no_watch:
                        try:
                            server.serve_forever()
                        except KeyboardInterrupt:
                            print("\nServer stopped.")
                    else:
                        assert reload_broker is not None
                        stop_event = threading.Event()
                        server_thread = threading.Thread(
                            target=server.serve_forever,
                            daemon=True,
                        )
                        server_thread.start()

                        def report_validation_error(message: str) -> None:
                            print(
                                f"vividly run: reload validation failed: {message}",
                                file=sys.stderr,
                                flush=True,
                            )

                        try:
                            watch_for_reloads(
                                compositions,
                                reload_broker,
                                stop_event,
                                report_validation_error,
                            )
                            raise WatcherError("watcher stopped unexpectedly")
                        except KeyboardInterrupt:
                            print("\nServer stopped.")
                        finally:
                            stop_event.set()
                            server.shutdown()
                            server_thread.join()
            finally:
                if reload_broker is not None:
                    reload_broker.close()
    except (
        OSError,
        CompositionError,
        ProjectConfigError,
        RuntimeManifestError,
        WatcherError,
    ) as error:
        raise SystemExit(f"vividly run: {error}") from error


def thumbnails_command(arguments: argparse.Namespace) -> None:
    """Generate all thumbnails or a selected subset."""
    # thumbnails imports Playwright, whose initialization can substantially delay
    # unrelated commands such as `vividly run`.
    from .thumbnails import ThumbnailError, generate_thumbnails

    project_root = cast(Path, arguments.project_root)
    presentation_id = cast(str | None, arguments.presentation_id)
    addresses = cast(list[str] | None, arguments.slides)
    missing_only = cast(bool, arguments.missing_only)

    def report_progress(
        slide_position: int,
        slide_total: int,
        selected_id: str,
        address: str,
        step: int,
        step_position: int,
        step_total: int,
    ) -> None:
        print(
            f"Capturing slide {slide_position}/{slide_total}: {selected_id}:{address}, "
            f"step {step} ({step_position} of {step_total})",
            flush=True,
        )

    try:
        results = generate_thumbnails(
            project_root,
            presentation_id=presentation_id,
            addresses=addresses,
            missing_only=missing_only,
            on_progress=report_progress,
        )
    except ThumbnailError as error:
        raise SystemExit(f"vividly thumbnails: {error}") from error
    for result in results:
        print(
            f"Captured {result.presentation_id}:{result.address} "
            f"at step {result.step}: {result.path}"
        )
    count = len(results)
    noun = "thumbnail" if count == 1 else "thumbnails"
    print(f"Generated {count} {noun}.")


def export_command(arguments: argparse.Namespace) -> None:
    """Materialize a complete static site from one project."""
    project_root = cast(Path, arguments.project_root)
    destination = cast(Path, arguments.output)
    try:
        exported = export_project(project_root, destination)
    except (
        OSError,
        CompositionError,
        ExportError,
        ProjectConfigError,
        RuntimeManifestError,
    ) as error:
        raise SystemExit(f"vividly export: {error}") from error
    print(f"Exported static site to {exported}")


def publish_command(arguments: argparse.Namespace) -> None:
    """Publish one complete site to a configured target."""
    project_root = cast(Path, arguments.project_root)
    target_name = cast(str | None, arguments.target_name)
    dry_run = cast(bool, arguments.dry_run)

    def report_plan(plan: PublicationPlan) -> None:
        print(f"Project: {plan.project_root}")
        print(f"Source revision: {plan.source_commit}")
        print(f"Target: {plan.target}")
        print(f"Publication branch: {plan.remote}/{plan.branch}")
        print(
            "GitHub Pages setup: configure the repository to deploy "
            f"`{plan.branch}` from `/` (root)."
        )
        if plan.expected_url is not None:
            print(f"Expected URL: {plan.expected_url}")
        if plan.custom_domain is not None:
            print(f"Custom domain: {plan.custom_domain} (configure DNS separately).")

    try:
        result = publish_project(
            project_root,
            target_name=target_name,
            dry_run=dry_run,
            on_plan=report_plan,
        )
    except PublicationError as error:
        raise SystemExit(f"vividly publish: {error}") from error

    print(f"Framework version: {result.identity.framework_version}")
    print(f"Runtime integrity: {result.identity.runtime_integrity}")
    if result.operation == "dry-run-initial":
        print(
            "Dry run: initial publication would be created; "
            "no candidate Git objects or refs were written."
        )
    elif result.operation == "dry-run-changed":
        print(
            "Dry run: publication would change; "
            "no candidate Git objects or refs were written."
        )
    elif result.operation == "dry-run-unchanged":
        print(
            "Dry run: deployable bytes are unchanged; "
            "no candidate Git objects or refs were written."
        )
    elif result.operation == "unchanged":
        print(
            f"Deployable bytes are unchanged at publication {result.publication_commit}; "
            "no commit was created or pushed."
        )
    else:
        print(f"Published commit: {result.publication_commit}")
        print("GitHub Pages activation is asynchronous and is not observed by Vividly.")


def rehearse_command(arguments: argparse.Namespace) -> None:
    """Run a user-driven cache-only rehearsal."""
    # Rehearsal imports Playwright only for the command that launches a browser.
    from .rehearsal import RehearsalError, rehearse_project

    project_root = cast(Path, arguments.project_root)
    try:
        result = rehearse_project(project_root)
    except (
        OSError,
        CompositionError,
        ProjectConfigError,
        RehearsalError,
        RuntimeManifestError,
    ) as error:
        raise SystemExit(f"vividly rehearse: {error}") from error

    if result.passed:
        print(
            "Rehearsal passed: the presentation worked without external dependency "
            "access for the slides and interactions exercised during this rehearsal."
        )
        return

    print("Rehearsal failed:", file=sys.stderr)
    for issue in result.issues:
        print(
            f"- {issue.kind} at {issue.route}: {issue.url} ({issue.detail})",
            file=sys.stderr,
        )
    raise SystemExit(1)


def _dependency_json(selection: DependencySelection) -> dict[str, object]:
    loader: dict[str, object] = {"type": selection.loader.type}
    if selection.loader.global_name is not None:
        loader["global"] = selection.loader.global_name
    return {
        "baseUrl": selection.base_url,
        "entry": selection.entry.as_posix(),
        "key": selection.key,
        "license": selection.license,
        "loader": loader,
        "owner": selection.owner,
        "ownerIdentity": selection.owner_identity,
        "projectUrl": selection.project_url,
        "sha256": selection.sha256,
        "url": urljoin(selection.base_url, selection.entry.as_posix()),
        "version": selection.version,
    }


def _print_dependency_table(dependencies: list[DependencySelection]) -> None:
    table = Table()
    table.add_column("KEY", style="cyan", no_wrap=True)
    table.add_column("OWNER", no_wrap=True)
    table.add_column("VERSION", no_wrap=True)
    table.add_column("LOADER", no_wrap=True)
    table.add_column("URL")
    for selection in dependencies:
        table.add_row(
            selection.key,
            selection.owner_identity or "catalog",
            selection.version or "—",
            selection.loader.type,
            urljoin(selection.base_url, selection.entry.as_posix()),
        )
    Console().print(table)


def _cache_record_json(record: DependencyCacheRecord) -> dict[str, object]:
    cached_at = (
        record.cached_at.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
        if record.cached_at is not None
        else None
    )
    return {
        "cachedAt": cached_at,
        "key": record.key,
        "relativePath": (
            record.relative_path.as_posix()
            if record.relative_path is not None
            else None
        ),
        "size": record.size,
        "sourceUrl": record.source_url,
        "status": record.status,
    }


def _print_cache_table(records: tuple[DependencyCacheRecord, ...]) -> None:
    status_styles = {
        "valid": "green",
        "missing": "bold red",
        "invalid": "bold red",
        "incomplete": "yellow",
        "unreadable": "bold red",
    }
    table = Table()
    table.add_column("KEY", no_wrap=True)
    table.add_column("RESOURCE")
    table.add_column("STATUS", no_wrap=True)
    table.add_column("SIZE", justify="right", no_wrap=True)
    table.add_column("CACHED", no_wrap=True)
    table.add_column("URL")
    for record in records:
        cached_at = (
            record.cached_at.astimezone().isoformat(
                sep=" ",
                timespec="seconds",
            )
            if record.cached_at is not None
            else "—"
        )
        table.add_row(
            record.key or "—",
            record.relative_path.as_posix()
            if record.relative_path is not None
            else "—",
            f"[{status_styles[record.status]}]{record.status}[/]",
            str(record.size) if record.size is not None else "—",
            cached_at,
            record.source_url or "—",
        )
    Console().print(table)


def cache_status_command(arguments: argparse.Namespace) -> None:
    """Display project-selected or global dependency-cache resources."""
    selected_project_root = cast(Path | None, arguments.project_root)
    inspect_all = cast(bool, arguments.all_cache)
    json_output = cast(bool, arguments.json_output)
    if inspect_all and selected_project_root is not None:
        raise SystemExit("vividly cache status: PATH cannot be combined with --all")
    project_root = selected_project_root or Path.cwd()
    cache_root = default_dependency_cache_root()
    try:
        if inspect_all:
            records = inspect_dependency_cache(cache_root)
            scope = "all"
        else:
            with compose_project(project_root) as composition:
                records = inspect_dependency_cache(
                    cache_root,
                    composition.dependencies,
                )
            scope = "project"
        if json_output:
            report = {
                "cacheRoot": str(cache_root.expanduser().resolve()),
                "resources": [_cache_record_json(record) for record in records],
                "schema": 1,
                "scope": scope,
            }
            print(
                json.dumps(
                    report,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        else:
            _print_cache_table(records)
    except (
        OSError,
        CompositionError,
        ProjectConfigError,
        RuntimeManifestError,
    ) as error:
        raise SystemExit(f"vividly cache status: {error}") from error


def cache_clear_command(arguments: argparse.Namespace) -> None:
    """Remove the complete dependency-cache root after explicit confirmation."""
    assume_yes = cast(bool, arguments.assume_yes)
    cache_root = default_dependency_cache_root().expanduser()
    try:
        if cache_root.is_symlink():
            raise DependencyAcquisitionError(
                f"dependency cache root is a symbolic link: {cache_root}"
            )
        if cache_root.exists() and not cache_root.is_dir():
            raise DependencyAcquisitionError(
                f"dependency cache root is not a directory: {cache_root}"
            )
        if not cache_root.exists():
            print(f"Dependency cache is already empty: {cache_root}")
            return
        if not assume_yes:
            try:
                answer = input(
                    f"Clear the complete Vividly dependency cache at {cache_root}? [y/N] "
                )
            except EOFError as error:
                raise DependencyAcquisitionError(
                    "confirmation input ended; rerun interactively or pass --yes"
                ) from error
            if answer.strip().lower() not in {"y", "yes"}:
                print("Dependency cache was not cleared.")
                return
        clear_dependency_cache(cache_root)
        print(f"Cleared dependency cache: {cache_root.resolve()}")
    except (OSError, DependencyAcquisitionError) as error:
        raise SystemExit(f"vividly cache clear: {error}") from error


def dependencies_command(arguments: argparse.Namespace) -> None:
    """Display the selected runtime and catalog dependency registry."""
    project_root = cast(Path, arguments.project_root)
    json_output = cast(bool, arguments.json_output)
    try:
        with compose_project(project_root) as composition:
            dependencies = list(composition.dependencies.values())
            if json_output:
                report = {
                    "dependencies": [_dependency_json(selection) for selection in dependencies],
                    "runtime": {
                        "source": composition.runtime.source,
                        "version": composition.runtime.manifest.version,
                    },
                    "schema": 1,
                }
                print(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                )
            else:
                _print_dependency_table(dependencies)
    except (
        OSError,
        CompositionError,
        ProjectConfigError,
        RuntimeManifestError,
    ) as error:
        raise SystemExit(f"vividly dependencies: {error}") from error


COMMANDS: tuple[tuple[str, str, CommandHandler], ...] = (
    ("provision", "Create a project or upgrade its package runtime", provision_command),
    ("run", "Serve a project locally", run_command),
    ("install-browser", "Install Chromium for thumbnail generation", install_browser_command),
    ("reference", "Materialize runtime reference documentation", reference_command),
    ("dependencies", "Display the effective dependency registry", dependencies_command),
    ("cache", "Inspect or clear the dependency cache", unimplemented_command),
    ("thumbnails", "Regenerate committed slide thumbnails", thumbnails_command),
    ("rehearse", "Run a user-driven cache-only rehearsal", rehearse_command),
    ("export", "Materialize a self-contained static site", export_command),
    ("publish", "Publish a project", publish_command),
)


def port_number(value: str) -> int:
    """Parse a valid TCP port number."""
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="vividly",
        description="Build, run, and publish Vividly projects.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=version_banner(),
        help="show the CLI version and the runtime version it installs",
    )
    subparsers = parser.add_subparsers(dest="command")

    for name, help_text, handler in COMMANDS:
        if name == "publish":
            command_parser = subparsers.add_parser(
                name,
                help=help_text,
                description=(
                    "Materialize and publish a complete site to a configured branch. "
                    "The entire containing Git repository must be clean."
                ),
                epilog=(
                    "Publishing uses an isolated temporary index: it does not switch "
                    "branches, create a worktree or local publication branch, or modify "
                    "the working tree or normal index. It uses an ordinary non-force "
                    "push. Success, dry-run, and unchanged results exit 0; validation, "
                    "Git, race, and push failures exit nonzero."
                ),
            )
        else:
            command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.set_defaults(handler=handler)
        if name == "provision":
            command_parser.add_argument(
            "project_root",
                type=Path,
                nargs="?",
                default=Path.cwd(),
                metavar="PATH",
                help="project root to create (default: current directory)",
            )
            command_parser.add_argument(
                "-y",
                "--yes",
                dest="assume_yes",
                action="store_true",
                help="skip the confirmation prompt",
            )
            command_parser.add_argument(
                "--upgrade",
                action="store_true",
                help="repin an existing package-runtime project to the installed runtime",
            )
        if name == "run":
            command_parser.add_argument(
                "project_root",
                type=Path,
                nargs="?",
                default=Path.cwd(),
                metavar="PATH",
                help="project root containing site/ (default: current directory)",
            )
            command_parser.add_argument(
                "--port",
                type=port_number,
                default=DEFAULT_PORT,
                help=f"port for the local server (default: {DEFAULT_PORT})",
            )
            command_parser.add_argument(
                "--no-watch",
                action="store_true",
                help="disable file watching and browser reload support",
            )
        if name == "reference":
            command_parser.add_argument(
                "project_root",
                type=Path,
                nargs="?",
                default=Path.cwd(),
                metavar="PATH",
                help="project root (default: current directory)",
            )
        if name == "dependencies":
            command_parser.add_argument(
                "project_root",
                type=Path,
                nargs="?",
                default=Path.cwd(),
                metavar="PATH",
                help="project root containing site/ (default: current directory)",
            )
            command_parser.add_argument(
                "--json",
                action="store_true",
                dest="json_output",
                help="write deterministic JSON for agents and tooling",
            )
        if name == "cache":
            cache_subparsers = command_parser.add_subparsers(
                dest="cache_action",
                required=True,
            )
            status_parser = cache_subparsers.add_parser(
                "status",
                help="inspect dependency-cache resources",
            )
            status_parser.set_defaults(handler=cache_status_command)
            status_parser.add_argument(
                "project_root",
                type=Path,
                nargs="?",
                default=None,
                metavar="PATH",
                help="project root containing site/ (default: current directory)",
            )
            status_parser.add_argument(
                "--all",
                action="store_true",
                dest="all_cache",
                help="inspect the complete global cache without loading a project",
            )
            status_parser.add_argument(
                "--json",
                action="store_true",
                dest="json_output",
                help="write deterministic JSON for agents and tooling",
            )
            clear_parser = cache_subparsers.add_parser(
                "clear",
                help="remove the complete dependency-cache root",
            )
            clear_parser.set_defaults(handler=cache_clear_command)
            clear_parser.add_argument(
                "--yes",
                action="store_true",
                dest="assume_yes",
                help="skip the confirmation prompt",
            )
        if name == "thumbnails":
            command_parser.add_argument(
                "project_root",
                type=Path,
                nargs="?",
                default=Path.cwd(),
                metavar="PATH",
                help="project root containing site/ (default: current directory)",
            )
            command_parser.add_argument(
                "--presentation",
                dest="presentation_id",
                metavar="ID",
                help="catalog presentation ID (default: all presentations)",
            )
            command_parser.add_argument(
                "--slide",
                action="append",
                dest="slides",
                metavar="ADDRESS",
                help="complete manifest address to capture (repeatable; default: all slides)",
            )
            command_parser.add_argument(
                "--missing",
                action="store_true",
                dest="missing_only",
                help="capture only slides with absent or incomplete thumbnail output",
            )
        if name == "rehearse":
            command_parser.add_argument(
                "project_root",
                type=Path,
                nargs="?",
                default=Path.cwd(),
                metavar="PATH",
                help="project root containing site/ (default: current directory)",
            )
        if name == "export":
            command_parser.add_argument(
                "project_root",
                type=Path,
                nargs="?",
                default=Path.cwd(),
                metavar="PATH",
                help="project root containing site/ (default: current directory)",
            )
            command_parser.add_argument(
                "--output",
                type=Path,
                required=True,
                metavar="DESTINATION",
                help="absent or empty destination directory outside the project",
            )
        if name == "publish":
            command_parser.add_argument(
                "project_root",
                type=Path,
                nargs="?",
                default=Path.cwd(),
                metavar="PATH",
                help="project root containing site/ (default: current directory)",
            )
            command_parser.add_argument(
                "--target",
                dest="target_name",
                metavar="TARGET",
                help="configured publication target (default: configured default or sole target)",
            )
            command_parser.add_argument(
                "--dry-run",
                action="store_true",
                help="validate and materialize without creating publication Git objects or refs",
            )

    return parser


def main() -> None:
    """Run the Vividly command-line interface."""
    parser = create_parser()
    arguments = parser.parse_args()
    if arguments.command is None:
        parser.print_help()
        return
    handler = cast(CommandHandler, arguments.handler)
    handler(arguments)


if __name__ == "__main__":
    main()
