# Releasing Vividly

Vividly has two maintainer entry points, both GitHub Actions workflows run from `main`:

- the [Release workflow](../.github/workflows/release.yml) publishes one exact
  committed source to PyPI, tags it, advances `stable`, and deploys the site; and
- the [Deploy Pages workflow](../.github/workflows/deploy-pages.yml) deploys the site
  without a PyPI release.

Generated thumbnails are not committed in this repository. Both paths regenerate them
in CI before deploying. Run `vividly thumbnails` locally to preview them.

## One-time setup

1. Push the workflows and their helpers to `main`.
2. Create a GitHub environment named **`pypi`**:
   - allow deployments from `main` only;
   - configure an approval rule if supported by the repository's GitHub plan;
   - for a sole maintainer, leave **Prevent self-review** disabled.
   The workflow alone does not create an approval rule. Configure this before dispatch.
3. Add a Trusted Publisher to the existing **`vividly`** PyPI project:

   | PyPI field | Value |
   | --- | --- |
   | Owner | `MikeHopcroft` |
   | Repository | `vividly` |
   | Workflow filename | `release.yml` |
   | Environment | `pypi` |

   No PyPI token or GitHub secret is needed.
4. In repository **Settings → Pages**, select **GitHub Actions** as the deployment
   source. Allow `main` in the `github-pages` environment's deployment rules.
5. Ensure repository rules allow the promotion job's `GITHUB_TOKEN` to create release
   tags and make ordinary fast-forward pushes to `stable`. Keep force pushes, tag
   replacement, and deletion prohibited.

## Release to PyPI and deploy Pages

1. Commit the shared package/runtime version and all source changes. Do not change
   versions during a release.
2. Dispatch the Release workflow with a full committed source SHA and its committed
   version, either from **Actions → Release → Run workflow** on **main**, or with the
   maintainer script. For example, replacing `<full-source-sha>` and `0.0.3`:

   ```bash
   bash tools/release.sh --source-commit <full-source-sha> --version 0.0.3 --wait
   ```

   ```powershell
   pwsh -File tools/release.ps1 --source-commit <full-source-sha> --version 0.0.3 --wait
   ```

3. The workflow runs `validate` (reusable CI), then `build`, which checks source and
   version eligibility, builds the wheel and sdist once, checks them, and smoke-tests
   the wheel. The distributions are saved as a workflow artifact for 7 days.
4. Approve the `pypi` environment. `publish` uploads the saved distributions with
   Trusted Publishing and smoke-tests the PyPI installation. `promote` creates the
   annotated `vX.Y.Z` tag and fast-forwards `stable`. `pages` then deploys the site
   from the released source commit, even for releases that change only Python code.
   Approve `github-pages` separately if its environment requires it.
5. Confirm the live site.

Nothing automatically bumps versions, creates a GitHub Release, or releases on push.

### Maintainer script

The `release` scripts are specific to `MikeHopcroft/vividly`. Bash and PowerShell
entry points share [one implementation](../tools/maintain.py). They only dispatch the
Release workflow on `main`; they do not bump versions, upload packages locally,
approve environments, or push. They require `uv` and the GitHub CLI (`gh`),
authenticated with `gh auth login --hostname github.com` using an account allowed to
dispatch this repository's workflows. For `--wait`, use authentication supported by
`gh run watch` (fine-grained PATs are not supported by that command).

The script prints the exact workflow run URL. Without `--wait`, success means the
workflow was requested. With `--wait`, it waits for that run and returns nonzero on
failure; approvals must still be granted in GitHub. Run it with `--help` for its
arguments.

## Deploy the site without a PyPI release

Commit and push the site changes to `main`, then run:

```bash
gh workflow run deploy-pages.yml --ref main
```

Or use **Actions → Deploy Pages → Run workflow** on **main**. The workflow deploys the
dispatched `main` commit. It does not publish to PyPI or change `stable` or tags.

Deployments do not cancel each other, and the most recent one determines the live
site. A release deploys its own source commit, so a release of an older commit can
replace a newer manual deployment; dispatch Deploy Pages again to restore `main`.

## Recovery

Recover with **Re-run failed jobs** on the same Release run. It reuses that run's saved
distributions and re-runs only the failed jobs and the jobs after them.

- **Before `publish`:** fix the error and start a new run. Source changes require a new
  committed SHA.
- **`publish` failed partway:** re-run failed jobs. Files already on PyPI are skipped
  and only the missing files from the same build are uploaded.
- **`promote` failed:** correct the authorization or ruleset issue and re-run failed
  jobs. An existing matching tag and an already advanced `stable` are accepted.
- **`pages` failed:** re-run failed jobs, or dispatch Deploy Pages directly. A Pages
  failure never affects the completed PyPI release.
- **Re-running all jobs, or a new run, after any upload:** `build` fails because the
  version already exists on PyPI. Use **Re-run failed jobs** instead.
- **Saved distributions expired (after 7 days):** bump the version and release again.
  Never rebuild and re-upload an already published version.

The workflow never rewinds `stable`, replaces tags, or force-pushes.
