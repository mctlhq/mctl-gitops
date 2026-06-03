# Design: issue-23-feat-web-create-order-step-2-coupled-dua

## Current state

### CreateOrder step 2 (web/src/screens/CreateOrder.tsx, lines 183-233)

Step 2 renders a single `pd-give-editor` block containing:

- A labelled `<input type="text" inputMode="decimal">` bound to `OptDraft.max_rate`
  (free text, lines 202-205).
- `<RatePreview>` (component-local function, lines 274-348) which:
  - Fetches `GET /api/rates/reference?base=<wantAsset>&quote=<giveAsset>` on mount
    and whenever the pair changes.
  - Holds a 600 ms debounce (`settledRate`) to avoid flagging violations mid-keystroke.
  - Calls `onViolation(settled, live)` to report deviation state to `CreateOrder`.
  - Renders the market ref label, a `RateChip` delta chip, and computed total.
  - Renders a red error message when `|settledDelta| > MAX_DEVIATION_PCT (10)`.
  - Renders "Reference rate unavailable — order can still be published" on a 503 or
    network failure.
- `CreateOrder` holds `rateViolations` and `liveRateViolations` maps (keyed by
  `OptDraft.id`) that disable Continue and change the button label to
  "Fix rate to continue" (lines 29-32, 88-101).

The `isRateViolation` helper (lines 268-272) and `MAX_DEVIATION_PCT = 10` constant
(line 264) implement the deviation check.

### Relevant shared types and components

- `OptDraft` (lines 8-13 of CreateOrder.tsx):
  `{ id: number, asset: Asset, max_rate: string, payment_methods: string[] }`
- `RateChip` (components.tsx, lines 100-142): renders a coloured delta-percent chip;
  accepts a numeric or string delta; re-usable as-is.
- `fmtAmount` (components.tsx, line 223): locale-aware formatter for amounts.
- `PD_GLYPH` (components.tsx, line 24): currency symbol map used by `pd-amount-field`
  glyphs.
- `GET /api/rates/reference?base=&quote=` (src/routes/rates.ts): returns
  `{ rate: number, source: string, timestamp: string }` or HTTP 503. The `rate` field
  is quote units per one base unit (e.g. RUB per EUR).
- No existing range-input or slider component exists in components.tsx or styles.css.

### Submit payload (CreateOrder.tsx, lines 72-86)

```
api.post('/orders', {
  want_asset: wantAsset, want_amount: wantAmount,
  location_city: city.trim() || null, comment: comment.trim() || null,
  give_options: [{
    asset: giveAsset,
    max_rate: o.max_rate.trim() || null,
    payment_methods: o.payment_methods,
  }],
});
```

`max_rate` is a nullable decimal string; the backend accepts any positive decimal.
The ±10 % constraint is front-end only.

---

## Proposed solution

### Overview

Replace the free-text `max_rate` input and `RatePreview` in step 2 with a new
`RateSlider` component that renders:

1. A **want-amount field** pre-filled with `wantAmount` from parent state, editable.
2. A **give-amount field** derived as `wantAmount x resolvedRate`, editable.
3. An `<input type="range">` slider bounded to `[ref x 0.9, ref x 1.1]`.
4. A live display of the resolved rate and a `RateChip` delta.
5. A fallback that renders only a free-text `max_rate` input and a hint message when
   the reference rate is unavailable.

### Data flow

```
referenceRate  (fetched once on mount; re-fetched when base or quote changes)
       |
offsetPct  in  [-10, 10]   (slider state, default 0)
       |
resolvedRate  =  referenceRate x (1 + offsetPct / 100)
       |
giveAmount  =  wantAmount x resolvedRate   (local derived string)
```

Editing the **want-amount field** (parent state `wantAmount`) triggers
re-derivation of `giveAmount = newWantAmount x resolvedRate`; the slider stays.

Editing the **give-amount field** triggers `onWantAmountChange(giveValue / resolvedRate)`;
the slider stays. To prevent a feedback loop, a `editingGive` ref suppresses the
prop-driven re-derivation of `giveInputValue` while the give field is focused.

Moving the **slider** changes `offsetPct`, recomputes `resolvedRate`, re-derives
`giveAmount = wantAmount x resolvedRate`, and calls `onRateResolved(resolvedRate)`.

### Component signature: `RateSlider` (new, in web/src/components.tsx)

```tsx
interface RateSliderProps {
  base: Asset;                               // want_asset (what the maker receives)
  quote: Asset;                              // give_asset
  wantAmount: string;                        // controlled: from CreateOrder state
  onWantAmountChange: (v: string) => void;   // called when give-edit drives want
  onRateResolved: (rate: string | null) => void; // null when reference unavailable
}
```

Internal state:
- `refRate: number | null` — fetched reference rate; null while loading.
- `unavailable: boolean` — true after a 503 or network error.
- `offsetPct: number` — slider percentage offset, default 0, clamped to [-10, 10].
- `giveInputValue: string` — local edit buffer for the give-amount field.

Lifecycle:
- On mount and on `base`/`quote` change: clear `refRate`, set `unavailable = false`,
  call `onRateResolved(null)`, fetch `GET /api/rates/reference?base=&quote=`. On
  success: set `refRate`, derive initial `giveInputValue`, call `onRateResolved`.
  On 503 or error: set `unavailable = true`, call `onRateResolved(null)`.
- On `wantAmount` prop change (and `editingGive.current === false`): recompute
  `giveInputValue = (parseFloat(wantAmount) x resolvedRate).toFixed(2)`.
- On `offsetPct` change: recompute `giveInputValue`, call `onRateResolved`.

When `unavailable === true`:
- Render a free-text `<input>` for max_rate (identical to the existing standalone
  `max_rate` input in step 2 today) and the hint text "Reference rate unavailable —
  order can still be published."
- Do NOT render the dual-amount block or slider.
- Call `onRateResolved(null)` so the parent sets `max_rate` to the fallback field's
  value externally (see CreateOrder changes below).

When `refRate === null` and `unavailable === false`:
- Render a loading placeholder ("Loading reference...") consistent with the existing
  `RatePreview` loading state.

### Changes to `CreateOrder` (web/src/screens/CreateOrder.tsx)

1. **Remove state**: `rateViolations`, `liveRateViolations`, `hasRateViolation`,
   `hasLiveRateViolation` (lines 29-32). The violation model is superseded.

2. **`nextEnabled` for step 2** (line 88): change from `!hasRateViolation` to
   `amountValid`. The rate is always in-range; the only gate is a valid want-amount.

3. **`nextText` for step 2** (line 89): remove the "Fix rate to continue" branch.
   Replace with simply `'Continue'`.

4. **`primaryAction` step-2 branch** (lines 99-103): remove the
   `hasRateViolation || hasLiveRateViolation` guard.

5. **Step 2 render** (lines 200-211): replace the `<span pd-label>Max rate</span>`,
   the `<input max_rate>`, and the `<RatePreview>` block with:

   ```tsx
   <RateSlider
     base={wantAsset}
     quote={giveAsset}
     wantAmount={wantAmount}
     onWantAmountChange={setWantAmount}
     onRateResolved={(r) => updateOpt(0, { max_rate: r ?? '' })}
   />
   ```

   When `RateSlider` is in fallback mode it renders its own free-text input
   internally, so no additional input element is needed in CreateOrder.

6. **Delete** the `isRateViolation` helper (lines 268-272) and the `RatePreview`
   function (lines 274-348) from CreateOrder.tsx. Their logic migrates into
   `RateSlider`.

7. **`MAX_DEVIATION_PCT`** (line 264) moves into `RateSlider`'s module scope in
   components.tsx where it is used to compute the slider bounds
   (`ref x (1 - MAX_DEVIATION_PCT/100)` to `ref x (1 + MAX_DEVIATION_PCT/100)`).

8. **`OptDraft.max_rate`** is retained. In slider mode it is set by the
   `onRateResolved` callback. In fallback mode the parent holds it from the
   free-text fallback field rendered inside `RateSlider`; `RateSlider` should
   call `onRateResolved(null)` on fallback-field change and the parent then uses a
   separate local state or the `OptDraft.max_rate` field directly. Because `RateSlider`
   renders the fallback input itself, the cleanest contract is: pass a `fallbackRate`
   and `onFallbackRateChange` prop pair in addition to `onRateResolved`, or have the
   component call `onRateResolved(typedValue)` on every keystroke in fallback mode
   so the parent treats it uniformly.

   Simpler unified contract: `onRateResolved(rate: string | null)` where `null` means
   "unavailable and no user input yet" and a non-empty string is always the rate to
   use (whether from the slider or from fallback free-text). The parent sets
   `OptDraft.max_rate = r ?? ''` in all cases.

### New CSS (web/src/styles.css)

Add to the "Form (Create order)" section, after `.pd-give-editor` rules:

```css
/* Dual-amount block within RateSlider */
.pd-dual-amounts {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

/* Rate slider */
.pd-rate-slider {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pd-slider-track {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pd-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: var(--pd-border);
  accent-color: var(--pd-accent-eff);
  cursor: pointer;
  outline: none;
}
.pd-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--pd-accent-eff);
  box-shadow: 0 2px 6px color-mix(in srgb, var(--pd-accent-eff) 40%, transparent);
  cursor: pointer;
}
.pd-slider-labels {
  display: flex;
  justify-content: space-between;
  font-size: var(--pd-fs-micro);
  color: var(--pd-hint);
  padding: 0 2px;
}
.pd-slider-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--pd-fs-sub);
  flex-wrap: wrap;
  margin-top: 2px;
}
.pd-slider-rate-val {
  color: var(--pd-text-2);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
```

The `::-webkit-slider-thumb` block covers Telegram's Chromium-based Android WebView.
The `accent-color` property covers modern WebKit and Blink without pseudo-elements.

### No backend changes required

`GET /api/rates/reference` (src/routes/rates.ts) already returns `{ rate: number }`.
`POST /api/orders` (src/routes/orders.ts) already accepts `max_rate` as a nullable
decimal string. No migrations, no new endpoints, no changes to src/.

---

## Alternatives

### A: Augment RatePreview — add a slider on top of the existing free-text input

Keep `RatePreview` and the `max_rate` input, hide the input when the reference is
available, and overlay a slider. Rejected: two sources of truth for the rate (slider
position + hidden input value), the 600 ms debounce logic becomes dead code, and the
violation-warning path remains live, increasing the chance of a regression. The
replacement approach is cleaner.

### B: Full custom slider (no native range input)

Implement a drag-based custom slider with `PointerEvent` handlers to avoid WebView
rendering inconsistencies. Rejected at this stage: native `<input type="range">` with
`accent-color` and a `::-webkit-slider-thumb` override is sufficient for current
Telegram WebViews and keeps the component under ~120 lines. A custom slider can be
added as a follow-up if QA reveals persistent rendering problems.

### C: Move the dual-amount block to step 1

Add the give-amount field and slider to step 1 alongside the want-amount field.
Rejected: step 1 already collects the currency pair and want-amount; adding
rate/give-amount refinement there overloads the first step and breaks the clear
three-step narrative (pair + amount, rate, review). Step 2 is the correct stage for
rate negotiation.

---

## Platform impact

- **Migrations**: none.
- **API changes**: none. Both `GET /api/rates/reference` and `POST /api/orders`
  are unchanged in contract.
- **Build**: three web files change (`CreateOrder.tsx`, `components.tsx`,
  `styles.css`). All existing TypeScript types are unchanged; no new types are
  introduced beyond the `RateSliderProps` interface.
- **Backward compatibility**: only the web client changes. The bot and API are
  unaffected. An in-progress form loses its previously typed `max_rate` on client
  reload, which was already true before this change.
- **Risk — reference-rate outage**: mitigated by the free-text fallback path
  (`unavailable = true` renders the original input). No user is blocked from
  submitting an order.
- **Risk — slider precision / floating-point**: `wantAmount x resolvedRate` may
  produce long decimals. Mitigated by displaying the give-amount rounded to 2 dp
  and sending `resolvedRate.toFixed(8)` as `max_rate`, consistent with the existing
  `max_rate` string handling in the backend.
- **Risk — give-amount edit feedback loop**: the `editingGive` ref pattern prevents
  `wantAmount` prop changes from overwriting the user's typed give value while they
  are focused on the give field. The implementer must test rapid alternating edits
  between both fields and tab-out behaviour.
