# review-worker producer for autonomous independent review receipts

## Context

mctl-api 4.153.0 (mctlhq/mctl-api#917) accepts autonomous worker review receipts at
`POST /api/v1/review-receipts`. It admits only an execution-bound agent run token with scope `review` for
agent `review-worker`. The reviewer execution must have been attached by the service principal acting
directly (`attached_direct_service=true`), its attempt and lineage must differ from the authoring ones, and
the request nonce is single-use. The route answers `501 review_worker_ingest_disabled` until an operator sets
`REVIEW_WORKER_INGEST_ENABLED=true`. mctl-agents already has the pure Tier A contract
(`orchestrator/review_receipts.py`, ADR 025), but nothing in mctl-agents produces a worker receipt. Tasks 7
(reviewer principal and profile), 8 (reviewer run seals evidence) and 9 (live acceptance) of the merged #905
proposal are still open.

This proposal adds the producer: a `review-worker` run that does five things. It opens a worker-mode review
request for a proposal or spike subject, carrying the server-provable authoring facts. It has the service
principal directly attach a new, independent reviewer execution. It mints a `review`-scoped run token bound
to that execution. It runs a read-only reviewer session under a bounded `independent-review` capability set,
then submits the receipt and seals `ExecutionEvidence` with `ArtifactRef(kind="review-receipt")`. Every
mctl-api refusal is typed, and no unobserved or disabled answer is ever read as PASS or as "no receipt".
Without this producer the gate can never report `satisfied` with `assurance=independent`, and #905 cannot
reach live acceptance.

## User stories

- AS the platform owner I WANT an autonomous reviewer to issue independent receipts SO THAT a proposal or
  spike can satisfy the ADR 025 review gate without a human manual assertion.
- AS a security reviewer I WANT the reviewer run to hold no GitHub write, merge, label, comment or approval
  capability SO THAT a review run can never act on what it reviews or impersonate a `GATING_BOTS` login.
- AS an operator I WANT every mctl-api refusal surfaced as a typed outcome SO THAT a disabled route, a
  consumed nonce or an ineligible reviewer is distinguishable from a review that never happened.
- AS an auditor I WANT the reviewer run sealed as `ExecutionEvidence` linking the receipt hash SO THAT
  every receipt can be traced to the run that produced it, without findings text leaking into the envelope.

## Acceptance criteria (EARS)

Request
- WHEN the producer is invoked for a `proposal` subject (service, slug, gitops_commit, content_digest) or a
  `spike_report` subject (full SHAs and inventory digest) THE SYSTEM SHALL build it with
  `review_receipts.proposal_subject` / `spike_subject` and seal a `mode="worker"` request with
  `review_receipts.seal_request`, carrying `authoring_execution_id`, `authoring_attempt_ids`,
  `authoring_lineage_root` and `author_actors`.
- THE SYSTEM SHALL take `authoring_attempt_ids` and `authoring_lineage_root` from mctl-api's
  `GET /api/v1/executions/{id}/provenance` for the authoring execution, never from a caller-supplied string.
- IF the authoring execution id is empty, does not match the Tier A execution-id grammar, or its provenance
  cannot be read, THEN THE SYSTEM SHALL stop with `review_authoring_unresolved` before any request is
  created, any execution is attached or any token is minted.
- THE SYSTEM SHALL generate the nonce with a CSPRNG (at least 32 bytes), hold it only in process memory,
  and never log it, write it to a file, put it in evidence or pass it to the reviewer model session.

Reviewer execution
- WHEN the request is created THE SYSTEM SHALL attach a NEW execution for the reviewer run through
  `POST /api/v1/work-items/{id}/executions` with the service credential acting directly. It SHALL NOT use a
  relayed surface header, an agent run token, or a resume of the authoring execution.
- THE SYSTEM SHALL use an `engine_ref` whose engine run (the part before `#`) is the reviewer's own Argo
  workflow name, so that `execution_provenance.attempt_id(engine, engine_ref)` differs from every authoring
  attempt.
- IF the attached execution id equals the authoring execution id, or its provenance shows an `attempt_id` in
  `authoring_attempt_ids`, a `lineage_root` equal to `authoring_lineage_root`, or
  `attached_direct_service != true`, THEN THE SYSTEM SHALL stop with the matching local refusal
  (`review_reviewer_not_independent` or `review_reviewer_ineligible`) and SHALL NOT mint a token.

Token
- THE SYSTEM SHALL mint the run token only after a usable attach answer (`EXECUTION_ATTACHED`) has
  produced an execution id. It SHALL NOT call the mint route with an empty `execution_id`.
- WHEN minting THE SYSTEM SHALL request agent `review-worker`, scope `review`, `permissions: []`, the
  reviewer execution id and a TTL of at most 900 seconds. It SHALL hold the plaintext token only in a local
  variable of the one function that submits, never in the environment, a file, a log line, an exception
  message or the model session.
- IF the mint answer is not 201 with an `art_` token whose `execution_id` equals the reviewer execution
  THEN THE SYSTEM SHALL stop with a typed refusal or an unobserved outcome, and SHALL NOT submit.
- WHEN the producer finishes, however it finishes, THE SYSTEM SHALL revoke the token through
  `run_token.revoke` (best effort).

Capability bound
- WHILE the reviewer session runs THE SYSTEM SHALL grant only read-only tools (`Read`, `Grep`, `Glob`)
  over a local read-only copy of the subject. It SHALL grant no `Bash`, `Write`, `Edit`, `WebFetch` or MCP
  server, and no GitHub token in the session env.
- WHILE the reviewer process runs THE SYSTEM SHALL hold no GitHub write credential. The policy checkpoint
  SHALL refuse every `github.*` action kind (`github.git.push`, `github.pull_request.*`,
  `github.issue.comment`, `github.issue.label`, `github.actions.run.rerun`) for the `independent-review`
  profile.
- THE SYSTEM SHALL never post, comment, review, label or merge on GitHub from the review-worker. No login
  it can act as SHALL be in `run_shepherd.GATING_BOTS`.

Submit and seal
- WHEN the reviewer session returns THE SYSTEM SHALL validate its output into an outcome and rubric
  criteria with `review_receipts.seal_receipt` (Tier A shape check) before submitting. A Tier A refusal such
  as `review_pass_with_unobserved` or `review_rubric_mismatch` SHALL stop the run without submitting.
- WHEN submitting THE SYSTEM SHALL send exactly `request_id`, `subject`, `nonce`, `outcome`, `criteria`,
  `findings_ref` and `evidence_ref`. It SHALL NOT send any identity field: `reviewer_actor`,
  `reviewer_execution_id`, `attempt_id`, `lineage_root`, `assurance`, `mode` or `tenant`.
- THE SYSTEM SHALL keep findings text out of the request, the receipt body, the evidence envelope, logs and
  GitHub. `findings_ref` carries only `name`, `kind` and the sha256 `content_hash` of the private findings
  bytes.
- WHEN a receipt is stored (201) THE SYSTEM SHALL verify that the answer has `mode=worker`,
  `assurance=independent` and the submitted `request_id`. It SHALL then seal `ExecutionEvidence` for stage
  `reviewer` through `evidence_producer.run`, with `ArtifactRef(name=<receipt_id>, kind="review-receipt",
  content_hash=<receipt content_hash>)` and no findings text.

Typed refusals
- IF mctl-api answers `501` with `review_worker_ingest_disabled` THEN THE SYSTEM SHALL report outcome
  `review_worker_ingest_disabled`, store nothing locally, seal no `review-receipt` artifact, and exit
  non-success.
- IF mctl-api answers a typed 4xx refusal THEN THE SYSTEM SHALL report that exact code as a `refused`
  outcome. This covers at least `review_nonce_consumed`, `review_nonce_mismatch`,
  `review_reviewer_ineligible`, `review_reviewer_not_independent`, `review_run_token_required`,
  `review_request_mode_manual`, `review_request_closed`, `review_request_not_found`,
  `review_binding_mismatch`, `review_execution_unproven`, `review_pass_with_unobserved`,
  `review_rubric_mismatch`, `review_malformed`, `review_unknown_key`, `review_bad_subject`,
  `review_authoring_unresolved`, `review_request_conflict` and `review_not_permitted`.
- IF mctl-api answers 503 (for example `review_store_unavailable` or `review_provenance_unavailable`), an
  untyped 5xx, a transport error, a timeout or an unparseable body THEN THE SYSTEM SHALL report outcome
  `unobserved`. That outcome is never a PASS and never "no receipt".
- IF a typed 4xx code is not in the known table THEN THE SYSTEM SHALL report `refused` with that code. It
  SHALL NOT treat the answer as success.
- IF a submit was unobserved and a retry with the same nonce answers `review_nonce_consumed` THEN THE
  SYSTEM SHALL read the receipt pool with the service credential (`GET /api/v1/review-receipts`). It SHALL
  report `stored` only if a receipt for this `request_id` with `assurance=independent` is present, and
  `unobserved` otherwise.

## Out of scope

- Setting `REVIEW_WORKER_INGEST_ENABLED` in mctl-gitops (operator change).
- Any change to the mctl-api #917 contract, including the deferred same-tenant and retry-key questions.
- Wiring the review gate into `run_shepherd` merge gating or DevLoop. `GATING_BOTS` and `VERDICT_STATES`
  are unchanged.
- Owner triage (#907), remediation (#906), and the subscription or Codex reviewer host
  (mctlhq/mctl-gitops#2278, #908).
- Live acceptance itself (#905 task 9). It is an owner-gated step after release, deploy and enablement.
  This proposal only prepares its runbook.

## Open questions

- Is agent `review-worker` registered in the mctl-api agent registry? The mint refuses unregistered names
  with `400 agent_unknown`. This run could not observe the registry (`GET /api/v1/agents` is outside the
  investigate scope). Assumption: registration is done with `mctl_create_agent` before live acceptance, and
  until then the producer reports the typed `agent_unknown` refusal.
- Does `POST /api/v1/agent-run-tokens` take the scope as a body field (`"scope": "review"`), or does
  mctl-api derive it from the agent name? `delegated_approval.py` sends no scope today. Assumption: send
  `"scope": "review"` and verify the `scope` field of the answer. The implementer must confirm against
  mctl-api `handlers_agent_run_tokens.go` at 4.153.0.
- `evidence_ref` is a submit field, but the reviewer's own `ev-` id is only known after the envelope is
  sealed, and the envelope links the receipt hash. Assumption: submit `evidence_ref=""` and make the
  envelope -> receipt link (the `review-receipt` ArtifactRef) authoritative. The alternative is a
  two-envelope scheme (seal an input-evidence first), which is listed under Alternatives.
- Where do the private findings bytes live? Assumption: an Argo output artifact (private S3) of the
  review-worker Workflow, referenced only by hash. No public gitops, GitHub or envelope copy.
- Which work item does the reviewer execution attach to, and is a second concurrent execution on it
  allowed? Assumption: the authoring work item, attached after the authoring execution is terminal. A
  `409 execution_active` answer is reported as the typed refusal `execution_active`, with no retry loop.
- Who is the authoring execution for a proposal subject? Assumption: the work-item store `we_` of the
  authoring run, from the DevLoop `work_context` query. The producer takes it as an explicit argument and
  never guesses it. A runtime `ex-` id (for example `.status.yaml` `execution.context_id`) passes the Tier A
  grammar, but mctl-api holds no provenance for it. The producer therefore refuses it locally with
  `review_authoring_unresolved` instead of opening a request whose authoring facts cannot be proven.
