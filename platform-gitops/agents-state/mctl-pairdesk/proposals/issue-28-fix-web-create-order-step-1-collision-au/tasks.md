# Tasks: issue-28-fix-web-create-order-step-1-collision-au

- [ ] 1. Fix collision auto-bump in `handleGiveChange` — in
  `web/src/screens/CreateOrder.tsx` line 43, change
  `setWantAsset(nextFree(a, a))` to `setWantAsset(nextFree(a, giveAsset))`.
  DoD: the argument change is in place; `giveAsset` (the pre-update closure value)
  is the second argument.

- [ ] 2. Fix collision auto-bump in `handleWantChange` (depends on 1) — in
  `web/src/screens/CreateOrder.tsx` line 49, change
  `setGiveAsset(nextFree(a, a))` to `setGiveAsset(nextFree(a, wantAsset))`.
  DoD: the argument change is in place; `wantAsset` (the pre-update closure value)
  is the second argument.

- [ ] 3. Verify build and types (depends on 1, 2) — run `npm run type-check` and
  `npm run build` inside the `web/` directory.
  DoD: both commands exit with code 0; no new TypeScript or Vite errors.

## Tests

- [ ] T3. Manual: open Create Order step 1 with defaults (give=RUB, want=EUR).
  Change give to EUR. Confirm want automatically changes to USDT (not RUB).

- [ ] T4. Manual: open Create Order step 1 with defaults (give=RUB, want=EUR).
  Change want to RUB. Confirm give automatically changes to USDT (not EUR).

- [ ] T5. Regression: change give to USDT (no collision with want=EUR). Confirm
  want stays EUR (no spurious bump when there is no collision).

- [ ] T6. Regression: use the swap button. Confirm give and want exchange correctly
  (handleSwap is unaffected by this change).

- [ ] T7. Regression: proceed through step 2 and step 3 and submit an order.
  Confirm the submitted `give_options[0].asset` matches the give asset shown in
  the step-1 picker after any auto-bump.

## Rollback

The change is isolated to two lines in one file with no API or schema impact. To
roll back: revert `web/src/screens/CreateOrder.tsx` to the previous commit's version
(`git revert <commit>` or `git checkout <previous-sha> -- web/src/screens/CreateOrder.tsx`)
and redeploy the web build. No database migration or API version change is required.
