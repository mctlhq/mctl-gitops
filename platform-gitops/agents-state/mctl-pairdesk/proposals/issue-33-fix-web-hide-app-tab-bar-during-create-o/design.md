# Design: issue-33-fix-web-hide-app-tab-bar-during-create-o

## Current state

### Tab-based rendering in App.tsx
`web/src/App.tsx` manages the single-page shell for the approved, post-disclaimer
user. A `tab` state (`'book' | 'create' | 'profile'`, defined in the `Tab` type at
line 13) drives which screen is shown inside `<main className="pd-content">` (lines
78–82):

```tsx
{tab === 'book'    && <OrderBook onOpen={setDetailOrderId} />}
{tab === 'create'  && <CreateOrder onCreated={(id) => setDetailOrderId(id)} />}
{tab === 'profile' && <Profile … />}
```

After `<main>`, the tab bar is rendered unconditionally (lines 83–97):

```tsx
<nav className="pd-tabbar">
  <button … Book …/>
  <button … Create FAB …/>
  <button … Profile …/>
</nav>
```

Because the tab bar is outside the conditional screen blocks it is always mounted,
regardless of the active tab.

### Tab bar CSS (web/src/styles.css lines 86–142)
- `position: fixed; bottom: 0; left: 0; right: 0` — overlaps any content below it.
- `padding-bottom: calc(7px + max(env(safe-area-inset-bottom), var(--tg-safe-area-inset-bottom, 0px)))` — respects device/Telegram safe areas.
- `transition: transform .15s ease` — used for the keyboard-open slide-out.
- `html[data-keyboard-open] .pd-tabbar { transform: translateY(100%); }` — slides
  the bar off-screen when a soft keyboard is open. `data-keyboard-open` is toggled
  by `setupKeyboardTracking()` in `web/src/tg.ts` (lines 169–196) based on
  `window.visualViewport` resize events.

### CreateOrder screen (web/src/screens/CreateOrder.tsx)
`CreateOrder` is a three-step wizard:
- Step 1 – currency pair selection.
- Step 2 – give-asset rate and payment methods.
- Step 3 – note, comment, and publish preview.

Navigation is driven by the Telegram native MainButton (`setMainButton` in `tg.ts`)
and BackButton (`showBackButton`) when running inside Telegram. In plain-browser
dev mode the screen renders inline Continue / Back `<button>` elements (guarded by
`!hasMainButton()`). The FAB button in the tab bar also maps to `tab === 'create'`
and is shown as `is-active` during the flow, but tapping it again is a no-op
(already on create).

### Content bottom padding
`.pd-content` bottom padding includes a hard-coded 120 px guard
(`web/src/styles.css` line 49):
```css
calc(var(--pd-sp-5) + 120px + var(--pd-keyboard-height, 0px) + max(…))
```
This is sized to clear the tab bar height plus the FAB's 10 px upward offset.

---

## Proposed solution

**Conditionally render the `<nav className="pd-tabbar">` only when
`tab !== 'create'`.**

In `web/src/App.tsx`, wrap the nav element with a short-circuit:

```tsx
{tab !== 'create' && (
  <nav className="pd-tabbar">
    …
  </nav>
)}
```

### Why this approach
1. **Minimal diff.** One three-line change in a single file; no new state, no new
   CSS rules, no new abstractions.
2. **Correct by construction.** The tab bar is absent precisely when and only when
   the create flow is mounted. No risk of a CSS class or attribute being left in
   the wrong state across re-renders.
3. **Keyboard behaviour unaffected.** The `html[data-keyboard-open]` selector and
   the `setupKeyboardTracking` logic in `tg.ts` continue to operate on whatever
   `.pd-tabbar` elements exist in the DOM. During create, there are none, so the
   rule is inert. On book and profile screens the rule remains fully functional.
4. **Safe-area handling unaffected.** The tab bar's own safe-area padding is only
   relevant when the element is mounted. `.pd-content` safe-area padding is
   independent (inset from `--tg-content-safe-area-inset-*`) and is not touched.
5. **React-idiomatic.** Conditional rendering is the established React pattern for
   toggling UI based on state. It avoids leaving hidden DOM that screen readers or
   automated tests might inadvertently interact with.

### No CSS changes required for the core fix
The existing `transition: transform .15s ease` on `.pd-tabbar` is for the
keyboard-open path only. Removing the element on tab switch is an instantaneous
unmount; no transition is needed or expected.

---

## Alternatives

### Alternative 1 — CSS class modifier (`pd-tabbar--hidden`)
Add a CSS class `pd-tabbar--hidden` with `display: none` to the nav when
`tab === 'create'`, and remove it otherwise:

```tsx
<nav className={`pd-tabbar${tab === 'create' ? ' pd-tabbar--hidden' : ''}`}>
```

```css
.pd-tabbar.pd-tabbar--hidden { display: none; }
```

**Dropped because:** the element remains in the DOM (wasted memory, potentially
confusing for automated tests or accessibility tools). It also requires a new CSS
rule for something conditional rendering handles without any CSS at all. There is
no animation benefit because `display` cannot be transitioned.

### Alternative 2 — `data-tab` attribute on `.pd-app` + CSS selector
Set `data-tab={tab}` on the outer `<div className="pd-app">` and write a CSS rule:

```css
.pd-app[data-tab="create"] .pd-tabbar { display: none; }
```

**Dropped because:** this scatters the logic across both TSX and CSS, making the
intent harder to follow. It also still leaves the element in the DOM (same drawback
as Alternative 1). The React JSX approach is both simpler and more explicit.

### Alternative 3 — Make CreateOrder a modal / separate full-screen overlay
Render `CreateOrder` as a CSS `position: fixed` overlay above the tab bar rather
than as a sibling in the content flow, so the tab bar is visually obscured.

**Dropped because:** it changes the component architecture significantly without
adding user-visible value. The issue explicitly states the create flow is already a
full-screen route (`App.tsx:80`) and asks only for the tab bar to be hidden, not for
a structural refactor.

---

## Platform impact

### Migrations
None. This is a pure front-end change confined to `web/src/App.tsx`.

### Backward compatibility
The `Tab` type exported from `App.tsx` (`'book' | 'create' | 'profile'`) is
unchanged. No other file depends on whether the tab bar element is mounted.

### Resource impact
Negligible: one fewer DOM element and its three child buttons are unmounted while
the create flow is active. No meaningful memory or layout cost.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Safe-area inset on device notch misaligns during create | Low | `.pd-content` uses `--tg-content-safe-area-inset-*` independently; tab bar absence does not affect it. Verify on a device with a bottom safe area. |
| Residual 120 px bottom padding on `.pd-content` during create causes excess whitespace | Low–medium | Out of scope for this fix but worth a visual check; a follow-on CSS tweak (conditional `padding-bottom` via a class) is straightforward if needed. |
| Re-mount cost of tab bar on returning to book/profile | Negligible | Three buttons and three SVG icons; no data fetching, no side effects on mount. |
