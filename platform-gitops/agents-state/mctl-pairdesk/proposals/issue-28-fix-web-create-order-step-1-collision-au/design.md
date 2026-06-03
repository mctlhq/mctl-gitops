# Design: issue-28-fix-web-create-order-step-1-collision-au

## Current state

### Asset constants

`web/src/types.ts` defines:

```ts
export type Asset = 'EUR' | 'RUB' | 'USDT';
export const ASSETS: Asset[] = ['EUR', 'RUB', 'USDT'];
```

The array has exactly three elements. Because give and want must always be distinct, at
any given moment one of the three assets is "uninvolved" (it appears on neither side).

### CreateOrder component — step 1

`web/src/screens/CreateOrder.tsx` holds two controlled state variables:

```ts
const [giveAsset, setGiveAsset] = useState<Asset>('RUB');
const [wantAsset, setWantAsset] = useState<Asset>('EUR');
```

The `nextFree` helper is designed to return the one asset that is neither of its two
arguments:

```ts
function nextFree(exclude1: Asset, exclude2: Asset): Asset {
  return ASSETS.find((a) => a !== exclude1 && a !== exclude2)!;
}
```

When called with two *distinct* assets this correctly returns the third. When called with
the same asset twice, `ASSETS.find` only tests `a !== exclude1` (since both arguments are
identical), so it returns the *first* element of `ASSETS` that differs from that asset —
which may be one of the two originally in use, not the uninvolved third.

### Collision handlers (buggy)

```ts
function handleGiveChange(a: Asset) {
  hapticSelection();
  setGiveAsset(a);
  if (a === wantAsset) setWantAsset(nextFree(a, a));   // BUG: excludes only `a`
}
function handleWantChange(a: Asset) {
  hapticSelection();
  setWantAsset(a);
  if (a === giveAsset) setGiveAsset(nextFree(a, a));   // BUG: excludes only `a`
}
```

**Trace of T3** — initial state: give=RUB, want=EUR; user picks give=EUR:
- `a = EUR`, `wantAsset = EUR` → collision branch taken
- `nextFree(EUR, EUR)` → first of `['EUR','RUB','USDT']` not equal to EUR → `RUB`
- Result: want → RUB. Expected: USDT.

**Trace of T4** — initial state: give=RUB, want=EUR; user picks want=RUB:
- `a = RUB`, `giveAsset = RUB` → collision branch taken
- `nextFree(RUB, RUB)` → first of `['EUR','RUB','USDT']` not equal to RUB → `EUR`
- Result: give → EUR. Expected: USDT.

### Dead-state observation

`opts` is initialized with `{ id: 0, asset: 'RUB', ... }` (line 22). The `asset` field is
never read by `submit()` (line 78 uses `giveAsset` directly), `previewOrder` (line 134),
or the step-2 give-editor header (lines 196-198, which also read `giveAsset`). It is
purely dead state but causes no functional harm.

### Build / type-check commands (from `web/package.json`)

- `npm run type-check` — `tsc --noEmit`
- `npm run build` — `vite build`

## Proposed solution

In each collision handler, pass the new asset value AND the old value of the *same* field
as the two exclusion arguments to `nextFree`. React state updates are asynchronous, so
`giveAsset` and `wantAsset` inside the handler closure still hold their pre-update values
at the time the handler executes.

```ts
function handleGiveChange(a: Asset) {
  hapticSelection();
  setGiveAsset(a);
  if (a === wantAsset) setWantAsset(nextFree(a, giveAsset));  // exclude new give + old give
}
function handleWantChange(a: Asset) {
  hapticSelection();
  setWantAsset(a);
  if (a === giveAsset) setGiveAsset(nextFree(a, wantAsset));  // exclude new want + old want
}
```

**Why this always yields the uninvolved third asset:**

In `handleGiveChange`, the pre-change state was (give=`giveAsset`, want=`wantAsset`). The
user picked `a` as the new give, and `a === wantAsset` (collision). The third, uninvolved
asset is the one that was on neither side before the change — i.e., not `giveAsset` and
not `wantAsset` (= `a`). `nextFree(a, giveAsset)` excludes exactly those two, returning
the third.

Symmetrically for `handleWantChange`: the uninvolved asset is not `wantAsset` (= `a`) and
not `giveAsset`. `nextFree(a, wantAsset)` returns it.

**Trace of T3 with fix** — give=RUB, want=EUR; user picks give=EUR:
- `a = EUR`, `wantAsset = EUR`, `giveAsset = RUB`
- `nextFree(EUR, RUB)` → first of `['EUR','RUB','USDT']` not EUR and not RUB → `USDT` ✓

**Trace of T4 with fix** — give=RUB, want=EUR; user picks want=RUB:
- `a = RUB`, `giveAsset = RUB`, `wantAsset = EUR`
- `nextFree(RUB, EUR)` → first of `['EUR','RUB','USDT']` not RUB and not EUR → `USDT` ✓

No type signature changes. `nextFree` already accepts two `Asset` parameters; passing two
distinct `Asset` values (guaranteed since the collision guard `a === wantAsset` / `a ===
giveAsset` ensures the new and old values are the same, meaning `a !== giveAsset` when
entering `handleGiveChange`'s collision branch only when `giveAsset !== wantAsset`, which
is always true for a valid pre-change state) satisfies the function's contract.

The scope of the change is exactly two lines in `web/src/screens/CreateOrder.tsx`.

## Alternatives

### Alternative 1 — swap instead of bump

When give=EUR and want=EUR, set want to the old give (RUB), effectively swapping. This
makes T3 pass (want → RUB → no wait, give becomes EUR, so we'd need want ≠ EUR, RUB gets
freed). Actually for T3 this would yield want=RUB, which is wrong per spec. The issue
explicitly requires the uninvolved third asset, so swapping is incorrect.

### Alternative 2 — rewrite nextFree to infer the second exclusion from component state

Make `nextFree` a closure over `giveAsset` and `wantAsset` rather than accepting two
arguments, removing explicit parameters. This would hide the bug site rather than fix it
cleanly, make the function less testable (it becomes stateful), and change the function
signature unnecessarily. The two-argument signature is already correct for its stated
purpose; the bug is purely in the call site.

### Alternative 3 — remove nextFree and inline the exclusion

Replace the helper with an explicit lookup table or a chain of conditionals. Inline logic
is harder to read and gains nothing: `nextFree` is already a one-liner, correctly named,
and trivially verified. Inlining would increase noise without fixing the root cause.

## Platform impact

- **Migrations**: none. No schema, API, or data changes.
- **Backward compatibility**: fully compatible. The fix only changes which asset is
  auto-selected on collision, producing a different (correct) asset in two edge-case
  scenarios. The resulting pair remains distinct and valid for submission.
- **Resource impact**: none. The fix does not add renders, network calls, or state fields.
- **Risks**: extremely low. The change is two character-level argument substitutions in a
  single file, with no shared utilities modified. TypeScript guarantees both arguments
  remain `Asset`. The pre-existing `nextFree` helper is unchanged.
- **Mitigation**: the acceptance tests T3 and T4 can be verified manually in the dev
  environment before merging (see `CLAUDE.md` local-dev instructions).
