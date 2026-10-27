# CLI Spec

Status: draft. Covers the `vividly` command-line tool, the author-owned project layout
it creates, exact runtime selection, composed development serving, thumbnail generation,
static export, and the publishing command surface.

Runtime selection, URL ownership, integrity, and composition validation are normative in
[`runtime-composition.md`](runtime-composition.md). This document defines how commands
expose that contract. Publication configuration, Git history, safety, and GitHub Pages
behavior are normative in [`publishing.md`](publishing.md).

## 1. Principles

- **The author owns project files.** Files created under `site/` and `.github/` are
  seeds that become author-owned immediately.
- **The runtime remains external to author source.** Normal projects use matching
  resources from the installed Vividly package. Provision does not copy managed
  framework files into `site/`.
- **Selection is exact.** A project either resolves the runtime recorded in
  `vividly.yaml` or fails with an actionable diagnostic. It never silently substitutes
  the runtime carried by the current tool.
- **Composition is shared.** Run, rehearsal, thumbnails, export, and publishing use the same
  validated URL-to-source mapping.
- **Destructive behavior is explicit.** Commands do not overwrite unknown author files
  or non-empty export destinations.

## 2. Commands

| command | purpose |
| --- | --- |
| `provision` | Create a new project and select the installed package runtime |
| `run` | Serve the composed project for authoring with optional live reload |
| `install-browser` | Install Vividly's managed Chromium browser |
| `reference` | Materialize version-matched reference Markdown for local agents |
| `dependencies` | Display the effective runtime and catalog dependency registry |
| `cache status` | Inspect project-relevant or global dependency-cache resources |
| `cache clear` | Explicitly remove the complete dependency-cache root |
| `thumbnails` | Regenerate committed author-presentation thumbnails |
| `rehearse` | Run a user-driven cache-only rehearsal |
| `export` | Materialize the composed site as a static artifact |
| `publish` | Materialize and publish a complete site to a configured target |

Invoking `vividly` with no command prints help and exits 0. Command failures print an
actionable message to stderr and exit 1 without a traceback.

`provision`, `run`, `reference`, `dependencies`, `cache status`, `thumbnails`,
`rehearse`, `export`, and `publish`
take an optional `PATH` positional naming the project root, defaulting to the current
directory. Commands that consume a project require `PATH/vividly.yaml`; composition
commands additionally require `PATH/site/catalog.yaml`.

Before reporting a missing `vividly.yaml`, every project-consuming command checks for
`PATH/vividly-baseline.json`. When the configuration is absent and that legacy marker
exists, the command reports the unsupported pre-composition layout and requires
reprovisioning. This is an existence check only: no command parses the baseline,
derives ownership from it, or attempts migration.

`vividly --version` reports the installed Python distribution, the framework runtime it
carries, and its composition API version.

## 3. Project layout and ownership

The first `provision` creates:

~~~text
my-project/
├── vividly.yaml
├── .gitignore             # contains .vividly/ when Vividly creates it
├── .github/
│   ├── copilot-instructions.md
│   ├── instructions/
│   │   └── vividly.instructions.md
│   └── skills/
│       └── vividly-presentations/
│           └── SKILL.md
└── site/
    ├── catalog.yaml
    ├── presentations/
    │   └── vividly.yaml
    ├── slides/
    │   └── <slide-id>/
    │       ├── slide.html
    │       ├── slide.css
    │       ├── slide.js
    │       └── assets/
    └── thumbnails/           # created by vividly thumbnails
        └── index.json
~~~

`site/` is author source, not a complete deployment artifact. It intentionally lacks
the runtime-owned `/index.html` shell and `/vividly/**` resources. Those paths appear
only in the logical composition and in a materialized export.

`site/catalog.yaml` is the one known author-owned presentation entry point.
`site/presentations/`, `site/slides/`, and `site/thumbnails/` are conventions used by
the starter and CLI; catalog and manifest references remain authoritative.

Every file under `site/` and `.github/` becomes author-owned when created. A
Vividly-created `.gitignore` is likewise an author-owned seed. Provision does not retain
per-file ownership, hashes, or merge ancestors and never updates those files later.
`vividly.yaml` is author-controlled project configuration: provision creates it,
authors may deliberately change runtime modes, and commands treat it as read-only
except for the explicit `vividly provision --upgrade` package-runtime transition.

The author tree may not contain `site/index.html`, `site/vividly`, or symbolic links.
The runtime-composition specification defines the resulting collision and path errors.

## 4. `vividly provision`

Provision creates a new project from the installed package's starter seeds and selects
the exact runtime carried by that package. Ordinary provision is not an update or
reconciliation command. `vividly provision --upgrade` explicitly repins an existing
package-runtime project to the exact runtime in the installed package.

### 4.1 Mode and legacy projects

Provision classifies the destination before any other project validation:

1. If `vividly.yaml` exists, ordinary provision refuses because the project is already
   provisioned. It does not refresh seeds or change runtime selection.
2. Otherwise, if `vividly-baseline.json` exists, refuse the unsupported
   pre-composition layout. The diagnostic says that automatic migration is unavailable,
   that nothing was written, and that the project must be reprovisioned.
3. Otherwise, perform new-project preflight.

A malformed `vividly.yaml` is still an existing project and is not replaced. Other
commands report its validation error. A baseline beside an existing `vividly.yaml` has
no meaning to Vividly and does not reactivate legacy behavior.

### 4.2 Existing-project package-runtime upgrade

`vividly provision --upgrade [PATH]` requires an existing valid `vividly.yaml` whose
runtime source is `package`. It fully verifies the installed package runtime before
changing anything. Repository and path runtime selections are author-managed and are
rejected without modification.

When the installed distribution, framework, or manifest identity differs from the
selected package runtime, the command:

1. displays the old and new distribution, framework, and integrity identities;
2. states that only `vividly.yaml` will change;
3. asks for confirmation unless `--yes` is supplied; and
4. atomically rewrites `vividly.yaml` with the installed package runtime selection.

The command never refreshes starter seeds or modifies `site/`, `.github/`,
`.gitignore`, thumbnails, or derived state. Declining writes nothing. An already-current
selection is a successful no-op and does not prompt. A missing or malformed
configuration, unavailable or invalid package runtime, or non-package runtime source
fails without writing.

### 4.3 New-project preflight

Checked in order, each failure exits 1 without writing:

1. `PATH` exists and is not a directory.
2. A path that provision would create, other than `.gitignore`, is already occupied.
3. The installed package runtime manifest is missing, malformed, incompatible with the
   tool, or fails full file-set and content-integrity verification.

Existing real directories may be shared with the starter project. An existing file,
directory of the wrong type, or symbolic link at a seed path is a collision, including
at intermediate components. An existing file is a collision even when its bytes match
the seed because Vividly has no ownership claim over it.

Provision examines only known seed paths and required ancestors rather than recursively
traversing unrelated directories such as `.git/`, `.venv/`, or `node_modules/`.

An existing regular `.gitignore` is not a collision and is never edited. When it
exists, provision reports the exact recommended `.vividly/` rule for the author to add.
Any non-file or symbolic-link entry at `.gitignore` remains a collision.

### 4.4 Confirmation and creation

Before writing, provision prints:

- the canonical destination;
- the top-level entries it will add;
- the installed distribution version;
- the selected framework version and manifest identity; and
- whether the destination already contains unrelated top-level entries.

Existing entries are listed up to ten followed by a remainder count. `.git/` is
described as an existing Git repository but receives no other special treatment.

Provision prompts for approval. Declining or closed stdin writes nothing. `--yes`
skips the prompt but never skips validation or the printed plan.

On approval, provision stages the complete seed payload in temporary storage, then
creates the validated absent paths. It writes `vividly.yaml` with `source: package` and
the installed distribution version, framework version, and runtime-manifest identity.
An error cannot leave a `vividly.yaml` that falsely identifies a complete project.

When `.gitignore` is absent, provision creates it with:

```gitignore
.vividly/
```

Provision never creates `.vividly/`, copies runtime files into `site/`, or records a
baseline. The generated starter contains no `site/index.html` or `site/vividly/`.

## 5. Runtime and tool versions

Vividly distinguishes:

- **Distribution version** — the version of the installed `vividly` Python package.
- **Framework version** — the version declared by the selected runtime manifest.
- **Composition API version** — the integer contract version shared by the CLI and
  runtime composition implementation.

The versions may evolve independently. Agent instructions and starter files are package
seeds, not managed runtime files, and are not updated merely because the selected
framework changes.

A normal provisioned project records the exact distribution and framework identity for
package mode. Repository and path modes record editable-source provenance as specified
by the runtime-composition contract.

`vividly --version` takes no project context:

```console
$ vividly --version
vividly 0.3.0 (framework 0.4.0; composition API 1)
```

`vividly version [PATH]` is reserved for a future project-aware identity query. It is
not an alias for `--version`.

Remote runtime acquisition, historical runtime caches, and runtime-version solving are
not supported. A package mismatch reports the exact required distribution version and
an installation command, but no project command performs network access or edits the
active Python environment.

## 6. `vividly run`

```console
vividly run [PATH] [--port PORT] [--no-watch]
```

Run validates the complete composition and serves it over HTTP on `--port`, default
8080. `/` serves the runtime-owned `/index.html`; all other requests resolve through
the shared composition map. Run does not select a presentation.

If the selected port is already in use, run exits 1 without a traceback, identifies
the port, and directs the author to choose another with `--port PORT`.

Every development response uses `Cache-Control: no-store`. Run injects the local
dependency capability into `/index.html` and serves the effective runtime-plus-catalog
dependency mapping beneath `/~dependencies/`. Runtime and catalog tables cannot contain
the same logical key. It also injects a development-only reload client and exposes
`/vividly/~dev/events` as a server-sent events endpoint unless `--no-watch` is present.
The dependency capability remains active with `--no-watch`. None of these injected
development features exists in export.

The browser loads the selected runtime's JSON dependency table before parsing the YAML
catalog, obtains js-yaml through the dependency registry, then pushes the catalog table.
The remaining built-in dependencies load through that same registry. Connected misses
populate the persistent per-user cache, and concurrent consumers of one logical key
receive one memoized loaded instance.

By default, run watches the author source root and, in repository or path mode, the
selected editable runtime root. It debounces relevant changes and notifies connected
clients to perform an ordinary full-page `location.reload()`. Package resources are
immutable for the command lifetime and are not watched. `--no-watch` disables
filesystem watching and reload-client injection but retains development `no-store`
headers.

Watcher startup and runtime failures are surfaced to the terminal. A runtime manifest
change in an editable source triggers complete composition revalidation before reload.
If revalidation fails, the server reports the error and does not notify clients to load
an invalid composition.

Run validates package manifest identity, compatibility, safe paths, and the exact file
set once at startup. It does not hash every package runtime file and performs no
per-request integrity work.

## 7. `vividly install-browser`

Installs the Playwright-managed Chromium version required by Vividly's installed
Playwright dependency. The command takes no project path and does not install or select
an arbitrary system browser. Browser files live in Playwright's user-level cache and
are shared by compatible Vividly installations. The Vividly distribution pins
Playwright to an exact version so project and independently resolved tool environments
require the same browser revision.

The operation is idempotent. If the matching browser is already installed, it succeeds
without downloading it again. Vividly invokes Playwright through the Python interpreter
running the command, so installation always targets that Vividly environment's
Playwright version. Installer progress and platform diagnostics stream directly to the
terminal. Vividly never requests administrator privileges. On a platform that lacks
required system libraries, the command exits 1 and leaves Playwright's
platform-specific prerequisite guidance visible for the user to run separately.

If thumbnail generation or rehearsal cannot find the executable required by its active
Playwright package, the failure identifies that Playwright version, explains that a
Vividly or Playwright installation or upgrade can require a new compatible browser, and
directs the user to run `vividly install-browser`. The diagnostic does not claim that no
other Chromium revision or system browser is installed.

## 8. `vividly reference`

```console
vividly reference [PATH]
```

Reference resolves the exact runtime selected by `vividly.yaml` and atomically
materializes its non-deployed reference Markdown under
`PATH/.vividly/reference/`. It does not require `site/catalog.yaml`.

In package mode, the command validates the configured runtime identity and verifies
every packaged reference file against `vividly-runtime.json`. In repository and path
modes, it copies the selected editable reference tree without enforcing content hashes.
Every mode rejects unsafe paths and symbolic links.

The generated `.vividly/reference/runtime.json` records enough selected-runtime
identity plus a digest of the reference paths and bytes to detect stale output. If both
the identity and content digest already match, the command succeeds without rewriting
files. Otherwise it stages the complete output before replacing the previous generated
reference tree. It never merges generated files with user edits.

The command performs no network access. Missing or unavailable package resources use
the same exact-version and offline diagnostics as other runtime consumers. Seeded agent
instructions tell agents to run the command when the materialized reference is absent
or stale.

## 9. `vividly dependencies`

```console
vividly dependencies [PATH]
vividly dependencies [PATH] --json
```

Dependencies resolves the selected runtime, validates its built-in dependency table,
loads the project catalog dependency table, rejects cross-table key collisions, and
displays the complete effective registry. It does not load presentation manifests.

The default human-readable output is sorted by logical key and contains:

- logical key;
- owner, either the selected runtime identity or `catalog`;
- declared version, or `—` for a catalog dependency;
- loader type; and
- complete CDN entry URL.

`--json` writes one UTF-8 JSON object followed by a line feed. The object has:

```json
{
  "schema": 1,
  "runtime": {
    "source": "package",
    "version": "0.0.1"
  },
  "dependencies": [
    {
      "key": "marked",
      "owner": "runtime",
      "ownerIdentity": "Vividly 0.0.1",
      "version": "12.0.2",
      "projectUrl": "https://github.com/markedjs/marked",
      "license": "MIT",
      "loader": {
        "type": "script",
        "global": "marked"
      },
      "baseUrl": "https://cdn.jsdelivr.net/npm/marked@12.0.2/lib/",
      "entry": "marked.umd.js",
      "url": "https://cdn.jsdelivr.net/npm/marked@12.0.2/lib/marked.umd.js",
      "sha256": "<64 lowercase hexadecimal digits>"
    }
  ]
}
```

Dependencies are sorted by `key`. Runtime records contain their declared `version`,
`projectUrl`, `license`, and `sha256`. Those four fields are `null` for catalog records
because the catalog schema does not declare them; the command does not infer metadata
from URL strings. A catalog record's loader is `{"type":"module"}`. `ownerIdentity`
identifies the selected runtime for a runtime record and is `null` for a catalog
record.

The command performs no network access, does not read or populate the dependency cache,
does not launch a browser, and does not execute dependency code. It is the supported
way for authors and agents to discover the dependencies available through
`ctx.dependency()`.

Human-readable dependency and cache reports use Rich tables. They adapt to terminal
color support and remain legible when redirected or when color is disabled. JSON
reports never contain Rich markup or ANSI control sequences.

### 9.1 `vividly cache`

```console
vividly cache status [PATH]
vividly cache status [PATH] --json
vividly cache status --all
vividly cache status --all --json
vividly cache clear
vividly cache clear --yes
```

Project-scoped status composes `PATH`, associates cache resources with every selected
dependency base, and adds a `missing` row when a selected entry URL has no valid cache
resource. It reports all physically present resources under each selected base,
including invalid, incomplete, and unreadable resources. `--all` does not load a
project; it inspects every resource namespace under the global cache root, including
old, unrelated, and unassociated resources.

Each row contains dependency key when known, relative resource path when known,
complete source URL when readable, status, byte size when observable, and cached time.
Statuses are `valid`, `missing`, `invalid`, `incomplete`, or `unreadable`. Cached time
is the `metadata.json` modification time, displayed with an explicit local timezone in
human output and as RFC 3339 UTC in JSON. Rows are sorted deterministically by key,
source URL, status, and physical cache path.

JSON output is one compact object followed by a line feed:

```json
{
  "schema": 1,
  "scope": "project",
  "cacheRoot": "/absolute/cache/path",
  "resources": [
    {
      "key": "marked",
      "relativePath": "marked.umd.js",
      "sourceUrl": "https://cdn.example.invalid/marked.umd.js",
      "status": "valid",
      "size": 1024,
      "cachedAt": "2026-09-28T03:15:00Z"
    }
  ]
}
```

Status is strictly read-only: it performs no acquisition, repair, deletion, browser
launch, dependency execution, or cache timestamp update. Resource enumeration does not
prove a multipart dependency graph is complete or offline-ready; `vividly rehearse`
remains the bounded offline-readiness authority.

`cache clear` targets only the complete resolved Vividly dependency-cache root. It
requires interactive confirmation unless `--yes` is present, succeeds when the root is
absent, refuses a symbolic-link or non-directory root, and preserves every sibling
path. Active Vividly processes may repopulate the cache and should be stopped before a
predictable clear-and-observe cycle.

## 10. `vividly thumbnails`

Generates the complete thumbnail sequence for selected author slides and writes
author-owned publishable output under `PATH/site/thumbnails/`.

```console
vividly thumbnails [PATH]
vividly thumbnails [PATH] --presentation ID
vividly thumbnails [PATH] --presentation ID --slide ADDRESS
vividly thumbnails [PATH] --missing
```

With neither option, the command regenerates every slide in every catalog
presentation. `--presentation ID` limits generation to that catalog entry. `--slide
ADDRESS` may be repeated and is valid only with exactly one `--presentation`.
System IDs beginning with `~` are not public thumbnail targets.

This is explicit selection, not dependency-based incremental generation. Equal
addresses in two presentations are distinct selections and outputs.

`--missing` further limits the selected slides to those without a version-3 index
entry or with at least one indexed image that is absent or not a regular file. It may
be combined with `--presentation` and `--slide`; the resulting selections intersect.
Vividly captures the complete sequence for each missing slide, not only the absent
steps. It does not compare source files, revisions, or current runtime step counts for
complete indexed slides, so ordinary generation remains the way to refresh thumbnails
after source changes.

### 10.1 Preconditions

Before capture or output mutation, thumbnails:

1. validates the composition without package per-file hashing;
2. validates the complete catalog structure and selected root manifests;
3. validates presentation IDs, slide addresses, incorporation, cycles, and
   `thumbnail.step` values;
4. validates the existing version-3 thumbnail index; and
5. verifies that the required Playwright-managed Chromium is installed.

A project-wide invocation loads every catalog presentation before capture. A selective
invocation does not load unselected manifests. A finite slide reporting more than
10,000 steps is invalid because generated names reserve four decimal digits.

An absent thumbnail index starts an empty ledger. An existing index with an unsupported
version, malformed sequence, invalid canonical step or revision, unsafe path, or path
outside the thumbnail root is an error. Any precondition failure exits 1 without
changing output.

Vividly does not silently download a browser or fall back to an arbitrary system
browser. If Chromium is absent, it directs the user to run
`vividly install-browser`.

### 10.2 Capture

The command starts a temporary loopback server backed by the shared composition and
the same connected per-user dependency cache used by `vividly run`, then launches a
fresh browser context. Runtime bootstrap dependencies and resources exercised during
rendering fill that cache; later interactions are not explored. The internal server
does not inject the live-reload client. It fixes the viewport at 1920x1080 with device
scale factor 1, locale, timezone, color scheme, and reduced-motion preference held
constant. Empty browser storage keeps capture independent of author presentation
progress.

For each selected slide, the command opens a fresh browser context and navigates to its
ID-prefixed step-zero route. It waits for the orchestrator's `data-render-ready` signal
and network quiescence, reads the finite step count or dynamic marker, and validates
the canonical step.

For a finite slide it captures step `0`, visits every remaining step in ascending order,
waits for render settling after each navigation, and captures each state. For a dynamic
slide it captures only initial state step `0`. Capture mode disables carets,
transitions, and animations. Each capture contains only the stage and is resized to a
320x180 PNG without volatile metadata.

`thumbnail.step` selects the canonical member of a finite sequence; it does not limit
which steps are generated. Without an override, the final finite step is canonical. A
dynamic slide may not declare `thumbnail.step`.

Playwright and the image encoder are pinned tool dependencies. Given the same tool,
browser, operating system, installed fonts, and slide inputs, encoding is deterministic.
Cross-platform byte identity is not promised because browser text rasterization can
differ.

Before replacing an image, the command compares bytes and leaves identical output
untouched. The lowercase hexadecimal SHA-256 of each PNG is its `revision`. The
timestamp-free, sorted index is likewise rewritten only when its bytes change.

### 10.3 Thumbnail ownership and reconciliation

`site/thumbnails/index.json` is the runtime lookup and generated-output ownership
ledger. Version 3 groups entries by presentation ID and presentation-local slide
address. Each slide entry records its canonical step and complete ascending sequence:

```json
{
  "version": 3,
  "presentations": {
    "product-tour": {
      "intro/title-card": {
        "canonicalStep": 1,
        "steps": [
          {
            "step": 0,
            "path": "product-tour/intro/title-card/step-0000.png",
            "revision": "628ee627a7b31e7f8c3185a14e408154fc10d484939d60ff5c5927c31f22056f"
          },
          {
            "step": 1,
            "path": "product-tour/intro/title-card/step-0001.png",
            "revision": "ba800375968690a9b7e2454a040eafff9b7c21c1905b9e31dbdb1448817e24"
          }
        ]
      }
    }
  }
}
```

Keys are sorted. Step arrays are nonempty, ascending, contiguous from zero, and contain
the canonical step. Image paths are relative to `site/thumbnails/`, contain no query or
fragment, and use:

```text
<presentation-id>/<slide-address>/step-<four-digit-step>.png
```

The index, not this convention, is authoritative. Presentation ID, complete
incorporation address, and step prevent collisions.

Each old indexed image is output previously generated by Vividly. Unindexed files are
author-owned and are never removed or overwritten. If a selected new output would
occupy an unindexed path, thumbnails reports a collision.

Every invocation computes complete reachability for each selected presentation.
Sequence length is computed for each slide selected for capture. The command constructs
the prospective index and identifies stale indexed paths within the selected scope.
Entries and files for unselected presentations or slides are carried forward unchanged.
A project-wide invocation also removes indexed output for presentation IDs no longer
in the catalog; selective invocation does not reconcile removed or unselected
presentation IDs.

`--missing` changes capture selection only. The invocation retains the same selected
scope for ownership reconciliation, including removal of unreachable indexed slides
and, for a project-wide invocation, presentations removed from the catalog.

All new images and the complete prospective index are staged before output mutation. A
validation or capture failure leaves previous images and the index intact. On success,
the command atomically replaces selected images, removes selected-scope stale indexed
files, prunes empty generated directories, and atomically replaces the complete index
last. There is no destructive `--clean` option.

The runtime fetches the stable index with cache revalidation and appends each indexed
revision as `?v=<revision>` to the image URL. Published hosting must revalidate the
mutable index and include the query string in image cache keys. Thumbnail images may
otherwise use long-lived caching.

## 11. `vividly rehearse`

```console
vividly rehearse [PATH]
```

Rehearse validates the composition, starts a cache-only loopback server, and launches a
fresh visible Chromium context with Service Workers blocked. It opens the project
catalog and allows only the exact local server origin. External HTTP, HTTPS, and
WebSocket requests are blocked and recorded.

The user drives the browser normally, then returns to the terminal and presses Enter to
finish. A rehearsal fails if the exercised path produces a dependency cache miss,
external network attempt, uncaught page error, or page crash. Each issue identifies its
kind, active hash route, URL, and detail.

Runtime bootstrap dependencies use the same cache-only boundary. If js-yaml is absent,
rehearsal reports a cache miss against the catalog route before a presentation or slide
route can load and makes no upstream request.

A successful run makes only this bounded claim:

> The presentation worked without external dependency access for the slides and
> interactions exercised during this rehearsal.

The command does not persist a readiness badge or claim coverage of unexercised
interactions. If Chromium is absent, it directs the user to
`vividly install-browser`.

## 12. `vividly export`

```console
vividly export [PATH] --output DESTINATION
```

Export validates the complete composition and, in package mode, verifies every runtime
file against its manifest digest. It materializes the logical site according to the
runtime-composition export contract.

`DESTINATION` is resolved canonically. It must be absent or an empty directory and
cannot contain or be contained by the project, author source, or selected runtime
source. Export stages all output in a sibling temporary directory on the destination
filesystem and renames it into place only after successful assembly.

The result contains the runtime-owned `/index.html` and `/vividly/**` paths plus every
author-owned path from `site/`. Runtime files include the built-in dependency table with
auditable version, source, integrity, loader, and license-identifier metadata. The
export contains no `vividly.yaml`, `.github/`, development reload client, development
endpoint, development cache policy, local dependency capability, dependency cache
bytes, selected third-party dependency payloads, or upstream license copies. Runtime
and catalog dependency selections remain CDN-backed.

Export preserves source bytes and does not rewrite URLs for a hosting target. The
runtime-owned shell and modules use relative URLs so the same artifact can be mounted
at an origin root or beneath a base path. Author-owned content intended for a base-path
deployment must likewise use relative URLs.

The exported files form a static site, but exercised dependencies require network
access to their pinned CDN origins. Export does not create a portable offline artifact.

Export destinations remain outside the project and its source trees. A sibling such as
`../project-export` is suitable for local inspection.

## 13. `vividly publish`

```console
vividly publish [PATH] [--target TARGET] [--dry-run]
```

Publish requires `PATH/vividly.publish.yaml` in addition to the ordinary project and
composition files. `--target` selects a configured target. When it is omitted, publish
uses the configured default or the sole configured target. `--dry-run` performs
complete validation and ephemeral candidate materialization without creating
candidate-derived Git objects, creating or updating refs, creating a commit, or
pushing. Remote inspection may fetch ordinary remote objects.

The initial target is GitHub Pages branch-root publication. Publish:

1. requires the entire containing Git repository to be committed and clean;
2. validates the target, Git identity, remote, and publication branch;
3. materializes the complete export in operating-system temporary storage;
4. adds deterministic publication metadata and target-owned files;
5. constructs a complete Git tree through an isolated temporary index;
6. creates an initial root commit or a single-parent successor to recognized
   publication history; and
7. pushes the commit through a normal non-force Git update.

Publish never switches branches, modifies the user’s working tree or index, creates a
Git worktree, creates a local publication branch, force-pushes, invokes a GitHub API,
or observes GitHub Pages activation.

An unchanged publication tree is a successful no-op that creates no commit and performs
no push. A successful changed publication means the remote accepted the publication
commit; provider activation remains asynchronous and unobserved.

The exact configuration schema, public `vividly-publication.json` format, publication
commit contract, branch-recognition rules, failure semantics, and GitHub Pages boundary
are defined by [`publishing.md`](publishing.md).

### 13.1 Repository public-site candidate

The Vividly source repository retains a repository-specific maintainer helper that
assembles a public-site candidate without publishing it:

```console
uv run python tools/export_public_site.py --output ../vividly-pages
```

The command requires a clean Git worktree, records the full `HEAD` revision in its
report, verifies that generated public reference Markdown matches its canonical package
source, and invokes the same `export_project()` primitive as `vividly export`. The
destination follows the ordinary export safety rules and remains generated and
uncommitted. It is not the `vividly publish` implementation and does not create or push
a publication commit. The command does not use GitHub credentials, invoke a deployment
API, or modify Pages configuration.
