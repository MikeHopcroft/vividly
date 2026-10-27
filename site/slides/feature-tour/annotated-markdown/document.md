<vividly-document-header title="Annotated Markdown">
A document reader whose annotations form the slide's step sequence.
</vividly-document-header>

# Controls and slides

Vividly controls render regions of a slide. They expose state as properties and events,
but they do not know about the presentation's step axis.

<vividly-annotation title="The control boundary">
The viewer can appear beside other content or more than once on a slide. That makes it
a control rather than a slide module.
</vividly-annotation>

## A thin adapter

The reusable slide module loads this document, counts its annotations, and maps each
step to `activeAnnotation`.

```js
setStep(step) {
  this.viewer.revealAnnotation(step);
}
```

<vividly-annotation title="Absolute steps">
Selecting annotation 1 always establishes the same state. The viewer does not need to
know whether the presenter moved forward, backward, or followed a deep link.
</vividly-annotation>

## Independent navigation

Select an annotation from the left pane or use the presentation arrow keys. Both paths
end at the same slide step and URL.

<vividly-annotation title="One source of truth">
Pointer interaction emits an event. The adapter asks the orchestrator to navigate, and
the orchestrator writes the resulting step back to the control.
</vividly-annotation>

## Hidden mounting

The runtime mounts nearby slides while their layers are hidden. Annotation selection is
safe at that point; scrolling waits until the current task finishes and layout is
available.

<vividly-annotation title="Deferred scrolling">
The deferred operation is cancellable and does not depend on animation frames, which
may stop while a browser tab is in the background.
</vividly-annotation>