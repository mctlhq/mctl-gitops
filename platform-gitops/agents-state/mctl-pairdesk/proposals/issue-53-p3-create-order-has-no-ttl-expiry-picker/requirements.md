# Add TTL/Expiry Picker to Create-Order Flow

## Context

PairDesk orders carry an `expires_at` timestamp that is computed server-side from
`expires_in_seconds` (validated range: 300 s – 30 days; default: `ORDER_TTL_SECONDS`,
currently 72 hours). The API already accepts any valid `expires_in_seconds` value from
the client, but the Create-Order Mini App screen never sends the field, so every order
silently receives the 72-hour default.

This is a P3 gap: users who want to post a short-lived request (e.g. "I need this
exchange in the next hour") have no way to express that through the UI. The fix is
purely front-end: add a preset expiry picker to step 3 ("Note & preview") of the
Create-Order flow and include the chosen value in the POST body.

## User stories

- AS an approved community member I WANT to choose how long my order stays active
  SO THAT I can signal urgency (short TTL) or availability (long TTL) to responders.
- AS an approved community member I WANT the default expiry to remain 72 hours
  SO THAT I do not have to think about TTL for standard requests.
- AS an approved community member I WANT to see the computed expiry in the order
  preview before publishing SO THAT I can confirm the order will expire when I expect.

## Acceptance criteria (EARS)

- WHEN a user opens the Create-Order flow THE SYSTEM SHALL pre-select the 72-hour
  expiry option.
- WHEN a user selects an expiry preset on step 3 THE SYSTEM SHALL highlight that
  preset as active and deselect all other presets.
- WHEN a user publishes an order THE SYSTEM SHALL include `expires_in_seconds`
  matching the selected preset in the POST `/api/orders` request body.
- WHEN the API validates the submitted `expires_in_seconds` THE SYSTEM SHALL accept
  any value from 300 seconds to 2,592,000 seconds (30 days) and reject values outside
  that range with HTTP 400.
- WHILE the user is on the preview sub-section of step 3 THE SYSTEM SHALL display
  the computed expiry time (e.g. "expires in 1h", "expires in 72h") adjacent to or
  inside the order preview card.
- IF the user navigates back from step 3 to step 2 and then returns to step 3 THE
  SYSTEM SHALL retain the previously selected expiry preset (selection must survive
  the step transition, not reset to default).
- WHEN the order is created successfully THE SYSTEM SHALL return the order object
  including the server-computed `expires_at` ISO timestamp, and the existing detail
  and list screens SHALL display it unchanged (no additional UI work required for
  existing screens — `expires_at` is already in the `Order` type and serialized by
  the API).

## Out of scope

- A free-text / custom-duration input. Preset chips are sufficient for the MVP.
- Changes to the server-side `ORDER_TTL_SECONDS` default or the validation range
  (300 s – 30 d). Those are operator concerns.
- Displaying `expires_at` on the OrderBook list cards or the OrderDetail screen. Both
  surfaces already receive `expires_at` from the API; a future ticket can decide how
  to surface it.
- Order renewal / TTL extension after creation.
- Admin controls to override per-order TTL.

## Open questions

1. **Preset values**: The issue suggests "1h / 6h / 24h / 72h". This proposal adopts
   those four values (3,600 / 21,600 / 86,400 / 259,200 seconds). No blocker — proceed
   with these unless a reviewer specifies different presets.
2. **Expiry display format in preview**: The issue does not specify. This proposal
   displays a short human string ("expires in 1 h", "expires in 72 h") inside the
   existing preview card footer or below the Notes textarea. Either location is
   acceptable; implementer may choose the less intrusive spot.
3. **Accessibility label for preset chips**: The chip group should carry an accessible
   label ("Order expiry") — standard Telegram Mini App practice but not called out in
   the issue. Treat as a must-have, not an open question.
