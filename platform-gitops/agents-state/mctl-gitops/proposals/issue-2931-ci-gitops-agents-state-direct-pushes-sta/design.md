# Design: issue-2931-ci-gitops-agents-state-direct-pushes-sta

## Current state
- Agent writers. Each of these templates under `platform-gitops/argo-workflows/cluster-templates/`
  has a `commit-and-push` template guarded by `synchronization.mutex: mctl-gitops-main-writes`:
  `cwft-mctl-agents-investigate.yaml` (~l.1041), `cwft-mctl-agents-implement.yaml` (~l.1096),
  `cwft-mctl-agents-approve.yaml` (l.568), `cwft-mctl-agents-shepherd.yaml` (l.959),
  `cwft-mctl-agents-reconcile.yaml` (l.457) and `cwft-mctl-agents-run.yaml` (~l.1207).
  Each step does a fresh clone, lays a handoff artifact over it, `git add`s only agents-state paths,
  and pushes with `for i in 1 2 3 4 5; do git push origin HEAD:main || git pull --rebase origin main; done`
  (for example approve l.794-820), using the deploy key mounted at `/secrets/deploy-key`. The image is
  `alpine/git:2.43.0`, the step deadline is about 300 s, and the workflow deadlines are 600 s (approve),
  1800 s (reconcile), 3600 s (run) and 7200 s or more (investigate, implement, shepherd). The incident
  responder runs through `cronworkflow-mctl-agents-incidents.yaml` (`15 * * * *`, mode=incident-responder)
  and uses the same templates.
- The mutex is template-scoped on purpose (investigate comment ~l.1043: the 2026-08-06 storm).
  `platform-gitops/argo-workflows/config/mutex-forensics-watchdog.yaml` alerts on waiters on that mutex
  older than 5 minutes.
- Merge queue checks. `.github/workflows/validate-manifests.yml` runs on `pull_request`, `push` to main
  and `merge_group`. `validate` aggregates the `validate-N` shards (gitops#2721). `cloudflare-plan.yml`
  and `agy-formal-queue.yml` also run on `merge_group`. `CLAUDE.md` documents the 120-minute removal of
  queue entries whose checks do not report.
- Image bumps already use the queue: the `enqueue-bump` job in `gitops-bump.yaml` (~l.707) and in
  `release-deploy.yaml` (~l.887). So agents-state is the only frequent direct pusher to `main`.
- Argo CD is already shielded from this commit rate:
  `platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml` l.28-33 sets
  `manifest-generate-paths` because "bot commits under agents-state/ arrive 10-20x/h" (#970).
  Nothing deploys from agents-state.
- `docs/runbooks/mctl-api-release-hold.md` l.65 lists these pushes as path P6 (BLOCKING-UNKNOWN,
  template guard only).
- Agent pods already receive a GitHub App token as a file (`github-token-file` volume, for example
  `cwft-mctl-agents-shepherd.yaml` l.190, consumed at `/var/run/gh/github-token`). Delivery is governed
  by `docs/runbooks/agent-credential-delivery.md` and its CI inventory validator. Pods reach
  api.github.com through `agent-egress-proxy.mctl-agents-egress`.
- No workflow in `.github/workflows/` reads merge queue state or alerts on queue starvation.

Deployed state checked:
- No tenant service is involved: the change is to CI workflows and Argo ClusterWorkflowTemplates, so no
  `services/<tenant>/<service>/values.yaml` applies. `$MCTL_GITOPS_ROOT/services` and `tenants` were
  not needed.
- `git log` in the clone: it is shallow and shows only the latest commit (`8deb841 ... mctl-agents[bot]
  chore(agents): shepherd run 2026-11-22`), so the commit rate in the issue could not be checked
  independently. Gap: the evidence about commit rate and queue rebuilds comes from the issue only.
- GitHub merge queue state (#2923/#2924/#2927) and `validate` merge_group durations: not observable from
  this run (no GitHub API access). These are recorded under Open questions in requirements.md.
- No mctl MCP tool was called: none exposes GitHub merge queue state.

## Proposed solution
Two independent parts, each behind its own switch.

### Part A: starvation detection (ships first, changes no behaviour)
- New `scripts/merge-queue-starvation.py`. Pure decision logic plus a thin GitHub client.
  - It reads `repository.mergeQueue(branch: "main") { entries { position state enqueuedAt pullRequest { number headRefOid } headCommit { oid } } }` over GraphQL.
  - It counts rebuilds of the head entry: the distinct `head_sha` values of `merge_group` runs of
    `validate-manifests.yml` on `refs/heads/gh-readonly-queue/main/pr-<N>-*` created since `enqueuedAt`
    (REST `actions/workflows/validate-manifests.yml/runs?event=merge_group`).
  - It counts direct pushes since `enqueuedAt`: commits on `main` by `mctl-agents[bot]` with a
    `chore(agents):` subject.
  - It fails when head age is at least `MQ_HEAD_MAX_AGE_MIN` (45), or rebuilds are at least
    `MQ_MAX_REBUILDS` (3). It exits with status 2 and "unknown" on any read error.
- New `.github/workflows/merge-queue-starvation-watch.yml`. Triggers: `schedule: '*/10 * * * *'` and
  `workflow_dispatch`. It has `permissions: contents: read, actions: read, pull-requests: read`, uses
  `GITHUB_TOKEN` only, has no environment and no secrets, and runs only on the default branch. A red run
  plus an `::error::` annotation is the alert. Notification beyond that is an open question.
- Tests: `tests/test_merge_queue_starvation.py`, wired into `validate-manifests.yml` next to the other
  `tests/test_*.py` steps.

### Part B: queue-aware deferral of agents-state pushes
- New script `platform-gitops/argo-workflows/scripts/merge-queue-quiet-wait.sh` (POSIX sh, curl + jq).
  - Inputs: `MQ_GATE_MODE` (`off|shadow|enforce`), `MQ_GATE_MAX_WAIT_S` (default 900),
    `MQ_GATE_POLL_S` (15), and the token file path.
  - Algorithm:
    1. Read the queue. On error, log and exit 0 (fail open).
    2. If no entry is in AWAITING_CHECKS, exit 0.
    3. Record the head PR number H.
    4. Poll. Exit 0 as soon as H is no longer in the queue (it merged or was removed), or no entry is in
       AWAITING_CHECKS, or the time limit is reached (with a `WARN` line).
    5. In `shadow` mode, compute and log the decision and the wait it would have taken, then exit 0
       without sleeping.
  - Why "wait for H to leave the queue": every deferred writer then pushes in a burst right after a
    merge. That burst rebuilds the next group only seconds after it started, while the alternative is
    rebuilding a group minutes into its checks. Each queue head therefore gets one full check cycle, so
    throughput no longer depends on agent activity, up to the time limit.
- New template `await-merge-queue-quiet`. It has no mutex, its own `activeDeadlineSeconds` (limit plus
  60 s), the token from the existing `github-token-file` volume, egress through the existing proxy env,
  and a pinned image that already ships curl and jq (implementer to confirm; `alpine/k8s:1.33.12` is
  already pinned in `cwft-mctl-agents-shepherd.yaml` l.1457). It is added as a step or dependency
  immediately before `commit-and-push` in investigate, implement, shepherd, run and reconcile
  (reconcile limit 300 s because of its 1800 s deadline).
  - `continueOn: {failed: true}` and `error: true`, so a broken gate can never skip `commit-and-push`.
  - It runs outside the mutex: waiting holds no lock, and pushes stay serialized exactly as today.
  - The script is fetched from the clone the template already makes. If no clone exists in that step,
    the script is inlined like `release-gate-guard.sh` usage. The implementer picks one; a test pins
    that the inlined and file copies stay identical.
- `approve` is exempt: it is human-latency-sensitive, rare and has a 600 s deadline.
- The mode is a workflow parameter `merge_queue_gate` with default `shadow` in each CWFT. After one week
  of shadow logs confirm the expected decisions, a follow-up PR flips the default to `enforce`.
- Credential delivery: add the new template as a consumer in the agent credential inventory, so that the
  CI validator described in `docs/runbooks/agent-credential-delivery.md` passes. The token is only used
  for GET/GraphQL reads.
- Docs: a new section in `docs/runbooks/mctl-api-release-hold.md` P6 (or a new
  `docs/runbooks/merge-queue-starvation.md` linked from `CLAUDE.md`) covering the gate, the switches and
  the watch.

## Alternatives
- Batching or coalescing commits per minute (option 1): it needs a shared flusher that holds other
  workflows' artifacts and rebases them, which is a new single point of failure. It lowers the rate but
  still breaks a group whenever a flush lands mid-check. Waiting for the queue achieves coalescing in
  time without a new component.
- Dedicated agents-state branch or repository (option 2): it removes the coupling entirely and shrinks
  the P6/#2543 surface. But mctl-api (decide page, proposal content digest computed against mctl-gitops
  `main`), the amendment flow ("edit requirements.md on mctl-gitops main through a PR"),
  `scripts/proposal-content-digest.py` and the mctl-agents readers all assume `main`. That is a
  multi-repo migration; it is recommended as a follow-up, and this proposal does not block it.
- Agents-state through PR + queue (option 3): each status write would cost a full queue cycle and
  compete with human PRs, which makes the starvation worse.
- Waiting inside the `commit-and-push` mutex: the step deadline (~300 s) is shorter than one validate
  cycle, and holding the lock would trip the mutex watchdog and serialize unrelated writers.

## Platform impact
- No migration. Templates change behaviour only in `enforce` mode, and the default is `shadow`.
- Latency: in `enforce` mode, agents-state writes can be delayed by up to 900 s (300 s for reconcile),
  but only while a merge group is building. When the queue is idle, the delay is one API call.
- Resources: one small pod per agent run (requests about 50m/64Mi) that is mostly sleeping. The watch
  costs one Actions job every 10 minutes, with read-only API usage within rate limits (about 4 calls per
  poll per waiting pod).
- Risks and mitigations:
  - API outage stalls agents: the gate fails open on errors and has a hard time limit.
  - A broken gate skips the push: `continueOn` plus a test that asserts `commit-and-push` does not
    depend on the gate's success.
  - Token scope creep: the gate makes reads only, and the inventory entry is validated in CI.
  - Long queue with continuous merges: the gate releases at each merge, so writers are never starved.
  - Agent workflow deadline overrun: each limit is set below the workflow's remaining deadline.
- Security: no new secret and no new write path. The P6 surface is unchanged (neither widened nor
  narrowed).
