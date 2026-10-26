# SecurityFinding remediation and exact-revision verification runner (mctl-api 4.124.0 contract)

## Context

mctlhq/.github#209 adds a `SecurityFinding` lifecycle in three slices. Slice 1, mctlhq/mctl-api#774, shipped in mctl-api `4.124.0` (tag contains `8023be018`, PR #799). It adds the durable store and the REST API under `/api/v1/security`. That contract is normative: `docs/security-findings.md` and `internal/openapi/openapi.yaml` at tag `4.124.0`. This proposal is slice 2, and it supersedes mctlhq/mctl-agents#778, whose DevLoop stopped at the dependency gate. In `mctl-agents` it adds the client side of remediation:

- start a `RemediationAttempt` for one `SecurityOccurrence`, bound to the existing WorkItem/DevLoop identities;
- bind the exact landed merge commit (or artifact digest) to the active attempt when the DevLoop's PR merges;
- run bounded verification strategies against exactly that revision, and record the result through the canonical API.

mctl-api decides every state change, and every write is audited there. `mctl-agents` never decides a state locally.

This matters because "merged" is not "fixed". Without this runner an occurrence would either stay in `fixing` forever, or be closed on a GitHub merge signal or an unauthenticated provider claim. Either way MCTL would report a vulnerability as resolved without proof bound to the code that actually shipped.

## User stories

- AS a platform operator I WANT to start remediation for one affected occurrence and get the normal governed DevLoop (investigate, human approval, implement, merge watch) SO THAT security fixes do not bypass the existing work and approval system.
- AS a security reviewer I WANT an occurrence to move to `resolved` only after a verification bound to the exact landed revision meets the configured minimum strength SO THAT "merged" is never reported as "fixed".
- AS a security reviewer I WANT every earlier attempt, fix and verification kept after a regression SO THAT I can audit each remediation cycle.
- AS a platform owner I WANT provider text and severity to have no effect on transitions, strength or permissions SO THAT a hostile scanner payload cannot resolve, reopen or escalate anything.
- AS the Runtime Assurance owner I WANT the runner to consume a confirmed assurance replay as evidence without re-implementing replay SO THAT assurance semantics stay in one place.

## Acceptance criteria (EARS)

Contract capture
- THE SYSTEM SHALL keep every security route string in one `ROUTES` table in `orchestrator/security_findings/client.py`. Each entry cites a JSON fixture under `tests/fixtures/security_finding_v1/` that was captured from mctl-api `internal/openapi/openapi.yaml` and `docs/security-findings.md` at ref `4.124.0`.
- THE SYSTEM SHALL take its occurrence states, attempt outcomes, verification mechanisms, results, strength order and error codes from those fixtures. Where the fixtures and the issue text disagree, the fixtures win. One example: the tag's error enum also has `work_items_unavailable` and `internal_error`.

Start remediation
- WHEN an operator requests remediation for an occurrence in `open`, `triaged`, `reopened` or `unverifiable` THE SYSTEM SHALL call `POST /api/v1/security/occurrences/{id}/remediation-attempts` with the occurrence's existing `work_item_id`, the deterministic `devloop_workflow_id` (`orchestrator/temporal/issue_ref.py::workflow_id_for`), `start_source`, the read `expected_state_version`, and an `Idempotency-Key` derived from `(occurrence_id, state_version)`.
- IF mctl-api answers `remediation_attempt_active` (409) THEN THE SYSTEM SHALL report a deterministic `already_active` outcome naming the active attempt id it reads back, and SHALL NOT create a second WorkItem, DevLoop or attempt.
- IF mctl-api answers `invalid_transition`, `version_conflict`, `work_item_not_found`, `idempotency_key_reused` or `forbidden` THEN THE SYSTEM SHALL report a typed refusal with that code and change nothing.
- WHEN two occurrences of one finding are started THE SYSTEM SHALL treat them as independent requests, each with its own attempt and its own WorkItem correlation.
- WHILE the store answers `security_findings_store_unavailable` (503), or the transport fails, THE SYSTEM SHALL report `unknown` and SHALL NOT treat it as "no occurrence" or "no active attempt".

Merge is not resolution
- WHEN a DevLoop's merge watch observes its PR `merged` and that DevLoop's workflow id is the `devloop_workflow_id` of an occurrence's active attempt THE SYSTEM SHALL call `POST /api/v1/security/remediation-attempts/{id}/fix` with `landed=true`, `landed_revision` = the PR's `merge_commit_sha` (`PRState.merge_commit`), and `landed_ref` = the PR URL.
- THE SYSTEM SHALL NOT record a verification or any `resolved` state because of a merge or an implementer completion alone. After binding the fix the occurrence is `awaiting_verification`, as mctl-api decides.
- IF the PR closed unmerged THEN THE SYSTEM SHALL record nothing against the attempt.

Verification
- WHEN an occurrence is `awaiting_verification` THE SYSTEM SHALL pick, from the occurrence's own evidence, the strongest strategy available among `deterministic_regression_test`, `assurance_replay` and `scanner_rerun_exact_revision`. Each run SHALL be bounded by a wall-clock budget and an attempt cap.
- THE SYSTEM SHALL send `revision` and/or `artifact_digest` equal to the active attempt's `landed_revision` / `landed_artifact_digest`. Before any write, it SHALL refuse locally any verification whose observed revision or artifact differs from them.
- IF mctl-api answers `verification_not_bound` (422) THEN THE SYSTEM SHALL record the refusal and SHALL NOT retry with a different revision.
- WHEN a strategy observes the vulnerability absent at the landed revision THE SYSTEM SHALL record `result=passed` with that mechanism. WHEN it observes the vulnerability present THE SYSTEM SHALL record `result=failed`.
- IF a strategy errors, times out or cannot reach its source THEN THE SYSTEM SHALL record `error`, `timeout` or `unavailable` respectively, and SHALL never record `passed` for an unobserved outcome.
- IF every applicable strategy has been exhausted within the per-attempt budget without an observed `passed`/`failed` THEN THE SYSTEM SHALL record `result=unverifiable`.
- THE SYSTEM SHALL never send a strength field. Strength is derived by mctl-api from the mechanism and the authenticated recorder's ceiling.
- THE SYSTEM SHALL NOT record a `provider_claim` or `manual` verification itself. A provider `fixed` observation is ingested and weighed by mctl-api, and under the default minimum it cannot resolve the occurrence.

Scanner rerun
- WHEN the scanner-rerun strategy runs THE SYSTEM SHALL look for an authenticated provider observation (`provider_ref` not prefixed `admin:`) with `claimed_action=absent` or `present` whose `observed_revision`/`observed_artifact_digest` equals the landed one, and SHALL NOT invoke or implement a scanner. mctl-api turns an `absent` observation into a verification by itself, so the runner records nothing for an `absent` observation it finds. It records `failed` only for a bound `present` observation.

Assurance replay
- WHEN the occurrence's observations carry an evidence ref of kind `assurance_finding` that names a `confirmed` `AssuranceFinding` (`orchestrator/runtime_assurance.py`) THE SYSTEM SHALL use a replay result produced by Runtime Assurance for that finding's scenario with target revision equal to the landed revision. Invariant `held` means passed, `violated` means failed, and `unknown`/partial/failed observation means unavailable. It SHALL record the verification with mechanism `assurance_replay` and an `evidence_refs` entry of kind `assurance_finding`.
- IF the `AssuranceFinding` is not `confirmed`, or the replay is bound to a different scenario hash, runtime or target revision, THEN THE SYSTEM SHALL NOT use the assurance strategy for this attempt.

Deterministic regression test
- WHEN the reviewed mapping `config/security_regression_tests.json` names a regression check for the occurrence's `(subject.repository, finding identity_key)` AND that required check of that name has concluded on the landed merge commit THE SYSTEM SHALL record `deterministic_regression_test`: `passed` on success, `failed` on failure, `unavailable` when the check is missing or unknown (`orchestrator/ci_checks.py::read_required_checks` with `known=False` counts as missing or unknown).

Regression and reopen
- WHEN an operator requests remediation for a `reopened` occurrence THE SYSTEM SHALL start a new attempt through the same route, and SHALL NOT modify or delete earlier attempts or verifications.
- THE SYSTEM SHALL NOT post observations, and SHALL NOT reopen, resolve or dismiss an occurrence by any route other than those listed above. Reopening, the stale-scan filter and the deduplication of redelivered observations are mctl-api's (`observation_hash`).
- THE SYSTEM SHALL count independent confirmations by distinct observation `id`/`observation_hash`, never by response count.

Trust boundary
- THE SYSTEM SHALL NOT read `untrusted.*` (title, description, severity, claimed_provider) in any decision, strategy choice, prompt-assembled policy or permission. It MAY pass these fields to the DevLoop issue text only as quoted untrusted data.
- THE SYSTEM SHALL treat `provider_ref`, `derived_strength` and `state` as mctl-api's answers. It SHALL never derive them from payload strings.

Audit
- THE SYSTEM SHALL perform every state-changing write through the three 4.124.0 mutation routes this slice uses (`occurrences/{id}/remediation-attempts`, `remediation-attempts/{id}/fix`, `remediation-attempts/{id}/verifications`), each with an `Idempotency-Key` and `expected_state_version`. It SHALL print one structured line per write, carrying occurrence id, attempt id, transition and `replayed`.

## Out of scope

- The provider webhook endpoint, provider configuration and tokens (mctlhq/mctl-gitops#2103), and posting observations from mctl-agents.
- Any scanner implementation.
- Security UI.
- Policy or approval redesign. The DevLoop approval gate is unchanged.
- Auto-merge or production auto-deploy.
- Changes to Runtime Assurance contracts (#151 / ADR 022, 023) or a second replay engine.
- Ancestry-aware regression detection (out of scope in the #774 contract itself).
- Dismissal (human-only in #774).
- The Argo CronWorkflow / CWFT wiring in mctl-gitops that schedules the verifier sweep (a follow-up gitops PR).

## Open questions

- **Transient results vs `unverifiable`.** The issue says error/timeout/unavailable lead to `unverifiable`. The 4.124.0 contract says those results keep the occurrence in `awaiting_verification`, and only an explicit `unverifiable` result moves it. Proceeding with the tag: record the transient result, and record `unverifiable` only after the per-attempt budget is exhausted. The budget default is proposed as 3 sweeps or 72 h; it needs confirming.
- **N-observation flapping rule.** #774 defines no "N independent scanner observations" threshold: a single post-resolution `present` observation at a non-pre-fix revision reopens. The runner therefore implements no threshold. It only guarantees it never double-counts a redelivered observation. If a threshold is wanted, it belongs in mctl-api.
- **`security:remediate` grant.** #774 says mctl-agents "is minted `security:remediate`". It is not observable here whether the service `MCTL_TOKEN` or the run token (`orchestrator/run_token.py`) carries it in production. Until then, writes are answered 403 `forbidden`, and the runner reports that as a refusal.
- **Regression-test reference.** The 4.124.0 schema has no dedicated field naming a deterministic regression test. A provider-supplied evidence ref must not choose it either: the agent recorder's ceiling is `deterministic_regression_test`, so a hostile provider naming a trivially passing check could resolve the occurrence. The proposal uses a PR-reviewed mapping in `config/security_regression_tests.json`, keyed by `(repository, identity_key)`. Without an entry, the strategy is skipped. A contract-level field may be preferable later.
- **Occurrence-to-DevLoop discovery after merge.** `GET /occurrences` filters by `repository` and `state` but not by `devloop_workflow_id`. The bind step lists `state=fixing&repository=<repo>` and matches `active_attempt_id`'s attempt on `devloop_workflow_id`, reading full occurrences where the summary omits attempts. A server-side filter would be cheaper.
