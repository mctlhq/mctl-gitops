# Tasks: mctl-agent-telegram-routing

- [ ] 1. Update `docs/platform/components.md` — apply the "Telegram alert routing"
         paragraph from `proposed-content.md` into the `mctl-agent` subsection.
         — DoD: paragraph present, `vitepress build docs` exits 0.
- [ ] 2. Verify the tenant names in the example (`admins`, `labs`, `ovk`) match the
         current tenant list in `mctl-gitops` before publishing.
         — DoD: names confirmed accurate.
- [ ] 3. (Optional) Add a one-liner cross-reference from `docs/guides/tenants.md` pointing
         to the new routing paragraph, for operators who discover the feature via the
         tenant guide.
         — DoD: cross-reference in place.
- [ ] 4. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
         — DoD: content live at docs.mctl.ai/platform/components.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. All links in the updated section resolve.
- [ ] T3. The `TELEGRAM_TENANT_CHAT_IDS` format example matches the parser in
          `mctl-agent:internal/config/config.go` (commit `f4e8a38`) — confirm whitespace
          trimming and comma-separation are correctly described.

## Rollback

- Revert the paragraph addition via a revert PR. Low risk — markdown only, no nav change.
- version-status: unverified (confirm mctl-agent 1.6.0 is in production before publishing).
