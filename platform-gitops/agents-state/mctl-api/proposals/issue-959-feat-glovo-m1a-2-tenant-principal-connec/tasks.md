# Tasks: issue-959-feat-glovo-m1a-2-tenant-principal-connec

- [ ] 1. Create `internal/glovo/types.go` and `internal/glovo/ids.go` in #977's existing package. Add `InstallState`, `ConnectionState`, the `transitions` table, `CanTransition`, `Live()`, `Owner.validate()` (non-empty tenant, `prn_` principal), the full closed refusal enum of the joint contract as `glovo.Code` constants with one fixed description each, `glovo.Status(code)`, a single `ErrNotFound`, and `newPrefixedID` for `gin_`/`gcn_`/`gae_`/`gsr_` (a copy of the `commerce.newULID` minting) — DoD: unit tests for every allowed/forbidden transition pass; `(*glovo.Error).Error()` contains only the code and its fixed description; every code maps to exactly one status.
- [ ] 2. Create `internal/glovo/secretref.go` with `SecretRef`, the `SecretRefs` interface and `RefusingSecretRefs`; the doc comment describes the future DEK/KEK envelope as a design note and does not use the term crypto-shredding (depends on 1) — DoD: compiles; `RefusingSecretRefs` returns `ErrSecretBackendUnavailable` from both methods.
- [ ] 3. Create `internal/glovo/schema.go` with `glovoSchema`: the four `glovo_*` tables, the partial unique index `glovo_connections_one_live`, the other indexes, the named CHECKs added via the `DO $$` + `pg_constraint` + `duplicate_object` pattern from `internal/commerce/store.go`, the always-refusing `glovo_audit_immutable()` UPDATE/DELETE trigger without an application-writable override, and the unconditional no-DELETE trigger on `glovo_connections` (pattern from `internal/decisions/store.go`) (depends on 1) — DoD: schema applies twice in a row without error on postgres:16.
- [ ] 4. Create `internal/glovo/store.go` with `ApplySchema(ctx, migrationConnStr)` (migration role; schema in one transaction under `pg_advisory_xact_lock(hashtext('glovo-schema'))`, then runtime GRANTs and the schema version row) and `NewStore(ctx, runtimeConnStr)` (uses `pgshared.Open`, runs no DDL, fails closed on a missing or different schema version), `Close`, option `WithClock` (retention maintenance deferred to separately approved privileged mechanism), and `withLocks(tenant, principal, installMode)` taking the shared or exclusive install key and then the owner key, both length-prefixed (depends on 3) — DoD: `NewStore` returns a wrapped error and releases the pool when the schema version check fails; `NewStore` issues no DDL (statement log test).
- [ ] 5. Implement `Install`, `GetInstall`, `RevokeInstall` and `Reinstall`. Revoke/reinstall take the exclusive install lock, check `expectedRevision` (`stale_install`), move the revision or state, revoke every live connection of older revisions with reason `install_revoked`/`install_reinstalled`, clear their `secret_ref`, append audit events, and return the ended connections (depends on 4) — DoD: DB tests T5 and T6 pass.
- [ ] 6. Implement `Connect`, `Reconnect`, `Transition`, `Revoke`, `GetConnection` and `LiveConnection`. All take the shared install lock and the owner lock, use owner-scoped single-statement lookups that return `ErrNotFound`, handle idempotency through `glovo_connect_requests` with a request hash, map a unique violation on `glovo_connections_one_live` to `connection_exists`, give reconnect a new `gcn_` with `supersedes_id`, and append an audit event on each state change in the same transaction (depends on 4, 5) — DoD: DB tests T2-T4 and T7-T9 pass.
- [ ] 7. Implement `ListAudit` as a tenant/owner-bound read only. There is **no runtime `SweepAudit` or GUC bypass** in this slice; record a separately gated retention maintenance plan (depends on 3, 4) — DoD: T10 proves immutable audit.
- [ ] 8. Add `internal/glovo/fixtures_test.go`: synthetic tenants `tg959-alpha-*`/`tg959-beta-*`, principals A1 and A2 in alpha and B1 in beta, foreign/never-existing `gcn_` IDs, stale revision and stale version helpers, and cleanup in a disposable test schema/database with a non-superuser runtime role (no trigger bypass, no `session_replication_role`, no global data deletion) (depends on 6) — DoD: tests are independent and parallel-safe.
- [ ] 9. Write `docs/glovo-connections.md`: data model, state diagram, lock order, refusal codes, retention, the explicit non-goals of this slice, and the manual down-migration script (depends on 6, 7) — DoD: the doc matches the code's constants.
- [ ] 10. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./internal/glovo/...` with `TEST_DATABASE_URL`; confirm `git diff` does not touch `cmd/api/main.go`, `internal/api/router.go` or `internal/mcp/server.go` (depends on 1-9) — DoD: CI `validate.yml` is green; the MCP tool count is unchanged.

## AMEND 2026-11-08 — additional non-superuser and audit tamper tests

- [ ] A1. Audit UPDATE and DELETE always fail for runtime application role. `SET LOCAL glovo.retention_sweep = 'on'` does NOT bypass the guard. Runtime role is not the schema/table owner.
- [ ] A2. No `session_replication_role = replica`, trigger disablement or superuser-only cleanup in fixtures. Test using isolated schema/database and dedicated test-owner role; never touch another service's tables.
- [ ] A3. Remove M1 `SweepAudit` runtime API and GUC-bypass semantics. Define retention obligations/document future separate privileged maintenance issue, without silently relaxing immutable audit.
- [ ] A4. CI PostgreSQL test as **non-superuser** verifies all negative cases, including concurrent connect/revoke and forbidden raw SQL updates. Missing DB tests must fail, not silently skip.

## AMEND 2026-11-09 — joint 959/960/961 contract

- [ ] A5. Split DDL from runtime: `ApplySchema` under a migration role, `NewStore` without DDL, runtime grants DML only (depends on 3, 4) — DoD: T14 passes.
- [ ] A6. Add `glovo_connections.expires_at`, `glovo_audit_events.actor_kind` with its CHECK, `glovo_pilot_allowlist` with `IsAllowlisted` (read only) and `glovo_schema_version` (depends on 3) — DoD: T12 still passes; names match the joint contract table exactly.
- [ ] A7. Route every terminal transition through one `endConnection` helper implementing the terminal-state purge table (depends on 5, 6) — DoD: T15 passes.
- [ ] A8. Document the joint contract (names, enum, status mapping, error body, kill switch) in `docs/glovo-connections.md` as the single reference for #960 and #961 (depends on 9).

## Tests

- [ ] T1. Unit, no DB: the transition table is exhaustive (every from/to pair checked), terminal states have no exits, `Owner.validate` rejects an empty tenant and a principal without the `prn_` prefix, and the ID prefixes and lengths are correct.
- [ ] T2. Isolation matrix: A1 connects. A2 (same tenant), B1 (other tenant) and A1 with a never-existing `gcn_` each call `GetConnection`, `Transition` and `Revoke`. All nine calls return `errors.Is(err, ErrNotFound)` with an identical `err.Error()`, and A1's row is unchanged (same version, no new audit event).
- [ ] T3. One live connection per owner: A1 `Connect` twice with different keys returns `connection_exists`. A1 and A2 can each hold one live connection at once, and so can B1.
- [ ] T4. Idempotency: the same key and arguments return `Replayed=true` with the same `gcn_`. The same key with a different expected revision returns `idempotency_key_reused`. 20 concurrent connects with one key produce exactly one row.
- [ ] T5. Stale install: `Connect` with `ExpectedInstallRevision = current-1` returns `stale_install`. `Connect` on a tenant without an install returns `no_install`, and so does `Connect` after `RevokeInstall`.
- [ ] T6. Reinstall atomicity: after A1 and A2 connect, `Reinstall` bumps the revision by 1 and revokes both with reason `install_reinstalled`. B1 is untouched. A new connect at the new revision succeeds and gets a new `gcn_`.
- [ ] T7. Race: 50 iterations run A1 `Connect` concurrently with `Reinstall`, separately with `RevokeInstall`, and separately with `Revoke` of A1's prior connection. After both finish, no live connection has `install_revision` below the install's current revision, and at most one live connection exists for A1.
- [ ] T8. Reconnect: the old connection is `revoked` (`superseded`) and the new one has a different `gcn_` and `supersedes_id` set to the old ID. A retry with the same key returns the same new ID (no third ID). Reconnect naming a foreign prior ID returns `ErrNotFound`.
- [ ] T9. Transitions in the DB: the happy path `pending_handoff -> pending_provider -> active -> revoked`. A stale `expectedVersion` returns `stale_version`. A forbidden edge (`revoked -> active`) returns `invalid_transition`. A terminal transition clears `secret_ref` and returns the released ref. A raw SQL update to an unknown state fails the CHECK.
- [ ] T10. Audit: each state change writes exactly one `gae_` event. A raw `UPDATE` and a raw `DELETE` on `glovo_audit_events` both fail. `SweepAudit` is unavailable; test that forged `SET LOCAL glovo.retention_sweep='on'` cannot enable UPDATE/DELETE of audit rows or connection rows. A raw `DELETE` on `glovo_connections` fails.
- [ ] T11. Transaction rollback: a test hook (`s.failAfterWrite`, unexported) forces an error after the connection insert. Afterwards there is no connection row, no audit event and no idempotency row.
- [ ] T12. Schema safety: `NewStore` called twice concurrently on a fresh database both succeed. Re-applying the schema on a database where a CHECK already exists is a no-op. No non-`glovo_` object is created or altered (queried via `pg_class`/`pg_proc` before and after).
- [ ] T14. Role separation: with the runtime role, `ALTER TABLE glovo_audit_events DISABLE TRIGGER ALL`, `DROP TRIGGER`, `DROP TABLE` and `ALTER TABLE ... ADD COLUMN` on every `glovo_*` table all fail with insufficient privilege; `NewStore` against a database without `ApplySchema` refuses to start.
- [ ] T15. Terminal-state purge: for each terminal path (`expired`, `failed`, `revoked`, `superseded`, `install_revoked`, `install_reinstalled`) `secret_ref` is NULL afterwards and the released ref is returned exactly once.
- [ ] T13. No secrets or PII: `secretscan.Scan` over JSON of every fixture, connection row and audit row, and over captured `slog` output, finds nothing. Fixtures contain no `@` (emails) and no cookie or session-shaped strings.

## Rollback

- Code: revert the PR. Nothing outside `internal/glovo/` and
  `docs/glovo-connections.md` changes, and no route, MCP tool or startup
  wiring is added, so a revert has no runtime effect.
- Data: this slice does not construct the store in `cmd/api/main.go`, so no
  production database receives the schema. If a later slice has applied
  it, the manual down script in `docs/glovo-connections.md` drops the
  triggers, then the functions `glovo_audit_immutable()` and the
  connection no-delete function, then the tables `glovo_connect_requests`,
  `glovo_audit_events`, `glovo_connections`, `glovo_installs`,
  `glovo_pilot_allowlist` and `glovo_schema_version`, in that order, run by
  the migration role. Only synthetic data ever exists in them.
