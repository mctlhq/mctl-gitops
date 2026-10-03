# Durable execution-evidence store: persist and retrieve sealed `evidence.mctl.ai/v1alpha1` envelopes

## Context

Tier A of `mctlhq/mctl-agents#199` froze an execution-evidence envelope contract
(`evidence.mctl.ai/v1alpha1`, `orchestrator/execution_evidence.py` plus ADR 018 in
mctl-agents). Tier B — this proposal — gives those sealed envelopes a durable home in
mctl-api, next to the canonical platform state they reference: `work_items` /
`work_item_executions` (`we_`), `work_item_context_snapshots` (`cs_`),
`work_item_execution_requests` (`xr_`), `action_approval_requests` (`aar_`) and
`model_usage_records`. The earlier direction that wrote durable evidence into the public
`mctl-gitops` repository (`mctl-agents#483`, `orchestrator/evidence_store.py`, `_evidence/`)
is rejected and must not be restored.

This matters because today there is no single place that answers "what actually happened in
this governed run, sealed and tamper-evident, after Argo TTL and Temporal retention have
lapsed". `docs/work-context-contract.md` already makes that argument for work state;
`internal/workitems/snapshots.go` already implements the immutable-sealed-record pattern for
context snapshots; `internal/usage/store.go` already implements the insert-only,
deterministically-keyed, correlation-only ledger pattern for cost. Evidence is the third
member of that family, and it must be built with the same discipline: references and hashes
only, never a second copy of execution or work-item state.

The proposal must also answer an unresolved contract question. Tier A's
`ExecutionJoin.execution_id` expects the canonical work execution `we_`, but only
issue-investigator runs carry one today; implementer and shepherd runs, `POLICY_DECISION`
records and `action_approval_requests.execution_id` generally carry the runtime
`ExecutionContext` id `ex-` (ADR 011). The storage layer may not decide this on its own, and
must neither assume a `we_` exists nor store an `ex-` in a `we_` field. That question is
decided in mctlhq/mctl-agents#539 (the ADR 018 amendment), which is a **blocking
prerequisite** for approving and implementing this proposal; storage mirrors the join shape
the amended ADR fixes.

## User stories

- AS the future mctl-agents evidence producer I WANT a single idempotent endpoint that
  accepts a sealed envelope SO THAT a retried, replayed or duplicated governed run never
  creates a second evidence record and never fails the workflow it is observing.
- AS a platform admin auditing a governed mutation I WANT to retrieve evidence by the
  canonical execution reference, by `trace_id`, by Temporal workflow reference and by
  repository/issue/PR SO THAT I can reconstruct what a run did without reading Argo logs
  that have aged out.
- AS a platform admin I WANT a sealed envelope's identity and content hash recomputed
  server-side on every write and re-verified on every read SO THAT stored evidence is
  tamper-evident rather than merely claimed to be.
- AS a tenant member I WANT to read the evidence attached to a work item I can already see
  SO THAT governance is legible to the people whose work it governs, without exposing
  cross-tenant evidence.
- AS a platform architect I WANT evidence storage to mirror exactly the execution join that
  ADR 018 (as amended by mctlhq/mctl-agents#539) defines SO THAT storage never pre-empts or
  silently redefines the envelope's identity semantics.
- AS an operator I WANT an absent evidence record to read as an explicit, distinguishable
  absence SO THAT "the producer never wrote evidence" is never confused with "the evidence
  store is not configured".

## Acceptance criteria (EARS)

### Ingest and identity (Tier A's algorithm, exactly)

- WHEN a caller holding `evidence:write` POSTs a sealed envelope to
  `POST /api/v1/evidence/records` THE SYSTEM SHALL validate it, recompute its
  `content_hash` and `evidence_id` with Tier A's sealing algorithm, store the received bytes
  verbatim and answer `201` with the stored record.
- WHEN an envelope's `api_version` is not in the server's supported set
  (`evidence.mctl.ai/v1alpha1`), or its `kind` does not match that version, THE SYSTEM
  SHALL reject the write with `400` and code `evidence_unsupported_api_version`, naming the
  versions it does support.
- WHEN an envelope arrives THE SYSTEM SHALL compute `content_hash` exactly as Tier A's
  `seal()` does:
  - take `sha256` over the canonical JSON of the envelope object minus `evidence_id`,
    `content_hash` and `created_at`, with empty optional blocks omitted;
  - use the canonical JSON rule of `context_snapshot._canonical_json`: sorted keys,
    `(",", ":")` separators, `ensure_ascii`, no HTML escaping, no NaN;
  - derive `evidence_id` as `"ev-" + content_hash[7:23]`.
- IF the envelope has unknown keys or duplicate keys, or is not valid JSON, THEN THE SYSTEM
  SHALL reject the write with `400` and code `evidence_invalid`.
- IF the envelope's own `content_hash` or `evidence_id` does not equal the value the server
  recomputes THEN THE SYSTEM SHALL reject the write with `400` and code
  `evidence_hash_mismatch`, echoing both the submitted and the recomputed value.
- WHILE an evidence record exists THE SYSTEM SHALL treat its `ev-` id as its immutable
  primary key and its `content_hash` as unique.
- WHEN the store reads an evidence record THE SYSTEM SHALL recompute the Tier A content hash
  of the stored bytes. IF it differs from the stored `content_hash` THEN THE SYSTEM SHALL
  refuse to serve the row as that evidence, mirroring `scanSnapshot` in
  `internal/workitems/snapshots.go`.

### Idempotency and conflict

- WHEN an envelope arrives whose `content_hash` equals a stored record's THE SYSTEM SHALL
  store nothing new and SHALL answer `200` with the already-stored record. This holds
  whether the bytes are identical or differ only in `created_at`, which Tier A excludes from
  the hash precisely so that a re-seal is the same evidence. The first stored bytes win.
- IF a write presents an existing `ev-` id with a different `content_hash` THEN THE SYSTEM
  SHALL reject it with `409` and code `evidence_divergence`, and SHALL NOT modify the stored
  row. This case is a 64-bit id-prefix collision between different content.
- WHILE any evidence row exists THE SYSTEM SHALL refuse every `UPDATE` of it at the database
  level via a `BEFORE UPDATE` trigger, in the same shape as
  `work_item_context_snapshots_no_update`.

### Content discipline

- WHEN an envelope exceeds the configured maximum size THE SYSTEM SHALL reject the write
  with `400` and code `evidence_too_large`, and SHALL NOT store a truncated record.
- WHEN an envelope's canonical bytes match a known secret pattern THE SYSTEM SHALL reject
  the write with `400`, reusing the existing `internal/secretscan` scanner already relied on
  by `workitems.ErrSecretInText`.
- WHILE evidence is stored THE SYSTEM SHALL persist only the sealed envelope's own
  references and hashes plus server-owned ingest provenance, and SHALL NOT copy prompts,
  tool payloads, artifact bodies, execution phase, work-item lifecycle state or approval
  state into the evidence tables.

### The `we_` / `ex-` split (ADR 018 Amendment 1, mctlhq/mctl-agents#539, merged)

- WHEN an envelope is stored THE SYSTEM SHALL copy `execution.execution_id` and
  `execution.runtime_execution_id` verbatim into two separate typed columns.
- WHEN an envelope is stored THE SYSTEM SHALL validate the join with Tier A's rules:
  - `execution_id` is blank or starts with `we_`;
  - `runtime_execution_id` is blank or is `ex-` followed by 16 lowercase hex characters;
  - at least one of the two is non-blank.
- IF the join violates any of those rules THEN THE SYSTEM SHALL reject the write with `400`
  and code `evidence_execution_ref_invalid`.
- WHEN computing `content_hash` THE SYSTEM SHALL apply Tier A's leaf rule: a blank
  `runtime_execution_id` is absent from the hashed payload, and `execution_id`,
  `work_item_id` and `trace_id` are always present.
- WHEN an admin filters by `execution_id` or by `runtime_execution_id` THE SYSTEM SHALL
  return every envelope carrying that identity, including a both-identities envelope looked
  up by its runtime id.
- WHILE storing or deriving references THE SYSTEM SHALL NOT classify, translate or map one
  execution identity shape into another, and SHALL NOT store a discriminator. The
  `primary_execution_ref` returned on reads is derived at read time.
- IF canonical state cannot resolve an envelope's valid join to a work item THEN THE SYSTEM
  SHALL store the evidence anyway with an empty derived projection.

### Retrieval and authorization

- WHEN an admin requests `GET /api/v1/evidence/{id}` THE SYSTEM SHALL return the wrapper and
  the verbatim envelope bytes, base64-encoded, so that the hash survives JSON re-encoding.
- WHEN an admin requests `GET /api/v1/evidence` with any combination of the supported
  filters (`execution_id`, `runtime_execution_id`, `trace_id`, `engine` + `engine_ref`, `work_item_id`,
  `repository` + `issue`, `repository` + `pr`) THE SYSTEM SHALL return a list-shaped
  response whose shape does not depend on which filters were supplied.
- WHEN a caller requests `GET /api/v1/work-items/{id}/evidence` THE SYSTEM SHALL apply the
  existing `visibleWorkItem` / `canSeeWorkItem` check from
  `internal/api/handlers_work_items.go` and SHALL answer `404` rather than `403` when the
  caller may not see the work item.
- WHILE an evidence record has no resolved work item THE SYSTEM SHALL make it readable to
  admins only.
- IF a caller lacks `evidence:write` THEN THE SYSTEM SHALL reject the ingest with `403`.
- WHILE the dedicated evidence-writer principal is authenticated THE SYSTEM SHALL confine it
  to `POST /api/v1/evidence/records` and answer `403` on every other route, mirroring
  `usageWriterGate` in `internal/api/handlers_usage.go`.
- WHEN an evidence write is accepted THE SYSTEM SHALL record an audit entry naming the evidence id, the primary execution identity and the ingesting principal.

### Availability, gaps and retention

- IF the evidence store is not configured THEN THE SYSTEM SHALL answer `503` with code
  `evidence_store_unavailable` on every evidence route, and SHALL NOT answer an empty list.
- WHEN a lookup finds no evidence for an existing execution reference THE SYSTEM SHALL
  answer `404` with code `evidence_not_found`, a status distinct from the `503` above, so a
  producer gap is observable rather than silent.
- WHILE `EVIDENCE_RETENTION_DAYS` is unset or zero THE SYSTEM SHALL retain evidence
  indefinitely.
- WHEN `EVIDENCE_RETENTION_DAYS` is set and a sweep runs THE SYSTEM SHALL delete whole
  evidence rows older than that age and SHALL NOT partially redact a retained row.
- WHILE evidence exists THE SYSTEM SHALL keep it exclusively in mctl-api's PostgreSQL
  storage and SHALL NOT write any part of it to a GitOps or public repository.

## Out of scope

- The evidence producer in mctl-agents (a separate `#199` child).
- Any change to approval semantics in `internal/workitems/action_approvals.go`.
- A new execution identity system; no third identifier is minted.
- Raw telemetry, artifact payload or transcript storage.
- Public GitOps persistence of evidence, in any form.
- Dashboards, UI or MCP tools. In particular, no MCP tool is added, so the tool-count
  expectation in `internal/mcp/server_test.go` stays untouched (`CLAUDE.md`).
- The final live proof that closes `mctl-agents#199`.
- Changing or extending the `evidence.mctl.ai/v1alpha1` envelope contract itself.

## Open questions

- **The `ev-` derivation is no longer open.** It is Tier A's algorithm, pinned in the
  acceptance criteria above and in `design.md` section 2, and it is proven by ported golden
  vectors.
- **The `we_` / `ex-` join model is settled.** mctlhq/mctl-agents#539 merged ADR 018
  Amendment 1 (model B, two typed fields, `v1alpha1`, hash-neutral). This proposal mirrors
  it.
- **Whether a runtime `ex-` can be resolved to a `we_` inside mctl-api today.** Nothing in
  this clone maps an `ex-` to a work execution; `internal/usage/types.go` explicitly accepts
  both shapes in one correlation column and resolves neither. The design therefore leaves
  `work_execution_id` empty for runtime references and treats any future resolver as an
  additive, rebuildable projection.
- **Tenant attribution for runtime-referenced evidence.** With no resolvable work item there
  is no tenant, so such records are admin-only. Whether governed runtime executions should
  later carry a tenant claim in the envelope is an ADR 018 question, not a storage one.
- **Batch ingest.** Deliberately single-envelope-per-request, because per-envelope conflict
  reporting must be unambiguous. If producer volume ever justifies batching, it is additive
  and can follow the `usage.IngestResult` accepted/deduped shape.
