# Tasks: issue-36-fix-web-entered-city-missing-from-live-p

- [ ] 1. Fix outcome variant footer in `web/src/components.tsx` — remove
  `location_city` from the `Maker` `sub` prop; add a sibling
  `{order.location_city && <span className="pd-loc"><Icon name="pin" size={12} cls="pd-mut-ic" />{order.location_city}</span>}`
  element between `<Maker maker={order.maker} />` and `<span className="pd-spacer" />`.
  DoD: the `Maker` call in the outcome variant has no `sub` prop; a `pd-loc`
  span is rendered conditionally on `order.location_city`; the existing
  `fmtRelTime` timestamp span is unchanged.

- [ ] 2. Fix rate variant footer in `web/src/components.tsx` (depends on 1,
  same pattern) — apply the identical decoupling: remove city from the `Maker`
  `sub` prop and add a sibling `pd-loc` span.
  DoD: the `Maker` call in the rate variant has no `sub` prop; a `pd-loc` span
  is rendered conditionally on `order.location_city`; no other rate variant
  markup is changed.

- [ ] 3. Build the web bundle and confirm no TypeScript or Vite compile errors.
  DoD: `npm run build` (or `npm run build:web` if the script is separate)
  exits 0 with no type errors in `web/src/components.tsx` or
  `web/src/screens/CreateOrder.tsx`.

## Tests

- [ ] T1. Manual smoke — Create-Order step 3 preview shows city: open the
  Mini App in dev mode (`AUTH_DEV_BYPASS=true`), navigate to Create Order,
  advance to step 3, type "Podgorica" in the City field. The preview card
  should show a pin icon followed by "Podgorica" in the card footer. Clearing
  the field should remove the pin immediately.

- [ ] T2. Manual smoke — preview with no city: on step 3 leave the City field
  empty. The preview card footer should show no pin element and no empty text.

- [ ] T3. Manual smoke — published order in outcome variant: after publishing
  an order with a city set, open the order book and verify the city pin appears
  on the order's card (outcome variant). Verify an order without a city shows
  no pin.

- [ ] T4. Manual smoke — own orders list (rate variant): open the "My orders"
  / orders screen that uses the rate variant. For an order that has
  `location_city` set, verify the city pin appears in the card footer. For an
  order with no city, verify no pin is shown.

- [ ] T5. Regression — maker + city in outcome variant: verify that a book
  order that has both a maker and a city still shows the maker row (avatar,
  name, rating/deals) AND the city pin. Both elements must be visible; neither
  should suppress the other.

## Rollback

The fix touches two JSX blocks inside `web/src/components.tsx`. Rollback is a
plain `git revert` of the commit that introduced the change, followed by
rebuilding the web bundle (`npm run build`). No database state, API contract,
or server-side code is affected. The revert restores the previous behavior
where city is passed as `Maker sub` and is invisible in the preview; no user
data is lost.
