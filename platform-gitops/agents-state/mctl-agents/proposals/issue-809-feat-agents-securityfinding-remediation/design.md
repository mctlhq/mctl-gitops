# Design: issue-809-feat-agents-securityfinding-remediation

## Current state

`mctl-agents` has no SecurityFinding code today. `grep -ri "securityfinding|SecurityOccurrence"` over the clone finds nothing. The pieces this slice builds on:

- **mctl-api client pattern.** `orchestrator/work_context/client.py::WorkItemClient` is a synchronous `urllib` client. It authenticates with `orchestrator.run_token.mctl_api_bearer`, refuses non-https, refuses redirects (`_no_redirect_opener`), and keeps all route strings in one module-level `ROUTES` dict. Its contract is "uncertainty is a value, never an exception": transport failures become a `*_UNKNOWN` answer. Answer parsing lives in sibling modules (`contract.py`, `executions.py`, `snapshots.py`, `execution_requests.py`), and tests monkeypatch the transport against JSON fixtures in `tests/fixtures/workitem/`. `orchestrator/action_approvals.py` uses the same `ROUTES` convention.
- **WorkItem creation.** `WorkItemClient.create_work_item(tenant, issue_url, run)` and `orchestrator/work_context/creation.py` (`canonical_issue_url`, `idempotency_key_for`, `create_body`) give a durable WorkItem keyed by `(tenant, external_key=issue URL)`. An open item with the same key is answered rather than duplicated.
- **DevLoop identity.** `orchestrator/temporal/issue_ref.py::workflow_id_for(issue_url)` gives the deterministic `dev-loop-mctlhq-<repo>-<n>` id. `DevLoopWorkflow` (`orchestrator/temporal/workflows/dev_loop.py`) runs investigate, then the human approval park, then implement, then the merge watch (`_watch_pr`), and finally `_finish_after_watch`. That tail is the one place reached with the final `PRState` whether or not the watch hopped across continue_as_new. It already gates new stages with `workflow.patched(...)` (`deploy-observation`, `incident-watch`).
- **Landed revision.** `orchestrator/temporal/activities/pr_state.py::PRState.merge_commit` is GitHub's `merge_commit_sha`, set only when `merged`. `head_sha` is the PR head.
- **Required checks.** `orchestrator/ci_checks.py::read_required_checks` returns `CIStatus`, with `known=False` on any probe failure (fail closed).
- **Runtime Assurance.** `orchestrator/runtime_assurance.py` defines `AssuranceFinding` (states `candidate|confirmed|rejected`; a confirmed finding requires a `validation` block whose replay run and result differ from the origin) and checks that a replay is bound to the same scenario, runtime and target revision (around line 1543). `orchestrator/assurance_harness.py::execute(...)` is the bounded probe harness. ADR 022 and ADR 023 own these semantics.
- **Policy.** `orchestrator/policy_checkpoint.py` and `action_approvals.py` gate actions. This slice adds no new action kind, because it performs no GitHub mutation.

Normative contract read at mctl-api tag `4.124.0` (`gh api repos/mctlhq/mctl-api/contents/<path>?ref=4.124.0`):

- `docs/security-findings.md`. Model: `SecurityFinding (sf_)` > `SecurityOccurrence (soc_)` > `ProviderObservation (sob_)`, `RemediationAttempt (sra_)` > `VerificationRecord (svr_)`, plus an occurrence event log. The transition table (`securityfindings.Transitions`) is the single enforcement point. There is at most one active attempt per occurrence (a partial unique index on `outcome IS NULL`). A landed fix moves the occurrence to `awaiting_verification`, never to `resolved`. The verification revision or artifact must match the landed one (`verification_not_bound`, 422). `unavailable`/`error`/`timeout` stay `awaiting_verification`, and `unverifiable` moves to `unverifiable`. Derived strength is `min(mechanism, recorder ceiling)`, and the agent ceiling holding `security:remediate` is `deterministic_regression_test`. `assurance_replay` requires an `assurance_finding` evidence ref, or it is capped at `provider_claim`. An `absent` observation bound to the landed revision becomes a server-side verification at `min(scanner_rerun_exact_revision, provider ceiling)`. Reopening happens on a post-resolution `present` observation that is not at a pre-fix affected revision. Dedup is by `observation_hash`. `untrusted.*` is inert.
- `internal/openapi/openapi.yaml` lines ~1444-1700 (schemas `SecurityFindingError`, `SecurityEvidenceRef`, `SecurityOccurrence`, `SecurityAttempt`, `SecurityVerification`, `SecurityMutationResult`, `SecurityStartRemediationRequest`, `SecurityRecordFixRequest`, `SecurityRecordVerificationRequest`) and lines ~5950-6239 (paths). The error enum at the tag also contains `work_items_unavailable` and `internal_error`, which the issue text does not list. `GET /occurrences` filters by `finding_id`, `tenant`, `state`, `repository`, `limit` and `cursor`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml` were read with grep. No `security`-related env, scope or `MCTL_API_BASE_URL` override appears (only pod and container security contexts). The DevLoop workers run in tenant `admins`.
- `grep -ri "security_finding|SECURITY_PROVIDERS|securityProviders"` over `$MCTL_GITOPS_ROOT/services` found nothing. So within the gitops services tree, mctl-api's security store and provider configuration were not observed. That does not prove they are unset. mctl-api's own values may sit elsewhere, and this run could not confirm whether `SECURITY_FINDINGS_DB_URL`/`EVIDENCE_DB_URL` is live.
- mctl MCP tools were not called in this run. Whether the service or run token holds `security:remediate` is therefore **not observed**. It is recorded under Open questions in requirements.md.

## Proposed solution

Add a new package `orchestrator/security_findings/`, one DevLoop hook, and one sweep entry point. Every state decision stays in mctl-api. The package only reads, picks a strategy, and writes through the three mutation routes.

### 1. Contract fixtures and client (`orchestrator/security_findings/client.py`, `contract.py`)

- `tests/fixtures/security_finding_v1/` holds JSON captured from the tagged files:
  - `routes.json`: method, path, success status, error codes per route;
  - `schemas/*.json`: the request and response schemas above;
  - `vocabulary.json`: occurrence states, attempt outcomes, mechanisms, results, strength order, default minimum, error codes;
  - example responses for each answer branch: `occurrence-fixing.json`, `occurrence-awaiting.json`, `occurrence-resolved-two-attempts.json`, `start-201.json`, `start-409-active.json`, `fix-200.json`, `verify-422-not-bound.json`, `store-503.json`;
  - a `SOURCE.md` naming the ref, `4.124.0`, and the line ranges.
- `client.py` defines `ROUTES` with comments citing `routes.json`:

  ```text
  list_findings     GET  /api/v1/security/findings
  get_finding       GET  /api/v1/security/findings/{id}
  list_occurrences  GET  /api/v1/security/occurrences
  get_occurrence    GET  /api/v1/security/occurrences/{id}
  start_remediation POST /api/v1/security/occurrences/{id}/remediation-attempts
  record_fix        POST /api/v1/security/remediation-attempts/{id}/fix
  record_verification POST /api/v1/security/remediation-attempts/{id}/verifications
  ```

  `triage`, `dismiss` and `observations` are deliberately absent. Dismiss is human-only, and observation ingest is provider-only. A test asserts that `ROUTES` equals the subset of `routes.json` this slice uses.
- `SecurityFindingsClient` copies `WorkItemClient`'s transport (bearer via `run_token.mctl_api_bearer`, https-only, no redirects, `MCTL_API_BASE_URL`). Each mutation takes an explicit `idempotency_key` and `expected_state_version` and sends `Idempotency-Key`.
- Answers are typed dataclasses: `OccurrenceAnswer` and `MutationAnswer`, each with `verdict` in `ok | refused | unknown`, plus `code`, `replayed`, `state` and `state_version`. A 503, a transport error or a malformed body is `unknown`. A 4xx with a known code is `refused(code)`. A code outside the fixture vocabulary is `unknown`, never `ok`.
- `contract.py` holds closed frozensets loaded once from `vocabulary.json` at import time: `STATES`, `MECHANISMS`, `RESULTS`, `STRENGTH_ORDER`, `ERROR_CODES`. The parser reads only `id`, `state`, `state_version`, `active_attempt_id`, `remediation_attempts[]`, `verifications[]`, `observations[].{id, observation_hash, provider_ref, claimed_action, observed_revision, observed_artifact_digest, evidence_refs}` and `subject.repository`. `untrusted` is dropped at parse time, so no downstream code can read it. A test pins that the parsed dataclass has no `untrusted` attribute.

### 2. Start remediation (`orchestrator/security_findings/remediation.py`, CLI `python -m orchestrator.security_findings start`)

Inputs: `--occurrence soc_...`, `--issue-url https://github.com/mctlhq/<repo>/issues/<n>` (the tracking issue the operator files for the DevLoop), `--tenant`.

1. `get_occurrence`. On `unknown`, stop with `unknown`.
2. `create_work_item(tenant, issue_url, run)`. The existing idempotent create answers the open WorkItem for that issue. Whether a regression reuses that WorkItem or gets a new one is therefore decided by the issue the operator passes. Both are allowed by #774, because `work_item_id` is a correlation.
3. `start_remediation(occ_id, work_item_id, devloop_workflow_id=workflow_id_for(issue_url), start_source="agent:security-remediation", expected_state_version, idempotency_key=sha256("sra-start", occ_id, state_version))`.
4. Map the answer:
   - `201` gives `started(attempt_id)` or `replayed`;
   - `remediation_attempt_active` gives `already_active(active_attempt_id re-read)`;
   - every other refusal is passed through.
5. The operator then starts the DevLoop exactly as today (`mctl_trigger_issue use_temporal=true`). The approval gate is untouched.

Keying the idempotency on `state_version` makes a replay of the same request a server-side `replayed`. A second request after the attempt exists sees a newer `state_version` and fixing state, and the server refuses it with `remediation_attempt_active`/`invalid_transition`. Either way it is deterministic.

### 3. Bind the landed revision (DevLoop hook)

- A new activity, `security_record_landed` in `orchestrator/temporal/activities/security_findings.py`, registered in `worker.py` on the existing exec queue.
- Input: `(workflow_id, target_repo, pr_url, merge_commit)`.
- It lists `GET /occurrences?state=fixing&repository=<repo>` (paginated with a cap of 10 pages), reads each candidate in full, and selects occurrences whose active attempt has `devloop_workflow_id == workflow_id`. For each, it calls `record_fix(attempt_id, landed=true, landed_revision=merge_commit, landed_ref=pr_url, expected_state_version, idempotency_key=sha256("sra-fix", attempt_id, merge_commit))`.
- It returns a list of `(occurrence_id, outcome)`. Zero matches is the normal case for non-security DevLoops, and costs one list call.
- Wiring: in `DevLoopWorkflow._finish_after_watch`, right after the `deploy-observation` block and gated by `workflow.patched("security-record-landed")` and `pr_state.merged and pr_state.merge_commit`, the workflow calls the activity with a bounded retry policy (3 attempts). On failure it logs and continues: the sweep in section 4 re-binds from the occurrence side. The DevLoop result gets an optional `security: list[...] | None = None` field (None on old histories).
- The hook never records a verification, so a merge alone leaves the occurrence `awaiting_verification`.
- Fallback for a missed hook: the sweep also handles occurrences in `fixing` whose attempt's DevLoop is finished with a merged PR. It reads `get_dev_loop` and the PR state, and binds the same `merge_commit`. The idempotency key makes a double bind a replay.

### 4. Verification runner (`orchestrator/security_findings/verification.py`, entry `orchestrator/run_security_verifier.py`)

The sweep is a one-shot CLI, run by a CronWorkflow added later in mctl-gitops. Each run:

1. Lists `state=awaiting_verification` (cap 50 per run) and reads each occurrence in full.
2. Takes the active attempt, and `bound = (landed_revision, landed_artifact_digest)`. A `bound` with neither set is skipped as `not_bound`.
3. Builds the strategy plan from the occurrence's evidence, strongest first. Each strategy is a `Verifier` protocol that returns `Outcome(result, revision, artifact_digest, evidence_refs)` or `NotApplicable`:
   - **`RegressionTestVerifier`** (`deterministic_regression_test`). Applicable only when the reviewed `config/security_regression_tests.json` maps `(repository, identity_key)` to a required-check name. It reads the check runs on `landed_revision` (GitHub commit check-runs, through the same token path `ci_checks` uses). success gives `passed`, failure gives `failed`, and missing, pending past budget or unknown gives `unavailable`.
   - **`AssuranceReplayVerifier`** (`assurance_replay`). Applicable only when an observation carries `evidence_refs[kind=assurance_finding]` and that `AssuranceFinding` parses via `runtime_assurance.AssuranceFinding.from_dict` as `confirmed`. It consumes a Runtime Assurance replay result (`AssuranceResult`) for the finding's scenario whose binding target revision equals `landed_revision`, using the existing binding check. The verdict mapping is `held` to `passed`, `violated` to `failed`, and `unknown` or a partial or failed observation to `unavailable`. It sends `evidence_refs=[{kind: assurance_finding, ref: afd-..., digest: content_hash}, {kind: assurance_result, ref: ars-...}]`. No new replay engine: if no such result exists yet, the outcome is `unavailable`, and requesting a replay stays with Runtime Assurance.
   - **`ScannerRerunVerifier`** (`scanner_rerun_exact_revision`). It inspects the observations already on the occurrence from authenticated providers (`provider_ref` not starting `admin:`), bound to the landed revision or artifact and observed after `landed_at`. A bound `absent` means mctl-api has already recorded the verification, so the runner records nothing and moves on. A bound `present` means record `failed`. Nothing found means `pending`. The runner never runs a scanner.
4. Records exactly one verification per sweep per attempt: the first strategy that produced `passed` or `failed`. Otherwise it records the strongest strategy's transient result (`unavailable`/`error`/`timeout`), with an exception or deadline mapped to `error`/`timeout`. Every write uses `expected_state_version` and the key `sha256("svr", attempt_id, mechanism, result, revision, sweep_window)`, so a crashed and rerun sweep replays rather than duplicates.
5. Exhaustion. When the attempt has accumulated more than `SECURITY_VERIFY_MAX_TRANSIENT` (default 3) transient verifications recorded by this agent, or `landed_at` is older than `SECURITY_VERIFY_DEADLINE_H` (default 72), with no `passed`/`failed`, it records `result=unverifiable` with the strongest mechanism attempted. Both counts are taken from the occurrence's own `verifications[]` read back, so they survive restarts.
6. Local binding guard. Before any write, `Outcome.revision`/`artifact_digest` must equal `bound`. A mismatch is dropped with `local_not_bound` and never sent. A server 422 `verification_not_bound` is logged and never retried with another revision.
7. Output: one JSON line per occurrence (`occurrence_id`, `attempt_id`, `mechanism`, `result`, `transition`, `state`, `replayed`).

The sweep never sends a strength, never records `provider_claim` or `manual`, and never reads `untrusted`.

### 5. Regression and reopen

Reopening happens in mctl-api, from provider observations. The runner's part:

- The `start` CLI accepts `reopened` (and `unverifiable`) occurrences and creates attempt `seq+1` through the same route. It never edits earlier attempts, because no route exists to do so.
- Confirmation counting anywhere in the runner keys on distinct `observation_hash`, so a redelivered observation, which mctl-api answers `duplicate` with the original id, cannot count twice.
- Stale pre-fix scans are filtered by mctl-api (it does not reopen at a revision recorded as affected before the fix). In addition, `ScannerRerunVerifier` ignores observations not bound to the current landed revision or artifact.

### 6. Trust boundary

- Provider identity and ceiling come from `provider_ref`/`derived_strength` as stored by mctl-api.
- Strategy selection reads only structural fields and the PR-reviewed regression-test mapping. A provider cannot pick the regression check.
- When the operator writes the DevLoop tracking issue, finding text appears there as quoted untrusted data. The investigator already treats issue bodies as untrusted.

## Alternatives

1. **Drive remediation from a new Temporal workflow (`SecurityRemediationWorkflow`) that owns the whole cycle and wraps a DevLoop as a child.** Dropped. It introduces a second durable owner per remediation, overlapping ADR-010 lifecycle ownership. It also complicates the approval park, which already lives in `DevLoopWorkflow`, and #748 shows a reached-implement DevLoop cannot be restarted anyway. A thin hook plus an idempotent sweep reuses the existing loop unchanged.
2. **Resolve on DevLoop completion or a provider `fixed` claim.** Dropped. This is exactly what the contract forbids: merge is not resolution, and `provider_claim` is below the default minimum.
3. **Have mctl-agents run scanners or post synthetic `absent` observations itself.** Dropped. Observation ingest is provider-only (admin ingest is capped at `provider_claim`), and scanner implementation is out of scope. Recording `scanner_rerun_exact_revision` verifications under the agent principal without a real scanner result would launder strength.
4. **Put the regression-test name in provider evidence refs.** Dropped. It lets a provider select a trivially passing check at the agent's `deterministic_regression_test` ceiling. A reviewed config file keeps that choice under PR review.

## Platform impact

- **Migrations:** none in mctl-agents. mctl-api owns the schema (`securityfinding/v1`).
- **Backward compatibility:** the DevLoop change is behind `workflow.patched("security-record-landed")`. Old histories replay unchanged, and the new `DevLoopResult.security` field defaults to None. Non-security DevLoops pay one `GET /occurrences` per merged PR. If the store answers 503 (disabled or not configured), the activity answers `unknown` and the loop continues.
- **Resource impact:** the sweep is bounded at 50 occurrences, 10 pages and per-request timeouts of 10 s. No model calls, so cost is nil.
- **Risks and mitigations:**
  - Missing `security:remediate`: writes return 403 and are reported as `refused(forbidden)`, with no state change. This is surfaced in the sweep output.
  - Wrong DevLoop match: exact equality on `devloop_workflow_id`, plus `repository` filtering, plus `expected_state_version`.
  - Double write on retry: idempotency keys are derived from immutable inputs.
  - Hostile provider text: dropped at parse time, with a test pinning it.
  - False reopen from rescanning an old unlisted revision: this is a known #774 limitation. The runner adds no reopen path.
- **Kill switch:** unset the CronWorkflow, or rely on mctl-api's `SECURITY_FINDINGS_DISABLED=true` (every route answers 503, and the runner answers `unknown`).
