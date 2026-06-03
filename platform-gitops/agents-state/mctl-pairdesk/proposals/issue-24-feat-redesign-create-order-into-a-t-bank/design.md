# Design: issue-24-feat-redesign-create-order-into-a-t-bank

## Current state

### CreateOrder screen (`web/src/screens/CreateOrder.tsx`)

The screen is a 3-step wizard driven by `useState<number>` (`step`). The
Telegram `MainButton` is the only forward control; a `Stepper` component
(`web/src/components.tsx`, line 527) renders progress dots.

**Step 1 (lines 137-169):** Renders `CurrencyPairPicker`, a want-amount text
input, and a city text input. The pair and the amount are all on the same
screen.

**Step 2 (lines 171-216):** Renders a hard-coded block for `opts[0]` only.
The `opts` state is typed as `OptDraft[]` (line 22) with fields `{ id, asset,
max_rate, payment_methods }`, implying multi-option support was planned but not
finished. The `RateSlider` component is called with `base=wantAsset`,
`quote=giveAsset`, `wantAmount`, `onWantAmountChange`, and `onRateResolved`.
Payment-method chip buttons are rendered by the wrapping block, not by
`RateSlider` itself.

**Step 3 (lines 218-242):** Comment textarea + live `OrderCard` in the
`outcome` variant (`web/src/components.tsx`, line 262).

**Submit (`submit`, lines 62-77):** `POST /orders` with `want_asset`,
`want_amount`, `location_city`, `comment`, and a one-element `give_options`
array built from `opts[0]`. The multi-option path is wired in the state type
but never serialised.

### RateSlider component (`web/src/components.tsx`, lines 562-711)

Already implements the T-Bank core UX:

- Fetches `GET /rates/reference?base={base}&quote={quote}` on mount and when
  the pair changes.
- `offsetPct` state drives the slider; `resolvedRate = refRate * (1 +
  offsetPct / 100)`.
- Slider `min`/`max` are `refRate * (1 - MAX_DEVIATION_PCT / 100)` and
  `refRate * (1 + MAX_DEVIATION_PCT / 100)` where `MAX_DEVIATION_PCT = 10`
  (line 564), mirroring the backend constant in `src/services/orders.ts`
  line 112.
- Two coupled `<input>` fields: the want field calls `onWantAmountChange`; the
  give field back-computes `want = give / resolvedRate` via `onWantAmountChange`.
- Falls back to a free-text rate input when `GET /rates/reference` returns 503.

### CurrencyPairPicker component (`web/src/components.tsx`, lines 492-525)

Renders two `AssetSelect` rows ("I have" / "I want to get") and a swap button
(`Icon name="arrowSwap"`). Already fully functional for step 1.

### Backend (`src/services/orders.ts`, `src/routes/rates.ts`)

`POST /orders` accepts `give_options[]` with 1..N options, each with its own
`asset`, `max_rate`, and `payment_methods`. The server enforces
`MAX_RATE_DEVIATION_PCT = 10` per option and takes a reference-rate snapshot
per option after the transaction. No changes are needed.

`GET /rates/reference?base=&quote=` (line 10 `src/routes/rates.ts`) returns
`{ rate, source, timestamp, baseAsset, quoteAsset }`. Already consumed by
`RateSlider`.

## Proposed solution

### Step restructure

**Step 1 becomes pure pair picker.** Remove the amount input and city field
from step 1. Render only `CurrencyPairPicker`. The "Continue" MainButton is
unconditionally enabled once both assets are selected (they always are on
mount via the existing defaults). City moves to step 3.

**Step 2 becomes T-Bank exchange window.** This step renders one composite
block per entry in `opts[]`. Each block contains:

1. An asset label header (give asset code + glyph).
2. `RateSlider` (already handles the coupled amounts + slider + reference chip).
3. A payment-method chip row (existing `pd-chips` pattern).
4. A remove button (only visible when `opts.length > 1`).

After the last block, an "Add alternative" button adds a new `OptDraft` entry
if `opts.length < ASSETS.length - 1` (i.e. there is still a free asset). The
default asset for the new option is computed with the existing `nextFree`
helper (line 27-29 `CreateOrder.tsx`). The MainButton "Continue" is enabled
when `amountValid` — the existing `wantAmount` validation (line 60) — holds.

**Step 3 unchanged**, except the city field is added here alongside the
comment textarea (above it, with a pin icon, matching the current city field
styling from step 1).

### State changes inside `CreateOrder.tsx`

The `opts` state already carries everything needed. Two additions:

1. `nextOptId` counter (or use `Date.now()` as a stable key): needed when
   appending a new `OptDraft` to preserve React key stability.
2. The `submit` function must serialise the full `opts` array instead of
   only `opts[0]`. Change lines 65-70 to:
   ```ts
   give_options: opts.map((o) => ({
     asset: o.asset,
     max_rate: o.max_rate.trim() || null,
     payment_methods: o.payment_methods,
   })),
   ```

### `RateSlider` contract remains unchanged

`RateSlider` already accepts `base`, `quote`, `wantAmount`,
`onWantAmountChange`, and `onRateResolved`. The step-2 loop passes each opt's
asset as `quote` and the shared `wantAmount` / `setWantAmount` as before. All
options derive give-amounts from the same `wantAmount`. This matches the issue
statement "give = want × rate".

### Component-level summary of changes

| File | Change |
|---|---|
| `web/src/screens/CreateOrder.tsx` | Restructure: step 1 = pair only; step 2 = full `opts[]` loop with add/remove; step 3 = comment + city + preview; `submit` serialises all opts |
| `web/src/components.tsx` | No structural change; `RateSlider` and `CurrencyPairPicker` are already correct. A minor cosmetic tweak may be needed: `RateSlider` currently renders the want-amount field as the top input; the label above it should read "I want to get" when this field is the "want" side. |
| `web/src/types.ts` | No change |
| Backend | No change |

### Stepper dot count

The `Stepper` remains 3 dots (pair / amounts+rate / note). The total passed to
`<Stepper step={step} total={3} />` stays 3.

## Alternatives

### Alternative A: single-page (accordion) form

Collapse all three steps into one scrollable page with collapsible sections, as
suggested by the `create flow (multi/single)` Tweak in the design notes
(`web/src/PairDesk Design Notes.md`, line 72). This was explicitly deferred by
the design — the current multi-step wizard is the target. A single-page layout
is a future toggle, not this issue.

### Alternative B: extract step-2 block into its own component

Factor the per-give-option block (asset header + `RateSlider` + payment methods
+ remove button) into a new `GiveOptionEditor` component. This is cleaner for
multi-option rendering but adds a new component that lives in `components.tsx`,
increasing scope. Recommended as a follow-on refactor once the feature is
working; not required for correctness of this issue.

### Alternative C: implement Option B (single pair, drop alternatives)

The issue explicitly recommends Option A (preserve give alternatives) and flags
Option B as the simpler but less powerful choice. Adopting Option B would
require removing the `give_options[]` array from the submit payload, which
would be a breaking change for any existing orders and for the order book's
multi-option rendering in `OrderCard`. Rejected.

## Platform impact

### Migrations

None. The backend schema and API contract are unchanged. The `give_options[]`
array has always accepted multiple entries; the frontend was simply not
exercising that code path.

### Backward compatibility

- Existing orders with one give option are unaffected.
- The changed `submit` function now serialises all opts. For the common case
  where `opts` has one entry the payload is identical to today's.
- The `RateSlider` and `CurrencyPairPicker` components are not exported from a
  package; they are internal. No external consumers to break.

### Resource impact

- `GET /rates/reference` is called once per `RateSlider` mount and on pair
  change. With up to two give options per order creation (three assets minus
  the want asset), at most two concurrent reference-rate fetches occur per
  create session. The backend rate source (`CBR`) is cached for 5 minutes in
  `src/services/rates.ts` line 27; this is unchanged.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Shared `wantAmount` across multiple sliders means editing one slider's give field updates the want amount seen by all other sliders | Document this as intended behaviour (single want, multiple give equivalents); add a clear label "Amount you want to receive" above the first amount field |
| Three-asset ASSETS list means at most two give options; if ASSETS expands in future the "Add alternative" logic using `nextFree` (returns exactly one free asset) would need updating | Leave a `// TODO: extend when ASSETS grows` comment at the add-alternative handler |
| Removing the city input from step 1 means it is no longer the first thing filled in; users may miss it | Place city prominently at the top of step 3, above the comment field, with the existing pin icon |
