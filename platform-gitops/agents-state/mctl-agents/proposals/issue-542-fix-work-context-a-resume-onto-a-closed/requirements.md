# Seal a context snapshot on a resume onto a closed loop whose proposal is terminal

## Context

`orchestrator/run_issue_investigator.py` runs an idempotency guard (`_investigate`,
around the `_OVERWRITABLE_STATUSES` check) before it clones the target repo and before
`_assemble_context` runs. The guard returns an `InvestigateResult(..., skipped_reason=...)`
whenever the proposal's `.status.yaml` carries any status other than `proposed`. That
rule is correct for its original purpose — never clobber a proposal an implementer or
shepherd owns — but it is applied to *every* run, including a run the work-item layer
dispatched as a `resume`. On the production run recorded in the issue (work item
`wi_5c479148`, execution `we_dd497dec`, loop `dev-loop-mctlhq-mctl-agents-494`, whose
proposal is `merged`), the investigator exited before assembling anything, no
`ContextSnapshot` C2 was sealed, and the execution was still advanced to `Succeeded` by
`DevLoopWorkflow` (`orchestrator/temporal/workflows/dev_loop.py`, the
`advance_phase = "Succeeded" if investigate_result.succeeded else "Failed"` line).

Two things are broken by that. First, ADR 011 §8 states that "a `resume` of a finished
loop is exactly a new run of it", and #431's recorded model says a fresh C2 is produced
by exactly this path — so for any item whose proposal reached `accepted`/`implemented`/
`merged`, the documented resume behaviour cannot happen at all. Second, an execution that
assembled nothing is indistinguishable in the ledger from one that did real work, which
violates the platform's "could not observe is never observed absent" rule. The repo
already has a precedent for refusing exactly this shape of silence:
`DISPATCHED_NOT_RUN_ERROR_TYPE = "DispatchedRequestNotRun"` in `dev_loop.py`, whose
comment says "a COMPLETED run that did nothing would make every later intake label on
the issue a silent 'already handled'".

## User stories

- AS the work-item store I WANT a dispatched `resume` onto a closed loop to seal a fresh
  `ContextSnapshot` SO THAT `/snapshots` shows C2 with provenance back to W1/E1/C1 even
  when the proposal has already merged.
- AS a platform operator reading the execution ledger I WANT an execution that did not
  rewrite a proposal to say so with a typed outcome SO THAT a context-only run is never
  mistaken for a full investigation.
- AS the implementer/shepherd owning a `merged` proposal I WANT a resume to remain unable
  to rewrite my proposal directory SO THAT in-flight and completed work is never clobbered.
- AS the #431 live-proof author I WANT the resume path to produce C2 on a real item SO THAT
  acceptance items 3, 4 and 7 can be proven live rather than only in tests.

## Acceptance criteria (EARS)

- WHEN `_investigate` is called with a work item whose proposal `.status.yaml` status is
  not in `_OVERWRITABLE_STATUSES`, AND the run is a dispatched resume (a
  `--resume-from-execution-id` is present, or a store `we_` `--execution-id` is present
  together with an `--execution-request-id`), AND `ISSUE_INVESTIGATOR_CONTEXT_MODE` is not
  `off`, THE SYSTEM SHALL clone the target repo, run `_assemble_context` and seal a
  `ContextSnapshot` before returning.
- WHILE a run is on that context-only path THE SYSTEM SHALL assemble under `shadow`
  semantics regardless of the configured context mode, because no prompt is built on this
  path and a sealed snapshot must never claim to describe a prompt that was not built.
- WHILE a run is on that context-only path THE SYSTEM SHALL NOT create a staging
  directory, SHALL NOT invoke the Claude Agent SDK, SHALL NOT call `write_status_yaml`,
  SHALL NOT perform the publish swap, and SHALL NOT comment on the GitHub issue.
- WHEN a context-only run seals a snapshot THE SYSTEM SHALL populate the snapshot's
  `work_context` block with `work_item_id`, this run's store `execution_id`,
  `execution_sequence`, `prior_execution_ids` including the `resumed_from_execution_id`,
  and `resumed_from_snapshot_id` resolved from the prior execution's snapshot — that is,
  the same `_work_context_ref` / `snapshots.resumed_from` path a normal run uses.
- WHEN any run returns without rewriting the proposal THE SYSTEM SHALL carry an explicit
  typed outcome on `InvestigateResult`: an `outcome_code` drawn from
  `orchestrator/execution_evidence.py`'s `OUTCOME_CODES` and an `outcome_reason` slug
  matching that module's slug pattern, using `proposal-terminal` for this condition.
- WHEN a context-only run ends THE SYSTEM SHALL print one machine-readable outcome line to
  stdout naming `outcome_code`, `outcome_reason`, the sealed snapshot id and the execution
  id, so the Argo log of the run is self-describing.
- IF a dispatched resume hits the terminal-proposal condition WHILE
  `ISSUE_INVESTIGATOR_CONTEXT_MODE` is `off` THEN THE SYSTEM SHALL return the existing
  skip without cloning, but SHALL set `outcome_code="refused"` and
  `outcome_reason="proposal-terminal"` so the run is still distinguishable from a real one.
- IF the run is NOT a dispatched resume (an intake-label investigation, a
  `@MCTL reinvestigate` directive, a direct CLI call with no work item) THEN THE SYSTEM
  SHALL behave exactly as today — skip before the clone, no assembly, no extra cost.
- WHILE the context-only path is running THE SYSTEM SHALL leave the existing proposal
  directory byte-identical, including its `.status.yaml`.
- WHEN `_OwnExecution.finish` runs for a context-only result THE SYSTEM SHALL advance the
  execution to `PHASE_SUCCEEDED`, not `PHASE_FAILED`: the run did everything it was
  permitted to do. (Today `succeeded` is computed as `skipped_reason is None`, which would
  mark it Failed.)
- IF `_assemble_context` raises on the context-only path THEN THE SYSTEM SHALL record
  `outcome_code="failed"` with `outcome_reason="context-assembly-failed"` and return an
  errored `InvestigateResult`, so a resume that could not seal C2 is never reported as a
  success.
- WHEN `DevLoopWorkflow` observes a context-only investigate result THE SYSTEM SHALL end
  the loop run with a typed `ended` reason naming `proposal-terminal` and SHALL NOT enter
  the approval wait or submit the implement step, since there is no new proposal revision
  to approve.

## Out of scope

- Option (b) from the issue: minting a fresh proposal revision behind a new approval gate
  for an already-`merged` proposal. That changes proposal identity, `resolve_slug`,
  `select_proposal_slug`, the implementer and the shepherd, and risks re-opening work that
  is done. It is a separate proposal.
- Option (c) as the *primary* behaviour: refusing the resume up front with
  `resume_refused:proposal_terminal`. It contradicts ADR 011 §8's reuse policy
  (`ALLOW_DUPLICATE`, "a `resume` of a finished loop is exactly a new run of it") and would
  make the resume surface unusable for the common case. This proposal borrows only its
  *explicit-outcome* half.
- Adding new members to `execution_requests.RESUME_REFUSAL_REASONS` or to
  `executions.PHASE_*`. The phase vocabulary is mctl-api's and closed
  (`Running`/`Succeeded`/`Failed`); the outcome is carried beside the phase, not as a new
  phase.
- Wiring the full ADR 018 `ExecutionEvidence` envelope into the investigator. This
  proposal only borrows that module's `OUTCOME_CODES` and slug rules so the outcome
  vocabulary is not invented twice.
- Changing `_OVERWRITABLE_STATUSES` itself, or relaxing the rule that a non-`proposed`
  proposal is never rewritten.

## Open questions

- Does `DevLoopWorkflow` need a `workflow.patched(...)` gate for the new end-of-loop
  branch? The observed incident shows the loop already ended in ~80s after investigate,
  so the branch may be reachable without changing the command sequence. The
  implementation must confirm this against `tests/fixtures/histories/dev_loop_resumed.json`
  and add a patch (named alongside `DISPATCHED_NOT_RUN_FAILS_PATCH`) if the replay
  diverges. Proceeding on the assumption that a patch is required, since adding one that
  turns out to be unnecessary is harmless and omitting a needed one wedges replay.
- How does the loop learn that an investigate run was context-only? The preferred route is
  the status the loop already reads through its existing `find_proposal_slug` / gitops
  activities, not a new CWFT output channel. If that read is not available at that point in
  `run`, the fallback is a typed non-zero exit code from the investigator that the CWFT
  maps to a distinguishable `WorkflowResult.phase`. Proceeding with the gitops-read route.
- The issue says E2 should not end "a bare `Succeeded`". Since the store's phase vocabulary
  is closed, this proposal keeps the phase `Succeeded` and makes it non-bare via the sealed
  C2 plus the typed outcome. If the owner wants a distinct phase, that is an mctl-api
  contract change and a separate proposal.
- Should a context-only run also post a short issue comment naming the sealed snapshot?
  Assumed no: commenting on an issue whose proposal already merged is noise. Recorded here
  in case the owner disagrees.

## Correction 2026-09-30 (owner decision, option 1): canonical WorkItem intents are a snapshot source

The resume intent lives in mctl-api (`POST /api/v1/work-items/{id}/intents`),
not in a GitHub comment. The earlier reading of design.md §5 ("the new intent is
visible in C2 because the collectors re-read the issue and its comments") was
wrong: an intent appended through the WorkItem API is never an issue comment,
so #431 acceptance item 7 would not be met. The owner rejected duplicating the
input into a GitHub comment.

Order of operations for a WorkItem-backed resumed execution (unchanged from
decision (a), now including intents):

1. resolve W1, E1, C1 and the resume intent;
2. assemble and seal C2, with the WorkItem intents as a source;
3. persist C2;
4. only then apply the proposal idempotency guard;
5. if the proposal is terminal, skip the proposal rewrite but keep E2 and C2.

### Additional acceptance criteria (EARS)

- WHEN a WorkItem-backed run assembles context, THE SYSTEM SHALL read the item's
  intents from the canonical mctl-api work-context API
  (`GET /api/v1/work-items/{id}/intents`, mctlhq/mctl-api#430) through
  `orchestrator/work_context/client.py`. It SHALL NOT read them from GitHub
  comments or from any caller-supplied text.
- WHEN the run is a dispatched resume whose execution request carries an
  `intent_id`, THE SYSTEM SHALL always include that intent in C2 as a pinned
  source that the budget never drops.
- IF that referenced intent cannot be resolved (404, a different work item, a
  read failure or a malformed body), THEN THE SYSTEM SHALL fail the run with
  `outcome_code="failed"`, `outcome_reason="intent-unresolved"` and a non-zero
  exit. It SHALL NOT seal a C2 that silently lacks the intent. A failed read is
  never treated as "no intent".
- WHILE selecting other intents, THE SYSTEM SHALL order them deterministically
  by ascending intent `id`. It SHALL take only intents newer than the highest
  intent id recorded in C1's provenance (all intents when there is no C1), up to
  a fixed cap. Intents already carried by C1 are referenced, not copied again.
- WHEN an intent enters C2, THE SYSTEM SHALL record it as a `ContextSource` of
  the new kind `work-item-intent` with a stable `source_id`
  `work-item-intent:<work_item_id>:<intent_id>`. The recorded provenance SHALL
  include the intent id, `actor_principal`, `surface`, `created_at` and a
  content hash of the canonical `{text, params}`, at `trust.tier="reported"`,
  the same tier as `human-input-response`.
- WHILE intents are in C2, THE SYSTEM SHALL treat them as input and provenance
  only. Nothing SHALL derive authorization, approval or policy state from them,
  and no historical conversation transcript SHALL be copied.
- WHILE assembling, THE SYSTEM SHALL apply the existing per-source limit,
  budget, dedup (by `source_id`) and freshness model to intents. Intents are
  immutable records, so they are classified as content-addressed.
- WHEN the proposal status is `accepted`, `implemented` or `merged`, THE SYSTEM
  SHALL still produce C2 on a valid WorkItem resume, and C2 SHALL contain the
  resume intent with its provenance.

### Dependency

mctlhq/mctl-api#430 (a read route for intents) must be released before the
source can be switched on. Until then, the collector finds the route absent.
That is a failed read for a referenced resume intent, so the run fails
explicitly; it is not an empty list. The investigator also needs
`execution_request_id` delivered to it, which is mctlhq/mctl-api#426 (released
in mctl-api 4.57.0).
