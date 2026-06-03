# Design: issue-22-feat-web-create-order-step-1-currency-pa

## Current state

### CreateOrder.tsx — step 1 (lines 132–167)
Step 1 holds a single `AssetSelect` component bound to `wantAsset` (currently
defaulting to `'EUR'`), followed by an amount input and a city field. When the
user changes `wantAsset` it cycles the first give option's asset in `opts[]` so
no two options share the same asset. There is no "give asset" concept in step 1
at all.

```tsx
// web/src/screens/CreateOrder.tsx  lines 17–21
const [wantAsset, setWantAsset] = useState<Asset>('EUR');
const [opts, setOpts] = useState<OptDraft[]>(() => [
  { id: 0, asset: 'RUB', max_rate: '', payment_methods: [] },
]);
```

### CreateOrder.tsx — step 2 (lines 169–234)
Step 2 iterates `opts` and renders for each option: a segmented control for the
give asset (`pd-segmini` + `availFor(i)` helper), a rate input, a `RatePreview`
component, payment-method chips, a Remove button (when `opts.length > 1`), and an
"Add alternative" button when all three assets are not yet used.

### AssetSelect (components.tsx lines 462–487)
Renders a horizontal row of pill buttons for each asset in `ASSETS`. An `exclude`
prop disables specific buttons. Reused on the order-book filter bar.

### PD_ICON (components.tsx line 21)
`arrowSwap: 'M7 7h11l-3-3M17 17H6l3 3'` — the swap arrow icon already exists; it
is used nowhere in the current UI but is defined.

### rates.ts (src/services/rates.ts)
`getReferenceRate(base, quote)` derives any EUR/RUB/USDT directed rate from the
CBR feed via a RUB cross. Returns `null` only for `base === quote`. All six
directed pairs are supported today.

### POST /orders contract (src/services/orders.ts lines 74–80)
Accepts `give_options[]` with 1 to N elements; each element needs `asset` ≠
`want_asset`. Sending exactly one element is already valid — no backend change is
required.

---

## Proposed solution

### 1. New `CurrencyPairPicker` component (`web/src/components.tsx`)

Add a self-contained component at the bottom of `components.tsx` (after `AssetSelect`).
It renders:

```
┌────────────────────────────────┐
│  I have                        │
│  [€ EUR]  [₽ RUB]  [₮ USDT]   │  ← AssetSelect with exclude=[wantAsset]
├────────────────────────────────┤
│          [↕ swap]              │  ← round button, arrowSwap icon
├────────────────────────────────┤
│  I want to get                 │
│  [€ EUR]  [₽ RUB]  [₮ USDT]   │  ← AssetSelect with exclude=[giveAsset]
└────────────────────────────────┘
```

Props:
```ts
interface CurrencyPairPickerProps {
  giveAsset: Asset;
  wantAsset: Asset;
  onGiveChange: (a: Asset) => void;
  onWantChange: (a: Asset) => void;
  onSwap: () => void;
}
```

The component is purely presentational; all state lives in `CreateOrder`. It reuses
the existing `AssetSelect` component (the horizontal pill row), passing the opposite
side's current asset as the `exclude` prop so that button is visually disabled and
non-interactive. With three assets and one excluded, each side always shows exactly
two enabled pills and one disabled pill.

New CSS classes (added to `web/src/styles.css`):

```css
/* Currency-pair picker */
.pd-pair-picker {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-bottom: 4px;
}
.pd-pair-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  background: var(--pd-surface);
  border-radius: var(--pd-radius-sm);
}
.pd-pair-row-label {
  font-size: var(--pd-fs-meta);
  font-weight: 600;
  color: var(--pd-hint);
  text-transform: uppercase;
  letter-spacing: .06em;
}
.pd-pair-swap-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: -1px 0;
  position: relative;
  z-index: 1;
}
.pd-swap-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1.5px solid var(--pd-border);
  background: var(--pd-card-bg);
  color: var(--pd-hint);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background .12s, color .12s, transform .15s;
}
.pd-swap-btn:active {
  transform: rotate(180deg);
  color: var(--pd-accent-eff);
}
```

The two `pd-pair-row` blocks have no visible gap between them to appear as a single
grouped surface; the swap button overlays the seam.

### 2. State changes in `CreateOrder` (`web/src/screens/CreateOrder.tsx`)

Add `giveAsset` as a first-class piece of step 1 state:

```tsx
const [giveAsset, setGiveAsset] = useState<Asset>('RUB');
```

Default pair: give=RUB, want=EUR (existing defaults, now both explicit).

Swap handler:
```tsx
function handleSwap() {
  hapticSelection();
  setGiveAsset(wantAsset);
  setWantAsset(giveAsset);
  // opts[0].asset must track giveAsset; update in step-2 editor or derive at submit
}
```

"Next free" helper (used when a pick collision occurs):
```tsx
function nextFree(exclude1: Asset, exclude2: Asset): Asset {
  return ASSETS.find((a) => a !== exclude1 && a !== exclude2)!;
}
```

When the user picks a give asset that equals `wantAsset`, auto-bump want:
```tsx
function handleGiveChange(a: Asset) {
  hapticSelection();
  setGiveAsset(a);
  if (a === wantAsset) setWantAsset(nextFree(a, a)); // nextFree(a, a) = the remaining asset
}
```

Symmetrically for want:
```tsx
function handleWantChange(a: Asset) {
  hapticSelection();
  setWantAsset(a);
  if (a === giveAsset) setGiveAsset(nextFree(a, a));
}
```

The `opts` array is kept as `OptDraft[]` but is always a single element. Its `asset`
field is kept in sync with `giveAsset` by deriving it at submit time rather than
mirroring state, removing the synchronisation hazard:

```tsx
// At submit (replacing the existing opts.map):
give_options: [{ asset: giveAsset, max_rate: opts[0].max_rate.trim() || null,
                 payment_methods: opts[0].payment_methods }]
```

`opts[0].asset` is no longer the source of truth for which asset is given;
`giveAsset` is. The `opts` array retains only `max_rate` and `payment_methods`
(both are still edited in step 2).

### 3. Step 1 JSX changes (`CreateOrder.tsx`)

Replace the existing section body in `step === 1`:

```tsx
{step === 1 && (
  <div className="pd-form-multi">
    <div className="pd-form-section">
      <div className="pd-form-section-head">
        <span className="pd-form-n pd-num">1</span>
        <span className="pd-form-title">Currency pair</span>
      </div>
      <CurrencyPairPicker
        giveAsset={giveAsset}
        wantAsset={wantAsset}
        onGiveChange={handleGiveChange}
        onWantChange={handleWantChange}
        onSwap={handleSwap}
      />
      <span className="pd-label">Amount <span className="pd-label-opt">· {wantAsset}</span></span>
      <label className="pd-amount-field">
        <span className="pd-amount-glyph">{PD_GLYPH[wantAsset]}</span>
        <input ... />   {/* unchanged */}
        <span className="pd-amount-code">{wantAsset}</span>
      </label>
      <span className="pd-label">City <span className="pd-label-opt">· optional</span></span>
      <label className="pd-field"> ... </label>  {/* unchanged */}
    </div>
    {!hasMainButton() && <button ...>Continue</button>}
  </div>
)}
```

The section number chip and stepper remain. The section title changes from
"I want to receive" to "Currency pair".

### 4. Step 2 simplification (`CreateOrder.tsx`)

Step 2 no longer needs the give-asset segmented control or the multi-option
infrastructure. The new step 2 renders a single give-option editor with:
- A read-only asset label (Glyph + code) showing the give asset selected in step 1,
  so the maker sees what they confirmed.
- Max rate input (unchanged label: `o.asset / wantAsset`).
- `RatePreview` with `base={wantAsset}` and `quote={giveAsset}`.
- Payment methods chips (unchanged).
- No Remove button, no "Add alternative" button.
- Section title: "I will give".

The `availFor` helper, the `addOpt` function, and the `opts.length` guard are all
removed. `rateViolations` / `liveRateViolations` remain; they are keyed by `opts[0].id`
which is always `0`.

### 5. `previewOrder` in step 3

The `give_options` array in the preview is derived from `giveAsset` + `opts[0]`:

```tsx
give_options: [{
  id: 0, asset: giveAsset,
  max_rate: opts[0].max_rate || null,
  payment_methods: opts[0].payment_methods,
  reference_rate: null, reference_source: null, delta_percent: null,
}],
```

This replaces the existing `opts.map(...)` call (lines 118–123).

---

## Alternatives

### A. Keep multi-option give in step 1 but add a pair-picker header
Show the "I have / swap / I want" block as a summary at the top of step 1 and still
show the multi-option `opts` list below it. This avoids touching step 2 but forces
the "one give asset" constraint via a cap in the UI rather than simplifying the data
model. Dropped because it contradicts the explicit decision in the issue to remove the
multi-alternative UI and does not simplify the mental model.

### B. Replace AssetSelect per-row with a tappable single-cell that opens a bottom sheet
Each row shows only the selected asset (large glyph + code) and tapping it opens a
full-screen or bottom-sheet picker. Closer to the T-Bank reference design. Dropped for
this issue because: the issue does not ship a screenshot, there are only three choices,
and adding a sheet layer introduces a new UI primitive (no existing `pd-sheet` or modal
component). This remains a possible follow-up once the basic pair picker ships.

### C. Merge give-asset state directly into `opts[0].asset` (no new `giveAsset` state)
Eliminate `giveAsset` as separate state; drive everything from `opts[0].asset` as
before. The `wantAsset` change handler already bumps `opts[0].asset` (lines 142–147
today). Dropped because: it keeps the awkward indirection where a step-1 concern is
modelled as a give-option object, and the swap handler would need to push into `opts`
state which is semantically a step-2 concern. A flat `giveAsset` state variable in
step 1 makes the intent explicit.

---

## Platform impact

### Migrations
None. This is a pure front-end change.

### Backward compatibility
The `POST /orders` payload already accepts `give_options` with one element (validation
in `src/services/orders.ts` line 74 checks `length === 0` as the rejection case).
Existing orders in the database are unaffected.

### Resource impact
Negligible. `CurrencyPairPicker` is a thin wrapper around two existing `AssetSelect`
instances plus one button. No new API calls.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| `nextFree` returns `undefined` if `ASSETS` changes | The `!` non-null assertion is safe for `ASSETS = ['EUR','RUB','USDT']` (three elements, two excluded at most). If a fourth asset is ever added, a runtime check should replace the assertion. |
| `opts[0]` accessed when `opts` is empty | `opts` is always initialised with one element and never emptied by this change (the Remove button is deleted). Guard with `opts[0] ?? ...` as a belt-and-suspenders measure. |
| Swap mid-edit clears rate/methods | Swap only flips `giveAsset` / `wantAsset`; `opts[0].max_rate` and `opts[0].payment_methods` are not touched. The rate shown in step 2 will re-fetch for the new pair (existing `useEffect` in `RatePreview` depends on `base`/`quote`). |
| Type-check fails if `exclude` prop removes all asset options | `AssetSelect` with `exclude=[oneAsset]` leaves two options; with three assets there is always at least one selectable. |
