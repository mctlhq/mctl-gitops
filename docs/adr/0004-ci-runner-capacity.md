# ADR 0004: CI runner capacity for mctl-gitops

**Status:** Proposed (the decision is the org owner's; merging this ADR changes
no runtime, runner or workflow)

Issue: mctlhq/mctl-gitops#2993. Related: #2931 (merge-queue starvation).
Stage 1 (superseding stale runs) merged in #2995 and #3010. The measuring script
is `scripts/ci-queue-latency.py` (#3038, with the release-run fix in #3043).

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
| release-deploy dispatch -> bump PR merged | 5 | 55m27s | 1h23m11s | 1h23m11s |

Release runs without a matched bump PR in the window (excluded, counted): 104.
Runs cancelled before any job started: 26. Runs with unreadable jobs: 0.

The release row covers only releases that went through a `release-bump/*` pull
request (5 of 109 release runs). The other 104 are excluded, not counted as
fast: preview bumps are direct pushes to `main`, so they have no bump PR to
measure against. Read the row as "releases that needed the PR route", not as
the typical release.

**After: 2026-11-25T23:00Z .. 2026-11-27T23:00Z** (1243 runs, after #2995 and
#3010; includes the DevLoop burst of 2026-11-27 around 11:30Z, seven parallel
investigations):

| Metric | n | p50 | p95 | max |
|---|---|---|---|---|
| merge-group run created -> first job started | 63 | 0m05s | 0m52s | 2m04s |
| PR enqueue -> merged | 15 | 6m28s | 14m11s | 16m39s |
| release-deploy dispatch -> bump PR merged | 2 | 43m15s | 1h07m06s | 1h07m06s |

Release runs without a matched bump PR in the window (excluded, counted): 103.
Runs cancelled before any job started: 49. Runs with unreadable jobs: 0.

What the two windows can and cannot be compared on:

- **Load is not comparable.** The after window has 1243 runs against 4086 and
  63 merge-group runs against 513. The 2026-11-27 burst was seven
  investigations, lighter than the 22-23.11 days that motivated #2993. The
  after row shows that Stage 1 holds under a moderate burst; it does not show
  how a 22-23.11-sized day behaves now. Part of the improvement may be lower
  load rather than Stage 1.
- **Supersession is visible.** Runs cancelled before any job started rose from
  26 to 49 while total runs fell to under a third: the Stage 1 groups are
  cancelling superseded work, which is what frees slots.
- **The release row is too small to read.** n=2 after against n=5 before, and
  both are only the releases that took the `release-bump/*` PR route. It is
  reported, not used for the decision.
- **Missing data:** no metric was unreadable (0 runs with unreadable jobs), and
  the script aborts on any truncated or failed read, so the counts above are
  complete for the window rather than a lower bound.

Reading the before numbers: the median start latency is under half a minute,
so slots are normally free. The p95 of 6m24s and the 2h20m queue maximum are
burst effects, and the queue maximum includes the head rebuilds described
above, which Stage 1 removes.

Reading the after numbers: merge-group p95 start latency is 0m52s, well under
the 5-minute threshold in the decision below, and the queue maximum fell from
2h20m to 16m39s. Under the load this window saw, no capacity purchase is
indicated.

## Facts about the existing hardware and org (read 2026-11-27)

- Org plan `free`. No workflow in this repository references a self-hosted
  label today; all CI here runs on hosted runners.
- The org already operates a small number of self-hosted runners on a shared
  operator machine. That machine has no isolation between CI and its other
  duties and no spare headroom for a burst of validate jobs. It would be
  existing infrastructure, not a new node (rule "no new nodes"), but using it
  for this repository would add a trust boundary.
- Host, group and account specifics are deliberately not recorded here: this
  repository is public, and a description of where CI code would run and what
  else lives next to it is useful mainly to an attacker. They are kept in a
  private note.

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

### C. Self-hosted runners on existing org hardware (cost: operator time, host load)

Rejected as a first step, for these reasons:

1. **Fit.** Almost every job assumes `ubuntu-latest` (apt, Docker, pinned
   linux binaries such as kubeconform). Running them on the existing host means
   a Linux VM there, on a machine that has no headroom for a burst of parallel
   validate jobs next to the work it already does.
2. **Required checks have no fallback.** A required check cannot fall back to
   a hosted runner. A sleeping, updating or overloaded machine would stall the
   merge queue, which is the failure this ADR is trying to remove.
3. **Trust boundary.** This repository is public. A self-hosted runner that
   can pick up a job from a fork pull request executes attacker-chosen code on
   hardware that is shared with other duties.
4. **Secrets.** `release-deploy.yaml` passes `APP_PRIVATE_KEY` and
   `GH_PACKAGES_TOKEN` to the build, and `agy-formal-queue.yml` reads
   `DISPATCH_APP_PRIVATE_KEY`. Neither moves to this hardware.

If option C is still wanted later, it is allowed only under all of these
constraints (task 8 of the proposal implements the CI half):

- A dedicated runner group `mctl-gitops-trusted`, restricted to this repository
  and to selected workflow files (an org setting, outside this repo), never the
  shared default group.
- Ephemeral/JIT runners (`--ephemeral`, re-registered after every job) in a
  Linux VM under a dedicated non-admin user; no access to the host's
  credentials, home directories or LAN; egress limited to GitHub and ghcr.
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
2. Fill in the "after" row from a real DevLoop burst (done 2026-11-27: p95
   start 0m52s, see Measurements).
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

- Live proof of preview-build cancellation (T4 of the proposal): **done
  2026-11-27.** Two back-to-back `workflow_dispatch` runs of
  `release-deploy.yaml` for a fictitious probe component `t4-probe-preview`
  (tags `main-aaaaaaa`, then `main-bbbbbbb`, seconds apart): the older run
  46066658762 ended `cancelled` with `build` skipped; the newer run 46066662656
  was not cancelled and stopped at preflight as expected (no repo binding).
  The negative control (a semver release is never cancelled) was not run live;
  it is pinned by `tests/test_workflow_concurrency.py`. Evidence:
  mctlhq/mctl-gitops#2993 (issuecomment-7227952530).
- The `release-deploy` dispatch-to-merge metric needs a window with more
  `release-bump/*` pull requests (n=5 before, n=2 after); it is empty for
  preview-only windows.
- Re-measure on the next day with load comparable to 2026-11-22/23 (several
  hundred merge-group runs in 48 hours) before treating option A as settled
  for that load.
- `await-bump` (up to 55 minutes holding a hosted slot per release) could move
  off Actions into a merge-queue webhook; that changes the release-red signal
  contract pinned by `tests/test_release_bump_enqueue.py`, so it is a separate
  proposal.
