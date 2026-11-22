# Stop mctl-agents agents-state pushes from starving the main merge queue

## Context
`main` merges through a merge queue (ruleset `main-protection`, mctlhq/.github#351). The mctl-agents
ClusterWorkflowTemplates (`cwft-mctl-agents-{investigate,implement,approve,shepherd,reconcile,run}.yaml`)
end in a `commit-and-push` step that pushes `platform-gitops/agents-state/**` straight to `main` with the
bypass deploy key (path P6 in `docs/runbooks/mctl-api-release-hold.md`). Every push from outside the queue
makes GitHub rebuild every merge group on the new tip, so the queue head's required checks (`validate`
with 4 shards, `reserved-hosts`, `cloudflare-plan`, `agy-formal-review`) start over. On 2026-11-22, 22
agent commits landed between 22:00 and 23:14 UTC, 40 s to 5 min apart. The queue head #2923 was rebuilt
at least four times and never finished. #2924 and #2927 got no merge group at all, and entries are
dropped after 120 minutes.

The issue lists four options and decides none of them. This proposal takes two steps that can ship
without a cross-repo migration: (a) detection, which alerts when the queue is being starved, and
(b) a queue-aware deferral of agents-state pushes. While a merge group is building, an agent push waits,
with a time limit, until that group merges or leaves the queue. Waiting writers then push together right
after a merge, when a rebuild costs the next group only seconds. Moving agents-state off `main`
(option 2) is the structural fix and is recorded as a follow-up, not built here.

## User stories
- AS a platform engineer I WANT a PR in the merge queue to merge within one check cycle even during a DevLoop burst SO THAT human and agent PRs are not blocked for hours.
- AS an on-call operator I WANT an alert when the merge queue head is rebuilt repeatedly or waits too long SO THAT starvation shows up as an alert, not as a PR "stuck in QUEUED".
- AS an mctl-agents maintainer I WANT the deferral to be bounded and to fail open SO THAT agent status writes are never lost and a GitHub API outage never stalls the dev loop.

## Acceptance criteria (EARS)
- WHEN an mctl-agents workflow reaches its push stage AND the `main` merge queue has an entry in state AWAITING_CHECKS THE SYSTEM SHALL wait before pushing to `main`, polling the queue at a fixed interval (default 15 s).
- WHEN the queue entry that was the head at the start of the wait leaves the queue (merged or removed), OR the queue has no AWAITING_CHECKS entry THE SYSTEM SHALL end the wait and run the existing `commit-and-push` unchanged.
- IF the wait reaches its limit (default 900 s; 300 s for `cwft-mctl-agents-reconcile`) THEN THE SYSTEM SHALL log a warning naming the queue head and push anyway.
- IF the GitHub API call fails, returns malformed data, or no token is available THEN THE SYSTEM SHALL log the error and push without waiting (fail open). A read that failed is never treated as "queue empty".
- WHILE the gate mode is `shadow` THE SYSTEM SHALL log the decision it would have made and its would-be wait time, and SHALL NOT wait.
- WHILE the gate mode is `off` THE SYSTEM SHALL skip the gate entirely.
- THE SYSTEM SHALL NOT apply the gate to `cwft-mctl-agents-approve.yaml`. It is human-triggered, rare and has a 600 s workflow deadline.
- THE SYSTEM SHALL run the gate outside the `mctl-gitops-main-writes` mutex, so that waiting never holds that lock or triggers `mutex-forensics-watchdog` waiter alerts.
- WHEN the scheduled starvation watch runs (every 10 minutes) AND the queue head has waited longer than the age threshold (default 45 min) OR its merge group has been rebuilt at least N times (default 3) since it was enqueued THE SYSTEM SHALL fail the run with an `::error::` annotation. The annotation names the head PR, how long it has waited, the rebuild count and the number of direct pushes to `main` since it was enqueued.
- IF the starvation watch cannot read the merge queue THEN THE SYSTEM SHALL fail the run with an "unknown" error, never pass silently.
- THE SYSTEM SHALL keep the existing `commit-and-push` path scoping (`git add` limited to agents-state), the 5x push/rebase loop and the deploy-key usage unchanged.

## Out of scope
- Moving agents-state off `main` to a dedicated branch or repository (option 2). This is the structural fix and needs mctl-api, mctl-agents and approval-digest changes; it is a follow-up issue.
- Routing agents-state writes through PRs and the queue (option 3).
- Changing the merge queue ruleset, its required checks or the 120-minute timeout.
- Changing `gitops-bump.yaml` / `release-deploy.yaml`. Their bumps already go through the queue (`enqueue-bump` job).
- Shrinking the P6 / #2543 deploy-key bypass surface.

## Open questions
- Alert channel: this proposal makes the watch run fail (red signal, like `await-bump`). Is a Telegram notification also wanted? If so, which existing notifier and secret should it use?
- Default thresholds (900 s wait limit, 45 min head age, 3 rebuilds) are estimates. They assume `validate` finishes in under about 10 minutes. The real duration of the `validate` shards on merge_group was not measured.
- Is a deferral of up to 15 minutes in agents-state status writes acceptable to mctl-api readers (decide page, `mctl_get_dev_loop_approval`) and to the shepherd? Nothing found in this repo depends on sub-minute freshness, but mctl-api and mctl-agents were not inspected.
- Should option 2 (dedicated agents-state branch or repo) be filed now as its own issue, linked to #2543?
