# Tasks: issue-39-document-mcp-as-a-platform-management-op

- [ ] 1. Add MCP intro callout to `docs/guides/deploy-first-app.md` — DoD: A `:::info Managing
  MCTL through MCP` block is inserted between the existing two-sentence intro paragraph and the
  `## Before you begin` heading. The block contains the issue's suggested text ("inspect tenants,
  deploy services, check workflow status, operate the platform conversationally"), an inline link to
  `/mcp/connecting`, and a note that each step includes both a portal path and an MCP path. No
  existing headings, anchors, or prerequisite bullets are modified. VitePress local dev (`npm run
  docs:dev`) renders the callout as a styled info block without build errors.

- [ ] 2. Add Portal alternative callout to `docs/getting-started/index.md` (depends on 1) — DoD:
  A `:::tip Portal alternative` block is inserted after the opening sentence ("This guide takes you
  from zero to a running service on MCTL in under 10 minutes. No Kubernetes experience required.")
  and before `## Prerequisites`. The block names the Portal URL (`app.mctl.ai`), describes it as a
  Backstage-powered service catalog, and states that MCP and Portal are complementary. No existing
  steps or prerequisites are modified. VitePress local dev renders the callout without build errors.

- [ ] 3. Verify both callouts link correctly and render (depends on 1, 2) — DoD: Running
  `npm run docs:build` in the repo root completes without errors or warnings. The built output at
  `.vitepress/dist/guides/deploy-first-app/index.html` contains the text "inspect tenants, deploy
  services, check workflow status" and an `<a href="/mcp/connecting">` anchor. The built output at
  `.vitepress/dist/getting-started/index.html` contains the text "Portal alternative" and a link to
  `https://app.mctl.ai`.

## Tests

- [ ] T1. VitePress build passes without errors after both edits: `npm run docs:build` exits 0.
- [ ] T2. `docs/guides/deploy-first-app.md` contains the string `/mcp/connecting` at least twice
  (once in "Before you begin", once in the new callout) — verified by `grep -c '/mcp/connecting'
  docs/guides/deploy-first-app.md` returning 2 or greater.
- [ ] T3. `docs/getting-started/index.md` contains the string `app.mctl.ai` in a prose context
  (not just as a nav link) — verified by `grep 'app.mctl.ai' docs/getting-started/index.md`
  returning at least one match inside the new `:::tip` block.
- [ ] T4. No existing heading IDs or anchor links in `deploy-first-app.md` are broken — verify by
  checking that `## Before you begin`, `## Step 1`, `## Optional: Add a custom domain`, and
  `## Optional: Manage the platform through MCP` all appear unchanged after the edit.

## Rollback

Both changes are additive edits to two Markdown files. To roll back:

1. Revert the merge commit on `main`: `git revert <merge-commit-sha> --no-edit`
2. Push the revert commit: `git push origin main`
3. The CI/CD pipeline will rebuild and redeploy the static site from the reverted source.

Because no files are deleted, no sidebar entries are added or removed, and no build configuration
is changed, the rollback is a single-commit operation with no residual artifacts to clean up.
