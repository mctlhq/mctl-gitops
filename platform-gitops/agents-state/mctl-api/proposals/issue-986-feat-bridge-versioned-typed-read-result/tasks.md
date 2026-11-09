# Tasks: issue-986-feat-bridge-versioned-typed-read-result

Blocking dependency (amended 2026-11-09 (b)): mctlhq/mctl-agents#1059 approved and
merged. Without it no task starts.

- [ ] 1. Vendor the #1059 v1alpha2 files into `internal/bridge/schema/v1alpha2/`
  (schemas, fixtures, digest vectors) with a `PROVENANCE` file (repo, PR, merge commit,
  sha256 per file) and a `TestVendoredV1alpha2MatchesProvenance`. DoD: no file differs
  from #1059; v1alpha1 files and their pin test are unchanged.
- [ ] 2. Versioning in `schema.go` and `store.go` (depends on 1):
  - `compileSchemas()` compiles both versions; `ParseResult` selects by `schema_version`;
  - `SubmitResult` (`store.go:745`) accepts v1alpha2 only for a v1alpha2 command;
  - `validate()` (`store.go:229-256`) gets the read-kind branch of design §2;
  - `projection()` (`store.go:334`) emits the stored `wire_version`;
  - `BridgeProviderConfig.SupportedVersions` (default `[v1alpha1]`), `Claim` leases read
    kinds only to v1alpha2-capable providers, versioned claim envelope
    (`handlers_bridge.go:200`) (OPEN-1059-2).
  DoD: all v1alpha1 tests pass unchanged.
- [ ] 3. Idempotent schema (depends on 2): the guarded `DO` block of design §4, the
  `bridge_read_results` table and the `bridge_commands_read_request` index, inside #985's
  `bridge.ApplySchema` under the migration role (amended (c)). DoD: applying it twice,
  and on a database with v1alpha1 rows, succeeds; the statement log of the second run
  contains no `ALTER TABLE`; the runtime role cannot run it.
- [ ] 3b. `internal/bridge/rawcheck.go`: token-level pre-check of design §5 step 3 (depends
  on 1). DoD: every vendored `must-reject.json` entry is rejected; every valid fixture
  passes.
- [ ] 4. `EnqueueRead` (the row values of design §3), `submitTx` read branch (no outbox
  row, result row in the same tx), `expireTx` read branch (no outbox row), `permitTx`
  refusing read kinds, `FetchReadResult` with the checks of design §5, and
  `ReadClient.Read` with the deadline and cancel-on-timeout of design §3 (depends on 3).
- [ ] 5. `ConnectionChecker`: the interface, `DenyConnectionChecker` as default, and an
  adapter over #959 `LiveConnection(ctx, glovo.Owner)` (amended (c)) wired when #959 is
  present. DoD: nil or missing #959 store keeps the deny default.
- [ ] 6. `bridgeStatus` (`handlers_bridge.go:95-113`): explicit cases for
  `ErrReadUnavailable`, `ErrReadNotAuthorized` and `payload_too_large`. No new route.
- [ ] 7. `EraseExpiredReads` in the `Expirer` tick (erase, then delete after 24 h), the
  metric, and `MCTL_BRIDGE_READ_RESULT_TTL` with the clamp.
- [ ] 8. Docs: `docs/bridge.md` gets a v1alpha2 read section (in-process only, no route,
  pointer to #1059). Run `go fmt`, `go vet`, `golangci-lint`, `go test ./...`.

## Tests

- [ ] T1. The vendored files match `PROVENANCE`; a one-byte change fails the test.
- [ ] T2. Every #1059 valid fixture parses; every invalid fixture fails with the same
  named reason as in #1059.
- [ ] T3. The #1059 digest vectors reproduce byte for byte through the Go JCS
  implementation.
- [ ] T4. v1alpha1 golden projection and result digests are unchanged.
- [ ] T5. A read command has `''` as `workflow_id`, `order_ref`, `execution_id` and
  `work_item_id`, and its completion writes no `bridge_signal_outbox` row.
- [ ] T5c. Round 3 (N1): two concurrent reads from two tenants, and two reads from one principal, all enqueue and are claimable together (no `unique_violation`, no read waits on another); after `ApplySchema` the index definition carries the read-kind predicate, a second run is a no-op, and a v1alpha1 execution's `sequence` ordering and duplicate-`sequence` refusal are unchanged.
- [ ] T5b. An expired read command writes no `bridge_signal_outbox` row, and `ExpireDue`
  in the same batch still expires a v1alpha1 write command and writes its outbox row.
- [ ] T6. A non-read command with an empty `workflow_id` or `order_ref` is rejected by
  the CHECK (raw SQL); no column of `bridge_commands` is nullable that was not before.
- [ ] T7. Submission refusals: wrong `schema_version`, effect other than `none`, payload
  on a failed outcome, `JCS(payload)` of 12289 bytes, the #1059 `over-cap` fixture,
  digest mismatch, a result carrying any binding ref, a result of another kind, a result
  after `expires_at`, a different `request_id`, every `must-reject.json` entry,
  `quantity: 1.0`, and a read payload on `place_order_fake`, each with the code of the
  design §5 pipeline. The #1059 `at-cap` fixture is accepted.
- [ ] T7b. `lease_token` never appears in `bridge_commands.result`,
  `bridge_read_results`, `bridge_command_transitions`, logs or audit rows after a read
  round trip (amended (c): `bridge_commands.lease_token` stores it by design).
- [ ] T7c. Versioning: a provider configured `[v1alpha1]` never receives a read-kind
  command from `Claim`; one configured with v1alpha2 does; an unclaimed read command
  expires.
- [ ] T7d. A provider queue with mixed read and v1alpha1 write commands: `Claim`,
  `Cancel`, `IssueWritePermit` (refused for the read) and `ExpireDue` all succeed on both
  kinds; nothing fails to scan.
- [ ] T8. Replay returns the same `res_`; a different digest gives `result_conflict`.
- [ ] T9. Round trip: a payload submitted with shuffled keys is stored canonically, and
  `FetchReadResult` returns bytes whose digest equals `payload_digest`. A stored byte
  flipped by raw SQL makes the fetch fail closed.
- [ ] T10. Fetch scope: another tenant, another owner and an unknown `res_` give the same
  sentinel; missing `glovo:read` gives `ErrReadNotAuthorized`.
- [ ] T10b. Round 3: `FetchReadResult` called directly with principal B's id against
  principal A's `res_` gives `ErrCommandNotFound` (the cross-owner case; it does not go
  through the A12 adapter, which always enqueues a new command). The `pho_`/cursor origin
  check (#1059 MUST 10) is #957 T7a, not a #986 test.
- [ ] T11. Fetch after expiry or erase gives `ErrCommandExpired`.
- [ ] T12. Connection: revoked, expired, absent and moved install revision each refuse;
  a checker error gives `ErrReadUnavailable`; the default checker denies. Round 3 (X-2): a row stored at revision N with live revision N+1 is refused `ErrBindingMismatch` (decimal comparison; the `irv_` plays no part), and `EnqueueRead` refuses a request whose `InstallRevision` or `InstallRevisionRef` is empty.
- [ ] T13. `ReadClient.Read` timeout cancels the command and returns
  `ErrReadUnavailable`; a late result for the cancelled command is refused.
- [ ] T14. Erase and delete: bytes are NULL after `expires_at`, the row is gone 24 h
  later, no tenant label on the metric.
- [ ] T15. No route: the full route list, the MCP tool list and the Temporal workflow
  and signal registrations are diffed before and after; nothing is added, and
  `glovoAudienceRoutes` is unchanged.
- [ ] T16. Schema idempotency: `bridge.ApplySchema` applied twice on an empty database
  and on a populated v1alpha1 database; the statement log (`log_statement = 'ddl'`) of
  the second run contains no `ALTER TABLE`.
- [ ] T17. Log hygiene: captured logs and audit rows across T7-T13 contain no payload
  bytes.

## Rollback

- Before reverting the code, cancel or expire every open read-kind command
  (`docs/bridge.md` procedure), so no provider holds a lease on a kind the old code
  cannot parse.
- Then revert the PR. The added columns, the CHECKs (no NOT NULL was relaxed), the index and `bridge_read_results` are harmless to v1alpha1 and can stay;
  they can be dropped in a follow-up after the table is empty.
