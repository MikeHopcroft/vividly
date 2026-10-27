# Markdown composition

The Markdown control renders ordinary prose, syntax-highlighted code, and trusted HTML
in the same light-DOM region.

<markdown-controls-callout label="Slide-defined element">
This content was preserved by the Markdown renderer and upgraded by the slide module.
</markdown-controls-callout>

```js
class MarkdownControlsCallout extends HTMLElement {
  connectedCallback() {
    this.dataset.upgraded = 'true';
  }
}
```