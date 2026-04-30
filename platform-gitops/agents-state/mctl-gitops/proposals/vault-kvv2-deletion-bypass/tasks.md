# Tasks: vault-kvv2-deletion-bypass

## Phase 1 — Policy tightening (interim mitigation)

- [ ] 1. Enumerate all Vault policies — run `vault policy list` and pull each policy's HCL.
  DoD: full list of policies with glob paths documented.

- [ ] 2. Identify policies that grant `delete` or `destroy` under a glob path (depends on 1).
  DoD: list of policy names and the offending capability lines.

- [ ] 3. Rewrite each identified policy to remove `delete`/`destroy` from glob rules; add
  explicit non-glob delete paths only where operationally required (depends on 2).
  DoD: updated HCL files committed to `infrastructure/` (or the relevant Terraform module);
  `vault policy read <name>` output matches the new HCL.

- [ ] 4. Apply updated policies to the production Vault instance (depends on 3).
  DoD: policies applied; `vault policy read <name>` confirms no glob `delete`/`destroy`.

- [ ] 5. Validate ESO ExternalSecret sync across both tenants after policy change (depends on 4).
  DoD: all ExternalSecrets in `admins` and `labs` show `Ready=True` within 5 minutes.

## Phase 2 — Vault upgrade to patched release

- [ ] 6. Review Vault v2.0.0 release notes for breaking changes affecting ESO ClusterSecretStore,
  ArgoCD Vault plugin, and any other Vault-dependent service (depends on Phase 1 complete).
  DoD: compatibility matrix document or PR description listing each breaking change and its
  mctl-specific impact.

- [ ] 7. Execute Vault v2.0.0 upgrade in staging and run full ESO + ArgoCD smoke tests
  (depends on 6). DoD: staging environment healthy; no ExternalSecret sync errors.

- [ ] 8. Schedule and execute production Vault upgrade (depends on 7).
  DoD: `vault status` shows v2.0.0; all ExternalSecrets `Ready=True`; ArgoCD Applications
  `Healthy` and `Synced`.

- [ ] 9. Update `context/current-version.md` (read-only in agent context — flag for human
  operator) to record the Vault version upgrade.

## Tests

- [ ] T1. Attempt to delete a secret using a glob-policy token that has no explicit delete grant —
  expect 403 Forbidden.
- [ ] T2. Confirm ExternalSecrets for `admins` tenant read secrets correctly after Phase 1
  policy change.
- [ ] T3. Confirm ExternalSecrets for `labs` tenant read secrets correctly after Phase 1
  policy change.
- [ ] T4. After Phase 2 upgrade, confirm `vault kv get secret/data/admins/<any-svc>` succeeds
  with the ESO service token.
- [ ] T5. Confirm ArgoCD Vault plugin (if in use) authenticates successfully after v2.0.0 upgrade.

## Rollback

**Phase 1 rollback:** Restore the previous policy HCL from git and re-apply via `vault policy write`.
ESO will resume using the previous (wider) policies within one sync cycle.

**Phase 2 rollback:** Restore the previous Vault version from the snapshot taken before the upgrade.
Vault snapshot procedure: `vault operator raft snapshot save pre-upgrade.snap` before upgrade.
Re-deploy the previous Vault container image; restore snapshot if data was written during the
failed upgrade window.
