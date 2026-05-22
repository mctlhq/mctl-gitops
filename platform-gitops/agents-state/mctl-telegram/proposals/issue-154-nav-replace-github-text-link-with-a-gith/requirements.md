# Nav: replace GitHub text link with inline SVG icon

## Context

The top navigation bar rendered by the `ui_topbar` template in
`internal/ui/chrome.go` contains five links (home, docs, security, privacy,
github), an accent-color picker, and a theme-toggle button. The last nav link
currently reads `github ↗` as plain text. On narrow mobile viewports that text,
combined with the rest of the controls, causes the nav row to wrap onto a second
line, degrading the layout.

Replacing the `github ↗` text label with a compact inline SVG GitHub mark
removes the widest variable-width word from the row. Because the icon is roughly
as wide as the existing `theme-toggle` button (28 px), the full nav bar fits on
one line on typical mobile viewports. This is a purely presentational change:
the link target, keyboard accessibility, and screen-reader label are all
preserved.

## User stories

- AS a mobile visitor I WANT the top navigation bar to stay on a single line
  SO THAT the page header does not take up extra vertical space.
- AS a keyboard or screen-reader user I WANT the GitHub link to have a
  descriptive label SO THAT I can identify and activate it without visible text.
- AS a developer I WANT the GitHub icon to use `currentColor` SO THAT it
  automatically adjusts when the user switches between light and dark themes or
  changes the accent color.

## Acceptance criteria (EARS)

- WHEN the page is rendered at any viewport width THE SYSTEM SHALL include an
  anchor element pointing to `https://github.com/mctlhq/mctl-telegram` with
  `target="_blank"` and `rel="noopener"`.
- WHEN the GitHub link is rendered THE SYSTEM SHALL display an inline SVG
  GitHub mark (the Invertocat/octocat outline) instead of the text `github ↗`.
- WHEN the GitHub link SVG is rendered THE SYSTEM SHALL set `aria-hidden="true"`
  on the SVG element and provide `aria-label="GitHub"` and `title="GitHub"` on
  the enclosing anchor element.
- WHEN the active theme changes (light/dark) THE SYSTEM SHALL render the GitHub
  icon in `currentColor` so it inherits the link color from `.topbar a` without
  any additional CSS rules.
- WHILE the page is displayed on a viewport no wider than 640 px THE SYSTEM
  SHALL render the complete top navigation (brand, all nav links including the
  GitHub icon, accent picker, theme toggle) on a single line, or at most two
  lines where the brand wraps independently from the controls row, consistent
  with the existing responsive layout.
- WHEN a user navigates to the GitHub link via keyboard THE SYSTEM SHALL make
  the link focusable and activatable in the same manner as the other nav links.
- IF the SVG icon is sized in the template THE SYSTEM SHALL use dimensions
  consistent with the neighbouring `theme-toggle` SVG icons (14 px x 14 px
  stroke-based or equivalent fill-based mark).

## Out of scope

- Changes to the footer "source" link in the `ui_footer` template — the issue
  explicitly states that link remains as text.
- Changes to the `ui_topbar_lite` / `topbarLiteHTML` constant used by
  strict-CSP OAuth-flow pages — those pages do not include the GitHub link.
- Any changes to the accent-color picker or theme-toggle controls.
- Hosting or caching the SVG as a separate asset file; the icon stays inline in
  the Go source template, consistent with how `theme-toggle` icons are authored.
- Responsive CSS changes beyond what is required to keep the single-line
  constraint — the existing `@media (max-width: 640px)` rules in
  `assets/components.css` already permit wrapping and may need no modification.

## Open questions

- None. The issue is fully specified: inline SVG, `currentColor`, `aria-label`,
  `title`, link attributes, and the affected template are all identified.
