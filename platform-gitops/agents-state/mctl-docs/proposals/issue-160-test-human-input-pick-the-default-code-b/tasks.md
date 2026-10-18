# Tasks: issue-160-test-human-input-pick-the-default-code-b

- [ ] 1. Confirm the requester's chosen pair from the human-input answer (default: option 1, `github-light` / `github-dark`) — DoD: chosen light and dark theme names recorded in the PR description.
- [ ] 2. Add `theme: { light: '<light>', dark: '<dark>' }` to the `markdown` object in `docs/.vitepress/config.ts`, keeping the existing `config(md)` mermaid fence override unchanged (depends on 1) — DoD: config diff touches only the `markdown` block.
- [ ] 3. Run `bun run build` (depends on 2) — DoD: test, llms generation and `vitepress build docs` succeed.
- [ ] 4. Visually check code blocks in `bun run dev` on pages with shell, YAML and TypeScript fences (depends on 2) — DoD: tokens legible against `--vp-code-block-bg`; mermaid diagrams still render.

## Tests
- [ ] T1. `bun run test` (`docs/.vitepress/theme/mermaid-links.test.ts`) passes.
- [ ] T2. Built HTML for a page with a code block contains `shiki` spans with the chosen dark theme class/name (e.g. grep `docs/.vitepress/dist` for `github-dark` or `one-dark-pro`).
- [ ] T3. A `mermaid` fence still renders as `<div class="mermaid-diagram" ...>` in the built output.

## Rollback
Revert the single commit adding `markdown.theme` and cut a new patch tag; or roll back the `admins/mctl-docs` service to the previous image tag. With option 1 the revert yields identical output, as it matches the VitePress default.
