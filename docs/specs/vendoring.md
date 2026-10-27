# Vendoring Specification

Status: draft. Defines the Stage 7 ownership, provenance, integrity, licensing, and
conflict contract. Command spelling and the complete manifest schema may be refined
before implementation, but implementations must preserve these semantics.

## 1. Purpose

Vendoring makes third-party browser artifacts durable, reviewable, offline-capable, and
license-compliant without adding a build step to ordinary Vividly development.

The contract supports both Vividly's framework dependencies and author projects built
from dependency-heavy HTML SPAs. It does not impose an artifact-count limit or assume
that a typical presentation resembles Vividly's currently small runtime dependency
set.

Vendoring is a rare maintenance operation:

```text
declared sources + committed acquisition lock
                    ↓ refresh
committed browser artifacts + licenses + notices + output lock
                    ↓ ordinary use
edit JavaScript/CSS → preview, export, and present without Node or a network
```

## 2. Non-goals

Stage 7 does not:

- bundle, transpile, minify, or tree-shake Vividly-authored source;
- make framework-private packages an author API;
- infer a license from a filename or package registry field alone;
- choose a winning version when dependency requirements conflict;
- rewrite slide imports automatically;
- fetch dependencies during preview, export, or presentation playback; or
- require Node for users who do not add or refresh vendored dependencies.

## 3. Vendoring workspace

A repository or author project that refreshes dependencies has a committed authoring
workspace outside its deployed `site/` tree:

```text
vendor/
├── vividly-vendor.yaml       # desired artifacts, scopes, sources, and output maps
├── vividly-vendor-lock.json  # generated output hashes and resolved provenance
├── package.json              # maintainer tool and npm acquisition inputs
└── package-lock.json         # public-registry npm lock
```

The workspace can describe hundreds of logical artifacts. It is not copied into the
deployed site. Generated browser artifacts, required license texts, and notices are
committed so a clone can preview and export without installing Node packages.

The npm project exists only for vendoring. Its scripts invoke committed local tooling;
the workflow does not use unpinned `npx`. The public-registry lock is canonical.
Contributor-specific proxy URLs and regenerated proxy locks are not committed.

Package installation disables lifecycle scripts by default. An artifact that requires
an install script needs an explicit reviewed exception in the manifest.

### 3.1 Node boundary

Node is required to add, resolve, refresh, or transform npm-backed dependencies. It is
not required to use committed vendored output.

An author can copy, preview, export, and present a self-contained slide whose browser
artifacts, lock metadata, licenses, and notices are already committed. The Python
tooling may verify those files without Node. Node becomes necessary when importing the
slide requires a new concrete package version, reconciliation with presentation-owned
dependencies, or regeneration of browser-ready output.

The product therefore distinguishes:

- **dependency consumers**, who use and validate committed vendored artifacts with
  Python-only Vividly; and
- **dependency maintainers**, who install Node to change the dependency graph.

Copying a pre-vendored slide must not trigger an implicit network request or Node
installation. If its declared requirements cannot be satisfied by the destination,
the import fails with the conflicting requirements and explains that dependency
maintenance is required.

## 4. Ownership scopes and output paths

Every manifest entry declares one scope and target. Artifact identifiers are unique
within that target and are safe lowercase path segments.

| Scope | Target identity | JavaScript and related output | Font output |
| --- | --- | --- | --- |
| Framework | Selected Vividly runtime | Runtime source `vividly/vendor/<artifact-id>/` | Runtime source `vividly/fonts/<artifact-id>/` |
| Project | Complete author-owned site | `site/vendor/<artifact-id>/` | `site/fonts/<artifact-id>/` |
| Presentation | Stable catalog presentation ID | `site/vendor/presentations/<presentation-id>/<artifact-id>/` | `site/fonts/presentations/<presentation-id>/<artifact-id>/` |
| Slide module | Canonical module directory | `<module>/vendor/<artifact-id>/` | `<module>/fonts/<artifact-id>/` |

Framework paths deploy beneath `/vividly/**` and remain framework-private. Author
artifacts never enter that namespace.

A slide target names a module, not a manifest instance. A command may accept a
presentation ID and slide address as a convenient selector, but it resolves that
instance to its module directory. If several instances or presentations use that
module, they share the module-owned vendored artifact.

Reusable slide modules may instead declare dependency requirements that a destination
presentation must resolve. The slide declaration records compatible versions, loading
model, and required browser identities; the presentation vendoring lock selects the
concrete artifacts. This is the preferred model for packages that cannot coexist
safely in one browser document. A slide-local copy is appropriate only for a
self-contained dependency whose coexistence has been verified.

Presentation scope is explicit even though presentation manifest placement is only a
convention. The stable catalog presentation ID determines its namespace; moving the
manifest does not move vendored output.

The assistant must support all four scopes through one acquisition, integrity, and
license pipeline. It may add many artifacts in one operation. It must not duplicate its
implementation for framework and author-owned targets.

## 5. Logical artifact records

One manifest entry describes one logical artifact, which may produce any number of
files. Each entry records at least:

- stable artifact ID;
- human-readable name;
- requested version or immutable release identity;
- source type and upstream project URL;
- exact npm package and version, or exact download URL and source SHA-256;
- scope and target;
- ordered source-to-output file mappings;
- loading model;
- SPDX license expression;
- upstream license and required notice files;
- whether reviewed lifecycle scripts are required; and
- any declared public global or import specifier.

Supported loading models include:

- relative ESM;
- classic script with an optional global name;
- CSS;
- font;
- WebAssembly;
- worker;
- data; and
- a multi-file package combining those forms.

### 5.1 Acquisition modes

The vendoring workflow supports three distinct acquisition modes:

1. **Locked package copy.** Run `npm ci`, then copy declared browser-ready files from an
   exact package into stable output paths. npm supplies acquisition and package
   integrity; Vividly still records selected output hashes and license material.
2. **Immutable URL.** Download a version-pinned release or CDN artifact with a declared
   SHA-256. The CDN is transport only. The entry separately identifies the upstream
   project and immutable license and notice inputs.
3. **Declared conversion.** When a package does not publish browser-ready files, run a
   pinned, package-specific conversion from locked inputs. The record includes the tool
   and version, entry points, options, complete inputs, outputs, and license coverage.

The initial implementation should support locked package copies and immutable URLs
before general conversion. It must not build from a package merely because npm was
used to acquire it. Vividly-authored source is never an input to dependency conversion.

### 5.2 Font artifacts

Font entries additionally declare family, style, weight, stretch, subset, source
format, and whether the bytes are copied unchanged or transformed. Refresh copies
selected upstream web-font files into the target scope and generates deterministic
`@font-face` CSS with stable relative URLs. A scope-specific CSS family alias may avoid
author-level name collisions without modifying the font binary.

Prefer, in order:

1. a locked package containing browser fonts and license files;
2. a pinned upstream release archive containing both;
3. immutable individual font and license URLs; and
4. a dynamic font-service CSS endpoint only when no reproducible source exists.

Dynamic endpoints whose output varies by request headers or browser are not acceptable
without capturing and hashing every returned CSS and font byte. Subsetting, format
conversion, or binary modification is a declared transformation and requires explicit
license-policy review, including any reserved-name obligation.

The manifest describes desired inputs. `vividly-vendor-lock.json` records resolved
package identities, source integrity, every generated output path and SHA-256, license
file hashes, notice inputs, and the vendoring-tool schema version. Entries and output
paths use deterministic ordering.

## 6. Refresh and check behavior

The assistant provides three semantic operations:

1. **Add or update** edits the desired manifest for a selected scope and target.
2. **Refresh** performs locked acquisition, stages the complete result, validates it,
   and atomically replaces only declared generated outputs.
3. **Check** verifies committed outputs, licenses, notices, and the output lock without
   modifying files.

Refresh fails before replacing output when:

- an input is not locked or its integrity does not match;
- a requested file is absent or maps outside its target root;
- two entries produce the same path;
- an unknown existing file would be removed or overwritten;
- required license or notice material is unavailable;
- a license requires explicit review that has not been recorded;
- generated notices or lock data would be incomplete; or
- the dependency graph violates the conflict rules in section 8.

Refresh never runs as part of preview, thumbnail generation, export, publication, wheel
installation, or presentation playback. Those consumers use and verify committed
outputs.

## 7. License and notice contract

Every shipped third-party byte belongs to exactly one logical artifact record and must
have:

- declared upstream provenance;
- an SPDX license expression or an explicit reviewed non-SPDX designation;
- complete required license text committed with the artifact;
- required copyright, attribution, and notice material;
- source and output integrity records; and
- inclusion in the owning scope's generated aggregate notice.

Artifact-local license material travels with a copied slide module or vendored
directory. Aggregate notices make the complete deployed site auditable:

- framework dependencies contribute to `/vividly/THIRD_PARTY_NOTICES.txt`;
- all author-owned project, presentation, and slide dependencies contribute to
  `/THIRD_PARTY_NOTICES.txt`.

The aggregate notice names the artifact, version, scope, deployed paths, upstream,
license expression, and colocated license path. It is generated deterministically and
is not hand-edited.

Missing or ambiguous license evidence is an error, not a warning. The initial
Highlight.js GitHub Dark stylesheet remains unresolved until its derivation and license
obligations are verified. Stage 6B cannot publish while any shipped artifact is
unresolved.

A package registry, release host, or CDN provides bytes; it does not prove that
Vividly's redistribution obligations are satisfied. For an immutable-URL source, the
manifest separately records the canonical upstream project, release identity, license
expression, and immutable license and notice URLs with hashes. A license header in a
minified artifact or a CDN's own compliance practice is not sufficient evidence.

The same rule applies to fonts. Refresh commits the complete applicable font license
beside the font files and records required attribution in the aggregate notice. The
tool verifies declared evidence and policy decisions; it does not provide a legal
opinion or infer permission from availability on a font service.

## 8. Dependency graph and version conflicts

The assistant models declared and transitive dependencies as a graph keyed by exact
resolved package identity, not as a flat list of filenames.

Physical placement at different URLs proves only file isolation. It does not prove
runtime coexistence: packages may share globals, custom-element registries, CSS names,
font families, DOM modifications, singleton state, import-map specifiers, workers, or
other browser-wide identities. Presentation scope is therefore the default resolution
boundary for reusable slides with external package requirements. It is an ownership
and compatibility boundary, not a separate JavaScript realm.

Because several presentations can run sequentially in the same Vividly document,
classic globals and other persistent browser-wide identities are checked across the
complete project even when their files are presentation-scoped. Presentation scope
does not authorize two incompatible global versions; it only keeps ownership and
ordinary dependency selection attached to the presentation that uses them.

The default rules are conservative:

1. Framework dependencies are private and never satisfy author requirements.
2. A reusable slide declares compatible dependency requirements; its destination
   presentation selects exact versions.
3. Dependencies in different slide-module targets are only physically isolated.
   Different exact versions may coexist only after their loading model and browser-wide
   identities have been explicitly verified as coexistence-safe.
4. Byte-identical dependencies may be deduplicated only within one ownership target and
   only when the output paths used by consumers remain stable.
5. A shared project or presentation dependency has one exact resolved version.
6. The assistant never silently chooses the newest, nearest, or first version.
7. Conflicting classic globals, import-map specifiers, CSS global names, or other
   singleton browser identities are errors across the complete project unless the
   manifest records an explicit isolation mechanism.
8. Framework globals loaded by the shell are reserved; author dependencies cannot
   replace or reinterpret them.

A diamond is compatible only when the shared dependency resolves to one exact version
accepted by both branches, or when each branch has an explicitly verified isolation
mechanism. Different relative URLs alone do not establish isolation. Otherwise refresh
fails with both dependency paths, requested ranges, resolved versions, scopes, browser
identities, and remediation choices.

Vendoring alone does not create a new browser realm. Packages that fundamentally
require incompatible singleton environments need a separately designed isolation
feature such as an iframe or worker, or they cannot appear together in one
presentation.

Stage 7 must test at least:

- repeated use of one exact dependency in a scope;
- two slide modules using different relative-ESM versions, including shared-state and
  custom-element counterexamples;
- a compatible shared transitive diamond;
- an incompatible transitive diamond that can remain isolated;
- an incompatible shared/global diamond that must fail;
- two classic scripts claiming the same global;
- two import-map entries claiming the same specifier; and
- fonts or CSS declaring colliding global family or layer names.

The investigation may justify explicit import maps or another isolation mechanism. It
must not weaken the no-silent-selection rule.

## 9. Determinism and offline operation

Given the same desired manifest, acquisition locks, vendoring-tool version, and source
artifacts, refresh produces the same paths and bytes. Generated files contain no
timestamps, host paths, registry credentials, proxy URLs, or machine-specific metadata.

Check validates output SHA-256 values without network access. A clean clone can run,
capture thumbnails, export, and present entirely offline from committed files. Network
access is limited to explicit add or refresh operations.

## 10. Source remains directly runnable

Vividly source and author slide source remain browser-native and unbundled. Vendoring
may select an upstream distribution file or perform a narrowly declared package
conversion during refresh, but it does not compile Vividly's own runtime or an author's
slide code.

The development and exported artifacts execute the same committed files. Optimization
experiments that would create separate development and release code paths remain
outside Stage 7.
