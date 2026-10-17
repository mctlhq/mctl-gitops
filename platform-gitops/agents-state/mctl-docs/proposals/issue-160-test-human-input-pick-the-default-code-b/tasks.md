# Tasks: issue-160-test-human-input-pick-the-default-code-b

- [ ] 1. Read the answer to the clarification in `human-input/` (option 1:
  `github-light` / `github-dark`; option 2: `one-light` / `one-dark-pro`);
  if none, use option 1 — DoD: chosen pair recorded in the PR description.
- [ ] 2. (depends on 1) In `docs/.vitepress/config.ts`, add
  `theme: { light: '<light>', dark: '<dark>' }` to the existing `markdown`
  object, leaving `config(md)` and its mermaid fence override unchanged —
  DoD: diff touches only that one key.
- [ ] 3. (depends on 2) Run `bun run build` — DoD: test, llms generation and
  VitePress build all succeed.

## Tests
- [ ] T1. `bun run build` succeeds (fails on an unknown theme name).
- [ ] T2. In the built output (`docs/.vitepress/dist`), a page with a fenced
  code block contains `shiki` classes and inline `--shiki-dark` colour values
  matching the chosen dark theme.
- [ ] T3. `bun run dev`: a page with a ```mermaid fence still renders a
  diagram (`.mermaid-diagram`), and code blocks keep the
  `--vp-code-block-bg` background and accent border from `custom.css`.

## Rollback
Revert the single `markdown.theme` line in `docs/.vitepress/config.ts` (or
the PR) and cut a new patch tag; the site returns to VitePress' default
`github-light` / `github-dark`. Alternatively roll the image back to
`0.1.53` in `services/admins/mctl-docs/values.yaml` via the normal rollback
path.
