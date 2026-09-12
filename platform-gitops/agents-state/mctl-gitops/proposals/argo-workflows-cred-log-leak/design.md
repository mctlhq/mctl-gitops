# Design: argo-workflows-cred-log-leak

## Current state
Argo Workflows runs all cron and on-demand pipelines for the platform (see
`context/architecture.md`), with manifests under `platform-gitops/argo-workflows/`:
`cluster-templates/` (CronWorkflow + ClusterWorkflowTemplate), `secrets/` (ExternalSecret
manifests sourcing artifact-repository and Git credentials from Vault via the
`vault-backend` ClusterSecretStore), and `service-templates/`/`file-templates/` (scaffolder
value templates). The workflow executor is the component responsible for pulling/pushing
workflow artifacts to/from S3, GCS, Azure Blob, and Git.

CVE-2026-42295 describes the executor logging these artifact-repository credentials in
plaintext during artifact operations, in versions 4.0.0 through <4.0.5. Per the latest
release-tracking cycle, the fleet is pinned at 4.1.2 or 4.1.3, both of which postdate the
fix. However, no record in this repo confirms (a) that the fleet was never briefly pinned
to an affected version during a prior upgrade sequence, or (b) that historical executor
logs from any such window have been checked for leaked credentials.

## Proposed solution
This is an audit/confirmation task, not a version-bump task, because the currently pinned
version already postdates the fix:

1. **Version-history confirmation.** Review the git history of the Argo Workflows version
   pin under `platform-gitops/argo-workflows/` to establish whether the fleet was ever
   running a version in the 4.0.0-<4.0.5 range, and for how long.
2. **Conditional log audit.** If step 1 finds such a window, pull the executor's historical
   logs (via the platform's log aggregation — Loki, per `context/architecture.md`) for that
   window and grep for known credential-log patterns (S3 access keys, GCS service-account
   JSON fragments, Azure SAS tokens, Git PATs/SSH key material) in executor pod logs.
3. **Conditional rotation.** If any credential is found exposed, rotate it at the source
   (the relevant Vault secret) and confirm the ExternalSecret in
   `platform-gitops/argo-workflows/secrets/` has re-synced the new value into the cluster;
   verify the affected CronWorkflow/ClusterWorkflowTemplate continues to authenticate
   against the artifact repository successfully with the rotated credential.
4. **Record the outcome.** Commit a short audit note under
   `platform-gitops/agents-state/argo-workflows-cred-log-leak/` documenting the version
   history checked, whether any exposure was found, and (if applicable) which credentials
   were rotated — this is a permanent audit record, not a manifest change, and follows the
   same read/append pattern already used for other confirmation-style proposals (e.g.
   `argocd-xss-version-verify`).

No version bump, no Argo Workflows manifest change, and no CRD schema change is needed if
the audit finds no historical exposure (the expected outcome, given the fleet has been on
4.1.x for at least the last two release cycles per prior inbox entries).

## Alternatives
**a. Immediately rotate all artifact-repository credentials as a precaution, without first
checking log history.**
Rejected: disproportionate — a blanket rotation touches every tenant's
artifact-repository access and risks breaking in-flight workflows for no confirmed benefit
if the fleet was never actually in the vulnerable version range. Audit-first is the
proportionate response given the low-effort framing of this finding.

**b. Add a log-scrubbing sidecar or redaction filter to the log pipeline as a permanent
mitigation, regardless of audit outcome.**
Rejected: a broader architectural change to the logging pipeline (Loki ingestion path) for
a bug that is already fixed upstream in the running version; disproportionate effort for a
CVE that (per current evidence) the fleet already postdates. Could be reconsidered as a
defense-in-depth follow-up if the audit finds evidence of exposure, but not proposed here
as day-one scope.

**c. Do nothing, since the fleet already postdates the fix.**
Rejected: this leaves the historical-exposure question unanswered. Even though the
code-level bug is fixed going forward, any credential logged during a past vulnerable
window remains exposed in log storage until explicitly checked and, if needed, rotated. A
lightweight audit closes this residual gap at negligible cost.

## Platform impact
**Migrations:** None. No manifest, CRD, or version-pin changes unless the audit finds a
genuinely vulnerable historical window, in which case only a Vault secret rotation is
involved (not a schema change).

**Backward compatibility:** Full. This proposal does not change any running component's
behavior in the no-exposure-found case; in the exposure-found case, only the affected Vault
secret value changes, transparently to the ExternalSecret/CronWorkflow consuming it.

**Resource impact (`labs`):** None. This is a log-query and (conditionally) a
Vault-secret-rotation task against the shared Argo Workflows control-plane component; no
tenant workload pods, memory requests, or limits change in `admins` or `labs`.

**Risks and mitigations:**
- Risk: log retention window in Loki is shorter than the vulnerable-version period, making
  a full historical audit impossible. Mitigation: document the retention gap explicitly in
  the audit note; treat any un-auditable window as "assume exposed" and rotate the relevant
  credentials as a precaution for that specific gap only.
- Risk: credential rotation breaks an in-flight or scheduled CronWorkflow if the
  ExternalSecret sync lags behind the rotation. Mitigation: verify ExternalSecret re-sync
  completes (check `lastRefreshTime`) before considering the rotation complete; monitor the
  next scheduled run of affected CronWorkflows.
- Risk: the audit reveals a broader logging pattern issue beyond just this CVE's specific
  credential types. Mitigation: scope this proposal's fix to the CVE's known credential
  classes; file a follow-up proposal for any broader logging hardening found.
