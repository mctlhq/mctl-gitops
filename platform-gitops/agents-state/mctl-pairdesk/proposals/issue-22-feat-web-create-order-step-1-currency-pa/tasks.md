# Tasks: issue-22-feat-web-create-order-step-1-currency-pa

- [ ] 1. Add `giveAsset` state + swap/collision logic to `CreateOrder` — DoD: `giveAsset: Asset`
  state is initialised to `'RUB'` (alongside existing `wantAsset='EUR'`); `handleGiveChange`,
  `handleWantChange`, `handleSwap`, and `nextFree` functions are implemented in
  `web/src/screens/CreateOrder.tsx`; all six directed pairs can be reached by toggling the
  two sides; no pair can be left with both sides equal.

- [ ] 2. Build `CurrencyPairPicker` component (depends on 1) — DoD: new exported function
  `CurrencyPairPicker` added to `web/src/components.tsx` with props
  `{ giveAsset, wantAsset, onGiveChange, onWantChange, onSwap }`. Renders two
  `AssetSelect` instances (one per side, each excluding the opposite asset) separated
  by a round swap button using the existing `arrowSwap` icon from `PD_ICON`. Exported
  from the same module; TypeScript type-checks cleanly.

- [ ] 3. Add CSS for pair picker (depends on 2) — DoD: classes `.pd-pair-picker`,
  `.pd-pair-row`, `.pd-pair-row-label`, `.pd-pair-swap-wrap`, `.pd-swap-btn` added to
  `web/src/styles.css`; the two asset-select rows appear as a single visually grouped
  surface with the swap button centred on the seam; the `:active` state rotates the
  button 180 degrees.

- [ ] 4. Rewire step 1 JSX to use `CurrencyPairPicker` (depends on 2, 3) — DoD: the
  existing single `AssetSelect` block for `wantAsset` in the `step === 1` branch of
  `CreateOrder.tsx` is replaced by `<CurrencyPairPicker .../>` wired to the handlers
  from task 1; the amount field's glyph and code remain keyed to `wantAsset`; the city
  field is unchanged; the section title reads "Currency pair".

- [ ] 5. Simplify step 2 to a single give-option editor (depends on 1) — DoD: in the
  `step === 2` branch of `CreateOrder.tsx`:
  - The `pd-segmini` asset segmented control is removed and replaced with a read-only
    asset tag showing `giveAsset`.
  - The `opts.map(...)` loop that rendered multiple give editors is replaced by a single
    inline block for `opts[0]`.
  - The Remove button, `addOpt` function call, and "Add alternative" button are deleted.
  - `availFor` and `addOpt` functions are deleted from the component.
  - The section title reads "I will give".
  - `rateViolations` / `liveRateViolations` continue to work (keyed on `opts[0].id = 0`).

- [ ] 6. Update submit payload and `previewOrder` (depends on 1, 5) — DoD: in the `submit`
  function, `give_options` is built as a single-element array using `giveAsset` (not
  `opts[0].asset`); the `previewOrder` object in step 3 uses `giveAsset` for
  `give_options[0].asset`; `POST /orders` receives a valid body with exactly one give
  option.

- [ ] 7. Verify build and type-check (depends on all above) — DoD: `npm run type-check`
  exits 0; `npm run build` exits 0; no unused imports or variables remain in the
  modified files.

## Tests

- [ ] T1. All six directed pairs selectable: starting from the default pair (give=RUB,
  want=EUR), cycle through every combination by changing each side; confirm the two
  sides never become equal and all six directed pairs (EUR/RUB, RUB/EUR, EUR/USDT,
  USDT/EUR, RUB/USDT, USDT/RUB) can be reached.

- [ ] T2. Swap button: set give=EUR, want=RUB; tap swap; confirm give=RUB, want=EUR.
  Set give=EUR, want=USDT; tap swap; confirm give=USDT, want=EUR.

- [ ] T3. Collision auto-bump on give change: set give=RUB, want=EUR; change give to EUR
  (same as current want); confirm want is auto-bumped to USDT (the remaining free asset).

- [ ] T4. Collision auto-bump on want change: set give=RUB, want=EUR; change want to RUB
  (same as current give); confirm give is auto-bumped to USDT.

- [ ] T5. Step 2 shows correct give asset label: select give=USDT in step 1, proceed to
  step 2; confirm the read-only asset display shows USDT; confirm no segmented control,
  Remove button, or "Add alternative" is present.

- [ ] T6. RatePreview base/quote correct after swap: select give=RUB, want=EUR, proceed
  to step 2; verify the rate preview label reads "Market ref. ≈ … RUB/EUR"; tap Back,
  swap to give=EUR, want=RUB, proceed to step 2; verify the label reads "RUB … EUR/RUB"
  (i.e., the base and quote follow the pair, not a hardcoded order).

- [ ] T7. Submit payload: complete all three steps; intercept or log the `POST /orders`
  request body; confirm `give_options` is an array of exactly one element with the
  `asset` matching what was selected in step 1.

- [ ] T8. Type-check and build: `npm run type-check && npm run build` both exit 0.

## Rollback
This change is limited to three front-end files:
- `web/src/screens/CreateOrder.tsx`
- `web/src/components.tsx`
- `web/src/styles.css`

No database migrations, no backend changes, and no API contract changes are involved.
Rollback is a git revert of the feature branch merge commit. The backend `POST /orders`
endpoint continues to accept the old multi-option payloads from any prior version of the
app because the array schema is unchanged.
