# Tasks: governed roadmap maintenance operations

- [ ] 1. Inventory the existing roadmap proposal/API, operation registry, audit, policy/risk, Temporal submission, and GitHub credential boundaries in `mctl-api`, `mctl-agents`, and `mctl-gitops`. — DoD: implementation notes identify the exact reusable symbols/files and confirm no second approval store or raw GitHub proxy is needed.
- [ ] 2. Define canonical roadmap target resolution in `mctl-api`: map accepted roadmap refs/work-item IDs to the owning EpicDefinition + bound GitHub issue/Project item without caller-controlled repository/project identifiers. — DoD: ambiguous/unbound/arbitrary targets fail closed with structured errors.
- [ ] 3. Add semantic operation contracts for create/update/close/reparent/set-priority and register them in MCP/OpenAPI with explicit risk levels. — DoD: schemas contain no raw REST/GraphQL/project-field/option parameters and actor identity is never caller supplied.
- [ ] 4. Implement `mctl_roadmap_set_priority` first: server-configured Org Project #1 + priority field/value mapping, canonical item lookup, current-value read, compare-and-set mutation, idempotency, policy/auth, and audit. — DoD: only canonical P0/P1/P2/PARK mapping is accepted; concurrent human change returns conflict; retry is a no-op/result replay.
- [ ] 5. Reuse/extend `RoadmapProposal` from `mctl-api#252` for graph-owned semantic mutations. Persist exact current manifest path/revision/hash plus proposed resulting hash/operation target. — DoD: repeated reads return immutable review content/hash; no alternate editable graph copy exists.
- [ ] 6. Implement create-work-item preview/proposal flow for a migrated epic. — DoD: no GitHub issue is created before reviewed desired state exists; retry cannot produce duplicate issues.
- [ ] 7. Implement bounded update-work-item proposal flow. — DoD: only explicitly supported roadmap fields can be changed; arbitrary issue-body replacement is rejected.
- [ ] 8. Implement close/supersede validation. Validate full corpus and required/dependent work before producing an approvable change. — DoD: required work or unresolved required dependents fail closed with actionable structured errors.
- [ ] 9. Implement reparent proposal flow. — DoD: authored parent changes pass full-corpus hierarchy/dependency validation, reject cycles, and never create dependencies from phase/parent order.
- [ ] 10. Integrate graph-owned operations with `.github#68` deterministic apply only after `.github#67` is proven. Bind execution to exact reviewed EpicDefinition path/git revision/content hash and current observed binding state. — DoD: no LLM in apply; hash/binding mismatch returns conflict before GitHub mutation.
- [ ] 11. Add deterministic idempotency keys and replay handling across all mutation paths. — DoD: repeated submission/retry/replay yields one effective issue/relation/Project mutation and one canonical result.
- [ ] 12. Add audit/evidence fields for actor, semantic operation, canonical target, resolved GitHub/Project references, manifest revision/hash or before/after priority, approval/policy reference, workflow/run, conflict/no-op/result. — DoD: full issue bodies/prompts/raw payloads are absent from audit.
- [ ] 13. Add auth/policy tests: unauthenticated, non-admin, arbitrary repo/project injection, caller-supplied actor, unsupported priority, raw GraphQL/REST payload attempts. — DoD: all fail closed and no downstream mutation occurs.
- [ ] 14. Add graph-safety tests: required-work close rejection, dependent-work rejection, reparent cycle, stale manifest hash, ambiguous binding, concurrent external change, mutation disabled while #67/#68 gates are unmet. — DoD: every case is deterministic and performs zero unsafe writes.
- [ ] 15. Add Project concurrency/idempotency tests with a fake/fixed GitHub Project adapter. — DoD: observed-value mismatch yields conflict; identical retry returns prior result; fixed GraphQL implementation never accepts caller query/variables.
- [ ] 16. Update docs/tool registry/count/schema surfaces consistently and document the source-of-truth split: EpicDefinition graph vs Org Project priority/status. — DoD: generated/OpenAPI/MCP tests and docs checks are green.
- [ ] 17. Run the portfolio-hygiene pilot after release: set `.github#57` P0; set `#66/#18/#35/#42` P1; exercise one reviewed reparent/correction; exercise one safe supersede/close; replay all operations and capture evidence. — DoD: GitHub/Project state matches intended result, RoadmapDiff returns converged for graph-owned changes, and retries produced no duplicate effective writes.

## Tests

- [ ] T1. Tool schemas expose semantic refs only; no arbitrary repository/project/REST/GraphQL parameters.
- [ ] T2. Actor/approver spoof input is rejected/ignored in favor of authenticated context.
- [ ] T3. Unknown or ambiguous roadmap target fails closed.
- [ ] T4. P0/P1/P2/PARK map server-side to configured Project options.
- [ ] T5. Unsupported priority is rejected before GitHub call.
- [ ] T6. Priority compare-and-set succeeds on expected value and conflicts on concurrent human edit.
- [ ] T7. Priority retry is idempotent.
- [ ] T8. Create work item produces reviewed desired-state change before issue creation and is duplicate-safe.
- [ ] T9. Close required work is rejected while canonical manifest still requires it.
- [ ] T10. Reparent cycle is rejected by full-corpus validation.
- [ ] T11. Manifest hash/revision mismatch prevents apply.
- [ ] T12. Arbitrary repo/project/field injection produces zero downstream writes.
- [ ] T13. Graph operations remain disabled until #67 detector proof and #68 apply boundary are satisfied.
- [ ] T14. Audit/evidence contains stable refs/results without full body/prompt leakage.
- [ ] T15. Portfolio-hygiene pilot converges and replay produces no duplicates.

## Rollback

Disable/unregister the roadmap-maintenance operations. Priority mutations remain individually reversible and audited. Graph state remains owned by reviewed EpicDefinition revisions, so rollback is a manifest revert followed by the same deterministic reconciliation path; there is no second desired-state store to repair.
