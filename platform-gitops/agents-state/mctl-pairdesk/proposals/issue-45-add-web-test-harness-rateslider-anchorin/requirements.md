# Add web test harness and RateSlider anchoring tests

## Context

The `web/` package is a React + Vite Mini App with no test framework. Its
`package.json` has three scripts — `build`, `dev`, and `type-check` — and
the CI `web` job in `.github/workflows/ci.yml` runs only `npm run type-check`
and `npm run build`. There are no test files anywhere under `web/`. The only
frontend gate is `tsc --noEmit`.

PR #44 (closing issue #38) added two-way anchoring to the `RateSlider`
component in `web/src/components.tsx`. A claude-review on #44 confirmed the
logic is correct but flagged the absence of test coverage as P2. This issue
spins that work out separately so it does not delay the 0.12.0 release.
Standing up the harness also unblocks future `web/` test authoring.

## User stories

- AS a developer I WANT a `npm test` script in `web/` SO THAT I can run
  component tests locally without any extra setup.
- AS a CI pipeline I WANT a `npm test` step in the `web` GitHub Actions job
  SO THAT anchoring regressions are caught automatically on every PR.
- AS a developer I WANT vitest unit tests for the `RateSlider` component SO
  THAT the two-way anchoring logic introduced in #44 is documented and
  protected against regression.

## Acceptance criteria (EARS)

### Harness setup

- WHEN `npm test` is run inside `web/` THE SYSTEM SHALL execute the vitest
  test suite and exit non-zero if any test fails.
- WHEN `npm run test:watch` is run inside `web/` THE SYSTEM SHALL start vitest
  in watch mode for interactive development.
- WHEN `npm run type-check` is run inside `web/` THE SYSTEM SHALL still pass
  (test files included in the TypeScript compilation scope).
- WHILE the test environment is initialised THE SYSTEM SHALL provide a jsdom
  DOM so React components can be rendered without a browser.
- WHEN the CI `web` job runs on a pull request THE SYSTEM SHALL execute
  `npm test` after `npm run type-check` and fail the job if any test fails.

### RateSlider — want anchors (slider varies give)

- WHEN the give input is not focused AND the slider value changes THE SYSTEM
  SHALL update the give input to `wantAmount × newRate` without calling
  `onWantAmountChange`.

### RateSlider — give anchors (give drives want)

- WHEN the give input has focus AND the user types a valid positive number THE
  SYSTEM SHALL call `onWantAmountChange` with `(giveValue / resolvedRate)`
  formatted to two decimal places.
- WHEN the give input has focus AND the slider value changes THE SYSTEM SHALL
  NOT update the give input display value and SHALL NOT call
  `onWantAmountChange`.

### RateSlider — non-anchored side updates on rate change

- WHEN the reference rate is fetched and `editingGive.current` is false THE
  SYSTEM SHALL call `onRateResolved` with the resolved rate string and update
  the give input to `wantAmount × resolvedRate`.
- WHEN `wantAmount` prop changes and the give input does not have focus THE
  SYSTEM SHALL recompute the give input to `wantAmount × resolvedRate`.

### RateSlider — pair change resets

- WHEN the `base` or `quote` prop changes THE SYSTEM SHALL call
  `onRateResolved(null)`, reset the slider offset to 0, clear the give input,
  and issue a new `/rates/reference` fetch for the new pair.

### RateSlider — edge cases

- IF the give input value is not a finite positive number THEN THE SYSTEM SHALL
  NOT call `onWantAmountChange`.
- IF `resolvedRate` is not a positive finite number THEN THE SYSTEM SHALL NOT
  call `onWantAmountChange` from the give onChange handler (division-by-zero
  guard at line 687 in `web/src/components.tsx`).
- WHEN the give input is blurred with an empty value AND `wantAmount` is a
  finite positive number THE SYSTEM SHALL auto-fill the give input with
  `wantAmount × resolvedRate`.
- WHEN the reference rate API call fails THE SYSTEM SHALL show the unavailable
  fallback UI (free-text rate input) and call `onRateResolved(null)`.

## Out of scope

- Tests for any component other than `RateSlider`.
- End-to-end or integration tests (no Playwright/Cypress setup).
- Coverage reporting or thresholds.
- Snapshot tests.
- Changes to backend or API behaviour.

## Open questions

- The issue states "give field anchors — slider varies want" as test scenario 2.
  Reading the code: while the give input IS focused, moving the slider does NOT
  recalculate the want field; the effect is blocked by the `editingGive.current`
  guard (line 599-606). The want updates only when the user types in the give
  field (onChange, line 683-689). The tests should verify actual code behaviour.
  If the intent is for the slider to drive want while give is anchored
  (even after blur), that would require a different state model and is a
  separate scope change. The proposal assumes current code behaviour is correct
  (confirmed sound by claude-review on #44).
- The `web/tsconfig.json` uses `"moduleResolution": "Bundler"` and strict
  mode. Vitest type globals (`vi`, `describe`, `it`, `expect`) can be exposed
  via `"types": ["vitest/globals"]` in tsconfig or imported explicitly. The
  proposal recommends explicit imports to stay consistent with the existing
  strict / no-unused-locals setup.
