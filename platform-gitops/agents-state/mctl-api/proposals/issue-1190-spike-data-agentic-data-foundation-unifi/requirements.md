# Spike: Agentic Data Foundation and Unified Knowledge Graph for MCTL (decision package)

## Context
Issue mctlhq/mctl-api#1190 is a research-only umbrella spike (P2). It asks whether MCTL needs a
shared, provenance-aware, agent-ready data contract and bounded read model across Personal
Assistant (PA), Knowledge Platform, DevLoop and operational agents, or whether the existing
authoritative APIs and on-demand joins already suffice. It adapts the logical
raw/normalized/agent-ready layering, identity crosswalk, entity/attribute/event grain, freshness and
outcome-feedback principles of the Databricks Agentic CDP article without adopting a CDP or vendor
stack. Four architectures are compared: A (existing APIs and federated joins), B (bounded
PostgreSQL relational/edge projections, recursive SQL before Apache AGE), C (Fuseki 2 + TDB2 or
Oxigraph, RDF/SPARQL with SHACL and a bounded OWL subset), D (Graphiti temporal agent memory).
The outcome is one of REUSE_EXISTING_APIS | BOUNDED_POSTGRES_READ_MODEL | TARGETED_GRAPH_PILOT | DEFER.

This matters because mctl-api already holds many authoritative, tenant-scoped, references-only
stores (principals, external identities, work items, sealed ContextSnapshots, execution evidence,
decision records, review receipts, lifecycle ownership, audit, Glovo consent). If agents start to
build their own copies, joins or inferred identity links, they bypass the tenant boundaries,
retention and fail-closed authorization these stores enforce. The spike must produce a
code-grounded inventory, a falsifiable synthetic benchmark and one recommendation. The deliverables
are documents, a synthetic fixture and an isolated test harness only. The spike adds no production
code, schema, service or data ingestion.

Provisional recommendation (to be confirmed or falsified by the benchmark): **REUSE_EXISTING_APIS**,
with a documented common read vocabulary and provenance-trace contract over the existing stores.
Escalate to **BOUNDED_POSTGRES_READ_MODEL** only if the baseline misses the failure criteria in
design.md. Under this GO, C and D are measured only as an isolated local comparison, are not
recommended for adoption, and are recorded as DEFER unless B fails a demonstrated requirement.

## User stories
- AS a platform owner I WANT a source-linked inventory of every authoritative entity, identity,
  event, consent, decision, outcome and memory source SO THAT I can decide on a read model with
  evidence rather than with issue descriptions.
- AS a DevLoop operator I WANT to reconstruct proposal -> approval -> execution -> review -> outcome
  from authoritative evidence, with missing or conflicting evidence marked, SO THAT I can audit a
  run without trusting an agent's summary.
- AS a PA owner I WANT a verified preference with provenance, conflicting values and as-of freshness
  SO THAT the assistant never acts on a stale or inferred fact as if it were verified.
- AS a security reviewer I WANT proof that identity linkage, consent revocation and deletion stay
  fail-closed in every candidate SO THAT no read model can become an identity, approval or policy
  authority.
- AS a Knowledge Platform maintainer I WANT public documentation relationships resolved without
  mixing in private memory SO THAT the public/private corpus boundary (mctl-docs#237) holds.
- AS a reviewer of the spike I WANT measured results kept apart from estimates, with UNKNOWN where
  nothing was measured, SO THAT the recommendation is falsifiable.

## Acceptance criteria (EARS)
- WHEN the spike completes THE SYSTEM SHALL deliver, under `docs/research/agentic-data-foundation/`
  in mctl-api, a current-state inventory where each row names owner, package/table, ID scheme,
  tenant boundary, retention, provenance, freshness, access path and gaps, tagged VERIFIED_CODE,
  VERIFIED_DEPLOYMENT, PROPOSED or UNKNOWN, with pinned commit SHAs.
- WHEN a row describes a source outside mctl-api (mctl-telegram, mctl-agents, mctl-docs, .github)
  that the spike could not read THE SYSTEM SHALL tag it UNKNOWN and record the exact follow-up
  evidence needed, and SHALL NOT infer its behaviour from issue text.
- THE SYSTEM SHALL deliver a duplicate/owner map that names the owner issue of each overlapping
  investigation (.github#342, .github#339, mctl-telegram#1488/#1325, mctl-docs#237,
  mctl-agents#989/#1127, .github#309) and states what #1190 does not cover.
- THE SYSTEM SHALL deliver a common vocabulary and logical entity/attribute/relationship/event model
  in which every fact carries a stable ID, tenant scope, source reference, evidence digest,
  observed_at, valid_from/valid_to, as_of, classification, confidence, assertion_kind
  (observed | user_confirmed | inferred) and schema_version.
- THE SYSTEM SHALL deliver a frozen synthetic fixture (no real personal data, tokens or production
  exports) and a benchmark harness that runs the same scenarios against baseline A and the smallest
  candidate B in an isolated local/test PostgreSQL (TEST_DATABASE_URL).
- WHEN a benchmark scenario runs THE SYSTEM SHALL record exact-answer correctness, false links,
  leakage/unauthorized actions, stale reads, P50/P95 latency, query count, token estimate, storage
  and deletion behaviour, plus sample size and methodology.
- IF a metric was not measured THEN THE SYSTEM SHALL report it as UNKNOWN and SHALL NOT substitute an
  estimate or an invented production SLO.
- IF any negative test (cross-tenant read, revoked grant, same-name/email match, deleted subject,
  prompt-injection content) yields a leak, an unauthorized action or an identity link THEN THE
  SYSTEM SHALL mark that candidate as failed.
- WHILE any candidate read model exists THE SYSTEM SHALL treat it as a rebuildable projection and
  SHALL NOT use it as identity, approval, consent or policy authority. Action-time checks go to the
  authoritative stores (principals, delegation grants, action approval requests, Glovo consent).
- WHILE identities are linked THE SYSTEM SHALL link only through explicit verified links
  (`external_identities`, `surface_identity_links`) and SHALL NOT link on LLM inference, shared
  email, display name or fuzzy match.
- WHEN a synthetic grant is revoked or a subject is deleted THE SYSTEM SHALL demonstrate denial at
  execution time and the invalidation or removal of every derived projection, cache and retrieval
  result that carried that subject.
- WHEN duplicate or out-of-order events are replayed THE SYSTEM SHALL demonstrate a deterministic
  projection (same input set gives the same content hash) and correction without losing the source
  reference.
- IF outcome feedback is recorded THEN THE SYSTEM SHALL keep it as a separate assertion with its own
  provenance and SHALL NOT promote an inferred fact to verified or expand any authority.
- WHEN the spike completes THE SYSTEM SHALL deliver a threat model, an evidence/benchmark matrix, an
  ADR candidate (status Proposed) and exactly one recommendation drawn from the four decision
  outcomes, with scope, costs and explicit failure criteria.
- WHERE C (Fuseki 2/TDB2 or Oxigraph) or D (Graphiti) is evaluated THE SYSTEM SHALL run it only
  locally against the same fixture, with no paid service, and SHALL report its model/backend
  dependencies and any UNKNOWN measurements.

## Out of scope
- Any production schema change, migration, new database, new service, new MCP server, new UI
  runtime or rollout. The spike adds no tables to `internal/*` stores.
- Production data ingestion, real personal conversations, real tokens or live user experiments.
- Spark/Databricks, CDP adoption or any vendor subscription.
- Replacing ZITADEL, the principal registry (`principals`, `prn_` IDs) or authorization
  (mctl-api#373/#374/#377/#435, .github#91).
- A competing memory runtime (mctl-telegram#1488/#1325, mctl-agents#989).
- Re-running the operational RCA graph (.github#342), business-semantics (.github#339) or task
  dependency graph (mctl-agents#1127) investigations.
- New MCP tools that write. Any later read-only MCP tool or provenance inspector is a separate
  follow-up proposal that needs its own approval.
- Automatic merging of identity records and DevLoop approval of anything this spike recommends.

## Open questions
- Cross-repo reads: this run only had the mctl-api clone and the mctl-gitops `platform-gitops/`
  checkout. The memory stores of mctl-telegram (PA memory), mctl-agents (context control plane,
  MemoryStore, tiered memory) and mctl-docs (corpus boundary) were not read. Their inventory rows
  are UNKNOWN until a follow-up run or the spike executor pins and reads them.
- Is running Fuseki 2, Oxigraph or Graphiti locally (containers on a developer machine) within "no
  new service" for the PoC? Assumed yes only for a throwaway local run with no cluster deployment.
  If not, C/D get a reproducible plan with UNKNOWN measurements.
- Graphiti requires an LLM and embedding provider for ingestion. A synthetic-only run still spends
  model budget, and the owner has not set a cap. Assumed: D is evaluated on paper plus a
  dependency inventory, without model calls, unless a budget is granted.
- Thresholds: the issue forbids invented SLOs. The proposed failure thresholds in design.md are
  relative to the measured baseline and must be confirmed by the owner after the baseline run.
- Lifecycle ownership lives in a separate database (`LIFECYCLE_DB_URL` -> `mctl-lifecycle`), so a
  single-database SQL view cannot join it with work items. Is a cross-database read contract
  acceptable, or must B copy lifecycle state? This proposal assumes federation at the API layer.
