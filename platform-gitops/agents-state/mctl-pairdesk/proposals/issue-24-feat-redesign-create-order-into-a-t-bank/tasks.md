# Tasks: issue-24-feat-redesign-create-order-into-a-t-bank

All changes are confined to `web/src/screens/CreateOrder.tsx` unless noted.
No backend files change.

---

- [ ] 1. Restructure step 1 to be a pure pair picker — DoD: step 1 renders
  only `CurrencyPairPicker` (give/want + swap) with no amount or city input;
  the "Continue" MainButton is always enabled (pair defaults are pre-set); the
  `Stepper` still shows 3 dots; existing pair swap and collision-avoidance
  logic (`handleGiveChange`, `handleWantChange`, `handleSwap`, `nextFree`) is
  preserved unchanged.

- [ ] 2. Move want-amount entry into step 2 (depends on 1) — DoD: the
  `wantAmount` state is populated via the `RateSlider`'s top input field in
  step 2, not from a standalone input in step 1; the `amountValid` check
  (regex + positive-number guard, currently line 60 `CreateOrder.tsx`) gates
  the step-2 "Continue" MainButton; the step-1 → step-2 transition no longer
  requires a valid amount.

- [ ] 3. Render all give-option blocks in step 2 (depends on 2) — DoD: step 2
  iterates over the full `opts[]` array; each entry renders an asset label
  header, a `RateSlider` (base=`wantAsset`, quote=`opt.asset`,
  wantAmount/onWantAmountChange shared, onRateResolved updating that opt's
  `max_rate`), and a payment-method chip row; a remove button appears on each
  block when `opts.length > 1` and calls a handler that splices the entry out
  of `opts`; the existing `updateOpt` and `toggleMethod` helpers are used
  without modification.

- [ ] 4. Add "Add alternative" button in step 2 (depends on 3) — DoD: an "Add
  alternative" button appears below the last give-option block when
  `opts.length < ASSETS.length - 1` (i.e. there is a remaining free asset);
  tapping it appends a new `OptDraft` with `asset = nextFree(giveAsset,
  wantAsset)` if `opts.length === 1`, or the sole remaining asset when
  `opts.length === 2`; a comment `// TODO: extend when ASSETS grows` is placed
  at this logic; the new block scrolls into view via `scrollFieldIntoView` on
  the next render.

- [ ] 5. Move city field to step 3 and update submit to serialise all opts
  (depends on 3) — DoD: step 3 renders a city input (with pin icon, matching
  current step-1 styling) above the comment textarea; step 1 no longer renders
  city; the `submit` function maps the full `opts` array to
  `give_options: opts.map(o => ({ asset: o.asset, max_rate: o.max_rate.trim()
  || null, payment_methods: o.payment_methods }))` instead of using only
  `opts[0]`; the `POST /orders` payload is otherwise unchanged; the live
  `OrderCard` preview in step 3 reflects all give options.

- [ ] 6. Verify MainButton state machine for the new step layout (depends on
  5) — DoD: `nextEnabled` evaluates to `true` in step 1 unconditionally
  (pair always selected), in step 2 when `amountValid`, and in step 3 when
  `!busy`; `nextText` reads "Continue" on steps 1 and 2, "Publish request" on
  step 3; the `showBackButton` effect fires on steps 2 and 3 (not step 1);
  no MainButton regression on the existing Telegram and non-Telegram (fallback
  `<button>`) paths.

---

## Tests

- [ ] T1. Unit-level: render `CreateOrder` in isolation (React Testing Library
  or Vitest + jsdom); assert that step 1 contains the `CurrencyPairPicker` and
  does NOT contain an amount `<input>`; assert that clicking Continue (or
  simulating the MainButton callback) advances to step 2.

- [ ] T2. Unit-level: at step 2 with a mocked `/rates/reference` response,
  assert that typing into the want-amount field updates the give-amount display;
  assert that moving the slider recomputes give-amount; assert that the slider
  `max` attribute equals `refRate * 1.10` (±0.01 tolerance).

- [ ] T3. Unit-level: at step 2 with `opts` containing two entries, assert that
  two `RateSlider` blocks are rendered; assert that the remove button on block 0
  reduces `opts` to length 1; assert that when `opts.length === 1` no remove
  button is rendered.

- [ ] T4. Integration smoke: start the API locally (`AUTH_DEV_BYPASS=true`);
  complete the three-step flow with a two-option order (EUR want, RUB + USDT
  give); assert `POST /orders` is called once with `give_options` of length 2,
  each with a non-null `max_rate` within ±10% of the reference; assert the
  response `id` is present and the new order appears in `GET /orders`.

- [ ] T5. Regression: existing single-option happy path — complete the flow
  with one give option; confirm the `POST /orders` body matches the shape
  produced before this change (one-element `give_options` array).

- [ ] T6. Fallback: mock `GET /rates/reference` to return 503 for one of the
  two give options; assert the corresponding block falls back to a free-text
  rate input with the unavailability note; assert the other block still renders
  the slider normally; assert the order can be submitted with the free-text
  rate.

---

## Rollback

This change is front-end only (`web/src/screens/CreateOrder.tsx`). No
database migration, no schema change, no breaking API change.

To roll back:
1. `git revert <merge-commit>` on the feature branch — or simply redeploy the
   previous image tag from the registry
   (`ghcr.io/mctlhq/mctl-pairdesk:<previous-tag>`).
2. The backend is unaffected and does not need to be rolled back.
3. Orders already created with two give options remain valid in the database and
   display correctly in the existing `OrderCard` multi-option rendering; no data
   cleanup is needed.
