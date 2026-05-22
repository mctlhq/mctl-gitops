# Align Storybook page title and og:title with MCTL UI

## Context

Pull request #4 updated the Storybook sidebar brand title to `MCTL UI` by
setting `brandTitle: 'MCTL UI'` in `apps/storybook/.storybook/mctl-theme.ts`.
However, the `managerHead` injection in `apps/storybook/.storybook/main.ts`
still injects `<title>MCTL Design System</title>` and
`<meta property="og:title" content="MCTL Design System">`. This creates a
visible inconsistency: the browser tab and any social-share previews show the
old name while the sidebar shows the new one.

This issue asks for a pure text substitution inside `main.ts` to bring the
page title and Open Graph title tag into alignment with the already-updated
`brandTitle`. No structural changes, no new files, and no changes to any other
file are required.

## User stories

- AS a developer browsing the Storybook site I WANT the browser-tab title to
  read "MCTL UI" SO THAT the tab label matches what I see in the sidebar.
- AS a team member sharing a link to `ui.mctl.ai` I WANT the og:title social
  card to display "MCTL UI" SO THAT the shared link preview is consistent with
  the product name.

## Acceptance criteria (EARS)

- WHEN the Storybook manager page is loaded THE SYSTEM SHALL render a
  `<title>` element whose text content is exactly `MCTL UI`.
- WHEN the Storybook manager page is loaded THE SYSTEM SHALL render a
  `<meta property="og:title">` tag whose `content` attribute is exactly
  `MCTL UI`.
- WHILE `apps/storybook/.storybook/main.ts` exists THE SYSTEM SHALL contain
  no occurrence of the string `MCTL Design System`.
- WHEN `pnpm build:storybook` is executed THE SYSTEM SHALL complete without
  errors.
- WHILE the change is applied THE SYSTEM SHALL leave every field other than
  the two listed above in `main.ts` unchanged.
- IF any other file in the repository currently contains `MCTL Design System`
  THEN THE SYSTEM SHALL leave that file unchanged (changes to other files are
  out of scope).

## Out of scope

- Renaming or updating `<h1>MCTL Design System</h1>` in
  `apps/storybook/stories/Introduction.stories.ts` — the issue acceptance
  criteria explicitly limits changes to `main.ts`.
- Changing `og:description`, `og:url`, `og:image`, or any other meta tag.
- Modifying `mctl-theme.ts`, `manager.ts`, `preview.ts`, or any package
  outside `apps/storybook`.
- Version bumps, changelog updates, or publish workflows.

## Open questions

None. The issue is fully specified: two string substitutions in one file,
with explicit acceptance criteria and an explicit "no other file changes"
constraint.
