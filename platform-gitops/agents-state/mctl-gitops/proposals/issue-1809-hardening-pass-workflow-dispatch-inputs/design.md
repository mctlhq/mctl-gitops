# Design: issue-1809-hardening-pass-workflow-dispatch-inputs

## Current state

### release-deploy.yaml

`.github/workflows/release-deploy.yaml` has nine `workflow_dispatch` inputs
and two jobs:

- `build` calls `./.github/workflows/build-image.yaml` and passes the inputs
  through `with:`. That is not shell text, so it is safe. `build-image.yaml`'s
  `Fetch Vault PAT` step already binds `repo`, `team_name` and
  `component_name` through `env:` and shape-checks them (team and component
  against `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, repo against `owner/name`, and a
  single-line check). That check is the only early validation today, and it
  runs only after the reusable workflow's job has started. `image_tag`,
  `git_ref`, `image_name` and `dockerfile_path` are not validated before the
  image is built and pushed to GHCR.
- `bump` runs in `environment: gitops-bump` and checks out `main` with
  `secrets.GITOPS_BUMP_DEPLOY_KEY`.
  - `Bump image tag(s)` binds every input through `env:` (`TEAM`, `SERVICE`,
    `VALUES_PATH`, `VALUES_GLOB`, `IMAGE_NAME`, `NEW_TAG`). Its Python
    heredoc validates `new_tag` with
    `re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9._-]{0,127}', ...)` (exit 5), and
    validates every path against `ALLOWED_PREFIXES` with `..` and absolute
    path checks (exit 4).
  - `Commit and push` binds `TEAM`, `SERVICE` and `NEW_TAG` through `env:`.
  - `Summary` is the remaining gap. Its `run:` interpolates
    `${{ inputs.team_name }}`, `component_name`, `image_name`, `image_tag`,
    `git_ref`, `values_glob`, `values_path`, and a
    `format('platform-gitops/services/{0}/{1}/values.yaml', ...)` expression
    directly into bash `echo` and `[[ -n "..." ]]` lines. An input such as
    `git_ref='x$(curl ...)'` is executed by bash. The runner checked out
    with the deploy key earlier in the same job. `actions/checkout` persists
    SSH credentials for the job by default, and the step sets no
    `persist-credentials: false`, so the key is still on that runner.
- `run-name:` interpolates inputs. It is rendered, not executed, and is out
  of scope.

### Repository-wide sweep

I parsed every `.github/workflows/*.y*ml` with PyYAML and listed each
`${{ ... }}` inside a step's `run:` or a github-script `with.script`.
Attacker-influenced contexts showed up in only two places:

| File | Step | Expression |
|------|------|------------|
| `release-deploy.yaml` | `bump` / `Summary` | `inputs.team_name`, `component_name`, `image_name`, `image_tag`, `git_ref`, `values_glob`, `values_path` |
| `auto-merge.yml` | `request-review` / `Request Copilot review` | `github.event.pull_request.number` |
| `auto-merge.yml` | `auto-merge` / `Merge PR` | `github.event.pull_request.number` |

A PR number is an integer, so the `auto-merge.yml` sites cannot be exploited
in practice. They still match the pattern the issue wants removed. The
`Guard` step in the same file already binds the same value as
`PR: ${{ github.event.pull_request.number }}`. The other hits in `run:` are
non-attacker contexts: `secrets.*` and `steps.*.outputs` in
`build-image.yaml`, `steps.*.outputs` in `cloudflare-access-login-probe.yml`
and `cloudflare-portal-health.yml`, `needs.*` in `cloudflare-plan.yml`, and
`github.repository` / `github.actor` / `github.token`. No workflow uses
`actions/github-script` with an interpolated script. There is no
`.github/actions/` directory (no composite actions).

### Existing lint pattern to mirror

`.github/workflows/validate-manifests.yml` runs on every `pull_request` and on
`push` to `main`, with no `paths:` filter. It already runs Python detectors,
each as `--selftest` first and then as a real scan. One example is
`scripts/validate-shell-param-interpolation.py`, which enforces the same
invariant for Argo templates (`{{inputs.parameters.X}}` inside
`script.source`/`command`/`args`; gitops#992). It also runs
`tests/test_release_deploy_bump.py`. That test extracts the
`Bump image tag(s)` heredoc with the regex
`- name: Bump image tag\(s\).*?python3 <<'PYEOF'` and runs it against
fixtures. The step name and heredoc shape must therefore stay stable. No
actionlint or zizmor is installed in CI today (grep of `.github` and
`scripts` found neither).

### Deployed state checked

- This change only touches GitHub Actions CI definitions in this repository.
  It changes no tenant service, values.yaml, or cluster resource, so I did
  not query `mctl_*` service tools or `$MCTL_GITOPS_ROOT/services/*`. No
  deployed service configuration is asserted anywhere in this design.
- I grepped the clone for `release-deploy`. It is referenced only from
  `deploy-signal.yml`, `gitops-bump.yaml` and `validate-manifests.yml`
  comments, `CLAUDE.md` and runbooks. No Argo template dispatches it, so its
  callers are outside this repository (other repos' CI and the mctl deploy
  path).
- Not observed: release-deploy's GitHub Actions run history, so I could not
  see the actual input values real callers send. This is recorded under Open
  questions in requirements.md. The validation patterns below are kept
  permissive for that reason.

## Proposed solution

### 1. release-deploy.yaml: env-bind the Summary step

Replace the `Summary` step's interpolations with step-level `env:` bindings:

```yaml
- name: Summary
  env:
    TEAM: ${{ inputs.team_name }}
    SERVICE: ${{ inputs.component_name }}
    IMAGE_NAME: ${{ inputs.image_name }}
    NEW_TAG: ${{ inputs.image_tag }}
    GIT_REF: ${{ inputs.git_ref }}
    VALUES_PATH: ${{ inputs.values_path }}
    VALUES_GLOB: ${{ inputs.values_glob }}
  run: |
    {
      echo "## Released ${TEAM}/${SERVICE}"
      ...
      echo "| **Image** | \`${IMAGE_NAME}:${NEW_TAG}\` |"
      echo "| **Git ref** | \`${GIT_REF}\` |"
      if [[ -n "${VALUES_GLOB}" ]]; then ...; fi
      if [[ -n "${VALUES_PATH}" || -z "${VALUES_GLOB}" ]]; then
        echo "| **Gitops file** | \`${VALUES_PATH:-platform-gitops/services/${TEAM}/${SERVICE}/values.yaml}\` |"
      fi
    } >> "$GITHUB_STEP_SUMMARY"
```

The shell default `${VALUES_PATH:-...}` replaces the `format()` expression,
and the output is the same. `$GITHUB_STEP_SUMMARY` is quoted. The
`Bump image tag(s)` step's name and heredoc stay untouched, so
`tests/test_release_deploy_bump.py` keeps extracting it.

### 2. release-deploy.yaml: a `validate-inputs` job before `build`

Add a first job, `validate-inputs` (`runs-on: ubuntu-latest`,
`permissions: {}`, no checkout, no secrets). Make `build` declare
`needs: validate-inputs`. `bump` already `needs: build`. The job's single
step binds every input through `env:` (`INPUT_*`) and checks it in bash. It
first rejects a newline in every single-line input, then matches each input
with `[[ =~ ]]`:

| Input | Rule |
|-------|------|
| `team_name`, `component_name` | `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, the same as build-image.yaml |
| `repo` | `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`, the same as build-image.yaml |
| `image_tag` | `^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$`, the same as the bump script |
| `image_name` | `^[a-z0-9.-]+(:[0-9]+)?(/[a-z0-9._-]+)+$` (lowercase registry/path, as OCI requires) |
| `git_ref` | `^[A-Za-z0-9._/+-]{1,255}$`, not starting with `-` |
| `dockerfile_path` | `^[A-Za-z0-9._/-]+$`, relative, no `..` segment |
| `values_glob` (optional) | `^[A-Za-z0-9._/*?-]+$`, relative, no `..` segment, under an allowed prefix |
| `values_path` (optional) | split on `,` and newline; each item `^[A-Za-z0-9._/-]+$`, relative, no `..` segment, under an allowed prefix |

On a failure, the step prints `::error::invalid <input>: <value>` and exits 1.
This happens before any image build or push. In the `ALLOWED_PREFIXES` copy
in this job, a comment points at the bump script's tuple. A test (task 5)
asserts that the two lists are equal, so they cannot drift. The bump script
keeps its own checks unchanged as the second layer. It is the step that
actually opens files.

`team_name` and `component_name` are also used to build the default
`platform-gitops/services/{team}/{service}/values.yaml`. Today a `team_name`
of `labs/other` would pass the bump script's prefix check and redirect the
bump to another directory under `services/`. The new pattern closes that gap.

### 3. auto-merge.yml: env-bind the PR number

In `Request Copilot review` and `Merge PR`, add `PR: ${{ github.event.pull_request.number }}`
and `REPO: ${{ github.repository }}` to `env:` (mirroring the existing
`Guard` step), and use `gh pr edit "$PR" ... --repo "$REPO"` /
`gh pr merge "$PR" ... --repo "$REPO"`. `steps.guard.outputs.head_sha` may
also move to `HEAD_SHA` for consistency. That output is produced by this
workflow, so the move is optional.

### 4. New check: `scripts/validate-gha-expression-injection.py`

This is a Python detector in the same style as
`scripts/validate-shell-param-interpolation.py`, executable with a shebang
and PyYAML (already used by the sibling scripts).

- Scope: `.github/workflows/*.yml` and `*.yaml`, plus any
  `.github/actions/**/action.y*ml` if one appears later (composite `runs.steps`).
- For each job's `steps[]`, the text it inspects is `step["run"]`, and
  `step["with"]["script"]` when `uses` starts with `actions/github-script`.
- Finding: any `${{ ... }}` whose body matches
  `\b(inputs\.|github\.event\.|github\.head_ref\b)`. That covers the issue's
  literal acceptance criterion (`${{ inputs.`) and the issue's
  `github.event.*` item. `head_ref` is included because it is
  attacker-chosen on PRs.
- Output: `file / job / step: run interpolates <expr>; bind it via env:`, with
  exit 1 on any finding and exit 2 on unparseable YAML. There is no baseline
  or ratchet list, because after tasks 1 and 3 the count is zero.
- `--selftest`: writes temporary workflows and asserts that it detects
  `${{ inputs.x }}` in `run:`, `${{ github.event.pull_request.title }}` in
  `run:`, a single-line `run:`, `${{inputs.x}}` with no spaces, and
  `${{ inputs.x }}` in a github-script `script:`. It also asserts that it
  does not report the same expressions under `env:`, `with:` (non-script),
  `if:` or `run-name:`.

Wire it into `validate-manifests.yml` next to the
`Check for shell interpolation of workflow parameters` step:

```yaml
- name: Check GitHub Actions run steps for expression injection
  run: |
    set -euo pipefail
    scripts/validate-gha-expression-injection.py --selftest
    scripts/validate-gha-expression-injection.py
```

`validate-manifests.yml` has no `paths:` filter, so the check runs on every
PR that edits a workflow. The issue's "fails on a deliberately reintroduced
one" criterion is covered in two ways: permanently by `--selftest`, and once
by hand on the implementation PR (tests T4).

## Alternatives

1. **zizmor (`template-injection` audit) in CI.** It catches this pattern and
   more. It was dropped as the gate for now because it adds a third-party
   binary to pin and maintain, and because its other audits (unpinned
   actions, excessive permissions, `secrets: inherit`, etc.) would land a
   batch of unrelated findings that would have to be triaged or suppressed
   before the gate could go green. That is scope creep for this issue. It
   could be a follow-up that runs alongside the in-repo script.
2. **actionlint.** Its expression check flags only a fixed list of known
   untrusted `github.event.*` fields (titles, bodies, head refs). It does
   not flag `inputs.*`, which is the issue's main case, so on its own it
   would not meet the acceptance criterion.
3. **A grep one-liner in CI** (`grep -n '\${{ *inputs\.' .github/workflows`).
   It cannot tell `run:` from `env:`/`with:`/`run-name:`. Every correct
   `env:` binding would match, and so would the `with:` block of the `build`
   job. The workaround would be fragile line-context heuristics. Parsing
   YAML costs about the same and is exact, and it matches the repository's
   existing detector style.
4. **Validation inside each consuming step instead of a separate job.** This
   is what the repository does today: build-image's Vault step and the bump
   script each validate part of the input set. That only fails after the
   build job is scheduled, and for `image_tag` only after the image is
   pushed. A dedicated zero-permission job gives fail-fast behaviour for
   about 10 seconds of runner time. The existing in-step checks stay as
   defence in depth.

## Platform impact

- **Migrations:** none. This changes CI YAML and adds one script.
- **Backward compatibility:** Every input that real callers are documented
  to send passes the new checks: `mctlhq/mctl-docs`,
  `ghcr.io/mctlhq/mctl-docs`, `0.1.18`, `Dockerfile`, team and service names
  that are DNS labels, and the paths under the three allowed prefixes,
  including the `cwft-mctl-agents-*.yaml` glob. The risk is a caller that
  sends something outside the patterns, for example an uppercase image name
  or a `git_ref` with an unusual character. Mitigation: the patterns are
  supersets of what the downstream steps already accept, or match them
  exactly. The failure is loud (`::error::invalid <input>`) and happens
  before anything is built or pushed. Rollback is a one-line revert of
  `needs: validate-inputs`.
- **Deploy path:** `validate-inputs` adds one short job (about 5-10 s queue
  plus run) before every release-deploy build. `deploy-signal.yml` watches
  release-deploy outcomes. A validation failure now shows up as a failed
  run with a log, which is the visibility that workflow exists for.
- **CI:** one extra Python step in `validate-manifests.yml`, which takes
  well under a second.
- **Security:** this removes the last shell-text interpolation of dispatch
  inputs in the job that holds the gitops deploy key. It also closes the
  `team_name` path-redirect gap under `platform-gitops/services/`.
- **Risk: `tests/test_release_deploy_bump.py` breaking.** That test locates
  the bump step by name and heredoc markers. The design leaves that step
  byte-identical, and T2 runs the test.
