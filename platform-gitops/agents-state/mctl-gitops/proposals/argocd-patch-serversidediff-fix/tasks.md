# Tasks: argocd-patch-serversidediff-fix

- [ ] 1. Verify CVE-2026-45737, CVE-2026-42880 and CVE-2026-43824 and their fixed-version lists against NVD and the Argo CD GHSA — DoD: each ID marked verified/unverified with source link; fixed versions per minor line recorded.
- [ ] 2. Read the running Argo CD version and determine whether ServerSideDiff is enabled (cmd-params, annotations, ApplicationSet templates) — DoD: version and ServerSideDiff status recorded.
- [ ] 3. Reconcile with existing proposals (`argocd-serversidediff-secret-leak`, `argocd-serversidediff-secret-exposure`, `argocd-secret-leakage-patch`) (depends on 1, 2) — DoD: decision to supersede/reuse recorded.
- [ ] 4. Choose the target patch in the same minor line, or stop and request an ADR if none is verified (depends on 1, 2) — DoD: target tag written down; priority set (downgraded if ServerSideDiff is off).
- [ ] 5. If ServerSideDiff is on and the upgrade is not immediate, disable it as interim mitigation (depends on 2) — DoD: setting committed, diffs still work.
- [ ] 6. Review release notes between current and target and check namespace quota (including `labs`) for rolling-restart surge (depends on 4) — DoD: notes summarized; quota headroom confirmed; labs memory baseline captured.
- [ ] 7. Commit the version bump and roll out to `admins`, one component at a time (depends on 6) — DoD: all Argo CD pods on target tag and Ready; previous tag recorded.
- [ ] 8. Observe for 24h and confirm labs memory unchanged (depends on 7) — DoD: all Apps Synced/Healthy; no errors; labs memory within baseline.

## Tests
- [ ] T1. `argocd version` and pod image tags match target — DoD: all components on target.
- [ ] T2. Diff an App containing a Secret — DoD: no Secret values appear in UI, CLI or logs.
- [ ] T3. Hard-refresh a sample of Apps from `admins` and `labs` tenants — DoD: Synced/Healthy.

## Rollback
Revert the version-bump commit (restore the previous image tag), let ArgoCD or a manual sync roll the components back, and re-run T3. If ServerSideDiff was disabled interim, re-enable it only after the fix is confirmed.
