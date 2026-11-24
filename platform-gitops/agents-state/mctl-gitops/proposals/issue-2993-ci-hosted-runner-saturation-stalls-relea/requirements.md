# Relieve hosted-runner saturation: supersede stale runs, measure, then decide on self-hosted runners or a paid plan

## Context

The mctlhq org is on the GitHub free plan: 20 concurrent hosted jobs shared by
every repository. On 2026-11-23 the merge-group `Validate Manifests` check for
release bump PR #2988 sat `queued` for 15 minutes because mctl-gitops alone held
17 queued and 9 running runs, seven of them for superseded commits (preview
builds for an older main SHA, and PR checks for two earlier heads of one PR).
Releases of mctl-telegram and mctl-alice waited behind it although they had
nothing to do with it.

The issue asks for a written decision between self-hosted runners on the two
macOS x64 machines already registered as org runners (label `agy-reviewer`), a
paid plan, or both, and asks to check the cheaper steps first: supersession via
`concurrency` on PR-triggered checks and preview builds (extending #2935, which
did this only for `push` runs of `validate-manifests.yml`), and cleanup of two
runs queued since 2026-10-07 and 2026-11-08. This proposal does the cheap steps
in code, adds a measurement script, records the decision in an ADR, and gates
any self-hosted rollout behind a configuration-enforced fork-PR boundary and a
test that proves it.

## User stories

- AS a release operator I WANT a release's merge-group checks to get a runner
  within minutes SO THAT a one-line fix reaches production without waiting on
  unrelated work.
- AS a PR author I WANT a new push to my PR to cancel the checks of my previous
  head SO THAT superseded runs do not hold shared runner slots.
- AS a platform owner I WANT a measured before/after comparison and a written
  decision SO THAT runner capacity is bought or built on evidence, not guesses.
- AS a security reviewer I WANT fork pull request code to be unable to reach a
  self-hosted runner by configuration SO THAT a public repository never hands a
  shell on our hardware to an outsider.

## Acceptance criteria (EARS)

- WHEN a `pull_request` event starts `validate-manifests.yml`,
  `cloudflare-plan.yml`, `yamllint.yml` or `security.yml` for a PR that already
  has a run of the same workflow in progress or queued THE SYSTEM SHALL cancel
  the older run (concurrency group keyed by workflow and PR number,
  `cancel-in-progress: true`).
- WHILE a run is triggered by `merge_group` THE SYSTEM SHALL keep a per-run
  concurrency group with no cancellation, so the check reports on exactly the
  commit the queue tests (unchanged behaviour of `validate-manifests.yml`).
- WHILE a run of `validate-manifests.yml` is triggered by `push` to `main` THE
  SYSTEM SHALL keep the existing #2935 group `validate-manifests-push-<ref>` with
  cancellation, and a test SHALL pin that expression so it cannot regress.
- WHEN `build-image.yaml` is dispatched by preview-deploy (`build_id` starting
  with `preview-deploy`) for the same team, component and `git_ref` as a queued
  or running preview build THE SYSTEM SHALL cancel the older preview build.
- IF `build-image.yaml` runs for any other caller (release-deploy `rd-*`,
  deploy-service, a hand dispatch) THEN THE SYSTEM SHALL use a per-run group and
  never cancel it.
- THE SYSTEM SHALL NOT add workflow-level `concurrency` to `agy-review.yml` or
  `claude-review.yml` (caller-level groups defeat the reusable workflow's own
  policy, as the comment in `agy-review.yml` documents).
- WHEN an operator runs `scripts/ci-queue-latency.py` for a time window THE
  SYSTEM SHALL report, per run, enqueue-to-start latency of merge-group runs,
  enqueue-to-merge time of the queue head, and dispatch-to-bump-merge time of
  `release-deploy` runs, reading only the public Actions and pulls APIs.
- WHEN the ADR `docs/adr/0004-ci-runner-capacity.md` is merged THE SYSTEM SHALL
  contain the before measurement, the after measurement of the concurrency
  changes, and a decision naming which option (paid plan, self-hosted, both,
  neither) is adopted and why.
- IF self-hosted runners are adopted THEN THE SYSTEM SHALL register them in a
  runner group restricted to `mctlhq/mctl-gitops` and to named workflow files,
  as ephemeral (one job per registration) runners under a dedicated low-privilege
  OS user inside a Linux VM, with no access to the operator's keychain, home
  directory or private network.
- IF self-hosted runners are adopted THEN THE SYSTEM SHALL route to them only
  jobs whose workflow has no `pull_request`, `pull_request_target` or
  `issue_comment` trigger, and a CI test SHALL fail any workflow that combines
  such a trigger with a self-hosted `runs-on` label.
- IF a self-hosted runner is offline THEN THE SYSTEM SHALL NOT block the merge
  queue: required checks stay on hosted runners until a hosted fallback is
  proven, and only non-required trusted jobs move first.

## Out of scope

- Agents-state pushes to `main` that rebuild the merge queue (tracked in #2931).
- Buying a plan or registering/reconfiguring runners in the org settings: these
  are org-owner actions outside this repository; this proposal prepares the
  evidence, the ADR and the code that a decision needs.
- Moving `build-image.yaml` / `release-deploy.yaml` (App tokens, registry
  credentials, third-party Dockerfiles) to self-hosted runners in this proposal.
- CI of other repositories in the org.

## Open questions

- Paid plan cost and concurrency: the exact concurrent-job limit and monthly
  price of the Team plan for this org must be confirmed by the org owner; the
  ADR records the confirmed numbers, not assumed ones.
- Preview `git_ref` shape: if preview-deploy is dispatched with a commit SHA
  rather than a branch name, a group keyed by `git_ref` never supersedes
  anything, and the "older main SHA" case from the issue is not covered.
  Assumed: key by team/component/git_ref now; widen to team/component only if
  the measurement shows SHA-keyed preview builds are the stale ones.
- The two runs queued since 2026-10-07 (`Cloudflare MCP portal health`) and
  2026-11-08 (`CodeQL`) could not be observed from this run (no GitHub API
  access); whether they hold a slot or a concurrency group is unknown, and
  cancelling them is an operator step in tasks.md.
- Whether the two macOS machines can host a Linux VM with enough CPU/RAM for
  `validate-manifests.yml` jobs (helm template, kubeconform) and how many
  concurrently: not observable from the repo; the ADR records the measured
  capacity before any rollout.
- Whether hosted fallback for a required check is acceptable as a "router" job
  that probes runner availability: it needs an org-runner read token, which is
  itself a new credential. Assumed: required checks stay hosted.
