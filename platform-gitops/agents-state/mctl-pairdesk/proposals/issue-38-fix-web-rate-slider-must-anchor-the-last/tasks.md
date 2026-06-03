# Tasks: issue-38-fix-web-rate-slider-must-anchor-the-last

All changes are in `web/src/components.tsx`, function `RateSlider` (lines 572-731).
No other files require modification.

- [ ] 1. Remove `editingGive` ref; add `lastEditedField` ref and `giveInputValueRef`
  — In `RateSlider`, delete `const editingGive = useRef(false);` (line 577).
  Add `const lastEditedField = useRef<'want' | 'give'>('want');`.
  Add `const giveInputValueRef = useRef(giveInputValue);` and a sync effect
  `useEffect(() => { giveInputValueRef.current = giveInputValue; });` immediately
  after, mirroring the existing `wantAmountRef` pattern (lines 581-582).
  DoD: file compiles with no TypeScript errors; the old ref name does not appear
  in the `RateSlider` function body.

- [ ] 2. Reset anchor and give value on pair change (depends on 1)
  — In the `useEffect([base, quote])` reset block (lines 585-595), add
  `lastEditedField.current = 'want';` and `setGiveInputValue('');` before the
  `onRateResolved(null)` call.
  DoD: switching the currency pair from the step-1 pair picker clears the give
  amount field and resets slider behaviour to want-anchored.

- [ ] 3. Update the slider/rate-change effect to branch on lastEditedField (depends on 1)
  — Replace the body of `useEffect([refRate, offsetPct, unavailable])` (lines 598-606)
  so that:
    - if `lastEditedField.current === 'want'`: compute give as `want * resolvedRate`
      (current behaviour, using `wantAmountRef.current`).
    - else (`'give'`): compute want as `give / resolvedRate` using
      `giveInputValueRef.current`; call `onWantAmountChange` with the result.
  DoD: dragging the slider after typing a give amount updates the want field and
  leaves the give field unchanged.

- [ ] 4. Update the wantAmount-change effect guard (depends on 1)
  — In `useEffect([wantAmount])` (lines 609-614), replace the guard
  `editingGive.current` with `lastEditedField.current !== 'want'`.
  DoD: typing in the want field updates give in real time when want is the anchor;
  typing in the give field (which calls `onWantAmountChange` internally) does not
  clobber the give value.

- [ ] 5. Set anchor in want input onChange (depends on 1)
  — In the want input's `onChange` handler (line 671), prepend
  `lastEditedField.current = 'want';` before the `onWantAmountChange` call.
  DoD: after typing into want, the anchor is 'want'.

- [ ] 6. Set anchor in give input onChange; remove onFocus (depends on 1)
  — In the give input's `onChange` handler (lines 683-689), prepend
  `lastEditedField.current = 'give';`.
  Remove the `onFocus={() => { editingGive.current = true; }}` handler (line 691).
  DoD: after typing into give, the anchor is 'give'; no TypeScript error for missing
  `editingGive`.

- [ ] 7. Simplify give input onBlur (depends on 1)
  — In the give input's `onBlur` handler (lines 692-700), remove the
  `editingGive.current = false;` line. Keep the empty-value restoration logic
  unchanged.
  DoD: blurring an empty give field still restores the derived value; no reference
  to `editingGive` remains.

- [ ] 8. Build and smoke-test (depends on 2-7)
  — Run `npm run build:api` (or the web build target) to confirm no compile errors.
  DoD: build exits 0; no TypeScript or Vite errors.

---

## Tests

Manual test matrix (no automated browser tests exist in this repo):

- [ ] T1. Want-first anchor: open Create-Order, step 2. Type `1000` in the EUR field.
  Drag the rate slider. EUR must stay `1000`; RUB must change. Pass if EUR is unchanged
  throughout all slider positions.

- [ ] T2. Give-first anchor: type `80000` in the RUB field. Drag the slider. RUB must
  stay `80000`; EUR must change. Pass if RUB is unchanged throughout all slider positions.

- [ ] T3. Anchor switch: type `1000` in EUR (anchor = want). Then type `80000` in RUB
  (anchor = give). Drag slider. RUB must stay `80000`; EUR must change. Then type `500`
  in EUR (anchor = want). Drag slider. EUR must stay `500`; RUB must change.

- [ ] T4. Pair switch resets anchor: set EUR=1000, drag slider to an offset. Change the
  currency pair (step 1 picker). Return to step 2. Verify give field is empty and slider
  is back at market reference (0%); typing into either field sets a fresh anchor.

- [ ] T5. Rate label in sync: in all T1-T4 scenarios, the rate value and delta chip in
  `pd-slider-info` must always reflect the current resolved rate.

- [ ] T6. onBlur restoration: type `1000` in EUR (anchor = want). Type into RUB then
  clear it entirely (anchor = give). Blur the RUB field. RUB must be restored to
  `1000 * resolvedRate`. Drag slider: RUB must still be the anchor (anchor was set when
  the user typed into RUB, before clearing).

- [ ] T7. Unavailable fallback unchanged: force `/rates/reference` to return a non-200
  (e.g., proxy-block in dev). Step 2 must render the free-text rate input, not the
  slider. No anchor logic applies. Existing behaviour preserved.

---

## Rollback

This change is frontend-only and self-contained. To roll back:

1. Revert the commit that implements this fix (`git revert <sha>`), or
2. Restore the original lines in `web/src/components.tsx` from the PR diff:
   - Reinstate `const editingGive = useRef(false);`
   - Reinstate `onFocus={() => { editingGive.current = true; }}` on the give input
   - Reinstate `editingGive.current = false;` in the give input onBlur
   - Restore the original `useEffect([refRate, offsetPct, unavailable])` body
   - Restore the original `useEffect([wantAmount])` guard
   - Remove the `lastEditedField` ref, `giveInputValueRef`, and their sync effects
3. Rebuild the web app and redeploy.

No database migration, no API change, no feature flag: rollback is instantaneous.
