# Tasks: backstage-backend-defaults-ssrf-fix

- [ ] 1. Identify the currently installed `@backstage/backend-defaults` version and
      the minimum patched version for our line (0.12.2 / 0.13.2 / 0.14.1 / 0.15.0)
      — DoD: exact target version confirmed and documented in the PR description.
- [ ] 2. Bump `@backstage/backend-defaults` (and any peer `@backstage/backend-*`
      packages yarn's resolver requires) in the workspace root `package.json`, run
      `yarn install`, commit updated `yarn.lock` (depends on 1) — DoD: `yarn install`
      completes cleanly with no unresolved peer-dependency warnings for backend
      packages.
- [ ] 3. Run the full backend test suite (`yarn workspace backend test` or
      equivalent) (depends on 2) — DoD: all existing tests pass with no new
      failures.
- [ ] 4. Manual smoke test in a staging/preview environment: load a TechDocs page,
      run a scaffolder template fetch from an external host, and exercise one
      `proxy` plugin route (depends on 2) — DoD: all three flows return expected
      content with no errors.
- [ ] 5. Verify the fix: point an allowlisted test host at a redirect to a
      non-allowlisted internal-looking URL (in a safe, non-production sandbox) and
      confirm the fetch is refused (depends on 2) — DoD: redirect to
      non-allowlisted target is rejected; error is logged.
- [ ] 6. Deploy via mctl-gitops → ArgoCD to tenant `admins` (depends on 3, 4, 5) —
      DoD: ArgoCD reports Healthy/Synced on the new revision; no new incidents
      opened for `mctl-portal` in the 24h following deploy.

## Tests
- [ ] T1. Unit/integration: existing backend test suite passes unmodified.
- [ ] T2. Manual: TechDocs page renders correctly post-bump.
- [ ] T3. Manual: scaffolder template fetch from an external allowlisted host
      succeeds.
- [ ] T4. Manual: `proxy` plugin route to an allowlisted external API succeeds.
- [ ] T5. Security regression: redirect from an allowlisted host to a
      non-allowlisted target is rejected (validates the CVE fix is effective).

## Rollback
Revert the `@backstage/backend-defaults` (and any co-bumped peer packages) version
in `package.json` / `yarn.lock` to the prior pinned version, re-run `yarn install`,
and redeploy through mctl-gitops → ArgoCD. Since this is a patch-level, additive
security fix with no config or schema migration, rollback is a plain dependency
downgrade and redeploy — no data cleanup required.
