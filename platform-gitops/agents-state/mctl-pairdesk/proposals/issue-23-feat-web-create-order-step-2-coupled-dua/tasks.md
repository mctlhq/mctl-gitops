# Tasks: issue-23-feat-web-create-order-step-2-coupled-dua

- [ ] 1. Add `RateSlider` component to `web/src/components.tsx` — DoD: component
  exports a `RateSlider` function accepting `RateSliderProps` (base, quote,
  wantAmount, onWantAmountChange, onRateResolved); fetches
  `GET /api/rates/reference?base=&quote=` on mount and on pair change; manages
  `refRate`, `unavailable`, `offsetPct` (default 0, clamped to [-10, 10]), and
  `giveInputValue` local state; renders dual-amount block (want field + give field)
  using existing `.pd-amount-field` markup and `PD_GLYPH`; renders an
  `<input type="range">` slider with min/max derived from the ±10 % window; renders
  a resolved-rate label and `RateChip` delta chip live; renders free-text fallback
  input + hint text when `unavailable === true`; calls `onRateResolved` on slider
  move and on fallback-field keystroke; calls `onWantAmountChange` when give-field
  edit drives a reverse-computed want-amount; an `editingGive` ref prevents the prop-
  driven `giveInputValue` sync from overwriting a live give-field edit; `MAX_DEVIATION_PCT`
  constant lives here; TypeScript compiles without errors.

- [ ] 2. Add CSS for the new slider and dual-amount block to `web/src/styles.css`
  (depends on 1) — DoD: classes `.pd-dual-amounts`, `.pd-rate-slider`,
  `.pd-slider-track`, `.pd-slider`, `::-webkit-slider-thumb` override,
  `.pd-slider-labels`, `.pd-slider-info`, and `.pd-slider-rate-val` are present and
  visually consistent with the existing token system (`--pd-accent-eff`, `--pd-border`,
  `--pd-hint`, `--pd-text-2`, `--pd-fs-sub`, `--pd-fs-micro`); slider thumb is 22 px
  with accent fill; no existing class names are modified.

- [ ] 3. Refactor CreateOrder step 2 in `web/src/screens/CreateOrder.tsx`
  (depends on 1 and 2) — DoD: `rateViolations`, `liveRateViolations`,
  `hasRateViolation`, `hasLiveRateViolation` state and all references removed;
  `isRateViolation` helper and the `RatePreview` function deleted from the file;
  step-2 `nextEnabled` changed to `amountValid`; step-2 `nextText` is `'Continue'`
  unconditionally; the `hasRateViolation || hasLiveRateViolation` guard in
  `primaryAction` removed; the `max_rate` `<input>` and `<RatePreview>` call replaced
  with `<RateSlider base={wantAsset} quote={giveAsset} wantAmount={wantAmount}
  onWantAmountChange={setWantAmount} onRateResolved={(r) => updateOpt(0, { max_rate:
  r ?? '' })} />`; `MAX_DEVIATION_PCT` constant removed from this file (moved to
  components.tsx in task 1); `npm run type-check` passes with zero new errors.

- [ ] 4. End-to-end smoke test (depends on 3) — DoD: dev server starts successfully
  with `AUTH_DEV_BYPASS=true DATABASE_SSL=false`; CreateOrder opens; step 1 accepts a
  valid amount and advances to step 2; step 2 shows two amount fields and a slider
  (not the old free-text max_rate input); moving the slider updates the give-amount
  field; editing the want-amount field updates the give-amount field; editing the
  give-amount field updates the want-amount field; tapping Continue reaches step 3;
  tapping Publish sends a POST /api/orders request whose body contains `want_amount`
  matching the want field and `give_options[0].max_rate` matching the slider-resolved
  rate; `npm run build` exits 0.

## Tests

- [ ] T1. Unit — coupling (want drives give): given `refRate = 100`, `offsetPct = 5`,
  `wantAmount = "10"`, assert that the give-amount field displays `"105.00"` and
  `onRateResolved` was called with `"105.00000000"` (or equivalent 8-dp value).

- [ ] T2. Unit — reverse coupling (give drives want): given the same initial state,
  simulate the user typing `"90"` in the give-amount field; assert `onWantAmountChange`
  is called with the string representation of `90 / 105` (approximately `"0.86"`);
  assert the slider `offsetPct` has not changed.

- [ ] T3. Unit — slider bounds: assert the slider `min` attribute equals
  `refRate x 0.9` and `max` attribute equals `refRate x 1.1`; assert that setting
  `offsetPct` programmatically to values outside [-10, 10] is clamped before
  `onRateResolved` is called.

- [ ] T4. Unit — fallback path: mock `GET /api/rates/reference` to return HTTP 503;
  assert `RateSlider` renders an `<input type="text">` and the fallback hint text
  "Reference rate unavailable — order can still be published"; assert no
  `<input type="range">` is rendered.

- [ ] T5. Build gate: `npm run type-check` and `npm run build` pass with no TypeScript
  errors introduced by this change.

## Rollback

1. Revert the three changed files (`web/src/screens/CreateOrder.tsx`,
   `web/src/components.tsx`, `web/src/styles.css`) to the commit immediately before
   this feature was merged. No database migrations or server restarts are required
   because all changes are front-end only.
2. The backend (`src/`) is entirely unaffected; no API or infrastructure rollback is
   needed.
3. If a flag-based rollback is preferred without a full revert, wrap the step-2
   render in a boolean env-driven feature flag:
   `if (import.meta.env.VITE_RATE_SLIDER) { <RateSlider /> } else { <input max_rate>
   + <RatePreview /> }`. This was not built by default to keep the diff minimal but
   is straightforward to add.
