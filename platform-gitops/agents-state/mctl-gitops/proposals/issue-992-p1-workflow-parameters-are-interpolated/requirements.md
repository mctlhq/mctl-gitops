# Remove workflow-parameter interpolation from ClusterWorkflowTemplate script text

## Context

Argo substitutes `{{inputs.parameters.X}}` / `{{workflow.parameters.X}}` into
the text of a `script.source` (or a `command`/`args` string) before `sh`
parses it, so a value containing `";` runs as a command. These pods run as
root and mount `mctl-gitops-deploy-key` (write access to this repo), a Vault
token, or both. Issue #992 asks for the whole class to be enumerated and
closed, with a test showing that a `";` payload does not execute.

Part of the work is already merged (gitops#993/#997). `wft-create-tenant.yaml`
now binds `display_name`/`description` through `env:`, and
`scripts/validate-shell-param-interpolation.py`, run in
`validate-manifests.yml`, is a ratchet: it fails on any new interpolation. It
still allows 30 baselined `(file, template, parameter)` sites, and it skips
any parameter whose *name* is in a hand-kept `CONSTRAINED` set. The baselined
sites that remain are reachable today. The live registry (`mctl_get_operation
deploy-service`, `minRole: developer`) puts no `pattern` on `host`, `git_tag`,
`image_tag`, `dockerfile_repo`, `port`, `service_template`, `env_vars` or
`secret_env_vars`. All of them are interpolated into `tpl-validate-tenant`,
`tpl-git-commit` and `tpl-vault-write`. This proposal removes the remaining
interpolation. It also turns the ratchet into a hard ban and adds an
executable reproduction.

## User stories

- AS a platform operator I WANT every workflow parameter to reach a shell only as an environment variable SO THAT no API caller can run commands in a pod that holds the gitops deploy key or a Vault token.
- AS a reviewer of cluster templates I WANT CI to fail on any `{{...parameters...}}` placeholder in script text SO THAT a template that looks right cannot quietly reopen the hole.
- AS a developer calling `deploy-service` I WANT onboard, deploy and update-config to behave exactly as they do today for legitimate input SO THAT the fix causes no regressions.

## Acceptance criteria (EARS)

- WHEN any ClusterWorkflowTemplate under `platform-gitops/argo-workflows/cluster-templates/` is changed THE SYSTEM SHALL fail CI if any `script.source`, `container`/`script` `command`/`args` string, or `initContainers` `command`/`args` string contains an `{{inputs.parameters.*}}` or `{{workflow.parameters.*}}` placeholder (the `{{=...}}` expression form included), with no baseline and no name-based exemption.
- WHEN `tpl-git-commit` `commit-service`, `tpl-validate-tenant` `validate`, `tpl-vault-write` `write-service-secrets` / `write-platform-secret`, `wft-smoke-test` (all script templates) or the `assert-attempt` templates of `cwft-mctl-agents-{implement,investigate,run,shepherd}` run THE SYSTEM SHALL read every input parameter from a `PARAM_*` environment variable bound in that template's own `script.env`.
- WHEN `env_vars` or `secret_env_vars` is parsed line by line THE SYSTEM SHALL feed the loop from the environment variable (for example an unquoted here-document containing only `$PARAM_ENV_VARS`), not from a here-document whose body is the substituted parameter text.
- IF a parameter value contains `"`, `'`, `;`, `$(...)`, a backtick, a newline, or a line equal to a here-document terminator (`ENVEOF`, `SECRETEOF`, `SECRETS_EOF`, and so on) THEN THE SYSTEM SHALL treat it as data, and no command in it SHALL run.
- WHEN the test suite runs THE SYSTEM SHALL execute a checked-in reproduction. It renders each converted template's script the way Argo does, with injection payloads (`"; touch $CANARY; #`, `'; touch $CANARY; #`, `$(touch $CANARY)`, and a here-document terminator followed by `touch $CANARY`), runs the parameter-reading prelude under `sh`, and asserts the canary file does not exist. A control case on the old interpolated form asserts the canary does exist.
- WHILE a script reads a `PARAM_*` variable THE SYSTEM SHALL have that variable defined in the same template's `env` (already enforced by `check_env_bindings`, kept).
- WHEN `tpl-vault-write` `write-platform-secret` builds its request body and URL THE SYSTEM SHALL take `json_data` and `vault_path` from the environment. `vault_path` SHALL be shape-checked (no `..`, no leading `/`, `[A-Za-z0-9/_-]` only) before it is used in a URL.
- WHEN `wft-smoke-test` builds a child Workflow manifest from its parameters THE SYSTEM SHALL write the values into the manifest as data (env-bound and inserted with `yq` `strenv()`), not by splicing `${VAR}` into YAML text.
- WHEN legitimate inputs are supplied (existing fixtures, `auto`/`none`/`__CLEAR__` sentinels, a multi-line `env_vars`) THE SYSTEM SHALL produce the same outputs as before: `/tmp/service_dir`, `/tmp/component_type`, `/tmp/image_tag`, the `values.yaml` edits and the Vault payload.

## Out of scope

- Expression injection in `when:` conditions (for example `wft-deploy-service.yaml` `write-secrets`, which compares `"{{workflow.parameters.secret_env_vars}}"` with `""`). This is a separate class, govaluate rather than shell. It is recorded under Open questions for a follow-up issue.
- YAML injection into `resource.manifest` templates, and into Helm values beyond what `validate-yq-interpolation.py` already covers.
- Adding `pattern` constraints in `mctl-api`'s `internal/operations/registry.go`. That is a different repository and is defence in depth only. A follow-up issue there is recommended (see Open questions).
- gitops#983 (agent-side worktree/root/deploy-key blast radius).
- Running containers as non-root or narrowing the deploy key's scope.

## Open questions

- Should `mctl-api` get registry patterns for `host`, `git_tag`, `image_tag`, `dockerfile_repo`, `port` and `service_template` (deploy-service), and for `display_name`/`description`/`contact_email` (create-tenant)? Recommended as a separate mctl-api issue. This proposal does not depend on it.
- `when:` expression interpolation of free-form parameters (`secret_env_vars` in `wft-deploy-service.yaml`): file a follow-up issue, or fold a minimal fix into this one? Assumed: follow-up issue.
- `write-platform-secret` has no caller anywhere in this repo (grep finds only the template and the validator baseline). Should it be deleted rather than converted? Assumed: convert it, because mctl-api may submit it directly and the clone cannot show that. Delete it only if the maintainer confirms it is unused.
- `wft-smoke-test` parameters: it is unclear whether the smoke test can be submitted by non-admins through the operations API, because it was not visible in the operations checked. It is converted regardless.
