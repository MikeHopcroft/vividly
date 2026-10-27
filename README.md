<p align="center">
  <img
    src="https://mikehopcroft.github.io/vividly/vividly/assets/logo-cropped.svg"
    alt="Vividly"
    width="80%"
  >
  <!-- https://mikehopcroft.github.io/vividly/vividly/assets/logo-cropped.svg -->
</p>

---

**Make complex ideas move.** 

Vividly is an agent-oriented toolkit for creating visually stunning, interactive web presentations.

Vividly allows you to focus all your creative energy on ***the vision*** and ***the story telling***. Coding agents ***bring your vision to life***.

Since Vividly presentations are just web apps, anything that runs in the the browser can be incorporated into your presentation.

**Status: Pre-alpha.** Expect rough edges and changes to commands, APIs, and project formats.

## Links

* [Why Vividly?](https://mikehopcroft.github.io/vividly/#/vividly/opening)
* [See It Work](https://mikehopcroft.github.io/vividly/#/vividly/gallery/overview)
* [Get Started](https://mikehopcroft.github.io/vividly/#/vividly/make-something/choose-your-path)
* [Documentation](https://mikehopcroft.github.io/vividly/#/vividly/documentation/overview)

## Examples

Explore four interactive examples. Each opens with an introduction explaining what to watch for and how to start the demo.

| [Tic-Tac-Toe](https://mikehopcroft.github.io/vividly/#/vividly/gallery/tic-tac-toe/introduction) | [Inverted](https://mikehopcroft.github.io/vividly/#/vividly/gallery/inverted/introduction) |
|:---:|:---:|
| [![Tic-Tac-Toe neural network showing board encodings, weights, and computations](https://mikehopcroft.github.io/vividly/slides/tic-tac-toe/introduction/assets/gallery-card.png)](https://mikehopcroft.github.io/vividly/#/vividly/gallery/tic-tac-toe/introduction)<br>Explore the math inside a neural network, play against it, and train it in your browser. | [![Dictionary entry for aglet circled in red](https://mikehopcroft.github.io/vividly/slides/inverted/introduction/assets/gallery-card.png)](https://mikehopcroft.github.io/vividly/#/vividly/gallery/inverted/introduction)<br>Discover inverted indexes through dictionary close-ups, concordances, and animated merging. |
| **[Cheese Context](https://mikehopcroft.github.io/vividly/#/vividly/gallery/cheese-context/introduction)** | **[Conway's Game of Life](https://mikehopcroft.github.io/vividly/#/vividly/gallery/life/introduction)** |
| [![Software project artifacts with highlighted regions representing an agent's context](https://mikehopcroft.github.io/vividly/slides/cheese-context/introduction/assets/gallery-card.png)](https://mikehopcroft.github.io/vividly/#/vividly/gallery/cheese-context/introduction)<br>See how an agent's context reveals fragments of a project through a Swiss-cheese visual metaphor. | [![Gosper glider gun producing moving patterns in Conway's Game of Life](https://mikehopcroft.github.io/vividly/slides/life/introduction/assets/gallery-card.png)](https://mikehopcroft.github.io/vividly/#/vividly/gallery/life/introduction)<br>Watch four simple rules create stable structures, oscillators, gliders, and surprising complexity. |

## Get started

Describe your vision to a coding agent, then collaborate on the slides while
previewing them in your browser. You do not need to clone this repository to create
a presentation.

Follow the [getting-started guide](https://mikehopcroft.github.io/vividly/#/vividly/make-something/choose-your-path),
or give your agent the directly readable
[bootstrap instructions](https://github.com/MikeHopcroft/vividly/blob/main/src/vividly/resources/reference/agentic-bootstrap.md).
For example:

```text
Read https://raw.githubusercontent.com/MikeHopcroft/vividly/main/src/vividly/resources/reference/agentic-bootstrap.md
and help me set up Vividly. Then create an interactive slide demonstrating how
planetary gears work, with controls for locking different gears.
```

## Documentation

- [Human documentation](https://mikehopcroft.github.io/vividly/#/vividly/documentation/overview)
  covers getting started, presenting, and sharing.
- [Agent reference index](https://github.com/MikeHopcroft/vividly/blob/main/src/vividly/resources/reference/agentic.md)
  routes coding agents to setup, authoring, command-line, and publishing guidance
  in Markdown, without requiring the interactive documentation site.

In an existing project, agents should follow the project's copilot instructions and the version-matched documentation
`.vividly/reference/` rather than the latest documentation from the repo.

## Contributing

To work on Vividly itself, see the
[contributor guide](https://github.com/MikeHopcroft/vividly/blob/main/CONTRIBUTING.md)
for development setup and focused validation, and the
[release guide](https://github.com/MikeHopcroft/vividly/blob/main/docs/releasing.md)
for maintainer publication procedures.

## Credits

Images in the example presentations were generated with ChatGPT and Claude. Dictionary and
concordance text in the Inverted example is adapted from Webster's Revised Unabridged
Dictionary (1913, public domain), with additions.

## License

Vividly is available under the [MIT License](LICENSE).
