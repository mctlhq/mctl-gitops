# Design: issue-154-nav-replace-github-text-link-with-a-gith

## Current state

All shared page chrome is defined in `internal/ui/chrome.go`. The file embeds
four assets (`assets/tokens.css`, `assets/components.css`, `assets/prepaint.js`,
`assets/toggle.js`) and builds a `html/template` variable called `base` from the
string `defs`, which contains four template defines:

- `ui_head` — `<head>` content for full pages (external CSS/fonts, pre-paint JS).
- `ui_topbar` — the `<header class="topbar">` element with brand + nav.
- `ui_footer` — page footer with text nav links.
- `ui_script` — the theme/accent toggle JS snippet.

The nav portion of `ui_topbar` (lines 65-81 of `chrome.go`) reads:

```html
<nav class="meta">
  <a href="/"          ...>home</a>
  <a href="/docs"      ...>docs</a>
  <a href="/security"  ...>security</a>
  <a href="/privacy"   ...>privacy</a>
  <a href="https://github.com/mctlhq/mctl-telegram" target="_blank" rel="noopener">github ↗</a>
  <span class="accent-picker" ...>...</span>
  <button class="theme-toggle" ...>
    <svg class="icon-moon" ...>...</svg>
    <svg class="icon-sun"  ...>...</svg>
  </button>
</nav>
```

The `theme-toggle` button already uses two inline SVG icons. Those SVGs use
`stroke="currentColor"` so they inherit the color of `.topbar a` / `.topbar
button` from `assets/components.css` without custom rules:

```css
/* assets/components.css, lines 109-115 */
.topbar a { color: var(--text-dim); text-decoration: none; transition: color .15s; }
.topbar a:hover { color: var(--text); }
.topbar a.active { color: var(--accent); }
```

The theme-toggle SVG dimensions are `14px x 14px` (set via `.theme-toggle svg`
in `components.css`, line 465).

The responsive breakpoint at `@media (max-width: 640px)` (lines 504-514 of
`components.css`) sets `flex-wrap: wrap` on `.topbar` and `.topbar .meta`,
already allowing wrapping. The problem is that the string `github ↗` is wide
enough to push the controls onto a second line before wrapping is needed for the
icon-sized replacement.

There is one test file, `internal/ui/chrome_test.go`, which asserts that full
pages contain the string `class="theme-toggle"` and `aria-label="Toggle theme"`.
No test currently asserts the presence of the GitHub link or its label.

## Proposed solution

**Single-file change:** edit `internal/ui/chrome.go`, replacing the one line in
the `ui_topbar` template define that produces the GitHub link. No other files
need to change.

### Replacement HTML

```html
<a href="https://github.com/mctlhq/mctl-telegram" target="_blank" rel="noopener"
   aria-label="GitHub" title="GitHub" class="gh-link">
  <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
             0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
             -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
             .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
             -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.65 7.65 0 0 1 2-.27
             c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12
             .51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48
             0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8
             c0-4.42-3.58-8-8-8z"/>
  </svg>
</a>
```

Key properties of this replacement:

1. **`fill="currentColor"`** — the SVG inherits its color from the anchor's
   computed color, which is `var(--text-dim)` at rest and `var(--text)` on
   hover, matching every other `.topbar a` link. No new CSS rules are needed.

2. **`aria-label="GitHub"` and `title="GitHub"` on the `<a>`** — since no
   visible text is present, these attributes provide the accessible name for
   keyboard users and screen readers, and a native tooltip on pointer hover.

3. **`aria-hidden="true"` on the SVG** — prevents screen readers from
   attempting to parse the SVG path as content, since the link's accessible
   name already comes from `aria-label`.

4. **`width="16" height="16"`** — the GitHub mark is a filled (not stroked)
   icon; 16 px is a common baseline for the GitHub Invertocat. The adjacent
   `theme-toggle` SVGs render at 14 px but are stroke-based and visually feel
   similar in weight. 16 px for a solid fill mark achieves optical equivalence.
   If visual review shows a mismatch, the implementer may use `width="14"
   height="14"` without any other change.

5. **`class="gh-link"`** — added to allow future CSS targeting without
   modifying the structural selector `.topbar a`. No CSS rule for `.gh-link` is
   required today; the existing `.topbar a` rules apply.

6. **No CSS changes required.** The `.topbar a` hover/active rules already
   handle color. The icon's intrinsic size is set directly in the SVG attributes
   so no `.gh-link svg` rule is needed. The existing responsive wrapping rules
   in `components.css` continue to apply unchanged.

### Test update

`chrome_test.go` should gain one additional assertion in `TestFullChrome`:

```go
`aria-label="GitHub"`,
```

This is the minimum assertion that covers the accessibility requirement without
over-specifying the SVG path data.

## Alternatives

### Alternative A: CSS background-image with a data URI SVG

Replace the anchor's text with an empty span and set the GitHub icon as a
`background-image` using a data URI. Rejected because:
- `currentColor` is not supported inside `background-image` data URIs; the SVG
  color would have to be hard-coded, breaking light/dark theming.
- Adds CSS rules to `components.css` for a single element.
- Departs from the pattern used by `theme-toggle` (inline SVG in HTML).

### Alternative B: External `<img src="/github-icon.svg">`

Serve the icon as a static asset via `net/http`. Rejected because:
- Requires a new static file, a new embed directive, and a new HTTP handler or
  file-server route.
- The strict-CSP `ui_head_lite` pages explicitly forbid external resource loads;
  adding a file-server route would need careful CSP exemption analysis even
  though the top nav is not present on lite pages.
- Disproportionate complexity for a single icon.

### Alternative C: Unicode symbol (e.g., a cat or code-branch glyph)

Use a Unicode character or an icon font glyph. Rejected because:
- Icon-font glyphs require an external font file or a font-face embed,
  increasing page weight and CSP surface.
- Unicode has no standard GitHub logo character; any symbol would be ambiguous.

## Platform impact

- **Migrations:** none. This is a pure template-string change in Go source.
- **Backward compatibility:** no API contract, JSON schema, or database schema is
  touched. The rendered HTML changes only cosmetically.
- **Resource impact:** the inline SVG path (~300 bytes of ASCII) is negligible
  relative to the embedded CSS already inlined into every full page.
- **Risk:** very low. The change is confined to one line in one template define
  in one `.go` file. The existing `chrome_test.go` test suite will catch any
  template parse error immediately. No runtime behaviour changes.
- **Rollback:** revert the single line in `internal/ui/chrome.go` to restore
  `github ↗`. No migration, no asset deletion, no config change required.
