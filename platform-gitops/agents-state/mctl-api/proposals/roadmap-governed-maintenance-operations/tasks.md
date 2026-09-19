# Tasks: governed roadmap maintenance operations

- [ ] 1. Pin the implementation surface to existing `mctl-api` paths: `internal/operations/registry.go`, `internal/operations/executor.go`, `internal/api/handlers_write.go`, `internal/mcp/server.go`, `internal/api/router.go` where needed, `cmd/api/main.go`, and `internal/audit/`; identify the shared `internal/roadmap/` substrate to land from `mctl-api#252`. — DoD: no second approval store, no raw GitHub proxy, and every planned edit has a named file/symbol boundary.
- [ ] 2. Define canonical roadmap target resolution in `mctl-api`: map accepted roadmap refs/work-item IDs to the owning EpicDefinition + bound GitHub issue/Project item using #67's case-insensitive owner/repository + numeric issue key. — DoD: ambiguous/unbound/arbitrary targets fail closed; authored casing is diagnostic only.
- [ ] 3. Add semantic operation contracts for create/update/close/supersede/reparent/set-priority in `internal/operations/registry.go` and mirror them in `internal/mcp/server.go` with explicit risk annotations. — DoD: schemas contain no raw REST/GraphQL/project-field/option parameters and actor identity is never caller supplied.
- [ ] 4. Implement `mctl_roadmap_set_priority` first: server-configured Org Project #1 + priority field/value mapping, canonical item lookup, per-target serialization for MCTL writers, immediate pre-write read/`expected_priority` check, fixed Project mutation, post-write verification, idempotency, policy/auth and audit. — DoD: only P0/P1/P2/PARK is accepted; pre-write mismatch conflicts; retry is a no-op/result replay; docs/tests explicitly do not claim atomic CAS against an external human race that GitHub Project v2 cannot conditionally reject.
- [ ] 5. Land or factor the shared RoadmapProposal persistence/hash substrate specified by open `mctl-api#252` before graph-owned operations depend on it. — DoD: durable proposal lifecycle exists once; READY/reviewable payload is immutable; no alternate approval store is introduced.
- [ ] 6. Define the two hash contracts explicitly: #252-style canonical-JSON `proposal_content_hash` for immutable review content, and #67/#68 `manifest_sha256` over exact EpicDefinition YAML bytes. — DoD: persistence/audit/tests never compare or substitute one hash for the other.
- [ ] 7. Implement create-work-item preview/proposal flow for a migrated epic. `phase` is metadata only. — DoD: no dependency is inferred from phase/parent/sibling order; no GitHub issue is created before the EpicDefinition change is merged; materialization binds to exact merged revision + `manifest_sha256`; retry cannot create duplicates.
- [ ] 8. Implement bounded update-work-item proposal flow. — DoD: only explicitly supported roadmap fields can change; arbitrary issue-body replacement is rejected; phase changes do not imply dependencies.
- [ ] 9. Implement close-work-item validation. Validate full corpus and required/dependent work before producing an approvable change. — DoD: required work or unresolved required dependents fail closed with actionable structured errors.
- [ ] 10. Implement a separate supersede-work-item flow requiring `successor_ref`. — DoD: successor resolves canonically, desired relationships are changed/reviewed/merged before predecessor terminal state, and prose-only supersede metadata cannot satisfy the transition.
- [ ] 11. Implement reparent proposal flow. — DoD: authored parent changes pass full-corpus hierarchy/dependency validation, reject cycles, and never create dependencies from phase/parent order.
- [ ] 12. Integrate graph-owned operations with `.github#68` deterministic apply. `#67` is already satisfied; only graph apply remains gated by #68. Bind execution to exact immutable proposal hash, exact merged EpicDefinition path/git revision/manifest-byte SHA-256, and current observed binding state. — DoD: no LLM in apply; hash/binding mismatch returns conflict before GitHub mutation.
- [ ] 13. Add deterministic idempotency keys and replay handling across all mutation paths. — DoD: repeated submission/retry/replay yields one effective issue/relation/Project mutation and one canonical result.
- [ ] 14. Add audit/evidence fields through `internal/audit/` for actor, semantic operation, canonical target, resolved GitHub/Project refs, `proposal_content_hash`, merged git revision/`manifest_sha256`, before/requested/after priority, approval/policy reference, workflow/run, conflict/no-op/result. — DoD: full issue bodies/prompts/raw payloads are absent.
- [ ] 15. Add auth/policy tests: unauthenticated, non-admin, arbitrary repo/project injection, caller-supplied actor, unsupported priority, raw GraphQL/REST payload attempts. — DoD: all fail closed and no downstream mutation occurs.
- [ ] 16. Add graph-safety tests: canonical-key case variants, create/update phase-no-dependency invariant, required-work close rejection, supersede without successor, dependent-work rejection, reparent cycle, stale proposal hash, stale exact-byte manifest hash, ambiguous binding, and graph mutation disabled while #68 is unmet. — DoD: every case is deterministic and performs zero unsafe writes.
- [ ] 17. Add Project concurrency/idempotency tests with a fixed fake Project adapter. — DoD: expected-value mismatch before write conflicts; identical retry returns prior result; per-target MCTL writers serialize; post-write mismatch is surfaced; test/docs make the external-human race window explicit rather than claiming impossible atomic CAS.
- [ ] 18. Update docs/tool registry/count/schema surfaces consistently and document the source-of-truth split: EpicDefinition graph vs Org Project priority/status. — DoD: generated/OpenAPI/MCP tests and docs checks are green.
- [ ] 19. Run the portfolio-hygiene pilot after release: set `.github#57` P0; set `#66/#18/#35/#42` P1; exercise one reviewed reparent/correction; exercise one safe supersede/close; replay all operations and capture evidence. — DoD: GitHub/Project state matches intended result, RoadmapDiff returns converged for graph-owned changes, and retries produced no duplicate effective writes.

## Tests

- [ ] T1. Tool schemas expose semantic refs only; no arbitrary repository/project/REST/GraphQL parameters.
- [ ] T2. Actor/approver spoof input is rejected/ignored in favor of authenticated context.
- [ ] T3. Unknown, unbound, case-variant ambiguous or otherwise non-canonical roadmap target fails closed.
- [ ] T4. P0/P1/P2/PARK map server-side to configured Project options.
- [ ] T5. Unsupported priority is rejected before GitHub call.
- [ ] T6. Priority expected-value check conflicts on a pre-write mismatch; post-write state is verified; external-human atomic CAS is not claimed.
- [ ] T7. Priority retry is idempotent and concurrent MCTL writers for one target serialize.
- [ ] T8. Create work item produces reviewed and merged desired-state change before issue creation and is duplicate-safe.
- [ ] T9. Create/update phase changes never synthesize dependency edges.
- [ ] T10. Close required work is rejected while canonical manifest still requires it.
- [ ] T11. Supersede without a canonical successor is rejected.
- [ ] T12. Reparent cycle is rejected by full-corpus validation.
- [ ] T13. Canonical-JSON proposal hash and exact-byte manifest SHA are distinct and both mismatches prevent their respective publish/apply steps.
- [ ] T14. Arbitrary repo/project/field injection produces zero downstream writes.
- [ ] T15. Graph operations remain disabled until #68 apply boundary is satisfied; priority remains independently available when its own gate passes.
- [ ] T16. Audit/evidence contains stable refs/results without full body/prompt leakage.
- [ ] T17. Portfolio-hygiene pilot converges and replay produces no duplicates.

## Rollback

Disable/unregister the roadmap-maintenance operations. Priority mutations remain individually reversible and audited. Graph state remains owned by reviewed/merged EpicDefinition revisions, so rollback is a manifest revert followed by the same deterministic reconciliation/apply path; there is no second desired-state store to repair.
