# Tasks: argocd-repo-cred-leak-patch

- [ ] 1. Identify current ArgoCD installation method and version pin — DoD: document whether
  ArgoCD is installed via Helm chart or Kustomize, and record the exact current version tag
  and chart version in a PR description or commit message.

- [ ] 2. Determine the argo-cd Helm chart version that ships ArgoCD v3.3.9 (depends on 1) —
  DoD: chart version identified from https://github.com/argoproj/argo-helm/releases and
  recorded; any CRD diff between current and target chart version is listed.

- [ ] 3. Apply CRD updates to the cluster ahead of the controller rollover (depends on 2) —
  DoD: `kubectl apply -f crds/` (or equivalent) completes without errors; existing Application,
  ApplicationSet, and AppProject objects remain in a valid state as verified by
  `kubectl get applications -A`.

- [ ] 4. Update the ArgoCD version pin in `platform-gitops/` to v3.3.9 / target chart version
  (depends on 3) — DoD: the relevant Helm values file or Kustomize image override references
  v3.3.9 image tags; the change is committed and a PR is raised.

- [ ] 5. Merge and observe ArgoCD self-upgrade via App-of-Apps reconciliation (depends on 4) —
  DoD: ArgoCD pods are running v3.3.9 as confirmed by `argocd version`; no CrashLoopBackOff
  or OOMKilled pods; all pre-existing Applications show Healthy/Synced within 10 minutes.

- [ ] 6. Add CI version gate to reject ArgoCD pins below v3.1.2 (depends on 5) — DoD: a
  `conftest` policy or shell script in the CI pipeline fails the build if the ArgoCD image
  tag is parsed as earlier than v3.1.2; gate is active on the main branch.

- [ ] 7. Recommend credential rotation for repository credentials (depends on 5) — DoD: a
  follow-up ticket is filed (out-of-scope for this proposal) to rotate the GitHub deploy key
  and bot credentials that may have been exposed during the window the vulnerability was open.

## Tests

- [ ] T1. Exploit reproduction test: using a project-scoped `get` token against the running
  v3.3.9 instance, call `/api/v1/projects/{project}/detailed` and assert that the response
  body contains no `username`, `password`, or `sshPrivateKey` fields for repositories.
- [ ] T2. ApplicationSet smoke test: verify that all three ApplicationSets (`apps`, `tenants`,
  `openclaw-skills`) reconcile successfully after the upgrade by checking that the number of
  generated Applications matches the pre-upgrade count.
- [ ] T3. Sync health check: confirm that every Application in the cluster reaches
  Sync=Synced and Health=Healthy within 10 minutes of the ArgoCD controller restart.
- [ ] T4. CI gate test: introduce a test branch that pins ArgoCD below v3.1.2 and confirm that
  the CI pipeline rejects it with a clear error message referencing CVE-2025-55190.

## Rollback
1. Revert the version-pin commit in `platform-gitops/` to the previous ArgoCD image tag.
2. Push the revert commit; the App-of-Apps reconciliation loop will downgrade ArgoCD back to
   the previous version.
3. If CRDs were updated as part of the upgrade, restore the previous CRD manifests from git
   history using `kubectl apply -f` — note that CRD downgrade may fail if new fields were
   written to existing objects; in that case, no-schema-change CRD versions can be restored
   safely, but objects using new fields would need to be re-created.
4. After rollback, re-assess whether the short-lived re-exposure window warrants immediate
   token revocation pending a re-attempt at the upgrade.
