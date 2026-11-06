# Design: issue-414-a-tier-2-implementer-that-correctly-decl

## Current state

All references are to `orchestrator/run_implementer.py` unless noted. Line numbers
are from the current clone and have shifted since the issue was filed.

- **Marker contract.** `REFUSAL_MARKER_FILENAME = ".implementer-refusal.json"` (~387).
  `RefusalMarker` (~428) is a frozen dataclass with `reason`, `insufficient_evidence`,
  `verification_budget_exhausted` and `remaining`. `_read_refusal_marker` (~486)
  fails closed. It does a bounded read (`MAX_REFUSAL_MARKER_BYTES`), requires the
  file to be untracked (`git ls-files --error-unmatch` must exit 1), requires a JSON
  object with `refused is True` and a non-empty `reason`, and caps the reason at
  `MAX_REFUSAL_REASON_CHARS = 600`. It has no notion of *why* the agent declined.
- **Review-fix path** (~3132): `obs.commits_present = _has_new_commits(target,
  base=old_head)`. If there are no commits, it reads the marker and maps it to
  `VERIFICATION_BUDGET_EXHAUSTED_ERROR_PREFIX` (exit 52), then
  `CI_EVIDENCE_INSUFFICIENT_ERROR_PREFIX` (exit 50), then `REFUSAL_ERROR_PREFIX`
  (exit 47). Otherwise it falls through to the charged exit 42.
- **Initial implement path** in `implement_one` (~5003-5104). After
  `_run_implementer_agent`, `obs.commits_present = _has_new_commits(target)`. If
  false, the only branch is `budget_ledger.exhausted` (the #430 hand-back or the
  terminal `verification-budget-exhausted`). Every other case calls
  `_mark_needs_triage(ref, code="no-commits", stage="agent", message="implementer
  produced no commits", attempt=..., claim_context=...)`. The marker is never read
  here.
- **`_mark_needs_triage`** (~3942) writes `failure.{code,stage,message}`, `notes`
  and the finished `attempt`. It accepts `extra_fields` and does the attempt
  compare-and-swap via `_status_is_still_ours`.
- **Prompt.** `_build_prompt` (~1915) initial branch (~2180) rule 5: "If the
  proposal can't be safely implemented (missing context, scope too large,
  blocking dependency), STOP without committing and explain why." A ground-rule
  bullet says cross-repo work should be described "in your final message". No
  marker is mentioned. Marker instructions appear only in the review branch
  (~2098-2174).
- **Agent definitions.** `agents/*/.claude/agents/implementer.md` (8 copies:
  `_generic`, `mctl-agent`, `mctl-agents`, `mctl-api`, `mctl-docs`,
  `mctl-gitops`, `mctl-portal`, `mctl-web`). The "Declining to act is a valid
  outcome" bullet limits the marker to review follow-ups and says that if
  BLOCKED, "do NOT write the marker. That is a failed attempt, not a refusal."
  This is correct for the review cap, but it is what drove the #242 agent to write
  nothing.
- **Completion.** `_classify_result` (~5506) maps errors starting with
  `_IMPLEMENT_NO_COMMITS_PREFIX = "implementer produced no commits"` (~5465) to
  `EXIT_NO_FOLLOWUP_COMMITS`, which gives `deterministic_failure / no_commits`.
  `orchestrator/implementation_completion.py` `STOP_REASON_OUTCOMES` already has
  `OUTCOME_BOUNDED_REFUSAL` codes (`deliberate_no_op`, `evidence_insufficient`,
  `policy_refused`). `docs/adr/021-implementation-completion-contract.md` holds
  the exit-to-completion table.
- **Similar arm.** The #410 admission gate (~4772) uses
  `read_source_issue(...)` (`orchestrator/source_issue.py`), records a
  `needs-triage` code, and sets `ImplementResult.stale_source` so `_batch_outcome`
  does not count it as failed. `verdict.issue_ref` gives the source issue.
- **Issue comments.** `orchestrator/run_issue_investigator.py` (~1448) posts
  `gh issue comment` through the policy checkpoint and treats failure as a
  warning (~4399-4405). The implementer has no comment path today.
- **Shepherd.** `orchestrator/run_shepherd.py` `SOURCE_RECHECKED_FAILURE_CODES`
  (~1631) is a closed set (`missing-pr`, `source-*`). New `refused-*` codes are
  not in it, so the shepherd will not overwrite them. That is the desired
  behaviour.
- **Tests.** `tests/test_run_implementer_refusal.py` (marker parsing and the
  review path), `tests/test_run_implementer_completion.py` (fails if an `EXIT_*`
  or stop reason is unmapped), and `tests/test_run_implementer_budget_handback.py`
  (initial-path no-commit arms).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/` lists the tenants `admins`, `karabu`, `labs`,
  `namax66`. `tenants/` lists `admins`, `commerce-proof`, `erpact`, `karabu`,
  `labs`, `mctl`, `namax66`. A grep there for `run_implementer` and
  `implementer-refusal` found nothing. The `mctl-agents-implement`
  ClusterWorkflowTemplate and its `assert-attempt` step are not under this
  checkout, so their handling of `failure.code` could not be observed (see Open
  questions in requirements.md).
- No mctl MCP tools were called. The change is orchestrator-internal and does not
  depend on any tenant service's runtime configuration.

## Proposed solution

### 1. Typed marker (`_read_refusal_marker`, `RefusalMarker`)

Add two optional fields to the marker:

```json
{"refused": true, "kind": "scope" | "cross-repo" | "blocked" | "no-op",
 "reason": "...", "recommendation": "..."}
```

- Add `REFUSAL_KINDS = frozenset({"no-op", "scope", "cross-repo", "blocked"})` and
  `MAX_REFUSAL_RECOMMENDATION_CHARS = 4000`. The recommendation needs more room
  than the 600-char reason, because a split plan is a list. It is still well
  under `MAX_REFUSAL_MARKER_BYTES`.
- `RefusalMarker` gains `kind: str = "no-op"` and `recommendation: str = ""`.
- Validation stays fail-closed. A missing `kind` means `no-op` (backward
  compatible). A present but unknown or non-string `kind` rejects the whole
  marker. A non-string `recommendation` is dropped, not repaired, the same way as
  `_parse_marker_remaining`. The recommendation is whitespace-normalised but keeps
  line breaks collapsed into single spaces, as the reason does.

### 2. Review-fix path keeps #360 semantics

At ~3137, after `refusal = _read_refusal_marker(target)`, treat
`refusal.kind != "no-op"` as `refusal = None` and log
`info: ignoring kind=<k> marker on review follow-up (blocked follow-ups charge the
cap)`. The existing three flag branches run unchanged for `no-op` markers. This
keeps the `implementer.md` rule that a blocked review follow-up is a charged
failure.

### 3. Initial implement path reads the marker

In `implement_one`, inside `if not obs.commits_present:`, keep the
`budget_ledger.exhausted` block first. The orchestrator's own observation outranks
the agent's claim, which matches the review path, where budget exhaustion wins.
Before the unconditional `no-commits` call, add:

```python
refusal = _read_refusal_marker(target)
if refusal is not None:
    code = f"refused-{refusal.kind}"          # refused-scope / -cross-repo / -blocked / -no-op
    message = f"{IMPLEMENT_REFUSED_ERROR_PREFIX} {refusal.kind}: {refusal.reason}"
    recorded = _mark_needs_triage(
        ref, code=code, stage="agent", message=message,
        attempt=attempt, claim_context=claim_ctx,
        extra_fields={"refusal": {
            "kind": refusal.kind, "reason": refusal.reason,
            "recommendation": refusal.recommendation or None,
            "recorded_at": _now_iso(), "attempt_id": attempt.get("id"),
        }},
    )
    if recorded and refusal.kind != "no-op":
        _comment_refusal_on_source_issue(ref, refusal)   # best-effort
    return ImplementResult(ref=ref, pr_url=None,
                           error=_triage_error(message, recorded),
                           implement_refusal=refusal.kind)
```

- Add the new constant `IMPLEMENT_REFUSED_ERROR_PREFIX = "implementer refused:"`.
- `ImplementResult` gets a new field `implement_refusal: str | None = None`.
- The `.status.yaml` write uses the existing `update_status_yaml` path, so the
  only gitops change is the one already being committed for `needs-triage`.

### 4. Best-effort source-issue comment

The new helper `_comment_refusal_on_source_issue(ref, refusal)`:

- Reads the source issue with `read_source_issue(_load_status(ref.status_path),
  stage="refusal", gh_api_json=_gh_api_json)`. It returns early if the source is
  not linked, is unknown, or is closed.
- Builds a body with a hidden idempotency marker
  `<!-- mctl-implementer-refusal attempt=<attempt_id> -->`, the kind, the reason,
  the recommendation, and the proposal path.
- Posts through the same policy checkpoint and `gh issue comment` pattern used in
  `run_issue_investigator.py`.
- Catches every failure and logs it with `warn:`. The comment never changes
  `ImplementResult`, the exit code or the recorded status.

### 5. Completion and batch accounting

- `_classify_result`: before the `_IMPLEMENT_NO_COMMITS_PREFIX` check, map
  `result.implement_refusal` to `(OUTCOME_BOUNDED_REFUSAL, "deliberate_no_op")`
  for `no-op`, and to `(OUTCOME_BOUNDED_REFUSAL, "implement_refused")` otherwise.
  Return exit code `None`, as the stale-source arm does.
- Add `"implement_refused": OUTCOME_BOUNDED_REFUSAL` to
  `implementation_completion.STOP_REASON_OUTCOMES`.
- Update the ADR 021 table with a row for the initial-path refusal marker.
- `_batch_outcome` excludes `implement_refusal` results from `failed`, as it does
  for `stale_source`. They still count toward the limit, because a model turn was
  spent. `main()`'s summary prints them under `=== Declined (re-scope) ===`.

### 6. Prompt and agent definitions

- `_build_prompt` initial branch, rule 5: tell the agent to write
  `.implementer-refusal.json` with `{"refused": true, "kind":
  "scope"|"cross-repo"|"blocked"|"no-op", "reason": ..., "recommendation": ...}`
  when it stops without committing. The recommendation should be a concrete split
  or routing plan. Never write the marker beside a commit. Update the cross-repo
  ground-rule bullet to point at `kind: cross-repo`.
- All 8 `agents/*/.claude/agents/implementer.md`: rewrite the "Declining to act"
  bullet into two cases. (a) On a review follow-up, write the marker only for a
  deliberate no-op; if blocked, do not write it (unchanged). (b) On an initial
  implement run, write it with the matching `kind` for scope, cross-repo, blocked
  or already-done.

## Alternatives

- **Scrape the agent's final message for "Why I'm stopping".** Rejected for the
  same reason as `REFUSAL_MARKER_FILENAME`'s comment: prose is unstable across
  models, and a regex could read a crash narration as a refusal.
- **Reuse the plain `no-op` marker on the initial path without `kind`.** Rejected.
  It cannot tell "already done" apart from "too large", and it contradicts the
  agent definitions' review-path rule that BLOCKED must not write the marker.
  The typed `kind` lets each path accept exactly what it means.
- **Move `refused-scope` to a new status (for example `needs-split`) or
  automatically re-trigger the investigator.** Deferred. It changes the status
  state machine consumed by the shepherd, reconcile and gitops tooling. It would
  also spend model budget without a human decision. The distinct code plus the
  issue comment already makes the signal actionable. Recorded as an open question.
- **Write the recommendation as `refusal.md` in the proposal directory.**
  Rejected for now. The implementer's gitops write path is `.status.yaml`-centric,
  and a bounded field there is enough. The issue comment covers the readable
  long-form copy.

## Platform impact

- **Migrations:** none. Existing `.status.yaml` files and markers are untouched.
  A marker without `kind` keeps its current meaning on both paths.
- **Backward compatibility:** new `failure.code` values (`refused-*`) and a new
  `refusal:` block. Consumers that pattern-match `no-commits` (possibly the
  mctl-gitops `assert-attempt` step) stop seeing these cases. That is intended, but
  it needs a companion mctl-gitops check. `STOP_REASON_CODES` grows by one value
  in `completion.mctl.ai/v1alpha1`. That is additive, but any strict external
  validator of the completion record needs the new code.
- **Risk: an agent abuses `scope` to dodge work.** Mitigation: the result is still
  terminal `needs-triage` with a human gate. It is not a success, does not open a
  PR, and is not retried automatically. It only changes the label and keeps the
  reasoning.
- **Risk: a committed or stale marker.** Mitigation: the existing untracked check
  and "commits win" ordering are kept.
- **Risk: comment noise or a failed comment.** Mitigation: one comment per
  recorded attempt (idempotency marker), skipped for closed issues, best-effort,
  and through the policy checkpoint.
- **Resources:** one extra GitHub read and one comment on refusal arms only. No
  model cost.
