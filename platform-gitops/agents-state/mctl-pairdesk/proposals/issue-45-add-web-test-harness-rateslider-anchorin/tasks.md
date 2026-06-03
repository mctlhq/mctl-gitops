# Tasks: issue-45-add-web-test-harness-rateslider-anchorin

All changes are inside the `web/` directory and `.github/workflows/ci.yml`.
No backend files are touched.

---

- [ ] 1. Add test devDependencies and scripts to web/package.json

  Add to `devDependencies`:
  - `vitest` (latest compatible with vite 5)
  - `jsdom`
  - `@testing-library/react`
  - `@testing-library/user-event`
  - `@testing-library/jest-dom`

  Add to `scripts`:
  - `"test": "vitest run"`
  - `"test:watch": "vitest"`

  DoD: `npm install` inside `web/` succeeds; `npm test` exits non-zero with
  "No test files found" (the runner is wired up but no test file exists yet).

---

- [ ] 2. Create web/vitest.config.ts (depends on 1)

  New file at `web/vitest.config.ts`:

  ```ts
  import react from '@vitejs/plugin-react';
  import { defineConfig } from 'vitest/config';

  export default defineConfig({
    plugins: [react()],
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test-setup.ts'],
    },
  });
  ```

  DoD: `npm test` inside `web/` resolves the config without errors. The
  `vite.config.ts` build settings (`base: '/app/'`, `outDir`) are unaffected.

---

- [ ] 3. Create web/src/test-setup.ts (depends on 2)

  New file at `web/src/test-setup.ts`:

  ```ts
  import '@testing-library/jest-dom';
  ```

  DoD: `@testing-library/jest-dom` matchers (`toBeInTheDocument`, `toHaveValue`,
  etc.) are available in every test file without explicit import. `npm run
  type-check` still passes (`web/tsconfig.json` `include` covers `src/**`).

---

- [ ] 4. Write web/src/RateSlider.test.tsx (depends on 3)

  New file containing all RateSlider unit tests. Skeleton structure:

  ```tsx
  import { render, screen, waitFor, fireEvent } from '@testing-library/react';
  import userEvent from '@testing-library/user-event';
  import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
  import { RateSlider } from './components';

  vi.mock('./api.js', () => ({ api: { get: vi.fn() } }));
  vi.mock('./tg.js', () => ({ scrollFieldIntoView: vi.fn(), initData: vi.fn(() => '') }));

  import { api } from './api.js';
  const mockGet = vi.mocked(api.get);
  ```

  Each `describe` block corresponds to one scenario. `beforeEach` calls
  `vi.clearAllMocks()` and sets `mockGet.mockResolvedValue({ rate: 100 })`.

  Helper: a `renderSlider` factory that accepts partial props and provides
  `vi.fn()` callbacks for `onWantAmountChange` and `onRateResolved`, returning
  `{ onWantAmountChange, onRateResolved, rerender }`.

  DoD: `npm test` exits 0 with all test cases passing (see Tests section below).

---

- [ ] 5. Add npm test step to CI web job in .github/workflows/ci.yml (depends on 4)

  In the `web` job, add `- run: npm test` between `npm run type-check` and
  `npm run build`:

  ```yaml
  - run: npm run type-check
  - run: npm test
  - run: npm run build
  ```

  DoD: on a PR, the `web` job in GitHub Actions runs all three steps in order.
  The job is red if any test fails.

---

## Tests

All tests live in `web/src/RateSlider.test.tsx`.

- [ ] T1. **Want anchors — slider moves, give updates, want unchanged**

  Setup: render with `wantAmount="10"`, `mockGet` resolves `{ rate: 100 }`.
  Wait for give input to show `"1000.00"` (10 × 100). Fire `change` on the
  range input with `value = 110` (rate +10). Assert: give input displays
  `"1100.00"` (10 × 110); `onWantAmountChange` is never called.

  Exercises: `editingGive.current === false` branch in the second `useEffect`
  (components.tsx line 603-605).

- [ ] T2. **Give anchors — typing give updates want**

  Setup: render with `wantAmount="10"`, refRate = 100. Wait for rate load.
  Click the give input (triggers focus → `editingGive.current = true`). Type
  `"1200"`. Assert: `onWantAmountChange` is called with `"12.00"` (1200 / 100).

  Exercises: give onChange handler (components.tsx lines 683-689).

- [ ] T3. **Give anchors — slider does not override give while give has focus**

  Setup: same as T2. Focus give input; do NOT blur. Fire `change` on slider to
  a new rate. Assert: give input value is unchanged; `onWantAmountChange` is
  NOT called by the slider effect.

  Exercises: the `if (!editingGive.current)` guard (components.tsx line 603).

- [ ] T4. **Non-anchored side updates on refRate arrival**

  Setup: render with `wantAmount="5"`. Verify that when `mockGet` resolves
  `{ rate: 200 }`, `onRateResolved` is called with `"200.00000000"` and the
  give field shows `"1000.00"` (5 × 200).

  Exercises: the second `useEffect` main path (components.tsx lines 599-606).

- [ ] T5. **wantAmount prop change recalculates give**

  Setup: render with `wantAmount="10"`, refRate = 100. Wait for load (give =
  "1000.00"). Rerender with `wantAmount="20"`. Assert: give field shows
  `"2000.00"`; `onWantAmountChange` is NOT called (give updates, not want).

  Exercises: the third `useEffect` (components.tsx lines 609-614).

- [ ] T6. **Pair change resets state and re-fetches rate**

  Setup: render with `base="EUR"`, `quote="RUB"`, refRate = 100. Wait for load.
  Rerender with `base="EUR"`, `quote="USDT"`, new mock returning `{ rate: 1 }`.
  Assert: `onRateResolved` is called with `null` (reset) then with the new rate;
  give field is recalculated for the new pair.

  Exercises: the first `useEffect` cleanup and re-run (components.tsx lines
  585-595).

- [ ] T7. **Edge: non-finite give input — want not updated**

  Setup: focus give input, type `"abc"`. Assert: `onWantAmountChange` is NOT
  called (`Number.isFinite("abc")` is false; guard at components.tsx line 687).

- [ ] T8. **Edge: division-by-zero guard**

  Setup: `mockGet` resolves `{ rate: 0 }`. Wait for the rate to arrive. Focus
  give, type `"100"`. Assert: `onWantAmountChange` is NOT called (`resolvedRate
  > 0` is false; guard at components.tsx line 687).

- [ ] T9. **Edge: blur auto-fill — empty give is filled from want**

  Setup: render with `wantAmount="10"`, refRate = 100. Wait for load. Click
  give input, clear it to `""`, then blur. Assert: give input value is
  `"1000.00"` (auto-filled from wantAmount × resolvedRate; components.tsx
  lines 694-700).

- [ ] T10. **Edge: API failure shows unavailable fallback UI**

  Setup: `mockGet` rejects with an error. Assert: the placeholder text "rate"
  is visible (the unavailable-state give input; components.tsx line 638) and
  a free-text rate input is shown; `onRateResolved` is called with `null`.

---

## Rollback

If the test infrastructure causes problems (e.g., jsdom version conflict, CI
flakiness), rolling back requires:

1. Revert `web/package.json` to remove the four test devDependencies and the
   two test scripts. Run `npm install` inside `web/` to update `package-lock.json`.
2. Delete `web/vitest.config.ts`.
3. Delete `web/src/test-setup.ts`.
4. Delete `web/src/RateSlider.test.tsx`.
5. Remove the `- run: npm test` line from the `web` job in
   `.github/workflows/ci.yml`.

No production code in `web/src/components.tsx` or any backend file is modified
by this issue, so rollback has zero runtime impact.
