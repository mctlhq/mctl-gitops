# Design: issue-160-test-human-input-pick-the-default-code-b

## Current state
- `package.json`: VitePress `^1.6.0`; `bun.lock` resolves Shiki `2.5.0` (with `@shikijs/themes@2.5.0`, which bundles `github-light` and `github-dark`). Build is `bun run test && bun run generate:llms && vitepress build docs`.
- `docs/.vitepress/config.ts`:
  - `appearance: 'force-dark'` (line 8) - the site renders only in dark mode, no toggle.
  - `markdown: { config(md) { ... } }` (around line 135) overrides `md.renderer.rules.fence` so `mermaid` fences become `<div class="mermaid-diagram" data-mermaid=...>`; all other fences fall through to `defaultFence` (VitePress/Shiki highlighting).
  - No `markdown.theme` key is set, so VitePress uses its implicit default, which in 1.x is `{ light: 'github-light', dark: 'github-dark' }`. The requested pair is therefore already what renders, but only by accident of the framework default.
- `docs/.vitepress/theme/vitepress-bridge.css` (lines 57-60) and `custom.css` (lines 30-32) set `--vp-code-bg`, `--vp-code-block-bg`, `--vp-code-color` and the divider colour to MCTL design tokens (`--surface-card`, `--syntax-string`, ...). These control block background and inline-code colour, not per-token Shiki colours. `custom.css` line 585 styles `div[class*='language-']` containers.
- `docs/.vitepress/theme/index.ts` imports `vitepress/theme-without-fonts`, the two CSS files, and the Mermaid renderer; nothing there touches Shiki.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-docs/values.yaml` (read via `/workdir/mctl-gitops/platform-gitops/services/*/mctl-docs/values.yaml`): service `mctl-docs`, team `admins`, chart `base-service`, image `ghcr.io/mctlhq/mctl-docs` tag `0.1.53` (matches `package.json` version), nginx-unprivileged on containerPort 8080. Static site; no runtime config relates to syntax highlighting.
- mctl MCP tools were not called; the gitops values file was sufficient, and the change is build-time only.

## Proposed solution
Add an explicit `theme` to the existing `markdown` block in `docs/.vitepress/config.ts`:

```ts
markdown: {
  theme: {
    light: 'github-light',
    dark: 'github-dark',
  },
  config(md) { /* existing mermaid fence override, unchanged */ },
},
```

Rationale:
- It is the author's choice (github-light / github-dark) stated in config, not inherited from a framework default.
- Rendered output today should be byte-for-byte the same as the current build (same themes), so the change carries almost no visual risk; its value is pinning.
- Both halves are set even though `appearance: 'force-dark'` means only github-dark is visible, so re-enabling light mode later needs no code-theme change.
- A short comment above `theme` should reference issue #160 as the source of the decision.

No changes to CSS: the bridge/custom CSS sets the block background to `--surface-card`, which github-dark tokens read well on (the current production state already shows this combination).

## Alternatives
1. **Leave config unchanged (rely on the VitePress default).** Visually identical today, but the decision stays invisible and any upstream default change would land silently on the next VitePress bump. Dropped: the issue asks for an explicit default.
2. **one-light / one-dark-pro.** Closer to MCTL design tokens and higher contrast, but explicitly not chosen by the author (clarification answer hir-d6dac56542bddcdf). Dropped.
3. **A custom Shiki theme built from MCTL `--syntax-*` tokens.** Best brand alignment, but substantially more work, needs theme JSON maintenance and was not one of the offered options. Dropped.

## Platform impact
- Migrations: none. Build-time config only; no new dependencies (themes are bundled in `@shikijs/themes@2.5.0`).
- Backward compatibility: generated HTML should match the current build because the configured themes equal the implicit default.
- Resources: none; static nginx image size unchanged.
- Deployment: normal release flow (release-please tag, CI image build, gitops tag bump in `services/admins/mctl-docs/values.yaml`).
- Risks: a typo in a theme name breaks the build (caught in CI, never shipped). Mitigation: build locally and diff `docs/.vitepress/dist` against a pre-change build.
- Note: the issue is a test issue marked "Do not implement"; the reviewer should confirm before an implementer picks it up.
