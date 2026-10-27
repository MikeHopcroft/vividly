# Runtime Composition Spec

Status: specified

## 1. Purpose

This specification defines how a Vividly project selects a runtime and how Vividly
combines that runtime with author-owned presentation sources. The composition is one
logical static site used by development serving, thumbnail generation, export, and
publishing.

The contract separates:

- the committed project configuration;
- the author-owned `site/` tree;
- the selected Vividly runtime source; and
- any physically assembled export.

This document is the normative runtime-composition contract.

## 2. Project configuration

The project root contains one committed `vividly.yaml` file. It is both the desired
configuration and the exact runtime-selection record. The initial design has no
separate lock file because it performs no remote dependency resolution.

`vividly.yaml` is UTF-8 YAML. Its top-level mapping contains:

- `schema`, the project-file schema version; and
- `runtime`, the selected runtime description.

The initial schema version is the integer `1`. Unknown schema versions are unsupported.
Unknown keys are errors so misspellings and configuration from a newer Vividly version
cannot silently change behavior.

Every runtime description contains:

- `source`, exactly one of `package`, `repository`, or `path`; and
- the source-specific identity fields defined below.

Vividly validates the complete file before resolving or serving either source tree.
Missing, duplicated, unknown, or incorrectly typed fields are errors. Configuration
errors identify the field and do not modify the project.

## 3. Runtime source modes

### 3.1 Package

`source: package` selects runtime resources from the installed Vividly Python package.
The runtime description records:

- `distribution_version`, the exact `vividly` Python distribution version expected to
  carry the runtime;
- `version`, the exact framework version required by the project; and
- `integrity`, the expected SHA-256 identity of that runtime release.

The installed package is usable only when its distribution version matches
`distribution_version` and its framework version and manifest identity match `version`
and `integrity`. Vividly never substitutes a different installed framework version,
including a newer compatible-looking version.

Example shape:

~~~yaml
schema: 1
runtime:
  source: package
  distribution_version: 0.0.r1
  version: 0.0.r1
  integrity: sha256:<runtime-manifest-digest>
~~~

### 3.2 Repository

`source: repository` selects an editable runtime source in the Vividly repository. The
runtime description records:

- `path`, the runtime root relative to the project root;
- `version`, the framework version from which the editable source derives; and
- `commit`, the Vividly repository commit that provides its provenance.

The version and commit describe provenance. They do not require the working tree to be
clean or byte-for-byte identical to that commit. Local runtime edits are intentional in
this mode and must be visible through the development composition.

Example shape:

~~~yaml
schema: 1
runtime:
  source: repository
  path: <project-relative-runtime-root>
  version: 0.0.r1
  commit: <full-vividly-commit-id>
~~~

### 3.3 Path

`source: path` selects an explicitly ejected, author-owned runtime source. The runtime
description records:

- `path`, the runtime root relative to the project root;
- `upstream_version`, the exact framework version from which the runtime was derived;
  and
- `upstream_commit`, the corresponding Vividly repository commit when known.

`upstream_commit` may be omitted only when no commit identity is available. The
upstream fields are provenance, not an integrity constraint. Vividly does not overwrite
the selected tree and allows it to diverge from its upstream identity.

Example shape:

~~~yaml
schema: 1
runtime:
  source: path
  path: <project-relative-ejected-runtime-root>
  upstream_version: 0.0.r1
  upstream_commit: <full-vividly-commit-id>
~~~

Remote runtime acquisition and historical runtime caches are outside the initial
contract.

## 4. Local runtime paths

The `path` value in `repository` and `path` modes is a normalized, project-relative
filesystem path. Absolute paths and paths that escape the project root are invalid.

Vividly resolves the configured path against the canonical project root. The runtime
root and every file selected from it must remain beneath that root after resolving
paths.

The selected runtime root must be distinct from the author-owned `site/` tree. Neither
tree may contain the other. These constraints keep committed configuration portable,
prevent accidental exposure of adjacent files, and prevent one physical file from
acquiring both runtime and author ownership.

Symbolic links are unsupported in both the author and runtime source trees. A symbolic
link at any traversed file or directory is an error, regardless of where it resolves.
Export therefore never preserves or dereferences a source symlink.

## 5. Runtime manifest and integrity

Every runtime root contains `vividly-runtime.json`. It is UTF-8 JSON with:

- `schema`, the runtime-manifest schema version;
- `version`, the exact framework version;
- `composition_api`, the integer composition API version; and
- `files`, an object mapping every deployed path without its leading `/` to the
  corresponding lowercase hexadecimal SHA-256 digest; and
- `reference_files`, an object mapping every path relative to the runtime's
  non-deployed `reference/` directory to its lowercase hexadecimal SHA-256 digest.

The initial manifest schema version is `1`. File keys use normalized `/` separators,
are sorted lexicographically in the serialized manifest, and cannot be absolute,
empty, parent-relative, or duplicate after normalization. The file set includes the
shell and every resource that composition maps below `/vividly/`. Reference keys obey
the same normalization rules and identify only regular files below `reference/`.

Each `files` key identifies both a physical file relative to the runtime root and its
deployed path after adding a leading `/`. The required shell key is `index.html`; every
other initial key begins with `vividly/`. `vividly-runtime.json` and `reference/` are
runtime metadata rather than deployed content and therefore cannot appear in `files`.

Canonical manifest bytes are UTF-8 JSON with object keys sorted lexicographically,
no insignificant whitespace, and one trailing line feed. The runtime identity is:

~~~text
sha256:<lowercase SHA-256 of the canonical manifest bytes>
~~~

Package mode always requires the configured `integrity` to match that identity. Every
composition consumer verifies that the selected package runtime resources have exactly
the manifest's deployed file set, but routine development commands do not hash each
file. Missing or additional deployed files are integrity errors.

Export and publish additionally hash every selected package runtime file and compare it
with the manifest's per-file digest before creating a distributable artifact. A changed
file is then an integrity error. Full content verification happens once per export or
publish operation, not once per HTTP request.

Reference materialization verifies the package reference file set and every
`reference_files` digest before copying it. Reference files are part of the aggregate
runtime identity but never enter the deployed URL map or an export.

Every runtime also deploys `/vividly/dependencies.json`, the schema-versioned built-in
dependency table specified by
[`dependency-resolution.md`](dependency-resolution.md). The table is an ordinary
runtime-owned deployed file covered by the manifest file set and digest. It records
auditable version, source, integrity, loader, and license-identifier metadata. The
selected third-party payload bytes and upstream license texts are not runtime source
files and do not appear in the runtime manifest.

Repository and path modes validate the manifest schema, framework version, composition
API, and safe file keys. They do not enforce the manifest's file set or content hashes
against the editable tree. This permits intentional local changes while retaining exact
upstream provenance.

In repository mode, the configured `version` must equal the manifest's `version`. In
path mode, `upstream_version` must equal the manifest's `version`. The configured commit
fields remain provenance and are not compared with working-tree contents.

## 6. Runtime compatibility

Every runtime source's manifest declares:

- its exact framework version;
- an integer composition API version; and
- the integrity metadata needed by package mode.

The CLI supports an explicit set of composition API versions. All source modes fail
when the selected runtime declares an unsupported API version.

Package mode additionally requires the configured framework version and integrity to
match the packaged runtime manifest exactly. Its file set must match for every command;
per-file content hashes are enforced for export and publish. Repository and path modes
allow content changes but still require a valid manifest and supported composition API
version.

The tool version and framework version remain distinct identities.

## 7. Package-resource lifetime and availability

Package mode locates its runtime through Python's `importlib.resources` APIs. It does
not assume a virtual-environment layout, a source checkout, or an ordinary filesystem
path inside `site-packages`.

When resources require extraction, Vividly enters one `importlib.resources.as_file()`
context for the complete runtime tree and holds it for the enclosing command's
lifetime. For `run`, that lifetime ends during server shutdown. For one-shot commands
such as thumbnails and export, it ends after the operation either succeeds or reports
failure. Vividly never retains a path returned by that context after closing it.

The initial composition design uses `.vividly/` only for disposable, generated
project-support state such as the materialized reference described below. It does not
cache runtime files there. Repository and path modes read their selected source trees
directly. Export uses temporary assembly storage governed by the export contract.

Package resolution performs no network access. When the installed distribution version,
framework version, manifest identity, or composition API does not satisfy
`vividly.yaml`, Vividly fails before serving or materializing files. The diagnostic
reports:

- the required and available distribution and framework identities;
- the first integrity or compatibility mismatch, when applicable;
- an exact command of the form
  `python -m pip install 'vividly==<distribution_version>'`; and
- that installation requires package access and must be performed separately if the
  environment is offline.

Failure does not rewrite `vividly.yaml`, substitute the installed runtime, or create
derived state.

`run` and thumbnail generation do not rehash package runtime contents during startup.
They validate the manifest identity, compatibility, safe declared paths, and actual
file set. A future explicit verification command may expose the same full per-file
check required by export and publish without creating an artifact.

## 8. Local reference materialization

`vividly reference` materializes version-matched reference Markdown from the selected
runtime's `reference/` source into `.vividly/reference/`. The output is derived,
disposable, excluded from composition and export, and must be ignored by source
control.

The command validates `vividly.yaml`, resolves the selected runtime, and stages the
complete reference tree before replacing the previous generated tree. In package mode
it verifies the reference file set and every manifest digest. In repository and path
modes it copies the current editable reference files without enforcing content hashes.
All modes reject symbolic links and unsafe paths.

`.vividly/reference/runtime.json` records the selected source mode, framework version,
manifest identity, repository or upstream commit when applicable, and a deterministic
digest of the materialized reference paths and bytes, excluding `runtime.json` itself.
`vividly reference` recomputes the selected source's reference digest and replaces the
output only when it differs. Package-mode identity changes can therefore be detected
from `vividly.yaml`; editable source changes are detected when the command re-examines
that source. Agents must not treat `.vividly/` as source or edit it as the canonical
reference.

The command performs no network access. A fresh clone may omit `.vividly/`; seeded
agent instructions direct an agent to run `vividly reference` before relying on local
reference content.

## 9. Deployed URL ownership

The selected runtime owns:

- `/index.html`, the application shell; and
- every path below `/vividly/`, the runtime resource namespace.

During `vividly run`, `/vividly/~dev/events` is a development-only server-sent events
endpoint. A runtime manifest cannot declare `/vividly/~dev` or a descendant. No
development-only path exists in an exported composition.

The author-owned `site/` tree supplies every other deployed path. In particular,
`/catalog.yaml`, `/presentations/**`, `/slides/**`, and `/thumbnails/**` are
author-owned unless a later specification reserves a narrower concrete path.

An author file, directory, or symbolic link that occupies `/index.html`, `/vividly`, or
any path below `/vividly/` is a collision. A collision is an error; neither source takes
precedence. The same validation applies to development, thumbnails, export, and
publishing.

The runtime source stores its shell and resources in a runtime-owned physical tree. Its
internal source layout is not part of the author project contract. Composition maps
that tree to the runtime-owned deployed paths.

## 10. Development and export equivalence

Development serving, thumbnail generation, export, and publishing consume one
composition result. For a given validated project and selected source trees, they use
the same:

- deployed URL set and ownership;
- validated runtime and catalog dependency tables;
- dependency-key collision result;
- URL normalization and filesystem resolution;
- deployed-path collision result;
- MIME-type selection; and
- source bytes.

`vividly run` has three development-only differences:

1. it injects the live-reload client into the `/index.html` response; and
2. it injects the local dependency capability into `/index.html`; and
3. it adds `Cache-Control: no-store` to every response.

Injection is a response transformation, not a source-file edit. No reload client, local
dependency capability, development endpoint, or development cache header is written
into an export. Thumbnail generation uses the same local connected dependency
capability without the reload client. Rehearsal uses the capability in cache-only mode.
Other than transformed `/index.html` responses, successful composition-file responses
preserve the selected source bytes.

## 11. Export semantics

Export first validates the complete composition, including all source paths, manifest
requirements, ownership collisions, and package-mode per-file hashes. It then copies
the composition into a sibling temporary directory on the destination filesystem and
renames that directory to the requested destination only after assembly succeeds.

The initial export contract requires the destination to be absent or an empty
directory. A non-empty destination is an error. Export does not delete or replace
unknown content and has no implicit force behavior.

When an empty destination directory already exists, export stages and validates the
complete artifact first, confirms immediately before installation that the destination
is still empty, removes that empty directory, and renames the staged directory into its
place. If the destination changes or cannot be replaced safely, export fails rather
than merging output into it.

The author source, runtime source, and project root cannot be inside the export
destination. The destination cannot be inside either source tree. These overlap checks
use canonical paths and occur before writing.

An export contains each composed deployed path exactly once and no development-only
state. Repeated exports from byte-identical source trees and configuration produce the
same file paths and bytes. Filesystem timestamps, ownership, and platform permission
bits are not part of the static-site identity.

An export contains the runtime dependency table but contains no dependency cache,
selected third-party payload bytes, or upstream license copies. Runtime and catalog
dependencies resolve to their pinned CDN URLs. An export is a complete static-site
artifact, but it requires network access for exercised dependency resources and is not
a portable offline artifact.

Publishing consumes a successfully assembled export or invokes this same export
primitive in temporary storage. It does not implement an independent overlay.

## 12. Composition validation

Every composition consumer validates in this order:

1. locate `vividly.yaml`, applying the unsupported legacy-marker diagnostic when it is
   absent;
2. parse and validate `vividly.yaml`;
3. resolve and validate the author and selected runtime roots;
4. load and validate the runtime manifest and compatibility;
5. load and validate the runtime-owned dependency table;
6. load and validate the catalog and its dependency table;
7. reject duplicate keys across the runtime and catalog tables;
8. enumerate both source trees, rejecting unsafe paths and symbolic links;
9. map source files to deployed paths and reject ownership collisions;
10. for package-mode export or publish, verify every runtime file's content hash; and
11. perform the requested serve, thumbnail, export, or publish operation.

Validation reports the earliest phase that fails and may report multiple errors within
that phase. A consumer does not start listening, launch a browser, write thumbnails,
create an export destination, or publish when composition validation fails.

## 13. Unsupported baseline projects

A project containing `vividly-baseline.json` uses the superseded managed-file layout.
When `vividly.yaml` is absent, every project-consuming command checks for that legacy
marker before reporting an ordinary missing-configuration error. If found, the command
states that the layout is unsupported, automatic migration is unavailable, and the
project must be reprovisioned.

This compatibility behavior is a read-only existence check, not support for the old
format. Vividly never parses the baseline, derives ownership from it, infers a new
`vividly.yaml`, merges the old `site/vividly/` tree, or attempts migration. A baseline
file beside a valid `vividly.yaml` has no special meaning.

The repository's own projects, package resources, examples, and tests will be converted
as implementation work. This pre-alpha conversion is not a general migration facility.
