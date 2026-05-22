# Design: issue-3-change-the-storybook-overview-brand-icon

## Current state

All Storybook brand imagery lives in three SVG files under
`apps/storybook/public/`:

| File | Dimensions | Usage |
|------|-----------|-------|
| `mctl-logo-light.svg` | 98 x 32 px | Sidebar brand image in **dark** mode |
| `mctl-logo-dark.svg` | 98 x 32 px | Sidebar brand image in **light** mode |
| `favicon.svg` | 32 x 32 px | Browser-tab favicon served at `/favicon.svg` |

These files are served as static assets because `apps/storybook/.storybook/main.ts`
declares `staticDirs: ['../public']`, which copies everything in `public/` to
the root of the Storybook static build output (`storybook-static/`).

The Storybook manager theme is defined in
`apps/storybook/.storybook/mctl-theme.ts`. It exports two `create()`-based
theme objects:

```
mctlDark  — brandImage: '/mctl-logo-light.svg'
mctlLight — brandImage: '/mctl-logo-dark.svg'
```

`mctlDark` is applied at startup in `manager.ts` (preventing a default-theme
flash), and both themes are passed to the `@vueless/storybook-dark-mode` addon
in `preview.ts` so that toggling light/dark mode swaps the brand image
automatically.

The current SVG mark in all three files is a geometric nested-square motif:
an outer rounded-corner rectangle stroke plus a centred filled rectangle,
rendered in cyan (`#00e5ff` for dark-mode assets, `#00b8cc` for light-mode
assets). The two wide logo files append the wordmark "MCTL" as SVG `<text>`.

There is no `<link rel="icon">` tag in the `managerHead` injection in
`main.ts`; the browser resolves the favicon via the standard `/favicon.svg`
file at the static root.

## Proposed solution

Replace the three SVG files in `apps/storybook/public/` with new artwork
reflecting the current mctl icon. No configuration files change; the filename
convention and the `brandImage` paths in `mctl-theme.ts` remain identical.

**File replacements:**

1. `apps/storybook/public/mctl-logo-light.svg`
   New content: updated icon mark + "MCTL" wordmark, foreground in light
   colours suitable for a dark chrome (e.g. white/cyan foreground, transparent
   background). Keep the 98 x 32 px canvas and `viewBox="0 0 98 32"` so
   Storybook's sidebar layout is undisturbed.

2. `apps/storybook/public/mctl-logo-dark.svg`
   Same geometry, foreground in dark colours suitable for a light chrome
   (e.g. near-black / dark-teal foreground, transparent background).
   Same 98 x 32 px canvas.

3. `apps/storybook/public/favicon.svg`
   Square icon-only mark at 32 x 32 px (no wordmark). Should be visually
   coherent as a small tab icon. If the new icon is transparent-background,
   embed a `prefers-color-scheme` media query inside the SVG so it reads
   cleanly in both OS light and dark modes.

**Optional hardening (conditional on testing):**

If the rebuilt Storybook does not display the favicon correctly in all tested
browsers, add an explicit link tag to the `managerHead` string in
`apps/storybook/.storybook/main.ts`:

```
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
```

This is the only code change outside the `public/` directory; it is a
one-line addition and carries no risk.

**Why this approach is correct:**

- The `brandImage` field in Storybook's `create()` theming API accepts any
  URL resolvable from the static root. The current setup already uses
  named paths (`/mctl-logo-light.svg`, `/mctl-logo-dark.svg`), so
  replacing the files on disk is sufficient — no import paths or config keys
  need updating.
- Storybook rebuilds are deterministic: the static-output directory is
  recreated from scratch on every `pnpm build:storybook` run, so stale
  artefacts cannot linger.
- The favicon is served by the same nginx image (see `nginx.conf`) that serves
  all static assets; no server configuration changes are required.

## Alternatives

### A. Inline the new icon as a `data:` URI in `mctl-theme.ts`

`brandImage` accepts a Base64 `data:image/svg+xml` URI. This avoids adding
files to `public/` but makes `mctl-theme.ts` unreadable, bloats the manager
bundle with repeated icon data, and breaks the pattern already established
in the repo. Rejected.

### B. Use a PNG or ICO for the favicon

PNG/ICO files are universally supported but larger, non-scalable, and harder
to theme with `prefers-color-scheme`. SVG favicons are supported by all modern
browsers and match the existing `favicon.svg` convention. Rejected — the repo
already commits to SVG-only assets.

### C. Add a new filename (`mctl-icon-v2.svg`) and update `mctl-theme.ts`

Keeping the old files alongside new ones and updating theme references would
prevent any ambiguity about which file is "current." However, it leaves dead
files in the tree and requires a code change in addition to the asset swap.
The simpler path is to replace files in place, which is idiomatic for asset
refreshes. Rejected.

## Platform impact

- **Migrations / backward compatibility:** None. The brand images appear only
  inside the Storybook manager chrome; they are not exported from any package
  and have no consumers outside `apps/storybook`.
- **Resource impact:** SVG files are typically 0.5–2 KB each; the delta on
  static build size is negligible.
- **CI:** No CI changes required. The existing `build:storybook` step in
  `ci.yml` will automatically include the updated SVGs.
- **Risks:** The only regression risk is a malformed SVG that fails to render.
  Mitigation: validate each SVG in a browser before committing (see Tasks).
- **Docker image:** The static build is consumed by `mctl-gitops` to build the
  nginx image; no Dockerfile changes are needed.
