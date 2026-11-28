# Design: issue-1190-spike-data-agentic-data-foundation-unifi

Revision R2. It supersedes the HOLD proposal (artifact sha256:6540e0c7...). The research-only
scope is unchanged.

## Current state

### Pins
| Repo | SHA | How read |
|---|---|---|
| mctl-api | `8e3b9b723b6be7cfb2e72748759d0ad489c8416a` | local read-only clone |
| mctl-gitops | `5affc672d179b25dc7196eebfedc6883aa5cdcaa` | `$MCTL_GITOPS_ROOT` checkout |
| mctl-agents | `935b959ab9f46fa8232b0b15df5215848119c5a8` (main) | read-only GitHub API (`gh api .../contents?ref=`) |
| mctl-telegram | `13fd2333a041c3a0a2634db29879bfa116250bf6` (main) | read-only GitHub API |
| mctl-docs | `c63588bf3c3779494df299487c6761cd71738836` (main) | read-only GitHub API |
| .github | `233dc60548ae628b3a9a6804d15fd85dd90adf48` (main) | read-only GitHub API (issue metadata only) |

The deployed mctl-api chart revision is `ddb6f57e6755...` and the image tag is `4.181.0`, per the
manifest (see Deployed state). That differs from the clone SHA, so every mctl-api row below is
VERIFIED_CODE at `8e3b9b72`. None of them is proven identical to what runs in production.

### mctl-api authoritative stores (VERIFIED_CODE)
mctl-api is a set of focused PostgreSQL stores. Each one creates its own schema at startup on pools
shared through `internal/pgshared`. A grep for `pgvector|apache_age|sparql|graphiti|rdf` over the
Go code finds nothing: there is no graph, RDF or vector dependency.

| Domain | Package / tables | IDs | Tenant scope | Provenance / time / retention |
|---|---|---|---|---|
| Canonical identity | `internal/principals/store.go`: `principals(kind human/agent/service, status)` and `external_identities UNIQUE(provider,issuer,subject)` | `prn_<ULID>` | global principal; tenancy from gitops membership | `verified_at`, `revoked_at`; the schema comment says `display` is "Informational only". `customer_deletion.go` holds `customer_deletions` |
| Surface crosswalk | `internal/surfaceid/store.go`: `surface_identity_links`, `surface_identity_challenges` | one live link per `(surface, external_id)` (partial unique index) | per link | `created_at`, `expires_at`, `revoked_at`, `revoked_by` (`system:expired`). The link is created by a challenge code, which makes it explicit and never inferred |
| Delegation | `internal/delegation/delegation.go` (store-free); `internal/workitems/delegation_grants.go` | grant ref | tenant | The package doc says no "header value, no body field, no token claim" may produce a subject |
| Work context | `internal/workitems/store.go`: `work_items`, `work_item_events`, `work_item_intents`, `work_item_executions`, `work_item_surface_refs`, idempotency tables, `execution_provenance` | `wi_`, `we_`, `xr_` | `work_items.tenant`, `visibility`, `owner_principal(_id)` | `state_version`, `schema_version`. Intent `text` is nullable so a retention sweep can redact it. Child tables cascade with `ON DELETE CASCADE` |
| ContextSnapshot | `internal/workitems/snapshots.go`: `work_item_context_snapshots` | `cs_` | via work item | `content_hash`, `canonical BYTEA`, `strategy(_version)`, `prior_snapshot_id`. A trigger refuses UPDATE. Snapshots cascade on work-item delete |
| Execution evidence | `internal/evidence/store.go`: `execution_evidence` (immutable trigger) and `execution_evidence_refs` | `ev-`, `ex-<16hex>` | `refs.tenant` | The comment calls `execution_evidence_refs` a "Rebuildable index projection ... It has no authority". There is deliberately no FK to work items. `EVIDENCE_RETENTION_DAYS` sweep is in `cmd/api/main.go:3172-3230` |
| Decisions | `internal/decisions/store.go`: `decision_records` (verdict allow/deny/require_approval, `*_digest`), `decision_attempt_events` | decision id; refs `aar_`, `ev-`, `ex-`, `inv_` | `tenant` | There is no FK "a decision must not die with a work-item purge". `DECISIONS_RETENTION_DAYS` sweep is in `cmd/api/main.go:849` |
| Approvals | `internal/workitems/action_approvals.go` (`action_approval_requests`), deploy, glovo and basket approvals | `aar_` | tenant | artifact hash and decided context digest |
| Review | `internal/reviewstore/store.go` (`review_requests`, `review_receipts`, `review_nonce_consumptions`), `internal/reviewreceipts` (pure) | `rr_` | tenant | A manual advisory receipt never satisfies `independent` |
| Lifecycle ownership | `internal/lifecycle/store.go` (`lifecycle_ownership`, `lifecycle_events`) | `(kind,id,phase)`, fencing epoch | n/a | Liveness is derived on read. It lives in a separate database (manifest) |
| Consent | `internal/glovoconsent/postgres.go` (`glovo_link_consents`), `access.go` (`glovo_access_requests/events/meta`), `notify.go` | per principal | principal | versioned; revoked rows kept as history |
| Events | `internal/events/outbox.go` (`event_outbox UNIQUE(event_id)`, lease), `envelope.go` | `event_id` | n/a | `mctl.events/v1` is reference-only: the envelope "says which pull request changed ... never what it contains" |
| Ops / usage / audit | `internal/audit` (`audit_events`, `redact.go`), `internal/usage` (`model_usage_records`), `internal/alerts`, `internal/securityfindings`, `internal/secretscan` | various | tenant | Audit already has redaction, and `secretscan` exists |
| MCP read surface | `internal/mcp/server.go` (read tools such as `mctl_get_work_item`, `mctl_list_work_item_snapshots`, `mctl_get_lifecycle_ownership`, `mctl_get_review_gate`, `mctl_get_epic_status`); `internal/mcp/resources.go` (overview and catalog resources); `internal/mcp/stats.go` (MCP App `ui://mctl-stats/view-3.html`) | n/a | caller-scoped | An MCP App runtime already exists |

Observations that drive the design:
1. **References, not copies.** Evidence, decisions and events already store references and digests
   instead of content. `execution_evidence_refs` is already a rebuildable, non-authoritative
   projection. That is the precedent B would follow: a projection is an index, never an answer.
2. **The identity crosswalk is explicit-only.** `external_identities` is unique on
   `(provider, issuer, subject)`. `surface_identity_links` are created only from a challenge.
   Nothing links on display name or email.
3. **The real gap is vocabulary, not storage.** There is no common `valid_from/valid_to`, `as_of`,
   `assertion_kind (observed|user_confirmed|inferred)`, `confidence` or `classification` across
   stores.
4. **Retention is per store, and one sweep could not be found.** Evidence and decision retention
   sweeps exist. The `WORKITEM_RETENTION_DAYS` purge is cited only in a comment
   (`internal/evidence/store.go:44`); the code shows no implementation. Deletion propagation into
   any projection therefore has to be driven by source deletion and tombstones, not by an assumed
   purge.
5. **DevLoop reconstruction needs eight-plus stores.** Reconstructing proposal, approval,
   execution, review and outcome reads `work_items`, executions, snapshots, evidence, decisions,
   approvals, review receipts and lifecycle (a second database), plus GitHub and gitops
   `.status.yaml`. No documented trace contract marks missing or conflicting links.
6. **Two snapshot id schemes.** mctl-api uses `cs_` (`SnapshotIDPrefix`). The DevLoop status file
   for this issue records `snapshot_id: cs-0222c3a7b1372189`. This duplicate goes into the map.
7. **The test harness today is not safe for this purpose.** `.github/workflows/validate.yml` runs
   `postgres:16` with `postgres:postgres` and exports a generic `TEST_DATABASE_URL`. Tests such as
   `internal/agentregistry/store_test.go:31` use any `TEST_DATABASE_URL` they find. R2-2 requires
   a stricter, fail-closed guard for research runs.

### Cross-repo evidence (read-only GitHub API at the pins above)
| Item | Finding | Label |
|---|---|---|
| mctl-telegram `internal/pa/memory.go` | The `MemoryStore` interface (`Recall/Remember/Forget` on an `ExecutionContext`). `MemoryItem{Text, Provenance}`; an unknown provenance is treated as external. The only implementation is `NoopMemoryStore`. `Remember` returns `ErrMemoryDisabled`. A code search finds the type only in `memory.go`, `doc.go` and `context_test.go` | VERIFIED_CODE. Runtime wiring is UNKNOWN (not checked in `cmd/`) |
| mctl-agents `orchestrator/context_snapshot.py` | `context.mctl.ai/v1alpha1` `ContextSnapshot`: frozen schema, `sha256:` hash, no I/O, "never consumed by an authorization decision". Its comment says it is "not yet imported by production code". The pinned SHA shows importers in `orchestrator/human_input.py:31` and `orchestrator/capability.py:56`, so the comment is stale or those modules are not production. ADRs 009, 011, 015, 019 and 022 reference it | VERIFIED_CODE for the importers. Whether a live caller exists is UNKNOWN |
| mctl-docs | `package.json`: `vitepress 1.6.4`, `mermaid ^11.13.0`; `generate:llms` runs `scripts/generate-llms-full.ts`, which walks the docs root with `readdir`. `docs/` holds `api getting-started guides human-input mcp platform public reference security`. `docs/.vitepress/config.ts` (219 lines) has no `srcExclude` match | VERIFIED_CODE. The corpus is public-only by construction; no private-corpus mechanism was found |
| Related issues | .github#342, .github#339, mctl-agents#1127, mctl-agents#989, mctl-telegram#1488 and mctl-docs#237 are all `open` (titles read) | VERIFIED (issue metadata only); their contents were not read |

### Deployed state checked
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml` at gitops `5affc672` (desired
  state, manifest only):
  - `targetRevision: ddb6f57e...`, `tag: "4.181.0"`, `replicaCount: 2`;
  - `AUDIT_DB_URL`, `OAUTH_DB_URL`, `GLOVO_DB_URL` and `WORK_ITEMS_DB_URL` point at
    `shared-pg-rw.platform-db.svc:5432/mctl-api`;
  - `LIFECYCLE_DB_URL` points at `.../mctl-lifecycle`;
  - Temporal is `temporal-frontend.temporal.svc.cluster.local:7233` with namespace `mctl-agents`;
  - `EVENTS_VALKEY_URL` points at `valkey.platform-events`.

  These are labelled "desired state (manifest)", not VERIFIED_DEPLOYMENT: no live read
  corroborates them. The hostnames feed the harness denylist.
- A grep of the same manifest and of `$MCTL_GITOPS_ROOT` for `EVIDENCE_RETENTION_DAYS`,
  `DECISIONS_RETENTION_DAYS` and `WORKITEM_RETENTION_DAYS` found no setting. The code default
  (unset means the sweep is disabled) would apply, but the effective values are UNKNOWN.
- `mctl_get_service_status(team=admins, service=mctl-api)` returned "ArgoCD application not found:
  admins-mctl-api". mctl-api is a platform app outside the tenant catalogue, so its live health is
  UNKNOWN, not absent.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-api/proposals/issue-1190-.../` holds the HOLD proposal and a
  `.status.yaml` with `status: proposed` and `snapshot_id: cs-0222c3a7...`. It was read as prior
  art only.
- `$MCTL_GITOPS_ROOT/infra-components/data/cnpg/shared/` holds the shared CNPG cluster manifests.
  Only file names were read; they feed the denylist.

## Proposed solution

### 0. Slicing (R2-5: no oversized grant)
| Slice | Content | Feasible in one bounded PR? | Approval |
|---|---|---|---|
| **S0 (this proposal)** | Docs-only decision package in `docs/research/agentic-data-foundation/`: inventory, duplicate and owner map, vocabulary and edge model, threat model, ADR candidate (Proposed), fixture spec, query catalogue with ground-truth semantics, harness spec, benchmark plan, `versions.lock` template, traceability matrix, recommendation (DEFER) | Yes. Markdown and YAML only; no Go is compiled into the binary | this proposal |
| S1 | Harness guard plus fixture generator plus candidates A and B (Go, build tag `research`, `internal/research/agenticdata/`) | Yes | separate proposal and owner approval |
| S2 | C-Fuseki and C-Oxigraph runners plus the OWL/SHACL layer (scripts and container specs under `research/agenticdata/rdf/`) | Yes | separate |
| S3 | Graphiti semantics document plus deterministic replay attempt (`research/agenticdata/graphiti/`, pinned Python lock) | Yes; execution may be BLOCKED | separate |
| S4 | Results matrix, sensitivity analysis, final recommendation, ADR update | Yes, docs only | separate |
| AGE | Only if S1 records a recursive-SQL failure | conditional | separate |

The implementer grant for this proposal covers **S0 only**.

### 1. Vocabulary and edge model (`vocabulary.md`)
A logical model, not a production schema.
- **Entity** `{id, kind, tenant, trust_domain (public|tenant_private|principal_private), authority_ref}`.
  `authority_ref` names the authoritative row, for example `principals:prn_...`,
  `work_items:wi_...` or `execution_evidence:ev-...`. Kinds:
  - `principal`: canonical and authenticated; only from `principals`.
  - `external_contact`: tenant-scoped, never an authority.
  - `knowledge_entity`: a doc page, metric definition or memory topic.
  - `work`: `wi_`, `we_`, `cs_`, `aar_`, `rr_`, decision, PR.
- **Assertion** (attribute or edge) `{assertion_key, assertion_id, source_fact_id, subject_id, predicate, object, tenant, trust_domain,
  assertion_kind (observed|user_confirmed|inferred), source_ref, source_version, evidence_digest,
  observed_at, valid_from, valid_to, recorded_at, classification (public|internal|private|pii),
  confidence (only for inferred), schema_version, supersedes[]}`.
- **Identity and version rules (R2 P1):** `assertion_key` is the canonical tuple `(tenant, trust_domain, source_ref, subject_id, predicate, source_fact_id)`; `source_fact_id` is a stable source-native fact/edge ID or a documented stable slot, not the current object or arrival time. `assertion_id` identifies an immutable revision, derived from the canonical key, source_version and canonical payload digest (including object, validity and supersedes). Use domain-separated canonical serialization and verify digest matches on replay. Distinct values/edges get distinct keys; identical predicate/source alone is never a dedupe key. If no stable ID exists, preserve content-addressed observations as distinct and flag ambiguous lineage; do not auto-merge or infer a correction. Source versions are ordered only within a key with a documented comparable source-version contract; incomparable versions or equal-version distinct digests surface as conflicts, not last-writer-wins. Exact key/version/digest replays are idempotent. Keep revision history and derive current/as-of results deterministically from explicit supersedes/tombstones and valid time, never arrival order. A targeted tombstone suppresses only its key/revision and stale replay cannot resurrect it; retention/forget physically removes subject data and derived records, preserving only lawful non-identifying replay fences where allowed.
- **Rules:**
  - Corrections and deletions append a superseding or tombstone assertion. A physical delete then
    follows the source store's retention.
  - A crosswalk merge or split is an assertion with `supersedes`, so it is reversible.
  - `inferred` never feeds authorization, linking or promotion.
  - Feedback is an assertion about an outcome. It cannot change the kind of another assertion.
  - Secrets are excluded at build time with `internal/secretscan`; there is no `secret` class to
    store.
- **Event:** reuse the `mctl.events/v1` envelope (`internal/events/envelope.go`, dedupe on
  `event_outbox.event_id`). The logical contract adds `source_version` and `observed_at` for
  out-of-order handling: retain immutable revisions per `assertion_key`, dedupe exact revision identity, and derive current/as-of state using the identity and version rules above. Equal-version divergent payloads are explicit conflicts.
- **DevLoop edges:** `proposed_by`, `approved_by (aar_)`, `executed_as (we_/ex-)`,
  `sealed_context (cs_)`, `evidenced_by (ev-)`, `decided_by`, `reviewed_by (rr_)`,
  `owned_by (lifecycle)`, `resulted_in (PR/merge)`, `depends_on`, `blocks`. Operational,
  metric and memory edges are named, and owned, by .github#342, .github#339 and
  mctl-telegram#1488 respectively. #1190 only reserves the shared envelope fields.

### 2. Candidates
- **A (baseline):** a Go trace composer that calls the existing store read methods (for example
  `workitems.Store`, `evidence` read, `decisions` chain in `internal/decisions/chain.go`,
  `reviewstore`, `lifecycle`) against the harness databases. It joins in memory and marks each
  link `present`, `missing` or `conflict`.
- **B:** one schema `research_projection` in the harness database, with
  `assertions(assertion_key, assertion_id, source_version, payload_digest, ...)` and an edge projection referencing immutable `assertion_id`. Store distinct revisions with unique `(assertion_key, source_version, payload_digest)` and exact replay `ON CONFLICT ... DO NOTHING` only after digest/payload verification. Derive current/as-of views with explicit conflict/supersession/tombstone semantics above; no destructive upsert keyed by source/predicate. RDF exports use assertion/revision IRIs (not bare triples alone) to preserve provenance and conflicts. Traversal
  uses `WITH RECURSIVE ... CYCLE dst SET is_cycle USING path` (PostgreSQL 14+). Tenant scope is a
  mandatory predicate inside every recursive step, not a filter applied afterwards.
- **C-Fuseki:** Apache Jena Fuseki (Fuseki 2 line; Fuseki 1 is archived and excluded) with TDB2.
  It uses one named graph per tenant plus a public graph, the union default graph off, and
  `arq:queryTimeout`. OWL uses a Jena rule reasoner restricted to the subset below. SHACL uses
  Jena SHACL.
- **C-Oxigraph:** the Oxigraph server with the same named graphs. It has no native OWL reasoning
  or SHACL, so entailment uses explicit materialization (the same rule set, applied
  per tenant graph by a pinned rule pass) and SHACL uses pinned pySHACL. Both layers are timed and
  counted in its burden.
- **AGE:** conditional (see S1).
- **D-Graphiti:**
  - S3 documents its pinned dependencies: graph backend options, LLM and embedder requirements,
    and the bi-temporal edge fields `valid_at` / `invalid_at` with LLM-driven contradiction
    invalidation.
  - It maps each Graphiti edge to `assertion_kind=inferred`.
  - Execution is attempted only with pre-extracted facts and no embedder call. Otherwise it is
    BLOCKED.

`versions.lock` records each image as `name@sha256:<digest>` plus the release version, the Python
and Go lock hashes, and the tokenizer name and version. S0 delivers the template with empty
digests and a `verify-lock` rule: a run with any empty digest refuses to start. Exact versions are
resolved and committed in S1 to S3. They are deliberately not guessed here.

### 3. Fixture and queries (`fixture-spec.md`, `queries.md`)
- **Generator:** deterministic and seeded. It is checked with `internal/secretscan`. Output is
  content-hashed (sha256 over JCS-canonical JSON, reusing `internal/jcs`) and recorded in
  `fixture.lock`.
- **S:** 2 tenants, about 300 entities, about 2k assertions.
- **L:** 20 tenants, with entity and edge counts as generator parameters (planned 50k and 500k).
  Counts are parameters, not results.
- **The same logical model is exported three ways:** SQL rows (A/B), N-Quads (C) and Graphiti
  episodes or triples (D).
- **Query catalogue.** Each query has ground truth and a correctness rule (exact set equality
  unless stated otherwise):
  - Q1 DevLoop dependency closure with a cycle (it must terminate, and each cycle is reported once).
  - Q2 Blast radius of a failed execution.
  - Q3 Negative causal control: a time-correlated but unlinked event must not appear.
  - Q4 Conflicting certified metric definitions: both definitions are returned, the conflict is
    flagged, and nothing is auto-resolved.
  - Q5 Temporal memory correction as-of T1 and T2.
  - Q6 Public-docs relationship query that must return zero private nodes. It also checks that
    an embedded "ignore instructions" string is returned only as a literal.
  - Q7 PA verified preference across two connector sources, returned with provenance, conflict
    and as-of.
  - Q8 Identity: explicit link versus a same-name or same-email decoy (zero false links). An
    erroneous link is reversed with no authority change.
  - Q9 Revoke and delete: after revocation, a denial comes from the authority read, and zero
    residual rows, triples, inferred edges, index entries or cache entries remain.
  - Q10 Duplicate and out-of-order replay that yields byte-identical projection digests. Q10a: one source/predicate, two subjects and multiple values for one subject, separate stable fact keys; preserve all. Q10b: same key/version, different payload digests, return conflict with both revisions. Q10c: correct/retract exactly one key, preserve sibling facts and valid-time history, reject stale resurrection; repeat with shuffled input, exact duplicates and cross-tenant lookalikes. RDF assertion IRIs must preserve the same ground truth.
  - Q11 Full DevLoop trace with an injected missing review and a conflicting approval digest.
- **RDF-only tests:**
  - E1 OWL subset: `rdfs:subClassOf`, `rdfs:subPropertyOf`, `owl:inverseOf`,
    `owl:TransitiveProperty`. `owl:sameAs` is forbidden and its presence fails validation.
  - E2 SHACL: valid and invalid instances, plus a malformed shape that must error rather than
    pass.
  - E3 Unsupported features, for example SHACL-SPARQL constraints or OWL cardinality, which must
    be reported as `unsupported`.
  - E4 Tenant-crossing entailment: a transitive chain spanning two tenant graphs produces zero
    cross-tenant triples.
- **Metrics per (candidate, size, query):**
  - answer and false positives, provenance completeness;
  - cold (after container restart and cache drop) and warm P50/P95 over at least 30 repeats,
    after 5 discarded warmups;
  - ingest and rebuild time;
  - peak cgroup memory (`memory.peak`, not RSS), CPU time (`cpu.stat`); if reporting process RSS, measure it separately and describe aggregation;
  - on-disk bytes;
  - setup steps and component count;
  - output tokens of the serialized answer with the pinned offline tokenizer, labelled
    "estimate";
  - the hardware, kernel and repeat count.

### 4. Harness guard (`harness-spec.md`; implemented in S1)
`internal/research/agenticdata/guard` is a pure package with a recording dialer.
- **Refused before any dial:**
  - a host that is not the container IP or socket the harness created;
  - any host containing `.svc`, `cluster.local`, `shared-pg`, `platform-db`, `mctl-api` or
    `mctl-lifecycle`;
  - a non-RFC1918 or non-loopback address;
  - a forbidden environment variable (any `*_DB_URL` other than a validated research DSN, plus
    `KUBECONFIG`, `VAULT_*`).
- **After the dial and before any write:**
  - `current_database()` matches `mctl_research_<run_id>`;
  - `current_user` matches the generated role;
  - `pg_control_system().system_identifier` matches the value captured at creation;
  - the sentinel table `research_sentinel(run_id, nonce)` matches.
- **Containers:**
  - run on a `docker network create --internal mctl-research-<run_id>` network, with the runner
    in a container on that network and no published ports;
  - limits `--cpus`, `--memory`, `--pids-limit`; `statement_timeout`; SPARQL and HTTP timeouts; a
    result cap;
  - a wall-clock kill.
- **Cleanup:** filters on the label `mctl.research.run=<run_id>` and re-checks the sentinel. It
  refuses anything else.
- **Isolation:** no shared pools (`pgshared` is not used), no `NewStore` against non-harness DSNs,
  and no migrations outside the harness DB.

### 5. Threat model (`threat-model.md`)
Assets are the principals, grants and consents, private memory, tenant data and the public corpus.
- **Threats:**
  - cross-tenant leakage through traversal or entailment;
  - a stale projection used for an allow decision;
  - an inferred identity link;
  - prompt injection from retrieved content;
  - secrets in projections or logs;
  - feedback poisoning;
  - deletion that leaves residue in indexes, caches or inferred triples;
  - arbitrary SPARQL or SQL from agents;
  - the harness hitting production.
- **Controls:**
  - action-time checks always read the authority (`principals`, delegation resolver,
    `action_approval_requests`, `glovoconsent`), and an unreachable authority means deny, matching
    the lifecycle "503 means UNKNOWN" rule;
  - mandatory tenant predicates within recursion and per-tenant named graphs with the union graph
    off;
  - only bounded, parameterized read tools;
  - redaction through `internal/audit/redact.go`;
  - tombstone-driven invalidation of derived and inferred edges;
  - every control is tied to a negative test (see tasks.md).

### 6. Decision rule (`adr-candidate.md`, status Proposed)
- **Hard gates.** A candidate is rejected on any failure of:
  - correctness on every ground-truth query;
  - zero leakage;
  - zero false links;
  - zero unauthorized actions;
  - 100% deletion and revocation propagation;
  - fail-closed authority;
  - E1 to E4 for RDF candidates.
- **Soft comparison** (replacing the 2x and 3x multipliers):
  - incremental absolute P95 latency in ms and resource cost, relative to A;
  - the count of new operational components (processes, images, backup and restore paths,
    deletion paths);
  - rebuild time.

  These are evaluated at an owner-confirmed workload, with a sensitivity sweep over 10^2 to 10^6
  queries per day and 95% bootstrap confidence intervals.
- **Outcomes:**
  - REUSE_EXISTING_APIS if A passes the hard gates and fits the budgets.
  - BOUNDED_POSTGRES_READ_MODEL if A fails a hard gate or budget and B passes.
  - TARGETED_GRAPH_PILOT only if B fails a hard requirement or budget and a graph candidate passes
    every hard gate with a non-overlapping confidence interval on the deciding metric.
  - DEFER otherwise, or whenever a required candidate is BLOCKED.
- **Current recommendation (S0): DEFER.** No measurement exists yet. The hypothesis to falsify in
  S1 is that A plus the vocabulary and a trace contract suffice, with B needed only for Q1, Q2 and
  Q11 at size L.

### 7. Traceability matrix (R2-6; `traceability.md` expands it)
| R2 item | Design | Tasks | Negative tests | Evidence artifact |
|---|---|---|---|---|
| R2-1 mandatory comparison, pins, AGE conditional, Graphiti | sections 2, 3 | 5, 13-17 | N1, N9, N11 | `versions.lock`, results matrix |
| R2-2 safe harness | section 4 | 6, 11 | H1-H10 | guard test log (zero dials) |
| R2-3 benchmark parity, OWL/SHACL, deletion | sections 3, 5 | 5, 7, 12-16 | N1-N10 | `fixture.lock`, per-query results |
| R2-4 cross-repo audit | Current state | 1, 2 | T1 | `inventory.md` with pins |
| R2-5 decision criteria and slicing | sections 0, 6 | 8, 10, 18 | T3 | `adr-candidate.md`, sensitivity sweep |
| R2-6 review gate | section 7 | 9 | T2 | `traceability.md` |

## Alternatives
- **Adopt Fuseki or Oxigraph now.** Rejected. It would be a second copy of tenant data with its own
  retention, deletion and access path, and it would contradict observation 1. Kept as a mandatory
  measured candidate.
- **Adopt Graphiti as shared memory.** Rejected. Its LLM-extracted edges are inferred by
  construction, and it would compete with mctl-telegram#1488 and mctl-agents#989.
- **A physical Bronze/Silver/Gold lake with CDC.** Rejected. It creates the immutable PII lake the
  issue forbids, and the reference-only `event_outbox` already provides incremental signals.
- **Run the benchmark against the existing CI `TEST_DATABASE_URL`.** Rejected. It is a generic
  `postgres:postgres` DSN that cannot prove isolation (observation 7).
- **One large implementer grant for S0 to S4.** Rejected by R2-5.

## Platform impact
- **Migrations:** none. S0 is Markdown and YAML in `docs/research/`. Later slices create schemas
  only inside disposable harness containers.
- **Compatibility:**
  - no change to routes, MCP tools (the `server_test.go` count is unchanged), helm or env;
  - the `Dockerfile` builds only `./cmd/api`, and research packages are behind the `research`
    build tag, so `make test` (`go test -p 1 ./...`) does not run them.
- **Resources:** none in the cluster. Local containers run with explicit limits.
- **Risks and mitigations:**
  - Results read as approval: the ADR stays Proposed, and each slice needs its own approval.
  - The harness reaches production: pre-dial denylist, sentinel and system identifier checks,
    and a zero-dial fake dialer in tests.
  - An unpinned image: `verify-lock` refuses the run.
  - The fixture contains real data: a seeded generator plus `secretscan`.
  - The clone and deployment SHAs differ: both are tagged, and the pins are refreshed at each
    slice.

## Open questions
See requirements.md: absolute budgets, expected workload, container runtime availability, Graphiti
without an embedder, the missing work-item purge, `cs_` versus `cs-`, and the unobserved production
env and health.
