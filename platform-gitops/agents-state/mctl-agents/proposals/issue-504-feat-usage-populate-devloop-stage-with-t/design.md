# Design: issue-504-feat-usage-populate-devloop-stage-with-t

## Current state

**One producer, one capture point.** `orchestrator/usage_ledger.py` holds
`UsageRecorder`, which turns a `claude_agent_sdk.ResultMessage` into one record
per model per turn and POSTs batches to `/api/v1/usage/records`. It is built in
exactly one place: `tracing.agent_run.__init__`
(`orchestrator/tracing.py:1015-1021`) does
`usage_ledger.UsageRecorder.from_env(agent)` inside a guarded `try`. Every
driver hands its whole SDK stream to that observer, so there is a single place
where a per-record field can be defaulted.

**The three agent names in use.** `tracing.agent_run(...)` is called from
exactly three sites:

| Site | `agent` argument | Ledger `agent` after `_AGENT_NAMES` |
|---|---|---|
| `orchestrator/run_issue_investigator.py:1654` | `issue-investigator` | `investigator` |
| `orchestrator/run_implementer.py:2421` (inside `_run_implementer_agent`) | `implementer` | `implementer` |
| `orchestrator/run_shepherd.py:2127` (inside `_format_bundle_via_sdk`) | `shepherd` | `shepherd` |

`_AGENT_NAMES` (`orchestrator/usage_ledger.py:126`) maps only
`issue-investigator -> investigator`; the other two pass through.
`run_service_agent.py`, `run_mentor.py` and `run_incident_responder.py` contain
no `tracing.` reference at all, so they record nothing today (consistent with
the ADR-012 invocation-path inventory).

**How per-run facts already reach the recorder.** `usage_ledger.correlate(...)`
(`orchestrator/usage_ledger.py:215`) sets a `contextvars` dict that
`UsageRecorder.from_env` merges as
`{**env_found, **_SCOPED.get({}), **explicit}`
(`orchestrator/usage_ledger.py:375-381`). `correlate` is wrapped around the
`anyio.run` that drives each session, so the scope is live at the moment
`tracing.agent_run` builds the recorder. Three call sites open it today:

- `orchestrator/run_issue_investigator.py:2473` — issue repo/number + execution id.
- `orchestrator/run_implementer.py:4114` (batch/first-pass path, inside
  `implement_one`) — `_usage_correlation(ref, execution_id=...)`.
- `orchestrator/run_implementer.py:2726` (review-feedback path, inside
  `review_feedback_one`) — same helper plus the PR.
- `orchestrator/run_shepherd.py:2964` — PR, source issue, tick execution id.

Everything in that dict is validated by `_checked_correlation`
(`orchestrator/usage_ledger.py:230`), which **drops with a warning** any value
mctl-api would reject (`target_repo` not `owner/name`, a non-positive
issue/PR number, a malformed `execution_id`) because the ingest is one
transaction and one bad field costs the whole batch. The surviving dict is
stored as `self._correlation` and splatted into the per-record `common` dict in
`_plan` (`orchestrator/usage_ledger.py:447-454`).

**Why the shepherd's follow-up is indistinguishable today.**
`run_shepherd.apply_followup` (`orchestrator/run_shepherd.py:2296`) writes the
review bundle to a temp file and forks
`[sys.executable, "-m", "orchestrator.run_implementer", "--service", ..., "--review-feedback", bundle_path, "--refusal-out", ...]`
(`orchestrator/run_shepherd.py:2405-2425`). That is a **new process**, so the
shepherd's `correlate` scope does not cross into it; the child rebuilds its own
correlation inside `review_feedback_one`
(`orchestrator/run_implementer.py:2726`) and opens
`tracing.agent_run("implementer", ...)`. Result: `agent=implementer` for both
first-pass implementation and review remediation.

**The contract text.** `docs/adr/012-model-usage-cost-attribution-contract.md`
lists `devloop_stage` in the record (line 147) and in the OTel mapping table
("`temporal_workflow_id`, `agent`, stage"), but the
"Amendment 2026-09-24 — the producer (mctlhq/.github#50)" section says nothing
about it and no code writes it.

**Existing tests that touch this shape.** `tests/test_usage_ledger.py`
(record shape, delivery, per-driver recording through the real drivers with
tracing off) and `tests/test_usage_correlation.py` (the correlation fields and
the scope, driven through the real call sites with a probe replacing the SDK
session). Two assertions there are exact-equality and will have to be updated:
`test_a_review_fix_names_its_pr` asserts
`scope == {"target_repo": ..., "pr_number": 42, "issue_number": 12}`
(`tests/test_usage_correlation.py:333`) and
`test_the_shepherd_names_the_pr_its_issue_and_its_tick` asserts a full dict.

## Proposed solution

Treat `devloop_stage` as **one more correlation field with a per-agent
default**, computed in the single place that already builds every record. Three
small, additive edits.

### 1. `orchestrator/usage_ledger.py` — the vocabulary, the default, the clamp

Add next to `_AGENT_NAMES`:

```python
# The closed v1 devloop_stage vocabulary (mctlhq/.github#50, owner decision 2).
# `reviewer` is produced by the review collector (mctlhq/.github#126), not here;
# it is part of the constant so the producer and the collector cannot drift.
STAGE_INVESTIGATOR = "investigator"
STAGE_IMPLEMENTER = "implementer"
STAGE_REVIEWER = "reviewer"
STAGE_SHEPHERD = "shepherd"
DEVLOOP_STAGES = frozenset({STAGE_INVESTIGATOR, STAGE_IMPLEMENTER, STAGE_REVIEWER, STAGE_SHEPHERD})

# Ledger agent name -> the stage its own runs belong to. Keyed on the name
# AFTER _AGENT_NAMES. An agent that is absent here records no stage: a path
# that starts recording later must name its stage deliberately.
_AGENT_STAGES = {
    "investigator": STAGE_INVESTIGATOR,
    "implementer": STAGE_IMPLEMENTER,
    "shepherd": STAGE_SHEPHERD,
}
```

Extend `_checked_correlation` with the same drop-and-warn treatment the other
fields get:

```python
stage = fields.get("devloop_stage")
if stage is not None and stage not in DEVLOOP_STAGES:
    drop("devloop_stage", "not one of the devloop_stage vocabulary")
```

Membership in a `frozenset[str]` is the whole check: a non-string, a
differently-cased value and free text all fail it, which is exactly the "never
send free text" requirement. The check is deliberately a plain lookup rather
than a regex, so widening the vocabulary is a one-line constant change.

Then, at the end of `UsageRecorder.__init__`, after
`self._correlation = _checked_correlation(...)`, fill the default:

```python
# The stage of this agent's own runs, unless the runner scoped one (the
# shepherd's review-feedback implementer child does; see run_implementer).
if "devloop_stage" not in self._correlation:
    stage = _AGENT_STAGES.get(self.agent)
    if stage:
        self._correlation["devloop_stage"] = stage
```

Because `self._correlation` is splatted into `common` in `_plan`, every record
of every batch then carries the field, with no change to `_plan`, `_deliver`,
`_commit`, `records_for`, the `(session_id, turn_key)` seen-set or the
`(session_id, model_key)` delta baseline. Precedence falls out of the existing
`from_env` merge: explicit argument > `correlate` scope > env > per-agent
default.

Also add an optional `devloop_stage` parameter to `work_correlation(...)`, so a
runner can build the whole dict in one call:

```python
def work_correlation(*, ..., devloop_stage: str | None = None) -> dict[str, Any]:
    ...
    if devloop_stage:
        fields["devloop_stage"] = devloop_stage
```

No validation there — `_checked_correlation` is the one gate, and duplicating it
is how a looser and a stricter copy drift apart.

### 2. `orchestrator/run_implementer.py` — the shepherd-owned implementer run

`_usage_correlation` (`orchestrator/run_implementer.py:1295`) gains a
`devloop_stage: str | None = None` parameter that it forwards to
`work_correlation`. The two call sites then differ by exactly one argument:

- `implement_one` (line ~4114): unchanged. The `implementer` default in
  `_AGENT_STAGES` already produces `devloop_stage=implementer`. Passing it
  explicitly would duplicate the default in a second place.
- `review_feedback_one` (line ~2726): passes
  `devloop_stage=usage_ledger.STAGE_SHEPHERD`.

That single site is the correct authority: `review_feedback_one` is reached
**only** from `main()` under `args.review_feedback`
(`orchestrator/run_implementer.py:4762` and `:4788`), which is the mode the
shepherd forks. `agent` stays `implementer` — untouched, since
`tracing.agent_run("implementer", ...)` is not modified.

### 3. `docs/adr/012-model-usage-cost-attribution-contract.md`

Append a short subsection to the 2026-09-24 producer amendment stating: the
closed v1 vocabulary and that it is closed; the per-agent default table; that a
review-feedback implementer run records `agent=implementer` with
`devloop_stage=shepherd` and why (the cost of remediation belongs to the stage
that ordered it, the binary that spent it is still named); that an
out-of-vocabulary value is omitted with a warning, not sent; and that `reviewer`
is produced by the collector (mctlhq/.github#126), not by this producer. Add two
testable invariants (10: every producer record carries a vocabulary value or
none; 11: a review-feedback run's records carry `agent=implementer` and
`devloop_stage=shepherd`).

### Resulting attribution matrix

| Path | `agent` | `devloop_stage` | Source of the stage |
|---|---|---|---|
| `run_issue_investigator` | `investigator` | `investigator` | `_AGENT_STAGES` default |
| `run_implementer.implement_one` | `implementer` | `implementer` | `_AGENT_STAGES` default |
| `run_shepherd._format_bundle_via_sdk` | `shepherd` | `shepherd` | `_AGENT_STAGES` default |
| `run_implementer.review_feedback_one` (forked by the shepherd) | `implementer` | `shepherd` | `correlate` scope |
| any future recording path not in `_AGENT_STAGES` | as given | absent | nothing — deliberate |

## Alternatives

**A. Pass the stage into `tracing.agent_run(agent, model, stage=...)`.**
Rejected. The fact "this is a review-remediation run" is known by
`review_feedback_one`, while `tracing.agent_run` is called several frames deeper
inside `_run_implementer_agent` (`orchestrator/run_implementer.py:2421`), which
both implementer paths share. Threading the stage down would mean a new
parameter on `_run_implementer_agent` (already carrying `envelope_s`,
`work_class`, `budget_ledger`) and a wider `tracing` signature, for a field that
is per-run correlation — exactly what `usage_ledger.correlate` exists for. A
variant of this, deriving the stage from the `work_class` the review bundle
carries, is worse still: it couples the FinOps label to a CI/review work
classification that can grow values for reasons unrelated to staging.

**B. Have the shepherd set an env var (`MCTL_DEVLOOP_STAGE=shepherd`) on the
forked subprocess and read it in `_CORRELATION_ENV`.** Rejected on two counts.
The child's environment is inherited by the SDK CLI child and everything the
model runs through Bash, so the stage becomes model-influenceable free text —
the producer would then need exactly the vocabulary clamp anyway, plus a new
trust boundary. And it makes the attribution depend on the launcher rather than
on the mode the process is actually running in, so an operator invoking
`run_implementer --review-feedback` by hand would silently record
`devloop_stage=implementer`. In-process derivation from
`review_feedback_one` cannot be wrong about which mode it is in.

**C. Derive the stage server-side in mctl-api from `agent` plus some hint.**
Rejected. mctl-api cannot see the difference: both implementer paths post
`agent=implementer` with a PR number (the batch path posts no PR, but an adopted
first-pass run can), so the server would have to guess. Deriving a stage from a
correlation heuristic is the kind of silent reinterpretation ADR-012's
"recorded as served, never as configured" rule exists to prevent, and it would
also put the vocabulary in two repos with no shared constant.

**D. Rename `agent` to the stage vocabulary and drop the duplication.**
Rejected outright by the issue ("Keep `agent` as is. Stage is an additional
field, not a rename.") and by the data: `agent=implementer` +
`devloop_stage=shepherd` is a real, non-redundant pair that a single column
cannot express.

## Platform impact

**Migrations.** None in this repo. No database, no GitOps state schema, no
`.status.yaml` field. mctl-api already accepts and stores `devloop_stage`
(the reviewer collector writes `devloop_stage=reviewer`, mctlhq/.github#126),
so no server change is required for this producer to start populating it.

**Backward compatibility.**
- Record identity is untouched: mctl-api derives the row id from
  `(session_id, result_uuid, model_key)`, none of which changes, so a re-sent
  batch still counts once and ADR-012 invariants 2, 3 and 4 still hold.
- The delta baseline is keyed on `(session_id, model_key)` and is unchanged, so
  token counts are byte-for-byte what they are today.
- `agent` values are unchanged, so every existing query, test and dashboard
  built on `agent` keeps working.
- Rows ingested before this change have `devloop_stage` null. Consumers must
  treat null as "not recorded", which is already the ADR-012
  absent-versus-zero/absent-versus-null rule. No backfill.

**Resource impact.** One short string per record on an existing POST. No extra
request, no extra thread, no extra model call. Negligible.

**Risks and mitigations.**
- *A bad value costs a whole batch.* The ingest is one transaction
  (`orchestrator/usage_ledger.py:526`), so if mctl-api validates the enum, one
  free-text stage would drop every record in the batch. Mitigated by the
  `DEVLOOP_STAGES` clamp in `_checked_correlation` — the producer can only ever
  send a vocabulary value or nothing — and by a test that asserts an
  out-of-vocabulary value is dropped with a warning rather than sent.
- *Vocabulary drift between producer and consumers.* Mitigated by one module
  constant (`usage_ledger.DEVLOOP_STAGES`) plus the ADR-012 amendment text, and
  by including `reviewer` in the constant even though no path here emits it.
- *A future recording path records a wrong stage by inheritance.* Mitigated by
  making `_AGENT_STAGES` a deliberate allowlist: an agent absent from it records
  no stage at all rather than defaulting to something plausible.
- *DevLoop behaviour regression.* The only DevLoop-path edits are one extra
  keyword argument in two helper signatures and one extra dict entry; recording
  remains wrapped in the module's existing "never fatal" guards
  (`observe`/`_record` swallow everything). A `correlate` scope that fails to
  build cannot break the run, and `tracing.agent_run` already tolerates the
  recorder being unavailable.
- *Exact-equality assertions in existing tests break.* Expected and intended —
  `tests/test_usage_correlation.py:333` and the shepherd scope test assert full
  dicts. They are updated in the same change so the new field is asserted, not
  tolerated.
