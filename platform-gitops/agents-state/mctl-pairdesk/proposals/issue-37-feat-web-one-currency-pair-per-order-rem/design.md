# Design: issue-37-feat-web-one-currency-pair-per-order-rem

## Current state

All relevant code lives in `web/src/screens/CreateOrder.tsx` and
`web/src/styles.css`.

### State (`CreateOrder.tsx` lines 22-23)

```ts
const [opts, setOpts] = useState<OptDraft[]>(() => [{ id: 0, asset: 'RUB', max_rate: '', payment_methods: [] }]);
const [nextOptId, setNextOptId] = useState(1);
```

`opts` is an array of `OptDraft` (`{ id, asset, max_rate, payment_methods }`).
`nextOptId` is a monotone counter used exclusively by `addAlternative` to stamp
stable `key` props on newly added editors.

### Sync effect (lines 57-85)

A `useEffect([giveAsset, wantAsset])` contains three branches:

1. Promote-to-primary: if `giveAsset` matches an existing alternative's asset,
   swap that alternative into slot 0 so its rate/methods are preserved.
2. Retarget: if no alternative matches, overwrite `opts[0].asset` and reset
   its rate/methods.
3. Dedup: filter out any option whose asset equals `wantAsset` or duplicates an
   earlier entry.

This complexity exists solely to manage the multi-option case. With a single
option the only needed behaviour is branch 2: keep `opts[0].asset === giveAsset`
and reset rate/methods when the asset changes.

### CRUD helpers (lines 89-116)

- `updateOpt(i, patch)` — used for RateSlider callbacks; needed for single opt.
- `toggleMethod(i, m)` — used for payment-method chips; needed for single opt.
- `removeOpt(i)` — guards `i === 0` and otherwise splices; not needed.
- `addAlternative()` — appends a new `OptDraft`; not needed.

### `canAddAlternative` (line 121)

```ts
const canAddAlternative = opts.length < ASSETS.length - 1;
```

Gates the "+ Add alternative" button. Not needed.

### Step-2 render (lines 231-281)

- `opts.map((o, i) => <div key={o.id} className="pd-give-editor"> ... </div>)`
  iterates over all options and renders an editor for each.
- Inside each editor, `i > 0` conditionally renders a remove button
  (lines 239-249).
- After the map, `canAddAlternative &&` renders the "+ Add alternative" button
  (lines 271-281).

### Preview / submit payload (lines 184-194 and 129-133)

Both map `opts` with `.map(o => ({ asset, max_rate, payment_methods }))`.
With a one-element array these mappings are unchanged and already correct.

### CSS (`web/src/styles.css` lines 1027-1052)

- `.pd-give-editor` (1028-1033): card container for a give-option editor.
  Still needed — the single editor sits inside it.
- `.pd-give-editor-head` (1034): header row (asset label + optional remove
  button). Still referenced; can be kept or removed depending on whether the
  implementer chooses to show the asset name in the header. See options below.
- `.pd-give-editors` (1035): column flex wrapper; still needed.
- `.pd-add-alt` (1036-1052): the dashed "Add alternative" button style. Not
  referenced after the button is removed; should be deleted.

---

## Proposed solution

### Strategy: minimal surgical removal

Retain `opts: OptDraft[]` as a one-element array. This keeps the submit mapping
(`opts.map(...)`) and the `previewOrder.give_options` mapping identical to
today — zero risk of a payload regression. Remove only the multi-option
machinery.

### Changes to `web/src/screens/CreateOrder.tsx`

1. **Remove `nextOptId` state** (line 23). It is used only in `addAlternative`.

2. **Simplify the giveAsset/wantAsset sync `useEffect`** (lines 57-85).
   Replace the three-branch promote/dedup logic with a single guard:

   ```ts
   useEffect(() => {
     setOpts((prev) => {
       if (prev[0].asset === giveAsset) return prev;
       return [{ ...prev[0], asset: giveAsset, max_rate: '', payment_methods: [] }];
     });
   }, [giveAsset]);
   ```

   The `wantAsset` dependency is dropped: deduplication against `wantAsset` was
   only needed to prevent alternatives from colliding with the want side.  With
   one option the step-1 `handleGiveChange` / `handleWantChange` collision
   guards already ensure `giveAsset !== wantAsset` before state is committed,
   so the effect never sees a collision.

3. **Remove `removeOpt` function** (lines 98-105). No callers after step 2 is
   simplified.

4. **Remove `addAlternative` function** (lines 107-116).

5. **Remove `canAddAlternative` variable** (line 121).

6. **Simplify the step-2 give-editors block** (lines 231-281):
   - Replace the `opts.map(...)` wrapper with a direct render of `opts[0]`.
     Using `opts[0]` (and passing index `0` to `updateOpt` / `toggleMethod`)
     is safe because the array always has exactly one element.
   - Remove the conditional remove button (`i > 0` block, lines 239-249).
   - Remove the `canAddAlternative &&` add-alternative button (lines 271-281).
   - The `.pd-give-editor-head` that previously held the asset label and remove
     button can be removed from the JSX; the asset label is already visible in
     the Step-1 pair picker and the RateSlider header.

### Changes to `web/src/styles.css`

- Delete the `.pd-add-alt` rule block (lines 1036-1052). It becomes dead code
  once the button is gone.
- `.pd-give-editor`, `.pd-give-editor-head`, and `.pd-give-editors` can all be
  retained; they still apply to the single remaining editor.

### No changes needed

- `web/src/types.ts` — `GiveOption` and `Order.give_options: GiveOption[]` stay
  as-is; the API expects an array.
- `web/src/api.ts` — no change.
- All server-side files under `src/` — no change.
- `web/src/components.tsx` — `RateSlider`, `CurrencyPairPicker`, etc. unchanged.

---

## Alternatives

### A. Flatten `opts` to scalar state (`giveRate`, `giveMethods`)

Replace `opts: OptDraft[]` with two flat state variables
(`const [giveRate, setGiveRate] = useState('')` and
`const [giveMethods, setGiveMethods] = useState<string[]>([])`).
Inline `updateOpt` / `toggleMethod` calls into callbacks.

**Why dropped**: larger diff, touches the submit mapping and the
`previewOrder` shape, higher risk of a subtle regression. The `OptDraft[]`
one-element form already works correctly; removing the scaffolding without
breaking the payload is the safer path for a focused removal PR.

### B. Keep `opts.map()` in the render but just stop adding elements

Do not touch the map loop; rely on the invariant that `opts` always has one
element. Only remove the "Add alternative" button and `removeOpt`.

**Why dropped**: the multi-option map loop, the `i > 0` remove-button branch,
`removeOpt`, `addAlternative`, `canAddAlternative`, and `nextOptId` would all
remain as dead or misleading code. The proposal should leave the file clean.

### C. Introduce a separate single-option component

Extract a `GiveOptionEditor` component with scalar props (asset, rate,
methods), replacing the `opts`-based pattern entirely.

**Why dropped**: over-engineering for a removal task. There is no other place
in the app that currently renders such a component, so the extraction buys
nothing immediately and increases the PR surface.

---

## Platform impact

- **Migrations**: none.
- **API backward compatibility**: the `POST /orders` payload continues to send
  `give_options` as an array (length 1). The server already handles length-1
  payloads; no server change is required.
- **Bundle size**: minor reduction (a handful of deleted functions and JSX).
- **Risk**: low. Changes are confined to one file (`CreateOrder.tsx`) and one
  CSS block. The submission path (`opts.map(...)`) is untouched in structure.
- **Mitigation**: the `previewOrder` on Step 3 renders an `OrderCard` using
  the same `opts` array, providing an in-app preview that confirms the payload
  shape before publish. Manual testing on Step 3 preview is sufficient to
  verify correctness before merging.
