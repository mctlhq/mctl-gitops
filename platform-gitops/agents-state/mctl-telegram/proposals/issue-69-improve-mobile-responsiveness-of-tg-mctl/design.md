# Design: issue-69-improve-mobile-responsiveness-of-tg-mctl

## Current state

The landing page lives entirely in `internal/web/landing.html`, embedded into the Go binary
via `//go:embed landing.html` in `internal/web/landing.go` and served by `Landing()`
(`internal/web/landing.go:44`). The template is rendered with `text/html.Template` against
a `landingData` struct that injects the MCP endpoint URL and OAuth well-known URLs. There is
no external stylesheet written by this repository; all page-specific CSS is inlined in two
`<style>` blocks in the `<head>`. A third-party design-token stylesheet (`ui.mctl.ai/mctl.css`)
is loaded from a CDN; an inline fallback variable block precedes it so the page is usable if
the CDN fails.

### Responsive CSS today

The file contains a single media query at lines 625-634:

```css
@media (max-width: 640px) {
  .wrap { padding: 0 18px; }
  .topbar .meta { gap: 12px; font-size: 11px; }
  .topbar .meta .hide-sm { display: none; }
  h1 { font-size: 28px; }
  .lead { font-size: 15px; }
  .tbl { font-size: 12.5px; }
  .tbl thead th, .tbl tbody td { padding: 8px 10px; }
  ol.steps > li { padding: 12px 14px 12px 50px; }
}
```

### Problem areas identified from the file

**Tables** (`internal/web/landing.html` lines 454-492, and three `<table class="tbl">` blocks
in the tools, scopes, and storage sections): The `.tbl` rule sets `overflow: hidden` (line 463)
and `width: 100%`. The table is a direct child of `.wrap` with no scroll-container wrapper.
On viewports narrower than the table's natural content width the table either overflows the
viewport silently or forces a page-level horizontal scrollbar.

**Code blocks** (lines 364-374): The `pre` rule sets `overflow: hidden`. On mobile, long
curl commands in the smoke-test section at `#smoke` (lines 881-888) overflow without
providing a scroll affordance. This is a straightforward one-property fix independent of
any breakpoint work.

**Touch targets**: `.theme-toggle` is explicitly sized to `width: 28px; height: 28px`
(lines 537-541), and `.accent-swatch` to `width: 16px; height: 16px` (lines 572-578).
Both are below the 44x44 CSS pixels recommended by WCAG 2.5.5 and Apple's Human Interface
Guidelines for touch targets.

**Setup-instructions density at 480px**: `ol.steps > li` uses `padding: 14px 16px 14px 56px`
(line 406), placing the `::before` counter chip at `left: 16px; top: 14px` with
`width: 28px; height: 28px`. On a 375px screen with `padding: 0 18px` on `.wrap` the usable
column width is 339px and the step text area is 339 - 56 = 283px, which is adequate but
tight. At 320px (the smallest common viewport) it drops to 220px; the counter chip and text
can become cramped.

**Topbar at 768-640px**: Between these widths the `.meta` nav shows all items including the
accent picker and scopes link. The accent-picker row with four 16px swatches sits in a flex
row alongside five nav links. On a 768px tablet in portrait this does not overflow but
approaches its limit.

**Font loading**: Google Fonts are requested with the `display=swap` URL parameter (line 43),
which is the correct approach. The `--font-display` and `--font-mono` CSS custom properties
reference system-ui and ui-monospace as fallbacks (lines 29-30). If the request fails the
browser uses system fonts immediately. This is already adequate; no code change is required
here, only verification.

## Proposed solution

All changes are confined to the inline CSS inside `internal/web/landing.html`. No Go code
changes, no new files, no new HTTP routes.

### Change 1 — Fix `pre` overflow (line 369)

Change:
```css
overflow: hidden;
```
to:
```css
overflow-x: auto;
```

This is a global correction not tied to any breakpoint. It affects the smoke-test `pre` and
any future `pre` blocks added to the page.

### Change 2 — Fix table horizontal overflow (line 463)

Change `overflow: hidden` to `overflow-x: auto` on `.tbl`. Because `.tbl` uses
`border-collapse: separate` (line 457), `border-radius` is preserved while `overflow-x: auto`
enables horizontal scrolling. No HTML markup changes are required.

### Change 3 — Add a 768px breakpoint

Insert a new `@media (max-width: 768px)` block after the existing 640px block:

```css
@media (max-width: 768px) {
  .wrap { padding: 0 20px; }
  .topbar .meta .hide-md { display: none; }
  .theme-toggle { width: 44px; height: 44px; }
  .accent-swatch { min-width: 44px; min-height: 44px; padding: 0; }
}
```

Add the class `hide-md` to the `<a href="#scopes">` nav link and to the `.accent-picker`
`<span>` in the topbar HTML (two markup changes). These elements are less critical on tablet
viewports and their removal prevents topbar crowding.

The `.theme-toggle` and `.accent-swatch` size increase at this breakpoint brings tap targets
to the recommended 44x44px minimum. The visual swatch colour indicator should remain centred
inside the larger button using `display: grid; place-items: center` or equivalent.

### Change 4 — Add a 480px breakpoint

Insert a new `@media (max-width: 480px)` block:

```css
@media (max-width: 480px) {
  .wrap { padding: 0 14px; }
  h1 { font-size: 24px; letter-spacing: -.015em; }
  .lead { font-size: 14px; }
  .endpoint .url { font-size: 14px; }
  ol.steps > li { padding: 10px 12px 10px 44px; }
  ol.steps > li::before { left: 10px; top: 10px; width: 26px; height: 26px; font-size: 11px; }
  pre code { font-size: 12px; }
  .tbl { font-size: 12px; }
  section { margin-top: 40px; }
  .topbar { margin-bottom: 36px; }
}
```

These values are derived from the existing 640px breakpoint by extrapolating the same
proportional reductions and are chosen to keep the page non-overflowing at 375px width
(iPhone SE, the reference device called out in the issue).

### Change 5 — Font-loading verification (no code change)

The `--font-display: 'Geist', system-ui, -apple-system, sans-serif` and
`--font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace` fallback stacks
(lines 29-30) are already correct. The Google Fonts URL already includes `display=swap`.
No change required; the task is to verify this behaviour during testing.

### Summary of file changes

| Location | Change |
|---|---|
| `pre` rule, line 369 | `overflow: hidden` to `overflow-x: auto` |
| `.tbl` rule, line 463 | `overflow: hidden` to `overflow-x: auto` |
| Topbar `<a href="#scopes">` | add class `hide-md` |
| Topbar `.accent-picker` `<span>` | add class `hide-md` |
| End of `<style>` block | add `@media (max-width: 768px)` block |
| End of `<style>` block | add `@media (max-width: 480px)` block |

Estimated CSS addition: 25-35 lines. Estimated HTML markup change: 2 attributes.

## Alternatives

### A: Card-layout tables on mobile

On viewports below 480px, hide `<thead>` and use a CSS `::before` pseudo-element with
`content: attr(data-label)` to prefix each cell with its column heading, turning each row
into a vertical card. This avoids horizontal scroll entirely and is more readable when table
columns have wide content.

Rejected because: (1) requires adding a `data-label` attribute to every `<td>` across three
tables (approximately 40 cells), cluttering the HTML; (2) adds roughly 80 additional lines
of CSS with per-table column-label definitions; (3) the tables here are reference material,
not interactive forms, so horizontal scroll with a visual affordance is acceptable and
familiar to mobile users. The approach is documented here for a follow-up if product decides
scroll is insufficient.

### B: Extract responsive CSS to a separate embedded file

Create `internal/web/mobile.css`, embed it via `//go:embed mobile.css`, serve it at
`/mobile.css`, and reference it with `<link rel="stylesheet" media="screen and
(max-width:768px)" href="/mobile.css">`.

Rejected because: (1) the page is served with `Cache-Control: no-store`, so the separate
file provides no caching benefit; (2) adds a new HTTP route and embed target for a small
amount of CSS; (3) contradicts the inline-CSS convention used by both `landing.html` and
`security.html` in the same package; (4) creates a split between base and responsive styles
that must be kept in sync manually.

### C: CSS utility framework (Tailwind via CDN)

Replace custom CSS with Tailwind CDN utility classes for built-in responsive utilities.

Rejected because: (1) adds a large CDN dependency (`cdn.tailwindcss.com`, ~100 KB) to a
page that deliberately budgets external requests; (2) requires rewriting all existing class
names and HTML structure; (3) the mctl design-token system from `ui.mctl.ai/mctl.css` does
not map cleanly onto Tailwind utility semantics; (4) Tailwind CDN is explicitly not
recommended for production by the Tailwind project.

## Platform impact

**Migrations**: None. CSS changes to an embedded template have no database, config, or
migration implications.

**Backward compatibility**: Fully backward-compatible. Media queries and the `overflow-x:
auto` corrections are additive or strictly less restrictive. The `overflow: hidden` on
`pre` was already causing silent content loss, so changing it to `overflow-x: auto` is a
correctness fix on desktop as well.

**Resource impact**: The HTML payload increases by approximately 30-40 lines of CSS (roughly
800-1000 bytes uncompressed). The binary size increases negligibly. No new network requests
are introduced.

**Safari iOS risk**: WebKit has historically had edge cases with `overflow` on table elements.
Specifically, `overflow-x: auto` on a `<table>` element with `border-radius` can cause the
radius to be ignored in some older versions. Mitigation: if Safari iOS testing reveals this
issue, wrap each `<table class="tbl">` in `<div class="tbl-scroll">` and style
`.tbl-scroll { overflow-x: auto; }` instead of changing the table's own overflow property.
The `<table>` itself would revert to `overflow: hidden`.

**CSP**: No new inline handlers or `style` attributes are introduced. The existing
`Content-Security-Policy` header (if configured by the operator deployment) is unaffected.
