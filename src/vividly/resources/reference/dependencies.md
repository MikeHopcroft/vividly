# Browser dependencies

Vividly uses logical dependency keys so slide code does not own a concrete package
version or CDN URL. The selected runtime owns its built-in dependencies, and
`site/catalog.yaml` owns one project-wide selection for each author dependency. Every
presentation in the page uses that effective registry.

This guide covers the dependency lifecycle: choosing a mechanism, adding or upgrading a
package, preparing its exercised resources for offline use, resolving conflicts, and
removing an unused selection.

## Choose the right mechanism

Run `vividly dependencies` before adding anything. Then choose:

| Need | Mechanism |
| --- | --- |
| Package already selected by the runtime or project | Reuse its logical key |
| Source code owned only by one slide | Keep a relative module in the slide directory |
| Slide-local classic script | Keep it with the slide and use `ctx.loadScript()` |
| Shared browser-ready ESM package | Declare one project-wide catalog dependency |
| Package requiring npm installation, bundling, source rewriting, or unsupported workers | Adapt it or choose another browser-ready artifact |

Vividly does not run a Node package manager, bundle code, rewrite package source,
resolve semver ranges, or generate import maps. Do not add a package manager or build
step merely to use a slide dependency.

## Inspect the effective registry

Use:

```console
vividly dependencies
vividly dependencies --json
```

The report includes each logical key, owning table, declared version, loader, and
source URL. It validates the effective registry without network access, cache access, a
browser launch, or package execution.

Runtime-owned keys include `js-yaml`, `marked`, `highlight-js`, and
`highlight-github-dark`. A catalog entry cannot replace a runtime-owned key.

## Evaluate a package

A catalog dependency must expose a browser-ready ESM entry at a pinned or otherwise
immutable HTTPS base. Before selecting it:

1. identify the upstream project and exact version;
2. verify the CDN path comes from the expected package and publisher;
3. review the package license and any notice or attribution obligations;
4. inspect the entry for bare specifiers or environment assumptions;
5. inspect relative static and dynamic imports;
6. inspect CSS, fonts, images, data, WebAssembly, and workers reached by the intended
   interactions; and
7. consider global, singleton, prototype, shared-symbol, or custom-element behavior
   that could conflict with other page code.

Project dependency records do not contain license or provenance fields. Record or
satisfy any project-specific review obligations outside the catalog; do not add
unsupported fields to its schema.

Relative ESM imports, dynamic imports, data, WebAssembly, CSS, fonts, images, and local
workers can follow the selected base during local serving. Vividly does not
automatically support absolute external URLs, root-relative URLs, bare specifiers, or
resources reached only through unexercised interactions. A conventional relative
worker from a cross-origin CDN entry will not work in static publication.

## Add and use a dependency

Declare one logical key under the top-level `dependencies` mapping in
`site/catalog.yaml`:

```yaml
version: 1

dependencies:
  three:
    baseUrl: https://cdn.jsdelivr.net/npm/three@0.180.0/
    entry: build/three.module.js

presentations:
  - id: product-tour
    title: Product Tour
    manifest: ./presentations/product-tour.yaml
```

A project dependency record has exactly two fields:

- `baseUrl`: an absolute HTTPS URL ending in `/`, without credentials, query, or
  fragment, and pinned to an immutable package selection;
- `entry`: a nonempty relative path without a query, fragment, empty segment, `.`, or
  `..`.

Catalog dependencies implicitly use the ESM module loader. Do not add `version`,
`loader`, `license`, integrity, or project-URL fields to a catalog record.

Use the logical key in slide code:

```js
const three = await this.ctx.dependency('three').load();
```

`load()` returns the page-wide promise-memoized module namespace for a catalog
dependency. `import()` remains a module-only compatibility operation and returns the
same namespace. Use `url()` only when an API requires the declared entry URL:

```js
const dependency = this.ctx.dependency('three');
const entryUrl = dependency.url();
```

Do not embed the selected CDN URL in slide code, import `/vividly/vendor/**`, read a
dependency global, or declare dependency selections in presentation manifests.

After adding the selection:

1. run `vividly dependencies` to validate ownership and normalized metadata;
2. run `vividly run`;
3. exercise all affected slides and package features while connected;
4. verify browser and network diagnostics; and
5. use cache-only rehearsal when the presentation must work without network access.

## Upgrade a dependency

A logical key has one project-wide selection. To upgrade it:

1. find every `ctx.dependency()` consumer of the key;
2. review upstream API, behavior, browser support, provenance, and license changes;
3. update the single catalog record;
4. run `vividly dependencies`;
5. test every consumer, not only the slide that motivated the upgrade;
6. exercise newly required resources while connected; and
7. repeat the intended cache-only rehearsal path.

Changing the selected version does not prove compatibility, migrate slide code, or
populate every resource that the new version might request.

## Resolve version conflicts

When imported slides expect incompatible versions, select one compatible project
version and adapt the affected consumers, or replace the package. Vividly does not
solve version constraints.

Giving incompatible versions different logical keys is not a general isolation
mechanism. Every dependency executes in the same browser realm. Packages can still
conflict through globals, custom-element names, prototype changes, shared symbols, or
singleton state. If coexistence cannot be demonstrated, do not present the combination
as supported.

## Remove a dependency

Before removing a catalog entry:

1. confirm that no slide still requests the logical key;
2. remove the catalog record;
3. run `vividly dependencies` to validate the remaining registry; and
4. recheck presentations that previously used the package.

Removing a selection does not clear its old bytes from the global cache. Those bytes
are no longer selected by the project and do not affect runtime lookup.

## Cache preparation and offline rehearsal

These commands answer different questions:

| Operation | What it establishes |
| --- | --- |
| `vividly dependencies` | Which dependency selections are valid and effective |
| Connected `vividly run` | Caches resources requested by the interactions you exercise |
| `vividly thumbnails` | Caches resources requested while rendering selected captures |
| `vividly cache status` | Which project-relevant resources are physically present and healthy |
| `vividly rehearse` | Whether the path you exercise works within the cache-only boundary |

Cache status is not an offline-readiness certificate. It cannot know which transitive
resources future interactions will request.

For an offline-sensitive change:

1. run `vividly run` with network access;
2. visit the relevant presentations, slides, steps, and interactive states;
3. optionally inspect the observed resources with `vividly cache status`;
4. stop the connected server; and
5. run `vividly rehearse`, repeating the intended path in the visible browser.

Rehearsal blocks external HTTP, HTTPS, and WebSocket access and serves dependencies
from the cache only. It fails on a missing dependency resource, blocked external
request, uncaught page error, or page crash. Success makes only this bounded claim:

> The presentation worked without external dependency access for the slides and
> interactions exercised during this rehearsal.

It does not cover unvisited slides, untriggered interactions, arbitrary inputs, or
unsupported URL behavior.

## Troubleshooting

| Symptom | Likely cause and response |
| --- | --- |
| Catalog validation rejects `baseUrl` | Use an absolute pinned HTTPS base ending in `/`, without credentials, query, or fragment |
| Catalog validation rejects `entry` | Use a normalized relative path without query, fragment, `.`, `..`, or empty segments |
| Key conflicts with a runtime dependency | Reuse the runtime-owned key; catalog selections cannot replace it |
| Browser reports a bare specifier | Select a browser-ready ESM artifact or an artifact with resolved relative imports |
| Resource bypasses the local dependency route | Replace or configure absolute and root-relative URLs to stay within supported package-relative behavior |
| Worker works locally but not after static export | Use a browser-ready worker arrangement that does not rely on a conventional relative worker from a cross-origin entry |
| Rehearsal reports a cache miss | Run connected, exercise the exact feature that requests the resource, then rehearse again |
| Two selected packages interfere | Reconcile versions or packages; separate keys do not provide browser-realm isolation |
| Chromium is missing or incompatible | Run `vividly install-browser` in the active Vividly environment |

Failures should remain explicit. Do not work around them with embedded CDN URLs,
ambient globals, silent fallbacks, or copies under runtime-owned paths.

## Dependency change checklist

- [ ] The effective registry was inspected before adding a key.
- [ ] The artifact is browser-ready and selected by a pinned HTTPS base.
- [ ] Upstream identity, version, CDN provenance, and license were reviewed.
- [ ] Slide code uses a logical key rather than a concrete package URL.
- [ ] Every consumer was checked after a project-wide selection changed.
- [ ] Relevant package features and transitive resources were exercised while
      connected.
- [ ] Browser, network, and package compatibility errors were checked.
- [ ] The intended offline path was rehearsed when disconnected use matters.
- [ ] An unused key was removed only after confirming that no consumers remain.

## See also

[Authoring slides](./authoring.md) — the complete slide workflow and definition of
done.

[Slides](./slides.md#browser-dependencies) — the slide-context dependency API and
runtime boundary.

[Command Line](./cli.md) — dependency inspection, cache administration, browser
installation, rehearsal, and export.
