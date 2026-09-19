# Design: incident-89787472

## Diagnosis
The `mctl-agents-implement` ClusterWorkflowTemplate
(platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml)
sets `spec.activeDeadlineSeconds: 7200` (documented in the file as a "hard 2h
safety ceiling"), while the `run-implementer` step's own internal budget,
`IMPLEMENTER_TIMEOUT_SECONDS`, is `5400` — and that budget applies to BOTH the
primary attempt (`implement`, oauth account 1) and, when the primary does not
succeed, the fallback attempt (`implement-fallback`, oauth account 2). Those
two attempts run sequentially, one after the other, in the same workflow.

For this run (mctl-agents-implement-9a41e408, proposal
issue-333-feat-human-input-durable-agent-clarifica):
- The primary `implement` step alone ran for ~7290s (00:29:38Z -> 02:31:08Z),
  i.e. essentially the entire 7200s workflow deadline, before Argo's
  controller caught up and killed it for "Step exceeded its deadline". The
  workflow-level deadline (02:29:38Z) had therefore already passed before
  this step was even torn down.
- Argo nonetheless went on to START `implement-fallback` at 02:31:08Z (two
  minutes after the deadline had already elapsed) and let it run a further
  20 minutes before discovering the deadline and failing it. The fallback
  attempt could not have done any real work in that window — it never had a
  time budget in the first place, since the deadline was already exhausted
  before it started.
- Argo then STARTED `commit-and-push` at 02:51:08Z, again well past the
  deadline, and let it run another 20 minutes before failing it with `retry
  exceeded workflow deadline 2026-09-19 02:29:38 +0000 UTC`.
- The workflow finally reported Failed at 03:11:18Z — 9690s after start,
  matching the incident summary, and ~41 minutes later than the documented
  "hard 2h ceiling" implies it should.

Root cause: `activeDeadlineSeconds` (7200s) is smaller than what the
template's own documented two-attempt retry design can legitimately need —
`IMPLEMENTER_TIMEOUT_SECONDS` × 2 attempts alone is already 10800s, before
counting the initContainer clones or the commit-and-push step. This means:
1. Whenever the primary attempt consumes close to its full 5400s budget, the
   fallback (added specifically so a quota-exhausted primary account can
   retry on a second account, per the template's own comments) is
   structurally unable to get a fair time budget — it starts already
   effectively out of time.
2. Rather than failing promptly once the workflow deadline is reached, Argo
   continues advancing the Steps sequence (fallback, then commit-and-push),
   each of which runs for a further ~20 minutes before its own deadline
   check fires. This turns a single missed 7200s ceiling into a ~9690s
   actual runtime, burning an extra ~40 minutes of a worker slot (this
   template also holds the `mctl-agents-proposal-claims` mutex for the
   `implement`/`implement-fallback` steps) for no benefit, since none of the
   post-deadline steps could complete successfully anyway.

This is a configuration/timing mismatch between two numeric fields in the
same file, not an application code bug, and not something the implementer
proposal's content (issue-333) caused.

## Confidence: MEDIUM
The Argo node timeline evidence (start/finish timestamps and failure
messages per step, captured above) is direct and conclusive for the sequence
of events. What is not independently verified here (no shell access, and
orchestrator/run_implementer.py lives in the mctl-agents repo, not
mctl-gitops) is exactly how IMPLEMENTER_TIMEOUT_SECONDS is enforced inside
the Python orchestrator — e.g. whether it wraps only the Claude Agent SDK
call or the whole step including clone/build-verification, which would
explain why the primary attempt's wall-clock time (~7290s) ran past its
5400s internal budget in the first place. That detail affects the exact
new value to choose but not the core diagnosis: 2 x IMPLEMENTER_TIMEOUT_SECONDS
already exceeds activeDeadlineSeconds today, and post-deadline steps still
get started and take ~20 minutes each to be torn down.

## Proposed Fix
File: `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`

Field: `spec.activeDeadlineSeconds`
Current value: `7200`
New value: `12000`

This gives headroom for the documented worst case — primary attempt up to
5400s + fallback attempt up to 5400s (10800s total) — plus the initContainer
clones, the commit-and-push step (with its own retryStrategy, up to 5
attempts with backoff), and the assert-attempt step, while remaining a
bounded, explicit ceiling (not "unlimited"). `max_proposals` stays at `1`
and `IMPLEMENTER_TIMEOUT_SECONDS` stays at `5400` — both are unrelated,
already-tuned safety boundaries per the file's own history (max_proposals=1
after incident-0f3b9ea3; IMPLEMENTER_TIMEOUT_SECONDS raised 900->2400->5400
after killing legitimately-progressing runs) and this fix does not need to
touch either.

Update the comment above `activeDeadlineSeconds` to explain the new value is
sized to cover a full primary+fallback pair, so a future reader does not
reintroduce this same mismatch by raising IMPLEMENTER_TIMEOUT_SECONDS again
without re-checking this field.

## Scope
Minimal. Only `spec.activeDeadlineSeconds` (and its explanatory comment) in
`cwft-mctl-agents-implement.yaml` changes. No changes to `max_proposals`,
`IMPLEMENTER_TIMEOUT_SECONDS`, retry counts, or any other template.
