# Tasks: issue-69-improve-mobile-responsiveness-of-tg-mctl

All changes are confined to `internal/web/landing.html`. No Go code changes, no new files,
no new HTTP routes. Tasks 1 and 2 are independent CSS property fixes; tasks 3-6 build the
new breakpoints and must be done after task 2 (markup changes needed for task 4 must land
before task 4's CSS is tested).

- [ ] 1. Fix `pre` overflow clipping in `internal/web/landing.html`
  Change `overflow: hidden` to `overflow-x: auto` on the `pre` rule (the `overflow`
  declaration is inside the `pre { ... }` block currently at line 369).
  DoD: a `pre` block containing a line wider than the viewport scrolls horizontally on a
  375px viewport rather than clipping or overflowing the page body.

- [ ] 2. Fix `.tbl` horizontal overflow in `internal/web/landing.html`
  Change `overflow: hidden` to `overflow-x: auto` on the `.tbl` rule (currently at line 463).
  `.tbl` already uses `border-collapse: separate` so `border-radius` is preserved.
  DoD: all three `.tbl` tables (tools at `#tools`, scopes at `#scopes`, storage at
  `#storage`) scroll horizontally within their own container on a 375px viewport; the page
  body shows no horizontal scrollbar.

- [ ] 3. Add `.hide-md` class to topbar markup (depends on nothing, required before task 4)
  In the `<nav class="meta">` block, add `hide-md` to the class list of the
  `<a href="#scopes">` anchor and to the `.accent-picker` `<span>`. No visible effect
  until the 768px media query in task 4 is in place.
  DoD: both elements have the `hide-md` class in the HTML source.

- [ ] 4. Add 768px breakpoint (depends on 3)
  Append a new `@media (max-width: 768px)` block to the second `<style>` block, after the
  existing `@media (max-width: 640px)` block. Include at minimum:
  - `.wrap { padding: 0 20px; }`
  - `.topbar .meta .hide-md { display: none; }`
  - `.theme-toggle { width: 44px; height: 44px; }` (touch target)
  - `.accent-swatch { min-width: 44px; min-height: 44px; }` (touch target; retain swatch
    visual size via inner background / centred display)
  DoD: at 768px Chrome DevTools emulation the scopes link and accent picker are hidden,
  the theme-toggle visible size is 44x44px, and the topbar does not overflow.

- [ ] 5. Add 480px breakpoint (depends on 4)
  Append a new `@media (max-width: 480px)` block after the 768px block. Include at minimum:
  - `.wrap { padding: 0 14px; }`
  - `h1 { font-size: 24px; letter-spacing: -.015em; }`
  - `.lead { font-size: 14px; }`
  - `.endpoint .url { font-size: 14px; }`
  - `ol.steps > li { padding: 10px 12px 10px 44px; }`
  - `ol.steps > li::before { left: 10px; top: 10px; width: 26px; height: 26px; font-size: 11px; }`
  - `pre code { font-size: 12px; }`
  - `.tbl { font-size: 12px; }`
  - `section { margin-top: 40px; }`
  - `.topbar { margin-bottom: 36px; }`
  DoD: page renders without any horizontal overflow at 375px viewport width (iPhone SE
  emulation) in both Chrome and Firefox DevTools. The `ol.steps` counter chips at `#setup`
  are fully visible and not clipped.

- [ ] 6. Verify font-loading graceful degradation (depends on 1-5; verification only, no code change required)
  In Chrome DevTools Network tab, block `fonts.googleapis.com` and `fonts.gstatic.com`,
  reload the page at 375px. Confirm the page is readable with the system-ui / ui-monospace
  fallback fonts declared in `--font-display` and `--font-mono`. If the fallback stack
  produces a broken layout (e.g. a monospace font used where a display font is expected),
  add an explicit fallback font-size adjustment in a `@supports not (font-family: 'Geist')`
  block or adjust the fallback stack order. No change is required if the page reads cleanly.
  DoD: page is legible without web fonts loaded; no layout collapse or unreadable text at
  375px.

## Tests

- [ ] T1. **375px baseline** — Open the running server (or `go run ./cmd/server/main.go`)
  in Chrome DevTools at iPhone SE emulation (375x667). Check: no `<body>`-level horizontal
  scrollbar; all three `.tbl` tables scroll within their own container; the `#smoke` `pre`
  block scrolls horizontally; `ol.steps` counter chips at `#setup` are fully visible; the
  `.endpoint .url` code block wraps or scrolls without overflowing `.wrap`.

- [ ] T2. **480px breakpoint** — Repeat T1 at 480px viewport width. Verify the 480px media
  query rules apply: `h1` is 24px, `ol.steps > li::before` chip is 26px, `pre code` font
  is 12px.

- [ ] T3. **768px breakpoint** — Repeat T1 at 768px viewport width. Verify: the
  `<a href="#scopes">` link is hidden; the `.accent-picker` is hidden; the `.theme-toggle`
  hit area is 44x44px (measure with DevTools computed styles); the topbar does not overflow
  its row.

- [ ] T4. **Font-loading fallback** — Block `fonts.googleapis.com` in DevTools Network,
  reload at 375px. Verify the page is readable with fallback fonts; no layout shift or
  unreadable text.

- [ ] T5. **CDN CSS fallback** — Block `ui.mctl.ai` in DevTools Network, reload. Verify
  the inline CSS variable fallback block provides correct colours (dark background, light
  text, accent colour on headings/links).

- [ ] T6. **Build check** — Run `go build ./...` from the repo root. The `//go:embed
  landing.html` directive must succeed; any malformed HTML that breaks Go template parsing
  will surface here.

- [ ] T7. **Vet check** — Run `go vet ./internal/web/...`. No regressions expected, but
  confirms the package compiles cleanly after the template edit.

- [ ] T8. **Existing 640px breakpoint unaffected** — At exactly 640px viewport width verify
  the existing `.hide-sm` rule still hides the scopes link (it already had `hide-sm` in the
  original markup), the topbar padding is 18px, and no regressions from the new blocks.

## Rollback

The change is a single-file edit to `internal/web/landing.html`. The landing page is served
with `Cache-Control: no-store` (`internal/web/landing.go:57`), so clients always fetch the
latest version and a rollback is visible immediately after redeployment.

To roll back:
```
git revert <merge-commit>
```
or, to surgically restore the file without reverting other changes in the same commit:
```
git checkout <prior-sha> -- internal/web/landing.html
```

Then redeploy. No database migration, no config change, no operator action is required.
