# Design: issue-160-test-human-input-pick-the-default-code-b

## Current state
- `docs/.vitepress/config.ts` (`defineConfig`) sets `appearance: 'force-dark'`
  (line 8) and a `markdown` block (lines 135-153) containing only a
  `config(md)` hook that overrides `md.renderer.rules.fence` to turn
  ```mermaid fences into `<div class="mermaid-diagram" data-mermaid=...>` and
  delegates every other fence to the default renderer (Shiki). There is no
  `markdown.theme` key.
- `bun.lock` pins `vitepress@1.6.4` with `shiki@2.5.0`. With no
  `markdown.theme`, VitePress 1.6 uses `{ light: 'github-light', dark:
  'github-dark' }`. Both candidate pairs (`github-*`, `one-light`,
  `one-dark-pro`) are bundled Shiki 2.x themes, so no new dependency is needed.
- `docs/.vitepress/theme/index.ts` extends `vitepress/theme-without-fonts`.
- `docs/.vitepress/theme/custom.css` sets `--vp-code-bg`, `--vp-code-color`
  and `--vp-code-block-bg` to MCTL surface tokens (lines 30-32) and styles
  `div[class*='language-']` with an accent border (lines 585-588). Token
  colours come from Shiki's dual-theme CSS variables (`--shiki-light` /
  `--shiki-dark`); block background comes from `--vp-code-block-bg`.
- `package.json` `build` = `bun run test && bun run generate:llms && vitepress build docs`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-docs/values.yaml`: tenant `admins`,
  image `ghcr.io/mctlhq/mctl-docs:0.1.53` (matches `package.json` version
  0.1.53), nginx on containerPort 8080, hosts `docs.mctl.ai` and
  `admins-mctl-docs.mctl.ai`. Static site; no runtime config affects code
  highlighting, which is decided at build time.
- mctl MCP tools were not called; the gitops checkout was sufficient for this
  build-time-only change.

## Proposed solution
Add an explicit theme pair to the existing `markdown` object in
`docs/.vitepress/config.ts`, next to `config(md)`:

```ts
markdown: {
  theme: { light: 'github-light', dark: 'github-dark' },
  config(md) { /* unchanged mermaid fence override */ },
},
```

If the requester picks option 2, the values are `{ light: 'one-light',
dark: 'one-dark-pro' }` instead. Nothing else changes. Pinning the pair
explicitly (even when it equals the default) records the decision in config
and protects against default changes in future VitePress upgrades.

Fallback until the clarification is answered: option 1 (`github-*`), because
it is byte-for-byte the current rendering and so is the zero-risk default.

## Alternatives
- Leave config untouched and rely on the VitePress default: gives option 1
  implicitly, but the decision is invisible and an upgrade can change it.
  Dropped.
- Single theme string (`theme: 'one-dark-pro'`): matches today's
  force-dark-only site, but the issue explicitly asks for both light and
  dark. Dropped.
- Custom theme / CSS token remapping of Shiki colours to MCTL design tokens:
  most on-brand, but well beyond a "pick one of two" request and costly to
  maintain. Dropped (out of scope).

## Platform impact
- No migration, no new dependencies, no deployment change; ships with the
  next tag (`MAJOR.MINOR.PATCH`) via existing CI/CD and GitOps image bump.
- Option 1: no visual change. Option 2: token colours in every code block
  change; block background stays `--vp-code-block-bg`.
- Risk: a misspelled theme name fails the VitePress build. Mitigation: the
  build is part of CI and of tests below.
- Risk: the mermaid fence override is accidentally removed while editing the
  `markdown` object. Mitigation: keep `config(md)` unchanged and verify a
  mermaid page still renders.
