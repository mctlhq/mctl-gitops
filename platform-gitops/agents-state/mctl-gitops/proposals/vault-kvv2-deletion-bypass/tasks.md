# Tasks: vault-kvv2-deletion-bypass

- [ ] 1. Confirm the running Vault version and identify the patched release for
         CVE-2026-3605 — DoD: version string from the running Vault Pod recorded in the
         ADR; upstream advisory confirms the minimum fixed version; coordination note
         added if this upgrade overlaps with `vault-ssrf-acme-patch`.

- [ ] 2. Audit all KVv2 Vault policies for glob patterns that include `delete`, `destroy`,
         or metadata write capabilities — DoD: a documented list of affected policies with
         specific capability lines highlighted, committed to `context/decisions/` as part
         of the ADR for this proposal.

- [ ] 3. (Interim mitigation — depends on 2) Produce revised policy HCL files that remove
         delete/destroy capabilities from glob-matched paths and restrict them to explicit
         paths only where genuinely required — DoD: revised HCL files reviewed, approved,
         and applied via `vault policy write`; ESO ClusterSecretStore remains `Ready`;
         no ExternalSecret sync errors in either namespace.

- [ ] 4. Identify and update any internal tooling that calls Vault via non-canonical URL
         paths (double slashes, trailing slashes) — DoD: grep across `platform-gitops/`
         and `cli/mctl/` finds no non-canonical Vault URL constructions, or all found
         instances are fixed and merged.

- [ ] 5. (depends on 1, 4) Upgrade Vault to the patched release in the relevant manifest
         under `platform-gitops/services/admins/vault/` (or bootstrap equivalent) —
         DoD: Vault Pod Running with the new version; `vault status` healthy; ArgoCD sync
         reports `Synced` and `Healthy`.

- [ ] 6. (depends on 5) Verify that authenticated endpoints previously unauthenticated in
         pre-2.0 Vault (e.g., health-check probes, Prometheus scrape targets) are updated
         to work with Vault v2.0.0 auth requirements — DoD: Prometheus Vault metrics
         scrape returns data; all health-check probes pass; no 401 errors in Vault audit
         log.

- [ ] 7. (depends on 5) Update `context/current-version.md` or the relevant service
         manifest to reflect the new Vault version — DoD: file updated, committed, and
         merged.

## Tests

- [ ] T1. (Interim mitigation) Using a test token with a `labs` glob policy, attempt to
          call the KVv2 metadata-delete endpoint on an `admins`-namespaced path; verify a
          403 response is returned — DoD: curl or Vault CLI output shows `permission
          denied`; no secret deleted.

- [ ] T2. (Post-upgrade) Repeat T1 against the patched Vault version to confirm the fix is
          effective at the engine level — DoD: same 403 result; Vault audit log shows the
          denied request.

- [ ] T3. ESO ExternalSecret sync test: verify all ExternalSecrets in both `admins` and
          `labs` namespaces show `SecretSynced` condition after the upgrade — DoD:
          `kubectl get externalsecrets -A` shows no `SecretSyncError` conditions.

- [ ] T4. Verify that a legitimate read operation by an ESO token on an authorized KVv2
          path still succeeds after policy tightening — DoD: `vault kv get` with the ESO
          service token returns the expected secret value.

- [ ] T5. Vault health check: `vault status` returns `sealed: false`, `initialized: true`,
          and the active node is confirmed — DoD: command output matches expected state;
          no errors in Vault server logs.

## Rollback
- **Policy tightening rollback:** re-apply the previous policy HCL using
  `vault policy write <name> <old-file.hcl>`. The pre-tightening HCL files must be saved
  before any `vault policy write` call in task 3.
- **Vault upgrade rollback:** revert the image tag commit in `mctl-gitops`; ArgoCD will
  sync the StatefulSet back to the previous version. Note: Vault storage format changes
  between major versions may require a snapshot restore if the upgrade involved a storage
  migration. Confirm whether a Vault snapshot is taken before upgrading (recommended as
  a pre-upgrade step in task 5's DoD).
- If both the upgrade and policy tightening were applied, roll back the upgrade first, then
  assess whether the policy rollback is also needed.
