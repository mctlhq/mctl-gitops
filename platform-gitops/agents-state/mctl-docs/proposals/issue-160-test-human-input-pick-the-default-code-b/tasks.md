# Tasks: issue-160-test-human-input-pick-the-default-code-b

- [ ] 1. Add `theme: { light: 'github-light', dark: 'github-dark' }` to the `markdown` object in `docs/.vitepress/config.ts`, above the existing `config(md)` mermaid fence override, with a one-line comment referencing mctlhq/mctl-docs#160 — DoD: config type-checks; `config(md)` body unchanged.
- [ ] 2. Run `bun run build` (depends on 1) — DoD: tests, `generate:llms` and `vitepress build docs` succeed with no Shiki theme warnings.
- [ ] 3. Compare a rendered page with code blocks (e.g. a page under `docs/guides/`) against a build of `main` (depends on 2) — DoD: code blocks carry github-dark colours in `--shiki-dark` and github-light in `--shiki-light`; no visual change expected versus `main`.
- [ ] 4. Open a PR from a feature branch; release via the normal release-please tag flow — DoD: PR merged, image built, gitops tag bumped.

## Tests
- [ ] T1. `bun run build` passes (includes `bun test ./docs/.vitepress/theme/mermaid-links.test.ts`).
- [ ] T2. In `docs/.vitepress/dist`, grep a built HTML page with a fenced `ts`/`yaml` block: spans contain `--shiki-dark:` values from github-dark (e.g. `#F97583` for keywords) and `--shiki-light:` values from github-light (e.g. `#D73A49`).
- [ ] T3. A page containing a `mermaid` fence still renders a `.mermaid-diagram` element and the diagram draws in `bun run preview`.
- [ ] T4. Visual check in `bun run preview`: code blocks readable on the `--surface-card` background in forced dark mode.

## Rollback
Revert the commit that adds `markdown.theme` and release a new patch tag (or roll the gitops image tag in `services/admins/mctl-docs/values.yaml` back to the previous version). Because the removed setting equals the VitePress implicit default, rollback has no visible effect on rendering.
