# Fix: city missing from Create-Order live preview card

## Context

In the PairDesk Mini App, Create-Order step 3 ("Note & preview") presents a
live `OrderCard` so the maker can verify the order appearance before
publishing. When the maker types a city (e.g. "Podgorica"), the city does not
appear in that card. The value is captured correctly in state and is submitted
to the API without loss; the defect is purely presentational and confined to
the `outcome` variant of `OrderCard`.

The root cause is a silent two-layer suppression: `OrderCard` (outcome variant)
passes `location_city` exclusively as the `sub` prop of the `Maker` component,
and `Maker` returns `null` immediately when its `maker` prop is `null` — the
preview order always has `maker: null` because the order has not yet been
submitted. No city element is ever mounted. A secondary instance of the same
pattern exists in the `rate` variant, where the card foot also routes city
through `Maker sub`; that variant is used for a maker's own order list and
always has a real maker at runtime, but the coupling is fragile for the same
reason.

## User stories

- AS a maker I WANT to see the city I typed reflected immediately in the
  Create-Order live preview card SO THAT I can verify the order will display
  correctly before publishing.
- AS a maker I WANT my published order to display the city pin in all card
  views where city is relevant SO THAT counterparties can locate me.
- AS a member browsing the order book I WANT city to appear on order cards
  whenever it is set SO THAT I can quickly filter by location before opening
  the detail view.

## Acceptance criteria (EARS)

- WHEN a user types a non-empty string in the City field of Create-Order
  step 3, THE SYSTEM SHALL show the city pin and text inside the live preview
  `OrderCard` (outcome variant) before the order is published.
- WHEN `order.maker` is `null` and `order.location_city` is a non-empty
  string, THE SYSTEM SHALL render the city pin element in the outcome variant
  card footer.
- WHEN `order.maker` is non-null and `order.location_city` is a non-empty
  string, THE SYSTEM SHALL render both the maker row and the city pin element
  in the outcome variant card footer.
- WHEN `order.location_city` is a non-empty string, THE SYSTEM SHALL render
  the city pin element in the rate variant card footer regardless of whether
  `maker` is populated.
- WHILE `order.location_city` is null or an empty string, THE SYSTEM SHALL NOT
  render a city pin element in the outcome or rate variant card footers.
- IF the city field is cleared after having been filled, THE SYSTEM SHALL
  remove the city pin from the preview card immediately (reactive binding is
  already in place via the `city` state variable).

## Out of scope

- Any API or database change.
- Changes to the `standard` or `compact` `OrderCard` variants (they already
  render city independently of `Maker`).
- Rendering a city on cards where `location_city` is genuinely null — do not
  fabricate placeholder text.
- Telegram bot notifications or server-side order serialization.
- Admin or deal-detail screens.

## Open questions

None. The issue fully specifies the expected behavior and the two candidate fix
locations. The approach of rendering city independently (rather than supplying
a placeholder maker) is adopted as stated in the issue notes.
