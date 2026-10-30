# Design: issue-1836-security-finish-env-bound-workflow-param

## Current state

**What #1812 shipped.** `tpl-validate-tenant`, `tpl-git-commit`,
`tpl-vault-write` and the four `assert-attempt` templates are env-bound.
`tests/test_shell_param_injection.py` does the following:
- holds a `CASES` list of `(file, template, stop-line)`;
- renders `script.env` values the way Argo does, using regex `PH`
  (`\{\{(?:inputs|workflow)\.parameters\.(...)\}\}`, no whitespace
  tolerance);
- runs the prelude up to the stop line under `sh` with five payloads and
  asserts the canary is absent;
- runs a control case that proves the harness detects injection.

CI runs it in `.github/workflows/validate-manifests.yml:472`. The validator
runs at `validate-manifests.yml:275-276` (`--selftest`, then the full run).

**Validator today** (`scripts/validate-shell-param-interpolation.py`, 235
lines):
- `PLACEHOLDER` matches only `{{ inputs|workflow.parameters.X }}`.
- `shell_blocks()` scans `script.source`, the `command`/`args` of
  `container`/`script`, and `initContainers`. It does not scan `sidecars` or
  `containerSet`.
- `check_env_bindings()` checks only `script.env` against `$PARAM_*` and
  `os.environ["PARAM_*"]` reads in `script.source`.
- `BASELINE` has 6 entries, all in `wft-smoke-test.yaml`: `run-onboard`
  `dockerfile_repo`/`git_tag`/`provision_database_on_onboard`, `run-deploy`
  `dockerfile_repo`/`git_tag`, and `check-pod-running`
  `previous_generation`.
- `CONSTRAINED` is a 23-name allow-list mirrored from mctl-api.
- `main()` passes on "6 known sites remain". `--selftest` covers
  `script.source`, an inline command and an unbound `PARAM_*`.

**Full scan on main.** Running `scan()` over `cluster-templates/` finds 26
templates:

| File | Templates | Parameters |
|---|---|---|
| `wft-smoke-test.yaml` | `run-onboard`, `run-deploy` | `team_name`, `component_name`, `component_type`, `dockerfile_repo`, `git_tag` (+ `provision_database_on_onboard` in onboard) |
| `wft-smoke-test.yaml` | `run-update-config`, `run-retire` | `team_name`, `component_name`, `component_type` |
| `wft-smoke-test.yaml` | `run-provision-db`, `trigger-argocd-sync`, `check-vault-app-secret`, `check-app-externalsecret`, `check-deploy-env-and-secret`, `check-vault-secret`, `check-k8s-secret`, `check-db-secret-wiring`, `check-env-var`, `check-retired` | `team_name`, `component_name` |
| `wft-smoke-test.yaml` | `check-pod-running` | `team_name`, `component_name`, `previous_generation` |
| `wft-create-tenant.yaml` | `create-vault-policy` (l.518), `wait-for-tenant-ready` (l.1025) | `tenant_name` |
| `wft-delete-tenant-safe.yaml` | `retire-tenant-services`, `delete-tenant-from-git`, `delete-vault-policy`, `cleanup-tenant-db-from-gitops` (l.238/383/535/622) | `tenant_name` |
| `wft-delete-tenant.yaml` | `delete-tenant-from-git`, `delete-vault-policy` (l.216/277) | `tenant_name` |
| `wft-deploy-service.yaml` | `refresh-apps-appset` (l.403-404) | `team_name`, `component_name` |
| `wft-provision-database.yaml` | `do-provision` (l.72-73) | `team_name`, `app_name` |
| `wft-retire-service.yaml` | `cleanup-db-from-gitops` (l.322-323) | `team_name`, `component_name` |

No `{{=` expression appears anywhere in `cluster-templates/`. No template
uses `sidecars` or `containerSet`. The only hit for those words is a comment
in `tpl-git-commit.yaml:492`.

**Smoke-test YAML splice.** `run-onboard` (l.~119-160), `run-deploy`,
`run-update-config`, `run-provision-db` and `run-retire` each assign
`TEAM="{{workflow.parameters.team_name}}"` and similar. They then pipe an
unquoted here-document Workflow manifest into
`kubectl create -n argo-workflows -o jsonpath='{.metadata.name}' -f -`, with
`value: "${REPO}"` and the other values spliced into YAML text. Env binding
alone removes the shell injection. It does not stop a value with `"` or a
newline from rewriting the child manifest, for example by adding a
`- {name: host, ...}` entry. `run-onboard`/`run-deploy` already bind
`PARAM_DOCKERFILE_PATH` and `SMOKE_RUN` (`{{workflow.name}}`) via `env:`.
`run-deploy` writes `/tmp/previous-generation` from `kubectl`. That file
feeds `check-pod-running` `inputs.parameters.previous_generation`, which is
used in `[ ... -gt 0 ]` at l.~613. Images: `alpine/k8s:1.33.12` (bash) for
most templates; `alpine:3.19` (sh, `apk add curl`) for
`check-vault-app-secret` and `check-vault-secret`.

**Tool availability.** `jq --arg` already runs in an `alpine/k8s:1.33.12`
step (`cwft-mctl-agents-shepherd.yaml`, image at l.1222, jq at l.1295).
`wft-provision-database.yaml` downloads a pinned yq with a sha256 check, but
that step runs on `alpine:3.19` (l.~49), so it says nothing about yq in
`alpine/k8s`.

**Tests that touch task-7 files.**
- `test_wft_create_tenant_existing.py` already models
  `TENANT="$PARAM_TENANT_NAME"` (l.88) and anchors on
  `TENANT_DIR=`/`# BEGIN tenant-ns-guard` markers.
- `test_wft_provision_database_values.py` anchors on `SVC_VALUES=` and
  injects its own `TEAM=labs\nAPP=demo` prelude (l.42-47).
- `test_wft_retire_service_guard.py` asserts `{{` is absent from
  `argocd-app-guard`.

None of these anchors sits on the lines being changed.

Deployed state checked:
- `scan()` from `scripts/validate-shell-param-interpolation.py` run on the
  clone: the 26 templates in the table above. The validator passes with
  "6 known sites remain". `--selftest` passes.
  `tests/test_shell_param_injection.py` passes.
- `mctl_get_operation smoke-test`: `minRole: admin`, `parameters: []`,
  description "Runs in the tests team". The API cannot override
  `team_name`, so via the API every run uses the template defaults.
- `mctl_get_tenant tests`: error "tenant not found: tests".
  `$MCTL_GITOPS_ROOT/tenants/` lists admins, commerce-proof, erpact, karabu,
  labs and mctl, with no `tests`. `services/` has no `tests/`. Whether a
  `tests` namespace exists in the cluster could not be observed.
- `mctl_get_tenant labs`: exists, `allowInternetEgress: true`, pods quota
  30, 19 services. `smoke-test-svc` is not present, so there is no
  collision.
- `mctl_get_operation deploy-service`: `team_name`, `component_name`,
  `dockerfile_repo`, `git_tag`, `host`, `port`, `env_vars`, `image_tag`,
  `dockerfile_path` and others now carry anchored patterns. `secret_env_vars`
  has only `maxLength`. This is defence in depth from the API side, and it
  does not replace template-side binding.

## Proposed solution

The #992 design is kept unchanged. The work follows #992 tasks 6, 7, 8 and 10
as separate PRs, with the ban last.

### 1. `wft-smoke-test.yaml` (task 6)

**Prelude conversion (all 15 templates).** Each template gets the bindings
it reads, appended to an existing `env:` where one exists (for example the
`VAULT_ADDR` entries on the two `alpine:3.19` checks, and
`PARAM_DOCKERFILE_PATH`/`SMOKE_RUN` on onboard/deploy):

```yaml
env:
  - name: PARAM_TEAM_NAME
    value: "{{workflow.parameters.team_name}}"
  - name: PARAM_COMPONENT_NAME
    value: "{{workflow.parameters.component_name}}"
```

Each prelude line becomes `TEAM="$PARAM_TEAM_NAME"`, and so on. Script
variable names (`TEAM`, `SVC`, `REPO`, `COMPONENT_TYPE`, `GIT_TAG`,
`PROVISION_DB`) stay the same, so the bodies do not change.

`check-pod-running` binds `PARAM_PREVIOUS_GENERATION` from
`{{inputs.parameters.previous_generation}}` and validates it with
`case "$PREVIOUS_GENERATION" in ''|*[!0-9]*) echo ...; exit 1;; esac` before
the first `kubectl`.

**Child manifests from data (`run-onboard`, `run-deploy`,
`run-update-config`, `run-provision-db`, `run-retire`).** Each here-document
is replaced by a static jq program in single quotes, with every
variable value passed as `--arg`:

```sh
MANIFEST="${TMPDIR:-/tmp}/child-workflow.json"
jq -n \
  --arg team "$TEAM" --arg svc "$SVC" --arg type "$COMPONENT_TYPE" \
  --arg repo "$REPO" --arg tag "$GIT_TAG" --arg db "$PROVISION_DB" \
  --arg path "$PARAM_DOCKERFILE_PATH" --arg img "${SMOKE_RUN}-onboard" '
  {apiVersion: "argoproj.io/v1alpha1", kind: "Workflow",
   metadata: {generateName: "smoke-onboard-", namespace: "argo-workflows"},
   spec: {workflowTemplateRef: {name: "deploy-service", clusterScope: true},
          arguments: {parameters: [
            {name: "action", value: "onboard"},
            {name: "team_name", value: $team},
            ...
            {name: "image_tag", value: $img}]}}}' > "$MANIFEST"
WF_NAME=$(kubectl create -n argo-workflows -o jsonpath='{.metadata.name}' -f "$MANIFEST")
```

The literal values stay literals in the program: `port: "8080"`, `host: ""`,
`env_vars: "SMOKE_ENV=deploy_action"`, and so on. The parameter list, its
order and all values match today's manifests exactly, so the child
workflows are byte-for-byte equivalent in effect. kubectl accepts JSON on
`-f`. `${TMPDIR:-/tmp}` lets the test harness redirect the file. The poll
loops after `kubectl create` do not change.

`jq` was chosen over `yq ... strenv()`:
- jq is already used in `alpine/k8s:1.33.12` in this repo;
- the output is plain JSON, with no YAML tag or anchor surprises;
- no binary download is needed.

If the first live run shows jq is missing, the fallback is the pinned,
sha256-verified yq download from `wft-provision-database.yaml` with
`strenv()`.

### 2. Constrained-name sites (task 7)

There are 11 templates (table above). Each gets `PARAM_TENANT_NAME`, or
`PARAM_TEAM_NAME` + `PARAM_COMPONENT_NAME` / `PARAM_APP_NAME`, appended to
its `script.env` (creating `env:` if absent; `create-vault-policy` already
has `VAULT_ADDR`). The prelude line becomes `TENANT="$PARAM_TENANT_NAME"`.
Existing in-script validation, such as the `grep -qE` team/app check in
`do-provision`, is kept as a second line of defence. One PR per file family:
- `wft-create-tenant`;
- `wft-delete-tenant-safe` + `wft-delete-tenant`;
- `wft-deploy-service` + `wft-provision-database` + `wft-retire-service`.

### 3. Harness coverage (T2 for tasks 6 and 7)

`tests/test_shell_param_injection.py` gains `CASES` entries:
- `wft-smoke-test.yaml`: `run-onboard` (stop at `WF_NAME=$(kubectl create`)
  and `check-pod-running` (stop at `check_missing_secret_reference()`).
- One template per task-7 file: `wft-create-tenant` `create-vault-policy`,
  `wft-delete-tenant-safe` `delete-vault-policy`, `wft-delete-tenant`
  `delete-vault-policy`, `wft-deploy-service` `refresh-apps-appset`,
  `wft-provision-database` `do-provision`, and `wft-retire-service`
  `cleanup-db-from-gitops`.

Each stop line is the first network, `apk`, `curl` or `kubectl` line,
taken from the template.

For `run-onboard`, the prelude includes the jq build. The test sets `TMPDIR`
to the work dir. For each payload it then asserts:
- the canary is absent;
- `child-workflow.json` parses;
- `team_name`, `git_tag` and `dockerfile_repo` in
  `spec.arguments.parameters` equal the payload exactly;
- the parameter name list is unchanged.

This last check is the YAML-splice regression test. A
`previous_generation` case asserts that a non-numeric payload exits non-zero.
The harness's `PH` regex is widened to tolerate whitespace inside braces, to
match the validator.

`do-provision` downloads yq before its prelude (l.60-70), so its CASES entry
needs a start marker as well as a stop marker. Extend `CASES` to an optional
`(start, stop)` pair rather than special-casing.

### 4. Validator ban (task 8, last PR)

`scripts/validate-shell-param-interpolation.py`:
- Delete `BASELINE`, `CONSTRAINED` and the stale-baseline branch. `main()`
  fails on any `scan()` hit and keeps the `check_env_bindings` gate.
- Add `EXPRESSION = re.compile(r"\{\{=(.*?)\}\}", re.S)`. A match whose body
  contains `inputs.parameters` or `workflow.parameters` is reported as a hit,
  with the parameter name taken from `parameters\.(\w+)` or
  `parameters\[['"](\w+)`, else `<expression>`.
- `shell_blocks()` also yields `sidecars[name].command/args` and
  `containerSet.containers[name].command/args`.
- `check_env_bindings()` generalises to every container-like spec (`script`,
  `container`, `initContainers`, `sidecars`, `containerSet.containers`). It
  checks `$PARAM_*` in each spec's own `source`/`command`/`args` against that
  spec's `env`.
- `--selftest` adds four cases: a here-document body
  (`cat <<'EOF'\n{{inputs.parameters.x}}\nEOF`), a `{{=` expression
  (`{{=sprig.trim(inputs.parameters.x)}}`), a sidecar arg and a
  containerSet arg.
- Update the module docstring: the script is a ban, not a ratchet.

### 5. Live check (task 10)

After the last merge and the ~3 min ArgoCD sync:
1. Submit `smoke-test` with `-p team_name=labs`, by `kubectl create` of a
   Workflow referencing the ClusterWorkflowTemplate. The API operation takes
   no parameters and would target the nonexistent `tests` tenant.
2. Run one `deploy-service` onboard and one `update-config` with multi-line
   `env_vars` and `secret_env_vars` against a throwaway `labs` service.
3. Compare the resulting `values.yaml` and Vault data with the expected
   output.

## Alternatives

- **`yq ... strenv()` for the child manifests** (the issue's first
  suggestion). It is equally safe. Dropped as the primary because nothing in
  the repo shows yq in `alpine/k8s:1.33.12`, and the one yq user downloads a
  pinned binary, which adds a network fetch and a checksum to five
  templates. It is kept as the documented fallback.
- **Keep `CONSTRAINED` and only remove `BASELINE`.** This is smaller, but it
  keeps a name-matched claim about mctl-api that silently exempts any
  `team_name` fed by another caller. The issue and #992 both require the
  allow-list to be deleted. Rejected.
- **Env-bind smoke-test values but keep the here-document with
  `"${VAR}"`.** This removes shell injection, but it still assembles YAML
  from text: a `"` or newline in `git_tag` rewrites the child's parameters.
  The issue explicitly forbids it. Rejected.
- **Pass the child arguments with `argo submit -p`.** The `argo` CLI is not
  in `alpine/k8s`, and it would need extra auth. Rejected.

## Platform impact

- **Migration:** none. These are ClusterWorkflowTemplate edits plus one
  script and one test. ArgoCD syncs in about 3 minutes. Workflows already
  running keep their submit-time snapshot.
- **Backward compatibility:** no parameter, output or child-workflow
  argument changes. For valid inputs the smoke-test children receive the
  same values. The only new failure mode is
  `check-pod-running` rejecting a non-numeric `previous_generation`, which
  today would already fail at `-gt`.
- **CI:** after task 8, any new `{{inputs|workflow.parameters.*}}` in a
  shell block fails `validate-manifests.yml`. Authors must use `env:`
  bindings. The failure message already explains how.
- **Risks and mitigations:**
  - *jq missing in the image, or a jq program typo, breaks the smoke test.*
    The harness runs the jq build in CI on every payload. The first
    smoke-test PR is followed by one manual run, and yq is the fallback.
  - *A binding lands on the wrong template.* `check_env_bindings` fails CI,
    and the harness runs each prelude.
  - *Tenant deletion or creation regresses (task 7).* These paths are rarely
    run. After their PR merges, run `create-tenant` and `delete-tenant-safe`
    against a throwaway tenant, or at least run their harness cases plus
    `test_wft_create_tenant_existing.py`.
  - *The ban lands before a site is converted.* Task 8 depends on tasks 6
    and 7, and its own CI run on the repo is the proof.
- **Resource impact:** none. A few extra env vars per pod, plus one small
  JSON file in `/tmp`.
