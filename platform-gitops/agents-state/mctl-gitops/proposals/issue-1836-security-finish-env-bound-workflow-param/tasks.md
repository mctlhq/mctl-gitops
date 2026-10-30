# Tasks: issue-1836-security-finish-env-bound-workflow-param

- [ ] 1. Extend `tests/test_shell_param_injection.py`:
  - widen `PH` to allow whitespace inside the braces;
  - let `CASES` entries carry an optional start marker as well as the stop
    marker;
  - honour `TMPDIR` so a prelude may write `child-workflow.json` into the
    work dir.

  — DoD: the existing cases and the control case still pass.
- [ ] 2. Convert all 15 script templates in `wft-smoke-test.yaml` to
  `PARAM_*` env bindings (appending to existing `env:` blocks). Add the
  numeric guard for `PREVIOUS_GENERATION` in `check-pod-running`. Replace
  the here-documents in `run-onboard`, `run-deploy`, `run-update-config`,
  `run-provision-db` and `run-retire` with a static single-quoted
  `jq -n --arg ...` program that writes `${TMPDIR:-/tmp}/child-workflow.json`,
  submitted with `kubectl create -f "$MANIFEST"`. The child parameter lists
  must match today's. Remove the 6 `wft-smoke-test.yaml` entries from
  `BASELINE`. Add harness cases for `run-onboard` (assert the canary is
  absent, the JSON parses, `team_name`/`git_tag`/`dockerfile_repo` equal the
  payload exactly, and the parameter name list is unchanged) and for
  `check-pod-running` (a non-numeric `previous_generation` exits non-zero).
  Use `Refs #1836`. (depends on 1) — DoD: `scan()` finds nothing in
  `wft-smoke-test.yaml`; the validator passes with `BASELINE` empty; one
  manual `smoke-test` run with `team_name=labs` succeeds after merge.
- [ ] 3. Convert `wft-create-tenant.yaml` `create-vault-policy` and
  `wait-for-tenant-ready` to `PARAM_TENANT_NAME`. Add a harness case for
  `create-vault-policy`. Use `Refs #1836`. (depends on 1) — DoD: no
  placeholder in either source; `test_wft_create_tenant_existing.py` and the
  harness pass.
- [ ] 4. Convert `wft-delete-tenant-safe.yaml` (`retire-tenant-services`,
  `delete-tenant-from-git`, `delete-vault-policy`,
  `cleanup-tenant-db-from-gitops`) and `wft-delete-tenant.yaml`
  (`delete-tenant-from-git`, `delete-vault-policy`) to `PARAM_TENANT_NAME`.
  Add a harness case for `delete-vault-policy` in each file. Use
  `Refs #1836`. (depends on 1) — DoD: no placeholder in any of the six
  sources; the harness passes.
- [ ] 5. Convert `wft-deploy-service.yaml` `refresh-apps-appset`,
  `wft-provision-database.yaml` `do-provision` (keeping its `grep -qE` name
  validation) and `wft-retire-service.yaml` `cleanup-db-from-gitops` to
  `PARAM_TEAM_NAME`/`PARAM_COMPONENT_NAME`/`PARAM_APP_NAME`. Add one harness
  case per template; `do-provision` uses a start marker after the yq
  download. Use `Refs #1836`. (depends on 1) — DoD: `scan()` over
  `cluster-templates/` returns no hits; `test_wft_provision_database_values.py`,
  `test_wft_retire_service_guard.py` and the harness pass.
- [ ] 6. Make `scripts/validate-shell-param-interpolation.py` a ban:
  - delete `BASELINE`, `CONSTRAINED` and the stale-baseline branch;
  - add the `{{= ... }}` expression match for
    `inputs.parameters`/`workflow.parameters`;
  - scan `sidecars` and `containerSet.containers` `command`/`args`;
  - generalise `check_env_bindings` to every container-like spec's `env`;
  - add selftest cases for a here-document body, a `{{=` expression, a
    sidecar arg and a containerSet arg;
  - rewrite the docstring.

  Use `Closes #1836`. (depends on 2-5) — DoD: `--selftest` and the full run
  pass on the repo; adding `{{inputs.parameters.x}}` to any script locally
  makes it fail.
- [ ] 7. Live check after the last merge and the ArgoCD sync (~3 min):
  - one `smoke-test` Workflow with `team_name=labs`, end to end;
  - one `deploy-service` onboard and one `update-config` with multi-line
    `env_vars` and `secret_env_vars` against a throwaway `labs` service.

  Record the workflow names on #1836. (depends on 2-6) — DoD: all three
  succeed, and `values.yaml` and Vault data match the inputs.

## Tests

- [ ] T1. The control case in `test_shell_param_injection.py` still creates
  the canary.
- [ ] T2. The #992 payloads (`"; touch $C; #`, `'; touch $C; #`,
  `$(touch $C)`, `` `touch $C` ``, terminator-line) leave no canary for
  `wft-smoke-test` `run-onboard` and `check-pod-running`, and for one
  template in each of `wft-create-tenant`, `wft-delete-tenant-safe`,
  `wft-delete-tenant`, `wft-deploy-service`, `wft-provision-database` and
  `wft-retire-service`.
- [ ] T3. `run-onboard`'s generated `child-workflow.json` carries each payload
  verbatim as a value, with an unchanged parameter name list (no YAML or JSON
  splice).
- [ ] T4. `validate-shell-param-interpolation.py --selftest` fires on
  `script.source`, an inline command, a here-document body, a `{{=`
  expression, a sidecar arg, a containerSet arg and an unbound `PARAM_*`.
- [ ] T5. `validate-shell-param-interpolation.py` passes on the repo with no
  `BASELINE` or `CONSTRAINED`.
- [ ] T6. Existing suites pass: `test_tpl_git_commit_yq.py`,
  `test_wft_create_tenant_existing.py`, `test_wft_provision_database_values.py`,
  `test_wft_retire_service_guard.py`, `validate-yq-interpolation.py`.
- [ ] T7. Manual: the smoke-test run on `labs`, the onboard and the
  update-config from task 7 succeed.

## Rollback

Each family ships as its own PR:
- smoke-test;
- create-tenant;
- delete-tenant(-safe);
- deploy/provision/retire;
- the validator ban, last.

If a workflow breaks, `git revert` that PR on a branch and open a PR. ArgoCD
restores the previous ClusterWorkflowTemplate in about 3 minutes, and
in-flight workflows keep their submit-time snapshot. Reverting a template PR
after the ban has landed would fail CI. In that case, revert the ban PR
first (its predecessor still blocks new sites through `BASELINE`), or
preferably fix the env binding forward. The interpolated form must not be
reintroduced as a fix. For the smoke-test PR, a jq problem is fixed forward
by switching to the pinned yq + `strenv()` fallback, not by restoring the
here-document.
