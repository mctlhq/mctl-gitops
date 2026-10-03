# Design: issue-488-dispatcher-residual-p3s-after-461-option

## Current state

### The engine-ref guard and the reason it gives

`orchestrator/temporal/dispatcher.py::Dispatcher._dispatch` is the first thing
that runs once a claimed request's work item resolves to a runnable mctlhq
issue URL (`dispatch_once` lines 388-392 derive `loop = workflow_id_for(issue_url)`):

```python
engine_ref = request_engine_ref(loop, request.request_id)
if len(engine_ref.encode("utf-8")) > MAX_ENGINE_REF_BYTES:
    # mctl-api would refuse the fulfil with a 400 that defers for
    # ever: refuse it here, before the loop takes it.
    return await self._reject(request, token, loop, f"{xr.RESUME_REFUSED}:engine-ref-too-long")
```

(`dispatcher.py` lines 402-406.)

The guard's rationale is sound and worth preserving verbatim. `_fulfil` only
rejects on `TERMINAL_FULFIL_CODES = {"state_version_conflict", "invalid_transition"}`
(lines 148-174); an over-long ref would come back as an untyped `invalid_request`
400, which the module documents as "most likely a schema skew between this build
and mctl-api; rejecting would destroy every request that a fixed build could
still serve" — so it defers, the lease lapses, and the next claim re-derives the
same over-long ref. Pre-empting the store is the only way out of that loop.

What is wrong is the **reason**. `xr.RESUME_REFUSED` is `"resume_refused"`, and
`orchestrator/work_context/execution_requests.py` lines 63-87 define it as:

> A resume the live DevLoop refused to accept, or one this platform refused
> before delivering it. One of `RESUME_REFUSAL_REASONS` is appended after a
> colon, never anything else.

Before #461 option A, only a `resume` ever reached a live loop under a ref the
dispatcher minted, so the prefix was accurate. Since option A,
`request_engine_ref` is minted for every kind (`issue_ref.py` lines 61-74 —
"whether the request started that loop, started a continuation of it, or was
delivered onto it while it ran"), and `_dispatch` runs this check before it even
looks at `request.kind`. So an over-long ref answers a `start` in the resume
vocabulary. `execution_requests.py` line 72 already concedes the anomaly —
`engine-ref-too-long` is listed as "the dispatcher's", sitting among five
loop-validator reasons — and ADR 011 line 322 repeats it: "The dispatcher adds
`engine-ref-too-long` itself".

The vocabulary is not decorative. `TemporalClientPort.deliver` (lines 279-284)
normalises any loop-supplied reason outside `RESUME_REFUSAL_REASONS` to
`RESUME_REFUSAL_UNSPECIFIED`, with the comment "Surfaces branch on this reason:
only the closed vocabulary, never the free text". A surface that branches
correctly on `resume_refused:*` is therefore being handed a `start` refusal.

### How narrow the guard actually is

`request_engine_ref` produces `<loop>#<request id>`. The request id is
`xr_` plus a 36-character UUID (`REQUEST_ID_PREFIX` in `execution_requests.py`
line 32; `DispatchFakeApi.create_request` in `tests/test_execution_request_dispatch.py`
line 81 mints `xr_00000001-0000-4000-8000-000000000461`) — 39 bytes, 40 with the
`#`. The loop id is `dev-loop-mctlhq-<repo>-<n>` (`issue_ref.workflow_id_for`),
whose fixed part is 16 bytes. Against `MAX_ENGINE_REF_BYTES = 256`, the repo name
and issue number would have to total roughly 199 characters. `_ISSUE_URL_RE`
(`issue_ref.py` line 12) does not bound either, but GitHub caps repository names
at 100. The branch is effectively unreachable in production — which is precisely
why #487 classified it P3, and why a fix here is about the contract, not about a
live incident. There is no test covering it today (no hit for `too_long` or
`too-long` anywhere under `tests/`).

### The stale `dev-loop-xr_` wording

Every in-repo mention is load-bearing and must stay:

- `dispatcher.PRE_ISSUE_KEYED_DISPATCH_PREFIX = "dev-loop-xr_"` (line 218) and
  its two uses in `_reconcile_closed_loops` (lines 539, 546) — a pre-option-A
  loop that closed without ending its execution is still reconciled.
- `execution_requests.ENGINE_RUN_ENDED` (lines 88-93) — "Kept as mctl-api
  vocabulary for old rows."
- `workflows/dev_loop.py` lines 305, 319, 2374 and the replay fixtures
  `tests/fixtures/histories/dev_loop_resumed.json`,
  `tests/test_investigator_loop_identity.py` line 31 — replay of histories
  recorded before option A, guarded by `workflow.patched("issue-keyed-dispatch")`.
- ADR 011 lines 273 and 390, which describe exactly that.

The two outside this repo are inert, as #488 says: a comment on
`temporal_workflow_id` in mctl-gitops'
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`
(the parameter is still required — `issue_ref.loop_workflow_id` prefers the id
the loop passed via `--temporal-workflow-id`), and the sample value
`dev-loop-xr_0000` in mctl-api's
`internal/api/handlers_write_devloop_params_test.go`.

## Proposed solution

Three changes, in two repositories plus one comment fix in a third. The
mctl-agents change is the only one with behaviour in it.

### 1. A kind-neutral top-level reason (mctl-api, then mctl-agents)

Add a new top-level reject reason beside `NO_RUNNABLE_TARGET`,
`UNSUPPORTED_KIND`, `LOOP_ACTIVE` and `ENGINE_RUN_ENDED` in
`orchestrator/work_context/execution_requests.py`:

```python
#: The engine ref this platform would mint for the request,
#: `<loop>#<request id>` (`issue_ref.request_engine_ref`), exceeds mctl-api's
#: `workitems.MaxEngineRefBytes`. Refused before any delivery and before any
#: fulfil, so no execution was minted. Kind-neutral: since #461 option A the
#: ref is minted for a `start` as well as a `resume` (#488).
ENGINE_REF_TOO_LONG = "engine_ref_too_long"
```

`_dispatch` then reads:

```python
if len(engine_ref.encode("utf-8")) > MAX_ENGINE_REF_BYTES:
    return await self._reject(request, token, loop, xr.ENGINE_REF_TOO_LONG)
```

with its existing comment kept. No other call site of `RESUME_REFUSED` changes:
lines 429 (`f"{xr.RESUME_REFUSED}:{answer.reason}"`) and the `deliver`
normalisation stay exactly as they are, because they carry a reason the *loop*
produced.

`"engine-ref-too-long"` **stays** in `RESUME_REFUSAL_REASONS`. That set is the
read-side vocabulary as well as the write-side one; dropping the member would
make a row rejected by a current build normalise to `unspecified` on any future
read. Its docstring changes from "The dispatcher's" to a note that it is
retained only for rows written before #488, and that the dispatcher now mints
`ENGINE_REF_TOO_LONG`.

### 2. A one-shot legacy fallback on the reject

The whole point of the guard is that a request must never enter the
claim-fulfil-defer-lapse loop. If mctl-agents starts emitting a reason mctl-api
does not yet accept, the reject itself returns a definite 4xx
(`execution_requests._refusal` maps any 400-499 outside 401/403/408/429 to
`xr.REFUSED`), `_reject` falls through to `DispatchOutcome(DEFERRED, ...)`
(line 585), the lease lapses, and the next claim does the same thing — the exact
failure the guard exists to prevent, just moved one step later.

So `_dispatch` uses a small helper rather than `_reject` directly:

```python
async def _reject_engine_ref_too_long(self, request, token, loop):
    outcome = await self._reject(request, token, loop, xr.ENGINE_REF_TOO_LONG)
    if outcome.action != DEFERRED:
        return outcome
    # An mctl-api that does not yet know the kind-neutral reason (#488)
    # would otherwise leave the request to be re-claimed for ever, which
    # is what this guard exists to prevent. One retry, legacy spelling.
    return await self._reject(request, token, loop, f"{xr.RESUME_REFUSED}:engine-ref-too-long")
```

Both attempts go through `_reject`, so both emit their own `reject` audit line
and the skew is visible in `EXECUTION_REQUEST_DISPATCH` output. Once the
mctl-api vocabulary addition has been deployed everywhere the second call is
dead code; it is cheap enough to keep as a permanent safety net, and the
docstring says so. It is deliberately *not* conditioned on the answer's `code`,
because a vocabulary refusal's code is mctl-api's to choose and this build
cannot know it.

### 3. Documentation, and the two out-of-repo wording fixes

- `docs/adr/011-work-item-resume-contract.md`: the sentence at line 322 ("The
  dispatcher adds `engine-ref-too-long` itself") becomes a statement that the
  dispatcher refuses an over-long ref with the kind-neutral top-level
  `engine_ref_too_long`, for every kind, and that
  `resume_refused:engine-ref-too-long` remains readable for older rows. The
  module docstring of `dispatcher.py` (which enumerates outcomes in its
  step-3 bullet list) gains no new claim it does not already make.
- mctl-gitops `cwft-mctl-agents-investigate.yaml`: rewrite the
  `temporal_workflow_id` comment to describe `dev-loop-<owner>-<repo>-<n>`;
  leave the parameter, its default and every consumer untouched.
- mctl-api `internal/api/handlers_write_devloop_params_test.go`: replace the
  literal `dev-loop-xr_0000` with an issue-keyed sample such as
  `dev-loop-mctlhq-mctl-agents-488`; assertions unchanged.

## Alternatives

1. **Reuse an existing kind-neutral reason — `no_runnable_target`.** Zero
   cross-repo work: mctl-api already knows it, and surfaces already branch on
   it. Dropped because it is a lie in the other direction. The item *is*
   runnable (a valid mctlhq issue URL got it past `runnable_issue_url` at line
   388); what fails is a length limit on an identifier this platform mints.
   Collapsing the two would make `no_runnable_target` unfalsifiable as a
   diagnostic and would lose the only signal that the ref limit was hit.

2. **Reuse the `fulfil_refused:<code>` prefix.** Superficially attractive: the
   guard is literally pre-empting the 400 the fulfil would return, and
   `FULFIL_REFUSED` is already kind-neutral and already known to mctl-api, so
   no vocabulary addition would be needed. Dropped because
   `execution_requests.py` lines 94-98 define the suffix as "the store's code",
   and `_fulfil` line 507 only ever appends `answer.code` — an mctl-api code.
   Minting a dispatcher-invented suffix under that prefix breaks the one
   property the prefix promises, and a surface mapping `fulfil_refused:*` onto
   mctl-api's error codes would see a code that does not exist. It also claims
   a fulfil was attempted when none was.

3. **Make the branch unreachable by construction instead of relabelling it.**
   Bound repo name and issue number in `issue_ref._ISSUE_URL_RE` (say 100 and 10
   characters), proving `len(engine_ref) <= 167 < 256`, and downgrade the check
   to an assertion or drop it. Dropped on two counts: it changes which issue
   URLs the platform accepts, for a bound GitHub owns and may change; and it
   replaces a typed refusal with a crash-or-silence in the one code path whose
   entire purpose is to avoid an unbounded retry loop. A guard that fails closed
   with a correct reason is strictly better than an invariant asserted from an
   external system's current limits. (The arithmetic is still worth recording
   in the code comment, and this proposal keeps it there.)

4. **Do nothing; keep the mislabel.** The path is unreachable in practice.
   Dropped because #488 exists, because the mislabel is already contradicting
   two docstrings and an ADR, and because the cost of fixing it is one constant
   plus a documentation pass.

## Platform impact

**Migrations.** None. Reject reasons are strings on mctl-api's
`execution_request` row; no schema, no backfill. Rows already rejected as
`resume_refused:engine-ref-too-long` are left as they are and stay readable,
which is why the member is retained in `RESUME_REFUSAL_REASONS`.

**Backward compatibility and ordering.** This is the one real risk, and it is
a deploy-ordering risk, not a code risk:

- mctl-api's vocabulary addition **must merge and deploy first**. Until it has,
  an mctl-agents build emitting `engine_ref_too_long` would get its reject
  refused. Mitigated twice over: by the merge-ordering requirement in
  `tasks.md`, and by the one-shot legacy fallback, which converts a skewed
  deployment from "request re-claimed for ever" into "request rejected under
  the old spelling, with two audit lines showing why".
- A surface that exhaustively switches on the top-level reason needs the new
  arm. The fallback does not help there — it only covers mctl-api refusing the
  write. Listed as an open question because no surface code is visible from
  this repo; the mitigating fact is that the emitting branch is unreachable
  with any real GitHub repo name, so even an unhandled arm cannot fire in
  production.
- Rolling back mctl-agents alone is safe in both directions: an older build
  emits the old reason, which mctl-api still accepts.

**Resource impact.** None. One extra `_reject` HTTP call, only on a branch that
cannot be reached with a real repo name, and only when mctl-api refused the
first one.

**Risks and mitigations.**

| Risk | Mitigation |
| --- | --- |
| mctl-agents ships before mctl-api knows the reason | Merge order enforced in tasks; one-shot legacy fallback in `_dispatch` |
| Removing `"engine-ref-too-long"` from `RESUME_REFUSAL_REASONS` silently degrades old rows to `unspecified` | Explicitly retained, with a test asserting membership and a docstring saying why |
| The relabel leaks into loop-originated refusals | Only the literal at line 406 changes; lines 427-429 and `deliver`'s normalisation are untouched, and a test asserts a loop refusal still reads `resume_refused:<reason>` |
| The guard's unreachability tempts a later change to delete it | The new test pins the behaviour, and the code comment records the 40-bytes-plus-loop-id arithmetic |
| Touching mctl-gitops' CWFT breaks the investigate template | Comment-only edit; `temporal_workflow_id` and every consumer are explicitly out of scope |
