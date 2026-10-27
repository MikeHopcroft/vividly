## Start with the smallest change

You do not need to extend the framework to make a distinctive presentation. Slides are browser-native modules, and most customization belongs in author-owned files under `site/`.

## Change the visual language

Ask your agent to create an author-owned theme stylesheet and select it in the presentation manifest. Use shared theme tokens for color, type, and spacing; keep slide-specific layout in that slide's stylesheet.

```text
Create a theme under site/themes/ for this presentation.
Use a warm light background, dark text, and a restrained blue accent.
Preserve focus visibility and contrast. Select the new theme in
the presentation manifest; do not modify the Vividly runtime.
Check the growth slide at presentation size and in a narrow window.
```

## Reuse before you extend

- **Different content, same behavior:** reuse a slide module with another data root or concise props.
- **A standard content region:** use a [built-in control](#/documentation/controls).
- **A reusable interactive region:** consider a custom element.
- **A slide with its own steps:** use a slide module.
- **A browser package:** inspect the dependency registry before adding one.

Read the [slide model](#/documentation/slides) and [authoring procedure](#/documentation/authoring) for these boundaries.

## Add a dependency deliberately

```sh
vividly dependencies
```

Packages are selected in the catalog and accessed by logical key through the slide context. Do not paste a CDN script tag into a slide or read library globals.

See [browser dependencies](#/documentation/dependencies) for selection, loading, caching, and offline verification.

## Keep the runtime boundary intact

Do not create author content under `site/vividly/` or edit the supplied runtime to change one presentation. A framework-level behavior change is a separate engineering task, not a prerequisite for making your next slide.
