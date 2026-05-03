# Tasks: git-plugin-install-allowlist

- [ ] 1. Confirm upstream `pluginPolicy.gitInstallAllowlist` config key behaviour in openclaw
  2026.5.2 — DoD: upstream changelog and config schema reviewed; behaviour (fail-closed on
  empty list, prefix matching, SSH URL normalisation) confirmed against the 2026.5.2 source
  or release notes and documented as a comment in the Helm chart values file.

- [ ] 2. Add `gitPluginInstall` Helm values block to the openclaw chart (depends on 1) — DoD:
  `helm/openclaw/templates/configmap-openclaw.yaml` renders a `pluginPolicy` section from
  `gitPluginInstall.enabled` and `gitPluginInstall.allowlist` values; `values.yaml` default
  is `enabled: false`, `allowlist: []`; `helm template` produces valid YAML with no new
  containers or init-containers.

- [ ] 3. Add `gitPluginInstall` block to `admins/values.yaml` with `enabled: false` and the
  initial allowlist (`https://github.com/mctlhq/`, `https://github.com/openclaw/`)
  (depends on 2) — DoD: gitops PR merged and ArgoCD reports sync-OK for `admins`; helm-diff
  shows only the new ConfigMap section with no resource-limit or replica changes.

- [ ] 4. Add `gitPluginInstall` block to `labs/values.yaml` with `enabled: false` and the
  same initial allowlist (depends on 3) — DoD: gitops PR merged and ArgoCD reports sync-OK
  for `labs`; s3-sync canary and restore-state probe both pass after sync; no memory
  increase detected in mctl-api metrics for the `labs` pod.

- [ ] 5. Add `gitPluginInstall` block to `ovk/values.yaml` with `enabled: false` and the
  same initial allowlist (depends on 4) — DoD: gitops PR merged and ArgoCD reports sync-OK
  for `ovk`; s3-sync canary and restore-state probe both pass after sync.

- [ ] 6. Add CI step `check-git-plugin-allowlist` to the mctl-gitops pipeline (depends on 2)
  — DoD: the step is defined in the CI config (e.g., `.github/workflows/policy-checks.yaml`
  or the equivalent); it fails a PR when `gitPluginInstall.enabled: true` is set alongside
  an empty or absent `allowlist`; it fails a PR when the rendered ConfigMap contains
  `gitInstallAllowlist` entries absent from the corresponding `values.yaml`; it passes on
  the existing `admins`, `labs`, and `ovk` values files; CI run evidence is attached to the
  PR.

- [ ] 7. Write operator runbook for expanding the allowlist (depends on 6) — DoD: a page
  (internal wiki or `docs/runbooks/git-plugin-allowlist.md` in mctl-gitops) explains the PR
  process for adding a new git host/org, the CI checks that will run, and who must approve;
  linked from the Helm values file as a comment.

- [ ] 8. Enable `git:` plugin installs on `admins` by flipping `enabled: true` (optional,
  separate PR, depends on 5 and 7) — DoD: `admins/values.yaml` sets `enabled: true`; a
  test install from an allowlisted URL succeeds; a test install from an off-list URL is
  rejected with the expected error message and log event; gitops PR reviewed by at least one
  security-team member.

## Tests

- [ ] T1. Unit test (Helm rendering): given `gitPluginInstall.enabled: false` and any
  allowlist, the rendered `config.yaml` ConfigMap contains `pluginPolicy.gitInstallAllowlist`
  with `enabled: false`. Given `enabled: true` and a non-empty allowlist, the rendered
  ConfigMap contains the correct prefix entries. Given `enabled: true` and an empty allowlist,
  `helm template` exits with an error (or the CI step catches it).

- [ ] T2. CI gate test: submit a PR to mctl-gitops that sets `gitPluginInstall.enabled: true`
  with `allowlist: []` — confirm the `check-git-plugin-allowlist` CI step fails and the
  failure message references the policy document. Then correct the allowlist — confirm the
  step passes.

- [ ] T3. Integration test on `admins` (after task 8): run
  `openclaw plugins install git:https://github.com/mctlhq/test-plugin-fixture` (allowlisted)
  and confirm install succeeds. Run
  `openclaw plugins install git:https://github.com/attacker/evil-plugin` (not allowlisted)
  and confirm the process exits non-zero with a policy-restriction message and a WARN-level
  log event visible in the mctl-api log pipeline.

- [ ] T4. Update-path test on `admins` (after task 8): install a plugin from an allowlisted
  URL, then remove that URL from the allowlist via a gitops PR, wait for ArgoCD sync, and
  run `openclaw plugins update <plugin>` — confirm the update is blocked with a log event and
  the previously installed plugin binary is unchanged.

- [ ] T5. Memory regression check on `labs` (after task 4): compare pod memory (via mctl-api
  metrics) before and after the ConfigMap sync. Confirm the delta is under 1 MB. Document
  the before/after values in the task 4 PR description.

- [ ] T6. Promotion gate: confirm that `ovk` values are not set to `enabled: true` until
  tasks T3 and T4 pass on `admins` and task T5 passes on `labs`. This is a process gate,
  not an automated test, but must be recorded as a checklist item in the `ovk` PR description.

## Rollback

**Config rollback (all tenants, any task 3–5 or 8):** The change is a Helm values update.
Roll back by reverting the gitops PR (or pushing a revert commit). ArgoCD will sync the
previous ConfigMap within its normal sync interval. No pod restart is required because the
allowlist is read at install-time, not held in a persistent data store. No plugins are
automatically removed on rollback.

**CI step rollback (task 6):** If the `check-git-plugin-allowlist` CI step causes false
positives, it can be disabled by removing or commenting out the step in the CI config via a
PR. This does not affect the runtime policy.

**If `labs` shows memory regression after task 4:** Revert the `labs` values PR immediately.
The `admins` values PR is independent and does not need to be reverted. Investigate whether
the openclaw 2026.5.2 `pluginPolicy` config section unexpectedly allocates memory (unlikely
given the analysis in design.md) before re-attempting the `labs` rollout.

**If `enabled: true` is set on `ovk` and a false-positive block occurs:** Revert the `ovk`
values PR (setting `enabled` back to `false`). This restores the previous behaviour where
`git:` installs are rejected entirely. No data loss occurs; installed plugins are not
removed. Investigate the allowlist entry and re-submit.
