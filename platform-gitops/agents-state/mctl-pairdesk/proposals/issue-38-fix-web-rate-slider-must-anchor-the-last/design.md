# Design: issue-38-fix-web-rate-slider-must-anchor-the-last

## Current state

### Component: `RateSlider` (`web/src/components.tsx:572-731`)

`RateSlider` owns all amount/rate coupling for one give option in Create-Order step 2.
Its props and key internal state:

```
props:
  base          Asset          -- the want asset (e.g. EUR); rendered in the left input
  quote         Asset          -- the give asset (e.g. RUB); rendered in the right input
  wantAmount    string         -- controlled by parent (CreateOrder.wantAmount)
  onWantAmountChange (v)       -- lift want amount to parent
  onRateResolved (rate|null)   -- lift resolved rate to parent (stored in opt.max_rate)

internal state / refs:
  refRate       number|null    -- market reference rate from /rates/reference
  unavailable   boolean        -- true when reference rate fetch fails
  offsetPct     number         -- slider position as % deviation from refRate
  giveInputValue string        -- current text in the give (right) input
  editingGive   Ref<boolean>   -- true only while give input has focus
  wantAmountRef Ref<string>    -- always-current mirror of wantAmount prop
```

**The two recompute effects:**

1. `useEffect([refRate, offsetPct, unavailable])` (`:598-606`): fires on slider drag
   and on initial rate fetch. Calls `onRateResolved` with the new resolved rate. Then,
   if `!editingGive.current`, recomputes give as `want * resolvedRate`.

2. `useEffect([wantAmount])` (`:609-614`): fires when the parent updates `wantAmount`
   (i.e., the user typed in the want field). If `!editingGive.current`, recomputes give.

**The problem:**

`editingGive.current` is `true` only while the give input is focused. After the user
types a give amount and tabs/taps away, `onBlur` sets it back to `false` (`:692-700`).
From that point on, every slider drag falls into the `!editingGive.current` branch and
recomputes give — overwriting what the user entered. The anchor is lost on blur.

**Give-typed path** (`:683-689`): when the user types in give, the component derives
want via `give / resolvedRate` and calls `onWantAmountChange`. The parent sets
`wantAmount`, which triggers `useEffect([wantAmount])`. That effect is guarded by
`editingGive.current` (true while focused), so it does not overwrite give — but only
*while the give field is focused*.

### Parent: `CreateOrder` (`web/src/screens/CreateOrder.tsx:251-257`)

Renders one `RateSlider` per give option with:
- `base={wantAsset}`, `quote={o.asset}`
- `wantAmount={wantAmount}` (shared across all options)
- `onWantAmountChange={setWantAmount}` (shared state setter)

No anchor logic is present in the parent; this is entirely a `RateSlider` concern.

---

## Proposed solution

Replace the transient `editingGive: Ref<boolean>` with a persistent
`lastEditedField: Ref<'want' | 'give'>`. Add a parallel `giveInputValueRef` so
the slider effect can read the current give amount without adding `giveInputValue`
to its dependency array (mirroring the existing `wantAmountRef` pattern).

### Changes to `web/src/components.tsx` — `RateSlider` only

**1. Replace the editingGive ref with lastEditedField**

```tsx
// remove:
const editingGive = useRef(false);

// add:
const lastEditedField = useRef<'want' | 'give'>('want');
```

Default is `'want'` — consistent with the form opening with the want field as the
natural starting point.

**2. Add giveInputValueRef**

```tsx
const giveInputValueRef = useRef(giveInputValue);
useEffect(() => { giveInputValueRef.current = giveInputValue; });
```

Same pattern as the existing `wantAmountRef` (`:581-582`).

**3. Reset anchor on pair change**

In the `useEffect([base, quote])` that resets the component (`:585-595`), add:

```tsx
lastEditedField.current = 'want';
setGiveInputValue('');
```

This ensures that switching the currency pair starts fresh with the want-anchored
behaviour.

**4. Update the slider/rate-change effect (`:598-606`)**

```tsx
useEffect(() => {
  if (refRate == null || unavailable) return;
  const resolvedRate = refRate * (1 + offsetPct / 100);
  onRateResolved(resolvedRate.toFixed(8));
  if (lastEditedField.current === 'want') {
    const want = Number.parseFloat(wantAmountRef.current);
    setGiveInputValue(Number.isFinite(want) && want > 0 ? (want * resolvedRate).toFixed(2) : '');
  } else {
    const give = Number.parseFloat(giveInputValueRef.current);
    if (Number.isFinite(give) && give > 0 && resolvedRate > 0) {
      onWantAmountChange((give / resolvedRate).toFixed(2));
    }
  }
}, [refRate, offsetPct, unavailable]);
```

**5. Update the wantAmount-change effect (`:609-614`)**

```tsx
useEffect(() => {
  if (refRate == null || unavailable || lastEditedField.current !== 'want') return;
  const resolvedRate = refRate * (1 + offsetPct / 100);
  const want = Number.parseFloat(wantAmount);
  setGiveInputValue(Number.isFinite(want) && want > 0 ? (want * resolvedRate).toFixed(2) : '');
}, [wantAmount]);
```

The guard changes from `editingGive.current` to `lastEditedField.current !== 'want'`:
recompute give only when want is the anchor (i.e., the user is typing in the want field,
or want was the last field edited).

**6. Set the anchor on want input onChange (`:670-672`)**

```tsx
onChange={(e) => {
  lastEditedField.current = 'want';
  onWantAmountChange(e.target.value);
}}
```

**7. Set the anchor on give input onChange (`:683-689`)**

```tsx
onChange={(e) => {
  const val = e.target.value;
  lastEditedField.current = 'give';
  setGiveInputValue(val);
  const give = Number.parseFloat(val);
  if (Number.isFinite(give) && give > 0 && resolvedRate > 0) {
    onWantAmountChange((give / resolvedRate).toFixed(2));
  }
}}
```

**8. Simplify onBlur on give input (`:692-700`)**

Remove the `editingGive.current = false` line (the ref no longer exists). Keep the
empty-value restoration logic unchanged:

```tsx
onBlur={() => {
  if (giveInputValue === '') {
    const want = Number.parseFloat(wantAmount);
    if (Number.isFinite(want) && want > 0) {
      setGiveInputValue((want * resolvedRate).toFixed(2));
    }
  }
}}
```

**9. Remove the onFocus handler on give input**

The `onFocus={() => { editingGive.current = true; }}` line (`:691`) is no longer
needed — anchor is set via onChange, not focus events.

### No changes to `CreateOrder.tsx`

The parent's prop interface and state management (`wantAmount`, `setWantAmount`,
`updateOpt`) are unchanged.

---

## Alternatives

### Alternative 1: useState instead of useRef for lastEditedField

Using `const [lastEditedField, setLastEditedField] = useState<'want'|'give'>('want')`
would work but triggers an extra render on every keystroke. Since the value is only
read inside effects (never rendered), a ref avoids unnecessary re-renders. The existing
code already establishes this pattern with `editingGive` and `wantAmountRef`. Dropped.

### Alternative 2: Lift anchor state to CreateOrder

Moving `lastEditedField` into the parent (`CreateOrder`) and passing it down as a prop
would make the anchor visible to the parent. However, the parent has no use for this
information — it only needs `wantAmount` and `max_rate`. Adding a prop purely for an
internal interaction concern violates component encapsulation. Dropped.

### Alternative 3: Reset anchor to 'want' on give-field blur

On blur of the give input, set `lastEditedField.current = 'want'`. This would mean
"after the user finishes editing give and moves on, the slider reverts to computing
give." This is arguably simpler but contradicts the issue's stated requirement: "if the
user last set RUB, sliding should vary EUR." The anchor must persist past the blur
event. Dropped.

---

## Platform impact

- **No migrations**: pure frontend change.
- **No API changes**: `/rates/reference` and all order endpoints are untouched.
- **No backward compatibility concerns**: the component is internal to the Mini App;
  no external callers.
- **Risk**: low. The change is isolated to one component function in one file
  (`web/src/components.tsx`). The `unavailable` fallback path is untouched. The
  `CreateOrder` parent is untouched.
- **Mitigation**: manual test matrix below (see tasks.md) covers the four primary
  interaction sequences (want-first, give-first, alternating, pair-switch).
