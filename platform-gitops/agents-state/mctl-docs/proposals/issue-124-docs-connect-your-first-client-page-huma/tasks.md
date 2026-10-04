# Tasks: issue-124-docs-connect-your-first-client-page-huma

- [ ] 1. Confirm the lead path (MCP connector assumed) from the clarification answer and
  confirm Telegram command behaviour with the mctl-telegram owners — DoD: lead path and
  `/mctl link`, `/mctl work` wording recorded in the PR description.
- [ ] 2. Create `docs/guides/connect-first-client.md` with sections: intro, Before you
  start, lead path procedure, "Alternative" section for the other path, Next steps
  (depends on 1) — DoD: exactly one numbered lead procedure; MCP section references
  `https://api.mctl.ai/mcp`, links `/mcp/connecting`, and verifies with "Who am I on
  MCTL?"; Telegram section lists `/mctl link` then `/mctl work`; no emoji, English.
- [ ] 3. Add `{ text: 'Connect your first client', link: '/guides/connect-first-client' }`
  to the "Guides" sidebar in `docs/.vitepress/config.ts` between "First-user checklist"
  and "Deploy your first app" (depends on 2) — DoD: entry appears in that position.
- [ ] 4. Add an entry for the page to `docs/public/llms.txt` (depends on 2) — DoD: one
  line in the existing format pointing to `https://docs.mctl.ai/guides/connect-first-client`.
- [ ] 5. Optionally add a one-line tip in `docs/getting-started/index.md` Step 2 linking to
  the new page (depends on 2) — DoD: link resolves.
- [ ] 6. Run `bun run build` to regenerate `docs/public/llms-full.txt` and build the site
  (depends on 2-5) — DoD: build succeeds, new page included in `llms-full.txt`.

## Tests
- [ ] T1. `bun run build` succeeds with no dead-link errors.
- [ ] T2. `bun run preview`: `/guides/connect-first-client` renders, the sidebar shows
  the entry in the correct position, and local search finds "Connect your first client".
- [ ] T3. Manual review: page has one lead procedure and one Alternative section, and the
  Telegram section states nothing beyond confirmed behaviour.
- [ ] T4. `grep` the new page for emoji / non-English content returns nothing.

## Rollback
Revert the PR (removes the new page, sidebar entry, `llms.txt` line and optional
getting-started link), then cut a new patch tag (`MAJOR.MINOR.PATCH`, no `v` prefix) so
CI rebuilds the image and updates GitOps. No data or state to restore.
