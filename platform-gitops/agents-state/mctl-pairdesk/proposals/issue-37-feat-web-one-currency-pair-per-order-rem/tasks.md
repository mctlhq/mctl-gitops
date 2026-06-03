# Tasks: issue-37-feat-web-one-currency-pair-per-order-rem

- [ ] 1. Remove multi-option state and helpers from `CreateOrder.tsx` —
  DoD: `nextOptId` state, `removeOpt`, `addAlternative`, and
  `canAddAlternative` are deleted from
  `web/src/screens/CreateOrder.tsx`; the file compiles with
  `npm run build:api` (which also type-checks `web/` via tsc) and no
  TypeScript errors are reported.

- [ ] 2. Simplify the giveAsset sync `useEffect` (depends on 1) —
  DoD: the `useEffect` at lines 57-85 of `CreateOrder.tsx` is replaced
  with the minimal single-branch form described in design.md
  (retarget `opts[0].asset` to `giveAsset` and reset rate/methods when
  the asset changes; no `wantAsset` dependency; no promote/dedup logic).
  The file still compiles without errors.

- [ ] 3. Simplify the Step-2 render in `CreateOrder.tsx` (depends on 1) —
  DoD: the `opts.map(...)` loop in the step-2 block is replaced by a
  direct render of `opts[0]`; the per-option remove button (`i > 0`
  branch) is removed; the `canAddAlternative &&` "Add alternative"
  button block is removed; the `.pd-give-editor-head` asset-label row
  is removed (the label is redundant with Step 1). No TypeScript errors.

- [ ] 4. Remove dead CSS (depends on 3) —
  DoD: the `.pd-add-alt` rule block (lines 1036-1052 of
  `web/src/styles.css`) is deleted. A global search for `.pd-add-alt`
  in `web/` returns no results, confirming no JSX references it.

- [ ] 5. Manual smoke-test and PR (depends on 2, 3, 4) —
  DoD: see Tests section below; a PR is opened against `main` from a
  feature branch named `feat/issue-37-one-give-option`; CI is green;
  the PR description references issue #37.

## Tests

- [ ] T1. Step 1 — selecting EUR/RUB, EUR/USDT, or RUB/USDT as the pair
  and advancing to Step 2 shows exactly one give-option editor whose
  asset label matches the Step-1 give selection.
- [ ] T2. Step 2 — no "Add alternative" button is visible anywhere in the
  step-2 form.
- [ ] T3. Step 2 — no per-option remove button (the "x" / close icon)
  appears on the single give-option editor.
- [ ] T4. Step 1 → back navigation — going back from Step 2 to Step 1,
  changing the give-asset, then re-entering Step 2 shows the new asset
  in the editor and blank rate/methods (not the previous values).
- [ ] T5. Swap — using the swap button on Step 1 (give ↔ want) then
  proceeding to Step 2 shows the swapped give-asset correctly.
- [ ] T6. Publish — completing all steps and publishing an order results
  in a `POST /orders` payload (visible via network inspector or server
  log) whose `give_options` array has exactly one element with the
  correct `asset`, `max_rate` (or null), and `payment_methods`.
- [ ] T7. No TypeScript errors — `npx tsc --noEmit` (or equivalent
  build step) passes with zero errors after all changes.

## Rollback

The changes are contained entirely within `web/src/screens/CreateOrder.tsx`
and `web/src/styles.css` — two files with no server-side dependencies. To roll
back:

1. Revert the feature branch commits on the PR (GitHub "Revert" button) or
   run `git revert <commit-sha>` locally.
2. Re-deploy the previous Mini App bundle; the server-side API is unchanged
   and continues to accept both single- and multi-element `give_options`
   arrays, so no server rollback is needed.
3. Confirm the old Step-2 "+ Add alternative" button reappears on a fresh
   Mini App load.
