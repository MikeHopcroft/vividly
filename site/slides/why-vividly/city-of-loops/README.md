# City of Loops sketch and tracing lab

The red-marker passage is one 9.53-second step at
`#/vividly/why-vividly/micro-demonstration/2`. The city now follows at step 3.
The top title/copy pair introduces the central loop; the bottom pair appears as
the network expands. Gears retain their phase from the preceding step, continue
turning during a 3.6-second fade (previously 1.2 seconds), and are no longer
drawn or updated afterward. The sketch dissolves into the city over 1 second
(previously 450 milliseconds); other canvas and caption transitions are unchanged.
Reduced motion shows the completed sketch and both narrative pairs immediately.

## Scene readiness

The progress bar fills when the last transient finishes, not after a suggested
reading or viewing pause. Ambient gears and traffic keep moving afterward.
Advancing before readiness still settles the scene first.

| Step | Scene | Ready after | Last transient |
| --- | --- | --- | --- |
| 0 | A case study | 3.5 s | Waterfall reveal |
| 1 | Motion is not enough | 1.3 s | Caption reveal |
| 2 | The realization | 9.53 s | Final sketch stroke |
| 3 | The essence | 1.3 s | Caption reveal |
| 4 | Loops inside loops | 12.2 s | Two 5.5-second zoom cycles after a 1.2-second delay |
| 5 | Night driving | 1.3 s | Caption reveal |
| 6 | The idea, made visible | 12 s | Final pullback |

These readiness windows preserve the animation pace. In particular, the closing
text finishes at 8.5 seconds, but the camera continues pulling back until 12 seconds.
The sketch duration is derived from its stroke endpoints.

## Tracing lab

Open `#/city-of-loops-lab/composition` for the static tracing composition.
The lab shares city geometry and marker paths with the presentation; it does not
run traffic or gear animations. Adjust layer opacity, show path labels and
text-safe areas, or load a local SVG overlay. Clean screenshot mode hides the
controls, labels, and guides. Restore controls from the bottom-right button
(hover or keyboard focus). Hide the presentation toolbar separately if visible.

Use a 1920 by 1080 screenshot and an SVG `viewBox="0 0 1920 1080"` so returned
artwork aligns without manual repositioning. Other viewport ratios letterbox
the lab artwork. Download the sketch SVG as an editable starting point.
Keep each independently timed loop, road, and arrowhead in a separate path with
a stable descriptive ID, such as `loop-center` or `road-upper-middle-center`.
Keep visible annotation labels in a separate layer from the drawing.

[sketch.js](./sketch.js) owns geometry, deterministic hand-drawn strokes, IDs,
and timing. The first loop makes three drifting, visibly differing passes before
its arrowhead. Arrowheads have individually curved, asymmetric wings and varied
positions between 10 and 2 o'clock. Two neighboring loops and three roads establish a triangle before
the remaining strokes overlap. SVG import is a lab preview only, not an
automatic replacement of production paths.
