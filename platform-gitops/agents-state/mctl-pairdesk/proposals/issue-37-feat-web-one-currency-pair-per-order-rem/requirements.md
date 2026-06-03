# feat(web): one currency pair per order — remove Add alternative

## Context

`CreateOrder.tsx` currently lets a maker attach multiple give-options to a
single order (the "alternatives" feature introduced in issues #23/#24). A
maker picks a primary `giveAsset` on Step 1, then on Step 2 can add up to two
additional give-options (one per unused asset) each with its own rate and
payment methods. This results in a `give_options` array of up to three elements
being posted to `POST /orders`.

The product decision recorded in issue #37 reduces scope: exactly one
give-option per order. The "+ Add alternative" UI and all supporting machinery
must be removed from the Mini App. The API payload shape is unchanged — it
remains a `give_options` array, just always length 1. No server-side or schema
change is required.

## User stories

- AS a maker I WANT to configure a single give-option (asset, rate, payment
  methods) for my order SO THAT the creation flow is simpler and unambiguous.
- AS a maker I WANT the give-option asset on Step 2 to always match what I
  selected on Step 1 SO THAT I never publish an order with a mismatched
  currency.

## Acceptance criteria (EARS)

- WHEN a user reaches Step 2 of CreateOrder THE SYSTEM SHALL display exactly
  one give-option editor block.
- WHEN a user is on Step 2 of CreateOrder THE SYSTEM SHALL NOT display an
  "Add alternative" button or any per-option remove button.
- WHEN a user changes `giveAsset` on Step 1 THE SYSTEM SHALL update the
  single give-option's asset to match and reset its `max_rate` and
  `payment_methods` to empty values, unless the asset is unchanged.
- WHEN a user publishes an order THE SYSTEM SHALL post a `give_options` array
  with exactly one element containing the configured asset, max_rate, and
  payment_methods.
- WHILE a user is on Step 2 THE SYSTEM SHALL allow editing the rate (via
  RateSlider) and toggling payment methods for the single give-option.
- IF `giveAsset` equals `wantAsset` after a Step-1 change THE SYSTEM SHALL
  automatically resolve the collision (existing behavior in `handleGiveChange`
  / `handleWantChange`) so the two assets are always distinct.

## Out of scope

- Any API or database change — the server already accepts a one-element
  `give_options` array.
- Validation that the server rejects payloads with more than one give-option
  (that is a future server-side concern if needed).
- Subscription filters or order-book display changes.
- Restore / re-enable of multi-give-option functionality.

## Open questions

None. The issue specifies the exact file, line ranges, and expected behavior.
The only ambiguity is whether to retain `opts: OptDraft[]` as a one-element
array or flatten to scalar state; this proposal chooses the array form (see
design.md) as it minimises the diff and keeps the submit mapping unchanged.
