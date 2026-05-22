# Rename Storybook brand title to 'MCTL UI'

## Context

The Storybook instance served at `ui.mctl.ai` displays a sidebar brand title
sourced from the `brandTitle` field of the Storybook theme created in
`apps/storybook/.storybook/mctl-theme.ts`. That value currently reads `'MCTL
Design System'`. The issue asks for it to be shortened to `'MCTL UI'` to
match how the project is referred to in other contexts.

This is a pure text-edit change confined to a single file. No visual layout,
color tokens, URLs, or other metadata are affected.

## User stories

- AS a developer browsing the Storybook sidebar I WANT to see the brand title
  read 'MCTL UI' SO THAT the label is consistent with how the design system is
  named elsewhere.
- AS a maintainer deploying a new Storybook build I WANT the brand title change
  to be the only observable difference SO THAT unrelated styling is not
  accidentally disturbed.

## Acceptance criteria (EARS)

- WHEN Storybook is opened in any supported browser THE SYSTEM SHALL display
  'MCTL UI' as the sidebar brand title for both the dark and light themes.
- WHEN `pnpm build:storybook` is executed THE SYSTEM SHALL complete without
  errors or warnings attributable to the edited file.
- WHILE the Storybook chrome is rendered THE SYSTEM SHALL leave `brandUrl`,
  `brandImage`, `brandTarget`, and all color tokens in `mctl-theme.ts`
  unchanged.
- IF `mctl-theme.ts` is inspected after the change THEN THE SYSTEM SHALL
  contain no occurrence of the string `'MCTL Design System'` in any
  `brandTitle` assignment.

## Out of scope

- Renaming the `<title>` or Open Graph `og:title` tags in
  `apps/storybook/.storybook/main.ts` (those read `MCTL Design System` today
  but are not mentioned in the issue).
- Updating the `<h1>MCTL Design System</h1>` heading in
  `apps/storybook/stories/Introduction.stories.ts`.
- Any change to package names, published npm identifiers, or `CLAUDE.md`.

## Open questions

1. **Sibling occurrences in `main.ts` and `Introduction.stories.ts`.**
   Two other files contain the string `MCTL Design System`:
   `apps/storybook/.storybook/main.ts` (`<title>` and `og:title`) and
   `apps/storybook/stories/Introduction.stories.ts` (`<h1>` heading). The
   issue only scopes the change to `mctl-theme.ts`; this proposal follows that
   scope. A reviewer should confirm whether those strings should be updated in
   a follow-up issue or bundled here.

   **Working assumption:** treat them as out of scope; proceed with the
   minimal `mctl-theme.ts` edit only.
