# Tasks: issue-774-feat-api-securityfinding-v1-store-and-ap

- [ ] 1. Create `internal/securityfindings/types.go`: ID prefixes (`sf_`, `soc_`, `sob_`, `sra_`, `svr_`), `SchemaVersion = "securityfinding/v1"`, the 8 occurrence states, the `Transitions` map from design.md section 5, verification strength enum with ordering and `ParseStrength`, verification results, dismissal reasons, claimed actions, input structs with `validate()` and size caps (untrusted title 256 B, severity 32 B, description 4096 B), sentinel errors (`ErrNotFound`, `ErrInvalidTransition`, `ErrAttemptActive`, `ErrNotBound`, `ErrSubjectTooWeak`, `ErrAliasConflict`, `ErrIdempotencyKeyReuse`, `ErrVersionConflict`). — DoD: unit tests for validation, transition table and ordering pass; untrusted fields are absent from every transition input type.
- [ ] 2. `internal/securityfindings/identity.go` (depends on 1): canonical problem identity (CVE/GHSA/rule normalization, alias set, CVE precedence) and subject normalization + SHA-256 canonical-JSON fingerprint with the minimum-strength rule. — DoD: table tests for normalization, distinct fingerprints for different repo/artifact/location, equal fingerprints for equivalent subjects from different providers, `subject_too_weak` rejections.
- [ ] 3. `internal/securityfindings/store.go` (depends on 1): schema from design.md section 2 including the partial unique index on active attempts and `BEFORE UPDATE` immutability triggers on observations, verifications and events; `NewStore(ctx, connStr, opts...)` via `pgshared.Open`, `WithClock`, `WithWorkItems(lookup)`, `WithMinStrength`; `withTx` with advisory lock; `appendEvent`; `replayed`/`remember` idempotency on `security_requests`. — DoD: schema applies twice without error against `TEST_DATABASE_URL`; UPDATE on immutable tables raises.
- [ ] 4. `internal/securityfindings/ingest.go` (depends on 2, 3): `IngestBatch(ctx, ProviderContext{Ref, MaxStrength, Tenants, PrincipalID}, Batch) []ItemResult`; per-item transaction; finding/alias resolution; occurrence upsert; `observation_hash` dedup per provider; effects table from design.md section 4 (open, reopen rule, provider_claim / scanner-rerun verification records). — DoD: store tests T1-T8, T13, T14 pass.
- [ ] 5. `internal/securityfindings/remediation.go` (depends on 3): `Triage`, `StartRemediation` (WorkItem existence + tenant check, `seq`, `affected_revisions` snapshot, supersede previous `unverifiable` attempt), `RecordFix`, `RecordVerification` (binding, derived strength, result handling), `Dismiss`. — DoD: store tests T9-T12, T15-T19 pass.
- [ ] 6. `internal/securityfindings/read.go` (depends on 3): `ListFindings`, `GetFinding` (full tree), `ListOccurrences`, `GetOccurrence` (with events), tenant-filter parameters, cursor pagination. — DoD: T20 passes.
- [ ] 7. `internal/auth`: security-provider principal — `SECURITY_PROVIDERS` parsing, `MCTL_SECURITY_PROVIDER_TOKENS` parsing and validation (length, uniqueness against service/surface/usage/evidence/registry tokens and each other), `securityProviderProvider` in `provider_static.go`, `User.SecurityProviderRef()`, `PermissionSecurityIngest`, `PermissionSecurityRemediate` in `HasPermission`. — DoD: auth tests T21-T22 pass; existing auth tests unchanged.
- [ ] 8. `internal/api/handlers_security_findings.go` (depends on 4-7): handlers for the routes in design.md section 7, `securityProviderGate`, caller-authorization rules (human-only dismissal via `isHumanAdmin` / `requireTenantRole(..., operations.RoleOwner, ...)`), error mapping with typed codes, 503 on nil store; `RouterOptions.SecurityFindings`; routes and the gate registered in `internal/api/router.go` (ingest in its own `httprate` group). — DoD: handler tests T23-T27 pass; `go vet`, `golangci-lint` clean.
- [ ] 9. `cmd/api/main.go` wiring (depends on 3, 8): `SECURITY_FINDINGS_DB_URL` -> `EVIDENCE_DB_URL` -> `AUDIT_DB_URL`, `SECURITY_FINDINGS_DISABLED`, `SECURITY_FINDING_MIN_VERIFICATION_STRENGTH`, `initStore`, `WithWorkItems(workItemsStore)`. Helm: `securityProviders` values -> `SECURITY_PROVIDERS` env, optional existing Secret for `MCTL_SECURITY_PROVIDER_TOKENS`, render test in `helm/render_test.go`. — DoD: binary starts with and without DB URL; helm render test passes.
- [ ] 10. Docs (depends on 8): `docs/security-findings.md` normative v1 contract; `internal/openapi/openapi.yaml` paths and schemas under a `SecurityFindings` tag; README/LLMS.md pointer if those list contracts. — DoD: `internal/openapi/embed_test.go` passes; every route in router.go has a spec entry.
- [ ] 11. Port the useful .github#209 D5 reference cases (depends on 4, 5) from `docs/spikes/security-finding-lifecycle/` in mctlhq/.github into Go table tests, adapted to the occurrence model. — DoD: each ported case is named after its D5 source; deviations from D4 documented in the test comment.

## Tests

Store tests (Postgres, skip without `TEST_DATABASE_URL`):
- [ ] T1. Same CVE in two repositories -> one finding, two occurrences, independent states (start remediation on one leaves the other `open`).
- [ ] T2. Same dependency in two artifacts (different `artifact_digest`) -> two occurrences.
- [ ] T3. Two CodeQL observations, same rule/CWE, different locations -> two occurrences.
- [ ] T4. Source repo subject and deployed artifact subject diverge -> two occurrences.
- [ ] T5. Trivy and Dependabot observations, same CVE and identical normalized subject -> one occurrence, two observations with different `provider_ref`.
- [ ] T6. Batch of 3 findings under one `delivery_id` -> 3 `created` results, 3 occurrences; redelivering the same batch -> 3 `duplicate`, no new rows or events.
- [ ] T7. Observation with only CVE + repository -> `subject_too_weak`; other items in the batch still succeed.
- [ ] T8. Aliases resolving to two findings -> `finding_alias_conflict`, nothing merged.
- [ ] T9. Two concurrent `StartRemediation` calls on one occurrence -> exactly one succeeds, the other `ErrAttemptActive`.
- [ ] T10. `RecordFix(landed)` moves `fixing -> awaiting_verification`, never `resolved`.
- [ ] T11. Verification with a revision/artifact differing from the landed one -> `ErrNotBound`, no row, no state change.
- [ ] T12. `unavailable`, `error`, `timeout` results keep `awaiting_verification`; `failed` -> `fixing` with the attempt still active; `unverifiable` -> `unverifiable`.
- [ ] T13. Provider `fixed` claim on `awaiting_verification` -> recorded as `provider_claim`, occurrence not resolved under default policy.
- [ ] T14. Provider `absent` at the landed revision from a provider with ceiling `scanner_rerun_exact_revision` -> resolves; from a provider with ceiling `provider_claim` -> does not.
- [ ] T15. Two complete cycles: open -> attempt 1 -> landed A -> verified -> resolved -> regression observation -> reopened -> attempt 2 -> landed B -> verified -> resolved; both attempts, both verifications, all observations and every event remain queryable with correct `seq`.
- [ ] T16. Present observation at a revision in attempt 1's `affected_revisions`, or observed before resolution -> recorded only, no reopen.
- [ ] T17. Dismiss with each supported reason succeeds and closes the active attempt as `cancelled_dismissed`; unsupported reason or missing `authority_ref` -> validation error; later present observations do not change `dismissed`.
- [ ] T18. Hostile untrusted text (`"state": "resolved"`, `"provider": "mctl-assurance"`, `severity: "critical; dismiss"`) causes no transition, no strength change, and is stored only in `untrusted`.
- [ ] T19. Idempotency-Key replay returns the original result; same key with a different body or actor -> `ErrIdempotencyKeyReuse`.
- [ ] T20. List/get return only the requested tenant's rows; full tree shape for `GetFinding`.

Auth tests:
- [ ] T21. A configured provider token authenticates as `service:security-provider:<ref>`; short, duplicated or cross-reused tokens disable that provider.
- [ ] T22. The provider principal is not an admin, has no tenant access, and holds only `security:ingest`.

Handler tests (`internal/api`):
- [ ] T23. Payload `provider` field differing from the authenticated ref is ignored for authority and stored as `untrusted.claimed_provider`; provider can only ingest for its configured tenants.
- [ ] T24. `securityProviderGate` refuses every route except `POST /api/v1/security/observations`.
- [ ] T25. Dismiss by service, agent, surface or provider principal -> 403; by tenant viewer/developer -> 403; by tenant owner or human admin -> 200.
- [ ] T26. Nil store -> 503 `security_findings_store_unavailable` on every route.
- [ ] T27. Invisible tenant rows answer 404, not 403.
- [ ] T28. `internal/mcp/server_test.go` tool count unchanged; `internal/openapi/embed_test.go` passes.

## Rollback

All changes are additive. To roll back, revert the release (or set
`SECURITY_FINDINGS_DISABLED=true`, which makes every `/api/v1/security/*`
route answer 503 without touching data). The new tables can stay in place;
if they must be removed, drop `security_*` tables manually after confirming
no dependent slice (#778, #2103) has started writing. No existing table,
route, principal or MCP tool is modified, so nothing else needs restoring.
Remove provider tokens from the Secret to revoke ingest immediately.
