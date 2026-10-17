# Design: issue-428-architecture-implementer-define-bounded

## Current state

**One implementer attempt, two entry points.** `orchestrator/run_implementer.py` (5281
lines) has two entry points:
- `_implement_one` (line ~4076): the first implementation. It runs as Argo CWFT
  `mctl-agents-implement`, step `run-implementer`.
- `_review_feedback_one` (line ~2831): `--review-feedback`, called by the shepherd as a
  subprocess.

Each attempt gets a deterministic id from `_resolve_attempt_id` (`WORKFLOW_UID`, or
`sha256(service|slug|owner_epoch|ordinal|HOSTNAME)`). The id is stamped into
`.status.yaml` as `attempt: {id, started_at, expires_at}`, with a 130-minute lease
(`IMPLEMENT_ATTEMPT_LEASE`). An ADR-010 `ExecutionClaim` is held through `_ClaimContext`
(`claim_id`, `entity`, `phase`, `owner_epoch`, `entity_version`, `executor`, `attempt`)
and checked before each push by `_check_claim_or_raise`. `_status_is_still_ours` guards
status writes against a newer attempt.

**How an attempt ends today.** The end is spread over several unversioned channels:
- **`.status.yaml`** (via `update_status_yaml` / `proposal_state.update_status_file`):
  - `implemented` + `pr` + `attempt.finished_at` + an ADR-011 `execution:` annotation
    (`context_id`, `trace_id`, `agent`, `version`), at step "8. Mark implemented"
    (~line 4544);
  - otherwise `_mark_needs_triage(code, stage, message)`, `_mark_blocked`,
    `_mark_rate_limited`, or budget / policy hand-backs (`budget_handbacks`,
    `policy_handbacks`).

  The file reaches gitops main through the CWFT's `changes` artifact (`/tmp/state-out`,
  S3 key `{{workflow.name}}/agents-state.tgz`), which `commit-and-push` commits under the
  `mctl-gitops-main-writes` mutex.
- **Exit codes** (lines 236-342): `EXIT_OK`, 42 `NO_FOLLOWUP_COMMITS`, 43
  `BRANCH_MISSING_ON_ORIGIN`, 44 `OPERATION_TIMEOUT`, 45 `BLOCKED_ONLY`, 46
  `ORPHANED_SUBAGENT`, 47 `DELIBERATE_NO_OP`, 48 `FENCED`, 49 `CLAIM_REFUSED`, 50
  `CI_EVIDENCE_INSUFFICIENT`, 51 `VERIFICATION_BUDGET_EXHAUSTED`, 52 `RATE_LIMITED`, 53
  `POLICY_REFUSED`, 54 `POLICY_UNDECIDED`. `_review_feedback_exit_code` maps from
  error-string prefixes (`"deliberate no-op:"`, `"fenced:"`, ...).
- **`--refusal-out` JSON** (`_write_refusal_out`, `_write_verification_budget_exhausted_out`):
  `{refused, reason, [verification_budget_exhausted, ledger counts]}`. Best effort.
- **Agent-authored marker** `.implementer-refusal.json` (`RefusalMarker`), validated by
  `_read_refusal_marker`: it must be untracked and bounded to 64 KiB.

**How consumers interpret it.**
- **Shepherd** (`orchestrator/run_shepherd.py`): `_followup_exit_codes()` returns
  `(deterministic, harness)` code sets, and `FollowupSubprocessError.kind` is one of
  `transient | deterministic | harness | refused | fenced`. That kind decides whether
  `review_attempts` or `harness_failures` (`MAX_HARNESS_FAILURES = 3`) is charged.
  `_read_refusal_reason` reads `--refusal-out`.
- **Temporal** (`orchestrator/temporal/workflows/dev_loop.py` `_implement`, ~line 4140):
  `classify()` from `orchestrator/temporal/implement_outcome.py` turns Argo's node graph
  into `pre_start | execution | finalization | success`. `success` only means the Argo
  workflow succeeded. `_record` then calls `record_execution`
  (`orchestrator/temporal/activities/state.py`). `ExecutionRecord` carries `outcome` and
  `pre_start_reason` as optional wire keys and retries once without them on a 4xx. The
  same pattern is used in `implement_sweep.py`.
- `read_proposal_status` (`orchestrator/temporal/activities/proposals.py`) already reads
  `.status.yaml` from GitHub, so Temporal does not need a checkout.

**Contract-module precedents.** Sealed, versioned, frozen-dataclass modules with
`from_dict` that rejects unknown keys and a `sha256:` content hash:
- `orchestrator/context_snapshot.py` (ADR 009);
- `orchestrator/execution_identity.py` (ADR 011, `identity.mctl.ai/v1alpha1`);
- `orchestrator/execution_evidence.py` (ADR 018, `evidence.mctl.ai/v1alpha1`). Its
  `Outcome.code` set is `succeeded | failed | refused | abandoned | superseded`, and
  `EvidenceRef` is `{evidence_id, kind}` only.

ADR 011 (execution budget) records the #411/#418/#423/#430 invariants this design must
reuse.

**Deployed state checked:**
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`:
  - steps `implement` → `implement-fallback` → `commit` → `assert-produced`;
  - no `outputs.parameters` anywhere, deliberately (#530/#531, gitops#1186);
  - the only output is the `changes` artifact (`/tmp/state-out`);
  - `activeDeadlineSeconds: 7200` on `run-implementer`;
  - inputs include `work_item_id`, `execution_id`, `temporal_workflow_id`,
    `temporal_run_id`, `execution_request_id`, `traceparent`.

  Conclusion: a new Argo output parameter is the wrong carrier, and `.status.yaml` via
  the existing artifact is the right one.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-implement/values.yaml`: the
  admission worker (#395), `replicaCount: 1` as an architectural invariant. It is not
  affected by this proposal.
- I did not call the mctl MCP tools: the change is code-only, with no deployed config to
  verify. mctl-api's `/api/v1/agents/executions` handler was not inspected; the claim in
  `state.py` that it drops unknown keys is taken from the clone. See Open questions.

## Proposed solution

### 1. New inert schema module: `orchestrator/implementation_completion.py`

Modelled on `execution_evidence.py`: frozen dataclasses, `to_dict` / `from_dict` with
unknown-key rejection, bounded leaves, `seal()` as the only constructor that fills
identity.

```
ImplementationCompletion
  api_version   "completion.mctl.ai/v1alpha1"
  kind          "ImplementationCompletion"
  completion_id "ic-" + content_hash[7:23]        (derived)
  content_hash  sha256 over canonical JSON minus created_at/completion_id/content_hash
  created_at    ISO-8601 Z (excluded from hash)
  subject       {service, slug, work_item_id?}
  attempt       {attempt_id, phase: implement|review-remediation, ordinal?,
                 execution_id? (we_), context_id? (ex-), claim_id?, owner_epoch?}
  source        {repository, base_ref, base_sha?, branch, head_sha?}   (40/64-hex)
  proposal      {proposal_digest (sha256: over requirements/design/tasks bytes),
                 review_bundle_digest? (sha256: of the --review-feedback bundle)}
  outcome       complete | incomplete | bounded_refusal | budget_exhausted
                | deterministic_failure | harness_failure
  stop_reason   {code: closed set, detail?: <=600 chars, redacted}
  verification  [<=32] {check_id, result: pass|fail|unknown|not_run,
                        classification: exit_zero|exit_nonzero|timeout|budget_denied|
                                        not_applicable|observation_failed,
                        required: bool, evidence_ref?: {evidence_id, kind}}
  remaining_work [<=32] {item_id (e.g. "task-3"), summary <=256 chars, redacted}
  evidence_refs [<=32] {evidence_id, kind}
```

Construction invariants, enforced in `__post_init__`:
- `complete` requires a `head_sha`, every `required` verification at `pass`, and empty
  `remaining_work`.
- `incomplete` requires non-empty `remaining_work`.

There is deliberately no field for approval, review verdict, merge, release, ownership,
claim extension or budget, so `from_dict` rejects all of them as unknown keys. The module
docstring and ADR 021 state that `complete` means only "the implementer believes the
approved scope is ready for independent review".

`stop_reason.code` closed set, with the mapping from today's arms:

| Today's signal | outcome | stop_reason.code |
| --- | --- | --- |
| `implemented` write / `EXIT_OK` with a new head | complete | `scope_done` |
| marker with new optional `remaining` list | incomplete | `known_work_remains` |
| 47 `DELIBERATE_NO_OP` | bounded_refusal | `deliberate_no_op` |
| 50 `CI_EVIDENCE_INSUFFICIENT` | bounded_refusal | `evidence_insufficient` |
| 53 `POLICY_REFUSED` | bounded_refusal | `policy_refused` |
| 51 `VERIFICATION_BUDGET_EXHAUSTED` / budget hand-back | budget_exhausted | `verification_budget` |
| 44 `OPERATION_TIMEOUT` | budget_exhausted | `operation_timeout` |
| 52 `RATE_LIMITED` | budget_exhausted | `rate_limited` |
| 42 `NO_FOLLOWUP_COMMITS` / no commits | deterministic_failure | `no_commits` |
| 43 `BRANCH_MISSING_ON_ORIGIN` | deterministic_failure | `branch_missing` |
| `needs-triage` policy arms (chart guard, stale source) | deterministic_failure | `policy_gate` / `stale_source` |
| 46 `ORPHANED_SUBAGENT` | harness_failure | `orphaned_subagent` |
| 48 `FENCED` | harness_failure | `fenced` |
| 49 `CLAIM_REFUSED` | harness_failure | `claim_refused` |
| 54 `POLICY_UNDECIDED` | harness_failure | `policy_undecided` |
| 1 generic / unexpected exception | harness_failure | `unexpected_error` |

`pre_start` attempts never start the implementer, so they produce no completion. That is
the #418 semantics: no attempt is counted and no record exists. The Argo-level
`finalization` class (commit-and-push failed after the implementer succeeded) is likewise
observed by Temporal, not by the implementer. A completion from such an attempt may say
`complete` while Temporal says `finalization`. That combination is legible and
intentional: the implementer finished, the platform lost the record.

### 2. Emission in `run_implementer.py`

- Add a pure function, `completion_from_result(result | exit_code, *, ctx, observed) ->
  ImplementationCompletion`, that encodes the table above. This one function is the only
  mapping; the exit-code helpers stay unchanged.
- Add `_AttemptObservations`, collected during the run:
  - `base_sha` / `head_sha` (`_capture_head_sha`, `_remote_head_sha`);
  - `proposal_digest`, computed at attempt start next to the `attempt = {...}` dict
    (~line 4336) by hashing the proposal directory's three files in sorted order;
  - `review_bundle_digest`, from `_load_review_feedback`;
  - verification records from orchestrator-observable checks: `commits_present`
    (`_has_new_commits`), `chart_major_guard` (`_detect_chart_major_bumps`),
    `push_succeeded`, `claim_valid_at_push`. Optional agent commands are taken from
    `CommandBudgetLedger` entries, as non-required records with an exit classification
    only and no output.
- Wire one `try/finally` emission point in `_implement_one` and `_review_feedback_one`,
  after claim acquisition. It seals the completion once. It does two things:
  - projects it into `.status.yaml` through `update_status_yaml(..., completion=...)` on
    the arms that already write status;
  - in review-feedback mode, writes the full record to `--completion-out` (new argparse
    flag; best effort and bounded, mirroring `_write_refusal_out`).
- `.status.yaml` projection (durable result, not telemetry):

  ```yaml
  completion:
    api_version: completion.mctl.ai/v1alpha1
    completion_id: ic-...
    content_hash: sha256:...
    attempt_id: ...
    outcome: complete
    stop_reason: scope_done
    head_sha: ...
    verification: {required_passed: 3, required_total: 3, optional_total: 2}
  ```

  The full verification list is not written to git. It travels through `--completion-out`
  and, later, the mctl-api read model.
- **Replay guard.** The projection write goes through `_status_is_still_ours(ref,
  attempt_id)` and a new `_completion_write_allowed(existing, new)`:
  - same `attempt_id` and same `completion_id`: no-op;
  - same `attempt_id` and a different id: refuse and log;
  - a different (newer) `attempt_id` already present: refuse, because this attempt is
    stale.

  A Temporal or Argo retry that reuses `WORKFLOW_UID` therefore cannot flip a recorded
  `harness_failure` / `budget_exhausted` into `complete`. Only a new attempt identity
  can.
- **Stale claim.** If `_check_claim_or_raise` raises at the emission point, no projection
  is written. The record still goes to `--completion-out` as `harness_failure` / `fenced`
  or `claim_refused`, so the shepherd sees the same thing it sees today.

### 3. Shepherd consumption (`run_shepherd.py`)

The shepherd passes `--completion-out <tmp>` next to `--refusal-out`. A new helper,
`_read_completion(path, expected_attempt_id)`, runs a bounded read and `from_dict`. It
returns `None` when:
- the file is absent, invalid or oversize;
- the `attempt_id` does not match the attempt the shepherd started. The shepherd sets
  `WORKFLOW_UID`-derived identity, or reads `attempt.id` back from status.

The kind is then derived with `_followup_kind_from_completion(c)`:

| completion | FollowupKind |
| --- | --- |
| `complete` | (success path) |
| `bounded_refusal` | `refused` |
| `harness_failure` + `fenced` / `claim_refused` | `fenced` |
| other `harness_failure` and `budget_exhausted` (except `rate_limited`) | `harness` |
| `rate_limited` | existing rate-limited handling |
| `deterministic_failure`, `incomplete` | `deterministic` |

If the completion is `None`, or the completion-derived kind disagrees with
`_followup_exit_codes()`'s class for the exit code, the exit-code class wins and a
`completion-disagreement` warning is printed. This rolls out as observe-then-trust:
shadow first, so no charging behaviour changes until the mapping is proven. A flag
`SHEPHERD_TRUST_COMPLETION` (default off) switches the source of truth.

### 4. Temporal / execution record

- `ExecutionRecord` gains optional `completion_id`, `completion_outcome` and
  `completion_stop_reason` (default `""`). `record_execution` adds them to the existing
  `optional` dict, so the retry-without-optional-keys path covers an mctl-api that rejects
  them.
- In `dev_loop._implement` and `implement_sweep`, after `_run_cwft` returns an outcome of
  `success` or `finalization`, a new read-only activity, `read_proposal_completion(service,
  slug)`, reads the `completion` block over HTTP. It is a sibling of
  `read_proposal_status` in `activities/proposals.py`. If the block's `attempt_id` does
  not equal the Argo workflow's UID, it is treated as absent: stale fails closed.
- The result is stored on `ImplementExecutionState` (`completion_outcome`) and passed to
  `_record`. The call is gated by `workflow.patched("implement-completion")` for replay
  safety. There is **no control-flow change**: `success` still returns. The new data is
  observational, like `pre_start_reason` was in #418.

### 5. Documentation

`docs/adr/021-implementation-completion-contract.md` records:
- the scope ("implementer-phase completion contract; not a review verdict, not approval,
  not a DevLoop");
- the outcome and stop-reason tables;
- the replay rules;
- the carrier boundary (git = durable result projection; Temporal / Argo = runtime;
  mctl-api = read model);
- the explicit non-authorities list.

`docs/temporal-flow.md` gets a short pointer.

## Alternatives

1. **Extend the exit-code table and `--refusal-out` JSON.** This is the cheapest option,
   but exit codes cannot carry the attempt, claim, head or digest bindings. The
   `--refusal-out` JSON is unversioned and only exists for review-feedback mode. It would
   keep growing the parallel tables in `_review_feedback_exit_code` and
   `_followup_exit_codes`, which are the very drift the issue complains about. Dropped.
2. **Reuse `ExecutionEvidence` (ADR 018) with an implementer-specific `Outcome`.** The
   envelope is a join of canonical records with a 5-value outcome shared by every agent.
   Widening that set or overloading `reason_code` would leak implementer semantics into a
   cross-agent contract, and Tier B storage does not exist yet. Instead the completion is
   its own small contract, and it can be referenced from an `ExecutionEvidence` via
   `ArtifactRef` (`kind: implementation-completion`, `content_hash`). Dropped as the
   primary carrier, kept as the join point.
3. **Publish the completion as an Argo output parameter, or a new S3 artifact that
   Temporal reads.** The CWFT explicitly forbids `outputs.parameters` (#530/#531,
   gitops#1186). A new artifact would need a cross-repo CWFT change plus S3 read access
   in the worker. The existing `changes` artifact → `.status.yaml` → `read_proposal_status`
   path already exists and stays inside the git = durable-result boundary. Dropped.
4. **Let the agent write the completion itself.** Model-authored self-certification is
   what the lifecycle boundary forbids. The orchestrator builds the record from observed
   facts. The agent's only input remains the validated, untracked marker. Dropped.

## Platform impact

- **Migrations:** none. `.status.yaml` gains an optional `completion:` key. Readers that
  do not know it ignore it (`proposal_state.load_status` returns a dict, and
  `gitops_state._parse_status_yaml` reads named keys only). Old proposals simply lack it.
- **Backward compatibility:**
  - Exit codes, `--refusal-out` and status transitions are unchanged.
  - A shepherd running an older implementer image gets no `--completion-out` file and
    falls back to exit codes. A newer implementer called by an older shepherd ignores the
    missing flag.
  - `record_execution` optional keys degrade via the existing 4xx retry.
  - Temporal changes sit behind `workflow.patched("implement-completion")`, so in-flight
    DevLoops replay unchanged. Pinned by the replay fixtures in
    `tests/fixtures/histories/`.
- **Resource impact:** one sha256 over three small files and one extra GitHub contents
  read per implement step. Negligible.
- **Risks and mitigations:**
  - *Mis-mapping charges the wrong counter.* The shepherd stays on exit codes until
    `SHEPHERD_TRUST_COMPLETION` is enabled, logs disagreements, and a test pins every
    exit code against the table.
  - *Private content leaks via `detail` / `summary`.* These fields are bounded,
    redacted, and there is no stdout/stderr field. The schema test asserts the absence of
    the forbidden keys.
  - *`complete` read as review-clean.* It is enforced by schema absence plus ADR wording.
    The shepherd's merge decision never reads `outcome`.
  - *Stale-attempt overwrite.* Guarded by the `_status_is_still_ours` and
    completion-write rules, and covered by tests.
  - *Status-write ordering.* The projection is written in the same `update_status_yaml`
    call as the existing transition, so no extra commit and no partial state is
    possible.

## Open questions

- No approved-content digest exists in `proposal_state.py`. `proposal_digest` is computed
  at attempt start. Should it later bind to an approval-time digest and fail closed on a
  mismatch?
- Which verification checks are "required" per service is undefined. v1alpha1 treats
  only orchestrator-side gates as required.
- `incomplete` needs a new optional `remaining` list in `.implementer-refusal.json`. Is
  that extension acceptable, or should `incomplete` stay reserved?
- mctl-api's `/api/v1/agents/executions` decoder was not inspected from here. Persisting
  the new optional fields is a cross-repo follow-up.
