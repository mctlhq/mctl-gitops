# Design: issue-45-add-web-test-harness-rateslider-anchorin

## Current state

### web/ package

`web/package.json` declares three npm scripts: `build` (vite build), `dev`
(vite dev server), and `type-check` (tsc --noEmit). There are no test
dependencies, no test configuration, and no test files anywhere under `web/`.

The CI pipeline in `.github/workflows/ci.yml` has a dedicated `web` job that
runs:

```yaml
- run: npm ci
- run: npm run type-check
- run: npm run build
```

There is no `npm test` step. The only correctness gate for the frontend is
TypeScript's type checker.

### RateSlider component

`web/src/components.tsx` lines 560-731 define `RateSlider`. The component
manages three pieces of local state:

- `refRate: number | null` — reference rate fetched from
  `GET /api/rates/reference?base=&quote=` via `api.get` (from `web/src/api.ts`)
- `offsetPct: number` — slider position as a percentage deviation from refRate
  (clamped to `±MAX_DEVIATION_PCT = 10`)
- `giveInputValue: string` — controlled value of the give amount text input

And one mutable ref:

- `editingGive: React.MutableRefObject<boolean>` — `true` when the give input
  has focus, `false` otherwise (set on `onFocus`/`onBlur`)

**Three `useEffect`s drive the anchoring logic:**

1. `[base, quote]` — fetches the reference rate; on change resets `refRate`,
   `offsetPct`, and `giveInputValue` and calls `onRateResolved(null)`.

2. `[refRate, offsetPct, unavailable]` — computes `resolvedRate = refRate *
   (1 + offsetPct/100)`, calls `onRateResolved(resolvedRate)`. If
   `editingGive.current === false`, also recomputes `giveInputValue` as
   `wantAmountRef.current * resolvedRate`. This is the "want anchors" path.

3. `[wantAmount]` — when `wantAmount` prop changes and `editingGive.current
   === false`, recomputes `giveInputValue` from the current resolved rate.
   This keeps give in sync when the parent updates the want amount.

**Give-field onChange** (line 683-689): if the user types a finite positive
number into the give field while it has focus, calls `onWantAmountChange(give /
resolvedRate)`. Division-by-zero is guarded by `resolvedRate > 0`.

**Give-field onBlur** (line 694-700): resets `editingGive.current = false`; if
`giveInputValue` is empty and `wantAmount` is a finite positive number,
auto-fills give from `wantAmount × resolvedRate`.

### api.ts dependency

`RateSlider` calls `api.get<{ rate: number }>('/rates/reference?...')` (the
`api` object is imported from `web/src/api.ts`). That module uses
`window.Telegram.WebApp.initData` (via `web/src/tg.ts`) and `localStorage`.
Neither is available in jsdom without explicit setup, so both must be mocked
in tests.

`scrollFieldIntoView` from `web/src/tg.ts` is called on `onFocus` of the want
input; it uses `window.visualViewport` and `setTimeout`, neither of which need
real behaviour in unit tests. It should be mocked to a no-op.

### vite.config.ts

`web/vite.config.ts` uses `base: '/app/'` and a build `outDir: '../public/app'`.
These are build-only settings and should not pollute the test environment.
Vitest can be configured independently via `web/vitest.config.ts`.

---

## Proposed solution

### 1. New devDependencies in web/package.json

Add the following to `devDependencies`:

| Package | Purpose |
|---|---|
| `vitest` | Test runner; shares Vite plugin graph |
| `jsdom` | DOM environment for React rendering in Node |
| `@testing-library/react` | `render`, `screen`, `waitFor`, `fireEvent` |
| `@testing-library/user-event` | High-level user interaction (typing, focus) |
| `@testing-library/jest-dom` | Custom matchers (`toBeInTheDocument`, etc.) |

Add two scripts:

```json
"test":       "vitest run",
"test:watch": "vitest"
```

`vitest run` exits after one pass (CI-safe). `vitest` without arguments is
watch mode for local development.

### 2. New web/vitest.config.ts

A standalone Vitest configuration file, separate from `vite.config.ts`, so
build-specific settings (`base`, `outDir`) do not leak into the test
environment.

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

The `@vitejs/plugin-react` plugin is already a devDependency; reusing it means
JSX transform is available with no extra configuration.

### 3. New web/src/test-setup.ts

```ts
import '@testing-library/jest-dom';
```

This registers the extended matchers (`toBeInTheDocument`, `toHaveValue`, etc.)
globally for every test file. It is referenced by `setupFiles` in
`vitest.config.ts`.

### 4. New web/src/RateSlider.test.tsx

The sole test file for this issue. It mocks two modules at the module boundary:

```ts
vi.mock('./api.js', () => ({
  api: { get: vi.fn() },
}));

vi.mock('./tg.js', () => ({
  scrollFieldIntoView: vi.fn(),
  initData: vi.fn(() => ''),
}));
```

Mocking `api.js` avoids any real HTTP calls and lets each test control the
returned `{ rate }`. Mocking `tg.js` suppresses the `visualViewport` /
`setTimeout` scroll logic and prevents `window.Telegram` access.

The `RateSlider` prop signature (from `web/src/components.tsx` lines 564-570):

```ts
interface RateSliderProps {
  base: Asset;
  quote: Asset;
  wantAmount: string;
  onWantAmountChange: (v: string) => void;
  onRateResolved: (rate: string | null) => void;
}
```

All five test scenarios from the issue will be covered (see Tasks section for
full list). Each test renders `<RateSlider>` with spy functions for the two
callbacks, awaits the async rate fetch via `waitFor`, then asserts on DOM
state and callback invocations.

**Slider interaction**: jsdom does not implement the range input's native slider
UX. Tests will use `fireEvent.change(sliderEl, { target: { value: newRate } })`
to simulate slider movement, which exercises the `onChange` handler directly
(line 712-717 in `components.tsx`).

**Give input interaction**: `userEvent.type` and `userEvent.click` from
`@testing-library/user-event` provide focus/blur events naturally, which is
required to correctly exercise the `editingGive` ref transitions.

### 5. .github/workflows/ci.yml — web job

Add `npm test` after the existing `npm run type-check` step:

```yaml
- run: npm run type-check
- run: npm test
- run: npm run build
```

Order: type-check → test → build. This catches type errors cheaply first,
then runs tests, then verifies the build still compiles. All three must pass.

### TypeScript scope for test files

`web/tsconfig.json` `include` currently lists `["src", "vite.config.ts"]`.
`web/src/RateSlider.test.tsx` and `web/src/test-setup.ts` fall under `src` and
are therefore already included. No tsconfig change is required.

The `noUnusedLocals` and `noUnusedParameters` strict flags are already active;
test files must comply. Vitest types (`vi`, `describe`, `it`, `expect`) should
be imported explicitly from `vitest` rather than relying on globals to avoid
breaking `noUnusedLocals` and to stay consistent with the codebase's explicit
import style.

---

## Alternatives

### A. Jest + babel-jest instead of Vitest

Jest is the de-facto standard but requires a Babel transform to handle the
project's ESM (`"type": "module"`) and JSX. Configuring `babel-jest` with the
project's TypeScript and ESM setup adds significant boilerplate (`babel.config`,
`jest.config`, transform exclusions). Vitest is ESM-native and reuses the
existing Vite plugin graph, keeping the configuration surface minimal. The
project already depends on `vite` and `@vitejs/plugin-react`, so Vitest is a
natural fit. The issue also explicitly names Vitest.

### B. Embed test config inside vite.config.ts

Vitest supports a `test` key directly in `vite.config.ts`. This avoids an extra
file, but the existing `vite.config.ts` carries build-only settings (`base:
'/app/'`, `outDir: '../public/app'`, the `server.proxy` block) that have no
meaning at test time. A separate `vitest.config.ts` keeps concerns separated
and makes it obvious what is production configuration versus test configuration.
The extra file cost is one small file.

### C. Playwright component tests instead of Vitest + jsdom

Playwright's component testing feature runs components in a real browser, which
would make slider interactions more faithful. However, Playwright CT is
experimental, adds a large binary dependency, and makes CI significantly slower.
The anchoring logic under test is pure React state and refs; jsdom is sufficient
to exercise it. Playwright would be the right tool for visual regression or
end-to-end flows.

---

## Platform impact

- **Migrations**: none. No database or schema changes.
- **Bundle**: `devDependencies` only; no production bundle change.
- **Backward compatibility**: the `RateSlider` component and its props are
  unchanged. The test file is read-only from the component's perspective.
- **CI timing**: vitest run on a single test file is fast (< 10 s expected).
  The `web` CI job currently takes most of its time on `npm ci` + Vite build;
  the test step adds minimal overhead.
- **Risks**: The `tg.ts` module executes side effects at import time (`const wa
  = window.Telegram?.WebApp` at line 47). Because `tg.js` is mocked entirely
  via `vi.mock`, this line is never reached in tests. If a future refactor
  removes the mock boundary, that side-effect could throw in jsdom. Mitigation:
  keep the `vi.mock('./tg.js')` call at the top of the test file.
- **Rollback**: removing the test infrastructure requires reverting changes to
  `web/package.json`, deleting `web/vitest.config.ts`, `web/src/test-setup.ts`,
  and `web/src/RateSlider.test.tsx`, and removing the `npm test` step from
  `ci.yml`. No runtime code is touched.
