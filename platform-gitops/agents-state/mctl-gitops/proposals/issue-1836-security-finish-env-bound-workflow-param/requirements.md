# Finish env-bound workflow parameters: wft-smoke-test, constrained-name sites, validator ban (#992 tasks 6-8, 10)

## Context

gitops#992 found that Argo substitutes `{{inputs.parameters.X}}` and
`{{workflow.parameters.X}}` into the text of a `script.source` before the
shell parses it. A value with a quote and a semicolon therefore runs as a
command in pods that hold the gitops deploy key, a Vault token or a GitHub
PAT. The accepted #992 proposal
(`platform-gitops/agents-state/mctl-gitops/proposals/issue-992-p1-workflow-parameters-are-interpolated/`)
fixed this by binding every parameter through `script.env` as `PARAM_*`, and
by turning `scripts/validate-shell-param-interpolation.py` into a ban. Its
first slice (#1812) shipped tasks 1-5: the harness
`tests/test_shell_param_injection.py` and the conversion of
`tpl-validate-tenant`, `tpl-git-commit`, `tpl-vault-write` and the
`assert-attempt` templates.

This issue (#1836) covers what is left. It reuses the #992 design and the
#1812 harness and does not re-derive them. On main today the validator scan
still finds 26 templates that interpolate a parameter: 15 in
`wft-smoke-test.yaml` (6 of those sites are in `BASELINE`, the rest pass only
because the names are in `CONSTRAINED`) and 11 constrained-name templates
across six other `wft-*` files. Once every site is converted, the validator
loses `BASELINE` and `CONSTRAINED` and becomes an unconditional ban. A live
smoke run after the merge confirms the deploy path still works.

## User stories

- AS a platform operator I WANT every workflow parameter to reach the shell
  as data, never as script text, SO THAT a crafted parameter value cannot
  execute in a pod that holds platform credentials, whatever the API
  accepts.
- AS a platform operator I WANT `wft-smoke-test` to build its child Workflow
  manifests from structured data SO THAT a parameter value cannot inject
  YAML keys or extra parameters into a child Workflow.
- AS a reviewer I WANT CI to reject any parameter placeholder in any shell
  block, with no allow-list, SO THAT the class stays closed without anyone
  having to keep a list of names in sync with another repository.
- AS an operator I WANT one live smoke run, one onboard and one update-config
  after the merge SO THAT I know the conversion did not break the deploy
  path.

## Acceptance criteria (EARS)

- WHEN any script template in `wft-smoke-test.yaml` runs THE SYSTEM SHALL
  read every `workflow.parameters.*` and `inputs.parameters.*` value from a
  `PARAM_*` variable in that template's `script.env`. No
  `{{inputs|workflow.parameters.*}}` placeholder SHALL remain in its
  `script.source`.
- WHEN `run-onboard`, `run-deploy`, `run-update-config`, `run-provision-db`
  or `run-retire` submits a child Workflow THE SYSTEM SHALL build the
  manifest with `jq -n --arg` from a static jq program, never by expanding a
  shell variable into YAML or JSON text, and SHALL submit it with
  `kubectl create -f <file>`.
- WHEN a smoke-test parameter carries a quote, a newline, `$(...)`, a
  backtick or a YAML fragment THE SYSTEM SHALL put that exact string in the
  matching child `arguments.parameters[].value` and SHALL NOT add or change
  any other key.
- IF `check-pod-running` receives a `previous_generation` that is not a
  non-negative integer THEN THE SYSTEM SHALL fail the step before it calls
  `kubectl`.
- WHEN any of the 11 constrained-name templates runs (`wft-create-tenant`
  `create-vault-policy` and `wait-for-tenant-ready`; `wft-delete-tenant-safe`
  `retire-tenant-services`, `delete-tenant-from-git`, `delete-vault-policy`
  and `cleanup-tenant-db-from-gitops`; `wft-delete-tenant`
  `delete-tenant-from-git` and `delete-vault-policy`; `wft-deploy-service`
  `refresh-apps-appset`; `wft-provision-database` `do-provision`;
  `wft-retire-service` `cleanup-db-from-gitops`) THE SYSTEM SHALL read
  `tenant_name`, `team_name`, `component_name` and `app_name` from `PARAM_*`
  env bindings.
- WHEN `tests/test_shell_param_injection.py` runs the #992 T2 payloads
  (`"; touch $C; #`, `'; touch $C; #`, `$(touch $C)`, `` `touch $C` ``, a
  terminator-line payload) against at least one `wft-smoke-test` template
  and one template from each converted task-7 file THE SYSTEM SHALL leave
  no canary file.
- WHEN `scripts/validate-shell-param-interpolation.py` runs on the repo THE
  SYSTEM SHALL fail on any parameter placeholder in any shell block. The
  script SHALL contain no `BASELINE` and no `CONSTRAINED`.
- WHEN a shell block contains a `{{= ... }}` expression that mentions
  `inputs.parameters` or `workflow.parameters` THE SYSTEM SHALL report it as
  a violation.
- WHEN a template declares `sidecars` or `containerSet.containers` THE SYSTEM
  SHALL scan their `command` and `args`. `check_env_bindings` SHALL check
  their `env` and the `container.env` of container templates.
- WHEN `validate-shell-param-interpolation.py --selftest` runs THE SYSTEM
  SHALL show that the detector fires on `script.source`, an inline
  `command`, a here-document body, a `{{=` expression, a `sidecars` arg, a
  `containerSet` arg and an unbound `PARAM_*`.
- WHILE the change is rolled out THE SYSTEM SHALL keep passing the existing
  suites: `test_tpl_git_commit_yq.py`, `test_wft_create_tenant_existing.py`,
  `test_wft_provision_database_values.py`, `test_wft_retire_service_guard.py`,
  `validate-yq-interpolation.py` and `test_shell_param_injection.py`.
- WHEN the last PR is merged and ArgoCD has synced THE SYSTEM SHALL complete
  one `smoke-test` run with `team_name=labs`, one `deploy-service` onboard and
  one `update-config` with a multi-line `env_vars` and `secret_env_vars`.

## Out of scope

- Task 9 of #992, the API-side registry patterns. This is tracked in
  mctlhq/mctl-api#559.
- Argo `when:` (govaluate) expressions that interpolate parameters, for
  example `wft-smoke-test.yaml` `verify-db-wiring`
  `when: "{{workflow.parameters.provision_database_on_onboard}} == true"`.
  They are not shell, and the validator does not scan them. This was the
  second follow-up in #992 task 9.
- Placeholders that are not parameters: `{{workflow.name}}`,
  `{{workflow.namespace}}`, `{{workflow.labels.*}}`, and
  `{{steps|tasks.*.outputs.*}}` used directly in shell text. The ban covers
  `inputs.parameters` and `workflow.parameters` only, as #992 defined it.
- Changing the `smoke-test` operation entry in mctl-api (it declares no
  parameters).
- Re-deriving the #992 design or rewriting the #1812 harness.

## Open questions

- **Which team does the T10 smoke run use?** The template defaults to
  `team_name: tests`, and the registry entry says "Runs in the tests team"
  with no parameters. `mctl_get_tenant tests` returns "tenant not found", and
  there is no `services/tests/` or `tenants/tests/` in gitops. The issue says
  to run on `labs`. This proposal assumes the operator submits the
  ClusterWorkflowTemplate directly with `-p team_name=labs`. Changing the
  template default from `tests` to `labs` is left to the reviewer. It is not
  part of this change, so that the security PRs carry no behaviour change.
- Whether the `tests` namespace still exists in the cluster (outside the
  tenant registry) could not be observed with the read-only tools.
- `jq` in `alpine/k8s:1.33.12` is inferred from in-repo usage
  (`cwft-mctl-agents-shepherd.yaml` uses `jq --arg` in an `alpine/k8s:1.33.12`
  step at line ~1222). The first PR's live run confirms it. If it is absent,
  fall back to the pinned, sha256-checked yq download that
  `wft-provision-database.yaml` already uses.
- Whether the #992 follow-up issue for `when:` interpolation was filed could
  not be checked from this clone.
