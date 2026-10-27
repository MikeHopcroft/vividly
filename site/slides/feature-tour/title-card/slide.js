// Declarative slide: no class, no JS body. The runtime falls back to the base
// Slide, injects the template, and drives steps through data-step / --step.

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 3,
};
