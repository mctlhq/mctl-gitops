# Design: issue-160-test-human-input-pick-the-default-code-b

## Current state
- `docs/.vitepress/config.ts` (154 lines) is the VitePress config. It sets `appearance: 'force-dark'` (line 8) and a `markdown` block (from line 135) that only defines `config(md)`, overriding `md.renderer.rules.fence` so `mermaid` fences become `<div class="mermaid-diagram" data-mermaid="...">` and all other fences go through the default renderer. There is no `markdown.theme`, so VitePress 1.6 (`package.json`: `"vitepress": "^1.6.0"`) uses its built-in Shiki default `{ light: 'github-light', dark: 'github-dark' }`.
- `docs/.vitepress/theme/vitepress-bridge.css` maps VitePress variables to MCTL tokens loaded from `https://ui.mctl.ai/0.7.0/mctl.css`, including `--vp-code-block-bg: var(--surface-card, #15181d)` and `--vp-code-color: var(--syntax-string, #c4a35a)` (inline code). `docs/.vitepress/theme/custom.css` repeats `--vp-code-*` in `:root` and styles `div[class*='language-']` with an accent-tinted border. Block background therefore comes from MCTL tokens; token colours come from the Shiki theme.
- Build: `package.json` `build` = `bun run test && bun run generate:llms && vitepress build docs`; Docker multi-stage build to nginx.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-docs/values.yaml`: service `mctl-docs` in tenant `admins`, image `ghcr.io/mctlhq/mctl-docs` tag `0.1.53`, nginx on containerPort 8080. Static site; the theme is a build-time setting, so no deployed config is affected.
- mctl MCP tools were not called; not needed since the change is purely build-time.

## Proposed solution
Add an explicit `theme` key to the existing `markdown` object in `docs/.vitepress/config.ts`, alongside (not replacing) `config(md)`:

```ts
markdown: {
  theme: { light: 'github-light', dark: 'github-dark' }, // or one-light / one-dark-pro per requester
  config(md) { ... unchanged ... },
},
```

Both candidate pairs are bundled Shiki themes, so no dependency is added. The default assumption is option 1 pending the requester's answer (see Open questions); option 2 is the identical edit with `one-light` / `one-dark-pro`. Code-block background remains governed by `--vp-code-block-bg` in the CSS, so the site chrome is unaffected; only token colours depend on the choice. With `force-dark`, the dark theme is what readers see.

## Alternatives
- Leave config implicit (rely on VitePress default): already yields option 1 visually, but an upgrade could change it and it does not record the decision. Dropped.
- Build a custom Shiki theme from MCTL `--syntax-*` tokens: best brand fit, but outside the two options the issue offers and much larger scope. Dropped.
- Override token colours via CSS on `.shiki span`: fragile, fights Shiki's inline styles. Dropped.

## Platform impact
- No migrations, no runtime or resource impact; static build output changes only in highlighted-token colours.
- Backward compatible; option 1 produces identical output to today.
- Risk: option 2 token colours may clash with the `#15181d` block background set by the bridge CSS. Mitigation: visual check of a few pages with shell/YAML/TS blocks in `bun run dev` before merge.
- Release: normal tag `MAJOR.MINOR.PATCH` triggers CI and the GitOps image bump.

## Open questions
- Which candidate pair the requester wants (blocking; clarification filed; proceeding on option 1).
- Whether the light half matters while `appearance: 'force-dark'` stays.
- The issue is a test issue marked "Do not implement".
