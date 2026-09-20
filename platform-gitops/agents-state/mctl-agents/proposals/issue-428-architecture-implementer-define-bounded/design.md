# Design: issue-428-architecture-implementer-define-bounded

## Current state

**The implementer's terminal signal is spread across four channels, none of them
a record.**

1. *Exit codes.* `orchestrator/run_implementer.py:191-256` defines `EXIT_OK` (0),
   `EXIT_GENERIC_FAILURE` (1), `EXIT_NO_FOLLOWUP_COMMITS` (42),
   `EXIT_BRANCH_MISSING_ON_ORIGIN` (43), `EXIT_OPERATION_TIMEOUT` (44),
   `EXIT_BLOCKED_ONLY` (45), `EXIT_ORPHANED_SUBAGENT` (46),
   `EXIT_DELIBERATE_NO_OP` (47), `EXIT_FENCED` (48), `EXIT_CLAIM_REFUSED` (49),
   `EXIT_CI_EVIDENCE_INSUFFICIENT` (50). `_review_feedback_exit_code`
   (`:520-546`) maps an `ImplementResult.error` string prefix onto one of them.
   The vocabulary is already semantically rich — and it is eight bits wide, only
   produced in `--review-feedback` mode, and bound to nothing.
2. *`.status.yaml`.* `update_status_yaml` flips `in-progress` (`:3232`),
   `implemented` (`:3302`), `needs-triage` (`_mark_needs_triage`, `:2772-2815`,
   writing `failure: {code, stage, message}` plus a truncated `notes`), or back
   to `accepted` on hand-back (`_hand_back_if_still_ours`, `:1171`). Writes go
   through `orchestrator/proposal_state.update_status_file`, which merges and
   renames atomically (`_write_status_atomic`) but is explicitly not exclusive —
   the lost-update race is documented there and tracked as #354.
3. *The refusal sidecar.* `--refusal-out` (`:3593`) writes
   `{"refused": true, "reason": ...}` via `_write_refusal_out` (`:444`),
   deliberately best-effort: "the exit code alone already carries the decision
   that matters". The shepherd reads it with `_read_refusal_reason`
   (`run_shepherd.py:778`) purely for prose.
4. *In-process only.* `ImplementResult` (`run_implementer.py:574-596`) carries
   `error`, `skipped_reason`, `blocked`, `counts_toward_limit`, `stale_source`.
   It never leaves the process; `BatchOutcome` (`:599-611`) aggregates it for a
   printed summary.

**The consumers re-derive intent.** `orchestrator/run_shepherd.py` owns the real
semantic map, in prose and in three separately-defined code sets:
`_followup_code_sets()` (`:655`) splits `deterministic` (42/43/44) from `harness`
(46/50); `_refusal_codes()` (`:755`) isolates 47; `_fenced_codes()` (`:766`)
isolates 48/49; everything else falls to `transient`. The result is
`FollowupKind = Literal["transient", "deterministic", "harness", "refused",
"fenced"]` (`:702`), whose docstring explains that a typo in the literal would
silently route work into the counter-less arm. That is the contract this issue
asks for — except that it lives in the *consumer*, is keyed on a process exit
status, and is scoped to review remediation.

**The platform observes Argo separately.**
`orchestrator/temporal/implement_outcome.py` reads the Argo node graph
(`observe_implementer`) and classifies `pre_start | execution | finalization |
success` (`classify`), specifically because "`Failed` alone cannot say WHETHER
the implementer ever ran". This is an observation *about* the run made by
something other than the run, and it deliberately fails closed toward
`execution` when the node map is unreadable.

**The durable audit row is one word.**
`orchestrator/temporal/activities/state.py:29-44` — `ExecutionRecord(
temporal_workflow_id, agent, environment, version, image_ref, target_repo,
argo_workflow_name, phase)` where `phase` is `Succeeded | Failed | Error`. Its
own docstring already records that `target_repository_sha` is missing because no
CWFT exposes it.

**Identity already exists and is deterministic.**
`run_implementer._resolve_attempt_id(service, slug, owner_epoch,
attempt_ordinal)` (`:822`) resolves `WORKFLOW_UID`, else
`sha256("{service}|{slug}|{owner_epoch}|{ordinal}|{HOSTNAME}")` — ADR-010 §8
forbids a UUID fallback for exactly the replay reason this issue raises.
`orchestrator/lifecycle/contract.py` supplies `ExecutionClaim`, `Executor`,
`ClaimAnswer`, the closed claim verdicts (`CLAIM_HELD_BY_ME`,
`CLAIM_HELD_BY_OTHER`, `CLAIM_FENCED`, `CLAIM_UNCLAIMED`, `CLAIM_UNKNOWN`) and
`idempotency_key_for` (`:1013`). `_status_is_still_ours` (`run_implementer:1144`)
is the compare-and-swap every ending attempt already performs on `attempt.id`.

**There is a precedent for exactly this deliverable.** ADR-009 plus
`orchestrator/context_snapshot.py`: a versioned (`context.mctl.ai/v1alpha1`),
stdlib-only, frozen-dataclass, `sha256:`-prefixed, content-addressed schema with
`seal()`, `from_dict`, `validate()`, closed vocabularies, bounded locator/selector
lengths, and an explicit "no field here is ever consumed by an authorization
decision" rule. It shipped inert — imported by tests and fixtures only. That is
the shape this proposal reuses.

## Proposed solution

### 1. A new schema module, inert on landing

`orchestrator/implementation_completion.py`, stdlib only (no
`claude_agent_sdk`, no `httpx`, no `yaml`), so the Temporal worker can import it
without violating `tests/test_worker_isolation.py`. Mirrors
`context_snapshot.py` structurally and reuses its two published primitives —
`context_snapshot.hash_bytes` and `canonical_json` — rather than inventing a
second hashing convention (the risk ADR-009 names by hand).

```text
api_version  "implementation.mctl.ai/v1alpha1"
kind         "ImplementationCompletion"

ImplementationCompletion
  api_version, kind
  completion_id      "ic-" + content_hash[7:23]   (derived, never random)
  content_hash       sha256: over every field except created_at
  created_at         ISO-8601, excluded from the hash
  work_item          WorkItemRef
  attempt            AttemptRef
  source             SourceRef
  outcome            closed vocabulary (below)
  stop_reason        StopReason | null      (null iff outcome == "complete")
  verification       VerificationRecord[]   (bounded)
  remaining_work     RemainingWork[]        (bounded)
  evidence_refs      EvidenceRef[]          (bounded; references only)

WorkItemRef            service, slug, proposal_path,
                       proposal_content_hash   (approved scope, sha256:)
AttemptRef             attempt_id, attempt_ordinal, owner_epoch, claim_id,
                       executor_type, executor_id, argo_workflow_name,
                       temporal_workflow_id, temporal_run_id
SourceRef              repo, base_branch, base_sha, head_branch, head_sha,
                       pr_url
StopReason             code (closed), message (bounded), exit_code
VerificationRecord     check_id, result (pass|fail|unknown), classification,
                       evidence_ref (bounded), required_for_completion
RemainingWork          task_ref, state (not-started|partial|blocked),
                       note (bounded)
```

Outcome vocabulary, closed and exhaustive:

| outcome | meaning | typical origin today |
|---|---|---|
| `complete` | the approved scope is implemented and its required verification passed; ready for independent review | `EXIT_OK` + `implemented` flip (`:3302`) |
| `incomplete` | the attempt ended with known approved work remaining | new — today indistinguishable from `complete` |
| `bounded_refusal` | the agent ran, reasoned and deliberately changed nothing | `EXIT_DELIBERATE_NO_OP` (47), `EXIT_CI_EVIDENCE_INSUFFICIENT` (50) |
| `budget_exhausted` | the bounded execution envelope (ADR-011 `implementer_envelope`) expired | `EXIT_OPERATION_TIMEOUT` (44) |
| `deterministic_failure` | the implementer did its job and the answer is no; re-running reproduces it | `EXIT_NO_FOLLOWUP_COMMITS` (42), `EXIT_BRANCH_MISSING_ON_ORIGIN` (43) |
| `harness_failure` | our own plumbing lost or could not supervise the work | `EXIT_ORPHANED_SUBAGENT` (46), `EXIT_GENERIC_FAILURE` (1) |

Claim outcomes (`EXIT_FENCED` 48, `EXIT_CLAIM_REFUSED` 49) deliberately produce
**no document**: the attempt stood down before mutating anything, and ADR-010
already says a fence is not a failure of the proposal. The absence is the signal,
and the shepherd's existing `fenced` arm keeps handling it.

`seal(...)` takes already-computed inputs, validates, and returns the frozen
document. `from_dict` rejects unknown keys, unknown `api_version`/`kind` and
vocabulary violations with `ImplementationCompletionError` — no default-shape
fallback, exactly as `context_snapshot.from_dict`.

### 2. Replay-safety as schema properties, not caller discipline

- `idempotency_key_for_completion(...)` delegates to
  `lifecycle.contract.idempotency_key_for` with `action="implementation-complete"`,
  so one attempt derives one key across a Temporal retry, an Argo pod restart and
  an exporter redelivery — ADR-010 §8's rule, not a second one.
- `reconcile(prior, new)` is a pure function returning
  `duplicate | accepted | refused`. Identical content for the same `attempt_id`
  is `duplicate`. A *different* `outcome` for the same `attempt_id` is `refused`,
  which makes "a retry silently turns `budget_exhausted` into `complete`"
  unrepresentable rather than merely discouraged. A different outcome needs a new
  `attempt_id`, which `_resolve_attempt_id` already mints deterministically per
  `(service, slug, owner_epoch, ordinal, HOSTNAME)`.
- `staleness_of(document, *, observed_head_sha, claim_verdict, status_attempt_id)`
  returns `fresh | stale`. Any disagreement — head moved, verdict is not
  `CLAIM_HELD_BY_ME`, the `.status.yaml` attempt block names someone else — is
  `stale`, and `effective_outcome()` downgrades a stale `complete` to
  `harness_failure` with `stop_reason.code = "stale-attempt"`. Fail closed in one
  direction only: nothing can ever be upgraded *to* `complete`.
- `reconcile_with_argo(argo_outcome, document)` folds
  `implement_outcome.classify`'s verdict against the document and resolves every
  disagreement to the non-complete side. The two observers stay independent; the
  contract only says which one loses.

### 3. Lifecycle boundary enforced by test, not by comment

The module contains no field expressing approval, review cleanliness, merge,
release, ownership or budget extension. `tests/test_implementation_completion.py`
asserts that no dataclass field name across the module matches
`approve|approval|merge|release|authoriz|grant|owner_state|review_clean|lease`,
and a mutation test flips a document to `complete` and asserts that
`proposal_state.execution_authorization`, `human_approval_satisfied` and
`run_shepherd`'s merge path all return exactly what they returned before. This is
ADR-010 §7's projection test applied to a result document, and it exists because
#344 records a reviewer reading an ownership label as merge authorization.

### 4. Integration points — all additive, none switched over in this proposal

- **`run_implementer.py`**: a new `--completion-out <path>` flag, sibling to
  `--refusal-out` and with identical best-effort semantics (an unwritable path is
  a warning; the exit code still carries the decision). One new
  `_build_completion(result, *, ref, attempt, claim_context, exit_code)` helper,
  called at the same places that already decide the outcome — the `implemented`
  arm (`:3299-3312`), `_mark_needs_triage` (`:2772`), the refusal arm
  (`:3710-3724`) and `_review_feedback_exit_code` (`:520`). Without the flag,
  behaviour is byte-identical to today.
- **`orchestrator/temporal/activities/state.py`**: `ExecutionRecord` gains
  trailing, defaulted `attempt_id: str = ""` and `completion: dict | None = None`
  (the same trailing-default convention `BatchOutcome.blocked` uses), posted as
  optional JSON keys. mctl-api ignoring unknown keys is the expected transition
  state; the server-side read model is a separate mctl-api issue.
- **`.status.yaml` projection**: one bounded block beside the existing `attempt`,
  carrying `{api_version, completion_id, content_hash, outcome,
  attempt_id, stop_reason_code, verification: {passed, failed, unknown,
  required_failed}}` and an explicit `# derived, not authoritative` marker. No
  timings, no token counts, no log excerpts — the Git/Temporal boundary the issue
  names stays where it is. Written through the existing
  `update_status_yaml`/`_status_is_still_ours` compare-and-swap, so an ending
  attempt cannot stamp a projection over a live successor's block.
- **`run_shepherd.py`**: `followup_kind_for(outcome, stop_reason_code) ->
  FollowupKind` ships next to `_followup_code_sets()`, and a test asserts it
  agrees with the current exit-code classification for every code in the
  vocabulary. The shepherd is *not* rewired to prefer the document in this
  proposal — the equivalence test is the evidence that rewiring later is a no-op.
- **ADR-012** (`docs/adr/012-implementation-completion-contract.md`) records the
  decision, the boundary table and, in as many words, that this is an
  implementer-phase completion contract — not an independent review verdict, not
  another DevLoop.

## Alternatives

**A. Widen the exit-code vocabulary and keep it as the contract.** Cheapest, and
the shepherd already knows how to read it. Rejected: an exit status is 8 bits
with no room to bind attempt identity, head SHA, approved-scope hash or
verification, which is most of what the issue asks for; it is only produced in
`--review-feedback` mode; and it forces every consumer to keep a private copy of
the semantic map, which is the duplication that produced
`_followup_code_sets` / `_refusal_codes` / `_fenced_codes` as three separate
sets in the first place.

**B. Extend the `.status.yaml` `failure: {code, stage, message}` block.** Also
cheap, and it is already durable and already read by the shepherd. Rejected on
two independent grounds. First, it inverts the boundary the issue explicitly
preserves: verification records and attempt correlation are runtime facts, and
putting them in gitops turns status files into telemetry. Second,
`proposal_state._write_status_atomic`'s own docstring records that the
read-modify-write is not exclusive (#354), so a richer payload there increases
the blast radius of a known lost-update race that ADR-010 deliberately routed
*around* rather than fixed.

**C. A nested implementation workflow with its own lifecycle owner.** A child
Temporal workflow per attempt would get durable state, retries and history for
free. Rejected: the issue forbids it in as many words, ADR-010's non-goals forbid
a second scheduler, and it would need a second admission path — which
mctl-agents#395 and ADR-008 D7 already settled as a task-queue slot limit, not a
lease. It would also make `implement_outcome.classify` a third opinion instead of
a cross-check.

**D. A generated schema (pydantic / protobuf / JSON Schema).** Better tooling,
cross-language consumers. Rejected: `tests/test_worker_isolation.py` pins the
Temporal worker's dependency surface, `context_snapshot.py` and
`temporal/issue_ref.py` both establish stdlib-only frozen dataclasses as the
convention for contracts that cross the worker/sandbox line, and a second
serialization framework for one document would be the disagreeing-convention risk
ADR-009 already warns about.

## Platform impact

**Migrations.** None. No database change ships here; the mctl-api column for the
completion payload is a separate issue, and until it exists the optional JSON key
is simply ignored by the server. The `.status.yaml` projection is additive and
preserved-by-default by `update_status_file`.

**Backward compatibility.** Every existing exit code, status value and shepherd
decision is unchanged. The module is inert on landing in the ADR-009 sense: it is
imported by tests, by the fixture generator, and by `run_implementer` only behind
the new `--completion-out` flag, which nothing passes yet. Existing
`ExecutionRecord` constructions keep working because the new fields are trailing
and defaulted.

**Resource impact.** One sealed JSON document per attempt (kilobytes, bounded by
`MAX_VERIFICATION_RECORDS`, `MAX_REMAINING_WORK`, `MAX_EVIDENCE_REFS` and the
per-field length caps), one sidecar write, and a few hundred bytes added to a
`.status.yaml`. No new network call, no new poll, no new timer.

**Risks and mitigations.**

- *Vocabulary drift between `outcome` and `FollowupKind`.* Mitigated by shipping
  one mapping function plus an equivalence test over the full exit-code
  vocabulary; a new exit code with no mapping fails the test.
- *A document produced by a fenced or superseded attempt being believed.*
  Mitigated by `staleness_of` + `effective_outcome`, by producing no document at
  all on the 48/49 arms, and by routing the projection write through the existing
  `_status_is_still_ours` compare-and-swap.
- *Evidence-shaped payload smuggling.* Mitigated by bounded `evidence_ref` /
  `message` / `note` lengths validated at `seal()` and `from_dict`, following
  `context_snapshot`'s `MAX_LOCATOR_LENGTH` / `MAX_SELECTOR_JSON_LENGTH`
  precedent, and by a test that a long payload raises rather than truncates.
- *A consumer reading `complete` as an approval.* Mitigated by the field-name
  test, the mutation test, and the ADR stating the boundary in the first
  paragraph.
- *`proposal_content_hash` churn.* Hashing only the approved scope files in
  sorted order keeps the hash stable against unrelated proposal-directory
  additions; the open question in `requirements.md` records the choice.
