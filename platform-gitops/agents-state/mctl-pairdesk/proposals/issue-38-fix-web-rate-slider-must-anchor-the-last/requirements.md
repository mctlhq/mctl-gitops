# fix(web): rate slider must anchor the last-edited amount

## Context

In Create-Order step 2, `RateSlider` (`web/src/components.tsx:572-731`) shows two
coupled amount inputs (want/base and give/quote) linked by a market-referenced rate
slider. The slider is supposed to hold the field the user last typed in place and
recompute the other field. Currently, the component tracks only whether the give input
is *currently focused* (a transient `editingGive` ref), not which field was *last
edited*. Once the user blurs the give field the ref resets to `false`, and all
subsequent slider drags recompute the give amount regardless of what the user typed
last. This breaks the core UX contract of the widget: the user-supplied value should
stay fixed while the slider adjusts the opposite side.

The fix is entirely within the web Mini App (`web/`). No API, schema, or backend
change is required.

## User stories

- AS a maker I WANT the amount I just typed to stay fixed when I drag the rate slider
  SO THAT I can explore different rates without losing my entered amount.
- AS a maker I WANT switching from editing one amount field to the other to
  automatically update which side the slider anchors
  SO THAT the widget behaves intuitively regardless of my editing order.

## Acceptance criteria (EARS)

- WHEN the user types into the want (base) input and then drags the rate slider
  THE SYSTEM SHALL keep the want amount unchanged and recompute the give amount
  from `want * resolvedRate`.

- WHEN the user types into the give (quote) input and then drags the rate slider
  THE SYSTEM SHALL keep the give amount unchanged and recompute the want amount
  from `give / resolvedRate`, propagating the result to the parent via
  `onWantAmountChange`.

- WHEN the user types into the want input
  THE SYSTEM SHALL set the anchor to `want` (recomputing give) for all subsequent
  slider interactions until the user types into the give input.

- WHEN the user types into the give input
  THE SYSTEM SHALL set the anchor to `give` (recomputing want) for all subsequent
  slider interactions until the user types into the want input.

- WHEN the currency pair (base/quote) changes
  THE SYSTEM SHALL reset the anchor to `want`, clear `giveInputValue`, and
  re-fetch the reference rate, leaving the slider at market reference (0% offset).

- WHILE the rate slider is being dragged
  THE SYSTEM SHALL keep the rate label and delta-vs-market chip in sync with the
  resolved rate, irrespective of which side is anchored.

- IF the give input is left empty and the user blurs it
  THE SYSTEM SHALL restore the give amount derived from the current want amount and
  resolved rate (existing onBlur behaviour, unchanged).

- IF the reference rate is unavailable (`unavailable === true`)
  THE SYSTEM SHALL render the fallback free-text rate input (existing path,
  unchanged); anchor logic does not apply in this state.

## Out of scope

- Any API or database change.
- Changes to `CreateOrder.tsx` beyond what is needed to correctly wire updated props
  (the parent is not expected to need changes — the fix is self-contained in
  `RateSlider`).
- Multi-community or backend subscription logic.
- The `unavailable` fallback path rendering (keep as-is).

## Open questions

- **Initial anchor when the form loads with a pre-filled `wantAmount` prop**: the most
  reasonable default is `'want'`, consistent with the user having set the want side.
  This is what the current code implicitly does and what the issue describes.
- **Slider drag while a field is actively focused**: the issue does not mention this
  edge case. The proposed implementation reads `lastEditedField` (set on `onChange`),
  so a focused-but-untyped field does not change the anchor until a keystroke fires.
  This is acceptable; no special handling needed.
