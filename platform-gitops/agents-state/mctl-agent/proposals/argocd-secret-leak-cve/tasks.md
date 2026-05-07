# Tasks: argocd-secret-leak-cve

- [ ] 1. Confirm the exact Argo CD version currently running in the `admins` cluster —
  DoD: a comment in the PR records the output of `argocd version --server` (or
  `kubectl -n argocd get deploy argocd-server -o jsonpath='{.spec.template.spec.containers[0].image}'`)
  showing the current tag.

- [ ] 2. Pin the Argo CD image tags in `mctlhq/mctl-gitops` `admins` overlay to
  v3.3.9 (or v3.2.11 if the cluster is on the v3.2.x branch) — DoD: a PR to
  `mctlhq/mctl-gitops` is open with the image tag change in every affected
  Deployment manifest (`argocd-server`, `argocd-repo-server`,
  `argocd-application-controller`, `argocd-applicationset-controller`,
  `argocd-notifications-controller`).

- [ ] 3. Verify CRD compatibility — DoD: diff of upstream CRD manifests between the
  current tag and the target tag shows zero schema changes; the diff is attached to
  the GitOps PR description.

- [ ] 4. Merge and sync the GitOps PR; monitor rolling restart — DoD: all Argo CD
  pods in `argocd` namespace report `Running` and pass readiness probes; Argo CD
  UI/CLI confirms version v3.3.9 or v3.2.11; the `mctl-agent` Application shows
  `Synced / Healthy` within 10 minutes of merge.

- [ ] 5. Validate CVE remediation — DoD: a manual ServerSideDiff request containing a
  Kubernetes Secret reference (using a read-only Argo CD service account) returns
  HTTP 403 with no secret data in the response body; this test is documented and the
  result screenshot or log snippet is attached to the incident ticket.

- [ ] 6. Update the CVE tracker — DoD: CVE-2026-42880 is marked `remediated` in the
  internal vulnerability tracker with a link to the merged GitOps PR and the
  validation evidence.

## Tests

- [ ] T1. Pre-upgrade smoke test: `argocd app list` returns all expected applications
  with `Synced / Healthy` status before the rollout starts.

- [ ] T2. Post-upgrade version assertion: `argocd version --server | grep v3.3.9`
  (or `v3.2.11`) exits 0.

- [ ] T3. CVE-specific regression test: authenticated read-only request to the
  ServerSideDiff endpoint with a Secret in scope returns HTTP 403 — run against
  the upgraded server and record response.

- [ ] T4. mctl-agent health check: `curl https://agent.mctl.ai/healthz` returns HTTP
  200 both immediately before and within 5 minutes after the Argo CD pod restart.

- [ ] T5. ArgoCDDrift skill regression: trigger a synthetic drift event after the
  upgrade and confirm the `ArgoCDDrift` builtin skill detects and reports it
  correctly (no false negatives introduced by the Argo CD version change).

## Rollback
If the upgraded Argo CD pods fail readiness probes or the `mctl-agent` Application
enters a degraded state:

1. Revert the image tag PR in `mctlhq/mctl-gitops` to the previous Argo CD version.
2. Force-sync the `argocd` Application: `argocd app sync argocd --force`.
3. Confirm all Argo CD pods return to `Running` with the old image tag.
4. If self-managed sync is broken, apply the previous Argo CD install manifest directly:
   `kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/<previous-tag>/manifests/install.yaml`.
5. File a post-mortem and re-evaluate the target patch version before retry.
