# Tasks: issue-33-fix-web-hide-app-tab-bar-during-create-o

- [ ] 1. Conditionally render the tab bar in `web/src/App.tsx` — DoD: The
  `<nav className="pd-tabbar">` block (currently lines 83–97) is wrapped in
  `{tab !== 'create' && ( … )}`. When `tab === 'create'` the element is absent
  from the DOM; when `tab` is `'book'` or `'profile'` it is present and
  functionally identical to the current code. The `Tab` type and all other
  exports from `App.tsx` are unchanged.

- [ ] 2. Visual smoke-test — bottom padding during create (depends on 1) — DoD:
  Manually open the create flow on a device or simulator. Verify that no
  unexpected blank space appears below the Step 3 preview card or the inline
  Back/Publish buttons. If the 120 px guard in `.pd-content` produces visible
  excess whitespace, raise a follow-on issue rather than changing the padding in
  this PR (per the out-of-scope boundary).

## Tests

- [ ] T1. `tab === 'book'` — tab bar is rendered with all three buttons (Book,
  Create FAB, Profile). The Book button carries `is-active` and
  `aria-current="page"`.
- [ ] T2. `tab === 'create'` — no element matching `.pd-tabbar` is present in the
  DOM. The `<CreateOrder>` component is mounted inside `.pd-content`.
- [ ] T3. `tab === 'profile'` — tab bar is rendered; the Profile button carries
  `is-active`.
- [ ] T4. After `CreateOrder` fires `onCreated(id)` (simulated by calling the
  callback with a numeric id), `detailOrderId` is set and the app renders
  `<OrderDetail>` (the early return path in `App.tsx` line 70–72). The tab bar
  is not visible (the early return exits before it).
- [ ] T5. Keyboard-open behaviour — on book and profile screens, setting
  `html[data-keyboard-open]` (as `setupKeyboardTracking` does) applies
  `transform: translateY(100%)` to `.pd-tabbar`. This is a CSS-only rule and is
  not broken by the TSX change; verify in a browser DevTools computed-style check.
- [ ] T6. Safe-area inset — on a device or emulator with a bottom notch/bar, the
  tab bar bottom padding (`max(env(safe-area-inset-bottom), var(--tg-safe-area-inset-bottom, 0px))`)
  is applied correctly on book/profile screens after returning from create.

## Rollback

The change is a single conditional expression added to one JSX block in
`web/src/App.tsx`. Rollback is:

```
git revert <merge-commit-sha>
```

or, if reverting the whole commit is not appropriate, restore the original
unconditional nav block:

```tsx
// replace:
{tab !== 'create' && (
  <nav className="pd-tabbar">
    …
  </nav>
)}

// with:
<nav className="pd-tabbar">
  …
</nav>
```

No database migrations, no API changes, no config changes to undo.
