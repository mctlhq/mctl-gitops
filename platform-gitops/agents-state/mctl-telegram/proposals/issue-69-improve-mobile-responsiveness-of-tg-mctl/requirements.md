# Improve Mobile Responsiveness of tg.mctl.ai Landing Page

## Context

The landing page served at tg.mctl.ai is generated from `internal/web/landing.html`, a
single-file embedded HTML template with all CSS inlined in two `<style>` blocks. The page
explains how to connect mctl-telegram to Claude.ai and contains setup instructions, reference
tables for tools and scopes, data-storage disclosures, and a smoke-test code block. At
present the page has one responsive breakpoint at 640px which reduces padding and font sizes
but does not address table overflow, code-block overflow, dense step-list layout on the
narrowest phones, or undersized touch targets on interactive controls.

Mobile users encountering this page on a 375-480px viewport will see tables overflow the
viewport, `pre` code blocks clip wide curl commands, and the theme-toggle button present a
sub-standard 28x28px tap target. Adding breakpoints at 768px and 480px, fixing `overflow`
on table and code-block containers, and growing interactive hit areas to 44x44px will make
the page usable on the handset viewports most commonly used to follow setup instructions.

## User stories

- AS a developer following the connector setup on a mobile phone I WANT the step-by-step
  instructions to be readable on a 375px viewport SO THAT I can complete the Claude.ai
  setup without zooming or horizontal scrolling.
- AS a mobile user consulting the tools reference table I WANT the table to scroll
  horizontally within its container SO THAT the page body does not overflow and all
  columns remain accessible.
- AS a mobile user I WANT `pre` code blocks containing long curl commands to scroll
  horizontally SO THAT no command text is silently clipped.
- AS a touch-screen user I WANT the theme-toggle button and accent-color swatches to have
  a tap target of at least 44x44 CSS pixels SO THAT I can interact with them without
  mis-tapping on a small screen.
- AS a user on a slow or restricted mobile network I WANT the page to render legibly even
  if Google Fonts or `ui.mctl.ai/mctl.css` fail to load SO THAT I can read the setup
  instructions using system fallback fonts.

## Acceptance criteria (EARS)

- WHEN the viewport width is 768px or narrower THE SYSTEM SHALL apply a dedicated CSS
  breakpoint that adjusts `.wrap` padding, hides lower-priority navigation items via a
  `.hide-md` class, and begins enlarging interactive hit areas.
- WHEN the viewport width is 480px or narrower THE SYSTEM SHALL apply a second dedicated
  CSS breakpoint that reduces heading font sizes, tightens `ol.steps` counter-chip geometry,
  and reduces `pre code` font size so the smoke-test commands fit on screen.
- WHILE a `.tbl` table is rendered on any viewport THE SYSTEM SHALL allow horizontal
  scrolling within the table container rather than clipping content or causing page-level
  overflow (change `overflow: hidden` to `overflow-x: auto` on `.tbl`).
- WHILE a `pre` block containing wide content is rendered on any viewport THE SYSTEM SHALL
  allow horizontal scrolling within the block rather than clipping the content (change
  `overflow: hidden` to `overflow-x: auto` on `pre`).
- WHEN the viewport width is 768px or narrower THE SYSTEM SHALL ensure the `.theme-toggle`
  button has a minimum clickable area of 44x44 CSS pixels.
- WHEN the viewport width is 768px or narrower THE SYSTEM SHALL ensure each `.accent-swatch`
  button has a minimum clickable area of 44x44 CSS pixels, achieved via padding or
  `min-width`/`min-height` without necessarily changing the swatch's visual size.
- IF `https://fonts.googleapis.com` is unreachable THEN THE SYSTEM SHALL render the page
  legibly using the `system-ui, -apple-system, sans-serif` fallback already declared in
  the `--font-display` CSS custom property.
- IF `https://ui.mctl.ai/mctl.css` fails to load THEN THE SYSTEM SHALL render the page
  with correct colours and spacing using the inline CSS variable fallback block already
  present in the first `<style>` tag in `internal/web/landing.html`.
- WHILE any breakpoint is active THE SYSTEM SHALL preserve the dark/light theme toggle and
  accent-color picker behaviour defined by the existing inline JavaScript.

## Out of scope

- Changes to `internal/web/privacy.html` or `internal/web/security.html`.
- Any Go backend code changes (no changes outside `internal/web/landing.html`).
- Serving CSS as a separate file; the inline-CSS convention established in the codebase
  must be maintained.
- JavaScript-driven responsive behaviours such as accordions or card-flip animations.
- Full WCAG 2.1 AA audit beyond the touch-target and colour-contrast issues cited in the
  issue.
- Card-layout transformation of tables (horizontal scroll is the chosen approach; card
  layout is recorded as a design alternative).

## Open questions

- Should the `.accent-picker` be hidden at 768px (matching `.hide-sm` at 640px) or remain
  visible but repositioned? The issue does not specify. This proposal hides it via `.hide-md`
  at 768px for simplicity and to reduce topbar crowding; a follow-up could expose it in the
  footer on mobile.
- The issue mentions "card layout" for tables as an option. Horizontal scroll is chosen here
  (lower complexity, no markup changes beyond an overflow property). If product prefers cards,
  see the design alternatives section — it requires `data-label` attributes on every `<td>`
  and approximately 80 additional lines of CSS.
