# Auditable execution evidence for governed agent runs

## Context

mctl-agents now has four of the five inputs an after-the-fact audit needs, and
none of them is joined to the others. Execution traces exist in code
(`orchestrator/tracing.py`, `docs/observability/execution-traces.md`) but
**nothing is exported in production**: the platform Collector has no trace
backend, the choice is still open (mctl-gitops#1280), the batch processor drops
spans when its 2048-span queue fills, and the export guard deliberately strips
the target of a policy decision. Execution identity is sealed and
content-addressed (`orchestrator/execution_identity.py`, ADR 011). Policy
decisions are evaluated fail-closed and printed as one `POLICY_DECISION <json>`
line per decision (`orchestrator/policy_checkpoint.py`, ADR 014). Durable
single-use approvals live in mctl-api and are redeemed at decision time
(`orchestrator/action_approvals.py`, mctl-api#366). Model usage and cost are
recorded nowhere at all today — ADR 012 is the contract, `usage-ledger` is not
built.

Issue #199 asks for the record that joins them: one immutable, versioned,
queryable document per governed execution that answers "what happened, under
which policy, who approved it, and what did it produce" — derived from what the
run already knows, not by duplicating raw telemetry. ADR 009 already reserved
the seam: `ContextSnapshot.evidence_refs` carries `{evidence_id, kind}` and
says "#199 owns the referent"
(`docs/adr/009-context-snapshot-contract.md:91,136,230`). This proposal defines
that referent, the contract module that seals it, the recording points, the
storage and retrieval path, and the completeness check that notices a governed
mutation with no policy decision behind it.

## User stories

- AS a platform owner I WANT one evidence document per governed execution SO
  THAT I can reconstruct what an autonomous agent did without reading pod logs
  that have already rotated.
- AS an incident responder I WANT to fetch the evidence for a workflow id SO
  THAT I can see the actions, decisions, approvals and artifacts of the run
  that caused the incident in one place.
- AS a security reviewer I WANT every consequential mutation linked to the
  policy rule that permitted it and, where gated, to the approval receipt and
  approver SO THAT "it was authorized" is a checkable claim rather than an
  assertion.
- AS a policy author I WANT the record to name the exact policy version and
  rule id that decided each action SO THAT I can tell which runs a policy
  change would have affected.
- AS an operator I WANT the record to flag its own gaps SO THAT an evidence
  document that is missing a decision is visibly incomplete instead of silently
  reassuring.
- AS a maintainer I WANT the record to carry digests and references instead of
  payloads SO THAT storing it durably never turns it into a secret store.

## Acceptance criteria (EARS)

### Shape and identity

- WHEN a governed execution finishes THE SYSTEM SHALL seal exactly one
  `ExecutionEvidence` document carrying `api_version`
  (`evidence.mctl.ai/v1alpha1`), `kind`, `evidence_id`, `content_hash`,
  `created_at`, and the sections `execution`, `identity`, `models`, `actions`,
  `approvals`, `artifacts`, `evaluations`, `completeness`, `outcome` and
  `retention`.
- WHEN a document is sealed THE SYSTEM SHALL derive `content_hash` as
  `"sha256:" + hex` over the canonical JSON of every field except `created_at`,
  and `evidence_id` as `"ev-" + content_hash[7:23]`, using
  `context_snapshot.canonical_json` / `hash_bytes` so the encoding matches the
  snapshot and approval-intent encodings already in the repo.
- WHILE a document exists THE SYSTEM SHALL treat it as immutable: a correction
  is a new document with a new `evidence_id`, never an edit.
- WHEN a document is parsed by `from_dict` THE SYSTEM SHALL reject any key the
  contract does not declare, and SHALL reject an unsupported `api_version`.
- IF `recompute_content_hash` disagrees with the stored `content_hash` THEN THE
  SYSTEM SHALL treat the document as untrusted and report it as such rather
  than returning it as evidence.

### Derivation from existing sources

- WHEN the sealed execution context is available from
  `MCTL_EXECUTION_CONTEXT_FILE` THE SYSTEM SHALL populate `execution` and
  `identity` from it: `trace_id`, `context_id`, `workflow_type`,
  `correlation.temporal_workflow_id`, `correlation.temporal_run_id`,
  `correlation.argo_workflow_name`, `correlation.attempt`, `actor.{type,id,
  verification}`, `executor.{type,id,agent,version,image_ref,binding}` and the
  scope's environment.
- IF no control-plane context is available THEN THE SYSTEM SHALL still seal a
  document, mark `identity.context_trust` as `unverified`, and record a
  completeness gap with code `identity_unavailable`.
- WHEN a policy decision is made through `policy_checkpoint.decide()` THE
  SYSTEM SHALL append one entry to `actions` carrying `action_kind`,
  `operation`, `target_ref`, `args_digest`, `action_digest`, `policy_version`,
  `rule_id`, `decision`, `code`, `approval_ref` and `permitted` — the same
  fields the `POLICY_DECISION` line already prints, plus the boolean derived
  from `code in {allowed, approved}`.
- WHEN an action's `code` is `approved` THE SYSTEM SHALL resolve the receipt
  named by `approval_ref` and append an `approvals` entry with the receipt id,
  `intent_hash`, state, approver identity, `decided_at` and `consumed_at`, and
  SHALL link the action entry to it by receipt id.
- IF the approval receipt cannot be resolved THEN THE SYSTEM SHALL keep the
  action entry, record the receipt id alone, and record a completeness gap with
  code `approval_unresolved`.
- WHEN a model turn completes inside an observed SDK session THE SYSTEM SHALL
  add or update a `models` entry keyed by `(provider, model)` with turn count
  and summed input/output token counters, reading only the fixed vocabulary
  `tracing.AgentRunObserver` already reads.
- WHEN ADR 012's usage ledger exists THE SYSTEM SHALL carry its record
  reference on the `models` entry rather than recomputing cost.
- WHEN the run publishes a proposal artifact THE SYSTEM SHALL record `name`,
  `kind`, `content_hash` (`sha256:` over the bytes written), `byte_count` and a
  bounded `locator` (gitops repo-relative directory plus commit SHA when
  known), never the file contents.
- WHEN the implementer pushes a branch, opens a PR or the shepherd merges one
  THE SYSTEM SHALL record those as artifacts of kind `branch`, `pull_request`
  and `merge_commit` identified by `owner/repo`, ref and SHA.

### Completeness, evaluations and outcome

- WHEN a governed transport performs a mutation THE SYSTEM SHALL require a
  recorded decision for the same `action_digest`, and IF none exists THEN THE
  SYSTEM SHALL record a completeness gap with code `mutation_without_decision`
  naming the action kind and operation.
- WHILE a transport is outside the checkpoint's reach (the agent's own shell,
  ADR 014 open decision 4) THE SYSTEM SHALL record a standing gap with code
  `ungoverned_transport` rather than reporting coverage it cannot prove.
- WHEN `completeness.gaps` is empty THE SYSTEM SHALL set `completeness.status`
  to `COMPLETE`, and otherwise to `INCOMPLETE`.
- WHEN a document is sealed THE SYSTEM SHALL emit an `evaluations` entry
  `policy_compliance` with `PASS` only IF every recorded mutation is permitted
  by a linked decision AND `completeness.status` is `COMPLETE`, and `FAIL`
  otherwise.
- WHEN the run ends THE SYSTEM SHALL set `outcome.status` to exactly one of
  `SUCCESS`, `FAILURE`, `REFUSED`, `UNDECIDED` or `SKIPPED`, with a bounded
  `code` and no free-text message.
- IF a checkpoint answered with an undecided code (`evaluator_error`,
  `identity_unavailable`, `approval_lookup_error`) THEN THE SYSTEM SHALL record
  the action with that code and SHALL NOT classify the run as `REFUSED` on its
  account.

### Redaction and retention

- WHILE assembling any field THE SYSTEM SHALL refuse prompts, completions,
  tool arguments and results, issue and comment bodies, argv, commit messages,
  file contents, stdout/stderr and credentials, and SHALL carry a digest or a
  bounded reference in their place.
- WHEN a `target` is not a closed, already-public shape (a github.com issue/PR
  URL, `owner/repo`, `owner/repo:<ref>`, an `aar_`/`we_`/`cs-` id, or an
  mctl-api operation id) THE SYSTEM SHALL store `target_digest` instead of
  `target_ref`.
- IF any string value matches a credential shape or exceeds 256 characters
  THEN THE SYSTEM SHALL drop it rather than truncate or mask it, matching the
  export guard's rule in `tracing_sdk.py`.
- WHEN a document is sealed THE SYSTEM SHALL carry a `retention` block using
  ADR 009's vocabulary (`class` in `telemetry | execution-record | gitops`,
  `expires_after_days`) so the store that holds it knows how long to keep it.

### Storage, retrieval and export

- WHEN a document is sealed THE SYSTEM SHALL persist it under a deterministic,
  collision-free path derived from the workflow id and the evidence id, and
  SHALL write a `by-trace` pointer so the same document is reachable from the
  trace id.
- WHEN an operator asks for a workflow id or a trace id THE SYSTEM SHALL return
  every evidence document of that workflow or trace, newest attempt first.
- WHEN a document is exported THE SYSTEM SHALL emit the canonical JSON of the
  sealed document unchanged, so the exported bytes re-hash to its
  `content_hash`.
- WHEN a run finishes THE SYSTEM SHALL print one `EXECUTION_EVIDENCE <json>`
  summary line (ids, counts, completeness status, outcome) following the
  structured-log convention of `lifecycle/claim.py`'s `_emit` and
  `policy_checkpoint`'s `POLICY_DECISION`.
- IF sealing, persisting or emitting evidence fails THEN THE SYSTEM SHALL log
  once and let the run continue with its own result unchanged: evidence never
  fails a run, and never changes an exit code.

## Out of scope

- Any change to what the policy decides. Rules, verdicts and the built-in
  `mctl-agents/policy/v1` table are ADR 014's, not this proposal's.
- Building the mctl-api evidence store, its HTTP surface or its retention
  enforcement. This proposal pins the contract, the id format and the export
  bytes so that store is additive; the cross-repo work is a follow-up issue.
- Choosing or wiring a trace backend (mctl-gitops#1280) and anything on #195's
  live-evidence checklist.
- Implementing ADR 012's usage ledger or any cost computation. Evidence carries
  the token counters it can already see and a reference slot for the ledger.
- The #198 Temporal approval wait, the approval UI and the mctl-api signal.
- Governing the agent's own Bash transport (ADR 014 open decision 4). This
  proposal only makes the blind spot visible in the record.
- A dashboard, UI or compliance report over evidence documents.

## Open questions

- **Primary store.** This proposal persists to the gitops agents-state tree
  because that is the only durable store mctl-agents already writes to from
  every agent pod, and ADR 009 already names `gitops` as a retention class.
  mctl-api is the better long-term home (it already holds work items,
  executions and approvals). Proceeding with gitops now and a schema shaped for
  a byte-identical mctl-api import later.
- **Retention defaults.** The issue asks for "retention/redaction expectations"
  without numbers. Proceeding with `class: gitops`, `expires_after_days: 3650`
  for the sealed document, on the grounds that it holds digests and public refs
  only. A shorter class can be set per workflow type later without a schema
  change.
- **One document per execution or per workflow.** A DevLoop spans several
  executions (investigate, implement, shepherd) under one workflow id. The
  issue's example reads like one record per run. Proceeding with one document
  per *execution*, joined by `execution.temporal_workflow_id` and `trace_id`; a
  per-workflow rollup is a read-side concern and is left to the retrieval API.
- **Evidence for ungoverned runs.** The mentor has MCP tools but no hooks (ADR
  014 open decision 2). Proceeding by sealing evidence for it too, with the
  standing `ungoverned_transport` gap, rather than omitting the run entirely.
- **Approver identity source.** mctl-api's approval record is the authority for
  who approved. Proceeding by copying whatever principal identifier the
  `GET /action-approvals/{id}` payload exposes, and recording
  `approver: "unknown"` with a gap if it exposes none.
