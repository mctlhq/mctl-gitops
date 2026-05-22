# Design: issue-6-align-storybook-page-title-og-title-with

## Current state

Storybook's manager (chrome) page head is customised via the `managerHead`
hook in `apps/storybook/.storybook/main.ts`. The hook receives the existing
`<head>` fragment and returns an augmented string. As of the current clone,
lines 14-29 of that file read:

```ts
managerHead: (head) =>
  `${head}
  <title>MCTL Design System</title>
  <meta property="og:title" content="MCTL Design System">
  <meta property="og:description" content="Design tokens, CSS theme, and Vue 3 components for MCTL products.">
  <meta property="og:url" content="https://ui.mctl.ai">
  <meta property="og:image" content="https://ui.mctl.ai/mctl-logo-light.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    /* Hide "Storybook X.Y.Z" version badge in sidebar footer */
    [class*='sidebar_footer'] a[href*='storybook.js.org'],
    [class*='sidebar_footer'] > div:last-child { display: none !important; }
    body, button, input { font-family: 'JetBrains Mono', ui-monospace, monospace !important; }
  </style>`,
```

The sidebar brand title is set independently in
`apps/storybook/.storybook/mctl-theme.ts` (line 8):

```ts
brandTitle: 'MCTL UI',
```

That value was updated in PR #4. The `managerHead` title strings were not
updated at the same time, leaving a mismatch.

A third occurrence of `MCTL Design System` exists in
`apps/storybook/stories/Introduction.stories.ts` (line 15) as an `<h1>` in
the rendered story body. That occurrence is intentionally left unchanged per
the issue's acceptance criteria.

## Proposed solution

Edit exactly two string literals inside the `managerHead` template in
`apps/storybook/.storybook/main.ts`:

1. Line 16: change `<title>MCTL Design System</title>` to
   `<title>MCTL UI</title>`.
2. Line 17: change `content="MCTL Design System"` to `content="MCTL UI"` in
   the `og:title` meta tag.

No other characters in the file are touched. The change is a direct
string-substitution — no refactoring, no new abstractions, no import changes.

This approach is correct because `managerHead` is the canonical Storybook API
for injecting custom HTML into the manager page's `<head>`. The `brandTitle`
in `mctl-theme.ts` controls only the sidebar label; it does not propagate to
the `<title>` element or Open Graph tags. The two surfaces are independently
configured and must be independently updated.

## Alternatives

**A. Derive the title from `brandTitle` at build time.**
One could import the `brand` object (or the `brandTitle` constant) from
`mctl-theme.ts` into `main.ts` and interpolate it into both tags, eliminating
the duplication. This would prevent future drift. However, the issue explicitly
says "no other field or file changes," the `brandTitle` value is a short
literal that is unlikely to change again soon, and adding a build-time import
introduces unnecessary coupling between the two files. Deferred.

**B. Move the title injection into a Storybook `manager-head.html` static
file.**
Storybook also supports a `manager-head.html` file as an alternative to the
`managerHead` hook. Migrating the tags to a static file would be a
refactoring change unrelated to the issue and would alter the project's
established pattern. Out of scope.

**C. Update all three occurrences of `MCTL Design System` across the repo.**
The occurrence in `Introduction.stories.ts` is visible story prose, not a
branding identifier in the same sense. The issue acceptance criteria explicitly
excludes changes outside `main.ts`. Updating the story is a separate
editorial decision. Out of scope.

## Platform impact

- **Migrations:** None. The change is a pure text edit with no API surface,
  no exported symbols, and no schema changes.
- **Backward compatibility:** Not applicable. The `managerHead` output is an
  HTML string consumed at build time by Storybook; no downstream packages
  depend on it.
- **Resource impact:** None. Two string literals are shorter; the byte delta
  is negligible.
- **Risks:** Essentially zero. The only risk is a typo introducing malformed
  HTML; this is mitigated by the `pnpm build:storybook` acceptance gate, which
  would surface any parse error.
- **Rollback:** Revert the two string literals to `MCTL Design System`. A
  single-commit revert suffices.
