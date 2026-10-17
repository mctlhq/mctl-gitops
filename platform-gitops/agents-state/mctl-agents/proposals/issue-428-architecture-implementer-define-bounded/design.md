# Design: issue-428-architecture-implementer-define-bounded

This is a revision of the 2026-10-17 proposal. It changes three things in response to the
owner review: (1) a primary / fallback authority rule, (2) a three-PR delivery split, and
(3) an honest statement of what `complete` means in v1alpha1. Everything else is unchanged:
observe-only in Temporal, the shepherd flag off by default, and no approval, review, merge
or ownership fields in the schema.

## Current state

**One implementer attempt, two entry points.** `orchestrator/run_implementer.py` has two
entry points:
- `_implement_one`: the first implementation. It runs as Argo CWFT `mctl-agents-implement`,
  template `run-implementer`.
- `_review_feedback_one`: `--review-feedback`, called by the shepherd as a subprocess.

**Attempt identity.** `_resolve_attempt_id` (line 1034) returns `WORKFLOW_UID` if it is
set. Otherwise it returns `sha256(service|slug|owner_epoch|ordinal|HOSTNAME)`.
`_implement_one` calls it with `owner_epoch=0, attempt_ordinal=0` (line 4289), after
`ensure_auth_for_sdk()` (line 4280, which raises `SystemExit` on failure, before any claim).
The id is stamped into `.status.yaml` as `attempt: {id, started_at, expires_at}` (130-minute
`IMPLEMENT_ATTEMPT_LEASE`). An ADR-010 `ExecutionClaim` is held through `_ClaimContext`,
acquired *before* the `in-progress` write, checked before each push by
`_check_claim_or_raise`, and released on every ending arm (`_release_claim`, lines 3729,
4481, 4572, 4621, 4638, 4698, 4762). `_status_is_still_ours` (line 1407) guards status
writes against a newer attempt.

**The primary / fallback pair.** In the deployed CWFT the `implement-proposals` steps
template runs:
1. `implement` (`is-fallback: "false"`, token `claude-code-oauth-token`), with
   `continueOn: {failed, error}`;
2. `implement-fallback` (`is-fallback: "true"`, token `claude-code-oauth-token-2`), with
   `when: "{{steps.implement.status}} != Succeeded"`;
3. `commit` (`commit-and-push`);
4. `assert-produced`, which succeeds if either step succeeded.

Both steps run the same `run-implementer` template. Facts that matter for this design:
- They are separate pods, each with its own fresh gitops clone. Because `commit-and-push`
  runs only after both, **the fallback's clone cannot see anything the primary wrote**.
- Both upload the `changes` artifact (`/tmp/state-out`) to the same literal S3 key,
  `{{workflow.name}}/agents-state.tgz`. The CWFT comment says: "when both run the fallback
  goes second and wins". An attempt that produced nothing uploads nothing and "leaves a
  previous attempt's object intact".
- If token-2 is unset, the shell prelude exits 1 before Python starts. If token-2 is set
  but unusable, `ensure_auth_for_sdk` raises before the claim. In both cases the fallback
  produces no status write and the primary's artifact survives.
- When the fallback gets past auth, it runs a full attempt. Typical endings on this
  platform are `rate_limited`, a claim refusal, or another harness error, which
  `_mark_*` writes into the fallback's `.status.yaml`. That file then overwrites the
  primary's in the shared artifact.
- The CWFT sets `WORKFLOW_NAME`, `ARGO_WORKFLOW_NAME` and `IS_FALLBACK` in the pod env. It
  does **not** set `WORKFLOW_UID`. So in the deployed shape the two steps derive
  *different* `attempt_id`s, because their `HOSTNAME`s (pod names) differ. In a shape that
  sets `WORKFLOW_UID` (the docstring assumes "the Temporal path always sets" it) they
  would derive the *same* id, as the owner review describes. Either way, `attempt_id`
  alone cannot say which step a record came from. This design binds the step explicitly.

**How an attempt ends today.** The end is spread over unversioned channels:
- `.status.yaml` via `update_status_yaml` (line 1381): `implemented` + `pr` +
  `attempt.finished_at` + an ADR-011 `execution:` annotation, or `_mark_needs_triage`
  (line 3689), `_mark_blocked`, `_mark_rate_limited`, or budget / policy hand-backs;
- exit codes 0, 1, 42-54 (`EXIT_NO_FOLLOWUP_COMMITS` ... `EXIT_POLICY_UNDECIDED`), with
  `_review_feedback_exit_code` mapping error-string prefixes;
- the `--refusal-out` JSON (`_write_refusal_out`, line 551);
- the agent-authored marker `.implementer-refusal.json` (`RefusalMarker`, line 392,
  validated by `_read_refusal_marker`, line 416).

**How consumers interpret it.**
- Shepherd (`orchestrator/run_shepherd.py`): `_followup_exit_codes()` returns
  `(deterministic, harness)` code sets. `FollowupSubprocessError.kind` decides whether
  `review_attempts` or `harness_failures` is charged.
- Temporal (`orchestrator/temporal/workflows/dev_loop.py` `_implement`): `classify()` from
  `orchestrator/temporal/implement_outcome.py` maps the Argo node graph to `pre_start |
  execution | finalization | success`. `_record` then calls `record_execution`
  (`orchestrator/temporal/activities/state.py`, `ExecutionRecord`, with optional wire keys
  and a 4xx retry without them). Temporal knows the Argo `result.workflow_name` and
  already sends it as `argo_workflow_name`.
- `read_proposal_status` (`orchestrator/temporal/activities/proposals.py`) already reads
  `.status.yaml` over HTTP.

**Contract-module precedents.** `orchestrator/context_snapshot.py` (ADR 009),
`orchestrator/execution_identity.py`, and `orchestrator/execution_evidence.py` (ADR 018,
`evidence.mctl.ai/v1alpha1`, `EvidenceRef = {evidence_id, kind}`). The newest ADR is
`docs/adr/020-capability-commerce-contract.md`, so the next number is 021.

**Deployed state checked:**
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`:
  - the steps and their `when` / `continueOn` are as described above;
  - the shared artifact key is `{{workflow.name}}/agents-state.tgz`, with "fallback goes
    second and wins";
  - the `IS_FALLBACK` shell prelude exits 1 when token-2 is unset;
  - there is no `WORKFLOW_UID` env for `run-implementer`. A grep of `argo-workflows/`
    finds `WORKFLOW_UID` only in `cwft-argo-local-workdir-canary.yaml`;
  - `WORKFLOW_NAME` is set to `{{workflow.name}}`;
  - there are no `outputs.parameters` (deliberate);
  - `activeDeadlineSeconds: 7200` on `run-implementer`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-implement/`: exists (the #395
  admission worker). Not affected.
- mctl MCP tools: not called. This change is code plus one optional CWFT input; no
  runtime config needs to be observed. mctl-api's `/api/v1/agents/executions` decoder was
  not inspected (see Open questions).
- Not observed: whether token-2 is currently seeded in production. The owner review says
  the fallback "has no working second account". The design covers both the seeded and
  unseeded cases.

## Proposed solution

### 1. Inert schema module: `orchestrator/implementation_completion.py` (PR 1)

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

- `run_id` and `step` are part of the hashed content. The primary and fallback records of
  one Argo run therefore always have distinct `completion_id`s, even under the
  `WORKFLOW_UID` shape where `attempt_id`s coincide. `step` comes from `IS_FALLBACK`
  (`"true"` → `fallback`, anything else → `primary`). The review-feedback mode, which the
  shepherd runs as a subprocess, is always `primary`, and `run_id` is the shepherd's own
  Argo workflow name.
- **Invariants.** `complete` requires a `head_sha`, every `required` check at `pass`, and
  empty `remaining_work`. `incomplete` requires non-empty `remaining_work`. There are no
  fields for approval, review verdict, merge, release, ownership, claim extension or
  budget.
- **What `complete` means in v1alpha1 (owner review point 3).** The required set is
  exactly the orchestrator-side gates: `commits_present` (`_has_new_commits`),
  `chart_major_guard` (`_detect_chart_major_bumps`), `push_succeeded`, and
  `claim_valid_at_push`. Nothing compares the pushed head with the approved `tasks.md`.
  The module docstring, ADR 021, and the stop-reason code all say so:
  - `complete` / `gates_passed` means "the attempt pushed a head that passed the
    orchestrator gates";
  - it does not mean "the approved scope is implemented", and it is not a review verdict.

  Task-coverage verification is recorded as follow-up **F1**: a future `task_coverage`
  check, which would become `required` in a later api version.

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
shell exit) produce no completion. The Argo `finalization` class remains Temporal's to
observe.

### 2. Emission and projection in `run_implementer.py` (PR 1)

- Add `completion_from_result(...)` (the table above) and `_AttemptObservations`
  (`base_sha` / `head_sha`, `proposal_digest` computed next to the `attempt = {...}` dict,
  `review_bundle_digest`, and the four required gate records plus non-required
  `CommandBudgetLedger` entries, classification only).
- Add one `try/finally` emission point after claim acquisition in `_implement_one` and
  `_review_feedback_one`. It seals once, projects into `.status.yaml` through
  `update_status_yaml(..., completion=...)` on the arms that already write status, and
  writes `--completion-out` (new flag, bounded, best effort, mirroring
  `_write_refusal_out`).
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

- **Replay guard.** The guard keys on `(run_id, step, attempt_id)`:
  - same key, same `completion_id`: no-op;
  - same key, different `completion_id`: refuse and log;
  - a different `run_id` whose `attempt.id` already owns the status: refuse
    (`_status_is_still_ours`).

  A pod restart or Argo retry inside one step therefore cannot flip `budget_exhausted` /
  `harness_failure` into `complete`. Only a new step or a new run can produce a new
  record, and the authority rule below decides between steps.
- **Stale claim.** If `_check_claim_or_raise` raises at emission, no projection is
  written. `--completion-out` still gets a `harness_failure` / `fenced` or `claim_refused`
  record.

### 3. Primary / fallback authority (PR 1; owner review point 1)

**Decision: within one Argo run, the primary record is authoritative unless the fallback
is `complete`.** A failing fallback never replaces the primary's outcome. A succeeding
fallback does replace it, and the primary's record is kept as a `superseded` summary. This
is the owner's second option ("never project a fallback completion over a primary one")
with one exception, for a fallback that actually produced a gated head. That exception
mirrors `assert-produced`, which already counts the run as produced if either step
succeeded.

`select_authoritative(primary: Summary | None, fallback: Completion) -> Projection` is a
pure function in `implementation_completion.py`:

| primary handoff | fallback outcome | authoritative | other |
| --- | --- | --- | --- |
| present, any outcome | `complete` | fallback | primary as `superseded` |
| present, any outcome | not `complete` | primary | fallback as `fallback` |
| absent (primary emitted nothing) | any | fallback, `primary_observed: false` | none |
| fallback never reached the claim | n/a (no record) | primary (artifact untouched) | none |

The primary step itself always writes `authoritative = own record`. It runs first and
never sees a fallback.

**Making the primary visible to the fallback.** The fallback's gitops clone predates the
primary's status, so the rule needs the primary's handoff. That handoff already exists:
it is the artifact at `{{workflow.name}}/agents-state.tgz`. One additive mctl-gitops change
gives `run-implementer` an *optional* input artifact at that same literal key, unpacked to
`/tmp/prior-state`:
- for the primary, nothing exists yet, so the input is skipped;
- for the fallback, it holds the primary's `.status.yaml`, if the primary wrote one.

The fallback reads only the `completion.authoritative` block from it (bounded read,
`from_dict`-validated summary). It accepts the block only if `run_id` equals its own
`WORKFLOW_NAME` and `step == primary`, so a stale object from another run fails closed to
"absent".

The status *transition* the fallback writes (for example `rate_limited` over the primary's
`needs-triage`) is unchanged existing behaviour and out of scope. Only the `completion:`
block follows the authority rule. ADR 021 states this explicitly, so that a reader knows
`completion.authoritative` (the attempt's result) and `status` (lifecycle state) may
legitimately differ after a failed fallback.

Until the CWFT input is deployed, `/tmp/prior-state` is absent and the fallback projects
with `primary_observed: false`. Consumers (PR 2 and PR 3) treat a
`step: fallback, primary_observed: false` non-`complete` record as "fallback result only,
primary outcome unknown" and never as the primary's outcome. The rule is pinned by tests
T3a and T3b, whatever the CWFT state.

### 4. Shepherd consumption, shadow mode (PR 2)

The shepherd passes `--completion-out <tmp>` next to `--refusal-out`. Review-feedback runs
are single-step subprocesses (no fallback pair), so the record is always `step: primary`.
`_read_completion(path, expected_run_id)` performs a bounded read and `from_dict`, and
returns `None` on an absent, invalid or oversize file, or on a mismatched run or attempt.

`_followup_kind_from_completion(c)`:

| completion | FollowupKind |
| --- | --- |
| `complete` | success path |
| `bounded_refusal` | `refused` |
| `harness_failure` + `fenced` / `claim_refused` | `fenced` |
| other `harness_failure`; `budget_exhausted` except `rate_limited` | `harness` |
| `rate_limited` | existing rate-limited handling |
| `deterministic_failure`, `incomplete` | `deterministic` |

The shepherd always computes this and logs `completion-disagreement` against
`_followup_exit_codes()`. Charging behaviour changes only when `SHEPHERD_TRUST_COMPLETION`
is on (default off). With the flag on, a `None` or disagreeing record still falls back to
the exit code. The merge decision never reads `outcome`.

### 5. Temporal / execution record (PR 3)

- `ExecutionRecord` gains optional `completion_id`, `completion_outcome`,
  `completion_stop_reason` and `completion_step` (default `""`). They go through the
  existing `optional` dict and 4xx retry path.
- New read-only activity `read_proposal_completion(service, slug)` in
  `activities/proposals.py` (a sibling of `read_proposal_status`), registered in
  `worker.py`. After `_run_cwft` returns `success` or `finalization`, `dev_loop._implement`
  and `implement_sweep` read `completion.authoritative`. They treat it as absent unless
  `completion.run_id == result.workflow_name` (stale fails closed). This replaces the
  previous revision's `attempt_id == workflow UID` check, which the deployed CWFT (no
  `WORKFLOW_UID`) would always have failed.
- The value is stored on `ImplementExecutionState.completion_outcome` and passed to
  `_record`, gated by `workflow.patched("implement-completion")`. There is no
  control-flow change.

### 6. Documentation (PR 1)

`docs/adr/021-implementation-completion-contract.md` covers:
- scope: an implementer-phase completion contract, not a review verdict, not approval,
  not a DevLoop;
- the outcome / stop-reason table;
- the v1alpha1 meaning of `complete` and follow-up F1 (task coverage);
- the primary / fallback authority rule;
- the replay key;
- the carrier boundary: git = durable result projection, Temporal / Argo = runtime,
  mctl-api = read model;
- the non-authorities list.

PR 2 and PR 3 each append their consumer section. `docs/temporal-flow.md` gets a pointer
in PR 3.

## Alternatives

1. **Extend exit codes and the `--refusal-out` JSON.** Exit codes cannot carry the run,
   step, claim, head or digest bindings, and the JSON is unversioned and only exists in
   review-feedback mode. Dropped.
2. **Reuse `ExecutionEvidence` (ADR 018) with an implementer-specific outcome.** That
   would leak implementer semantics into a cross-agent five-value outcome. Kept only as
   the join point: `ArtifactRef(kind: implementation-completion, content_hash)`.
3. **Fallback authority: last writer wins (status quo for the artifact).** Simple, but a
   fallback `harness_failure` on the missing second account would erase the primary's
   real `deterministic_failure` or `budget_exhausted`, which is exactly the owner's
   concern. Dropped.
4. **Fallback authority: drop the fallback's record entirely (replay guard refuses
   it).** This loses the only record when the fallback *succeeds*, and it loses the
   evidence that a second account was tried. Dropped in favour of the
   primary-unless-fallback-complete rule, which keeps both as summaries.
5. **Merge the two records in `commit-and-push`.** That would move contract logic into a
   CWFT shell script that this repo cannot unit-test. Dropped. The optional input
   artifact keeps the logic in Python under test.
6. **Argo output parameter or a new artifact read by Temporal.** The CWFT forbids
   `outputs.parameters` (#530/#531, gitops#1186). Dropped.
7. **Agent-authored completion.** This is self-certification, which the issue forbids.
   Dropped.

## Platform impact

- **Delivery:** three mctl-agents PRs, merged in order (see tasks.md), plus one small
  additive mctl-gitops PR (an optional input artifact on `run-implementer`). The latter
  can merge before or after mctl-agents PR 1: either order is safe.
- **Migrations:** none. `.status.yaml` gains an optional `completion:` key that existing
  readers ignore (`proposal_state.load_status`, `gitops_state._parse_status_yaml` read
  named keys).
- **Backward compatibility:** exit codes, `--refusal-out` and status transitions are
  unchanged. An older shepherd ignores the new file, and a newer shepherd with an older
  implementer falls back to exit codes. Temporal sits behind
  `workflow.patched("implement-completion")`. The optional CWFT input is skipped when the
  key is missing.
- **Resource impact:** one sha256 over three small files, one extra optional artifact
  download (a small tgz) in the fallback pod, and one GitHub contents read per Temporal
  implement step.
- **Risks and mitigations:**
  - *`complete` read as "scope done" or review-clean.* Mitigated by the `gates_passed`
    code name, the docstring and ADR wording, schema absence of review fields, and the
    shepherd never reading `outcome` for merge.
  - *Fallback hides the primary's outcome.* Mitigated by `select_authoritative` and
    T3a / T3b. Before the CWFT input lands, it is visible as `primary_observed: false`
    rather than silent.
  - *Stale artifact from an earlier run is read as the primary.* The `run_id` match fails
    closed.
  - *Mis-mapping charges the wrong counter.* The shepherd stays in shadow until the flag
    is turned on, and an exhaustive mapping test is added.
  - *Private content leaks.* Bounded, redacted leaves; no stdout/stderr field.

## Open questions

- `WORKFLOW_UID` is not set by the deployed implement CWFT, so the per-pod `HOSTNAME`
  derivation is what actually runs. Should the CWFT set it, as the `_resolve_attempt_id`
  docstring assumes? Out of scope here: the design binds `run_id` + `step` and is correct
  either way.
- Is the interim `primary_observed: false` behaviour, before the mctl-gitops optional
  input lands, acceptable? Or should mctl-agents PR 1 wait for it?
- Approved-content digest binding (`proposal_digest` vs. a future approval-time digest).
- The `RefusalMarker.remaining` extension as the only source of `incomplete`.
- The mctl-api `/api/v1/agents/executions` decoder was not inspected. Persisting the new
  optional fields is a cross-repo follow-up.
- Whether token-2 is seeded in production was not observed. It does not change the
  design.
