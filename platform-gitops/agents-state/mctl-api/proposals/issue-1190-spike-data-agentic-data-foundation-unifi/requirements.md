# Agentic data foundation and unified knowledge graph: R2 research decision package (spike, research only)

## Context

Issue mctlhq/mctl-api#1190 is the umbrella research spike (P2). It asks whether MCTL needs a shared,
provenance-aware, agent-ready data contract and a bounded read model across the Personal Assistant
(PA), the Knowledge Platform, DevLoop and the operational agents. The alternative is that the
existing authoritative PostgreSQL stores and APIs, with on-demand joins, already suffice. The
answer must be one of REUSE_EXISTING_APIS, BOUNDED_POSTGRES_READ_MODEL, TARGETED_GRAPH_PILOT or
DEFER, backed by evidence. The issue does not authorize implementation, production schema
changes, a new service or database, a paid vendor, live agent execution or external model calls.

This is revision R2. The owner put the first proposal (artifact
sha256:6540e0c7...) on HOLD and requires the following:
- A practical comparison of A (existing APIs and joins), B (PostgreSQL recursive SQL), Fuseki 2
  with TDB2, and Oxigraph on one common, versioned, content-hashed synthetic fixture. The
  comparison is a required deliverable, not an optional one.
- A Graphiti semantics comparison.
- A fail-closed, disposable test harness.
- Benchmark parity: the same data, the same queries and the same correctness semantics for every
  candidate.
- A pinned cross-repo audit.
- Decision criteria that are justified rather than arbitrary multipliers.
- A traceability matrix.
- An explicit split into separately approved, bounded slices.

This proposal covers Slice 0 (the documentation-only decision package and the executable
specification) and defines Slices 1 to 4. Each later slice needs its own owner approval. Until the
benchmark slices have run, the recommendation is DEFER for any graph adoption.

## User stories

- AS the platform owner I WANT a code-grounded, pinned inventory of authoritative entities,
  identities, events, consent, decisions, outcomes and memory sources across mctl-api,
  mctl-agents, mctl-telegram, mctl-docs, .github and mctl-gitops SO THAT any read model reuses
  existing authority instead of duplicating it.
- AS the platform owner I WANT A, B, C-Fuseki and C-Oxigraph measured on identical frozen data and
  queries, plus a Graphiti semantics comparison, SO THAT a graph adoption decision rests on
  measurements rather than assertion.
- AS a security reviewer I WANT a harness that refuses any non-disposable, production-like or
  unverified database or endpoint before its first write SO THAT the research can never touch
  production.
- AS a PA and DevLoop maintainer I WANT a common vocabulary (entity, assertion, edge, event) with
  provenance, observed and valid time, as-of, assertion kind, classification, confidence, schema
  version and tenant scope SO THAT agent context can be explained, corrected and deleted.
- AS an independent reviewer I WANT a traceability matrix from each R2 requirement to design,
  task, negative test and evidence SO THAT I can review before the owner decides.

## Acceptance criteria (EARS)

### Inventory and audit (R2-4)
- WHEN the Slice 0 package is delivered THE SYSTEM SHALL contain a source-linked inventory in
  which every row carries a pinned commit SHA and exactly one evidence label: VERIFIED_CODE,
  VERIFIED_DEPLOYMENT, PROPOSED, UNKNOWN or BLOCKED.
- THE SYSTEM SHALL label a gitops manifest value VERIFIED_DEPLOYMENT only when a live read
  corroborates it. A manifest value without that is labelled "desired state (manifest)".
- IF a repository, file or live endpoint cannot be read THEN THE SYSTEM SHALL record it as
  BLOCKED or UNKNOWN, with the exact follow-up evidence required. It SHALL NOT be recorded as
  absent.
- THE SYSTEM SHALL NOT infer runtime status from module comments. A comment such as "not yet
  imported by production code" SHALL be checked against importers at the pinned SHA.
- THE SYSTEM SHALL deliver an owner and duplicate map that keeps .github#342, .github#339,
  mctl-telegram#1488 and #1325, mctl-docs#237, mctl-agents#989 and #1127, and .github#309 as
  owners of their scopes. #1190 owns only the shared vocabulary, the provenance and trace contract,
  the benchmark and the decision.

### Comparison scope (R2-1)
- THE SYSTEM SHALL specify the candidates A, B, C-Fuseki (Apache Jena Fuseki 2 line with TDB2) and
  C-Oxigraph as mandatory benchmark targets on the same fixture. None may be silently dropped or
  made optional.
- THE SYSTEM SHALL pin every image, binary and package by exact version and by content digest in
  a `versions.lock` file that is committed with the fixture.
- IF a run lacks a digest pin THEN THE SYSTEM SHALL refuse to start it.
- WHERE recursive SQL in B fails a required query (not expressible, or outside the owner-set
  absolute budget) THE SYSTEM SHALL add Apache AGE as a conditional candidate. Otherwise AGE is
  recorded as "not triggered".
- THE SYSTEM SHALL deliver a mandatory Graphiti comparison of dependencies and of temporal and
  edge-invalidation semantics. Any execution SHALL use only deterministic replay, canned
  extraction or pre-extracted facts, labelled PARTIAL_COVERAGE.
- IF the Graphiti execution needs an LLM or embedder call THEN THE SYSTEM SHALL record it as
  BLOCKED pending a separately approved, capped budget, and SHALL make no external model call.
- IF any candidate cannot be executed locally THEN THE SYSTEM SHALL record BLOCKED or UNKNOWN for
  its measurements and SHALL recommend DEFER for graph adoption. It SHALL NOT report a comparative
  result.

### Safe harness (R2-2)
- WHEN the harness starts THE SYSTEM SHALL create its own disposable, network-isolated
  containers:
  - generated credentials;
  - a unique database `mctl_research_<run_id>` and a unique schema;
  - a unique per-run sentinel row (run_id plus a 256-bit nonce);
  - resource labels `mctl.research.run=<run_id>`.
- IF the target DSN host is not the harness-owned container address or socket THEN THE SYSTEM
  SHALL refuse before dialing. This covers hosts that contain `.svc`, `shared-pg`, `platform-db`,
  `mctl-api` or `mctl-lifecycle`, and any non-loopback or remote endpoint.
- IF `TEST_DATABASE_URL`, `TEST_DB_URL`, `AUDIT_DB_URL`, `WORK_ITEMS_DB_URL`, `LIFECYCLE_DB_URL`,
  `GLOVO_DB_URL`, `OAUTH_DB_URL`, `KUBECONFIG`, `VAULT_ADDR`, `VAULT_TOKEN` or any `*_DB_URL` is
  present in the harness environment THEN THE SYSTEM SHALL refuse to start. The exception is a
  generic `TEST_DATABASE_URL` that passes every fail-closed check below.
- WHEN a generic `TEST_DATABASE_URL` is offered THE SYSTEM SHALL accept it only if all of the
  following hold:
  - the host check passes;
  - the database name matches `mctl_research_<run_id>`;
  - the role is the generated per-run role;
  - `pg_control_system().system_identifier` equals the value recorded at container creation;
  - the sentinel row exists with the expected nonce.
- IF any of those checks fails THEN THE SYSTEM SHALL refuse with no write.
- WHILE a run is active THE SYSTEM SHALL enforce bounds on every candidate: CPU and memory limits,
  a PID limit and a wall-clock limit per container; `statement_timeout`; a per-query timeout for
  SPARQL and HTTP; and a result-row cap.
- WHEN cleanup runs THE SYSTEM SHALL remove only resources that carry this run's label and whose
  sentinel matches.
- IF a cleanup target is unlabelled or foreign THEN THE SYSTEM SHALL refuse.
- THE SYSTEM SHALL never connect to a production endpoint, including to test that the endpoint is
  refused. Refusal tests use a recording fake dialer that asserts zero dials.

### Benchmark parity (R2-3)
- THE SYSTEM SHALL use one frozen, content-hashed fixture in two sizes, S (small) and L (scaled),
  generated deterministically from a seed. Every candidate SHALL receive the same ground-truth
  answers and the same logical queries under the same correctness semantics wherever they are
  comparable.
- THE SYSTEM SHALL include each of these cases:
  - DevLoop dependency closure and blast radius, with cycles;
  - a negative causal control;
  - conflicting certified metric definitions;
  - temporal memory corrections with as-of;
  - public and private corpus isolation;
  - PA verified preference from two sources;
  - an identity false match (same name or email);
  - consent revocation and deletion propagation;
  - duplicate and out-of-order event replay.
- THE SYSTEM SHALL include RDF tests for an explicit OWL entailment subset and for SHACL
  conformance, covering:
  - invalid shapes;
  - invalid instances;
  - unsupported features, which SHALL be reported as unsupported and not as passing;
  - tenant-crossing entailment, which SHALL produce zero cross-tenant triples.
- WHERE a candidate lacks native OWL or SHACL support (for example Oxigraph) THE SYSTEM SHALL use
  a pinned external validation or inference layer and SHALL count that layer's time, memory and
  operational burden against the candidate.
- WHEN a subject is deleted or a grant is revoked THE SYSTEM SHALL verify that zero rows, triples,
  inferred edges, index entries or cache entries still reference the subject. This holds in every
  candidate.
- WHEN a query needs an authority read that is stale, revoked or unreachable THE SYSTEM SHALL fail
  closed and SHALL NOT answer from the projection.
- THE SYSTEM SHALL record, per candidate, size and query:
  - exact answers and false positives;
  - provenance completeness;
  - P50 and P95 latency, cold and warm;
  - ingest and rebuild time;
  - peak RSS and CPU time;
  - storage bytes;
  - setup and operations burden;
  - output tokens counted with a pinned offline tokenizer, labelled "estimate" and kept separate
    from any actual LLM usage;
  - the repeat count;
  - the hardware and kernel.
- THE SYSTEM SHALL NOT invent any value. Unmeasured cells are UNKNOWN.

### Decision criteria (R2-5)
- THE SYSTEM SHALL treat correctness, zero tenant leakage, zero false identity links, zero
  unauthorized actions, complete deletion and revocation propagation, and fail-closed authority as
  hard gates. A candidate that fails any of them is rejected, whatever its performance.
- THE SYSTEM SHALL replace the first proposal's relative 2x query-count and 3x latency gates with
  comparisons of absolute incremental latency, cost and maintenance against an owner-confirmed
  expected workload. The comparison SHALL include a sensitivity sweep across workload sizes and
  report 95% bootstrap confidence intervals.
- THE SYSTEM SHALL recommend a graph store only if (a) B fails a hard requirement or an
  owner-set absolute budget, and (b) the graph candidate passes every hard gate with a
  non-overlapping confidence interval on the deciding metric.
- IF the benchmark has not run THEN THE SYSTEM SHALL recommend DEFER for graph adoption. It SHALL
  also list the precise blockers and a reproduction plan.
- THE SYSTEM SHALL NOT state any production SLO or token saving that was not measured.

### Boundaries
- THE SYSTEM SHALL keep PostgreSQL and the existing source APIs authoritative. Any projection or
  graph is an optional, rebuildable read model and never an identity, approval, consent or policy
  authority.
- THE SYSTEM SHALL NOT link accounts or grant privileges from LLM inference, shared email, display
  name or a fuzzy match. A crosswalk merge is reversible by a superseding assertion and is never
  an authorization input.
- THE SYSTEM SHALL keep private tenant memory and public documentation as separate trust domains,
  with no cross-tenant federation or inference.
- THE SYSTEM SHALL allow no arbitrary agent SPARQL or SQL and no update path from agents.
- THE SYSTEM SHALL treat retrieved content as data, never as instructions.
- THE SYSTEM SHALL NOT let feedback change another assertion's kind, promote an inferred fact to
  verified, or expand any authority.
- THE SYSTEM SHALL describe any later read contract as a bounded, parameterized, read-only tool or
  resource on the existing MCP server (`internal/mcp`). An optional provenance inspector SHALL
  reuse the existing MCP App pattern (`internal/mcp/stats.go`). No new MCP server or UI runtime is
  introduced.

### Review gate (R2-6)
- THE SYSTEM SHALL deliver a traceability matrix: R2 requirement, then design section, task,
  negative test and evidence artifact.
- THE SYSTEM SHALL stop at proposed. Independent review is required before owner approval of any
  slice.

## Out of scope

- Any production code path:
  - changes to `cmd/api/main.go`, `internal/api/router.go` or `internal/mcp/server.go`;
  - new MCP tools (the tool count in `server_test.go` is unchanged);
  - helm or env changes;
  - production migrations or schema changes.
- Deploying or subscribing to any graph store, vector store, Spark or Databricks, or any paid
  service. Fuseki, Oxigraph, AGE and Graphiti run only as disposable local containers in a later,
  separately approved slice.
- Ingesting real personal conversations, tokens, production rows or live user data.
- Live agent execution, external LLM or embedding calls, and automatic merging of identity
  records.
- Replacing the principal registry (`internal/principals`), ZITADEL, delegation, approvals, the
  ContextSnapshot contracts or the PA MemoryStore.
- Approving the first or this proposal, and starting parallel DevLoops for the related issues.

## Open questions

- The owner-set absolute budgets used in the decision rule (per-query P95 in ms at the expected
  workload, and the acceptable count of added operational components) are not stated. Slice 4
  proposes candidate thresholds derived from the baseline run, and the owner confirms them.
  Nothing is decided before then.
- The expected real workload (queries per day per scenario) is UNKNOWN. Reading production
  counts, for example from `model_usage_records` or `audit_events`, is not authorized. The
  sensitivity sweep therefore covers 10^2 to 10^6 queries per day until the owner supplies a
  figure.
- Whether a local container runtime with `docker network create --internal` is available to the
  executor of Slices 1 to 3 is UNKNOWN. If it is not, those slices are BLOCKED and the outcome
  stays DEFER.
- Graphiti at the pinned version may not accept pre-extracted facts without an embedder. If it
  does not, its execution is BLOCKED and only the semantics comparison is delivered.
- `WORKITEM_RETENTION_DAYS` is cited in a comment in `internal/evidence/store.go:44`, but no
  sweep implementing it was found in the code at `8e3b9b72`. Whether production purges work items
  at all is UNKNOWN. This matters for deletion propagation.
- mctl-api seals snapshots with the id prefix `cs_` (`internal/workitems/snapshots.go`). The
  DevLoop `.status.yaml` records `cs-<hex>`. Whether these are two id schemes for one concept or
  two concepts needs an owner answer (see the duplicate map).
- Effective production env values for mctl-api (retention, `MCTL_SUBMIT_CREATES_EXECUTION`) and
  its live Argo health were not observable. They are UNKNOWN.
