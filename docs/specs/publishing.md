# Publishing Spec

Status: draft

## 1. Purpose

This specification defines how Vividly turns one validated project composition into an
immutable Git publication and pushes it to a branch consumed by GitHub Pages.

Publishing is artifact-first:

```text
committed author site
    + selected runtime
    + publication-owned files
    = complete publication tree
```

Vividly materializes that tree locally. GitHub Pages consumes the committed tree
without installing or invoking Vividly, regenerating thumbnails, or transforming site
content.

This document is the normative publishing contract. The CLI surface is summarized in
[`cli.md`](cli.md), and composition remains governed by
[`runtime-composition.md`](runtime-composition.md).

## 2. Initial scope

The initial publishing contract supports:

- a project contained in a non-bare Git working repository;
- one or more named GitHub Pages targets;
- publication to the root of one configured remote branch per target;
- complete local materialization through the export composition;
- an isolated temporary Git index;
- an initial root publication commit;
- later single-parent publication commits;
- normal non-force pushes;
- deterministic public publication metadata; and
- an ephemeral dry run.

The initial contract does not support:

- GitHub REST or GraphQL APIs;
- automatic GitHub Pages repository configuration;
- provider activation observation;
- Git worktrees;
- dirty-source publication;
- stage-only, commit-only, or redeploy modes;
- rollback command syntax;
- replacing an unrelated existing publication branch;
- Azure, Cloudflare, S3, or another provider; or
- general-purpose CI installation or materialization, except the repository release
  workflow specified in section 18.1.

## 3. Terminology

### Source repository

The containing Git working repository whose `HEAD` identifies the committed source of
the publication. The Vividly project may be the repository root or a directory below
it.

### Author site

The project’s committed `site/` tree.

### Runtime

The selected runtime-owned `/index.html` and `/vividly/**` composition paths.

### Candidate

The complete temporary directory containing the materialized composition plus
publication-owned files.

### Publication tree

The Git tree created from every candidate path and no other paths.

### Publication commit

A commit on the configured publication branch whose root tree is one complete
publication tree.

### Publication

Successful acceptance of a publication commit by the configured remote publication
branch.

### Activation

The later provider operation that makes a publication available from a public URL.
Activation is asynchronous and outside Vividly’s observation boundary.

## 4. Command contract

```console
vividly publish [PATH] [--target TARGET] [--dry-run]
```

`PATH` names the Vividly project root and defaults to the current directory. The
project root contains `vividly.yaml`, `vividly.publish.yaml`, and `site/`.

`--target` selects one configured target by exact, case-sensitive name. When it is
omitted:

- the configured `default` target is selected when present;
- the sole configured target is selected when exactly one target exists; and
- multiple configured targets without `default` are an error.

`--dry-run` performs source, configuration, composition, candidate, remote, and
intended-operation validation without creating candidate-derived Git objects, creating
or updating refs, creating a commit, or pushing. Remote inspection may fetch ordinary
remote objects.

Normal publication prints the resolved project, source revision, target, remote,
publication branch, and configured expected URL before publication writes. The command
does not prompt. Invoking `publish` without `--dry-run` is explicit authorization to
create and push a publication commit.

Success exits 0. A validation, materialization, Git, credential, race, or push failure
prints an actionable diagnostic to stderr and exits 1 without a traceback. A
successful identical-tree no-op exits 0.

## 5. Publishing configuration

### 5.1 Location and parsing

The project root contains one committed `vividly.publish.yaml`. It is a regular,
non-symbolic-link UTF-8 YAML file.

Mappings reject duplicate keys. Missing, unknown, incorrectly typed, and empty required
fields are errors. Boolean values are not integers. Configuration validation completes
before composition or Git writes.

The version 1 shape is:

```yaml
schema: 1
default: pages

targets:
  pages:
    provider: github-pages
    remote: origin
    branch: gh-pages
    expected_url: https://example.github.io/presentation/
    custom_domain: presentation.example.com
```

### 5.2 Top-level fields

The top-level mapping accepts only:

- `schema`, required, the integer `1`;
- `default`, optional, a target name; and
- `targets`, required, a nonempty mapping of target names to target configurations.

`default` must name an entry in `targets`. It is required when `targets` contains more
than one entry and optional when `targets` contains exactly one entry.

A target name is a nonempty string that begins with an ASCII letter or digit and whose
remaining characters are ASCII letters, digits, `.`, `_`, or `-`.

### 5.3 GitHub Pages target

A GitHub Pages target accepts only:

- `provider`, required, exactly `github-pages`;
- `remote`, optional, default `origin`;
- `branch`, optional, default `gh-pages`;
- `expected_url`, optional; and
- `custom_domain`, optional.

`remote` is a nonempty configured Git remote name, not a URL. The remote must resolve
to exactly one push destination. Remote inspection and push use that same destination;
multiple push destinations are unsupported because preflight could not establish the
state of every destination safely.

`branch` is a nonempty branch name accepted by `git check-ref-format --branch`. It must
not equal the current source branch.

`expected_url`, when present, is an absolute `https` URL with a host and without user
information, query, or fragment. It is reporting metadata only. Vividly does not
derive, request, probe, or verify it.

`custom_domain`, when present, is an ASCII DNS name without a scheme, path, port,
query, fragment, wildcard, or trailing dot. Vividly lowercases it before generating
`CNAME`. DNS configuration remains external to Vividly.

The file contains no credentials, tokens, passwords, private keys, transient
deployment identifiers, or machine-specific credential paths. Git authentication uses
the user’s existing Git credential configuration.

## 6. Source and Git preflight

Vividly resolves `PATH` canonically, validates the Vividly project, and locates the
containing Git repository. Publication rejects:

- a project outside a Git working repository;
- a bare repository;
- an unborn or detached `HEAD`;
- a missing source commit;
- a missing Git executable;
- a missing Git author name or email;
- a missing configured remote;
- an unsupported multiple-push-destination remote;
- a publication branch equal to the checked-out source branch; or
- a dirty or in-progress repository.

The entire containing repository must be clean. Clean means:

- no staged changes;
- no unstaged changes;
- no untracked files;
- no unresolved conflicts; and
- no merge, rebase, cherry-pick, or revert in progress.

Ignored files do not make the repository dirty. The rule applies to the entire
repository even when `PATH` names a nested project. Vividly records the full source
`HEAD` object ID and symbolic source branch name. It does not require the source commit
to have been pushed.

Preflight resolves the remote publication branch tip without creating or checking out
a local publication branch and without creating a Git worktree. Fetching may add
ordinary Git objects, but it must not change the current branch, source commit, normal
index, working tree, or an existing local branch.

The remote branch state is either:

- absent, permitting an initial publication; or
- present at one fetched commit that satisfies the recognized-publication contract.

An existing branch with an unavailable, malformed, unrelated, or unrecognized tip is
an error. Vividly never replaces it automatically.

## 7. Candidate materialization

Vividly creates one process-unique directory under the operating system’s temporary
directory, outside:

- the project;
- the containing repository’s Git metadata;
- the author site;
- the selected runtime;
- the Vividly installation; and
- any persistent export destination.

The temporary layout contains at least:

```text
vividly-publish-<random>/
├── candidate/
└── publication.idx
```

Vividly invokes the same composition and export primitive as `vividly export`. It
performs package-mode per-file runtime verification and preserves every composed source
byte. It does not regenerate thumbnails, rewrite author URLs, bundle resources, or add
development-only behavior.

The candidate initially contains exactly the complete export. Vividly then adds the
publication-owned files specified below.

## 8. Publication-owned paths

The root-level publication-owned paths are:

| Path | Required bytes |
| --- | --- |
| `.nojekyll` | empty |
| `CNAME` | normalized `custom_domain` followed by `\n`, only when configured |
| `vividly-publication.json` | canonical metadata defined in section 9 |

These paths are reserved even when a target would not generate the optional `CNAME`.
If the composition already contains a file, directory, or symbolic link at one of
these paths, publication fails. Vividly never silently replaces an author path, even
when its bytes match the generated bytes.

The candidate contains only regular files and directories. Symbolic links and unsafe
relative paths are errors.

## 9. Public publication metadata

### 9.1 Runtime content integrity

Publication runtime integrity identifies the actual runtime paths and bytes included in
the candidate. It is distinct from the runtime-manifest identity defined by the
runtime-composition specification.

For every composed file whose owner is `runtime`, Vividly creates one mapping entry:

```text
absolute deployed URL path -> lowercase SHA-256 of the source bytes
```

The mapping therefore includes `/index.html` and every selected `/vividly/**` path.
Vividly forms this document:

```json
{"files":{"/index.html":"<digest>"},"schema":1}
```

The real `files` object contains every runtime-owned path. Canonical integrity-document
bytes are UTF-8 JSON with keys sorted lexicographically, no insignificant whitespace,
and one trailing line feed. Runtime content integrity is:

```text
sha256:<lowercase SHA-256 of the canonical integrity-document bytes>
```

This identity changes when a runtime path is added or removed or its bytes change. It
therefore identifies package, repository, and path runtime content uniformly, including
intentional editable-runtime divergence.

### 9.2 Manifest shape

The candidate contains `/vividly-publication.json` with exactly:

```json
{
  "runtime": {
    "framework_version": "0.0.1",
    "integrity": "sha256:..."
  },
  "schema": 1,
  "vividly": {
    "distribution_version": "0.0.post1"
  }
}
```

The example is expanded for readability. Canonical file bytes are UTF-8 JSON with keys
sorted lexicographically, no insignificant whitespace, and one trailing line feed.

`vividly.distribution_version` is the active `vividly` Python distribution version.
`runtime.framework_version` is the selected runtime manifest version.
`runtime.integrity` is the runtime content integrity from section 9.1.

The file contains no source revision, publication commit, Git tree ID, timestamp,
runtime source path, installation URL, credential, provider secret, or machine-local
value. A publication commit or tree cannot be embedded because its identity depends on
the file’s own bytes.

Commit trailers and public metadata are generated from one validated in-memory identity
so overlapping values cannot diverge through separate derivation logic.

## 10. Git construction

### 10.1 Git execution

Vividly uses the installed Git executable through argument-safe Python `subprocess`
calls. It does not add GitPython, pygit2, Dulwich, or another Python Git dependency.

The implementation:

- passes arguments as a sequence and never uses `shell=True`;
- never interpolates paths or configuration into a shell command string;
- preserves normal Git configuration and credential handling;
- scopes the temporary index and candidate work tree to individual operations;
- captures stdout and stderr separately;
- reports Git failures without a Python traceback; and
- redacts credentials from displayed remote URLs and Git diagnostics.

### 10.2 Complete tree

Vividly starts the temporary index from an empty tree, adds every candidate file, and
writes one tree. It never reads the previous publication tree into the index.

Every candidate file is stored as a non-executable regular Git blob. The resulting
tree contains every candidate path and no path inherited from an earlier publication.
Removing a candidate path therefore removes it from the active publication tree while
preserving it in older publication commits.

The temporary index never replaces or locks the user’s normal index.

### 10.3 Initial publication

When the remote publication branch is absent, Vividly creates a commit with the
candidate tree and no parent:

```text
source:       A

publication:  P1
```

`P1` is a root commit. The source commit is recorded in metadata but is not a parent.

### 10.4 Later publication

When the remote publication branch points to recognized publication `P1`, Vividly
creates `P2` with:

- the candidate tree; and
- exactly one parent, `P1`.

Publication history remains separate and linear:

```text
source:       A -- B -- C

publication:  P1 -- P2
```

Vividly does not create a merge commit or use the source commit as a parent.

## 11. Commit identity and recognized history

### 11.1 Commit message

The publication commit uses the user’s configured Git name and email as both author and
committer identity. The subject and trailers are:

```text
Publish site from source revision <12-character-source-prefix>

Vividly-Publication: 1
Source-Revision: <full-source-object-id>
Vividly-Distribution: <distribution-version>
Framework-Version: <framework-version>
Runtime-Integrity: <runtime-content-integrity>
Target: <target-name>
Provider: github-pages
```

Trailer names, capitalization, order, and single-value cardinality are normative. The
subject uses the first 12 hexadecimal characters of the source object ID. Values
contain no embedded line ending.

Publication commits are not required to have stable object IDs across machines because
Git author, committer, and timestamp metadata are legitimate commit inputs. The root
tree is the exact site-image identity.

### 11.2 Recognized remote tip

An existing remote publication tip is recognized only when:

- it is a commit with zero or one parent;
- it has exactly one of every required trailer from section 11.1;
- `Vividly-Publication` equals `1`;
- `Provider` equals `github-pages`;
- `Target` equals the selected target name;
- its root tree contains a regular root `vividly-publication.json`;
- that file has canonical version 1 bytes and valid field values; and
- the commit’s distribution, framework, and runtime-integrity trailers equal the
  corresponding public metadata fields.

Recognition establishes that Vividly owns the branch tip and can safely append a
complete replacement tree. It does not require the source revision to be present in
the local repository and does not claim that GitHub Pages is configured or active.

A malformed marker, missing trailer, metadata mismatch, merge commit, or non-publication
tip is unrecognized. Vividly reports the branch and tip and refuses to append or
replace it.

## 12. No-change behavior

After writing the candidate tree, Vividly compares its tree object ID with the fetched
remote publication tip’s tree object ID.

When they are equal:

- no commit is created;
- no push is attempted;
- the existing publication commit remains current;
- the command reports that deployable bytes are unchanged; and
- the command exits 0.

The public metadata omits source revision and timestamps so a later source commit that
does not change deployable bytes remains an identical-tree no-op.

## 13. Push and race behavior

Vividly pushes the generated commit directly to:

```text
refs/heads/<configured-branch>
```

It uses an ordinary non-force push. It never uses `--force`, force-with-lease, ref
deletion, remote reset, or history replacement.

The push is accepted only when:

- the branch is still absent for an initial publication; or
- the branch still points to the parent used for a later publication.

If another publisher creates or advances the branch after preflight, the push fails.
Vividly reports a publication race, leaves the remote unchanged by its own attempt, and
directs the author to rerun publication from a newly validated source state.

Publication succeeds at the Git boundary when the remote accepts the commit. Provider
activation is not part of command success.

## 14. Dry run

Dry-run performs:

- project and configuration validation;
- whole-repository clean-state validation;
- Git executable, identity, remote, and branch validation;
- remote branch discovery and recognized-tip validation;
- complete composition and package-runtime verification;
- candidate materialization;
- runtime content-integrity calculation;
- publication-owned path collision validation;
- public metadata generation; and
- determination of whether publication would be initial, changed, or unchanged.

Dry-run removes the candidate before exiting. It does not populate a temporary Git
index, write candidate-derived blobs, trees, or commits, create or update refs, or
push. Remote inspection may add fetched objects to the local object database.

Dry-run reports the intended target, branch, source revision, expected URL, runtime
identity, and operation classification. Because it does not write a Git tree, its
changed/unchanged classification compares candidate path, non-executable mode, and Git
blob identities with the fetched publication tree.

## 15. Branch and checkout safety

Publishing never:

- switches the current branch;
- detaches `HEAD`;
- modifies the source commit;
- modifies or locks the user’s normal index;
- modifies or deletes working-tree files;
- creates or checks out a local publication branch;
- creates or registers a Git worktree;
- resets or deletes an existing ref;
- stashes user content; or
- requires the author to restore a source checkout after failure.

The command may add ordinary unreachable blobs, trees, or commits to the local object
database before a later failure. They are harmless and eligible for normal Git garbage
collection.

## 16. Temporary resources and cleanup

Normal success, no-op, dry-run, and handled failure remove:

- the candidate directory;
- the isolated index; and
- an adjacent isolated-index lock, when present.

Abrupt termination or machine failure may leave these files in the operating system’s
temporary directory. They are not registered with Git and are safe to delete when no
publication process is using them.

Verbose or diagnostic output exposes the temporary root while it exists. Vividly does
not recommend manually deleting Git objects or running immediate garbage collection.

A crash after a successful push is not a cleanup case. The publication succeeded and
may later activate at the provider.

## 17. Failure boundaries

### Preflight failure

No candidate, publication tree, commit, push, or deployment change is created. A remote
inspection may have transferred ordinary Git objects.

### Materialization or metadata failure

The candidate is removed. Source checkout and remote branch remain unchanged.

### Tree or commit failure

Temporary resources are removed. Source checkout and remote branch remain unchanged.
Unreachable Git objects require no manual cleanup.

### Push rejection or transport failure

The source checkout remains unchanged. Vividly distinguishes:

- authentication or authorization failure;
- unavailable remote;
- branch protection or policy rejection;
- publication race; and
- another Git rejection when Git supplies the distinction.

Vividly never retries with force.

### Successful push

The publication commit and branch are reported. Failure to activate or serve the site
later does not retroactively make the Git publication fail.

## 18. GitHub Pages boundary

The author performs one provider control-plane operation outside Vividly: configure the
repository in GitHub’s Pages settings to deploy from the configured publication branch
root.

After that setup:

```text
Vividly pushes publication commit
    -> GitHub observes branch update
    -> GitHub Pages asynchronously activates branch contents
```

Vividly:

- uses standard Git transport over SSH or smart HTTPS;
- does not call GitHub REST or GraphQL APIs;
- does not configure repository Pages settings;
- does not generate a GitHub Actions workflow;
- does not install or run in provider automation;
- does not poll deployment status; and
- does not claim that a particular commit is live.

An unauthenticated HTTP request to `expected_url` cannot prove activation because
provider delay and cache state are ambiguous. Vividly therefore reports the configured
URL and that activation is not observed.

For a custom domain, Vividly commits `CNAME`. The author configures DNS separately.

### 18.1 Vividly repository releases

Vividly's own repository may run a manually dispatched release workflow from `main`.
This exception does not change the ordinary `vividly publish` command or require
Actions in author projects.

The workflow selects a full source commit and an ordinary `0.x.y` version. The source
must be clean, on `main`'s history, and descend from `stable`. Package, runtime manifest,
runtime text, and project-selector versions must agree. New releases advance the
version on `stable` and require an unused PyPI version and tag.

The workflow runs reusable CI, then builds and checks the wheel and sdist once and
saves them as a short-lived workflow artifact. The `pypi` environment gates upload.
Trusted Publishing uploads those saved files, skipping files PyPI already has, and an
isolated PyPI installation is smoke-tested. Promotion then creates the annotated
version tag and fast-forwards `stable` without force. Finally the workflow calls the
Pages deployment workflow for the released source commit, including for releases that
change only Python code.

Recovery uses GitHub's **Re-run failed jobs** on the same run, which reuses that run's
saved distributions. A re-run accepts an already existing matching tag and an already
advanced `stable` at the same source. Starting a new run for a version already present
on PyPI fails; after the saved distributions expire, the maintainer releases a new
version. No failure authorizes a force push, tag replacement, or version reuse. PyPI
publication and Pages deployment share no state: a Pages failure never affects a
completed PyPI release.

### 18.2 Repository site deployment

Vividly's own repository deploys its site with a Pages Actions workflow rather than
`vividly publish`. Generated thumbnails are ignored by Git in this repository. The
workflow checks out one commit, installs Chromium, regenerates thumbnails with
`vividly thumbnails`, exports the site with the public-site exporter, and deploys it
with GitHub's Pages actions. It does not push a publication branch, keeps no site
history, and retains its Pages artifact only briefly.

Manual dispatch deploys the dispatched `main` commit. The release workflow calls it
with the released source commit. Deployments are serialized without cancellation; the
most recent deployment determines the live site. A failed deployment is recovered by
re-running it.

A repository-local `release` command dispatches the Release workflow on `main` with an
explicit full source SHA and version. It uses locked local dependencies, checks GitHub
authentication, and targets `MikeHopcroft/vividly`. Dispatch returns the exact workflow
run URL; optional waiting observes that run and exits nonzero on failure without
bypassing environment approvals. The site is deployed on its own with
`gh workflow run deploy-pages.yml --ref main`.

## 19. Security and diagnostics

Vividly never prints credentials embedded in a remote URL, credential-helper output, or
provider error payload. Diagnostics identify the configured remote by name and display
a sanitized destination when useful.

Configuration-derived target, branch, path, URL, and domain values are passed as
individual subprocess arguments or validated file bytes, never shell syntax.

Publication rejects symbolic links and unsafe paths. It writes only below the
process-unique temporary root and to Git’s ordinary object database, then requests one
normal remote ref update.

No secret belongs in `vividly.publish.yaml`, `vividly-publication.json`, a publication
commit message, or the publication tree.

## 20. Deferred behavior

The following require later specifications:

- project-relative clean-state rules for monorepos;
- persistent candidate inspection;
- guided publishing setup;
- rollback command syntax and selection;
- shared neutral branches across providers;
- cache-measurement automation;
- Azure, Cloudflare, and S3 targets; and
- general-purpose source-triggered CI materialization.

Later work may add providers, but it cannot weaken the initial GitHub Pages guarantees
without an explicit specification revision.
