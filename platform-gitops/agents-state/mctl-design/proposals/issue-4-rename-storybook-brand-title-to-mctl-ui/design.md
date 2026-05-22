# Design: issue-4-rename-storybook-brand-title-to-mctl-ui

## Current state

`apps/storybook/.storybook/mctl-theme.ts` exports two Storybook theme objects,
`mctlDark` and `mctlLight`, both created with `storybook/theming`'s `create()`
helper.

Rather than duplicating brand fields, the file declares a single shared
constant:

```ts
// apps/storybook/.storybook/mctl-theme.ts  (lines 7-11)
const brand = {
  brandTitle: 'MCTL Design System',
  brandUrl: 'https://ui.mctl.ai',
  brandTarget: '_self',
};
```

Both theme exports spread this object:

```ts
export const mctlDark  = create({ base: 'dark',  ...brand, brandImage: '/mctl-logo-light.svg', ... });
export const mctlLight = create({ base: 'light', ...brand, brandImage: '/mctl-logo-dark.svg',  ... });
```

`mctlDark` is applied in `manager.ts` as the initial chrome theme, and both
themes are passed to the `@vueless/storybook-dark-mode` addon parameters in
`preview.ts`. Neither of those files reference `brandTitle` directly.

Two other files in the repository also contain the string `MCTL Design System`
but are not part of this change:

- `apps/storybook/.storybook/main.ts` — `<title>` tag and `og:title` meta
  in `managerHead` (lines 16-17).
- `apps/storybook/stories/Introduction.stories.ts` — an `<h1>` heading in
  the Introduction story template (line 15).

## Proposed solution

Edit the single `brandTitle` field inside the `brand` constant in
`apps/storybook/.storybook/mctl-theme.ts`:

```diff
-  brandTitle: 'MCTL Design System',
+  brandTitle: 'MCTL UI',
```

Because both `mctlDark` and `mctlLight` spread `brand`, this one-line change
propagates to both themes automatically. No other file requires modification to
satisfy the issue's acceptance criteria.

The change is a pure string substitution; no imports, exports, types, or
runtime logic are touched.

## Alternatives

**A. Edit `brandTitle` separately in each `create()` call**
The issue body speculated there might be two separate `brandTitle` entries to
update (one per theme). Inspection of the file reveals the value is factored
into the shared `brand` constant, so this alternative is unnecessary and would
increase the diff surface without benefit. Rejected.

**B. Also update `<title>` and `og:title` in `main.ts`**
The `managerHead` in `main.ts` contains the same `MCTL Design System` string.
Updating it alongside `mctl-theme.ts` would produce a more consistent page
title and social-share card. However, the issue explicitly scopes the change to
`mctl-theme.ts` and the `brandTitle` field. Including `main.ts` in this PR
exceeds that scope and should be a separate decision. Rejected for this
proposal; captured as an open question in `requirements.md`.

**C. Extract the brand title to a shared constant in a tokens/config package**
Moving `'MCTL UI'` to a workspace-level constant would prevent future drift
between `mctl-theme.ts` and `main.ts`. This is a valid long-term improvement
but is disproportionate to a one-word rename and introduces a cross-package
dependency purely for a display string. Rejected for this proposal.

## Platform impact

- **Backward compatibility:** `brandTitle` is a Storybook UI label only; it
  has no effect on published package APIs, component names, or CSS class names.
  No consumer migration is required.
- **Build:** The change does not alter the TypeScript type surface.
  `pnpm build:storybook` should complete without errors.
- **CI:** The `ci.yml` workflow runs `build:storybook`; the change must not
  break that step.
- **Docker / deploy:** The Docker image is built from the static Storybook
  output by `mctl-gitops`. The label change will appear in the next image
  build; no pipeline changes are needed.
- **Risk:** Negligible. A single string literal in a non-compiled theme file
  is changed. The worst failure mode is a Storybook build error, which is
  caught by CI before merge.
