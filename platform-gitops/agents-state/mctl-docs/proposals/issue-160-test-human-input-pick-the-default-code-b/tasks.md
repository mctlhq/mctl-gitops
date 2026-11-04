# Tasks: issue-160-test-human-input-pick-the-default-code-b

- [ ] 0. Confirm the theme pair from the answer to `human-input/draft.json`. If there is no answer, use `github-light` / `github-dark`. Confirm the hold ("Do not implement", test issue) has been lifted before building. — DoD: the chosen pair and approval to build are both recorded on the issue or proposal.
- [ ] 1. (depends on 0) In `docs/.vitepress/config.ts`, add `theme: { light: <light>, dark: <dark> }` to the existing `markdown` block with a one-line comment that cites issue #160. Leave `config(md)` unchanged. — DoD: the diff touches only that block.
- [ ] 2. (depends on 1) Run `bun run build` locally. — DoD: the build succeeds, including the existing `bun test` for mermaid links.
- [ ] 3. (depends on 2) Open a PR from a feature branch. The tag (MAJOR.MINOR.PATCH, no `v`) is cut by release-please after merge. — DoD: PR green on `build.yml`.

## Tests
- [ ] T1. `bun run build` succeeds, which proves the theme names resolve in shiki 2.5.0.
- [ ] T2. In `bun run preview`, a page with `ts`/`bash`/`yaml` fences renders with the chosen dark theme's token colours (inspect the inline `--shiki-dark` styles on `pre.shiki` spans), and the block background stays `#15181d` / `--surface-card`.
- [ ] T3. A `mermaid` fence still renders as `div.mermaid-diagram`, not as a highlighted code block.

## Rollback
Revert the PR (remove the `markdown.theme` key) and cut a patch release. The site
goes back to the VitePress default themes. There is no data or runtime state to
restore. As an alternative, roll the `admins/mctl-docs` image back to the previous tag.
