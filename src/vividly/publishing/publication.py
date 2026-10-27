"""Local materialization and Git publication orchestration."""

import hashlib
import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Literal, cast

from ..composition import Composition, CompositionError, compose_project
from ..export import ExportError, export_composition
from ..project import ProjectConfigError, load_project_config
from ..runtime import RuntimeManifestError
from .config import (
    GitHubPagesTarget,
    PublishingConfigError,
    load_publishing_config,
    resolve_target,
)
from .git import (
    GitRepository,
    PublicationGitError,
    candidate_entries,
    commit_message,
    commit_parents,
    commit_tree_id,
    create_commit,
    fetch_remote_tip,
    inspect_repository,
    push_commit,
    show_file,
    tree_entries,
    tree_entry,
    validate_target,
    write_tree,
)

_INTEGRITY = re.compile(r"sha256:[0-9a-f]{64}")
_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_RESERVED_PATHS = (
    PurePosixPath("/.nojekyll"),
    PurePosixPath("/CNAME"),
    PurePosixPath("/vividly-publication.json"),
)
_TRAILER_NAMES = (
    "Vividly-Publication",
    "Source-Revision",
    "Vividly-Distribution",
    "Framework-Version",
    "Runtime-Integrity",
    "Target",
    "Provider",
)

type PublicationOperation = Literal[
    "dry-run-initial",
    "dry-run-changed",
    "dry-run-unchanged",
    "published",
    "unchanged",
]


class PublicationError(RuntimeError):
    """A project cannot be published safely."""


@dataclass(frozen=True)
class PublicationIdentity:
    """Deterministic public tool and runtime identity."""

    distribution_version: str
    framework_version: str
    runtime_integrity: str


@dataclass(frozen=True)
class PublicationPlan:
    """Resolved operation details reported before publication writes."""

    project_root: Path
    source_commit: str
    target: str
    remote: str
    branch: str
    expected_url: str | None
    custom_domain: str | None


@dataclass(frozen=True)
class PublicationResult:
    """Outcome of one publication or dry run."""

    plan: PublicationPlan
    operation: PublicationOperation
    identity: PublicationIdentity
    publication_commit: str | None


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()


def _runtime_paths(composition: Composition) -> tuple[PurePosixPath, ...]:
    return tuple(
        url_path
        for url_path, composed in sorted(composition.files.items())
        if composed.owner == "runtime"
    )


def _runtime_integrity(candidate: Path, paths: tuple[PurePosixPath, ...]) -> str:
    files: dict[str, str] = {}
    for url_path in paths:
        candidate_path = candidate.joinpath(*url_path.parts[1:])
        files[str(url_path)] = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    content = _canonical_json({"files": files, "schema": 1})
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _metadata(identity: PublicationIdentity) -> bytes:
    return _canonical_json(
        {
            "runtime": {
                "framework_version": identity.framework_version,
                "integrity": identity.runtime_integrity,
            },
            "schema": 1,
            "vividly": {"distribution_version": identity.distribution_version},
        }
    )


def _reject_publication_collisions(composition: Composition) -> None:
    for path in _RESERVED_PATHS:
        author_path = composition.author_root.joinpath(*path.parts[1:])
        if path in composition.files or author_path.exists() or author_path.is_symlink():
            raise PublicationError(f"author content occupies publication-owned path: {path}")


def _add_publication_files(
    candidate: Path,
    target: GitHubPagesTarget,
    identity: PublicationIdentity,
) -> None:
    (candidate / ".nojekyll").write_bytes(b"")
    if target.custom_domain is not None:
        (candidate / "CNAME").write_text(f"{target.custom_domain}\n", encoding="ascii")
    (candidate / "vividly-publication.json").write_bytes(_metadata(identity))


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PublicationError(f"publication metadata contains duplicate key {key!r}")
        result[key] = value
    return result


def _parse_metadata(content: bytes) -> PublicationIdentity:
    try:
        text = content.decode("utf-8")
        loaded = cast(object, json.loads(text, object_pairs_hook=_object_pairs))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PublicationError(f"publication metadata is invalid: {error}") from error
    if not isinstance(loaded, dict):
        raise PublicationError("publication metadata has an invalid top-level shape")
    document = cast(dict[object, object], loaded)
    if set(document) != {"runtime", "schema", "vividly"}:
        raise PublicationError("publication metadata has an invalid top-level shape")
    if document["schema"] != 1:
        raise PublicationError("publication metadata has an unsupported schema")
    runtime_value = document["runtime"]
    vividly_value = document["vividly"]
    if not isinstance(runtime_value, dict):
        raise PublicationError("publication metadata has an invalid runtime shape")
    runtime = cast(dict[object, object], runtime_value)
    if set(runtime) != {"framework_version", "integrity"}:
        raise PublicationError("publication metadata has an invalid runtime shape")
    if not isinstance(vividly_value, dict):
        raise PublicationError("publication metadata has an invalid vividly shape")
    vividly = cast(dict[object, object], vividly_value)
    if set(vividly) != {"distribution_version"}:
        raise PublicationError("publication metadata has an invalid vividly shape")
    framework = runtime["framework_version"]
    integrity = runtime["integrity"]
    distribution = vividly["distribution_version"]
    if not isinstance(framework, str) or not framework:
        raise PublicationError("publication metadata framework version is invalid")
    if not isinstance(distribution, str) or not distribution:
        raise PublicationError("publication metadata distribution version is invalid")
    if not isinstance(integrity, str) or _INTEGRITY.fullmatch(integrity) is None:
        raise PublicationError("publication metadata runtime integrity is invalid")
    identity = PublicationIdentity(
        distribution_version=distribution,
        framework_version=framework,
        runtime_integrity=integrity,
    )
    if content != _metadata(identity):
        raise PublicationError("publication metadata bytes are not canonical")
    return identity


def _parse_message(message: str) -> tuple[str, dict[str, str]]:
    lines = message.rstrip("\n").splitlines()
    if len(lines) != 9 or lines[1] != "":
        raise PublicationError("publication commit message has an invalid shape")
    trailers: dict[str, str] = {}
    for expected, line in zip(_TRAILER_NAMES, lines[2:], strict=True):
        prefix = f"{expected}: "
        if not line.startswith(prefix):
            raise PublicationError(f"publication commit is missing `{expected}` trailer")
        value = line[len(prefix) :]
        if not value or "\n" in value or "\r" in value:
            raise PublicationError(f"publication commit has invalid `{expected}` trailer")
        trailers[expected] = value
    return lines[0], trailers


def _recognize_tip(
    repository: GitRepository,
    commit: str,
    target: GitHubPagesTarget,
) -> None:
    parents = commit_parents(repository, commit)
    if len(parents) > 1:
        raise PublicationError(f"publication branch tip is a merge commit: {commit}")
    metadata_entry = tree_entry(repository, commit, "vividly-publication.json")
    if metadata_entry is None or metadata_entry.mode != "100644":
        raise PublicationError(
            f"publication branch tip is not recognized as Vividly history: {commit}"
        )
    identity = _parse_metadata(show_file(repository, commit, "vividly-publication.json"))
    subject, trailers = _parse_message(commit_message(repository, commit))
    source_revision = trailers["Source-Revision"]
    if _OBJECT_ID.fullmatch(source_revision) is None:
        raise PublicationError("publication commit source revision is invalid")
    if subject != f"Publish site from source revision {source_revision[:12]}":
        raise PublicationError("publication commit subject does not match its source revision")
    expected = {
        "Vividly-Publication": "1",
        "Vividly-Distribution": identity.distribution_version,
        "Framework-Version": identity.framework_version,
        "Runtime-Integrity": identity.runtime_integrity,
        "Target": target.name,
        "Provider": target.provider,
    }
    for name, value in expected.items():
        if trailers[name] != value:
            raise PublicationError(f"publication commit `{name}` trailer does not match")


def _commit_message(
    source_commit: str,
    identity: PublicationIdentity,
    target: GitHubPagesTarget,
) -> str:
    return (
        f"Publish site from source revision {source_commit[:12]}\n\n"
        "Vividly-Publication: 1\n"
        f"Source-Revision: {source_commit}\n"
        f"Vividly-Distribution: {identity.distribution_version}\n"
        f"Framework-Version: {identity.framework_version}\n"
        f"Runtime-Integrity: {identity.runtime_integrity}\n"
        f"Target: {target.name}\n"
        f"Provider: {target.provider}\n"
    )


def _assert_source_unchanged(original: GitRepository, project_root: Path) -> None:
    current = inspect_repository(project_root)
    if (
        current.root != original.root
        or current.source_branch != original.source_branch
        or current.source_commit != original.source_commit
    ):
        raise PublicationError("source branch or commit changed during publication")


def _publish(
    project_root: Path,
    *,
    target_name: str | None,
    dry_run: bool,
    on_plan: Callable[[PublicationPlan], None] | None,
) -> PublicationResult:
    canonical_project = project_root.expanduser().resolve()
    load_project_config(canonical_project)
    config = load_publishing_config(canonical_project)
    target = resolve_target(config, target_name)
    repository = inspect_repository(canonical_project)
    validate_target(repository, target.remote, target.branch)
    previous = fetch_remote_tip(repository, target.remote, target.branch)
    if previous is not None:
        _recognize_tip(repository, previous, target)
    plan = PublicationPlan(
        project_root=canonical_project,
        source_commit=repository.source_commit,
        target=target.name,
        remote=target.remote,
        branch=target.branch,
        expected_url=target.expected_url,
        custom_domain=target.custom_domain,
    )
    if on_plan is not None:
        on_plan(plan)

    with tempfile.TemporaryDirectory(prefix="vividly-publish-") as temporary:
        temporary_root = Path(temporary)
        candidate = temporary_root / "candidate"
        index = temporary_root / "publication.idx"
        with compose_project(canonical_project, verify_package_contents=True) as composition:
            _reject_publication_collisions(composition)
            runtime_paths = _runtime_paths(composition)
            framework_version = composition.runtime.manifest.version
            export_composition(composition, candidate)
        identity = PublicationIdentity(
            distribution_version=version("vividly"),
            framework_version=framework_version,
            runtime_integrity=_runtime_integrity(candidate, runtime_paths),
        )
        _add_publication_files(candidate, target, identity)
        _assert_source_unchanged(repository, canonical_project)

        if dry_run:
            entries = candidate_entries(repository, candidate)
            if previous is None:
                operation: PublicationOperation = "dry-run-initial"
            elif entries == tree_entries(repository, previous):
                operation = "dry-run-unchanged"
            else:
                operation = "dry-run-changed"
            return PublicationResult(
                plan=plan,
                operation=operation,
                identity=identity,
                publication_commit=previous if operation == "dry-run-unchanged" else None,
            )

        tree = write_tree(repository, candidate, index)
        if previous is not None and tree == commit_tree_id(repository, previous):
            return PublicationResult(
                plan=plan,
                operation="unchanged",
                identity=identity,
                publication_commit=previous,
            )
        commit = create_commit(
            repository,
            tree,
            _commit_message(repository.source_commit, identity, target),
            previous,
        )
        push_commit(repository, target.remote, target.branch, commit)
        return PublicationResult(
            plan=plan,
            operation="published",
            identity=identity,
            publication_commit=commit,
        )


def publish_project(
    project_root: Path,
    *,
    target_name: str | None = None,
    dry_run: bool = False,
    on_plan: Callable[[PublicationPlan], None] | None = None,
) -> PublicationResult:
    """Validate, materialize, and optionally publish one complete site."""
    try:
        return _publish(
            project_root,
            target_name=target_name,
            dry_run=dry_run,
            on_plan=on_plan,
        )
    except PublicationError:
        raise
    except (
        OSError,
        CompositionError,
        ExportError,
        ProjectConfigError,
        PublishingConfigError,
        PublicationGitError,
        RuntimeManifestError,
    ) as error:
        raise PublicationError(str(error)) from error
