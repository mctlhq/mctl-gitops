# Design: incident-895edee7

## Confidence: LOW

No Loki logs and no Argo workflow audit record were available for the
specific failed run named in this incident, so the exact failing step
inside that run is not directly observed. The diagnosis below is built
from (a) a duration-band pattern already established across several other
`mctl-agents-implement` / `mctl-agents-run` incidents triaged in this same
repo, and (b) live queue evidence captured at triage time showing a third
run of the same workflow actively blocked on the lock this diagnosis
implicates. That is strong circumstantial evidence, not a confirmed
stack trace — the implementer should treat the root cause as likely,
not certain, before spending significant effort on it.

## Diagnosis

`cwft-mctl-agents-implement` failed twice within a 30-minute window
(1079.42s at 02:45Z, and again at 03:10Z per occurrence_count=2 on this
incident's fingerprint `workflow_failed:implement::`). Both durations
fall inside the ~300-1250s band that prior triage passes on this same
incident class (see `mctl-gitops/proposals/incident-b11a9798`'s design.md)
already associated with contention on the shared
`argo-workflows/Mutex/mctl-gitops-main-writes` lock, as opposed to the much
shorter ~100-210s band associated with OAuth/auth fast-fails
(`incident-mctl-agents-oauth-quota-exhaustion`).

That association is corroborated directly: at the moment this incident was
triaged, `mctl_list_recent_agent_runs` showed a THIRD implement run
(`mctl-agents-implement-1784950800`, submitted 03:40:46Z) sitting in
`submitted` status with the message "Waiting for
argo-workflows/Mutex/mctl-gitops-main-writes lock. Lock status: 1/1" — i.e.
the lock was fully held and unavailable in real time, not a hypothetical.

The likely structural cause: `cwft-mctl-agents-implement.yaml` acquires
this mutex at the top-level `spec.synchronization` (covers the ENTIRE
workflow — clone, Go-cache restore, the ~10-20 minute Claude SDK
implementer run(s), Go-cache save, and finally the actual git
commit-and-push), even though only the final `commit-and-push` template
needs exclusive access to `mctl-gitops` main. `cwft-mctl-agents-run.yaml`
and `wft-delete-tenant.yaml` share the exact same mutex name at the same
workflow-wide scope (see comments in those files: "Same mutex name as
wft-delete-tenant.yaml so we share the lock" / "Same shared mutex as
cwft-mctl-agents-run"). With three different workflow kinds each holding
this one global lock for their full multi-minute runtime instead of just
the seconds needed to commit, ticks queue behind each other far more than
necessary, increasing the odds that a queued run's Pending-on-mutex node
gets caught up in whatever ends a run as Failed (evidenced separately by
several currently-`accepted`-but-not-yet-implemented proposals in this
same repo — `incident-argo-mct`, `incident-1820e6ee`,
`incident-agents-run-f868212c` — all carrying the note "implementer
produced no commits; reverted to accepted", consistent with implementer
runs themselves repeatedly failing to make progress under the same lock).

## Proposed Fix

Narrow the mutex to only the step that actually needs it.

File: `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`

- Current (workflow-wide, ~line 43-45):
  ```yaml
  spec:
    ...
    synchronization:
      mutex:
        name: mctl-gitops-main-writes
  ```
  Remove this block from `spec:`.

- New: add the same block as a template-level field on the
  `commit-and-push` template (~line 487), sibling to that template's
  `script:` key:
  ```yaml
    - name: commit-and-push
      synchronization:
        mutex:
          name: mctl-gitops-main-writes
      script:
        image: alpine/git:2.43.0
        ...
  ```

This keeps the lock's purpose intact (still serializes every writer of
`mctl-gitops` main across `implement`, `run`, and `delete-tenant`) while
reducing the window each run holds it from the full workflow duration
(minutes) to just the git commit/push step (seconds), which should reduce
queueing and the failures that appear to result from it.

## Scope

Minimal. Only `cwft-mctl-agents-implement.yaml`, moving one
`synchronization.mutex` block from workflow-level `spec:` to the
`commit-and-push` template. `cwft-mctl-agents-run.yaml` and
`wft-delete-tenant.yaml` have the identical workflow-wide pattern and
would likely benefit from the same change, but that is left as a follow-up
(see tasks.md) rather than folded into this fix, to keep this change
scoped to the workflow actually named in this incident.
