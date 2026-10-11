# Tasks: issue-992-p1-workflow-parameters-are-interpolated

- [ ] 1. Add `tests/test_shell_param_injection.py` with the control case: the old `X="{{inputs.parameters.p}}"` form rendered with `"; touch $CANARY; #` creates the canary under `sh`. Add a generic helper that renders a template's `script.source` and `script.env` values the way Argo does (text replacement of `{{inputs|workflow.parameters.X}}`) and runs a prelude extracted from the template. Wire the test into `.github/workflows/validate-manifests.yml` next to `test_tpl_git_commit_yq.py`. — DoD: the control case passes and the harness proves it can detect injection.
- [ ] 2. Convert `tpl-validate-tenant.yaml` `validate` (lines 54-62 and 146-147) to `PARAM_*` env bindings for all 9 parameters. Remove its entries from `BASELINE`. (depends on 1) — DoD: no placeholder left in its `script.source`; the validator and `check_env_bindings` pass; the injection test covers `validate` with all payloads and the canary is absent; `/tmp/image_tag` output is unchanged for `git_tag=v1.2.3`, `image_tag=auto` and an explicit override.
- [ ] 3. Convert `tpl-git-commit.yaml` `commit-service`: bind all 16 parameters, including the late `SKIP_HEALTH`, appended to the existing `env:` that holds `HEALTH_CHECK_PATH`. Replace all six quoted here-documents (`ENVEOF`, `SECRETEOF`, `ENVEOF3`, `SECRETEOF3` and the update-config pair) with unquoted here-documents whose body is only `$PARAM_ENV_VARS` / `$PARAM_SECRET_ENV_VARS`. Update the extraction regex in `tests/test_tpl_git_commit_yq.py`. (depends on 1) — DoD: no placeholder in `commit-service`; `test_tpl_git_commit_yq.py` passes; the injection test runs the env/secret loops with a terminator-line payload, the canary is absent and valid keys are still written.
- [ ] 4. Convert `tpl-vault-write.yaml`: `write-service-secrets` (prelude plus the `SECRETS_EOF` here-document), `delete-service-secrets`, and `write-platform-secret` (bind `PARAM_VAULT_PATH`/`PARAM_JSON_DATA`, shape-check `vault_path`, send the body with `printf ... | curl --data-binary @-`). (depends on 1) — DoD: no placeholder in any template; the injection test covers `write-service-secrets`; a `vault_path` containing `..` or a newline is rejected.
- [ ] 5. Convert the `assert-attempt` template in `cwft-mctl-agents-{implement,investigate,run,shepherd}.yaml` to `PARAM_PRIMARY`/`PARAM_FALLBACK`. — DoD: the baseline entries are removed and the validator passes.
- [ ] 6. Convert every script template in `wft-smoke-test.yaml`. Build the child Workflow manifests in `run-onboard`/`run-deploy`/`run-update-config`/`run-provision-db`/`run-retire` from a static skeleton filled with `yq ... strenv()`, or `jq --arg` if `alpine/k8s:1.33.12` lacks yq. Never splice `${VAR}` into YAML text. (depends on 1) — DoD: no placeholder in the file; one manual `wft-smoke-test` run succeeds end to end.
- [ ] 7. Convert the remaining constrained-name sites: `wft-create-tenant.yaml` (`create-vault-policy`, `wait-for-tenant-ready`), `wft-delete-tenant-safe.yaml` (4 templates), `wft-delete-tenant.yaml` (2), `wft-deploy-service.yaml` `refresh-apps-appset`, `wft-provision-database.yaml` `do-provision`, `wft-retire-service.yaml` `cleanup-db-from-gitops`. — DoD: `scan()` returns no hits at all across `cluster-templates/`.
- [ ] 8. Turn `scripts/validate-shell-param-interpolation.py` into a ban: delete `BASELINE` and `CONSTRAINED`; widen `PLACEHOLDER` to `{{=` expressions that mention `inputs.parameters`/`workflow.parameters`; scan `sidecars` and `containerSet.containers` `command`/`args` (and their `env` in `check_env_bindings`); add selftest cases for a here-document body and a `{{=` expression; update the docstring. (depends on 2-7) — DoD: `--selftest` and the full run pass, and adding any placeholder to any script fails CI.
- [ ] 9. File two follow-up issues: mctl-api `registry.go` patterns for `host`/`git_tag`/`image_tag`/`dockerfile_repo`/`port`/`service_template` and the create-tenant free-text fields; and govaluate `when:` interpolation of free-form parameters (e.g. `wft-deploy-service.yaml` `write-secrets`). — DoD: both issues exist and are linked from #992.
- [ ] 10. After each merge, wait about 3 minutes for ArgoCD to sync, then run one `deploy-service` onboard and one `update-config` (with a multi-line `env_vars` and `secret_env_vars`) against a test tenant. — DoD: both succeed, and the resulting `values.yaml` and Vault data match what the pre-change templates produced.

## Tests

- [ ] T1. Control: interpolated form plus a `";` payload creates the canary (the harness is live).
- [ ] T2. For `tpl-validate-tenant/validate`, `tpl-git-commit/commit-service`, `tpl-vault-write/write-service-secrets` and one `wft-smoke-test` template, each payload (`"; touch $C; #`, `'; touch $C; #`, `$(touch $C)`, `` `touch $C` ``, `x\nENVEOF\ntouch $C`) leaves no canary.
- [ ] T3. env_vars and secret_env_vars loops: the terminator-line payload does not execute, and the legitimate `KEY=value` lines are still applied (extends `test_tpl_git_commit_yq.py`).
- [ ] T4. `validate-shell-param-interpolation.py --selftest`: fires on `script.source`, inline `command`, a here-document body, a `{{=` expression, and an unbound `PARAM_*`.
- [ ] T5. `validate-shell-param-interpolation.py` passes on the repo with no baseline.
- [ ] T6. Existing suites still pass: `test_tpl_git_commit_yq.py`, `test_wft_create_tenant_existing.py`, `test_wft_provision_database_values.py`, `test_wft_retire_service_guard.py`, `validate-yq-interpolation.py`.
- [ ] T7. Manual: a `wft-smoke-test` run and a deploy-service onboard plus update-config succeed after deploy.

## Rollback

Each template family ships as its own PR. If a deploy path breaks, revert
that PR with `git revert` on a branch plus a PR; ArgoCD restores the previous
ClusterWorkflowTemplate in about 3 minutes, and in-flight workflows keep
their submit-time snapshot. The validator ban (task 8) lands last. If it has
to be reverted on its own, the ratchet version comes back and still blocks
new sites. The interpolated form must not be reintroduced to fix a
regression: fix the env binding forward.
