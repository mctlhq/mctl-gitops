# Tasks: openclaw-api-routing

- [ ] 1. Update `docs/platform/openclaw.md` — apply the "API paths and namespace routing"
         subsection from `proposed-content.md`.
         — DoD: subsection present, `vitepress build docs` exits 0.
- [ ] 2. Resolve `<TODO>` in the identity listing allowlist description: confirm the exact
         allowlist mechanism (env var name, config file, or hardcoded list) with the author
         of commit `edba139` in mctl-api before publishing.
         — DoD: `<TODO>` removed, allowlist description is accurate.
- [ ] 3. (Optional) Add a one-liner note to `docs/api/index.md` linking to the OpenClaw
         routing subsection for readers who land on the API reference first.
         — DoD: cross-reference in place.
- [ ] 4. Open a PR against `mctlhq/mctl-docs`, run code review, merge.
         — DoD: content live at docs.mctl.ai/platform/openclaw.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. All links in the new subsection resolve (cross-link to `docs/api/index.md`
          returns 200 in local preview).
- [ ] T3. The mermaid flow diagram renders without errors in `vitepress dev`.
- [ ] T4. The `<TODO>` regarding the identity allowlist mechanism has been resolved
          before the PR is merged.

## Rollback

- Revert the subsection addition via a revert PR. Low risk — markdown only, no nav change.
- version-status: unverified (confirm against production mctl-api ≥ 4.15.0 before publishing).
