# Tasks: issue-1190-spike-data-agentic-data-foundation-unifi

Research-only. Every artifact lives under `docs/research/agentic-data-foundation/` or the test-only
package `internal/research/agenticdata/` (build tag `research`). No change to `cmd/api/main.go`,
`internal/api/router.go`, `internal/mcp/server.go`, the helm chart or any production store.

- [ ] 1. Pin SHAs (mctl-api main, deployed `targetRevision` from
  `bootstrap/templates/mctl-platform/mctl-api.yaml`, mctl-gitops) and write `inventory.md` covering
  every store in design.md "Current state". Each row has owner, table, IDs, tenant boundary,
  retention, provenance, freshness, access route/MCP tool, gaps and an evidence tag. — DoD: every row
  links file:line at a pinned SHA. The deployed-vs-clone SHA gap is recorded.
- [ ] 2. Extend the inventory to mctl-telegram, mctl-agents, mctl-docs and .github (PA memory,
  context control plane/MemoryStore, corpus boundary, evidence graph). (depends on 1) — DoD: each
  source is VERIFIED_CODE with a SHA, or UNKNOWN with the exact follow-up read listed.
- [ ] 3. Write `owners.md` (duplicate/owner map) for .github#342/#339/#309, mctl-telegram#1488/#1325,
  mctl-docs#237 and mctl-agents#989/#1127. (depends on 2) — DoD: no investigation duplicated, and
  #1190's own scope is stated in one paragraph.
- [ ] 4. Write `vocabulary.md`: entity kinds (canonical principal vs external contact vs knowledge
  entity), the assertion fields, assertion_kind rules, supersedes-based correction/merge/split and
  the DevLoop edge vocabulary. (depends on 1) — DoD: every field maps to an existing column or is
  marked as a gap.
- [ ] 5. Write `threat-model.md`: action-time authority, fail-closed reads, delegated actor/subject
  separation, revocation, deletion propagation, cross-tenant isolation, secret exclusion, prompt
  injection, cache/projection invalidation and feedback poisoning. (depends on 4) — DoD: each threat
  names a control in an existing package or a negative test.
- [ ] 6. Build the frozen synthetic fixture in `internal/research/agenticdata/testdata/fixture-v1/`
  with a seeded generator and a content-hash manifest. (depends on 4) — DoD: it covers all six
  scenario families, passes the `internal/secretscan` check and contains no real identifiers.
- [ ] 7. Implement baseline A: a trace composer over existing store read methods against
  TEST_DATABASE_URL plus a second test database for lifecycle. (depends on 6) — DoD: answers every
  scenario and marks missing/conflicting evidence explicitly.
- [ ] 8. Implement candidate B in schema `research_projection` (views, then a rebuildable table, with
  `WITH RECURSIVE` traversal), dropped at teardown. (depends on 6) — DoD: the build is idempotent and
  the projection hash is identical under duplicate/out-of-order replay.
- [ ] 9. Optional: local C (Oxigraph, Fuseki 2 + TDB2 + SHACL) over the RDF-converted fixture, and a
  D (Graphiti) dependency/semantics review. (depends on 6) — DoD: measured or UNKNOWN per metric,
  with no cluster deployment and no paid service.
- [ ] 10. Run the benchmark (N >= 200 per scenario) and write `benchmark.md`: the matrix, sample size,
  methodology, hardware, and MEASURED vs ESTIMATE vs UNKNOWN. (depends on 7, 8) — DoD: all negative
  tests show zero leakage, zero false links and zero unauthorized actions, or the candidate is marked
  failed.
- [ ] 11. Write `adr-candidate.md` (status Proposed) with one outcome, scope, costs, failure criteria
  f1-f3 and phased follow-ups only if warranted. (depends on 3, 5, 10) — DoD: the outcome follows from
  the matrix, and each follow-up is a separate proposal needing owner approval.

## Tests
- [ ] T1. PA: a verified preference across two synthetic connectors returns both values,
  provenance, the conflict flag and as_of. An inferred value never shows as verified.
- [ ] T2. Identity: an explicit `external_identities` link resolves. Same-name and same-email decoys
  produce zero links. Tenant B cannot read tenant A. Superseding an erroneous link restores the prior
  state with no grant change.
- [ ] T3. Consent: after a synthetic grant is revoked, the execution-time check denies, and derived
  context for that subject is invalidated in B (and C/D if run).
- [ ] T4. Deletion: after a synthetic subject is forgotten, zero projection, cache or retrieval rows
  reference it.
- [ ] T5. DevLoop: the trace proposal -> approval -> execution -> review -> outcome is reconstructed.
  The missing review receipt and the conflicting approval digest are reported, not filled in.
- [ ] T6. Knowledge: public doc relationships resolve with zero private-memory rows. The injected
  instruction string is returned as data and changes no behaviour.
- [ ] T7. Replay: duplicate and shuffled events give an identical projection content hash, and a
  correction supersedes without losing source_ref.
- [ ] T8. Feedback: an outcome assertion does not change the assertion_kind of any other row and
  grants no authority.
- [ ] T9. Guard: `go test -p 1 ./...` without `-tags research` is unchanged, and the MCP tool count
  in `internal/mcp/server_test.go` is unchanged.

## Rollback
Nothing is deployed. To roll back, delete `docs/research/agentic-data-foundation/` and
`internal/research/agenticdata/`. The test databases are dropped at teardown, and local C/D
containers are stopped and removed. Production stores, routes, MCP tools and gitops are untouched.
