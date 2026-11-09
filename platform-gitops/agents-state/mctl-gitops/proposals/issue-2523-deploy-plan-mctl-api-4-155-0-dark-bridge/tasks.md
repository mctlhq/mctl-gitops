# Tasks: issue-2523-deploy-plan-mctl-api-4-155-0-dark-bridge

- [ ] 1. Write `docs/runbooks/mctl-api-4.155.0-dark-rollout.md`. It contains the decision gate (default
  `BLOCKED_RELEASE_HOLD`), the evidence table E1-E11, the release STOP conditions, the post-deploy checks
  P1-P6, and the E5-dependent rollback branches described in design.md. — DoD: every field links its source
  issue or PR; the gate value is BLOCKED; the doc says explicitly that READY is not approval and that
  `release-deploy.yaml` must not be used for this bump.
- [ ] 2. Add a pointer line in `CLAUDE.md` under "Secrets Management" / runbooks, next to the other runbook
  pointers (depends on 1). — DoD: one line referencing the new runbook.
- [ ] 3. Add `tests/test_mctl_api_bridge_dark.py`. It asserts that `MCTL_BRIDGE_ENABLED` is absent or "false",
  that `MCTL_BRIDGE_PROVIDERS` and `MCTL_BRIDGE_PROVIDER_TOKENS` are absent, that
  `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` is absent or "false", and that no bridge-named secret source
  exists, all in `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`. — DoD: passes on the
  current file; fails on each injected violation (see T2).
- [ ] 4. Wire task 3 into `.github/workflows/validate-manifests.yml` as `python3 tests/test_mctl_api_bridge_dark.py`
  (depends on 3). — DoD: the job runs it on PRs touching that file.
- [ ] 5. Open one doc+test PR for tasks 1-4 from a feature branch (depends on 1-4). — DoD: the PR changes no
  `image.tag` and no env value, and CI is green.
- [ ] 6. GATED, not to be done by the implementer now: the operator fills in E1-E11 after the #934 owner GO
  (depends on 5 and on the external blockers). — DoD: every field is filled; the gate flips to
  `READY_FOR_SEPARATE_DARK_DEPLOY_APPROVAL`.
- [ ] 7. GATED: open the one-line tag-bump PR `4.154.0` to `4.155.0` with the rendered Helm diff attached, and
  merge it only on explicit owner approval (depends on 6). — DoD: the diff is exactly one line; test B is
  green; the owner approval is recorded.
- [ ] 8. GATED: run P1-P6 and record the results in the runbook (depends on 7). — DoD: all pass, or the
  rollback was executed per the matching branch.

## Tests

- [ ] T1. `python3 tests/test_mctl_api_bridge_dark.py` passes on the unmodified `mctl-api.yaml`.
- [ ] T2. The test fails for each fixture variant: `MCTL_BRIDGE_ENABLED: "true"`, the presence of
  `MCTL_BRIDGE_PROVIDERS`, the presence of `MCTL_BRIDGE_PROVIDER_TOKENS`,
  `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE: "true"`, and an `envFromExtraSecret` naming `bridge`.
- [ ] T3. When it is eventually run: `helm template mctl-api <mctl-api repo>/helm` at E10 with the inline values,
  for both 4.154.0 and 4.155.0. The only difference is the container image reference.
- [ ] T4. Post-deploy: P3, the negative Bridge smoke. Bridge routes are not served, and the logs show no
  dispatcher or sweeper start.

## Rollback

- Tasks 1-5 are a doc and a CI test only. Revert the PR.
- Task 7: choose according to E5. If 4.154.0 can replay 4.155.0 Temporal histories, revert the bump PR and
  confirm that Argo `admins-mctl-api` is Synced at the revert and that the running digest equals the E11
  pre-bump digest. If it cannot, do NOT revert the image. Stop, page the release owner, and drain or handle
  the affected workflows per mctl-agents#1007 B4 before any revert. The chart tracks mctl-api `main` and is
  not rolled back by the tag revert.
