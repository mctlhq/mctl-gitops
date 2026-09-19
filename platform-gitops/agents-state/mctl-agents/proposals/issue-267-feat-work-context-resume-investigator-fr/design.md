# Design: issue-267-feat-work-context-resume-investigator-fr

## Current state

**One issue, one workflow, one shot.** `orchestrator/temporal/issue_ref.py:30`
derives the workflow id `dev-loop-{owner}-{repo}-{issue}` from the issue URL
alone. `orchestrator/temporal/start.py:65-72` starts `DevLoopWorkflow.run` with
`IssueRef(issue_url=...)`, `id_reuse_policy=ALLOW_DUPLICATE_FAILED_ONLY` and
`id_conflict_policy=USE_EXISTING`. The consequences are documented in
`start.py:31-61`: a RUNNING duplicate start is a no-op, a previously SUCCEEDED
run raises `WorkflowAlreadyStartedError` (the poller treats it as "already
handled", `run_issue_poller.py:225-242`), and a FAILED run restarts from the
top. `dev_loop.py:925-935` states the gap this issue targets outright: "It is a
restart, not a resume — the new run re-investigates and waits for a fresh
approve signal."

**The workflow input carries no context.** `IssueRef`
(`dev_loop.py:370-372`) is a single `issue_url: str`. `DevLoopWorkflow`
(`dev_loop.py:712-1005`) runs resolve → `_run_cwft("mctl-agents-investigate",
{"issue_url", "agent_image", "agent_version"})` (`:812-817`) → `_record(...)`
(`:818`) → `await workflow.wait_condition(lambda: self._approved)` (`:827`) →
slug lookup → `mctl-agents-approve` → `mctl-agents-implement` → merge/deploy/
incident watches. Its complete handler set is two queries (`shepherd_in_loop`
`:753`, `lifecycle_claim` `:766`) and one signal (`approve` `:787-800`); there
are no update handlers anywhere in `orchestrator/temporal/workflows/`. Every
behavioural fork is gated by a `workflow.patched` marker — `exec-queue` `:499`,
`atomic-approve` `:864`, `slug-scoped-implement` `:869`, `merge-detection`
`:966`, `shepherd-in-loop` `:2247`, and seven more — and `dev_loop.py:2287-2295`
records the standard for when a new marker is justified. There is no
`continue_as_new`; history growth is managed by cadence arithmetic
(`dev_loop.py:129-144`, `:193-208`).

**Execution identity exists, but is issue-keyed.** `_record`
(`dev_loop.py:524-563`) posts an `ExecutionRecord`
(`orchestrator/temporal/activities/state.py:28-46`) whose primary correlation
key is `temporal_workflow_id = workflow.info().workflow_id`, plus
`argo_workflow_name`, `agent`, `version`, `image_ref`, `target_repo`, `phase`.
`state.py:34-42` notes the target SHA is deliberately not captured. Agent
versions are pinned per step via the registry (`_resolve` `:474`,
`_require_release` `:660`, `activities/registry.py`).

**The context contract exists but has no producer.** ADR 009
(`docs/adr/009-context-snapshot-contract.md`) and
`orchestrator/context_snapshot.py` define a frozen, stdlib-only,
content-addressed `ContextSnapshot`: `seal()` (`context_snapshot.py:885`)
computes `content_hash` over canonical JSON of everything except
`content_hash`/`snapshot_id`/`created_at`, and `snapshot_id = "cs-" +
content_hash[7:23]`. `ExecutionCorrelation` (`:406-476`) is explicitly designed
to join on fields both sides already have — `temporal_workflow_id`,
`argo_workflow_name`, the four version/hash pins, `target_repository_sha`. ADR
009's follow-up table names exactly what is still missing: "(a) a producer wired
into `run_issue_investigator.py` that calls `seal()`" and "(b) persisting sealed
snapshots next to `ExecutionRecord` in mctl-api" — both "needs an issue". This
issue is that issue, plus resume.

**The investigator already reconstructs state from durable artifacts.**
`run_issue_investigator.investigate()` (`:1457`) resolves the proposal directory
by issue number via `resolve_slug` (`:842`, rename-safe since #246), reads the
existing `.status.yaml` with `_load_status` (`:889`), refuses to clobber a
proposal outside `_OVERWRITABLE_STATUSES`, carries prior files forward with
`_carry_forward` (`:712`), fetches five issue fields with `gh_issue_view`
(`:868`), clones the target repo with `_clone_repo` (`:900`), and pins the SHA
with `_target_repository_sha` (`:117`). Untrusted text is neutralized by
`_neutralize_prompt_tags` (`:1098`) and wrapped as DATA by `_build_prompt`
(`:1127`). Its CLI (`main()` `:2075`) accepts only `--issue-url`, `--state-dir`,
`--dry-run`. So the machinery for transcript-free canonical reconstruction is
already there; what is missing is a work-item identity to hang it on.

**There is a precedent for exactly this shape of cross-repo contract.**
`orchestrator/lifecycle/` (ADR 010) is a durable, mctl-api-owned ownership
record consumed by mctl-agents through two transports: a synchronous urllib
`OwnershipClient` for Argo pods and CLI processes (`lifecycle/client.py`, whose
docstring states "The Temporal side does NOT use this module"), and async httpx
activities for the worker (`activities/lifecycle.py`). It carries a monotonic
`epoch` (`lifecycle/contract.py:85`), returns denials as data rather than
exceptions, treats an unreachable store as `UNKNOWN` rather than permission, and
is rolled out through `LIFECYCLE_ROLLOUT_MODE` (`lifecycle/rollout.py:59`). This
design reuses that pattern rather than inventing a second one.

## Proposed solution

Five additive pieces. Nothing existing changes shape; every new behaviour is
opt-in on the presence of a work-item reference.

### 1. `orchestrator/work_item.py` — the client-side contract (new, stdlib-only)

Frozen dataclasses mirroring `context_snapshot.py` and `lifecycle/contract.py`:
no pydantic, no `schemas/` package, every field defaulted so a payload recorded
before a field existed still deserializes out of Temporal history.

- `WorkItemRef(work_item_id, canonical_task_ref, epoch)` — `canonical_task_ref`
  is the issue URL today; the id is opaque and server-minted.
- `SurfaceRef(kind, id)` with closed vocabulary `SURFACE_KINDS = {"github-issue",
  "telegram", "web", "cli", "cron", "api"}`; `ActorRef(kind, id)` with
  `ACTOR_KINDS = {"human", "service", "agent"}`. Identifiers only — never a
  credential, never a token, never free text.
- `ResumeIntent(work_item_id, expected_epoch, surface, actor, reason_code,
  idempotency_key)`.
- `ExecutionIdentity(execution_id, work_item_id, epoch, parent_execution_id,
  prior_execution_ids, prior_snapshot_ids)` — all minted or returned by the
  store; this module never invents an id.
- `resume_key(work_item_id, expected_epoch, surface, actor) -> str`, a
  sha256-derived idempotency key. Deterministic on purpose: it is computed
  inside `@workflow.defn` code, where `uuid4()`/`time.time()` are forbidden.
- Bounded-length and closed-vocabulary validation with loud failure, copying
  `context_snapshot._reject_unknown_keys`/`_require_str` verbatim in style, and
  a `MAX_ID_LENGTH` ceiling so no id field becomes a free-text carrier.

No field name may contain `allow`/`deny`/`permit`/`grant`/`authorized` — the
recursive field-name assertion in `tests/test_context_snapshot.py` is extended
to cover this module, so ADR 009 sec. 5 ("context relevance is never an
authorization mechanism") survives the addition.

### 2. Two transports to the mctl-api work-context surface

Exactly the lifecycle split, for exactly the lifecycle reasons:

- `orchestrator/work_context_client.py` — synchronous urllib, no-redirect
  opener, used by `run_issue_investigator` inside the Argo pod. Methods:
  `resolve(work_item_id)`, `open_execution(ResumeIntent)`,
  `publish_snapshot(execution_id, snapshot_dict)`, `report_refusal(...)`.
- `orchestrator/temporal/activities/work_items.py` — async httpx activities
  `resolve_work_item`, `open_work_item_execution`, `record_surface_transition`,
  used by `DevLoopWorkflow`. Workflow code never calls HTTP directly (ADR 010
  §9).

Failure semantics follow `lifecycle/client.py`: a conflict is **data** (a 409
becomes an explicit `conflict` answer, not an exception), while unreachable is
`UNKNOWN` and, for a resume, fails closed — an execution identity is never
invented locally. A `WORK_ITEM_ROLLOUT_MODE` env switch (`off | shadow |
enforce`), modelled on `lifecycle/rollout.py`, lets the surface be exercised in
shadow before it decides anything.

### 3. `ContextSnapshot` gains an optional `work_item` block (ADR 011)

New frozen dataclass in `orchestrator/context_snapshot.py`:

```
WorkContextRef(
  work_item_id, epoch, execution_id,
  parent_execution_id | None,
  prior_execution_ids: tuple[str, ...],
  prior_snapshot_ids: tuple[str, ...],
  surface_kind, surface_id, actor_kind, actor_id,
  resume_reason_code,
)
```

carried as `ContextSnapshot.work_item: WorkContextRef | None = None`.

**Hash rule — omit when absent.** `_content_payload` (`context_snapshot.py:860`)
includes the `"work_item"` key **only when the block is present**. That is a
deliberate, narrow amendment to ADR 009 sec. 2, and it is what keeps the
checked-in golden fixture `tests/fixtures/context/investigator-snapshot.json`
hashing byte-for-byte to `sha256:de22a552...` under the existing T3 test. The
`step` key keeps its always-rendered `null`, untouched. ADR 009 declares sec. 1
and sec. 2 normative and not reopenable by a follow-up, so this lands as **ADR
011, an amendment ADR** that states the rule, the compatibility argument, and
the new field-owner row — not as a silent schema edit.

The chaining rule extends consistently: `validate(parent=...)`
(`context_snapshot.py:796-805`) already requires a child's `execution` block to
equal its parent's; it will require the same of `work_item`. Resume never
mutates a chain — it starts a **new root** whose `prior_execution_ids` and
`prior_snapshot_ids` point backwards. `to_log_dict()` (`:807`) gains
`work_item_id`, `execution_id`, `epoch`: identifiers only, no locator, no
selector, no payload-derived string.

### 4. `run_issue_investigator.py` — resume input plus the first real producer

`main()` (`:2075`) gains optional flags, all absent-by-default so today's CWFT
invocation is untouched:

```
--work-item <id>            canonical WorkItem reference
--expected-epoch <n>        compare-and-set guard for the resume
--surface <kind>:<id>       provenance of THIS invocation
--actor <kind>:<id>         provenance of THIS invocation
--resume-of <execution_id>  prior execution being continued
```

`investigate()` (`:1457`) gains a matching optional `work_item: WorkItemRef |
None` parameter and, when present:

1. Calls `open_execution(...)` before any agent work; the store returns the
   `ExecutionIdentity` (execution id, epoch, prior execution/snapshot ids) or an
   explicit conflict, which aborts without running the agent.
2. Reconstructs canonical state from durable artifacts only — the WorkItem
   record, the existing proposal triplet found by `resolve_slug`/`_load_status`,
   and `gh_issue_view`. There is no transcript parameter, and the prompt builder
   has no place to put one.
3. Feeds `_build_prompt` (`:1127`) a new, clearly-delimited "prior work on this
   WorkItem" section built from those artifacts, keeping the existing untrusted
   wrapping (`_neutralize_prompt_tags` `:1098`) for anything third-party
   authored. Prior proposal documents are `proposal-dir` sources at trust tier
   `reported`; the issue body stays `untrusted`; the clone stays `authoritative`
   at its pinned SHA.
4. On completion, seals one **root** `ContextSnapshot` with `seal()`
   (`:885`) — sources: `github-issue`, `target-repo` at
   `_target_repository_sha` (`:117`), and on resume the `proposal-dir` — plus the
   `work_item` block, and publishes it with `publish_snapshot`. This is ADR 009
   follow-ups (a) and (b), scoped to the investigator.
5. Leaves the existing idempotency guard in force: a proposal outside
   `_OVERWRITABLE_STATUSES` is still refused, and the refusal is now also
   reported against the WorkItem rather than only printed.

Every step is skipped entirely when `--work-item` is absent, so the
`agents:intake` poller path and the current CWFT parameters keep working
unchanged during rollout.

### 5. `DevLoopWorkflow` — resume without a second engine

- `IssueRef` (`dev_loop.py:370`) grows **defaulted** fields: `work_item_id: str
  = ""`, `surface_kind/surface_id/actor_kind/actor_id: str = ""`,
  `resume_of_execution_id: str = ""`, `epoch: int = 0`. Defaults are what make
  old histories deserialize — the pattern `DevLoopResult` already relies on
  (`dev_loop.py:449-471`).
- New marker `workflow.patched("work-item-resume")` guards every new branch:
  passing `work_item_id`/`execution_id` into `investigate_params`
  (`:812-815`), and the new signal/query below. Histories without the marker
  replay exactly as recorded, per the memoization semantics pinned by
  `tests/test_patch_memoization.py`.
- New signal `resume(self, *args: object)`, written in the defensive style of
  `approve` (`:787-800`) — signals must never raise. It records the
  actor/surface transition via `record_surface_transition` and updates the
  in-workflow provenance fields. It does **not** approve anything.
- `approve` is extended to accept the optional keys `actor_kind`, `actor_id`,
  `surface_kind`, `surface_id`, `epoch` in its dict form, still ignoring
  anything unrecognized. An approval recorded for epoch N does not satisfy a
  gate in epoch N+1: on the resume path the workflow requires
  `self._approved_epoch == self._epoch`. Approval *enforcement* stays where it
  is — mctl-api's authenticated approve endpoint (`cli.py:113-118`) — this is
  bookkeeping that prevents inheritance, not a new authority.
- New query `work_item() -> WorkItemView(work_item_id, epoch, execution_ids)`,
  alongside `shepherd_in_loop` and `lifecycle_claim`, so trace/evidence views
  and the mctl-api liveness route can correlate executions to one WorkItem.
- Start path: `start.py` gains `start_dev_loop_resume(work_item, intent)`.
  `workflow_id_for` stays byte-identical for epoch 0 — `mctl_get_dev_loop`, the
  poller and the shepherd cron all derive ids from it — and a new
  `resume_workflow_id_for(issue_url, epoch)` appends `-r{epoch}` for epoch > 0.
  Reuse/conflict policies are unchanged.

**Why this satisfies concurrency.** The epoch is minted by the WorkItem store
under a compare-and-set on `expected_epoch`. Two concurrent resumes carrying the
same `resume_key` receive the same epoch and therefore the same workflow id,
where `WorkflowIDConflictPolicy.USE_EXISTING` (`start.py:71`) collapses them to
one run; a resume presenting a stale `expected_epoch` gets a 409 that surfaces as
a non-retryable `ApplicationError` and starts nothing. A resume arriving while
the first execution is still parked at `wait_condition` (`:827`) is routed as the
`resume` signal instead of a start — one Temporal execution, provenance
recorded, no fork.

## Alternatives

**A. Put the work-item fields inside `ExecutionCorrelation`.** It is the natural
home (it already carries `temporal_workflow_id`, `argo_workflow_name`, the
version pins). Dropped because `ExecutionCorrelation.to_dict()` is unconditional
inside `_content_payload`, so adding fields changes the `content_hash` of *every*
snapshot including the golden fixture, invalidating the one test ADR 009 relies
on to prove hash stability — and because the "child execution block must equal
parent's" rule would then silently bind step-chaining to resume state.

**B. Bump `api_version` to `context.mctl.ai/v1alpha2`.** Honest about the schema
change and avoids the omit-when-absent subtlety. Dropped because it forces two
supported versions in `SUPPORTED_API_VERSIONS` (`context_snapshot.py:44`), a
migration path in `from_dict`, and a second golden fixture, for a strictly
additive optional block — ADR 009's own platform-impact section already names
"additive, defaulted fields" as the intended growth path and reserves
`apiVersion` bumps for breaking changes.

**C. Resume by re-using the same Temporal workflow id and history
(continue-as-new or a long-lived per-WorkItem workflow).** Dropped for two
reasons: it violates "historical execution/snapshot state is not mutated on
resume" in spirit — one execution identity would span surfaces — and it breaks
the repo's history-size discipline, since the 14-day watch is already budgeted
against the 50k-event ceiling (`dev_loop.py:129-144`) with no continue-as-new
anywhere in the codebase.

**D. Carry a summarized transcript between executions as prompt text.** Simplest
to build, and explicitly what the issue forbids. Dropped: it makes surface
content a load-bearing input, has no content-hash story, and would smuggle
payload into a schema whose entire design is payload-free (ADR 009 sec. 7).

## Platform impact

- **Migrations.** None in this repo. The WorkItem store lives in mctl-api
  (the depended-on contract); mctl-agents is a client. No GitOps schema, no
  manifest field, no `.status.yaml` shape change.
- **Cross-repo sequencing.** `mctl-agents-investigate` must accept new CWFT
  parameters (`work_item_id`, `execution_id`) before `DevLoopWorkflow` sends
  them: the template lives in mctl-gitops (`cwft-mctl-agents-investigate.yaml`)
  and mctl-api's operation registry validates params. mctl-agents CI cannot
  check that sibling repo — the same blind spot `dev_loop.py:936-950` documents
  for the implement CWFT's `service` param — so the gitops change lands first,
  and the workflow only passes the params behind `workflow.patched`.
- **Backward compatibility.** Additive by construction. Absent `--work-item`
  reproduces today's behaviour exactly; `IssueRef`'s new fields are defaulted;
  the `work_item` snapshot block is omitted from the content payload when
  absent, so existing snapshot ids and the golden fixture hash are unchanged;
  `workflow_id_for` is untouched for epoch 0.
- **Determinism and replay.** The chief risk. Mitigations: every new branch
  behind one marker (`work-item-resume`); the idempotency key derived by
  sha256, never `uuid4`/wall-clock, inside workflow code; all HTTP through
  activities; replay tests extended with a pre-patch history fixture in
  `tests/fixtures/histories/`.
- **Resource impact.** One extra activity per execution start and one extra
  HTTP POST per completed investigation — not per poll, so the 14-day
  history budget (`dev_loop.py:193-208`) is untouched. A sealed snapshot is a
  few kilobytes of primitives. New modules stay stdlib-only (client) or
  httpx-only (activities), preserving `tests/test_worker_isolation.py`'s line
  against `claude_agent_sdk` in the worker.
- **Risks and mitigations.**
  - *Resume becomes a privilege-escalation path across surfaces.* Mitigated by
    epoch-scoped approval, actor/surface recorded as identifiers only, no
    authorization field names in any new schema (asserted by test), and
    enforcement left with mctl-api.
  - *The store is down and a resume proceeds anyway.* Mitigated by fail-closed
    UNKNOWN handling copied from `lifecycle/client.py`, plus the
    `WORK_ITEM_ROLLOUT_MODE` shadow stage before anything decides.
  - *A resume clobbers an in-flight implementer's proposal.* Mitigated by the
    existing `_OVERWRITABLE_STATUSES` guard, which resume must not weaken, now
    also reported back to the WorkItem.
  - *Snapshot ids drift and old ones stop verifying.* Mitigated by the
    omit-when-absent hash rule plus a test asserting the existing fixture's
    hash byte-for-byte and a second fixture for the resume shape.
  - *A permanent patch marker for a feature that gets reverted.* Accepted and
    bounded: markers are removed by attrition via `workflow.deprecate_patch`
    after `MERGE_WATCH_DEADLINE` (14 days), never by deleting deployed code.
- **Security.** The snapshot stays payload-free and non-authoritative. Surface
  and actor are identifiers with bounded length and closed vocabularies.
  Provider-side authorization (GitHub, mctl MCP, Kubernetes) remains the only
  enforcement, unchanged.
