# Tasks: review-receipts-overview

version-status: unverified, see commit SHA

- [ ] 0. Confirm prod availability of `mctl_submit_review_assertion` on the shared portal (e.g. via mctl MCP tool list) and the tool's argument schema with the author of 30ae621. - DoD: TODOs resolved; otherwise stop.
- [ ] 1. Apply `proposed-content.md` to `docs/mcp/tools-reference.md`. - DoD: `vitepress build docs` green.
- [ ] 2. No sidebar change. - DoD: confirmed.
- [ ] 3. `npm run dev`; open page. - DoD: renders.
- [ ] 4. Check tool-count statements on the page/overview for staleness. - DoD: consistent.
- [ ] 5. PR against `mctlhq/mctl-docs`, `@claude review`, merge. - DoD: deployed.

## Tests
- [ ] T1. `vitepress build docs` clean.
- [ ] T2. Links resolve.
- [ ] T3. No invented parameters remain.

## Rollback
- Revert PR (markdown only).
