# Tasks: mcp-agents-tools

- [ ] 1. Update `docs/mcp/tools-reference.md` — apply the "mctl-agents pipeline controls"
         section from `proposed-content.md`.
         — DoD: section present, `vitepress build docs` exits 0.
- [ ] 2. Cross-check tool parameter enums against `mctl-api:internal/mcp/server.go`
         (commits `016b3c8` and `f41590e`) to confirm `service` enum values and
         `force` accepted values are accurate.
         — DoD: no discrepancy between docs and source code.
- [ ] 3. Verify the `mctl_get_workflow_status` cross-link in the status-polling note
         resolves to the correct anchor on `docs/mcp/tools-reference.md`.
         — DoD: link returns 200 in local `vitepress dev`.
- [ ] 4. (Optional) Add a note in `docs/getting-started/index.md` or `docs/platform/components.md`
         hinting that admins can control the agents pipeline via MCP — drives discoverability.
         — DoD: one-liner cross-reference in place.
- [ ] 5. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
         — DoD: content live at docs.mctl.ai/mcp/tools-reference.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the new section resolves (cross-link to `mctl_get_workflow_status`
          anchor, cross-links to related pages if added).
- [ ] T3. The `service` enum in the `mctl_trigger_single_service` and `mctl_trigger_implementer`
          docs matches the current enum in `mctl-api:internal/operations/registry.go`
          (7 repos: mctl-web, mctl-openclaw, mctl-docs, mctl-api, mctl-portal, mctl-agent,
          mctl-gitops).
- [ ] T4. Confirm mctl-api version ≥ 4.15.0 is deployed to production before publishing.

## Rollback

- Revert the section addition via a revert PR. Low risk — markdown only, no config change.
- version-status: unverified (confirm mctl-api 4.16.0 in production before publishing).
