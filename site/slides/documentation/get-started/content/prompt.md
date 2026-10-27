## Describe the result, not the implementation

Copy this request into your coding agent. Let it inspect the workspace before making changes.

```text
Replace the starter welcome slide with a single interactive slide
about compound growth.

Start with $1,000, no further deposits, and a five-year horizon.
Add an annual-growth slider from 0% to 20%, initially 8%.
Show a line chart for years 0 through 5 and the final dollar value.
Use annual compounding: 1000 * (1 + rate / 100) ** year.
Keep the chart scale fixed from $1,000 to $2,500.

Make it clear and legible, with accessible labels and no external
assets or new dependencies. Use a single presentation step.

Start the preview server if needed, check the result, and give me the full URL to open.
```

The agent may ask for some clarification and then it will create the slide, start the preview server, test the slide in the playwright browser, iterate until all looks good, and then give you a url to view the slide in your browser.

The design it produces may differ from our example. That's fine: we're checking the behavior and explanation, not trying to reproduce identical pixels.
