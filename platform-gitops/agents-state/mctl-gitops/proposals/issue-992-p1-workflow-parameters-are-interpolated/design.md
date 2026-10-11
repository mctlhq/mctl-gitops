# Design: issue-992-p1-workflow-parameters-are-interpolated

## Current state

**Mechanism.** Argo renders `{{inputs.parameters.X}}` and
`{{workflow.parameters.X}}` as text into `script.source` before the
interpreter runs, so `X="{{inputs.parameters.x}}"` with a value of
`"; cmd; #` runs `cmd`. The safe pattern already exists in the repo:
`cwft-mctl-agents-approve.yaml` (lines ~182-201: `WORKFLOW_SERVICE`,
`WORKFLOW_SLUG`, `WORKFLOW_APPROVER` in `script.env`), and
`tpl-git-commit.yaml` `delete-service` (lines ~675-686, `PARAM_TEAM_NAME` and
so on).

**Already done (gitops#993/#997).**
- `wft-create-tenant.yaml`, the issue's headline site: `display_name` is
  env-bound (lines ~607-637). A `"`/newline check sits at ~717. No
  interpolation of `display_name`/`description` remains in script text.
- `scripts/validate-shell-param-interpolation.py`, run in
  `.github/workflows/validate-manifests.yml:275-276` with `--selftest`. It
  scans `script.source`, `container`/`script` `command`/`args` and
  `initContainers` for `PLACEHOLDER =
  \{\{\s*(?:inputs|workflow)\.parameters\.(...)\s*\}\}`. It fails on any site
  that is neither in `BASELINE` (30 entries) nor named in `CONSTRAINED` (a
  hand-mirrored list of registry-constrained names). It also has
  `check_env_bindings`, which requires every `$PARAM_*` read to be defined in
  the same template's `script.env`.
- `tpl-git-commit.yaml` yq calls go through `strenv()`
  (`validate-yq-interpolation.py`, `tests/test_tpl_git_commit_yq.py`).

**Enumeration (the cross-product the issue asks for).** Produced by running
`scan()` from the validator over the 37 files in `cluster-templates/` and
classifying each hit:

| File / template | Unconstrained (BASELINE), still interpolated | Constrained-by-name, still interpolated |
|---|---|---|
| `tpl-git-commit.yaml` / `commit-service` (lines 58-88, heredocs at 382, 402, 495, 527, 564, 597) | `image_tag`, `port`, `host`, `env_vars`, `secret_env_vars`, `dockerfile_repo`, `service_template`, `config_patch` | `team_name`, `component_name`, `component_type`, `action`, `provision_database`, `clear_env`, `clear_secrets`, `skip_health_check` |
| `tpl-validate-tenant.yaml` / `validate` (54-62, 146-147) | `host`, `dockerfile_repo`, `image_tag`, `git_tag`, `service_template` | `team_name`, `component_name`, `action`, `component_type` |
| `tpl-vault-write.yaml` / `write-service-secrets` (23-25, heredoc at 64) | `secret_env_vars` | `team_name`, `component_name` |
| `tpl-vault-write.yaml` / `write-platform-secret` (240-248) | `json_data`, `vault_path` | none |
| `tpl-vault-write.yaml` / `delete-service-secrets` (264-265) | none | `team_name`, `component_name` |
| `wft-smoke-test.yaml` (`run-onboard` 119-124, `run-deploy` ~201-203, `check-pod-running` 542, and about 14 other check-* templates) | `dockerfile_repo`, `git_tag`, `provision_database_on_onboard`, `previous_generation` | `team_name`, `component_name`, `component_type` |
| `cwft-mctl-agents-{implement,investigate,run,shepherd}.yaml` / `assert-attempt` (implement 1115-1116) | `primary`, `fallback`. Origin traced: `{{steps.<x>.status}}` (implement line ~292), an Argo-controlled phase enum, so not attacker-controlled | none |
| `wft-create-tenant.yaml` (`create-vault-policy`, `wait-for-tenant-ready`) | none | `tenant_name` |
| `wft-delete-tenant-safe.yaml` (4 templates), `wft-delete-tenant.yaml` (2) | none | `tenant_name` |
| `wft-deploy-service.yaml` / `refresh-apps-appset`, `wft-provision-database.yaml` / `do-provision`, `wft-retire-service.yaml` / `cleanup-db-from-gitops` | none | `team_name`, `component_name`, `app_name` |

Other placeholder kinds found in script text are `{{workflow.name}}` and
`{{workflow.labels.*}}` (Argo- or Kubernetes-constrained), plus ESO template
fields `.username`/`.password` in `wft-provision-database.yaml`, which are
not Argo placeholders. No `{{=...}}` expression form appears in script text
today, but the validator regex would not catch one.

**Heredoc sub-class.** `tpl-git-commit.yaml` (`ENVEOF`, `SECRETEOF`,
`ENVEOF3`, `SECRETEOF3`, and the update-config pair) and `tpl-vault-write.yaml`
(`SECRETS_EOF`) splice the free-form parameter into the body of a quoted
here-document. Quoting stops `$` expansion, but a value containing a line
equal to the terminator ends the document, and the lines after it run as
shell. `tests/test_tpl_git_commit_yq.py` extracts the env_vars loop with a
regex anchored on `done << 'ENVEOF'`, so it has to follow the conversion.

**Smoke-test YAML splice.** `wft-smoke-test.yaml` `run-onboard`/`run-deploy`
also splice `${REPO}`, `${GIT_TAG}` and similar into an unquoted heredoc
manifest piped to `kubectl create -f -`. Env-binding removes the shell
injection, but the manifest is still assembled from text.

Deployed state checked:
- `mctl_get_operation deploy-service`: `minRole: developer`. `team_name` and
  `component_name` have patterns (`^[a-z0-9][a-z0-9-]{0,30}$`); `action`,
  `component_type`, `clear_*`, `provision_database`, `skip_health_check` and
  `autoscaling_enabled` are enums. `dockerfile_repo`, `git_tag`, `port`,
  `host`, `env_vars`, `secret_env_vars`, `health_check_path`,
  `dockerfile_path`, `image_tag`, `min/max_replicas`, `cpu_threshold` and
  `service_template` have **no pattern and no enum**. The baselined sites are
  therefore reachable by any developer today.
- `mctl_get_operation create-tenant`: `minRole: authenticated`; only
  `tenant_name` (`^[a-z0-9][a-z0-9-]{1,62}$`) and `allow_internet_egress`
  (enum) are constrained. This matches the issue. The template side is
  already fixed in this clone.
- `python3 scripts/validate-shell-param-interpolation.py` on the clone:
  passes, "30 known sites remain". `--selftest` passes.
- Not checked: whether `wft-smoke-test` and `write-platform-secret` are
  exposed as operations (neither looked up), and the mctl-api registry source
  itself (a different repo, not in this clone). Both are recorded in Open
  questions.

## Proposed solution

Close the class mechanically, then make the validator a hard ban so it stays
closed.

1. **Convert every remaining site to env binding**, following the
   `delete-service` pattern. Each template gets
   `script.env: - name: PARAM_<UPPER> value: "{{inputs.parameters.<x>}}"`, and
   the script assigns `X="$PARAM_<UPPER>"`. Existing variable names inside the
   scripts (`TEAM`, `HOST`, `TAG`, ...) stay, so only the prelude lines change.
   Where a template already has `env:` (for example `tpl-git-commit`
   `HEALTH_CHECK_PATH`, the `tpl-vault-write` `VAULT_ADDR`), append to it.
   `check_env_bindings` catches a binding placed on the wrong template
   (the gitops#993 regression).
   - `tpl-git-commit.yaml` `commit-service`: all 16 params, plus the late
     `SKIP_HEALTH` assignment at line 88.
   - `tpl-validate-tenant.yaml` `validate`: all 9, including the second
     `GIT_TAG`/`IMG_OVERRIDE` read at 146-147, which becomes
     `"$PARAM_GIT_TAG"`/`"$PARAM_IMAGE_TAG"`.
   - `tpl-vault-write.yaml`: `write-service-secrets` and
     `delete-service-secrets` get the same prelude. `write-platform-secret`
     binds `PARAM_VAULT_PATH` and `PARAM_JSON_DATA`, rejects a `vault_path`
     that is multi-line, contains `..`, starts with `/` or falls outside
     `[A-Za-z0-9/_-]`, and sends the body with
     `printf '{"data":%s}' "$PARAM_JSON_DATA" | curl --data-binary @- ...`.
   - The other `wft-*` templates listed above (constrained names only):
     convert as well. Registry patterns are a claim about another repo, and
     the issue states that env binding must hold "regardless of what reaches
     the template".
   - `assert-attempt` (4 files): bind `PARAM_PRIMARY`/`PARAM_FALLBACK`.
     This is trivial and removes the last baseline entries.
   - `wft-smoke-test.yaml`: bind every `workflow.parameters.*`/
     `inputs.parameters.*` read. For the child-workflow manifests, write a
     static manifest with empty values, fill them with `yq -i
     '... = strenv(PARAM_X)'` (`alpine/k8s` ships yq; confirm during
     implementation, otherwise build the manifest as JSON with `jq --arg`),
     then `kubectl create -f`.

2. **Fix the heredocs.** Replace the
   `done << 'ENVEOF'\n{{inputs.parameters.env_vars}}\nENVEOF` shape with an
   unquoted here-document whose body is only the variable:
   ```sh
   done <<ENVEOF
   $PARAM_ENV_VARS
   ENVEOF
   ```
   The shell expands the parameter once and never re-parses the result, so
   neither a terminator line nor `$(...)` inside the value has any effect. A
   pipe (`printf ... | while`) was rejected because it runs the loop in a
   subshell, and `tpl-vault-write` `write-service-secrets` accumulates
   `JSON_DATA` inside the loop. Update the regex in
   `tests/test_tpl_git_commit_yq.py` to the new terminator form.

3. **Harden the validator into a ban** (`scripts/validate-shell-param-interpolation.py`):
   - Delete `BASELINE` and `CONSTRAINED`. Any hit fails.
   - Widen `PLACEHOLDER` to also catch `{{=` expression forms that mention
     `inputs.parameters`/`workflow.parameters`.
   - Also scan `sidecars[*]` and `containerSet.containers[*]`
     `command`/`args`, and their `env`, in `check_env_bindings`. None exist
     today, so this closes a gap without changing behaviour.
   - Extend `--selftest` with a heredoc-body case and a `{{=` case.

4. **Executable reproduction, the issue's acceptance**
   (`tests/test_shell_param_injection.py`, wired into `validate-manifests.yml`
   next to `test_tpl_git_commit_yq.py`):
   - Control: render `X="{{inputs.parameters.p}}"` with the payload
     `"; touch $CANARY; #` and run it under `sh`. The canary **must** appear.
     This proves the harness can detect injection.
   - For each converted template (`tpl-git-commit/commit-service`,
     `tpl-validate-tenant/validate`, `tpl-vault-write/*`, and one
     `wft-smoke-test` template), load the YAML. Render `script.source` the way
     Argo does by replacing every `{{inputs|workflow.parameters.X}}` with the
     payload, and render each `env[].value` the same way. Extract the
     parameter prelude: the lines up to the first network or `apk` call,
     taken from the template rather than copied, as
     `test_tpl_git_commit_yq.py` already does. Run it with the rendered env
     and assert the canary is absent. Payloads: `"; touch $C; #`,
     `'; touch $C; #`, `$(touch $C)`, `` `touch $C` ``, and
     `x\nENVEOF\ntouch $C`.
   - Run the env_vars and secret_env_vars loops (the shape already extracted
     in `test_tpl_git_commit_yq.py`) with the terminator payload, and assert
     the canary is absent while valid `KEY=value` lines are still written.

5. **Follow-ups filed, not implemented here**: an mctl-api registry
   `pattern` issue, and a `when:`-expression injection issue (see
   requirements Open questions).

## Alternatives

- **Registry patterns only (mctl-api).** Rejected as the primary fix. It
  lives in another repo, it cannot cover free-form `env_vars`/`json_data`,
  and it leaves every other submission path (Backstage, direct
  `argo submit`, templates calling templates) unprotected. The issue itself
  calls it defence in depth.
- **Keep the ratchet with `CONSTRAINED` and convert only the 30 BASELINE
  sites.** Smaller diff, but "constrained" is a name-matched claim about
  another repository's code. A template parameter called `team_name` that a
  different caller feeds is exempted silently. The issue warns that patching
  named sites "leaves the class open". Rejected.
- **Shell-escape values in Argo with a sprig expression** (for example
  `{{=sprig.squote(...)}}`). Argo expression templates and sprig quoting do
  not reliably escape an embedded single quote for POSIX sh, so this keeps
  the value in the script text. Rejected.
- **Pass parameters as files (input artifacts or `raw` artifacts).** This
  works, but it is heavier, and it diverges from the in-repo `env:` pattern
  for no gain.

## Platform impact

- **Migration:** none. These are template-only changes. ArgoCD syncs
  ClusterWorkflowTemplates in about 3 minutes. Workflows already submitted
  keep the snapshot taken at submit time.
- **Backward compatibility:** parameter names and outputs are unchanged.
  The `auto`/`none`/`__CLEAR__` sentinel handling is kept as is.
  - One behaviour change: inside a here-document the old form passed the
    value through the YAML block's indentation, so lines 2+ of a multi-line
    `env_vars` carried the template's 10-space indent. The new form passes
    the raw value. The loops already `xargs`-trim keys and values, so the
    output is the same, and the yq test checks this.
  - A deliberate change: values that contain `"` or `$` were previously
    mangled or executed, and now arrive verbatim.
- **Risks and mitigations:**
  - *A binding goes on the wrong template, or is missing.*
    `check_env_bindings` already fails CI, and the new test runs each
    prelude.
  - *Smoke-test manifest construction regresses.* Run `wft-smoke-test` once
    after the merge, before the deploy-service changes are relied on (see
    tasks).
  - *The deploy path breaks for every tenant.* Merge the conversion as one PR
    per template family (tpl-validate-tenant, tpl-git-commit,
    tpl-vault-write; then the rest), and run one onboard and one
    update-config smoke after each.
  - *Environment size:* `env_vars` and `secret_env_vars` are small, well
    below the pod env limits. `secret_env_vars` in an env var is visible in
    the pod spec. That is no worse than today, because the value is already
    in the rendered script source of the same pod spec, and mctl-api already
    prefers `secret_env_secret` (`write-service-secrets-from-secret`).
- **Resource impact:** none.
