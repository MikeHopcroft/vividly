Install the CLI using either `uv`
```sh
uv tool install vividly
```

or `pipx`
```sh
pipx install vividly
```

Then check the installation

```sh
vividly --version
vividly --help
```

You should see the Vividly version number and then a help message. You're now ready to create a workspace.

<details>
<summary>Installation help</summary>

If uv installed the tool but your shell cannot find `vividly`, run

```sh
uv tool update-shell
```

and restart your terminal.

If pipx installed the tool but your shell cannot find `vividly`, run
```sh
pipx ensurepath
```
and restart your terminal.

[Still stuck?](#/documentation/troubleshooting)

</details>

