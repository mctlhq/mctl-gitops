# Tasks: issue-1809-hardening-pass-workflow-dispatch-inputs

- [ ] 1. In `.github/workflows/release-deploy.yaml`, rewrite the `bump` job's
  `Summary` step to bind `team_name`, `component_name`, `image_name`,
  `image_tag`, `git_ref`, `values_path` and `values_glob` through a
  step-level `env:` (`TEAM`, `SERVICE`, `IMAGE_NAME`, `NEW_TAG`, `GIT_REF`,
  `VALUES_PATH`, `VALUES_GLOB`). Replace the `format(...)` default with
  `${VALUES_PATH:-platform-gitops/services/${TEAM}/${SERVICE}/values.yaml}`
  and quote `"$GITHUB_STEP_SUMMARY"`. — DoD: the step's `run:` contains no
  `${{`. For the same inputs, the rendered summary table is identical to
  today's. The `Bump image tag(s)` step is byte-identical.
- [ ] 2. In `.github/workflows/release-deploy.yaml`, add a `validate-inputs`
  job (`runs-on: ubuntu-latest`, `permissions: {}`, no checkout, no secrets)
  that binds every input through `env:` and enforces the rules in design.md
  section 2: a newline check on single-line inputs, regexes for
  team/component/repo/image_tag/image_name/git_ref/dockerfile_path, and
  relative path, no `..`, allowed prefix and charset checks on each
  `values_path` item and on `values_glob`. Add `needs: validate-inputs` to
  `build`. Add a comment that the prefix list mirrors the bump script's
  `ALLOWED_PREFIXES`. — DoD: an invalid input fails this job with
  `::error::invalid <input>`, and `build`/`bump` are skipped. Valid inputs
  pass.
- [ ] 3. In `.github/workflows/auto-merge.yml`, bind
  `github.event.pull_request.number` and `github.repository` through `env:`
  (`PR`, `REPO`) in `Request Copilot review` and `Merge PR`, and reference
  them as `"$PR"` / `"$REPO"`. Optionally bind
  `steps.guard.outputs.head_sha` as `HEAD_SHA`. — DoD: neither step's `run:`
  contains `github.event.`.
- [ ] 4. Add `scripts/validate-gha-expression-injection.py` (executable,
  PyYAML), as specified in design.md section 4. It scans `run:` and
  github-script `with.script` in `.github/workflows/*.y*ml` (and any
  `.github/actions/**/action.y*ml`) for `${{ }}` expressions referencing
  `inputs.`, `github.event.` or `github.head_ref`. It exits 1 on findings
  and 2 on unparseable YAML, and has a `--selftest` mode. (depends on 1, 3,
  so the real scan is clean) — DoD: `--selftest` passes, and the real scan
  exits 0 on the branch.
- [ ] 5. Add `tests/test_release_deploy_validate_inputs.py`. It extracts the
  `validate-inputs` step's bash from `release-deploy.yaml` (in the same way
  `tests/test_release_deploy_bump.py` extracts the bump heredoc), runs it
  with `INPUT_*` env against valid and invalid fixtures, and asserts that
  its prefix list equals the bump script's `ALLOWED_PREFIXES`. (depends on 2)
  — DoD: the test passes locally and fails if either prefix list is edited
  alone.
- [ ] 6. Wire both into `.github/workflows/validate-manifests.yml`: a step
  `Check GitHub Actions run steps for expression injection` that runs the
  script with `--selftest` and then without it, placed next to
  `Check for shell interpolation of workflow parameters`, and
  `python3 tests/test_release_deploy_validate_inputs.py` next to
  `Unit-test the release-deploy bump script`. Each step gets a short comment
  explaining why it exists, in the style of its neighbours. (depends on 4,
  5) — DoD: validate-manifests is green on the PR.
- [ ] 7. Add a sentence to `scripts/README.md` describing the new detector,
  next to the existing validate-* entries. — DoD: the README lists the
  script.

## Tests

- [ ] T1. `scripts/validate-gha-expression-injection.py --selftest` passes.
  It reports `inputs.x` in multi-line and single-line `run:`,
  `github.event.pull_request.title` in `run:`, and an interpolation in a
  github-script `script:`. It does not report expressions under `env:`,
  `with:`, `if:` or `run-name:`.
- [ ] T2. `python3 tests/test_release_deploy_bump.py` passes unchanged. This
  proves the bump heredoc is still extractable and still behaves the same.
- [ ] T3. `python3 tests/test_release_deploy_validate_inputs.py` runs these
  cases:
  - The documented examples are accepted: `mctlhq/mctl-docs`,
    `ghcr.io/mctlhq/mctl-docs`, `0.1.18`, `main-abc1234`, `Dockerfile`, the
    `cwft-mctl-agents-*.yaml` glob, and two comma-separated values paths.
  - These are rejected: `team_name=labs/other`, `image_tag='1.2.3"\n  x: y'`,
    `git_ref='v1$(id)'`, `git_ref='-x'`, `values_path=../etc/passwd`,
    `values_path=/abs`, an out-of-prefix `values_glob`, and `image_name` with
    uppercase or a space.
- [ ] T4. Manual negative check on the implementation PR: temporarily add
  `run: echo "${{ inputs.team_name }}"` to a workflow in a throwaway commit
  and confirm that validate-manifests fails on the new step, then drop the
  commit. Record the failing run link in the PR description.
- [ ] T5. Post-merge: wait for the next real release-deploy dispatch (or
  trigger one for a low-risk service). Confirm that `validate-inputs` passes,
  that the tag-bump commit lands on `main`, and that the Summary renders the
  same as before. If a caller is rejected, the `::error::` line names the
  input; see Rollback.

## Rollback

All changes are CI-only and are reverted with a single `git revert` of the
implementation PR. The revert goes through a normal PR, because workflow
changes are not covered by the bot-commit exception. If only the input
validation is the problem (a legitimate caller is rejected), the minimal
hotfix is to remove `needs: validate-inputs` from the `build` job, or to
widen the single offending regex. The env-binding of `Summary`, the
`auto-merge.yml` change, and the lint check are independent of that and can
stay. No cluster state, image, or values.yaml is touched by this proposal,
so there is nothing to undo outside the repository.
