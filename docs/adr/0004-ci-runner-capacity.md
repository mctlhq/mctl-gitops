# ADR 0004: CI runner capacity for mctl-gitops

**Status:** Proposed (the decision is the org owner's; merging this ADR changes
no runtime, runner or workflow)

Issue: mctlhq/mctl-gitops#2993. Related: #2931 (merge-queue starvation).
Stage 1 (superseding stale runs) merged in #2995 and #3010. The measuring script
is `scripts/ci-queue-latency.py` (#3038).

## Context

Every job in this repository runs on GitHub-hosted runners (`ubuntu-latest`).
The org is on the `free` plan, which caps concurrent hosted jobs. During
DevLoop bursts the queue stalls, merge-group checks wait, and releases that
`await-bump` hold a hosted slot for up to 55 minutes while waiting on that
same queue.

Two diagnoses were mixed up in the issue and must stay apart:

- **Capacity:** too few hosted slots for the burst.
- **Wasted work:** runs for superseded heads and superseded preview builds kept
  running and kept slots. The 1h58m queue wait seen on #2995 was head rebuilds
  of the merge-queue head (#2931), not a lack of runner slots: 15 of 22 direct
  pushes to `main` in two hours were preview bumps, three per `mctl-telegram`
  push.

Stage 1 addresses only the second. This ADR decides whether the first needs
money or hardware.

## Measurements

Produced with `scripts/ci-queue-latency.py` (read-only, 6-hour query chunks, a
truncated or failed read aborts the report).

**Before: 2026-11-22T00:00Z .. 2026-11-24T00:00Z** (4086 runs, before #2995):

| Metric | n | p50 | p95 | max |
|---|---|---|---|---|
| merge-group run created -> first job started | 513 | 0m23s | 6m24s | 11m50s |
| PR enqueue -> merged | 86 | 11m35s | 1h19m48s | 2h20m54s |
| release-deploy dispatch -> bump PR merged | 0 | not measured | not measured | not measured |

Runs cancelled before any job started: 26. Runs with unreadable jobs: 0.

The release metric is empty because release bumps for previews are direct
pushes, not `release-bump/*` pull requests; it does not mean releases were
fast.

**After (a window of equal length that includes a DevLoop burst, after #2995
merged at 2026-11-24T02:39Z): not measured.** No burst had happened when this
was written. The ADR must not be accepted with a capacity decision until this
row is filled in; rerun the script on the burst window and paste the table.

Reading the before numbers: the median start latency is under half a minute,
so slots are normally free. The p95 of 6m24s and the 2h20m queue maximum are
burst effects, and the queue maximum includes the head rebuilds described
above, which Stage 1 removes. How much of the tail was capacity is exactly
what the "after" row will show.

## Facts about the existing hardware and org (read 2026-11-27)

- Org plan `free`. Two org-level self-hosted runners (macOS, x64) are online,
  with the label `agy-reviewer`; no workflow in this repository references a
  self-hosted label today.
- Runner group `Default` is visible to all repositories and allows public
  repositories; it is not restricted to selected workflows. Fork PR approval
  policy is `all_external_contributors` for the org and this repository.
- The machine hosting those runners is an Intel Mac mini: 4 cores
  (i3-8100B), 8 GB RAM, about 20 GB free disk, load about 1.4 with 18 days of
  uptime. It also runs, as a different OS user, four runner registrations for
  other projects, and as the operator user several always-on services: an
  agent worker, an events session, a tunnel, a Codex daemon, a media stack and
  a Colima/Lima Linux VM. The operator's login Keychain, API keys and other
  credentials live on the same host. No hostnames or account names are
  recorded here because this repository is public.
- It counts as existing infrastructure, not a new node (rule "no new nodes"):
  nothing would be provisioned, only an additional runner registration. It
  would still add a new trust boundary, covered below.

## Options

### A. Stay on hosted runners, rely on Stage 1 (cost: none)

Superseded PR checks, label bursts and superseded preview builds now end
`cancelled`. Required checks are evaluated on the latest head, so merging is
unaffected. Measure the "after" window; if merge-group p95 start latency stays
at or below 5 minutes during a burst, nothing further is needed.

### B. Paid GitHub plan (cost: owner to state)

More hosted concurrency, no hardware to maintain, covers required checks, and
adds no trust boundary. The monthly figure is **not known to this ADR**; the
owner confirms it before this option can be chosen.

### C. Self-hosted runners on the Mac mini (cost: operator time, host load)

Rejected as a first step, for these reasons:

1. **Fit.** Almost every job assumes `ubuntu-latest` (apt, Docker, pinned
   linux binaries such as kubeconform). The host is macOS x64 with 8 GB RAM and
   about 20 GB free disk. Running linux jobs means a Linux VM on a machine that
   already runs one for other services; a 4-core, 8 GB host already carrying
   its current services has little headroom, and a burst of parallel validate
   jobs would compete with the always-on services it hosts.
2. **Required checks have no fallback.** A required check cannot fall back to
   a hosted runner. A sleeping, updating or overloaded Mac would stall the
   merge queue, which is the failure this ADR is trying to remove.
3. **Trust boundary.** This repository is public. A self-hosted runner that
   can pick up a job from a fork pull request executes attacker-chosen code on
   hardware that holds operator credentials.
4. **Secrets.** `release-deploy.yaml` passes `APP_PRIVATE_KEY` and
   `GH_PACKAGES_TOKEN` to the build, and `agy-formal-queue.yml` reads
   `DISPATCH_APP_PRIVATE_KEY`. Neither moves to this hardware.

If option C is still wanted later, it is allowed only under all of these
constraints (task 8 of the proposal implements the CI half):

- A dedicated runner group `mctl-gitops-trusted`, restricted to this repository
  and to selected workflow files (an org setting, outside this repo). Not the
  `Default` group.
- Ephemeral/JIT runners (`--ephemeral`, re-registered after every job) in a
  Linux VM under a dedicated non-admin user; no access to the operator
  Keychain, home directory or LAN; egress limited to GitHub and ghcr.
- Only trusted events: `push` to `main` and `workflow_dispatch`. A CI test
  rejects any workflow that has a `pull_request`, `pull_request_target` or
  `issue_comment` trigger and a job using a self-hosted label.
- First candidates are non-required jobs only (the `push: main` run of
  `validate-manifests.yml`, which is drift detection after direct bumps).
  Required merge-group checks move only after an availability fallback is
  proven.
- No host secrets in the job environment; rollback is reverting `runs-on` to
  `ubuntu-latest` and disabling the group.

## Decision (proposed)

1. Adopt Stage 1 (done). Treat option A as the standing answer until the
   "after" window says otherwise.
2. Fill in the "after" row from a real DevLoop burst.
3. If the after window shows merge-group p95 start latency above 5 minutes
   during a burst, prefer option B (paid plan) first, because it covers
   required checks and adds no trust boundary.
4. Option C is not adopted. It stays available as an additive, non-required,
   trusted-events-only option under the constraints above, and only if the
   host is given enough headroom first.

Owner of the final choice: the org owner. Until they accept it, the status
stays Proposed.

## Housekeeping recorded here

Two runs from the issue were stuck in `queued` with zero jobs, holding no
runner slot: `Cloudflare MCP portal health` (2026-10-07) and `CodeQL`
(2026-11-08). `cancel` and `force-cancel` both returned 409 "has not been
queued yet". On 2026-11-27 the first was removed with `gh run delete`. The
second cannot be deleted by a user: the API answers 403, which is consistent
with a run created by GitHub's CodeQL default setup rather than by a workflow
file in this repository. It is left in place; it occupies no slot.

## Open items

- Live proof of preview-build cancellation (T4 of the proposal): needs two
  overlapping `main-<sha>` preview dispatches of one component. All
  dispatches observed so far were more than 20 minutes apart.
- The `release-deploy` dispatch-to-merge metric needs a window with
  `release-bump/*` pull requests; it is empty for preview-only windows.
- `await-bump` (up to 55 minutes holding a hosted slot per release) could move
  off Actions into a merge-queue webhook; that changes the release-red signal
  contract pinned by `tests/test_release_bump_enqueue.py`, so it is a separate
  proposal.
