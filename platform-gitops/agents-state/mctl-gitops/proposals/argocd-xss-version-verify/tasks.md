# Tasks: argocd-xss-version-verify

- [ ] 1. Confirm cluster context and query ArgoCD server version — DoD: Run
  `kubectl config current-context` to confirm the target cluster, then run
  `argocd version --server` and capture the full output to a local file.
  Output must show ArgoCD server version v3.0.4 or later.

- [ ] 2. Commit version-check artifact to agents-state (depends on 1) — DoD:
  The file `platform-gitops/agents-state/argocd-xss-version-verify/version-check.txt`
  is committed to the main branch. The file contains: the raw `argocd version` output,
  the date of the check, the operator's identity, and a signed-off statement that
  CVE-2025-47933 does not apply because the running version is v3.0.4 or later.

- [ ] 3. Add version-floor comment to the ArgoCD Application manifest (depends on 1) — DoD:
  The ArgoCD Application manifest in `platform-gitops/apps/` contains a comment block
  immediately above the image tag or `targetRevision` field, referencing CVE-2025-47933,
  the minimum safe version (v3.0.4), and a link to GHSA-2hj5-g64g-fp6p. The file passes
  `argocd app diff` with no unexpected changes to the live Application object.

- [ ] 4. Open follow-up incident if version is below v3.0.4 (depends on 1) — DoD:
  This task is conditional. IF the version queried in task 1 is below v3.0.4, a
  high-priority incident is opened in the platform incident tracker referencing
  CVE-2025-47933, and tasks 2 and 3 are blocked until the incident is resolved.
  If the version is v3.0.4 or later, this task is marked not applicable (N/A).

## Tests

- [ ] T1. Verify ArgoCD pod image tag is v3.0.4 or later — run
  `kubectl get deployment argocd-server -n argocd -o jsonpath='{.spec.template.spec.containers[0].image}'`
  and confirm the tag is not within v1.2.0-rc1 through v3.0.3.

- [ ] T2. Verify the version-check artifact is present and non-empty in git —
  `git show HEAD:platform-gitops/agents-state/argocd-xss-version-verify/version-check.txt`
  returns content and includes the string "CVE-2025-47933".

- [ ] T3. Simulate a downgrade scenario — attempt to change the Application manifest
  `targetRevision` to `v3.0.3` in a feature branch and confirm that the version-floor
  comment is visible and that a reviewer would be expected to reject the PR based on the
  documented constraint.

## Rollback

This proposal makes no changes to any running resource. The only changes are:
- A new text file committed to `platform-gitops/agents-state/`.
- A YAML comment added to an existing Application manifest.

To roll back: revert the relevant git commits. ArgoCD will re-sync the Application manifest
without the comment, and the agents-state artifact can be removed. No cluster state changes
and no downtime.
