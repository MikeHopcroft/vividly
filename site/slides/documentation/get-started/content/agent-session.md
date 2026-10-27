## From a request to a clearer explanation

**Illustrative session, not a recording of a real agent run.** This authored example explores how an annotated transcript could work. Agent wording and outcomes are examples, not evidence of a completed implementation.

The project is richer than the starter: compare a one-time investment with regular contributions, using controls for rate and monthly deposit.

## 1. Frame the question

**Author**

> Create a slide that helps someone compare two ways of saving over ten years: $1,000 invested once, and $1,000 plus a monthly deposit. Let me change the annual rate and monthly contribution. Label assumptions clearly. Read the workspace's Vividly instructions first.

**Agent**

> Before implementing: should monthly deposits happen at the start or end of the month, and should the annual rate be treated as an effective annual rate?

**Why this matters:** the agent surfaced a modeling decision instead of silently choosing a formula.

**Author**

> End of month. Treat the slider as an effective annual rate, converted to a monthly rate. No fees, taxes, or inflation. This is an illustration, not a forecast.

## 2. Review the first result

**Illustrative first result:** two curves, a final-balance number, and two sliders.

**Author**

> Both curves update, but I can't tell how much of the difference is money I deposited versus investment growth. Separate those in the final summary, and identify each curve without relying only on color.

**Why this matters:** "make it better" gives little direction. This observation identifies the explanatory gap and an accessibility requirement.

## 3. Verify the model, not just the appearance

**Agent**

> I'll label each curve directly and show total deposited separately from growth. I'll also check the 0% case.

**Author**

> At 0%, with a $100 monthly deposit for ten years, the contribution scenario must end at $13,000: $1,000 plus 120 deposits. With the deposit set to zero, both scenarios must agree.

**Expected check:** the controls satisfy those two cases. If they do not, fix the calculation before polishing the layout.

**Why this matters:** a plausible chart is not evidence that the model is correct. Simple boundary cases make the result testable.

## 4. Refine the presentation

**Author**

> Keep this as one interactive slide. Put assumptions under the chart, make the labels readable at presentation size, and verify that Tab reaches both sliders. Don't add decorative animation.

**Illustrative final result:** directly labeled curves, a deposited-versus-growth summary, explicit assumptions, and keyboard-operable controls.

## What to borrow

1. Describe the audience's question and the intended outcome.
2. Resolve assumptions that affect correctness.
3. Preview early and critique specific observations.
4. Test a simple case by hand.
5. Stop when the explanation works; more effects are not automatically an improvement.

[Try the short walkthrough](#/make-something/get-started/prompt) or read the [authoring procedure](#/documentation/authoring).
