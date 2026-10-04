# Tasks: issue-124-docs-connect-your-first-client-page-huma

- [ ] 1. Confirm the current `/mctl link` and `/mctl work` UX and release status from mctlhq/mctl-telegram (bot handle, code flow, replies) and mctl-api surface identity deployment — DoD: notes captured in the PR description with source links; decision recorded whether the Status warning is needed.
- [ ] 2. Create `docs/getting-started/connect-first-client.md` with the sections in design.md, Telegram first, MCP connector as "Alternative" linking to `/mcp/connecting` (depends on 1) — DoD: page follows the outline, English, no emoji, uses `::: warning` / `::: tip` containers, links to `/human-input/surface-identity`, `/guides/first-user-checklist`, `/guides/deploy-first-app`.
- [ ] 3. Add `{ text: 'Connect your first client', link: '/getting-started/connect-first-client' }` after "Quick Start" in the "Getting Started" sidebar group of `docs/.vitepress/config.ts` (depends on 2) — DoD: item visible in sidebar in `bun run dev`.
- [ ] 4. Add cross-links: a `::: tip` in Step 2 of `docs/getting-started/index.md` and a sentence in item 8 of `docs/guides/first-user-checklist.md` (depends on 2) — DoD: both links resolve to the new page.
- [ ] 5. Add the page to "Key Documentation Links" in `docs/public/llms.txt` (depends on 2) — DoD: entry present with absolute `https://docs.mctl.ai/getting-started/connect-first-client` URL.

## Tests
- [ ] T1. `bun run build` succeeds with no dead-link errors; `docs/public/llms-full.txt` contains `FILE: /getting-started/connect-first-client.md`.
- [ ] T2. In `bun run preview`, `/getting-started/connect-first-client` renders; the first connection section is Telegram and precedes any MCP setup content.
- [ ] T3. `grep -n "/mctl link" docs/getting-started/connect-first-client.md` appears before `grep -n "/mctl work"`, and both appear before the "Alternative" heading.
- [ ] T4. Facts on the page (code validity, single use, `challenge_invalid`, `link_conflict`) match `docs/human-input/surface-identity.md`.
- [ ] T5. Local search finds the page for queries "telegram" and "connect".
- [ ] T6. No emoji and no non-English text in the changed files.

## Rollback
Revert the PR (removes the new page, the sidebar entry, the cross-links and the llms.txt entry), then tag a new PATCH release (`MAJOR.MINOR.PATCH`, no `v`) so CI rebuilds the image and updates GitOps. No data or config migration to undo.
