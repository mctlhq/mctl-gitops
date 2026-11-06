# Design: issue-160-test-human-input-pick-the-default-code-b

## Current state
- The VitePress config is at `docs/.vitepress/config.ts`, not `.vitepress/config.ts` as `.claude/CLAUDE.md` says. The theme files are in `docs/.vitepress/theme/`.
- `package.json` declares `vitepress ^1.6.0`. `bun.lock` resolves `vitepress@1.6.4` with `shiki@2.5.0` / `@shikijs/themes@2.5.0`. All four candidate theme names (`github-light`, `github-dark`, `one-light`, `one-dark-pro`) are bundled Shiki themes in that version.
- `docs/.vitepress/config.ts` sets `appearance: 'force-dark'`, so readers only ever see the dark variant.
- The `markdown` block in `config.ts` has only a `config(md)` hook. That hook wraps `md.renderer.rules.fence` so that `mermaid` fences become `<div class="mermaid-diagram">` and every other fence goes to the default (Shiki) renderer. There is no `markdown.theme` key, so VitePress uses its built-in default `{ light: 'github-light', dark: 'github-dark' }`.
- Code-block background: `--vp-code-block-bg: var(--surface-card, #15181d)` is set in `docs/.vitepress/theme/custom.css` (line ~30) and in `vitepress-bridge.css` (line ~68), together with `--vp-code-block-divider-color`. The comment in `vitepress-bridge.css` says inline-code roles leave "code blocks and Shiki highlighting untouched". So token colours come from the Shiki theme and the background comes from the MCTL tokens.
- No file in `docs/` mentions `shiki`, `github-dark` or `one-dark`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-docs/values.yaml`: tenant `admins`, image `ghcr.io/mctlhq/mctl-docs:0.1.61`, nginx-unprivileged on containerPort 8080, Service port 80, requests 50m CPU / 128Mi. This is a static site, and the theme is fixed at build time. No runtime config is involved.
- I did not call the mctl MCP tools. The gitops values file was enough for a build-time-only change.

## Proposed solution
Add an explicit theme pair to the existing `markdown` block in
`docs/.vitepress/config.ts`, next to the existing `config(md)` hook:

```ts
markdown: {
  // Default code-block theme (issue #160). Site is force-dark, so `dark` is what readers see.
  theme: { light: 'github-light', dark: 'github-dark' },
  config(md) { /* unchanged mermaid fence rule */ },
},
```

If the clarification answer is option 2, the values become
`{ light: 'one-light', dark: 'one-dark-pro' }`. Nothing else changes.
`--vp-code-block-bg` keeps overriding the theme background, so the blocks stay
on MCTL surface colours. The mermaid fence rule is untouched because it returns
before calling the default fence renderer.

Why this way: it is a one-key, first-party VitePress option. It needs no new
dependency, no CSS, and no custom theme JSON.

## Alternatives
- Leave the config implicit (rely on the VitePress default). Dropped: the issue asks for an explicit default, and a future VitePress major could change the implicit one.
- Ship a custom Shiki theme JSON built from MCTL design tokens. Dropped: the issue asks for a choice between two existing themes, and a custom theme is more to maintain.
- Override token colours in `custom.css`. Dropped: it fights Shiki's inline styles and is fragile.

## Platform impact
- No migrations and no runtime or resource change. The theme is baked into the static HTML at build time, and the image tag bumps through the normal release-please flow.
- Backward compatible. With option 1 the output looks the same as today. With option 2, token colours change on all code blocks, which is cosmetic.
- Risk: `one-dark-pro` token colours might clash with or lack contrast against the `#15181d` card background. Mitigation: check a few pages (for example `docs/getting-started/`, `docs/reference/`) in `bun run preview` before release.
- Risk: a misspelled theme name fails the build. Mitigation: `bun run build` in CI (`.github/workflows/build.yml`).
