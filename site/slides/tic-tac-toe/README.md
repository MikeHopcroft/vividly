# Tic-Tac-Toe source

This directory is the published copy of the Tic-Tac-Toe presentation. The
definitive source is `site/slides/tic-tac-toe/` in the `presentations` project.
It includes the introduction, math walkthrough, interactive inference, training,
and model assets.

The presentation is registered in `../../catalog.yaml`; its manifest is
`../../presentations/tic-tac-toe.yaml`. Open `#/tic-tac-toe/introduction` to start.

The output-layer explanation accumulates the first two active hidden-unit columns
of W2 transpose separately, then the remaining columns and output biases together.
Matching green outlines connect each column group to its hidden-vector values.
The displayed weights remain unscaled; only the flying contributions are scaled
by their hidden-vector values.
Flying contributions use the weight/bias display scale rather than normalizing
against the largest product. The logit display auto-normalizes to its current
largest absolute score on each update, including intermediate accumulation
frames. This changes only dot sizes, not the scores or argmax calculation.

Rendered matrix rectangles use a crosshair cursor. Hovering a W2-transpose row
highlights its output-board cell, just like hovering a logit. Output hover preserves
the current step's board display: Xs and Os remain hidden until the argmax at
step 14. Hovering a W1 row
highlights its input-board cell; each group of three encoding rows maps to one
board cell. The hovered row temporarily replaces that cell's display with its
encoded state (blank, X, or O), using a green background and bold green lettering.
Leaving the matrix restores the board's normal display without changing its data.

Step 15 (`#/tic-tac-toe/demo/15`) is an isolated column-contribution explorer,
following the argmax step and preceding the summary callouts. It opens with the
logits selected, showing all nine scores as a 3x3 bar chart. The activation gauge
and readout are hidden in this view, with their space reserved to prevent layout
shifts. Press `[` to select the last hidden column and reveal the gauge; press `]`
past the last hidden column to return to logits. Logit bar heights normalize to
the largest absolute score without changing the scores themselves.
The selected hidden
activation and W2-transpose column have matching green outlines, as does the full
W1 column unless a single W1 weight is selected. Logit mode has no W1 outline.
Use `[` and `]`
or the selection buttons to move between all columns, including inactive ones.
Click a W1 weight to select its hidden unit and highlight only that matrix cell.
Click a W2-transpose weight to select its full hidden column, or click the logits
array to select logits. Both actions leave W1 single-weight mode.
In this mode, `[` and `]` keep the selected W1 row and move the highlighted weight
along with the hidden activation and W2-transpose column. Clicking outside a W1
weight or pressing `\` restores the full-column highlight without closing the
explorer or changing the selected column.
Editing the input board keeps step 15 and the selected column, and refreshes the
explorer from the new hidden activation and network output.
Drag the vertical gauge's handle to preview positive or negative activations in
a 2.5D board-shaped chart. Releasing it restores the original value over 420 ms.
Positive bars have three opaque, differently lit red faces. Negative bars are
shaded blue with a light rim and dark, recessed opening at the zero plane.
A translucent gray board and four tic-tac-toe divider lines mark the zero plane,
layered above negative bars and below positive bars.
The board plane is rotated 15 degrees counterclockwise from its original
projection to make rows nearly horizontal; the bars remain vertical.
The focused gauge also supports Up/Down and Home/End, restoring on key release.
Its range includes zero and one; chart height uses a fixed scale while dragging.
This experiment does not change hidden activations, logits, or model decisions.
The math slide now has 22 steps, with callouts at steps 16 through 21.

## Token-completion explainer

`tokens/` is a standalone, single-step slide after the movie explainer, at
`#/tic-tac-toe/tokens`. It adapts the token prototype's five-position board,
one-hot encoding blocks, abbreviated matrices, and ranked output scores to the
same red/blue, yellow, and green visual vocabulary.

The fixture uses the GPT-2 vocabulary (50,257 tokens). Input IDs and all twelve
output candidates were checked against the
[GPT-2 vocabulary](https://huggingface.co/gpt2/resolve/main/vocab.json).
Quoted labels preserve leading spaces. The prototype's `" windowsill"` candidate
was replaced by `" window"` because the former is not one GPT-2 token.
W1 has 251,285 rows (five position-specific vocabulary blocks) and 48 columns;
W2 transpose has 50,257 rows and 48 columns.

Weights, hidden activations, and scores are separate, deterministic illustrative
fixtures, not a trained model or a computed forward pass. The slide explicitly
distinguishes this toy fixed-context MLP from a transformer. It adds no tokenizer,
browser package, network resource, or custom keyboard navigation. Resize handling
fits its 1920-by-1080 layout to the slide container and is released on unmount.

## Movie-recommendation explainer

`movies/` follows training at `#/tic-tac-toe/movies`. Its four steps frame
the liked movies and multi-hot input, the network, the winning unseen movie and
nearby masked examples, and the complete poster wall. The equation stays outside
the pan/zoom stage. Vividly owns presentation navigation; drag pans, wheel zooms,
and Reset view restores the current step's framing.
Step 0 hides the diagram to the right of the multi-hot input without changing
its layout. It fades in during the 900 ms zoom to step 1. The forward zoom from
step 1 to step 2 takes 1,800 ms; other camera transitions remain 900 ms.
Fades and camera motion settle together and are skipped for reduced motion or
`?instant`.

The 46 distinct movie records preserve the v5 prototype's scores and catalog rows.
Four already-liked movies are masked despite scores above the unseen winner,
Cold Case, Warm Room (8.54). The other 114 wall tiles are decorative repeated
posters, excluded from the accessibility tree and the distinct-movie count.
Weights, activations, and logits are illustrative fixtures, not a forward pass.

All 46 poster files are local under `movies/posters/`, copied from the original
movie demo's thumbnail assets. `movies/data.js` explicitly maps titles to files,
including the numbered spy-poster variants and the title differences for Wrong
Larry, Unlisted Number, and Chorus on the Fifth Floor. No external images or
browser packages are needed.

The two new explainers share deterministic SVG helpers in `mlp-diagram.js`.
Movies reuse the existing demo's `StageCamera`, release its events and observer
on unmount, and settle camera transitions through the slide lifecycle. Their
larger canvas opts into a lower minimum fit scale, so the complete wall also fits
smaller windows; the tic-tac-toe camera's default minimum remains unchanged.

Make future improvements in the `presentations` project. Periodically copy its
slide directory and manifest to the matching paths here for GitHub Pages.
Synchronization flows from `presentations` to `vividly-public`, not the reverse.
Preserve this README's published-copy guidance, review removed files when
synchronizing, and regenerate this project's Tic-Tac-Toe thumbnails with
`vividly thumbnails --presentation tic-tac-toe`.
