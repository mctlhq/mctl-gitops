# Bind workflow inputs through env in GitHub Actions run steps, validate release-deploy inputs early, and lint against regressions

## Context

`.github/workflows/release-deploy.yaml` is dispatched with free-form
`workflow_dispatch` inputs (`repo`, `git_ref`, `image_name`, `image_tag`,
`dockerfile_path`, `team_name`, `component_name`, `values_path`,
`values_glob`). Its `bump` job runs in the `gitops-bump` environment and holds
the write deploy key on `main`'s ruleset bypass list. The `Bump image tag(s)`
and `Commit and push` steps already bind inputs through `env:`, but the final
`Summary` step still substitutes `${{ inputs.* }}` directly into the bash
script text. GitHub substitutes expressions before bash parses the script, so
an input containing a quote or `$(...)` runs as a shell command on a runner
that has just used that deploy key. Nothing validates the shape of these
inputs before the `build` job starts.

The issue asks for three things: move every `${{ inputs.* }}` and
`${{ github.event.* }}` out of `run:` scripts in this workflow; validate
input shapes early and fail fast; and sweep the rest of `.github/workflows/`
and add a CI check so the pattern cannot return. A sweep of the clone found
one more site outside release-deploy: `.github/workflows/auto-merge.yml`
interpolates `${{ github.event.pull_request.number }}` into the `run:` of
`Request Copilot review` and `Merge PR`.

## User stories

- AS a platform operator I WANT release-deploy to treat dispatch inputs as
  data, never as shell text, SO THAT a malformed or hostile input cannot run
  commands on a runner that holds the gitops deploy key.
- AS a platform operator I WANT release-deploy to reject malformed inputs
  before it builds an image SO THAT a bad dispatch fails in seconds, with a
  clear error, and pushes nothing.
- AS a reviewer of `.github/workflows/` changes I WANT CI to fail when a
  `run:` script interpolates an untrusted expression SO THAT the hardening
  cannot quietly regress.

## Acceptance criteria (EARS)

- WHILE any workflow in `.github/workflows/` is on `main`, THE SYSTEM SHALL
  contain no `${{ ... }}` expression referencing `inputs.`, `github.event.`
  or `github.head_ref` inside a step's `run:` text or an
  `actions/github-script` `with.script`.
- WHEN `release-deploy.yaml`'s `Summary` step runs, THE SYSTEM SHALL read
  every input value from a step-level `env:` variable and SHALL produce the
  same summary table it produces today for well-formed inputs.
- WHEN `release-deploy.yaml` is dispatched, THE SYSTEM SHALL run a
  `validate-inputs` job before `build`, and `build` SHALL depend on it.
- IF `team_name` or `component_name` does not match
  `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, THEN THE SYSTEM SHALL fail
  `validate-inputs` with an `::error::` naming the input, and SHALL NOT start
  `build` or `bump`.
- IF `image_tag` does not match `^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$` (the
  regex the bump script already enforces), THEN THE SYSTEM SHALL fail
  `validate-inputs`.
- IF `repo` is not `owner/name` matching
  `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`, THEN THE SYSTEM SHALL fail
  `validate-inputs`.
- IF `image_name`, `git_ref`, `dockerfile_path` or `values_glob` contains a
  newline, or does not match its documented pattern (see design.md), THEN
  THE SYSTEM SHALL fail `validate-inputs`.
- IF `values_path` or `values_glob` contains a `..` segment, is absolute, or
  is not under one of the bump script's `ALLOWED_PREFIXES`, THEN THE SYSTEM
  SHALL fail `validate-inputs`. (`values_path` may still hold several paths
  separated by commas or newlines.)
- WHEN a pull request or a push to `main` runs `validate-manifests.yml`, THE
  SYSTEM SHALL run the new checker in `--selftest` mode and then against
  `.github/workflows/`, and SHALL fail the job on any finding.
- WHEN the checker runs with `--selftest`, THE SYSTEM SHALL prove that it
  reports a deliberately reintroduced `${{ inputs.x }}` in a `run:` block, a
  `${{ github.event.pull_request.title }}` in a `run:` block, and an
  interpolation in a github-script `script:`, and that it does not report the
  same expressions under `env:` or `with:`.
- WHEN release-deploy is dispatched with valid inputs after this change, THE
  SYSTEM SHALL bump the image tag on `main` exactly as before, and
  `tests/test_release_deploy_bump.py` SHALL still pass unchanged.
- WHEN `auto-merge.yml` requests a Copilot review or merges a PR, THE SYSTEM
  SHALL read the PR number and repository from `env:` variables.

## Out of scope

- Expressions that are not attacker-controlled (`secrets.*`, `steps.*.outputs`,
  `needs.*`, `github.repository`, `github.actor`, `github.token`) inside
  `run:`. They are not flagged by the new check; converting them is
  optional cleanup, not part of this proposal.
- Expressions in `run-name:`, `if:`, `with:` and `env:`. These are not
  parsed by a shell. `run-name` renders in the UI only.
- Restricting `image_tag` to strict semver. Callers also pass non-semver
  tags (`build-image.yaml` documents `main-abc1234`); see Open questions.
- Adopting zizmor or actionlint as a full CI gate, and the other audits
  those tools run.
- Argo Workflow templates. `scripts/validate-shell-param-interpolation.py`
  already covers them (gitops#992).
- Workflows in other repositories that dispatch release-deploy.

## Open questions

- The issue says "semver tag". This proposal validates `image_tag` against
  the image-tag grammar the bump script already enforces, not strict semver,
  because a semver-only rule could reject live callers. A reviewer should
  confirm whether every release-deploy caller (the CI in other repos and
  mctl-api's deploy path) sends semver. If they all do, the regex can be
  tightened later.
- Release-deploy's run history (the input shapes that real callers send)
  could not be observed from this run. The `image_name` and `git_ref`
  patterns are chosen to be permissive enough for the documented examples.
  The first real dispatch after merge is the confirmation.
