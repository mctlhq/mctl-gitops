# Tasks: argocd-v3-4-1-cluster-gen-migration

- [ ] 1. Audit all uses of `argocd.argoproj.io/kubernetes-version` in `platform-gitops/` —
  grep the entire `platform-gitops/` tree for the label key in cluster Secrets and
  ApplicationSet specs; record every file, line, and current value.
  DoD: a complete list of occurrences is documented in the PR description; grep confirms
  no occurrences are missed by checking both `kubernetes-version` as a label key and as a
  template variable reference.

- [ ] 2. Update all label values to `vMajor.Minor.Patch` format (depends on 1) — for each
  occurrence found in task 1, change the label value to strict `vMajor.Minor.Patch` format
  (e.g., `1.30` becomes `v1.30.0`; `v1.30` becomes `v1.30.0`). Apply via a single PR
  to keep the change atomic.
  DoD: all `argocd.argoproj.io/kubernetes-version` label values in `platform-gitops/`
  match the regex `^v[0-9]+\.[0-9]+\.[0-9]+$`; the PR is reviewed and merged.

- [ ] 3. Verify ArgoCD v3.4.0 reconciles ApplicationSets with updated labels (depends on 2) —
  after the label PR is merged and ArgoCD syncs, confirm that all ApplicationSets using
  the cluster generator continue generating the expected Applications without errors.
  DoD: `kubectl get applications -A` shows the same set of Applications as before the label
  change; ArgoCD ApplicationSet controller logs contain no generation errors for at least
  10 minutes after reconciliation.

- [ ] 4. Update ArgoCD Helm chart to v3.4.1 in `admins` (depends on 3) — change the ArgoCD
  chart version in `platform-gitops/services/admins/<argocd-svc>/` to v3.4.1 and open
  a PR.
  DoD: ArgoCD syncs the `admins` Deployment to v3.4.1; all ApplicationSets generate the
  correct Applications; ApplicationSet controller logs contain no label-format errors;
  no Applications transition to an error state within 30 minutes of rollout.

- [ ] 5. Monitor ApplicationSet controller in `admins` (depends on 4) — observe the
  ApplicationSet controller logs for 30 minutes post-upgrade.
  DoD: zero generation errors logged; all Applications in `admins` remain `Synced` and
  `Healthy`; the v3.4.1 upgrade is confirmed stable.

- [ ] 6. Update ArgoCD Helm chart to v3.4.1 in `labs` (depends on 5) — change the ArgoCD
  chart version in `platform-gitops/services/labs/<argocd-svc>/` to v3.4.1 and open
  a PR.
  DoD: same criteria as task 4, applied to the `labs` tenant; no memory increase observed
  in the `labs` namespace.

- [ ] 7. Confirm optional new features available post-upgrade (depends on 6) — verify that
  the ApplicationSet `health` field and Watch API are accessible in the upgraded ArgoCD
  instance (e.g., via `argocd appset get` output or ArgoCD API inspection).
  DoD: a note is added to the PR confirming feature availability; no action required to
  enable them (they are additive). This task is informational and does not block the
  proposal from being considered complete.

## Tests

- [ ] T1. ApplicationSet generation regression test — after label migration (task 2) and
  after ArgoCD upgrade (task 4), compare the full list of generated Applications before and
  after each change. Confirm the sets are identical (no Applications added or removed as a
  side-effect of the migration or upgrade).

- [ ] T2. Label format CI validation — add or verify a CI lint step in `platform-gitops/`
  that validates all `argocd.argoproj.io/kubernetes-version` label values against the
  regex `^v[0-9]+\.[0-9]+\.[0-9]+$`, failing the pipeline if any non-conforming value is
  found. This prevents regression after the migration.
  DoD: CI pipeline enforces the format check on every PR touching cluster Secrets or
  ApplicationSet specs.

- [ ] T3. Generation failure error-visibility test — temporarily apply a cluster Secret with
  an intentionally malformed `kubernetes-version` label (e.g., `1.30`) to a non-production
  context after upgrading to v3.4.1. Confirm the ApplicationSet controller emits a
  structured error log identifying the offending ApplicationSet and label value within one
  reconciliation cycle. Revert the test label immediately after verification.

## Rollback

If the ArgoCD v3.4.1 upgrade causes ApplicationSet generation failures or unexpected
Application state changes:

1. Revert the chart version change via `git revert` on the relevant commit in
   `platform-gitops/services/<tenant>/<argocd-svc>/`.
2. Merge and push the revert; ArgoCD reconciles back to v3.4.0.
3. Confirm all ApplicationSets resume normal generation.
4. The label migration (tasks 1-3) does not need to be reverted — the `vMajor.Minor.Patch`
   format is valid in v3.4.0 as well; reverting it would add unnecessary churn.
5. Open a post-mortem issue to identify the regression before re-attempting the v3.4.1
   upgrade.

Existing Applications generated before the upgrade are never deleted by a chart version
rollback — ArgoCD preserves Application resources regardless of controller version.
