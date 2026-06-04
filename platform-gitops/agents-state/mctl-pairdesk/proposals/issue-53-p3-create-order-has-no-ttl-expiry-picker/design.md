# Design: issue-53-p3-create-order-has-no-ttl-expiry-picker

## Current state

### API (no changes needed)

`src/services/orders.ts` `normalizeInput()` (lines 91-94) already handles the
client-supplied `expires_in_seconds` field on `CreateOrderInput`:

```ts
const ttl = input.expires_in_seconds ?? config.orderTtlSeconds;
if (!Number.isFinite(ttl) || ttl < 300 || ttl > 30 * 86_400) {
  throw new AppError(400, 'expires_in_seconds out of range (300s–30d)');
}
```

When the client omits the field, `config.orderTtlSeconds` (default 259,200 s = 72 h,
sourced from `ORDER_TTL_SECONDS` env var, `src/config.ts` line 54) is used. The INSERT
in `createOrder()` (line 141) writes `now() + ($8 || ' seconds')::interval` directly
into `expires_at`. The `Order` serializer already includes `expires_at` in the response.

### Web client

`web/src/screens/CreateOrder.tsx` `submit()` (lines 72-89) posts to `POST /api/orders`
with `want_asset`, `want_amount`, `location_city`, `comment`, and `give_options`. The
`expires_in_seconds` field is never included. The `previewOrder` object (line 142-154)
sets `expires_at: null`.

`web/src/types.ts` `Order` interface (line 47) already declares `expires_at: string | null`.

The Create-Order flow has three steps rendered inline:
- Step 1 — currency pair picker (`CurrencyPairPicker`).
- Step 2 — give options / rate slider (`RateSlider`).
- Step 3 — city, notes, and preview (`OrderCard` with `variant="outcome"`).

Step 3 is the correct injection point: it is the final review step before the
"Publish request" main button fires.

The `Stepper` component (`web/src/components.tsx` line 526) renders a dot-trail for
a fixed `total`; it will not need changes if the total stays at 3.

## Proposed solution

All changes are confined to `web/src/screens/CreateOrder.tsx`. No API, schema, or
serializer changes are required.

### 1. Expiry presets constant

Define a typed array of presets above the component:

```ts
const EXPIRY_PRESETS = [
  { label: '1 h',  seconds: 3_600 },
  { label: '6 h',  seconds: 21_600 },
  { label: '24 h', seconds: 86_400 },
  { label: '72 h', seconds: 259_200 },
] as const;
type ExpiryPreset = typeof EXPIRY_PRESETS[number]['seconds'];
```

### 2. State

Add one state variable to the `CreateOrder` component:

```ts
const [expiresInSeconds, setExpiresInSeconds] = useState<ExpiryPreset>(259_200);
```

The default value (259,200 s = 72 h) preserves existing behaviour for users who never
interact with the picker.

### 3. Submit

In `submit()`, include `expires_in_seconds: expiresInSeconds` in the POST body
alongside the existing fields (after `comment`). No other submit changes are required.

### 4. UI in step 3

In the step-3 JSX block, insert the picker between the Notes textarea and the
existing preview `<div className="pd-preview">`:

```tsx
<span className="pd-label">Order expires after</span>
<div className="pd-chips" role="group" aria-label="Order expiry">
  {EXPIRY_PRESETS.map((p) => (
    <button
      key={p.seconds}
      type="button"
      className={`pd-chip pd-chip-sm${expiresInSeconds === p.seconds ? ' is-on' : ''}`}
      onClick={() => { hapticSelection(); setExpiresInSeconds(p.seconds); }}
    >
      {p.label}
    </button>
  ))}
</div>
```

This reuses the existing `.pd-chip` / `.pd-chip-sm` / `.is-on` CSS classes (already
present for payment-method chips in step 2, same component file line 205-211) so no
new CSS is needed.

### 5. Preview annotation

Below the `<OrderCard order={previewOrder} variant="outcome" />` element, add a small
expiry indicator so the user sees the consequence of their selection before publishing:

```tsx
<p className="pd-form-sub" style={{ marginTop: 6, textAlign: 'right' }}>
  <Icon name="clock" size={13} cls="pd-mut-ic" />
  {' '}expires in {EXPIRY_PRESETS.find((p) => p.seconds === expiresInSeconds)?.label}
</p>
```

`pd-form-sub` is already styled as muted secondary copy (used on line 241 of
`CreateOrder.tsx`). `Icon` and the `clock` glyph are already imported and defined in
`components.tsx` (line 7, key `clock`).

### 6. previewOrder update

Update the `previewOrder` object so the `expires_at` field reflects the selected preset
(useful if `OrderCard` ever renders it):

```ts
expires_at: new Date(Date.now() + expiresInSeconds * 1000).toISOString(),
```

This is a display-only change; the server computes the authoritative value.

## Alternatives

### A. Free-text minutes/hours input

A `<input type="number">` lets users pick any TTL within the server's 300 s – 30 d
range. Dropped: the issue explicitly suggests chips; free text adds validation burden,
error states, and a worse mobile UX on Telegram's compact viewport. Presets cover the
practical use-cases for P2P bulletin-board orders.

### B. A fourth flow step ("Step 4: Expiry")

Adding a dedicated step would give the picker more breathing room. Dropped: the
`Stepper` currently renders `total={3}` and the step is hardcoded; adding a step
requires changing the step-counting logic, the back-button guard, and the stepper
label. The expiry picker is a single row of chips, not worth its own screen. Placing
it in step 3 alongside city and notes is natural ("how long should this note stay
visible?").

### C. Expiry in step 1 (pair picker)

Surfacing TTL at the very start mimics some exchange UIs. Dropped: at step 1 the user
has not yet set an amount or rates, so the context for "how urgent is this?" is
lacking. Step 3 (review) is the right confirmation moment.

## Platform impact

### Migrations
None. `expires_at` already exists in the `orders` table and the API already writes to it.

### Backward compatibility
- Any existing order created before this change retains the 72-hour default TTL. No
  data migration needed.
- The API change is additive: clients that still omit `expires_in_seconds` continue to
  receive the server default.

### Resource impact
Negligible. Four preset buttons in an existing React form step. No new API endpoints,
no new DB columns, no additional queries.

### Risks and mitigations
- **Risk**: A user might select a very short TTL (1 h) and then their order expires
  before a counterparty notices it. **Mitigation**: the 1-hour preset is the shortest
  offered; the server-side minimum of 300 s is not surfaced. The expiry preview in
  the form tells the user exactly what they are choosing.
- **Risk**: If `ORDER_TTL_SECONDS` is later changed by the operator to a value not
  in the preset list, the default preset (259,200 s) will silently diverge from the
  server default. **Mitigation**: the client-sent `expires_in_seconds` takes precedence
  over the server default when present, so the 72-hour preset in the UI is always
  honoured regardless of the operator env-var. Document this in `CLAUDE.md` or a
  comment near the constant.
