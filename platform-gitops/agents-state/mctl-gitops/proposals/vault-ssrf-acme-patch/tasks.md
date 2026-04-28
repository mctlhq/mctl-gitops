# Tasks: vault-ssrf-acme-patch

- [ ] 1. Audit ACME challenge usage across all Vault PKI mounts — DoD: a written finding (PR
  description or ADR comment) states whether http-01 or tls-alpn-01 ACME challenge is enabled
  and actively used by any tenant. Confirms which remediation path (A = disable, B = upgrade)
  will be taken.

- [ ] 2. Assess Vault CE v2.0.0 memory footprint vs current version (depends on 1, required
  for Path B) — DoD: a concrete comparison of Vault CE v2.0.0 vs current version memory usage
  (from HashiCorp release notes, official benchmarks, or a local test run) is documented. If
  v2.0.0 memory increase would exhaust available headroom for the `labs` tenant, the decision to
  fall back to Path A is recorded and Path B is blocked.

- [ ] 3. Review all Vault CE v2.0.0 breaking changes and produce an adaptation checklist (depends
  on 1; required for Path B) — DoD: a checklist item exists for each breaking change (Docker
  helper path changes, auth endpoint requirement changes). Each item is marked "no action needed"
  or "action taken" with a pointer to the specific file changed under `infrastructure/` or the
  relevant ArgoCD manifest. The `vault-backend` ClusterSecretStore auth configuration is
  explicitly validated against v2.0.0 Vault Kubernetes auth endpoint behaviour.

- [ ] 4a. **[Path A]** Disable ACME challenge on all Vault PKI mounts via Terraform (depends on
  1 confirming ACME is unused) — DoD: `acme_enabled = false` is set on all relevant
  `vault_pki_secret_backend_config_acme` Terraform resources under `infrastructure/`; `terraform
  plan` shows only the ACME config change; git commit is created.

- [ ] 4b. **[Path B]** Update Vault version pin and apply breaking-change adaptations in
  Terraform (depends on 2 confirming memory is acceptable AND 3 adaptation checklist complete)
  — DoD: the Vault Terraform module version targets CE v2.0.0; all adaptation checklist items
  from Task 3 are applied and reflected in changed files under `infrastructure/`; `terraform
  plan` is reviewed and shows no unexpected destroy/replace operations on critical resources
  (Vault storage, PKI mounts, existing secrets); git commit is created.

- [ ] 5. Create PR with all infrastructure/ changes (depends on 4a or 4b) — DoD: PR is open;
  diff contains only the changes described in Task 4a or 4b; CI lint/validation passes; PR
  description references CVE-2026-5052 and HCSEC-2026-06 and states which path was taken.

- [ ] 6. Apply Terraform changes and verify Vault health (depends on 5 merged) — DoD: `terraform
  apply` completes without error; Vault health endpoint (`/v1/sys/health`) returns HTTP 200;
  Vault pod(s) in the `admins` namespace are Running and Ready; no error-level log entries in
  the Vault pod logs in the 10 minutes following rollout.

- [ ] 7. Verify ESO integration is intact (depends on 6) — DoD: `vault-backend` ClusterSecretStore
  status condition is `Ready: True`; all ExternalSecret resources across all tenant namespaces
  show `READY: True` / `Synced`; no new error events on ExternalSecret objects within 10 minutes
  of Vault rollout.

- [ ] 8. Record the decision and close out (depends on 7) — DoD: an ADR entry is added under
  `context/decisions/` recording CVE-2026-5052, the remediation path taken, the date applied,
  and the Vault version in production post-fix; the PR is merged to main.

## Tests

- [ ] T1. Confirm Vault version: `kubectl exec -n admins <vault-pod> -- vault version` — expected
  output: Vault v2.0.0 (Path B) OR same version as before with ACME config change logged (Path A).

- [ ] T2. Verify ACME endpoint is disabled (both paths): `vault read pki/config/acme` (for each
  PKI mount) — expected: `acme_enabled = false`. If Path B and ACME was deliberately kept
  enabled, verify the SSRF-safe version is running instead.

- [ ] T3. Vault health check: `curl -s https://secrets.mctl.ai/v1/sys/health` — expected: HTTP
  200 with `"initialized": true, "sealed": false, "standby": false`.

- [ ] T4. ClusterSecretStore readiness: `kubectl get clustersecretstore vault-backend -o
  jsonpath='{.status.conditions}'` — expected: condition type `Ready` with status `True`.

- [ ] T5. ExternalSecret sync across all namespaces: `kubectl get externalsecret -A` — expected:
  all rows show `READY: True`; no rows in `SecretSyncedError` or `InternalError` state.

- [ ] T6. Vault logs clean: `kubectl logs -n admins -l app.kubernetes.io/name=vault --since=10m
  | grep -iE 'error|panic|fatal'` — expected: no output (zero error-level entries).

- [ ] T7. Memory check for labs (Path B only): `kubectl top pods -n labs` — expected: all pods
  are below their configured memory limits; no OOMKilled events in `kubectl get events -n labs`.

- [ ] T8. Regression test — create or re-sync one test ExternalSecret in a staging namespace and
  confirm the resulting Kubernetes Secret contains the correct data from Vault — expected: secret
  data matches Vault source.

## Rollback

The rollback procedure differs by path taken.

**Path A rollback (ACME re-enable):**
1. Run `git revert <commit-sha>` for the commit that set `acme_enabled = false` in
   `infrastructure/`.
2. Merge the revert commit.
3. Run `terraform apply` — Vault ACME endpoint is re-enabled. No Vault pod restart required.
4. Verify ACME endpoint is accepting requests again.
5. Note: re-enabling ACME re-introduces the CVE-2026-5052 exposure. Immediately escalate to
   Path B planning or implement a network-layer control as a temporary compensating control.

**Path B rollback (Vault version downgrade):**
1. Run `git revert <commit-sha>` for the commit that bumped the Vault version and applied v2.0.0
   adaptations in `infrastructure/`.
2. Merge the revert commit.
3. Run `terraform apply` — Vault pod rolls back to the previous version.
4. If v2.0.0 auth endpoint changes were applied to `vault-backend` ClusterSecretStore or other
   Terraform resources, the revert commit must also undo those; verify the revert diff is
   complete before merging.
5. Confirm Vault health (T3), ClusterSecretStore readiness (T4), and ExternalSecret sync (T5)
   after rollback completes.
6. If Vault storage or Raft data was affected (unlikely for a version rollback), follow the Vault
   operator runbook for snapshot restore from the most recent Vault snapshot.
7. Document the rollback incident under `context/decisions/` and re-open this proposal for a
   revised upgrade approach.

**Important:** Vault Raft snapshots should be taken immediately before executing `terraform
apply` in Task 6 to provide a clean restore point. The snapshot command:
`vault operator raft snapshot save vault-pre-upgrade-<date>.snap`.
