# Proposal: Update Storybook Brand Icon and Favicon

## Context

The Storybook instance deployed at `ui.mctl.ai` displays a sidebar brand image
and a browser-tab favicon that together form the visual identity of the design
system showcase. Both assets currently use an SVG mark composed of nested
rectangles with cyan (`#00e5ff` / `#00b8cc`) strokes — the previous mctl icon
geometry. The issue requests replacing those assets with the current mctl icon
to keep the Storybook branding consistent with the live mctl visual identity.

The change is intentionally narrow: only the SVG asset files change. No
Storybook configuration, theme colour values, or story content needs to be
touched, making this the smallest possible surface for the "Stage-0 dry-pilot"
task in the autonomous pipeline.

## User stories

- AS a developer visiting ui.mctl.ai I WANT to see the current mctl icon in
  the sidebar and browser tab SO THAT the design-system showcase looks like an
  official mctl property.
- AS a designer reviewing the Storybook I WANT the brand icon to match the
  mctl visual identity SO THAT I can trust the showcase reflects production
  branding.

## Acceptance criteria (EARS)

- WHEN a user loads any page at ui.mctl.ai THEN THE SYSTEM SHALL display the
  updated mctl icon SVG in the Storybook manager sidebar (brand area, top-left).
- WHEN the Storybook is in dark mode THEN THE SYSTEM SHALL render the light
  variant of the brand image (white/cyan foreground, transparent background)
  appropriate for a dark chrome.
- WHEN the Storybook is in light mode THEN THE SYSTEM SHALL render the dark
  variant of the brand image (dark foreground, transparent background)
  appropriate for a light chrome.
- WHEN a user loads any page at ui.mctl.ai in a browser THEN THE SYSTEM SHALL
  display the updated mctl icon as the browser-tab favicon.
- WHILE the Introduction/Overview story is open THEN THE SYSTEM SHALL render
  all existing story content without regression.
- IF the Storybook build (`pnpm build:storybook`) is run after the asset
  replacement THEN THE SYSTEM SHALL complete without errors and include the
  updated SVGs in the static output.

## Out of scope

- Changing any Storybook theme colour tokens (`colorPrimary`, `appBg`, etc.)
  defined in `apps/storybook/.storybook/mctl-theme.ts`.
- Modifying any story file other than as needed to reference the new assets.
- Updating the `og:image` meta tag in `managerHead` in
  `apps/storybook/.storybook/main.ts` (the OG image is a separate concern and
  the issue does not mention social cards).
- Publishing new versions of `@mctlhq/tokens`, `@mctlhq/css`, or `@mctlhq/ui`.
- Changing the brand title text ("MCTL Design System") or brand URL.

## Open questions

1. **New icon artwork not provided.** The issue says "new mctl icon" but does
   not attach or link the replacement SVG artwork. The implementer must obtain
   the authoritative icon from the MCTL landing design spec (referenced in
   CLAUDE.md) or from a designer before beginning. The proposal assumes two
   variants are needed: a light-on-transparent variant (for dark mode) and a
   dark-on-transparent variant (for light mode), matching the current
   naming convention (`mctl-logo-light.svg` / `mctl-logo-dark.svg`).

2. **Favicon colour variant.** The current `favicon.svg` uses a single dark
   background rectangle with a cyan mark, making it self-contained for all
   contexts. If the new icon is transparent-background, a separate approach
   for dark/light OS theming (CSS `prefers-color-scheme` media query inside the
   SVG, or two separate favicons with `media` attributes) may be needed. This
   proposal adopts the simplest path: a single self-contained `favicon.svg`
   matching the current structure.

3. **Explicit favicon link tag.** The current `managerHead` in `main.ts` does
   not include a `<link rel="icon">` tag; Storybook serves `favicon.svg` from
   the static root and the browser picks it up automatically. If testing shows
   the favicon is not auto-detected after the rebuild, an explicit link should
   be added to `managerHead`. This is noted as a conditional task.
