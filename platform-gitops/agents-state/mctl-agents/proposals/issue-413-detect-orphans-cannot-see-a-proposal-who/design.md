# Design: issue-413-detect-orphans-cannot-see-a-proposal-who

## Current state

### The detector

`orchestrator/temporal/activities/orphans.py` owns the whole of orphan
detection. Its module docstring (lines 1-5) states the definition the issue
quotes, and both detection paths implement it identically:

- `_sync_detect_orphans(state_dir, active_workflow_ids)` (lines 47-79), used only
  when an explicit local `state_dir_path` is passed. It calls
  `run_shepherd._discover_refs(state_dir, reconcile=True)` and then, per ref,
  `run_shepherd.find_pr_for_proposal(...)`, dropping the ref at line 59 when
  `pr is None or pr.closed_unmerged or pr.merged`.
- `_detect_from_github(active_ids)` (lines 102-126), the production path. It
  calls `gitops_state.list_proposal_refs()` and `gitops_state.fetch_pr_snapshots(refs)`,
  and drops the ref with the same condition at line 109.

`ACTIONABLE_STATUSES` (line 25) is `{accepted, in-progress, implemented,
review-fixing}`, so an `accepted` proposal is enumerated and then dropped. In the
GitHub path that drop is unconditional for a proposal with no `pr:`:
`fetch_pr_snapshots` (gitops_state.py:319-382) only fetches refs for which
`pr_ref_of(ref)` returns a `(repo, number)` pair, and `pr_ref_of` returns `None`
when `ref.pr_url` is falsy (gitops_state.py:299-300). In the local path
`find_pr_for_proposal` (run_shepherd.py:1333-1357) additionally falls back to
`_find_pr_url_by_branch(service, slug)`, so a proposal whose implementer pushed a
branch but never opened a PR can still resolve there — but for "never started"
there is no branch either, so both paths land on `pr is None`.

`_expected_workflow_id(slug, repo, service)` (lines 82-99) derives
`dev-loop-{owner}-{service}-{issue}` from an `issue-<N>-` slug prefix, and takes
the owner from the PR's repo. That is the only place the PR is needed for the
active-workflow comparison, and the owner defaults to `mctlhq` when there is no
repo (line 98) — so the ID can be derived without a PR.

### What happens to the result

`detect_orphans` (lines 129-164) logs one `ORPHAN` line per signal at INFO and
returns `OrphanDetectionResult(total_actionable, orphans, skipped_reason)`.
`ReconcileWorkflow` (workflows/reconcile.py:124-186) embeds that result in
`ReconcileWorkflowResult`, and nothing reads it: the 15-minute schedule in
`orchestrator/temporal/worker.py:241-269` starts the workflow and never fetches a
result. The log line is the entire consumer surface.
`docs/adr/010-lifecycle-ownership-contract.md:48` records this explicitly —
"Owner-less PR detected | `OrphanSignal` | No | nothing — logged only".
`orchestrator/temporal/activities/lifecycle_reconcile.py:65-68` imports
`ACTIONABLE_STATUSES` and `_expected_workflow_id` from this module, reusing the
predicate but never the result type.

### The state the detector would have to read

`.status.yaml` merge semantics live in `orchestrator/proposal_state.py:145-187`
(`update_status_file`; unknown keys preserved, `None` deletes, `UNSET` leaves
alone), with `now_iso()` at lines 26-33 producing RFC3339 UTC with a `Z` suffix.
Relevant keys for this change:

- `status`, `updated_at`, `updated_by` — written on every status write
  (proposal_state.py:166-168), present on all 371 live status files.
  `updated_at` is currently read by nothing in this repo.
- `approval: {approved_by, approved_at}` — written only by the Argo CWFT
  `cwft-mctl-agents-approve.yaml`, never by this repo, present on 122 files.
  `approved_at` is read by nothing today; `approved_by` is read by
  `proposal_state.py:110-116`.
- `attempt: {id, started_at, expires_at, finished_at}` — minted by
  `run_implementer.py:2693-2703` under `IMPLEMENT_ATTEMPT_LEASE`
  (`timedelta(minutes=130)`, run_implementer.py:668), and read by
  `run_shepherd._attempt_is_fresh` (run_shepherd.py:2795-2877), which parses
  `expires_at` with `datetime.fromisoformat(value.replace("Z", "+00:00"))` and
  returns `False` on `(TypeError, ValueError)`.

Neither ref type carries any of these timestamps. `run_shepherd.ProposalRef`
(run_shepherd.py:847-876) carries `proposal_dir` and a derived `status_path`, so
the local path *could* re-read the file. `gitops_state.ProposalStateRef`
(gitops_state.py:66-76) carries only `service, slug, status, pr_url`, because
`_parse_status_yaml` (gitops_state.py:137-148) returns only `(status, pr_url)` and
`_blob_cache` caches exactly that tuple keyed by blob SHA
(gitops_state.py:56-57, 123-134). The production path therefore has **no access to
any timestamp at all** today.

### Existing "age since X" precedent

- `run_shepherd._within_settle_window(head_pushed_at, now, settle_min)`
  (run_shepherd.py:1493-1515) — parse, normalise naive to UTC, guard future
  timestamps, compare against a `timedelta`. Threshold
  `SHEPHERD_MERGE_SETTLE_MIN` at run_shepherd.py:479-497, env-overridable,
  default 15, non-positive disables.
- `run_incident_responder.py:52` — `MIN_AGE_MINUTES = int(os.getenv("MIN_AGE_MINUTES", "30"))`,
  "skip incidents younger than N minutes". The closest precedent for an
  only-act-on-things-older-than gate.
- ADR-010 lines 204-240 — liveness and progress bounds must exceed twice the
  cadence of the loop they measure, so one missed tick cannot make a live entity
  look dead.

### Determinism constraints

`ReconcileWorkflow` guards every command addition with a `workflow.patched`
marker (`orphan-active-ids`, `reconcile-apply`, `lifecycle-reconcile`,
`exec-queue`), and `tests/test_workflow_replay.py:142-160` replays
`tests/fixtures/histories/reconcile_apply.prepatch.json` against the live
definitions. `tests/test_workflow_replay.py:22-40` records the measured fact that
an *extra argument to an existing activity* and a *changed return payload* are
invisible to the Replayer — only added, removed or reordered commands are not.
`tests/test_patch_memoization.py` records that a marker is memoized for the life
of an execution, so an unpatched branch can never be deleted while old executions
may be in flight. `tests/test_worker_isolation.py:36,82-104` names `orphans.py`
as a module the worker imports at module scope and fails the build if any new
module-level import there transitively reaches `claude_agent_sdk` or
`orchestrator.run_implementer`.

## Proposed solution

Split the predicate rather than loosening it, exactly as the issue asks, and
deliver the second signal **inside the existing `detect_orphans` activity result**
so that no new workflow command is scheduled.

### 1. A second signal type, in `activities/orphans.py`

```python
NEVER_STARTED_STATUSES = {"accepted", "in-progress"}

# Grace window between approval and claim. Four reconcile ticks; must exceed
# twice the approve-to-implement cadence per ADR-010 L208-240.
STALLED_NEVER_STARTED_MINUTES = int(os.getenv("STALLED_NEVER_STARTED_MINUTES", "60"))

REASON_NEVER_STARTED = "execution-never-started"
REASON_NEVER_STARTED_UNKNOWN_AGE = "execution-never-started-unknown-age"

@dataclass(frozen=True)
class StalledSignal:
    service: str
    slug: str
    status: str
    since: str | None        # the timestamp the age was measured from
    since_field: str         # which key it came from: attempt.started_at, ...
    age_minutes: int | None  # None when no timestamp parsed
    reason: str              # stable slug, groupable by a future metric
```

`OrphanDetectionResult` gains one defaulted field:

```python
stalled: list[StalledSignal] = field(default_factory=list)
```

Defaulted for the same reason `skipped_reason` (orphans.py:41-44) and
`PRSnapshot.head_sha` (gitops_state.py:88-91) are: an activity result recorded
before this field existed must still deserialize.

### 2. The predicate

Evaluated for a ref only when the existing orphan branch has already skipped it
with `pr is None`, so the two predicates are disjoint by construction and a
proposal can never appear in both lists:

1. `ref.status in NEVER_STARTED_STATUSES` — `implemented` and `review-fixing`
   without a PR are a different corruption, out of scope.
2. No PR at all. In the GitHub path this is `snapshots.get(key) is None`; in the
   local path it is the `pr is None` the loop already computed. A `closed_unmerged`
   or `merged` PR is *not* a never-started case and keeps falling through the
   existing skip.
3. No matching active DevLoopWorkflow: `_expected_workflow_id(ref.slug, None, ref.service)`
   not in the active set. The existing helper already handles the missing-repo
   case by defaulting the owner to `mctlhq` (orphans.py:98), and already returns
   `None` for a slug with no `issue-<N>-` prefix (incident and pre-Temporal
   proposals) — those never had a DevLoop, so no active-ID check applies and the
   ref stays eligible.
4. No live claim: the `attempt:` block has no `finished_at` and an `expires_at`
   in the future. This is the guard that keeps a running implementer, which holds
   a 130-minute lease and has not opened its PR yet, from being reported.
   Implemented as a local `_attempt_is_live(attempt, now)` mirroring
   `run_shepherd._attempt_is_fresh`'s parsing idiom rather than importing it,
   because `_attempt_is_fresh` takes a `ProposalRef` and reads the file itself —
   and because `IMPLEMENT_ATTEMPT_LEASE` lives in `run_implementer`, which
   `orphans.py` must never import (tests/test_worker_isolation.py:36).
5. Age past the threshold. The clock is the first parseable of
   `attempt.finished_at`, `attempt.started_at`, `approval.approved_at`,
   `updated_at` — a "last forward progress" timestamp in ADR-010's vocabulary,
   which also gives `in-progress` a sensible clock. Parsed with the repo's
   `.replace("Z", "+00:00")` idiom, naive values normalised to UTC, future
   timestamps treated as age zero, following `_within_settle_window`
   (run_shepherd.py:1493-1515).

If no timestamp parses, the ref is reported anyway with
`REASON_NEVER_STARTED_UNKNOWN_AGE` and `age_minutes=None`. This deliberately
breaks with `_within_settle_window`'s "unknown timestamp means no constraint"
convention: that function gates an *action*, this one gates a *log line*, and the
entire point of the issue is that silence is the failure mode. The cost of a
false positive here is one INFO line.

### 3. Known-versus-unknown active set

Today `_sync_detect_orphans` collapses the distinction at line 55
(`active_ids = active_workflow_ids or set()`). `ReconcileWorkflow`'s unpatched
replay branch (reconcile.py:170-175) calls `detect_orphans` with the state dir
only, so `active_workflow_ids` is `None` and every candidate would look
workflow-less. The new predicate therefore checks `active_workflow_ids is None`
and emits no stalled signals in that case, recording it in `skipped_reason` if it
is not already set. The existing orphan behaviour on that branch is left exactly
as it is — changing it would be a behaviour change visible to a resumed
execution, and it is not what this issue is about.

### 4. Surfacing

- The logging loop in `detect_orphans` (orphans.py:154-162) gains a second loop
  emitting `STALLED service=%s slug=%s status=%s since=%s age_minutes=%s reason=%s`.
  Distinct prefix, distinct stable reason slug, so a promtail metrics stage can
  count them separately — `orchestrator/lifecycle/shadow.py:121` records that
  promtail attaches no labels, so the class has to be in the line itself.
- `ReconcileWorkflowResult.orphans.stalled` is the workflow-level surface. No new
  field on `ReconcileWorkflowResult`, no new activity, no new
  `workflow.patched` marker, and no new command in the history — so
  `reconcile_apply.prepatch.json` replays unchanged and
  `reconcile_apply.patched.json` does not need re-recording either. The
  visibility-failure early return (reconcile.py:110-122) constructs
  `OrphanDetectionResult` by keyword and picks up the empty default for free.

### 5. Reading the timestamps in the production path

`gitops_state._parse_status_yaml` must return more than `(status, pr_url)`. It
becomes a small frozen dataclass:

```python
@dataclass(frozen=True)
class ParsedStatus:
    status: str
    pr_url: str | None
    approved_at: str | None
    updated_at: str | None
    attempt_started_at: str | None
    attempt_finished_at: str | None
    attempt_expires_at: str | None
```

`ProposalStateRef` gains the same five timestamp fields, all defaulted to `None`
so existing constructions and any recorded result stay valid. `_blob_cache`
(gitops_state.py:56-57) changes its value type from the tuple to `ParsedStatus`;
it is an in-process LRU keyed by blob SHA with no persistence, so a deploy starts
with an empty cache and there is no mixed-shape hazard. Cost is unchanged: the
blobs are already fetched and already parsed, and only the parsed shape widens —
no extra GitHub call, which matters for a sweep that runs every 15 minutes over
212 proposals under one shared token (gitops_state.py:18-27).

For the local `state_dir` path the timestamps come from re-reading
`ref.status_path` with `run_shepherd._load_status`, the same thing
`_attempt_is_fresh` does — that path is test/CLI only, so an extra file read per
actionable ref is not a cost worth optimising away.

### 6. Docs

`docs/adr/005-temporal-reconcile.md` lines 127-136 (the orphan definition) gets
the second predicate written next to the first.
`docs/adr/010-lifecycle-ownership-contract.md:48` gets a second row for the
never-started signal, still "logged only".
`docs/temporal-flow.md:157` and `docs/diagrams/temporal-flow-schedules.mmd:4`
describe the `detect_orphans` node and must mention both outputs.

## Alternatives

**Loosen the existing predicate to `pr is None or open PR`.** One-line change,
and the issue explicitly rejects it: the two conditions stop being
distinguishable at the consumer, the single `reason` string stops meaning one
thing, and any future alert has to re-derive which case it is holding from
`pr_url is None`. It also silently changes the meaning of the existing
`OrphanSignal`, which `lifecycle_reconcile.py` and ADR-010 both reference.

**A separate `detect_stalled` activity called from `ReconcileWorkflow`.** The
cleanest module boundary, and the most expensive: a new
`workflow.execute_activity` is a new command, so it needs its own
`workflow.patched` marker with an `else` branch that can never be deleted
(tests/test_patch_memoization.py), a new fake in
`tests/test_reconcile_workflow.py::_fake_activities`, a re-recorded
`reconcile_apply.patched.json` via `tools/record_workflow_history.py --kind patched`,
and registration in `worker.py`'s `short_activities`. It would also re-read the
same 212 blobs the orphan sweep just read, doubling the tick's GitHub cost, or
require a shared cache across two activities. Rejected: the two predicates
consume identical inputs (the ref list, the PR snapshots, the active set) and
belong in one pass.

**Extend the ownership sweep (`reconcile_lifecycle_ownership`, ADR-010) instead.**
That sweep already classifies entities against liveness and progress bounds and
has a vocabulary for `stuck`. But ADR-010 lines 838-842 say deliberately that an
entity with no record and no live execution is "drift `detect_orphans` reports in
the same tick from the same active set" — the ownership store is scoped to
entities that have an owner, and a proposal that was never claimed has no
ownership row to classify. Putting the check there would mean inventing rows for
entities nobody ever owned, and the sweep issues writes, which this signal must
not. Rejected as a contract violation, not just a cost.

**Report every never-started proposal with no age threshold.** Simplest, and
unusable: every proposal reports during the normal window between approval and
the next implement cron firing, so the signal is noisy from the first tick and
gets ignored — which is the failure mode #412 already demonstrated a different
way.

## Platform impact

**Migrations.** None. No schema change to `.status.yaml`, no new key written, no
gitops write at all. The change is read-only, in the same activity that is
already read-only.

**Backward compatibility.**
- `OrphanDetectionResult.stalled` and the new `ProposalStateRef` fields are
  defaulted, so results and refs recorded before this change deserialize
  unchanged — the rule already applied at orphans.py:41-44 and
  gitops_state.py:88-91.
- `ReconcileWorkflowResult` is untouched.
- No command is added to `ReconcileWorkflow`, so
  `tests/test_workflow_replay.py:142-160` passes without a new marker and
  `reconcile_apply.prepatch.json` must not be re-recorded
  (`tests/replay_scenarios.py:26-37`).
- `detect_orphans`' signature is unchanged, so a resumed execution re-executing
  it from the unpatched branch still matches the worker's signature
  (reconcile.py:165-169).
- The existing `ORPHAN` line, its reason string, and the PR-based predicate are
  byte-identical after this change.

**Resource impact.** Zero extra GitHub calls: the widened parse consumes blobs
the sweep already downloads, and the never-started branch only runs for refs the
orphan branch already skipped. The blob cache keeps its SHA key and its
`_BLOB_CACHE_MAX` bound of 4096; only the cached value grows by five optional
strings, roughly 0.5 KB per proposal at today's 212 proposals. The extra
per-tick work is a handful of `datetime.fromisoformat` calls.

**Risks and mitigations.**
- *Log noise on first deploy.* Every genuinely stalled proposal in the backlog
  reports on the first tick after rollout, and keeps reporting every 15 minutes
  until it moves, because the signal is stateless. Mitigation: the reason slugs
  make the lines trivially greppable, the threshold is env-tunable via
  `STALLED_NEVER_STARTED_MINUTES` without a redeploy of code, and the signal is
  INFO with no alert wired, so the blast radius is a log volume increase. The
  first tick after merge should be read deliberately — it is a backlog census,
  not an incident.
- *False positives from an implementer that claims without stamping `attempt:`.*
  Guard 4 relies on the attempt block existing. If a future claim path skips it,
  a live implementer reports as stalled. Mitigation: guard 3 (active DevLoop ID)
  catches the Temporal path independently, and the signal takes no action.
- *`updated_at` as a fallback clock is coarse.* Any status write refreshes it,
  so a proposal that flipped status for an unrelated reason gets its age reset
  and reports later than it should. Mitigation: it is the fourth fallback, used
  only when `attempt` and `approval` are both absent, and late-reporting is the
  safe direction for a detector whose competing failure mode is noise.
- *Worker isolation.* `orphans.py` is explicitly named in
  `tests/test_worker_isolation.py:82-104` as a module the worker imports at
  module scope. The new code adds only `os`, `datetime` and
  `run_shepherd._load_status` — `run_shepherd` is already imported there
  (orphans.py:16-19) — and must not import `run_implementer` for
  `IMPLEMENT_ATTEMPT_LEASE`. The test enforces this.
- *Timezone handling.* `now_iso()` (proposal_state.py:26-33) and the approve CWFT
  both write `Z`-suffixed UTC, but two legacy files carry a `retry:` key and old
  hand-edits exist. Naive timestamps are normalised to UTC and future timestamps
  clamped to age zero, per `_within_settle_window`.
