# Bind implementer admission to Argo's serialization width, and record a queue-kill distinctly

## Context

`run-implementer` in `cwft-mctl-agents-implement.yaml` is guarded by the
capacity-1 Argo mutex `mctl-agents-proposal-claims`, while Temporal admits
`IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES = 3` implement submits at once
(`orchestrator/temporal/constants.py`, and `"3"` in
`services/admins/mctl-agents-worker-implement/values.yaml`). The two numbers
are set independently and nothing makes them agree. The 2026-09-19 00:12-00:31Z
burst is what that costs: six implementers created inside 19 minutes, every one
of them killed at creation time plus 2h00m, having done between zero and
nineteen minutes of real work. `dev_loop.py` already records the coupling as an
expectation ("N and the mutex capacity have to move together - ADR-008 D7
records that the gitops mutex is expected to be at least N") but no code, test
or CI check enforces it.

Part of the hole is already closed. mctl-gitops moved the 7200s budget off the
workflow spec and onto the `run-implementer` template, where it is applied to
the pod and therefore starts after the mutex is acquired; the spec keeps a
28800s runaway guard. mctl-agents #395 added the admission queue
(`mctl-dev-loop-implement`), the node-graph classifier
(`orchestrator/temporal/implement_outcome.py`) and the `pre_start` requeue.
What remains is exactly what this issue names: admission width is still 3 where
Argo's width is 1, so two of every three admitted submits burn an admission
slot while queued inside Argo against the spec-level guard; the pod-scoped
deadline invariant is unpinned and can silently regress; and `pre_start` lives
only in Temporal runtime state, so nothing durable - not `assert-attempt`, not
`.status.yaml`, not the execution record read by `mctl_list_agent_executions` -
can tell "killed while queued" from "ran and produced nothing".

## User stories

- AS the DevLoop orchestrator I WANT surplus implement work to wait in
  Temporal rather than inside Argo SO THAT a burst of approvals well past the
  serialization width completes every item instead of losing its tail.
- AS a platform operator I WANT admission capacity and Argo's serialization
  width to be one coupled decision SO THAT raising N cannot silently create
  runs that are killed before they execute.
- AS a platform operator I WANT CI to fail when the implement CWFT stops
  charging queue time outside the attempt SO THAT the pod-scoped deadline fix
  cannot be reverted unnoticed by the repository that depends on it.
- AS the recovery plane (incident responder, reconciler, a human on triage) I
  WANT a run killed while it still held no lock to be recorded with a distinct
  reason SO THAT it is requeued as unattempted work rather than triaged as an
  agent that tried and produced nothing.

## Acceptance criteria (EARS)

- WHEN the implementation worker starts THE SYSTEM SHALL log, on one line, the
  configured `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`, the declared Argo
  serialization width for `run-implementer`, and the effective capacity it will
  poll with.
- IF the configured capacity exceeds the declared Argo serialization width THEN
  THE SYSTEM SHALL poll with the width as its effective capacity and SHALL warn
  that the configured value was reduced, naming both settings.
- IF no Argo serialization width is declared in the environment THEN THE SYSTEM
  SHALL assume a width of 1, because the checked-in template declares a
  capacity-1 mutex and the fail-closed direction is the one that never admits
  work Argo cannot run.
- WHILE every effective-capacity slot is occupied THE SYSTEM SHALL leave further
  implement activities Scheduled in Temporal, creating no Argo workflow and
  starting no Argo deadline for them.
- WHEN an implement submit ends with no `run-implementer` pod having executed
  THE SYSTEM SHALL classify the result `pre_start`, derive a pre-start reason
  from Argo's node graph (`queued` when the node was blocked on a
  synchronization lock, `unscheduled` when Argo accepted the workflow but never
  placed a pod, `unknown` otherwise) and requeue without counting an attempt,
  up to `MAX_PRESTART_REQUEUES`.
- WHEN a `pre_start` outcome is observed THE SYSTEM SHALL include the outcome
  and the pre-start reason in the durable execution record posted to
  `/api/v1/agents/executions`, and SHALL expose both through the
  `implement_execution` query.
- IF mctl-api rejects the execution record because it does not yet understand
  the added fields THEN THE SYSTEM SHALL retry once with the previous payload
  so that the row is still recorded.
- WHEN the loop gives up after `MAX_PRESTART_REQUEUES` THE SYSTEM SHALL fail
  with `ImplementationNotStarted` and a message that names the pre-start reason
  and the requeue count, never a generic implementation failure.
- WHEN the test suite runs with `MCTL_GITOPS_ROOT` pointing at an mctl-gitops
  checkout THE SYSTEM SHALL fail if `cwft-mctl-agents-implement.yaml` declares
  no template-level `activeDeadlineSeconds` on `run-implementer`, if the
  spec-level deadline is smaller than one full drain of the declared width, or
  if the declared serialization width is smaller than this repository's default
  admission capacity.
- IF the mctl-gitops checkout is absent THEN THE SYSTEM SHALL error under CI
  and warn locally, matching `orchestrator/validate_manifest.py`'s existing
  treatment of a missing sibling checkout.
- WHEN the burst regression test replays the 2026-09-19 00:12-00:31Z shape
  against a submit fake that models Argo's serialization width THE SYSTEM SHALL
  complete every item and SHALL produce no `pre_start` result.

## Out of scope

- Removing the `mctl-agents-proposal-claims` mutex. ADR-010's non-goals record
  why it stays: the admin-only `mctl_trigger_implementer` bypasses Temporal
  admission entirely, and the server-side claim that would replace the mutex is
  mctl-api#337.
- Routing `mctl_trigger_implementer` through Temporal admission. That is an
  mctl-api change; this proposal only makes the bypass survivable by keeping
  Argo's width honest and recording a queue-kill distinctly.
- Editing `cwft-mctl-agents-implement.yaml` itself. The implementer's PR lands
  in `mctlhq/mctl-agents`; the gitops half (an `assert-attempt` start-marker,
  and any later widening of the mutex into a ConfigMap-backed semaphore) is
  specified in design.md and tracked as a companion mctl-gitops change. This
  repository's contribution is the CI guard that fails when the two drift.
- Changing `IMPLEMENTER_TIMEOUT_SECONDS` (5400), the 7200s pod budget or the
  28800s spec guard. Their sizing is not what this issue is about.
- Writing an in-progress marker into git mid-attempt. ADR-008 keeps git as
  durable lifecycle state and Temporal/Argo as durable runtime state; the
  durable pre-start record belongs on the execution row, not in `.status.yaml`.

## Open questions

- Does `mctl-api`'s `/api/v1/agents/executions` handler ignore unknown JSON
  fields, or reject them? The design assumes "ignores" (the common Go
  `encoding/json` default) and fails safe with a one-shot retry on the older
  payload, so either answer is survivable. The persistence of `outcome` and
  `pre_start_reason` needs a companion mctl-api issue either way.
- Argo does not expose "did this node get a pod" as a step variable, so
  `assert-attempt` cannot be fixed from this repository alone. The design
  proposes an always-written, optional start-marker artifact per attempt, by
  analogy with the `changes` handoff already in that template; whether Argo
  resolves a parameter-interpolated artifact key for a skipped step must be
  confirmed on a canary before that companion PR merges.
- Whether the eventual widening uses `synchronization.semaphore` with a
  `configMapKeyRef` (one number, read by both the template and the worker) or
  waits for ADR-010's server-side claim at `enforce`. Both are compatible with
  the width-coupling guard proposed here; the guard does not decide it.
