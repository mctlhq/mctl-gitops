# Tasks: argocd-annotation-xss-privesc

- [ ] 1. Confirm currently-pinned Argo CD version — inspect the chart/image tag in
  `platform-gitops/bootstrap/` and cross-reference `context/current-version.md`.
  DoD: current minor line (3.2.x / 3.3.x / 3.4.x) and patch number identified and documented
  in the PR description; confirmed it is below the corresponding fixed version (3.2.12 /
  3.3.10 / 3.4.2).

- [ ] 2. Check for overlap with `argocd-secret-leakage-patch` /
  `argocd-serversidediff-secret-exposure` in-flight work (depends on 1).
  DoD: decision recorded on whether this bump is landed standalone or combined with the
  ServerSideDiff patch PR; no duplicate version-pin commits.

- [ ] 3. Bump Argo CD version pin in `platform-gitops/bootstrap/` to the fixed release
  identified in task 1 (depends on 2).
  DoD: PR merged; Argo CD's self-managed Application shows the new version after sync;
  `argocd-server`, `application-controller`, and `repo-server` pods report the new image
  tag.

- [ ] 4. Verify annotation rendering fix (depends on 3).
  DoD: a test Application with a benign `link.argocd.argoproj.io/*` annotation still
  renders as a clickable link in the UI; a crafted payload (used only in a non-prod/test
  Application, never committed to a real service) is confirmed to render as inert text, not
  execute.

- [ ] 5. Confirm no new app-write role bindings were introduced during the rollout window
  (depends on 3).
  DoD: RBAC diff on `platform-gitops/services/*/*` shows no unrelated permission changes
  landed alongside this patch.

## Tests
- [ ] T1. Version confirmation test — after sync, `argocd version` (or the UI About page)
  reports 3.2.12 / 3.3.10 / 3.4.2 or higher.
- [ ] T2. XSS regression test — in a disposable test Application (not a real tenant
  service), set a `link.argocd.argoproj.io/*` annotation to a script-injection payload;
  confirm it renders as literal text in the Argo CD UI and no script executes when an admin
  views it. Remove the test Application afterward.
- [ ] T3. Legitimate link regression test — confirm at least one real Application's
  existing external-link annotation still renders and is clickable post-upgrade.

## Rollback
If the upgrade causes UI regressions or sync instability:
1. Revert the version-pin commit in `platform-gitops/bootstrap/` via `git revert`.
2. Push the revert; Argo CD's self-managed Application reconciles back to the previous
   image via rolling update.
3. Confirm `argocd-server` returns to a healthy state and Application sync resumes
   normally across all tenants.
4. Re-attempt the upgrade after root-causing the regression; the CVE remains open in the
   interim, so prioritize re-attempt within the same patch cycle if possible.
