# feat(web): Create Order step 2 — coupled dual-amount fields and rate slider

## Context

Step 2 of the New Request wizard currently collects a free-text `max_rate` per give
option and uses the `RatePreview` component to show the market reference rate, a
delta chip, an estimated total, and a deviation warning that gates the Continue button
when the typed rate exceeds ±10 % of the reference. The experience is friction-heavy:
users must know a valid rate before typing, can trigger the alarming warning mid-keystroke,
and have no visual anchor to understand the market window.

Issue #23 asks to replace this with a T-Bank-inspired interaction model: two paired
amount fields (`wantAmount` and `giveAmount`) linked by a live exchange rate, plus a
slider that moves the rate within ±10 % of the market reference. Because the slider
constrains the range mechanically, the deviation warning and the "Fix rate to
continue" gate are no longer needed. A free-text fallback preserves publishability
when the reference is unavailable. No backend or schema changes are required; the
submitted API payload (`want_amount` + `max_rate` per give option) is unchanged.

## User stories

- AS a community member posting a request I WANT to see how much of my give asset
  corresponds to the receive amount at the current rate SO THAT I can confirm the
  deal makes economic sense before I submit.
- AS a community member I WANT to adjust the exchange rate with a bounded slider
  SO THAT I can set a small discount or premium without accidentally entering an
  out-of-range value.
- AS a community member I WANT to type directly into either amount field SO THAT I
  can start from a give-amount target rather than a receive-amount target.
- AS a community member I WANT to be able to publish my request even when the market
  reference is unavailable SO THAT a CBR data outage does not block me.

## Acceptance criteria (EARS)

- WHEN the user reaches step 2 and the reference rate is available THE SYSTEM SHALL
  display a dual-amount block containing a want-amount field (pre-filled from step 1)
  and a give-amount field (computed as wantAmount x resolvedRate), plus a rate slider
  centered on the market reference and bounded to [ref x 0.9, ref x 1.1].
- WHEN the user moves the rate slider THE SYSTEM SHALL recompute the give-amount
  field as wantAmount x resolvedRate and display the resolved rate and its delta from
  the market reference using the existing RateChip component.
- WHEN the user edits the want-amount field THE SYSTEM SHALL recompute the give-
  amount field as newWantAmount x resolvedRate without moving the slider.
- WHEN the user edits the give-amount field THE SYSTEM SHALL recompute the want-
  amount field as newGiveAmount / resolvedRate without moving the slider.
- WHILE the rate slider is active THE SYSTEM SHALL prevent the resolved rate from
  exceeding ±10 % of the market reference at any slider position.
- WHEN the reference rate is available THE SYSTEM SHALL NOT display the free-text
  max_rate input field or the rate-deviation warning.
- WHEN the reference rate is unavailable (GET /rates/reference returns 503 or a
  network error) THE SYSTEM SHALL display a free-text max_rate input and the message
  "Reference rate unavailable — order can still be published" instead of the dual-
  amount block and slider.
- WHEN the user advances from step 2 in slider mode THE SYSTEM SHALL include
  want_amount equal to the current want-amount field value and max_rate equal to the
  slider's resolved rate (formatted as a decimal string) in the give_options array
  of the POST /orders request body, matching the existing API contract.
- WHEN the user advances from step 2 in fallback mode THE SYSTEM SHALL send max_rate
  equal to the free-text field value, unchanged from today's behavior.
- WHEN the user navigates back to step 1 and returns to step 2 THE SYSTEM SHALL
  restore the slider to the last-used offset (or to 0 % if none was set) and
  re-derive give-amount from the current wantAmount and resolved rate.
- AFTER the implementation npm run type-check and npm run build MUST complete without
  errors.

## Out of scope

- Per-alternative (multi-option) sliders: the issue explicitly fixes to a single
  pair (epic #24, variant B). The existing multi-option OptDraft array is retained in
  state but only opts[0] is rendered.
- Backend or database changes: the submit payload and API schema are unchanged.
- Applying the slider interaction to screens other than CreateOrder step 2 (e.g., the
  Subscriptions max_rate field or deal response forms). This issue touches only
  CreateOrder.tsx, components.tsx, and styles.css.
- Stage 4 subscription fan-out or bot notifications.

## Open questions

1. Should editing the give-amount field update the slider position (implying a rate
   change) or keep the slider fixed and recompute want-amount instead? The issue
   wording "editing either recomputes the other from the current rate" and the formula
   "want = give / rate" both imply the slider stays fixed when give is edited. This
   proposal adopts that reading. If the intent is that typing a give amount also moves
   the slider, the RateSlider implementation needs an additional slider-sync path.

2. Should want-amount be re-editable in step 2, or display-only (locked after step 1)?
   The issue says "editing either recomputes the other," which implies both fields are
   editable. This proposal makes both editable; a step-2 edit to want-amount updates
   the shared wantAmount state and therefore affects the submitted want_amount payload.

3. Decimal precision of computed amounts: the issue does not specify how many decimal
   places to show in the give-amount field. This proposal rounds the displayed give-
   amount to 2 decimal places for UX clarity and sends resolvedRate.toFixed(8) as
   max_rate. The implementer should confirm rounding rules with the product owner.

4. Cross-browser range input: Telegram Mini App WebViews vary across platforms. This
   proposal uses a native HTML input[type=range] with accent-color CSS. If Telegram's
   Android WebView does not honour accent-color, a ::-webkit-slider-thumb override or
   a lightweight custom overlay should be added.
