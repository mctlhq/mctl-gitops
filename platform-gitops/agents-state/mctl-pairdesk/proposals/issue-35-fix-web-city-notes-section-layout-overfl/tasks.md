# Tasks: issue-35-fix-web-city-notes-section-layout-overfl

- [ ] 1. Fix `.pd-form-sub` margin in `web/src/styles.css:921` — change
  `margin: -8px 0 12px` to `margin: 0 0 10px` so that the helper text
  carries a non-negative top margin and does not overlap any preceding
  element regardless of context.
  DoD: The single-line rule at line 921 reads
  `.pd-form-sub { font-size: var(--pd-fs-sub); color: var(--pd-hint); margin: 0 0 10px; line-height: 1.5; }`
  and no other rule in `styles.css` is modified.

- [ ] 2. Add "Notes" label and reorder helper text in
  `web/src/screens/CreateOrder.tsx:297-307` (depends on 1, but can be
  done in the same commit) — insert
  `<span className="pd-label">Notes <span className="pd-label-opt">· optional</span></span>`
  immediately before `<p className="pd-form-sub">`, and remove it from
  between the city field and the notes textarea. The final order of
  elements inside the step-3 `pd-form-section` div must be:
  (a) City pd-label, (b) city pd-field label, (c) Notes pd-label,
  (d) pd-form-sub paragraph, (e) notes textarea.pd-input.
  DoD: Lines 297-307 of `CreateOrder.tsx` match the markup shown in
  `design.md § Proposed solution`, and no other JSX in the file is
  changed.

- [ ] 3. Build and smoke-test the Mini App (depends on 2) — run
  `npm run build` (or `vite build`) in `web/` and confirm zero TypeScript
  errors and zero Vite warnings about the changed files.
  DoD: Build exits 0; `public/` is updated; no new console errors when
  the Mini App is loaded in a browser at 375 px viewport width.

## Tests

- [ ] T1. Visual check at 375 px viewport: open the Mini App in a Chromium
  DevTools mobile viewport (375x812), navigate to Create Order, reach
  step 3. Confirm: City label is fully visible above the city input; Notes
  label is visible above the notes textarea; the helper paragraph sits
  below the Notes label with no overlap of any field border; no horizontal
  scroll bar appears.

- [ ] T2. Visual check at 320 px viewport: repeat T1 at 320 px width.
  Confirm the helper paragraph wraps onto multiple lines without
  horizontal overflow.

- [ ] T3. Keyboard open simulation: in DevTools, toggle the mobile
  keyboard overlay (or use a physical device). Focus the city input, then
  the notes textarea. Confirm `scrollFieldIntoView` positions each field
  above the keyboard without the Notes label or helper text being obscured.

- [ ] T4. Regression check for other `.pd-label` / `.pd-form-sub` usages:
  open `Subscriptions.tsx` filter panel and `Profile.tsx` edit form.
  Confirm their labels and spacing are visually unchanged (neither screen
  uses `pd-form-sub`, so no regression is expected, but verify).

## Rollback

The fix is a two-file change committed on a feature branch. To roll back:

```
git revert <commit-sha>
```

This restores `web/src/styles.css` and `web/src/screens/CreateOrder.tsx`
to their pre-fix state in a single revert commit, which can then be merged
via the normal PR flow. No database migration, no infrastructure change,
and no environment variable is involved, so no further rollback action is
needed.
