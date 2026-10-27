## "vividly: command not found"

Open a new terminal after installation. For a uv tool installation, run `uv tool update-shell` and restart the terminal. Confirm the tool is installed with `uv tool list`.

If installation itself failed, read that error first. A package-policy failure is not a PATH problem; use your organization's approved package source.

## The agent did not follow the Vividly instructions

Open the provisioned project as the workspace root, not only its `site` subfolder. Use an agent mode that can read and edit files.

Ask it to read the workspace's instructions and Vividly authoring skill, inspect the existing catalog and manifest, and report which presentation it is changing.

## The server will not start

Run `vividly run` from the folder containing `vividly.yaml`. If the port is already occupied, use another:

```sh
vividly run --port 8090
```

Open the URL printed by that process, not a remembered URL for another server.

## I see the catalog, not my slide

The catalog is the normal entry point. Select the presentation and then its slide, or use the exact route reported by the agent. The walkthrough requests `#/vividly/growth`.

If that route does not resolve, ask the agent to verify both IDs against `site/catalog.yaml` and the presentation manifest.

## The slide is blank or the numbers are wrong

Report the exact route, the observed behavior, and any browser-console error to your agent.

For the starter example, test 0%, 8%, and 20%. At 0%, $1,000 must remain $1,000. Do not accept an attractive chart in place of a correct model.

## Publish says the repository is dirty

Run `git status` at the project root. The requirement covers the whole containing repository, including untracked files. Review and commit intended source changes; do not delete or stage unknown files just to make the check pass.

## The push succeeded, but the public site is not ready

Check GitHub **Settings > Pages** for the branch and deployment status. The branch is `gh-pages`, with `/ (root)` selected. Activation is asynchronous.

Check the deployed base address before adding the slide route. `expected_url` in the configuration is metadata and can be mistyped.

For credential, history, or remote errors, follow the [publishing reference](#/documentation/publishing). Do not force-push to work around them.
