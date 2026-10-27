Run these commands from the folder where you keep your projects:

```sh
vividly provision growth-demo
cd growth-demo
```
Vividly will summarize its provisioning plan and then prompt you to continue. If all looks good, enter 'y'. The result will be a new folder, populated with a one-slide starter presentation.

```text
growth-demo/
|-- .github/      # Instructions and skills for your agent
|-- .gitignore    # Files Git should ignore
|-- .vividly/     # Vividly-managed runtime and documentation
|-- site/         # Your starter presentation
`-- vividly.yaml  # Vividly project configuration
```

## Give your agent the right workspace
Start a fresh agent conversation in this folder. Use a mode that can edit files, and allow the agent to read the Vividly instructions in the `.github` folder.

You do not need to understand the the projecxt structure or JavaScript to create a slide - your agent will take care of this.

<details>
<summary>What did provisioning do?</summary>

* Copied the Vividly runtime and agent-facing documentation to the `.vividly/` folder.
* Pinned the version of the runtime in `vividly.yaml`.
* Configured agent instructions and skills in the `.github/` folder.
* Created an initial presentation in the `site/` folder.
* Created an initial `.gitignore` file.

See the [command-line reference](#/documentation/cli) for provisioning and upgrades.

</details>
