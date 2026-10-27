# Dependency Resolution

Status: Specified. The catalog cache and rehearsal are implemented; the runtime-owned
registry extension is planned.

## 1. Purpose

A Vividly project may combine presentations and slides written at different times.
Those sources may expect different versions of the same browser package, and the
project may need to run without network access in high-stakes or disconnected
environments.

The dependency system therefore separates:

1. the logical dependency name used by slide code;
2. the runtime or project table that owns the concrete selection;
3. the immutable CDN location recorded by that table; and
4. the environment-specific URL and shared instance used at runtime.

This specification initially covers browser-ready dependencies. Vividly does not run a
Node package manager, transform packages, discover arbitrary transitive dependencies, or
rewrite package source.

## 2. Design principles

- **Explicit ownership.** The selected runtime owns its built-in dependency selections,
  and the project catalog owns author dependency selections.
- **Slide-owned use.** Slide code asks for a logical key and does not embed the selected
  version or environment.
- **Page-wide consistency.** A logical key has one owner, one concrete selection, and
  one memoized loaded instance throughout the SPA.
- **No shadowing.** A later dependency table cannot replace a key from an earlier
  table.
- **No source rewriting.** Relative imports and resource references keep their browser
  semantics.
- **Environment neutrality.** The same slide code resolves directly to the declared CDN
  in a static export and to a same-origin mirrored tree when local dependency serving is
  available.
- **Truthful offline claims.** A presentation is not declared ready for disconnected use
  merely because some dependency files have been cached.

## 3. Scope

The design includes:

- a runtime-owned built-in dependency table;
- project-catalog dependency mappings;
- one stacked browser dependency registry;
- module, classic-script, and stylesheet loading;
- a shared slide dependency API;
- direct CDN resolution for static exports;
- a constrained local read-through cache under a fixed URL base; and
- a user-driven, cache-only rehearsal mode.

The following are outside the initial scope:

- npm resolution or package installation;
- import-map generation;
- JavaScript, CSS, or WebAssembly rewriting;
- automatic discovery of absolute external URLs;
- package recipes or a package registry;
- dependency-table shadowing;
- automatic isolation of mutually incompatible packages;
- automatic traversal of every possible slide interaction;
- persistent readiness certificates or badges;
- cache administration beyond what is needed to run and rehearse a presentation; and
- Service Worker interception.

## 4. Dependency tables

### 4.1 Logical keys

A logical key is a lowercase author identifier:

```text
^[a-z0-9]+(?:-[a-z0-9]+)*$
```

Examples include `three`, `marked`, and `chart-renderer`. Keys have one meaning
throughout the SPA, regardless of which table owns them. Slide code uses a key instead
of a package URL.

### 4.2 Runtime-owned table

Every selected runtime provides deployed UTF-8 JSON at:

```text
/vividly/dependencies.json
```

Its top-level object contains exactly:

- `schema`, currently the integer `1`; and
- `dependencies`, a mapping from logical keys to built-in dependency records.

The file uses JSON because it must be loaded before js-yaml is available. It is part of
the selected runtime file set and runtime-manifest identity. In package mode authors
cannot edit it independently of the selected Vividly release. Repository and path modes
treat changes as intentional editable-runtime changes.

Each runtime dependency record contains:

- `version`, a nonempty human-readable upstream version;
- `projectUrl`, a clean absolute HTTPS URL for the upstream project;
- `baseUrl`, following the URL rules in section 4.4;
- `entry`, following the path rules in section 4.4;
- `sha256`, exactly 64 lowercase hexadecimal digits containing the expected entry-file
  digest;
- `license`, a nonempty SPDX license identifier or expression; and
- `loader`, one of the loader records in section 4.5.

Unknown top-level and record fields are errors. The initial built-in keys are:

| Key | Version | Loader |
| --- | --- | --- |
| `js-yaml` | 4.1.0 | Classic script exposing `jsyaml` |
| `marked` | 12.0.2 | Classic script exposing `marked` |
| `highlight-js` | 11.9.0 | Classic script exposing `hljs` |
| `highlight-github-dark` | 11.9.0 | Stylesheet |

The selected runtime, not `catalog.yaml`, owns these versions and loading models.
`version`, `projectUrl`, and `license` are auditable metadata; they do not alter URL
resolution or cause Vividly to fetch license text.

### 4.3 Project catalog table

The optional top-level `dependencies` field in `catalog.yaml` is a mapping:

```yaml
version: 1

dependencies:
  three:
    baseUrl: https://cdn.jsdelivr.net/npm/three@0.180.0/
    entry: build/three.module.js
  d3:
    baseUrl: https://cdn.jsdelivr.net/npm/d3@7.9.0/
    entry: src/index.js

presentations:
  - id: architecture-talk
    title: Architecture Talk
    manifest: ./presentations/architecture-talk.yaml
  - id: appendix
    title: Appendix
    manifest: ./presentations/appendix.yaml
```

Each catalog record has exactly two fields:

- `baseUrl`, following the URL rules in section 4.4; and
- `entry`, following the path rules in section 4.4.

Unknown fields are rejected. Omitting `dependencies` is equivalent to an empty project
table. Catalog dependencies implicitly use the `module` loader and do not declare
loader or integrity fields in this schema.

### 4.4 Common concrete-selection rules

`baseUrl` must:

- be an absolute HTTPS URL;
- end in `/`;
- contain no credentials, query, or fragment; and
- select a version-pinned or otherwise immutable package base.

Vividly validates the URL shape but cannot prove that a remote publisher will keep bytes
immutable.

`entry` must:

- be nonempty;
- be relative rather than absolute or root-relative;
- contain no query or fragment;
- contain no empty, `.` or `..` path segment; and
- use `/` as its path separator.

### 4.5 Loader records

A runtime dependency loader is one of:

```json
{ "type": "module" }
```

```json
{ "type": "script", "global": "marked" }
```

```json
{ "type": "stylesheet" }
```

Unknown loader fields are errors. `module` and `stylesheet` accept only `type`.
`script` requires exactly one `global`, which must be a JavaScript identifier naming a
direct property of `globalThis`.

Loader results are:

| Loader | Instantiation | Result |
| --- | --- | --- |
| `module` | Dynamic import of the entry URL | Module namespace |
| `script` | One classic script element | Declared global value |
| `stylesheet` | One stylesheet link element | Loaded link element |

The loader describes executable behavior, not package compatibility. Different module
URLs do not create separate browser realms. Packages that use globals, custom-element
names, shared symbols, prototype mutation, or other singleton state may still reject
or malfunction with multiple versions.

### 4.6 Table stacking and ownership

The browser registry first receives the selected runtime table and then the project
catalog table. Each push validates the complete candidate before changing registry
state. A push fails if:

- the candidate table is invalid;
- a candidate key duplicates another key in that table; or
- a candidate key already exists in any table in the registry.

Tables never shadow or replace earlier tables, even when two records are byte-for-byte
equivalent. A collision identifies the key and both owners.

Python composition performs the same runtime-versus-catalog collision check before
serving or exporting. Browser validation repeats it as defense in depth.

The catalog mapping applies to every presentation and thread in the SPA. Presentation
manifests, including manifests incorporated through a `type: presentation` node, must
not declare concrete dependency selections.

When imported slides or presentations expect different versions, the project author
must choose compatible project selections and adapt incompatible slide code. Distinct
keys may select distinct versions, but Vividly does not claim that those versions can
coexist safely in one page. Vividly does not solve version constraints or provide
iframe, worker, rewriting, or other automatic isolation.

## 5. Runtime API

Every slide context provides:

```js
const dependency = this.ctx.dependency('three');
const module = await dependency.load();
```

The dependency handle has three operations:

```js
dependency.url();    // URL string for the declared entry
dependency.load();   // Shared registry instance
dependency.import(); // Module-only compatibility operation
```

`url()` is synchronous. `load()` returns the registry's promise-memoized result for the
record's loader. The registry stores the promise before awaiting network or DOM events,
so concurrent framework and slide callers receive one execution and one result.

`import()` remains available for existing catalog module consumers. It returns the same
memoized module namespace as `load()` for a `module` dependency and fails clearly for
`script` or `stylesheet`.

Requesting an unmapped key throws an error that identifies the slide address and logical
key. Runtime-owned keys are available through the same API as catalog keys. Slides must
not import `/vividly/vendor/**` or read dependency globals directly.

The initial API does not expose arbitrary package-relative paths; relative imports and
resources reached from the entry are resolved by the browser.

## 6. Bootstrap and environment-specific resolution

### 6.1 Bootstrap sequence

The runtime starts in this order:

1. fetch and validate `/vividly/dependencies.json` without a third-party parser;
2. create the page-wide dependency registry;
3. push the runtime table;
4. load `js-yaml` through the registry;
5. fetch and parse `catalog.yaml` with that instance;
6. normalize and push the catalog dependency table;
7. eagerly load the remaining initial built-in dependencies; and
8. load the selected presentation using the same registry.

The runtime does not define the presentation custom element or begin catalog-driven
orchestration until the required bootstrap dependencies are ready. Catalog,
presentation-manifest, and YAML slide-data parsing receive js-yaml from the registry
rather than treating `window.jsyaml` as an ambient public API.

### 6.2 Static export

The committed runtime shell and static exports contain no local dependency capability
or dependency payload bytes. Runtime and catalog records resolve directly to their
pinned CDN locations:

```text
dependency.url() = new URL(entry, baseUrl)
```

For the `three` example, the result is:

```text
https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js
```

Runtime classic scripts and stylesheets use their declared SHA-256 as browser integrity
metadata where the platform supports it. Catalog module entries retain their current
direct-import behavior.

Static publication requires network access to every exercised CDN resource. It is not a
portable offline artifact.

### 6.3 Local dependency capability

`vividly run` and the internal server used by `vividly thumbnails` add a
`dependency-base` attribute to the root element:

```html
<vividly-presentation
  catalog="./catalog.yaml"
  dependency-base="./~dependencies/"
></vividly-presentation>
```

The attribute is absent from committed static output and export. It resolves to a
nonempty same-origin URL, and the runtime normalizes it to a trailing-slash base.
Because the shell uses `./~dependencies/`, a shell served at the origin root resolves
the dependency tree at `/~dependencies/`; presentation IDs and runtime resources below
`/vividly/` do not change that base.

The local entry URL is:

```text
<dependency-base>/<logical-key>/<entry>
```

The `three` example becomes:

```text
http://localhost:8000/~dependencies/three/build/three.module.js
```

The server is responsible for associating the logical key with the validated effective
runtime-plus-catalog selection. Browser-controlled query parameters or arbitrary
upstream URLs must never select the upstream origin.

## 7. Relative resource compatibility

The local server mirrors package-relative paths below the selected fixed `baseUrl`.
Consequently, browser URL resolution can request the corresponding local path without
source parsing or rewriting.

This works for resources that remain relative to files in the mirrored tree, including:

- static relative ESM imports;
- executed dynamic relative imports;
- module-relative WebAssembly and data requests;
- relative CSS imports and `url(...)` references;
- relative fonts and images; and
- relative workers during local serving.

It does not automatically cover:

- absolute external imports, fetches, fonts, images, or other URLs;
- root-relative URLs;
- bare module specifiers without an import map;
- conventional relative workers when the entry itself runs from a cross-origin CDN in
  a static export; or
- resources discovered only along unexercised interaction paths.

Packages needing unsupported URL behavior must provide a browser-ready bundle, expose
configuration that slide code can point at supported URLs, or wait for a future
extension. Vividly does not silently claim those resources are available offline.

## 8. Local read-through cache

The local dependency route is a constrained mapping, not a general proxy.

For each request, the server will:

1. identify the logical key from the local path;
2. obtain the uniquely owned runtime or catalog record from the effective composition;
3. canonicalize the remaining package-relative path;
4. reject traversal, malformed encoding, and paths outside the fixed base;
5. return a valid cached response when available;
6. otherwise fetch the corresponding HTTPS upstream URL;
7. reject redirects rather than following them;
8. require an HTTP 200 response no larger than 64 MiB;
9. require a built-in entry response to match its declared SHA-256;
10. commit successful bytes and metadata atomically; and
11. return an explicit error on failure.

Acquisition sends no browser credentials or referrer. It uses a 15-second timeout.

The persistent cache lives in the operating system's per-user cache location, outside
the project. Its internal namespace includes the SHA-256 digest of the canonical
`baseUrl`, so projects selecting different versions under the same logical key cannot
collide. Each resource is further identified by the SHA-256 digest of its complete
upstream URL.

Stored metadata includes:

- schema version;
- complete upstream URL;
- normalized media type;
- byte length; and
- SHA-256 of the response bytes.

Cache reads verify the metadata, length, and stored digest before returning bytes. A
built-in entry must additionally match the digest declared by the selected runtime.
Missing or invalid entries are reacquired in connected mode. Payload and metadata files
are written through same-directory temporary files and atomic replacement, with
metadata committed last. Concurrent requests for the same resource are serialized
within one Vividly process.

The current composition owns the effective runtime-plus-catalog selection used by each
request. A successful development reload therefore changes the fixed upstream mapping
without restarting the server, while an invalid runtime table, catalog change, or
cross-table collision leaves the previous validated composition active.

In cache-only mode, a missing or invalid entry produces HTTP 504 and never invokes the
acquirer.

Connected `vividly run` and `vividly thumbnails` processes use this same per-user cache
for built-in and catalog dependencies. Thumbnail rendering therefore warms the built-in
bootstrap and resources exercised while rendering the selected slides, but it does not
discover later interactions or certify offline readiness.

### 8.1 Cache observation and reset

`vividly cache status [PATH]` inspects resources physically stored under every base
selected by the effective project registry. `--all` instead inspects every global cache
namespace without loading a project. Inspection classifies resources as `valid`,
`missing`, `invalid`, `incomplete`, or `unreadable` and never invokes acquisition,
repair, deletion, dependency code, or a browser.

A physically present resource is associated with a project dependency when its parent
namespace is the SHA-256 of that dependency's canonical base URL. Readable metadata may
add its complete source URL and relative path. If several selected keys share a base,
the physical row is reported once for each matching key. A selected entry URL without
a valid resource receives a synthetic `missing` row even when a separate invalid or
incomplete physical row exists for that URL.

`valid` requires both files, readable schema-1 metadata, matching source-URL resource
namespace, matching byte length and digest, a string media type, and any selected
entry integrity. One missing file is `incomplete`; I/O or permission failure is
`unreadable`; all other structural or integrity failures are `invalid`. Byte size is
reported when content can be inspected. Cached time is derived only from
`metadata.json` modification time.

`vividly cache clear` removes the complete resolved cache root after confirmation, or
without prompting under `--yes`. It rejects a symbolic-link or non-directory root,
succeeds if the root is absent, and never deletes a narrower resource selection or an
unrelated sibling. Active processes may immediately repopulate a cleared cache.

Neither status nor clearing changes the offline-readiness contract. Only rehearsal of
the intended browser path supplies bounded offline-readiness evidence.

## 9. Cache-only rehearsal

`vividly rehearse [PATH]` checks disconnected readiness with a fresh, visible
Playwright-controlled Chromium browser:

1. the local Vividly origin remains available;
2. the browser blocks and records external HTTP(S) and WebSocket requests;
3. Service Workers are blocked;
4. the Vividly server runs in cache-only mode;
5. the user drives the intended presentation path; and
6. the user returns to the terminal and presses Enter to finish the rehearsal.

The rehearsal starts at the project catalog rather than selecting a presentation. The
user may navigate among catalog presentations and interact with slides normally.
Service Worker registration requests may resolve in browser script, but the fresh
context creates and activates no Service Workers.

Built-in dependencies participate in cache-only behavior. A missing js-yaml entry can
fail before the catalog or a slide route exists. The rehearsal reports active route
`(catalog)` and the missing local dependency URL, and never attempts upstream
acquisition.

Each observed issue reports:

- issue kind;
- active hash route, or `(catalog)`;
- failing URL; and
- a short detail.

The failure kinds are:

- missing dependency in the cache;
- blocked external HTTP(S) request;
- blocked external WebSocket; and
- uncaught browser page error or page crash.

External WebSockets are intercepted before connection and deliberately left
unconnected. The exact local origin is allowed. Other URL schemes are not treated as
network access by the initial boundary.

A successful rehearsal supports only this claim:

> The presentation worked without external dependency access for the slides and
> interactions exercised during this rehearsal.

It does not prove that unvisited slides, untriggered interactions, arbitrary user input,
or unsupported absolute URLs will work offline.

The result is printed for the current run only. Vividly stores no readiness badge,
certificate, or durable success record.

## 10. Built-in dependency provenance

The runtime packages `/vividly/dependencies.json`, not the selected third-party payload
bytes. Each runtime record provides the upstream version, project URL, exact artifact
URL components, expected SHA-256, loader type, and license identifier needed to audit
the selection.

Vividly does not package or export copies of the upstream license texts or a generated
third-party notice merely because a browser fetches the selected artifact directly from
its CDN. If legal review identifies an attribution or notice requirement for a future
selection, the selected runtime must add the required material as an ordinary
runtime-owned deployed file before publication.

The runtime manifest covers `dependencies.json`. Package and export validation require
the table and verify its digest like every other runtime file.

## 11. Future extensions

The following require separate evidence and design:

- integrity declarations for author-selected dependency entries;
- import-map support for bare package specifiers (the runtime's own `vividly/` entry
  is specified in [`presentation-orchestration.md`](presentation-orchestration.md) §2.1);
- explicit access to additional package-relative entry points;
- configurable resource helpers;
- Service Worker interception;
- isolation for mutually incompatible global packages; and
- broader cache inspection or management.

These extensions must not weaken fixed-base routing, table ownership, collision
rejection, or the accuracy of offline-readiness claims.
