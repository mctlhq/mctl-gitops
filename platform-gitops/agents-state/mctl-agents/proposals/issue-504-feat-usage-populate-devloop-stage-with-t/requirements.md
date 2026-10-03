# Populate `devloop_stage` on every usage record with the closed v1 vocabulary

## Context

`orchestrator/usage_ledger.UsageRecorder` is the model-usage producer for
mctl-agents (ADR-012, mctlhq/.github#50). It is fed from exactly one place —
`tracing.agent_run`'s observer (`orchestrator/tracing.py:1018`) — and today it
writes `agent` (`investigator` | `implementer` | `shepherd`, mapped in
`usage_ledger._AGENT_NAMES`) plus the #499 correlation fields, but it never
writes `devloop_stage`. ADR-012's record section lists `devloop_stage`
(`docs/adr/012-model-usage-cost-attribution-contract.md:147`) and nothing
populates it. The owner decision on mctlhq/.github#50 (comment 5844714851)
fixes it as a **closed v1 vocabulary: `investigator | implementer | reviewer |
shepherd`**.

`agent` alone cannot answer the question FinOps actually asks. The shepherd's
address-review follow-up forks a subprocess into
`python -m orchestrator.run_implementer --review-feedback <bundle>`
(`orchestrator/run_shepherd.py:2405-2425`, entering
`run_implementer.review_feedback_one` at `orchestrator/run_implementer.py:2583`),
and that child opens its SDK session as
`tracing.agent_run("implementer", ...)` (`orchestrator/run_implementer.py:2421`).
So review-remediation spend and first-pass implementation spend are recorded
identically as `agent=implementer` and cannot be separated. `devloop_stage`
makes the distinction explicit — remediation cost is attributed to the stage
that caused it (`shepherd`) while `agent` keeps naming the binary that spent it
(`implementer`). The reviewer collector already records
`devloop_stage=reviewer` (mctlhq/.github#126), so the column and the vocabulary
exist server-side; this proposal makes the mctl-agents producer speak the same
vocabulary.

## User stories

- AS a platform FinOps analyst I WANT every usage record to carry a
  `devloop_stage` from a closed four-value vocabulary SO THAT I can group spend
  by DevLoop stage without parsing agent names or guessing.
- AS a platform FinOps analyst I WANT the shepherd's review-feedback
  implementer runs to be recorded with `devloop_stage=shepherd` SO THAT I can
  tell the cost of review remediation apart from the cost of first-pass
  implementation.
- AS a usage-ledger consumer I WANT `devloop_stage` to be either one of the
  four vocabulary values or absent SO THAT I can treat it as an enum and never
  have to defend against free text.
- AS an mctl-agents maintainer I WANT `agent` to keep its current values SO
  THAT existing queries, dashboards and tests built on it keep working.
- AS an mctl-agents maintainer I WANT the ADR-012 amendment text in this repo
  to record the vocabulary SO THAT the producer contract is readable next to
  the code that implements it.

## Acceptance criteria (EARS)

- WHEN `UsageRecorder` plans the records of a `ResultMessage` for the issue
  investigator (ledger agent name `investigator`) THE SYSTEM SHALL set
  `devloop_stage` to `investigator` on every record of that batch.
- WHEN `UsageRecorder` plans the records of a `ResultMessage` for an
  implementer run over an accepted proposal (`run_implementer.implement_one`)
  THE SYSTEM SHALL set `devloop_stage` to `implementer`.
- WHEN `UsageRecorder` plans the records of a `ResultMessage` for the
  shepherd's own model call (`run_shepherd._format_bundle_via_sdk`, ledger
  agent name `shepherd`) THE SYSTEM SHALL set `devloop_stage` to `shepherd`.
- WHEN the implementer runs in review-feedback mode
  (`run_implementer.review_feedback_one`, i.e. the run the shepherd forked)
  THE SYSTEM SHALL set `devloop_stage` to `shepherd` while leaving `agent` as
  `implementer`.
- WHILE a value for `devloop_stage` is supplied from any source (a
  `usage_ledger.correlate` scope, an explicit `UsageRecorder` correlation
  argument, or a per-agent default) THE SYSTEM SHALL emit it only if it is one
  of `investigator`, `implementer`, `reviewer`, `shepherd`.
- IF a supplied `devloop_stage` is not in the vocabulary (free text, wrong
  case, non-string, empty) THEN THE SYSTEM SHALL omit the field from the record
  and log one warning, exactly as `_checked_correlation` already does for
  `target_repo` and `execution_id`.
- IF the ledger agent name has no stage in the vocabulary (for example a future
  `service-agent`, `mentor` or `incident-responder` path reaching
  `tracing.agent_run`) AND no stage is supplied THEN THE SYSTEM SHALL omit
  `devloop_stage` rather than invent one.
- WHILE recording usage THE SYSTEM SHALL keep the record identity
  `(session_id, result_uuid, model_key)` and the per-`(session, model)` delta
  baseline unchanged, so adding the stage changes no dedupe key and no counter.
- WHILE recording usage THE SYSTEM SHALL keep `agent` exactly as it is today
  (`_AGENT_NAMES` mapping included) — the stage is an additional field, never a
  rename.
- IF recording the stage fails for any reason THEN THE SYSTEM SHALL log and
  swallow it, so DevLoop behaviour (investigate, implement, shepherd tick,
  merge) is unchanged — the existing "never fatal" rule of
  `orchestrator/usage_ledger.py`.
- WHEN the change lands THE SYSTEM SHALL record the closed vocabulary and the
  review-feedback attribution rule in
  `docs/adr/012-model-usage-cost-attribution-contract.md`.

## Out of scope

- The reviewer collector itself. `reviewer` is part of the vocabulary constant
  but no mctl-agents producer path emits it; it is produced elsewhere
  (mctlhq/.github#126).
- The pricing catalog, `calculated_cost` and `pricing_version` — separate
  children of mctlhq/.github#50.
- Temporal / Argo id plumbing (`temporal_workflow_id`, `argo_workflow_name`,
  `work_item_id`) — separate children of #50.
- Any change to delivery (retries, the daemon thread, the `atexit` flush),
  dedupe keys, or the delta-baseline semantics.
- Making `run_service_agent.py`, `run_mentor.py` or `run_incident_responder.py`
  record usage at all. They do not go through `tracing.agent_run` today
  (verified: no `tracing.` reference in those three modules), so they emit no
  records and therefore need no stage.
- Server-side enforcement of the vocabulary in mctl-api, and any mctl-api
  schema or migration work.
- Backfilling `devloop_stage` on already-ingested rows.
- Exporting the stage as an OpenTelemetry span attribute.

## Open questions

- Does mctl-api validate `devloop_stage` against the same closed vocabulary at
  ingest, and does it reject the whole batch on a bad value? The ingest is one
  transaction (`orchestrator/usage_ledger.py:526`), so a rejected field costs
  the batch. The producer therefore clamps to the vocabulary itself, which is
  safe under either server behaviour. Evidence the field is accepted: the
  reviewer already records `devloop_stage=reviewer` per mctlhq/.github#126.
- The issue says "reject or omit". This proposal chooses **omit with a
  warning**, consistent with `_checked_correlation`'s existing treatment of
  every other correlation field, because refusing the record would lose real
  token counts over a bookkeeping label.
- Should a shepherd tick that forks an implementer child also mark its own
  summariser call differently from the child (for example `shepherd` vs
  `shepherd`)? Decision: no — both are `shepherd`, and `agent` already
  separates them (`shepherd` vs `implementer`), which is exactly the pairing
  the issue asks for.
- Nothing in this repo currently sets a stage for an adopted-PR review-feedback
  run started by a human operator calling `run_implementer --review-feedback`
  directly. Decision: it is still `shepherd`, because the stage names the
  DevLoop phase (review remediation), not who launched it.
