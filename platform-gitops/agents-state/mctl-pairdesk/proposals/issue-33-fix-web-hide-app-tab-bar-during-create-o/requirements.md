# fix(web): hide app tab bar during Create-Order flow

## Context
The PairDesk Mini App renders a persistent bottom tab bar (`Book / + / Profile`)
on the main screen. The tab bar is defined in `web/src/App.tsx` (lines 83–97) as
`<nav className="pd-tabbar">` and is `position: fixed` at the bottom of the
viewport (`web/src/styles.css` lines 86–99). It is rendered unconditionally for
every `tab` value, including `'create'`.

When the user taps the FAB ("+") to open the Create-Order flow (`tab === 'create'`),
the tab bar remains visible on top of the multi-step form. The Create-Order screen
is a full-screen, multi-step wizard (steps 1–3 across `web/src/screens/CreateOrder.tsx`)
that drives navigation via Continue / Back buttons and, in Telegram, the native
MainButton and BackButton. Having Book / + / Profile tabs present during this flow
creates visual clutter and an escape mechanism the user did not ask for. Hiding the
tab bar during create gives the flow full ownership of the screen, consistent with
the Telegram Mini App UX pattern of dedicated screens.

## User stories
- AS a community member I WANT the bottom tab bar to disappear when I start
  creating an order SO THAT the create flow owns the full screen and the tab bar
  buttons do not distract or overlap the form.
- AS a community member I WANT the tab bar to reappear once I finish (publish or
  cancel) the create flow SO THAT I can navigate back to the order book or profile
  without hunting for a navigation control.

## Acceptance criteria (EARS)

- WHEN `tab === 'create'` in `App.tsx` THE SYSTEM SHALL not render the
  `<nav className="pd-tabbar">` element.
- WHEN the user publishes a new order (the `onCreated` callback fires and
  `detailOrderId` is set) THE SYSTEM SHALL no longer be on `tab === 'create'`,
  so the tab bar remains absent (the app transitions to `OrderDetail`).
- WHEN the user navigates away from the create flow by any route that results in
  `tab !== 'create'` THE SYSTEM SHALL render the `<nav className="pd-tabbar">`
  element.
- WHILE `tab !== 'create'` THE SYSTEM SHALL preserve the existing
  `html[data-keyboard-open] .pd-tabbar { transform: translateY(100%); }` behaviour
  unchanged — the tab bar must still slide off-screen when the soft keyboard is
  open on book or profile screens.
- WHILE `tab !== 'create'` THE SYSTEM SHALL preserve the existing safe-area inset
  padding (`--tg-safe-area-inset-*`) on `.pd-tabbar` unchanged.
- IF the Create-Order flow is abandoned by tapping the tab bar (only possible on
  non-Telegram / dev-mode render where the in-page Back button is the control)
  THEN THE SYSTEM SHALL restore the tab bar as soon as `tab` changes.

## Out of scope
- Any change to the server-side API.
- Animation or slide-out transition when the tab bar disappears on entering create
  mode (the existing transition rule is for keyboard-open, not tab switches).
- Reducing the `.pd-content` bottom padding (`120px` guard) when in create mode;
  this is a follow-on quality-of-life improvement, not required by the issue.
- Introducing a new navigation abstraction or routing library.

## Open questions
1. **Content bottom padding during create**: `.pd-content` uses
   `calc(var(--pd-sp-5) + 120px + ...)` as bottom padding. The 120 px was
   sized to clear the tab bar (plus the FAB's `-10px` offset). When the tab bar
   is absent during create, this extra whitespace appears below the form.
   The issue does not call this out; treating it as out of scope is reasonable,
   but the implementer should verify it does not look wrong on the preview step.
2. **Direct-link / deep-link to `tab === 'create'`**: There is no current
   mechanism for this, but if one is added later, the hiding behaviour will
   automatically apply because it is driven by `tab` state.
