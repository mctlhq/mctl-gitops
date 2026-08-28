# Tasks: issue-911-set-explicit-auto-merge-enabled-false-fo

- [ ] 1. Add `AUTO_MERGE_ENABLED: "false"` to the `env` map in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml`,
  directly below the existing `DRY_RUN: "false"` line, with a comment
  explaining the fail-closed rationale (mirroring the style of the
  `GITHUB_TOKEN_FILE` / `OPTIMIZER_ENABLED` comments already in this
  file) — DoD: the file has exactly one new line (plus its comment) added
  to the `env:` block; no other key, value, image tag, or section in the
  file is touched; the value is the quoted string `"false"`, matching the
  quoting style of every other boolean-shaped flag in this file.

- [ ] 2. Render and inspect the change before merge (depends on 1) — DoD:
  either `helm template` against the `base-service` chart with the
  edited inline values block, or `argocd app diff admins-mctl-agent`
  against the branch, shows a Deployment container env entry
  `- name: AUTO_MERGE_ENABLED` / `value: "false"` and shows no other
  diff.

- [ ] 3. Open a PR with this single-file change, following the repo's
  normal PR path (this is a template/spec change under
  `bootstrap/templates/`, not a `gitops-bump.yaml` / `release-deploy.yaml`
  image-tag bump, so it does NOT qualify for the direct-to-main
  exception in `CLAUDE.md` — it goes through `claude-review.yml` and
  `validate-manifests.yml` like any other template change) — DoD: PR
  opened, CI (`validate-manifests.yml`) green, `claude-review.yml`
  review posted.

- [ ] 4. After merge, confirm ArgoCD auto-syncs `admins-mctl-agent`
  (depends on 3) — DoD: `mctl_get_service_status` (or `argocd app get
  admins-mctl-agent`) shows `Synced` + `Healthy` within the normal
  reconciliation window; no manual sync should be required given
  `syncPolicy.automated`.

- [ ] 5. Verify the *live* pod env, not just ArgoCD sync status (depends
  on 4) — DoD: `kubectl -n admins exec <admins-mctl-agent pod> -- env |
  grep AUTO_MERGE_ENABLED` (or `mctl_get_service_logs` startup-log check
  if the binary logs its resolved config on boot) shows
  `AUTO_MERGE_ENABLED=false`. This step is the explicit acceptance
  criterion from the issue ("fail-closed config rule") and must not be
  skipped even if step 4 is green.

## Tests
- [ ] T1. `helm template` (or `argocd app diff`) dry-run from task 2 shows
  the new env entry and zero unrelated diff lines.
- [ ] T2. `validate-manifests.yml` CI check passes on the PR (manifest
  syntax / schema validation for the bootstrap template).
- [ ] T3. Post-sync live pod env check from task 5 confirms
  `AUTO_MERGE_ENABLED=false` is actually present in the running
  container, not merely in git.

## Rollback
Revert the single-line addition (plus comment) in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml` via a
follow-up PR (or `git revert` of the merge commit) and let
`syncPolicy.automated` (`prune: true`, `selfHeal: true`) reconcile the
pod back to its prior env set on the next sync — no manual kubectl
intervention needed. Because `strategy.type: Recreate` is already in
place, the rollback pod swap is atomic the same way the forward change
is: no mixed-env window. There is no data migration or external state to
unwind; this is a pure env-var change.
