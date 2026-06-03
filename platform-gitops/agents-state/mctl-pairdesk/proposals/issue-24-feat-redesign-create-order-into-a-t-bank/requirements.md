# Redesign Create Order into a T-Bank-Style Exchange Flow

## Context

The current "New request" screen (`web/src/screens/CreateOrder.tsx`) follows a
generic form pattern: step 1 mixes pair selection, want-amount entry, and city
in one page; step 2 shows a rate slider. The issue asks for a T-Bank-style
currency-exchange UX where step 1 is a clean, dedicated pair-picker and step 2
is a coupled-amounts block (type one field, the other recomputes) plus a rate
slider bounded to the existing ±10% market-deviation limit.

Both child sub-issues (#22 pair selector, #23 coupled amounts + slider) are
already partially implemented: `CurrencyPairPicker` and `RateSlider` exist in
`web/src/components.tsx`. The redesign reorganises these components into the
correct two-window structure, completes multi-option support in step 2 (Option A
per the issue recommendation), and ensures step 3 (note + preview) is
undisturbed. No backend changes are required; the `POST /orders` contract and
the `MAX_RATE_DEVIATION_PCT = 10` server gate are already correct.

## User stories

- AS a maker I WANT a focused step-1 screen that only asks me what pair I am
  exchanging SO THAT I can commit to the trade direction before thinking about
  amounts or rates.
- AS a maker I WANT the two amount fields (want and give) to stay in sync with
  each other as I type SO THAT I always know the implied give total without
  doing mental arithmetic.
- AS a maker I WANT a rate slider bounded to ±10% of the market reference SO
  THAT I cannot accidentally publish an order the backend would reject.
- AS a maker I WANT to add multiple give-asset alternatives, each with its own
  coupled amounts + rate slider block, SO THAT I preserve pairdesk's
  multi-option matching power while still benefiting from the clean T-Bank UX.
- AS a maker I WANT to see the resolved rate and its market-reference chip below
  the slider SO THAT I understand how competitive my offer is before submitting.

## Acceptance criteria (EARS)

### Step 1 - Pair picker

- WHEN the user opens the Create tab THE SYSTEM SHALL display only the
  `CurrencyPairPicker` (give / want asset selector + swap button) and optionally
  the city field; no amount field SHALL appear on this step.
- WHEN the user taps the swap button THE SYSTEM SHALL exchange give and want
  assets, preserving any entered amounts.
- WHILE both give and want assets are selected THE SYSTEM SHALL enable the
  "Continue" MainButton unconditionally (no amount is required to advance from
  step 1).

### Step 2 - Coupled amounts + rate slider

- WHEN the user reaches step 2 THE SYSTEM SHALL display one `RateSlider` block
  per give option in `opts[]`.
- WHILE a reference rate is loading THE SYSTEM SHALL show a loading indicator
  inside the relevant slider block and disable the rate slider controls.
- WHEN the user enters a value in the want-amount field THE SYSTEM SHALL
  recompute and display the give-amount as `want * resolvedRate` without the
  user touching the give field.
- WHEN the user enters a value in the give-amount field THE SYSTEM SHALL
  recompute and display the want-amount as `give / resolvedRate`.
- WHEN the user moves the rate slider THE SYSTEM SHALL update both amount fields
  to reflect the new rate, keeping whichever field was last edited as the anchor
  side.
- WHILE the rate slider is rendered THE SYSTEM SHALL constrain its range to
  `[refRate * 0.90, refRate * 1.10]`, matching the backend constant
  `MAX_RATE_DEVIATION_PCT = 10` in `src/services/orders.ts`.
- IF the reference rate is unavailable (503 from `GET /rates/reference`) THE
  SYSTEM SHALL fall back to a free-text rate input and display the note
  "Reference rate unavailable — order can still be published".
- WHEN the user taps "Add alternative" THE SYSTEM SHALL append a new
  `OptDraft` entry with a default asset that is neither the current give asset
  nor the want asset, render a new `RateSlider` block for it, and scroll it
  into view.
- WHEN there is more than one give-option block THE SYSTEM SHALL show a remove
  button on each block that deletes that option from `opts[]`.
- WHILE step 2 is active THE SYSTEM SHALL enable the "Continue" MainButton only
  when at least one give option has a valid want-amount (parseable positive
  number).

### Step 3 - Note + preview (unchanged)

- WHEN the user reaches step 3 THE SYSTEM SHALL display an optional comment
  textarea and a live `OrderCard` preview in the `outcome` variant.
- WHEN the user taps "Publish request" THE SYSTEM SHALL call `POST /orders` with
  `want_asset`, `want_amount`, `location_city`, `comment`, and
  `give_options[{ asset, max_rate, payment_methods }]` — identical to the
  current submit payload shape.

### Cross-cutting

- WHILE any step is active THE SYSTEM SHALL show a `Stepper` indicator with
  three dots reflecting the current position.
- WHEN the user is on steps 2 or 3 THE SYSTEM SHALL show the Telegram
  BackButton which navigates to the previous step.
- WHILE a submit is in progress THE SYSTEM SHALL set the MainButton to the
  loading state and prevent duplicate submissions.

## Out of scope

- Backend changes to `POST /orders`, `/rates/reference`, or the database schema.
- Option B (single-pair simplification, dropping `give_options[]` support).
- Bot fan-out / subscription matching (Stage 4).
- Rate slider for the respond (deal creation) flow — out of scope for this issue.
- Animating the swap or transition between steps.

## Open questions

1. **City field placement.** The city field currently lives in step 1. Moving it
   to step 3 alongside the comment would make step 1 a pure pair picker. Both
   are defensible. This proposal places it in step 3 (Note screen) to keep step 1
   minimal, but the implementer should confirm with the designer.
2. **"Add alternative" asset default.** With three assets (EUR, RUB, USDT) and
   give + want already committed, there is exactly one remaining asset for a
   second option. If the user already has two options, the button should be
   hidden (no further unique asset is available). Verify that the `nextFree`
   helper in `CreateOrder.tsx` (line 27-29) covers this.
3. **Want-amount anchor across step navigation.** Currently `wantAmount` is
   shared state for all give-option sliders. With multiple sliders, should each
   slider own its own want-amount, or should they all share one? The issue says
   "give = want × rate" implying a shared want-amount. This proposal keeps the
   single shared `wantAmount` state.
4. **Payment methods per alternative.** The existing `OptDraft` carries
   `payment_methods[]` per option. The `RateSlider` component does not render
   the payment-method chips; those are rendered by the wrapping step-2 block.
   Confirm that each alternative block keeps its own payment-method chip row.
