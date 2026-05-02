# Tasks: mcp-shepherd-tool

> **Prerequisite:** `proposals/mcp-agents-tools/` must be applied first (or applied
> together). If the "mctl-agents pipeline controls" section already exists in
> `docs/mcp/tools-reference.md`, skip task 1 and proceed to task 2.

- [ ] 1. Apply `proposals/mcp-agents-tools/proposed-content.md` to
         `docs/mcp/tools-reference.md` to create the "mctl-agents pipeline controls"
         section (five tools).
         — DoD: section present, tool summary table visible, `vitepress build docs` exits 0.

- [ ] 2. Amend `proposals/mcp-agents-tools/proposed-content.md`:
         a. Change "five tools" → "six tools" in the intro paragraph.
         b. Add `mctl_trigger_shepherd` row to the tool summary table.
         c. Add `mctl-agents` to the `service` enum in the `mctl_trigger_single_service`
            and `mctl_trigger_implementer` parameter tables.
         — DoD: proposed-content reflects 6 tools and 8 service values.

- [ ] 3. Insert the `### mctl_trigger_shepherd` detail block (from
         `proposed-content.md` in this proposal) into `docs/mcp/tools-reference.md`,
         after `### mctl_trigger_implementer` and before `### Status polling`.
         — DoD: shepherd section present, `vitepress build docs` exits 0.

- [ ] 4. Update `docs/mcp/tools-reference.md` service enum rows for
         `mctl_trigger_single_service` and `mctl_trigger_implementer` to include
         `mctl-agents` as the 8th value.
         — DoD: both tables list 8 service values.

- [ ] 5. Update `proposals/mcp-agents-tools/tasks.md` test T3 to say "8 repos"
         and add `mctl-agents` to the list. Add test T5 (see below).
         — DoD: tasks.md is consistent with the implemented content.

- [ ] 6. Run `npm run dev` locally and open `docs/mcp/tools-reference.md#mctl-agents-pipeline`.
         — DoD: shepherd block renders, `dry_run` parameter table visible, no broken anchors.

- [ ] 7. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
         — DoD: content live at docs.mctl.ai/mcp/tools-reference.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the shepherd block resolves (cross-link to `mctl_get_workflow_status`
          anchor, cross-link to `mctl_trigger_implementer`).
- [ ] T3. The `service` enum for `mctl_trigger_single_service` and `mctl_trigger_implementer`
          lists exactly 8 values: `mctl-web`, `mctl-openclaw`, `mctl-docs`, `mctl-api`,
          `mctl-portal`, `mctl-agent`, `mctl-gitops`, `mctl-agents`.
          Verify against `mctl-api:internal/mcp/server.go` (commits `f29adbd`, `e1fbe3f`).
- [ ] T4. `mctl_trigger_shepherd` parameter table lists: `service` (optional enum, 8 values),
          `slug` (optional string), `dry_run` (optional enum "true"/"false", default "false").
- [ ] T5. Confirm mctl-api ≥ 4.17.0 is deployed to production before publishing.
          (mctl-gitops `00dc844` confirms 4.17.0 was deployed 2026-05-01.)

## Rollback

- Revert the shepherd block insertion and enum row additions via a revert PR.
- Low risk — markdown only, no config change.
- version-status: verified — mctl-api 4.17.0 in production as of 2026-05-01
  (mctl-gitops commit `00dc844`).
