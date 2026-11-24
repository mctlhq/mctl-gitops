# Design: issue-2993-ci-hosted-runner-saturation-stalls-relea

## Current state

Every job in `.github/workflows/` runs on GitHub-hosted runners: 75 jobs use
`runs-on: ubuntu-latest` and one (`cli-mctl.yml`) uses a matrix `os`. No
workflow references a self-hosted label; `agy-reviewer` appears nowhere in the
repo, so the two macOS runners the issue mentions are used by other
repositories' workflows (mctlhq/.github), not by mctl-gitops.

Concurrency as it exists today:

- `validate-manifests.yml` (triggers `pull_request`, `push: main`,
  `merge_group`; 12 jobs including `validate`, `reserved-hosts`,
  `zitadel-iac`, `grafana-iac`, `vault-human-auth-iac`,
  `forgejo-reconcile-teams`) has a workflow-level group added by #2935:
  `validate-manifests-push-<ref>` with `cancel-in-progress` for `push` only;
  every `pull_request` and `merge_group` run gets its own group
  `validate-manifests-<run_id>`. So a new PR head does NOT cancel the previous
  head's 12 jobs; this is the "PR checks for two earlier heads" in the issue.
- `cloudflare-plan.yml` (`pull_request` incl. `labeled`/`unlabeled`,
  `merge_group`, `workflow_dispatch`; jobs `changes`, `discover`, `plan`,
  `assert-scripts`, `cloudflare-plan`) has no concurrency at all. Every label
  change on any PR starts it.
- `yamllint.yml` (`pull_request`, `push: main`, path-filtered) and
  `security.yml` (`pull_request` to main, weekly schedule; Trivy) have none.
- `agy-review.yml` deliberately has no workflow-level group; its comment
  explains that a caller-level group would kill in-flight reviews before the
  reusable workflow's own per-repo group applies. `claude-review.yml` likewise.
- `agy-formal-queue.yml` runs on `merge_group` only, one 5-minute job.
- `build-image.yaml` (`run-name: build-<build_id>: <team>/<component>
  (<tag>)`, `workflow_dispatch` + `workflow_call`) has no concurrency. It is
  dispatched by `wft-preview-deploy.yaml` (`build_id = {{workflow.name}}`,
  i.e. `preview-deploy-*`), by `wft-deploy-service.yaml`, by hand, and called by
  `release-deploy.yaml` job `build` with `build_id: rd-<run_id>`.
- `wft-preview-deploy.yaml` `trigger-github-build` waits 30 x 10 s for the run
  to appear and 40 x 15 s for it to finish, then exits 1 on any non-success
  conclusion. So a preview build that stays queued for 10+ minutes on a
  saturated org already fails its preview; a cancelled superseded build fails
  the same way, loudly, which is acceptable for a superseded preview.
- `release-deploy.yaml` serialises only `publish-direct`/`publish-pr`;
  `enqueue-bump` and `await-bump` (up to 55 minutes) are deliberately outside
  any group. `await-bump` holds a hosted slot for the whole merge-queue wait,
  which is part of the saturation it is waiting on. `gitops-bump.yaml` carries
  the same jobs (`tests/test_release_bump_enqueue.py` keeps them identical).
- `mirror-image.yaml` and the cloudflare cron workflows already have groups.

Release secrets: `release-deploy.yaml` `build` passes `APP_PRIVATE_KEY` and
`GH_PACKAGES_TOKEN` to `build-image.yaml` and checks out third-party source;
`agy-formal-queue.yml` reads `DISPATCH_APP_PRIVATE_KEY` from the
`app-dispatch-queue` environment. Both are poor first candidates for
self-hosted hardware.

Tests that pin workflow structure live in `tests/` (pytest), e.g.
`tests/test_release_bump_enqueue.py`, `tests/test_release_gate_watch.py`; none
pins `validate-manifests.yml`'s concurrency expression today. ADRs live in
`docs/adr/` (`0002-log-backend.md`, `0003-temporal-client-authz.md`).

Deployed state checked:

- Not applicable to cluster state: this change touches only GitHub Actions
  workflows, a script, tests and an ADR; no tenant service, hostname or Helm
  value is involved, so no mctl MCP tool and no `$MCTL_GITOPS_ROOT` path was
  read.
- GitHub org state (runner registrations, runner groups, plan, live queued
  runs, the two long-queued runs) was NOT observable from this run: no GitHub
  API access. The issue's figures are taken as reported and recorded as gaps in
  Open questions; nothing here assumes they are absent.

## Proposed solution

Three stages; each is independently useful and the later ones are gated on
the evidence of the earlier ones.

### Stage 1: supersede stale runs (code, this repo)

1. `validate-manifests.yml`: extend the group expression to three cases:
   - `push`: `validate-manifests-push-<ref>`, cancel (unchanged);
   - `pull_request`: `validate-manifests-pr-<pr number>`, cancel;
   - `merge_group` and anything else: `validate-manifests-<run_id>`, no cancel.
   `cancel-in-progress` becomes `${{ github.event_name == 'push' ||
   github.event_name == 'pull_request' }}`, so it is true exactly for the two
   cancelling groups. Update the comment block (keep the merge-group rationale).
2. `cloudflare-plan.yml`: add a workflow-level group
   `cloudflare-plan-pr-<pr number>` with cancel for `pull_request` (this also
   collapses label-change bursts), per-run without cancel for `merge_group` and
   `workflow_dispatch`. Nothing in it writes to the API, so a cancel is safe.
3. `yamllint.yml` and `security.yml`: same PR-number pattern for
   `pull_request`; `push`/`schedule` get a per-ref group with cancel (yamllint)
   or per-run (security schedule).
4. `build-image.yaml`: workflow-level group
   `${{ startsWith(inputs.build_id, 'preview-deploy') &&
   format('build-image-preview-{0}-{1}-{2}', inputs.team_name,
   inputs.component_name, inputs.git_ref) || format('build-image-{0}',
   github.run_id) }}`, `cancel-in-progress` true only for the preview case.
   Release (`rd-*`) and deploy-service builds never share a group and are never
   cancelled. Because `release-deploy.yaml` calls it with `workflow_call`, the
   callee group is evaluated per call with `rd-*` build ids and therefore stays
   per-run; a test pins this.
5. Leave `agy-review.yml`, `claude-review.yml`, `agy-formal-queue.yml`,
   `release-deploy.yaml` and `gitops-bump.yaml` concurrency untouched.
6. New test `tests/test_workflow_concurrency.py` parses the workflows with
   PyYAML and asserts, for each file above, the group string and that
   `merge_group` never resolves to a cancelling shared group (evaluate the
   expression for each event by simple string assertions on the two branches).
   It also asserts the preview prefix matches `wft-preview-deploy.yaml`'s
   `build_id = "{{workflow.name}}"` with `metadata.name: preview-deploy`.

### Stage 2: measure (script + ADR, this repo)

`scripts/ci-queue-latency.py` (stdlib only, `GITHUB_TOKEN` read-only, run by an
operator): for a `--since/--until` window it lists
`/repos/mctlhq/mctl-gitops/actions/runs` and reports (a) per merge-group run
`created_at` -> first job `started_at`, (b) for PRs merged via the queue,
enqueue time (from the PR timeline `added_to_merge_queue` event) -> `merged_at`,
(c) per `release-deploy` run `created_at` -> bump PR `merged_at`, and (d) a
count of runs whose head SHA was superseded while queued. It prints a Markdown
table for the ADR. A test feeds it recorded JSON fixtures under
`tests/fixtures/ci_queue_latency/`.

Before numbers: the 2026-11-22/23 window. After numbers: a window of equal
length after Stage 1 merges that includes a DevLoop burst.

### Stage 3: decision (ADR `docs/adr/0004-ci-runner-capacity.md`)

The ADR compares, with the measurements:

- Paid plan: more hosted concurrency, no hardware, known monthly cost
  (confirmed by the org owner), no new trust boundary.
- Self-hosted on the two macOS hosts, constrained as follows if chosen:
  - Execution: one Linux VM per host (Docker needed for linux/amd64 builds and
    `ubuntu-latest` assumptions), each running ephemeral runners
    (`--ephemeral`, re-registered by a supervisor after every job) under a
    dedicated non-admin user; no host keychain, home directory or LAN access
    (VM network restricted to GitHub/ghcr egress).
  - Placement: a runner group `mctl-gitops-trusted` restricted to
    `mctlhq/mctl-gitops` and to selected workflow files; label
    `mctl-trusted-linux`.
  - Jobs: first only non-required trusted jobs, i.e. the `push: main` runs of
    `validate-manifests.yml` (drift detection after direct bumps; not a merge
    gate). Because `validate-manifests.yml` also has `pull_request`, those jobs
    move by splitting the push path into a new `validate-manifests-main.yml`
    (triggers `push: main` only) that reuses the same job definitions through a
    local reusable workflow, leaving the PR/merge-group file on hosted.
    Required merge-group checks move only after an availability fallback is
    proven; secret-bearing release builds do not move.
  - Fork boundary, enforced twice: runner group workflow restriction (org
    setting, outside the repo) and the CI test below that rejects any workflow
    with a `pull_request`/`pull_request_target`/`issue_comment` trigger whose
    jobs use a self-hosted label. A proof test: a throwaway PR adding a
    `pull_request` job with `runs-on: [self-hosted, mctl-trusted-linux]` stays
    unscheduled (runner group refuses) and the CI test fails.
  - Capacity: measured jobs-per-host in the VM, recorded in the ADR.

Recommendation recorded in the ADR draft: adopt Stage 1 now; if the after
measurement still shows merge-group start latency above 5 minutes during a
burst, prefer the paid plan first (no new trust boundary, covers required
checks), and treat self-hosted as an additive option limited to non-required
trusted jobs. The final choice is the org owner's.

## Alternatives

- Self-hosted first, for all trusted jobs including required checks: rejected
  as a first step; a sleeping or updating machine would stall the merge queue
  (a required check has no runner fallback in GitHub Actions), and release
  builds carry App and registry credentials onto hardware outside the cluster.
- Native macOS runners for script-style jobs only: rejected; almost every job
  assumes `ubuntu-latest` (apt, Docker, linux binaries such as kubeconform with
  pinned SHAs), so the covered set would be tiny.
- One shared cancelling group for merge-group runs: rejected, as the existing
  comment in `validate-manifests.yml` explains, it would cancel position 1's
  check when position 2 starts.
- Move `await-bump` (55-minute waiter) off Actions into a merge-queue webhook:
  would free a slot per release, but changes the release-red signal contract
  that `tests/test_release_bump_enqueue.py` pins; noted in the ADR as follow-up.

## Platform impact

- No cluster, Helm or Argo CD change. No migration.
- Behaviour change: an older PR head's checks and a superseded preview build
  now end `cancelled`. Required checks are evaluated on the latest head, so
  merging is unaffected. The preview-deploy Argo workflow whose build was
  superseded fails with "Build failed: cancelled"; its newer sibling succeeds.
- Risk: a wrong expression makes merge-group runs share a cancelling group and
  the queue drops entries. Mitigation: the merge-group branch always resolves
  to `run_id`, and `tests/test_workflow_concurrency.py` pins it; validate on
  the PR's own merge-group run before relying on it.
- Risk: preview builds keyed by SHA are not superseded. Mitigation: measured in
  Stage 2, widened later if needed.
- Self-hosted (only if adopted): new trust boundary on owned hardware; the
  double enforcement and the ephemeral VM are the mitigations, and rollback is
  reverting `runs-on` to `ubuntu-latest`.
- Cost: none for Stages 1-2; Stage 3 cost is the decision being recorded.
