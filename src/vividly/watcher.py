"""Filesystem watching for validated development compositions."""

import threading
from collections.abc import Callable

from watchfiles import watch

from .composition import CompositionError
from .project import ProjectConfigError
from .runtime import RuntimeManifestError
from .server import CompositionSession, ReloadBroker

WATCH_DEBOUNCE_MS = 200
WATCH_STEP_MS = 50
WATCH_STOP_POLL_MS = 250


class WatcherError(RuntimeError):
    """The filesystem watcher could not continue."""


def watch_for_reloads(
    compositions: CompositionSession,
    reload_broker: ReloadBroker,
    stop_event: threading.Event,
    report_validation_error: Callable[[str], None],
) -> None:
    """Revalidate changed sources and notify clients only after success."""
    try:
        changes = watch(
            *compositions.watch_roots(),
            debounce=WATCH_DEBOUNCE_MS,
            step=WATCH_STEP_MS,
            stop_event=stop_event,
            rust_timeout=WATCH_STOP_POLL_MS,
        )
        for _ in changes:
            try:
                compositions.refresh()
            except (
                OSError,
                CompositionError,
                ProjectConfigError,
                RuntimeManifestError,
            ) as error:
                report_validation_error(str(error))
                continue
            reload_broker.notify_reload()
    except OSError as error:
        raise WatcherError(str(error)) from error
