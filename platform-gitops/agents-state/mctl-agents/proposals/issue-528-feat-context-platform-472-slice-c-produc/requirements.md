# Context strategy release lifecycle, Slice C: production evidence gate, soak gate, production promotion and operator runbook

> **Correction 2026-09-28 (before approval).** ADR 019 requires production
> evidence from **>= 3 consecutive observe-mode investigations**. As first
> written, this proposal collected it by making the candidate authoritative:
> binding it in `shadow` at `enforce`, which on the production investigator
> resolves `AGENT_ENVIRONMENT`/`production` and never reaches the shadow
> binding (`context_assembly.py:1176`), or setting
> `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY=<candidate>`. Either way it is production
> exposure before the gate. Both paths are removed. Production soak evidence
> now comes only from Slice B's **non-authoritative observe candidate**,
> evaluated in the same production investigation as
> `evidence_kind: observe-candidate`. It carries its own `execution_ref`,
> never a borrowed `store_ref`, because the candidate is never persisted. The
> candidate does not serve the investigation that evaluates it.

## Context

Slices A (mctlhq/mctl-agents#472) and B (#527) shipped the context-strategy
release contract of ADR 019 (`docs/adr/019-context-strategy-release-contract.md`):
immutable, content-pinned `ContextStrategyVersion` documents under
`config/context-strategies/versions/`, an append-only per-(agent, environment)
`ContextStrategyBinding` under `config/context-strategies/bindings/`, the
`orchestrator/context_release.py` loader/resolver/`promote()`/`rollback()`
builders, the `tools/context_release.py` operator CLI, and the
`off/observe/enforce/only` rollout ladder in `orchestrator/context_rollout.py`
wired into `orchestrator/context_assembly.assemble()`. One thing is still
deliberately missing: `context_release.promote()` refuses **every** promotion
to an environment other than `shadow` outright as `evidence-missing`
(`orchestrator/context_release.py:631-649`), because the evaluator whose
evidence it would have to validate did not exist on the running image.

That evaluator now exists. mctlhq/mctl-agents#526 shipped
`orchestrator/context_eval.py` with `EvalRecord`, `EvidenceIdentity`,
`FreshnessPolicy`, ADR 019's two v1 policy constants
(`ADR019_V1_FRESHNESS_WINDOW_SECONDS = 604_800`,
`ADR019_V1_MIN_CONSECUTIVE_OBSERVATIONS = 3`) and `assess_evidence()`, which
answers `fresh | missing | stale | mismatched | insufficient-observations`
and explicitly leaves "does `fresh` permit a production promotion" to this
slice. Slice C closes the loop: it turns `assess_evidence`'s status into
ADR 019's closed-vocabulary promotion verdict, makes a production promotion
possible for the first time, adds the evaluator reference to the
`CONTEXT_STRATEGY_COMPARE` line, and writes the operator runbook so the whole
`publish -> promote-to-shadow -> observe -> promote-to-production -> roll back`
lifecycle can be run from the README without reading code. Promotion stays a
human-reviewed commit in this repository: passing the gate authorises a PR,
it never performs one.

## User stories

- AS a platform operator I WANT `tools/context_release.py promote --environment production`
  to accept a promotion only when real `context-eval` evidence backs it SO THAT a
  strategy cannot reach the authoritative investigator path on a reason string alone.
- AS a platform operator I WANT each refusal to name one closed-vocabulary reason
  (`evidence-missing`, `evidence-stale`, `evidence-insufficient`, `evidence-mismatch`,
  `hash-mismatch`, `version-not-promotable`, `version-disabled`) SO THAT I can tell
  "no evidence" from "stale evidence" from "wrong strategy" without reading English prose.
- AS a platform operator I WANT a README runbook covering publish, promote-to-shadow,
  soak/observe, promote-to-production, inspect-the-evidence and roll back SO THAT I can
  run the lifecycle end to end with no code reading.
- AS an incident responder I WANT `CONTEXT_RELEASE_ROLLOUT_MODE=off` documented as the
  one-variable break-glass SO THAT I can take a bad binding out of the decision path
  without a catalog change, a revert or a redeploy.
- AS a reviewer of a promotion PR I WANT the binding revision to record the evidence
  reference, evaluator version, newest observation timestamp and consecutive-observation
  count SO THAT the gate's inputs are auditable in git long after the logs roll off.
- AS an operator reading `CONTEXT_STRATEGY_COMPARE` I WANT the line to name the evaluator
  that produces promotion evidence SO THAT I can correlate a comparison with the
  `context_eval=` records, without the release layer inventing a second, disagreeing metric.

## Acceptance criteria (EARS)

Promotion gate

- WHEN `context_release.promote()` is called with `environment="production"` and
  `evidence_kind="none"` THE SYSTEM SHALL refuse with `ContextReleaseError.code ==
  "evidence-missing"`.
- WHEN `promote()` is called with `environment="production"` and no evidence records
  THE SYSTEM SHALL refuse with `evidence-missing`.
- WHEN the same promotion (same strategy, version and reason) is made to
  `environment="shadow"` with `evidence_kind="none"` THE SYSTEM SHALL accept it and
  append exactly one revision, unchanged from today's Slice A behaviour.
- WHEN production evidence is supplied whose newest counted observation is older
  than `ADR019_V1_FRESHNESS_WINDOW_SECONDS` (7 days) THE SYSTEM SHALL refuse with
  `evidence-stale`.
- WHEN production evidence carries fewer than `ADR019_V1_MIN_CONSECUTIVE_OBSERVATIONS`
  (3) consecutive observe-mode observations of the promoted identity THE SYSTEM SHALL
  refuse with `evidence-insufficient`.
- WHILE assessing production evidence THE SYSTEM SHALL count only records with
  `evidence_kind: observe-candidate`; `live`, `stored-replay`, `fixture-baseline` and
  `none` records, including `live` records of a run where the candidate was itself
  authoritative, SHALL be dropped before assessment, so they can never satisfy the
  soak gate (a pool with none left -> `evidence-missing`).
- WHEN production evidence names a different strategy, version, `contentHash` or
  `implementationHash` than the version being promoted THE SYSTEM SHALL refuse with
  `evidence-mismatch`.
- IF any supplied evidence record whose declared strategy/version matches the promotion
  carries `verdict: "hash-mismatch"` THEN THE SYSTEM SHALL refuse with `hash-mismatch`
  before any freshness or sufficiency check runs.
- IF the supplied `evidence.evaluatorVersion` disagrees with the evaluator version in
  the records THEN THE SYSTEM SHALL refuse with `evidence-mismatch`.
- WHEN a production promotion names a version whose `spec.lifecycle` is `deprecated`
  THE SYSTEM SHALL refuse with `version-not-promotable`, WHILE `resolve()` on an
  existing binding already pointing at that version SHALL keep succeeding.
- WHEN a promotion names a version whose `spec.lifecycle` is `disabled` THE SYSTEM
  SHALL refuse with `version-disabled`.
- WHEN a promotion names an environment outside `{shadow, production}` THE SYSTEM
  SHALL refuse with `unknown`, naming the two supported environments.
- WHEN every production check passes THE SYSTEM SHALL append exactly one revision whose
  `evidence` block records `kind: context-eval`, a non-empty `ref`, the
  `evaluatorVersion`, the newest observation's `observedAt` and the counted
  `observations`, and SHALL leave every prior revision byte-identical.
- WHILE the gate runs THE SYSTEM SHALL read no environment variable for the freshness
  window or the minimum observation count, taking both from
  `context_eval.ADR019_V1_*` only.
- WHILE the gate runs THE SYSTEM SHALL read no clock of its own: `now` is a caller-supplied
  argument, as `context_eval.assess_evidence` already requires.
- IF the gate passes THEN THE SYSTEM SHALL still require a human-reviewed commit — no
  code path in this proposal writes a binding without an operator invoking the CLI.

Observe-candidate evidence (the only production soak source)

- WHEN the rollout ladder is at `observe` AND the shadow pass sealed a candidate
  snapshot AND `ISSUE_INVESTIGATOR_CONTEXT_EVAL=on` THE SYSTEM SHALL evaluate that
  candidate snapshot too and print one more `[context] context_eval=` record with
  `evidence_kind: "observe-candidate"`, after the authoritative record.
- THE SYSTEM SHALL keep the candidate non-authoritative: it SHALL NOT reach the
  prompt, `AssemblyResult.snapshot`, `rendered` or the work-item store (Slice B's
  invariant, unchanged). It MAY be returned on a new, separate
  `AssemblyResult.observe_candidate` field that only the evaluation emitter reads.
- THE SYSTEM SHALL give an `observe-candidate` record `store_ref: null` and a new
  `execution_ref: {work_item_id, execution_id}` taken from the candidate snapshot's
  own `work_context` (the execution it was assembled in), and SHALL never attach the
  authoritative snapshot's `store_ref` to it.
- WHEN an `observe-candidate` record is verified THE SYSTEM SHALL check the
  candidate's document identity (`content_hash`, `snapshot_id`) and SHALL NOT apply a
  store match: this is ADR 015's second provenance mode, `execution-observed`, not an
  exception to `StoreRef`.
- WHEN evidence is counted THE SYSTEM SHALL key an `observe-candidate` observation
  on `execution_ref.(work_item_id, execution_id)`, exactly as a stored observation is
  keyed on `store_ref`, so the retries of one investigation are one observation; an
  `observe-candidate` record without an `execution_ref` (no store execution, e.g.
  the work-context rollout below `observe`) SHALL NOT be counted.

Catalog and loader

- WHEN `load_binding()` reads a revision with `evidence.kind: context-eval` THE SYSTEM
  SHALL require non-empty `ref`, `evaluatorVersion`, `observedAt` and a positive integer
  `observations`, and SHALL fail closed with `unknown` naming the missing field otherwise.
- WHEN `load_binding()` reads a revision with `evidence.kind: none` THE SYSTEM SHALL
  accept it exactly as today, with `observedAt`/`observations` absent.
- WHILE no production promotion has been reviewed and merged THE SYSTEM SHALL ship no
  `config/context-strategies/bindings/production/issue-investigator.yaml` in this
  repository.

Observability

- WHEN `CONTEXT_STRATEGY_COMPARE` is emitted THE SYSTEM SHALL additionally carry
  `record_kind`, `evaluator_name`, `evaluator_version` and `metrics_contract_version`
  from `orchestrator/context_eval.py`.
- WHILE emitting that line THE SYSTEM SHALL carry no counter delta, no ratio and no
  judgment about which strategy performed better, and SHALL carry no `locator`,
  `selector` or any byte derived from a retrieved payload.
- IF `orchestrator.context_eval` cannot be imported at emission time THEN THE SYSTEM
  SHALL emit the four new keys as `null` and SHALL NOT fail the run.

Documentation and defaults

- WHEN an operator reads the README's context-strategy release section THE SYSTEM SHALL
  document publish, promote-to-shadow, evidence collection, evidence inspection,
  promote-to-production, rollback and the `CONTEXT_RELEASE_ROLLOUT_MODE=off` break-glass,
  with runnable commands and no code reading required.
- WHILE `.env.example` documents the lifecycle's variables THE SYSTEM SHALL keep every
  one commented out and SHALL state that unset means unchanged behaviour.
- WHEN ADR 019 is amended by this slice THE SYSTEM SHALL supersede its sec. 5 note
  deferring the compare-line evaluation reference, and SHALL state the refusal
  precedence and the status-to-verdict mapping.

Compatibility

- WHILE `CONTEXT_RELEASE_ROLLOUT_MODE` is unset or `off` THE SYSTEM SHALL leave the
  investigator's prompt bytes, sealed snapshot bytes and `snapshot_id`s unchanged.
- WHEN `orchestrator/context_assembly.py` changes in this slice THE SYSTEM SHALL
  republish every affected `ContextStrategyVersion` document and append one shadow
  binding revision pinning the new hashes, so that the CI hash-drift guard
  (`tests/test_context_release.py::test_published_catalog_hashes_are_not_drifted`) and
  `test_committed_shadow_binding_resolves` both pass on the merge commit.

## Out of scope

- Automatic promotion on a metric threshold. Every promotion stays a reviewed commit.
- Committing a `production` binding for `issue-investigator` in this PR.
- Any new mctl-api table, route or registry client for context strategies (ADR 019
  "Non-goals"); the catalog stays committed in `mctl-agents` for v1.
- Changing ADR 015's metric definitions, the evaluator's fixture corpus or
  `baseline.json` — those are mctlhq/mctl-agents#526's.
- Persisting or rendering the `observe` shadow pass's snapshot, or emitting counter
  deltas/ratios/"which strategy won" on `CONTEXT_STRATEGY_COMPARE`.
- Writing a new strategy or ranker, extending the lifecycle beyond `issue-investigator`,
  or per-tenant strategy selection.
- Changing the 7-day window or 3-run minimum; they are ADR 019 v1 policy constants,
  changed only by amending that ADR.

## Open questions

- **What counts as an "observe-mode investigation".** Resolved by the owner
  (2026-09-28): the non-authoritative `observe` candidate of a real investigation,
  evaluated as `evidence_kind: observe-candidate` with its own `execution_ref`.
  Making the candidate authoritative to collect evidence is rejected: it is
  production exposure before the gate, and on the production investigator the
  `enforce` path does not even reach the `shadow` binding. The candidate snapshot
  stays unpersisted; ADR 015 gains a second provenance mode rather than a
  `StoreRef` that does not describe stored bytes.
- **"the four new variables" in task 12.** Two (`CONTEXT_RELEASE_ROLLOUT_MODE`,
  `CONTEXT_RELEASE_REQUIRED`) already landed in `.env.example` with Slice B and one
  (`ISSUE_INVESTIGATOR_CONTEXT_EVAL`) with #526. Proceeding by auditing the whole
  `ISSUE_INVESTIGATOR_CONTEXT_*` / `CONTEXT_RELEASE_*` block rather than blindly adding
  four more, and cross-referencing the new README section from it.
- **Evidence file transport.** A JSONL file of `context_eval` record payloads, passed as
  `--evidence-file`, with `evidence.ref` recording where it came from. Because
  `observe-candidate` records are never stored, they are collected from the
  investigator's `[context] context_eval=` log lines (the Argo workflow log archive),
  not from `run_context_eval` replay. This keeps `orchestrator/context_release.py`
  free of network and store access.
- **Whether a non-`{shadow, production}` environment should stay `evidence-missing`.**
  Slice A refuses e.g. `staging` as `evidence-missing`
  (`test_non_shadow_promotion_is_refused_even_when_not_named_production`). Proceeding
  with `unknown` instead, which is what the closed vocabulary means for something this
  module cannot classify; that existing test is updated in this slice.
