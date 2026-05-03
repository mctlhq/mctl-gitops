# Tasks: prometheus-security-patch

- [ ] 1. Audit Prometheus version pins across the repository — DoD: A complete list of
  every file under `platform-gitops/services/` and `platform-gitops/helm-charts/` that
  references a Prometheus image tag or Helm chart version is produced. Each entry records
  the file path and the current pinned value. Produced by running:
  `grep -r "prometheus" platform-gitops/services/ platform-gitops/helm-charts/ --include="*.yaml" -l`
  followed by targeted tag/version extraction.

- [ ] 2. Update all Prometheus version pins to v3.11.3 (depends on 1) — DoD: Every file
  identified in task 1 that pins Prometheus below v3.11.3 has been updated to `v3.11.3`.
  No file in `platform-gitops/services/` or `platform-gitops/helm-charts/` references a
  Prometheus image tag earlier than v3.11.3. Verified by re-running the grep from task 1
  and confirming no sub-v3.11.3 references remain.

- [ ] 3. Audit and enforce credential logging configuration (depends on 1) — DoD: Every
  Prometheus values file has been inspected for `auth.credentials_in_debug_log` (or the
  chart-equivalent key). Files missing the key have it added as `false`. Files with the
  key set to `true` have been corrected to `false`. A comment referencing the AzureAD
  credential exposure fix in v3.11.3 is added inline.

- [ ] 4. Commit all changes and open PR (depends on 2, 3) — DoD: A single git commit
  (or small PR) contains all version pin updates and credential log configuration changes.
  The commit message references the three security issues addressed by v3.11.3. The PR
  description links to the Prometheus v3.11.3 release notes.

- [ ] 5. Verify ArgoCD sync succeeds (depends on 4) — DoD: After merging the PR, ArgoCD
  reports all Prometheus Applications as `Synced` and `Healthy`. The Prometheus pod image
  tag is confirmed as `v3.11.3` via:
  `kubectl get pod -l app=prometheus -o jsonpath='{.items[*].spec.containers[*].image}'`

## Tests

- [ ] T1. Prometheus pod image tag is v3.11.3 or later — query the running pod image tag
  and assert it matches `v3.11.3` or a later patch.

- [ ] T2. No credentials appear in Prometheus logs under AzureAD OAuth configuration —
  if AzureAD OAuth is configured in any tenant, enable debug logging temporarily in a
  non-production environment and confirm that no `client_secret` or token values appear
  in `kubectl logs` output for the Prometheus pod.

- [ ] T3. Load test with malformed snappy payload does not crash Prometheus — send a
  malformed snappy-encoded body to the Prometheus remote-write endpoint
  (`POST /api/v1/write`) and verify the pod does not restart (check
  `kubectl get pod` restart count before and after).

## Rollback

Revert the version pin commit(s) in git. ArgoCD will detect the revert and re-sync
Prometheus to the previous image tag on the next reconciliation cycle. No persistent data
is affected; Prometheus TSDB on-disk format is unchanged between patch versions. If the
credential logging configuration change needs to be reverted, revert that commit separately.
