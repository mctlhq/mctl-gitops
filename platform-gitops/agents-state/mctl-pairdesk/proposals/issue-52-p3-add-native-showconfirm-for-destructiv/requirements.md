# Add native showConfirm for destructive actions (cancel order / accept response)

## Context

PairDesk is a Telegram Mini App where vetted community members post and match P2P
exchange requests. Two actions in the order-detail flow carry significant, hard-to-
reverse consequences: a maker cancelling their order (which rejects all pending deals
and removes the order from the book) and a maker accepting a specific responder (which
is the concurrency-critical binding event that locks the order, shares contact details,
and auto-rejects all sibling deals). Both actions currently execute immediately on
button tap with no confirmation step.

Telegram's `WebApp.showConfirm` (Bot API 6.2+) provides a native, platform-consistent
confirmation dialog. The codebase already contains version-gating infrastructure in
`web/src/tg.ts` (see `disableSwipes`, which guards `disableVerticalSwipes` behind
`isVersionAtLeast('7.7')`). Adding a `showConfirm` wrapper there — with a
`window.confirm` fallback for plain-browser and older-client scenarios — is a
self-contained, low-risk improvement that raises the UX safety floor for these
two actions.

## User stories

- AS a maker I WANT a confirmation dialog before my order is cancelled SO THAT I do
  not accidentally remove my order from the book with a stray tap.
- AS a maker I WANT a confirmation dialog before I accept a responder SO THAT I do
  not accidentally lock in a deal and share contacts with the wrong person.
- AS a user running an older Telegram client or a plain browser SO THAT I still get
  confirmation protection even when `WebApp.showConfirm` is unavailable.

## Acceptance criteria (EARS)

- WHEN the maker taps "Cancel order" THE SYSTEM SHALL show a confirmation dialog
  with the message "Cancel this order? This cannot be undone." before sending the
  cancel request to the API.
- WHEN the maker taps "Accept" on a pending response THE SYSTEM SHALL show a
  confirmation dialog with the message "Accept this response? Contacts will be
  shared and other responses rejected." before sending the accept request to the API.
- IF the user confirms the dialog THEN THE SYSTEM SHALL proceed with the API call
  exactly as it does today (no change to request payload or backend behaviour).
- IF the user dismisses or cancels the dialog THEN THE SYSTEM SHALL abort the action
  and leave the order and deal states unchanged.
- WHILE `WebApp.showConfirm` is available (Bot API 6.2+) THE SYSTEM SHALL use the
  native Telegram dialog.
- IF `WebApp.showConfirm` is unavailable (older client or plain browser) THEN THE
  SYSTEM SHALL fall back to `window.confirm`, maintaining functional parity.
- IF `window.confirm` is also unavailable or blocked (e.g., sandboxed iframe) THEN
  THE SYSTEM SHALL default to confirmed (proceed without dialog) so the action
  remains operable.
- WHILE a confirmation dialog is open THE SYSTEM SHALL not allow duplicate
  submissions (the button is already guarded by the existing `busy` state which is
  set before the dialog resolves, so no additional change is needed provided the
  `busy` flag is set only after confirmation).

## Out of scope

- Backend changes: no server-side guard is added; the existing idempotency
  behaviour of `POST /orders/:id/cancel` and `POST /deals/:id/accept` is unchanged.
- The "Reject" action on a pending response is not included; it does not share
  contacts or lock any state and is lower stakes.
- The "Mark deal complete" action is not included; it is a cooperative completion
  step, not a unilateral destructive one.
- The "Respond to order" action (responder side) is not included; it is a
  submission, not a destructive action.
- Any changes to the `Deals.tsx` list screen; all affected actions live in
  `OrderDetail.tsx`.
- Bot API version detection beyond the `isVersionAtLeast` helper already in
  `web/src/tg.ts`.
- UI changes to the buttons themselves (label, styling, layout).

## Open questions

- The Telegram docs define `showConfirm(message, callback)` with a boolean result
  passed to the callback. The proposed implementation wraps it in a Promise. If the
  Telegram client invokes the callback synchronously in some versions, the Promise
  wrapper still works correctly. No ambiguity.
- The exact confirmation message wording is chosen here; the reviewer should
  confirm it matches community tone. Current proposal: "Cancel this order? This
  cannot be undone." and "Accept this response? Contacts will be shared and other
  responses rejected."
- None blocking implementation.
