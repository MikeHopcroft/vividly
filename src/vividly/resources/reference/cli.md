# Vividly CLI

The CLI creates projects, serves the composed site, inspects dependencies, materializes
local reference Markdown, and regenerates committed thumbnails. Run `vividly` or
`vividly <command> --help` for current syntax.

## Project layout

```text
my-project/
├── vividly.yaml                exact runtime selection
├── .gitignore                  ignores .vividly/
├── .github/                    agent instructions and authoring skill
└── site/                       author-owned source
    ├── catalog.yaml            root-presentation registry
    ├── presentations/          conventional manifest location
    ├── slides/                 reusable modules, data, and assets
    └── thumbnails/             generated presentation images
```

The selected runtime supplies deployed `/index.html` and `/vividly/**`. Development
commands compose those resources with `site/`; export materializes the complete static
site. Authors do not create `site/index.html` or `site/vividly/`.

`site/catalog.yaml` registers independently routable presentations. Each entry supplies
a stable presentation ID, display title, and local manifest path. Catalog order is
display order. Author IDs use lowercase ASCII letters and digits separated by single
hyphens. The `~` namespace is reserved for runtime views.

## `vividly provision`

Create a project in the current directory or at an explicit project root:

```console
vividly provision
vividly provision path/to/my-project
```

Provision validates every starter path and asks for confirmation. `--yes` skips the
prompt, never validation. It creates `vividly.yaml` selecting the exact runtime in the
installed package. Starter files under `site/` and `.github/` immediately become
author-owned and are never reconciled or upgraded by later provision runs.

Projects containing only the obsolete `vividly-baseline.json` marker must be
reprovisioned. Vividly does not parse or migrate that file.

To explicitly repin an existing package-runtime project to the exact runtime in the
installed package, run:

```console
vividly provision --upgrade
vividly provision --upgrade --yes
```

The command displays the old and new runtime identities and asks for confirmation
unless `--yes` is supplied. It atomically updates only `vividly.yaml`; author files,
starter seeds, thumbnails, and derived state are untouched. Repository and path runtime
sources must be updated through their author-managed workflows.

## `vividly run`

Serve the composed project:

```console
vividly run
vividly run path/to/my-project --port 8090
vividly run --no-watch
```

Run validates `vividly.yaml`, the selected runtime, and `site/catalog.yaml`. It serves
runtime and author files without a build, disables browser caching, and reloads
connected browsers after relevant author or editable-runtime changes. `--no-watch`
disables watching and reload injection.

## `vividly reference`

Materialize version-matched local reference Markdown for coding agents:

```console
vividly reference
vividly reference path/to/my-project
```

Output is written atomically under `.vividly/reference/`. It is derived, disposable,
and ignored by Git. Run the command again after changing runtime selection or editing a
repository/path runtime reference.

## `vividly install-browser`

Thumbnail capture uses Vividly's Playwright-managed Chromium:

```console
vividly install-browser
```

The command installs the Chromium revision required by the Playwright package in the
active Vividly environment. It is safe to run again and does not redownload an existing
matching browser. Run it after upgrading Vividly or Playwright if capture reports that
a compatible Chromium is missing.

## `vividly dependencies`

Display every dependency available from the selected runtime and project catalog:

```console
vividly dependencies
vividly dependencies path/to/my-project --json
```

The deterministic report includes each logical key, owner, declared version, loader,
and source URL. JSON output includes normalized metadata for agents and tooling. The
command validates the effective registry without accessing the network or dependency
cache, launching a browser, or executing dependency code.

## `vividly cache`

Inspect project-relevant cache resources:

```console
vividly cache status
vividly cache status path/to/my-project --json
```

Inspect every resource in the global Vividly dependency cache without loading a
project:

```console
vividly cache status --all
```

Status reports resource-level keys, paths, URLs, health, sizes, and cached timestamps.
It is read-only and does not claim that multipart dependencies are complete; use
[`vividly rehearse`](#vividly-rehearse) to verify the intended offline presentation
path. See [Browser dependencies](./dependencies.md#cache-preparation-and-offline-rehearsal)
for the distinction between registry inspection, cache observation, and rehearsal.

Clear the complete Vividly dependency cache:

```console
vividly cache clear
vividly cache clear --yes
```

The default form asks for confirmation. Stop active Vividly processes first when you
need a predictable clear-and-observe cycle.

## `vividly rehearse`

Verify an intended presentation path against the dependency cache without network
fallback:

```console
vividly rehearse
vividly rehearse path/to/my-project
```

Rehearse validates the composition, starts a cache-only loopback server, and launches a
fresh visible instance of Vividly's Playwright-managed Chromium with Service Workers
blocked. It opens the project catalog. Drive the browser through the slides, steps, and
interactions that must work offline, then return to the terminal and press Enter.

The browser allows only the exact local Vividly origin. The run fails if the exercised
path produces a dependency-cache miss, external HTTP, HTTPS, or WebSocket attempt,
uncaught page error, or page crash. Each issue identifies its kind, active route, URL,
and detail.

A successful rehearsal verifies only the path exercised during that run. It does not
discover or certify unvisited slides or untriggered interactions, and it stores no
readiness badge. Populate required resources first with connected `vividly run` or
`vividly thumbnails`. If the required Chromium is absent, run
`vividly install-browser`.

See [Browser dependencies](./dependencies.md#cache-preparation-and-offline-rehearsal)
for the connected preparation and rehearsal workflow.

## `vividly thumbnails`

Capture every slide in every catalog presentation:

```console
vividly thumbnails
```

Select one presentation or presentation-local addresses within it:

```console
vividly thumbnails --presentation product-tour
vividly thumbnails --presentation product-tour --slide intro/title-card
```

Add `--missing` to capture only slides whose index entry is absent or whose indexed
sequence has a missing file. Vividly recaptures the complete sequence for each such
slide. This option can be combined with `--presentation` and `--slide`; it does not
detect source changes:

```console
vividly thumbnails --missing
vividly thumbnails --presentation product-tour --missing
```

Outputs live beneath `site/thumbnails/<presentation-id>/`. The version-3 index records
their paths and content revisions. Selective generation preserves unselected
presentations.

## `vividly export`

Materialize the complete static site:

```console
vividly export --output dist
```

The destination must be absent or empty. Export combines the author source and selected
runtime without modifying either and never includes development reload behavior or
`.vividly/` state.

## `vividly publish`

Publish a complete static site to a configured GitHub Pages branch:

```console
vividly publish
vividly publish path/to/my-project
vividly publish --target pages
vividly publish --dry-run
```

The project root contains `vividly.publish.yaml`. `PATH` defaults to the current
directory; `--target` selects an exact configured target, and `--dry-run` validates and
classifies the intended operation without creating candidate Git objects or refs and
without pushing.

Publishing requires the entire containing Git repository to be clean. It materializes
the complete site locally, creates a complete commit through an isolated temporary
index, and performs an ordinary non-force push to the configured publication branch.
It never switches branches, creates a worktree or local publication branch, or modifies
the author working tree or normal index.

GitHub Pages must be configured once to deploy the publication branch from `/` (root).
Vividly reports remote acceptance as success; provider activation is asynchronous and
is not observed. An identical publication is a successful no-op with no commit or
push.

See [Publishing a presentation](./publishing.md) for target configuration, custom
domains, safety guarantees, result interpretation, cleanup, and recovery.

## See also

[Authoring slides](./authoring.md) — the end-to-end slide workflow and validation
checklist.

[Browser dependencies](./dependencies.md) — package selection, cache preparation, and
offline verification.

[Publishing a presentation](./publishing.md) — GitHub Pages setup, publication
configuration, safety, and recovery.
