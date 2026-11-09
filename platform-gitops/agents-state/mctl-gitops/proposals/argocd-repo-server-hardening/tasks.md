# Tasks: argocd-repo-server-hardening

- [ ] 1. Verify CVE-2026-15416 and CVE-2026-113709 against NVD, the Argo CD GHSA and the Red Hat advisory; record ID validity, affected and fixed versions — DoD: a short note lists each ID as verified or unverified with the source link; unverified IDs are flagged in later commit messages.
- [ ] 2. Record the running Argo CD version (mctl or cluster) and compare with the verified ranges (depends on 1) — DoD: version recorded and "affected / not affected" stated.
- [ ] 3. Check existing proposals (for example `argocd-repo-server-rce-network-isolation`) and live cluster for an existing repo-server NetworkPolicy; avoid duplication — DoD: decision recorded to extend, replace or create.
- [ ] 4. Inventory Apps using kustomize with Helm (`--enable-helm` in build options, `helmCharts` in kustomizations) across `platform-gitops/` — DoD: list of Apps (possibly empty) attached to the PR.
- [ ] 5. Author NetworkPolicy manifest for repo-server and Redis (depends on 3) — DoD: manifest in this repo, passes `kubectl --dry-run=server` and review of pod labels and ports.
- [ ] 6. Apply kustomize Helm change: remove `--enable-helm` if inventory is empty, else pin `helmGlobals.configHome` outside the repo (depends on 4) — DoD: change committed; all Apps still Synced/Healthy.
- [ ] 7. Roll out on `admins` Argo CD, enforce, and observe for 24h (depends on 5, 6) — DoD: no new OutOfSync/Unknown Apps, no repo-server connection errors in logs.
- [ ] 8. Confirm no memory or pod-count change in `labs` (depends on 7) — DoD: labs memory usage unchanged within noise; stated in the PR.

## Tests
- [ ] T1. From an unrelated pod, connect to repo-server 8081 and Redis 6379 — DoD: connection is refused/times out.
- [ ] T2. From application-controller and server pods, force a hard refresh of an App — DoD: manifests generate successfully.
- [ ] T3. Refresh each App from the task 4 inventory — DoD: render succeeds after the Helm change.
- [ ] T4. Prometheus still scrapes Argo CD metrics — DoD: targets are up.

## Rollback
Remove the NetworkPolicy manifest (git revert) and ArgoCD reconciles it away; restore the previous `argocd-cm` kustomize build options via git revert and restart repo-server. Neither step touches data.
