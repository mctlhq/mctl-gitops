# fix(web): Rework Create-Order step navigation buttons

## Context

The Create-Order wizard (`web/src/screens/CreateOrder.tsx`) is a three-step flow.
Navigation uses two parallel mechanisms: inside Telegram the native MainButton
(bottom bar) drives the primary action and the native BackButton drives back
navigation; in a plain browser (local dev, `AUTH_DEV_BYPASS`) in-page HTML
buttons serve both roles. Currently the in-page Back button on steps 2 and 3 is
rendered unconditionally — it appears even in a real Telegram session where the
native BackButton is already active, producing a duplicate back control that
floats detached from any primary-action button. The desired result is one clean
action row per step, consistent across both environments.

The fix is confined entirely to the Mini App (`web/`). No API routes, database
schema, or server code are affected.

## User stories

- AS a maker I WANT a single, clearly placed Back button per step SO THAT I do
  not see two separate back controls at the same time.
- AS a maker I WANT the Back and Continue/Publish buttons to sit side by side in
  a single row SO THAT the relationship between the two actions is visually clear.
- AS a developer running the app in a plain browser (AUTH_DEV_BYPASS) I WANT the
  in-page button row to behave identically to the Telegram-hosted flow SO THAT
  local dev faithfully represents the production UI.

## Acceptance criteria (EARS)

- WHEN the user is on step 1 THE SYSTEM SHALL show exactly one primary-action
  button labelled "Continue" (via Telegram MainButton or in-page fallback) and no
  Back button.
- WHEN the user is on step 2 THE SYSTEM SHALL show a "Back" button immediately to
  the left of a "Continue" button in a single flex row, with Back rendered as a
  ghost control and Continue rendered as the block/primary control.
- WHEN the user is on step 3 THE SYSTEM SHALL show a "Back" button immediately to
  the left of a "Publish request" button in a single flex row, with the same
  Back-ghost / Publish-primary pairing.
- WHILE `hasMainButton()` returns true (real Telegram client) THE SYSTEM SHALL
  suppress the in-page Back button and in-page primary-action button entirely,
  relying solely on the native Telegram controls.
- WHILE `hasMainButton()` returns false (plain browser) THE SYSTEM SHALL render
  all navigation controls as in-page HTML buttons.
- WHEN step 2's Continue button is rendered in-page THE SYSTEM SHALL disable it
  whenever `amountValid` is false, mirroring the existing `nextEnabled` gate.
- WHEN step 3's Publish button is rendered in-page THE SYSTEM SHALL disable it
  whenever `busy` is true, mirroring the existing `nextEnabled` gate.
- IF an error occurs during submission on step 3 THE SYSTEM SHALL display the
  error message above the action row as it does today.

## Out of scope

- Changes to the Telegram MainButton or BackButton effects (lines 170-182 in
  `CreateOrder.tsx`); those already work correctly.
- Any modification to the `nextEnabled` or `nextText` logic.
- Any API, server, or database change.
- Multi-step form state persistence across navigation (existing behaviour is
  preserved).
- Bot notifications, subscription matching, or any Stage 4 work.

## Open questions

- None. The issue fully specifies the desired per-step layout and names the exact
  lines to change.
