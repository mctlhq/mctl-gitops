# Record a Tier 2 implementer's scope refusal as a refusal, not as `no-commits`, and keep its reasoning

## Context

mctl-agents#360 separated "the agent deliberately committed nothing" from "the run
failed", but only on the review-fix path. In `orchestrator/run_implementer.py`,
`_read_refusal_marker` is called only from the review-follow-up flow (around line
3137). The initial implement path in `implement_one` (around line 5091) records
`needs-triage / failure.code: no-commits` whenever `_has_new_commits(target)` is
false, unless the orchestrator's own command-budget ledger is exhausted. The prompt
has the same gap. `_build_prompt` rule 5 ("If the proposal can't be safely
implemented (missing context, scope too large, blocking dependency), STOP without
committing and explain why") gives the agent no channel for its answer. The
`implementer.md` agent definitions say a BLOCKED agent must NOT write
`.implementer-refusal.json`. So an agent that follows the prompt exactly
(mctl-agents#242, workflow `mctl-agents-implement-4df6cd9e`) ends up with a durable
record that looks the same as a crashed run. Its split plan, the only useful output
of that run, survives only in an Argo step log that will age out.

This proposal adds a typed refusal channel for the initial implement path. A scope,
cross-repo or blocked decline gets a distinct durable failure code. The agent's
reason and recommendation are kept in `.status.yaml` and, as a best-effort step,
posted on the source issue. The review-fix path keeps its current semantics.

## User stories

- AS an operator triaging `needs-triage` proposals I WANT an oversized-proposal decline to carry its own failure code and the agent's split plan SO THAT I can re-scope it without digging through archived Argo logs, and without confusing it with a crash or a rate limit.
- AS the issue author I WANT a comment on my issue when the implementer declines it as too large or cross-repo SO THAT I see that it needs splitting and how.
- AS a Tier 2 implementer agent I WANT a documented marker shape for "I stopped because this cannot be done in one pass" SO THAT following prompt rule 5 produces a recognised outcome instead of `no-commits`.
- AS a platform maintainer I WANT the review-fix path's #360 charging semantics unchanged SO THAT a blocked review follow-up still charges the bounded fix-attempt cap.

## Acceptance criteria (EARS)

- WHEN `_read_refusal_marker` reads a valid marker THE SYSTEM SHALL also parse an optional `kind` field with exactly one of `no-op`, `scope`, `cross-repo` or `blocked`, and an optional string `recommendation` capped at `MAX_REFUSAL_RECOMMENDATION_CHARS` (4000) after whitespace normalisation.
- IF a marker has no `kind` field THEN THE SYSTEM SHALL treat it as `kind: no-op`, so existing markers keep their current meaning.
- IF a marker's `kind` is present but is not one of the four allowed values THEN THE SYSTEM SHALL reject the whole marker (return `None`), the same fail-closed rule used for a missing `refused: true`.
- WHEN the initial implement path finds no new commits AND the orchestrator command-budget ledger is not exhausted AND a valid marker with `kind` in {`scope`, `cross-repo`, `blocked`} exists THE SYSTEM SHALL record `status: needs-triage` with `failure.code` `refused-scope`, `refused-cross-repo` or `refused-blocked` respectively, `failure.stage: agent`, and the marker's reason as the failure message, instead of `no-commits`.
- WHEN the initial implement path finds no new commits AND a valid marker with `kind: no-op` exists AND the ledger is not exhausted THE SYSTEM SHALL record `needs-triage` with `failure.code: refused-no-op`.
- WHEN the initial implement path records any `refused-*` code THE SYSTEM SHALL write a bounded `refusal:` block (`kind`, `reason`, `recommendation`, `recorded_at`, `attempt_id`) into the same `.status.yaml` update, through `_mark_needs_triage(..., extra_fields=...)`, under the existing attempt compare-and-swap.
- WHILE the orchestrator's command-budget ledger reports `exhausted` on the initial path THE SYSTEM SHALL keep the existing budget hand-back / `verification-budget-exhausted` behaviour, ahead of any marker the agent wrote.
- IF the initial implement path finds no new commits and no valid marker THEN THE SYSTEM SHALL record `needs-triage / no-commits` exactly as today.
- IF a valid marker exists but the agent also committed THEN THE SYSTEM SHALL ignore the marker for outcome selection (commits win), as today.
- WHEN a `refused-scope`, `refused-cross-repo` or `refused-blocked` code is recorded and the proposal has a readable source issue THE SYSTEM SHALL post one comment on that issue with the kind, reason and recommendation, through the policy checkpoint, as a best-effort step whose failure is logged and never changes the recorded outcome.
- WHEN the review-fix path reads a marker whose `kind` is `scope`, `cross-repo` or `blocked` THE SYSTEM SHALL treat it as no refusal (the existing charged "no follow-up commits" path), keeping the #360 rule that a blocked review follow-up charges the cap.
- WHEN the review-fix path reads a marker with no `kind` or `kind: no-op` THE SYSTEM SHALL behave exactly as today (exit 47, or 50 / 53 for the existing flag variants).
- WHEN `_build_prompt` builds the initial (non-review) prompt THE SYSTEM SHALL tell the agent, under rule 5, to write `.implementer-refusal.json` with `refused`, `kind`, `reason` and `recommendation` when it stops without committing for scope, cross-repo or blocking reasons.
- WHEN the completion record is built for a `refused-*` initial-path result THE SYSTEM SHALL classify it as outcome `bounded_refusal` with stop reason `implement_refused` (or `deliberate_no_op` for `refused-no-op`), not `deterministic_failure / no_commits`.
- WHILE a tick's only non-success results are `refused-*` outcomes THE SYSTEM SHALL not count them as failures in `_batch_outcome`, so a correct decline does not turn the tick red. It SHALL still count them toward the per-tick limit, because a model turn was spent.

## Out of scope

- Changing the `needs-triage` state machine, or adding a new status such as `needs-split` / automatic re-investigation (see Open questions). `needs-triage` stays the terminal human gate.
- The `assert-attempt` step's misleading "five_hour/seven_day / HTTP 429" hint. That step lives in the `mctl-agents-implement` workflow template in mctl-gitops, which is not in this repo, and needs a companion change there.
- Re-labelling past `no-commits` records, such as mctl-agents#242's.
- Changing #410 (stale source) or #364 (rate limit) classification.
- Writing extra files into the gitops proposal directory beyond `.status.yaml`.

## Open questions

- Issue point 4: should `refused-scope` move the proposal to a state that invites re-investigation? This proposal records a distinct code and the recommendation, but leaves the proposal in `needs-triage` (terminal, per #300). Automatic re-investigation spends model budget and bypasses the human approval gate, so it should be a follow-up decision.
- Should `refused-no-op` on the initial path (for example "already implemented on main") be a separate code, as proposed, or fold into `refused-blocked`? Proposed: separate, because it tells the operator something different.
- An issue comment from the implementer is a new outbound write. It needs a policy-checkpoint rule like the investigator's (`orchestrator/policy_checkpoint.py`). If the checkpoint refuses it, the `.status.yaml` record is still authoritative.
- The deployed `mctl-agents-implement` CWFT and its `assert-attempt` step could not be observed from this checkout. Whether it pattern-matches `failure.code: no-commits` (and would need to learn the new codes) is unverified.
