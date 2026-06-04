# Tasks: issue-53-p3-create-order-has-no-ttl-expiry-picker

All changes live in `web/src/screens/CreateOrder.tsx` only (one file).
No API, DB, or serializer changes are required.

- [ ] 1. Add `EXPIRY_PRESETS` constant and `expiresInSeconds` state to `CreateOrder`
  — DoD: `EXPIRY_PRESETS` is defined above the component as a `const` array of
  `{ label, seconds }` tuples for 1 h / 6 h / 24 h / 72 h; `useState(259_200)` is
  added inside the component; TypeScript compiles without error (`npm run build:api`
  and the web Vite build both pass).

- [ ] 2. Include `expires_in_seconds` in the POST body inside `submit()` (depends on 1)
  — DoD: the `api.post('/orders', { ..., expires_in_seconds: expiresInSeconds })`
  call in `submit()` sends the selected value; verified by inspecting the Network tab
  in dev with `AUTH_DEV_BYPASS=true` and confirming the JSON body contains the field.

- [ ] 3. Render the expiry chip picker in the step-3 JSX block (depends on 1)
  — DoD: a labelled group of four `pd-chip pd-chip-sm` buttons (1 h / 6 h / 24 h /
  72 h) appears between the Notes textarea and the preview block in step 3; the
  selected chip carries the `is-on` class; clicking a chip calls `hapticSelection()`
  and updates `expiresInSeconds`; the 72 h chip is highlighted by default on fresh
  mount; selection survives a step-2 → step-3 back-and-forward cycle.

- [ ] 4. Add expiry annotation below the preview card in step 3 (depends on 1, 3)
  — DoD: a muted `pd-form-sub` line with the clock icon and text "expires in Xh" is
  rendered directly below `<OrderCard order={previewOrder} variant="outcome" />`; the
  label updates synchronously when a different chip is selected.

- [ ] 5. Update `previewOrder.expires_at` to reflect the selected preset (depends on 1)
  — DoD: `previewOrder.expires_at` is set to
  `new Date(Date.now() + expiresInSeconds * 1000).toISOString()` rather than `null`;
  TypeScript is happy; no visual regression in the preview card (OrderCard
  `variant="outcome"` does not currently render `expires_at`, so this is a non-visible
  but forward-compatible fix).

## Tests

- [ ] T1. Manual smoke — dev mode: start the server with `AUTH_DEV_BYPASS=true`
  `ORDER_TTL_SECONDS=259200`, open the Create-Order flow, confirm that 72 h is
  pre-selected, select 1 h, publish an order, and verify that the returned order's
  `expires_at` is approximately `now + 3,600 s` (not `now + 259,200 s`).

- [ ] T2. Manual smoke — default preserved: repeat T1 without touching the picker
  (leave 72 h selected) and confirm `expires_at ≈ now + 259,200 s`.

- [ ] T3. Back-navigation persistence: on step 3, select 6 h, click Back to step 2,
  click Continue back to step 3, confirm the 6 h chip is still highlighted.

- [ ] T4. API boundary — minimum: craft a direct `POST /api/orders` with
  `expires_in_seconds: 299` (below the 300 s minimum) and confirm the API returns
  HTTP 400 with the "out of range" message. This exercises the existing server
  validation, not the new UI, but should be confirmed as a sanity check.

- [ ] T5. Existing expiry integration test: run `npm run test:expiry` (exercises
  `expireStaleOrders()` in `tests/integration/expiry.test.mjs`) to confirm no
  regression.

- [ ] T6. TypeScript build: `npm run build:api` passes with no new type errors after
  the changes.

## Rollback

The change is isolated to `web/src/screens/CreateOrder.tsx` and does not touch
the API, database schema, or any other component.

To roll back:
1. Revert the single file change to `web/src/screens/CreateOrder.tsx` (git revert
   the feature commit, or `git checkout main -- web/src/screens/CreateOrder.tsx`).
2. Rebuild the web bundle (`npm run build` in `web/`).
3. Deploy. No DB migration, no data backfill, no config change is needed.

Orders already published with a non-default TTL retain their `expires_at` in the
database and continue to expire correctly regardless of the UI rollback; the rollback
only prevents future orders from carrying a client-chosen TTL.
