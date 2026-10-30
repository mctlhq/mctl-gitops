# Design: issue-428-architecture-implementer-define-bounded

**This DevLoop implements PR 1 only. PR 2 and PR 3 are separate follow-up work items and
must not be implemented in this attempt.** PR 1 is sections 1, 2, 3 and 6 below. Sections
4 and 5 (and the mctl-gitops input artifact in section 3) are kept as reference design,
marked out of scope, for the follow-up issues:
- PR 2, shepherd shadow consumption: mctlhq/mctl-agents#679;
- PR 3, Temporal observe-only: mctlhq/mctl-agents#680;
- task 8, mctl-gitops optional prior-state input: mctlhq/mctl-gitops#1947.

The technical design is the one accepted in the owner review of proposal 5b586922e
(`run_id` + `step` in the identity and hash, `select_authoritative`, the honest definition
of `complete`). This revision changes only the delivery scope, plus one grounding detail:
`proposal_digest` reuses `proposal_state.proposal_content_digest`, which landed in #658
after the previous revision.

## Current state

**One implementer attempt, two entry points.** `orchestrator/run_implementer.py`:
- `_implement_one` (line 4108): the first implementation, run by Argo CWFT
  `mctl-agents-implement`, template `run-implementer`.
- `_review_feedback_one` (line 2835): `--review-feedback`, called by the shepherd as a
  subprocess.

**Attempt identity and claim.** `_resolve_attempt_id` (line 1038) returns `WORKFLOW_UID`
if set, otherwise `sha256(service|slug|owner_epoch|ordinal|HOSTNAME)`. `_implement_one`
calls it after `ensure_auth_for_sdk()` (which raises `SystemExit` before any claim). The id
is stamped into `.status.yaml` as `attempt: {id, started_at, expires_at}`. An ADR-010
`ExecutionClaim` is held through `_ClaimContext` (line 1072), checked before each push by
`_check_claim_or_raise` (line 1239), and released on every ending arm via `_release_claim`
(line 1360). `_status_is_still_ours` (line 1411) guards status writes against a newer
attempt. `update_status_yaml` is at line 1385.

**Approved-content binding.** `orchestrator/proposal_state.py` defines
`proposal_content_digest` (length-prefixed SHA-256 over `requirements.md`, `design.md`,
`tasks.md`, `proposed-content.md`) and `approval_digest_problem`, which the implementer
uses to refuse content that drifted from `approval.content_digest` (#658,
`_approval_digest_message` in `run_implementer.py`).

**The primary / fallback pair.** In the deployed CWFT the `implement-proposals` steps
template runs:
1. `implement` (`is-fallback: "false"`, token `claude-code-oauth-token`), with
   `continueOn: {failed, error}`;
2. `implement-fallback` (`is-fallback: "true"`, token `claude-code-oauth-token-2`), with
   `when: "{{steps.implement.status}} != Succeeded"`;
3. `commit` (`commit-and-push`);
4. `assert-produced`, which succeeds if either step succeeded.

Both run the same `run-implementer` template in separate pods, each with its own gitops
clone. Because `commit-and-push` runs after both, the fallback's clone cannot see what the
primary wrote. Both upload the `changes` artifact to the same S3 key
`{{workflow.name}}/agents-state.tgz` ("fallback goes second and wins"). The CWFT passes
`IS_FALLBACK` and `WORKFLOW_NAME` in the pod env; `IS_FALLBACK` is read today only by the
shell prelude (it exits 1 when token-2 is unset), not by Python. `WORKFLOW_NAME` is read in
Python only by `usage_ledger.py` (as `argo_workflow_name`). `WORKFLOW_UID` is not set, so
the two steps derive different `attempt_id`s from their `HOSTNAME`s; in a shape that sets
it they would coincide. Either way `attempt_id` alone cannot name the step, so this design
binds `run_id` + `step` explicitly.

**How an attempt ends today.** Spread over unversioned channels:
- `.status.yaml`: `implemented` + `pr` + `attempt.finished_at` + ADR-011 `execution:`,
  or `_mark_needs_triage` (line 3721), `_mark_blocked`, `_mark_rate_limited` (line 3913),
  budget / policy hand-backs;
- exit codes 0, 1, 42-54, with `_review_feedback_exit_code` mapping error prefixes;
- the `--refusal-out` JSON (`_write_refusal_out`, line 555);
- the agent-authored `.implementer-refusal.json` (`RefusalMarker`, line 396, validated by
  `_read_refusal_marker`, line 420).

**Consumers (unchanged by PR 1).** The shepherd's `_followup_exit_codes()` and
`FollowupSubprocessError.kind` (`orchestrator/run_shepherd.py`); Temporal's `classify()`
(`orchestrator/temporal/implement_outcome.py`) and `record_execution` /
`ExecutionRecord` (`orchestrator/temporal/activities/state.py`).

**Contract-module precedents.** `orchestrator/context_snapshot.py` (ADR 009),
`orchestrator/execution_identity.py`, `orchestrator/execution_evidence.py` (ADR 018,
`EvidenceRef = {evidence_id, kind}`), `orchestrator/redaction.py`. The newest ADR is
`docs/adr/020-capability-commerce-contract.md`, so the next number is 021.

**Deployed state checked:**
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`:
  `IS_FALLBACK` env (line 637) and its shell prelude check (line 455); the step order,
  `when` / `continueOn` and shared artifact key as described; several existing
  `optional: true` artifacts/secrets; no `WORKFLOW_UID` env for `run-implementer`; no
  `/tmp/prior-state` input (that is mctl-gitops#1947).
- Prior revision of this proposal at
  `agents-state/mctl-agents/proposals/issue-428-architecture-implementer-define-bounded/`
  (status `proposed`): read in full; its technical design is carried over unchanged.
- mctl MCP tools: not called. PR 1 is code-only and changes no runtime configuration.
- Not observed: whether token-2 is seeded in production. The design covers both cases.

## Proposed solution

### 1. Inert schema module: `orchestrator/implementation_completion.py` (PR 1, in scope)

Modelled on `execution_evidence.py`: frozen dataclasses, `to_dict` / `from_dict` with
unknown-key rejection, bounded leaves, and `seal()` as the only constructor that fills
identity.

```
ImplementationCompletion
  api_version   "completion.mctl.ai/v1alpha1"
  kind          "ImplementationCompletion"
  completion_id "ic-" + content_hash[7:23]        (derived)
  content_hash  sha256 over canonical JSON minus created_at/completion_id/content_hash
  created_at    ISO-8601 Z (excluded from hash)
  subject       {service, slug, work_item_id?}
  attempt       {attempt_id, run_id (WORKFLOW_NAME), step: primary|fallback,
                 phase: implement|review-remediation, ordinal?,
                 execution_id? (we_), context_id? (ex-), claim_id?, owner_epoch?}
  source        {repository, base_ref, base_sha?, branch, head_sha?}
  proposal      {proposal_digest, review_bundle_digest?}
  outcome       complete | incomplete | bounded_refusal | budget_exhausted
                | deterministic_failure | harness_failure
  stop_reason   {code: closed set, detail?: <=600 chars, redacted}
  verification  [<=32] {check_id, result: pass|fail|unknown|not_run,
                        classification: exit_zero|exit_nonzero|timeout|budget_denied|
                                        not_applicable|observation_failed,
                        required: bool, evidence_ref?}
  remaining_work [<=32] {item_id, summary <=256 chars, redacted}
  evidence_refs [<=32] {evidence_id, kind}
```

- `run_id` and `step` are part of the hashed content, so the primary and fallback records
  of one Argo run always have distinct `completion_id`s. `step` comes from `IS_FALLBACK`
  (`"true"` → `fallback`, anything else → `primary`). Review-feedback mode is always
  `primary`; its `run_id` is the shepherd's own Argo workflow name.
- `proposal_digest` is `proposal_state.proposal_content_digest(proposal_dir)`, the same
  framing the approval gate already checks, computed at attempt start.
- **Invariants.** `complete` requires a `head_sha`, every `required` check at `pass`, and
  empty `remaining_work`. `incomplete` requires non-empty `remaining_work`. There are no
  fields for approval, review verdict, merge, release, ownership, claim extension or
  budget.
- **What `complete` means in v1alpha1.** The required set is exactly the
  orchestrator-side gates: `commits_present` (`_has_new_commits`), `chart_major_guard`
  (`_detect_chart_major_bumps`), `push_succeeded`, `claim_valid_at_push`. Nothing compares
  the pushed head with the approved `tasks.md`. The module docstring, ADR 021 and the
  stop-reason code say so: `complete` / `gates_passed` means "the attempt pushed a head
  that passed the orchestrator gates"; it does not mean "the approved scope is
  implemented", and it is not a review verdict. Task-coverage verification is follow-up
  **F1** (a future `task_coverage` check, `required` in a later api version).

`stop_reason.code` closed set and mapping (one pure function, `completion_from_result`):

| Today's signal | outcome | stop_reason.code |
| --- | --- | --- |
| `implemented` write / `EXIT_OK` with a new head | complete | `gates_passed` |
| marker with new optional `remaining` list | incomplete | `known_work_remains` |
| 47 `DELIBERATE_NO_OP` | bounded_refusal | `deliberate_no_op` |
| 50 `CI_EVIDENCE_INSUFFICIENT` | bounded_refusal | `evidence_insufficient` |
| 53 `POLICY_REFUSED` | bounded_refusal | `policy_refused` |
| 51 `VERIFICATION_BUDGET_EXHAUSTED` / budget hand-back | budget_exhausted | `verification_budget` |
| 44 `OPERATION_TIMEOUT` | budget_exhausted | `operation_timeout` |
| 52 `RATE_LIMITED` / `_mark_rate_limited` | budget_exhausted | `rate_limited` |
| 42 `NO_FOLLOWUP_COMMITS` / no commits | deterministic_failure | `no_commits` |
| 43 `BRANCH_MISSING_ON_ORIGIN` | deterministic_failure | `branch_missing` |
| `needs-triage` policy arms (chart guard, stale source) | deterministic_failure | `policy_gate` / `stale_source` |
| 46 `ORPHANED_SUBAGENT` | harness_failure | `orphaned_subagent` |
| 48 `FENCED` | harness_failure | `fenced` |
| 49 `CLAIM_REFUSED` | harness_failure | `claim_refused` |
| 54 `POLICY_UNDECIDED` | harness_failure | `policy_undecided` |
| 1 generic / unexpected exception | harness_failure | `unexpected_error` |

Pre-claim exits (`pre_start` per #418, `ensure_auth_for_sdk` failure, the token-2-unset
shell exit, and the approval-digest `blocked` arm if it precedes the claim) produce no
completion.

### 2. Emission and projection in `run_implementer.py` (PR 1, in scope)

- Add `completion_from_result(...)` (the table above) and `_AttemptObservations`
  (`base_sha` / `head_sha`, `proposal_digest`, `review_bundle_digest`, the four required
  gate records, and non-required `CommandBudgetLedger` entries, classification only).
- Add one `try/finally` emission point after claim acquisition in `_implement_one` and
  `_review_feedback_one`. It seals once, projects into `.status.yaml` through
  `update_status_yaml(..., completion=...)` on the arms that already write status, and
  writes `--completion-out` (new flag, bounded, best effort, mirroring
  `_write_refusal_out`). Nothing consumes `--completion-out` in PR 1; it is the carrier
  #679 will read.
- `RefusalMarker` gains an optional bounded `remaining: [{item_id, summary}]`. When it is
  present on an otherwise successful push, the outcome is `incomplete`.
- `.status.yaml` projection (durable result, not telemetry):

  ```yaml
  completion:
    api_version: completion.mctl.ai/v1alpha1
    run_id: mctl-agents-implement-abc12
    authoritative:            # the record that speaks for this Argo run
      completion_id: ic-...
      content_hash: sha256:...
      attempt_id: ...
      step: primary
      outcome: deterministic_failure
      stop_reason: no_commits
      head_sha: null
      verification: {required_passed: 1, required_total: 4, optional_total: 0}
    other:                    # optional: the non-authoritative step's summary
      relation: fallback      # fallback | superseded
      completion_id: ic-...
      step: fallback
      outcome: harness_failure
      stop_reason: rate_limited
    primary_observed: true
  ```

- **Replay guard** keyed on `(run_id, step, attempt_id)`: same key and same
  `completion_id` is a no-op; same key and different `completion_id` is refused and
  logged; a write whose `attempt.id` no longer owns the status is refused
  (`_status_is_still_ours`). A pod restart or Argo retry inside one step therefore cannot
  flip `budget_exhausted` / `harness_failure` into `complete`.
- **Stale claim.** If `_check_claim_or_raise` raises at emission, no projection is
  written; `--completion-out` still gets `harness_failure` / `fenced` or `claim_refused`.

### 3. Primary / fallback authority (PR 1, in scope)

**Decision: within one Argo run, the primary record is authoritative unless the fallback
is `complete`.** A failing fallback never replaces the primary's outcome. A succeeding
fallback does, and the primary's record is kept as a `superseded` summary. This mirrors
`assert-produced`, which counts the run as produced if either step succeeded.

`select_authoritative(primary: Summary | None, fallback: Completion) -> Projection` is a
pure function in `implementation_completion.py`:

| primary handoff | fallback outcome | authoritative | other |
| --- | --- | --- | --- |
| present, any outcome | `complete` | fallback | primary as `superseded` |
| present, any outcome | not `complete` | primary | fallback as `fallback` |
| absent (not readable) | any | fallback, `primary_observed: false` | none |
| fallback never reached the claim | n/a (no record) | primary (artifact untouched) | none |

The primary step always writes `authoritative = own record`; it runs first and never sees
a fallback.

**In scope for PR 1:** the fallback reads an optional directory, `/tmp/prior-state`, via
`_load_prior_handoff(path, ref, run_id)`: a bounded read of `.status.yaml`, extracting only
`completion.authoritative`, validated, accepted only if `run_id` equals its own
`WORKFLOW_NAME` and `step == primary`; otherwise treated as absent. When the directory does
not exist, the fallback projects with `primary_observed: false`. The owner has accepted
this interim state.

**Out of scope for this attempt (reference, mctlhq/mctl-gitops#1947):** the mctl-gitops
change that populates `/tmp/prior-state` by adding an `optional: true` input artifact on
`run-implementer` at the existing key `{{workflow.name}}/agents-state.tgz`. For the
primary nothing exists yet and the input is skipped; for the fallback it holds the
primary's handoff. PR 1 must work identically whether or not that change is deployed.

The status *transition* the fallback writes (for example `rate_limited` over the primary's
`needs-triage`) is unchanged existing behaviour. Only the `completion:` block follows the
authority rule. ADR 021 states that `completion.authoritative` (the attempt's result) and
`status` (lifecycle state) may legitimately differ after a failed fallback.

### 4. Shepherd consumption, shadow mode (PR 2) — OUT OF SCOPE for this attempt

Reference design for mctlhq/mctl-agents#679; not implemented here. The shepherd passes
`--completion-out <tmp>` next to `--refusal-out`; `_read_completion(path, expected_run_id)`
does a bounded read and `from_dict`, returning `None` on absent, invalid, oversize or
mismatched files. `_followup_kind_from_completion(c)`:

| completion | FollowupKind |
| --- | --- |
| `complete` | success path |
| `bounded_refusal` | `refused` |
| `harness_failure` + `fenced` / `claim_refused` | `fenced` |
| other `harness_failure`; `budget_exhausted` except `rate_limited` | `harness` |
| `rate_limited` | existing rate-limited handling |
| `deterministic_failure`, `incomplete` | `deterministic` |

The shepherd logs `completion-disagreement` against `_followup_exit_codes()` and changes
charging only when `SHEPHERD_TRUST_COMPLETION` is on (default off). The merge decision
never reads `outcome`.

### 5. Temporal / execution record (PR 3) — OUT OF SCOPE for this attempt

Reference design for mctlhq/mctl-agents#680; not implemented here. `ExecutionRecord` gains
optional `completion_id`, `completion_outcome`, `completion_stop_reason`,
`completion_step`, sent through the existing `optional` dict and 4xx retry path. A new
read-only activity `read_proposal_completion(service, slug)` in
`orchestrator/temporal/activities/proposals.py` (registered in `worker.py`) is read by
`dev_loop._implement` and `implement_sweep` after `success` or `finalization`, accepted
only when `completion.run_id == result.workflow_name`, behind
`workflow.patched("implement-completion")`, with no control-flow change. A
`step: fallback, primary_observed: false` record is recorded with its step and never
relabelled as the primary.

### 6. Documentation (PR 1, in scope)

`docs/adr/021-implementation-completion-contract.md` covers: scope (implementer-phase
completion contract, not a review verdict, not approval, not a DevLoop); the outcome /
stop-reason table; the v1alpha1 meaning of `complete` and follow-up F1; the primary /
fallback authority rule and `primary_observed: false`; the replay key; the carrier
boundary (git = durable result projection, Temporal / Argo = runtime, mctl-api = read
model); the non-authorities list; and a "Consumers (follow-up)" section linking #679,
#680 and mctl-gitops#1947. #679 and #680 will each extend the ADR with their consumer
section.

## Alternatives

1. **Extend exit codes and the `--refusal-out` JSON.** Exit codes cannot carry the run,
   step, claim, head or digest bindings, and the JSON is unversioned and exists only in
   review-feedback mode. Dropped.
2. **Reuse `ExecutionEvidence` (ADR 018) with an implementer-specific outcome.** Leaks
   implementer semantics into a cross-agent outcome. Kept only as a join point
   (`ArtifactRef(kind: implementation-completion, content_hash)`).
3. **Fallback authority: last writer wins.** A fallback `harness_failure` on the missing
   second account would erase the primary's real outcome. Dropped.
4. **Fallback authority: drop the fallback's record.** Loses the only record when the
   fallback succeeds. Dropped for primary-unless-fallback-complete.
5. **Merge the two records in `commit-and-push`.** Moves contract logic into untestable
   CWFT shell. Dropped.
6. **Ship PR 1-3 in this one DevLoop.** A DevLoop delivers one branch and one PR; it cannot
   wait for PR 1 to merge before opening PR 2 and PR 3. Dropped: PR 2 and PR 3 are
   separate work items (#679, #680).

## Platform impact

- **Delivery:** this DevLoop produces one mctl-agents PR (PR 1). It changes no consumer
  behaviour. #679, #680 and mctl-gitops#1947 follow independently; mctl-gitops#1947 may
  merge before or after PR 1.
- **Migrations:** none. `.status.yaml` gains an optional `completion:` key that existing
  readers ignore (`proposal_state.load_status`, `gitops_state._parse_status_yaml` read
  named keys).
- **Backward compatibility:** exit codes, `--refusal-out` and status transitions are
  unchanged. The shepherd does not pass `--completion-out` yet, so review-feedback runs
  only project into `.status.yaml`. `/tmp/prior-state` absent yields
  `primary_observed: false`.
- **Resource impact:** one sha256 over the proposal files (already computed by the approval
  gate) and a small extra YAML block per status write.
- **Risks and mitigations:**
  - *`complete` read as "scope done" or review-clean:* the `gates_passed` code name,
    docstring and ADR wording, and no review fields in the schema.
  - *Fallback hides the primary's outcome:* `select_authoritative` and T3a / T3b; before
    mctl-gitops#1947 it is visible as `primary_observed: false`, not silent.
  - *Stale prior-state from another run read as the primary:* `run_id` match fails closed.
  - *Emission bug breaks an existing arm:* emission is in a `finally` that catches and logs
    its own errors and never changes the exit code; T7 pins existing behaviour.
  - *Scope creep into PR 2 / PR 3:* requirements forbid touching `run_shepherd.py` and
    `orchestrator/temporal/**` in this attempt.
  - *Private content leaks:* bounded, redacted leaves; no stdout/stderr field.

## Open questions

- `incomplete` comes only from the new `RefusalMarker.remaining` list. Proceeding with it.
- Whether the record should additionally carry the recorded `approval.content_digest`
  (today it carries `proposal_content_digest`, which the approval gate already enforces
  equal before the attempt starts). Deferred to a later version.
- Resolved by owner: `primary_observed: false` interim is acceptable; `WORKFLOW_UID` in the
  CWFT is a separate decision.
