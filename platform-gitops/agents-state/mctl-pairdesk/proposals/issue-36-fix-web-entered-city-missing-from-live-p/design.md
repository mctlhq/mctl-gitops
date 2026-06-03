# Design: issue-36-fix-web-entered-city-missing-from-live-p

## Current state

### Maker component — web/src/components.tsx:155-173

```tsx
export function Maker({ maker, sub }: { maker: MakerData | null; sub?: React.ReactNode }) {
  if (!maker) return null;          // <-- sub is silently discarded
  ...
  <span className="pd-maker-sub">
    ...deals
    {sub ? <><span className="pd-dot-sep">·</span>{sub}</> : null}
  </span>
```

When `maker` is `null` the entire component — including the `sub` slot — is
unmounted. There is no fallback render for orphaned `sub` content.

### outcome variant footer — web/src/components.tsx:312-323

```tsx
<div className="pd-row pd-card-foot">
  <Maker
    maker={order.maker}
    sub={order.location_city ? (
      <><Icon name="pin" size={12} cls="pd-mut-ic" />{order.location_city}</>
    ) : undefined}
  />
  <span className="pd-spacer" />
  <span className="pd-when pd-num">{fmtRelTime(order.created_at)}</span>
</div>
```

City is only reachable through the `sub` prop of `Maker`, so it is
unconditionally hidden whenever `maker` is `null`.

### rate variant footer — web/src/components.tsx:400-411

Identical pattern: city passed as `Maker sub`, same suppression risk.

### previewOrder — web/src/screens/CreateOrder.tsx:184-196

```tsx
const previewOrder: Order = {
  id: 0, want_asset: wantAsset, want_amount: wantAmount || '0', status: 'active',
  location_city: city || null,   // value is correct here
  ...
  maker: null,                   // always null — user has not yet submitted
};
```

`location_city` is populated correctly from the `city` state variable. The
defect is entirely in how `OrderCard` (outcome variant) renders that field.

### Variants without the defect

- `standard` variant (`components.tsx:435-438`): renders city as a `pd-loc`
  span inside `pd-card-line`, independent of `Maker`.
- `compact` variant (`components.tsx:336-338`): renders city inline inside
  `pd-cc-sub`, independent of `Maker`.

## Proposed solution

Decouple city rendering from the `Maker` component in the two affected card
variants. City becomes a sibling element in the card footer row, using the
`pd-loc` CSS class already established in the `standard` variant.

### Change 1 — outcome variant footer (components.tsx ~line 312)

Replace:
```tsx
<div className="pd-row pd-card-foot">
  <Maker
    maker={order.maker}
    sub={order.location_city ? (
      <><Icon name="pin" size={12} cls="pd-mut-ic" />{order.location_city}</>
    ) : undefined}
  />
  <span className="pd-spacer" />
  <span className="pd-when pd-num">{fmtRelTime(order.created_at)}</span>
</div>
```

With:
```tsx
<div className="pd-row pd-card-foot">
  <Maker maker={order.maker} />
  {order.location_city && (
    <span className="pd-loc">
      <Icon name="pin" size={12} cls="pd-mut-ic" />{order.location_city}
    </span>
  )}
  <span className="pd-spacer" />
  <span className="pd-when pd-num">{fmtRelTime(order.created_at)}</span>
</div>
```

### Change 2 — rate variant footer (components.tsx ~line 400)

Same structural change: remove the city `sub` from `Maker`, add an explicit
`pd-loc` span conditional on `order.location_city`.

Replace:
```tsx
<Maker
  maker={order.maker}
  sub={
    order.location_city ? (
      <><Icon name="pin" size={12} cls="pd-mut-ic" />{order.location_city}</>
    ) : undefined
  }
/>
```

With:
```tsx
<Maker maker={order.maker} />
{order.location_city && (
  <span className="pd-loc">
    <Icon name="pin" size={12} cls="pd-mut-ic" />{order.location_city}
  </span>
)}
```

### No change required in CreateOrder.tsx

`previewOrder.location_city` is already wired correctly (`city || null` at
line 186). The fix is entirely in rendering.

### No change required in the Maker component

`Maker` keeps its current semantics (returns `null` when no maker). Removing
the `sub` prop from both call sites eliminates the dead-code path for this
feature without altering a shared primitive.

### Visual consequence for real orders

For orders in the `outcome` or `rate` variant that have both a maker and a
city, the city pin shifts from appearing as trailing content in the maker's
sub-line to being a standalone `pd-loc` element in the footer row. This aligns
with the rendering pattern used by the `standard` variant. The change is
cosmetically minor and no CSS update is needed because `pd-loc` is already
defined.

## Alternatives

### Option A — Placeholder maker in previewOrder (CreateOrder.tsx only)

Supply `maker: { display_name: 'You', username: null, rating_score: null, completed_deals_count: null }` in `previewOrder` so `Maker` does not return `null` and the `sub` prop reaches the DOM.

Rejected: the preview card would then show a fake avatar with "You", a dash
rating, and "0 deals" — misleading the user about their public profile. The
city rendering issue in the `rate` variant (real orders) would also remain
unaddressed. The fix is narrowly scoped to `CreateOrder.tsx` while the actual
defect is in `components.tsx`.

### Option B — Make Maker render sub when maker is null

Add a fallback branch to `Maker`:
```tsx
if (!maker) return sub ? <div className="pd-maker">{sub}</div> : null;
```

Rejected: changes a generic layout primitive to know about domain fallback
behavior; any future call site passing a `sub` with a null maker would silently
render that content, possibly unintentionally. The `Maker` component's contract
— "nothing visible when there is no maker" — is clean and should stay that way.

### Option C — Inline the preview markup in CreateOrder.tsx

Skip `OrderCard` for the preview and write bespoke JSX that always renders the
city. Rejected: duplicates all of `OrderCard`'s outcome logic; divergence
between the preview and the live card would be impossible to detect at a glance
and likely to recur with future feature additions.

## Platform impact

- No database migrations.
- No API changes or backward-compatibility concerns.
- No new dependencies.
- Affected file: `web/src/components.tsx` only (two ~10-line JSX blocks).
- Risk: low. The change is additive for the preview case (city now renders
  where it was invisible) and visually minimal for real orders (city pin moves
  from Maker sub-line to footer row peer, same content, same icon, same class).
- Rollback: revert the two JSX blocks; no state or data is affected.
