# fix(web): Create Order step 1 — collision auto-bump selects the wrong asset

## Context

The Create Order step-1 currency-pair picker (delivered in PR #27, issue #22) includes
auto-bump logic: when the user selects a give or want asset that collides with the other
side, the component automatically displaces the colliding side to a free asset. With three
supported assets (EUR, RUB, USDT defined in `ASSETS` in `web/src/types.ts`), exactly one
"third" asset is always available after excluding two.

The shipped implementation passes the same argument twice to `nextFree(exclude1, exclude2)`,
so only one asset is actually excluded. The bump therefore returns the wrong asset — the
first non-colliding entry in `ASSETS` rather than the genuinely uninvolved third asset.
The pair produced is always distinct (no crash, no type error), which is why automated
checks passed, but it contradicts the acceptance tests (T3, T4) written for issue #22.

## User stories

- AS a community member creating an order I WANT the give/want pair to update predictably
  when I change one side to match the other SO THAT I can trust the displayed pair without
  manually correcting it.
- AS a community member I WANT the auto-bumped asset to be the uninvolved third currency
  SO THAT my earlier implicit choice (the asset that was neither give nor want before I
  changed anything) is preserved as the new opposite side.

## Acceptance criteria (EARS)

- WHEN the user selects a give asset equal to the current want asset, THE SYSTEM SHALL
  update the want asset to the asset that is neither the new give asset nor the old give
  asset (i.e. the uninvolved third asset).
- WHEN the user selects a want asset equal to the current give asset, THE SYSTEM SHALL
  update the give asset to the asset that is neither the new want asset nor the old want
  asset (i.e. the uninvolved third asset).
- WHILE the user has not triggered a collision (selected give != want), THE SYSTEM SHALL
  leave the opposite asset unchanged.
- WHEN give=RUB and want=EUR and the user changes give to EUR, THE SYSTEM SHALL set
  want=USDT (acceptance test T3 from issue #22).
- WHEN give=RUB and want=EUR and the user changes want to RUB, THE SYSTEM SHALL set
  give=USDT (acceptance test T4 from issue #22).
- WHEN any asset selection change occurs, THE SYSTEM SHALL continue to emit a haptic
  selection signal exactly once per change (no regression on haptic behavior).
- IF `npm run type-check` is executed in the `web/` directory, THEN THE SYSTEM SHALL exit
  with code 0 (no new TypeScript errors).
- IF `npm run build` is executed in the `web/` directory, THEN THE SYSTEM SHALL exit with
  code 0 (Vite build succeeds).

## Out of scope

- Any change to the API, database schema, or server-side routes.
- Changes to files other than `web/src/screens/CreateOrder.tsx`.
- Removal of the `opts[0].asset` dead-state field (noted as an optional nit in the issue;
  deferred to avoid scope creep on a focused bugfix).
- Behavior when `ASSETS` contains fewer than three entries (current invariant: exactly
  EUR, RUB, USDT; `nextFree` relies on `Array.find` returning a non-null value).
- Multi-give-option UI (not yet implemented; `opts` array is always length 1 in step 2).

## Open questions

None. The issue fully specifies the root cause, the two-line fix, the exact acceptance
tests, and the success criteria. The optional nit (cleaning up `opts[0].asset` dead state)
is recorded above under "Out of scope" and may be addressed in a follow-up.
