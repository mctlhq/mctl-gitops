# Design: issue-778-feat-agents-securityfinding-remediation

## Current state

No SecurityFinding code exists in mctl-agents. A repo-wide search for
`SecurityFinding|SecurityOccurrence|security_finding` only hits the spike
fixture `tests/fixtures/spike_manifests/security-finding-lifecycle.yaml`
(verdict `ADD_SECURITY_FINDING_CONTRACT`, follow-ups mctl-api#774,
mctl-agents#778, mctl-gitops#2103). The pieces this slice composes already
exist:

- **WorkItem / execution requests** - `orchestrator/work_context/client.py`
  (`WorkItemClient`, synchronous urllib, `MCTL_TOKEN` bearer via
  `orchestrator.run_token.mctl_api_bearer`, https-only, no-redirect opener,
  "uncertainty is a value, never an exception", one module-level `ROUTES`
  table), `work_context/creation.py` (`idempotency_key_for`, `create_body`),
  `work_context/execution_requests.py` (claim/fulfil/reject answers), and the
  dispatcher in `orchestrator/temporal/dispatcher.py` that delivers a pending
  request to a DevLoop (enabled in prod by `EXECUTION_REQUEST_DISPATCHER`).
- **DevLoopWorkflow** - `orchestrator/temporal/workflows/dev_loop.py`.
  `IssueRef` (line ~847) is the single workflow input, already extended with
  defaulted optional fields (`work_item_id`, `resume`,
  `execution_request_id`) under `workflow.patched` conventions. The
  post-merge tail (`_finish_after_watch`, ~line 4425) gates deploy
  observation on `pr_state.merged` behind `workflow.patched("deploy-observation")`.
- **PR state** - `orchestrator/temporal/activities/pr_state.py` `PRState`
  already carries `merge_commit` (from GitHub `merge_commit_sha`), `merged_at`
  and `head_sha`.
- **Runtime Assurance** - `orchestrator/runtime_assurance.py` (ADR 022)
  defines `AssuranceFinding` with states candidate/confirmed/rejected,
  `VersionBinding`/`TargetRevision`, `FindingValidation` and
  `check_finding_confirmation` (replay must be a distinct run, same binding,
  same invariant violated). `orchestrator/assurance_harness.py` (ADR 023)
  executes bounded probes. Both are pure/bounded; neither persists anything.
- **Evidence** - `orchestrator/execution_evidence.py` (`ArtifactRef`,
  `ExecutionJoin`, `ev-` ids, ADR 018), `orchestrator/redaction.py`
  (`contains_credential`, bounded redaction).
- **Rollout ladders** - `orchestrator/work_context/rollout.py` and
  `orchestrator/lifecycle/rollout.py`: `off|observe|enforce|only`, default
  `off`, typo answers `off`, env var read in exactly one module.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the
  DevLoop/schedule-owning worker; `LIFECYCLE_ROLLOUT_MODE: observe`,
  `EXECUTION_REQUEST_DISPATCHER: "true"`, `GITHUB_TOKEN_FILE` mounted. No
  security-related env var exists.
- `$MCTL_GITOPS_ROOT/services/admins/` also contains
  `mctl-agents-worker-exec` and `mctl-agents-worker-implement` (queue split,
  ADR 008); not inspected in detail, no change proposed for them.
- mctl-api#774 contract: NOT observable from this run (cross-repo, no
  checkout). Recorded as the gating open question; not assumed absent.
- mctl MCP tools: not called; gitops checkout was sufficient for the one
  deployed fact needed (which worker owns schedules).

## Proposed solution

A new package `orchestrator/security_remediation/`, modelled on
`orchestrator/work_context/`, plus two small DevLoop hooks and one Temporal
schedule. mctl-api#774 remains the only store and state machine; this package
only reads, requests and submits evidence.

### 1. `security_remediation/contract.py` - client-side view of #774

Frozen dataclasses parsed from #774 responses with `_reject_unknown` style
strictness: `OccurrenceRef`, `Occurrence` (id, finding id, state,
state_version, `provider_channel` = authenticated adapter identity and its
`allowed_strategies` / strength map as returned by #774), `RemediationAttempt`
(id, sequence, active flag, work_item_id, execution_request_id,
execution_ids, `landed: RevisionBinding | None`), `RevisionBinding`
(repository, commit_sha 40-hex, optional artifact digest `sha256:`),
`VerificationEvidence` (strategy, verdict in {absent, present, unverifiable},
strength, observation_key, binding, evidence ref). Provider text fields are
carried only as redacted, bounded strings (`redaction`) and are never read by
any decision function - a test pins that no decision function accepts them.

### 2. `security_remediation/client.py` - `SecurityClient`

Structural copy of `WorkItemClient` (same auth, https-only, no-redirect,
"unknown is a value"). One `ROUTES` table; every route string from #774 lives
there. Methods: `get_occurrence`, `list_attempts`, `start_remediation`
(idempotency key `sha256(occurrence_id|state_version|"start")`),
`bind_landed_revision(attempt_id, RevisionBinding)`,
`submit_verification(attempt_id, VerificationEvidence)` (idempotency key =
observation_key), `submit_observation(occurrence_id, ...)` for regression
evidence. Every answer is `found | refused(code) | unknown(reason)`; unknown
never collapses to "no active attempt".

### 3. Start remediation (`security_remediation/start.py`)

`start_remediation(occurrence_id)`:
1. read the occurrence; unknown -> stop, write nothing;
2. call #774 start-remediation; #774 enforces one active attempt and decides
   WorkItem reuse vs. creation for regressions; an `active_attempt_exists`
   refusal is returned verbatim (deterministic, no side effects);
3. on success, request execution through the existing
   `mctl_request_work_item_execution` path (`WorkItemClient`), so the existing
   dispatcher starts a DevLoop via Update-with-Start. The DevLoop input
   carries a new defaulted field `IssueRef.remediation_attempt_id: str | None
   = None` (old histories deserialize unchanged).
Exposed as a CLI `python -m orchestrator.security_remediation start
--occurrence-id ...` for operators; no new MCP/approval surface. Separate
occurrences naturally produce separate attempts/WorkItems/DevLoops.

### 4. Merge binds, never resolves (DevLoop hook)

In `_finish_after_watch`, behind `workflow.patched("security-remediation-bind")`
and only when `remediation_attempt_id` is set and `pr_state.merged`, run a new
activity `bind_remediation_landed(attempt_id, repo, pr_state.merge_commit,
artifact_digest)` (activities module
`orchestrator/temporal/activities/security_remediation.py`). It calls
`bind_landed_revision`; #774 moves the occurrence to `awaiting_verification`.
The rollout gate lives in activity code (as with `LIFECYCLE_ROLLOUT_MODE`), so
workflow commands are mode-independent and replay-safe. The DevLoop never
calls a resolve route; there is no code path from merge/implementer outcome
to `resolved`. If deploy observation produced an image digest, it is passed
as the artifact binding; otherwise SHA only.

### 5. Verification runner (`security_remediation/verify.py`)

A `Strategy` protocol: `run(occurrence, attempt, budget) -> StrategyResult`.
Strategies shipped:
- `assurance_replay` - only if the occurrence references an
  `AssuranceFinding`; loads finding/run/result, validates via
  `runtime_assurance.*.from_dict` and `check_finding_confirmation`-equivalent
  binding checks, requires `TargetRevision` == landed SHA, and uses the
  existing harness (`assurance_harness.execute`) only to replay the existing
  scenario - no new probe generation.
- `regression_test` - a named deterministic CI check on the landed SHA via
  `orchestrator/ci_checks.py`; pass -> absent, fail -> present, missing/pending
  past budget -> unverifiable.
- `provider_claim` - maps a provider `fixed` claim to `absent` at the weak
  strength #774 assigns; never sufficient alone under default policy.
- `scanner_rerun` and `manual_evidence` - adapter protocol only; registry
  empty by default (real scanner adapters are out of scope).

`decide(occurrence, attempt, results)` is a pure function:
1. discard any result whose binding != `attempt.landed` (rejected, logged);
2. any error/timeout/budget exhaustion -> `unverifiable`;
3. `present` from any allowed strategy -> `present`;
4. `absent` whose strength (looked up from `occurrence.provider_channel`,
   never from the payload) meets #774's threshold -> `absent`;
5. otherwise `unverifiable`.
The runner submits each piece of evidence and the decision via
`submit_verification`; #774 performs the transition. Each strategy has a
wall-clock timeout and max attempts; the whole run is bounded.

Trigger: a new Temporal schedule `security-verify-sweep` on the schedule-owning
worker (`mctl-agents-worker`) that lists `awaiting_verification` /
`unverifiable` occurrences (bounded page) and runs the runner per occurrence,
plus an optional inline call right after the bind activity. Re-running is
safe: evidence submits are idempotent by observation key.

### 6. Regression evidence

`submit_observation` forwards scanner/assurance observations for resolved
occurrences with (observation_key, revision binding, provider channel). The
runner does not decide reopen: it refuses locally only when the observation is
bound to the attempt's pre-fix revision or to a revision #774 reports as
not-descendant; ancestry unknown is passed as unknown. Confirmation counting
(N independent observations vs. one deterministic proof) is #774's, and the
stable observation_key guarantees redelivery counts once. When work restarts,
step 3 creates attempt #2; attempt #1 is never modified by this package.

### 7. Rollout

`security_remediation/rollout.py`, same ladder as `work_context/rollout.py`:
`SECURITY_REMEDIATION_ROLLOUT_MODE` = `off` (default, no #774 call) |
`observe` (read + log decisions, no writes) | `enforce` (writes). Merge can
land before #774 ships; gitops flips later.

## Alternatives

1. **Keep remediation state in mctl-agents (proposal `.status.yaml` or a
   local table).** Dropped: the issue requires every transition through #774
   and auditable; a second store would fork lifecycle state and recreate the
   `vulnerable_rev/fixed_rev` mutable-pair problem.
2. **Resolve on merge plus a later "re-check".** Dropped: explicitly
   forbidden ("merge is not resolution") and creates a window where resolved
   is false.
3. **Verification as a new DevLoop stage only (no sweep).** Dropped as the
   sole mechanism: DevLoops end after the incident-watch window, verification
   inputs (CI on landed SHA, scanner reruns) can arrive later, and an
   unverifiable result must be retryable without restarting the loop. Kept as
   a best-effort inline hint.
4. **Extend `AssuranceFinding` to model security findings.** Dropped: the
   spike decided a separate contract, and the issue forbids turning Runtime
   Assurance into a general scanner or changing its contracts.

## Platform impact

- **Dependency:** blocked on mctl-api#774 release. Code ships with rollout
  `off`; no runtime behaviour change until gitops sets the mode.
- **Workflow compatibility:** `IssueRef.remediation_attempt_id` is defaulted;
  the bind step is behind `workflow.patched("security-remediation-bind")`, so
  existing histories replay unchanged.
- **Migrations:** none in mctl-agents. gitops: one env var on
  `admins/mctl-agents-worker` when enabling; the schedule is registered by the
  worker like existing scheduled dispatches.
- **Resources:** sweep is bounded (page size, per-strategy timeout); assurance
  replay reuses existing harness budgets. Negligible model cost (no model
  call in the runner).
- **Risks:**
  - #774 shape drift -> single `ROUTES` table and strict parsing; tests run
    against recorded #774 fixtures that are refreshed when #774 merges.
  - False resolve from wrong revision -> local binding check plus #774 server
    check; unknown never resolves.
  - Hostile provider text -> redacted, bounded, and structurally excluded from
    decision functions (test-pinned).
  - API outage -> unknown answers write nothing; sweep retries next tick.
