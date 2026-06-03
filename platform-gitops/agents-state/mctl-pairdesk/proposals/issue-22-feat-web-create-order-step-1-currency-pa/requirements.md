# feat(web): Create Order step 1 — currency-pair selector with swap (want / give)

## Context
The New Request flow (`web/src/screens/CreateOrder.tsx`) currently presents step 1 as
a single `AssetSelect` component that picks only `wantAsset` ("I want to receive"), while
the give side is deferred entirely to step 2 as a potentially multi-option list. This
separation is confusing: the maker's core intent — which pair they are trading — is split
across two screens.

The redesign folds the give asset into step 1, presenting both sides as a stacked
currency-pair picker modelled on the T-Bank currency-rates screen: one row for "I have"
(give asset) and one row for "I want to get" (want asset), with a round swap button between
them. Exactly one give asset is allowed — the multi-alternative give workflow is removed.
The backend already supports every EUR/RUB/USDT directed pair through `getReferenceRate`
in `src/services/rates.ts`, so this is a pure UI change with no schema or API work.

## User stories
- AS a maker I WANT to see both sides of my trade on the first form screen SO THAT I can
  understand and confirm the full pair before entering an amount.
- AS a maker I WANT a swap button between the two asset rows SO THAT I can quickly flip the
  direction of my trade without re-selecting both sides manually.
- AS a maker I WANT to freely select any of the six directed EUR/RUB/USDT pairs SO THAT I
  am not artificially limited to a subset of combinations.

## Acceptance criteria (EARS)

### Pair display
- WHEN the user opens step 1 of the New Request flow THE SYSTEM SHALL display two stacked
  rows: "I have" (give asset) above and "I want to get" (want asset) below, each showing
  the currency glyph and three-letter code.
- WHILE step 1 is visible THE SYSTEM SHALL keep both rows in sync so that the two selected
  assets are always different (never equal).

### Asset selection
- WHEN the user taps a different asset on the "I have" row THE SYSTEM SHALL update the give
  asset and, if the newly selected asset equals the current want asset, automatically set the
  want asset to the one remaining free asset.
- WHEN the user taps a different asset on the "I want to get" row THE SYSTEM SHALL update the
  want asset and, if the newly selected asset equals the current give asset, automatically set
  the give asset to the one remaining free asset.
- WHILE either side is being changed THE SYSTEM SHALL call `hapticSelection()` once per
  committed tap.
- IF `ASSETS` = ['EUR', 'RUB', 'USDT'] THEN THE SYSTEM SHALL allow all six directed pairs
  to be selected: EUR→RUB, RUB→EUR, EUR→USDT, USDT→EUR, RUB→USDT, USDT→RUB.

### Swap button
- WHEN the user taps the swap button THE SYSTEM SHALL exchange the give and want asset values
  and call `hapticSelection()`.
- WHILE a swap results in the two values already being distinct THE SYSTEM SHALL not
  auto-bump either side (the direct flip is always safe because they were distinct before).

### Amount and city
- WHILE step 1 is active THE SYSTEM SHALL display the amount input below the pair picker,
  pre-labelled with the want asset glyph and code, matching the currently selected `wantAsset`.
- WHILE step 1 is active THE SYSTEM SHALL display the optional city field below the amount
  input, retaining existing behaviour unchanged.

### Step 2 — single give option
- WHEN the user proceeds to step 2 THE SYSTEM SHALL show the rate and payment-method editor
  for exactly one give option, pre-populated with the give asset chosen in step 1.
- WHILE step 2 is active THE SYSTEM SHALL NOT show the give-asset segmented control,
  the Remove button, or the "Add alternative" button.
- WHILE step 2 is active THE SYSTEM SHALL display the section title as "I will give" (not
  "I will give — one of these").
- WHEN the user submits the form THE SYSTEM SHALL send `POST /orders` with
  `give_options` containing exactly one element whose `asset` matches the give asset
  selected in step 1.

### Build
- WHEN `npm run type-check` is run THE SYSTEM SHALL exit with code 0 (no TypeScript errors).
- WHEN `npm run build` is run THE SYSTEM SHALL exit with code 0 (no Vite build errors).

## Out of scope
- Epic #24 contract changes: any backend API changes to accept a top-level `give_asset`
  field instead of `give_options[]`. This proposal keeps the existing array-based contract
  with exactly one element.
- Epic #23: the rate slider on step 2 is an independent issue; this proposal changes only
  what happens in step 1 and removes the multi-option UI from step 2.
- Adding new asset codes (beyond EUR, RUB, USDT) — `ASSETS` in `web/src/types.ts` is
  unchanged.
- Backend `getReferenceRate` — confirmed already supports all six directed pairs via RUB
  cross in `src/services/rates.ts`; no change required.
- Subscription filter UI — `web/src/screens/Subscriptions.tsx` is not modified.
- Any change to the step 3 note/preview screen.

## Open questions
1. **Default initial pair.** The current state defaults to `wantAsset='EUR'` with the first
   give option `asset='RUB'`. The proposal keeps EUR/RUB as the initial pair (give=RUB,
   want=EUR) because it is the most common direction. If the product team prefers a
   different default, it is a one-line change.
2. **Per-row selector style.** The issue references the T-Bank screen but does not provide
   a screenshot file. The proposal interprets "flag/glyph + code" as reusing the existing
   `AssetSelect` component (three-pill horizontal row per side) with the opposite asset
   excluded, rather than a tappable single-row that opens a sheet picker. If a sheet picker
   is preferred, an additional component and routing work would be required.
3. **Step 2 give-asset display.** When the user reaches step 2, the give asset is already
   fixed. The proposal shows it as a read-only label rather than keeping the segmented
   control. This could be reversed if the decision is that the asset must remain editable
   on step 2.
