# Design: issue-986-feat-review-review-worker-producer-for-a

## Current state

Tier A contract, no producer:
- `orchestrator/review_receipts.py` (ADR `docs/adr/025-independent-review-receipts.md`) is pure. It provides
  `proposal_subject`, `spike_subject`, `spike_report_digest`, `seal_request`, `seal_receipt`, `ReviewRequest`
  / `ReviewReceipt` (`from_dict` rejects unknown keys), `evaluate_review_gate`, the rubrics
  (`RUBRIC_FOR_SUBJECT`) and the Tier A codes (`review_pass_with_unobserved`, `review_rubric_mismatch`,
  `review_malformed`, ...). `_EXECUTION_ID_RE` admits `we_<uuid>`, `we_<hex>` and `ex-<16 hex>`.
  `evidence_ref` is optional (`ev-` + 16 hex when set). `findings_ref` is an `ArtifactRef` hash pointer.
- Nothing in `orchestrator/` calls `/api/v1/review-requests` or `/api/v1/review-receipts`. A grep for both
  paths returns nothing.

Building blocks the producer reuses:
- **Service-principal mint, then use.** `orchestrator/temporal/activities/delegated_approval.py`
  `_mint_and_execute` POSTs `/api/v1/agent-run-tokens` with `{agent, execution_id, ttl_seconds: 900,
  permissions: []}` under `mctl_client.auth_headers()` (the service credential). It keeps the `art_` token
  in a local variable for one HTTP call, and maps typed refusals with `_refusal_of` / `_code_of`. Retryable
  codes include `agent_run_tokens_unavailable`. `RUN_TOKEN_AGENT = "issue-investigator"` there.
- **Pod-side run token.** `orchestrator/run_token.py` exchanges the pod's projected SA token at
  `/api/v1/agent-run-tokens/exchange` and has `revoke(token)` at `/api/v1/agent-run-tokens/self/revoke`. The
  token is kept out of `os.environ`.
- **Execution attach.** `orchestrator/work_context/client.py` `attach_execution(work_item_id, EngineRun,
  phase)` POSTs `/api/v1/work-items/{id}/executions`. It is idempotent on `(engine, engine_ref)`.
  `orchestrator/work_context/executions.py` `answer_from_attach` classifies the answer as
  `EXECUTION_ATTACHED` / `EXISTING` / `ACTIVE` / `REFUSED` / `UNKNOWN`, and accepts a 2xx only if it
  describes this exact item, engine run and phase.
- **Provenance derivation.** `orchestrator/execution_provenance.py`: `attempt_id(engine, engine_ref)` hashes
  the engine run (the `engine_ref` before `#`), and `lineage_root(root_execution_id)` hashes the root
  execution. Two executions with the same engine run share an attempt id. A resume shares the lineage.
- **Evidence.** `orchestrator/evidence_producer.py`: `run(stage)` context manager, `RunEvidence`,
  `note_artifact_file(path, kind)` (file based), and `note_work_execution`. `STAGES = {investigator,
  implementer, shepherd}`. `orchestrator/execution_evidence.py` `USAGE_DEVLOOP_STAGES` already contains
  `reviewer`.
- **Capability bound.** `orchestrator/options.py`: every builder goes through `_scrubbed`, which blanks the
  usage, evidence and mctl-api tokens. `build_authoring_canary_options` is the minimal read-only, no-MCP,
  no-hooks builder, and `build_shepherd_options` grants `["Read"]` with `mcp_servers={}`.
  `orchestrator/policy_checkpoint.py` defines the `github.*` action kinds (`GITHUB_GIT_PUSH`,
  `GITHUB_PR_MERGE`, `GITHUB_PR_COMMENT`, `GITHUB_ISSUE_COMMENT`, `GITHUB_ISSUE_LABEL`, `GITHUB_RUN_RERUN`)
  and `BUILTIN_POLICY`. `orchestrator/run_shepherd.py:156` has
  `GATING_BOTS = (REVIEW_BOT, CODEX_CONNECTOR_BOT)`.
- **Manifests and profiles.** `agents/_manifests/<agent>/agent.yaml` binds to a mctl-gitops profile at
  `platform-gitops/agent-platform/execution-profiles/<name>/profile.yaml`. `orchestrator/validate_manifest.py`
  diffs the profile's `runtime.optionsBuilder` and `tools` against `options.py`. A runner pattern without
  Temporal exists in `orchestrator/run_security_verifier.py`.

mctl-api contract (from the #917 proposal `design.md` in mctl-gitops `agents-state/mctl-api/proposals/
issue-917-feat-review-enable-autonomous-worker-rec/`):
- The worker handler requires `user.IsAgent()`, a non-empty `ExecutionID()` and scope `review`, else
  `403 review_run_token_required`. The body is decoded with `DisallowUnknownFields`.
- `SubmitWorker` checks, in order: request (404 / `review_request_closed` / `review_request_mode_manual` /
  `review_binding_mismatch`), `review_nonce_mismatch`, provenance (`review_execution_unproven`,
  `review_provenance_unavailable`), `review_reviewer_ineligible` (`!attached_direct_service`),
  `review_reviewer_not_independent`, then one transaction: nonce consumption (`review_nonce_consumed`) plus
  the receipt insert, otherwise `503 review_store_unavailable`. It answers 201 with `receipt_id`,
  `request_id`, `mode`, `assurance`, `tenant` and `receipt`.
- `attached_direct_service` is `isDirectService(user) && !user.IsAgent()` at attach time.
- The `review` scope admits only `GET /api/v1/whoami` and `POST /api/v1/review-receipts`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`: image tag `4.153.0`, so #917 is
  deployed. A grep for `REVIEW_WORKER_INGEST` and `review-worker` across `platform-gitops/` matched only
  proposal documents, never deployed config, so the worker route answers `501
  review_worker_ingest_disabled` today.
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/`: profiles `authoring-canary-default`,
  `implementer-default`, `incident-responder-default`, `issue-investigator-default`, `mentor-default`,
  `scout-default`, `service-agent-default` and `shepherd-default`. There is no `independent-review` profile.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/`: there is no review-worker CWFT.
  `cwft-mctl-agents-investigate.yaml` shows the projected `mctl-api-run-token` SA token volume and the
  `execution_id` workflow parameter pattern.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-905-*/.status.yaml`: status `merged` (PR #971).
  Its `tasks.md` tasks 7, 8 and 9 are unchecked.
- `mctl_list_agents`: refused with "GET /api/v1/agents is outside the investigate scope". Whether
  `review-worker` is registered is therefore NOT observed (see Open questions in requirements.md).

## Proposed solution

### Shape

A new package, `orchestrator/review_worker/`, and a runner, `orchestrator/run_review_worker.py`. The runner
is the one place where the service credential and the run token meet. The model session never sees either.

```
run_review_worker.main(subject args, authoring_execution_id, work_item_id, author_actors)
  with evidence_producer.run("reviewer") as ev:
    1. authoring = api.authoring_facts(authoring_execution_id)        # service cred, GET provenance
    2. nonce = secrets.token_urlsafe(32)                                # memory only
       request = review_receipts.seal_request(subject, mode="worker", author_actors, nonce,
                                              authoring_execution_id, attempt_ids, lineage_root)
       api.open_request(request)                                       # service cred, POST review-requests
    3. reviewer = api.attach_reviewer(work_item_id, EngineRun(engine, engine_ref=<own workflow>#review), "review")
       independence.check_local(request, reviewer.provenance)           # guard A
    4. verdict = reviewer_session.run(subject_dir)                      # read-only SDK session
       draft = review_receipts.seal_receipt(...)                        # Tier A shape guard
    5. result = submitter.mint_and_submit(api, reviewer.execution_id, request, draft)  # guard B: token local
    6. if result.stored: ev.note_artifact_ref(result.receipt_id, "review-receipt", result.content_hash)
       ev.set_outcome(result.outcome_code)
```

### Modules

- `orchestrator/review_worker/contract.py` (pure)
  - `AGENT_NAME = "review-worker"`, `SCOPE = "review"`, `PROFILE = "independent-review"`, `TOKEN_TTL_SECONDS = 900`.
  - `Outcome` (frozen dataclass: `state` in `{stored, refused, disabled, unobserved}`, `code`, `http_status`,
    `receipt_id`, `content_hash`). Only `stored` carries a receipt. `disabled` and `unobserved` are distinct
    from `refused`, and none of them is `stored`.
  - `KNOWN_REFUSALS`: every #917 and #897 code, mapped to the status mctl-api documents
    (`review_nonce_consumed` 409, `review_nonce_mismatch` 403, `review_reviewer_ineligible` 403,
    `review_reviewer_not_independent` 409, `review_run_token_required` 403, `review_request_mode_manual` 409,
    `review_request_closed`, `review_request_not_found`, `review_binding_mismatch`,
    `review_execution_unproven`, `review_authoring_unresolved`, `review_request_conflict`,
    `review_not_permitted`, plus the Tier A codes). `UNOBSERVED_CODES`: `review_store_unavailable`,
    `review_provenance_unavailable`, `review_principal_unavailable`, `review_evidence_unavailable` and
    `agent_run_tokens_unavailable`.
  - `classify(status, payload) -> Outcome`, in this order:
    1. 201 with a valid body -> `stored`.
    2. 501 + `review_worker_ingest_disabled` -> `disabled`.
    3. 503, any 5xx, a typed unobserved code, transport error or bad JSON -> `unobserved`.
    4. A 4xx with a string `code` -> `refused(code)`. An unknown code is still `refused`.
    5. 401/408/429 -> `unobserved`, because they say nothing about the receipt (same reasoning as
       `answer_from_attach`).
  - `check_independent(request, reviewer_provenance) -> code | None`. It mirrors gate step 5 and #917 step 5:
    the execution id differs, the attempt id is not in the authoring attempts, the lineage root differs,
    and `attached_direct_service is True`.
- `orchestrator/review_worker/api.py`. An `httpx` client in the style of `delegated_approval.py`, with an
  injectable transport for tests.
  - `authoring_facts(execution_id)`: GET `/api/v1/executions/{id}/provenance`, service credential. It
    returns the attempt ids and lineage root, or raises `Unresolved("review_authoring_unresolved")`. An `ex-`
    id is refused locally.
  - `open_request(request)`: POST `/api/v1/review-requests`, service credential. The body is
    `request.to_dict()` without `created_at`. On 201 the server's `request_id` must equal the locally sealed
    `request_id`, otherwise `refused("review_request_conflict")`.
  - `attach_reviewer(...)`: delegates to `WorkContextClient.attach_execution`, then reads provenance for the
    new execution. Only `EXECUTION_ATTACHED` is usable. `EXISTING` means an earlier review attempt reused
    the engine run and is refused as `review_reviewer_not_independent`, never reused. The client is
    constructed with the static service credential explicitly (no `run_token.mctl_api_bearer`, no relay
    header), so the attach is direct-service.
  - `receipt_pool(subject)`: GET `/api/v1/review-receipts`, service credential, used only by the
    consumed-after-unobserved reconciliation.
- `orchestrator/review_worker/submitter.py`
  - `mint_and_submit(api, execution_id, request, draft) -> Outcome`. It asserts `execution_id` is a
    non-empty store id (guard B), then POSTs `/api/v1/agent-run-tokens` with `{agent: "review-worker",
    scope: "review", execution_id, ttl_seconds: 900, permissions: []}`. It checks that the answer has an
    `art_` token, `scope == "review"` and `execution_id == execution_id`. It POSTs
    `/api/v1/review-receipts` with Bearer `art_` and a body built by `worker_body(request, draft)`, which
    emits exactly the seven allowed keys. It revokes the token in `finally`. The token never leaves this
    function's locals. Errors carry the status and code only.
  - Retry: at most one retry with the same nonce after an `unobserved` submit. Then
    `review_nonce_consumed` -> `receipt_pool` reconciliation -> `stored` only if this `request_id` holds an
    `independent` receipt.
- `orchestrator/review_worker/session.py`. Runs the reviewer through `options.build_review_worker_options`,
  with the subject materialized read-only in a temp dir. The proposal bytes come from
  `read_proposal_content_digest`'s fetch, or the spike files read for `spike_report_digest`. The digest is
  re-verified locally against the subject before the session starts. It parses a strict JSON verdict
  (`outcome`, `criteria[{id,status}]`, `findings`). It writes `findings` bytes to the private artifact path
  and returns `findings_ref = ArtifactRef(name="review-findings.json", kind="review-findings",
  content_hash=hash_bytes(bytes))`. Findings text goes nowhere else.
- `orchestrator/options.py`. Adds `REVIEW_WORKER_TOOLS = ("Read", "Grep", "Glob")` and
  `build_review_worker_options(agent_dir, model)`, built through `_scrubbed` with `mcp_servers={}` and
  `setting_sources=["project"]`. Its env has `GH_TOKEN`, `GITHUB_TOKEN` and `MCTL_TOKEN` blanked in addition
  to `_scrubbed`. A PreToolUse policy checkpoint hook loads the `independent-review` policy, which denies
  every `github.*` action kind.
- `orchestrator/policy_checkpoint.py`. Adds a named policy `REVIEW_WORKER_POLICY`: default DENY, with no
  `github.*` ALLOW rule and no `mcp__mctl__*` rule. It is selected by `policyRef: independent-review`.
- `orchestrator/evidence_producer.py`.
  - `STAGES` gains `STAGE_REVIEWER = "reviewer"`.
  - New `RunEvidence.note_artifact_ref(name, kind, content_hash)` validates `content_hash` against
    `sha256:<64 hex>`. It is the hash-only twin of `note_artifact_file`, because a receipt is a server
    document, not a local file.
  - The envelope therefore carries `ArtifactRef(kind="review-receipt")` and, when present, the
    `review-findings` hash. It never carries text.
  - `note_work_execution(reviewer_execution_id, work_item_id)` ties the envelope to the reviewer `we_`.
- `agents/_manifests/review-worker/agent.yaml` and `agents/_review_worker/.claude/agents/review-worker.md`
  (the reviewer prompt: rubric ids per subject kind; it must answer `unobserved` instead of guessing).
- `docs/adr/025-independent-review-receipts.md` gets an amendment section, "Producer", that records the
  canonical name `review-worker`, the flow above and the refusal table.
- mctl-gitops companion PR (separate repository; the implementer drafts it, the operator merges it):
  - `agent-platform/execution-profiles/independent-review/profile.yaml`: `tools: [Read, Grep, Glob]`,
    `permissions.repository` all false, `mutationScopes: []`, `kubernetes: none`,
    `policyRef: independent-review`, `optionsBuilder: orchestrator.options:build_review_worker_options`.
  - `cwft-mctl-agents-review.yaml`: no `github-token` secret mount, mounts only the service credential and
    the evidence-writer token, and exposes an output artifact for findings.
  - The `REVIEW_WORKER_INGEST_ENABLED` switch is NOT part of this PR.

### Why guards are local as well as server-side

mctl-api refuses an ineligible or non-independent reviewer, but only after the request exists, and a
mis-attached execution would still be minted a token. The local checks (`check_independent` before mint,
the non-empty execution assertion in `mint_and_submit`, `worker_body`'s fixed key set, the capability
builder) fail earlier, spend no nonce, and are each pinned by a mutation test (tasks T6 to T9).

## Alternatives

1. **Run the reviewer as a DevLoop Temporal activity, like `submit_delegated_approve`.** It would give
   durable retries. Dropped for this slice: the gate is not wired into DevLoop (ADR 025 non-goal), and a
   Temporal activity inherits the DevLoop's engine run, which risks sharing the authoring attempt id. A
   standalone Argo Workflow has its own workflow name and therefore its own `attempt_id` by construction.
   The pure modules are reusable from an activity later.
2. **Exchange the pod SA token (`run_token.exchange`) instead of a service-principal mint.** Dropped: the
   exchange derives the execution from the Workflow parameters, and the issue requires the token to be
   minted for an execution the service principal attached directly, in the same run. The explicit mint
   binds the token to exactly the `we_` just attached, and lets the producer assert that binding.
3. **Two envelopes so the receipt can carry `evidence_ref`.** Seal an "inputs" envelope first, pass its
   `ev-` id as `evidence_ref`, and seal a second envelope with the receipt hash. Dropped for now: it doubles
   evidence writes, and the `ev-` id of an envelope that does not yet contain the outcome proves little.
   The single envelope -> receipt link is enough for audit, and the field stays empty, which Tier A
   permits. It is recorded as an open question.

## Platform impact

- **Migrations:** none in mctl-agents. mctl-gitops gains one profile and one CWFT, both additive. No mctl-api
  change.
- **Backward compatibility:** `evidence_producer.STAGES` gains a value, and `note_artifact_ref` is new;
  existing stages are untouched. `run_shepherd`, `GATING_BOTS` and `VERDICT_STATES` are unchanged. Nothing
  consumes the gate.
- **Behaviour while disabled:** the deployed route answers 501. A review-worker run ends `disabled` with
  outcome `review_worker_ingest_disabled`. The open review request and the attached execution remain
  (append-only server resources), but no receipt and no `review-receipt` artifact exist. The run is cheap
  to repeat after enablement because each run uses a fresh nonce and request.
- **Cost:** one model session per review (budget capped in the profile, proposed $2), plus about six
  mctl-api calls. The `review:` rate-limit group allows 30 per minute per principal.
- **Risks and mitigations:**
  - *Token leakage.* The token is held in locals of one function, `_scrubbed` env, no `os.environ`, revoked
    in `finally`, with a TTL of 900 seconds. A test asserts that the token string never appears in captured
    logs, the evidence envelope or the session options.
  - *Reviewer shares the authoring attempt.* The `engine_ref` is the review Workflow's own name, and the
    local check refuses before mint. `EXECUTION_EXISTING` is refused, never reused.
  - *Agent not registered or scope body field differs.* Both surface as typed refusals (`agent_unknown`,
    the mint's own code), never as success. The live-acceptance runbook lists registration as a
    precondition.
  - *Findings leakage.* There is no GitHub credential in the process, the policy denies `github.*`, and
    findings exist only as private artifact bytes plus a hash.
  - *Second active execution on the work item.* `409 execution_active` is a typed refusal. The runbook runs
    the reviewer after the authoring execution is terminal.
