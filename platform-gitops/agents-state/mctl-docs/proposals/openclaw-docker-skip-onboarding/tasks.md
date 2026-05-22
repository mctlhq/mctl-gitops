# Tasks: openclaw-docker-skip-onboarding

- [ ] 1. Update `docs/platform/openclaw.md` — add the "Deployment configuration" section
         from `proposed-content.md` (env var table with `OPENCLAW_SKIP_ONBOARDING`).
         — DoD: file updated, `vitepress build docs` is green.
- [ ] 2. Verify the table renders correctly in local preview.
         — DoD: `npm run dev` shows the table with correct columns and link.
- [ ] 3. Cross-link: check `docs/guides/gitops-workflows.md` — if it mentions OpenClaw
         deployment, add a reference to the new "Deployment configuration" section.
         — DoD: relevant cross-reference in place (or noted as not applicable).
- [ ] 4. Open a PR against `mctlhq/mctl-docs`, run code review, merge.
         — DoD: content live at docs.mctl.ai/platform/openclaw.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. The external link to `docs.openclaw.ai/install/docker` resolves (HTTP 200).
- [ ] T3. Accepted truthy values (`1`, `true`, `yes`, `on`) have been verified against
          the upstream `scripts/docker/setup.sh` diff in commit `490e6d6`.

## Rollback

- Revert the table addition via a PR. Low risk — markdown only, no build impact.
- version-status: unverified (confirm against production mctl-openclaw before publishing).
