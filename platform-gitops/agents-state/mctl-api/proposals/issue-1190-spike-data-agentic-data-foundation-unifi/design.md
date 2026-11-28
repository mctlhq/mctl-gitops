# Design: issue-1190-spike-data-agentic-data-foundation-unifi

## Current state

Pinned: mctl-api `8e3b9b723b6be7cfb2e72748759d0ad489c8416a` (2026-11-28), mctl-gitops
`d947e47bd173627a6a636a818e258930babfc9c6`.

mctl-api is already a set of focused, PostgreSQL-backed, authoritative stores. Each one creates its
own schema at startup under an advisory lock (for example `principals.NewStore`, which takes
`pg_advisory_xact_lock(hashtext('principals-schema'))`) on pools shared through `internal/pgshared`.
mctl-api has no graph, RDF, vector or AGE dependency: a grep for `pgvector|apache_age|sparql|graphiti`
over `*.go` returns nothing. The stores relevant to an "agent-ready" read model (VERIFIED_CODE):

| Domain | Package / tables | IDs | Tenant boundary | Provenance / retention notes |
|---|---|---|---|---|
| Canonical identity | `internal/principals/store.go`: `principals`, `external_identities` | `prn_<ULID>`; `UNIQUE(provider, issuer, subject)` | Global principal; tenancy from gitops membership | `verified_at`, `revoked_at`. `display` is informational only (comment in schema). `customer_deletion.go`: `customer_deletions` |
| Surface identity crosswalk | `internal/surfaceid/store.go`: `surface_identity_links`, `surface_identity_challenges` | one surface-native id -> one human (`github:<login>` or `prn_`) | Per link | Package doc: "This is not a principal model (.github#91)" |
| Delegation | `internal/delegation/delegation.go` (store-free); `internal/workitems/delegation_grants.go` | grant refs | Tenant | Subject only from the ref and token binding, "no header value, no body field, no token claim" |
| Federation | `internal/auth` registry, `docs/federation.md` | `(provider, issuer, subject)` | n/a | `Verified` type cannot express "speaking for someone else" |
| Work context | `internal/workitems/store.go`: `work_items`, `work_item_events`, `work_item_intents`, `work_item_executions`, `work_item_surface_refs`, request tables | `wi_`, `we_`, `xr_` | `work_items.tenant`, `visibility`, `owner_principal` | `state_version`, `schema_version`. Intent `text` is nullable for a retention sweep (`text_redacted`) |
| ContextSnapshot | `internal/workitems/snapshots.go`: `work_item_context_snapshots` | `cs_` | via work item | `content_hash`, `canonical` bytes, `strategy`/`strategy_version`, `prior_snapshot_id`. An immutability trigger blocks updates. Cascades on work item delete |
| Execution evidence | `internal/evidence/*`: `execution_evidence`, `execution_evidence_refs` | `ev-` (Tier A seal reproduced) | Tenant | "References and hashes only, never a second copy". Own retention (`EVIDENCE_RETENTION_DAYS`, `cmd/api/main.go`) |
| Execution provenance | `internal/executionprovenance/provenance.go` | `attempt_id`, `lineage_root` | n/a (pure) | Pure contract, no I/O |
| Decisions | `internal/decisions/*`: `decision_records`, `decision_attempt_events` | decision ids; refs `aar_`, `ev-`, `ex-`, `inv_` | Tenant | "Digests and references only". Retention deletes whole decisions |
| Approvals | `internal/workitems/action_approvals.go` and siblings: `action_approval_requests` | `aar_` | Tenant | artifact hash, decided context digest |
| Review | `internal/reviewstore`, `internal/reviewreceipts`: `review_requests`, `review_receipts`, `review_nonce_consumptions` | `rr_` | Tenant | Manual advisory receipts never satisfy `independent` |
| Lifecycle ownership | `internal/lifecycle/*`: `lifecycle_ownership`, `lifecycle_events` | `(kind, id, phase)`, fencing epoch | n/a | Package doc: "deliberately NOT a second lifecycle database"; liveness derived on read. Separate DB (see deployed state) |
| Consent | `internal/glovoconsent/*`: `glovo_link_consents`, `glovo_access_*` | per principal | Principal | Versioned consent; revoked rows kept as history; lapses derived at read |
| Events | `internal/events/*`: `event_outbox`, `event_outbox_lease`; Valkey stream `mctl:events:github` | `event_id` unique | n/a | `mctl.events/v1` envelope is reference-only ("says which pull request changed ..., never what it contains") |
| Audit / usage / ops | `internal/audit` (`audit_events`, `redact.go`), `internal/usage` (`model_usage_records`), `internal/alerts` (`alerts`, `alert_evidence`), `internal/securityfindings` | various | Tenant | Redaction exists in audit |
| MCP read surface | `internal/mcp/server.go` tools; resources in `internal/mcp/resources.go` (overview, catalog) and `internal/mcp/stats.go` (stats MCP App `ui://mctl-stats/...`) | n/a | Caller-scoped | An MCP App runtime already exists and can be reused for a read-only inspector |

Observations that shape the decision:
1. mctl-api already applies the "silver/gold as logical, not physical copies" principle: evidence,
   decisions and events hold references and digests rather than copies. A new projection that copies
   content would reverse a deliberate, repeated design choice.
2. The identity crosswalk already exists and is explicit-only (`external_identities`,
   `surface_identity_links`). Nothing links on display name or email, and `display` is documented as
   informational.
3. Bitemporal fields are partial. There are `created_at`, `verified_at`, `revoked_at`, `state_version`
   and `schema_version`, but no common `valid_from/valid_to`, `as_of`, `confidence` or `assertion_kind`
   across stores. This is the real gap, and it is a vocabulary gap rather than a storage gap.
4. Retention is per store (`EVIDENCE_RETENTION_DAYS`, work-item retention, decision retention) and
   deletion cascades through `ON DELETE CASCADE` from `work_items`. Any projection must subscribe to
   those deletions or it becomes the "immutable PII lake" the issue forbids.
5. Reconstructing a DevLoop run (proposal -> approval -> execution -> review -> outcome) today means
   reading work items, executions, snapshots, evidence, decisions, approvals, review receipts and
   lifecycle ownership, plus GitHub and gitops `.status.yaml`. Each is reachable through existing
   REST/MCP routes, but no single documented trace contract marks missing or conflicting links.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml` (gitops `d947e47b`): the chart
  is at mctl-api `targetRevision ddb6f57e...`, image tag `4.181.0`, `replicaCount: 2`.
  `WORK_ITEMS_DB_URL` and `GLOVO_DB_URL` point at `shared-pg-rw.platform-db.svc:5432/mctl-api`.
  `LIFECYCLE_DB_URL` points at a separate database, `mctl-lifecycle`. `EVENTS_VALKEY_URL` points at
  `valkey.platform-events.svc`, and Temporal at namespace `mctl-agents`. VERIFIED_DEPLOYMENT for these
  env values. The deployed SHA `ddb6f57e` differs from the clone SHA `8e3b9b72`, so store behaviour
  described above is VERIFIED_CODE at the clone SHA, not proven identical in production.
- A grep of that manifest for `EVIDENCE_RETENTION_DAYS`, `EVIDENCE_DB_URL` and
  `MCTL_SUBMIT_CREATES_EXECUTION` found no explicit entries in the scanned ranges. Code defaults apply
  (evidence falls back to `AUDIT_DB_URL`; retention unset means disabled per
  `parseEvidenceRetentionDays`). Effective production values are UNKNOWN: they were not read from a
  running pod.
- `mcp__mctl__mctl_get_service_status(team=admins, service=mctl-api)` returned "ArgoCD application not
  found: admins-mctl-api". mctl-api is a platform app outside the tenant catalogue, so its live
  Argo health was not observed through this tool. This is UNKNOWN, not "absent".
- `$MCTL_GITOPS_ROOT/agents-state/*/proposals` listing: related proposals exist for mctl-api
  (`issue-227` work context, `issue-409` evidence persistence), mctl-agents (`issue-264` ContextSnapshot,
  `issue-265/266/267` context assembly/evals/resume, `issue-472/527/528` context platform,
  `issue-520/539` evidence, `issue-597` enterprise MCP context benchmark, `issue-670` decision context)
  and mctl-telegram (`issue-443` bind telegram threads, `issue-705` memory). Only directory names were
  read. Their contents are PROPOSED/UNKNOWN for this spike.
- Not available in this run: clones of mctl-telegram, mctl-agents, mctl-docs and .github. Their
  memory, MemoryStore, context control plane and corpus stores are UNKNOWN (see Open questions).

## Proposed solution

This spike produces a decision package only. All artifacts land in mctl-api under
`docs/research/agentic-data-foundation/` and a test-only harness under
`internal/research/agenticdata/` behind the build tag `research`. Nothing is wired into
`cmd/api/main.go`, the router or the MCP server. The MCP tool count in `server_test.go` is
unchanged.

### 1. Inventory and duplicate map (`inventory.md`, `owners.md`)
The table above is extended to every store and to the cross-repo sources. Each row gets an evidence
tag (VERIFIED_CODE / VERIFIED_DEPLOYMENT / PROPOSED / UNKNOWN), a file:line link and a pinned SHA. The
owner map assigns operational evidence/RCA to .github#342, business semantics/metrics to .github#339,
private agent memory to mctl-telegram#1488/#1325 and mctl-agents#989, public corpus to mctl-docs#237,
task graphs to mctl-agents#1127 and governed assistants to .github#309. #1190 owns only the shared
vocabulary, the provenance/trace contract and the decision.

### 2. Common vocabulary (`vocabulary.md`)
A logical model, not a schema:
- **Entity**: `{id, kind, tenant, authority_ref}`, where `authority_ref` names the authoritative store
  row (for example `principals:prn_...`, `work_items:wi_...`). Canonical authenticated principals
  (`prn_`) are a distinct kind from tenant-scoped external contacts and knowledge entities, which
  never carry authority.
- **Assertion** (attribute or edge): `{subject_id, predicate, object, tenant, assertion_kind
  (observed|user_confirmed|inferred), source_ref, evidence_digest, observed_at, valid_from,
  valid_to, as_of, classification (public|tenant|private|secret-excluded), confidence,
  schema_version, supersedes}`. Corrections append a new assertion with `supersedes`. Merges and
  splits are assertions on a crosswalk entity, reversible by superseding them. An `inferred`
  assertion can never be the source of an authorization or link decision.
- **Event**: reuse the `mctl.events/v1` envelope (reference-only, `event_id` dedupe via the
  `event_outbox_event_id` unique index) and add `observed_at` and `source_version` for ordering.
- Edge vocabulary for DevLoop: `proposed_by`, `approved_by (aar_)`, `executed_as (we_/ex-)`,
  `sealed_context (cs_)`, `evidenced_by (ev-)`, `decided_by (decision)`, `reviewed_by (rr_)`,
  `owned_by (lifecycle)`, `resulted_in (pr/merge)`.

### 3. Candidate architectures and the benchmark
- **A, baseline**: a test-only Go "trace composer" that answers each scenario by calling the existing
  store read methods (in-process against TEST_DATABASE_URL, including a second test database for
  lifecycle to mirror production) and joining in memory. It marks missing or conflicting links
  explicitly.
- **B, smallest candidate**: in the test database only, one schema `research_projection` with
  `assertions` and `edges` tables built idempotently from the same fixture. Built as SQL views first,
  then as a rebuildable table keyed by `(source_ref, evidence_digest)`. It is queried with
  `WITH RECURSIVE` for traversal. Apache AGE is noted only, not installed, unless recursive SQL fails
  a scenario.
- **C/D, optional local comparison**: Oxigraph (single binary) and Fuseki 2 + TDB2 with SHACL shapes
  for the same fixture, converted to RDF. Graphiti is evaluated as a dependency and semantics review
  only (it needs an LLM/embedder and a graph backend). Its measurements are UNKNOWN unless a model
  budget is granted.

Fixture (`testdata/fixture-v1/`, frozen, content-hashed): two synthetic tenants; principals with
explicit links plus decoy same-name/same-email contacts; two synthetic PA connector sources with a
conflicting preference; a consent grant that is revoked mid-scenario; a deletion request; one
DevLoop run with a deliberately missing review receipt and a conflicting approval digest; public doc
pages with an injected "ignore instructions" string; and duplicate plus out-of-order events.

Scenarios map 1:1 to the issue's acceptance checklist (PA, Identity, Consent/Deletion, DevLoop,
Knowledge, Replay). Metrics: exact-answer correctness, false links, leakage/unauthorized actions,
stale reads, P50/P95 latency over N >= 200 runs per scenario, query count, estimated tokens of the
returned context, storage bytes and deletion completeness. Every metric is MEASURED or UNKNOWN.

### 4. Security, consent and deletion rules (`threat-model.md`)
- Action-time authority stays with `principals`, delegation resolution (`internal/delegation`),
  `action_approval_requests` and `glovoconsent`. A projection value is never consulted for an
  allow decision, and a stale, missing or unreachable authority read fails closed. This mirrors the
  lifecycle tool rule that 503 means UNKNOWN, never UNOWNED.
- Deletion propagation: a projection row carries `source_ref`. A delete or cascade of the source
  (`work_items ON DELETE CASCADE`, decision retention, evidence retention, `customer_deletions`)
  must remove or tombstone it. The test checks for zero remaining rows that reference the subject.
- Secrets are excluded at build time using the existing `internal/secretscan` and audit
  `redact.go`. Retrieved content is data, never instructions. Feedback is stored as an assertion of
  kind `inferred` or `user_confirmed` with its own provenance and cannot change `assertion_kind` of
  another row.
- No arbitrary SPARQL/SQL from agents. Any later MCP surface is a bounded, parameterized, read-only
  tool or resource on the existing server (`internal/mcp`), and a provenance inspector would reuse
  the MCP App pattern in `internal/mcp/stats.go`.

### 5. Decision and failure criteria (`adr-candidate.md`, status Proposed)
Provisional outcome: **REUSE_EXISTING_APIS**, plus the vocabulary and a documented trace contract.
Escalate to **BOUNDED_POSTGRES_READ_MODEL** if, on the fixture, A fails any of:
- (f1) the DevLoop trace needs more than 2x B's queries, or misses a link that B finds;
- (f2) A's P95 for a trace exceeds 3x B's P95 (relative, from measurement, not an SLO);
- (f3) the PA preference with as-of freshness cannot be answered without a new cross-source join.
B itself fails, and a graph pilot is considered, only if recursive SQL cannot express a required
traversal or its P95 exceeds 3x the best of C. Any candidate fails outright on any leakage, false
link, unauthorized action or incomplete deletion. If the harness cannot be run, the outcome is
**DEFER**, with the reproducible plan and UNKNOWN measurements.

## Alternatives
- **Adopt a graph store now (C: Fuseki 2/TDB2 or Oxigraph).** Dropped as a default. It adds a
  second copy of tenant data with its own retention, deletion and access path. It duplicates
  authoritative stores that deliberately hold references only. SPARQL and OWL entailment widen the
  attack surface (unbounded queries, cross-tenant inference). Kept as a measured local comparison.
- **Adopt Graphiti (D) as shared memory.** Dropped. It is a memory runtime with LLM-driven
  extraction that would compete with mctl-telegram#1488 and mctl-agents#989. LLM-extracted edges are
  inferred by construction and must never become identity or authority.
- **Build a physical Bronze/Silver/Gold lake with CDC.** Dropped. It creates the unconditional PII
  lake the issue forbids. The existing `event_outbox` with a reference-only envelope already covers
  the incremental-signal need without content copies.
- **Do nothing (no vocabulary).** Dropped. The bitemporal and assertion-kind gap (observation 3) is
  real and would be filled ad hoc by each consumer.

## Platform impact
- Migrations: none. The `research_projection` schema exists only in the test database created by the
  harness and is dropped at teardown.
- Backward compatibility: no change to routes, MCP tools (count in `server_test.go` unchanged),
  helm chart or env vars.
- Resources: none in the cluster. Local benchmark only. Optional Oxigraph/Fuseki containers run on a
  developer machine, never in the cluster.
- Risks and mitigations:
  - Fixture accidentally contains real data. Mitigation: generated by a deterministic generator with
    a seed, checked by `internal/secretscan`, and reviewed.
  - The recommendation is read as implementation approval. Mitigation: the ADR status stays
    Proposed, and every follow-up is listed as a separate proposal needing owner approval.
  - The clone/deployment SHA gap (`8e3b9b72` vs `ddb6f57e`). Mitigation: the inventory tags both and
    re-pins at execution time.
  - Cross-repo inventory incomplete. Mitigation: UNKNOWN rows with an exact follow-up list.

## Open questions
- Cross-repo stores (mctl-telegram memory, mctl-agents context control plane/MemoryStore, mctl-docs
  corpus, .github#342 evidence graph) were not readable in this run. Follow-up evidence: pin main of
  each repo and read their store/schema packages and deployed values.
- Effective production values of `EVIDENCE_RETENTION_DAYS`, the work-item retention setting and
  `MCTL_SUBMIT_CREATES_EXECUTION` are UNKNOWN. They need a read of the rendered helm values or of a
  running pod's environment.
- Live Argo health of mctl-api was not observable with `mctl_get_service_status`. The platform Argo
  app name needs confirming.
- Local container use for C, and the model budget for D (see requirements.md).
- The relative thresholds f1-f3 need owner confirmation after the baseline run.
- Is a cross-database (`mctl-api` + `mctl-lifecycle`) read acceptable for B, or must B stay
  single-database and leave lifecycle to the API layer?
