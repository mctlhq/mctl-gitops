# Tasks: argocd-v3-6-3-security-patch

- [ ] 1. Confirm deployed Argo CD version and verify the 7 advisories on GHSA — DoD: version and advisory list recorded in the PR.
- [ ] 2. Complete the release-name audit (argocd-helm-release-name-validation) (depends on 1) — DoD: zero offending names.
- [ ] 3. Bump image/chart to v3.6.3 in the bootstrap definition (depends on 2) — DoD: PR merged, all components on v3.6.3.
- [ ] 4. Record memory/CPU baseline vs post-rollout, especially for labs (depends on 3) — DoD: delta <10%.
- [ ] 5. Mark argocd-v3-6-2-regexp2-cve-patch superseded (depends on 3) — DoD: noted in PR.

## Tests
- [ ] T1. All Applications Synced/Healthy after rollout.
- [ ] T2. Malformed unauthenticated request to argocd-server does not crash it (staging only).
- [ ] T3. ApplicationSet delete respects allowed namespaces.

## Rollback
Revert the bump commit; ArgoCD self-reconciles to the previous tag. Check Application CRDs are compatible.
