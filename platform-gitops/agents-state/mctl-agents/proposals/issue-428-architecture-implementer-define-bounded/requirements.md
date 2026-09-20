# Bounded implementation completion and handoff contract for the implementer phase

## Context

Tier 2 today ends an implementation attempt through three unrelated, partly
private channels: a process exit code (`orchestrator/run_implementer.py:191-256`
— `EXIT_OK`, `EXIT_NO_FOLLOWUP_COMMITS`, `EXIT_OPERATION_TIMEOUT`,
`EXIT_ORPHANED_SUBAGENT`, `EXIT_DELIBERATE_NO_OP`, `EXIT_FENCED`,
`EXIT_CLAIM_REFUSED`, `EXIT_CI_EVIDENCE_INSUFFICIENT`), a `.status.yaml` flip to
`implemented` / `needs-triage` carrying an untyped `failure: {code, stage,
message}` block (`run_implementer._mark_needs_triage`, `:2772`), and an advisory
`--refusal-out` sidecar carrying `{refused, reason}`
(`run_implementer._write_refusal_out`, `:444`). None of those is bound to the
attempt identity, the head SHA the attempt was pinned to, the approved
requirements/tasks it was supposed to satisfy, or the verification it actually
ran. The Temporal side reconstructs a fourth, independent answer from Argo's node
graph (`orchestrator/temporal/implement_outcome.py` — `observe_implementer`,
`classify` returning `pre_start | execution | finalization | success`), and the
durable audit row records only `phase: Succeeded | Failed | Error`
(`orchestrator/temporal/activities/state.py:29-44`, `ExecutionRecord`). The
shepherd is left re-deriving intent from exit codes in prose
(`orchestrator/run_shepherd.py:655-776`, `FollowupKind = Literal["transient",
"deterministic", "harness", "refused", "fenced"]` at `:702`).

The practical consequence is that "a PR exists" reads as "implementation
complete". This proposal defines a versioned, replay-safe
`ImplementationCompletion` document that the existing implementer phase emits for
one attempt, so every downstream consumer can tell a finished implementation from
a bounded refusal, an exhausted envelope, a deterministic failure and a lost
harness without parsing model text. It creates no new lifecycle owner, no nested
DevLoop, and no second admission or timeout mechanism: it reuses ADR-010's
ownership/claim identity, ADR-011's execution envelope, and the boundary that Git
stores durable lifecycle/result state while Temporal/Argo own runtime state. It
follows the precedent of ADR-009 / `orchestrator/context_snapshot.py`: an
architecture-first, stdlib-only, inert, content-hashed schema module landed
before any consumer is switched over to it.

## User stories

- AS the Tier 3 shepherd I WANT a typed terminal outcome for the implementer
  attempt I just ran SO THAT I can choose between charging a review attempt,
  waiting, and escalating without inferring intent from an exit code or from
  agent prose.
- AS a DevLoop execution consumer (`record_execution`, future mctl-api read
  models and FinOps attribution) I WANT the attempt's outcome, identity and
  verification summary on the durable execution record SO THAT "which attempt
  produced this PR, and did it finish" is answerable without re-querying Argo,
  whose workflow objects expire.
- AS an operator triaging a wedged proposal I WANT to see whether the implementer
  stopped with known work remaining, refused on insufficient evidence, or was cut
  off by its own envelope SO THAT I know whether to re-run, widen the envelope, or
  fix the proposal.
- AS a platform maintainer I WANT the contract to be provably unable to express
  an approval, a review verdict, a merge or an ownership change SO THAT a future
  consumer cannot read a self-check as authorization, which is the exact mistake
  ADR-010 §6 records for `merge_owner`.
- AS the DevLoop workflow I WANT the contract to be idempotent under Temporal
  retry, Argo pod restart and exporter redelivery SO THAT one attempt can never
  produce two disagreeing durable completion records.

## Acceptance criteria (EARS)

Schema and vocabulary

- WHEN a producer seals an `ImplementationCompletion` THE SYSTEM SHALL emit a
  frozen document carrying `api_version = "implementation.mctl.ai/v1alpha1"`,
  `kind = "ImplementationCompletion"`, a derived `completion_id`, and a
  `sha256:`-prefixed `content_hash` computed over every field except
  `created_at`, using the hashing and canonical-JSON rules already published by
  `orchestrator/context_snapshot.hash_bytes` / `canonical_json`.
- WHEN a document declares an `api_version` or `kind` outside the supported
  allow-list THE SYSTEM SHALL raise `ImplementationCompletionError` and SHALL NOT
  fall back to a default shape, mirroring `context_snapshot.from_dict` and
  `orchestrator/manifest.py`'s `SUPPORTED_API_VERSIONS`.
- WHEN an outcome is set THE SYSTEM SHALL accept exactly one member of the closed
  vocabulary `complete`, `incomplete`, `bounded_refusal`, `budget_exhausted`,
  `deterministic_failure`, `harness_failure`, and SHALL reject any other value.
- WHILE a document is valid THE SYSTEM SHALL bind it to the WorkItem identity
  (`service`, `slug`, the `agents-state` proposal path, and an immutable
  `proposal_content_hash` over the approved `requirements.md` / `design.md` /
  `tasks.md`), the attempt identity (`attempt_id` as produced by
  `run_implementer._resolve_attempt_id`, `attempt_ordinal`, `owner_epoch`,
  `claim_id`, executor type/id), the runtime correlation (`argo_workflow_name`,
  `temporal_workflow_id`, `temporal_run_id`), and the source identity
  (`repo`, `base_branch`, `base_sha`, `head_branch`, `head_sha`, `pr_url`).
- WHEN identity fields are unavailable in the running environment THE SYSTEM
  SHALL record them as explicit empty/`null` values and SHALL NOT substitute a
  random or wall-clock-derived value, per ADR-010 §8's refusal of the
  `uuid.uuid4()` attempt-id fallback.

Verification evidence

- WHEN verification was performed THE SYSTEM SHALL record it as a bounded list of
  `VerificationRecord` entries carrying `check_id`, `result` in
  `pass | fail | unknown`, a `classification` slug, a bounded `evidence_ref`, and
  a `required_for_completion` flag.
- IF the number of verification records exceeds `MAX_VERIFICATION_RECORDS` or an
  `evidence_ref` exceeds `MAX_EVIDENCE_REF_LENGTH` THEN THE SYSTEM SHALL raise
  `ImplementationCompletionError` rather than truncate silently.
- WHILE any verification record has `required_for_completion = true` and
  `result != "pass"` THE SYSTEM SHALL reject `outcome = "complete"` as invalid.
- THE SYSTEM SHALL NOT persist prompts, completions, raw stdout/stderr, diffs or
  any other private model payload in the document; only references
  (a check id, a run URL, an evidence id) are permitted, and a validator SHALL
  enforce the length bounds that make a payload unsmuggleable.

Stop reason and remaining work

- WHEN an attempt ends with any outcome other than `complete` THE SYSTEM SHALL
  carry a structured `stop_reason` with a `code` from a closed vocabulary, a
  bounded human `message`, and the `exit_code` the implementer process used, so
  the existing sentinel codes remain the machine-readable join key.
- WHEN an attempt ends `incomplete` THE SYSTEM SHALL carry at least one
  `remaining_work` entry referencing an approved task by its `tasks.md` ordinal,
  with a bounded note.
- IF `outcome = "incomplete"` and `remaining_work` is empty THEN THE SYSTEM SHALL
  raise `ImplementationCompletionError`.

Lifecycle boundary

- THE SYSTEM SHALL contain no field expressing approval, independent review
  cleanliness, merge authority, release, ownership transfer, claim extension or
  budget extension, and a test SHALL assert that no field name in the module
  matches those concepts.
- WHILE `outcome = "complete"` THE SYSTEM SHALL mean only "the implementer
  believes the approved implementation scope is ready for independent review",
  and the documentation SHALL state that Claude/Agy review and required CI remain
  independent post-handoff gates.
- IF any consumer derives an authorization, a merge decision or an ownership
  change from a completion document THEN the design SHALL be considered violated;
  a mutation test SHALL flip the document to `complete` and assert that no
  approval, merge or ownership decision changes, mirroring ADR-010 §7's
  projection test.

Replay, retry and staleness

- WHEN the same attempt seals a completion more than once with identical content
  THE SYSTEM SHALL derive an identical `completion_id`, `content_hash` and
  `idempotency_key`, so redelivery collapses to one durable record.
- IF a second completion is offered for an `attempt_id` that already has a
  recorded completion with a different `outcome` THEN THE SYSTEM SHALL refuse it
  and SHALL require a new `attempt_id` for any different outcome.
- IF a prior recorded outcome is `budget_exhausted` or `harness_failure` and a
  replay presents `complete` under the same `attempt_id` THEN THE SYSTEM SHALL
  refuse the upgrade.
- WHEN a consumer validates a completion against the world it observes now
  (current head SHA, current claim verdict, current attempt block) and any of
  them disagrees with the document THE SYSTEM SHALL classify the document as
  stale and SHALL read it as non-complete, never as `complete`.
- IF no completion document is available at all THEN THE SYSTEM SHALL fall back
  to the existing exit-code and Argo-node classification
  (`run_shepherd._followup_code_sets`, `implement_outcome.classify`) and SHALL
  NOT synthesize `complete`.
- WHEN the Argo-derived outcome and the document disagree THE SYSTEM SHALL
  resolve to the non-complete side.

Integration

- WHEN `run_implementer.py` is invoked with `--completion-out <path>` THE SYSTEM
  SHALL write one sealed document to that path, using the same best-effort write
  discipline as `_write_refusal_out` so an unwritable path degrades to a warning
  and never changes the exit code.
- WHILE no `--completion-out` is passed THE SYSTEM SHALL behave exactly as today;
  every existing exit code, status flip and shepherd decision SHALL be unchanged
  by this proposal.
- WHEN `ExecutionRecord` is constructed THE SYSTEM SHALL accept an optional,
  trailing, defaulted completion projection so existing call sites keep working
  unchanged.
- WHEN a completion projection is written to `.status.yaml` THE SYSTEM SHALL
  write a bounded, explicitly derived, non-authoritative block and SHALL NOT
  write runtime telemetry (timings, token counts, log excerpts) into gitops.

## Out of scope

- Any change to how many implementer runs may exist at once (admission remains
  ADR-008 D7 / mctl-agents#395), to the execution envelope itself (ADR-011 /
  mctl-agents#418), or to bounded evidence retrieval (mctl-agents#423).
- A second lifecycle owner, a nested DevLoop, a retry scheduler, or a new
  recovery mechanism. Recovery stays ADR-010 §5 plus `activities/stranded.py`.
- Changing the shepherd's decisions. The mapping from completion outcomes to
  `FollowupKind` ships and is tested for equivalence with the current exit-code
  classification; switching the shepherd to read it as primary is a follow-up.
- mctl-api schema/storage work for the execution read model and FinOps
  attribution. This proposal defines the payload and the optional field; the
  server side is a separate mctl-api issue.
- Making the implementer actually run verification it does not run today. The
  contract can express a verification record; producing more of them is future
  work.
- Migrating `orchestrator/temporal/implement_outcome.py` away. It stays as the
  platform's independent Argo-side observation and becomes the cross-check.

## Open questions

- Whether `proposal_content_hash` should cover the whole proposal directory or
  only `requirements.md` + `tasks.md` (the approved scope). Proceeding with: hash
  the approved scope files (`requirements.md`, `design.md`, `tasks.md`) in sorted
  order via `context_snapshot.canonical_json` over `{filename: sha256}`, so a
  design-only edit is still visible but no non-scope file can churn the hash.
- Where the durable completion record ultimately lives. ADR-010 §1 puts "who may
  act" in mctl-api Postgres and keeps "what the entity is" in Git. A completion
  is a result, not an ownership fact, so this proposal keeps the authoritative
  record on the execution audit trail (`record_execution`) with a bounded
  `.status.yaml` projection. If mctl-api later declines the field, the sidecar
  file plus the projection still satisfy the shepherd consumer.
- Whether `bounded_refusal` should be split into "refused on operator/design
  grounds" (`EXIT_DELIBERATE_NO_OP`) and "refused on insufficient evidence"
  (`EXIT_CI_EVIDENCE_INSUFFICIENT`). Proceeding with one outcome plus a
  distinguishing `stop_reason.code`, because the shepherd already treats them as
  two different kinds (`refused` vs `harness`) and the stop reason is where that
  divergence belongs; the equivalence test pins it.
- Whether `pre_start` (Argo accepted the workflow but no implementer pod ever
  ran) deserves its own outcome. Proceeding with: no document is produced at all
  in that case — by construction, since nothing ran to produce one — and the
  absence is read through the existing `classify()` path, which is exactly what
  `implement_outcome.py` was built for.
