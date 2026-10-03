# Tasks: argo-workflows-cred-log-leak

- [ ] 1. Reconstruct Argo Workflows version-pin history under
  `platform-gitops/argo-workflows/`.
  DoD: git log/blame of the version-pin file(s) shows the full sequence of versions the
  fleet has run; documented whether any version in 4.0.0-<4.0.5 was ever deployed, and for
  what date range.

- [ ] 2. If task 1 finds a vulnerable window, pull executor logs from that window via Loki
  (depends on 1).
  DoD: log query results for the identified date range, scoped to Argo Workflows executor
  pods, are exported for review; if no vulnerable window is found, this task is marked done
  with "not applicable."

- [ ] 3. Grep exported logs (if any) for credential patterns — S3 access keys, GCS
  service-account JSON fragments, Azure SAS tokens, Git PATs/SSH keys (depends on 2).
  DoD: findings documented (either "no matches" or a list of exposed credential
  identifiers, without pasting the actual secret values into any committed file).

- [ ] 4. Rotate any credential found exposed in task 3, via its Vault secret (depends on 3).
  DoD: new value written to the corresponding Vault path; the ExternalSecret in
  `platform-gitops/argo-workflows/secrets/` shows an updated `lastRefreshTime`; a real
  CronWorkflow run using that credential completes successfully post-rotation.

- [ ] 5. Commit the audit record to
  `platform-gitops/agents-state/argo-workflows-cred-log-leak/` (depends on 1, 3, 4).
  DoD: a short markdown note documenting version history checked, log-retention window
  audited, findings, and any rotations performed is committed to this repo.

## Tests
- [ ] T1. Version-range test — confirm via `git log` (or the CI/CD deployment record) that
  the currently pinned version (4.1.2/4.1.3) is, and has recently been, at or above 4.0.5.
- [ ] T2. Log-pattern test — run the credential-pattern grep against a known-good log
  sample (a log line manually crafted to contain a fake matching pattern) to confirm the
  search pattern actually matches before trusting a "no matches" result on the real logs.
- [ ] T3. Rotation verification test (only if task 4 executes) — confirm the old credential
  value is rejected by the artifact-repository provider (S3/GCS/Azure/Git) after rotation,
  and the new value is accepted by a live workflow run.

## Rollback
This proposal has no infrastructure change to roll back in the expected
(no-exposure-found) case — it produces only an audit record. If a credential rotation
(task 4) causes a workflow to fail authenticating against its artifact repository:
1. Check the ExternalSecret sync status and Vault secret version history; revert to the
   immediately prior secret version in Vault if the new value was entered incorrectly.
2. Re-run the affected CronWorkflow manually to confirm recovery.
3. If the original credential was genuinely compromised, do not roll back to it — instead,
   fix the new credential's value/permissions in Vault and retry, since reverting to a
   leaked credential defeats the purpose of the rotation.
