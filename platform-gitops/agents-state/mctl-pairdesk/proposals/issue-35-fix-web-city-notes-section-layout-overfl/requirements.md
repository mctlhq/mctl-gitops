# fix(web): CITY and Notes section layout overflow in Create-Order step 3

## Context

In the Create-Order flow (`web/src/screens/CreateOrder.tsx`), step 3 ("Note & preview")
contains a city input and a notes textarea. The current JSX places the helper paragraph
(`pd-form-sub`) between the city field and the notes textarea, and the notes textarea has
no label. The `.pd-form-sub` rule in `web/src/styles.css:921` uses `margin: -8px 0 12px`.
That negative top margin was designed to pull hint text closer to a preceding label element,
but the city field (`label.pd-field`) carries no margin-bottom, so the -8px is applied as a
literal 8 px upward shift that visually overlaps the bottom edge of the city field box.

This causes the helper text to appear clipped against or embedded inside the city field, and
the notes textarea — which has no label — appears to float without context. On the narrow
Telegram Mini App viewport (roughly 343 px usable after safe-area insets) the effect is
especially noticeable. The issue is purely CSS and JSX markup; no API or data layer is
involved.

## User stories

- AS a community member creating a P2P exchange order I WANT the City and Notes fields in
  step 3 to display with clean, unclipped labels and consistent spacing SO THAT I can
  confidently fill them in without visual confusion.
- AS a developer maintaining the Mini App I WANT `.pd-form-sub` helper text to align with
  the element it describes SO THAT adding new form fields with helper text does not require
  workarounds.

## Acceptance criteria (EARS)

- WHEN the user navigates to step 3 of Create-Order THE SYSTEM SHALL render the City label,
  City field, Notes label, Notes helper text, and Notes textarea as five visually distinct,
  non-overlapping elements in that top-to-bottom order.
- WHEN the Mini App viewport width is 320 px or greater THE SYSTEM SHALL display no
  horizontal text overflow or clipping in the City label, Notes label, or Notes helper
  paragraph.
- WHILE the on-screen keyboard is open THE SYSTEM SHALL keep the active field (city input or
  notes textarea) scrolled into view without the helper text or Notes label overlapping any
  field border.
- IF `.pd-form-sub` follows any `.pd-label` element THE SYSTEM SHALL render the helper text
  with a non-negative top clearance so that it does not overlap the label's rendered bounding
  box.
- WHEN the City input or Notes textarea is focused THE SYSTEM SHALL show the focus ring on
  the correct field only (no ring bleed onto adjacent elements).

## Out of scope

- Any change to the Express/TypeScript API layer.
- Subscriptions.tsx or Profile.tsx — those screens also use `.pd-label` but do not use
  `.pd-form-sub` and are not reported as broken.
- Step 1 or step 2 of the Create-Order flow.
- The preview card (`pd-preview`) rendered below the textarea.
- Internationalization, placeholder text changes, or copy edits.

## Open questions

- None. The issue identifies the exact lines and the expected visual outcome. The most
  reasonable interpretation is: restructure the step-3 markup to add a "Notes" label and
  place the helper text beneath it, and fix the `.pd-form-sub` margin to eliminate the
  negative-top overlap.
