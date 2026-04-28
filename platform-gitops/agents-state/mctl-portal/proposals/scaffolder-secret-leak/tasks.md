# Tasks: scaffolder-secret-leak

Note: tasks 1–5 fully overlap with `scaffolder-path-traversal` because both CVEs are closed
by the same PR. If `scaffolder-path-traversal` has already been implemented, tasks 1–5 are
considered done for this proposal as well.

- [ ] 1. Update `@backstage/backend-defaults` to ^0.12.2 and `plugin-scaffolder-backend`
  to ^3.1.1 in `packages/backend/package.json` and the root `package.json` (single PR with
  `scaffolder-path-traversal`) — DoD: `yarn install` finishes without errors; `yarn.lock`
  records versions >= 0.12.2 and >= 3.1.1; `yarn backstage-cli versions:check` reports no
  peer conflicts.

- [ ] 2. Run `yarn backstage-cli repo build` (depends on 1) — DoD: the build finishes
  without TypeScript errors.

- [ ] 3. Run a playwright smoke test of the create-service template in staging (depends on
  2) — DoD: the test passes; the onboarding form works correctly.

- [ ] 4. Build a Docker image and update the tag in the ArgoCD manifest of the `admins`
  tenant (depends on 3) — DoD: ArgoCD status `Synced` and `Healthy`.

- [ ] 5. Run `yarn audit --level high` (depends on 4) — DoD: no high/critical CVEs related
  to CVE-2026-32237 or CVE-2026-24046.

- [ ] 6. Trigger rotation of every secret mounted in the backend pod via ExternalSecret
  (depends on 4) — DoD: new values for the Vault token, Postgres DSN, GitHub App credentials
  are written to Vault; ExternalSecret has updated the Kubernetes Secret; the pod has
  restarted with the new secrets; old credentials are revoked.

## Tests

- [ ] T1. Integration test: call the dry-run endpoint with a template that explicitly
  references `process.env.VAULT_TOKEN` — confirm the response replaces the value with
  `[REDACTED]` rather than returning it in clear.
- [ ] T2. Integration test: dry-run response with a nested JSON object containing a
  `credentials` key with a sensitive value — confirm recursive redaction.
- [ ] T3. Smoke test: dry-run of a legitimate template (no secret references) returns the
  correct preview without `[REDACTED]` in non-secret fields.
- [ ] T4. `yarn audit` in CI must fail the build on severity >= high.

## Rollback
1. Restore the previous Docker image tag in the ArgoCD manifest of the `admins` tenant.
2. Run `argocd app sync mctl-portal --prune`.
3. The CVE-2026-32237 vulnerability returns; as a temporary mitigation — disable the
   dry-run endpoint via the Backstage permission framework (deny the action
   `scaffolder.template.parameter.read` for every group).
4. If secret rotation (task 6) has already been performed — no rollback is needed for it;
   the new credentials remain in force.
