# Design: issue-352-feat-lifecycle-ownership-add-executor-cl

## Current state

### What phase 1 shipped

`orchestrator/lifecycle/` is an ownership client and a policy resolver that owns
no state (`orchestrator/lifecycle/__init__.py`).

- `contract.py` holds the frozen dataclasses (`EntityRef`, `Owner`, `Ownership`,
  `OwnershipAnswer`), the closed verdict vocabulary (`OWNED_BY_ME`,
  `OWNED_BY_OTHER`, `UNOWNED`, `UNKNOWN`, `WROTE_NO_RECORD`) and — deliberately —
  the **only** implementation of HTTP-to-verdict classification, `answer_from`.
  Its module comment records that the classification already drifted once when a
  second copy lived in the Temporal activity, and that "two implementations of
  one safety decision is how that decision becomes a coin flip".
- `client.py` is the synchronous urllib transport (`OwnershipClient`) for CLI
  processes, with an https pin, a no-redirect opener, `BATCH_CHUNK_SIZE = 100`,
  and `acquire` / `progress` / `handoff_start` / `handoff_complete` / `release` /
  `terminal`.
- `policy.py` answers who *should* own a service (`default_owner_for`,
  `merge_authority_for`, `policy_ref_for`), delegating to
  `run_shepherd._service_mode` and `run_shepherd._merge_owner_for` rather than
  copying them.
- `rollout.py` is the four-stage gate `off | observe | enforce | only` behind
  `LIFECYCLE_ROLLOUT_MODE`, with `blocks_on_unknown()` as the single reader of
  the `LIFECYCLE_OWNERSHIP_REQUIRED` break-glass. Its docstring pins one rule
  that constrains this proposal directly: `workflow.patched(...)` is a history
  marker and is never a rollout control.
- `shadow.py` is the observe-stage divergence comparison; it decides nothing.
- `orchestrator/temporal/activities/lifecycle.py` exposes one activity,
  `lifecycle_ownership`, with flat `OwnershipRequest` / `OwnershipResult`
  dataclasses (every field defaulted, so history recorded before a field existed
  still deserializes) and `_PATHS` mapping five ops to
  `/api/v1/lifecycle/ownership/...`.
- `orchestrator/temporal/workflows/dev_loop.py` tracks `self._owner_epoch`
  (initialised at line 635, reset at 1410/1509/1938/2100, refreshed from activity
  results at 1564/1667/1894) and passes it as `epoch=` on progress and handoff
  calls (lines 689, 1273).

### What is missing

There is no `ExecutionClaim` anywhere: a repository-wide grep for
`ExecutionClaim`, `claim_id`, `idempotency_key` and `force-with-lease` returns
only ADR-010 itself. `EntityRef.version` is present and its docstring says it
"becomes a precondition on an execution claim (phase 2, #352) — never on
ownership itself", but nothing reads it as one.

Three concrete defects follow from that.

**The one lease that exists does not fence.** `run_implementer.py` writes the
`attempt` block just before flipping the proposal to `in-progress`:

```python
attempt = {
    "id": os.getenv("WORKFLOW_UID") or str(uuid.uuid4()),
    "started_at": started.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "expires_at": (
        started + timedelta(minutes=130)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}
update_status_yaml(ref, "in-progress", attempt=attempt, failure=None, blocked=None)
```

`run_shepherd._attempt_is_fresh` (line 2669) reads only `expires_at`; the holder
id is written and never compared, and `expires_at` is computed from the worker's
own clock. The `uuid.uuid4()` fallback is non-deterministic precisely in the
retried-pod case, which ADR-010 section 8 calls out by name.

**The authoritative CAS layer is half-built.** `run_shepherd.merge_pr` (around
line 2201) already passes `--match-head-commit` with `pr.head_sha` (line 2221).
The push side does not: `run_implementer._push_followup` is

```python
def _push_followup(repo_dir: Path, branch: str) -> None:
    """Push the follow-up commit to the existing branch (no `-u`)."""
    _run(["git", "push", "origin", branch], cwd=repo_dir)
```

and `_push_and_open_pr` (line 1661) does `git push -u origin <branch>`. Neither
carries a lease, which is the time-of-check/time-of-use hole ADR-010 section 6
describes: an epoch check against mctl-api followed by a push to GitHub is a
check and a mutation against two different systems.

**A fenced attempt has no outcome shape yet — but the right one exists.**
`run_shepherd.FollowupSubprocessError` (line 747) already distinguishes
`transient | deterministic | harness | refused`, where three of the four do not
charge a `review_attempts` slot. ADR-010 section 6 says a fenced claim "aborts
before invoking git, and does not consume a `review_attempts` slot — the existing
transient/deterministic distinction in `apply_followup` already has the right
shape for this."

Also relevant: `apply_followup` (line 2022) does not push at all. It bundles the
findings and forks `run_implementer` with `--review-feedback`, so the push a
claim must fence is inside the implementer process, not the shepherd's.

## Proposed solution

Five additions, each placed so that no safety decision gets a second
implementation.

### 1. Claim types and the single classifier, in `orchestrator/lifecycle/contract.py`

Extend the existing contract module rather than adding a parallel one, because
its whole reason to exist is that two transports must not carry two copies of the
classification. New frozen dataclasses, every field defaulted:

```text
Executor      type, id            (shepherd | pr-steward | devloop-workflow | reconciler)
ExecutionClaim
  claim_id, entity (EntityRef), phase
  owner_epoch        FENCE
  entity_version     FENCE — the head/content hash this attempt is pinned to
  executor, attempt
  lease_until        server clock, informational to the client
  idempotency_key, outcome
  state              active | released | expired | fenced
ClaimAnswer
  verdict, claim, reason, accepted
```

The verdict vocabulary is closed and mirrors the ownership one:
`CLAIM_HELD_BY_ME`, `CLAIM_HELD_BY_OTHER`, `CLAIM_FENCED`, `CLAIM_UNCLAIMED`,
`CLAIM_UNKNOWN`. `ClaimAnswer.may_execute` is true only for `CLAIM_HELD_BY_ME`;
`CLAIM_UNKNOWN` is false, exactly as `OwnershipAnswer.may_mutate` treats
`UNKNOWN`. `HOLDING_CLAIM_STATES = {active}` and `FREE_CLAIM_STATES =
{released, expired, fenced}` are both closed, and a state in neither is
`CLAIM_UNKNOWN` — the same both-sides-closed rule `verdict_for` already applies.

`claim_answer_from(status, payload, asking, *, path, body_empty)` is the single
classifier, written alongside `answer_from` and sharing its rules: a 2xx whose
body is not a claim record is `CLAIM_UNKNOWN`, a 404 on a write is
`CLAIM_UNKNOWN` (missing route, not "no such claim"), a 409 carrying
`code: "fenced"` is `CLAIM_FENCED`, any other 409 is `CLAIM_HELD_BY_OTHER`, and
every 4xx/5xx beyond those is `CLAIM_UNKNOWN`.

`idempotency_key_for(kind, id, phase, owner_epoch, attempt, version, action)` is a
pure function here, verbatim from ADR-010 section 8: `sha256` over the
pipe-joined fields, no wall clock, no UUID.

### 2. `ClaimClient` in `orchestrator/lifecycle/claim.py`

A synchronous urllib client for `run_shepherd` and `run_implementer`, built on the
same `_no_redirect_opener` / https-pin / `OwnershipUnavailable`-to-`UNKNOWN`
machinery as `OwnershipClient`. Methods: `acquire`, `renew`, `check`, `record`,
`release`, mapping to `/api/v1/lifecycle/claims/{acquire,renew,check,record,release}`.

Three properties are enforced client-side:

- **The lease is the server's.** `acquire` sends `lease_seconds`; it never sends
  or computes `lease_until`. A worker with a skewed clock cannot extend its own
  lease.
- **No random attempt.** `acquire` takes an `attempt` string and raises
  `ValueError` on an empty one, the way `OwnershipClient.progress` already
  refuses empty `evidence` — so the failure is legible locally instead of arriving
  as a server 400 the caller never sees.
- **Events are emitted here**, one structured line per decision, using a
  `LOG_PREFIX` in the style of `shadow.LOG_PREFIX`:
  `lifecycle-claim: acquired entity=pull-request:mctlhq/mctl-web#42 phase=review-remediation epoch=3 version=abc123 executor=shepherd/... attempt=... claim=...`,
  with `acquired | rejected | renewed | released | expired | fenced` as the closed
  event vocabulary.

### 3. `execution_claim` activity, in `orchestrator/temporal/activities/lifecycle.py`

A **second** activity next to `lifecycle_ownership` (`lifecycle.py:197`), not an
overload of it: flat `ExecutionClaimRequest` / `ExecutionClaimResult` dataclasses
with every field defaulted, a `_CLAIM_PATHS` map, the same `httpx` transport and
the same short-circuit on `rollout.records_writes()` that `lifecycle.py:209-230`
already applies — and for the reason its comment gives, the gate must stay in the
activity rather than move into `dev_loop.py`, or replay breaks. It calls
`contract.claim_answer_from` and flattens the result; it does not classify.
Registered in `orchestrator/temporal/worker.py` alongside the existing activity.

**Naming, deliberately.** `DevLoopWorkflow` already exposes a
`@workflow.query lifecycle_claim` returning a `LifecycleClaim` dataclass
(`dev_loop.py:336`, `:674-693`) that reports the workflow's *ownership* claim
state — `entity_id / epoch / last_op / last_op_landed / abandoned`. That name is
taken and means something else, so the activity and its types are
`execution_claim` / `ExecutionClaim*`. Reusing `lifecycle_claim` would put two
different concepts behind one word in the one file where a reader is trying to
tell ownership from execution apart.

`dev_loop.py` schedules it and consumes the typed result; no HTTP originates in
`@workflow.defn` code. The workflow's claim calls sit behind a **new, separate**
`workflow.patched("lifecycle-claims")` marker — separate from
`lifecycle-ownership` because `rollout.py` pins one job per switch, and because an
execution recorded under phase 1 must replay unchanged.

### 4. Fencing at the two real mutation boundaries

The early filter is a `claim.check()` immediately before the mutation. The
authoritative CAS is the target system's own precondition:

- `run_implementer._push_followup` gains the claimed head SHA and becomes
  `git push --force-with-lease=<branch>:<expected_sha> origin <branch>`. This is
  the change ADR-010 section 6 names explicitly.
- `run_implementer._push_and_open_pr` keeps `-u` for the create case — the branch
  has no remote ref, and `_branch_exists_on_origin` (line 914) already
  distinguishes the two — but gains `--force-with-lease` on the adopt-existing
  branch path at line 1551.
- `run_shepherd.merge_pr` keeps `--match-head-commit` unchanged; it was already
  correct.

A fenced `check()` raises `FollowupSubprocessError(kind="fenced")` — a fifth
label in the existing closed `FollowupKind` literal (`run_shepherd.py:643`),
sharing the non-charging behaviour of `harness` and `refused` through the derived
`transient` property (`kind != "deterministic"`), with its own operator-facing log
line and its own sentinel exit code beside `EXIT_NO_FOLLOWUP_COMMITS` (42),
`EXIT_BRANCH_MISSING_ON_ORIGIN` (43), `EXIT_OPERATION_TIMEOUT` (44),
`EXIT_ORPHANED_SUBAGENT` (46) and `EXIT_DELIBERATE_NO_OP` (47). The
`MAX_REVIEW_ATTEMPTS` budget (`run_shepherd.py:411`, currently 5) is untouched by
a race the executor did not cause.

This also replaces a real misclassification. Today a push rejected because a
concurrent writer advanced the branch is an ordinary `CalledProcessError` with no
sentinel code, so it lands in the generic `shell-failed` arm
(`run_implementer.py:1891-1901`) and the shepherd reads it as `transient`. A lost
race is currently indistinguishable from a network blip — which is exactly the
"stale executor failure is explicit, not silently retried" property the issue
asks for.

### 5. Handoff, and the union lease

Handoff needs no new endpoint. Ownership already has `handoff/start` and
`handoff/complete` (`client.py` lines 280-300) and the activity already maps
`handoff-start` (`lifecycle.py:105`); completion is what bumps the epoch. What is
missing is a caller — `dev_loop.py` has **no `handoff-start` call site at all**,
so today a workflow that ends simply releases (`_watch_pr` finally,
`dev_loop.py:2349-2364`) and leaves a zero-owner gap for the cron sweeper to
notice. This proposal adds the handoff at that same point: terminal PRs still go
`terminal`, but a non-terminal watch that ends hands off to
`OWNER_SHEPHERD` instead of releasing, so the gap is the deterministic
`handing-off` state ADR-010 path 2 describes rather than an absence.

Claims are fenced **lazily**, on the next `check`/`renew`/`record`, by
comparing `owner_epoch` against the ownership row's current epoch under the same
advisory lock. Nothing sweeps and nothing is materialised — which is what keeps
this from becoming the second scheduler that ADR-010's invariant 9 forbids.

`run_shepherd._attempt_is_fresh` becomes the union ADR-010 section 12 prescribes:
a proposal is held if an active claim exists **or** the yaml lease is unexpired,
and the yaml branch additionally compares the holder instead of only
`expires_at`. At `only` the yaml read drops out.

`run_implementer` gains its first lifecycle wiring of any kind — it currently
imports nothing from `orchestrator/lifecycle/`, even though `client.py:5-7`
already names it as an intended `OwnershipClient` caller. It acquires a claim on
`(devloop-proposal, "{service}/{slug}", implement)` beside the existing
`attempt` write at line 1786, dual-writing both through `enforce`.
`contract.py:31-35` has no executor-side owner constant, so `OWNER_IMPLEMENTER`
is added there alongside the five existing `OWNER_*` values, and the bare
`timedelta(minutes=130)` literal at line 1782 becomes a named constant the claim
lease and the yaml lease both read.

`run_implementer`'s attempt id stops being a UUID. It resolves `WORKFLOW_UID`,
then a deterministic
`sha256("{service}|{slug}|{owner_epoch}|{attempt_ordinal}")` fallback, and
refuses to acquire a claim if neither is derivable. The `.status.yaml` `attempt`
block keeps its existing field shape for backward compatibility, but its id is
never a random value again.

Delegated execution (ADR-010 path 3, `mctlhq/mctl-agents#292`) needs no new type:
the claim's `executor` is the shepherd while `owner_epoch` is the steward's, and
the ownership row does not move. Merge authority is re-evaluated at the merge
boundary through `policy.merge_authority_for` and `run_shepherd._service_mode` —
holding a claim contributes nothing to it, which is the point of
`mctlhq/mctl-agents#344`.

## Alternatives

**Put the claim in `.status.yaml` next to the `attempt` block.** Rejected for the
four reasons ADR-010 section 1 already records and that this repository confirms:
the proposal-less path (`mctlhq/mctl-agents#334`) has no `.status.yaml` at all;
every gitops write goes through Argo under the global `mctl-gitops-main-writes`
mutex, for which `workflows/reconcile.py` sizes its own wait at 35 minutes — the
entire double-drive window this issue exists to close; git's non-fast-forward
rejection is not a per-record CAS, and the standard rebase-and-retry recovery
converts a detected conflict into a silent lost update. That last one is not
theoretical here: `proposal_state._write_status_atomic` documents it in its own
docstring (lines 209-213) — "It does NOT make the surrounding read-modify-write
exclusive: two writers that both load before either replaces still lose one
update" — tracked as `mctlhq/mctl-agents#307`. Building a fence on a
read-modify-write that already loses updates would make an untracked live race
the foundation of the safety property. And the pr-steward has no gitops write
path, so it could not participate at all.

**Fence with Temporal alone — workflow id, `USE_EXISTING`, and signals.**
Rejected because it re-creates the exact defect ADR-010 was written about. The
`shepherd_in_loop` query is workflow memory that dies with the execution, and two
of the required handoff cases — steward to delegated shepherd, and proposal-less
adoption — involve actors that are not Temporal workers at all. A fence only the
Temporal side can see is not a fence.

**A generic distributed lock (Redis/etcd/Redlock).** An explicit non-goal in the
issue, and independently wrong here: it expresses mutual exclusion but not
`owner_epoch`, not `entity_version`, not owner-versus-executor, and not the
recorded `outcome` that makes a retry idempotent. It would also add a datastore
this repository does not have — `pyproject.toml` pins neither a redis nor an etcd
client — for a property four primitives already running in mctl-api supply.

**Ship only `--force-with-lease` and `--match-head-commit`, no claim record.**
Tempting, because the authoritative layer is the one that actually stops the
write. Rejected: it gives no way for a loser to learn who won, no idempotency
dedupe across a Temporal retry, no claim event stream to explain a race
afterwards, and no coverage for mutations that are not git — `.status.yaml`
transitions, PR comments, proposal flips. It satisfies one acceptance criterion
out of eight.

## Platform impact

**Migration.** The four `rollout.py` stages carry this unchanged, and the
governing rule stays "at every stage exactly one mechanism is authoritative, and
disagreement means owned, never free". At `off` no claim HTTP call is made; at
`observe` claims are acquired and fences logged but nothing is blocked, which is
what measures the real race rate before it can cause an outage; `enforce` lets a
fence veto a push or a merge; `only` drops the yaml lease read. No new rollout
switch is introduced — a fifth environment variable competing with
`LIFECYCLE_ROLLOUT_MODE` is exactly what `rollout.py`'s docstring forbids. Two new
tunables are lease durations only: `LIFECYCLE_CLAIM_LEASE_SECONDS_IMPLEMENT`
(default 7800) and `LIFECYCLE_CLAIM_LEASE_SECONDS_REVIEW` (default 1800).

**Server dependency.** `/api/v1/lifecycle/claims/*` does not exist yet; it is a
mctl-api change tracked separately. Until it ships, every claim call returns
`CLAIM_UNKNOWN`, which at `off`/`observe` changes nothing and at `enforce` blocks
pushes. The rollout order is therefore fixed: mctl-api routes, then `observe`,
then the soak, then `enforce`.

**Backward compatibility.** Temporal history: the new activity is additive and
gated by a new patch marker, so executions recorded under phase 1 replay
unchanged, and `tests/test_workflow_replay.py` is the gate. `.status.yaml`: the
`attempt` block keeps its shape and its consumers; only its id derivation
changes, and `_attempt_is_fresh` becomes a union rather than a replacement. The
`ownership:` projection stays read-only and derived; the claim adds no second
projection.

**Resource impact.** Two extra HTTP calls per mutating attempt (acquire, then
check immediately before the mutation) plus one renew per tick for a long
implement run. Against a 130-minute implementer attempt and a 30-minute shepherd
poll this is negligible, and it removes work elsewhere: the `_dev_loop_owns`
thread pool and its 60-second budget are already slated to collapse into one
batched read.

**Risks and mitigations.**

- *An mctl-api outage stalls all pushes at `enforce`.* This is the deliberate
  behaviour inversion ADR-010 section 12 records. Mitigation: the block is scoped
  to push and merge — reads, the projection and human escalation stay permitted —
  and `LIFECYCLE_OWNERSHIP_REQUIRED=false` is the documented break-glass, read
  only through `rollout.blocks_on_unknown()`.
- *`--force-with-lease` misuse deletes a colleague's commits.* Mitigated by
  always pinning the explicit expected SHA form
  (`--force-with-lease=<branch>:<sha>`), never the bare flag, whose implicit
  remote-tracking ref can be refreshed by an intervening fetch.
- *A wrong `entity_version` fences a healthy executor on every tick.* This is why
  the proposal hash excludes the derived `ownership:` block, and why the fenced
  outcome is non-charging: a mis-derived version costs ticks, never a proposal
  flipped to `review-stuck`. The `observe` stage exists to surface exactly this
  before it can block anything.
- *`claim_answer_from` drifts from `answer_from`.* Both live in `contract.py`,
  and a test asserts they classify the shared status codes identically. The
  module comment already records what happened the last time one safety decision
  had two implementations.
- *Two claim-state vocabularies, Python and Go.* Same weakness `shadow.py`
  already documents for the divergence classes: a test pins the literals and
  names the Go file, because CI cannot read across repositories.
