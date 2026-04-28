# Tasks: helm-security-patch

- [ ] 1. Inventory all Helm usage points across the platform — DoD: a list (ArgoCD image, ClusterWorkflowTemplate image refs, Backstage scaffolder actions) with the current Helm versions in each is compiled.
- [ ] 2. Determine the ArgoCD version that contains Helm v4.1.4 (check the official ArgoCD changelog) — DoD: the minimum ArgoCD image tag with Helm >= v4.1.4 is captured.
- [ ] 3. Update the ArgoCD image tag in `platform-gitops/apps/` (depends on 2) — DoD: image tag updated, the PR contains only a version change.
- [ ] 4. Update image references in ClusterWorkflowTemplate files in `platform-gitops/argo-workflows/cluster-templates/` for all steps using the helm CLI (depends on 1) — DoD: every helm-using step points at an image with Helm v4.1.4.
- [ ] 5. Inspect and update Backstage scaffolder templates if helm is used in actions (depends on 1) — DoD: either the absence of helm in the scaffolder is confirmed, or the relevant image/version is updated.
- [ ] 6. Create a single PR with the changes from steps 3–5 — DoD: PR created, diff contains only version updates, CI is green.
- [ ] 7. After merge run ArgoCD sync and verify Application states (depends on 6) — DoD: every affected ArgoCD Application is `Synced` + `Healthy`.
- [ ] 8. Verify the Helm version in deployed components (depends on 7) — DoD: `helm version` in the ArgoCD pod and in the workflow executor pod returns v4.1.4 or newer.

## Tests
- [ ] T1. Verify the Helm version in ArgoCD: `kubectl exec -n argocd <argocd-server-pod> -- helm version` — expected v4.1.4+.
- [ ] T2. Run an ArgoCD dry-run sync for several key Applications (including `base-service` for the `admins` tenant) — expected: rendering succeeds without errors.
- [ ] T3. Run a test Workflow that uses a helm CLI step (if present in `cluster-templates/`) — expected status `Succeeded`.
- [ ] T4. Confirm all ArgoCD Applications stay `Synced` + `Healthy` 15 minutes after the ArgoCD upgrade.
- [ ] T5. Confirm there are no Helm-rendering-related errors in the ArgoCD repo-server logs: `kubectl logs -n argocd -l app.kubernetes.io/component=repo-server --since=15m | grep -i "helm\|error"`.

## Rollback
1. Run `git revert <commit-sha>` against the image-tag bump commit in mctl-gitops.
2. Merge the revert commit.
3. ArgoCD automatically rolls images back to previous versions via App-of-Apps sync.
4. If ArgoCD itself was updated — verify that after revert its image also returned to the previous tag.
5. Verify the rollback: re-run T1 with the expected old Helm version.
