# Tasks: issue-38-add-first-user-onboarding-checklist

- [ ] 1. Create `docs/guides/first-user-checklist.md` — DoD: file exists at that path
  in the `docs/guides/` directory; page contains all eight task-list items from the
  issue in order; each item includes a brief description and at least one inline link
  to a relevant existing page or URL; the file follows repo conventions (no emoji,
  English only, no frontmatter required beyond what VitePress infers).

- [ ] 2. Add sidebar entry to `docs/.vitepress/config.ts` (depends on 1) — DoD: the
  Guides sidebar array in `config.ts` contains
  `{ text: 'First-user checklist', link: '/guides/first-user-checklist' }` inserted
  before the existing "Deploy your first app" entry (currently at array index 0 of the
  Guides items block, lines 62-63); no other sidebar entries are modified.

- [ ] 3. Verify local build passes (depends on 2) — DoD: running `npm run docs:build`
  from the repository root exits with code 0; no broken-link warnings reference the
  new page; the output directory (`docs/.vitepress/dist/`) contains
  `guides/first-user-checklist/index.html`.

## Tests

- [ ] T1. VitePress build: `npm run docs:build` exits 0 with no errors or broken-link
  warnings in the output for `guides/first-user-checklist`.
- [ ] T2. Route resolves: the built output at
  `docs/.vitepress/dist/guides/first-user-checklist/index.html` exists and contains
  each of the eight checklist item labels (spot-check against the issue's suggested
  list).
- [ ] T3. Sidebar entry present: `docs/.vitepress/config.ts` contains the string
  `first-user-checklist` exactly once, inside the Guides sidebar array, and the
  sidebar section compiles without TypeScript errors (`npx tsc --noEmit`).
- [ ] T4. Internal links valid: all relative `href` targets in the new page
  (`/guides/deploy-first-app`, `/guides/tenants`, `/guides/scaffolding`,
  `/mcp/overview`, `/mcp/connecting`, `/mcp/tools-reference`) resolve to existing
  built HTML files in `docs/.vitepress/dist/`.
- [ ] T5. No regressions: the navigation structure for all pre-existing Guides pages
  is unchanged — confirm the ten original entries still appear in the sidebar output
  in their original order.

## Rollback

1. Delete `docs/guides/first-user-checklist.md`.
2. Revert the sidebar entry added to `docs/.vitepress/config.ts` (remove the
   `{ text: 'First-user checklist', link: '/guides/first-user-checklist' }` line).
3. Run `npm run docs:build` to confirm the build still passes.
4. Tag and deploy as normal (tag push triggers CI/CD per the repo workflow).

Both changes are in two files and are fully additive; no data migration, schema
change, or external system update is involved, so the rollback is a single commit.
