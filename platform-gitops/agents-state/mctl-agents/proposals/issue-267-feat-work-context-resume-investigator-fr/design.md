# Design: issue-267-feat-work-context-resume-investigator-fr

## Current state

**Task identity is the issue URL, and nothing else.**
`orchestrator/temporal/workflows/dev_loop.py:370-372` defines the workflow
input as a frozen dataclass with one field:

```python
@dataclass(frozen=True)
class IssueRef:
    issue_url: str
```

`orchestrator/temporal/issue_ref.py:30-37` derives the workflow id
(`dev-loop-mctlhq-<repo>-<N>`) from that URL, and
`orchestrator/temporal/start.py:65-72` starts the loop with
`id_reuse_policy=ALLOW_DUPLICATE_FAILED_ONLY` /
`id_conflict_policy=USE_EXISTING`. So Temporal already dedupes *per issue*, but
there is no identifier for a *task* that could outlive the issue or span
surfaces.

**There is no execution identity.** A repo-wide grep for `execution_id`
returns zero hits. `orchestrator/resolver.py`'s `ExecutionPlan`
(`resolver.py:226-258`) has no id field — its identity is the tuple of pins
(`definition_version`, `profile_content_hash`, `release_revision`,
`target_repository_sha`, ...), and ADR 007's validation expectations
(`007:301-302`) explicitly want two runs with identical inputs to produce
*identical* plan identifiers. Runtime identity comes from outside: the
`ExecutionRecord` at `orchestrator/temporal/activities/state.py:29-44` carries
`temporal_workflow_id` and `argo_workflow_name`.

**Snapshot correlation is intra-execution only.**
`orchestrator/context_snapshot.py` implements ADR 009: `seal()` at `:885`
produces a content-addressed document (`content_hash = "sha256:" +
sha256(canonical JSON)`, `snapshot_id = "cs-" + content_hash[7:23]`, `:915-916`),
`ExecutionCorrelation` at `:407-476` quotes the plan's pins, and `StepRef` at
`:480-500` chains a step snapshot to a per-execution root — with the rule at
`:796-805` that a child's `execution` block must equal its parent's. ADR 009
`:203-205` scopes that chain to *one* execution; there is no contract for two
executions of one task. The module is inert: its own docstring (`:19-21`) says
it "is not yet imported by production code, only by tests and fixture
generation", and ADR 009 follow-up (a) — "a producer wired into
`run_issue_investigator.py`" — still reads "needs an issue".

**The investigator has three flags.**
`orchestrator/run_issue_investigator.py:2075-2094` builds the parser inline in
`main()`: `--issue-url` (required), `--state-dir`, `--dry-run`. `investigate()`
(`:1457-1461`) takes `(issue_url, state_dir, dry_run)`. State is entirely
derived from the issue: `gh_issue_view` (`:868`), then
`resolve_slug(proposals_dir, number, title)` (`:842`) picks the
`issue-<N>-<slug>` directory, and `_load_status` (`:889`) reads the
`.status.yaml` the previous run wrote (`write_status_yaml`, `:979-1044`). The
de-facto cross-run memory is therefore already transcript-free — it is the
gitops proposal directory — but it is keyed on the issue, not on a work item.

**Resume is explicitly denied today.** `dev_loop.py:923-936`:
"It is a restart, not a resume — the new run re-investigates and waits for a
fresh approve signal." The only signal is `approve` (`:787-800`), which parses
its payload defensively and never raises; the durable wait is
`await workflow.wait_condition(lambda: self._approved)` (`:827`) with no
timeout. The two queries are `shepherd_in_loop` (`:753`) and `lifecycle_claim`
(`:766`).

**There is a proven pattern for exactly this kind of change.**
ADR-010 shipped `orchestrator/lifecycle/` as: `contract.py` (frozen
dataclasses mirroring an mctl-api surface, tolerant `from_payload`
staticmethods that ignore unknown keys and return `None` on a malformed
payload — `contract.py:129-137`), `client.py` (synchronous stdlib-urllib
client, `Bearer $MCTL_TOKEN`, https-only, no-redirect opener, uncertainty
returned as an `UNKNOWN` *value* rather than an exception), `policy.py` (pure
decisions) and `rollout.py` (a four-stage `off | observe | enforce | only`
switch read from one env var, defaulting to `off`, warning rather than raising
on a typo — `rollout.py:62-79`). This proposal reuses that shape wholesale.

**Nothing exists yet.** A repo-wide grep for
`work_item|WorkItem|work-item|WorkContextRef|ContextSnapshotRef` returns *no
matches*. This is greenfield within a well-established set of conventions.

## Proposed solution

Five additions, all inside `mctlhq/mctl-agents`.

### 1. `orchestrator/work_context/` — the client-side WorkItem contract

A new package mirroring `orchestrator/lifecycle/`, because the situation is
identical: mctl-api (#227) owns the store, this repo owns a tolerant client
mirror.

- `contract.py` — stdlib only, frozen dataclasses, `from_payload`
  staticmethods that ignore unknown keys and return `None` on a malformed
  payload (the `orchestrator/lifecycle/contract.py:129-137` discipline; an
  mctl-api deploy that adds a field must not become an agents outage).
  Symbols: `SurfaceRef(kind, surface_id, thread_ref)`,
  `ActorRef(kind, actor_id)`, `WorkItemRef(work_item_id, revision)`,
  `ExecutionRef(execution_id, sequence, temporal_workflow_id, started_at,
  surface, actor)`, `WorkItem(work_item_id, revision, state, origin,
  executions, issue_url, service, slug)`, `WorkItemAnswer(verdict, item,
  reason, accepted)`. Closed vocabularies as module frozensets:
  `SURFACE_KINDS`, `ACTOR_KINDS`, `WORK_ITEM_STATES`, and the verdicts
  `WORK_ITEM_FOUND | WORK_ITEM_ABSENT | WORK_ITEM_CONFLICT |
  WORK_ITEM_UNKNOWN`. Plus two pure functions:
  - `execution_id_for(work_item_id, sequence, attempt) -> str` — a sha256 of
    `"{work_item_id}|{sequence}|{attempt}"`, deliberately the same shape as
    `lifecycle/contract.py:1013-1024`'s `idempotency_key_for`, so a duplicate
    resume derives the *same* id and dedupes by construction rather than by
    luck. A UUID fallback is forbidden, as in ADR-010 §8.
  - `reconstruct_canonical_state(item, proposal_dir, prior_digests) ->
    CanonicalState` — see §4.
- `client.py` — `WorkItemClient`, synchronous urllib, copied structurally from
  `lifecycle/client.py:86-301`: `MCTL_API_BASE_URL` (default
  `https://api.mctl.ai`), `Bearer $MCTL_TOKEN`, refusal of a non-https base,
  `_no_redirect_opener`, and a `WorkItemUnavailable(RuntimeError)` raised only
  by the transport and converted by every public method into a
  `WORK_ITEM_UNKNOWN` answer. Routes live in one module-level table:
  `GET /api/v1/work-items/{id}`, `POST /api/v1/work-items/{id}/executions`,
  `GET /api/v1/work-items/{id}/executions`.
- `rollout.py` — `WORK_CONTEXT_ROLLOUT_MODE` with the same `OFF/OBSERVE/
  ENFORCE/ONLY` ladder, `mode()`, `at_least()`, `records_writes()`,
  `computes_new_answer()`, `new_answer_may_veto()`, `new_answer_decides()`,
  and `blocks_on_unknown()` reading the `WORK_CONTEXT_REQUIRED` break-glass and
  nothing else. Default `off`: the entire change is inert until an operator
  moves it, which is what makes this safe to merge ahead of
  mctlhq/mctl-gitops#1279 and mctlhq/mctl-api#335.
- `__init__.py` — a re-export block with `# noqa: F401`, matching
  `orchestrator/lifecycle/__init__.py`.

The package imports no third-party module, so `tests/test_worker_isolation.py`
stays green whether the worker or the Argo sandbox imports it.

### 2. `WorkContextRef` on the ContextSnapshot

A new frozen dataclass in `orchestrator/context_snapshot.py`, following that
module's *strict* discipline (a sealed document rejects unknown keys, unlike
the tolerant API mirror above — the two are different jobs and the difference
is deliberate):

```
WorkContextRef(work_item_id, work_item_revision, execution_id,
               execution_sequence, prior_execution_ids, resumed_from_snapshot_id,
               origin_surface, current_surface, actor_kind, actor_id,
               surface_transition)
```

Wired as `ContextSnapshot.work_context: WorkContextRef | None = None`, added to
`_SNAPSHOT_KEYS` (`:631`), `to_dict`, `from_dict`, `_content_payload`
(`:860-882`, so it participates in `content_hash` exactly as `step` does),
`validate()` (closed-vocabulary checks for `origin_surface`/`current_surface`/
`actor_kind`, and — extending the existing parent rule at `:804-805` — a child
step snapshot's `work_context` must equal its parent's), and `to_log_dict()`
(`:807-827`, emitting `work_item_id`/`execution_id`/`execution_sequence` for
#195 trace correlation but **not** `actor_id`).

This is the piece that satisfies "resume creates a new execution identity and
ContextSnapshot while retaining correlation to prior executions" *without*
mutating history. Execution B seals its own snapshot; because `work_context`
feeds the hash and `execution_id` differs, its `snapshot_id` differs from
execution A's. Correlation is carried forward by `work_item_id` and
`prior_execution_ids`, and by the optional one-way pointer
`resumed_from_snapshot_id`. Nothing re-opens A's document. This deliberately
does **not** reuse `StepRef`: ADR 009 `:203-205` scopes step chaining to one
execution and requires a child's `execution` block to equal its parent's, which
is exactly what a resume violates. `WorkContextRef` is the sibling-correlation
axis; `StepRef` remains the intra-execution axis.

Because it adds a field to the sealed shape, this needs a short **ADR 011**
(the repo's `docs/adr/` template: Context → Decision → Alternatives → Non-goals
→ Platform impact → Implementation map), stating that it extends ADR 009 sec. 1's
field/owner table and reaffirms the sec. 5 boundary — `work_context` records
provenance and is never read by an authorization decision.

### 3. Investigator flags

`main()` (`run_issue_investigator.py:2075`) gains `--work-item-id`,
`--execution-id`, `--resume-from-execution-id`, `--surface`, `--actor-kind`,
`--actor-id`; `--issue-url` drops `required=True` and becomes conditionally
required by an explicit post-parse check (missing → `SystemExit` unless
`--work-item-id` is given and the mode is `only`). `investigate()` gains the
same names as **keyword-only parameters defaulting to `None`**, so every
existing call site — `investigate(url, tmp_path)` in ~170 tests, and any direct
trigger — is untouched. A small `_work_context_from_args(args) ->
WorkContextInput | None` helper does the validation (closed vocabularies, the
`--resume-from-execution-id` ⇒ `--work-item-id` requirement) in one testable
place, and `orchestrator/work_context` is imported **lazily**, inside the
functions that use it, preserving the module-scope import discipline that
`run_issue_investigator.py:68-73` documents and `test_worker_isolation.py`
enforces.

When the mode is at least `observe`, `investigate()` resolves the `WorkItem`,
computes the canonical state, and records the resulting `WorkContextRef` on the
`ExecutionPlan` log line; the `seal()` producer itself remains ADR 009
follow-up (a) and is out of scope here.

### 4. Canonical-state reconstruction

`reconstruct_canonical_state(item: WorkItem, proposal_dir: Path | None,
prior_digests: Sequence[Mapping[str, Any]]) -> CanonicalState` is a pure
function whose *signature has no parameter capable of carrying a transcript*.
Its inputs are:

- the `WorkItem`'s own structured fields (`state`, `issue_url`, `service`,
  `slug`, `executions`);
- the gitops artifacts `run_issue_investigator` already reads —
  `.status.yaml` via `_load_status` (`:889`) and the
  `requirements.md`/`design.md`/`tasks.md` triplet (`TRIPLET`, `:258`);
- prior execution digests in `ContextSnapshot.to_log_dict()` shape (ids,
  counts, hashes — never payloads).

It returns `CanonicalState(work_item_id, state, service, slug, issue_url,
prior_execution_ids, prior_status, artifacts_present, reconstructed_from)`.
The "no raw transcript" requirement becomes testable as a *type* property
rather than a promise: a test asserts the function's signature and the
`CanonicalState` field set contain no free-text message field, mirroring how
`ContextSource` is defended by having no payload field to put one in
(`context_snapshot.py:277-281`).

### 5. The `resume` signal on `DevLoopWorkflow`

```
@workflow.signal def resume(self, *args: object) -> None
@workflow.query  def work_context(self) -> WorkContextState
```

`resume` parses defensively and never raises, exactly like `approve`
(`dev_loop.py:787-800`). Accepted payload:
`{"work_item_id", "execution_id", "surface", "actor_kind", "actor_id"}`.
New workflow state: `_work_item_id`, `_executions: list[ExecutionRef]`,
`_seen_execution_ids: set[str]`, `_resume_pending: bool`,
`_resume_rejections: list[ResumeRejection]`, `_current_surface`,
`_current_actor`.

Semantics, and why each is the conservative choice:

| Case | Behaviour |
|---|---|
| `execution_id` already in `_seen_execution_ids` | no-op (idempotent). Because `execution_id_for` is a deterministic hash, a duplicated signal derives the same id and lands here automatically. |
| a different `execution_id` while `_resume_pending` | rejected; a `ResumeRejection(execution_id, reason="resume-already-pending")` is appended and surfaced by the query. Never a fork. |
| `work_item_id` disagrees with the one already bound | rejected, `reason="work-item-mismatch"`. |
| accepted, same surface and actor | new `ExecutionRef` appended; approval untouched. |
| accepted, surface or actor changed | new `ExecutionRef` appended, `surface_transition=True` recorded, **`self._approved = False` and `self._approver = None`** |

That last row is the whole answer to "authorization/approval is re-evaluated"
and to the "no cross-surface privilege inheritance" non-goal: the existing
`await workflow.wait_condition(lambda: self._approved)` (`:827`) simply
re-arms, so the loop parks again until the *current* actor approves through the
normal `approve` signal, whose authorization is governed by #198 and unchanged
here.

**Determinism.** A signal handler adds no workflow commands, so the handler and
the query can be added unguarded. Anything that changes the *command stream* —
merging work-context keys into `investigate_params` (`:812-815`), or re-entering
the wait after clearing `_approved` — sits behind a new
`workflow.patched("work-context-resume")` marker, following
`"atomic-approve"`/`"slug-scoped-implement"` (`:864-869`) and heeding the
explicit cost note at `:2286-2295`. `IssueRef` gains an optional
`work_item_id: str | None = None` field; a defaulted field keeps old histories
deserializable.

**The submission path stays closed.** `investigate_params` is `dict[str, str]`
POSTed verbatim as the operation body (`activities/argo.py:118-125`), and the
mctl-api registry rejects unknown parameters until mctlhq/mctl-api#335 and the
CWFT change mctlhq/mctl-gitops#1279 land. So the merge is guarded by *both* the
patch marker and `work_context.rollout.at_least(ENFORCE)`, and with the default
`off` mode nothing new is ever sent. A pure `work_context_params(...) ->
dict[str, str]` helper carries the logic and is unit-tested directly.

## Alternatives

1. **Reuse `StepRef` for cross-execution chaining.** Rejected: ADR 009
   `:796-805` requires a child's `execution` block to equal its parent's, and
   a resume by definition has a different execution. Relaxing that rule would
   reopen one of ADR 009's explicitly frozen decisions (`009:454-462`) and would
   make "same execution" unfalsifiable. A separate correlation axis keeps both
   rules intact and each one checkable.

2. **Put resume state in the proposal's `.status.yaml`.** Rejected for the four
   reasons ADR-010 §1 already gives for not putting ownership there — chiefly
   the ~35-minute gitops mutex, which makes it useless as a concurrency control
   for "two surfaces resumed at once". Also, a resume must work before any
   proposal exists.

3. **A second Temporal workflow per execution, parented to a work-item
   workflow.** Rejected: it doubles the workflow-id space and the replay
   surface for no gain the `resume` signal does not already provide, and the
   issue explicitly forbids introducing a parallel orchestration engine.
   `DevLoopWorkflow` already owns durable per-issue state and already parks
   indefinitely on `wait_condition`.

4. **Omit `work_context` from `_content_payload` when `None`, to preserve
   existing `content_hash` values.** Rejected: it would make the canonical JSON
   shape conditional, diverging from `step`, which is always emitted as
   `null` (`:876`). Since the module has no production producer yet
   (`:19-21`), the entire cost of an unconditional key is re-cutting one golden
   fixture. Recorded here because a reviewer who disagrees only has to flip one
   line — the tests pin the decision either way.

## Platform impact

**Migrations.** None in this repository. The only durable state it touches is
Temporal workflow history (handled by `workflow.patched`) and the gitops
proposal directory (unchanged on disk). The mctl-api `WorkItem` table is
mctl-api#227's migration, not this one.

**Backward compatibility.**
- CLI: every new flag is optional and defaults to `None`; omitting all of them
  reproduces today's behaviour exactly. `investigate()`'s new parameters are
  keyword-only, so the ~170 existing positional call sites compile unchanged.
- Workflow: `IssueRef` gains one defaulted field; new commands are patch-gated;
  a recorded pre-change history must replay, which is enforced by adding a
  scenario to `tests/replay_scenarios.py` / `tests/test_workflow_replay.py`.
- Snapshot: `ContextSnapshot.work_context` defaults to `None` and `from_dict`
  accepts a document without the key. The `content_hash` of a `work_context=None`
  document changes once; the only artifact affected is
  `tests/fixtures/context/investigator-snapshot.json`, which is re-cut in the
  same PR.
- Rollout default `off` means the merged PR changes no runtime behaviour at
  all, which is what allows it to land before its two cross-repo prerequisites.

**Resource impact.** Negligible. At `observe` and above, one extra
`GET /api/v1/work-items/{id}` per investigator execution (10 s timeout,
uncertainty returned as a value), plus a handful of strings in workflow memory
and a slightly larger snapshot document. The Temporal worker's 256 Mi limit
(ADR-008, agents#179) is unaffected: the new package is stdlib-only and adds no
dependency to `pyproject.toml`.

**Risks and mitigations.**

| Risk | Mitigation |
|---|---|
| Workflow nondeterminism wedges in-flight approved loops at deploy time — the failure mode `dev_loop.py:845-852` was written about | Every new command behind `workflow.patched("work-context-resume")`; a pre-patch history added to the replay suite as a merge gate. |
| A resume from a hostile or merely different surface inherits an earlier approval | Surface/actor transition clears `_approved` and `_approver`; covered by a dedicated workflow test. |
| Concurrent resumes fork one work item | Deterministic `execution_id_for` makes duplicates idempotent; a differing id while pending is rejected with a recorded reason; Temporal's single-writer execution serialises the handler. Server-side sequence allocation remains the long-term answer and is recorded as a known simplification. |
| mctl-api route shape guessed wrong | Routes isolated in one table; the client fails to a `WORK_ITEM_UNKNOWN` value, and at the default `off` mode is never called. |
| Worker bloat / import-line regression | `orchestrator/work_context` is stdlib-only and imported lazily inside functions in `run_issue_investigator.py`; `tests/test_worker_isolation.py` already fails the build if that line moves. |
| Scope creep into the submission path | The `investigate_params` merge is double-gated (patch + `enforce`) and defaults to sending nothing; the cross-repo work stays in mctlhq/mctl-gitops#1279 and mctlhq/mctl-api#335. |
